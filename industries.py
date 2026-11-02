"""Industry registry, classifier, and default pricing for outreach emails.

A single source of truth for the business industries and seasonal campaigns (plus
a neutral ``general`` fallback). Each :class:`Industry` knows:

* which standalone template file in ``email_templates/`` renders its email,
* the keywords used to auto-detect it from a Google-Maps ``category`` string,
* its accent colour (documentation / design reference), and
* its seed package pricing (the starting point the TUI pricing editor loads).

The classifier is deliberately forgiving: Google Maps categories are noisy
("Electrical installation service", "Mexican restaurant", …), so each industry
carries a generous list of lowercase substrings. The best-scoring industry wins;
registry order breaks ties. Specific local services are checked before broad
groups; nothing matching falls back to ``general``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

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
            "air conditioning", "landscap", "lawn",
            "construction", "remodel", "renovation", "handyman", "painter",
            "painting", "flooring", "carpet", "fence", "concrete", "masonry",
            "pest", "garage door", "septic", "excavat", "drywall",
            "insulation", "solar", "deck", "window", "cleaning service",
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


# Specific services take precedence over broad groups. Seasonal campaigns have
# no matching keywords: choose them explicitly, regardless of the current date.
LOCAL_INDUSTRIES: List[Industry] = [
    Industry(key='insurance_home', label='Home Insurance Providers', template_filename='insurance_home.html',
             keywords=('home insurance', 'homeowner insurance', 'homeowners insurance', "homeowner's insurance", 'home owner insurance'), accent='#60a5fa'),
    Industry(key='insurance_auto', label='Auto Insurance Providers', template_filename='insurance_auto.html',
             keywords=('auto insurance', 'car insurance', 'vehicle insurance', 'automobile insurance'), accent='#38bdf8'),
    Industry(key='insurance_renters', label='Renters & Rental Property Insurance', template_filename='insurance_renters.html',
             keywords=('renters insurance', 'renter insurance', "renter's insurance", "renters' insurance", 'rental insurance', 'rental property insurance', 'tenant insurance', 'landlord insurance'), accent='#c084fc'),
    Industry(key='insurance_boat', label='Boat & Marine Insurance Providers', template_filename='insurance_boat.html',
             keywords=('boat insurance', 'marine insurance', 'watercraft insurance', 'yacht insurance'), accent='#2dd4bf'),
    Industry(key='insurance_health', label='Health Insurance Providers', template_filename='insurance_health.html',
             keywords=('health insurance', 'healthcare insurance', 'health care insurance', 'medical insurance', 'medicare insurance', 'health insurance broker'), accent='#86efac'),
    Industry(key='lawncare', label='Lawncare & Landscaping', template_filename='lawncare.html',
             keywords=('lawn', 'landscap', 'grass cutting', 'mowing'), accent='#84cc16'),
    Industry(key='tree_removal', label='Tree Removal & Arborists', template_filename='tree_removal.html',
             keywords=('tree service', 'tree removal', 'arborist', 'stump grinding', 'tree trimming'), accent='#34d399'),
    Industry(key='roofing', label='Roofing Contractors', template_filename='roofing.html',
             keywords=('roofing', 'roofer', 'roof repair'), accent='#fb923c'),
    Industry(key='gutters', label='Gutter Installation & Cleaning', template_filename='gutters.html',
             keywords=('gutter', 'downspout'), accent='#38bdf8'),
    Industry(key='hvac', label='HVAC & Heating', template_filename='hvac.html',
             keywords=('hvac', 'heating', 'cooling', 'air conditioning', 'furnace'), accent='#22d3ee'),
    Industry(key='plumbing', label='Plumbing & Drain Services', template_filename='plumbing.html',
             keywords=('plumb', 'drain cleaning', 'water heater'), accent='#60a5fa'),
    Industry(key='electrical', label='Electrical Contractors', template_filename='electrical.html',
             keywords=('electrician', 'electrical', 'electric'), accent='#facc15'),
    Industry(key='excavation', label='Excavation & Site Work', template_filename='excavation.html',
             keywords=('excavat', 'site preparation', 'land clearing', 'grading contractor'), accent='#fbbf24'),
    Industry(key='septic', label='Septic Services', template_filename='septic.html',
             keywords=('septic', 'sewage disposal'), accent='#2dd4bf'),
    Industry(key='concrete_masonry', label='Concrete & Masonry', template_filename='concrete_masonry.html',
             keywords=('concrete', 'masonry', 'mason', 'bricklayer'), accent='#cbd5e1'),
    Industry(key='fencing_decks', label='Fencing & Decks', template_filename='fencing_decks.html',
             keywords=('fence', 'fencing', 'deck builder', 'deck contractor', 'deck'), accent='#d9a066'),
    Industry(key='painting', label='Painting Contractors', template_filename='painting.html',
             keywords=('painter', 'painting'), accent='#c084fc'),
    Industry(key='flooring', label='Flooring Installation', template_filename='flooring.html',
             keywords=('flooring', 'floor installer', 'carpet installer', 'tile contractor'), accent='#eab308'),
    Industry(key='pressure_washing', label='Pressure Washing', template_filename='pressure_washing.html',
             keywords=('pressure wash', 'power wash', 'soft wash'), accent='#67e8f9'),
    Industry(key='residential_cleaning', label='Residential Cleaning', template_filename='residential_cleaning.html',
             keywords=('house cleaning', 'residential cleaning', 'maid', 'cleaning service'), accent='#f9a8d4'),
    Industry(key='junk_removal', label='Junk Removal & Cleanouts', template_filename='junk_removal.html',
             keywords=('junk removal', 'cleanout', 'rubbish removal'), accent='#a3e635'),
    Industry(key='pest_control', label='Pest Control', template_filename='pest_control.html',
             keywords=('pest', 'exterminat', 'termite'), accent='#bef264'),
    Industry(key='towing', label='Towing & Roadside Assistance', template_filename='towing.html',
             keywords=('towing', 'tow truck', 'roadside assistance', 'wrecker'), accent='#fbbf24'),
    Industry(key='pet_grooming', label='Pet Grooming', template_filename='pet_grooming.html',
             keywords=('pet groom', 'dog groom', 'cat groom'), accent='#f0abfc'),
    Industry(key='farm_equipment_repair', label='Farm Equipment Repair', template_filename='farm_equipment_repair.html',
             keywords=('farm equipment', 'tractor repair', 'agricultural service', 'agricultural equipment'), accent='#fcd34d'),
    Industry(key='seasonal_snow_removal', label='Seasonal — Winter Snow Removal', template_filename='seasonal_snow_removal.html',
             keywords=(), accent='#7dd3fc'),
    Industry(key='seasonal_mowing', label='Seasonal — Spring & Summer Mowing', template_filename='seasonal_mowing.html',
             keywords=(), accent='#a3e635'),
    Industry(key='seasonal_leaves_tree_trimming', label='Seasonal — Fall Leaves & Tree Trimming', template_filename='seasonal_leaves_tree_trimming.html',
             keywords=(), accent='#fb923c'),
    Industry(key='seasonal_flood_water_mitigation', label='Seasonal — Spring Flooding & Water Mitigation', template_filename='seasonal_flood_water_mitigation.html',
             keywords=(), accent='#38bdf8'),
]

GENERAL = Industry(
    key=GENERAL_KEY,
    label="General (default)",
    template_filename="general.html",
    keywords=(),
    accent="#6366f1",
)

REGISTRY = LOCAL_INDUSTRIES + REGISTRY
_ALL: List[Industry] = REGISTRY + [GENERAL]
_BY_KEY: Dict[str, Industry] = {ind.key: ind for ind in _ALL}


class CatalogError(ValueError):
    """An external template catalog needs correction."""


def template_directory():
    """Use the same editable directory as the desktop app, without Qt imports."""
    from gui import runtime
    return runtime.user_asset("email_templates")


def _catalog_entries(templates_dir=None):
    """Read the external catalog, retaining built-ins for older installations."""
    directory = Path(templates_dir) if templates_dir is not None else template_directory()
    path = directory / "templates.json"
    if not path.exists():
        local_keys = {i.key for i in LOCAL_INDUSTRIES}
        return [(100 if i.key in local_keys else 0, i) for i in _ALL]
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict) or payload.get("version", 1) != 1:
            raise ValueError("Expected an object with version 1")
        entries = payload.get("templates")
        if not isinstance(entries, list):
            raise ValueError("'templates' must be a list")
        loaded = []
        seen = set()
        for number, entry in enumerate(entries, 1):
            if not isinstance(entry, dict):
                raise ValueError(f"Entry {number} must be an object")
            key, label, filename = (entry.get(field) for field in ("id", "name", "file"))
            if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", key):
                raise ValueError(f"Entry {number}: id must use lowercase letters, numbers and underscores")
            if key in seen:
                raise ValueError(f"Duplicate id: {key}")
            if not isinstance(label, str) or not label.strip():
                raise ValueError(f"{key}: name must be a nonempty string")
            if (not isinstance(filename, str) or not filename or '/' in filename
                    or '\\' in filename or Path(filename).suffix.lower() != '.html'):
                raise ValueError(f"{key}: file must be an HTML filename in the templates folder")
            target = directory / filename
            if not target.is_file() or not target.resolve().is_relative_to(directory.resolve()):
                raise ValueError(f"{key}: HTML file missing or outside the folder: {filename}")
            keywords = entry.get("keywords", [])
            if not isinstance(keywords, list) or any(not isinstance(k, str) or not k.strip() for k in keywords):
                raise ValueError(f"{key}: keywords must be a list of nonempty strings")
            accent = entry.get("accent", "#6366f1")
            if not isinstance(accent, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
                raise ValueError(f"{key}: accent must be a six-digit hex color")
            priority = entry.get("priority", 100)
            if type(priority) is not int:
                raise ValueError(f"{key}: priority must be an integer")
            prices = entry.get("default_pricing", {})
            if (not isinstance(prices, dict) or any(k not in _DEFAULT_PRICES or
                    not isinstance(v, str) or not v.strip() for k, v in prices.items())):
                raise ValueError(f"{key}: default_pricing must contain package names and nonempty price strings")
            loaded.append((priority, Industry(key, label.strip(), filename,
                tuple(k.lower() for k in keywords), accent, {**_DEFAULT_PRICES, **prices})))
            seen.add(key)
        # Preserve a neutral fallback even if the catalog omits its listing.
        if GENERAL_KEY not in seen:
            loaded.append((-1, GENERAL))
        loaded.sort(key=lambda pair: pair[0], reverse=True)
        return loaded
    except (OSError, UnicodeError, ValueError) as exc:
        raise CatalogError(f"{path}: {exc}") from exc


def all_industries(templates_dir=None) -> List[Industry]:
    """Every listed template, ordered by priority and then catalog order."""
    return [industry for _, industry in _catalog_entries(templates_dir)]


def get(key: str, templates_dir=None) -> Industry:
    """Look up a registered template; unknown IDs use the catalog's general entry."""
    entries = {i.key: i for i in all_industries(templates_dir)}
    return entries.get(key or "", entries.get(GENERAL_KEY, GENERAL))


def choices(templates_dir=None) -> List[Tuple[str, str]]:
    return [(ind.label, ind.key) for ind in all_industries(templates_dir)]


def default_pricing() -> Dict[str, Dict[str, str]]:
    return {ind.key: dict(ind.default_pricing) for ind in all_industries()}


def classify(category: str = "", name: str = "", *, templates_dir=None) -> str:
    """Match category before name; catalog priority/order resolves equal scores.

    Highest priority matching group wins, then keyword count within that group.
    The catalog is ordered by priority; built-in broad groups follow specifics.
    """
    entries = _catalog_entries(templates_dir)
    groups = sorted({priority for priority, _ in entries}, reverse=True)
    for text in (category, name):
        haystack = (text or "").lower()
        for priority in groups:
            best_key, best_score = GENERAL_KEY, 0
            for entry_priority, ind in entries:
                if entry_priority != priority or ind.key == GENERAL_KEY:
                    continue
                score = sum(1 for kw in ind.keywords if kw in haystack)
                if score > best_score:
                    best_key, best_score = ind.key, score
            if best_score:
                return best_key
    return GENERAL_KEY
