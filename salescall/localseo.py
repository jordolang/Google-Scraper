"""Local SEO ranking engine.

The scraped businesses ARE the local competitive set for the origin search
(e.g. "roofing Zanesville, OH"). Google's local ranking is driven by
prominence (reviews + rating), proximity, and relevance — so we compute a
defensible local-SEO rank per career field, identify closest competitors, and
translate the standing into spoken sales pitches.

Exact SERP positions (SerpApi / DataForSEO / Brightdata) are a future upgrade;
this proxy uses the same factors Google actually weighs.
"""

from __future__ import annotations

import math
import os
import re

from .models import Business, Competitor, Finding, LocalRanking

# Default search origin — Zanesville, OH. Override with SALESCALL_ORIGIN_LATLNG="lat,lng".
_ZANESVILLE = (39.9403, -82.0132)

_COORD_RE = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")

# Career-field canonicalization: keyword -> field label (first match wins).
_FIELD_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("roof", "Roofing"),
    ("gutter", "Gutters & Spouting"),
    ("spouting", "Gutters & Spouting"),
    ("seamless", "Gutters & Spouting"),
    ("pressure wash", "Pressure Washing"),
    ("power wash", "Pressure Washing"),
    ("wash", "Pressure Washing"),
    ("paint", "Painting"),
    ("handyman", "Handyman"),
    ("siding", "Siding & Exteriors"),
    ("exterior", "Siding & Exteriors"),
    ("lumber", "Building Supply"),
    ("supply", "Building Supply"),
    ("general contractor", "General Contractor"),
    ("construction", "General Contractor"),
    ("contractor", "General Contractor"),
)


def origin() -> tuple[float, float]:
    raw = os.environ.get("SALESCALL_ORIGIN_LATLNG", "")
    match = re.match(r"\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*", raw)
    if match:
        return float(match.group(1)), float(match.group(2))
    return _ZANESVILLE


def extract_latlng(maps_url: str) -> tuple[float, float] | None:
    m = _COORD_RE.search(maps_url or "")
    return (float(m.group(1)), float(m.group(2))) if m else None


def haversine_miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return round(2 * 3958.8 * math.asin(math.sqrt(h)), 1)


def canonical_field(category: str) -> str:
    cat = (category or "").lower()
    for keyword, field in _FIELD_KEYWORDS:
        if keyword in cat:
            return field
    return (category or "Other").title()


def _prominence(rating: float | None, reviews: int | None, has_website: bool,
                distance: float | None, max_distance: float) -> float:
    """Composite of the factors Google weighs for local ranking."""
    score = 0.0
    # Prominence — reviews dominate when present (log-scaled), rating next.
    if reviews:
        score += math.log1p(reviews) * 14.0
    if rating:
        score += rating * 6.0
    # Web presence helps local SEO.
    if has_website:
        score += 8.0
    # Proximity — closer to the search origin ranks higher.
    if distance is not None and max_distance > 0:
        score += (1.0 - min(distance, max_distance) / max_distance) * 12.0
    return round(score, 2)


def _competitor(business: Business, rank: int, distance: float | None) -> Competitor:
    return Competitor(
        name=business.name,
        rank=rank,
        rating=business.rating,
        reviews=business.reviews_count,
        has_website=business.has_website,
        distance_miles=distance,
    )


