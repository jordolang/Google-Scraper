"""Logs — everything the app has done this session."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QMessageBox

from .. import services
from ..widgets.common import Card, LogView, button, hint, search_box, title
from . import Page

SOURCES = ["All", "search", "scan", "email", "call", "tools", "export", "settings"]


class LogsPage(Page):
    heading = "Logs"

    def __init__(self, state, parent=None) -> None:
        super().__init__(state, parent)
        self.root().addWidget(title("LOGS"))
        card = Card()

        controls = QHBoxLayout()
        self.source = QComboBox()
        self.source.addItems(SOURCES)
        self.source.currentIndexChanged.connect(self.refresh)
        self.search = search_box("Filter log lines…")
        self.search.textChanged.connect(self.refresh)
        self.save_button = button("Save Log…")
        self.clear_button = button("Clear")
        self.save_button.clicked.connect(self.save)
        self.clear_button.clicked.connect(self.clear)
        controls.addWidget(self.search, 3)
        controls.addWidget(self.source, 1)
        controls.addStretch(1)
        controls.addWidget(self.save_button)
        controls.addWidget(self.clear_button)
        card.add_layout(controls)

        self.view = LogView(max_lines=6000)
        card.add(self.view, 1)
        self.count = hint("0 lines")
        card.add(self.count)
        self.root().addWidget(card, 1)

        self._shown = 0
        state.logged.connect(self._on_logged)

    def _on_logged(self, _source: str, line: str) -> None:
        """Append one line rather than re-rendering the whole buffer.

        A long scrape emits thousands of lines; rebuilding the document for
        each one made the page crawl and threw away the scroll position.
        """
        if not self.isVisible():
            return
        if self._matches(line):
            self.view.append(line)
            self._shown += 1
            self.count.setText(
                f"{self._shown} line(s) of {len(self.state.log_lines)}")

    def _matches(self, line: str) -> bool:
        source = self.source.currentText()
        if source != "All" and f"[{source}]" not in line:
            return False
        needle = self.search.text().strip().lower()
        return not needle or needle in line.lower()

    def _filtered(self):
        return (line for line in self.state.log_lines if self._matches(line))

    def refresh(self) -> None:
        """Rebuild the view — only needed when the filters or buffer change."""
        lines = list(self._filtered())
        self.view.setPlainText("\n".join(lines))
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())
        self._shown = len(lines)
        self.count.setText(f"{len(lines)} line(s) of {len(self.state.log_lines)}")

    def save(self) -> None:
        suggested = services.default_export_dir(self.state.settings) / \
            services.suggested_filename("session_log", "txt")
        path, _filter = QFileDialog.getSaveFileName(
            self, "Save log", str(suggested), "Text files (*.txt)")
        if not path:
            return
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text("\n".join(self._filtered()), encoding="utf-8")
        QMessageBox.information(self, "Saved", f"Log written to\n{path}")

    def clear(self) -> None:
        self.state.log_lines.clear()
        self.refresh()

    def on_show(self) -> None:
        self.refresh()
