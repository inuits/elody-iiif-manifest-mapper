import json
import os

os.environ.setdefault("COLLECTION_API_URL", "http://collection.test/")
os.environ.setdefault("IMAGE_API_URL", "http://image.test")
os.environ.setdefault("IMAGE_API_URL_EXT", "http://image.ext.test")
os.environ.setdefault(
    "PRESENTATION_API_URL", "http://present.test/iiif-manifest-service/"
)
os.environ["HEALTH_CHECK_EXTERNAL_SERVICES"] = "False"

import pytest
from app import app as flask_app
from manifest_generator import ConfigurableManifestGenerator
from resources import pre_generate as pre_generate_module
from resources.pre_generate import PreGenerate

IMAGE_BASE = "https://vliz-uat.test/canopy-generator"
CONFIG = "wetenschatten"


def _mediafile(mf_id, parent_id, filename):
    return {
        "_id": mf_id,
        "type": "mediafile",
        "filename": f"{filename}.tif",
        "transcode_filename": f"{filename}-transcode-1.jpg",
        "img_width": 800,
        "img_height": 600,
        "metadata": [
            {"key": "title", "value": "Gilson (1914, fig. 12)"},
            {"key": "description", "value": "Een kwal"},
        ],
        "relations": [{"type": "belongsTo", "key": parent_id}],
    }


ENTITIES = {
    "MED-mf-1": _mediafile("MED-mf-1", "MED-media-1", "aaaa"),
    "MED-mf-2": _mediafile("MED-mf-2", "MED-media-1", "bbbb"),
    "MED-mf-3": _mediafile("MED-mf-3", "MED-media-2", "cccc"),
    "MED-media-1": {
        "_id": "MED-media-1",
        "type": "media",
        "metadata": [{"key": "title", "value": "Kwallen | Gilson 1914"}],
        "relations": [{"type": "hasAlbum", "key": "album-leaf"}],
    },
    "MED-media-2": {
        "_id": "MED-media-2",
        "type": "media",
        "metadata": [{"key": "title", "value": "Duinen | Massart 1908"}],
        "relations": [{"type": "hasAlbum", "key": "album-top"}],
    },
    "album-leaf": {
        "_id": "album-leaf",
        "type": "album",
        "metadata": [{"key": "title", "value": "Kwallen"}],
        "relations": [{"type": "hasAlbum", "key": "album-top"}],
    },
    "album-top": {
        "_id": "album-top",
        "type": "album",
        "metadata": [{"key": "title", "value": "Fauna"}],
        "relations": [],
    },
}
MEDIAFILE_IDS = ["MED-mf-1", "MED-mf-2", "MED-mf-3"]


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.headers = {}

    def json(self):
        return json.loads(json.dumps(self._payload))


class _FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, headers=None, allow_redirects=True):
        path = url.replace("http://collection.test/", "/").replace("//", "/")
        self.calls.append(path)
        if path.startswith("/entities?type=mediafile"):
            skip = int(path.split("skip=")[1].split("&")[0])
            return _Resp({"results": [ENTITIES[i] for i in MEDIAFILE_IDS][skip:]})
        if path.startswith("/entities/") and path.endswith("/mediafiles"):
            parent_id = path.split("/")[2]
            children = [
                ENTITIES[i]
                for i in MEDIAFILE_IDS
                if ENTITIES[i]["relations"][0]["key"] == parent_id
            ]
            return _Resp({"results": children})
        entity_id = path.rsplit("/", 1)[-1]
        if path.startswith(("/entities/", "/mediafiles/")) and entity_id in ENTITIES:
            return _Resp(ENTITIES[entity_id])
        return _Resp({}, 404)


@pytest.fixture
def fake_api(monkeypatch, tmp_path):
    gen = ConfigurableManifestGenerator()
    # Singleton: drop per-test stubs other tests leave on the instance.
    for attr in ("_get_from_collection_api", "_get_relation_metadata_values"):
        gen.__dict__.pop(attr, None)
    session = _FakeSession()
    monkeypatch.setattr(gen, "session", session)
    monkeypatch.setattr(gen, "headers", {})
    monkeypatch.setenv("MANIFEST_CACHE_DIR", str(tmp_path / "cache"))
    yield session
    assert gen._response_cache is None  # never left on for on-demand requests


def _cached(mf_id):
    return pre_generate_module.get_cached_manifest((mf_id, CONFIG, IMAGE_BASE))


