"""Settings — accounts, browser behaviour, storage and pricing."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from .. import runtime, services, settings_store
from ..widgets.common import Card, Field, button, checkbox, hint, title
from ..workers import JobRunner
from . import Page


class SettingsPage(Page):
    navigate_requested = Signal(str)
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
        layout.addWidget(self._build_deliverability())
        layout.addWidget(self._build_images())
        layout.addWidget(self._build_previews())
        layout.addWidget(self._build_scraping())
        layout.addWidget(self._build_storage())
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

    def _build_deliverability(self) -> Card:
        card = Card("Deliverability")
        self.send_via = QComboBox()
        self.send_via.addItem("Your email account (SMTP)", "smtp")
        self.send_via.addItem("Resend (recommended for volume)", "resend")
        self.resend_key = QLineEdit()
        self.resend_key.setEchoMode(QLineEdit.Password)
        self.resend_key.setPlaceholderText("re_…  (only needed when sending with Resend)")
        self.sender_name = QLineEdit()
        self.sender_address = QLineEdit()
        self.sender_address.setPlaceholderText("123 Main St, Columbus, OH 43215")
        self.unsubscribe_url = QLineEdit()
        self.unsubscribe_url.setPlaceholderText(
            "Only used without an unsubscribe site; blank = reply \"Unsubscribe\"")
        self.unsubscribe_site = QLineEdit()
        self.unsubscribe_site.setPlaceholderText("https://your-unsubscribe.vercel.app")
        self.unsubscribe_site.setToolTip(
            "The vercel/ folder of this project, deployed to Vercel. Each email "
            "links there with its own one-click unsubscribe link.")
        self.unsubscribe_secret = QLineEdit()
        self.unsubscribe_secret.setEchoMode(QLineEdit.Password)
        self.unsubscribe_secret.setPlaceholderText("Generate one, then paste it into Vercel too")
        self.unsubscribe_secret.setToolTip(
            "Signs every unsubscribe link so nobody can forge one. Must match "
            "UNSUBSCRIBE_SECRET in your Vercel project's environment variables.")
        self.generate_secret_button = button("Generate && Copy")
        self.generate_secret_button.setToolTip(
            "Makes a new signing secret, fills it in and copies it so you can "
            "paste it into Vercel.")
        self.generate_secret_button.clicked.connect(self._generate_secret)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.addWidget(Field("Send With", self.send_via), 0, 0)
        grid.addWidget(Field("Resend API Key", self.resend_key), 0, 1)
        grid.addWidget(Field("Your Name (signature and From)", self.sender_name), 1, 0)
        grid.addWidget(Field("Postal Address (email footer)", self.sender_address), 1, 1)
        grid.addWidget(Field("Unsubscribe Site (Vercel)", self.unsubscribe_site), 2, 0)
        secret_row = QHBoxLayout()
        secret_row.addWidget(Field("Unsubscribe Secret", self.unsubscribe_secret), 1)
        secret_column = QVBoxLayout()
        secret_column.addSpacing(15)
        secret_column.addWidget(self.generate_secret_button)
        secret_row.addLayout(secret_column)
        grid.addLayout(secret_row, 2, 1)
        grid.addWidget(Field("Fallback Unsubscribe Page", self.unsubscribe_url), 3, 0, 1, 2)
        card.add_layout(grid)
        card.add(hint(
            "Every email goes out with a plain-text copy, an unsubscribe header and "
            "a randomised gap between sends. With the unsubscribe site, its secret "
            "and a Vercel Blob token (Image Hosting) set, each email gets its own "
            "one-click unsubscribe link and anyone who unsubscribes is skipped "
            "automatically (setup: docs/unsubscribe.md). A postal address in the "
            "footer is required for commercial email in the US. API keys are kept "
            "in the app's own .env file, not in settings.json."))
        self.domain_button = button("Check My Domain")
        self.domain_button.setToolTip("Looks up SPF, DKIM and DMARC for your From address.")
        self.domain_button.clicked.connect(self.check_domain)
        card.add(self.domain_button)
        self.domain_result = QLabel("")
        self.domain_result.setWordWrap(True)
        self.domain_result.setTextFormat(Qt.RichText)
        self.domain_result.setStyleSheet("font-size: 12px;")
        card.add(self.domain_result)
        return card

    def _build_images(self) -> Card:
        card = Card("Image Hosting")
        self.blob_token = QLineEdit()
        self.blob_token.setEchoMode(QLineEdit.Password)
        self.blob_token.setPlaceholderText("vercel_blob_rw_…")
        self.blob_folder = QLineEdit()
        self.blob_folder.setPlaceholderText("email-images")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.addWidget(Field("Vercel Blob Read-Write Token", self.blob_token), 0, 0)
        grid.addWidget(Field("Folder", self.blob_folder), 0, 1)
        card.add_layout(grid)
        card.add(hint(
            "Images in an email have to live at a public web address. Website "
            "previews and images you add on the Outreach page are uploaded to your "
            "Vercel Blob store (Vercel → Storage → a store with Public access) and "
            "linked into each email. The same store keeps the unsubscribe list."))
        return card

    def _build_previews(self) -> Card:
        from site_preview import DEFAULT_MODEL, MODELS

        card = Card("Website Previews")
        self.hf_key_id = QLineEdit()
        self.hf_key_id.setPlaceholderText("API key ID")
        self.hf_key_secret = QLineEdit()
        self.hf_key_secret.setEchoMode(QLineEdit.Password)
        self.hf_key_secret.setPlaceholderText("API key secret")
        self.preview_model = QComboBox()
        for key, model in MODELS.items():
            self.preview_model.addItem(model.label, key)
        self.preview_model.setCurrentIndex(max(0, self.preview_model.findData(DEFAULT_MODEL)))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.addWidget(Field("Higgsfield API Key ID", self.hf_key_id), 0, 0)
        grid.addWidget(Field("Higgsfield API Key Secret", self.hf_key_secret), 0, 1)
        grid.addWidget(Field("Image Model", self.preview_model), 1, 0, 1, 2)
        card.add_layout(grid)
        card.add(hint(
            "Draws a screenshot of a new website for each business and puts it at the "
            "top of its email. Get a key at console.higgsfield.ai → API keys. Each "
            "image uses Higgsfield credits; previews are kept on your image host."))
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
        self.password.setText(self.state.password)
        runtime.load_env()
        index = self.send_via.findData(s.get("send_via", "smtp"))
        self.send_via.setCurrentIndex(max(0, index))
        self.resend_key.setText(os.environ.get("RESEND_API_KEY", ""))
        self.sender_name.setText(str(s.get("sender_name", "")))
        self.sender_address.setText(str(s.get("sender_address", "")))
        self.unsubscribe_url.setText(str(s.get("unsubscribe_url", "")))
        self.unsubscribe_site.setText(str(s.get("unsubscribe_site", "")))
        self.unsubscribe_secret.setText(os.environ.get("UNSUBSCRIBE_SECRET", ""))
        self.blob_folder.setText(str(s.get("blob_folder", "") or "email-images"))
        self.blob_token.setText(os.environ.get("BLOB_READ_WRITE_TOKEN", ""))
        self.hf_key_id.setText(os.environ.get("HF_API_KEY_ID", ""))
        self.hf_key_secret.setText(os.environ.get("HF_API_KEY_SECRET", ""))
        model = self.preview_model.findData(s.get("preview_model", ""))
        if model >= 0:
            self.preview_model.setCurrentIndex(model)

    def _generate_secret(self) -> None:
        """A new unsubscribe signing secret, filled in and on the clipboard."""
        from PySide6.QtWidgets import QApplication

        from opt_outs import new_secret

        if self.unsubscribe_secret.text().strip():
            answer = QMessageBox.question(
                self, "Replace the secret?",
                "Links in emails you've already sent stop working once the "
                "secret changes. Make a new one anyway?")
            if answer != QMessageBox.Yes:
                return
        secret = new_secret()
        self.unsubscribe_secret.setText(secret)
        QApplication.clipboard().setText(secret)
        QMessageBox.information(
            self, "Secret copied",
            "A new secret is filled in and copied to your clipboard.\n\n"
            "In Vercel, open your unsubscribe project → Settings → Environment "
            "Variables, add UNSUBSCRIBE_SECRET with this value, and redeploy. "
            "Then press Save here.")

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
            send_via=self.send_via.currentData() or "smtp",
            sender_name=self.sender_name.text().strip(),
            sender_address=self.sender_address.text().strip(),
            unsubscribe_url=self.unsubscribe_url.text().strip(),
            unsubscribe_site=self.unsubscribe_site.text().strip().rstrip("/"),
            blob_folder=self.blob_folder.text().strip().strip("/") or "email-images",
            preview_model=self.preview_model.currentData() or "",
        )
        try:
            runtime.save_env_values({
                "RESEND_API_KEY": self.resend_key.text().strip(),
                "BLOB_READ_WRITE_TOKEN": self.blob_token.text().strip().strip('"'),
                "UNSUBSCRIBE_SECRET": self.unsubscribe_secret.text().strip(),
                "HF_API_KEY_ID": self.hf_key_id.text().strip(),
                "HF_API_KEY_SECRET": self.hf_key_secret.text().strip(),
            })
        except OSError as exc:
            self.state.log("settings", f"Could not save API keys: {exc}")
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

    def check_domain(self) -> None:
        """Look up SPF, DKIM and DMARC for the From address, off the UI thread."""
        if self.runner.running:
            return
        import deliverability

        from_email = self.from_email.text().strip()
        smtp_server = self.smtp_server.text().strip()
        if not smtp_server and from_email:
            from send_emails import EmailSender

            smtp_server = EmailSender(from_email=from_email).smtp_server
        send_via = self.send_via.currentData() or "smtp"
        self._tested_sender = None
        self.domain_button.setEnabled(False)
        self.domain_result.setText("Checking DNS…")

        def job(progress, on_event):
            return deliverability.check_domain(
                from_email, smtp_server=smtp_server, send_via=send_via)

        self.runner.start(job)

    def _show_domain(self, checks) -> None:
        import html

        import deliverability

        marks = {"pass": ("✓", "#16a34a"), "warn": ("!", "#d97706"),
                 "fail": ("✕", "#dc2626")}
        rows = []
        for check in checks:
            mark, colour = marks.get(check.status, ("?", "#6b7280"))
            fix = (f'<br><span style="color:#6b7280;">Fix: {html.escape(check.fix)}</span>'
                   if check.fix and check.status != "pass" else "")
            rows.append(f'<p style="margin:0 0 6px 0;"><b style="color:{colour};">{mark} '
                        f'{html.escape(check.name)}</b> {html.escape(check.detail)}{fix}</p>')
        summary = html.escape(deliverability.summary(checks))
        self.domain_result.setText(f"<p><b>{summary}</b></p>" + "".join(rows))

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
        if isinstance(ok, list):
            self._show_domain(ok)
            return
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
        if not self.domain_button.isEnabled():
            self.domain_result.setText(f"Could not check the domain: {message}")
            return
        self.state.log("settings", f"SMTP test failed: {message}")
        QMessageBox.critical(self, "Could not connect", message)

    def _on_test_ended(self) -> None:
        self.domain_button.setEnabled(True)
        self.test_button.setEnabled(True)
        self.test_button.setText("Test Connection")
        self.state.set_status("Ready")

    def on_show(self) -> None:
        self.load()

    def on_close(self) -> None:
        if self.runner.running:
            self.runner.stop()
            self.runner.wait(3000)
