"""Persist website intel to disk so the call cockpit loads it instantly.

Intel gathering is slow (network + headless browser), so we run it once in a
batch ('prep') and cache per-business JSON. The cockpit only reads the cache.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import Business, Finding, WebsiteIntel

CACHE_DIR = Path(".salescall_cache")


def _path(slug: str) -> Path:
    return CACHE_DIR / f"intel_{slug}.json"


def save_intel(business: Business, intel: WebsiteIntel) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    _path(business.slug).write_text(
        json.dumps(asdict(intel), indent=2), encoding="utf-8"
    )


def load_intel(business: Business) -> WebsiteIntel | None:
    path = _path(business.slug)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    findings = tuple(Finding(**f) for f in data.get("findings", []))
    data["findings"] = findings
    data["tech_stack"] = tuple(data.get("tech_stack", ()))
    return WebsiteIntel(**data)


def has_intel(business: Business) -> bool:
    return _path(business.slug).exists()


_SERP_PATH = CACHE_DIR / "serp_rankings.json"


def save_serp(positions: dict[str, int], field_sizes: dict[str, int]) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    _SERP_PATH.write_text(
        json.dumps({"positions": positions, "field_sizes": field_sizes}, indent=2),
        encoding="utf-8",
    )


def load_serp() -> tuple[dict[str, int], dict[str, int]]:
    if not _SERP_PATH.exists():
        return {}, {}
    try:
        data = json.loads(_SERP_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}, {}
    return data.get("positions", {}), data.get("field_sizes", {})
