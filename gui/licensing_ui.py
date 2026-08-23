"""The licence in front of the customer: banner, gate dialogs, activation.

Three things live here, all of them shared by more than one page:

:class:`LicenseBanner`
    The strip along the top of the window: trial countdown, expiry warning, or
    nothing at all when there is nothing to say. A licensed customer with weeks
    left should never see it.

:func:`require`
    The gate. Call it before starting gated work; it returns True, or shows the
    upgrade dialog and returns False. One line at each call site, and the
    message names the tier that unlocks the thing.

:class:`ActivationDialog`
    Where a key gets typed. It also carries the "start my trial" button,
    because those are the same moment for most people.

Every network call goes through :class:`~gui.workers.JobRunner`, off the UI
thread. A licence server that is slow to answer must never freeze the window.
"""

from __future__ import annotations

import webbrowser
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from licensing import get_manager, keys, plans
from licensing.errors import LicenseError, ServiceUnreachable, TrialExhausted

from . import theme
from .widgets.common import button, hint


# -- the gate ------------------------------------------------------------

def require(parent: QWidget, feature: str, *, action: str = "") -> bool:
    """True if ``feature`` is licensed here; otherwise explain and return False.

    ``action`` names what the customer was trying to do, so the dialog reads
    "Sending email needs…" rather than a bare feature name.
    """
    manager = get_manager()
    if manager.allows(feature):
        return True
    label = action or plans.FEATURE_LABELS.get(feature, feature)
    status = manager.status()
    upgrade = manager.lowest_tier_with(feature)
    if not status.licensed:
        body = (f"{label} needs an active licence.\n\n"
                f"{status.headline()}\n\n"
                "Start the free 72-hour trial or activate a key from the "
                "Licence screen.")
    elif upgrade:
        body = (f"{label} is part of {plans.tier(upgrade).name}.\n\n"
                f"Your licence is {status.tier_name}. Upgrading takes effect "
                "as soon as you activate — nothing is reinstalled.")
    else:
        body = f"{label} is not available on your licence."
    box = QMessageBox(parent)
    box.setWindowTitle("Not on this licence")
    box.setIcon(QMessageBox.Information)
    box.setText(body)
    see = box.addButton("See plans", QMessageBox.AcceptRole)
    box.addButton("Not now", QMessageBox.RejectRole)
    box.exec()
    if box.clickedButton() is see:
        _open_license_page(parent)
    return False


def _open_license_page(widget: QWidget) -> None:
    """Walk up to the main window and switch to the Licence screen."""
    window = widget.window() if widget is not None else None
    go_to = getattr(window, "go_to", None)
    if callable(go_to):
        go_to("license")


def cap_notice(parent: QWidget, requested: int, allowed: int, noun: str) -> None:
    """Tell the customer their number was clipped, once, without nagging."""
    if allowed >= requested:
        return
    QMessageBox.information(
        parent, "Licence limit",
        f"Your licence covers {allowed} {noun} per run; you asked for "
        f"{requested}.\n\nRunning with {allowed}. The Licence screen shows "
        "what each plan includes.")


# -- the banner ----------------------------------------------------------

