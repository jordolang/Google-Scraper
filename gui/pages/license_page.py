"""Screen — the licence: what you have, what you could have, and how to buy it.

The page answers four questions in the order people ask them:

1. What am I running right now, and until when?
2. What does it let me do, and what does it not?
3. What do the plans cost — both ways of paying?
4. How do I put a key in, or hand this computer's seat back?

The plan table shows the two pricing models side by side rather than hiding one
behind a toggle. Someone deciding between "£89 a month forever" and "£1,299
once" is doing arithmetic, and hiding half the numbers makes them leave to do
it on a website.
"""

from __future__ import annotations

import time
import webbrowser
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget,
)

from licensing import get_manager, keys as key_module, plans
from licensing.errors import LicenseError

from .. import theme
from ..licensing_ui import ActivationDialog, open_pricing_page
from ..widgets.common import Card, KeyValueRow, button, h_line, hint, title
from ..workers import JobRunner
from . import Page


class LicensePage(Page):
    """Status, entitlements, the price list, and the activation controls."""

    navigate_requested = Signal(str)
    heading = "Licence"

    def __init__(self, state, parent=None) -> None:
        super().__init__(state, parent)
        self.runner = JobRunner(self)
        self.root().addWidget(title("LICENCE & BILLING"))

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._build_status_card(), 2)
        body.addWidget(self._build_entitlements_card(), 3)
        self.root().addLayout(body)

        self.root().addWidget(self._build_plans_card(), 1)
        self.refresh()

    # -- construction ------------------------------------------------------
    def _build_status_card(self) -> Card:
        card = Card("This computer")
        self.state_label = QLabel("—")
        self.state_label.setStyleSheet("font-size: 17px; font-weight: 700;")
        self.state_label.setWordWrap(True)
        card.add(self.state_label)

        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet("font-size: 11px; color: #8B949E;")
        card.add(self.detail_label)
        card.add(h_line())

        self.row_tier = KeyValueRow("Plan", "—")
        self.row_model = KeyValueRow("Billing", "—")
        self.row_expiry = KeyValueRow("Renews / expires", "—")
        self.row_key = KeyValueRow("Key", "—")
        self.row_seat = KeyValueRow("Seat", "—")
        self.row_email = KeyValueRow("Licensed to", "—")
        for row in (self.row_tier, self.row_model, self.row_expiry,
                    self.row_key, self.row_seat, self.row_email):
            card.add(row)

        card.add(h_line())
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.activate_button = button("Activate a key…", "Primary")
        self.activate_button.clicked.connect(self.open_activation)
        self.refresh_button = button("Check now")
        self.refresh_button.setToolTip(
            "Ask the licence service for an up-to-date licence. Needed only "
            "after a renewal, an upgrade, or a long spell offline.")
        self.refresh_button.clicked.connect(self.check_now)
        self.deactivate_button = button("Deactivate this computer", "Danger")
        self.deactivate_button.setToolTip(
            "Hand this computer's seat back so another machine can use it.")
        self.deactivate_button.clicked.connect(self.deactivate)
        buttons.addWidget(self.activate_button)
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.deactivate_button)
        buttons.addStretch(1)
        card.add_layout(buttons)
        return card

    def _build_entitlements_card(self) -> Card:
        card = Card("What this licence includes")
        self.limits_label = QLabel("")
        self.limits_label.setWordWrap(True)
        self.limits_label.setStyleSheet("font-size: 12px;")
        card.add(self.limits_label)
        card.add(h_line())

        self.feature_grid = QGridLayout()
        self.feature_grid.setHorizontalSpacing(10)
        self.feature_grid.setVerticalSpacing(3)
        holder = QWidget()
        holder.setLayout(self.feature_grid)
        card.add(holder)
        card.body().addStretch(1)
        return card

    def _build_plans_card(self) -> Card:
        card = Card("Plans")
        card.add(hint(
            "Two ways to pay for the same software. A subscription keeps "
            "renewing and always has the newest version. A one-time licence "
            "is yours permanently and includes twelve months of updates — "
            "after that it keeps working, it just stops changing."))

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        headers = ["", "Monthly", "Yearly", "One-time", "Machines", ""]
        for column, text in enumerate(headers):
            label = QLabel(text)
            label.setStyleSheet("font-size: 11px; font-weight: 700; color: #8B949E;")
            grid.addWidget(label, 0, column)

        self._buy_buttons: Dict[str, object] = {}
        for row, key in enumerate((plans.SOLO, plans.PRO, plans.AGENCY), start=1):
            tier = plans.TIERS[key]
            name = QLabel(f"{tier.name}")
            name.setStyleSheet("font-size: 13px; font-weight: 700;")
            name.setToolTip(tier.blurb)
            grid.addWidget(name, row, 0)

            monthly, yearly = tier.subscription_cents or (0, 0)
            grid.addWidget(self._price_label(f"{key}-subscription-monthly", monthly), row, 1)
            grid.addWidget(self._price_label(f"{key}-subscription-yearly", yearly), row, 2)
            grid.addWidget(self._price_label(f"{key}-perpetual-once",
                                             tier.perpetual_cents or 0), row, 3)
            grid.addWidget(QLabel(str(tier.limits.max_machines)), row, 4)

            blurb = QLabel(tier.blurb)
            blurb.setWordWrap(True)
            blurb.setStyleSheet("font-size: 11px; color: #8B949E;")
            grid.addWidget(blurb, row, 5)

        holder = QWidget()
        holder.setLayout(grid)
        card.add(holder)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        for key in (plans.SOLO, plans.PRO, plans.AGENCY):
            buy = button(f"Buy {plans.TIERS[key].name}", "Primary")
            buy.clicked.connect(lambda _checked=False, k=key: self.buy(k))
            actions.addWidget(buy)
            self._buy_buttons[key] = buy
        actions.addStretch(1)
        self.compare_button = button("Full comparison in your browser")
        self.compare_button.clicked.connect(lambda: open_pricing_page())
        actions.addWidget(self.compare_button)
        card.add_layout(actions)
        return card

    def _price_label(self, sku: str, cents: int) -> QLabel:
        price = plans.price_for(sku)
        label = QLabel(price.display if price else ("—" if not cents else f"${cents/100:,.0f}"))
        label.setStyleSheet("font-size: 13px; font-weight: 600;")
        return label

    # -- refresh -----------------------------------------------------------
    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        manager = get_manager()
        status = manager.status(refresh=True)
        self.state_label.setText(status.headline())
        self.detail_label.setText(status.detail)

        self.row_tier.set_value(status.tier_name)
        self.row_model.set_value({
            plans.SUBSCRIPTION: "Subscription",
            plans.PERPETUAL: "One-time (perpetual)",
        }.get(status.model, "—"))
        if status.perpetual:
            token = manager.token()
            until = token.updates_until if token else None
            self.row_expiry.set_value(
                f"Never expires · updates to {_date(until)}" if until else "Never expires")
        else:
            self.row_expiry.set_value(_date(status.expires_at))
        self.row_key.set_value(key_module.masked(status.key) if status.key else "—")
        self.row_seat.set_value(str(status.seat) if status.key else "—")
        self.row_email.set_value(status.email or "—")

        self.limits_label.setText("\n".join(f"•  {line}" for line in manager.restrictions()))
        self._fill_features(manager)

        self.deactivate_button.setEnabled(bool(status.key))
        self.refresh_button.setEnabled(bool(status.key) or status.state == "trial")

    def _fill_features(self, manager) -> None:
        while self.feature_grid.count():
            item = self.feature_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        held = manager.features()
        for index, feature in enumerate(plans.ALL_FEATURES):
            included = feature in held
            mark = QLabel("✓" if included else "—")
            mark.setStyleSheet(
                f"color: {'#3FB950' if included else '#6E7681'}; font-weight: 700;")
            label = QLabel(plans.FEATURE_LABELS[feature])
            label.setStyleSheet(
                f"font-size: 11px; color: {'#C9D1D9' if included else '#6E7681'};")
            if not included:
                upgrade = manager.lowest_tier_with(feature)
                if upgrade:
                    label.setToolTip(f"Included from {plans.tier(upgrade).name}")
            row, column = divmod(index, 2)
            self.feature_grid.addWidget(mark, row, column * 2)
            self.feature_grid.addWidget(label, row, column * 2 + 1)

    # -- actions -----------------------------------------------------------
    def open_activation(self) -> None:
        dialog = ActivationDialog(self, runner=JobRunner(self))
        dialog.exec()
        self.refresh()
        if dialog.outcome:
            QMessageBox.information(
                self, "Thanks",
                "Trial started — you have 72 hours of everything."
                if dialog.outcome == "trial" else
                f"Activated. This computer is now on "
                f"{get_manager().status().tier_name}.")

    def check_now(self) -> None:
        """Force a refresh against the licence service, off the UI thread."""
        self.refresh_button.setEnabled(False)
        self.state.set_status("Checking licence…")

        def job(progress, on_event):
            try:
                get_manager().refresh()
            except LicenseError as exc:
                return {"error": str(exc)}
            return {"error": ""}

        def done(result):
            self.refresh_button.setEnabled(True)
            self.state.set_status("Ready")
            self.refresh()
            problem = (result or {}).get("error")
            if problem:
                QMessageBox.warning(self, "Licence check", problem)

        runner = JobRunner(self)
        runner.finished.connect(done)
        runner.failed.connect(lambda message: done({"error": message}))
        runner.start(job)

    def deactivate(self) -> None:
        answer = QMessageBox.question(
            self, "Deactivate this computer",
            "This hands the seat back so another computer can use it.\n\n"
            "Your scraped data and settings stay where they are. You can "
            "activate again with the same key at any time.\n\nContinue?")
        if answer != QMessageBox.Yes:
            return

        def job(progress, on_event):
            try:
                get_manager().deactivate()
            except LicenseError as exc:
                # Falling back to a local-only release: a customer who cannot
                # reach the service must still be able to leave a machine
                # behind. The seat is reclaimed server-side when support asks,
                # or by the customer from the account page.
                get_manager().deactivate(local_only=True)
                return {"warning": str(exc)}
            return {"warning": ""}

        def done(result):
            self.refresh()
            warning = (result or {}).get("warning")
            if warning:
                QMessageBox.information(
                    self, "Deactivated locally",
                    f"{warning}\n\nThis computer has been released here, but "
                    "the licence service has not been told yet. If the seat "
                    "still shows as used, contact support.")

        runner = JobRunner(self)
        runner.finished.connect(done)
        runner.failed.connect(lambda message: done({"warning": message}))
        runner.start(job)

    def buy(self, tier_key: str) -> None:
        """Ask the service for a checkout link and open it in a browser.

        Payment happens on Stripe's pages, in the customer's own browser —
        never inside this window. Card details should never touch an app that
        does not need them, and a hosted page is what keeps this product out of
        PCI scope entirely.
        """
        sku = f"{tier_key}-{plans.SUBSCRIPTION}-{plans.MONTHLY}"

        def job(progress, on_event):
            try:
                return {"url": get_manager().checkout_url(sku), "error": ""}
            except LicenseError as exc:
                return {"url": "", "error": str(exc)}

        def done(result):
            url = (result or {}).get("url")
            if url:
                webbrowser.open(url)
                QMessageBox.information(
                    self, "Checkout opened",
                    "Finish the purchase in your browser. Your licence key "
                    "arrives by email — paste it into “Activate a key”.")
                return
            # No link: fall back to the public pricing page rather than
            # leaving someone who wants to pay with nowhere to go.
            open_pricing_page(sku)

        runner = JobRunner(self)
        runner.finished.connect(done)
        runner.failed.connect(lambda _message: open_pricing_page(sku))
        runner.start(job)


def _date(stamp: Optional[float]) -> str:
    if not stamp:
        return "—"
    return time.strftime("%d %b %Y", time.localtime(stamp))
