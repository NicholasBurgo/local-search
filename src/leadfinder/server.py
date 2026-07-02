"""Local web app server (stdlib http.server): serves the frontend + a JSON API.

Bound to 127.0.0.1 by default (use --host 0.0.0.0 for a container/LAN). The HTTP
shell is thin; all logic lives in pure endpoint functions, which are unit-tested
with fakes. The frontend is real static files under web/ (served here), not
Python string templates.
"""

from __future__ import annotations

import asyncio
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pandas as pd

from .analytics import lead_records
from .categories import BUSINESS_CATEGORIES
from .config import Settings
from .geo import bbox_center, bbox_from_center
from .geocode import city_bbox, suggest_places
from .logging_setup import get_logger
from .sources.overture import fetch_overture_bbox
from .store import LeadStore
from .verify import verify_rows

_WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

# Whitelisted static routes -> (filename, directory, content-type).
_STATIC: dict[str, tuple[str, str, str]] = {
    "/": ("index.html", _WEB_DIR, "text/html; charset=utf-8"),
    "/index.html": ("index.html", _WEB_DIR, "text/html; charset=utf-8"),
    "/review": ("review.html", _WEB_DIR, "text/html; charset=utf-8"),
    "/review.html": ("review.html", _WEB_DIR, "text/html; charset=utf-8"),
    "/app.css": ("app.css", _WEB_DIR, "text/css; charset=utf-8"),
    "/app.js": ("app.js", _WEB_DIR, "text/javascript; charset=utf-8"),
    "/review.js": ("review.js", _WEB_DIR, "text/javascript; charset=utf-8"),
    "/leaflet.css": ("leaflet.css", _ASSETS_DIR, "text/css; charset=utf-8"),
    "/leaflet.js": ("leaflet.js", _ASSETS_DIR, "text/javascript; charset=utf-8"),
}


def read_static(path: str) -> tuple[bytes, str] | None:
    entry = _STATIC.get(path)
    if not entry:
        return None
    name, directory, ctype = entry
    file_path = os.path.join(directory, name)
    if not os.path.isfile(file_path):
        return None
    with open(file_path, "rb") as f:
        return f.read(), ctype


def _records_from_leads(leads) -> list[dict]:
    """Lead objects -> JSON records (scores + coerced types), same shape as the dashboard."""
    if not leads:
        return []
    return lead_records(pd.DataFrame([lead.to_row() for lead in leads]))


def config_endpoint(settings: Settings) -> dict:
    return {
        "defaultLocation": settings.cities[0] if settings.cities else "Covington LA",
        "defaultRadius": int(settings.radius_miles) if settings.radius_miles else 10,
        "minConfidence": settings.min_confidence,
        "categories": [
            {"key": key, "label": key.replace("_", " ").title()} for key in BUSINESS_CATEGORIES
        ],
    }


def suggest_endpoint(params: dict, suggester=suggest_places) -> dict:
    query = (params.get("q") or "").strip()
    if len(query) < 3:
        return {"suggestions": []}
    try:
        return {"suggestions": suggester(query)}
    except Exception as exc:  # surface autocomplete failure quietly
        get_logger().warning("suggest failed: %s", exc)
        return {"suggestions": []}


def geocode_endpoint(params: dict, geocoder=city_bbox) -> dict:
    query = (params.get("q") or "").strip()
    if not query:
        return {"error": "missing location"}
    try:
        bbox = geocoder(query)
    except Exception as exc:
        return {"error": str(exc)}
    lat, lon = bbox_center(bbox)
    return {"center": [lat, lon], "bbox": list(bbox), "label": query}


def _merge_stored(records: list[dict], store) -> None:
    """Overlay persisted marks (decision/contacted/verification) onto fresh records."""
    stored = store.get([r.get("place_id") for r in records])
    for r in records:
        s = stored.get(r.get("place_id"))
        if not s:
            continue
        r["decision"] = s.get("decision")
        r["contacted"] = bool(s.get("contacted"))
        if s.get("verification_status"):
            r["verification_status"] = s["verification_status"]
        if s.get("verified_date"):
            r["verified_date"] = s["verified_date"]


def search_endpoint(
    payload: dict, settings: Settings, store=None, *, fetch=fetch_overture_bbox, geocoder=city_bbox
) -> dict:
    """Resolve center (from q or lat/lon) + radius -> bbox -> Overture leads."""
    try:
        radius = float(payload.get("radius_miles") or 10)
    except (TypeError, ValueError):
        return {"error": "invalid radius"}
    radius = max(0.5, min(radius, 100))

    label = None
    if payload.get("q"):
        try:
            bbox = geocoder(payload["q"])
        except Exception as exc:
            return {"error": f"could not find '{payload['q']}': {exc}"}
        center = bbox_center(bbox)
        label = payload["q"]
    elif payload.get("lat") is not None and payload.get("lon") is not None:
        center = (float(payload["lat"]), float(payload["lon"]))
    else:
        return {"error": "provide a location or coordinates"}

    bbox = bbox_from_center(center[0], center[1], radius)
    min_conf = float(payload.get("min_confidence", settings.min_confidence))
    categories = payload.get("categories") or settings.categories
    try:
        leads = fetch(
            bbox,
            release=settings.overture_release,
            min_confidence=min_conf,
            allowed_categories=categories,
        )
    except Exception as exc:
        get_logger().error("web search failed: %s", exc)
        return {"error": f"search failed: {exc}"}

    records = _records_from_leads(leads)
    if store is not None:
        store.upsert(records)  # persist so we don't have to re-pull
        _merge_stored(records, store)  # show any existing marks
    return {
        "center": list(center),
        "radius_miles": radius,
        "bbox": list(bbox),
        "label": label,
        "count": len(records),
        "leads": records,
    }


