"""City name -> bounding box via Nominatim (OpenStreetMap), with a disk cache.

Free, no key. Etiquette for the shared public instance: identify the app via
User-Agent and avoid repeat lookups (hence the cache; one lookup per city ever).
"""

from __future__ import annotations

import json
import os

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "leadfinder/0.1 (+https://github.com/NicholasBurgo/local-search)"

Bbox = tuple[float, float, float, float]  # (west, south, east, north)

# Free-text "Covington LA" can geocode as "Covington Lane"; expanding the state
# code ("Covington, Louisiana") plus a settlement bias makes the town win.
US_STATES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}


def expand_city_query(city: str) -> str:
    """'Covington LA' -> 'Covington, Louisiana' (avoids the 'Lane' misparse)."""
    cleaned = city.strip().rstrip(",")
    parts = cleaned.rsplit(" ", 1)
    if len(parts) == 2:
        town, state = parts[0].rstrip(","), parts[1].upper().rstrip(".")
        if state in US_STATES:
            return f"{town}, {US_STATES[state]}"
    return cleaned


def _load_cache(cache_path: str | None) -> dict:
    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(cache_path: str | None, cache: dict) -> None:
    if not cache_path:
        return
    directory = os.path.dirname(cache_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except OSError:
        pass  # cache is best-effort


def city_bbox(city: str, cache_path: str | None = None, client: httpx.Client | None = None) -> Bbox:
    """Return (west, south, east, north) for a free-text city like 'Covington LA'.

    Nominatim's boundingbox comes back as [south, north, west, east] strings.
    """
    cache = _load_cache(cache_path)
    if city in cache:
        west, south, east, north = cache[city]
        return (float(west), float(south), float(east), float(north))

    query = expand_city_query(city)
    own_client = client is None
    if own_client:
        client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15)
    try:
        # Bias toward towns/cities first; fall back to an unconstrained search.
        resp = client.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "featureType": "settlement"},
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            resp = client.get(NOMINATIM_URL, params={"q": query, "format": "json", "limit": 1})
            resp.raise_for_status()
            results = resp.json()
    finally:
        if own_client:
            client.close()

    if not results:
        raise ValueError(f"Could not geocode '{city}' via Nominatim")
    south, north, west, east = (float(x) for x in results[0]["boundingbox"])
    bbox: Bbox = (west, south, east, north)

    cache[city] = list(bbox)
    _save_cache(cache_path, cache)
    return bbox
