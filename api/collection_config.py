"""
IIIF Collection Configuration - Parse collection config from Elody entities or JSON files.

This module provides dataclasses and utilities for parsing IIIF Collection
configuration from Elody entity structures or JSON configuration files.
Configuration entities define how to traverse the Elody entity graph and
map entities to IIIF resources.

Entity Types:
- iiifCollectionConfig: Root configuration entity
- iiifTraversalStep: Defines how to follow relations
- iiifMetadataMapping: Maps Elody metadata to IIIF properties

JSON Config Format:
- See config/ directory for example JSON configuration files
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class TraversalStep:
    """
    Defines a single step in traversing the Elody entity graph.

    Attributes:
        relation_type: The relation type to follow (e.g., "hasAlbum", "hasMedia")
        maps_to_iiif: What IIIF type this level maps to ("Collection" or "Manifest")
        order: The order of this step in the traversal
        include_thumbnails: Whether to include thumbnails for items at this level
        max_depth: Maximum depth to traverse (None for unlimited)
        inverse: If True, search for entities that have relation_type pointing TO
                 the current entity (e.g., find albums where has_context = current_id)
        target_type: When using inverse lookup, the entity type to search for
    """

    relation_type: str
    maps_to_iiif: str  # "Collection" | "Manifest" | "Canvas"
    order: int
    include_thumbnails: bool = True
    max_depth: Optional[int] = None
    inverse: bool = False
    target_type: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "TraversalStep":
        """Create TraversalStep from a dictionary (JSON config)."""
        return cls(
            relation_type=data.get("relationType", ""),
            maps_to_iiif=data.get("mapsToIIIF", "Collection"),
            order=int(data.get("order", 0)),
            include_thumbnails=data.get("includeThumbnails", True),
            max_depth=int(data["maxDepth"]) if "maxDepth" in data else None,
            inverse=data.get("inverse", False),
            target_type=data.get("targetType"),
        )

    @classmethod
    def from_elody_entity(cls, entity: dict) -> "TraversalStep":
        """Create TraversalStep from an Elody iiifTraversalStep entity."""
        metadata = {m["key"]: m["value"] for m in entity.get("metadata", [])}

        return cls(
            relation_type=metadata.get("relationType", ""),
            maps_to_iiif=metadata.get("mapsToIIIF", "Collection"),
            order=int(metadata.get("order", 0)),
            include_thumbnails=metadata.get("includeThumbnails", "true").lower()
            == "true",
            max_depth=int(metadata["maxDepth"]) if "maxDepth" in metadata else None,
            inverse=metadata.get("inverse", "false").lower() == "true",
            target_type=metadata.get("targetType"),
        )


@dataclass
class MetadataMapping:
    """
    Maps an Elody metadata key to an IIIF property.

    Attributes:
        elody_key: The metadata key in Elody entities (e.g., "title")
        iiif_property: The IIIF property to map to (e.g., "label")
        language: Optional language code for the value (e.g., "nl", "en")
        transform: Optional transformation to apply (e.g., "uppercase")
        relation_type: For source="relation", the relation type to follow (e.g., "hasCreator")
        related_key: For source="relation", the metadata key on the related entity (default: "title")
    """

    elody_key: str = ""
    iiif_property: str = ""
    language: Optional[str] = None
    transform: Optional[str] = None
    source: str = "entity"
    relation_type: Optional[str] = None
    related_key: str = "title"
    regex: Optional[str] = None  # Extract value via regex capture group
    max_values: Optional[int] = None  # Limit number of values for this mapping

    @classmethod
    def from_dict(cls, data: dict) -> "MetadataMapping":
        """Create MetadataMapping from a dictionary (JSON config)."""
        return cls(
            elody_key=data.get("elodyKey", ""),
            iiif_property=data.get("iiifProperty", ""),
            language=data.get("language"),
            transform=data.get("transform"),
            source=data.get("source", "entity"),
            relation_type=data.get("relationType"),
            related_key=data.get("relatedKey", "title"),
            regex=data.get("regex"),
            max_values=data.get("maxValues"),
        )

    @classmethod
    def from_elody_entity(cls, entity: dict) -> "MetadataMapping":
        """Create MetadataMapping from an Elody iiifMetadataMapping entity."""
        metadata = {m["key"]: m["value"] for m in entity.get("metadata", [])}

        return cls(
            elody_key=metadata.get("elodyKey", ""),
            iiif_property=metadata.get("iiifProperty", ""),
            language=metadata.get("language"),
            transform=metadata.get("transform"),
            source=metadata.get("source", "entity"),
            relation_type=metadata.get("relationType"),
            related_key=metadata.get("relatedKey", "title"),
        )


@dataclass
class CollectionConfig:
    """
    Complete configuration for generating an IIIF Collection from Elody data.

    Attributes:
        name: Human-readable name for the collection
        description: Optional description of the collection
        iiif_version: IIIF Presentation API version (2 or 3)
        traversal_steps: List of steps defining how to traverse the entity graph
        metadata_mappings: List of metadata field mappings
        featured_ids: List of entity IDs to feature prominently
        rights_uri: Default rights/license URI
        attribution: Default attribution text
        base_url: Base URL for generated IIIF resources
        viewing_direction: Manifest viewingDirection (e.g. "left-to-right")
        behavior: Manifest behavior (e.g. "paged")
        provider: IIIF provider block (list of Agent dicts)
    """

    name: str
    description: Optional[str] = None
    iiif_version: int = 3
    traversal_steps: list[TraversalStep] = field(default_factory=list)
    metadata_mappings: list[MetadataMapping] = field(default_factory=list)
    featured_ids: list[str] = field(default_factory=list)
    rights_uri: Optional[str] = None
    attribution: Optional[str] = None
    base_url: Optional[str] = None
    viewing_direction: Optional[str] = None
    behavior: Optional[str] = None
    provider: Optional[list] = None

    @classmethod
    def from_dict(cls, data: dict) -> "CollectionConfig":
        """
        Create CollectionConfig from a dictionary.

        Args:
            data: Configuration dictionary

        Returns:
            Configured CollectionConfig instance
        """
        # Parse traversal steps
        traversal_steps = []
        for step_data in data.get("traversalSteps", []):
            step = TraversalStep.from_dict(step_data)
            traversal_steps.append(step)
        traversal_steps.sort(key=lambda x: x.order)

        # Parse metadata mappings
        mappings = []
        for mapping_data in data.get("metadataMappings", []):
            mapping = MetadataMapping.from_dict(mapping_data)
            mappings.append(mapping)

        return cls(
            name=data.get("name", "Collection"),
            description=data.get("description"),
            iiif_version=int(data.get("iiifVersion", 3)),
            traversal_steps=traversal_steps,
            metadata_mappings=mappings,
            featured_ids=data.get("featuredIds", []),
            rights_uri=data.get("rightsUri"),
            attribution=data.get("attribution"),
            base_url=data.get("baseUrl"),
            viewing_direction=data.get("viewingDirection"),
            behavior=data.get("behavior"),
            provider=data.get("provider"),
        )

    @classmethod
    def from_json_file(cls, config_name: str, config_dir: str = None) -> "CollectionConfig":
        """
        Create CollectionConfig from a JSON configuration file.

        Args:
            config_name: Name of the config file (without .json extension)
            config_dir: Optional directory containing config files.
                       Defaults to 'config/' relative to this module.

        Returns:
            Configured CollectionConfig instance

        Raises:
            FileNotFoundError: If the config file doesn't exist
            json.JSONDecodeError: If the config file contains invalid JSON
        """
        if config_dir is None:
            # Default to config/ directory relative to this module
            config_dir = Path(__file__).parent.parent / "config"
        else:
            config_dir = Path(config_dir)

        config_path = config_dir / f"{config_name}.json"

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return cls.from_dict(data)

    @classmethod
    def from_elody_entity(
        cls,
        entity: dict,
        traversal_entities: list[dict] = None,
        mapping_entities: list[dict] = None,
    ) -> "CollectionConfig":
        """
        Create CollectionConfig from an Elody iiifCollectionConfig entity.

        Args:
            entity: The iiifCollectionConfig entity
            traversal_entities: List of related iiifTraversalStep entities
            mapping_entities: List of related iiifMetadataMapping entities

        Returns:
            Configured CollectionConfig instance
        """
        metadata = {m["key"]: m["value"] for m in entity.get("metadata", [])}

        # Parse traversal steps from related entities
        traversal_steps = []
        if traversal_entities:
            for te in traversal_entities:
                step = TraversalStep.from_elody_entity(te)
                traversal_steps.append(step)
            traversal_steps.sort(key=lambda x: x.order)

        # Parse metadata mappings from related entities
        mappings = []
        if mapping_entities:
            for me in mapping_entities:
                mapping = MetadataMapping.from_elody_entity(me)
                mappings.append(mapping)

        # Extract featured IDs from relations
        featured_ids = []
        for relation in entity.get("relations", []):
            if relation.get("type") == "hasFeaturedItem":
                featured_ids.append(relation.get("key"))

        return cls(
            name=metadata.get("name", "Collection"),
            description=metadata.get("description"),
            iiif_version=int(metadata.get("iiifVersion", 3)),
            traversal_steps=traversal_steps,
            metadata_mappings=mappings,
            featured_ids=featured_ids,
            rights_uri=metadata.get("rightsUri"),
            attribution=metadata.get("attribution"),
            base_url=metadata.get("baseUrl"),
        )

    def get_mapping_for_iiif_property(
        self, iiif_property: str
    ) -> Optional[MetadataMapping]:
        """Get the metadata mapping for a specific IIIF property."""
        for mapping in self.metadata_mappings:
            if mapping.iiif_property == iiif_property:
                return mapping
        return None

    def get_step_for_relation(self, relation_type: str) -> Optional[TraversalStep]:
        """Get the traversal step for a specific relation type."""
        for step in self.traversal_steps:
            if step.relation_type == relation_type:
                return step
        return None


# Default metadata mappings for common Elody fields
DEFAULT_METADATA_MAPPINGS = [
    MetadataMapping(elody_key="title", iiif_property="label", language="nl"),
    MetadataMapping(elody_key="description", iiif_property="summary", language="nl"),
    MetadataMapping(elody_key="rights", iiif_property="rights"),
    MetadataMapping(elody_key="source", iiif_property="attribution"),
]
