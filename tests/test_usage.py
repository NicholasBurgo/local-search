import json

import pytest

from leadfinder.models import SkuTier
from leadfinder.usage import UsageTracker


def test_estimate_enterprise(tmp_path):
    tracker = UsageTracker(10_000, str(tmp_path / "u.json"))
    est = tracker.estimate(2250, SkuTier.ENTERPRISE)
    assert est.free_remaining == 1000
    assert est.billable == 1250
    assert est.est_usd == round(1250 / 1000 * 35.0, 2)


def test_record_and_persist(tmp_path):
    path = str(tmp_path / "u.json")
    tracker = UsageTracker(2000, path)
    for _ in range(5):
        tracker.record(SkuTier.ENTERPRISE)
    assert tracker.calls_for(SkuTier.ENTERPRISE) == 5
    reloaded = UsageTracker(2000, path)
    assert reloaded.total_calls() == 5


def test_stale_month_resets(tmp_path):
    path = str(tmp_path / "u.json")
    with open(path, "w") as f:
        json.dump({"month": "1999-01", "counts": {"enterprise": 42}}, f)
    tracker = UsageTracker(2000, path)
    assert tracker.total_calls() == 0


def test_budget_gate(tmp_path):
    tracker = UsageTracker(3, str(tmp_path / "u.json"))
    assert tracker.can_spend()
    for _ in range(3):
        tracker.record(SkuTier.ENTERPRISE)
    assert not tracker.can_spend()


def test_positive_budget_required():
    with pytest.raises(ValueError):
        UsageTracker(0, "unused.json")
