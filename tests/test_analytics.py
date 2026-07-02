import json

import pandas as pd

from leadfinder.analytics import compute_stats, lead_records, render_dashboard
from leadfinder.models import lead_fieldnames


def _df(rows):
    cols = lead_fieldnames()
    filled = [{**{c: "" for c in cols}, **r} for r in rows]
    return pd.DataFrame(filled, columns=cols)


def test_coverage_counts_ignore_blanks():
    df = _df(
        [
            {"name": "A", "city": "Austin TX", "rating": 4.6, "phone": "555", "hours": "Mon"},
            {"name": "B", "city": "Austin TX", "rating": 4.1, "phone": "", "hours": ""},
            {"name": "C", "city": "Denver CO", "rating": "", "phone": "666", "hours": "Tue"},
        ]
    )
    stats = compute_stats(df)
    assert stats["total_businesses"] == 3
    assert stats["with_phone"] == 2
    assert stats["with_hours"] == 2
    assert stats["with_rating"] == 2
    assert stats["cities"] == 2


def test_score_formula_overture_and_google():
    df = _df(
        [
            {  # overture-style: full contact info + max confidence = 100
                "name": "Max Overture",
                "city": "Covington LA",
                "phone": "555",
                "email": "a@b.com",
                "socials": "https://facebook.com/x",
                "address": "1 Main St",
                "confidence": 1.0,
                "source": "overture",
            },
            {  # google-style: phone+address+top rating+many reviews+hours = 80
                "name": "Max Google",
                "city": "Covington LA",
                "phone": "555",
                "address": "2 Main St",
                "rating": 5.0,
                "review_count": 10000,
                "hours": "Mon-Fri",
                "source": "google",
            },
            {"name": "Nothing", "city": "Covington LA"},  # no signals = 0
        ]
    )
    records = lead_records(df)
    scores = {r["name"]: r["quality"] for r in records}
    assert scores["Max Overture"] == 100
    assert scores["Max Google"] == 80
    assert scores["Nothing"] == 0


def test_lead_records_shape():
    df = _df(
        [
            {
                "name": "Joe Diner",
                "city": "Austin TX",
                "category": "food_beverage",
                "rating": 4.6,
                "review_count": 120,
                "phone": "555",
                "place_id": "P1",
                "source": "google",
            },
            {"name": "No Rating", "city": "Denver CO", "rating": "", "review_count": 0},
        ]
    )
    records = lead_records(df)
    assert len(records) == 2
    assert records[0]["name"] == "Joe Diner"
    assert records[0]["rating"] == 4.6
    assert records[0]["place_id"] == "P1"
    assert records[0]["source"] == "google"
    assert isinstance(records[0]["quality"], int)
    assert records[1]["rating"] == ""  # missing rating stays blank, not NaN
    assert lead_records(_df([])) == []


def test_empty_dataset_renders_without_crashing():
    html = render_dashboard("empty.csv", [])
    assert "Leadfinder" in html
    payload = html.split("const LEADS = ", 1)[1].split(";\n", 1)[0]
    assert payload == "[]"
    assert "NaN" not in payload  # no pandas NaN leaks into the embedded data


def test_dashboard_is_a_checkable_worklist():
    df = _df(
        [
            {
                "name": "Cafe Delish",
                "city": "Covington LA",
                "phone": "555",
                "category": "food_beverage",
                "place_id": "X1",
                "source": "overture",
                "confidence": 0.9,
            }
        ]
    )
    html = render_dashboard("leads.csv", lead_records(df))
    # worklist features
    assert "leadfinder.checked.v1" in html  # check-off persistence
    assert 'id="f-hide"' in html  # hide-contacted toggle
    assert "Reset checks" in html
    assert 'id="progress-fill"' in html  # progress bar
    assert 'id="theme-toggle"' in html  # light/dark toggle
    # filters, export, embedded data
    assert 'id="f-q"' in html and 'id="f-city"' in html and 'id="f-cat"' in html
    assert "Export filtered CSV" in html
    assert '"contacted"' in html  # export includes contacted column
    payload = html.split("const LEADS = ", 1)[1].split(";\n", 1)[0]
    leads = json.loads(payload)
    assert leads[0]["name"] == "Cafe Delish"
    assert leads[0]["place_id"] == "X1"


def test_dashboard_output_is_ascii():
    df = _df(
        [
            {
                "name": "Cafe",
                "city": "Austin TX",
                "rating": 4.5,
                "phone": "555",
                "category": "food_beverage",
            }
        ]
    )
    html = render_dashboard("leads.csv", lead_records(df))
    assert html.isascii()
