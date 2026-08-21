"""Screens 4 and 5 — outreach: email campaigns and the call assistant."""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QHBoxLayout, QInputDialog, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QSpinBox, QSplitter,
    QTabWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from .. import services, theme
from ..scripts import ObjectionCard, ScriptStep, objection_cards, script_steps
from ..state import AppState, Lead
from ..widgets.common import (
    Card, DataTable, Field, KeyValueRow, LogView, Stat, button, hint, h_line,
    progress_bar, section_heading, title,
)
from ..workers import JobRunner
from . import Page

SEND_METHODS = ["SMTP (send for real)", "Dry run (compose only, nothing sent)"]
CALL_OUTCOMES = ["Interested — follow up", "Not interested", "Voicemail",
                 "Wrong number", "Call back later", "Won the job"]


# ===========================================================================
#  Tab 1 — Outreach Dashboard
# ===========================================================================
class OutreachDashboard(QWidget):
    """Where the pipeline stands, and what to do next."""

    navigate_requested = Signal(str)

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        tiles = Card()
        self.tile_total = Stat("Total Leads", "0")
        self.tile_email = Stat("With Email", "0")
        self.tile_phone = Stat("With Phone", "0")
        self.tile_emailed = Stat("Already Emailed", "0", green=True)
        self.tile_to_call = Stat("Call Queue", "0")
        line = QHBoxLayout()
        line.setSpacing(28)
        for tile in (self.tile_total, self.tile_email, self.tile_phone,
                     self.tile_emailed, self.tile_to_call):
            line.addWidget(tile)
        line.addStretch(1)
        tiles.add_layout(line)
        layout.addWidget(tiles)

        split = QHBoxLayout()
        split.setSpacing(12)

        next_card = Card("Next Steps")
        for label, key, note in (
            ("Find more businesses", "dashboard",
             "Search Google Maps for another industry or city."),
            ("Scan websites for contact details", "scraper",
             "Turn listings into emails, names and phone numbers."),
            ("Review the extracted data", "listings",
             "Filter, search and export what has been collected."),
        ):
            btn = button(label)
            btn.clicked.connect(lambda _c=False, k=key: self.navigate_requested.emit(k))
            next_card.add(btn)
            next_card.add(hint(note))
        next_card.body().addStretch(1)
        split.addWidget(next_card, 2)

        activity = Card("Recent Outreach Activity")
        self.activity = LogView(max_lines=400)
        activity.add(self.activity, 1)
        split.addWidget(activity, 3)
        layout.addLayout(split, 1)

        state.leads_changed.connect(self.refresh)
        state.logged.connect(self._on_logged)

    def _on_logged(self, source: str, line: str) -> None:
        if source in {"email", "call", "export"}:
            self.activity.append(line)

    def refresh(self) -> None:
        leads = self.state.leads
        self.tile_total.set_value(len(leads))
        self.tile_email.set_value(sum(1 for lead in leads if lead.business.has_email))
        self.tile_phone.set_value(
            sum(1 for lead in leads if lead.business.phones or lead.business.phone))
        self.tile_emailed.set_value(sum(1 for lead in leads if lead.business.emailed))
        self.tile_to_call.set_value(len(self.state.callable_leads()))


