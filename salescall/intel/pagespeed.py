"""Google PageSpeed Insights — real performance + SEO scores and Core Web Vitals.

Works without an API key (rate-limited). Set PAGESPEED_API_KEY for reliability.
Network/API failures degrade to an empty result rather than raising.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import requests

_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
_TIMEOUT = 60
_MAX_RETRIES = 3


@dataclass(frozen=True)
class PageSpeedResult:
    strategy: str
    performance: int | None = None
    seo: int | None = None
    accessibility: int | None = None
    lcp_seconds: float | None = None
    cls: float | None = None
    tbt_ms: int | None = None
    speed_index_seconds: float | None = None
    error: str = ""


def _pct(category: dict, name: str) -> int | None:
    cat = category.get(name)
    if cat and isinstance(cat.get("score"), (int, float)):
        return round(cat["score"] * 100)
    return None


def _audit_seconds(audits: dict, key: str) -> float | None:
    audit = audits.get(key, {})
    val = audit.get("numericValue")
    return round(val / 1000.0, 1) if isinstance(val, (int, float)) else None


def run_pagespeed(url: str, strategy: str = "mobile") -> PageSpeedResult:
    params = {
        "url": url,
        "strategy": strategy,
        "category": ["performance", "seo", "accessibility"],
    }
    api_key = os.environ.get("PAGESPEED_API_KEY")
    if api_key:
        params["key"] = api_key

    data: dict = {}
    last_error = ""
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.get(_ENDPOINT, params=params, timeout=_TIMEOUT)
            if resp.status_code == 429:
                # Rate limited (common without an API key) — back off and retry.
                last_error = "429 rate limited"
                time.sleep(2 ** attempt * 3)
                continue
            resp.raise_for_status()
            data = resp.json()
            break
        except (requests.RequestException, ValueError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(1)
    if not data:
        return PageSpeedResult(strategy=strategy, error=last_error or "no data")

    lh = data.get("lighthouseResult", {})
    cats = lh.get("categories", {})
    audits = lh.get("audits", {})

    cls_audit = audits.get("cumulative-layout-shift", {})
    tbt_audit = audits.get("total-blocking-time", {})
    return PageSpeedResult(
        strategy=strategy,
        performance=_pct(cats, "performance"),
        seo=_pct(cats, "seo"),
        accessibility=_pct(cats, "accessibility"),
        lcp_seconds=_audit_seconds(audits, "largest-contentful-paint"),
        cls=round(cls_audit["numericValue"], 3) if isinstance(cls_audit.get("numericValue"), (int, float)) else None,
        tbt_ms=round(tbt_audit["numericValue"]) if isinstance(tbt_audit.get("numericValue"), (int, float)) else None,
        speed_index_seconds=_audit_seconds(audits, "speed-index"),
    )
