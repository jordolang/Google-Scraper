"""The screens that fill the workspace to the right of the navigation rail."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..state import AppState


class Page(QWidget):
    """Base class: holds the shared state and a standard page margin."""

    #: Text shown in the window title bar while this page is on screen.
    heading = ""

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self.setObjectName("Workspace")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(16, 14, 16, 14)
        self._root.setSpacing(12)

    def root(self) -> QVBoxLayout:
        return self._root

    def on_show(self) -> None:
        """Called each time the page becomes visible; refresh derived views."""

    def on_close(self) -> None:
        """Called when the window is closing; stop background work."""
