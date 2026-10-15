import os

os.environ.setdefault("COLLECTION_API_URL", "http://collection.test/")
os.environ.setdefault("IMAGE_API_URL", "http://image.test")
os.environ.setdefault("IMAGE_API_URL_EXT", "http://image.ext.test")
os.environ.setdefault(
    "PRESENTATION_API_URL", "http://present.test/iiif-manifest-service/"
)

import pytest
from collection_config import CollectionConfig, MetadataMapping
from collection_generator import CollectionGenerator
from manifest_generator import ConfigurableManifestGenerator


def _album(album_id, title, parent_id=None):
    relations = [{"type": "hasContext", "key": "context-1"}]
    if parent_id:
        relations.append({"type": "hasAlbum", "key": parent_id})
    return {
        "_id": album_id,
        "type": "album",
        "metadata": [{"key": "title", "value": title}],
        "relations": relations,
    }


# top-album > mid-album > leaf-album, plus a media item in the leaf album.
ENTITIES = {
    "top-album": _album("top-album", "Top"),
    "mid-album": _album("mid-album", "Mid", parent_id="top-album"),
    "leaf-album": _album("leaf-album", "Leaf", parent_id="mid-album"),
    "loop-a": _album("loop-a", "Loop A", parent_id="loop-b"),
    "loop-b": _album("loop-b", "Loop B", parent_id="loop-a"),
}

MEDIA = {
    "_id": "media-1",
    "type": "media",
    "metadata": [{"key": "title", "value": "Some media"}],
    "relations": [{"type": "hasAlbum", "key": "leaf-album"}],
}


def _fake_get(endpoint, entity=False, **kwargs):
    entity_id = endpoint.rsplit("/", 1)[-1]
    return ENTITIES[entity_id]


def _album_values(metadata):
    return [m["value"]["nl"][0] for m in metadata if m["label"]["nl"] == ["Album"]]


def test_mapping_recursive_flag_defaults_off_and_parses_from_config():
    assert MetadataMapping.from_dict({"iiifProperty": "Album"}).recursive is False
    assert (
        MetadataMapping.from_dict(
            {"iiifProperty": "Album", "recursive": True}
        ).recursive
        is True
    )


def test_wetenschatten_album_mapping_is_recursive():
    config = CollectionConfig.from_json_file("wetenschatten")
    album = next(m for m in config.metadata_mappings if m.iiif_property == "Album")
    assert album.recursive is True


@pytest.fixture
def manifest_gen(monkeypatch):
    gen = ConfigurableManifestGenerator()
    # ConfigurableManifestGenerator is a singleton and other tests stub this
    # method on the instance; drop that so the real implementation is exercised.
    gen.__dict__.pop("_get_relation_metadata_values", None)
    monkeypatch.setattr(gen, "_get_from_collection_api", _fake_get)
    return gen


def test_manifest_relation_values_follow_parent_albums_when_recursive(manifest_gen):
    values = manifest_gen._get_relation_metadata_values(
        MEDIA, "hasAlbum", "title", recursive=True
    )
    assert values == ["Leaf", "Mid", "Top"]


def test_manifest_relation_values_stay_one_level_by_default(manifest_gen):
    values = manifest_gen._get_relation_metadata_values(MEDIA, "hasAlbum", "title")
    assert values == ["Leaf"]


def test_manifest_relation_values_survive_cycles(manifest_gen):
    media = {**MEDIA, "relations": [{"type": "hasAlbum", "key": "loop-a"}]}
    values = manifest_gen._get_relation_metadata_values(
        media, "hasAlbum", "title", recursive=True
    )
    assert values == ["Loop A", "Loop B"]


def test_collection_parent_metadata_includes_ancestor_albums(monkeypatch):
    gen = CollectionGenerator()
    monkeypatch.setattr(gen, "_get_from_collection_api", _fake_get)
    monkeypatch.setattr(
        gen, "_config", CollectionConfig.from_json_file("wetenschatten")
    )

    metadata = gen._build_parent_only_metadata(MEDIA)

    assert _album_values(metadata) == ["Leaf", "Mid", "Top"]
