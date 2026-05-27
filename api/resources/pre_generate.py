"""
Batch pre-generation endpoint for IIIF Manifests.

Generates all mediafile manifests for a given config and caches them
in-memory so subsequent requests are instant.
"""

import logging
import re
import time

from flask import request
from flask_restful import Resource

from manifest_generator import ConfigurableManifestGenerator
from collection_config import CollectionConfig

logger = logging.getLogger(__name__)

# Global manifest cache: (entity_id, config_file, image_base_url) -> manifest dict
manifest_cache = {}


class PreGenerate(Resource):
    """
    POST /pre-generate — Batch-generate all mediafile manifests.

    Efficiently generates manifests by grouping mediafiles per parent
    entity, doing only 1 parent + creator lookup per group.

    Query Parameters:
        config_file: Config file name (e.g. "wetenschatten")
        image_base_url: Optional image base URL override

    Returns count of generated manifests.
    """

    def __init__(self):
        self.generator = ConfigurableManifestGenerator()

    def post(self):
        config_file = request.args.get("config_file", "wetenschatten")
        image_base_url = request.args.get("image_base_url", type=str)
        max_parents = request.args.get("max_parents", default=0, type=int)

        auth_header = request.headers.get("Authorization")
        if auth_header:
            self.generator.headers["Authorization"] = auth_header

        start = time.time()
        count = self._generate_all(config_file, image_base_url, max_parents=max_parents)
        elapsed = time.time() - start

        return {
            "status": "ok",
            "manifests_generated": count,
            "cache_size": len(manifest_cache),
            "elapsed_seconds": round(elapsed, 1),
        }, 200

    def _generate_all(self, config_file: str, image_base_url: str = None, max_parents: int = 0) -> int:
        """Generate all mediafile manifests grouped by parent media entity."""
        global manifest_cache

        # Load config
        config = CollectionConfig.from_json_file(config_file)

        # Store image base URL
        self.generator._image_base_url = image_base_url.rstrip("/") if image_base_url else None
        self.generator._config = config

        # Fetch ALL mediafiles and group by parent (belongsTo relation)
        logger.info("Pre-generate: fetching all mediafiles...")
        all_mediafiles = self._get_all_entities("mediafile")
        logger.info(f"Pre-generate: found {len(all_mediafiles)} mediafiles")

        # Group by parent ID
        by_parent = {}
        for mf in all_mediafiles:
            parent_id = None
            for rel in mf.get("relations", []):
                if rel.get("type") == "belongsTo":
                    parent_id = rel.get("key")
                    break
            if parent_id:
                by_parent.setdefault(parent_id, []).append(mf)

        logger.info(f"Pre-generate: {len(by_parent)} unique parents")

        # Fetch parent entities and resolve metadata once per parent
        count = 0
        parent_cache = {}

        parent_items = list(by_parent.items())
        if max_parents > 0:
            parent_items = parent_items[:max_parents]

        for i, (parent_id, mediafiles) in enumerate(parent_items):
            # Fetch parent entity (media entity) once
            if parent_id not in parent_cache:
                try:
                    parent_entity = self.generator._get_from_collection_api(
                        f"/entities/{parent_id}", entity=True
                    )
                    parent_metadata = self._resolve_parent_metadata(
                        parent_entity, config
                    )
                    parent_cache[parent_id] = parent_metadata
                except Exception as e:
                    logger.warning(f"Pre-generate: failed to fetch parent {parent_id}: {e}")
                    parent_cache[parent_id] = []

            parent_metadata_items = parent_cache[parent_id]

            logger.info(
                f"Pre-generate: [{i+1}/{len(by_parent)}] "
                f"parent {parent_id}: {len(mediafiles)} mediafiles"
            )

            for mediafile in mediafiles:
                mf_id = mediafile.get("_id") or mediafile.get("id")
                if not mf_id:
                    continue

                cache_key = (mf_id, config_file, image_base_url or "")

                try:
                    manifest = self._build_manifest_fast(
                        mediafile, parent_metadata_items
                    )
                    manifest_cache[cache_key] = manifest
                    count += 1
                except Exception as e:
                    logger.warning(f"Pre-generate: failed for {mf_id}: {e}")

        logger.info(f"Pre-generate: done. {count} manifests cached (cache_size={len(manifest_cache)}).")
        return count

    def _resolve_parent_metadata(
        self, parent_entity: dict, config: CollectionConfig
    ) -> list[dict]:
        """Resolve all parent-source metadata ONCE.

        Returns pre-built IIIF metadata items for all source="parent"
        mappings, including relation lookups (hasCreator) and property
        lookups (theme, publication). Deduplicates by (label, value).
        """
        metadata_items = []
        seen = set()  # (iiif_property, value) for deduplication
        skip_properties = {"label", "summary", "rights", "attribution"}

        for mapping in config.metadata_mappings:
            if mapping.iiif_property.lower() in skip_properties:
                continue
            if mapping.source != "parent":
                continue

            lang = mapping.language or "nl"

            added_for_mapping = 0

            if mapping.relation_type:
                # Follow relations on parent (e.g. hasCreator)
                values = self.generator._get_relation_metadata_values(
                    parent_entity, mapping.relation_type, mapping.related_key
                )
                for value in values:
                    if mapping.max_values and added_for_mapping >= mapping.max_values:
                        break
                    dedup_key = (mapping.iiif_property, value)
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)
                    metadata_items.append({
                        "label": self.generator._make_language_map(
                            mapping.iiif_property, lang
                        ),
                        "value": self.generator._make_language_map(value, lang),
                    })
                    added_for_mapping += 1
            elif mapping.elody_key:
                value = self.generator._get_entity_metadata_value(
                    parent_entity, mapping.elody_key
                )
                if value:
                    vals = value if isinstance(value, list) else [value]
                    for v in vals:
                        if mapping.max_values and added_for_mapping >= mapping.max_values:
                            break
                        extracted = str(v)
                        if mapping.regex:
                            match = re.search(mapping.regex, extracted)
                            if match:
                                extracted = match.group(1)
                            else:
                                continue
                        dedup_key = (mapping.iiif_property, extracted)
                        if dedup_key in seen:
                            continue
                        seen.add(dedup_key)
                        metadata_items.append({
                            "label": self.generator._make_language_map(
                                mapping.iiif_property, lang
                            ),
                            "value": self.generator._make_language_map(
                                extracted, lang
                            ),
                        })
                        added_for_mapping += 1

        return metadata_items

    def _build_manifest_fast(
        self, mediafile: dict, parent_metadata_items: list[dict]
    ) -> dict:
        """Build a manifest for a mediafile without any parent API calls.

        Uses pre-resolved parent_metadata_items instead of looking up
        relations again.
        """
        gen = self.generator
        entity_id = mediafile.get("_id") or mediafile.get("id")

        # Label/summary from the mediafile itself
        label = gen._get_entity_metadata_value(mediafile, "title") or f"Item {entity_id}"
        summary = gen._get_entity_metadata_value(mediafile, "description")

        # Build manifest ID
        base_url = gen.presentation_api_url.rstrip("/")
        manifest_id = f"{base_url}/iiif/manifest/{entity_id}"
        if gen._image_base_url:
            from urllib.parse import quote
            manifest_id += f"?image_base_url={quote(gen._image_base_url, safe='')}"

        manifest = {
            "@context": "http://iiif.io/api/presentation/3/context.json",
            "id": manifest_id,
            "type": "Manifest",
            "label": gen._make_language_map(label),
        }

        if summary:
            manifest["summary"] = gen._make_language_map(summary)

        if gen._config.rights_uri:
            manifest["rights"] = gen._config.rights_uri

        if gen._config.attribution:
            manifest["requiredStatement"] = {
                "label": {"en": ["Attribution"]},
                "value": gen._make_language_map(gen._config.attribution),
            }

        # Entity-specific metadata (e.g. Beschrijving) + pre-resolved parent metadata.
        # Honour each mapping's optional regex (same as _resolve_parent_metadata and
        # the manifest/collection generators) so title-derived facets like Auteur /
        # Periode index the extracted value instead of the raw title.
        entity_metadata = []
        seen = set()
        skip_properties = {"label", "summary", "rights", "attribution"}
        for mapping in gen._config.metadata_mappings:
            if mapping.iiif_property.lower() in skip_properties:
                continue
            if mapping.source in ("parent", "relation", "mediafile"):
                continue
            lang = mapping.language or "nl"
            value = gen._get_entity_metadata_value(mediafile, mapping.elody_key)
            if not value:
                continue
            vals = value if isinstance(value, list) else [value]
            for v in vals:
                extracted = str(v)
                if mapping.regex:
                    match = re.search(mapping.regex, extracted)
                    if not match:
                        continue
                    extracted = match.group(1).strip()
                dedup_key = (mapping.iiif_property, extracted)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                entity_metadata.append({
                    "label": gen._make_language_map(mapping.iiif_property, lang),
                    "value": gen._make_language_map(extracted, lang),
                })

        all_metadata = entity_metadata + parent_metadata_items
        if all_metadata:
            manifest["metadata"] = all_metadata

        # Thumbnail
        thumbnail = gen._get_thumbnail_from_mediafile(mediafile)
        if thumbnail:
            manifest["thumbnail"] = [thumbnail]

        # Single canvas
        manifest["items"] = gen._build_canvases(entity_id, [mediafile])

        return manifest

    def _get_all_entities(self, entity_type: str) -> list:
        """Fetch all entities of a given type (paginated)."""
        all_entities = []
        offset = 0
        limit = 500

        while True:
            response = self.generator._get_from_collection_api(
                f"/entities?type={entity_type}&limit={limit}&skip={offset}"
            )
            results = response.get("results", []) if isinstance(response, dict) else response
            if not results:
                break
            all_entities.extend(results)
            if len(results) < limit:
                break
            offset += limit

        return all_entities

