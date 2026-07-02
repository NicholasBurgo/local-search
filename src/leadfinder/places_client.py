"""Thin wrapper over the Places API (New) client (`google-maps-places`).

Isolates the SDK behind one class so an upgrade touches only this module. The
installed SDK's Text Search does not paginate, so search_text is a single call
capped by max_result_count (<= 20); coverage comes from the keyword x city
fan-out, not pagination.
"""

from __future__ import annotations

import random
import time

from google.api_core.exceptions import (
    Aborted,
    DeadlineExceeded,
    InternalServerError,
    ResourceExhausted,
    ServiceUnavailable,
    TooManyRequests,
)
from google.maps import places_v1

from .field_mask import build_field_mask, sku_for_profile
from .logging_setup import get_logger
from .models import FieldProfile
from .usage import UsageTracker

# Transient errors worth retrying; client errors (PermissionDenied,
# InvalidArgument, NotFound) propagate immediately since a retry cannot help.
_RETRYABLE = (
    ServiceUnavailable,
    DeadlineExceeded,
    InternalServerError,
    ResourceExhausted,
    TooManyRequests,
    Aborted,
)


class PlacesGateway:
    """Text Search and Place Details over Places API (New), with retry + usage."""

    def __init__(
        self,
        api_key: str,
        usage: UsageTracker | None = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ):
        self.client = places_v1.PlacesClient(client_options={"api_key": api_key})
        self.usage = usage
        self.max_retries = max_retries
        self.base_delay = base_delay
        self._log = get_logger()

    def _retry(self, func, what: str):
        for attempt in range(self.max_retries):
            try:
                return func()
            except _RETRYABLE as exc:
                if attempt == self.max_retries - 1:
                    self._log.error("%s failed after %d attempts: %s", what, self.max_retries, exc)
                    raise
                delay = self.base_delay * (2**attempt) + random.uniform(0, 0.5)
                self._log.warning(
                    "%s attempt %d failed (%s); retrying in %.2fs",
                    what,
                    attempt + 1,
                    exc,
                    delay,
                )
                time.sleep(delay)

    def search_text(
        self, query: str, profile: FieldProfile, max_results: int = 20
    ) -> list[places_v1.Place]:
        """Run one Text Search and return its places (up to max_results)."""
        mask = build_field_mask(profile, prefix="places.")
        request = places_v1.SearchTextRequest(text_query=query, max_result_count=max_results)

        response = self._retry(
            lambda: self.client.search_text(request=request, metadata=[("x-goog-fieldmask", mask)]),
            f"search_text({query!r})",
        )
        if self.usage is not None:
            self.usage.record(sku_for_profile(profile), 1)
        return list(response.places)

    def get_place(self, place_id: str, profile: FieldProfile) -> places_v1.Place:
        """Fetch one place's details (Place Details New). Optional enrichment path."""
        mask = build_field_mask(profile, prefix="")
        request = places_v1.GetPlaceRequest(name=f"places/{place_id}")

        place = self._retry(
            lambda: self.client.get_place(request=request, metadata=[("x-goog-fieldmask", mask)]),
            f"get_place({place_id})",
        )
        if self.usage is not None:
            self.usage.record(sku_for_profile(profile), 1)
        return place
