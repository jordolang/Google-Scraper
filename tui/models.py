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

    # Populated by the website contact-scraping step.
    emails: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    contact_names: List[str] = field(default_factory=list)
    scanned: bool = False

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
    def contact_line(self) -> str:
        """Single-line summary of scraped contact info."""
        parts = []
        if self.emails:
            parts.append(", ".join(self.emails))
        if self.contact_names:
            parts.append("(" + ", ".join(self.contact_names) + ")")
        if self.phones:
            parts.append(self.phones[0])
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
            emails=_split_multi(data.get("email", "")),
            phones=_split_multi(data.get("scraped_phone", "")),
            contact_names=_split_multi(data.get("contact_name", "")),
        )

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
class EmailMessage:
    """A composed (and possibly user-edited) outreach email."""

    business: Business
    to_email: str
    subject: str
    html: str

    @property
    def label(self) -> str:
        return f"{self.business.name or '(unnamed)'}  →  {self.to_email}"
