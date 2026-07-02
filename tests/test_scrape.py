import csv

from google.maps import places_v1 as p

from leadfinder.categories import keywords_for
from leadfinder.config import Settings
from leadfinder.field_mask import sku_for_profile
from leadfinder.logging_setup import setup_logging
from leadfinder.models import FieldProfile
from leadfinder.scrape import run_scrape
from leadfinder.sources.google import GoogleSource
from leadfinder.usage import UsageTracker

FAKE_KEY = "AIzaFAKEKEY_00000000000000000000000000"


def _display_name(text):
    return p.Place.meta.fields["display_name"].message(text=text)


class FakeGateway:
    """Returns one no-website candidate, one with-website, one closed per query."""

    def __init__(self):
        self.calls = 0

    def search_text(self, query, profile, max_results=20):
        self.calls += 1
        return [
            p.Place(
                id=f"N{self.calls}",
                display_name=_display_name(f"Cafe {self.calls}"),
                website_uri="",
                business_status=p.Place.BusinessStatus.OPERATIONAL,
                types=["cafe"],
            ),
            p.Place(
                id=f"H{self.calls}",
                display_name=_display_name("Chain"),
                website_uri="https://chain.example",
                business_status=p.Place.BusinessStatus.OPERATIONAL,
                types=["cafe"],
            ),
            p.Place(
                id=f"C{self.calls}",
                display_name=_display_name("Dead"),
                website_uri="",
                business_status=p.Place.BusinessStatus.CLOSED_PERMANENTLY,
                types=["cafe"],
            ),
        ]


def _settings(tmp_path, **kw):
    base = dict(
        cities=["Austin TX"],
        api_key=FAKE_KEY,
        source="google",
        field_profile=FieldProfile.ENTERPRISE,
        categories=["agriculture_pets"],
        output_dir=str(tmp_path),
        monthly_call_budget=1000,
    )
    base.update(kw)
    return Settings(**base)


def test_scrape_filters_and_resumes(tmp_path):
    setup_logging("CRITICAL")
    settings = _settings(tmp_path)
    n_keywords = len(keywords_for(["agriculture_pets"]))

    gateway = FakeGateway()
    usage = UsageTracker(1000, str(tmp_path / "u.json"))
    source = GoogleSource(settings, gateway=gateway, usage=usage)
    result = run_scrape(settings, source=source, usage=usage)

    assert gateway.calls == n_keywords  # one call per keyword (single city)
    assert 1 <= result["leads"] <= n_keywords

    main = next(f for f in result["files"] if "all_leads" in f)
    rows = list(csv.DictReader(open(main)))
    assert rows, "expected at least one lead row"
    assert all(r["website_uri"] == "" for r in rows)  # only no-website kept
    assert all(r["name"] not in ("Chain", "Dead") for r in rows)  # has-website + closed dropped
    assert all(r["source"] == "google" for r in rows)

    # Resume: checkpoint is complete, so a fresh gateway makes no calls.
    gateway2 = FakeGateway()
    source2 = GoogleSource(settings, gateway=gateway2)
    run_scrape(settings, source=source2, usage=UsageTracker(1000, str(tmp_path / "u2.json")))
    assert gateway2.calls == 0


def test_scrape_stops_at_budget(tmp_path):
    setup_logging("CRITICAL")
    settings = _settings(tmp_path, cities=["Austin TX", "Denver CO"], monthly_call_budget=3)

    class BudgetGateway:
        def __init__(self, usage):
            self.calls = 0
            self.usage = usage

        def search_text(self, query, profile, max_results=20):
            self.calls += 1
            self.usage.record(sku_for_profile(profile))
            return []

    usage = UsageTracker(3, str(tmp_path / "u.json"))
    gateway = BudgetGateway(usage)
    source = GoogleSource(settings, gateway=gateway, usage=usage)
    run_scrape(settings, source=source, usage=usage)
    assert gateway.calls == 3  # stopped once the budget was consumed


def test_failed_job_is_retried_on_resume(tmp_path):
    setup_logging("CRITICAL")
    settings = _settings(tmp_path)

    class FlakyGateway:
        """Fails every call in round one, succeeds in round two."""

        def __init__(self):
            self.calls = 0
            self.fail = True

        def search_text(self, query, profile, max_results=20):
            self.calls += 1
            if self.fail:
                raise RuntimeError("transient")
            return []

    gateway = FlakyGateway()
    usage = UsageTracker(1000, str(tmp_path / "u.json"))
    n_keywords = len(keywords_for(["agriculture_pets"]))

    run_scrape(settings, source=GoogleSource(settings, gateway=gateway), usage=usage)
    assert gateway.calls == n_keywords  # all attempted, all failed, none checkpointed

    gateway.fail = False
    run_scrape(settings, source=GoogleSource(settings, gateway=gateway), usage=usage)
    assert gateway.calls == 2 * n_keywords  # failed jobs were retried, not skipped
