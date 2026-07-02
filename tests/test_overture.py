import json

from leadfinder.config import Settings
from leadfinder.sources.overture import (
    OvertureSource,
    build_query,
    fetch_overture_bbox,
    row_to_lead,
)

BBOX = (-90.17, 30.43, -90.05, 30.55)


def _row(
    *,
    pid="08f4",
    name="Joe's Diner",
    cat="restaurant",
    alt=("american_restaurant",),
    phones=("(985) 555-0100",),
    emails=("joe@example.com",),
    socials=("https://facebook.com/joesdiner",),
    locality="Covington",
    confidence=0.9,
    status="open",
):
    addresses = [
        {"freeform": "123 Main St", "locality": locality, "region": "LA", "postcode": "70433"}
    ]
    return (
        pid,
        name,
        cat,
        json.dumps(list(alt)),
        json.dumps(list(phones)),
        json.dumps(list(emails)),
        json.dumps(list(socials)),
        json.dumps(addresses),
        confidence,
        status,
        -90.1,
        30.47,
    )


def test_build_query_contains_filters():
    sql = build_query("2026-06-17.0", BBOX)
    assert "release/2026-06-17.0/theme=places/type=place" in sql
    assert "websites IS NULL" in sql
    assert "brand IS NULL" in sql
    assert "bbox.xmin BETWEEN -90.17 AND -90.05" in sql
    assert "bbox.ymin BETWEEN 30.43 AND 30.55" in sql
    assert "names.primary IS NOT NULL" in sql


def test_row_to_lead_maps_fields():
    lead = row_to_lead(_row(), city="Covington LA", min_confidence=0.5, allowed_categories=None)
    assert lead is not None
    row = lead.to_row()
    assert row["name"] == "Joe's Diner"
    assert row["phone"] == "(985) 555-0100"
    assert row["email"] == "joe@example.com"
    assert row["socials"] == "https://facebook.com/joesdiner"
    assert row["address"] == "123 Main St, Covington, LA 70433"
    assert row["category"] == "food_beverage"
    assert row["source"] == "overture"
    assert row["confidence"] == 0.9
    assert row["website_uri"] == ""
    assert row["place_id"] == "08f4"


def test_filters_low_confidence_closed_and_wrong_locality():
    low = row_to_lead(
        _row(confidence=0.3), city="Covington LA", min_confidence=0.5, allowed_categories=None
    )
    closed = row_to_lead(
        _row(status="permanently_closed"),
        city="Covington LA",
        min_confidence=0.5,
        allowed_categories=None,
    )
    neighbor = row_to_lead(
        _row(locality="Abita Springs"),
        city="Covington LA",
        min_confidence=0.5,
        allowed_categories=None,
    )
    missing_locality = row_to_lead(
        _row(locality=""), city="Covington LA", min_confidence=0.5, allowed_categories=None
    )
    assert low is None
    assert closed is None
    assert neighbor is None
    assert missing_locality is not None  # rows without a locality are kept


def test_category_allowlist():
    kept = row_to_lead(
        _row(), city="Covington LA", min_confidence=0.5, allowed_categories=["food_beverage"]
    )
    dropped = row_to_lead(
        _row(), city="Covington LA", min_confidence=0.5, allowed_categories=["automotive"]
    )
    assert kept is not None
    assert dropped is None


def test_source_jobs_and_fetch(tmp_path):
    settings = Settings(cities=["Covington LA"], source="overture", output_dir=str(tmp_path))
    captured = {}

    def fake_runner(sql):
        captured["sql"] = sql
        return [_row(), _row(pid="08f5", name="Nowhere Cafe", confidence=0.2)]

    source = OvertureSource(settings, query_runner=fake_runner, bbox_resolver=lambda city: BBOX)
    jobs = source.jobs()
    assert len(jobs) == 1
    assert jobs[0].key.startswith("Covington LA|overture:2026-06-17.0:")

    leads = jobs[0].run()
    assert "websites IS NULL" in captured["sql"]
    assert len(leads) == 1  # low-confidence row filtered
    assert leads[0].name == "Joe's Diner"
    assert "overture" in (source.preflight() or "")


def test_fetch_overture_bbox_shared_helper():
    captured = {}

    def fake_runner(sql):
        captured["sql"] = sql
        return [_row()]

    leads = fetch_overture_bbox(
        BBOX,
        release="2026-06-17.0",
        min_confidence=0.5,
        allowed_categories=None,
        query_runner=fake_runner,
        city="Covington LA",
    )
    assert "bbox.xmin BETWEEN -90.17 AND -90.05" in captured["sql"]
    assert len(leads) == 1 and leads[0].source == "overture"


def test_different_radius_gives_different_job_key():
    base = dict(cities=["Covington LA"], source="overture", output_dir="/tmp")
    k10 = OvertureSource(Settings(**base, radius_miles=10)).jobs()[0].key
    k20 = OvertureSource(Settings(**base, radius_miles=20)).jobs()[0].key
    k_city = OvertureSource(Settings(**base)).jobs()[0].key
    assert k10 != k20 != k_city and k10 != k_city  # each re-queries, no stale checkpoint reuse


def test_radius_expands_bbox_around_center():
    settings = Settings(
        cities=["Covington LA"], source="overture", radius_miles=20, output_dir="/tmp"
    )
    source = OvertureSource(settings, query_runner=lambda sql: [], bbox_resolver=lambda city: BBOX)
    # BBOX center is ~(30.49, -90.11); a 20-mile radius must widen well past it
    west, south, east, north = source._resolve_bbox("Covington LA")
    assert east - west > (BBOX[2] - BBOX[0])  # wider than the city's own bbox
    assert north - south > (BBOX[3] - BBOX[1])
    assert north - south < 0.7  # 20 mi ~ 0.58 deg lat, sanity bound
