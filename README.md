# Leadfinder

### Find local businesses without websites. Build your client pipeline.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

A Python tool that discovers local businesses without websites - useful for
freelance web developers, digital agencies, and marketing consultants building a
prospect list.

**Free by default.** The default data source is Overture Maps open data: no API
key, no account, no credit card. A Google Places API key is an optional upgrade
for wider coverage.

The pipeline: **scrape** candidates from the configured source, **verify** by
probing each business's likely domains over HTTP (removing false positives and
chains), then work the list in an interactive **dashboard** where you check
leads off as you contact them.

---

## Quick start (no key, no card)

```bash
# 1. Install dependencies into a managed virtual environment
uv sync

# 2. Configure: just set your cities
cp .env.example .env
#   edit .env: SEARCH_CITIES=Covington LA

# 3. Run the pipeline
uv run leadfinder scrape      # open data -> candidate leads ($0)
uv run leadfinder verify      # HTTP-probe domains -> drop false positives
uv run leadfinder dashboard   # build the interactive worklist
```

Output CSVs land in `leads_output/`; verified leads in `leads_output/verified/`;
the dashboard next to the CSV it was built from.

---

## Data sources (best of both)

| Source | Cost | Coverage | Extras |
|---|---|---|---|
| `overture` (default) | $0, no key | Good, but thinner than Google for tiny businesses | emails + socials, existence confidence, chains pre-filtered |
| `google` | Free tier ~1k calls/mo, needs key + billing | Best-in-class | ratings, reviews, hours, price level |
| `both` | as above | Union (Google wins on duplicates) | everything |

```bash
uv run leadfinder scrape --source overture   # default
uv run leadfinder scrape --source google     # needs GOOGLE_API_KEY
uv run leadfinder scrape --source both       # blend
```

The verify stage is source-independent: whatever produced the candidate list,
each business's likely domains (guessed from its name) are probed over HTTP, and
leads with a live matching site are removed. The probe - not the dataset - is
the final arbiter of "no website."

---

## The dashboard is a worklist

`uv run leadfinder dashboard` produces a single self-contained HTML file:

- **Check off leads** as you contact them - persisted in your browser
  (localStorage), survives regenerating the file.
- **Progress bar** ("12 of 87 contacted") and a **hide contacted** toggle.
- **Search, city/category filters, sortable columns** - KPIs and charts update
  live with your filters.
- **Click-to-call / click-to-email** (`tel:` / `mailto:` links).
- **Export filtered CSV** including a `contacted` column.
- **Light/dark theme** toggle, persisted.
- **Map** of every lead with coordinates (OpenStreetMap), colored by score,
  with a **center picker** and a **radius (miles) slider** that filters the
  table and pins together. Click a pin for call/email/details.
- Columns adapt to the data: rating columns appear only when the source
  provides ratings; an email column only when emails exist.

Each lead gets a **score** (0-100): contactability (phone +25, email +15,
socials +5, address +10) plus establishment (rating/reviews/hours for Google
data; existence confidence for Overture data).

The dashboard file works offline. Opened locally you get the full street map;
in a shared/hosted view the street tiles are hidden (content security policy)
but pins, radius, and the worklist still work.

---

## Interactive web app

For changing location and radius *live* (fetching more leads as you widen the
search), run the local web app:

```bash
uv run leadfinder serve            # http://127.0.0.1:8000
```

Search any location, drag the **radius slider** (a bigger radius re-queries
Overture and shows more businesses), plot every result on a real street map,
click **Verify** to probe domains and drop the ones that actually have a site,
and **Export CSV**. Local-only by default; needs internet for the map tiles.
The `scrape` command also takes `--radius <miles>` to widen the area for the
static dashboard.

---

## Commands

```bash
# Scrape specific cities and categories
uv run leadfinder scrape --cities "Covington LA" --categories food_beverage home_services

# Overture tuning: confidence floor, radius (miles), or a manual bounding box
uv run leadfinder scrape --min-confidence 0.4
uv run leadfinder scrape --radius 15
uv run leadfinder scrape --bbox " -90.17,30.43,-90.05,30.55"

# Verify with more concurrency
uv run leadfinder verify --probe-concurrency 20

# Dashboard from a specific output directory
uv run leadfinder dashboard --output-dir leads_output

# Interactive map + live location/radius search
uv run leadfinder serve --port 8000
```