class LicenseBanner(QFrame):
    """A one-line strip that appears only when the licence needs attention."""

    activate_requested = Signal()

    #: How close to the end a subscription gets before the banner speaks up.
    WARN_WITHIN_DAYS = 7

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("LicenseBanner")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFrameShape(QFrame.NoFrame)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        self.message = QLabel("")
        self.message.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: 600;")
        self.action = QPushButton("See plans")
        self.action.setCursor(Qt.PointingHandCursor)
        self.action.setObjectName("BannerAction")
        self.action.clicked.connect(self.activate_requested.emit)

        layout.addWidget(self.message, 1)
        layout.addWidget(self.action)

        # A trial counts down in hours; refreshing every few minutes keeps the
        # number honest without spending anything.
        self._timer = QTimer(self)
        self._timer.setInterval(60_000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def refresh(self) -> None:
        manager = get_manager()
        status = manager.status(refresh=True)
        tone, text, action = _banner_content(status)
        if not text:
            self.setVisible(False)
            return
        self.setVisible(True)
        self.message.setText(text)
        self.action.setText(action)
        self.setStyleSheet(
            f"#LicenseBanner {{ background: {tone}; }}"
            "#BannerAction { background: rgba(255,255,255,0.18); color: #FFFFFF;"
            " border: none; border-radius: 4px; padding: 4px 12px;"
            " font-size: 11px; font-weight: 600; }"
            "#BannerAction:hover { background: rgba(255,255,255,0.30); }"
        )


def _banner_content(status) -> tuple:
    """(colour, message, button text) — empty message means "show nothing"."""
    from licensing import manager as manager_module

    amber, red, blue = "#B4801A", "#A03030", theme.BLUE
    if status.state == manager_module.TRIAL:
        return amber, f"Trial — {status.headline()}", "Buy a licence"
    if status.state == manager_module.TRIAL_EXPIRED:
        return red, "Your 72-hour trial has ended. Scraping and sending are off.", "See plans"
    if status.state == manager_module.EXPIRED:
        return red, "Your subscription has ended. Renew to start scraping again.", "Renew"
    if status.state == manager_module.GRACE_EXPIRED:
        return amber, ("This licence needs to check in online — connect once to "
                       "carry on."), "Check now"
    if status.state == manager_module.CLOCK_TAMPERED:
        return red, "This computer's clock is set in the past; fix it and restart.", "Details"
    if status.state == manager_module.INVALID:
        return red, status.detail or "The licence file could not be read.", "Fix"
    if status.state == manager_module.UNLICENSED:
        return blue, "No licence yet — start your free 72-hour trial.", "Start trial"
    days = status.days_left()
    if status.state in (manager_module.ACTIVE, manager_module.STALE) \
            and days is not None and days <= LicenseBanner.WARN_WITHIN_DAYS:
        plural = "s" if days != 1 else ""
        return amber, f"Your licence renews in {days} day{plural}.", "Manage"
    return blue, "", ""


# -- activation ----------------------------------------------------------

class ActivationDialog(QDialog):
    """Type a key, or start the trial. Both talk to the licence service."""

    def __init__(self, parent: Optional[QWidget] = None, runner=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Activate Local Lead Scraper Pro")
        self.setMinimumWidth(460)
        self._runner = runner
        self.outcome = ""

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        heading = QLabel("Activate this computer")
        heading.setStyleSheet("font-size: 15px; font-weight: 700;")
        layout.addWidget(heading)
        layout.addWidget(hint(
            "Paste the licence key from your receipt. One key covers several "
            "computers depending on your plan — this one takes a seat, and you "
            "can hand it back from the Licence screen at any time."))

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("LLSP-XXXXX-XXXXX-XXXXX-XXXXX")
        self.key_input.textChanged.connect(self._on_key_changed)
        layout.addWidget(self.key_input)

        self.feedback = QLabel("")
        self.feedback.setWordWrap(True)
        self.feedback.setStyleSheet("font-size: 11px; color: #8B949E;")
        layout.addWidget(self.feedback)

        buttons = QDialogButtonBox()
        self.activate_button = buttons.addButton("Activate", QDialogButtonBox.AcceptRole)
        self.trial_button = buttons.addButton("Start 72-hour trial",
                                              QDialogButtonBox.ActionRole)
        buttons.addButton("Close", QDialogButtonBox.RejectRole)
        self.activate_button.setEnabled(False)
        self.activate_button.clicked.connect(self._activate)
        self.trial_button.clicked.connect(self._start_trial)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if self._runner is not None:
            # Connected once here rather than per call: reconnecting on every
            # attempt stacks handlers and fires the same result twice.
            self._runner.finished.connect(self._on_job_finished)
            self._runner.failed.connect(self._on_job_failed)

        status = get_manager().status()
        if status.state != "unlicensed":
            self.trial_button.setEnabled(status.state == "trial")

    def _on_key_changed(self, text: str) -> None:
        # Validate as they type: the checksum catches a wrong character before
        # anyone waits on a round trip to find out.
        if not text.strip():
            self.feedback.setText("")
            self.activate_button.setEnabled(False)
            return
        if keys.is_valid(text):
            self.feedback.setText("Key looks right.")
            self.activate_button.setEnabled(True)
        else:
            self.feedback.setText("Not a complete key yet.")
            self.activate_button.setEnabled(False)

    def _busy(self, busy: bool, note: str = "") -> None:
        self.activate_button.setEnabled(not busy and keys.is_valid(self.key_input.text()))
        self.trial_button.setEnabled(not busy)
        self.key_input.setEnabled(not busy)
        if note:
            self.feedback.setText(note)

    def _activate(self) -> None:
        typed = self.key_input.text()
        self._busy(True, "Activating…")
        self._run(lambda: get_manager().activate(typed), "activated")

    def _start_trial(self) -> None:
        self._busy(True, "Starting your trial…")
        self._run(lambda: get_manager().start_trial(), "trial")

    def _run(self, work, outcome: str) -> None:
        """Run a licence call off the UI thread, then report.

        The worker catches its own :class:`LicenseError` and returns it as a
        result rather than letting it escape: :class:`~gui.workers.JobRunner`
        reports failures as formatted strings, and the friendly wording below
        depends on knowing *which* error it was.
        """

        def attempt():
            try:
                work()
            except LicenseError as exc:
                return {"ok": False, "error": exc}
            return {"ok": True, "outcome": outcome}

        if self._runner is None:
            # No runner (tests, or a caller that did not pass one): inline.
            # Blocking briefly is better than not working at all.
            self._report(attempt())
            return
        self._runner.start(lambda progress, on_event: attempt())

    def _on_job_finished(self, result) -> None:
        if isinstance(result, dict) and ("ok" in result):
            self._report(result)

    def _on_job_failed(self, message: str) -> None:
        # Something that was not a LicenseError got out — a bug, or a broken
        # environment. Show it rather than leaving the dialog stuck on "…".
        self._busy(False)
        self.feedback.setText(str(message))

    def _report(self, result) -> None:
        if result.get("ok"):
            self.outcome = result.get("outcome") or ""
            self._busy(False)
            self.accept()
            return
        self._failed(result.get("error"))

    def _failed(self, exc) -> None:
        self._busy(False)
        if isinstance(exc, TrialExhausted):
            message = ("This computer has already used its 72-hour trial. "
                       "Choose a plan to carry on.")
        elif isinstance(exc, ServiceUnreachable):
            message = (f"{exc}\n\nIf you are offline, the trial still starts — "
                       "it just runs shorter until the app can check in.")
        else:
            message = str(exc)
        self.feedback.setText(message)
        QMessageBox.warning(self, "Activation", message)


def open_pricing_page(sku: str = "") -> None:
    """Open the website's pricing page (or a direct checkout) in a browser."""
    from licensing.client import service_url

    url = f"{service_url()}/pricing"
    if sku:
        url = f"{url}?plan={sku}"
    webbrowser.open(url)
