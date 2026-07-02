"""Persistent lead store (DuckDB): leads survive reloads/restarts, so we don't
re-pull Overture and triage/contacted marks are remembered.

The web server is threaded and a DuckDB connection is not thread-safe, so every
operation is serialized with a lock on one persistent connection. This is a
separate connection from the in-memory httpfs one used for Overture queries.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta

import duckdb

from .models import normalize_phone

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
    "stage",
]

# Sales-pipeline stages a lead moves through. None = not on the list; "new" is
# where a lead lands when added from the map; "won"/"lost" are the closed states.
STAGES = ("new", "contacted", "qualified", "proposal_sent", "negotiating", "won", "lost")
# Open deals still worth working (the follow-up queue only nags about these).
ACTIVE_STAGES = ("new", "contacted", "qualified", "proposal_sent", "negotiating")
ACTIVITY_TYPES = ("call", "email", "note", "meeting")

# Remap the earlier triage stages onto the pipeline so existing rows stay valid.
_STAGE_MIGRATION = {
    "possible": "new",
    "accepted": "qualified",
    "declined": "lost",
    "completed": "won",
    "not_possible": "lost",
}

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
  decision VARCHAR, contacted BOOLEAN DEFAULT false, stage VARCHAR,
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

# "listed" = everything on the board; one exact-match filter per pipeline stage.
_FILTERS = {"listed": "stage IS NOT NULL"}
_FILTERS.update({stage: f"stage = '{stage}'" for stage in STAGES})

# Activity timeline (calls/emails/notes/meetings) + a per-lead follow-up reminder.
_ACTIVITY_SCHEMA = (
    "CREATE SEQUENCE IF NOT EXISTS activity_id_seq START 1",
    "CREATE TABLE IF NOT EXISTS activities ("
    "  id BIGINT PRIMARY KEY, place_id VARCHAR, type VARCHAR, body VARCHAR, created_at TIMESTAMP"
    ")",
)
# Newest last activity per lead, for the "gone stale" query and the queue display.
_LAST_ACTIVITY = (
    "LEFT JOIN (SELECT place_id, max(created_at) AS last_activity "
    "FROM activities GROUP BY place_id) la ON la.place_id = l.place_id"
)

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
        g("stage") or None,
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
        # Additive migration so a DB created before the pipeline model upgrades.
        self._con.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS stage VARCHAR")
        # Remap any legacy triage stages onto the current pipeline (idempotent).
        for old, new in _STAGE_MIGRATION.items():
            self._con.execute("UPDATE leads SET stage = ? WHERE stage = ?", [new, old])
        # Follow-up reminder per lead + the activity timeline table.
        self._con.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS next_follow_up TIMESTAMP")
        for stmt in _ACTIVITY_SCHEMA:
            self._con.execute(stmt)

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
            if "phone" in rec:
                rec["phone"] = normalize_phone(rec["phone"])
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

    def mark(self, place_id: str, decision=_UNSET, contacted=_UNSET, stage=_UNSET) -> None:
        sets, params = [], []
        if decision is not _UNSET:
            sets.append("decision = ?")
            params.append(decision or None)
        if contacted is not _UNSET:
            sets.append("contacted = ?")
            params.append(bool(contacted))
        if stage is not _UNSET:
            sets.append("stage = ?")
            params.append(stage or None)
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
            rows = self._con.execute(
                "SELECT stage, count(*) FROM leads WHERE stage IS NOT NULL GROUP BY stage"
            ).fetchall()
        counts = {stage: n for stage, n in rows}
        out = {"total": total, "listed": sum(counts.values())}
        for stage in STAGES:
            out[stage] = counts.get(stage, 0)
        return out

    # ---- activities + follow-ups ----

    def log_activity(self, place_id: str, kind: str, body: str) -> dict:
        """Append a call/email/note/meeting to a lead's timeline; return the row."""
        now = datetime.now()
        with self._lock:
            self._con.execute(
                "INSERT INTO activities (id, place_id, type, body, created_at) "
                "VALUES (nextval('activity_id_seq'), ?, ?, ?, ?)",
                [place_id, kind, body or "", now],
            )
            cur = self._con.execute(
                "SELECT * FROM activities WHERE place_id = ? ORDER BY id DESC LIMIT 1", [place_id]
            )
            return self._records(cur)[0]

    def activities_for(self, place_id: str) -> list[dict]:
        with self._lock:
            cur = self._con.execute(
                "SELECT * FROM activities WHERE place_id = ? ORDER BY created_at DESC, id DESC",
                [place_id],
            )
            return self._records(cur)

    def set_follow_up(self, place_id: str, days=None) -> str | None:
        """Set the next-follow-up to now + `days` (int), or clear it when days is None."""
        when = None if days is None else datetime.now() + timedelta(days=int(days))
        with self._lock:
            self._con.execute(
                "UPDATE leads SET next_follow_up = ?, last_updated = now() WHERE place_id = ?",
                [when, place_id],
            )
        return when.isoformat() if when else None

    def follow_up_queue(self, stale_days: int = 3) -> dict:
        """The 'today' view: follow-ups due/overdue, and active deals gone quiet."""
        now = datetime.now()
        cutoff = now - timedelta(days=stale_days)
        active = ", ".join(f"'{s}'" for s in ACTIVE_STAGES)
        base = (
            f"SELECT l.*, la.last_activity FROM leads l {_LAST_ACTIVITY} "
            f"WHERE l.stage IN ({active})"
        )
        with self._lock:
            due = self._records(
                self._con.execute(
                    f"{base} AND l.next_follow_up IS NOT NULL AND l.next_follow_up <= ? "
                    "ORDER BY l.next_follow_up",
                    [now],
                )
            )
            stale = self._records(
                self._con.execute(
                    f"{base} AND l.next_follow_up IS NULL "
                    "AND coalesce(la.last_activity, l.first_seen) <= ? "
                    "ORDER BY coalesce(la.last_activity, l.first_seen)",
                    [cutoff],
                )
            )
        return {"due": due, "stale": stale, "stale_days": stale_days}
