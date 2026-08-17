import os

import pytest  # noqa: F401

os.environ.setdefault("COLLECTION_API_URL", "http://collection.test/")
os.environ.setdefault("IMAGE_API_URL", "http://image.test")
os.environ.setdefault("IMAGE_API_URL_EXT", "http://image.ext.test")
os.environ.setdefault(
    "PRESENTATION_API_URL", "http://present.test/iiif-manifest-service/"
)

from generatorv3 import ManifestGeneratorv3
from iiif_prezi3 import Manifest


def _manifest():
    return Manifest(id="http://present.test/manifest/entity-1", label="Some entity")


def _mediafile(**overrides):
    mf = {
        "_id": "mf-1",
        "filename": "0123456789abcdef0123456789abcdef-DIG 30965.tif",
        "original_filename": "Adam en Eva.tif",
        "mimetype": "image/tiff",
        "metadata": [{"key": "source", "value": "Some archive"}],
    }
    mf.update(overrides)
    return mf


def _add_canvas(mediafile):
    generator = ManifestGeneratorv3()
    manifest = _manifest()
    generator._ManifestGeneratorv3__add_canvas_to_manifest(manifest, mediafile)
    return manifest.items[0]


def test_canvas_label_is_original_filename():
    canvas = _add_canvas(_mediafile())

    assert canvas.label == {"none": ["Adam en Eva.tif"]}


def test_canvas_label_strips_uuid_prefix_when_no_original_filename():
    mediafile = _mediafile()
    del mediafile["original_filename"]

    canvas = _add_canvas(mediafile)

    assert canvas.label == {"none": ["DIG 30965.tif"]}


def test_canvas_label_falls_back_to_filename_without_uuid_prefix():
    canvas = _add_canvas(_mediafile(filename="DIG30965.tif", original_filename=None))

    assert canvas.label == {"none": ["DIG30965.tif"]}


def test_canvas_id_still_uses_stored_filename():
    canvas = _add_canvas(_mediafile())

    assert canvas.id.endswith("0123456789abcdef0123456789abcdef-DIG%2030965.tif.json")
