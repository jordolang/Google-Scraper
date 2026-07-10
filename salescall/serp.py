"""Real local-pack rankings from a SERP provider.

Fetches the actual Google Maps local results for a "{field} {location}" query
and matches scraped businesses to their true ranked position. This replaces the
prominence-based proxy in localseo.py whenever real positions are available.

Provider is pluggable; SerpApi is the default (free tier ~100 searches/mo).
Set SERPAPI_KEY (or SERP_API_KEY) in your environment / .env. With no key the
module returns nothing and callers fall back to the proxy ranking.

  SerpApi:     https://serpapi.com/google-maps-api   (engine=google_maps)

To add another backend (Brightdata, DataForSEO), implement a function with the
same shape as `_serpapi_fetch` and register it in _PROVIDERS.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

import requests

from .models import Business

_TIMEOUT = 40


@dataclass(frozen=True)
class SerpResult:
    position: int
    title: str
    rating: float | None = None
    reviews: int | None = None
    place_id: str = ""
    lat: float | None = None
    lng: float | None = None


def _api_key() -> str:
    return os.environ.get("SERPAPI_KEY") or os.environ.get("SERP_API_KEY") or ""


def provider_name() -> str:
    return os.environ.get("SERP_PROVIDER", "serpapi").lower()


def available() -> bool:
    """True when a SERP backend is configured and usable."""
    return bool(_api_key())


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _serpapi_fetch(query: str, latlng: tuple[float, float] | None) -> list[SerpResult]:
    params = {
        "engine": "google_maps",
        "type": "search",
        "q": query,
        "api_key": _api_key(),
        "hl": "en",
    }
    if latlng:
        # SerpApi "ll" format: @lat,lng,zoom
        params["ll"] = f"@{latlng[0]},{latlng[1]},13z"

    resp = requests.get("https://serpapi.com/search.json", params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    # The maps engine returns a list under "local_results"; the plain google
    # engine nests them under {"local_results": {"places": [...]}}.
    raw = data.get("local_results", [])
    if isinstance(raw, dict):
        raw = raw.get("places", [])

    results: list[SerpResult] = []
    for i, item in enumerate(raw, 1):
        gps = item.get("gps_coordinates", {}) or {}
        reviews = item.get("reviews")
        results.append(SerpResult(
            position=item.get("position", i),
            title=item.get("title", ""),
            rating=item.get("rating"),
            reviews=int(reviews) if isinstance(reviews, (int, float)) else None,
            place_id=item.get("place_id", ""),
            lat=gps.get("latitude"),
            lng=gps.get("longitude"),
        ))
    return results


_PROVIDERS = {"serpapi": _serpapi_fetch}


def fetch_local_results(query: str, latlng: tuple[float, float] | None = None) -> list[SerpResult]:
    """Fetch ranked local results for a query. Returns [] on any failure."""
    if not available():
        return []
    fetch = _PROVIDERS.get(provider_name())
    if not fetch:
        return []
    try:
        return fetch(query, latlng)
    except (requests.RequestException, ValueError, KeyError):
        return []


def match_position(business: Business, results: list[SerpResult]) -> int | None:
    """Find a business's real position in the result list by name match."""
    target = _norm(business.name)
    if not target:
        return None
    for r in results:
        rt = _norm(r.title)
        if rt and (rt == target or rt in target or target in rt):
            return r.position
    return None


def gather_real_positions(
    businesses: list[Business], origin_latlng: tuple[float, float] | None = None
) -> tuple[dict[str, int], dict[str, int]]:
    """Query the SERP provider once per career field and match businesses.

    Returns (positions, field_sizes):
      positions   {business.slug: real local-pack position}
      field_sizes {canonical_field: number of results Google returned}
    Empty dicts when no SERP key is configured.
    """
    if not available():
        return {}, {}

    # Imported here to avoid any import-order coupling.
    from .localseo import canonical_field

    location = next((b.search_location for b in businesses if b.search_location), "")
    by_field: dict[str, list[Business]] = {}
    for b in businesses:
        by_field.setdefault(canonical_field(b.category), []).append(b)

    positions: dict[str, int] = {}
    field_sizes: dict[str, int] = {}
    for field, members in by_field.items():
        query = f"{field} {location}".strip()
        results = fetch_local_results(query, origin_latlng)
        if not results:
            continue
        field_sizes[field] = len(results)
        for b in members:
            pos = match_position(b, results)
            if pos is not None:
                positions[b.slug] = pos
    return positions, field_sizes
