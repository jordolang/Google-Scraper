"""Settings — accounts, browser behaviour, storage and pricing."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFileDialog, QGridLayout, QHBoxLayout, QLineEdit,
    QMessageBox, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from .. import services, settings_store
from ..widgets.common import Card, Field, button, checkbox, hint, title
from ..workers import JobRunner
from . import Page


class SettingsPage(Page):
    heading = "Settings"

    def __init__(self, state, parent=None) -> None:
        super().__init__(state, parent)
        self.root().addWidget(title("SETTINGS"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        inner.setObjectName("Workspace")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(12)
        layout.addWidget(self._build_sender())
        layout.addWidget(self._build_scraping())
        layout.addWidget(self._build_storage())
        layout.addWidget(self._build_license())
        layout.addStretch(1)
        scroll.setWidget(inner)
        self.root().addWidget(scroll, 1)

        actions = QHBoxLayout()
        self.save_button = button("Save Settings", "Primary")
        self.reset_button = button("Reset to Defaults")
        self.open_config_button = button("Open Settings Folder")
        self.save_button.clicked.connect(self.save)
        self.reset_button.clicked.connect(self.reset)
        self.open_config_button.clicked.connect(self.open_config_dir)
        actions.addWidget(hint(f"Stored in {settings_store.config_path()}"))
        actions.addStretch(1)
        actions.addWidget(self.open_config_button)
        actions.addWidget(self.reset_button)
        actions.addWidget(self.save_button)
        self.root().addLayout(actions)

        # The SMTP test runs on a worker thread; these carry its result back.
        self.runner = JobRunner(self)
        self._tested_sender = None
        self._tested_password = ""
        self.runner.message.connect(lambda line: self.state.log("settings", line))
        self.runner.finished.connect(self._on_test_finished)
        self.runner.failed.connect(self._on_test_failed)
        self.runner.ended.connect(self._on_test_ended)
        self.load()

    # -- sections ----------------------------------------------------------
    def _build_sender(self) -> Card:
        card = Card("Email Account")
        self.from_email = QLineEdit()
        self.reply_to = QLineEdit()
        self.smtp_username = QLineEdit()
        self.smtp_username.setPlaceholderText("Defaults to the From address")
        self.smtp_username.setToolTip(
            "Some providers (iCloud custom domains especially) want the account "
            "that owns the domain here, not the alias in the From: header.")
        self.smtp_server = QLineEdit()
        self.smtp_server.setPlaceholderText("Auto-detected from the address")
        self.smtp_port = QSpinBox()
        self.smtp_port.setRange(0, 65535)
        self.smtp_port.setSpecialValueText("Auto")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("Kept in memory for this session only")

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.addWidget(Field("From Email", self.from_email), 0, 0)
        grid.addWidget(Field("Reply To", self.reply_to), 0, 1)
        grid.addWidget(Field("SMTP Username", self.smtp_username), 1, 0)
        grid.addWidget(Field("App-Specific Password", self.password), 1, 1)
        grid.addWidget(Field("SMTP Server", self.smtp_server), 2, 0)
        grid.addWidget(Field("SMTP Port", self.smtp_port), 2, 1)
        card.add_layout(grid)
        card.add(hint(
            "The password is never written to disk. Set EMAIL_PASSWORD in a .env "
            "file next to the app to have it loaded automatically."))
        self.test_button = button("Test Connection")
        self.test_button.clicked.connect(self.test_connection)
        card.add(self.test_button)
        return card

    def _build_scraping(self) -> Card:
        card = Card("Scraping")
        self.headless = checkbox("Run Chrome headless (no visible browser window)", True)
        self.demo_mode = checkbox(
            "Demo mode — use built-in sample data instead of a real browser", False)
        self.demo_mode.setToolTip(
            "Lets you explore every screen with no Chrome, network or credentials.")
        self.scan_delay = QDoubleSpinBox()
        self.scan_delay.setDecimals(1)
        self.scan_delay.setRange(0.0, 30.0)
        self.scan_delay.setSingleStep(0.5)
        self.scan_delay.setSuffix(" seconds")
        self.max_results = QSpinBox()
        self.max_results.setRange(1, 1000)
        card.add(self.headless)
        card.add(self.demo_mode)
        line = QHBoxLayout()
        line.addWidget(Field("Pause Between Websites", self.scan_delay))
        line.addWidget(Field("Default Max Results per Industry", self.max_results))
        line.addStretch(1)
        card.add_layout(line)
        return card

    def _build_storage(self) -> Card:
        card = Card("Storage")
        self.data_root = QLineEdit()
        self.data_root.setPlaceholderText("Default: the data/ folder beside the app")
        browse = button("Browse…")
        browse.clicked.connect(self._browse_data_root)
        open_folder = button("Open Data Folder")
        open_folder.clicked.connect(self._open_data_root)
        line = QHBoxLayout()
        line.addWidget(Field("Export Folder", self.data_root), 1)
        column = QVBoxLayout()
        column.addSpacing(15)
        buttons = QHBoxLayout()
        buttons.addWidget(browse)
        buttons.addWidget(open_folder)
        column.addLayout(buttons)
        line.addLayout(column)
        card.add_layout(line)
        card.add(hint(
            "Every run files its CSVs under <export folder>/<search term>/<location>/."))
        return card

    def _build_license(self) -> Card:
        card = Card("License")
        self.license_tier = QComboBox()
        self.license_tier.addItems(["Pro", "Standard", "Trial"])
        self.license_expires = QLineEdit()
        line = QHBoxLayout()
        line.addWidget(Field("Tier", self.license_tier))
        line.addWidget(Field("Expires", self.license_expires))
        line.addStretch(1)
        card.add_layout(line)
        card.add(hint("Shown in the sidebar; this build does not enforce licensing."))
        return card

    # -- load / save -------------------------------------------------------
    def load(self) -> None:
        s = self.state.settings
        self.from_email.setText(str(s.get("from_email", "")))
        self.reply_to.setText(str(s.get("reply_to", "")))
        self.smtp_username.setText(str(s.get("smtp_username", "")))
        self.smtp_server.setText(str(s.get("smtp_server", "")))
        self.smtp_port.setValue(int(s.get("smtp_port", 0) or 0))
        self.headless.setChecked(bool(s.get("headless", True)))
        self.demo_mode.setChecked(bool(s.get("demo_mode", False)))
        self.scan_delay.setValue(float(s.get("scan_delay", 1.0)))
        self.max_results.setValue(int(s.get("max_results", 50)))
        self.data_root.setText(str(s.get("data_root", "")))
        self.license_tier.setCurrentText(str(s.get("license_tier", "Pro")))
        self.license_expires.setText(str(s.get("license_expires", "")))
        self.password.setText(self.state.password)

    def save(self) -> None:
        self.state.password = self.password.text()
        path = self.state.update_settings(
            from_email=self.from_email.text().strip(),
            reply_to=self.reply_to.text().strip(),
            smtp_username=self.smtp_username.text().strip(),
            smtp_server=self.smtp_server.text().strip(),
            smtp_port=int(self.smtp_port.value()),
            headless=self.headless.isChecked(),
            demo_mode=self.demo_mode.isChecked(),
            scan_delay=float(self.scan_delay.value()),
            max_results=int(self.max_results.value()),
            data_root=self.data_root.text().strip(),
            license_tier=self.license_tier.currentText(),
            license_expires=self.license_expires.text().strip(),
        )
        if path is None:
            self.state.log("settings", "Could not write the settings file.")
            QMessageBox.warning(
                self, "Not saved",
                f"The settings file could not be written to\n"
                f"{settings_store.config_path()}\n\n"
                "The values are active for this session only.")
            return
        self.state.log("settings", f"Settings saved to {path}.")
        QMessageBox.information(self, "Saved", "Settings saved.")

    def reset(self) -> None:
        if QMessageBox.question(self, "Reset settings",
                                "Restore every setting to its default?") != QMessageBox.Yes:
            return
        self.state.settings.update(settings_store.DEFAULTS)
        settings_store.save(self.state.settings)
        self.state.settings_changed.emit()
        self.load()

    # -- actions -----------------------------------------------------------
    def _browse_data_root(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Choose export folder",
            self.data_root.text() or str(services.default_export_dir(self.state.settings)))
        if path:
            self.data_root.setText(path)

    def _open_data_root(self) -> None:
        path = Path(self.data_root.text().strip() or
                    services.default_export_dir(self.state.settings))
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def open_config_dir(self) -> None:
        path = settings_store.config_dir()
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def test_connection(self) -> None:
        """Log in to the SMTP server and hang up — no message is sent.

        On a thread: a TLS handshake against an unreachable server blocks for
        the whole socket timeout, and doing that on the GUI thread freezes the
        window.
        """
        if self.runner.running:
            return
        password = self.password.text() or self.state.password
        if not password:
            QMessageBox.warning(self, "No password",
                                "Enter the app-specific password first.")
            return
        from send_emails import EmailSender

        sender = EmailSender(
            from_email=self.from_email.text().strip() or "jordan@jlang.dev",
            smtp_server=self.smtp_server.text().strip() or None,
            smtp_port=int(self.smtp_port.value()) or None,
            smtp_username=self.smtp_username.text().strip() or None,
        )
        self._tested_sender = sender
        self._tested_password = password
        self.test_button.setEnabled(False)
        self.test_button.setText("Connecting…")
        self.state.set_status("Testing SMTP…")

        def job(progress, on_event):
            progress(f"Connecting to {sender.smtp_server}:{sender.smtp_port}…")
            ok = sender.connect(password)
            if ok:
                sender.disconnect()
            return bool(ok)

        self.runner.start(job)

    def _on_test_finished(self, ok) -> None:
        sender = self._tested_sender
        if sender is None:
            return
        if ok:
            self.state.password = self._tested_password
            QMessageBox.information(
                self, "Connected",
                f"Authenticated with {sender.smtp_server}:{sender.smtp_port}.")
        else:
            QMessageBox.critical(
                self, "Could not connect",
                f"{sender.smtp_server}:{sender.smtp_port} refused the login.\n\n"
                "For an iCloud custom domain, the username must be the Apple ID "
                "that owns the domain and the password an app-specific one.")

    def _on_test_failed(self, message: str) -> None:
        self.state.log("settings", f"SMTP test failed: {message}")
        QMessageBox.critical(self, "Could not connect", message)

    def _on_test_ended(self) -> None:
        self.test_button.setEnabled(True)
        self.test_button.setText("Test Connection")
        self.state.set_status("Ready")

    def on_show(self) -> None:
        self.load()

    def on_close(self) -> None:
        if self.runner.running:
            self.runner.stop()
            self.runner.wait(3000)
