import os

os.environ.setdefault("COLLECTION_API_URL", "http://collection.test/")
os.environ.setdefault("IMAGE_API_URL", "http://image.test")
os.environ.setdefault("IMAGE_API_URL_EXT", "http://image.ext.test")
os.environ.setdefault(
    "PRESENTATION_API_URL", "http://present.test/iiif-manifest-service/"
)

from collection_config import CollectionConfig
from collection_generator import CollectionGenerator


def _make_generator(config: CollectionConfig) -> CollectionGenerator:
    gen = CollectionGenerator()
    gen._config = config
    gen._config_file = "digipolis"
    gen._image_base_url = None
    return gen


def test_collection_emits_provider_and_manifest_items():
    config = CollectionConfig.from_json_file("digipolis")
    gen = _make_generator(config)

    institution = {
        "_id": "inst-1",
        "type": "institution",
        "metadata": [{"key": "name", "value": "Rubenshuis"}],
    }

    # Stub the inverse-relation lookup (institution -> assets) so the test
    # stays offline; return one asset that should become a Manifest ref.
    gen._get_entities_by_inverse_relation = lambda entity, rel, target=None: [
        {
            "_id": "asset-1",
            "type": "asset",
            "metadata": [{"key": "title", "value": "Adam en Eva"}],
        }
    ]
    gen._get_entity_thumbnail = lambda entity: None

    collection = gen._build_collection(
        institution, step_index=0, current_depth=0, max_depth=None
    )

    assert collection["type"] == "Collection"
    assert collection["label"]["nl"] == ["Rubenshuis"]
    assert collection["provider"][0]["label"] == {"nl": ["Stad Antwerpen"]}

    items = collection["items"]
    assert len(items) == 1
    assert items[0]["type"] == "Collection"
    # Manifest ref points at the configurable endpoint with the digipolis config
    assert "/iiif-manifest-service/collection/asset-1" in items[0]["id"]
    assert "config_file=digipolis" in items[0]["id"]
