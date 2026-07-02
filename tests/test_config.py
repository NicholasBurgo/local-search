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
