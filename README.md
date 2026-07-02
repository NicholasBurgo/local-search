# Leadfinder

### Find local businesses without websites. Build your client pipeline.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

A Python tool that discovers local businesses without websites - useful for
freelance web developers, digital agencies, and marketing consultants building a
prospect list.

The scraper reads business data from the Google Places API (New) and keeps only
businesses whose `websiteUri` is empty. An optional verify stage then probes each
business's likely domains over HTTP to remove false positives, and a dashboard
command renders the results as a static HTML report.

---

## What it does

- **Discovery** - searches a wide taxonomy (150+ business types across 12
  categories) across the cities you configure.
- **Filtering** - keeps only operational businesses with no website on file;
  drops permanently closed ones.
- **Verification (optional)** - probes candidate domains guessed from the
  business name (no Google scraping), classifying each as no-website, has-website,
  chain, or parked.
- **Analytics** - a self-contained HTML dashboard: leads by city and category,
  rating distribution, data-coverage, and a top-businesses table.
- **Cost awareness** - a per-SKU monthly usage tracker with a soft budget and a
  pre-flight cost estimate before each run.

---

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) for environment and dependency management
- A Google Places API key with **Places API (New)** enabled

---

## Quick start

```bash
# 1. Install dependencies into a managed virtual environment
uv sync

# 2. Configure
cp .env.example .env
#   edit .env: set GOOGLE_API_KEY and SEARCH_CITIES

# 3. Collect leads
uv run leadfinder scrape

# 4. Verify (removes false positives) and build a dashboard
uv run leadfinder verify
uv run leadfinder dashboard
```

Output CSVs land in `leads_output/`; verified leads in `leads_output/verified/`.

---

## Commands

```bash
# Scrape specific cities and categories
uv run leadfinder scrape --cities "Austin TX" "Denver CO" --categories food_beverage home_services

# Cheaper run: fewer results per query and a tighter monthly budget
uv run leadfinder scrape --max-results 10 --monthly-budget 1000

# Verify the most recent leads file
uv run leadfinder verify --probe-concurrency 20

# Build a dashboard from the latest CSV in an output directory
uv run leadfinder dashboard --output-dir leads_output
```

Every flag has an `.env` equivalent; flags override the `.env` value for that run
only and never rewrite the file.

Scrapes are resumable: progress is checkpointed per (city, keyword), so a run
interrupted partway through picks up where it left off.

---

## Configuration

Required (`.env`):

| Setting | Description |
|---------|-------------|
| `GOOGLE_API_KEY` | Places API (New) key |
| `SEARCH_CITIES` | Comma-separated `City State` list |

Optional (defaults shown in `.env.example`):

| Setting | Default | Description |
|---------|---------|-------------|
| `FIELD_PROFILE` | `enterprise` | `essentials` / `pro` / `enterprise` / `atmosphere` |
| `SEARCH_CATEGORIES` | (all) | Subset of category keys to search |
| `MAX_RESULTS` | `20` | Results per query (Text Search caps at 20) |
| `MONTHLY_CALL_BUDGET` | `5000` | Soft ceiling on billable calls per month |
| `PROBE_CONCURRENCY` | `10` | Concurrent HTTP probes during verify |
| `PROBE_TIMEOUT` | `5.0` | Per-probe timeout in seconds |
| `OUTPUT_DIR` | `leads_output` | Where CSVs are written |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

---

## API cost (important)

Pricing changed in 2025. The old "25,000 free requests/day" model is gone.

- Google now bills **per SKU** with **per-SKU monthly free tiers** (roughly
  10,000 Essentials / 5,000 Pro / 1,000 Enterprise calls per month). The old
  universal $200 monthly credit was retired in March 2025.
- Billing is by **field mask**: the highest-tier field you request sets the SKU
  for the entire call. The `websiteUri` field this tool depends on is an
  **Enterprise** field, so scrape calls bill at the Enterprise Text Search SKU.
- Because Text Search (New) returns `websiteUri` directly, leadfinder uses a
  single Text Search call per query (no per-place Place Details call), which is
  far cheaper than the old two-stage approach.

leadfinder prints a pre-flight estimate (expected calls, SKU, free-tier
remaining, estimated USD) before each run and stops at `MONTHLY_CALL_BUDGET`. To
control spend, narrow `SEARCH_CATEGORIES`, lower `MAX_RESULTS`, or reduce the
number of cities.

See Google's [Places API usage and billing](https://developers.google.com/maps/documentation/places/web-service/usage-and-billing).

---

## Business categories

Twelve category groups, 150+ specific business types: food and beverage, retail,
health and wellness, professional services, home services, automotive,
entertainment and recreation, education and childcare, events and hospitality,
manufacturing and wholesale, agriculture and pets, transportation and logistics.

Edit `BUSINESS_CATEGORIES` in `src/leadfinder/categories.py` to customize.

---

## Development

```bash
uv sync                 # install runtime + dev dependencies
uv run ruff check .     # lint
uv run ruff format .    # format
uv run pytest           # run tests
```

Project layout:

```
src/leadfinder/
  config.py          settings from env/.env
  models.py          Lead dataclass, enums, SKU/pricing tables
  field_mask.py      Places API field masks per profile/SKU
  categories.py      search taxonomy
  domains.py         chain/social domain filters
  names.py           name normalization, domain guessing, fuzzy match
  places_client.py   Places API (New) gateway (google-maps-places)
  mapping.py         Place proto -> Lead
  usage.py           monthly per-SKU usage tracking + cost estimate
  storage.py         checkpoints, de-duplication, CSV output
  scrape.py          scrape pipeline
  probe.py           async HTTP domain probing
  verify.py          verify pipeline
  analytics.py       HTML dashboard
  cli.py             command-line interface
tests/
```

---

## Troubleshooting

**`PERMISSION_DENIED` / `403`** - the API key does not have **Places API (New)**
enabled (it is separate from the legacy Places API). Enable it in the Google
Cloud Console and, ideally, restrict the key to that API.

**`GOOGLE_API_KEY not found`** - ensure `.env` exists and contains the key.

**`No leads found`** - check remaining budget/quota, verify the city format
(`"Austin TX"`, not `"Austin, Texas"`), and try a single city first.

**Run stopped early at the budget** - raise `MONTHLY_CALL_BUDGET` or narrow the
search with `SEARCH_CATEGORIES` / `MAX_RESULTS`.

---

## License

MIT License - see the LICENSE file.
