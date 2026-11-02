"""The live send log that sits beside Campaign Stats.

It shows one row per recipient as a campaign runs: when it happened, who it
went to, and whether it was sent, skipped, refused (with the reason) or only
composed in a dry run. Above the rows are a status pill, running counters, a
progress bar and an elapsed / time-left estimate.

The page feeds it with the dict events the pipeline emits
(``{"kind": "email", "index", "total", "status", "detail", "business", "to"}``)
plus a few of its own for the composing and preview passes.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Dict, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QTableWidget,
    QTableWidgetItem, QWidget,
)

from .. import theme
from .common import Card, Pill, button, progress_bar

# status -> (icon, label, colour)
_STATUS = {
    "composing": ("✎", "Composing", theme.INK_SOFT),
    "preview": ("🖼", "Preview", theme.INK_SOFT),
    "connecting": ("…", "Connecting", theme.INK_SOFT),
    "connected": ("✓", "Connected", theme.GREEN),
    "sending": ("➜", "Sending…", theme.BLUE),
    "sent": ("✓", "Sent", theme.GREEN),
    "failed": ("✗", "Failed", theme.RED),
    "skipped": ("⏭", "Skipped", theme.AMBER),
    "dry_run": ("○", "Dry run", theme.MUTED),
    "error": ("⚠", "Error", theme.RED),
    "info": ("•", "", theme.INK_SOFT),
}


def _fmt_seconds(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}:{secs:02d}"


class SendMonitor(Card):
    """A real-time, per-recipient log of the current campaign."""

    COLUMNS = ["Time", "#", "Business", "Email", "Status", "Details"]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Live Send Log", parent)
        self._rows: Dict[int, int] = {}       # recipient index -> table row
        self._started: Optional[float] = None
        self._total = 0
        self._done = 0
        self._counts = {"sent": 0, "failed": 0, "skipped": 0, "dry_run": 0}
        self._dry_run = False

        header = QHBoxLayout()
        self.pill = Pill("Idle", "idle")
        self.counters = QLabel()
        self.counters.setTextFormat(Qt.RichText)
        self.timing = QLabel("")
        self.timing.setStyleSheet(f"color: {theme.MUTED};")
        self.clear_button = button("Clear")
        self.clear_button.clicked.connect(self.clear)
        header.addWidget(self.pill)
        header.addWidget(self.counters)
        header.addStretch(1)
        header.addWidget(self.timing)
        header.addWidget(self.clear_button)
        self.add_layout(header)

        self.bar = progress_bar(blue=True)
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.add(self.bar)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setWordWrap(False)
        self.table.setMinimumHeight(170)
        head = self.table.horizontalHeader()
        for column in range(len(self.COLUMNS)):
            head.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(len(self.COLUMNS) - 1, QHeaderView.Stretch)
        self.add(self.table, 1)

        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._update_timing)
        self._update_counters()

    # -- lifecycle -------------------------------------------------------
    def clear(self) -> None:
        self.table.setRowCount(0)
        self._rows.clear()
        self._counts = dict.fromkeys(self._counts, 0)
        self._done = 0
        self._total = 0
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.timing.setText("")
        self.pill.set_state("Idle", "idle")
        self._update_counters()

    def begin(self, total: int, *, dry_run: bool, label: str = "") -> None:
        """Start a fresh run of ``total`` recipients."""
        self.clear()
        self._total = max(0, total)
        self._dry_run = dry_run
        self._started = time.monotonic()
        self.bar.setRange(0, max(1, self._total))
        self.pill.set_state("Dry run" if dry_run else "Sending", "warn" if dry_run else "busy")
        self.note("info", label or (
            f"Dry run of {total} email(s) — composed only, nothing is sent"
            if dry_run else f"Live send to {total} recipient(s)"))
        self._clock.start()
        self._update_timing()

    def finish(self, *, cancelled: bool = False, error: str = "") -> None:
        self._clock.stop()
        self._update_timing(final=True)
        if error:
            self.pill.set_state("Failed", "bad")
            self.note("error", error)
        elif cancelled:
            self.pill.set_state("Stopped", "warn")
            self.note("info", "Stopped by you.")
        elif self._dry_run:
            self.pill.set_state("Dry run done", "warn")
            self.note("dry_run", f"Composed {self._counts['dry_run']} email(s). Nothing "
                      "was sent — set Send Method to “Send for real” to email them.")
        elif self._counts["failed"] and not self._counts["sent"]:
            self.pill.set_state("All failed", "bad")
        else:
            self.pill.set_state("Done", "good")
        self._update_counters()

    # -- feeding ---------------------------------------------------------
    def note(self, status: str, detail: str) -> None:
        """A run-level line (connecting, errors, summaries)."""
        self._append(None, status, "", "", detail)

    def handle(self, event) -> None:
        """Apply one pipeline event dict; ignores anything else."""
        if not isinstance(event, dict) or event.get("kind") != "email":
            return
        status = str(event.get("status", "info"))
        index = event.get("index")
        if index is None:
            self.note(status, str(event.get("detail", "")))
            return
        index = int(index)
        if event.get("total"):
            self._total = int(event["total"])
            self.bar.setRange(0, max(1, self._total))
        business = str(event.get("business", ""))
        to = str(event.get("to", ""))
        detail = str(event.get("detail", ""))
        row = self._rows.get(index)
        if row is None:
            row = self._append(index, status, business, to, detail)
            self._rows[index] = row
        else:
            self._set_row(row, index, status, business, to, detail)
        if status in self._counts:
            self._counts[status] += 1
            self._done += 1
            self.bar.setValue(min(self._done, self.bar.maximum()))
        self._update_counters()
        self._update_timing()

    # -- internals -------------------------------------------------------
    def _append(self, index, status, business, to, detail) -> int:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._set_row(row, index, status, business, to, detail)
        self.table.scrollToBottom()
        return row

    def _set_row(self, row, index, status, business, to, detail) -> None:
        icon, label, colour = _STATUS.get(status, _STATUS["info"])
        index_text = (f"{index}/{self._total}" if self._total else str(index)) \
            if index is not None else ""
        values = [datetime.now().strftime("%H:%M:%S"), index_text, business, to,
                  f"{icon} {label}".strip(), detail]
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column in (4, 5) or index is None:
                item.setForeground(QColor(colour))
            if status in ("failed", "error"):
                item.setBackground(QColor(theme.RED_SOFT))
            elif status == "sent":
                item.setBackground(QColor(theme.GREEN_SOFT))
            if column == 5 and detail:
                item.setToolTip(detail)
            self.table.setItem(row, column, item)

    def _update_counters(self) -> None:
        c = self._counts
        parts = [
            f"<span style='color:{theme.GREEN}'><b>{c['sent']}</b> sent</span>",
            f"<span style='color:{theme.RED}'><b>{c['failed']}</b> failed</span>",
            f"<span style='color:{theme.AMBER}'><b>{c['skipped']}</b> skipped</span>",
        ]
        if self._dry_run or c["dry_run"]:
            parts.append(f"<span style='color:{theme.MUTED}'><b>{c['dry_run']}</b> "
                         "composed (dry run)</span>")
        if self._total:
            parts.append(f"<span style='color:{theme.INK_SOFT}'>"
                         f"{self._done}/{self._total}</span>")
        self.counters.setText("&nbsp;&nbsp;·&nbsp;&nbsp;".join(parts))

    def _update_timing(self, final: bool = False) -> None:
        if self._started is None:
            return
        elapsed = time.monotonic() - self._started
        text = f"Elapsed {_fmt_seconds(elapsed)}"
        if not final and self._done and self._total > self._done:
            left = elapsed / self._done * (self._total - self._done)
            text += f"  ·  ~{_fmt_seconds(left)} left"
        self.timing.setText(text)

    # Handy for tests and the page's summary dialog.
    @property
    def counts(self) -> Dict[str, int]:
        return dict(self._counts)
