"""Where every scrape lands on disk.

All scraped rows are written to a CSV under the repo's ``data/`` directory,
partitioned by the search that produced them::

    data/<search term>/<location>/listings71326-1109pm.csv
    data/<search term>/<location>/contacts71326-1109pm.csv

So a search for "Electricians" in "Zanesville, OH" writes to
``data/Electricians/Zanesville-OH/``.  The state is kept in the location folder
so two same-named cities in different states never merge.

Both the CLI scrapers and the TUI pipeline go through :func:`export_listings`
and :func:`export_contacts`, so no run is lost when the interface closes.
"""

from __future__ import annotations

import csv
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping, Sequence

#: Columns written by :func:`export_listings` (Google Maps search results).
#:
#: The listings CSV is the durable record of a search: the scrape fills the
#: business columns, the contact scan fills the contact columns, and a sent
#: email fills the outreach columns — so one file tells you who was found, how
#: to reach them, and who has already been contacted.
LISTING_FIELDS: Sequence[str] = (
    "name", "rating", "reviews_count", "category", "address", "phone",
    "website", "plus_code", "hours", "url", "search_term", "search_location",
    # Filled in by the website contact scan, or by the Google / Yellow Pages
    # phone lookup when the website gave us nothing (phone_source says which).
    "email", "contact_name", "scraped_phone", "phone_source",
    # Filled in when an outreach email actually goes out.
    "emailed", "emailed_at", "emailed_to", "emailed_subject", "email_template",
)

#: What we write into ``email_template`` for the normal outreach email.
STANDARD_EMAIL = "standard contact email"

#: Columns written by :func:`export_contacts` (website contact scrape).
CONTACT_FIELDS: Sequence[str] = (
    "name", "email", "scraped_phone", "original_phone", "contact_name",
    "address", "website", "category", "rating", "url",
    "search_term", "search_location", "phone_source",
)

_UNSPECIFIED = "unspecified"
_REPO_ROOT = Path(__file__).resolve().parent


def data_root() -> Path:
    """The ``data/`` directory all exports live under.

    ``GOOGLE_SCRAPER_DATA_DIR`` overrides it (used by the tests, and handy for
    pointing a run at an external drive).
    """
    override = os.environ.get("GOOGLE_SCRAPER_DATA_DIR")
    return Path(override).expanduser() if override else _REPO_ROOT / "data"


def slugify(value: str, fallback: str = _UNSPECIFIED) -> str:
    """Turn a search term or location into one safe path segment.

    ``"Zanesville, OH"`` -> ``"Zanesville-OH"``; ``"HVAC / Heating"`` ->
    ``"HVAC-Heating"``.  Words keep their original casing so the folders stay
    readable.
    """
    cleaned = re.sub(r"[^\w\s-]", " ", str(value or "")).strip()
    cleaned = re.sub(r"[\s_-]+", "-", cleaned).strip("-")
    return cleaned or fallback


def search_dir(search_term: str, location: str = "", base: Path | None = None) -> Path:
    """Return (and create) the folder holding one search's exports."""
    root = Path(base) if base is not None else data_root()
    directory = root / slugify(search_term) / slugify(location)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def timestamped_name(prefix: str, when: datetime | None = None) -> str:
    """Build a filename like ``listings71326-1109pm.csv``."""
    when = when or datetime.now()
    stamp = f"{when.month}{when.day}{when:%y}"
    clock = when.strftime("%I%M%p").lstrip("0").lower()
    return f"{prefix}{stamp}-{clock}.csv"


def _unique(directory: Path, filename: str) -> Path:
    """Avoid clobbering an export made in the same minute."""
    path = directory / filename
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    counter = 2
    while (directory / f"{stem}-{counter}{suffix}").exists():
        counter += 1
    return directory / f"{stem}-{counter}{suffix}"


def write_rows(
    rows: Iterable[Mapping[str, object]],
    *,
    fields: Sequence[str],
    prefix: str,
    search_term: str,
    location: str = "",
    base: Path | None = None,
    when: datetime | None = None,
) -> Path | None:
    """Write ``rows`` to a timestamped CSV in this search's folder.

    Returns the path written, or ``None`` when there is nothing to save.
    Rows are stamped with the search that produced them so a CSV read back
    later still knows where it came from.
    """
    rows = list(rows)
    if not rows:
        return None

    path = _unique(search_dir(search_term, location, base), timestamped_name(prefix, when))
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore", restval="")
        writer.writeheader()
        for row in rows:
            record = dict(row)
            record.setdefault("search_term", search_term)
            record.setdefault("search_location", location)
            if not record.get("search_term"):
                record["search_term"] = search_term
            if not record.get("search_location"):
                record["search_location"] = location
            writer.writerow(record)
    return path


def export_listings(
    rows: Iterable[Mapping[str, object]],
    search_term: str,
    location: str = "",
    base: Path | None = None,
) -> Path | None:
    """Save Google Maps search results."""
    return write_rows(
        rows, fields=LISTING_FIELDS, prefix="listings",
        search_term=search_term, location=location, base=base,
    )


def export_contacts(
    rows: Iterable[Mapping[str, object]],
    search_term: str,
    location: str = "",
    base: Path | None = None,
) -> Path | None:
    """Save the website contact-scrape enrichment for a search."""
    return write_rows(
        rows, fields=CONTACT_FIELDS, prefix="contacts",
        search_term=search_term, location=location, base=base,
    )


def row_key(name: str) -> str:
    """Match key used to line a business up with its row in the listings CSV."""
    return re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).strip()


def update_listings(path: Path | None, updates: Mapping[str, Mapping[str, object]]) -> Path | None:
    """Merge ``updates`` into an existing listings CSV, keyed by :func:`row_key`.

    Used to fold the contact scan and the send results back into the file the
    search produced, so the export is never a stale snapshot of step one.
    Unknown businesses are appended rather than dropped.
    """
    if not path or not updates:
        return None
    path = Path(path)
    if not path.exists():
        return None

    with open(path, "r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    pending = {key: dict(value) for key, value in updates.items()}
    for row in rows:
        patch = pending.pop(row_key(row.get("name", "")), None)
        if patch:
            row.update({k: v for k, v in patch.items() if v not in (None, "")})

    for key, patch in pending.items():  # emailed a business the file never saw
        if patch.get("name"):
            rows.append(dict(patch))

    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(LISTING_FIELDS), extrasaction="ignore", restval="",
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def outreach_record(
    to_email: str,
    subject: str = "",
    when: datetime | None = None,
    template: str = STANDARD_EMAIL,
) -> dict[str, str]:
    """The columns stamped onto a listing once its email is delivered."""
    when = when or datetime.now()
    return {
        "emailed": "yes",
        "emailed_at": when.strftime("%Y-%m-%d %H:%M:%S"),
        "emailed_to": to_email,
        "emailed_subject": subject,
        "email_template": template,
    }


def was_emailed(row: Mapping[str, object]) -> bool:
    """True when a listings row records a delivered outreach email."""
    return str(row.get("emailed", "") or "").strip().lower() in {"yes", "true", "1", "sent"}


def latest_export(prefix: str, base: Path | None = None) -> Path | None:
    """Most recently written ``<prefix>*.csv`` anywhere under ``data/``."""
    root = Path(base) if base is not None else data_root()
    if not root.exists():
        return None
    matches = list(root.rglob(f"{prefix}*.csv"))
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)
