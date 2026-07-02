import pytest

from leadfinder.config import Settings, _as_list, _as_profile
from leadfinder.models import FieldProfile


def test_as_list():
    assert _as_list("Austin TX, Denver CO") == ["Austin TX", "Denver CO"]
    assert _as_list(["A", "B"]) == ["A", "B"]
    assert _as_list(None) == []


def test_as_profile():
    assert _as_profile("enterprise") == FieldProfile.ENTERPRISE
    assert _as_profile(FieldProfile.PRO) == FieldProfile.PRO
    with pytest.raises(ValueError):
        _as_profile("bogus")


def test_validate_rejects_bad_max_results():
    with pytest.raises(ValueError):
        Settings(api_key="x" * 12, cities=["Austin TX"], max_results=50).validate()


def test_from_env_overrides_win(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza" + "x" * 30)
    monkeypatch.setenv("SEARCH_CITIES", "Austin TX, Denver CO")
    settings = Settings.from_env(max_results=10, field_profile="pro")
    assert settings.max_results == 10
    assert settings.field_profile == FieldProfile.PRO
    assert settings.cities == ["Austin TX", "Denver CO"]


def test_overture_needs_no_api_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("SEARCH_CITIES", "Covington LA")
    settings = Settings.from_env()  # default source=overture
    assert settings.source == "overture"
    assert settings.api_key == ""


def test_google_source_requires_api_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("SEARCH_CITIES", "Covington LA")
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        Settings.from_env(source="google")
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        Settings.from_env(source="both")


def test_bbox_parsing(monkeypatch):
    monkeypatch.setenv("SEARCH_CITIES", "Covington LA")
    settings = Settings.from_env(bbox="-90.17,30.43,-90.05,30.55")
    assert settings.bbox == (-90.17, 30.43, -90.05, 30.55)
    with pytest.raises(ValueError, match="bbox"):
        Settings.from_env(bbox="1,2,3")


def test_invalid_source_rejected(monkeypatch):
    monkeypatch.setenv("SEARCH_CITIES", "Covington LA")
    with pytest.raises(ValueError, match="source"):
        Settings.from_env(source="bing")


def test_radius_miles_parse(monkeypatch):
    monkeypatch.setenv("SEARCH_CITIES", "Covington LA")
    assert Settings.from_env().radius_miles is None
    assert Settings.from_env(radius_miles=15).radius_miles == 15.0
    with pytest.raises(ValueError, match="radius_miles"):
        Settings.from_env(radius_miles=500)
