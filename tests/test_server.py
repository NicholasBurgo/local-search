from leadfinder.config import Settings
from leadfinder.models import Lead
from leadfinder.server import (
    config_endpoint,
    geocode_endpoint,
    mark_endpoint,
    read_static,
    reverify_endpoint,
    saved_endpoint,
    search_endpoint,
    stats_endpoint,
    suggest_endpoint,
    verify_endpoint,
)
from leadfinder.store import LeadStore

BBOX = (-90.17, 30.43, -90.05, 30.55)


def _settings():
    return Settings(cities=["Covington LA"], source="overture", output_dir="/tmp")


def test_geocode_endpoint():
    out = geocode_endpoint({"q": "Covington LA"}, geocoder=lambda q: BBOX)
    assert out["center"] == [(30.43 + 30.55) / 2, (-90.17 - 90.05) / 2]
    assert out["bbox"] == list(BBOX)
    assert out["label"] == "Covington LA"


def test_geocode_missing_and_failure():
    assert "error" in geocode_endpoint({})

    def boom(q):
        raise ValueError("nope")

    assert "error" in geocode_endpoint({"q": "x"}, geocoder=boom)


def test_search_by_query_builds_bbox_and_records():
    captured = {}

    def fake_fetch(bbox, release, min_confidence, allowed_categories):
        captured["bbox"] = bbox
        captured["conf"] = min_confidence
        return [
            Lead(
                name="Joe",
                city="Covington LA",
                latitude=30.47,
                longitude=-90.1,
                phone="555",
                confidence=0.9,
                source="overture",
            )
        ]

    out = search_endpoint(
        {"q": "Covington LA", "radius_miles": 10},
        _settings(),
        fetch=fake_fetch,
        geocoder=lambda q: BBOX,
    )
    assert out["count"] == 1
    assert out["radius_miles"] == 10
    lead = out["leads"][0]
    assert lead["name"] == "Joe"
    assert lead["latitude"] == 30.47
    assert "quality" in lead  # score computed via lead_records
    # bbox centered on the geocoded center (~-90.11), widened westward by 10 mi
    assert captured["bbox"][0] < -90.11


def test_search_by_coords_and_missing_location():
    out = search_endpoint(
        {"lat": 30.47, "lon": -90.1, "radius_miles": 5},
        _settings(),
        fetch=lambda *a, **k: [],
        geocoder=None,
    )
    assert out["count"] == 0
    assert out["center"] == [30.47, -90.1]

    assert "error" in search_endpoint(
        {"radius_miles": 5}, _settings(), fetch=lambda *a, **k: [], geocoder=None
    )


def test_search_reports_fetch_error():
    def boom(*a, **k):
        raise RuntimeError("s3 down")

    out = search_endpoint({"lat": 30, "lon": -90, "radius_miles": 5}, _settings(), fetch=boom)
    assert "error" in out and "s3 down" in out["error"]


def test_config_endpoint():
    out = config_endpoint(_settings())
    assert out["defaultLocation"] == "Covington LA"
    assert out["defaultRadius"] >= 1
    assert isinstance(out["categories"], list) and out["categories"][0]["key"]


def test_suggest_endpoint():
    def fake(q):
        return [{"label": "Mandeville, LA", "lat": 30.36, "lon": -90.06}]

    out = suggest_endpoint({"q": "Mande"}, suggester=fake)
    assert out["suggestions"][0]["label"].startswith("Mandeville")
    # too short: no suggester call, empty result
    assert suggest_endpoint({"q": "ab"})["suggestions"] == []


def test_read_static_serves_frontend():
    index = read_static("/")
    assert index is not None
    body, ctype = index
    assert b"Leadfinder" in body and "text/html" in ctype
    assert read_static("/app.js") is not None
    assert read_static("/app.css") is not None
    assert read_static("/leaflet.js") is not None
    assert read_static("/review") is not None  # review page
    assert read_static("/review.js") is not None
    assert read_static("/nope") is None  # not whitelisted


def test_search_persists_and_merges_marks(tmp_path):
    store = LeadStore(str(tmp_path / "db.duckdb"))
    store.upsert([{"place_id": "P1", "name": "Joe", "source": "overture"}])
    store.mark("P1", stage="accepted")

    def fake_fetch(bbox, release, min_confidence, allowed_categories):
        return [
            Lead(
                name="Joe",
                city="Covington LA",
                place_id="P1",
                latitude=30.4,
                longitude=-90.1,
                phone="555",
                source="overture",
                confidence=0.9,
            )
        ]

    out = search_endpoint(
        {"lat": 30.4, "lon": -90.1, "radius_miles": 10},
        _settings(),
        store,
        fetch=fake_fetch,
        geocoder=None,
    )
    lead = out["leads"][0]
    assert lead["place_id"] == "P1"
    assert lead["stage"] == "accepted"  # merged from the store onto the fresh record
    assert store.stats()["listed"] == 1


def test_saved_mark_stats_endpoints(tmp_path):
    store = LeadStore(str(tmp_path / "db.duckdb"))
    store.upsert(
        [
            {"place_id": "P1", "name": "Joe", "source": "overture", "quality": 80},
            {"place_id": "P2", "name": "Bob", "source": "overture", "quality": 60},
        ]
    )
    assert saved_endpoint({}, store)["count"] == 2
    assert mark_endpoint({"place_id": "P1", "stage": "possible"}, store)["ok"] is True
    assert saved_endpoint({"filter": "possible"}, store)["count"] == 1
    assert stats_endpoint(store)["possible"] == 1
    assert "error" in mark_endpoint({}, store)  # missing place_id


def test_reverify_endpoint(tmp_path):
    store = LeadStore(str(tmp_path / "db.duckdb"))
    store.upsert([{"place_id": "P1", "name": "Joe", "source": "overture"}])

    def fake_verify(rows):
        return [
            {**rows[0], "verification_status": "REMOVED_HAS_WEBSITE", "verified_date": "2026-07-02"}
        ]

    out = reverify_endpoint({}, _settings(), store, verifier=fake_verify)
    assert out["count"] == 1
    assert store.get(["P1"])["P1"]["verification_status"] == "REMOVED_HAS_WEBSITE"


def test_verify_endpoint():
    rows = [{"name": "Joe", "city": "Covington LA", "quality": 80}]

    def fake_verify(r):
        return [{**r[0], "verification_status": "VERIFIED_NO_WEBSITE"}]

    out = verify_endpoint({"leads": rows}, _settings(), verifier=fake_verify)
    assert out["count"] == 1
    assert out["leads"][0]["verification_status"] == "VERIFIED_NO_WEBSITE"

    assert verify_endpoint({"leads": []}, _settings())["leads"] == []
