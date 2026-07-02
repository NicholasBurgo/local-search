from leadfinder.config import Settings
from leadfinder.models import Lead
from leadfinder.server import geocode_endpoint, search_endpoint, verify_endpoint

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


def test_verify_endpoint():
    rows = [{"name": "Joe", "city": "Covington LA", "quality": 80}]

    def fake_verify(r):
        return [{**r[0], "verification_status": "VERIFIED_NO_WEBSITE"}]

    out = verify_endpoint({"leads": rows}, _settings(), verifier=fake_verify)
    assert out["count"] == 1
    assert out["leads"][0]["verification_status"] == "VERIFIED_NO_WEBSITE"

    assert verify_endpoint({"leads": []}, _settings())["leads"] == []