def _pre_generate(parent_ids=None):
    with flask_app.test_request_context(
        f"/pre-generate?config_file={CONFIG}&image_base_url={IMAGE_BASE}",
        method="POST",
        json={"parentIds": parent_ids} if parent_ids is not None else None,
    ):
        return PreGenerate().post()


def _on_demand(entity_id):
    with flask_app.test_request_context(f"/iiif/{entity_id}/manifest"):
        return ConfigurableManifestGenerator().generate_manifest(
            entity_id=entity_id, config_file=CONFIG, image_base_url=IMAGE_BASE
        )


def test_pre_generate_caches_every_mediafile(fake_api):
    body, status = _pre_generate()

    assert status == 200
    assert body["manifests_generated"] == 3
    for mf_id in MEDIAFILE_IDS:
        assert _cached(mf_id) is not None


def test_pre_generated_manifest_equals_on_demand_manifest(fake_api):
    # Guards the fixes the on-demand path already has (manifest id path with
    # config_file, filename image ids, parent/recursive album metadata) from
    # silently diverging in the cached copies canopy is served.
    _pre_generate()

    for mf_id in MEDIAFILE_IDS:
        assert _cached(mf_id) == _on_demand(mf_id)


def test_pre_generated_manifest_has_expected_shape(fake_api):
    _pre_generate()
    manifest = _cached("MED-mf-1")

    assert manifest["id"].startswith(
        "http://present.test/iiif-manifest-service/iiif/MED-mf-1/manifest?config_file=wetenschatten"
    )
    body = manifest["items"][0]["items"][0]["items"][0]["body"]
    assert (
        body["id"] == f"{IMAGE_BASE}/iiif/3/aaaa-transcode-1.jpg/full/max/0/default.jpg"
    )
    labels = {m["label"]["nl"][0]: m["value"]["nl"] for m in manifest["metadata"]}
    assert labels["Auteur"] == ["Gilson"]
    assert labels["Periode"] == ["1914"]
    assert labels["Thema"] == ["Kwallen"]
    album_values = [
        m["value"]["nl"][0]
        for m in manifest["metadata"]
        if m["label"]["nl"] == ["Album"]
    ]
    assert album_values == ["Kwallen", "Fauna"]


def test_pre_generate_fetches_each_shared_entity_once(fake_api):
    _pre_generate()

    assert fake_api.calls.count("/entities/MED-media-1") == 1
    assert fake_api.calls.count("/entities/album-top") == 1


def test_on_demand_requests_are_not_served_from_the_batch_response_cache(fake_api):
    _pre_generate()
    before = fake_api.calls.count("/entities/MED-media-1")

    _on_demand("MED-mf-1")

    assert fake_api.calls.count("/entities/MED-media-1") == before + 1


def test_cached_manifest_is_served_without_collection_api_calls(fake_api):
    # The cache lives on disk, so every gunicorn worker serves what one
    # worker's pre-generate run wrote.
    from resources.configurable_manifest import ConfigurableManifest

    _pre_generate()
    calls_before = len(fake_api.calls)

    with flask_app.test_request_context(
        f"/iiif/MED-mf-3/manifest?config_file={CONFIG}&image_base_url={IMAGE_BASE}"
    ):
        body, status, _headers = ConfigurableManifest().get("MED-mf-3")

    assert status == 200
    assert body == _cached("MED-mf-3")
    assert len(fake_api.calls) == calls_before


def test_a_new_pre_generate_run_replaces_cached_manifests(fake_api):
    _pre_generate()
    original = ENTITIES["MED-mf-1"]["metadata"][1]["value"]
    ENTITIES["MED-mf-1"]["metadata"][1]["value"] = "Een andere kwal"
    try:
        _pre_generate()
        assert _cached("MED-mf-1")["summary"] == {"nl": ["Een andere kwal"]}
    finally:
        ENTITIES["MED-mf-1"]["metadata"][1]["value"] = original


def test_pre_generate_can_be_limited_to_given_parents(fake_api):
    # A canopy build only needs the mediafiles of the media in its
    # collections, not every mediafile in the tenant.
    body, status = _pre_generate(parent_ids=["MED-media-2"])

    assert status == 200
    assert body["manifests_generated"] == 1
    assert _cached("MED-mf-3") == _on_demand("MED-mf-3")
    assert _cached("MED-mf-1") is None
    assert not any(c.startswith("/entities?type=mediafile") for c in fake_api.calls)
