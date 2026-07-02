"""Persistent lead store (DuckDB): leads survive reloads/restarts, so we don't
re-pull Overture and triage/contacted marks are remembered.

The web server is threaded and a DuckDB connection is not thread-safe, so every
operation is serialized with a lock on one persistent connection. This is a
separate connection from the in-memory httpfs one used for Overture queries.
"""

from __future__ import annotations

import os
import threading

import duckdb

# Source columns (from analytics.lead_records) that a fresh search may refresh.
_SOURCE_COLS = [
    "name",
    "city",
    "category",
    "rating",
    "review_count",
    "phone",
    "email",
    "socials",
    "address",
    "hours",
    "price_level",
    "website_uri",
    "source",
    "confidence",
    "latitude",
    "longitude",
    "quality",
]
# Full insert column order (marks preserved on conflict, not overwritten).
_INSERT_COLS = [
    "place_id",
    *_SOURCE_COLS,
    "verification_status",
    "verified_date",
    "decision",
    "contacted",
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
  place_id VARCHAR PRIMARY KEY,
  name VARCHAR, city VARCHAR, category VARCHAR,
  rating DOUBLE, review_count INTEGER,
  phone VARCHAR, email VARCHAR, socials VARCHAR, address VARCHAR,
  hours VARCHAR, price_level VARCHAR, website_uri VARCHAR,
  source VARCHAR, confidence DOUBLE, latitude DOUBLE, longitude DOUBLE,
  quality INTEGER,
  verification_status VARCHAR, verified_date VARCHAR,
  decision VARCHAR, contacted BOOLEAN DEFAULT false,
  first_seen TIMESTAMP, last_updated TIMESTAMP
)
"""

_UPSERT_SQL = (
    "INSERT INTO leads ("
    + ", ".join(_INSERT_COLS)
    + ", first_seen, last_updated) VALUES ("
    + ", ".join(["?"] * len(_INSERT_COLS))
    + ", now(), now()) "
    + "ON CONFLICT (place_id) DO UPDATE SET "
    + ", ".join(f"{c}=excluded.{c}" for c in _SOURCE_COLS)
    + ", last_updated=now()"
)

_FILTERS = {
    "undecided": "decision IS NULL",
    "keep": "decision = 'keep'",
    "reject": "decision = 'reject'",
    "contacted": "contacted = true",
}

_UNSET = object()


def _num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _int(v):
    n = _num(v)
    return int(n) if n is not None else None


def _row_params(rec: dict) -> list:
    g = rec.get
    return [
        g("place_id") or "",
        g("name") or "",
        g("city") or "",
        g("category") or "",
        _num(g("rating")),
        _int(g("review_count")),
        g("phone") or "",
        g("email") or "",
        g("socials") or "",
        g("address") or "",
        g("hours") or "",
        g("price_level") or "",
        g("website_uri") or "",
        g("source") or "",
        _num(g("confidence")),
        _num(g("latitude")),
        _num(g("longitude")),
        _int(g("quality")),
        g("verification_status") or None,
        g("verified_date") or None,
        g("decision") or None,
        bool(g("contacted") or False),
    ]


class LeadStore:
    def __init__(self, db_path: str):
        directory = os.path.dirname(db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self.db_path = db_path
        self._lock = threading.Lock()
        self._con = duckdb.connect(db_path)
        self._con.execute(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._con.close()

    def _records(self, cursor) -> list[dict]:
        cols = [d[0] for d in cursor.description]
        out = []
        for row in cursor.fetchall():
            rec = {}
            for k, v in zip(cols, row, strict=True):
                rec[k] = v.isoformat() if hasattr(v, "isoformat") else v
            out.append(rec)
        return out

    def upsert(self, records: list[dict]) -> int:
        rows = [_row_params(r) for r in records if r.get("place_id")]
        if not rows:
            return 0
        with self._lock:
            self._con.executemany(_UPSERT_SQL, rows)
        return len(rows)

    def get(self, place_ids: list[str]) -> dict[str, dict]:
        ids = [p for p in place_ids if p]
        if not ids:
            return {}
        placeholders = ", ".join(["?"] * len(ids))
        with self._lock:
            cur = self._con.execute(f"SELECT * FROM leads WHERE place_id IN ({placeholders})", ids)
            recs = self._records(cur)
        return {r["place_id"]: r for r in recs}

    def saved(self, filter: str | None = None) -> list[dict]:
        where = _FILTERS.get(filter or "", "1=1")
        with self._lock:
            cur = self._con.execute(
                f"SELECT * FROM leads WHERE {where} ORDER BY quality DESC NULLS LAST, name"
            )
            return self._records(cur)

    def mark(self, place_id: str, decision=_UNSET, contacted=_UNSET) -> None:
        sets, params = [], []
        if decision is not _UNSET:
            sets.append("decision = ?")
            params.append(decision or None)
        if contacted is not _UNSET:
            sets.append("contacted = ?")
            params.append(bool(contacted))
        if not sets:
            return
        sets.append("last_updated = now()")
        params.append(place_id)
        with self._lock:
            self._con.execute(f"UPDATE leads SET {', '.join(sets)} WHERE place_id = ?", params)

    def update_verification(self, rows: list[dict]) -> int:
        n = 0
        with self._lock:
            for r in rows:
                pid = r.get("place_id")
                if not pid:
                    continue
                self._con.execute(
                    "UPDATE leads SET verification_status = ?, verified_date = ?, "
                    "last_updated = now() WHERE place_id = ?",
                    [r.get("verification_status"), r.get("verified_date"), pid],
                )
                n += 1
        return n

    def stats(self) -> dict:
        with self._lock:
            total = self._con.execute("SELECT count(*) FROM leads").fetchone()[0]
            keep = self._con.execute("SELECT count(*) FROM leads WHERE decision='keep'").fetchone()[
                0
            ]
            reject = self._con.execute(
                "SELECT count(*) FROM leads WHERE decision='reject'"
            ).fetchone()[0]
            contacted = self._con.execute(
                "SELECT count(*) FROM leads WHERE contacted=true"
            ).fetchone()[0]
        return {
            "total": total,
            "keep": keep,
            "reject": reject,
            "undecided": total - keep - reject,
            "contacted": contacted,
        }
