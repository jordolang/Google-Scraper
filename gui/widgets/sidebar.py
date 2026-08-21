"""The dark navigation rail down the left of the window."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from .. import theme

# (key, label, glyph) for every destination, top to bottom.
NAV_ITEMS: Sequence[Tuple[str, str, str]] = (
    ("dashboard", "Dashboard", "⌂"),
    ("listings", "Business Listings", "▤"),
    ("scraper", "Website Scraper", "◎"),
    ("outreach", "Contacts & Outreach", "✉"),
    ("settings", "Settings", "⚙"),
    ("tools", "Tools", "⚒"),
    ("logs", "Logs", "☰"),
    ("help", "Help", "?"),
)


def brand_mark(size: int = 26) -> QPixmap:
    """The round blue app mark, drawn rather than shipped as an asset."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(theme.BLUE))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(0, 0, size - 1, size - 1)
    painter.setBrush(QColor("#FFFFFF"))
    inner = size // 3
    painter.drawEllipse((size - inner) // 2, (size - inner) // 2 - 1, inner, inner)
    painter.end()
    return pixmap


class Sidebar(QWidget):
    """Emits :attr:`navigated` with the key of whichever item was clicked."""

    navigated = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        # A plain QWidget ignores a stylesheet background unless it is told to
        # draw one; without this the rail renders transparent.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(214)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(4)

        # -- brand ---------------------------------------------------------
        mark = QLabel()
        mark.setPixmap(brand_mark(28))
        name = QLabel("Local Lead\nScraper Pro")
        name.setObjectName("SidebarBrand")
        name.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: 700;")
        brand = QWidget()
        brand_layout = QVBoxLayout(brand)
        brand_layout.setContentsMargins(2, 0, 0, 8)
        brand_layout.setSpacing(6)
        brand_layout.addWidget(mark)
        brand_layout.addWidget(name)
        layout.addWidget(brand)

        rule = QFrame()
        rule.setObjectName("SidebarRule")
        rule.setFixedHeight(1)
        layout.addWidget(rule)
        layout.addSpacing(6)

        # -- destinations --------------------------------------------------
        self._buttons: Dict[str, QPushButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for key, label, glyph in NAV_ITEMS:
            # "&" opens a keyboard mnemonic in Qt button text; "&&" prints it.
            button = QPushButton(f"  {glyph}   {label.replace(chr(38), chr(38) * 2)}")
            button.setObjectName("NavItem")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(32)
            button.clicked.connect(lambda _checked=False, k=key: self.navigated.emit(k))
            self._group.addButton(button)
            layout.addWidget(button)
            self._buttons[key] = button

        layout.addStretch(1)

        # -- licence + status ---------------------------------------------
        self.license_label = QLabel("License: Pro")
        self.license_label.setObjectName("SidebarCaption")
        self.expiry_label = QLabel("Expires: —")
        self.expiry_label.setObjectName("SidebarCaption")
        layout.addWidget(self.license_label)
        layout.addWidget(self.expiry_label)
        layout.addSpacing(8)

        self.status_label = QLabel("● Ready")
        self.status_label.setObjectName("SidebarStatus")
        layout.addWidget(self.status_label)

    # -- api ---------------------------------------------------------------
    def select(self, key: str) -> None:
        button = self._buttons.get(key)
        if button is not None and not button.isChecked():
            button.setChecked(True)

    def set_license(self, tier: str, expires: str) -> None:
        self.license_label.setText(f"License: {tier}")
        self.expiry_label.setText(f"Expires: {expires}")

    def set_status(self, text: str, tone: str = "idle") -> None:
        colours = {
            "idle": "#3FB950",   # green dot = ready
            "busy": "#E3B341",
            "bad": "#F85149",
        }
        dot = colours.get(tone, colours["idle"])
        self.status_label.setText(f"● {text}")
        self.status_label.setStyleSheet(f"color: {dot}; font-size: 11px;")

    def keys(self) -> List[str]:
        return list(self._buttons)