Every flag has an `.env` equivalent; flags override for that run only and never
rewrite the file. Scrapes are checkpointed and resumable.

---

## Configuration

Required (`.env`):

| Setting | Description |
|---------|-------------|
| `SEARCH_CITIES` | Comma-separated `City State` list |

Common optional settings (see `.env.example` for all):

| Setting | Default | Description |
|---------|---------|-------------|
| `SOURCE` | `overture` | `overture` / `google` / `both` |
| `GOOGLE_API_KEY` | - | Only for `google`/`both`; needs "Places API (New)" enabled |
| `OVERTURE_RELEASE` | `2026-06-17.0` | Pinned open-data release |
| `MIN_CONFIDENCE` | `0.5` | Overture existence-confidence floor (0-1) |
| `SEARCH_CATEGORIES` | (all) | Subset of the 12 category keys |
| `MONTHLY_CALL_BUDGET` | `5000` | Google-only soft spend gate |
| `PROBE_CONCURRENCY` | `10` | Verify-stage concurrent HTTP probes |
| `OUTPUT_DIR` | `leads_output` | Where CSVs and the dashboard go |

---

## Google API cost (only if you opt into `google`/`both`)

Google bills per SKU with per-SKU monthly free tiers (~1,000 free
Enterprise-tier calls/month; the universal $200 credit ended March 2025), by
**field mask** - the highest-tier field requested sets the SKU. `websiteUri` is
Enterprise-tier, so scrape calls bill at the Enterprise Text Search SKU.
leadfinder prints a pre-flight estimate (calls, SKU, free-tier headroom, USD)
and stops at `MONTHLY_CALL_BUDGET`. Overture runs cost $0 and are not counted.

---

## Development

```bash
uv sync                              # install runtime + dev dependencies
uv run ruff check . && uv run ruff format --check .
uv run pytest                        # 50+ tests, all network mocked
uv run python scripts/check_ascii.py # source stays ASCII-only
```

Project layout:

```
src/leadfinder/
  config.py          settings from env/.env (key optional for overture)
  models.py          Lead dataclass, enums, SKU/pricing tables
  categories.py      search taxonomy (12 groups, 150+ types)
  domains.py         chain/social domain filters
  names.py           name normalization, domain guessing, fuzzy match
  geocode.py         city -> bbox via Nominatim (cached, state-code aware)
  geo.py             miles <-> bbox, haversine distance
  sources/
    base.py          Job protocol shared by all sources
    google.py        Places API (New) keyword searches
    overture.py      DuckDB bbox queries over Overture S3 parquet
  places_client.py   Places API (New) gateway (google-maps-places)
  mapping.py         Place proto -> Lead
  field_mask.py      Places API field masks per profile/SKU
  usage.py           monthly per-SKU usage tracking + cost estimate
  storage.py         checkpoints, de-duplication, CSV output
  scrape.py          source-agnostic scrape loop
  probe.py           async HTTP domain probing
  verify.py          verify pipeline
  analytics.py       interactive worklist dashboard (map + radius)
  server.py          local web app (stdlib http.server)
  webui.py           web app HTML page
  assets/            vendored Leaflet (third-party)
  cli.py             command-line interface
tests/
```

---

## Troubleshooting

**0 leads from Overture** - check the geocoded bbox in the log line
(`Overture bbox for ...`); if it looks wrong, pass `--bbox W,S,E,N` explicitly.
Lower `--min-confidence` for a longer (noisier) list. Small towns genuinely
yield short lists from open data.

**`PERMISSION_DENIED` (google source)** - the key does not have
**Places API (New)** enabled (it is separate from the legacy Places API).

**Slow first Overture query** - DuckDB downloads its httpfs extension once and
the S3 scan takes a few seconds; subsequent runs are faster.

**Checks disappeared from the dashboard** - check-offs live in the browser's
localStorage per origin; clearing site data clears them. Export CSV to keep a
permanent record (includes the `contacted` column).

---

## License

MIT License - see the LICENSE file.
