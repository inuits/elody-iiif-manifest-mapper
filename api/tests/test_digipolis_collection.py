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


def _thumbnail_generator() -> CollectionGenerator:
    gen = _make_generator(CollectionConfig.from_dict({"name": "d"}))
    for stub in (
        "_get_entity_thumbnail",
        "_get_entities_by_inverse_relation",
        "_get_from_collection_api",
    ):
        gen.__dict__.pop(stub, None)
    return gen


def test_mediafile_entity_thumbnail_has_dimensions_and_image_service():
    gen = _thumbnail_generator()

    thumbnail = gen._get_entity_thumbnail(
        {
            "_id": "mf-1",
            "type": "mediafile",
            "filename": "abc-DIG30965.tif",
            "img_width": 4000,
            "img_height": 2000,
            "metadata": [],
        }
    )

    assert thumbnail == {
        "id": "http://image.ext.test/iiif/3/abc-DIG30965.tif/full/200,/0/default.jpg",
        "type": "Image",
        "format": "image/jpeg",
        "width": 200,
        "height": 100,
        "service": [
            {
                "id": "http://image.ext.test/iiif/3/abc-DIG30965.tif",
                "type": "ImageService3",
                "profile": "level1",
            }
        ],
    }


def test_related_mediafile_thumbnail_has_dimensions_and_image_service():
    gen = _thumbnail_generator()
    gen._get_from_collection_api = lambda endpoint, **kwargs: {
        "_id": "mf-1",
        "img_width": 1000,
        "img_height": 500,
        "metadata": [{"key": "filename", "value": "abc-DIG30965.tif"}],
    }

    thumbnail = gen._get_entity_thumbnail(
        {
            "_id": "asset-1",
            "type": "asset",
            "relations": [{"type": "hasMediafile", "key": "mf-1"}],
        }
    )

    assert thumbnail["width"] == 200
    assert thumbnail["height"] == 100
    assert thumbnail["service"] == [
        {
            "id": "http://image.ext.test/iiif/3/abc-DIG30965.tif",
            "type": "ImageService3",
            "profile": "level1",
        }
    ]


def test_thumbnail_without_dimensions_falls_back_to_square():
    gen = _thumbnail_generator()

    thumbnail = gen._get_entity_thumbnail(
        {
            "_id": "mf-1",
            "type": "mediafile",
            "filename": "abc-DIG30965.tif",
            "metadata": [],
        }
    )

    assert thumbnail["width"] == 200
    assert thumbnail["height"] == 200
