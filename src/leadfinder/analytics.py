"""Static HTML analytics dashboard for a leads CSV.

A streamlined, self-contained (no external assets), ASCII-only rewrite of the
original dashboard. Percentages are computed in Python and all divisions are
zero-guarded, so an empty dataset renders cleanly instead of crashing.
"""

from __future__ import annotations

import glob
import html
import os
from datetime import datetime

import numpy as np
import pandas as pd

from .logging_setup import get_logger


def _pct(n: float, d: float) -> float:
    return (n / d * 100.0) if d else 0.0


def load_leads(csv_path: str) -> pd.DataFrame:
    return pd.read_csv(csv_path)


def compute_stats(df: pd.DataFrame) -> dict:
    """Summary statistics for a leads DataFrame (robust to missing columns)."""
    total = len(df)
    rating = (
        pd.to_numeric(df["rating"], errors="coerce") if "rating" in df else pd.Series(dtype=float)
    )
    stats: dict = {
        "total_businesses": total,
        "cities": int(df["city"].nunique()) if "city" in df else 0,
        "categories": int(df["category"].nunique()) if "category" in df else 0,
        "with_phone": int(df["phone"].fillna("").astype(str).str.strip().ne("").sum())
        if "phone" in df
        else 0,
        "with_rating": int(rating.notna().sum()),
        "with_hours": int(df["hours"].fillna("").astype(str).str.strip().ne("").sum())
        if "hours" in df
        else 0,
    }
    stats["city_breakdown"] = df["city"].value_counts().to_dict() if "city" in df else {}
    stats["category_breakdown"] = (
        df["category"].value_counts().to_dict() if "category" in df else {}
    )

    valid_rating = rating.dropna()
    if not valid_rating.empty:
        stats["rating_stats"] = {
            "average": float(valid_rating.mean()),
            "median": float(valid_rating.median()),
            "min": float(valid_rating.min()),
            "max": float(valid_rating.max()),
        }
        stats["rating_distribution"] = {
            f"{k:.1f}": int(v) for k, v in valid_rating.round(0).value_counts().sort_index().items()
        }

    # Quality score: rating (<=40) + log-scaled reviews (<=30) + hours (20) + phone (10).
    scores: list[float] = []
    for _, row in df.iterrows():
        score = 0.0
        r = pd.to_numeric(pd.Series([row.get("rating")]), errors="coerce").iloc[0]
        if pd.notna(r) and r > 0:
            score += min(r * 20, 40)
        rc = pd.to_numeric(pd.Series([row.get("review_count")]), errors="coerce").iloc[0]
        if pd.notna(rc) and rc > 0:
            score += min(float(np.log1p(rc)) * 5, 30)
        hours_val = row.get("hours")
        if pd.notna(hours_val) and str(hours_val).strip():
            score += 20
        phone_val = row.get("phone")
        if pd.notna(phone_val) and str(phone_val).strip():
            score += 10
        scores.append(min(score, 100))

    if scores:
        stats["quality_stats"] = {
            "average": float(np.mean(scores)),
            "high_quality": int(sum(1 for s in scores if s >= 70)),
            "medium_quality": int(sum(1 for s in scores if 40 <= s < 70)),
            "low_quality": int(sum(1 for s in scores if s < 40)),
        }
        ranked = df.copy()
        ranked["quality_score"] = scores
        cols = [
            c for c in ["name", "city", "rating", "review_count", "quality_score"] if c in ranked
        ]
        stats["top_businesses"] = ranked.nlargest(min(10, total), "quality_score")[cols].to_dict(
            "records"
        )
    else:
        stats["quality_stats"] = {
            "average": 0.0,
            "high_quality": 0,
            "medium_quality": 0,
            "low_quality": 0,
        }
        stats["top_businesses"] = []

    return stats


def _bar_rows(breakdown: dict, limit: int = 15) -> str:
    if not breakdown:
        return '<p class="empty">No data.</p>'
    items = list(breakdown.items())[:limit]
    top = max(v for _, v in items) or 1
    rows = []
    for label, value in items:
        width = _pct(value, top)
        rows.append(
            f'<div class="bar-row"><span class="bar-label">{html.escape(str(label))}</span>'
            f'<span class="bar"><span class="bar-fill" style="width:{width:.1f}%"></span></span>'
            f'<span class="bar-val">{value}</span></div>'
        )
    return "\n".join(rows)