# ===========================================================================
#  Tab 2 — Email Campaigns
# ===========================================================================
class EmailCampaigns(QWidget):
    """Compose from the industry templates and send over SMTP."""

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self.runner = JobRunner(self)
        self._recipients: List[Lead] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._build_setup(), 3)
        body.addWidget(self._build_recipients(), 5)
        layout.addLayout(body, 1)
        layout.addWidget(self._build_stats())

        self.runner.message.connect(self._on_message)
        self.runner.finished.connect(self._on_finished)
        self.runner.failed.connect(self._on_failed)
        self.runner.cancelled.connect(lambda: self.state.log("email", "Send stopped."))
        self.runner.ended.connect(lambda: self._set_running(False))
        state.leads_changed.connect(self.refresh)
        state.selection_changed.connect(self.refresh)

    # -- left column -------------------------------------------------------
    def _build_setup(self) -> Card:
        card = Card("4.  OUTREACH SETUP")
        settings = self.state.settings

        self.campaign_name = QLineEdit(str(settings.get("campaign_name", "")))
        self.from_email = QLineEdit(str(settings.get("from_email", "")))
        self.reply_to = QLineEdit(str(settings.get("reply_to", "")))
        self.subject = QLineEdit()
        self.subject.setPlaceholderText("Auto — generated per business")
        self.subject.setToolTip(
            "Leave blank to use the per-business subject the generator writes.")

        self.template = QComboBox()
        self.template.addItem("Auto — match each business's industry", "")
        for label, key in services.available_templates():
            self.template.addItem(label, key)
        self.edit_template_button = button("Edit Template…")
        self.edit_template_button.clicked.connect(self._edit_template)

        self.send_method = QComboBox()
        self.send_method.addItems(SEND_METHODS)
        self.send_method.setCurrentIndex(1 if settings.get("dry_run", True) else 0)

        self.delay = QDoubleSpinBox()
        self.delay.setDecimals(0)
        self.delay.setRange(0.0, 600.0)
        self.delay.setSuffix(" seconds")
        self.delay.setValue(float(settings.get("email_delay", 30.0)))
        self.delay.setToolTip("Pause between messages; keeps you under provider rate limits.")

        self.daily_limit = QSpinBox()
        self.daily_limit.setRange(1, 5000)
        self.daily_limit.setValue(int(settings.get("daily_limit", 50)))
        self.daily_limit.setSuffix(" emails/day")

        for label, widget in (
            ("Campaign Name", self.campaign_name),
            ("From Email", self.from_email),
            ("Reply To", self.reply_to),
            ("Subject Line", self.subject),
            ("Email Template", self.template),
        ):
            card.add(Field(label, widget))
        card.add(self.edit_template_button)
        card.add(h_line())
        card.add(section_heading("Send Options"))
        for label, widget in (
            ("Send Method", self.send_method),
            ("Delay Between Emails", self.delay),
            ("Daily Send Limit", self.daily_limit),
        ):
            card.add(Field(label, widget))

        self.preview_button = button("Preview Email")
        self.preview_button.clicked.connect(self.preview)
        card.add(self.preview_button)
        card.body().addStretch(1)
        return card

    # -- right column ------------------------------------------------------
    def _build_recipients(self) -> Card:
        card = Card("Recipients")
        self.recipient_count = hint("0 selected", wrap=False)
        card.add(self.recipient_count)

        self.table = DataTable(
            ["Business Name", "Email", "Contact", "Website", "Industry"],
            checkable=True, stretch_column=3)
        self.table.selection_toggled.connect(self._sync_selection)
        card.add(self.table, 1)

        self.total_label = hint("Total Leads: 0", wrap=False)
        self.select_all_button = button("Select All")
        self.select_none_button = button("Select None")
        self.import_button = button("Import Leads…")
        self.send_button = button("✉  Send Emails", "Primary")
        self.stop_button = button("■  Stop", "Danger")
        self.stop_button.setEnabled(False)
        self.select_all_button.clicked.connect(lambda: self._set_all(True))
        self.select_none_button.clicked.connect(lambda: self._set_all(False))
        self.import_button.clicked.connect(self.import_leads)
        self.send_button.clicked.connect(self.send)
        self.stop_button.clicked.connect(lambda: self.runner.stop())

        controls = QHBoxLayout()
        controls.addWidget(self.total_label)
        controls.addStretch(1)
        for widget in (self.select_all_button, self.select_none_button,
                       self.import_button, self.send_button, self.stop_button):
            controls.addWidget(widget)
        card.add_layout(controls)

        self.progress = progress_bar(blue=True)
        self.progress.setVisible(False)
        card.add(self.progress)
        return card

    def _build_stats(self) -> Card:
        card = Card("Campaign Stats")
        self.stat_widgets: Dict[str, Stat] = {}
        line = QHBoxLayout()
        line.setSpacing(28)
        tracked = {"sent", "delivered", "bounced"}
        for key, label in (("sent", "✉ Sent"), ("delivered", "✓ Delivered"),
                           ("opened", "👁 Opened"), ("clicked", "↗ Clicked"),
                           ("replied", "↩ Replied"), ("bounced", "⚠ Bounced")):
            stat = Stat(label, "0" if key in tracked else "—")
            if key not in tracked:
                stat.setToolTip(
                    "Opens, clicks and replies need a tracking provider "
                    "(SendGrid, Mailgun, …). Direct SMTP cannot report them.")
            line.addWidget(stat)
            self.stat_widgets[key] = stat
        line.addStretch(1)
        card.add_layout(line)
        return card

    # -- data --------------------------------------------------------------
    def refresh(self) -> None:
        pool = [lead for lead in self.state.leads if lead.business.has_email]
        self._recipients = pool
        rows = []
        for lead in pool:
            b = lead.business
            rows.append([b.name, b.primary_email, ", ".join(b.contact_names),
                         b.website, lead.industry])
        self.table.set_rows(rows, checked=[lead.selected for lead in pool])
        for index, lead in enumerate(pool):
            if lead.business.emailed:
                self.table.tint_row(index, theme.GREEN_SOFT)
        chosen = [lead for lead in pool if lead.selected]
        self.recipient_count.setText(f"{len(chosen)} selected")
        self.total_label.setText(f"Total Leads: {len(pool)}")
        self.send_button.setEnabled(bool(chosen) and not self.runner.running)
        self.preview_button.setEnabled(bool(chosen))
        for key, value in self.state.campaign_stats.items():
            if key in self.stat_widgets and self.stat_widgets[key].value.text() != "—":
                self.stat_widgets[key].set_value(value)

    def _sync_selection(self) -> None:
        checked = set(self.table.checked_rows())
        for index, lead in enumerate(self._recipients):
            lead.selected = index in checked
        self.state.selection_changed.emit()

    def _set_all(self, selected: bool) -> None:
        self.state.set_selected(self._recipients, selected)
        self.table.set_all_checked(selected)

    def chosen(self) -> List[Lead]:
        return [lead for lead in self._recipients if lead.selected]

    # -- actions -----------------------------------------------------------
    def _save_settings(self) -> None:
        self.state.update_settings(
            campaign_name=self.campaign_name.text().strip(),
            from_email=self.from_email.text().strip(),
            reply_to=self.reply_to.text().strip(),
            email_delay=float(self.delay.value()),
            daily_limit=int(self.daily_limit.value()),
            dry_run=self.send_method.currentIndex() == 1,
        )

    def _build_message(self, lead: Lead, pipeline):
        message = pipeline.build_message(
            lead.business, industry_key=self.template.currentData() or None)
        subject = self.subject.text().strip()
        if subject:
            message.subject = subject.replace("{business}", lead.business.name)
        return message

    def preview(self) -> None:
        chosen = self.chosen()
        if not chosen:
            return
        self._save_settings()
        try:
            message = self._build_message(chosen[0], self.state.make_pipeline())
        except Exception as exc:  # noqa: BLE001 - templates are user-editable
            QMessageBox.critical(self, "Preview failed", str(exc))
            return
        path = Path(tempfile.gettempdir()) / "llsp_email_preview.html"
        path.write_text(message.html, encoding="utf-8")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        self.state.log("email", f"Previewed “{message.subject}” for {message.business.name}")

    def _edit_template(self) -> None:
        key = self.template.currentData()
        if not key:
            QMessageBox.information(
                self, "Pick a template",
                "Choose a specific industry template to edit — “Auto” renders "
                "whichever template matches each business.")
            return
        path = Path(services.runtime.user_asset("email_templates")) / f"{key}.html"
        if not path.exists():
            QMessageBox.warning(self, "Template missing", f"{path} was not found.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def import_leads(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _filter = QFileDialog.getOpenFileName(
            self, "Import leads", str(services.default_export_dir(self.state.settings)),
            "CSV files (*.csv)")
        if not path:
            return
        import csv

        from tui.models import Business

        try:
            with open(path, newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
        except OSError as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
            return
        businesses = [Business.from_dict(row) for row in rows if row.get("name")]
        added = self.state.add_businesses(businesses, "Imported")
        self.state.log("email", f"Imported {len(added)} lead(s) from {path}")
        QMessageBox.information(
            self, "Imported",
            f"Added {len(added)} new lead(s) from {Path(path).name}\n"
            f"({len(businesses) - len(added)} were already in the list).")

    def send(self) -> None:
        if self.runner.running:
            return
        chosen = self.chosen()
        if not chosen:
            return
        self._save_settings()
        dry_run = self.send_method.currentIndex() == 1
        limit = int(self.daily_limit.value())
        if len(chosen) > limit:
            answer = QMessageBox.question(
                self, "Over the daily limit",
                f"{len(chosen)} recipients selected but the daily limit is {limit}.\n"
                f"Send the first {limit} now?")
            if answer != QMessageBox.Yes:
                return
            chosen = chosen[:limit]

        password = ""
        if not dry_run:
            password = self.state.password
            if not password:
                password, ok = QInputDialog.getText(
                    self, "SMTP password",
                    "App-specific password for "
                    f"{self.state.settings.get('smtp_username') or self.from_email.text()}:",
                    QLineEdit.Password)
                if not ok or not password:
                    return
                self.state.password = password
            confirm = QMessageBox.question(
                self, "Send for real?",
                f"This sends {len(chosen)} email(s) from "
                f"{self.from_email.text().strip()}.\n\nContinue?")
            if confirm != QMessageBox.Yes:
                return

        pipeline = self.state.make_pipeline()
        delay = float(self.delay.value())
        self._set_running(True)
        self.progress.setRange(0, len(chosen))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.state.set_status("Sending…")
        self.state.log(
            "email",
            f"Campaign “{self.campaign_name.text().strip()}”: "
            f"{len(chosen)} recipient(s), {'dry run' if dry_run else 'live send'}")

        build = self._build_message

        def job(progress, on_event):
            messages = []
            for index, lead in enumerate(chosen, 1):
                progress(f"[{index}/{len(chosen)}] composing for {lead.business.name}…")
                messages.append(build(lead, pipeline))
            return pipeline.send(messages, password=password, delay=delay,
                                 dry_run=dry_run, progress=progress)

        self.runner.start(job)

    def _set_running(self, running: bool) -> None:
        self.send_button.setEnabled(not running and bool(self.chosen()))
        self.stop_button.setEnabled(running)
        self.import_button.setEnabled(not running)
        if not running:
            self.progress.setVisible(False)
            self.state.set_status("Ready")

    def _on_message(self, line: str) -> None:
        self.state.log("email", line)
        if line.startswith("[") and "/" in line:
            self.progress.setValue(self.progress.value() + 1)

    def _on_finished(self, stats) -> None:
        if not isinstance(stats, dict):
            return
        sent = int(stats.get("sent", 0))
        self.state.campaign_stats["sent"] += sent
        self.state.campaign_stats["delivered"] += sent
        self.state.campaign_stats["bounced"] += int(stats.get("failed", 0))
        self.refresh()
        self.state.leads_changed.emit()
        summary = (f"sent {sent}, failed {stats.get('failed', 0)}, "
                   f"skipped {stats.get('skipped', 0)}")
        self.state.log("email", f"Campaign finished — {summary}")
        if stats.get("error"):
            QMessageBox.warning(
                self, "SMTP problem",
                f"{stats['error']}\n\nCheck the account and app-specific "
                "password on the Settings page.")
        else:
            QMessageBox.information(self, "Campaign finished", summary)

    def _on_failed(self, message: str) -> None:
        self.state.log("email", f"ERROR {message}")
        QMessageBox.critical(self, "Send failed", message)

    def on_close(self) -> None:
        if self.runner.running:
            self.runner.stop()
            self.runner.wait(4000)


# ===========================================================================
#  Tab 3 — Call Scripts
# ===========================================================================
class CallScripts(QWidget):
    """The call assistant: who to ring, what to say, what to say back."""

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._queue: List[Lead] = []
        self._lead: Optional[Lead] = None
        self._steps: List[ScriptStep] = script_steps()
        self._step = 0
        self._call_started: Optional[datetime] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(self._build_current(), 3)
        top.addWidget(self._build_progress(), 3)
        layout.addLayout(top)

        middle = QSplitter(Qt.Horizontal)
        middle.addWidget(self._build_guide())
        middle.addWidget(self._build_objections())
        middle.setSizes([560, 460])
        layout.addWidget(middle, 1)

        layout.addWidget(self._build_notes())
        state.leads_changed.connect(self.refresh)

    def _build_current(self) -> Card:
        card = Card("Current Call")
        self.queue_picker = QComboBox()
        self.queue_picker.currentIndexChanged.connect(self._pick_from_queue)
        card.add(Field("Call Queue", self.queue_picker))
        self.row_name = KeyValueRow("Business Name", "—")
        self.row_phone = KeyValueRow("Phone", "—")
        self.row_contact = KeyValueRow("Contact", "Owner / Manager")
        self.row_website = KeyValueRow("Website", "—")
        for widget in (self.row_name, self.row_phone, self.row_contact, self.row_website):
            card.add(widget)
        self.complete_button = button("✔  Mark Call Complete", "Success")
        self.complete_button.clicked.connect(self.mark_complete)
        card.add(self.complete_button)
        card.body().addStretch(1)
        return card

    def _build_progress(self) -> Card:
        card = Card("Call Progress")
        self.steps_list = QListWidget()
        self.steps_list.setStyleSheet(
            f"QListWidget {{ border: 1px solid {theme.BORDER}; border-radius: 6px; }}"
            f"QListWidget::item {{ padding: 5px 8px; }}"
            f"QListWidget::item:selected {{ background: {theme.BLUE_SOFT}; color: {theme.INK}; }}"
        )
        self.steps_list.currentRowChanged.connect(self.go_step)
        for index, step in enumerate(self._steps, 1):
            self.steps_list.addItem(QListWidgetItem(f"{index}.  {step.title}"))
        card.add(self.steps_list, 1)
        self.call_timer_label = hint("No call in progress")
        card.add(self.call_timer_label)
        return card

    def _build_guide(self) -> Card:
        card = Card("Script Guide")
        self.guide_title = section_heading("")
        self.guide = QTextBrowser()
        self.guide.setOpenExternalLinks(True)
        self.guide.setStyleSheet(
            f"QTextBrowser {{ border: 1px solid {theme.BORDER}; border-radius: 6px;"
            f" padding: 8px; background: {theme.CARD}; }}")
        card.add(self.guide_title)
        card.add(self.guide, 1)
        self.prev_step_button = button("‹  Previous Step")
        self.next_step_button = button("Next Step  ›", "Primary")
        self.prev_step_button.clicked.connect(lambda: self.go_step(self._step - 1))
        self.next_step_button.clicked.connect(lambda: self.go_step(self._step + 1))
        nav = QHBoxLayout()
        nav.addWidget(self.prev_step_button)
        nav.addStretch(1)
        nav.addWidget(self.next_step_button)
        card.add_layout(nav)
        return card

    def _build_objections(self) -> Card:
        card = Card("Objection Handling")
        self.objection_picker = QComboBox()
        self.objection_picker.currentIndexChanged.connect(self._show_objection)
        card.add(self.objection_picker)
        self.objection_view = QTextBrowser()
        self.objection_view.setStyleSheet(
            f"QTextBrowser {{ border: 1px solid {theme.BORDER}; border-radius: 6px;"
            f" padding: 8px; background: {theme.CARD}; }}")
        card.add(self.objection_view, 1)
        return card

    def _build_notes(self) -> Card:
        card = Card("Call Notes")
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Add notes about this call…")
        self.notes.setFixedHeight(70)
        card.add(self.notes)
        self.outcome = QComboBox()
        self.outcome.addItems(CALL_OUTCOMES)
        self.end_button = button("✕  End Call", "Danger")
        self.followup_button = button("🗓  Schedule Follow Up")
        self.end_button.clicked.connect(self.end_call)
        self.followup_button.clicked.connect(self.schedule_followup)
        line = QHBoxLayout()
        line.addWidget(Field("Outcome", self.outcome), 2)
        line.addStretch(1)
        line.addWidget(self.followup_button)
        line.addWidget(self.end_button)
        card.add_layout(line)
        return card

    # -- data --------------------------------------------------------------
    def refresh(self) -> None:
        self._queue = self.state.callable_leads()
        current = self.queue_picker.currentIndex()
        self.queue_picker.blockSignals(True)
        self.queue_picker.clear()
        for lead in self._queue:
            b = lead.business
            phone = (b.phones[0] if b.phones else b.phone) or "no number"
            mark = "✔ " if lead.call_status else ""
            self.queue_picker.addItem(f"{mark}{b.name}  —  {phone}")
        self.queue_picker.blockSignals(False)
        if self._queue:
            self.queue_picker.setCurrentIndex(min(max(current, 0), len(self._queue) - 1))
            self._pick_from_queue(self.queue_picker.currentIndex())
        else:
            self._lead = None
            self.row_name.set_value("—")
            self.row_phone.set_value("—")
            self.row_website.set_value("—")
            self._load_objections()
            self.go_step(0)

    def _pick_from_queue(self, index: int) -> None:
        if not (0 <= index < len(self._queue)):
            return
        # Keep whatever was typed against the lead we are leaving.
        if self._lead is not None:
            self._lead.notes = self.notes.toPlainText()
        self._lead = self._queue[index]
        b = self._lead.business
        self.row_name.set_value(b.name or "—")
        self.row_phone.set_value((b.phones[0] if b.phones else b.phone) or "—")
        self.row_contact.set_value(", ".join(b.contact_names) or "Owner / Manager")
        self.row_website.set_value(b.website or "no website")
        self.notes.setPlainText(self._lead.notes)
        self._load_objections()
        self.go_step(0)
        if self._call_started is None:
            self._call_started = datetime.now()
        self.call_timer_label.setText(f"Started {self._call_started:%I:%M %p}")

    def _load_objections(self) -> None:
        business = self._lead.business if self._lead else None
        self._objections: List[ObjectionCard] = objection_cards(business)
        self.objection_picker.blockSignals(True)
        self.objection_picker.clear()
        for card in self._objections:
            self.objection_picker.addItem(card.label)
        self.objection_picker.blockSignals(False)
        self._show_objection(0)

    def _show_objection(self, index: int) -> None:
        if not getattr(self, "_objections", None) or not (0 <= index < len(self._objections)):
            self.objection_view.setHtml("")
            return
        card = self._objections[index]
        html = [
            f'<p style="color:{theme.RED};font-weight:600;margin:0 0 6px 0">'
            f'Objection: “{card.label}”</p>',
            f'<p style="margin:0 0 10px 0"><b>Response:</b> {card.response}</p>',
            f'<p style="margin:0 0 10px 0;color:{theme.INK_SOFT}">'
            f'<b>Next action:</b> {card.next_action}</p>',
        ]
        if card.fallback:
            html.append(
                f'<p style="margin:0;color:{theme.MUTED}"><b>If they still push back:</b> '
                f'{card.fallback}</p>')
        self.objection_view.setHtml("".join(html))

    def go_step(self, index: int) -> None:
        if not self._steps:
            return
        self._step = max(0, min(index, len(self._steps) - 1))
        step = self._steps[self._step]
        self.guide_title.setText(f"{self._step + 1}.  {step.title.upper()}")
        self.guide.setMarkdown(self._personalise(step.body))
        if self.steps_list.currentRow() != self._step:
            self.steps_list.blockSignals(True)
            self.steps_list.setCurrentRow(self._step)
            self.steps_list.blockSignals(False)
        self.prev_step_button.setEnabled(self._step > 0)
        self.next_step_button.setEnabled(self._step < len(self._steps) - 1)

    def _personalise(self, text: str) -> str:
        """Swap the script's [Business] style placeholders for the real name."""
        if self._lead is None:
            return text
        b = self._lead.business
        replacements = {
            "[Business]": b.name or "[Business]",
            "[Business Name]": b.name or "[Business Name]",
            "[business]": b.name or "[business]",
            "[Name]": ", ".join(b.contact_names) or "[Name]",
            "[City]": (b.address.split(",")[1].strip()
                       if b.address.count(",") >= 1 else "[City]"),
        }
        for needle, value in replacements.items():
            text = text.replace(needle, value)
        return text

    # -- actions -----------------------------------------------------------
    def mark_complete(self) -> None:
        if self._lead is None:
            return
        self._lead.call_status = "called"
        self._lead.notes = self.notes.toPlainText()
        self._lead.history.append(
            f"{datetime.now():%Y-%m-%d %H:%M} — call completed ({self.outcome.currentText()})")
        self.state.log(
            "call",
            f"{self._lead.business.name}: {self.outcome.currentText()}"
            + (f" — {self._lead.notes.splitlines()[0]}" if self._lead.notes.strip() else ""))
        index = self.queue_picker.currentIndex()
        self.refresh()
        if index + 1 < self.queue_picker.count():
            self.queue_picker.setCurrentIndex(index + 1)

    def end_call(self) -> None:
        self._call_started = None
        self.call_timer_label.setText("No call in progress")
        if self._lead is not None:
            self._lead.notes = self.notes.toPlainText()
            self.state.log("call", f"{self._lead.business.name}: call ended")

    def schedule_followup(self) -> None:
        if self._lead is None:
            return
        when, ok = QInputDialog.getText(
            self, "Schedule follow up",
            "When should this business be called back?", QLineEdit.Normal,
            "Tuesday morning")
        if not ok or not when.strip():
            return
        self._lead.call_status = "follow-up"
        self._lead.history.append(f"{datetime.now():%Y-%m-%d %H:%M} — follow up: {when.strip()}")
        self.state.log("call", f"{self._lead.business.name}: follow up {when.strip()}")
        QMessageBox.information(
            self, "Follow up noted",
            f"{self._lead.business.name} is marked for a follow-up {when.strip()}.\n"
            "It stays in the call queue and shows a ✔ in the picker.")
        self.refresh()


# ===========================================================================
#  The page itself
# ===========================================================================
class OutreachPage(Page):
    navigate_requested = Signal(str)
    heading = "Contacts & Outreach"

    def __init__(self, state, parent=None) -> None:
        super().__init__(state, parent)
        self.root().addWidget(title("4.  OUTREACH  —  EMAIL CAMPAIGNS & CALL ASSISTANT"))
        self.tabs = QTabWidget()
        self.dashboard = OutreachDashboard(state)
        self.campaigns = EmailCampaigns(state)
        self.calls = CallScripts(state)
        self.dashboard.navigate_requested.connect(self.navigate_requested)
        self.tabs.addTab(self.dashboard, "Outreach Dashboard")
        self.tabs.addTab(self.campaigns, "Email Campaigns")
        self.tabs.addTab(self.calls, "Call Scripts")
        self.root().addWidget(self.tabs, 1)

    def on_show(self) -> None:
        self.dashboard.refresh()
        self.campaigns.refresh()
        self.calls.refresh()

    def on_close(self) -> None:
        self.campaigns.on_close()