def _findings(business: Business, ranking_data: dict) -> tuple[Finding, ...]:
    field = ranking_data["field"]
    rank = ranking_data["rank"]
    size = ranking_data["field_size"]
    above = ranking_data["competitors_above"]
    is_real = ranking_data.get("is_real", False)
    findings: list[Finding] = []

    placed = f"#{rank} of {size}"
    if size <= 1:
        return ()

    # Real Google rank → state it as fact; proxy → frame as an estimate.
    source_phrase = (
        "in Google's actual local results" if is_real
        else "by our analysis (reviews, rating, proximity)"
    )
    top_half = rank <= max(1, size // 2)
    above_with_site = sum(1 for c in above if c.has_website)

    if not top_half:
        findings.append(Finding(
            key="local_rank_low", severity="critical",
            headline=f"{'Google rank' if is_real else 'Est. local rank'} {placed} for {field}",
            detail=f"Bottom half of {size} local competitors ({'SERP' if is_real else 'proxy'}).",
            pitch=f"For '{field.lower()}' around here you're sitting at {placed} "
                  f"{source_phrase} — that's page-two territory, and almost nobody "
                  f"scrolls there. The jobs are going to whoever's in the top 3.",
        ))
    elif rank == 1:
        findings.append(Finding(
            key="local_rank_top", severity="warning",
            headline=f"{'Google rank' if is_real else 'Est. local rank'} #1 for {field}",
            detail=f"Top of {size} competitors ({'SERP' if is_real else 'proxy'}).",
            pitch=f"You're #1 {source_phrase} for '{field.lower()}' — that's a real "
                  f"asset, and it's exactly why a great site matters: you've got the "
                  f"visibility, but if the site behind it is weak or missing, you're "
                  f"sending hard-won traffic to a dead end. Let's convert that #1 "
                  f"spot into booked jobs before a competitor takes it.",
        ))
    else:
        findings.append(Finding(
            key="local_rank_ok", severity="warning",
            headline=f"{'Google rank' if is_real else 'Est. local rank'} {placed} for {field}",
            detail=f"Top half of {size} competitors ({'SERP' if is_real else 'proxy'}).",
            pitch=f"You're actually doing alright — {placed} {source_phrase} for "
                  f"'{field.lower()}'. But the gap between #{rank} and the #1 spot is "
                  f"real money, and a proper site is how you climb it.",
        ))

    if not business.has_website and above_with_site:
        verb = "has" if above_with_site == 1 else "have"
        n_phrase = "one" if above_with_site == 1 else str(above_with_site)
        findings.append(Finding(
            key="local_competitors_have_sites", severity="critical",
            headline=f"{above_with_site} higher-ranked competitor(s) have websites",
            detail="Businesses ranked above this one have real websites.",
            pitch=f"And {n_phrase} of the outfits ranking above you {verb} a real "
                  f"website while you've got nothing. That's not a coincidence — "
                  f"Google rewards it, and it's costing you the top spot.",
        ))

    nearest = ranking_data.get("nearest")
    if nearest and nearest.distance_miles is not None:
        edge = ("has a website" if nearest.has_website else "still has no website")
        findings.append(Finding(
            key="local_nearest_competitor", severity="info",
            headline=f"Closest competitor: {nearest.name} ({nearest.distance_miles} mi)",
            detail=f"Same field, {nearest.distance_miles} miles away.",
            pitch=f"Your closest competitor, {nearest.name}, is only "
                  f"{nearest.distance_miles} miles from you and {edge} — "
                  f"{'we can leapfrog them' if not nearest.has_website else 'we can outbuild them'}.",
        ))

    return tuple(findings)


def build_local_rankings(
    businesses: list[Business],
    origin_latlng: tuple[float, float] | None = None,
    real_positions: dict[str, int] | None = None,
    real_field_sizes: dict[str, int] | None = None,
) -> dict[str, LocalRanking]:
    """Rank every business within its career field; return {slug: LocalRanking}.

    When ``real_positions`` (slug -> Google local-pack position) is supplied,
    those businesses are ordered by their true rank and marked source="serp";
    everyone else falls back to the prominence proxy.
    """
    orig = origin_latlng or origin()
    real_positions = real_positions or {}
    real_field_sizes = real_field_sizes or {}
    coords: dict[str, tuple[float, float] | None] = {
        b.slug: extract_latlng(b.maps_url) for b in businesses
    }
    distances: dict[str, float | None] = {
        b.slug: (haversine_miles(orig, coords[b.slug]) if coords[b.slug] else None)
        for b in businesses
    }
    max_dist = max((d for d in distances.values() if d is not None), default=1.0) or 1.0

    def proxy(b: Business) -> float:
        return _prominence(b.rating, b.reviews_count, b.has_website,
                           distances[b.slug], max_dist)

    # Group by canonical field.
    fields: dict[str, list[Business]] = {}
    for b in businesses:
        fields.setdefault(canonical_field(b.category), []).append(b)

    rankings: dict[str, LocalRanking] = {}
    for field, members in fields.items():
        # Order: real-ranked businesses by true position first, then proxy.
        scored = sorted(
            members,
            key=lambda b: (real_positions.get(b.slug, 10_000), -proxy(b)),
        )
        ranked_competitors = [
            _competitor(b, i + 1, distances[b.slug]) for i, b in enumerate(scored)
        ]
        size = len(scored)
        for idx, b in enumerate(scored):
            rank = idx + 1
            above = tuple(ranked_competitors[:idx])
            top = tuple(ranked_competitors[: min(3, size)])
            nearest = None
            if coords[b.slug]:
                others = [
                    (haversine_miles(coords[b.slug], coords[o.slug]), o)
                    for o in scored if o.slug != b.slug and coords[o.slug]
                ]
                if others:
                    dist, other = min(others, key=lambda x: x[0])
                    nearest = _competitor(other, scored.index(other) + 1, dist)

            real_rank = real_positions.get(b.slug)
            is_real = real_rank is not None
            real_size = real_field_sizes.get(field)
            eff_rank = real_rank if is_real else rank
            eff_size = (real_size if is_real and real_size else size)
            percentile = round((size - rank) / max(size - 1, 1) * 100, 0) if size > 1 else 100.0
            findings = _findings(b, {
                "field": field, "rank": eff_rank, "field_size": eff_size,
                "competitors_above": above, "nearest": nearest, "is_real": is_real,
            })
            rankings[b.slug] = LocalRanking(
                field=field, rank=rank, field_size=size, percentile=percentile,
                score=proxy(b), distance_from_origin=distances[b.slug],
                competitors_above=above, top_competitors=top,
                nearest_competitor=nearest, findings=findings,
                source="serp" if is_real else "proxy",
                real_rank=real_rank, real_field_size=real_size,
            )
    return rankings
