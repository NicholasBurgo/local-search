"""Places API (New) field masks and their billing SKU tiers.

Billing rule: the highest-tier field present in the mask sets the SKU for the
whole call. See
https://developers.google.com/maps/documentation/places/web-service/choose-fields

websiteUri -- the signal this tool is built on -- is an Enterprise field, so the
default profile is ENTERPRISE and no field trimming makes the core function
cheaper. Field names use the API (camelCase) form.
"""

from __future__ import annotations

from .models import PROFILE_SKU, FieldProfile, SkuTier

TIER_FIELDS: dict[FieldProfile, list[str]] = {
    FieldProfile.ESSENTIALS: [
        "id",
        "formattedAddress",
        "shortFormattedAddress",
        "plusCode",
        "types",
        "location",
    ],
    FieldProfile.PRO: [
        "displayName",
        "businessStatus",
        "accessibilityOptions",
    ],
    FieldProfile.ENTERPRISE: [
        "websiteUri",
        "nationalPhoneNumber",
        "rating",
        "userRatingCount",
        "priceLevel",
        "regularOpeningHours",
        "currentOpeningHours",
    ],
    FieldProfile.ATMOSPHERE: [
        "servesBeer",
        "servesWine",
        "takeout",
        "delivery",
        "dineIn",
        "curbsidePickup",
        "reservable",
    ],
}

# Cumulative order: a profile includes every tier up to and including itself.
_PROFILE_ORDER = [
    FieldProfile.ESSENTIALS,
    FieldProfile.PRO,
    FieldProfile.ENTERPRISE,
    FieldProfile.ATMOSPHERE,
]


def fields_for_profile(profile: FieldProfile) -> list[str]:
    """All field names to request for a given profile (cumulative across tiers)."""
    out: list[str] = []
    for tier in _PROFILE_ORDER:
        out.extend(TIER_FIELDS[tier])
        if tier == profile:
            break
    return out


def build_field_mask(profile: FieldProfile, prefix: str = "places.") -> str:
    """Comma-joined field mask string.

    Text Search (New) requires prefix='places.'; Place Details (New) requires prefix=''.
    """
    return ",".join(f"{prefix}{name}" for name in fields_for_profile(profile))


def sku_for_profile(profile: FieldProfile) -> SkuTier:
    """The billing SKU tier a profile's field mask resolves to."""
    return PROFILE_SKU[profile]
