"""Screen 2 — visit each selected website and pull the details off it."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox

from contact_scraper import INSIGHT_CATEGORIES

from .. import theme, services, runtime
from ..state import Lead
from ..widgets.common import (
    Card, DataTable, KeyValueRow, LogView, Pill, button, checkbox, hint,
    progress_bar, title,
)
from ..workers import JobRunner
from . import Page


class WebsiteScraperPage(Page):
    """Drives the contact scan and narrates it the way the mockup does."""

    navigate_requested = Signal(str)
    heading = "Website Scraper"

    def __init__(self, state, parent=None) -> None:
        super().__init__(state, parent)
        self.runner = JobRunner(self)
        self._targets: List[Lead] = []
        self._by_name: Dict[str, Lead] = {}
        self._started: Optional[datetime] = None
        self._completed = 0
        self._in_flight = 0
        self._data_points = 0
        self._current: Optional[Lead] = None
        self._phase = "scan"
        self._lookups_done = 0

        self.root().addWidget(title("2.  WEBSITE SCRAPER  —  SCRAPING WEBSITES FOR MORE INFO"))

        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(self._build_selected(), 3)
        top.addWidget(self._build_current(), 4)
        top.addWidget(self._build_overview(), 3)
        self.root().addLayout(top)

        middle = QHBoxLayout()
        middle.setSpacing(12)
        middle.addWidget(self._build_log(), 7)
        middle.addWidget(self._build_categories(), 3)
        self.root().addLayout(middle, 1)

        self.root().addWidget(self._build_preview(), 1)
        self.root().addLayout(self._build_controls())

        self.runner.message.connect(self._on_message)
        self.runner.event.connect(self._on_scan_event)
        self.runner.failed.connect(self._on_failed)
        self.runner.cancelled.connect(self._on_cancelled)
        self.runner.ended.connect(self._on_ended)

        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._tick)

    # -- construction ------------------------------------------------------
    def _build_selected(self) -> Card:
        card = Card("Selected Business")
        self.selected_name = QLabel("—")
        self.selected_name.setStyleSheet(f"font-weight: 700; color: {theme.INK};")
        self.selected_site = QLabel("")
        self.selected_site.setObjectName("Link")
        self.selected_site.setOpenExternalLinks(True)
        self.selected_site.setTextInteractionFlags(Qt.TextBrowserInteraction)
        card.add(self.selected_name)
        card.add(self.selected_site)
        card.add(hint("Selections come from the Dashboard's results table."))
        card.body().addStretch(1)
        return card

    def _build_current(self) -> Card:
        card = Card("Current Progress")
        self.current_label = QLabel("Scraping Website: —")
        self.current_label.setStyleSheet(f"color: {theme.INK_SOFT};")
        self.progress = progress_bar(blue=True)
        self.percent = QLabel("0%")
        self.percent.setStyleSheet(f"font-weight: 700; color: {theme.INK};")
        bar_row = QHBoxLayout()
        bar_row.setSpacing(8)
        bar_row.addWidget(self.progress, 1)
        bar_row.addWidget(self.percent)
        card.add(self.current_label)
        card.add_layout(bar_row)
        self.status_pill = Pill("Idle", "idle")
        pill_row = QHBoxLayout()
        pill_row.addWidget(self.status_pill)
        pill_row.addStretch(1)
        card.body().addLayout(pill_row)
        card.body().addStretch(1)
        return card

    def _build_overview(self) -> Card:
        card = Card("Live Progress Overview", spacing=2)
        self.ov_selected = KeyValueRow("Businesses Selected", 0)
        self.ov_completed = KeyValueRow("Websites Completed", 0)
        self.ov_progress = KeyValueRow("Websites In Progress", 0)
        self.ov_remaining = KeyValueRow("Websites Remaining", 0)
        self.ov_points = KeyValueRow("Total Data Points Found", 0)
        self.ov_start = KeyValueRow("Start Time", "—")
        self.ov_elapsed = KeyValueRow("Elapsed Time", "00:00:00")
        for widget in (self.ov_selected, self.ov_completed, self.ov_progress,
                       self.ov_remaining, self.ov_points, self.ov_start, self.ov_elapsed):
            card.add(widget)
        card.body().addStretch(1)
        return card

    def _build_log(self) -> Card:
        card = Card("Scraper Activity Log")
        self.log = LogView()
        self.log.setMinimumHeight(150)
        card.add(self.log, 1)
        return card

    def _build_categories(self) -> Card:
        card = Card("Data Categories", spacing=3)
        self.category_boxes: Dict[str, object] = {}
        self.category_counts: Dict[str, QLabel] = {}
        # Membership decides it: unticking everything is a deliberate choice
        # and must survive a restart. (The stored default lists them all.)
        enabled = set(self.state.settings.get("data_categories", []))
        for key, label in INSIGHT_CATEGORIES:
            box = checkbox(label, label in enabled)
            box.stateChanged.connect(self._save_categories)
            count = QLabel("")
            count.setStyleSheet(f"color: {theme.MUTED}; font-size: 11px;")
            count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            line = QHBoxLayout()
            line.setContentsMargins(0, 0, 0, 0)
            line.addWidget(box)
            line.addStretch(1)
            line.addWidget(count)
            card.body().addLayout(line)
            self.category_boxes[key] = box
            self.category_counts[key] = count
        card.body().addStretch(1)
        card.add(hint("Unticked categories are collected but hidden from the preview."))
        return card

    def _build_preview(self) -> Card:
        card = Card("Results Preview (Live)")
        self.preview = DataTable(["Field", "Data Found", "Category", "Count"],
                                 stretch_column=1)
        self.preview.setMinimumHeight(140)
        card.add(self.preview, 1)
        return card

    def _build_controls(self) -> QHBoxLayout:
        self.phone_lookup_box = checkbox(
            "Also look up missing phone numbers (Google + Yellow Pages)", False)
        self.start_button = button("▶  Start Scraping", "Primary")
        self.pause_button = button("❚❚  Pause")
        self.stop_button = button("✕  Stop", "Danger")
        self.next_button = button("Go to Data Results  →")
        self.start_button.clicked.connect(self.start)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.stop_button.clicked.connect(self.stop)
        self.next_button.clicked.connect(lambda: self.navigate_requested.emit("listings"))
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)

        line = QHBoxLayout()
        line.addWidget(self.phone_lookup_box)
        line.addStretch(1)
        for widget in (self.next_button, self.start_button,
                       self.pause_button, self.stop_button):
            line.addWidget(widget)
        return line

    # -- lifecycle ---------------------------------------------------------
    def on_show(self) -> None:
        if not self.runner.running:
            self._targets = self.state.selected_leads() or self.state.leads
            self._refresh_idle_state()

    def _refresh_idle_state(self) -> None:
        self.ov_selected.set_value(len(self._targets))
        self.ov_remaining.set_value(len(self._targets))
        first = self._targets[0] if self._targets else None
        self.selected_name.setText(first.business.name if first else "—")
        if first and first.business.website:
            url = first.business.website
            self.selected_site.setText(f'<a href="{url}" style="color:{theme.BLUE}">{url}</a>')
        else:
            self.selected_site.setText("")
        self.start_button.setEnabled(bool(self._targets))

    def _save_categories(self) -> None:
        labels = [
            label for key, label in INSIGHT_CATEGORIES
            if self.category_boxes[key].isChecked()
        ]
        self.state.settings["data_categories"] = labels
        self._refresh_preview()

    # -- running -----------------------------------------------------------
    def start(self) -> None:
        if self.runner.running:
            return
        self._targets = self.state.selected_leads() or self.state.leads
        if not self._targets:
            QMessageBox.information(
                self, "Nothing selected",
                "Run a search on the Dashboard and tick the businesses to scan.")
            return

        self._by_name = {lead.business.name: lead for lead in self._targets}
        self._phase = "scan"
        self._lookups_done = 0
        self._started = datetime.now()
        self._completed = 0
        self._in_flight = 0
        self._data_points = 0
        self.log.clear()
        self.preview.set_rows([])
        self.progress.setValue(0)
        self.percent.setText("0%")
        self.ov_start.set_value(f"{self._started:%I:%M:%S %p}")
        self.ov_selected.set_value(len(self._targets))
        self.ov_remaining.set_value(len(self._targets))
        self.ov_completed.set_value(0)
        self.ov_points.set_value(0)
        self._set_running(True)
        self.status_pill.set_state("Scraping", "busy")
        self.state.set_status("Scanning websites…")
        self._clock.start()

        pipeline = self.state.make_pipeline()
        businesses = [lead.business for lead in self._targets]
        want_phones = self.phone_lookup_box.isChecked()

        def job(progress, on_event):
            runtime.ensure_embedded_browser(progress)
            pipeline.scrape_contacts(businesses, progress=progress, on_event=on_event)
            if want_phones:
                progress("Looking up phone numbers for the sites that came up empty…")
                pipeline.find_phones(businesses, progress=progress, on_event=on_event)
            return len(businesses)

        self.runner.start(job)

    def toggle_pause(self) -> None:
        if not self.runner.running:
            return
        paused = self.runner.toggle_pause()
        self.pause_button.setText("▶  Resume" if paused else "❚❚  Pause")
        self.status_pill.set_state("Paused" if paused else "Scraping",
                                   "warn" if paused else "busy")
        self.state.set_status("Paused" if paused else "Scanning websites…")

    def stop(self) -> None:
        if self.runner.running:
            self.runner.stop()
            self.status_pill.set_state("Stopping", "warn")

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.pause_button.setEnabled(running)
        self.stop_button.setEnabled(running)
        self.phone_lookup_box.setEnabled(not running)
        if not running:
            self.pause_button.setText("❚❚  Pause")

    # -- job signals -------------------------------------------------------
    def _on_message(self, line: str) -> None:
        self.log.append(f"{datetime.now():%H:%M:%S}  {line}")
        self.state.log("scan", line)
        if line.startswith("Looking up phone numbers"):
            self._phase = "lookup"

    def _lead_for(self, event):
        """The lead an event belongs to.

        Scan events arrive in batch order, so the index identifies the lead
        exactly — which matters when two businesses share a name and the name
        alone would resolve to the wrong one.
        """
        index = getattr(event, "index", 0) - 1
        if self._phase == "scan" and 0 <= index < len(self._targets):
            return self._targets[index]
        return self._by_name.get(event.name)

    def _on_scan_event(self, event) -> None:
        total = max(1, getattr(event, "total", 1))
        lead = self._lead_for(event)
        if self._phase == "lookup":
            # Phone lookups run over a subset after the scan; counting them as
            # completed websites would push the bar past the batch size.
            if event.finished:
                self._lookups_done += 1
                self._data_points += len(event.phones)
                self.ov_points.set_value(self._data_points)
                if lead is not None:
                    self.state.lead_updated.emit(lead)
                self.current_label.setText(
                    f"Phone lookup: {self._lookups_done}/{total}")
            return

        if event.status == "scanning":
            self._in_flight = 1
            self._current = lead
            self.current_label.setText(f"Scraping Website: {event.website or event.name}")
            self.selected_name.setText(event.name)
            if event.website:
                self.selected_site.setText(
                    f'<a href="{event.website}" style="color:{theme.BLUE}">{event.website}</a>')
        else:
            self._in_flight = 0
            self._completed += 1
            self._data_points += event.data_points
            if lead is not None:
                self.state.lead_updated.emit(lead)


        percent = int(round(min(1.0, self._completed / total) * 100))
        self.progress.setValue(percent)
        self.percent.setText(f"{percent}%")
        self.ov_completed.set_value(self._completed)
        self.ov_progress.set_value(self._in_flight)
        self.ov_remaining.set_value(max(0, len(self._targets) - self._completed))
        self.ov_points.set_value(self._data_points)
        if event.finished and event.status != "skipped":
            self._refresh_preview(event)

    def _refresh_preview(self, event=None) -> None:
        """Show the current business's findings, field by field."""
        lead = self._current
        if event is not None:
            lead = self._lead_for(event) or lead
        if lead is None:
            return
        b = lead.business
        pairs = [
            ("Business Name", b.name),
            ("Website", b.website),
            ("Phone", ", ".join(b.phones) or b.phone),
            ("Email", ", ".join(b.emails)),
            ("Contact", ", ".join(b.contact_names)),
            ("Address", b.address),
        ]
        counts = [
            (label, b.insights.get(key, 0))
            for key, label in INSIGHT_CATEGORIES
            if self.category_boxes[key].isChecked()
        ]
        rows = []
        for index in range(max(len(pairs), len(counts))):
            field, value = pairs[index] if index < len(pairs) else ("", "")
            label, count = counts[index] if index < len(counts) else ("", "")
            rows.append([field, value, label, count])
        self.preview.set_rows(rows)
        for key, label in INSIGHT_CATEGORIES:
            found = b.insights.get(key, 0)
            self.category_counts[key].setText(str(found) if found else "")

    def _tick(self) -> None:
        if self._started is None:
            return
        elapsed = datetime.now() - self._started
        hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        self.ov_elapsed.set_value(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    def _on_failed(self, message: str) -> None:
        self.status_pill.set_state("Failed", "bad")
        self.state.log("scan", f"ERROR {message}")
        QMessageBox.critical(
            self, "Scan failed", f"{message}\n\n{services.explain_failure(message)}")

    def _on_cancelled(self) -> None:
        self.status_pill.set_state("Stopped", "warn")
        self.log.append("Stopped by user — everything scanned so far was saved.")

    def _on_ended(self) -> None:
        self._clock.stop()
        self._tick()
        self._set_running(False)
        if self.status_pill.text() not in {"Failed", "Stopped"}:
            self.status_pill.set_state("Completed", "good")
            self.progress.setValue(100)
            self.percent.setText("100%")
            self.current_label.setText("Scraping Website: done")
        self.state.set_status("Ready")
        self.state.leads_changed.emit()

    def on_close(self) -> None:
        if self.runner.running:
            self.runner.stop()
            self.runner.wait(4000)
