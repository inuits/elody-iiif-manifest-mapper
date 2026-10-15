import copy
import logging
import os
from collections.abc import Iterator

import requests
from elody.exceptions import NoMediafilesException, NotFoundException
from flask import request
from manifest_exceptions import RedirectException
from werkzeug.exceptions import Forbidden, Unauthorized

allow_static_jwt = os.getenv("ALLOW_STATIC_JWT", "false").lower() in {"true", "1"}

THUMBNAIL_WIDTH = 200
logger = logging.getLogger(__name__)


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class BaseGenerator(metaclass=Singleton):
    # Opt-in memo of successful collection-api responses, keyed by request.
    # Only set for the duration of a batch run (see resources/pre_generate.py)
    # so shared lookups (parent media, albums, creators, licenses) are fetched
    # once; None — the default — means every call goes to collection-api.
    # Generators are singletons, so whoever sets it must reset it.
    _response_cache: dict | None = None

    def __init__(self):
        self.collection_api_url = os.getenv("COLLECTION_API_URL")
        self.image_api_url = os.getenv("IMAGE_API_URL")
        self.image_api_url_ext = os.getenv("IMAGE_API_URL_EXT")
        self.presentation_api_url = os.getenv("PRESENTATION_API_URL")
        # Default upstream auth: fall back to STATIC_JWT when the inbound
        # request has no Authorization header. Public canopy site builds
        # call /collection/<id> without auth; without this default, every
        # upstream call to collection-api 401's and entities resolve to None.
        # An inbound Authorization header still overrides per-request via
        # the resource handlers.
        self.headers = {}
        static_jwt = os.getenv("STATIC_JWT")
        self.session = requests.session()
        if static_jwt and allow_static_jwt:
            self.headers["Authorization"] = f"Bearer {static_jwt}"

    def _build_thumbnail(self, image_url: str, width: int, height: int) -> dict:
        thumbnail_height = round(THUMBNAIL_WIDTH * height / width) if width else None
        return {
            "id": f"{image_url}/full/{THUMBNAIL_WIDTH},/0/default.jpg",
            "type": "Image",
            "format": "image/jpeg",
            "width": THUMBNAIL_WIDTH,
            "height": thumbnail_height or THUMBNAIL_WIDTH,
            "service": [
                {
                    "id": image_url,
                    "type": "ImageService3",
                    "profile": "level1",
                }
            ],
        }

    def _get_dimensions(self, mediafile: dict) -> tuple:
        def _coerce(value):
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        # Top-level fields
        width = _coerce(mediafile.get("img_width"))
        height = _coerce(mediafile.get("img_height"))

        # metadata dict
        metadata = mediafile.get("metadata")
        if (width is None or height is None) and isinstance(metadata, dict):
            width = width if width is not None else _coerce(metadata.get("img_width"))
            height = (
                height if height is not None else _coerce(metadata.get("img_height"))
            )

        # metadata array (key/value entries)
        if isinstance(metadata, list):
            for entry in metadata:
                if not isinstance(entry, dict):
                    continue
                if width is None and entry.get("key") == "img_width":
                    width = _coerce(entry.get("value"))
                if height is None and entry.get("key") == "img_height":
                    height = _coerce(entry.get("value"))

        return (width or 1000, height or 1000)

    def _get_attribution_for_mediafile(self, mediafile):
        ret = f"source: {self._get_item_metadata_value(mediafile, 'source')}"
        if photographer := self._get_item_metadata_value(mediafile, "photographer"):
            ret = f"photographer: {photographer}, {ret}"
        if rights_holder := self._get_item_metadata_value(mediafile, "copyright"):
            ret = f"rightsholder: {rights_holder}, {ret}"
        return ret

    def _get_from_collection_api(
        self,
        endpoint,
        entity=False,
        mediafiles=False,
        check_canonical_uris=False,
        entity_id=None,
    ):
        cache_key = (endpoint, entity, mediafiles, check_canonical_uris, entity_id)
        if self._response_cache is not None and cache_key in self._response_cache:
            return copy.deepcopy(self._response_cache[cache_key])
        result = self._fetch_from_collection_api(
            endpoint, entity, mediafiles, check_canonical_uris, entity_id
        )
        if self._response_cache is not None:
            self._response_cache[cache_key] = copy.deepcopy(result)
        return result

    def _fetch_from_collection_api(
        self, endpoint, entity, mediafiles, check_canonical_uris, entity_id
    ):
        req = self.session.get(
            f"{self.collection_api_url}{endpoint}",
            headers={
                **self.headers,
                **request.headers,
            },
            allow_redirects=not check_canonical_uris,
        )
        if entity and req.status_code == 404:
            raise NotFoundException()
        elif mediafiles and not len(req.json()):
            raise NoMediafilesException()
        elif req.status_code in {301, 302}:
            location = req.headers["location"]
            raise RedirectException(canonical_id=location.split("/")[-1])
        elif req.status_code == 401:
            raise Unauthorized
        elif req.status_code == 403:
            raise Forbidden
        if (
            entity_id
            and (canonical_id := req.json().get("_id"))
            and entity_id != canonical_id
        ):
            raise RedirectException(canonical_id)

        return req.json()

    def _post_to_collection_api(self, endpoint, body):
        # Forward the inbound headers like _get_from_collection_api does, minus
        # the ones describing the inbound request's own body/host.
        forwarded = {
            k: v
            for k, v in request.headers.items()
            if k.lower() not in {"host", "content-length", "content-type"}
        }
        req = self.session.post(
            f"{self.collection_api_url}{endpoint}",
            json=body,
            headers={**self.headers, **forwarded},
        )
        if req.status_code == 401:
            raise Unauthorized
        elif req.status_code == 403:
            raise Forbidden
        req.raise_for_status()
        return req.json()

    def _iter_related_entities(
        self, entity: dict, relation_type: str, recursive: bool = False
    ) -> Iterator[tuple[str, dict]]:
        """
        Yield (id, entity) for each entity that `entity` points at via
        relation_type, nearest first. With recursive, keep following
        relation_type from each yielded entity (e.g. sub-album -> parent
        album -> ...). Each entity is yielded at most once, so cycles end.
        Entities that fail to fetch are logged and skipped.
        """
        visited = {entity.get("_id") or entity.get("id")}
        queue = [entity]
        while queue:
            current = queue.pop(0)
            for relation in current.get("relations", []) or []:
                if relation.get("type") != relation_type:
                    continue
                related_id = relation.get("key")
                if not related_id or related_id in visited:
                    continue
                visited.add(related_id)
                try:
                    related = self._get_from_collection_api(
                        f"/entities/{related_id}", entity=True
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        f"{relation_type}: failed to fetch related entity "
                        f"{related_id}: {e}"
                    )
                    continue
                yield related_id, related
                if recursive:
                    queue.append(related)

    def _get_item_metadata_value(self, item, key, include_lang=False):
        for entry in [x for x in item.get("metadata", []) if x["key"] == key]:
            return (entry["lang"], entry["value"]) if include_lang else entry["value"]
        return None

    def _get_license_for_mediafile(self, mediafile):
        license_name = self._get_item_metadata_value(mediafile, "rights")
        return {
            "CC BY-NC 4.0": "https://creativecommons.org/licenses/by-nc/4.0/",
            "CC BY-NC-ND 4.0": "https://creativecommons.org/licenses/by-nc-nd/4.0/",
            "CC BY-SA 4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
            "CC0 1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
            "Copyright Undetermined": "https://rightsstatements.org/page/UND/1.0/",
            "In Copyright - non-commercial use permitted": "http://rightsstatements.org/vocab/InC-NC/1.0/",
            "In Copyright - unknown rightsholder": "http://rightsstatements.org/vocab/InC-RUU/1.0/",
            "In Copyright": "http://rightsstatements.org/vocab/InC/1.0/",
            "Public Domain Mark 1.0": "https://creativecommons.org/publicdomain/mark/1.0/",
        }.get(license_name, "https://rightsstatements.org/page/InC/1.0/?language=en")
