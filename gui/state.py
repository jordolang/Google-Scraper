"""Shared application state.

One :class:`AppState` lives on the main window and every page reads from it, so
a search on the Dashboard is immediately visible to the Website Scraper, the
Data Results grid and the outreach screens without any page-to-page plumbing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from PySide6.QtCore import QObject, Signal

from tui.models import Business

from . import services, settings_store


@dataclass
class Lead:
    """One business row, plus the bits of UI state that hang off it."""

    business: Business
    industry: str = ""
    selected: bool = False
    notes: str = ""
    call_status: str = ""  # "" | called | follow-up | not interested | won
    history: List[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        b = self.business
        return f"{b.name.strip().lower()}|{b.address.strip().lower()}"

    @property
    def data_points(self) -> int:
        b = self.business
        return (
            len(b.emails) + len(b.phones) + len(b.contact_names)
            + sum(int(v or 0) for v in b.insights.values())
        )


class AppState(QObject):
    """Everything the pages share, with signals for the things that change."""

    leads_changed = Signal()        # rows added / removed
    lead_updated = Signal(object)   # one Lead's data changed
    selection_changed = Signal()
    settings_changed = Signal()
    logged = Signal(str, str)       # (source, line) for the Logs page
    status_changed = Signal(str)    # sidebar status text

    def __init__(self) -> None:
        super().__init__()
        self.settings: Dict = settings_store.load()
        self.leads: List[Lead] = []
        self.log_lines: List[str] = []
        # Held in memory only, never written to disk.
        self._password: str = os.environ.get("EMAIL_PASSWORD", "")
        self.campaign_stats: Dict[str, int] = {
            "sent": 0, "delivered": 0, "opened": 0,
            "clicked": 0, "replied": 0, "bounced": 0,
        }
        self.started_at = datetime.now()

    # -- settings ---------------------------------------------------------
    def update_settings(self, **values) -> None:
        self.settings.update(values)
        settings_store.save(self.settings)
        self.settings_changed.emit()

    def make_pipeline(self):
        return services.make_pipeline(self.settings)

    @property
    def demo(self) -> bool:
        return bool(self.settings.get("demo_mode"))

    # -- credentials ------------------------------------------------------
    @property
    def password(self) -> str:
        if not self._password:
            # send_emails ships a tiny .env reader; reuse it rather than
            # inventing a second one.
            try:
                from send_emails import load_dotenv

                from . import runtime

                for candidate in runtime.env_files():
                    load_dotenv(str(candidate))
            except Exception:  # pragma: no cover - optional convenience
                pass
            self._password = os.environ.get("EMAIL_PASSWORD", "")
        return self._password

    @password.setter
    def password(self, value: str) -> None:
        self._password = value or ""

    # -- leads ------------------------------------------------------------
    def add_businesses(self, businesses: Iterable[Business], industry: str = "") -> List[Lead]:
        """Merge a batch of search results in, skipping ones already held."""
        known = {lead.key for lead in self.leads}
        added: List[Lead] = []
        for business in businesses:
            lead = Lead(business=business, industry=industry or business.search_term)
            if lead.key in known:
                continue
            known.add(lead.key)
            self.leads.append(lead)
            added.append(lead)
        if added:
            self.leads_changed.emit()
        return added

    def clear_leads(self) -> None:
        self.leads.clear()
        self.leads_changed.emit()
        self.selection_changed.emit()

    def industries(self) -> List[str]:
        """Industry tabs, in the order their first result arrived."""
        seen: List[str] = []
        for lead in self.leads:
            name = lead.industry or "Results"
            if name not in seen:
                seen.append(name)
        return seen

    def leads_for(self, industry: str = "") -> List[Lead]:
        if not industry:
            return list(self.leads)
        return [lead for lead in self.leads if (lead.industry or "Results") == industry]

    def selected_leads(self) -> List[Lead]:
        return [lead for lead in self.leads if lead.selected]

    def scanned_leads(self) -> List[Lead]:
        return [lead for lead in self.leads if lead.business.scanned]

    def emailable_leads(self) -> List[Lead]:
        return [lead for lead in self.leads if lead.business.has_email]

    def callable_leads(self) -> List[Lead]:
        """Leads worth ringing: a number, and no email already sent."""
        out = []
        for lead in self.leads:
            b = lead.business
            if (b.phones or b.phone) and not b.emailed:
                out.append(lead)
        return out

    def lead_by_key(self, key: str) -> Optional[Lead]:
        for lead in self.leads:
            if lead.key == key:
                return lead
        return None

    def set_selected(self, leads: Iterable[Lead], selected: bool) -> None:
        changed = False
        for lead in leads:
            if lead.selected != selected:
                lead.selected = selected
                changed = True
        if changed:
            self.selection_changed.emit()

    # -- logging ----------------------------------------------------------
    def log(self, source: str, line: str) -> None:
        stamped = f"{datetime.now():%H:%M:%S}  [{source}]  {line}"
        self.log_lines.append(stamped)
        # Keep the buffer bounded; a long scrape produces thousands of lines.
        if len(self.log_lines) > 5000:
            del self.log_lines[:1000]
        self.logged.emit(source, stamped)

    def set_status(self, text: str) -> None:
        self.status_changed.emit(text)
