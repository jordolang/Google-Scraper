"""Tools — the utilities that do not belong to one screen."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLineEdit, QMessageBox,
)

from .. import services
from ..widgets.common import Card, DataTable, Field, button, hint, title
from ..workers import JobRunner
from . import Page


class ToolsPage(Page):
    heading = "Tools"

    def __init__(self, state, parent=None) -> None:
        super().__init__(state, parent)
        self.runner = JobRunner(self)
        self.root().addWidget(title("TOOLS"))

        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(self._build_phone_lookup(), 1)
        row.addWidget(self._build_pricing(), 1)
        self.root().addLayout(row)

        self.root().addWidget(self._build_import(), 1)

        self._lookup_failed = False
        self.runner.message.connect(lambda line: state.log("tools", line))
        self.runner.ended.connect(self._on_ended)
        self.runner.failed.connect(self._on_failed)

    # -- phone lookup ------------------------------------------------------
    def _build_phone_lookup(self) -> Card:
        card = Card("Find Missing Phone Numbers")
        card.add(hint(
            "Searches Google and Yellow Pages for every lead whose website scan "
            "came up empty, and writes what it finds back to the CSVs."))
        self.source = QComboBox()
        self.source.addItems(["Google + Yellow Pages", "Google only", "Yellow Pages only"])
        card.add(Field("Sources", self.source))
        self.lookup_button = button("Look Up Missing Numbers", "Primary")
        self.lookup_button.clicked.connect(self.find_phones)
        card.add(self.lookup_button)
        self.lookup_status = hint("")
        card.add(self.lookup_status)
        card.body().addStretch(1)
        return card

    def find_phones(self) -> None:
        if self.runner.running:
            return
        targets = [lead for lead in self.state.leads
                   if not lead.business.has_contact_info]
        if not targets:
            QMessageBox.information(self, "Nothing to look up",
                                    "Every lead already has contact information.")
            return
        sources = {
            0: ("google", "yellowpages"),
            1: ("google",),
            2: ("yellowpages",),
        }[self.source.currentIndex()]
        pipeline = self.state.make_pipeline()
        # Numbers found here have to reach the file the leads came from,
        # otherwise a lookup after an import updates nothing the user can see.
        if self.state.listings_csv:
            pipeline.last_listings_csv = self.state.listings_csv
        businesses = [lead.business for lead in targets]
        self._lookup_failed = False
        self.lookup_button.setEnabled(False)
        self.lookup_status.setText(f"Looking up {len(targets)} number(s)…")
        self.state.set_status("Looking up numbers…")

        def job(progress, on_event):
            return pipeline.find_phones(businesses, sources=sources,
                                        progress=progress, on_event=on_event)

        self.runner.start(job)

    def _on_failed(self, message: str) -> None:
        self._lookup_failed = True
        self.state.log("tools", f"ERROR {message}")
        QMessageBox.critical(
            self, "Lookup failed", f"{message}\n\n{services.explain_failure(message)}")

    def _on_ended(self) -> None:
        self.lookup_button.setEnabled(True)
        # `ended` fires after `failed`, so it must not paint over the failure.
        if self._lookup_failed:
            self.lookup_status.setText("Failed — see the Logs page.")
            self.state.set_status("Lookup failed")
        else:
            self.lookup_status.setText("Done — see the Logs page for details.")
            self.state.set_status("Ready")
        self.state.leads_changed.emit()

    # -- pricing -----------------------------------------------------------
    def _build_pricing(self) -> Card:
        card = Card("Package Pricing")
        card.add(hint(
            "The prices the email templates and call scripts quote. Stored in "
            "pricing.json and shared with the terminal app."))
        self.pricing_industry = QComboBox()
        self.pricing_fields = {}
        try:
            import industries
            import pricing_store

            self.pricing_industry.addItems([label for label, _key in industries.choices()])
            grid = QGridLayout()
            grid.setHorizontalSpacing(12)
            for index, field in enumerate(pricing_store.PACKAGE_FIELDS):
                edit = QLineEdit()
                self.pricing_fields[field] = edit
                grid.addWidget(Field(pricing_store.FIELD_LABELS[field], edit),
                               index // 2, index % 2)
            card.add(Field("Industry", self.pricing_industry))
            card.add_layout(grid)
            self.pricing_industry.currentIndexChanged.connect(self._load_pricing)
            save = button("Save Pricing", "Primary")
            save.clicked.connect(self._save_pricing)
            card.add(save)
            self._load_pricing()
        except Exception as exc:  # pragma: no cover - pricing is optional
            card.add(hint(f"Pricing is unavailable: {exc}"))
        card.body().addStretch(1)
        return card

    def _industry_key(self) -> str:
        import industries

        choices = industries.choices()
        index = max(0, self.pricing_industry.currentIndex())
        return choices[index][1] if index < len(choices) else "general"

    def _load_pricing(self) -> None:
        import pricing_store

        prices = pricing_store.prices_for(self._industry_key())
        for field, edit in self.pricing_fields.items():
            edit.setText(str(prices.get(field, "")))

    def _save_pricing(self) -> None:
        import pricing_store

        pricing = pricing_store.load_pricing()
        key = self._industry_key()
        pricing.setdefault(key, {})
        for field, edit in self.pricing_fields.items():
            pricing[key][field] = edit.text().strip()
        pricing_store.save_pricing(pricing)
        self.state.log("tools", f"Pricing saved for {key}.")
        QMessageBox.information(self, "Saved", "Pricing saved to pricing.json.")

    # -- import ------------------------------------------------------------
    def _build_import(self) -> Card:
        card = Card("Load a Previous Export")
        card.add(hint(
            "Pick any listings or contacts CSV this app (or the terminal app) "
            "wrote and carry on where it left off."))
        line = QHBoxLayout()
        self.import_path = QLineEdit()
        self.import_path.setPlaceholderText("Choose a CSV…")
        browse = button("Browse…")
        load = button("Load into App", "Primary")
        browse.clicked.connect(self._browse_csv)
        load.clicked.connect(self._load_csv)
        line.addWidget(self.import_path, 1)
        line.addWidget(browse)
        line.addWidget(load)
        card.add_layout(line)

        self.preview = DataTable(["Business Name", "Phone", "Email", "Website"],
                                 checkable=False, stretch_column=3)
        card.add(self.preview, 1)
        open_folder = button("Open Data Folder")
        open_folder.clicked.connect(self._open_data_folder)
        card.add(open_folder)
        return card

    def _browse_csv(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, "Choose a CSV",
            str(services.default_export_dir(self.state.settings)), "CSV files (*.csv)")
        if path:
            self.import_path.setText(path)
            self._preview_csv(Path(path))

    def _rows_from(self, path: Path):
        import csv

        with path.open(newline="", encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle))

    def _preview_csv(self, path: Path) -> None:
        try:
            rows = self._rows_from(path)
        except OSError as exc:
            QMessageBox.critical(self, "Could not read that file", str(exc))
            return
        self.preview.set_rows([
            [row.get("name", ""), row.get("scraped_phone") or row.get("phone", ""),
             row.get("email", ""), row.get("website", "")]
            for row in rows[:200]
        ])

    def _load_csv(self) -> None:
        path = Path(self.import_path.text().strip())
        if not path.is_file():
            QMessageBox.warning(self, "Pick a file", "Choose a CSV to load first.")
            return
        from tui.models import Business

        try:
            rows = self._rows_from(path)
        except OSError as exc:
            QMessageBox.critical(self, "Could not read that file", str(exc))
            return
        import data_store

        businesses = []
        for row in rows:
            if not row.get("name"):
                continue
            business = Business.from_dict(row)
            # A row that already carries contact details has been scanned.
            business.scanned = bool(business.emails or business.phones
                                    or business.contact_names)
            # And one that was emailed stays emailed — otherwise re-loading an
            # export puts delivered leads back into the call queue and the
            # next campaign.
            business.emailed = data_store.was_emailed(row)
            businesses.append(business)
        added = self.state.add_businesses(
            businesses, businesses[0].search_term if businesses else "Imported")
        # Remember where they came from so a later phone lookup writes back
        # into the same file.
        if "listings" in path.name.lower():
            self.state.listings_csv = path
        self.state.log("tools", f"Loaded {len(added)} lead(s) from {path}")
        QMessageBox.information(
            self, "Loaded",
            f"Added {len(added)} new lead(s).\n"
            f"{len(businesses) - len(added)} were already in the list.")

    def _open_data_folder(self) -> None:
        path = services.default_export_dir(self.state.settings)
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def on_close(self) -> None:
        if self.runner.running:
            self.runner.stop()
            self.runner.wait(4000)
