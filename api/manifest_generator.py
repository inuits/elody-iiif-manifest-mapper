"""
Configurable IIIF Manifest Generator - Generate IIIF v3 Manifests with JSON config.

This module provides a configurable manifest generator that uses the same
configuration structure as the collection generator, allowing metadata
mappings to be defined via JSON config.
"""

import logging
from typing import Optional

from base_generator import BaseGenerator
from collection_config import CollectionConfig, MetadataMapping, DEFAULT_METADATA_MAPPINGS

logger = logging.getLogger(__name__)


class ConfigurableManifestGenerator(BaseGenerator):
    """
    Generator for IIIF v3 Manifest resources with configurable metadata mappings.

    Uses the same CollectionConfig structure for consistency with the collection
    generator, but focuses on generating single Manifests with Canvases.
    """

    def __init__(self):
        super().__init__()
        self._config: Optional[CollectionConfig] = None

    def generate_manifest(
        self,
        entity_id: str,
        config_file: Optional[str] = None,
        config_dict: Optional[dict] = None,
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
        # Load config (dict > file > default)
        if config_dict:
            self._config = CollectionConfig.from_dict(config_dict)
        elif config_file:
            self._config = CollectionConfig.from_json_file(config_file)
        else:
            self._config = self._default_config()

        # Fetch entity
        entity = self._get_from_collection_api(f"/entities/{entity_id}", entity=True)

        # Get mediafiles for this entity
        mediafiles = self._get_mediafiles_for_entity(entity)

        # Build manifest
        manifest = self._build_manifest(entity, mediafiles)

        return manifest

    def _default_config(self) -> CollectionConfig:
        """Create a default configuration."""
        return CollectionConfig(
            name="Manifest",
            iiif_version=3,
            metadata_mappings=DEFAULT_METADATA_MAPPINGS,
        )

    def _build_manifest(self, entity: dict, mediafiles: list[dict]) -> dict:
        """
        Build an IIIF v3 Manifest from an entity and its mediafiles.

        Args:
            entity: The Elody entity
            mediafiles: List of mediafile entities

        Returns:
            IIIF v3 Manifest as dictionary
        """
        entity_id = entity.get("_id") or entity.get("id")

        # Extract metadata using mappings
        label = self._extract_mapped_value(entity, "label") or f"Item {entity_id}"
        summary = self._extract_mapped_value(entity, "summary")

        # Build manifest ID (strip trailing slashes from base URL)
        base_url = self.presentation_api_url.rstrip("/")
        manifest_id = f"{base_url}/manifest/{entity_id}"

        # Create manifest structure
        manifest = {
            "@context": "http://iiif.io/api/presentation/3/context.json",
            "id": manifest_id,
            "type": "Manifest",
            "label": self._make_language_map(label),
        }

        if summary:
            manifest["summary"] = self._make_language_map(summary)

        # Add rights from config
        if self._config.rights_uri:
            manifest["rights"] = self._config.rights_uri

        # Add attribution
        attribution = self._extract_mapped_value(entity, "attribution")
        if attribution or self._config.attribution:
            manifest["requiredStatement"] = {
                "label": {"en": ["Attribution"]},
                "value": self._make_language_map(
                    attribution or self._config.attribution
                ),
            }

        # Add custom metadata fields
        metadata_items = self._build_metadata(entity)
        if metadata_items:
            manifest["metadata"] = metadata_items

        # Add thumbnail from first mediafile
        if mediafiles:
            thumbnail = self._get_thumbnail_from_mediafile(mediafiles[0])
            if thumbnail:
                manifest["thumbnail"] = [thumbnail]

        # Build canvases from mediafiles
        manifest["items"] = self._build_canvases(entity_id, mediafiles)

        return manifest

    def _build_canvases(self, entity_id: str, mediafiles: list[dict]) -> list[dict]:
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
            canvas = self._build_canvas(entity_id, mediafile, idx)
            if canvas:
                canvases.append(canvas)

        return canvases

    def _build_canvas(self, entity_id: str, mediafile: dict, index: int) -> Optional[dict]:
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

        mediafile_id = mediafile.get("_id") or mediafile.get("id") or filename

        # Get dimensions if available
        metadata = mediafile.get("metadata", {})
        if isinstance(metadata, dict):
            width = metadata.get("img_width", 1000)
            height = metadata.get("img_height", 1000)
        else:
            width, height = 1000, 1000

        # Build image URL
        image_url = f"{self.image_api_url_ext}/iiif/3/{filename}"

        # Build canvas URL (strip trailing slashes from base URL)
        base_url = self.presentation_api_url.rstrip("/")
        canvas_id = f"{base_url}/canvas/{entity_id}/{index}"
        annotation_page_id = f"{canvas_id}/page/1"
        annotation_id = f"{canvas_id}/annotation/1"

        canvas = {
            "id": canvas_id,
            "type": "Canvas",
            "label": self._make_language_map(filename),
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
        }

        return canvas

    def _build_metadata(self, entity: dict) -> list[dict]:
        """
        Build IIIF metadata array from entity using configured mappings.

        Only includes mappings that are NOT label, summary, rights, or attribution
        (those are handled separately in the manifest structure).

        Args:
            entity: The entity to extract metadata from

        Returns:
            List of IIIF metadata objects
        """
        metadata_items = []
        skip_properties = {"label", "summary", "rights", "attribution"}

        for mapping in self._config.metadata_mappings:
            if mapping.iiif_property.lower() in skip_properties:
                continue

            value = self._get_entity_metadata_value(entity, mapping.elody_key)
            if value:
                metadata_items.append({
                    "label": self._make_language_map(
                        mapping.iiif_property,
                        mapping.language or "nl"
                    ),
                    "value": self._make_language_map(
                        value,
                        mapping.language or "nl"
                    ),
                })

        return metadata_items

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
            if response and response.get("results"):
                return response["results"]
        except Exception as e:
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
                    except Exception as e:
                        logger.warning(f"Failed to fetch mediafile {mediafile_id}: {e}")

        # Strategy 3: Use primary_mediafile_id
        if not mediafiles and entity.get("primary_mediafile_id"):
            try:
                mediafile = self._get_from_collection_api(
                    f"/mediafiles/{entity['primary_mediafile_id']}", entity=True
                )
                if mediafile:
                    mediafiles.append(mediafile)
            except Exception as e:
                logger.warning(f"Failed to fetch primary mediafile: {e}")

        return mediafiles

    def _get_mediafile_filename(self, mediafile: dict) -> Optional[str]:
        """Extract filename from mediafile."""
        # Direct fields
        if mediafile.get("transcode_filename"):
            return mediafile["transcode_filename"]
        if mediafile.get("filename"):
            return mediafile["filename"]
        if mediafile.get("display_filename"):
            return mediafile["display_filename"]

        # From metadata dict
        metadata = mediafile.get("metadata", {})
        if isinstance(metadata, dict):
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

    def _get_thumbnail_from_mediafile(self, mediafile: dict) -> Optional[dict]:
        """Get thumbnail object from a mediafile."""
        filename = self._get_mediafile_filename(mediafile)
        if filename:
            return {
                "id": f"{self.image_api_url_ext}/iiif/3/{filename}/full/200,/0/default.jpg",
                "type": "Image",
                "format": "image/jpeg",
            }
        return None

    def _extract_mapped_value(self, entity: dict, iiif_property: str) -> Optional[str]:
        """Extract a value from entity using configured mappings."""
        # First try configured mappings
        for mapping in self._config.metadata_mappings:
            if mapping.iiif_property.lower() == iiif_property.lower():
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

    def _get_entity_metadata_value(self, entity: dict, key: str) -> Optional[str]:
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

        return None

    def _make_language_map(self, value: str, language: str = "nl") -> dict:
        """Create an IIIF language map."""
        return {language: [value]}
