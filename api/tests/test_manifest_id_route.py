import os

os.environ.setdefault("COLLECTION_API_URL", "http://collection.test/")
os.environ.setdefault("IMAGE_API_URL", "http://image.test")
os.environ.setdefault("IMAGE_API_URL_EXT", "http://image.ext.test")
os.environ.setdefault(
    "PRESENTATION_API_URL", "http://present.test/iiif-manifest-service/"
)
os.environ["HEALTH_CHECK_EXTERNAL_SERVICES"] = "False"

import pytest
from app import app


@pytest.mark.parametrize(
    "path",
    [
        # The id ConfigurableManifestGenerator puts in the manifest; viewers
        # and the canopy "IIIF Manifest" link dereference it.
        "/iiif/MED-123/manifest",
        "/iiif/manifest/MED-123",
        "/MED-123/manifest",
        "/manifest/MED-123",
    ],
)
def test_configurable_manifest_paths_resolve(path):
    adapter = app.url_map.bind("present.test")
    endpoint, args = adapter.match(path)
    assert endpoint == "configurablemanifest"
    assert args == {"entity_id": "MED-123"}