def render_dashboard(stats: dict, source_name: str) -> str:
    total = stats["total_businesses"]
    rating_stats = stats.get("rating_stats", {})
    quality = stats.get("quality_stats", {})
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    kpis = [
        ("Total leads", f"{total:,}"),
        ("Cities", str(stats["cities"])),
        ("Categories", str(stats["categories"])),
        ("Avg rating", f"{rating_stats.get('average', 0):.2f}"),
        ("Avg quality", f"{quality.get('average', 0):.0f}"),
        ("High-quality", str(quality.get("high_quality", 0))),
    ]
    kpi_html = "\n".join(
        f'<div class="kpi"><div class="kpi-val">{html.escape(v)}</div>'
        f'<div class="kpi-label">{html.escape(k)}</div></div>'
        for k, v in kpis
    )

    coverage = [
        ("Phone", _pct(stats["with_phone"], total)),
        ("Rating", _pct(stats["with_rating"], total)),
        ("Hours", _pct(stats["with_hours"], total)),
    ]
    coverage_html = "\n".join(
        f'<div class="bar-row"><span class="bar-label">{label}</span>'
        f'<span class="bar"><span class="bar-fill" style="width:{val:.1f}%"></span></span>'
        f'<span class="bar-val">{val:.0f}%</span></div>'
        for label, val in coverage
    )

    top_rows = (
        "".join(
            "<tr>"
            f"<td>{html.escape(str(b.get('name', '')))}</td>"
            f"<td>{html.escape(str(b.get('city', '')))}</td>"
            f"<td>{b.get('rating', '')}</td>"
            f"<td>{b.get('review_count', '')}</td>"
            f"<td>{float(b.get('quality_score', 0)):.0f}</td>"
            "</tr>"
            for b in stats.get("top_businesses", [])
        )
        or '<tr><td colspan="5" class="empty">No data.</td></tr>'
    )

    city_html = _bar_rows(stats.get("city_breakdown", {}))
    category_html = _bar_rows(stats.get("category_breakdown", {}))
    rating_html = _bar_rows(stats.get("rating_distribution", {}))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Leadfinder Dashboard</title>
<style>
  :root {{ --bg:#0f1220; --card:#1a1e30; --ink:#e8ebf5; --muted:#9aa3bf; --accent:#5b8cff; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
         background:var(--bg); color:var(--ink); padding:24px; }}
  h1 {{ margin:0 0 4px; font-size:22px; }}
  .sub {{ color:var(--muted); margin-bottom:20px; font-size:13px; }}
  .grid {{ display:grid; gap:16px; }}
  .kpis {{ grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); }}
  .cards {{ grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); }}
  .card {{ background:var(--card); border-radius:12px; padding:18px; }}
  .card h2 {{ font-size:14px; margin:0 0 14px; color:var(--muted); text-transform:uppercase;
             letter-spacing:.5px; }}
  .kpi {{ background:var(--card); border-radius:12px; padding:18px; text-align:center; }}
  .kpi-val {{ font-size:28px; font-weight:700; }}
  .kpi-label {{ color:var(--muted); font-size:12px; margin-top:4px; }}
  .bar-row {{ display:flex; align-items:center; gap:10px; margin:7px 0; font-size:13px; }}
  .bar-label {{ width:130px; color:var(--muted); overflow:hidden; text-overflow:ellipsis;
               white-space:nowrap; }}
  .bar {{ flex:1; background:#252a40; border-radius:6px; height:12px; overflow:hidden; }}
  .bar-fill {{ display:block; height:100%; background:var(--accent); }}
  .bar-val {{ width:52px; text-align:right; color:var(--ink); }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid #252a40; }}
  th {{ color:var(--muted); font-weight:600; }}
  .empty {{ color:var(--muted); }}
  .full {{ grid-column:1/-1; }}
</style>
</head>
<body>
  <h1>Leadfinder Dashboard</h1>
  <div class="sub">Source: {html.escape(source_name)} &middot; Generated {generated}</div>

  <div class="grid kpis">
    {kpi_html}
  </div>

  <div class="grid cards" style="margin-top:16px;">
    <div class="card"><h2>Data coverage</h2>{coverage_html}</div>
    <div class="card"><h2>Leads by city</h2>{city_html}</div>
    <div class="card"><h2>Leads by category</h2>{category_html}</div>
    <div class="card"><h2>Rating distribution</h2>{rating_html}</div>
    <div class="card full"><h2>Top businesses by quality score</h2>
      <table>
        <thead><tr><th>Name</th><th>City</th><th>Rating</th><th>Reviews</th><th>Quality</th></tr></thead>
        <tbody>{top_rows}</tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""


def build_dashboard(csv_path: str, output_file: str | None = None) -> str:
    """Compute stats from csv_path and write an HTML dashboard. Returns the output path."""
    logger = get_logger()
    df = load_leads(csv_path)
    stats = compute_stats(df)
    html_out = render_dashboard(stats, os.path.basename(csv_path))
    if output_file is None:
        output_file = os.path.join(os.path.dirname(csv_path) or ".", "dashboard.html")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_out)
    logger.info("Dashboard written to %s (%d leads)", output_file, stats["total_businesses"])
    return output_file


def latest_leads_file(output_dir: str) -> str | None:
    files = glob.glob(os.path.join(output_dir, "all_leads_no_website_*.csv"))
    files += glob.glob(os.path.join(output_dir, "verified", "verified_no_website_*.csv"))
    return max(files) if files else None


def main(output_dir: str = "leads_output", output_file: str | None = None) -> str | None:
    logger = get_logger()
    latest = latest_leads_file(output_dir)
    if not latest:
        logger.error("No leads CSV found in %s. Run the scraper first.", output_dir)
        return None
    return build_dashboard(latest, output_file)
