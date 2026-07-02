"""Small geographic helpers: miles <-> bounding box, centers, and distances.

A degree of latitude is ~69 miles everywhere; a degree of longitude shrinks by
cos(latitude). Good enough for radius filtering local businesses.
"""

from __future__ import annotations

import math

Bbox = tuple[float, float, float, float]  # (west, south, east, north)
Point = tuple[float, float]  # (lat, lon)

_MILES_PER_DEG_LAT = 69.0
EARTH_RADIUS_MILES = 3958.7613


def bbox_from_center(lat: float, lon: float, radius_miles: float) -> Bbox:
    """Square bounding box (west, south, east, north) around a center point."""
    dlat = radius_miles / _MILES_PER_DEG_LAT
    dlon = radius_miles / (_MILES_PER_DEG_LAT * max(math.cos(math.radians(lat)), 1e-6))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def bbox_center(bbox: Bbox) -> Point:
    """Center point (lat, lon) of a bounding box."""
    west, south, east, north = bbox
    return ((south + north) / 2.0, (west + east) / 2.0)


def haversine_miles(a: Point, b: Point) -> float:
    """Great-circle distance in miles between two (lat, lon) points."""
    lat1, lon1 = a
    lat2, lon2 = b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(min(1.0, math.sqrt(h)))
