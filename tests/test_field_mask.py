from leadfinder.field_mask import build_field_mask, fields_for_profile, sku_for_profile
from leadfinder.models import FieldProfile, SkuTier


def test_fields_are_cumulative():
    essentials = set(fields_for_profile(FieldProfile.ESSENTIALS))
    enterprise = set(fields_for_profile(FieldProfile.ENTERPRISE))
    assert essentials.issubset(enterprise)
    assert "websiteUri" in enterprise
    assert "websiteUri" not in essentials


def test_atmosphere_is_superset_of_enterprise():
    enterprise = set(fields_for_profile(FieldProfile.ENTERPRISE))
    atmosphere = set(fields_for_profile(FieldProfile.ATMOSPHERE))
    assert enterprise.issubset(atmosphere)
    assert "servesBeer" in atmosphere
    assert "servesBeer" not in enterprise


def test_prefix_differs_for_search_vs_details():
    search = build_field_mask(FieldProfile.ENTERPRISE, prefix="places.")
    details = build_field_mask(FieldProfile.ENTERPRISE, prefix="")
    assert all(part.startswith("places.") for part in search.split(","))
    assert not any(part.startswith("places.") for part in details.split(","))
    assert "places.websiteUri" in search
    assert "websiteUri" in details.split(",")


def test_sku_mapping():
    assert sku_for_profile(FieldProfile.ESSENTIALS) == SkuTier.ESSENTIALS
    assert sku_for_profile(FieldProfile.PRO) == SkuTier.PRO
    assert sku_for_profile(FieldProfile.ENTERPRISE) == SkuTier.ENTERPRISE
    assert sku_for_profile(FieldProfile.ATMOSPHERE) == SkuTier.ENTERPRISE_ATMOSPHERE
