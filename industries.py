"""Industry registry, classifier, and default pricing for outreach emails.

A single source of truth for the ten business industries Jlang.dev targets (plus
a neutral ``general`` fallback). Each :class:`Industry` knows:

* which standalone template file in ``email_templates/`` renders its email,
* the keywords used to auto-detect it from a Google-Maps ``category`` string,
* its accent colour (documentation / design reference), and
* its seed package pricing (the starting point the TUI pricing editor loads).

The classifier is deliberately forgiving: Google Maps categories are noisy
("Electrical installation service", "Mexican restaurant", …), so each industry
carries a generous list of lowercase substrings. The best-scoring industry wins;
registry order breaks ties; nothing matching falls back to ``general``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

GENERAL_KEY = "general"

# The seed prices every industry starts from. Mirrors the values that used to be
# hardcoded in the old single template. The TUI pricing editor overlays these and
# persists changes to pricing.json, so these are only ever the first-run defaults.
_DEFAULT_PRICES: Dict[str, str] = {
    "launchpad": "$499",
    "launchpad_sale": "$400",
    "attribution": "$350",
    "professional": "Starting at $1,499+",
    "enterprise": "Custom Pricing",
}


@dataclass(frozen=True)
class Industry:
    """One targetable industry and everything the email pipeline needs for it."""

    key: str  # stable id; also the template filename stem
    label: str  # human label shown in the TUI dropdown
    template_filename: str  # file under email_templates/
    keywords: Tuple[str, ...]  # lowercase substrings matched on category + name
    accent: str  # hex accent (design reference / docs)
    default_pricing: Dict[str, str] = field(default_factory=lambda: dict(_DEFAULT_PRICES))


# Order matters: earlier industries win keyword ties. Creative sits before
# Professional Services so "marketing agency" lands on creative, not consulting.
REGISTRY: List[Industry] = [
    Industry(
        key="home_trade_services",
        label="Home & Trade Services",
        template_filename="home_trade_services.html",
        keywords=(
            "contractor", "plumb", "electric", "hvac", "heating", "cooling",
            "air conditioning", "roofing", "roofer", "landscap", "lawn",
            "construction", "remodel", "renovation", "handyman", "painter",
            "painting", "flooring", "carpet", "fence", "concrete", "masonry",
            "pest", "garage door", "gutter", "septic", "excavat", "drywall",
            "insulation", "solar", "deck", "siding", "window", "cleaning service",
            "junk removal", "tree service", "pool service", "welding",
        ),
        accent="#f59e0b",  # amber — tools / hi-vis
    ),
    Industry(
        key="creative_design",
        label="Creative & Design",
        template_filename="creative_design.html",
        keywords=(
            "graphic design", "design studio", "design agency", "sign", "signage",
            "photograph", "photo studio", "videograph", "video production",
            "film", "branding", "brand", "print", "printing", "web design",
            "web develop", "marketing agency", "advertis", "creative", "media",
            "screen print", "embroidery", "illustrat", "animation",
            "photo studio", "recording studio", "art studio",
        ),
        accent="#8b5cf6",  # violet — agency / tech
    ),
    Industry(
        key="food_beverage",
        label="Food & Beverage",
        template_filename="food_beverage.html",
        keywords=(
            "restaurant", "bar ", "pub", "tavern", "cafe", "coffee", "bakery",
            "bake", "catering", "caterer", "food truck", "deli", "pizzeria",
            "pizza", "grill", "diner", "brewery", "brewpub", "winery", "juice",
            "ice cream", "creamery", "bistro", "eatery", "steakhouse", "sushi",
            "taco", "bbq", "barbecue", "sandwich", "donut", "smoothie", "food",
            "kitchen", "dining", "delivery",
        ),
        accent="#ef4444",  # red — appetite
    ),
    Industry(
        key="health_wellness",
        label="Health & Wellness",
        template_filename="health_wellness.html",
        keywords=(
            "gym", "fitness", "yoga", "pilates", "crossfit", "personal train",
            "chiropract", "physical therapy", "physiotherapy", "wellness",
            "nutrition", "dietit", "dental", "dentist", "orthodont", "clinic",
            "medical", "doctor", "physician", "chiro", "rehab", "acupuncture",
            "health", "therapy", "counseling", "optometr", "vision",
        ),
        accent="#10b981",  # emerald — health
    ),
    Industry(
        key="beauty_personal_care",
        label="Beauty & Personal Care",
        template_filename="beauty_personal_care.html",
        keywords=(
            "salon", "barber", "hair", "nail", "spa", "esthetic", "skincare",
            "skin care", "lash", "brow", "tattoo", "waxing", "beauty",
            "cosmetolog", "med spa", "makeup", "microblad", "tanning", "massage",
            "day spa", "grooming",
        ),
        accent="#ec4899",  # pink — beauty
    ),
    Industry(
        key="automotive",
        label="Automotive",
        template_filename="automotive.html",
        keywords=(
            "auto", "automotive", "mechanic", "car repair", "tire", "detailing",
            "body shop", "collision", "oil change", "transmission", "dealership",
            "car dealer", "motorcycle", "towing", "tow ", "car wash", "muffler",
            "brake", "windshield", "vehicle", "garage", "smog", "lube",
        ),
        accent="#3b82f6",  # blue — chrome / steel
    ),
    Industry(
        key="professional_services",
        label="Professional Services",
        template_filename="professional_services.html",
        keywords=(
            "law", "lawyer", "attorney", "legal", "account", "cpa", "bookkeep",
            "tax", "insurance", "consult", "financial", "finance", "notary",
            "advisor", "staffing", "recruit", "payroll", "audit", "wealth",
            "investment", "title company", "escrow", "engineer", "architect",
            "surveyor", "translation",
        ),
        accent="#6366f1",  # indigo — trust / corporate
    ),
    Industry(
        key="real_estate_property",
        label="Real Estate & Property",
        template_filename="real_estate_property.html",
        keywords=(
            "real estate", "realtor", "realty", "broker", "property management",
            "property manage", "mortgage", "apartment", "leasing", "home builder",
            "homes", "land", "commercial real estate", "rental", "housing",
            "condo", "relocation",
        ),
        accent="#14b8a6",  # teal — property
    ),
    Industry(
        key="retail_boutique",
        label="Retail & Boutique",
        template_filename="retail_boutique.html",
        keywords=(
            "boutique", "shop", "store", "florist", "flower", "gift", "jewelry",
            "jeweler", "apparel", "clothing", "fashion", "furniture", "thrift",
            "consignment", "retail", "market", "grocery", "hardware", "bookstore",
            "candle", "antique", "toy", "pet store", "supply",
        ),
        accent="#a855f7",  # purple — boutique
    ),
    Industry(
        key="events_hospitality",
        label="Events & Hospitality",
        template_filename="events_hospitality.html",
        keywords=(
            "event", "venue", "wedding", "hotel", "motel", "inn", "resort",
            "dj", "entertainment", "rental", "party", "banquet", "hospitality",
            "tour", "travel", "planner", "florist event", "photo booth",
            "limousine", "limo", "catering hall", "conference",
        ),
        accent="#f43f5e",  # rose — celebration
    ),
]

GENERAL = Industry(
    key=GENERAL_KEY,
    label="General (default)",
    template_filename="general.html",
    keywords=(),
    accent="#6366f1",
)

_ALL: List[Industry] = REGISTRY + [GENERAL]
_BY_KEY: Dict[str, Industry] = {ind.key: ind for ind in _ALL}


def all_industries() -> List[Industry]:
    """Every industry, in dropdown order (the ten targets, then general)."""
    return list(_ALL)


def get(key: str) -> Industry:
    """Look an industry up by key; unknown keys resolve to :data:`GENERAL`."""
    return _BY_KEY.get(key or "", GENERAL)


def choices() -> List[Tuple[str, str]]:
    """``[(label, key), …]`` for a Textual ``Select`` widget."""
    return [(ind.label, ind.key) for ind in _ALL]


def default_pricing() -> Dict[str, Dict[str, str]]:
    """The seed pricing table: ``{industry_key: {package: price}}``."""
    return {ind.key: dict(ind.default_pricing) for ind in _ALL}


def classify(category: str = "", name: str = "") -> str:
    """Best-guess industry key for a business from its category (and name).

    Scores each industry by how many of its keywords appear in the lowercased
    ``category + " " + name`` text; the highest score wins, registry order breaks
    ties, and no match falls back to :data:`GENERAL_KEY`.
    """
    haystack = f"{category or ''} {name or ''}".lower()
    best_key = GENERAL_KEY
    best_score = 0
    for ind in REGISTRY:
        score = sum(1 for kw in ind.keywords if kw in haystack)
        if score > best_score:
            best_key = ind.key
            best_score = score
    return best_key
