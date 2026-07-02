"""Persistence: atomic checkpoints, lead de-duplication, and CSV output."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import datetime

from .logging_setup import get_logger
from .models import lead_fieldnames
from .names import fuzzy_match, name_slug


def save_checkpoint(data: dict, path: str) -> bool:
    """Atomically write a checkpoint dict to path. Returns success."""
    logger = get_logger()
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = f"{path}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        return True
    except (OSError, TypeError, ValueError) as exc:
        logger.error("Failed to save checkpoint '%s': %s", path, exc)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False


def load_checkpoint(path: str) -> dict:
    """Load a checkpoint dict, or an empty default if absent/corrupt."""
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"processed": [], "rows": []}
    return {"processed": [], "rows": []}


def checkpoint_path_for(output_dir: str, cities: list[str], keywords: list[str]) -> str:
    """Stable checkpoint filename for a (cities, keywords) configuration."""
    config_str = "|".join(sorted(cities)) + "||" + "|".join(sorted(keywords))
    digest = hashlib.md5(config_str.encode()).hexdigest()[:8]
    return os.path.join(output_dir, f"checkpoint_{digest}.json")


def dedupe_rows(rows: list[dict], fuzzy_threshold: float = 0.9) -> tuple[list[dict], int]:
    """De-duplicate lead rows.

    First on place_id (exact), then on a fuzzy name match *within the same city*
    so two different businesses with similar names in different cities are kept.
    Returns (unique_rows, num_removed).
    """
    seen_ids: set[str] = set()
    id_unique: list[dict] = []
    for row in rows:
        pid = row.get("place_id")
        if pid:
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
        id_unique.append(row)

    names_by_city: dict[str, list[str]] = {}
    result: list[dict] = []
    for row in id_unique:
        city = row.get("city", "")
        slug = name_slug(row.get("name", ""))
        seen_here = names_by_city.setdefault(city, [])
        if slug and any(fuzzy_match(slug, other, fuzzy_threshold) for other in seen_here):
            continue
        if slug:
            seen_here.append(slug)
        result.append(row)

    return result, len(rows) - len(result)


def write_rows_csv(rows: list[dict], path: str, fieldnames: list[str] | None = None) -> int:
    """Write rows to a CSV. fieldnames defaults to the Lead schema order."""
    if not rows:
        return 0
    if fieldnames is None:
        fieldnames = lead_fieldnames()
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def slug_city(city: str) -> str:
    """Filesystem-safe token for a city name, e.g. 'Austin, TX' -> 'Austin_TX'."""
    return city.replace(", ", "_").replace(" ", "_")


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")
