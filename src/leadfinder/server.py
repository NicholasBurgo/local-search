"""Local web app server (stdlib http.server): live map search over Overture.

Bound to 127.0.0.1 by default. The HTTP shell is thin; all logic lives in the
pure endpoint functions (geocode/search/verify), which are unit-tested with fakes.
"""

from __future__ import annotations

import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pandas as pd

from .analytics import lead_records
from .config import Settings
from .geo import bbox_center, bbox_from_center
from .geocode import city_bbox
from .logging_setup import get_logger
from .sources.overture import fetch_overture_bbox
from .verify import verify_rows
from .webui import render_app_page


def _records_from_leads(leads) -> list[dict]:
    """Lead objects -> JSON records (scores + coerced types), same shape as the dashboard."""
    if not leads:
        return []
    return lead_records(pd.DataFrame([lead.to_row() for lead in leads]))


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


def search_endpoint(
    payload: dict, settings: Settings, *, fetch=fetch_overture_bbox, geocoder=city_bbox
) -> dict:
    """Resolve center (from q or lat/lon) + radius -> bbox -> Overture leads."""
    try:
        radius = float(payload.get("radius_miles") or 10)
    except (TypeError, ValueError):
        return {"error": "invalid radius"}
    radius = max(0.5, min(radius, 100))

    if payload.get("q"):
        try:
            center = bbox_center(geocoder(payload["q"]))
        except Exception as exc:
            return {"error": f"could not find '{payload['q']}': {exc}"}
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

    return {
        "center": list(center),
        "radius_miles": radius,
        "bbox": list(bbox),
        "count": len(leads),
        "leads": _records_from_leads(leads),
    }


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


def make_handler(settings: Settings):
    class _Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):  # keep stdout clean; we log via our logger
            pass

        def do_GET(self):
            route = urlparse(self.path)
            if route.path in ("/", "/index.html"):
                self._send(
                    200, render_app_page(settings).encode("utf-8"), "text/html; charset=utf-8"
                )
            elif route.path == "/api/geocode":
                params = {k: v[0] for k, v in parse_qs(route.query).items()}
                self._send(200, geocode_endpoint(params))
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
                self._send(200, search_endpoint(payload, settings))
            elif route.path == "/api/verify":
                self._send(200, verify_endpoint(payload, settings))
            else:
                self._send(404, {"error": "not found"})

    return _Handler


def serve(settings: Settings, host: str = "127.0.0.1", port: int = 8000) -> None:
    logger = get_logger()
    httpd = ThreadingHTTPServer((host, port), make_handler(settings))
    logger.info("Leadfinder web app running at http://%s:%d  (Ctrl-C to stop)", host, port)
    logger.info("Default location: %s", settings.cities[0] if settings.cities else "(none)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down.")
    finally:
        httpd.server_close()


def main(**overrides) -> None:
    host = overrides.pop("host", None) or "127.0.0.1"
    port = int(overrides.pop("port", None) or 8000)
    # Web app defaults to Overture (no key needed); ignore an accidental google source.
    overrides.setdefault("source", "overture")
    settings = Settings.from_env(**overrides)
    serve(settings, host=host, port=port)
