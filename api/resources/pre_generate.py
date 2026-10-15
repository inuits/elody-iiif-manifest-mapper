"""
Batch pre-generation endpoint for IIIF Manifests.

Generates the manifest of every mediafile for a given config ahead of a
canopy site build and caches it, so the build's manifest requests are served
instantly instead of each triggering several collection-api lookups.

Manifests are built by exactly the same code as an on-demand request
(ConfigurableManifestGenerator.generate_manifest), so a cached manifest is
identical to what /iiif/<id>/manifest would return. Lookups shared between
mediafiles (parent media, albums, creators, licenses) are fetched once per
run through the generator's response cache, which is switched off again
afterwards.

The cache is kept on disk (MANIFEST_CACHE_DIR) rather than in process memory:
gunicorn runs several workers, and whichever one serves a manifest request
must see what the pre-generate run wrote. Reading from disk every time also
means a later run's manifests are never shadowed by an older in-memory copy.
"""

import hashlib
import json
import logging
import os
import tempfile
import time
from pathlib import Path

from collection_config import CollectionConfig
from flask import request
from flask_restful import Resource
from manifest_generator import ConfigurableManifestGenerator

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = "/tmp/iiif-manifest-cache"


def _cache_dir() -> Path:
    return Path(os.getenv("MANIFEST_CACHE_DIR", DEFAULT_CACHE_DIR))


def _cache_path(key: tuple) -> Path:
    digest = hashlib.sha256(json.dumps(list(key)).encode()).hexdigest()
    return _cache_dir() / f"{digest}.json"


def cache_key(entity_id: str, config_file: str | None, image_base_url: str | None):
    """Key of a cached manifest, matching an /iiif/<id>/manifest request."""
    return (entity_id, config_file or "", image_base_url or "")


def store_manifest(key: tuple, manifest: dict) -> None:
    """Write a manifest to the shared cache (atomically, for concurrent readers)."""
    _cache_dir().mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=_cache_dir(), suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(manifest, f)
        tmp.replace(_cache_path(key))
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def get_cached_manifest(key: tuple) -> dict | None:
    """Return the cached manifest for key, or None when there is none."""
    try:
        with _cache_path(key).open() as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        logger.warning(f"Manifest cache: unreadable entry for {key}: {e}")
        return None


def _cache_size() -> int:
    if not _cache_dir().exists():
        return 0
    return sum(1 for p in _cache_dir().iterdir() if p.suffix == ".json")


class PreGenerate(Resource):
    """
    POST /pre-generate — Batch-generate all mediafile manifests.

    Query Parameters:
        config_file: Config file name (e.g. "wetenschatten")
        image_base_url: Optional image base URL override
        max_parents: Optional limit on the number of parent media handled

    Returns the number of generated manifests.
    """

    def __init__(self):
        self.generator = ConfigurableManifestGenerator()

    def post(self):
        config_file = request.args.get("config_file", "wetenschatten")
        image_base_url = request.args.get("image_base_url", type=str)
        max_parents = request.args.get("max_parents", default=0, type=int)
        body = request.get_json(silent=True) or {}
        parent_ids = body.get("parentIds") if isinstance(body, dict) else None

        auth_header = request.headers.get("Authorization")
        if auth_header:
            self.generator.headers["Authorization"] = auth_header

        start = time.time()
        count = self._generate_all(
            config_file,
            image_base_url,
            max_parents=max_parents,
            parent_ids=parent_ids,
        )
        elapsed = time.time() - start

        return {
            "status": "ok",
            "manifests_generated": count,
            "cache_size": _cache_size(),
            "elapsed_seconds": round(elapsed, 1),
        }, 200

    def _generate_all(
        self,
        config_file: str,
        image_base_url: str | None = None,
        max_parents: int = 0,
        parent_ids: list[str] | None = None,
    ) -> int:
        """Generate and cache mediafile manifests, per parent.

        With parent_ids, only the mediafiles of those parents (e.g. the media
        in a canopy build's collections); otherwise every mediafile.
        """
        gen = self.generator
        # Fail fast on an unknown config, before any collection-api work.
        CollectionConfig.from_json_file(config_file)

        gen._response_cache = {}
        try:
            if parent_ids is not None:
                by_parent = self._mediafiles_of_parents(parent_ids)
            else:
                by_parent = self._mediafiles_by_parent()
            logger.info(f"Pre-generate: {len(by_parent)} unique parents")

            parent_items = list(by_parent.items())
            if max_parents > 0:
                parent_items = parent_items[:max_parents]

            count = 0
            failed = 0
            for i, (parent_id, mediafile_ids) in enumerate(parent_items):
                logger.info(
                    f"Pre-generate: [{i + 1}/{len(parent_items)}] "
                    f"parent {parent_id or '-'}: {len(mediafile_ids)} mediafiles"
                )
                for mf_id in mediafile_ids:
                    try:
                        manifest = gen.generate_manifest(
                            entity_id=mf_id,
                            config_file=config_file,
                            image_base_url=image_base_url,
                        )
                        store_manifest(
                            cache_key(mf_id, config_file, image_base_url), manifest
                        )
                        count += 1
                    except Exception as e:  # noqa: BLE001
                        failed += 1
                        logger.warning(f"Pre-generate: failed for {mf_id}: {e}")
        finally:
            gen._response_cache = None

        logger.info(
            f"Pre-generate: done. {count} manifests cached, {failed} failed "
            f"(cache_size={_cache_size()})."
        )
        return count

    def _mediafiles_by_parent(self) -> dict[str, list[str]]:
        """Ids of every mediafile, grouped by parent (belongsTo)."""
        logger.info("Pre-generate: fetching all mediafiles...")
        all_mediafiles = self._get_all_entities("mediafile")
        logger.info(f"Pre-generate: found {len(all_mediafiles)} mediafiles")
        by_parent: dict[str, list[str]] = {}
        for mf in all_mediafiles:
            mf_id = mf.get("_id") or mf.get("id")
            if not mf_id:
                continue
            parent_id = next(
                (
                    rel.get("key")
                    for rel in mf.get("relations", []) or []
                    if rel.get("type") == "belongsTo"
                ),
                None,
            )
            by_parent.setdefault(parent_id or "", []).append(mf_id)
        return by_parent

    def _mediafiles_of_parents(self, parent_ids: list[str]) -> dict[str, list[str]]:
        """Ids of the mediafiles of each given parent."""
        gen = self.generator
        by_parent: dict[str, list[str]] = {}
        for parent_id in dict.fromkeys(parent_ids):
            try:
                parent = gen._get_from_collection_api(
                    f"/entities/{parent_id}", entity=True
                )
                mediafiles = gen._get_mediafiles_for_entity(parent)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Pre-generate: no mediafiles for {parent_id}: {e}")
                continue
            by_parent[parent_id] = [
                mf_id for mf in mediafiles if (mf_id := mf.get("_id") or mf.get("id"))
            ]
        return by_parent

    def _get_all_entities(self, entity_type: str) -> list:
        """Fetch all entities of a given type (paginated)."""
        all_entities = []
        offset = 0
        limit = 500

        while True:
            response = self.generator._get_from_collection_api(
                f"/entities?type={entity_type}&limit={limit}&skip={offset}"
            )
            results = (
                response.get("results", []) if isinstance(response, dict) else response
            )
            if not results:
                break
            all_entities.extend(results)
            if len(results) < limit:
                break
            offset += limit

        return all_entities
