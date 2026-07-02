"""Runtime configuration, loaded from environment / .env with optional overrides.

Reading configuration never writes it back: unlike the old CLI, nothing here
mutates the .env file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

from .models import FieldProfile


def _as_list(raw: str | list[str] | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [part.strip() for part in raw.split(",") if part.strip()]


def _as_profile(raw: str | FieldProfile) -> FieldProfile:
    if isinstance(raw, FieldProfile):
        return raw
    try:
        return FieldProfile(str(raw).strip().lower())
    except ValueError as exc:
        valid = ", ".join(p.value for p in FieldProfile)
        raise ValueError(f"Invalid field profile '{raw}'. Choose one of: {valid}") from exc


def _pick(overrides: dict[str, Any], key: str, env_key: str, default: Any) -> Any:
    """Override (if not None) > environment variable > default."""
    if overrides.get(key) is not None:
        return overrides[key]
    env_val = os.getenv(env_key)
    return env_val if env_val is not None else default


SOURCE_CHOICES = ("overture", "google", "both")


def _as_bbox(raw) -> tuple[float, float, float, float] | None:
    """Parse 'W,S,E,N' (or a 4-item sequence) into a bbox tuple."""
    if raw is None or raw == "":
        return None
    parts = raw.split(",") if isinstance(raw, str) else list(raw)
    if len(parts) != 4:
        raise ValueError("bbox must be 'west,south,east,north' (4 numbers)")
    west, south, east, north = (float(p) for p in parts)
    return (west, south, east, north)


@dataclass
class Settings:
    """All tunable settings for a scrape/verify/dashboard run."""

    cities: list[str]
    api_key: str = ""  # required only when source is google/both
    source: str = "overture"  # overture (free, no key) | google | both
    field_profile: FieldProfile = FieldProfile.ENTERPRISE
    categories: list[str] | None = None  # subset of BUSINESS_CATEGORIES keys; None = all
    max_results: int = 20  # per query; Text Search (New) caps at 20
    output_dir: str = "leads_output"
    monthly_call_budget: int = 5000  # soft ceiling on billable calls per month
    request_delay: float = 0.0  # optional politeness delay between API calls
    overture_release: str = "2026-06-17.0"  # pinned Overture data release
    min_confidence: float = 0.5  # drop Overture places below this existence confidence
    bbox: tuple[float, float, float, float] | None = None  # manual override, skips geocoding
    probe_concurrency: int = 10
    probe_timeout: float = 5.0
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, **overrides: Any) -> Settings:
        """Build Settings from .env / environment, with keyword overrides winning."""
        load_dotenv()

        cities = _as_list(_pick(overrides, "cities", "SEARCH_CITIES", None))
        if not cities:
            raise ValueError("SEARCH_CITIES not set. Add e.g. SEARCH_CITIES=Austin TX, Portland OR")

        categories_raw = _pick(overrides, "categories", "SEARCH_CATEGORIES", None)
        categories = _as_list(categories_raw) or None

        settings = cls(
            cities=cities,
            api_key=str(_pick(overrides, "api_key", "GOOGLE_API_KEY", "") or ""),
            source=str(_pick(overrides, "source", "SOURCE", "overture")).strip().lower(),
            field_profile=_as_profile(
                _pick(overrides, "field_profile", "FIELD_PROFILE", "enterprise")
            ),
            categories=categories,
            max_results=int(_pick(overrides, "max_results", "MAX_RESULTS", 20)),
            output_dir=str(_pick(overrides, "output_dir", "OUTPUT_DIR", "leads_output")),
            monthly_call_budget=int(
                _pick(overrides, "monthly_call_budget", "MONTHLY_CALL_BUDGET", 5000)
            ),
            request_delay=float(_pick(overrides, "request_delay", "REQUEST_DELAY", 0.0)),
            overture_release=str(
                _pick(overrides, "overture_release", "OVERTURE_RELEASE", "2026-06-17.0")
            ),
            min_confidence=float(_pick(overrides, "min_confidence", "MIN_CONFIDENCE", 0.5)),
            bbox=_as_bbox(_pick(overrides, "bbox", "SEARCH_BBOX", None)),
            probe_concurrency=int(_pick(overrides, "probe_concurrency", "PROBE_CONCURRENCY", 10)),
            probe_timeout=float(_pick(overrides, "probe_timeout", "PROBE_TIMEOUT", 5.0)),
            log_level=str(_pick(overrides, "log_level", "LOG_LEVEL", "INFO")),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.source not in SOURCE_CHOICES:
            raise ValueError(f"Invalid source '{self.source}'. Choose one of: {SOURCE_CHOICES}")
        if self.source in ("google", "both") and (not self.api_key or len(self.api_key) < 10):
            raise ValueError(
                f"GOOGLE_API_KEY is required for source '{self.source}'. "
                "Use SOURCE=overture for the free, keyless path."
            )
        if not self.cities:
            raise ValueError("No cities specified")
        if not 1 <= self.max_results <= 20:
            raise ValueError("max_results must be between 1 and 20 (Text Search caps at 20)")
        if self.monthly_call_budget <= 0:
            raise ValueError("monthly_call_budget must be positive")
        if not 0 <= self.min_confidence <= 1:
            raise ValueError("min_confidence must be between 0 and 1")
        if self.probe_concurrency < 1:
            raise ValueError("probe_concurrency must be at least 1")
        if self.probe_timeout <= 0:
            raise ValueError("probe_timeout must be positive")
