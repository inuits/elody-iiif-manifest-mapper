import os

os.environ.setdefault("COLLECTION_API_URL", "http://collection.test/")
os.environ.setdefault("IMAGE_API_URL", "http://image.test")
os.environ.setdefault("IMAGE_API_URL_EXT", "http://image.ext.test")
os.environ.setdefault(
    "PRESENTATION_API_URL", "http://present.test/iiif-manifest-service/"
)

import pytest
from collection_generator import CollectionGenerator
from flask import Flask


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeSession:
    """Serves pre-baked /entities/filter pages and records each POST."""

    def __init__(self, pages):
        self._pages = list(pages)
        self.calls = []

    def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResponse({"results": self._pages.pop(0)})


@pytest.fixture
def gen():
    generator = CollectionGenerator()
    # CollectionGenerator is a singleton and other tests stub this method on
    # the instance; drop that so the real implementation is exercised.
    generator.__dict__.pop("_get_entities_by_inverse_relation", None)
    with Flask(__name__).test_request_context():
        yield generator


def _entities(prefix, count):
    return [{"_id": f"{prefix}-{i}", "type": "mediafile"} for i in range(count)]


def test_inverse_lookup_uses_relation_filter_instead_of_property_param(
    gen, monkeypatch
):
    # collection-api's GET /entities ignores property_<relation> params, so
    # the lookup must go through POST /entities/filter with a relation filter.
    session = _FakeSession([_entities("mf", 2)])
    monkeypatch.setattr(gen, "session", session)

    result = gen._get_entities_by_inverse_relation(
        {"_id": "media-1"}, "belongsTo", "mediafile"
    )

    assert [e["_id"] for e in result] == ["mf-0", "mf-1"]
    call = session.calls[0]
    assert "/entities/filter?" in call["url"]
    assert "property_" not in call["url"]
    assert {"type": "type", "value": "mediafile"} in call["json"]
    assert {
        "type": "selection",
        "key": "relations.belongsTo.key",
        "value": "media-1",
        "match_exact": True,
    } in call["json"]


def test_inverse_lookup_follows_pagination_past_first_page(gen, monkeypatch):
    session = _FakeSession(
        [_entities("a", 500), _entities("b", 500), _entities("c", 3)]
    )
    monkeypatch.setattr(gen, "session", session)

    result = gen._get_entities_by_inverse_relation(
        {"_id": "album-1"}, "hasAlbum", "media"
    )

    assert len(result) == 1003
    assert [
        ("skip=0" in c["url"], "skip=500" in c["url"], "skip=1000" in c["url"])
        for c in session.calls
    ] == [
        (True, False, False),
        (False, True, False),
        (False, False, True),
    ]


def test_inverse_lookup_drops_self_references(gen, monkeypatch):
    session = _FakeSession([[{"_id": "album-1"}, {"_id": "media-9"}]])
    monkeypatch.setattr(gen, "session", session)

    result = gen._get_entities_by_inverse_relation({"_id": "album-1"}, "hasAlbum")

    assert [e["_id"] for e in result] == ["media-9"]
    # No target type → no type filter in the query
    assert all(f.get("type") != "type" for f in session.calls[0]["json"])
