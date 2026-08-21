"""Screen 3 — the grids: raw Business Listings and extracted Data Results."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QMessageBox, QTabWidget, QVBoxLayout, QWidget,
)

from .. import services, theme
from ..state import AppState, Lead
from ..widgets.common import Card, DataTable, button, hint, search_box, title
from . import Page

PAGE_SIZES = ["25", "50", "100", "All"]

FILTERS = [
    ("All businesses", lambda lead: True),
    ("Has email", lambda lead: lead.business.has_email),
    ("Has phone", lambda lead: bool(lead.business.phones or lead.business.phone)),
    ("Missing contact info", lambda lead: not lead.business.has_contact_info),
    ("Scanned", lambda lead: lead.business.scanned),
    ("Not scanned", lambda lead: not lead.business.scanned),
    ("Emailed", lambda lead: lead.business.emailed),
    ("Not emailed", lambda lead: not lead.business.emailed),
]


class TablePanel(QWidget):
    """A searchable, filterable, paginated grid over the shared lead list."""

    def __init__(self, state: AppState, headers: Sequence[str],
                 row_builder: Callable[[Lead], List], *, export_prefix: str,
                 checkable: bool = True, stretch_column: int = 0,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self.headers = list(headers)
        self.row_builder = row_builder
        self.export_prefix = export_prefix
        self._page = 0
        self._visible: List[Lead] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        card = Card()
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.search = search_box("Search results…")
        self.search.textChanged.connect(self._on_filter_changed)
        self.filter = QComboBox()
        self.filter.addItems([label for label, _fn in FILTERS])
        self.filter.currentIndexChanged.connect(self._on_filter_changed)
        self.page_size = QComboBox()
        self.page_size.addItems(PAGE_SIZES)
        self.page_size.setCurrentText("50")
        self.page_size.currentIndexChanged.connect(self._on_filter_changed)
        controls.addWidget(self.search, 3)
        controls.addWidget(self.filter, 1)
        controls.addWidget(self.page_size)
        controls.addStretch(1)
        self.export_csv_button = button("Export Results (CSV)")
        self.export_xlsx_button = button("Export to Excel")
        self.export_csv_button.clicked.connect(lambda: self.export("csv"))
        self.export_xlsx_button.clicked.connect(lambda: self.export("xlsx"))
        controls.addWidget(self.export_csv_button)
        controls.addWidget(self.export_xlsx_button)
        card.add_layout(controls)

        self.table = DataTable(self.headers, checkable=checkable,
                               stretch_column=stretch_column)
        self.table.selection_toggled.connect(self._sync_selection)
        card.add(self.table, 1)

        footer = QHBoxLayout()
        self.count_label = hint("No results yet", wrap=False)
        self.select_all_button = button("Select All")
        self.select_none_button = button("Select None")
        self.prev_button = button("‹  Prev")
        self.page_label = hint("1", wrap=False)
        self.next_button = button("Next  ›")
        self.select_all_button.clicked.connect(lambda: self._set_all(True))
        self.select_none_button.clicked.connect(lambda: self._set_all(False))
        self.prev_button.clicked.connect(lambda: self.go_page(self._page - 1))
        self.next_button.clicked.connect(lambda: self.go_page(self._page + 1))
        footer.addWidget(self.count_label)
        footer.addStretch(1)
        footer.addWidget(self.select_all_button)
        footer.addWidget(self.select_none_button)
        footer.addSpacing(12)
        footer.addWidget(self.prev_button)
        footer.addWidget(self.page_label)
        footer.addWidget(self.next_button)
        card.add_layout(footer)

        layout.addWidget(card, 1)
        state.leads_changed.connect(self.refresh)
        state.lead_updated.connect(lambda _lead: self.refresh())

    # -- data --------------------------------------------------------------
    def matching(self) -> List[Lead]:
        needle = self.search.text().strip().lower()
        predicate = FILTERS[max(0, self.filter.currentIndex())][1]
        out = []
        for lead in self.state.leads:
            if not predicate(lead):
                continue
            if needle:
                b = lead.business
                haystack = " ".join([
                    b.name, b.category, b.address, b.website, b.phone,
                    " ".join(b.emails), " ".join(b.phones), " ".join(b.contact_names),
                    lead.industry,
                ]).lower()
                if needle not in haystack:
                    continue
            out.append(lead)
        return out

    def page_size_value(self) -> int:
        text = self.page_size.currentText()
        return 10 ** 6 if text == "All" else int(text)

    def refresh(self) -> None:
        matched = self.matching()
        size = self.page_size_value()
        pages = max(1, -(-len(matched) // size))
        self._page = min(self._page, pages - 1)
        start = self._page * size
        self._visible = matched[start:start + size]

        rows = [self.row_builder(lead) for lead in self._visible]
        self.table.set_rows(rows, checked=[lead.selected for lead in self._visible])
        for index, lead in enumerate(self._visible):
            if lead.business.emailed:
                self.table.tint_row(index, theme.GREEN_SOFT)

        first = start + 1 if matched else 0
        last = start + len(self._visible)
        self.count_label.setText(
            f"Showing {first} to {last} of {len(matched)} results"
            if matched else "No results match this filter"
        )
        self.page_label.setText(f"{self._page + 1} / {pages}")
        self.prev_button.setEnabled(self._page > 0)
        self.next_button.setEnabled(self._page < pages - 1)
        for widget in (self.export_csv_button, self.export_xlsx_button):
            widget.setEnabled(bool(matched))

    def go_page(self, page: int) -> None:
        self._page = max(0, page)
        self.refresh()

    def _on_filter_changed(self, *_args) -> None:
        self._page = 0
        self.refresh()

    def _sync_selection(self) -> None:
        checked = set(self.table.checked_rows())
        for index, lead in enumerate(self._visible):
            lead.selected = index in checked
        self.state.selection_changed.emit()

    def _set_all(self, selected: bool) -> None:
        self.state.set_selected(self.matching(), selected)
        self.table.set_all_checked(selected)

    # -- export ------------------------------------------------------------
    def export(self, fmt: str) -> None:
        matched = self.matching()
        if not matched:
            return
        suggested = services.default_export_dir(self.state.settings) / \
            services.suggested_filename(self.export_prefix, fmt)
        label = "CSV files (*.csv)" if fmt == "csv" else "Excel workbook (*.xlsx)"
        path, _filter = QFileDialog.getSaveFileName(
            self, f"Export {self.export_prefix}", str(suggested), label)
        if not path:
            return
        rows = [self.row_builder(lead) for lead in matched]
        writer = services.export_csv if fmt == "csv" else services.export_xlsx
        writer(Path(path), self.headers, rows)
        self.state.log("export", f"Exported {len(rows)} row(s) → {path}")
        QMessageBox.information(self, "Exported", f"Saved {len(rows)} rows to\n{path}")


def _listing_row(lead: Lead) -> List:
    b = lead.business
    if b.emailed:
        status = "Emailed"
    elif b.scanned:
        status = "Scanned"
    else:
        status = "New"
    return [b.name, b.category, b.phone, b.website, b.rating,
            b.reviews_count, b.address, lead.industry, status]


def _result_row(lead: Lead) -> List:
    b = lead.business
    return [
        b.name,
        b.website,
        ", ".join(b.phones) or b.phone,
        ", ".join(b.emails),
        ", ".join(b.contact_names),
        b.address,
        b.insights.get("services", 0),
        b.insights.get("images", 0),
        b.rating,
        " | ".join(b.social_links),
    ]


class ListingsPage(Page):
    """Business Listings and Data Results, side by side as tabs."""

    navigate_requested = Signal(str)
    heading = "Business Listings"

    def __init__(self, state, parent=None) -> None:
        super().__init__(state, parent)
        self.root().addWidget(title("3.  DATA RESULTS  —  EXTRACTED INFORMATION"))

        self.tabs = QTabWidget()
        self.listings = TablePanel(
            state,
            ["Business Name", "Category", "Phone", "Website", "Rating",
             "Reviews", "Address", "Industry", "Status"],
            _listing_row, export_prefix="listings", stretch_column=6,
        )
        self.results = TablePanel(
            state,
            ["Business Name", "Website", "Phone", "Email", "Contact",
             "Address", "Services", "Images", "Rating", "Social Links"],
            _result_row, export_prefix="data_results", stretch_column=5,
        )
        self.tabs.addTab(self.listings, "Business Listings")
        self.tabs.addTab(self.results, "Data Results")
        self.root().addWidget(self.tabs, 1)

        footer = QHBoxLayout()
        footer.addWidget(hint(
            "Ticked rows carry over to the Website Scraper and to email campaigns."))
        footer.addStretch(1)
        scan_button = button("Scan Selected Websites  →")
        outreach_button = button("Start Outreach  →", "Primary")
        scan_button.clicked.connect(lambda: self.navigate_requested.emit("scraper"))
        outreach_button.clicked.connect(lambda: self.navigate_requested.emit("outreach"))
        footer.addWidget(scan_button)
        footer.addWidget(outreach_button)
        self.root().addLayout(footer)

    def on_show(self) -> None:
        self.listings.refresh()
        self.results.refresh()
