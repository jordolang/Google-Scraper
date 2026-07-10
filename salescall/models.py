"""Immutable domain models for the sales-call cockpit.

All records are frozen dataclasses — load/merge/prioritize steps return new
objects rather than mutating shared state.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import IntEnum
from typing import Optional


class Tier(IntEnum):
    """Call priority tiers. Lower value = called first (hottest lead)."""

    NO_SITE_NO_EMAIL = 1   # invisible online — cleanest, most urgent pitch
    NO_SITE = 2            # no website (may have an email)
    WEAK_SITE = 3          # has a site but it's poor / no contact captured
    HAS_SITE = 4           # established web presence — consultative upsell
    UNCALLABLE = 9         # no valid phone — cannot be called, parked aside


@dataclass(frozen=True)
class Business:
    """A single merged business record, cleaned and call-ready."""

    name: str
    category: str = ""
    address: str = ""
    city: str = "your area"
    phone: Optional[str] = None          # formatted (XXX) XXX-XXXX, best available
    raw_phones: tuple[str, ...] = ()      # every distinct number we scraped
    email: Optional[str] = None           # best real email, or None
    website: Optional[str] = None         # real website URL, or None
    has_website: bool = False
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    hours: str = ""
    maps_url: str = ""
    search_location: str = ""   # the seed-search location (origin), if recorded

    @property
    def has_email(self) -> bool:
        return bool(self.email and "@" in self.email)

    @property
    def callable(self) -> bool:
        return self.phone is not None

    @property
    def slug(self) -> str:
        import re

        s = re.sub(r"[^\w\s-]", "", self.name.lower())
        return re.sub(r"[-\s]+", "_", s).strip("_") or "business"


@dataclass(frozen=True)
class Finding:
    """One website-intel observation plus its sales translation."""

    key: str                       # machine id, e.g. "pagespeed_mobile_poor"
    severity: str                  # "critical" | "warning" | "good" | "info"
    headline: str                  # short human label for the brief
    detail: str = ""               # the raw technical fact
    pitch: str = ""                # ★ what the caller actually says about it


@dataclass(frozen=True)
class WebsiteIntel:
    """Aggregated intelligence about a business's web presence."""

    url: Optional[str] = None
    reachable: bool = False
    tech_stack: tuple[str, ...] = ()
    hosting: str = ""
    pagespeed_mobile: Optional[int] = None
    pagespeed_desktop: Optional[int] = None
    seo_score: Optional[int] = None
    findings: tuple[Finding, ...] = ()
    error: str = ""                # populated when analysis could not complete

    @property
    def selling_points(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity in ("critical", "warning"))

    @property
    def strengths(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == "good")


@dataclass(frozen=True)
class Competitor:
    """A rival business in the same career field, for comparison."""

    name: str
    rank: int
    rating: Optional[float] = None
    reviews: Optional[int] = None
    has_website: bool = False
    distance_miles: Optional[float] = None


@dataclass(frozen=True)
class LocalRanking:
    """Where a business sits in local SEO for its field, near the origin."""

    field: str                                   # canonical career field
    rank: int                                    # 1-based within the field
    field_size: int                              # competitors in the field
    percentile: float                            # 0–100, higher = better
    score: float
    distance_from_origin: Optional[float] = None  # miles from search origin
    competitors_above: tuple[Competitor, ...] = ()
    top_competitors: tuple[Competitor, ...] = ()
    nearest_competitor: Optional[Competitor] = None
    findings: tuple[Finding, ...] = ()
    source: str = "proxy"                         # "serp" (real) or "proxy"
    real_rank: Optional[int] = None               # true Google local-pack position
    real_field_size: Optional[int] = None         # competitors Google returned

    @property
    def is_real(self) -> bool:
        return self.source == "serp" and self.real_rank is not None

    @property
    def display_rank(self) -> int:
        return self.real_rank if self.is_real else self.rank

    @property
    def display_size(self) -> int:
        return self.real_field_size if (self.is_real and self.real_field_size) else self.field_size


@dataclass(frozen=True)
class QueueEntry:
    """A business positioned in the call queue with its slot metadata."""

    business: Business
    tier: Tier
    score: float
    suggested_minutes: int
    intel: Optional[WebsiteIntel] = None
    local: Optional[LocalRanking] = None

    def with_intel(self, intel: WebsiteIntel) -> "QueueEntry":
        return replace(self, intel=intel)

    def with_local(self, local: LocalRanking) -> "QueueEntry":
        return replace(self, local=local)


@dataclass(frozen=True)
class Outcome:
    """Logged result of a single call attempt."""

    business_slug: str
    business_name: str
    disposition: str               # e.g. "booked", "callback", "not_interested"
    notes: str = ""
    duration_seconds: int = 0
    timestamp: str = ""
    callback_at: str = ""
