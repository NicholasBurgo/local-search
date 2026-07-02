"""Data-source protocol: a source yields checkpointable jobs that produce Leads.

scrape.py drives any source the same way: iterate jobs, skip keys already in the
checkpoint, run the rest, checkpoint after each. Sources own how leads are
fetched (Google keyword searches, one Overture bbox query per city, ...).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ..models import Lead


@dataclass
class Job:
    """One checkpointable unit of work. key must be stable across runs."""

    key: str
    run: Callable[[], list[Lead]]


class LeadSource(Protocol):
    name: str

    def jobs(self) -> list[Job]:
        """All jobs for this run (keys stable so resume works)."""
        ...

    def preflight(self) -> str | None:
        """Optional human-readable cost/scope message logged before the run."""
        ...


class MultiSource:
    """Concatenates sources; earlier sources win on dedupe (dedupe keeps first)."""

    def __init__(self, sources: list[LeadSource]):
        self.sources = sources
        self.name = "+".join(s.name for s in sources)

    def jobs(self) -> list[Job]:
        out: list[Job] = []
        for source in self.sources:
            out.extend(source.jobs())
        return out

    def preflight(self) -> str | None:
        messages = [m for m in (s.preflight() for s in self.sources) if m]
        return " | ".join(messages) if messages else None
