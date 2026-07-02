"""Overture Maps lead source: one DuckDB bbox query per city over open data.

Free and keyless: reads the public Overture GeoParquet release on S3 with
anonymous access. Chains are dropped at query time (brand IS NULL) and only
places with no website on file are fetched (websites IS NULL) -- the HTTP probe
in the verify stage remains the arbiter of whether a site truly exists.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime
from functools import partial

from ..categories import category_for_types
from ..config import Settings
from ..geo import Bbox, bbox_center, bbox_from_center
from ..geocode import city_bbox
from ..logging_setup import get_logger
from ..models import Lead
from .base import Job

S3_PATH_TEMPLATE = "s3://overturemaps-us-west-2/release/{release}/theme=places/type=place/*"

# SELECT column order; _row_to_lead depends on it.
_COLUMNS = (
    "id",
    "name",
    "category_primary",
    "category_alternate",
    "phones",
    "emails",
    "socials",
    "addresses",
    "confidence",
    "operating_status",
    "lon",
    "lat",
)


def build_query(release: str, bbox: Bbox) -> str:
    """DuckDB SQL for no-website, non-chain places inside a bbox."""
    west, south, east, north = bbox
    path = S3_PATH_TEMPLATE.format(release=release)
    return f"""
SELECT
  id,
  names.primary AS name,
  categories.primary AS category_primary,
  CAST(categories.alternate AS JSON) AS category_alternate,
  CAST(phones AS JSON) AS phones,
  CAST(emails AS JSON) AS emails,
  CAST(socials AS JSON) AS socials,
  CAST(addresses AS JSON) AS addresses,
  confidence,
  operating_status,
  bbox.xmin AS lon,
  bbox.ymin AS lat
FROM read_parquet('{path}', filename=true, hive_partitioning=1)
WHERE bbox.xmin BETWEEN {west} AND {east}
  AND bbox.ymin BETWEEN {south} AND {north}
  AND websites IS NULL
  AND brand IS NULL
  AND names.primary IS NOT NULL
""".strip()


def duckdb_query_runner(sql: str) -> list[tuple]:
    """Run SQL against the public Overture S3 bucket via DuckDB (anonymous)."""
    import duckdb  # heavy import; keep lazy

    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("SET s3_region='us-west-2';")
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def fetch_overture_bbox(
    bbox: Bbox,
    release: str,
    min_confidence: float,
    allowed_categories: list[str] | None,
    query_runner: Callable[[str], list[tuple]] | None = None,
    city: str = "",
) -> list[Lead]:
    """Query Overture for a bbox and map rows to Leads. Shared by the source,
    the radius-scrape path, and the web server's search endpoint."""
    logger = get_logger()
    runner = query_runner or duckdb_query_runner
    rows = runner(build_query(release, bbox))
    logger.info("Overture returned %d candidate rows for bbox %s", len(rows), bbox)

    now_d = datetime.now().strftime("%Y-%m-%d")
    now_t = datetime.now().strftime("%H:%M:%S")
    leads: list[Lead] = []
    for row in rows:
        lead = row_to_lead(
            row,
            city=city,
            min_confidence=min_confidence,
            allowed_categories=allowed_categories,
            scraped_date=now_d,
            scraped_time=now_t,
        )
        if lead is not None:
            leads.append(lead)
    logger.info("Kept %d leads after filters", len(leads))
    return leads


