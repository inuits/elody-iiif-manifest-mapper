import os

os.environ.setdefault("COLLECTION_API_URL", "http://collection.test/")
os.environ.setdefault("IMAGE_API_URL", "http://image.test")
os.environ.setdefault("IMAGE_API_URL_EXT", "http://image.ext.test")
os.environ.setdefault(
    "PRESENTATION_API_URL", "http://present.test/iiif-manifest-service/"
)

from collection_config import CollectionConfig
from manifest_generator import ConfigurableManifestGenerator

IMAGE_BASE = "http://proxy.test/canopy-generator"


def _generator(config_dict: dict) -> ConfigurableManifestGenerator:
    gen = ConfigurableManifestGenerator()
    gen._config = CollectionConfig.from_dict(config_dict)
    gen._image_base_url = IMAGE_BASE
    gen._config_file = None
    return gen


def _media():
    return {"_id": "MED-media-1", "metadata": [{"key": "title", "value": "Plate"}]}


def _mediafile(**overrides):
    mf = {
        "_id": "MED-dfbd670d-4991-4b56-a150-1862cd04f942",
        "filename": "2553ca04-original.tif",
        "transcode_filename": "2553ca04-transcode-52742.jpg",
        "original_filename": "plate 4.tif",
        "img_width": 762,
        "img_height": 1156,
    }
    mf.update(overrides)
    return mf


def _image_urls(canvas: dict) -> list[str]:
    body = canvas["items"][0]["items"][0]["body"]
    return [body["id"], body["service"][0]["id"], canvas["thumbnail"][0]["id"]]


def test_config_image_identifier_defaults_to_id():
    assert CollectionConfig.from_dict({"name": "x"}).image_identifier == "id"


def test_config_parses_image_identifier():
    config = CollectionConfig.from_dict({"name": "x", "imageIdentifier": "filename"})
    assert config.image_identifier == "filename"


def test_default_uses_mediafile_id():
    canvas = _generator({"name": "x"})._build_canvas(_media(), _mediafile(), 0)
    for url in _image_urls(canvas):
        assert url.startswith(f"{IMAGE_BASE}/iiif/3/MED-dfbd670d-")


def test_filename_mode_uses_transcode_filename():
    gen = _generator({"name": "x", "imageIdentifier": "filename"})
    canvas = gen._build_canvas(_media(), _mediafile(), 0)
    for url in _image_urls(canvas):
        assert url.startswith(f"{IMAGE_BASE}/iiif/3/2553ca04-transcode-52742.jpg")


def test_filename_mode_falls_back_to_stored_filename_not_original_name():
    gen = _generator({"name": "x", "imageIdentifier": "filename"})
    mf = _mediafile(transcode_filename=None)
    canvas = gen._build_canvas(_media(), mf, 0)
    for url in _image_urls(canvas):
        assert url.startswith(f"{IMAGE_BASE}/iiif/3/2553ca04-original.tif")


def test_filename_mode_thumbnail_from_mediafile():
    gen = _generator({"name": "x", "imageIdentifier": "filename"})
    thumb = gen._get_thumbnail_from_mediafile(_mediafile())
    assert thumb["id"].startswith(f"{IMAGE_BASE}/iiif/3/2553ca04-transcode-52742.jpg")


def test_wetenschatten_config_uses_filename():
    assert CollectionConfig.from_json_file("wetenschatten").image_identifier == "filename"
