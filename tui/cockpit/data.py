"""Load the prioritized call queue for the cockpit screens.

Mirrors sales_calls._load_queue but returns an empty list (never exits) when
no scraped CSVs are present, so the TUI can show a friendly empty-state.
"""

from __future__ import annotations

from salescall import cache
from salescall.data_loader import load_businesses
from salescall.localseo import build_local_rankings
from salescall.models import QueueEntry
from salescall.prioritize import build_queue


def has_scraped_data(root: str = ".") -> bool:
    return bool(load_businesses(root))


def load_queue(root: str = ".") -> list[QueueEntry]:
    businesses = load_businesses(root)
    if not businesses:
        return []
    queue = build_queue(businesses)
    positions, field_sizes = cache.load_serp()
    rankings = build_local_rankings(
        businesses, real_positions=positions, real_field_sizes=field_sizes
    )
    return [
        e.with_local(rankings[e.business.slug]) if e.business.slug in rankings else e
        for e in queue
    ]
