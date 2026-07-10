"""Turn a flat list of businesses into an ordered, tiered call queue.

Priority rules (per the calling strategy):
  * Businesses with NO website and NO email are the hottest, cleanest pitches
    ("you're invisible online") and get called first.
  * A valid phone is required — no phone means it cannot be a call, so those
    are parked in the UNCALLABLE tier at the very end.
  * Within a tier, established businesses (more reviews, higher rating) rank
    higher: they can afford the service and the social proof aids the pitch.
"""

from __future__ import annotations

from .models import Business, QueueEntry, Tier

# Suggested call length by tier (minutes), inside the 5–15 min session window.
_TIER_MINUTES = {
    Tier.NO_SITE_NO_EMAIL: 7,
    Tier.NO_SITE: 8,
    Tier.WEAK_SITE: 12,
    Tier.HAS_SITE: 13,
    Tier.UNCALLABLE: 0,
}


def classify(business: Business) -> Tier:
    """Assign a business to its call tier."""
    if not business.callable:
        return Tier.UNCALLABLE
    if not business.has_website:
        return Tier.NO_SITE_NO_EMAIL if not business.has_email else Tier.NO_SITE
    # Has a website. Treat "no captured contact email" as a weaker presence
    # signal worth a more consultative (longer) conversation.
    return Tier.WEAK_SITE if not business.has_email else Tier.HAS_SITE


def score(business: Business) -> float:
    """Higher = call sooner within a tier. Rewards reach + social proof."""
    value = 0.0
    if business.reviews_count:
        # Diminishing returns; 100+ reviews ≈ a well-established operator.
        value += min(business.reviews_count, 200) / 4.0
    if business.rating:
        value += business.rating * 6.0          # 4.9★ ≈ +29
    if len(business.raw_phones) > 1:
        value += 3.0                             # multiple numbers = reachable
    if business.address:
        value += 2.0
    return round(value, 2)


def build_queue(businesses: list[Business]) -> list[QueueEntry]:
    """Build the fully ordered call queue with tier + score + slot length."""
    entries = [
        QueueEntry(
            business=b,
            tier=classify(b),
            score=score(b),
            suggested_minutes=_TIER_MINUTES[classify(b)],
        )
        for b in businesses
    ]
    entries.sort(key=lambda e: (int(e.tier), -e.score, e.business.name.lower()))
    return entries


def tier_breakdown(entries: list[QueueEntry]) -> dict[Tier, int]:
    counts: dict[Tier, int] = {tier: 0 for tier in Tier}
    for entry in entries:
        counts[entry.tier] += 1
    return counts


def session_estimate(entries: list[QueueEntry]) -> int:
    """Total estimated calling minutes for the callable queue."""
    return sum(e.suggested_minutes for e in entries if e.tier != Tier.UNCALLABLE)
