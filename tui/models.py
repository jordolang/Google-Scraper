"""Dataclasses shared across the TUI screens and the pipeline layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


def _split_multi(value: str) -> List[str]:
    """Split a comma separated CSV cell into a clean list of values."""
    if not value:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


@dataclass
class Business:
    """A single business returned by the Google Maps search.

    The optional contact fields (:attr:`emails`, :attr:`phones`,
    :attr:`contact_names`) are populated later by the contact-scraping step.
    """

    name: str = ""
    category: str = ""
    address: str = ""
    phone: str = ""
    website: str = ""
    rating: str = ""
    reviews_count: str = ""
    url: str = ""

    # The search that produced this row; used to file its CSV export under
    # data/<search term>/<location>/.
    search_term: str = ""
    search_location: str = ""

    # Populated by the website contact-scraping step.
    emails: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    contact_names: List[str] = field(default_factory=list)
    scanned: bool = False

    # Where :attr:`phones` came from when the website scan found nothing:
    # "" (the site itself), "google", or "yellowpages".
    phone_source: str = ""

    # Set once an outreach email is delivered; such a business is logged on the
    # listings CSV and skipped by the sales-call script.
    emailed: bool = False

    @property
    def primary_email(self) -> str:
        return self.emails[0] if self.emails else ""

    @property
    def has_email(self) -> bool:
        return bool(self.primary_email and "@" in self.primary_email)

    @property
    def display_line(self) -> str:
        """A short, single-line label used in the selection lists."""
        bits = [self.name or "(unnamed)"]
        if self.category:
            bits.append(self.category)
        if self.rating:
            bits.append(f"★{self.rating}")
        if self.website:
            bits.append(self.website)
        return "  •  ".join(bits)

    @property
    def has_contact_info(self) -> bool:
        """True when the scan (or a phone lookup) turned up anything usable."""
        return bool(self.emails or self.phones or self.contact_names)

    @property
    def needs_phone(self) -> bool:
        """True when we have no phone number for this business from any source."""
        return not self.phones and not self.phone

    @property
    def contact_line(self) -> str:
        """Single-line summary of scraped contact info."""
        parts = []
        if self.emails:
            parts.append(", ".join(self.emails))
        if self.contact_names:
            parts.append("(" + ", ".join(self.contact_names) + ")")
        if self.phones:
            phone = self.phones[0]
            if self.phone_source:
                # Parenthesised, not bracketed: Rich would read [x] as markup.
                phone += f" (via {self.phone_source})"
            parts.append(phone)
        elif self.phone:
            parts.append(self.phone)
        return "  •  ".join(parts) if parts else "no contact info found"

    @classmethod
    def from_dict(cls, data: dict) -> "Business":
        """Build a :class:`Business` from a scraper/CSV row dict."""
        return cls(
            name=str(data.get("name", "") or "").strip(),
            category=str(data.get("category", "") or "").strip(),
            address=str(data.get("address", "") or "").strip(),
            phone=str(data.get("phone", "") or data.get("original_phone", "") or "").strip(),
            website=str(data.get("website", "") or "").strip(),
            rating=str(data.get("rating", "") or "").strip(),
            reviews_count=str(data.get("reviews_count", "") or "").strip(),
            url=str(data.get("url", "") or "").strip(),
            search_term=str(data.get("search_term", "") or "").strip(),
            search_location=str(data.get("search_location", "") or "").strip(),
            phone_source=str(data.get("phone_source", "") or "").strip(),
            emails=_split_multi(data.get("email", "")),
            phones=_split_multi(data.get("scraped_phone", "")),
            contact_names=_split_multi(data.get("contact_name", "")),
        )

    def to_listing_row(self) -> dict:
        """Return a dict shaped like a ``listings`` CSV row (search results)."""
        return {
            "name": self.name,
            "rating": self.rating,
            "reviews_count": self.reviews_count,
            "category": self.category,
            "address": self.address,
            "phone": self.phone,
            "website": self.website,
            "url": self.url,
            "search_term": self.search_term,
            "search_location": self.search_location,
            "phone_source": self.phone_source,
        }

    def to_contact_row(self) -> dict:
        """Return a dict shaped like a ``contacts`` CSV row (scraped contacts)."""
        row = self.to_generator_row()
        row["search_term"] = self.search_term
        row["search_location"] = self.search_location
        row["phone_source"] = self.phone_source
        return row

    def to_generator_row(self) -> dict:
        """Return a dict shaped like a ``contact_details`` CSV row.

        This is the exact input ``EmailGenerator.generate_email`` expects.
        """
        return {
            "name": self.name,
            "email": ", ".join(self.emails),
            "scraped_phone": ", ".join(self.phones),
            "original_phone": self.phone,
            "contact_name": ", ".join(self.contact_names),
            "address": self.address,
            "website": self.website,
            "category": self.category,
            "rating": self.rating,
            "url": self.url,
        }


@dataclass
class ScanEvent:
    """One update from the website contact-scanning step.

    The pipeline emits a ``"scanning"`` event when it starts a website and a
    terminal event (``"done"``, ``"skipped"`` or ``"error"``) when it finishes,
    so the UI can both show what is in flight and advance a progress bar.
    """

    index: int  # 1-based position in the batch
    total: int
    name: str
    website: str = ""
    status: str = "scanning"  # scanning | done | skipped | error
    emails: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    contact_names: List[str] = field(default_factory=list)
    error: str = ""

    @property
    def finished(self) -> bool:
        """True once this business is no longer being worked on."""
        return self.status != "scanning"


@dataclass
class EmailMessage:
    """A composed (and possibly user-edited) outreach email."""

    business: Business
    to_email: str
    subject: str
    html: str

    @property
    def label(self) -> str:
        return f"{self.business.name or '(unnamed)'}  →  {self.to_email}"
