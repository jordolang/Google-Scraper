"""Small building blocks the pages are assembled from.

Everything here is presentational: a card with a title, a labelled field, a
stat tile, a log pane, a table that behaves the way a data grid should. Pages
stay readable because the chrome lives here.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPlainTextEdit, QProgressBar, QPushButton, QSizePolicy,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import theme


class Card(QFrame):
    """A white panel with an optional title row; the app's basic container."""

    def __init__(self, title: str = "", parent: Optional[QWidget] = None,
                 *, spacing: int = 8, margins: tuple = (14, 12, 14, 12)) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(*margins)
        self._layout.setSpacing(spacing)
        self.title_label: Optional[QLabel] = None
        if title:
            self.title_label = QLabel(title)
            self.title_label.setObjectName("CardTitle")
            self._layout.addWidget(self.title_label)

    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self._layout.addWidget(widget, stretch)
        return widget

    def add_layout(self, layout) -> None:
        self._layout.addLayout(layout)

    def set_title(self, text: str) -> None:
        if self.title_label is not None:
            self.title_label.setText(text)


class Field(QWidget):
    """A caption above an input, the way every form in the mockups reads."""

    def __init__(self, label: str, widget: QWidget, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        caption = QLabel(label)
        caption.setObjectName("FieldLabel")
        layout.addWidget(caption)
        layout.addWidget(widget)
        self.caption = caption
        self.widget = widget


class Stat(QWidget):
    """A label-over-value pair used across the status strips."""

    def __init__(self, label: str, value: str = "—", *, green: bool = False,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.caption = QLabel(label)
        self.caption.setObjectName("StatLabel")
        self.value = QLabel(value)
        self.value.setObjectName("StatValueGreen" if green else "StatValue")
        layout.addWidget(self.caption)
        layout.addWidget(self.value)

    def set_value(self, text: str) -> None:
        self.value.setText(str(text))

    def set_green(self, green: bool) -> None:
        self.value.setObjectName("StatValueGreen" if green else "StatValue")
        self.value.style().unpolish(self.value)
        self.value.style().polish(self.value)


class KeyValueRow(QWidget):
    """One `Label            value` line, for the overview panels."""

    def __init__(self, label: str, value: str = "0", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(8)
        self.caption = QLabel(label)
        self.caption.setStyleSheet(f"color: {theme.MUTED}; font-size: 11px;")
        self.value = QLabel(str(value))
        self.value.setStyleSheet(f"color: {theme.INK}; font-size: 11px; font-weight: 600;")
        self.value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.caption)
        layout.addStretch(1)
        layout.addWidget(self.value)

    def set_value(self, text) -> None:
        self.value.setText(str(text))


class Pill(QLabel):
    """A small status chip: Ready / Scraping / Completed / Failed."""

    TONES = {
        "idle": (theme.MUTED, "#EEF2F7"),
        "busy": (theme.BLUE, theme.BLUE_SOFT),
        "good": (theme.GREEN, theme.GREEN_SOFT),
        "warn": (theme.AMBER, "#FEF3E2"),
        "bad": (theme.RED, theme.RED_SOFT),
    }

    def __init__(self, text: str = "", tone: str = "idle", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        # A chip hugs its text; letting it stretch turns it into a banner.
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        fg, bg = self.TONES.get(tone, self.TONES["idle"])
        self.setStyleSheet(
            f"color: {fg}; background: {bg}; border-radius: 9px;"
            f"padding: 2px 9px; font-size: 11px; font-weight: 600;"
        )

    def set_state(self, text: str, tone: str) -> None:
        self.setText(text)
        self.set_tone(tone)


class LogView(QPlainTextEdit):
    """Append-only monospaced activity log that follows the tail."""

    def __init__(self, parent: Optional[QWidget] = None, *, max_lines: int = 2000) -> None:
        super().__init__(parent)
        self.setObjectName("Log")
        self.setReadOnly(True)
        self.setMaximumBlockCount(max_lines)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)

    def append(self, line: str) -> None:  # noqa: A003 - mirrors QTextEdit.append
        self.appendPlainText(line)
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())


class DataTable(QTableWidget):
    """A read-only grid with sane defaults and an optional checkbox column."""

    selection_toggled = Signal()

    def __init__(self, headers: Sequence[str], parent: Optional[QWidget] = None,
                 *, checkable: bool = False, stretch_column: int = -1) -> None:
        self._checkable = checkable
        self._headers = ["" if checkable else None]
        columns = (["☑"] if checkable else []) + list(headers)
        super().__init__(0, len(columns), parent)
        self.setHorizontalHeaderLabels(columns)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setShowGrid(True)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setWordWrap(False)
        self.verticalHeader().setDefaultSectionSize(26)
        header = self.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionResizeMode(QHeaderView.Interactive)
        if checkable:
            header.setSectionResizeMode(0, QHeaderView.Fixed)
            self.setColumnWidth(0, 32)
        if stretch_column >= 0:
            offset = 1 if checkable else 0
            header.setSectionResizeMode(stretch_column + offset, QHeaderView.Stretch)
        self.itemChanged.connect(self._on_item_changed)
        self._suppress = False

    # -- rows -------------------------------------------------------------
    def set_rows(self, rows: Iterable[Sequence], *, checked: Optional[Sequence[bool]] = None,
                 tooltips: Optional[Sequence[Sequence[str]]] = None) -> None:
        """Replace the whole grid in one shot."""
        rows = [list(row) for row in rows]
        self._suppress = True
        self.setRowCount(len(rows))
        offset = 1 if self._checkable else 0
        for r, row in enumerate(rows):
            if self._checkable:
                box = QTableWidgetItem()
                box.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                state = bool(checked[r]) if checked and r < len(checked) else False
                box.setCheckState(Qt.Checked if state else Qt.Unchecked)
                self.setItem(r, 0, box)
            for c, value in enumerate(row):
                item = QTableWidgetItem("" if value is None else str(value))
                if tooltips and r < len(tooltips) and c < len(tooltips[r]):
                    item.setToolTip(str(tooltips[r][c]))
                self.setItem(r, c + offset, item)
        self._suppress = False
        self.resizeColumnsToContents()
        self._cap_widths()

    def _cap_widths(self, cap: int = 320) -> None:
        for col in range(self.columnCount()):
            if self.columnWidth(col) > cap:
                self.setColumnWidth(col, cap)

    def checked_rows(self) -> List[int]:
        if not self._checkable:
            return sorted({index.row() for index in self.selectedIndexes()})
        return [
            row for row in range(self.rowCount())
            if (item := self.item(row, 0)) is not None and item.checkState() == Qt.Checked
        ]

    def set_all_checked(self, checked: bool) -> None:
        if not self._checkable:
            return
        self._suppress = True
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item is not None:
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self._suppress = False
        self.selection_toggled.emit()

    def set_row_checked(self, row: int, checked: bool) -> None:
        item = self.item(row, 0) if self._checkable else None
        if item is not None:
            self._suppress = True
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            self._suppress = False

    def tint_row(self, row: int, colour: str) -> None:
        for col in range(self.columnCount()):
            item = self.item(row, col)
            if item is not None:
                item.setBackground(QColor(colour))

    def bold_cell(self, row: int, column: int) -> None:
        offset = 1 if self._checkable else 0
        item = self.item(row, column + offset)
        if item is not None:
            font = item.font()
            font.setBold(True)
            item.setFont(font)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if not self._suppress and self._checkable and item.column() == 0:
            self.selection_toggled.emit()


def h_line() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet(f"color: {theme.BORDER}; background: {theme.BORDER}; max-height: 1px;")
    return line


def row(*widgets: QWidget, spacing: int = 8, margins: tuple = (0, 0, 0, 0)) -> QWidget:
    """Lay widgets out horizontally; an int in the list becomes a stretch."""
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    for widget in widgets:
        if isinstance(widget, int):
            layout.addStretch(widget)
        else:
            layout.addWidget(widget)
    return container


def title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("PageTitle")
    return label


def hint(text: str, *, wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Hint")
    label.setWordWrap(wrap)
    return label


def button(text: str, kind: str = "", *, tooltip: str = "") -> QPushButton:
    btn = QPushButton(text)
    if kind:
        btn.setObjectName(kind)
    if tooltip:
        btn.setToolTip(tooltip)
    btn.setCursor(Qt.PointingHandCursor)
    return btn


def progress_bar(*, blue: bool = False) -> QProgressBar:
    bar = QProgressBar()
    bar.setTextVisible(False)
    bar.setRange(0, 100)
    bar.setValue(0)
    if blue:
        bar.setObjectName("Blue")
    bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return bar


def search_box(placeholder: str = "Search results…") -> QLineEdit:
    box = QLineEdit()
    box.setPlaceholderText(placeholder)
    box.setClearButtonEnabled(True)
    return box


def checkbox(text: str, checked: bool = True) -> QCheckBox:
    box = QCheckBox(text)
    box.setChecked(checked)
    return box


def section_heading(text: str) -> QLabel:
    label = QLabel(text)
    font = QFont()
    font.setBold(True)
    font.setPointSize(9)
    label.setFont(font)
    label.setStyleSheet(f"color: {theme.INK};")
    return label
