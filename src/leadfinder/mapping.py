"""Map a Places API (New) Place proto to a Lead dataclass.

Kept separate from models.py so that models stays SDK-free, and separate from
places_client.py so the pure proto->Lead logic is easy to unit-test.
"""

from __future__ import annotations

from google.maps import places_v1

from .categories import category_for_types
from .models import PRICE_LEVEL_DISPLAY, Lead


def _has(msg: object, field: str) -> bool:
    """Presence check that tolerates fields for which `in` is not defined."""
    try:
        return field in msg  # type: ignore[operator]
    except (TypeError, ValueError):
        return False


def _opt_bool(msg: object, field: str) -> str:
    """'' when an optional bool is unset, else 'true'/'false'."""
    if _has(msg, field):
        return "true" if getattr(msg, field) else "false"
    return ""


def place_to_lead(
    place: places_v1.Place,
    *,
    city: str = "",
    keyword: str = "",
    scraped_date: str = "",
    scraped_time: str = "",
) -> Lead:
    """Convert a Place proto into a Lead. Missing fields become empty values."""
    types = list(place.types)

    price_name = places_v1.PriceLevel(place.price_level).name
    price_display = PRICE_LEVEL_DISPLAY.get(price_name, "")

    status_name = places_v1.Place.BusinessStatus(place.business_status).name
    business_status = "OPERATIONAL" if status_name == "BUSINESS_STATUS_UNSPECIFIED" else status_name

    hours = ""
    if _has(place, "regular_opening_hours"):
        hours = " | ".join(place.regular_opening_hours.weekday_descriptions)

    currently_open = "Unknown"
    if _has(place, "current_opening_hours") and _has(place.current_opening_hours, "open_now"):
        currently_open = "true" if place.current_opening_hours.open_now else "false"
    elif _has(place, "regular_opening_hours") and _has(place.regular_opening_hours, "open_now"):
        currently_open = "true" if place.regular_opening_hours.open_now else "false"

    plus_code = place.plus_code.global_code if _has(place, "plus_code") else ""
    latitude = place.location.latitude if _has(place, "location") else ""
    longitude = place.location.longitude if _has(place, "location") else ""

    wheelchair = ""
    if _has(place, "accessibility_options"):
        wheelchair = _opt_bool(place.accessibility_options, "wheelchair_accessible_entrance")

    return Lead(
        name=place.display_name.text,
        phone=place.national_phone_number,
        address=place.formatted_address,
        vicinity=place.short_formatted_address,
        rating=place.rating if place.rating else "",
        review_count=place.user_rating_count,
        price_level=price_display,
        business_status=business_status,
        currently_open=currently_open,
        hours=hours,
        types="|".join(types),
        category=category_for_types(types),
        city=city,
        search_keyword=keyword,
        place_id=place.id,
        plus_code=plus_code,
        latitude=latitude,
        longitude=longitude,
        website_uri=place.website_uri,
        serves_beer=_opt_bool(place, "serves_beer"),
        serves_wine=_opt_bool(place, "serves_wine"),
        takeout=_opt_bool(place, "takeout"),
        delivery=_opt_bool(place, "delivery"),
        dine_in=_opt_bool(place, "dine_in"),
        curbside_pickup=_opt_bool(place, "curbside_pickup"),
        reservable=_opt_bool(place, "reservable"),
        wheelchair_accessible=wheelchair,
        source="google",
        scraped_date=scraped_date,
        scraped_time=scraped_time,
    )
