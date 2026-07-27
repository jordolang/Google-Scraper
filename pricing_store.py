"""Persisted, per-industry package pricing for outreach emails.

Pricing used to be hardcoded inside the email HTML. It now lives in
``pricing.json`` at the repo root, seeded from :mod:`industries` defaults and
edited from the TUI — so Jordan never has to touch a ``.py`` file to change a
price. Prices are free-form display strings ("$400", "Starting at $1,499+",
"Custom Pricing"); nothing does arithmetic on them.

Public API
----------
* :func:`load_pricing`  – read pricing.json, backfilled with defaults.
* :func:`save_pricing`  – atomically write pricing.json.
* :func:`prices_for`    – the merged price row for one industry.
* :func:`pricing_tokens` – turn a price row into ``{{TOKEN}} -> value`` pairs
  for the email template renderer.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Optional

import industries

# The package fields, in display order. Keys match industries' default_pricing.
PACKAGE_FIELDS = (
    "launchpad",       # regular Launchpad price
    "launchpad_sale",  # discounted email-recipient price
    "attribution",     # attribution-option price
    "professional",    # Professional package
    "enterprise",      # Enterprise package
)

# Human labels for the TUI pricing editor.
FIELD_LABELS = {
    "launchpad": "Launchpad (regular)",
    "launchpad_sale": "Launchpad (email price)",
    "attribution": "Attribution option",
    "professional": "Professional",
    "enterprise": "Enterprise",
}

# Placeholder tokens each field maps to inside the templates.
_FIELD_TOKENS = {
    "launchpad": "{{LAUNCHPAD_PRICE}}",
    "launchpad_sale": "{{LAUNCHPAD_SALE_PRICE}}",
    "attribution": "{{ATTRIBUTION_PRICE}}",
    "professional": "{{PROFESSIONAL_PRICE}}",
    "enterprise": "{{ENTERPRISE_PRICE}}",
}

PRICING_PATH = Path("pricing.json")
SCHEMA_VERSION = 1

# A hero-image URL can be stored per industry (applied to every business in that
# industry unless a business overrides it). Kept in a separate "heroes" block so
# it never mixes with the price fields.
HERO_FIELD = "hero"


def default_pricing() -> Dict[str, Dict[str, str]]:
    """The full seed table from :mod:`industries` (a fresh copy)."""
    return industries.default_pricing()


def _merge_defaults(stored: Dict) -> Dict[str, Dict[str, str]]:
    """Overlay ``stored`` onto the defaults, backfilling any missing keys.

    Guarantees every registered industry and every package field is present, so
    callers never hit a KeyError even after new industries/fields are added.
    """
    table = default_pricing()
    industries_block = (stored or {}).get("industries", {}) if isinstance(stored, dict) else {}
    for key, defaults in table.items():
        overrides = industries_block.get(key, {}) if isinstance(industries_block, dict) else {}
        if isinstance(overrides, dict):
            for field in PACKAGE_FIELDS:
                value = overrides.get(field)
                if isinstance(value, str) and value.strip():
                    defaults[field] = value
    return table


def load_pricing(path: Path = PRICING_PATH) -> Dict[str, Dict[str, str]]:
    """Return ``{industry_key: {field: price}}``, defaults backfilled.

    A missing or malformed file yields the pure defaults — pricing is never a
    hard dependency on a file existing or being valid.
    """
    if not Path(path).exists():
        return default_pricing()
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_pricing()
    return _merge_defaults(raw)


def save_pricing(
    table: Dict[str, Dict[str, str]],
    path: Path = PRICING_PATH,
    *,
    heroes: Optional[Dict[str, str]] = None,
) -> Path:
    """Atomically persist the pricing table (and, optionally, hero URLs).

    When ``heroes`` is ``None`` any hero URLs already on disk are preserved, so a
    price-only save never wipes them.
    """
    path = Path(path)
    if heroes is None:
        heroes = load_heroes(path)
    payload = {"version": SCHEMA_VERSION, "industries": table, "heroes": heroes}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return path


def load_heroes(path: Path = PRICING_PATH) -> Dict[str, str]:
    """Return ``{industry_key: hero_url}`` from pricing.json (``{}`` if none)."""
    if not Path(path).exists():
        return {}
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    heroes = raw.get("heroes", {}) if isinstance(raw, dict) else {}
    if not isinstance(heroes, dict):
        return {}
    return {k: v for k, v in heroes.items() if isinstance(v, str) and v.strip()}


def hero_for(industry_key: str, heroes: Optional[Dict[str, str]] = None) -> str:
    """The stored hero-image URL for an industry (``""`` if none set)."""
    table = heroes if heroes is not None else load_heroes()
    return table.get(industry_key, "")


def prices_for(
    industry_key: str,
    store: Optional[Dict[str, Dict[str, str]]] = None,
) -> Dict[str, str]:
    """The merged price row for one industry (loads pricing.json if needed)."""
    table = store if store is not None else load_pricing()
    if industry_key in table:
        row = dict(table[industry_key])
    else:
        row = dict(industries.get(industry_key).default_pricing)
    # Backfill any field the row is missing so downstream tokens never blank out.
    seed = industries.get(industry_key).default_pricing
    for field in PACKAGE_FIELDS:
        row.setdefault(field, seed.get(field, ""))
    return row


def pricing_tokens(prices: Dict[str, str]) -> Dict[str, str]:
    """Turn a price row into ``{'{{LAUNCHPAD_PRICE}}': '$499', …}`` for rendering."""
    return {token: prices.get(field, "") for field, token in _FIELD_TOKENS.items()}
