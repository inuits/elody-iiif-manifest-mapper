"""
IIIF Collection Generator - Generate IIIF v3 Collections from Elody entities.

This module provides the CollectionGenerator class which traverses Elody entity
graphs and generates IIIF Presentation API v3 Collection resources.
"""

import logging
from typing import Optional

from base_generator import BaseGenerator
from collection_config import CollectionConfig, TraversalStep, DEFAULT_METADATA_MAPPINGS
from iiif_prezi3 import Collection, Manifest

logger = logging.getLogger(__name__)


class CollectionGenerator(BaseGenerator):
    """
    Generator for IIIF v3 Collection resources from Elody entities.

    Extends BaseGenerator with methods for:
    - Fetching and parsing collection configurations
    - Traversing entity graphs via relations
    - Building nested Collection structures
    - Generating manifest references
    """

    def __init__(self):
        super().__init__()
        self._config: Optional[CollectionConfig] = None
        self._config_file: Optional[str] = None  # Track config file for manifest URLs

    def generate_collection(
        self,
        root_entity_id: str,
        config_entity_id: Optional[str] = None,
        config_file: Optional[str] = None,
        config_dict: Optional[dict] = None,
        depth: Optional[int] = None,
    ) -> dict:
        """
        Generate an IIIF v3 Collection from an Elody entity.

        Args:
            root_entity_id: ID of the root entity to start traversal from
            config_entity_id: Optional ID of an iiifCollectionConfig entity.
                            If not provided, uses default configuration.
            config_file: Optional name of a JSON config file (without .json extension).
                        If provided, loads config from config/{config_file}.json.
            config_dict: Optional config as a dictionary (from POST body).
                        Takes precedence over config_file and config_entity_id.
            depth: Optional maximum depth to traverse (None for unlimited)

        Returns:
            IIIF v3 Collection as a dictionary
        """
        # Store config file name for use in manifest URLs
        self._config_file = config_file

        # Fetch configuration (dict > file > entity > default)
        if config_dict:
            self._config = CollectionConfig.from_dict(config_dict)
            # For POST requests, we can't pass config to manifest URLs easily
            # So we don't set _config_file in this case
            self._config_file = None
        elif config_file:
            self._config = CollectionConfig.from_json_file(config_file)
        elif config_entity_id:
            self._config = self._fetch_config(config_entity_id)
        else:
            self._config = self._default_config()

        # Fetch root entity
        root_entity = self._get_from_collection_api(
            f"/entities/{root_entity_id}", entity=True
        )

        # Determine starting step based on entity type
        start_step = self._find_starting_step(root_entity)

        # Build collection
        collection = self._build_collection(
            entity=root_entity,
            step_index=start_step,
            current_depth=0,
            max_depth=depth,
        )

        return collection

    def _fetch_config(self, config_entity_id: str) -> CollectionConfig:
        """
        Fetch and parse collection configuration from Elody.

        Supports two approaches:
        1. Entity with 'iiif_config' metadata containing full config as JSON
        2. Traditional iiifCollectionConfig entity with related traversal/mapping entities

        Args:
            config_entity_id: ID of the config entity (any type with iiif_config, or iiifCollectionConfig)

        Returns:
            Parsed CollectionConfig instance
        """
        # Fetch config entity
        config_entity = self._get_from_collection_api(
            f"/entities/{config_entity_id}", entity=True
        )

        # Check for iiif_config metadata field (embedded JSON config)
        metadata = config_entity.get("metadata", [])
        for m in metadata:
            if m.get("key") == "iiif_config":
                config_value = m.get("value")
                if config_value:
                    # If value is already a dict, use it directly
                    if isinstance(config_value, dict):
                        return CollectionConfig.from_dict(config_value)
                    # If value is a JSON string, parse it
                    if isinstance(config_value, str):
                        import json
                        try:
                            config_dict = json.loads(config_value)
                            return CollectionConfig.from_dict(config_dict)
                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse iiif_config JSON: {e}")

        # Fall back to traditional iiifCollectionConfig approach
        # Fetch related traversal step entities
        traversal_entities = self._get_related_entities_by_type(
            config_entity, "hasTraversalStep"
        )

        # Fetch related metadata mapping entities
        mapping_entities = self._get_related_entities_by_type(
            config_entity, "hasMetadataMapping"
        )

        return CollectionConfig.from_elody_entity(
            config_entity,
            traversal_entities=traversal_entities,
            mapping_entities=mapping_entities,
        )

    def _default_config(self) -> CollectionConfig:
        """Create a default configuration for basic collection generation."""
        return CollectionConfig(
            name="Collection",
            iiif_version=3,
            traversal_steps=[
                TraversalStep(
                    relation_type="hasItem",
                    maps_to_iiif="Manifest",
                    order=1,
                ),
            ],
            metadata_mappings=DEFAULT_METADATA_MAPPINGS,
        )

    def _find_starting_step(self, entity: dict) -> int:
        """
        Determine which traversal step to start from based on entity type.

        When an entity is fetched directly, we need to find the appropriate step
        in the traversal hierarchy. For inverse lookups:
        - Step N with targetType=X finds entities of type X pointing to current
        - So if current entity IS of type X, we should skip to step N+1

        Args:
            entity: The entity to find starting step for

        Returns:
            Index of the step to start from
        """
        entity_type = entity.get("type", "").lower()

        # Check each step to see if we should skip it
        for i, step in enumerate(self._config.traversal_steps):
            if step.inverse and step.target_type:
                # This step finds entities of target_type pointing to parent
                # If current entity IS that target_type, use the next step
                if entity_type == step.target_type.lower():
                    return i + 1

        # Default: start at step 0
        return 0

    def _build_collection(
        self,
        entity: dict,
        step_index: int,
        current_depth: int,
        max_depth: Optional[int],
    ) -> dict:
        """
        Build an IIIF Collection from an entity.

        Args:
            entity: The Elody entity to build from
            step_index: Current index in traversal_steps
            current_depth: Current depth in the collection hierarchy
            max_depth: Maximum depth to traverse

        Returns:
            IIIF Collection as dictionary
        """
        entity_id = entity.get("_id") or entity.get("id")

        # Extract metadata using mappings
        label = self._extract_mapped_value(entity, "label") or f"Collection {entity_id}"
        summary = self._extract_mapped_value(entity, "summary")
        rights = self._extract_mapped_value(entity, "rights")

        # Build collection ID (strip trailing slashes from base URL)
        base_url = self.presentation_api_url.rstrip("/")
        collection_id = f"{base_url}/collection/{entity_id}"

        # Create collection structure
        collection = {
            "@context": "http://iiif.io/api/presentation/3/context.json",
            "id": collection_id,
            "type": "Collection",
            "label": self._make_language_map(label),
        }

        if summary:
            collection["summary"] = self._make_language_map(summary)

        if rights:
            collection["rights"] = rights
        elif self._config.rights_uri:
            collection["rights"] = self._config.rights_uri

        # Add attribution
        attribution = self._extract_mapped_value(entity, "attribution")
        if attribution or self._config.attribution:
            collection["requiredStatement"] = {
                "label": {"en": ["Attribution"]},
                "value": self._make_language_map(
                    attribution or self._config.attribution
                ),
            }

        # Add thumbnail from first mediafile if available
        thumbnail = self._get_entity_thumbnail(entity)
        if thumbnail:
            collection["thumbnail"] = [thumbnail]

        # Build items
        collection["items"] = self._build_collection_items(
            entity=entity,
            step_index=step_index,
            current_depth=current_depth,
            max_depth=max_depth,
        )

        return collection

    def _build_collection_items(
        self,
        entity: dict,
        step_index: int,
        current_depth: int,
        max_depth: Optional[int],
    ) -> list[dict]:
        """
        Build the items array for a collection by following relations.

        Args:
            entity: The parent entity
            step_index: Current index in traversal_steps
            current_depth: Current depth in hierarchy
            max_depth: Maximum depth to traverse

        Returns:
            List of IIIF Collection or Manifest references
        """
        items = []

        # Check if we've exceeded max depth
        if max_depth is not None and current_depth >= max_depth:
            return items

        # Get traversal step for current level
        if step_index >= len(self._config.traversal_steps):
            return items

        step = self._config.traversal_steps[step_index]

        # Get related entities - either forward or inverse lookup
        if step.inverse:
            # Inverse lookup: find entities that have relation_type pointing TO current entity
            related_entities = self._get_entities_by_inverse_relation(
                entity, step.relation_type, step.target_type
            )
        else:
            # Forward lookup: follow relations FROM current entity
            related_entities = self._get_related_entities_by_type(
                entity, step.relation_type
            )

        for related_entity in related_entities:
            if step.maps_to_iiif == "Collection":
                # Recursively build sub-collection
                sub_collection = self._build_collection(
                    entity=related_entity,
                    step_index=step_index + 1,
                    current_depth=current_depth + 1,
                    max_depth=max_depth,
                )
                # Add as reference (not full collection)
                items.append(self._make_collection_reference(sub_collection))

            elif step.maps_to_iiif == "Manifest":
                # Create manifest reference
                manifest_ref = self._make_manifest_reference(related_entity)
                items.append(manifest_ref)

        return items

    def _make_collection_reference(self, collection: dict) -> dict:
        """Create a reference to a collection (for nesting in items)."""
        ref = {
            "id": collection["id"],
            "type": "Collection",
            "label": collection.get("label"),
        }

        if "thumbnail" in collection:
            ref["thumbnail"] = collection["thumbnail"]

        if "summary" in collection:
            ref["summary"] = collection["summary"]

        return ref

    def _make_manifest_reference(self, entity: dict) -> dict:
        """Create a reference to a manifest for an entity."""
        entity_id = entity.get("_id") or entity.get("id")
        label = self._extract_mapped_value(entity, "label") or f"Item {entity_id}"

        # Build manifest URL - use configurable endpoint with config_file if available
        base_url = self.presentation_api_url.rstrip("/")
        if self._config_file:
            manifest_url = f"{base_url}/iiif/manifest/{entity_id}?config_file={self._config_file}"
        else:
            # Fall back to standard manifest endpoint
            manifest_url = f"{base_url}/iiif/manifest/{entity_id}"

        manifest_ref = {
            "id": manifest_url,
            "type": "Manifest",
            "label": self._make_language_map(label),
        }

        # Add thumbnail if available
        thumbnail = self._get_entity_thumbnail(entity)
        if thumbnail:
            manifest_ref["thumbnail"] = [thumbnail]

        return manifest_ref

    def _get_related_entities_by_type(
        self, entity: dict, relation_type: str
    ) -> list[dict]:
        """
        Fetch all entities related via a specific relation type.

        Args:
            entity: The parent entity
            relation_type: The type of relation to follow

        Returns:
            List of related entity dictionaries
        """
        related_entities = []

        for relation in entity.get("relations", []):
            if relation.get("type") == relation_type:
                related_id = relation.get("key")
                if related_id:
                    try:
                        related_entity = self._get_from_collection_api(
                            f"/entities/{related_id}", entity=True
                        )
                        related_entities.append(related_entity)
                    except Exception as e:
                        logger.warning(f"Failed to fetch related entity {related_id}: {e}")

        return related_entities

    def _get_entities_by_inverse_relation(
        self, entity: dict, relation_type: str, target_type: Optional[str] = None
    ) -> list[dict]:
        """
        Fetch entities that have a property/relation pointing TO the current entity.

        This is an inverse lookup - instead of following relations FROM the entity,
        we search for entities that have a relation TO this entity.

        For example, if albums have "has_context" pointing to a context entity,
        calling this with relation_type="has_context" will find all albums
        that reference the current context.

        Args:
            entity: The current entity (target of the relation)
            relation_type: The property/relation name to search for (e.g., "has_context")
            target_type: Optional entity type to filter results (e.g., "album")

        Returns:
            List of entities that have relation_type pointing to this entity
        """
        entity_id = entity.get("_id") or entity.get("id")
        related_entities = []

        try:
            # Build query parameters for collection API
            # Search for entities where the relation_type property contains this entity's ID
            params = {
                f"property_{relation_type}": entity_id,
                "limit": 100,
            }
            if target_type:
                params["type"] = target_type

            # Query collection API for entities with this property value
            query_string = "&".join(f"{k}={v}" for k, v in params.items())
            response = self._get_from_collection_api(f"/entities?{query_string}")

            if response and "results" in response:
                related_entities = response["results"]
            elif response and isinstance(response, list):
                related_entities = response

            # Filter out self-references (entity shouldn't appear in its own children)
            related_entities = [
                e for e in related_entities
                if (e.get("_id") or e.get("id")) != entity_id
            ]

        except Exception as e:
            logger.warning(
                f"Failed to fetch entities by inverse relation {relation_type}={entity_id}: {e}"
            )

        return related_entities

    def _extract_mapped_value(
        self, entity: dict, iiif_property: str
    ) -> Optional[str]:
        """
        Extract a value from entity metadata using configured mappings.

        Args:
            entity: The entity to extract from
            iiif_property: The IIIF property to get value for

        Returns:
            The extracted value or None
        """
        # First try configured mappings
        mapping = self._config.get_mapping_for_iiif_property(iiif_property)
        if mapping:
            value = self._get_item_metadata_value(entity, mapping.elody_key)
            if value:
                return value

        # Fall back to default mappings
        for default_mapping in DEFAULT_METADATA_MAPPINGS:
            if default_mapping.iiif_property == iiif_property:
                value = self._get_item_metadata_value(
                    entity, default_mapping.elody_key
                )
                if value:
                    return value

        return None

    def _get_entity_thumbnail(self, entity: dict) -> Optional[dict]:
        """
        Get a thumbnail for an entity from its mediafiles.

        Tries multiple strategies:
        1. Use primary_mediafile_id if present on entity
        2. Look for hasMediafile relations on entity
        3. For inverse-fetched entities, check the relations array

        Args:
            entity: The entity to get thumbnail for

        Returns:
            IIIF thumbnail object or None
        """
        try:
            filename = None

            # Strategy 1: Check for primary_mediafile_id
            primary_mediafile_id = entity.get("primary_mediafile_id")
            if primary_mediafile_id:
                filename = self._get_mediafile_filename(primary_mediafile_id)

            # Strategy 2: Check relations array for hasMediafile
            if not filename:
                for relation in entity.get("relations", []):
                    if relation.get("type") in ("hasMediafile", "hasPrimaryMediafile"):
                        mediafile_id = relation.get("key")
                        if mediafile_id:
                            filename = self._get_mediafile_filename(mediafile_id)
                            if filename:
                                break

            # Strategy 3: For albums/contexts, try to get thumbnail from first child
            # by doing an inverse lookup for media with has_album pointing here
            if not filename and entity.get("type") in ("album", "context"):
                entity_id = entity.get("_id") or entity.get("id")
                child_entities = self._get_entities_by_inverse_relation(
                    entity, "has_album", "media"
                )
                if not child_entities:
                    child_entities = self._get_entities_by_inverse_relation(
                        entity, "has_context", "media"
                    )
                if child_entities:
                    # Recursively get thumbnail from first child
                    return self._get_entity_thumbnail(child_entities[0])

            if filename:
                return {
                    "id": f"{self.image_api_url_ext}/iiif/3/{filename}/full/200,/0/default.jpg",
                    "type": "Image",
                    "format": "image/jpeg",
                }

        except Exception as e:
            logger.warning(f"Failed to get thumbnail for entity: {e}")

        return None

    def _get_mediafile_filename(self, mediafile_id: str) -> Optional[str]:
        """
        Get the filename from a mediafile entity.

        Args:
            mediafile_id: ID of the mediafile entity

        Returns:
            Filename string or None
        """
        try:
            mediafile = self._get_from_collection_api(
                f"/mediafiles/{mediafile_id}", entity=True
            )
            if mediafile:
                # Try different locations for filename
                # 1. Direct metadata.filename
                metadata = mediafile.get("metadata", {})
                if isinstance(metadata, dict):
                    filename = metadata.get("filename")
                    if filename:
                        return filename

                # 2. From metadata array (Elody format)
                if isinstance(metadata, list):
                    for m in metadata:
                        if m.get("key") == "filename":
                            return m.get("value")

                # 3. display_filename field
                if mediafile.get("display_filename"):
                    return mediafile.get("display_filename")

                # 4. From identifiers (often contains filename)
                for identifier in mediafile.get("identifiers", []):
                    if "." in identifier and not identifier.startswith("MED-"):
                        return identifier

        except Exception as e:
            logger.warning(f"Failed to get mediafile {mediafile_id}: {e}")

        return None

    def _make_language_map(
        self, value: str, language: str = "nl"
    ) -> dict[str, list[str]]:
        """
        Create an IIIF language map from a string value.

        Args:
            value: The string value
            language: Language code (default: "nl")

        Returns:
            Language map dictionary
        """
        return {language: [value]}
