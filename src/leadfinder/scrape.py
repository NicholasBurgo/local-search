"""Scrape pipeline: run the configured source's jobs and collect no-website leads.

Source-agnostic: a source (google, overture, or both) yields checkpointable jobs;
this loop resumes from the checkpoint, enforces the monthly budget (relevant only
to billable sources), de-duplicates, and writes the CSV outputs.
"""

from __future__ import annotations

import os
import time
from datetime import datetime

from .categories import BUSINESS_CATEGORIES
from .config import Settings
from .logging_setup import get_logger
from .sources import build_source
from .sources.base import LeadSource
from .storage import (
    checkpoint_path_for,
    dedupe_rows,
    load_checkpoint,
    save_checkpoint,
    slug_city,
    write_rows_csv,
)
from .usage import UsageTracker


def run_scrape(
    settings: Settings,
    source: LeadSource | None = None,
    usage: UsageTracker | None = None,
) -> dict:
    """Run the scrape and write CSVs. Returns a summary dict.

    source/usage are injectable for testing; by default they are built from settings.
    """
    logger = get_logger()
    os.makedirs(settings.output_dir, exist_ok=True)

    if usage is None:
        usage = UsageTracker(
            settings.monthly_call_budget,
            os.path.join(settings.output_dir, "usage_state.json"),
        )
    if source is None:
        source = build_source(settings, usage)

    jobs = source.jobs()
    preflight = source.preflight()
    if preflight:
        logger.info("Pre-flight: %s", preflight)

    # Checkpoint identity = the exact set of job keys (source/config-sensitive).
    ckpt = checkpoint_path_for(
        settings.output_dir, settings.cities, sorted(job.key for job in jobs)
    )
    state = load_checkpoint(ckpt)
    processed: set[str] = set(state.get("processed", []))
    rows: list[dict] = list(state.get("rows", []))
    total = len(jobs)
    done = len(processed)
    if done:
        logger.info("Resuming from checkpoint: %d/%d jobs done", done, total)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for job in jobs:
        if job.key in processed:
            continue
        if not usage.can_spend():
            logger.warning(
                "Monthly call budget of %d reached. Stopping early.",
                settings.monthly_call_budget,
            )
            break

        done += 1
        logger.info("[%d/%d] %s", done, total, job.key)
        try:
            leads = job.run()
        except Exception as exc:
            logger.error("Job '%s' failed: %s (will retry on resume)", job.key, exc)
            done -= 1
            continue

        if leads:
            rows.extend(lead.to_row() for lead in leads)
            logger.info("  kept %d no-website leads", len(leads))

        processed.add(job.key)
        save_checkpoint(
            {"processed": sorted(processed), "rows": rows, "timestamp": datetime.now().isoformat()},
            ckpt,
        )
        if settings.request_delay:
            time.sleep(settings.request_delay)

    return _write_outputs(rows, settings.cities, settings.output_dir, stamp, usage, logger)


def _write_outputs(rows, cities, output_dir, stamp, usage, logger) -> dict:
    if not rows:
        logger.warning("No leads found. Check city spelling, source availability, and filters.")
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
    get_logger().info("Scraping %d cities via source '%s'", len(settings.cities), settings.source)
    return run_scrape(settings)
