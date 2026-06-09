import os

import pytest

os.environ.setdefault("COLLECTION_API_URL", "http://collection.test/")
os.environ.setdefault("IMAGE_API_URL", "http://image.test")
os.environ.setdefault("IMAGE_API_URL_EXT", "http://image.ext.test")
os.environ.setdefault("PRESENTATION_API_URL", "http://present.test/iiif-manifest-service/")

from collection_config import CollectionConfig
from manifest_generator import ConfigurableManifestGenerator


def test_config_parses_provider_viewing_direction_and_behavior():
    config = CollectionConfig.from_dict(
        {
            "name": "Digipolis",
            "iiifVersion": 3,
            "viewingDirection": "left-to-right",
            "behavior": "paged",
            "provider": [
                {
                    "id": "https://data.antwerpen.be/agent/123",
                    "type": "Agent",
                    "label": {"nl": ["Stad Antwerpen"]},
                }
            ],
        }
    )

    assert config.viewing_direction == "left-to-right"
    assert config.behavior == "paged"
    assert isinstance(config.provider, list)
    assert config.provider[0]["id"] == "https://data.antwerpen.be/agent/123"


def test_config_defaults_when_absent():
    config = CollectionConfig.from_dict({"name": "x", "iiifVersion": 3})
    assert config.viewing_direction is None
    assert config.behavior is None
    assert config.provider is None


def _make_generator(config: CollectionConfig) -> ConfigurableManifestGenerator:
    gen = ConfigurableManifestGenerator()
    gen._config = config
    gen._image_base_url = None
    gen._config_file = "digipolis"
    return gen


def _asset(**overrides):
    a = {
        "_id": "asset-1",
        "metadata": [
            {"key": "title", "value": "Adam en Eva"},
            {"key": "creator", "value": "Peter Paul Rubens"},
            {"key": "date", "value": "1598-1600"},
        ],
    }
    a.update(overrides)
    return a


def _mediafile(**overrides):
    mf = {
        "_id": "mf-1",
        "filename": "abc123-DIG30965.tif",
        "img_width": 11110,
        "img_height": 6880,
        "metadata": [
            {"key": "rights", "value": "In Copyright"},
            {"key": "attribution", "value": "Peter Paul Rubens, RH.S.164, foto: Michel Wuyts"},
        ],
    }
    mf.update(overrides)
    return mf


def test_manifest_emits_viewing_direction_behavior_provider():
    config = CollectionConfig.from_dict(
        {
            "name": "Digipolis",
            "iiifVersion": 3,
            "viewingDirection": "left-to-right",
            "behavior": "paged",
            "provider": [{"id": "https://data.antwerpen.be/agent/123", "type": "Agent"}],
        }
    )
    gen = _make_generator(config)
    entity = {"_id": "asset-1", "metadata": [{"key": "title", "value": "Adam en Eva"}]}

    manifest = gen._build_manifest(entity, [_mediafile()])

    assert manifest["viewingDirection"] == "left-to-right"
    # behavior is an array per the IIIF v3 spec
    assert manifest["behavior"] == ["paged"]
    assert manifest["provider"][0]["id"] == "https://data.antwerpen.be/agent/123"


def test_canvas_has_real_dimensions_and_jpeg_thumbnail():
    gen = _make_generator(CollectionConfig.from_dict({"name": "d", "iiifVersion": 3}))
    canvas = gen._build_canvas(_asset(), _mediafile(), 0)

    assert canvas["width"] == 11110
    assert canvas["height"] == 6880
    assert canvas["thumbnail"][0]["format"] == "image/jpeg"
    assert canvas["thumbnail"][0]["id"].endswith("/full/200,/0/default.jpg")


def test_canvas_dimensions_read_from_top_level_fields():
    """img_width/img_height live at the top level of digipolis mediafiles,
    not inside the metadata dict."""
    gen = _make_generator(CollectionConfig.from_dict({"name": "d", "iiifVersion": 3}))
    mf = _mediafile(metadata=[], img_width=4000, img_height=3000)
    canvas = gen._build_canvas(_asset(), mf, 0)
    assert canvas["width"] == 4000
    assert canvas["height"] == 3000


def test_body_has_service_format_dimensions_and_label():
    gen = _make_generator(CollectionConfig.from_dict({"name": "d", "iiifVersion": 3}))
    canvas = gen._build_canvas(_asset(), _mediafile(), 0)
    body = canvas["items"][0]["items"][0]["body"]

    assert body["format"] == "image/jpeg"
    assert body["width"] == 11110
    assert body["height"] == 6880
    assert body["label"]["nl"] == ["abc123-DIG30965.tif"]
    assert body["service"][0]["type"] == "ImageService3"
    assert body["id"].endswith("/full/max/0/default.jpg")


def test_canvas_has_per_image_rights_and_required_statement():
    gen = _make_generator(CollectionConfig.from_dict({"name": "d", "iiifVersion": 3}))
    canvas = gen._build_canvas(_asset(), _mediafile(), 0)

    assert canvas["rights"] == "http://rightsstatements.org/vocab/InC/1.0/"
    value_map = canvas["requiredStatement"]["value"]
    assert any(v for v in value_map.values())


def test_canvas_label_generated_from_asset_fields():
    gen = _make_generator(CollectionConfig.from_dict({"name": "d", "iiifVersion": 3}))
    canvas = gen._build_canvas(_asset(), _mediafile(), 0)
    caption = canvas["label"]["nl"][0]

    assert "Adam en Eva" in caption
    assert "Peter Paul Rubens" in caption
    assert "1598-1600" in caption
    assert ".tif" not in caption


def test_canvas_label_falls_back_to_filename_when_no_asset_metadata():
    gen = _make_generator(CollectionConfig.from_dict({"name": "d", "iiifVersion": 3}))
    canvas = gen._build_canvas({"_id": "asset-1", "metadata": []}, _mediafile(metadata=[]), 0)
    assert canvas["label"]["nl"] == ["abc123-DIG30965.tif"]


def test_identifiers_are_well_formed():
    gen = _make_generator(CollectionConfig.from_dict({"name": "d", "iiifVersion": 3}))
    canvas = gen._build_canvas(_asset(), _mediafile(), 0)

    assert "servicecanvas" not in canvas["id"]
    page = canvas["items"][0]
    anno = page["items"][0]
    assert page["id"].startswith("http")
    assert "annotationpageLink" not in page["id"]
    assert "annotationLink" not in anno["id"]
    assert anno["target"] == canvas["id"]
