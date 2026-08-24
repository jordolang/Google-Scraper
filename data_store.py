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
#:
#: Every listing column is carried through verbatim, so the contacts file is a
#: superset of the listings file rather than a lossy subset of it.  It used to
#: drop ``reviews_count``, ``plus_code`` and ``hours``, which meant a mail
#: merge fed from the contacts export simply had no column to map those to.
#: ``original_phone`` trails the listing columns: it is the number Google Maps
#: gave us, kept beside the one the website gave us.
CONTACT_FIELDS: Sequence[str] = tuple(LISTING_FIELDS) + ("original_phone",)

#: Human-readable header for every column, for the exports that are handed to
#: another program (a mail-merge tool, a CRM import) rather than read back by
#: this one.  ``--friendly-headers`` writes these instead of the snake_case
#: field names; :func:`field_for_header` maps them back on the way in, so a
#: file written either way still round-trips through the rest of the pipeline.
FIELD_LABELS: Mapping[str, str] = {
    "name": "Business Name",
    "rating": "Rating",
    "reviews_count": "Reviews Count",
    "category": "Category",
    "address": "Address",
    "phone": "Phone",
    "website": "Website",
    "plus_code": "Plus Code",
    "hours": "Hours",
    "url": "URL",
    "search_term": "Search Term",
    "search_location": "Search Location",
    "email": "Email",
    "contact_name": "Contact Name",
    "scraped_phone": "Scraped Phone",
    "phone_source": "Phone Source",
    "emailed": "Emailed",
    "emailed_at": "Emailed At",
    "emailed_to": "Emailed To",
    "emailed_subject": "Emailed Subject",
    "email_template": "Email Template",
    "original_phone": "Original Phone",
    "phone_e164": "Phone E164",
}


def _slug(value: str) -> str:
    """``"Business Name"`` -> ``"business_name"`` — one comparable form."""
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


#: Every spelling of a column we accept on the way in -> its internal name.
_HEADER_TO_FIELD: dict[str, str] = {}
for _field, _label in FIELD_LABELS.items():
    _HEADER_TO_FIELD[_field] = _field
    _HEADER_TO_FIELD[_slug(_label)] = _field


def header_label(field: str) -> str:
    """The human-readable header for one column."""
    return FIELD_LABELS.get(field, str(field or "").replace("_", " ").title())


def field_for_header(header: str) -> str:
    """The internal column name for a CSV header, however it was spelled.

    ``"Business Name"``, ``"business name"`` and ``"name"`` all mean ``name``.
    An unrecognised header keeps its own slug, so an extra column somebody
    added by hand survives a read/write round trip.
    """
    return _HEADER_TO_FIELD.get(_slug(header), _slug(header))


def normalise_row(row: Mapping[str, object]) -> dict[str, object]:
    """Re-key one CSV row onto the internal column names."""
    return {field_for_header(key): value for key, value in row.items() if key}


def read_rows(path: Path | str) -> list[dict[str, object]]:
    """Read a CSV written by this app, whichever header style it used."""
    with open(path, "r", newline="", encoding="utf-8") as handle:
        return [normalise_row(row) for row in csv.DictReader(handle)]


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
    friendly_headers: bool = False,
) -> Path | None:
    """Write ``rows`` to a timestamped CSV in this search's folder.

    Returns the path written, or ``None`` when there is nothing to save.
    Rows are stamped with the search that produced them so a CSV read back
    later still knows where it came from.

    ``friendly_headers`` swaps the snake_case field names for the labels in
    :data:`FIELD_LABELS` (``name`` -> ``Business Name``) for files that go
    straight into a mail merge.  Every column is still present, in the same
    order, and :func:`read_rows` reads either style back.
    """
    rows = list(rows)
    if not rows:
        return None

    fields = list(fields)
    path = _unique(search_dir(search_term, location, base), timestamped_name(prefix, when))
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", restval="")
        if friendly_headers:
            writer.writerow({field: header_label(field) for field in fields})
        else:
            writer.writeheader()
        for row in rows:
            record = normalise_row(row)
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
    friendly_headers: bool = False,
) -> Path | None:
    """Save Google Maps search results."""
    return write_rows(
        rows, fields=LISTING_FIELDS, prefix="listings",
        search_term=search_term, location=location, base=base,
        friendly_headers=friendly_headers,
    )


def export_contacts(
    rows: Iterable[Mapping[str, object]],
    search_term: str,
    location: str = "",
    base: Path | None = None,
    friendly_headers: bool = False,
) -> Path | None:
    """Save the website contact-scrape enrichment for a search."""
    return write_rows(
        rows, fields=CONTACT_FIELDS, prefix="contacts",
        search_term=search_term, location=location, base=base,
        friendly_headers=friendly_headers,
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
        reader = csv.DictReader(handle)
        original_headers = list(reader.fieldnames or [])
        rows = [normalise_row(row) for row in reader]
    # Rewrite the file the way we found it: a listings CSV exported with
    # friendly headers must not silently turn back into snake_case halfway
    # through a run, or the mail merge loses its column mapping.
    friendly = any(
        header != field_for_header(header) for header in original_headers
    )

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
        if friendly:
            writer.writerow({f: header_label(f) for f in LISTING_FIELDS})
        else:
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
