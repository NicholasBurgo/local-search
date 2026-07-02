"""Core data model: leads, enums, and SKU/pricing tables.

This module deliberately has no SDK imports so it stays cheap to import for
tests of field masks, usage tracking, and CSV handling.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, fields
from enum import Enum

_NON_DIGIT = re.compile(r"\D")


def normalize_phone(raw) -> str:
    """Format a US phone as "(XXX) XXX-XXXX".

    Handles the assorted shapes sources return (e.g. "+19858457455",
    "19858457455", "9858457455", "985-845-7455"). A leading US country code is
    dropped. Anything that is not a 10-digit US number is returned trimmed but
    otherwise untouched, so odd/foreign values are never mangled or lost.
    """
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    digits = _NON_DIGIT.sub("", s)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return s


class FieldProfile(str, Enum):
    """Which set of Place fields to request. Higher profile = richer data + higher SKU."""

    ESSENTIALS = "essentials"
    PRO = "pro"
    ENTERPRISE = "enterprise"  # default: includes websiteUri, the core "no website" signal
    ATMOSPHERE = "atmosphere"  # + service attributes (serves_beer, takeout, ...)


class SkuTier(str, Enum):
    """Billing SKU tier for a Places API Text Search call."""

    ESSENTIALS = "essentials"
    PRO = "pro"
    ENTERPRISE = "enterprise"
    ENTERPRISE_ATMOSPHERE = "enterprise_atmosphere"


# Text Search (New) price per 1000 calls at the 0-100k monthly tier, in USD.
# Approximate 2026 figures, used only for pre-flight cost estimates.
TEXT_SEARCH_USD_PER_1000: dict[SkuTier, float] = {
    SkuTier.ESSENTIALS: 5.0,
    SkuTier.PRO: 32.0,
    SkuTier.ENTERPRISE: 35.0,
    SkuTier.ENTERPRISE_ATMOSPHERE: 40.0,
}

# Per-SKU monthly free-tier call caps. Google retired the universal $200 credit
# in March 2025 in favour of these per-SKU allotments.
FREE_TIER_CALLS_PER_MONTH: dict[SkuTier, int] = {
    SkuTier.ESSENTIALS: 10_000,
    SkuTier.PRO: 5_000,
    SkuTier.ENTERPRISE: 1_000,
    SkuTier.ENTERPRISE_ATMOSPHERE: 1_000,
}

# The SKU a field profile bills at (highest-tier field in the mask wins).
PROFILE_SKU: dict[FieldProfile, SkuTier] = {
    FieldProfile.ESSENTIALS: SkuTier.ESSENTIALS,
    FieldProfile.PRO: SkuTier.PRO,
    FieldProfile.ENTERPRISE: SkuTier.ENTERPRISE,
    FieldProfile.ATMOSPHERE: SkuTier.ENTERPRISE_ATMOSPHERE,
}

# Google PriceLevel enum name -> display string. Keyed by the proto enum name so
# this module stays independent of the SDK import.
PRICE_LEVEL_DISPLAY: dict[str, str] = {
    "PRICE_LEVEL_UNSPECIFIED": "",
    "PRICE_LEVEL_FREE": "Free",
    "PRICE_LEVEL_INEXPENSIVE": "$",
    "PRICE_LEVEL_MODERATE": "$$",
    "PRICE_LEVEL_EXPENSIVE": "$$$",
    "PRICE_LEVEL_VERY_EXPENSIVE": "$$$$",
}


class VerificationStatus(str, Enum):
    VERIFIED_NO_WEBSITE = "VERIFIED_NO_WEBSITE"
    REMOVED_HAS_WEBSITE = "REMOVED_HAS_WEBSITE"
    REMOVED_CHAIN = "REMOVED_CHAIN"
    ERROR = "ERROR"


class ProbeResult(str, Enum):
    LIVE_MATCH = "LIVE_MATCH"  # reachable and the domain matches the business name
    LIVE_UNRELATED = "LIVE_UNRELATED"  # reachable but unrelated / social / directory
    PARKED = "PARKED"  # reachable but a parked / placeholder page
    NO_RESPONSE = "NO_RESPONSE"  # nothing answered
    NOT_PROBED = "NOT_PROBED"


@dataclass
class Lead:
    """A single business lead. Field declaration order = CSV column order."""

    name: str = ""
    phone: str = ""
    address: str = ""
    vicinity: str = ""
    rating: float | str = ""
    review_count: int = 0
    price_level: str = ""
    business_status: str = "OPERATIONAL"
    currently_open: str = "Unknown"
    hours: str = ""
    types: str = ""
    category: str = "other"
    city: str = ""
    search_keyword: str = ""
    place_id: str = ""
    plus_code: str = ""
    latitude: float | str = ""
    longitude: float | str = ""
    website_uri: str = ""  # empty => candidate "no website" lead
    serves_beer: str = ""
    serves_wine: str = ""
    takeout: str = ""
    delivery: str = ""
    dine_in: str = ""
    curbside_pickup: str = ""
    reservable: str = ""
    wheelchair_accessible: str = ""
    email: str = ""
    socials: str = ""  # pipe-joined URLs
    source: str = ""  # which data source produced this lead (google | overture)
    confidence: float | str = ""  # Overture existence-confidence score, 0-1
    scraped_date: str = ""
    scraped_time: str = ""

    def to_row(self) -> dict:
        return asdict(self)


def lead_fieldnames() -> list[str]:
    """CSV column names, in declaration order."""
    return [f.name for f in fields(Lead)]