def _jlist(value) -> list:
    """Parse a DuckDB JSON-cast column defensively into a Python list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _format_address(addresses: list) -> tuple[str, str]:
    """(full_address, vicinity) from the first Overture address struct."""
    if not addresses or not isinstance(addresses[0], dict):
        return "", ""
    first = addresses[0]
    freeform = (first.get("freeform") or "").strip()
    locality = (first.get("locality") or "").strip()
    region = (first.get("region") or "").strip()
    postcode = (first.get("postcode") or "").strip()
    parts = [p for p in (freeform, locality, f"{region} {postcode}".strip()) if p]
    return ", ".join(parts), freeform


def row_to_lead(
    row: tuple,
    city: str,
    min_confidence: float,
    allowed_categories: list[str] | None,
    scraped_date: str = "",
    scraped_time: str = "",
    strict_locality: bool = True,
) -> Lead | None:
    """Map one query row to a Lead; None when filtered out."""
    record = dict(zip(_COLUMNS, row, strict=True))

    status = str(record.get("operating_status") or "").lower()
    if "closed" in status:
        return None

    confidence = record.get("confidence")
    if confidence is not None and float(confidence) < min_confidence:
        return None

    addresses = _jlist(record.get("addresses"))
    address, vicinity = _format_address(addresses)

    # A rectangular bbox catches neighboring towns; keep rows whose stated
    # locality matches the requested city (rows without a locality are kept).
    if strict_locality and addresses and isinstance(addresses[0], dict):
        locality = (addresses[0].get("locality") or "").strip().lower()
        town = city.rsplit(" ", 1)[0].strip().lower()  # "Covington LA" -> "covington"
        if locality and town and town not in locality:
            return None

    cat_primary = record.get("category_primary") or ""
    cat_alternate = [c for c in _jlist(record.get("category_alternate")) if isinstance(c, str)]
    types = [c for c in [cat_primary, *cat_alternate] if c]
    category = category_for_types(types) if types else "other"
    if allowed_categories and category not in allowed_categories:
        return None

    phones = [p for p in _jlist(record.get("phones")) if isinstance(p, str)]
    emails = [e for e in _jlist(record.get("emails")) if isinstance(e, str)]
    socials = [s for s in _jlist(record.get("socials")) if isinstance(s, str)]

    return Lead(
        name=record.get("name") or "",
        phone=phones[0] if phones else "",
        address=address,
        vicinity=vicinity,
        types="|".join(types),
        category=category,
        city=city,
        search_keyword=f"overture:{cat_primary or 'place'}",
        place_id=record.get("id") or "",
        latitude=record.get("lat") if record.get("lat") is not None else "",
        longitude=record.get("lon") if record.get("lon") is not None else "",
        website_uri="",
        email=emails[0] if emails else "",
        socials="|".join(socials),
        source="overture",
        confidence=round(float(confidence), 2) if confidence is not None else "",
        scraped_date=scraped_date,
        scraped_time=scraped_time,
    )


class OvertureSource:
    name = "overture"

    def __init__(
        self,
        settings: Settings,
        query_runner: Callable[[str], list[tuple]] | None = None,
        bbox_resolver: Callable[[str], Bbox] | None = None,
    ):
        self.settings = settings
        self.query_runner = query_runner or duckdb_query_runner
        cache_path = os.path.join(settings.output_dir, ".geocode_cache.json")
        self.bbox_resolver = bbox_resolver or partial(city_bbox, cache_path=cache_path)

    def preflight(self) -> str | None:
        return (
            f"overture: 1 open-data query per city ({len(self.settings.cities)} total), "
            f"release {self.settings.overture_release}, cost $0 (no key, no billing)"
        )

    def _param_tag(self) -> str:
        """Short hash of the params that change the result, so a checkpoint from a
        different radius / confidence / bbox / categories does not get reused."""
        import hashlib

        raw = "|".join(
            str(x)
            for x in (
                self.settings.radius_miles,
                self.settings.min_confidence,
                self.settings.categories,
                self.settings.bbox,
            )
        )
        return hashlib.md5(raw.encode()).hexdigest()[:6]

    def jobs(self) -> list[Job]:
        release = self.settings.overture_release
        tag = self._param_tag()
        return [
            Job(key=f"{city}|overture:{release}:{tag}", run=partial(self._fetch, city))
            for city in self.settings.cities
        ]

    def _resolve_bbox(self, city: str) -> Bbox:
        if self.settings.bbox is not None:
            return self.settings.bbox
        geo_bbox = self.bbox_resolver(city)
        if self.settings.radius_miles:
            lat, lon = bbox_center(geo_bbox)
            return bbox_from_center(lat, lon, self.settings.radius_miles)
        return geo_bbox

    def _fetch(self, city: str) -> list[Lead]:
        bbox = self._resolve_bbox(city)
        get_logger().info("Overture bbox for %s: %s", city, bbox)
        return fetch_overture_bbox(
            bbox,
            release=self.settings.overture_release,
            min_confidence=self.settings.min_confidence,
            allowed_categories=self.settings.categories,
            query_runner=self.query_runner,
            city=city,
        )
