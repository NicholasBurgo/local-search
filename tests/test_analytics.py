import pandas as pd

from leadfinder.analytics import compute_stats, render_dashboard
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


def test_empty_dataset_renders_without_crashing():
    stats = compute_stats(_df([]))
    assert stats["total_businesses"] == 0
    html = render_dashboard(stats, "empty.csv")  # would ZeroDivisionError in the old code
    assert "Total leads" in html
    assert "nan" not in html.lower()


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
    html = render_dashboard(compute_stats(df), "leads.csv")
    assert html.isascii()
