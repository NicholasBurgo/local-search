"""Verify 'no website' leads by probing their likely domains (async, httpx).

Replaces the old Playwright/Google-SERP verifier. Reads a leads CSV, probes each
business, and writes verified / removed / full-results CSVs.
"""

from __future__ import annotations

import asyncio
import csv
import glob
import os
from datetime import datetime

import httpx

from .config import Settings
from .logging_setup import get_logger
from .models import VerificationStatus, lead_fieldnames
from .probe import USER_AGENT, probe_business
from .storage import timestamp, write_rows_csv

# Columns the verify stage adds on top of the Lead schema.
VERIFY_COLUMNS = [
    "probed_domain",
    "probe_final_url",
    "probe_http_status",
    "probe_result",
    "verification_status",
    "verified_date",
]


async def verify_rows(
    rows: list[dict],
    settings: Settings,
    client: httpx.AsyncClient | None = None,
) -> list[dict]:
    """Probe every row concurrently (bounded) and return rows + verification columns."""
    semaphore = asyncio.Semaphore(settings.probe_concurrency)
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=settings.probe_timeout,
            headers={"User-Agent": USER_AGENT},
        )
    try:

        async def _one(row: dict) -> dict:
            outcome = await probe_business(
                client, row.get("name", ""), semaphore, settings.probe_timeout
            )
            merged = dict(row)
            merged.update(outcome)
            merged["verified_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return merged

        return await asyncio.gather(*(_one(row) for row in rows))
    finally:
        if own_client:
            await client.aclose()


def summarize(results: list[dict]) -> dict:
    stats = {status.value: 0 for status in VerificationStatus}
    for row in results:
        status = row.get("verification_status", VerificationStatus.ERROR.value)
        stats[status] = stats.get(status, 0) + 1
    stats["total"] = len(results)
    return stats


def save_results(results: list[dict], output_dir: str) -> dict:
    """Write verified / removed / full CSVs. Returns paths + stats."""
    verified_dir = os.path.join(output_dir, "verified")
    os.makedirs(verified_dir, exist_ok=True)
    stamp = timestamp()
    full_cols = lead_fieldnames() + VERIFY_COLUMNS

    verified = [
        r
        for r in results
        if r.get("verification_status") == VerificationStatus.VERIFIED_NO_WEBSITE.value
    ]
    removed = [
        r
        for r in results
        if r.get("verification_status") != VerificationStatus.VERIFIED_NO_WEBSITE.value
    ]

    paths: dict[str, str] = {}
    if verified:
        # Clean file: Lead columns only (extrasaction='ignore' drops probe columns).
        path = os.path.join(verified_dir, f"verified_no_website_{stamp}.csv")
        write_rows_csv(verified, path, fieldnames=lead_fieldnames())
        paths["verified"] = path
    if removed:
        path = os.path.join(verified_dir, f"removed_businesses_{stamp}.csv")
        write_rows_csv(removed, path, fieldnames=full_cols)
        paths["removed"] = path
    full_path = os.path.join(verified_dir, f"full_verification_results_{stamp}.csv")
    write_rows_csv(results, full_path, fieldnames=full_cols)
    paths["full"] = full_path
    return {"paths": paths, "stats": summarize(results)}


def _read_rows(csv_path: str) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def latest_leads_file(output_dir: str) -> str | None:
    files = glob.glob(os.path.join(output_dir, "all_leads_no_website_*.csv"))
    return max(files) if files else None


def verify_file(csv_path: str, settings: Settings) -> dict:
    """Verify a single leads CSV end-to-end and write results."""
    logger = get_logger()
    rows = _read_rows(csv_path)
    if not rows:
        logger.warning("No rows in %s; nothing to verify.", csv_path)
        return {"paths": {}, "stats": {"total": 0}}
    logger.info("Verifying %d leads from %s", len(rows), csv_path)
    results = asyncio.run(verify_rows(rows, settings))
    outcome = save_results(results, settings.output_dir)
    stats = outcome["stats"]
    total = max(1, stats.get("total", 0))
    logger.info(
        "Verification done. verified_no_website=%d has_website=%d chain=%d error=%d (%.1f%% kept)",
        stats.get(VerificationStatus.VERIFIED_NO_WEBSITE.value, 0),
        stats.get(VerificationStatus.REMOVED_HAS_WEBSITE.value, 0),
        stats.get(VerificationStatus.REMOVED_CHAIN.value, 0),
        stats.get(VerificationStatus.ERROR.value, 0),
        stats.get(VerificationStatus.VERIFIED_NO_WEBSITE.value, 0) / total * 100,
    )
    return outcome


def main(**overrides) -> dict:
    """Entry point: verify the most recent leads CSV in the output directory."""
    settings = Settings.from_env(**overrides)
    logger = get_logger()
    latest = latest_leads_file(settings.output_dir)
    if not latest:
        logger.error("No leads file found in %s. Run the scraper first.", settings.output_dir)
        return {"paths": {}, "stats": {"total": 0}}
    return verify_file(latest, settings)
