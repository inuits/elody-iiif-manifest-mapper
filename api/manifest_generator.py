"""
Configurable IIIF Manifest Generator - Generate IIIF v3 Manifests with JSON config.

This module provides a configurable manifest generator that uses the same
configuration structure as the collection generator, allowing metadata
mappings to be defined via JSON config.
"""

import logging
import os
import re

from base_generator import BaseGenerator
from collection_config import (
    DEFAULT_METADATA_MAPPINGS,
    CollectionConfig,
)

logger = logging.getLogger(__name__)

# Relation type mediafiles use to point at their License vocab entity.
# Confirmed against live data: the relation's own `key` IS the license URI
# (no id indirection to resolve). See the license-badge implementation plan
# in the sibling dams-canopy-generator-service repo
# (docs/superpowers/plans/2026-07-28-license-badge.md, Task 1) for the full
# investigation record.
LICENSE_RELATION_TYPE = "hasMediaLicense"
DEFAULT_CONFIG_FILE = os.getenv("CLIENT_CONFIG_FILE")


class ConfigurableManifestGenerator(BaseGenerator):
    """
    Generator for IIIF v3 Manifest resources with configurable metadata mappings.

    Uses the same CollectionConfig structure for consistency with the collection
    generator, but focuses on generating single Manifests with Canvases.
    """

    def __init__(self):
        super().__init__()
        self._config: CollectionConfig | None = None
        self._image_base_url: str | None = (
            None  # Override for image URLs (e.g. dashboard proxy)
        )
        self._config_file: str | None = (
            None  # Track config file for self-referencing manifest id
        )

    def generate_manifest(
        self,
        entity_id: str,
        config_file: str | None = None,
        config_dict: dict | None = None,
        image_base_url: str | None = None,
    ) -> dict:
        """
        Generate an IIIF v3 Manifest from an Elody entity.

        Args:
            entity_id: ID of the entity to generate manifest for
            config_file: Optional name of JSON config file (without .json extension)
            config_dict: Optional config dict with metadataMappings (takes precedence)

        Returns:
            IIIF v3 Manifest as a dictionary
        """
        # Store image base URL override (e.g. dashboard proxy URL)
        self._image_base_url = image_base_url.rstrip("/") if image_base_url else None
        # Track config_file so the manifest's own `id` field can advertise it.
        # Without this, canopy-iiif refetches the manifest by its `id` and the
        # call lacks config_file — metadataMappings aren't applied and the
        # manifest comes back without Auteur/Thema/Periode metadata, breaking
        # related-items grouping in the viewer.
        self._config_file = config_file

        # Load config (dict > file > default file > default)
        if config_dict:
            self._config = CollectionConfig.from_dict(config_dict)
            # POST-based dict configs can't be referenced by URL, so don't
            # advertise a config_file in the self-id.
            self._config_file = None
        elif config_file:
            self._config = CollectionConfig.from_json_file(config_file)
        elif DEFAULT_CONFIG_FILE:
            self._config = CollectionConfig.from_json_file(DEFAULT_CONFIG_FILE)
        else:
            self._config = self._default_config()

        # Fetch entity
        entity = self._get_from_collection_api(
            f"/entities/{entity_id}", entity=True, check_canonical_uris=True
        )

        # Resolve mediafiles and (optional) parent entity for metadata inheritance.
        # Originally we only looked up the parent when entity.type == "mediafile",
        # but the Wetenschatten data has manifests at the media level (not
        # mediafile), so source="parent" mappings were silently empty — search
        # facets and related-items grouped on Auteur/Thema/Periode came back
        # blank. Always try the parent lookup via belongsTo when relations are
        # present; if none exist, parent_entity stays None and source="parent"
        # mappings simply yield nothing as before.
        parent_entity = None
        entity_type = entity.get("type")
        logger.info(
            "manifest_generator: entity %s type=%s relations=%s",
            entity_id,
            entity_type,
            [r.get("type") for r in (entity.get("relations") or [])],
        )

        if entity_type == "mediafile":
            mediafiles = [entity]
        else:
            mediafiles = self._get_mediafiles_for_entity(entity)

        for rel in entity.get("relations", []) or []:
            if rel.get("type") == "belongsTo":
                try:
                    parent_entity = self._get_from_collection_api(
                        f"/entities/{rel['key']}", entity=True
                    )
                    logger.info(
                        "manifest_generator: resolved parent %s for %s",
                        rel.get("key"),
                        entity_id,
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Failed to fetch parent entity {rel['key']}: {e}")
                break

        # Build manifest
        manifest = self._build_manifest(entity, mediafiles, parent_entity=parent_entity)

        return manifest

    def _default_config(self) -> CollectionConfig:
        """Create a default configuration."""
        return CollectionConfig(
            name="Manifest",
            iiif_version=3,
            metadata_mappings=DEFAULT_METADATA_MAPPINGS,
        )

    def _build_manifest(
        self, entity: dict, mediafiles: list[dict], parent_entity: dict | None = None
    ) -> dict:
        """
        Build an IIIF v3 Manifest from an entity and its mediafiles.

        Args:
            entity: The Elody entity
            mediafiles: List of mediafile entities
            parent_entity: Optional parent entity for inherited metadata

        Returns:
            IIIF v3 Manifest as dictionary
        """
        entity_id = entity.get("_id") or entity.get("id")

        # Extract metadata using mappings (pass first mediafile for mediafile-source mappings)
        first_mediafile = mediafiles[0] if mediafiles else None
        label = (
            self._extract_mapped_value(entity, "label", first_mediafile)
            or f"Item {entity_id}"
        )
        summary = self._extract_mapped_value(entity, "summary", first_mediafile)

        # Build manifest ID using /iiif/manifest/ endpoint (strip trailing slashes from base URL)
        # Include image_base_url so runtime fetches (e.g. Clover viewer) also get proxied image URLs.
        # Include config_file too, otherwise the viewer's refetch by id would load the manifest
        # without the metadataMappings config and lose Auteur/Thema/Periode metadata.
        from urllib.parse import quote

        base_url = self.presentation_api_url.rstrip("/")
        manifest_id = f"{base_url}/iiif/manifest/{entity_id}"
        query_params = []
        if self._config_file:
            query_params.append(f"config_file={self._config_file}")
        if self._image_base_url:
            query_params.append(
                f"image_base_url={quote(self._image_base_url, safe='')}"
            )
        if query_params:
            manifest_id += "?" + "&".join(query_params)

        # Create manifest structure
        manifest = {
            "@context": "http://iiif.io/api/presentation/3/context.json",
            "id": manifest_id,
            "type": "Manifest",
            "label": self._make_language_map(label),
        }

        if summary:
            manifest["summary"] = self._make_language_map(summary)

        # Add rights: prefer the entity's real license (if any), falling
        # back to the static site-wide default from config.
        license_title, license_uri = self._resolve_license(entity)
        if license_uri or self._config.rights_uri:
            manifest["rights"] = license_uri or self._config.rights_uri

        # Add presentation hints and provider from config
        if self._config.viewing_direction:
            manifest["viewingDirection"] = self._config.viewing_direction
        if self._config.behavior:
            manifest["behavior"] = (
                self._config.behavior
                if isinstance(self._config.behavior, list)
                else [self._config.behavior]
            )
        if self._config.provider:
            manifest["provider"] = self._config.provider

        # Add attribution
        attribution = self._extract_mapped_value(entity, "attribution")
        if attribution or self._config.attribution:
            manifest["requiredStatement"] = {
                "label": {"en": ["Attribution"]},
                "value": self._make_language_map(
                    attribution or self._config.attribution
                ),
            }

        # Add custom metadata fields (pass first mediafile for mediafile-source mappings)
        first_mediafile = mediafiles[0] if mediafiles else None
        metadata_items = self._build_metadata(
            entity, mediafile=first_mediafile, parent_entity=parent_entity
        )
        if license_title:
            metadata_items.append(
                {
                    "label": self._make_language_map("Licentie", "nl"),
                    "value": self._make_language_map(license_title, "nl"),
                }
            )
        if metadata_items:
            manifest["metadata"] = metadata_items

        # Add thumbnail from first mediafile
        if mediafiles:
            thumbnail = self._get_thumbnail_from_mediafile(mediafiles[0])
            if thumbnail:
                manifest["thumbnail"] = [thumbnail]

        # Build canvases from mediafiles
        manifest["items"] = self._build_canvases(entity, mediafiles)

        return manifest

    def _build_canvases(self, entity: dict, mediafiles: list[dict]) -> list[dict]:
        """
        Build Canvas items from mediafiles.

        Args:
            entity_id: Parent entity ID
            mediafiles: List of mediafile entities

        Returns:
            List of IIIF Canvas objects
        """
        canvases = []

        for idx, mediafile in enumerate(mediafiles):
            canvas = self._build_canvas(entity, mediafile, idx)
            if canvas:
                canvases.append(canvas)

        return canvases

    def _build_canvas(self, entity: dict, mediafile: dict, index: int) -> dict | None:
        """
        Build a single Canvas from a mediafile.

        Args:
            entity_id: Parent entity ID
            mediafile: Mediafile entity
            index: Canvas index

        Returns:
            IIIF Canvas object or None
        """
        filename = self._get_mediafile_filename(mediafile)
        if not filename:
            return None

        entity_id = entity.get("_id") or entity.get("id")
        mediafile_id = mediafile.get("_id") or mediafile.get("id") or filename

        # Get dimensions (top-level fields, metadata dict or metadata array)
        width, height = self._get_dimensions(mediafile)

        # Build image URL (use override if set, e.g. for dashboard proxy)
        image_base = self._image_base_url or self.image_api_url_ext
        image_url = f"{image_base}/iiif/3/{mediafile_id}"

        # Build canvas URL (strip trailing slashes from base URL)
        base_url = self.presentation_api_url.rstrip("/")
        canvas_id = f"{base_url}/canvas/{entity_id}/{index}"
        annotation_page_id = f"{canvas_id}/page/1"
        annotation_id = f"{canvas_id}/annotation/1"

        canvas = {
            "id": canvas_id,
            "type": "Canvas",
            "label": self._make_language_map(
                self._build_canvas_label(entity, mediafile, filename)
            ),
            "width": width,
            "height": height,
            "items": [
                {
                    "id": annotation_page_id,
                    "type": "AnnotationPage",
                    "items": [
                        {
                            "id": annotation_id,
                            "type": "Annotation",
                            "motivation": "painting",
                            "body": {
                                "id": f"{image_url}/full/max/0/default.jpg",
                                "type": "Image",
                                "format": "image/jpeg",
                                "label": self._make_language_map(filename),
                                "width": width,
                                "height": height,
                                "service": [
                                    {
                                        "id": image_url,
                                        "type": "ImageService3",
                                        "profile": "level1",
                                    }
                                ],
                            },
                            "target": canvas_id,
                        }
                    ],
                }
            ],
            "thumbnail": [
                {
                    "id": f"{image_url}/full/200,/0/default.jpg",
                    "type": "Image",
                    "format": "image/jpeg",
                }
            ],
            # Download target for the Clover viewer. Clover only renders its
            # download control from a manifest/canvas `rendering` array (it does
            # not derive downloads from the image body), so expose the full-res
            # JPEG here to make the viewer's download button appear.
            "rendering": [
                {
                    "id": f"{image_url}/full/max/0/default.jpg",
                    "type": "Image",
                    "label": self._make_language_map("Download afbeelding"),
                    "format": "image/jpeg",
                }
            ],
        }

        # Per-image rights statement (rights are registered per mediafile).
        rights = self._get_license_for_mediafile(mediafile)
        if rights:
            canvas["rights"] = rights

        # Per-image attribution / required statement.
        required_statement = self._build_required_statement(mediafile)
        if required_statement:
            canvas["requiredStatement"] = required_statement

        return canvas

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
        if width is None or height is None:
            width = (
                width
                if width is not None
                else _coerce(self._get_entity_metadata_value(mediafile, "img_width"))
            )
            height = (
                height
                if height is not None
                else _coerce(self._get_entity_metadata_value(mediafile, "img_height"))
            )

        return (width or 1000, height or 1000)

    def _build_canvas_label(self, entity: dict, mediafile: dict, filename: str) -> str:
        title = (
            self._get_entity_metadata_value(entity, "title")
            or self._get_entity_metadata_value(mediafile, "title")
            or mediafile.get("original_filename")
        )
        maker = self._get_entity_metadata_value(
            entity, "creator"
        ) or self._get_entity_metadata_value(mediafile, "creator")
        date = self._get_entity_metadata_value(
            entity, "date"
        ) or self._get_entity_metadata_value(mediafile, "date")

        collection_owning_instance = self._extract_mapped_value(entity, "Data-eigenaar")

        parts = []
        if title:
            parts.append(f"{title}.")
        if maker:
            parts.append(f"door {maker}")
        if date:
            parts.append(f"in {date}.")
        if collection_owning_instance:
            parts.append(collection_owning_instance)
        caption = " ".join(parts).strip()
        return caption or filename

    def _build_required_statement(self, mediafile: dict) -> dict | None:
        attribution = self._get_entity_metadata_value(
            mediafile, "attribution"
        ) or self._get_entity_metadata_value(mediafile, "minimal_attribution")
        if not attribution:
            mediafile_id = mediafile.get("_id") or mediafile.get("id")
            if mediafile_id:
                try:
                    full = self._get_from_collection_api(
                        f"/mediafiles/{mediafile_id}", entity=True
                    )
                    attribution = self._get_entity_metadata_value(
                        full, "attribution"
                    ) or self._get_entity_metadata_value(full, "minimal_attribution")
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        f"Failed to fetch attribution for mediafile {mediafile_id}: {e}"
                    )
        if not attribution:
            return None
        return {
            "label": self._make_language_map("Naamsvermelding"),
            "value": self._make_language_map(attribution),
        }

    def _build_metadata(
        self,
        entity: dict,
        mediafile: dict | None = None,
        parent_entity: dict | None = None,
    ) -> list[dict]:
        """
        Build IIIF metadata array from entity using configured mappings.

        Only includes mappings that are NOT label, summary, rights, or attribution
        (those are handled separately in the manifest structure).

        Args:
            entity: The entity to extract metadata from
            mediafile: Optional first mediafile for mediafile-source mappings
            parent_entity: Optional parent entity for source="parent" mappings

        Returns:
            List of IIIF metadata objects
        """
        metadata_items = []
        seen = set()  # (iiif_property, value) for deduplication
        skip_properties = {"label", "summary", "rights", "attribution"}

        for mapping in self._config.metadata_mappings:
            if mapping.iiif_property.lower() in skip_properties:
                continue

            lang = mapping.language or "nl"

            if mapping.source == "parent" and parent_entity:
                if mapping.relation_type:
                    values = self._get_relation_metadata_values(
                        parent_entity, mapping.relation_type, mapping.related_key
                    )
                    for value in values:
                        dedup_key = (mapping.iiif_property, value)
                        if dedup_key in seen:
                            continue
                        seen.add(dedup_key)
                        metadata_items.append(
                            {
                                "label": self._make_language_map(
                                    mapping.iiif_property, lang
                                ),
                                "value": self._make_language_map(value, lang),
                            }
                        )
                elif mapping.elody_key:
                    value = self._get_entity_metadata_value(
                        parent_entity, mapping.elody_key
                    )
                    if value:
                        vals = value if isinstance(value, list) else [value]
                        for v in vals:
                            # Apply regex extraction if configured
                            extracted = str(v)
                            if mapping.regex:
                                match = re.search(mapping.regex, extracted)
                                if match:
                                    extracted = match.group(1)
                                else:
                                    continue  # Skip if regex doesn't match
                            dedup_key = (mapping.iiif_property, extracted)
                            if dedup_key in seen:
                                continue
                            seen.add(dedup_key)
                            metadata_items.append(
                                {
                                    "label": self._make_language_map(
                                        mapping.iiif_property, lang
                                    ),
                                    "value": self._make_language_map(extracted, lang),
                                }
                            )
            elif mapping.source == "relation":
                values = self._get_relation_metadata_values(
                    entity, mapping.relation_type, mapping.related_key
                )
                for value in values:
                    metadata_items.append(
                        {
                            "label": self._make_language_map(
                                mapping.iiif_property, lang
                            ),
                            "value": self._make_language_map(value, lang),
                        }
                    )
            elif mapping.source == "mediafile" and mediafile:
                value = self._get_entity_metadata_value(mediafile, mapping.elody_key)
                self._append_with_regex(metadata_items, seen, value, mapping, lang)
            else:
                value = self._get_entity_metadata_value(entity, mapping.elody_key)
                self._append_with_regex(metadata_items, seen, value, mapping, lang)

        return metadata_items

    def _append_with_regex(
        self,
        metadata_items: list,
        seen: set,
        value,
        mapping,
        lang: str,
    ) -> None:
        """Append metadata item(s), applying optional regex extraction.

        Honours the same regex semantics as source="parent" mappings — if a
        regex is set and matches, only group(1) is used; if it doesn't match,
        the entry is skipped entirely. Without a regex the raw value is used.
        Deduplicates on (iiif_property, value).
        """
        if value is None or value == "":
            return
        values = value if isinstance(value, list) else [value]
        for v in values:
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
            metadata_items.append(
                {
                    "label": self._make_language_map(mapping.iiif_property, lang),
                    "value": self._make_language_map(extracted, lang),
                }
            )

    def _get_relation_metadata_values(
        self, entity: dict, relation_type: str, related_key: str
    ) -> list[str]:
        """
        Get metadata values from related entities.

        Args:
            entity: The source entity containing relations
            relation_type: The relation type to match (e.g., "hasCreator")
            related_key: The metadata key to extract from related entities

        Returns:
            List of metadata values from matching related entities
        """
        values = []
        entity_id = entity.get("_id") or entity.get("id")
        matched_any = False
        for relation in entity.get("relations", []):
            if relation.get("type") != relation_type:
                continue
            matched_any = True
            related_id = relation.get("key")
            if not related_id:
                continue
            try:
                related_entity = self._get_from_collection_api(
                    f"/entities/{related_id}", entity=True
                )
                value = self._get_entity_metadata_value(related_entity, related_key)
                if value:
                    values.append(value)
                    logger.debug(
                        f"{relation_type}: resolved '{related_key}'={value!r} "
                        f"from related entity {related_id} (source entity {entity_id})"
                    )
                else:
                    logger.warning(
                        f"{relation_type}: related entity {related_id} (source entity "
                        f"{entity_id}) has no '{related_key}' value — metadata="
                        f"{related_entity.get('metadata')} properties="
                        f"{related_entity.get('properties')}"
                    )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    f"{relation_type}: failed to fetch related entity {related_id} "
                    f"(source entity {entity_id}): {e}"
                )
        if not matched_any:
            logger.debug(
                f"{relation_type}: entity {entity_id} has no '{relation_type}' relation"
            )
        return values

    def _resolve_license(
        self, entity: dict, license_cache: dict | None = None
    ) -> tuple[str | None, str | None]:
        """
        Resolve an entity's license relation to (title, uri).

        Looks for a relation of type LICENSE_RELATION_TYPE on `entity`. The
        relation's own `key` IS the license URI already (confirmed against
        live data) — there's no id indirection to resolve for the URI. Only
        the human-readable title needs a fetch: the license entity's own
        `_id` is that same URI, and its preference-label text lives under
        metadata key `prefLabel`. See the license-badge implementation plan
        in the sibling dams-canopy-generator-service repo
        (docs/superpowers/plans/2026-07-28-license-badge.md, Task 1) for the
        full investigation record behind these facts.

        Title lookups are cached by license URI in `license_cache` (if
        provided) so a caller processing many entities in one run (e.g.
        pre_generate's batch build) only fetches each distinct license
        term once, no matter how many entities use it. The live
        single-entity path can omit `license_cache` — a fresh throwaway
        dict is used and there's nothing to reuse across calls.

        If the title fetch fails, the URI is still returned (it never
        depended on that fetch) — only the title comes back None.
        """
        cache = license_cache if license_cache is not None else {}
        for rel in entity.get("relations", []) or []:
            if rel.get("type") != LICENSE_RELATION_TYPE:
                continue
            license_uri = rel.get("key")
            if not license_uri:
                continue
            if license_uri not in cache:
                from urllib.parse import quote

                try:
                    license_entity = self._get_from_collection_api(
                        f"/entities/{quote(license_uri, safe='')}", entity=True
                    )
                    title = self._get_entity_metadata_value(license_entity, "prefLabel")
                    cache[license_uri] = (title, license_uri)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Failed to fetch license {license_uri}: {e}")
                    cache[license_uri] = (None, license_uri)
            return cache[license_uri]
        return (None, None)

    def _get_mediafiles_for_entity(self, entity: dict) -> list[dict]:
        """
        Get mediafiles for an entity using multiple strategies.
        """
        entity_id = entity.get("_id") or entity.get("id")
        mediafiles = []

        # Strategy 1: Try the mediafiles endpoint
        try:
            response = self._get_from_collection_api(
                f"/entities/{entity_id}/mediafiles"
            )
            results = []
            if response and response.get("results"):
                results.extend(response.get("results"))
                # NOTE: the next on the /entities/{id}/mediafiles is wrong
                # and should be fixed, but fixing it should not break this
                # replace
                while next := response.get("next"):
                    next = next.replace("/filter", "")
                    response = self._get_from_collection_api(
                        f"/entities/{entity_id}{next}"
                    )
                    results.extend(response.get("results", []))

                return results

        except Exception as e:  # noqa: BLE001
            logger.debug(f"Mediafiles endpoint failed for {entity_id}: {e}")

        # Strategy 2: Get from relations (deduplicate by mediafile ID)
        seen_ids = set()
        for relation in entity.get("relations", []):
            if relation.get("type") in ("hasMediafile", "hasPrimaryMediafile"):
                mediafile_id = relation.get("key")
                if mediafile_id and mediafile_id not in seen_ids:
                    seen_ids.add(mediafile_id)
                    try:
                        mediafile = self._get_from_collection_api(
                            f"/mediafiles/{mediafile_id}", entity=True
                        )
                        if mediafile:
                            mediafiles.append(mediafile)
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"Failed to fetch mediafile {mediafile_id}: {e}")

        # Strategy 3: Use primary_mediafile_id
        if not mediafiles and entity.get("primary_mediafile_id"):
            try:
                mediafile = self._get_from_collection_api(
                    f"/mediafiles/{entity['primary_mediafile_id']}", entity=True
                )
                if mediafile:
                    mediafiles.append(mediafile)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Failed to fetch primary mediafile: {e}")

        return mediafiles

    def _get_mediafile_filename(self, mediafile: dict) -> str | None:
        """Extract filename from mediafile."""
        # Direct fields
        if mediafile.get("transcode_filename"):
            return mediafile["transcode_filename"]
        if mediafile.get("original_filename"):
            return mediafile["original_filename"]
        if mediafile.get("filename"):
            return mediafile["filename"]
        if mediafile.get("display_filename"):
            return mediafile["display_filename"]

        # From metadata dict
        metadata = mediafile.get("metadata", {})
        if isinstance(metadata, dict):  # noqa: SIM102
            if metadata.get("filename"):
                return metadata["filename"]

        # From metadata array
        if isinstance(metadata, list):
            for m in metadata:
                if m.get("key") == "filename":
                    return m.get("value")

        # From identifiers
        for identifier in mediafile.get("identifiers", []):
            if "." in identifier and not identifier.startswith("MED-"):
                return identifier

        return None

    def _get_thumbnail_from_mediafile(self, mediafile: dict) -> dict | None:
        """Get thumbnail object from a mediafile."""
        mediafile_id = mediafile["_id"]
        if mediafile_id:
            image_base = self._image_base_url or self.image_api_url_ext
            return {
                "id": f"{image_base}/iiif/3/{mediafile_id}/full/200,/0/default.jpg",
                "type": "Image",
                "format": "image/jpeg",
            }
        return None

    def _extract_mapped_value(
        self, entity: dict, iiif_property: str, mediafile: dict | None = None
    ) -> str | None:
        """Extract a value from entity (or mediafile) using configured mappings."""
        # First try configured mappings
        for mapping in self._config.metadata_mappings:
            if mapping.iiif_property.lower() == iiif_property.lower():
                if mapping.source == "relation":
                    values = self._get_relation_metadata_values(
                        entity, mapping.relation_type, mapping.related_key
                    )
                    if values:
                        return values[0]
                elif mapping.source == "mediafile" and mediafile:
                    value = self._get_entity_metadata_value(
                        mediafile, mapping.elody_key
                    )
                    if value:
                        return value
                else:
                    value = self._get_entity_metadata_value(entity, mapping.elody_key)
                    if value:
                        return value

        # Fall back to default mappings
        for mapping in DEFAULT_METADATA_MAPPINGS:
            if mapping.iiif_property.lower() == iiif_property.lower():
                value = self._get_entity_metadata_value(entity, mapping.elody_key)
                if value:
                    return value

        return None

    def _get_entity_metadata_value(self, entity: dict, key: str) -> str | None:
        """Get metadata value from entity in various formats."""
        # Format 1: metadata array with key/value
        for entry in entity.get("metadata", []):
            if isinstance(entry, dict) and entry.get("key") == key:
                return entry.get("value")

        # Format 2: properties dict
        properties = entity.get("properties", {})
        if key in properties:
            prop = properties[key]
            if isinstance(prop, dict):
                return prop.get("value")
            return prop

        # Format 3: flat top-level field directly on the document. Some
        # entities — observed on mediafiles created via import — store
        # fields like "title" as a bare top-level key with an empty
        # "metadata" array, rather than nesting it in metadata/properties.
        value = entity.get(key)
        if isinstance(value, str) and value:
            return value

        return None

    def _make_language_map(self, value: str, language: str = "nl") -> dict:
        """Create an IIIF language map."""
        return {language: [value]}
