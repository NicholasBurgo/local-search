"""Scrape pipeline: search each city x keyword and keep businesses with no website.

Text Search (New) returns websiteUri directly, so this is a single-stage pipeline
(no per-place Place Details call): one search per city x keyword, filter to
operational businesses with an empty websiteUri, de-duplicate, and write CSVs.
"""

from __future__ import annotations

import itertools
import os
import time
from datetime import datetime

from google.maps import places_v1

from .categories import BUSINESS_CATEGORIES, keywords_for
from .config import Settings
from .field_mask import sku_for_profile
from .logging_setup import get_logger
from .mapping import place_to_lead
from .places_client import PlacesGateway
from .storage import (
    checkpoint_path_for,
    dedupe_rows,
    load_checkpoint,
    save_checkpoint,
    slug_city,
    write_rows_csv,
)
from .usage import UsageTracker

_CLOSED = places_v1.Place.BusinessStatus.CLOSED_PERMANENTLY


def _is_no_website_candidate(place: places_v1.Place) -> bool:
    if place.website_uri:
        return False
    if place.business_status == _CLOSED:
        return False
    return True


def run_scrape(
    settings: Settings,
    gateway: PlacesGateway | None = None,
    usage: UsageTracker | None = None,
) -> dict:
    """Run the scrape and write CSVs. Returns a summary dict.

    gateway/usage are injectable for testing; by default they are built from settings.
    """
    logger = get_logger()
    os.makedirs(settings.output_dir, exist_ok=True)

    if usage is None:
        usage = UsageTracker(
            settings.monthly_call_budget,
            os.path.join(settings.output_dir, "usage_state.json"),
        )
    if gateway is None:
        gateway = PlacesGateway(settings.api_key, usage=usage)

    keywords = keywords_for(settings.categories)
    cities = settings.cities
    profile = settings.field_profile
    sku = sku_for_profile(profile)
    total = len(cities) * len(keywords)

    # Pre-flight cost estimate.
    est = usage.estimate(total, sku)
    logger.info(
        "Pre-flight: up to %d Text Search calls at %s SKU. Free-tier remaining %d; "
        "estimated billable %d (~$%.2f).",
        est.calls,
        sku.value,
        est.free_remaining,
        est.billable,
        est.est_usd,
    )
    if total > settings.monthly_call_budget:
        logger.warning(
            "Planned calls (%d) exceed monthly_call_budget (%d); the run will stop at the budget. "
            "Narrow --categories or raise the budget.",
            total,
            settings.monthly_call_budget,
        )

    # Resume from checkpoint if present.
    ckpt = checkpoint_path_for(settings.output_dir, cities, keywords)
    state = load_checkpoint(ckpt)
    processed: set[str] = set(state.get("processed", []))
    rows: list[dict] = list(state.get("rows", []))
    done = len(processed)
    if done:
        logger.info("Resuming from checkpoint: %d/%d combinations done", done, total)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for city, keyword in itertools.product(cities, keywords):
        key = f"{city}|{keyword}"
        if key in processed:
            continue
        if not usage.can_spend():
            logger.warning(
                "Monthly call budget of %d reached. Stopping early.", settings.monthly_call_budget
            )
            break

        done += 1
        logger.info("[%d/%d] search '%s' in %s", done, total, keyword, city)
        try:
            places = gateway.search_text(f"{keyword} in {city}", profile, settings.max_results)
        except Exception as exc:
            logger.error("Search failed for '%s' in %s: %s", keyword, city, exc)
            processed.add(key)
            continue

        now_d = datetime.now().strftime("%Y-%m-%d")
        now_t = datetime.now().strftime("%H:%M:%S")
        kept = 0
        for place in places:
            if not _is_no_website_candidate(place):
                continue
            lead = place_to_lead(
                place, city=city, keyword=keyword, scraped_date=now_d, scraped_time=now_t
            )
            rows.append(lead.to_row())
            kept += 1
        logger.info("  kept %d no-website leads of %d results", kept, len(places))

        processed.add(key)
        save_checkpoint(
            {"processed": sorted(processed), "rows": rows, "timestamp": datetime.now().isoformat()},
            ckpt,
        )
        if settings.request_delay:
            time.sleep(settings.request_delay)

    return _write_outputs(rows, cities, settings.output_dir, stamp, usage, logger)


def _write_outputs(rows, cities, output_dir, stamp, usage, logger) -> dict:
    if not rows:
        logger.warning("No leads found. Check the API key, quota/budget, and city spelling.")
        logger.info("Usage: %s", usage.summary())
        return {"leads": 0, "files": []}

    deduped, removed = dedupe_rows(rows)
    files: list[str] = []

    main_file = os.path.join(output_dir, f"all_leads_no_website_{stamp}.csv")
    write_rows_csv(deduped, main_file)
    files.append(main_file)
    logger.info(
        "Saved %d unique leads (removed %d duplicates) -> %s", len(deduped), removed, main_file
    )

    for city in cities:
        city_rows = [r for r in deduped if r.get("city") == city]
        if city_rows:
            path = os.path.join(output_dir, f"leads_{slug_city(city)}_{stamp}.csv")
            write_rows_csv(city_rows, path)
            files.append(path)
            logger.info("  %s: %d leads", city, len(city_rows))

    for category in BUSINESS_CATEGORIES:
        cat_rows = [r for r in deduped if r.get("category") == category]
        if cat_rows:
            path = os.path.join(output_dir, f"leads_{category}_{stamp}.csv")
            write_rows_csv(cat_rows, path)
            files.append(path)

    logger.info("Usage this month: %s", usage.summary())
    logger.info("Done. %d leads across %d files in %s/", len(deduped), len(files), output_dir)
    return {"leads": len(deduped), "files": files}


def main(**overrides) -> dict:
    """Entry point: build Settings from env/.env and run the scrape."""
    settings = Settings.from_env(**overrides)
    get_logger().info(
        "Scraping %d cities x %d keywords",
        len(settings.cities),
        len(keywords_for(settings.categories)),
    )
    return run_scrape(settings)
