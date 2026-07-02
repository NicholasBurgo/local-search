import math

from leadfinder.geo import bbox_center, bbox_from_center, haversine_miles


def test_bbox_from_center_lat_delta():
    # 69 miles north/south ~ 1 degree latitude
    _west, south, _east, north = bbox_from_center(30.0, -90.0, 69.0)
    assert math.isclose(north - 30.0, 1.0, abs_tol=0.02)
    assert math.isclose(30.0 - south, 1.0, abs_tol=0.02)


def test_bbox_from_center_lon_scales_with_latitude():
    # a degree of longitude is narrower away from the equator, so the same
    # mileage spans MORE longitude degrees at higher latitude
    _, _, east_low, _ = bbox_from_center(0.0, 0.0, 69.0)
    _, _, east_high, _ = bbox_from_center(60.0, 0.0, 69.0)
    assert east_high > east_low
    assert math.isclose(east_high, 2.0, abs_tol=0.05)  # cos(60)=0.5 -> ~2 deg


def test_bbox_center_roundtrip():
    bbox = bbox_from_center(30.44, -90.1, 10.0)
    lat, lon = bbox_center(bbox)
    assert math.isclose(lat, 30.44, abs_tol=1e-6)
    assert math.isclose(lon, -90.1, abs_tol=1e-6)


def test_haversine_known_distance():
    # ~1 degree of latitude is ~69 miles
    assert math.isclose(haversine_miles((30.0, -90.0), (31.0, -90.0)), 69.0, abs_tol=0.5)
    assert haversine_miles((30.44, -90.1), (30.44, -90.1)) == 0.0


def test_haversine_covington_pair():
    # two real Covington leads ~ under a mile apart
    d = haversine_miles((30.4830, -90.0918), (30.4771, -90.0949))
    assert 0.2 < d < 1.0
