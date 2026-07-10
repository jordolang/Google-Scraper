"""Load and merge scraped CSVs into clean, call-ready Business records.

Two scrape outputs describe the same businesses:
  * google_maps_results_*.csv — best phones, ratings, review counts, hours
  * contact_details_*.csv      — enriched emails (and extra phones)

We merge them by a normalized business name, preferring the richest signal
for each field.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from urllib.parse import urlparse

from .models import Business

_IMAGE_EXT = re.compile(r"\.(png|jpe?g|gif|svg|webp|bmp|ico)$", re.IGNORECASE)
_BAD_EMAIL_HOSTS = ("sentry.wixpress.com", "example.com", "email.com", "placeholder.")
_BAD_WEB_DOMAINS = (
    "google.com",
    "business.google.com",
    "maps.google",
    "facebook.com",
    "instagram.com",
    "yelp.com",
    "linktr.ee",
)


def _clean(text: object) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text).strip().strip("\"'")).strip()


def _norm_name(name: str) -> str:
    """Normalize a business name into a merge key."""
    n = re.sub(r"[^\w\s]", "", _clean(name).lower())
    return re.sub(r"\s+", " ", n).strip()


def _digits(value: str) -> str:
    return re.sub(r"[^\d]", "", value or "")


def _format_phone(value: str) -> str | None:
    d = _digits(value)
    if len(d) == 11 and d[0] == "1":
        d = d[1:]
    if len(d) == 10:
        return f"({d[:3]}) {d[3:6]}-{d[6:]}"
    return None


def _collect_phones(*raw_values: str) -> tuple[str, ...]:
    """Pull every distinct, valid 10-digit phone out of messy fields."""
    seen: dict[str, str] = {}
    for raw in raw_values:
        for chunk in re.split(r"[,\n;/]+", raw or ""):
            formatted = _format_phone(chunk)
            if formatted:
                seen.setdefault(_digits(formatted), formatted)
    return tuple(seen.values())


def _best_email(raw: str) -> str | None:
    for part in re.split(r"[,\s]+", raw or ""):
        part = part.strip().strip(".")
        if "@" not in part or _IMAGE_EXT.search(part):
            continue
        lowered = part.lower()
        if any(bad in lowered for bad in _BAD_EMAIL_HOSTS):
            continue
        if re.match(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", part, re.IGNORECASE):
            return part
    return None


def _real_website(raw: str) -> str | None:
    w = _clean(raw)
    if not w or "@" in w:
        return None
    try:
        netloc = urlparse(w if "//" in w else f"http://{w}").netloc.lower()
    except ValueError:
        return None
    if not netloc or any(bad in netloc for bad in _BAD_WEB_DOMAINS):
        return None
    return w if "//" in w else f"https://{w}"


def _extract_city(address: str) -> str:
    parts = [p.strip() for p in (address or "").split(",") if p.strip()]
    if len(parts) >= 2:
        city = re.sub(r"\s+[A-Z]{2}\s+\d.*$", "", parts[-2]).strip()
        if city:
            return city
    return "your area"


def _to_float(value: str) -> float | None:
    try:
        return float(_clean(value))
    except (TypeError, ValueError):
        return None


def _to_int(value: str) -> int | None:
    d = _digits(_clean(value))
    return int(d) if d else None


def _latest(pattern: str, directory: Path) -> Path | None:
    matches = sorted(directory.glob(pattern), reverse=True)
    return matches[0] if matches else None


def _read_rows(path: Path | None) -> list[dict[str, str]]:
    if not path or not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_businesses(
    directory: str | Path = ".",
    maps_csv: str | Path | None = None,
    contacts_csv: str | Path | None = None,
) -> list[Business]:
    """Load, merge, and clean the latest scrape CSVs into Business records."""
    directory = Path(directory)
    maps_path = Path(maps_csv) if maps_csv else _latest("google_maps_results_*.csv", directory)
    contacts_path = Path(contacts_csv) if contacts_csv else _latest("contact_details_*.csv", directory)

    merged: dict[str, dict[str, str]] = {}

    # Maps data first (authoritative phones / ratings / reviews / hours).
    for row in _read_rows(maps_path):
        key = _norm_name(row.get("name", ""))
        if key:
            merged.setdefault(key, {}).update(row)

    # Overlay contact-detail enrichment (emails, extra phones, contact name).
    for row in _read_rows(contacts_path):
        key = _norm_name(row.get("name", ""))
        if not key:
            continue
        bucket = merged.setdefault(key, {})
        for field_name in ("email", "scraped_phone", "original_phone", "contact_name"):
            if _clean(row.get(field_name)):
                bucket[field_name] = row[field_name]
        for field_name in ("website", "category", "rating", "address", "url"):
            if not _clean(bucket.get(field_name)) and _clean(row.get(field_name)):
                bucket[field_name] = row[field_name]

    businesses: list[Business] = []
    for data in merged.values():
        name = _clean(data.get("name"))
        if not name:
            continue
        phones = _collect_phones(
            data.get("phone", ""),
            data.get("original_phone", ""),
            data.get("scraped_phone", ""),
        )
        address = _clean(data.get("address"))
        website = _real_website(data.get("website", ""))
        businesses.append(
            Business(
                name=name,
                category=_clean(data.get("category")),
                address=address,
                city=_extract_city(address),
                phone=phones[0] if phones else None,
                raw_phones=phones,
                email=_best_email(data.get("email", "")),
                website=website,
                has_website=website is not None,
                rating=_to_float(data.get("rating")),
                reviews_count=_to_int(data.get("reviews_count")),
                hours=_clean(data.get("hours")),
                maps_url=_clean(data.get("url")),
                search_location=_clean(data.get("search_location")),
            )
        )

    businesses.sort(key=lambda b: b.name.lower())
    return businesses
