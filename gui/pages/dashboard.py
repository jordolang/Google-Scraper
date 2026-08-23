"""Screen 1 — find and scrape Google Maps listings."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLineEdit, QMessageBox, QTabBar,
    QVBoxLayout,
)

from licensing import get_manager, plans

from .. import services, theme, runtime
from ..licensing_ui import cap_notice, require
from ..state import Lead
from ..widgets.common import (
    Card, DataTable, Field, Pill, Stat, button, hint, progress_bar, title,
)
from ..workers import JobRunner
from . import Page

RADIUS_CHOICES = ["5 miles", "10 miles", "25 miles", "50 miles", "100 miles"]
RESULT_CHOICES = ["10", "25", "50", "100", "200"]
HEADERS = ["#", "Business Name", "Category", "Phone", "Website", "Rating", "Reviews", "Address"]

# The pipeline streams "[3/50] Acme Roofing" lines; that is the progress signal.
_COUNTER = re.compile(r"\[(\d+)\s*/\s*(\d+)\]")


class DashboardPage(Page):
    """Runs the Maps search and shows what came back, one tab per industry."""

    navigate_requested = Signal(str)
    heading = "Dashboard"

    def __init__(self, state, parent=None) -> None:
        super().__init__(state, parent)
        self.runner = JobRunner(self)
        self._industry_of_tab: List[str] = []
        self._rows: List[Lead] = []
        self._industry_progress: Dict[str, float] = {}
        self._planned: List[str] = []
        # Which industry the running job is on, so a "[3/50]" line can be
        # attributed to the right progress bucket.
        self._current_term = ""

        self.root().addWidget(title("1.  FIND & SCRAPE GOOGLE MAPS LISTINGS"))
        self.root().addWidget(self._build_form())
        self.root().addWidget(self._build_status())
        self.root().addWidget(self._build_results(), 1)

        self.runner.message.connect(self._on_message)
        self.runner.event.connect(self._on_event)
        self.runner.failed.connect(self._on_failed)
        self.runner.cancelled.connect(self._on_cancelled)
        self.runner.ended.connect(self._on_ended)
        state.leads_changed.connect(self.refresh)
        state.selection_changed.connect(self._update_footer)
        self._load_settings()

    # -- construction ------------------------------------------------------
    def _build_form(self) -> Card:
        card = Card()
        self.location = QLineEdit()
        self.location.setPlaceholderText("Columbus, Ohio, USA")

        self.industry = QComboBox()
        self.industry.setEditable(True)
        self.industry.setInsertPolicy(QComboBox.NoInsert)
        self.industry.setMinimumWidth(220)
        self.industry.addItems([
            "Roofing Contractors", "Plumbers", "Electricians", "HVAC Services",
            "Landscaping", "Dentists", "Accountants", "Auto Repair",
        ])
        self.industry.setToolTip(
            "One keyword, or several separated by commas — each becomes its own tab."
        )

        self.radius = QComboBox()
        self.radius.addItems(RADIUS_CHOICES)
        self.radius.setCurrentText("25 miles")
        self.radius.setToolTip(
            "Recorded with the run, for your own reference. Google Maps has no "
            "radius filter — it ranks results by distance from the location "
            "you type, so this does not change what is scraped."
        )

        self.max_results = QComboBox()
        self.max_results.setEditable(True)
        self.max_results.addItems(RESULT_CHOICES)
        self.max_results.setCurrentText("50")
        self.max_results.setToolTip("Stop after this many listings per industry.")

        self.start_button = button("▶  Start Scraping", "Primary")
        self.start_button.setMinimumHeight(32)
        self.start_button.clicked.connect(self.start)

        self.stop_button = button("■  Stop", "Danger")
        self.stop_button.setMinimumHeight(32)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop)

        line = QHBoxLayout()
        line.setSpacing(12)
        line.addWidget(Field("Location / City", self.location), 3)
        line.addWidget(Field("Industry / Keyword", self.industry), 3)
        line.addWidget(Field("Radius", self.radius), 1)
        line.addWidget(Field("Max Results per Industry", self.max_results), 1)

        buttons = QVBoxLayout()
        buttons.setSpacing(4)
        buttons.addSpacing(15)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(self.start_button)
        row.addWidget(self.stop_button)
        buttons.addLayout(row)
        line.addLayout(buttons)
        card.add_layout(line)
        return card

    def _build_status(self) -> Card:
        card = Card()
        self.status_pill = Pill("Ready", "idle")
        self.stat_status = Stat("Status", "Idle", green=True)
        self.stat_industries = Stat("Total Industries", "0")
        self.stat_found = Stat("Total Businesses Found", "0")

        self.progress = progress_bar()
        self.progress_label = Stat("Progress", "0%")
        progress_box = QVBoxLayout()
        progress_box.setSpacing(4)
        progress_box.addWidget(self.progress_label)
        progress_box.addWidget(self.progress)

        line = QHBoxLayout()
        line.setSpacing(24)
        line.addWidget(self.stat_status, 2)
        line.addWidget(self.stat_industries, 1)
        line.addWidget(self.stat_found, 2)
        line.addLayout(progress_box, 4)
        card.add_layout(line)
        return card

    def _build_results(self) -> Card:
        card = Card()
        self.tabs = QTabBar()
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        self.tabs.currentChanged.connect(lambda _i: self.refresh_table())
        card.add(self.tabs)

        self.table = DataTable(HEADERS, checkable=True, stretch_column=7)
        self.table.selection_toggled.connect(self._sync_selection_from_table)
        card.add(self.table, 1)

        self.count_label = hint("Showing 0 of 0 results", wrap=False)
        self.select_all_button = button("Select All")
        self.select_none_button = button("Select None")
        self.export_button = button("Export All (CSV)")
        self.next_button = button("Go to Website Scraper  →", "Primary")
        self.select_all_button.clicked.connect(lambda: self._set_all(True))
        self.select_none_button.clicked.connect(lambda: self._set_all(False))
        self.export_button.clicked.connect(self.export_csv)
        self.next_button.clicked.connect(self._go_to_scraper)

        footer = QHBoxLayout()
        footer.addWidget(self.count_label)
        footer.addStretch(1)
        for widget in (self.select_all_button, self.select_none_button,
                       self.export_button, self.next_button):
            footer.addWidget(widget)
        card.add_layout(footer)
        return card

    # -- settings ----------------------------------------------------------
    def _load_settings(self) -> None:
        settings = self.state.settings
        self.location.setText(str(settings.get("location", "")))
        self.industry.setCurrentText(str(settings.get("industries", "")))
        # Show the start of a long list rather than its tail.
        self.industry.lineEdit().setCursorPosition(0)
        self.radius.setCurrentText(f"{settings.get('radius_miles', 25)} miles")
        self.max_results.setCurrentText(str(settings.get("max_results", 50)))

    def _save_settings(self) -> None:
        radius = int(re.sub(r"\D", "", self.radius.currentText()) or 25)
        try:
            cap = max(1, int(self.max_results.currentText().strip()))
        except ValueError:
            cap = 50
        self.state.update_settings(
            location=self.location.text().strip(),
            industries=self.industry.currentText().strip(),
            radius_miles=radius,
            max_results=cap,
        )

    # -- running -----------------------------------------------------------
    def start(self) -> None:
        if self.runner.running:
            return
        terms = services.split_industries(self.industry.currentText())
        if not terms:
            QMessageBox.warning(self, "Nothing to search",
                                "Enter at least one industry or keyword.")
            return
        if not require(self, plans.SCRAPE_MAPS, action="Searching Google Maps"):
            return
        self._save_settings()

        # The licence caps two things here: how many industries run in one
        # batch, and how many results each returns. Both are clipped rather
        # than refused — a Solo licence asked for six industries should run the
        # two it has, not nothing.
        manager = get_manager()
        allowed_terms = manager.max_industries(len(terms))
        if allowed_terms < len(terms):
            cap_notice(self, len(terms), allowed_terms, "industries")
            terms = terms[:allowed_terms]

        location = self.location.text().strip()
        requested = int(self.state.settings.get("max_results", 50))
        cap = manager.max_results(requested)
        if cap < requested:
            cap_notice(self, requested, cap, "results")
        scrolls = services.scroll_budget(cap)
        pipeline = self.state.make_pipeline()
        demo = self.state.demo

        self._planned = terms
        self._industry_progress = {term: 0.0 for term in terms}
        self.progress.setValue(0)
        self.progress_label.set_value("0%")
        self.stat_industries.set_value(len(terms))
        self._set_running(True)
        self.stat_status.set_value("Scraping…")
        self.status_pill.set_state("Scraping", "busy")
        self.state.set_status("Scraping…")
        self.state.log("search", f"Searching {len(terms)} industry(ies) near {location or 'anywhere'}")

        def job(progress, on_event):
            runtime.ensure_embedded_browser(progress)
            for term in terms:
                on_event(("industry-start", term, None))
                progress(f"── {term} ──")
                # Deliver each listing as it is opened rather than waiting for
                # the whole industry: the table fills as the run goes, and a
                # Stop keeps everything already found instead of throwing the
                # industry away.
                # The cap is applied by the pipeline itself, so the CSV it
                # exports matches what the table shows.
                found = pipeline.search(
                    term, location, max_scrolls=scrolls, progress=progress,
                    on_business=lambda business, t=term: on_event(
                        ("business", t, business)),
                )
                on_event(("industry-done", term, found))
            return {"industries": len(terms), "demo": demo}

        self.runner.start(job)

    def stop(self) -> None:
        if self.runner.running:
            self.runner.stop()
            self.stat_status.set_value("Stopping…")
            self.state.log("search", "Stop requested — finishing the current listing.")

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        for widget in (self.location, self.industry, self.radius, self.max_results):
            widget.setEnabled(not running)

    # -- job signals -------------------------------------------------------
    def _on_message(self, line: str) -> None:
        self.state.log("search", line)
        match = _COUNTER.search(line)
        if match and self._current_term:
            done, total = int(match.group(1)), max(1, int(match.group(2)))
            self._industry_progress[self._current_term] = min(1.0, done / total)
            self._paint_progress()

    def _on_event(self, payload) -> None:
        kind, term, data = payload
        if kind == "industry-start":
            self._current_term = term
            self.stat_status.set_value(f"Scraping {term}…")
        elif kind == "business":
            # One listing, straight off the browser. The pipeline already caps
            # each search, and add_businesses de-duplicates, so the
            # industry-done sweep below cannot double these up.
            self.state.add_businesses([data], term)
            self._paint_progress()
        elif kind == "industry-done":
            self._industry_progress[term] = 1.0
            self.state.add_businesses(data or [], term)
            self._paint_progress()
            self.state.log("search", f"{term}: {len(data or [])} listing(s)")


    def _paint_progress(self) -> None:
        if not self._industry_progress:
            return
        share = sum(self._industry_progress.values()) / len(self._industry_progress)
        percent = int(round(share * 100))
        self.progress.setValue(percent)
        self.progress_label.set_value(f"{percent}%")
        self.stat_found.set_value(f"{len(self.state.leads)}")

    def _on_failed(self, message: str) -> None:
        self.stat_status.set_value("Failed")
        self.stat_status.set_green(False)
        self.status_pill.set_state("Failed", "bad")
        self.state.log("search", f"ERROR {message}")
        self.state.set_status("Scrape failed")
        QMessageBox.critical(
            self, "Scrape failed", f"{message}\n\n{services.explain_failure(message)}")

    def _on_cancelled(self) -> None:
        self.stat_status.set_value("Stopped")
        self.status_pill.set_state("Stopped", "warn")
        self.state.log(
            "search",
            f"Scrape stopped by user — kept {len(self.state.leads)} listing(s), "
            "already written to CSV.",
        )

    def _on_ended(self) -> None:
        self._set_running(False)
        if self.stat_status.value.text() not in {"Failed", "Stopped"}:
            self.stat_status.set_value("Scraping Completed")
            self.stat_status.set_green(True)
            self.status_pill.set_state("Completed", "good")
            self.progress.setValue(100)
            self.progress_label.set_value("100%")
        self.state.set_status("Ready")
        self.refresh()

    # -- table -------------------------------------------------------------
    def refresh(self) -> None:
        current = self.tabs.tabText(self.tabs.currentIndex()) if self.tabs.count() else ""
        industries = self.state.industries()
        if industries != self._industry_of_tab:
            self.tabs.blockSignals(True)
            while self.tabs.count():
                self.tabs.removeTab(0)
            for name in industries:
                self.tabs.addTab(name)
            self._industry_of_tab = industries
            if current in industries:
                self.tabs.setCurrentIndex(industries.index(current))
            self.tabs.blockSignals(False)
        self.stat_industries.set_value(len(industries) or len(self._planned))
        self.stat_found.set_value(len(self.state.leads))
        self.refresh_table()

    def refresh_table(self) -> None:
        index = self.tabs.currentIndex()
        industry = self._industry_of_tab[index] if 0 <= index < len(self._industry_of_tab) else ""
        self._rows = self.state.leads_for(industry)
        rows = []
        for position, lead in enumerate(self._rows, 1):
            b = lead.business
            rows.append([
                position, b.name, b.category, b.phone, b.website,
                b.rating, b.reviews_count, b.address,
            ])
        self.table.set_rows(rows, checked=[lead.selected for lead in self._rows])
        for position, lead in enumerate(self._rows):
            if lead.business.emailed:
                self.table.tint_row(position, theme.GREEN_SOFT)
        self._update_footer()

    def _sync_selection_from_table(self) -> None:
        checked = set(self.table.checked_rows())
        for position, lead in enumerate(self._rows):
            lead.selected = position in checked
        self.state.selection_changed.emit()

    def _set_all(self, selected: bool) -> None:
        self.state.set_selected(self._rows, selected)
        self.table.set_all_checked(selected)

    def _update_footer(self) -> None:
        total = len(self._rows)
        selected = len(self.state.selected_leads())
        shown = f"Showing 1 to {total} of {total} results" if total else "No results yet"
        self.count_label.setText(shown)
        self.next_button.setText(f"Go to Website Scraper ({selected} Selected)  →")
        self.next_button.setEnabled(selected > 0)
        self.export_button.setEnabled(bool(self.state.leads))

    # -- actions -----------------------------------------------------------
    def export_csv(self) -> None:
        if not self.state.leads:
            return
        suggested = services.default_export_dir(self.state.settings) / \
            services.suggested_filename("listings", "csv")
        path, _filter = QFileDialog.getSaveFileName(
            self, "Export listings", str(suggested), "CSV files (*.csv)")
        if not path:
            return
        rows = []
        for lead in self.state.leads:
            b = lead.business
            rows.append([
                b.name, b.category, b.phone, b.website, b.rating,
                b.reviews_count, b.address, lead.industry, b.search_location, b.url,
            ])
        services.export_csv(
            Path(path),
            ["Business Name", "Category", "Phone", "Website", "Rating",
             "Reviews", "Address", "Industry", "Location", "Maps URL"],
            rows,
        )
        self.state.log("export", f"Exported {len(rows)} listing(s) → {path}")
        QMessageBox.information(self, "Exported", f"Saved {len(rows)} listings to\n{path}")

    def _go_to_scraper(self) -> None:
        if not self.state.selected_leads():
            QMessageBox.information(self, "Nothing selected",
                                    "Tick the businesses you want scraped first.")
            return
        self.navigate_requested.emit("scraper")

    def on_show(self) -> None:
        self.refresh()

    def on_close(self) -> None:
        if self.runner.running:
            self.runner.stop()
            self.runner.wait(4000)
