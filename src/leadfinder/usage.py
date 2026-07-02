"""Monthly, per-SKU API usage tracking and pre-flight cost estimation.

Replaces the old daily 25,000-request model. Google now bills per SKU with
per-SKU monthly free-tier caps (the universal $200 credit ended March 2025), so
this counts calls per SKU within the current calendar month and enforces a soft
monthly call budget.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime

from .logging_setup import get_logger
from .models import FREE_TIER_CALLS_PER_MONTH, TEXT_SEARCH_USD_PER_1000, SkuTier


def _current_month() -> str:
    return datetime.now().strftime("%Y-%m")


@dataclass
class CostEstimate:
    calls: int
    sku: SkuTier
    free_remaining: int
    billable: int
    est_usd: float


class UsageTracker:
    """Tracks billable calls per SKU for the current month, persisted to JSON."""

    def __init__(self, monthly_budget: int, state_file: str = "usage_state.json"):
        if monthly_budget <= 0:
            raise ValueError("monthly_budget must be positive")
        self.monthly_budget = monthly_budget
        self.state_file = state_file
        self.month = _current_month()
        self.counts: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.state_file):
            return
        try:
            with open(self.state_file) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return
        # Reset counters on a new month.
        if data.get("month") == self.month:
            self.counts = {k: int(v) for k, v in data.get("counts", {}).items()}

    def _save(self) -> None:
        data = {"month": self.month, "counts": self.counts}
        tmp = f"{self.state_file}.tmp"
        try:
            directory = os.path.dirname(self.state_file)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(tmp, "w") as f:
                json.dump(data, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.state_file)
        except OSError as e:
            get_logger().error("Failed to save usage state: %s", e)
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass

    def total_calls(self) -> int:
        return sum(self.counts.values())

    def calls_for(self, sku: SkuTier) -> int:
        return self.counts.get(sku.value, 0)

    def record(self, sku: SkuTier, n: int = 1) -> None:
        """Record n billable calls against a SKU (rolls over if the month changed)."""
        now = _current_month()
        if now != self.month:
            self.month = now
            self.counts = {}
        self.counts[sku.value] = self.counts.get(sku.value, 0) + n
        self._save()

    def can_spend(self) -> bool:
        """True while total calls this month are under the soft budget."""
        return self.total_calls() < self.monthly_budget

    def free_remaining(self, sku: SkuTier) -> int:
        cap = FREE_TIER_CALLS_PER_MONTH.get(sku, 0)
        return max(0, cap - self.calls_for(sku))

    def estimate(self, expected_calls: int, sku: SkuTier) -> CostEstimate:
        """Pre-flight cost estimate for expected_calls additional calls at a SKU."""
        free_before = self.free_remaining(sku)
        billable = max(0, expected_calls - free_before)
        est_usd = billable / 1000.0 * TEXT_SEARCH_USD_PER_1000.get(sku, 0.0)
        return CostEstimate(
            calls=expected_calls,
            sku=sku,
            free_remaining=free_before,
            billable=billable,
            est_usd=round(est_usd, 2),
        )

    def summary(self) -> dict:
        return {
            "month": self.month,
            "total_calls": self.total_calls(),
            "by_sku": dict(self.counts),
            "monthly_budget": self.monthly_budget,
        }