def saved_endpoint(params: dict, store) -> dict:
    leads = store.saved(params.get("filter"))
    return {"count": len(leads), "leads": leads, "stats": store.stats()}


def mark_endpoint(payload: dict, store) -> dict:
    place_id = payload.get("place_id")
    if not place_id:
        return {"error": "missing place_id"}
    kwargs = {}
    if "decision" in payload:
        kwargs["decision"] = payload["decision"]
    if "contacted" in payload:
        kwargs["contacted"] = payload["contacted"]
    store.mark(place_id, **kwargs)
    return {"ok": True, "stats": store.stats()}


def reverify_endpoint(payload: dict, settings: Settings, store, *, verifier=None) -> dict:
    leads = store.saved()  # everything we hold
    if not leads:
        return {"leads": [], "count": 0}
    run = verifier or (lambda r: asyncio.run(verify_rows(r, settings)))
    try:
        results = run(leads)
    except Exception as exc:
        get_logger().error("reverify failed: %s", exc)
        return {"error": f"reverify failed: {exc}"}
    store.update_verification(results)
    return {"leads": results, "count": len(results), "stats": store.stats()}


def stats_endpoint(store) -> dict:
    return store.stats()


def verify_endpoint(payload: dict, settings: Settings, *, verifier=None) -> dict:
    rows = payload.get("leads") or []
    if not rows:
        return {"leads": [], "count": 0}
    run = verifier or (lambda r: asyncio.run(verify_rows(r, settings)))
    try:
        results = run(rows)
    except Exception as exc:
        get_logger().error("web verify failed: %s", exc)
        return {"error": f"verify failed: {exc}"}
    return {"leads": results, "count": len(results)}


def make_handler(settings: Settings, store: LeadStore):
    class _Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body, ctype="application/json", cache=False):
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            # Frontend files change during dev; never let the browser serve stale JS/CSS.
            if not cache:
                self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):  # keep stdout clean; we log via our logger
            pass

        def do_GET(self):
            route = urlparse(self.path)
            static = read_static(route.path)
            if static is not None:
                self._send(200, static[0], static[1])
            elif route.path == "/api/config":
                self._send(200, config_endpoint(settings))
            elif route.path == "/api/suggest":
                params = {k: v[0] for k, v in parse_qs(route.query).items()}
                self._send(200, suggest_endpoint(params))
            elif route.path == "/api/geocode":
                params = {k: v[0] for k, v in parse_qs(route.query).items()}
                self._send(200, geocode_endpoint(params))
            elif route.path == "/api/saved":
                params = {k: v[0] for k, v in parse_qs(route.query).items()}
                self._send(200, saved_endpoint(params, store))
            elif route.path == "/api/stats":
                self._send(200, stats_endpoint(store))
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            route = urlparse(self.path)
            length = int(self.headers.get("Content-Length", 0) or 0)
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._send(400, {"error": "invalid json"})
                return
            if route.path == "/api/search":
                self._send(200, search_endpoint(payload, settings, store))
            elif route.path == "/api/verify":
                self._send(200, verify_endpoint(payload, settings))
            elif route.path == "/api/reverify":
                self._send(200, reverify_endpoint(payload, settings, store))
            elif route.path == "/api/mark":
                self._send(200, mark_endpoint(payload, store))
            else:
                self._send(404, {"error": "not found"})

    return _Handler


def serve(settings: Settings, host: str = "127.0.0.1", port: int = 8000) -> None:
    logger = get_logger()
    store = LeadStore(os.path.join(settings.output_dir, "leadfinder.duckdb"))
    httpd = ThreadingHTTPServer((host, port), make_handler(settings, store))
    logger.info("Leadfinder web app running at http://%s:%d  (Ctrl-C to stop)", host, port)
    logger.info(
        "Default location: %s | stored leads: %s",
        settings.cities[0] if settings.cities else "(none)",
        store.stats(),
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down.")
    finally:
        httpd.server_close()
        store.close()


def main(**overrides) -> None:
    host = overrides.pop("host", None) or "127.0.0.1"
    port = int(overrides.pop("port", None) or 8000)
    overrides.setdefault("source", "overture")  # web app is keyless (Overture)
    # The web app searches any location interactively, so it can boot without a
    # configured city - fall back to a default initial location.
    if not os.getenv("SEARCH_CITIES") and not overrides.get("cities"):
        overrides["cities"] = ["Covington LA"]
    settings = Settings.from_env(**overrides)
    serve(settings, host=host, port=port)
