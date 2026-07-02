"""Pluggable lead sources: google (Places API New), overture (open data), both."""

from __future__ import annotations

from ..config import Settings
from ..usage import UsageTracker
from .base import Job, LeadSource, MultiSource

SOURCE_CHOICES = ("overture", "google", "both")


def build_source(settings: Settings, usage: UsageTracker | None = None) -> LeadSource:
    """Construct the configured source. Google is imported lazily (SDK weight)."""
    if settings.source == "overture":
        from .overture import OvertureSource

        return OvertureSource(settings)
    if settings.source == "google":
        from .google import GoogleSource

        return GoogleSource(settings, usage=usage)
    if settings.source == "both":
        from .google import GoogleSource
        from .overture import OvertureSource

        # Google first: on cross-source duplicates, dedupe keeps the richer record.
        return MultiSource([GoogleSource(settings, usage=usage), OvertureSource(settings)])
    raise ValueError(f"Unknown source '{settings.source}'. Choose one of: {SOURCE_CHOICES}")


__all__ = ["SOURCE_CHOICES", "Job", "LeadSource", "MultiSource", "build_source"]
