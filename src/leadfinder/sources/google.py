"""Google Places API (New) lead source: one Text Search per city x keyword."""

from __future__ import annotations

from datetime import datetime
from functools import partial
from itertools import product

from google.maps import places_v1

from ..categories import keywords_for
from ..config import Settings
from ..field_mask import sku_for_profile
from ..mapping import place_to_lead
from ..models import Lead
from ..places_client import PlacesGateway
from ..usage import UsageTracker
from .base import Job

_CLOSED = places_v1.Place.BusinessStatus.CLOSED_PERMANENTLY


def _is_no_website_candidate(place: places_v1.Place) -> bool:
    if place.website_uri:
        return False
    if place.business_status == _CLOSED:
        return False
    return True


class GoogleSource:
    name = "google"

    def __init__(
        self,
        settings: Settings,
        gateway: PlacesGateway | None = None,
        usage: UsageTracker | None = None,
    ):
        self.settings = settings
        self.usage = usage
        self.gateway = gateway or PlacesGateway(settings.api_key, usage=usage)
        self.keywords = keywords_for(settings.categories)

    def preflight(self) -> str | None:
        total = len(self.settings.cities) * len(self.keywords)
        sku = sku_for_profile(self.settings.field_profile)
        if self.usage is None:
            return f"google: up to {total} Text Search calls at {sku.value} SKU"
        est = self.usage.estimate(total, sku)
        message = (
            f"google: up to {est.calls} Text Search calls at {sku.value} SKU; "
            f"free-tier remaining {est.free_remaining}, est. billable {est.billable} "
            f"(~${est.est_usd:.2f})"
        )
        if total > self.settings.monthly_call_budget:
            message += (
                f" [WARNING: exceeds monthly_call_budget={self.settings.monthly_call_budget};"
                " run will stop at the budget]"
            )
        return message

    def jobs(self) -> list[Job]:
        return [
            Job(key=f"{city}|{keyword}", run=partial(self._fetch, city, keyword))
            for city, keyword in product(self.settings.cities, self.keywords)
        ]

    def _fetch(self, city: str, keyword: str) -> list[Lead]:
        places = self.gateway.search_text(
            f"{keyword} in {city}", self.settings.field_profile, self.settings.max_results
        )
        now_d = datetime.now().strftime("%Y-%m-%d")
        now_t = datetime.now().strftime("%H:%M:%S")
        return [
            place_to_lead(place, city=city, keyword=keyword, scraped_date=now_d, scraped_time=now_t)
            for place in places
            if _is_no_website_candidate(place)
        ]
