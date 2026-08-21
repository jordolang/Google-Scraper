"""Application shell: the window, the navigation rail, and the page stack."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Dict

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QStackedWidget, QWidget

from . import runtime, theme
from .pages import Page
from .pages.dashboard import DashboardPage
from .pages.help_page import HelpPage
from .pages.listings import ListingsPage
from .pages.logs import LogsPage
from .pages.outreach import OutreachPage
from .pages.settings_page import SettingsPage
from .pages.tools import ToolsPage
from .pages.website_scraper import WebsiteScraperPage
from .state import AppState
from .widgets.sidebar import Sidebar, brand_mark

APP_TITLE = "Local Lead Scraper Pro"


def app_version() -> str:
    """The repo's VERSION file, when it travelled with the app."""
    for candidate in (runtime.bundle_dir() / "VERSION",
                      Path(__file__).resolve().parent.parent / "VERSION"):
        try:
            return candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
    return ""


class MainWindow(QMainWindow):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state
        version = app_version()
        self.setWindowTitle(f"{APP_TITLE}{f'  v{version}' if version else ''}")
        self.setWindowIcon(QIcon(brand_mark(64)))
        self.resize(1280, 820)
        self.setMinimumSize(1080, 680)

        central = QWidget()
        central.setObjectName("Workspace")
        central.setAttribute(Qt.WA_StyledBackground, True)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar()
        self.stack = QStackedWidget()
        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        # -- pages ---------------------------------------------------------
        self.pages: Dict[str, Page] = {
            "dashboard": DashboardPage(state),
            "listings": ListingsPage(state),
            "scraper": WebsiteScraperPage(state),
            "outreach": OutreachPage(state),
            "settings": SettingsPage(state),
            "tools": ToolsPage(state),
            "logs": LogsPage(state),
            "help": HelpPage(state),
        }
        for page in self.pages.values():
            self.stack.addWidget(page)

        self.sidebar.navigated.connect(self.go_to)
        state.status_changed.connect(self._on_status)
        state.settings_changed.connect(self._apply_license)

        # Pages ask each other for the spotlight — "Go to Website Scraper".
        for page in self.pages.values():
            if hasattr(page, "navigate_requested"):
                page.navigate_requested.connect(self.go_to)

        self._apply_license()
        self.go_to("dashboard")

    # -- navigation --------------------------------------------------------
    def go_to(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        self.sidebar.select(key)
        self.stack.setCurrentWidget(page)
        page.on_show()

    def _on_status(self, text: str) -> None:
        tone = "idle"
        lowered = text.lower()
        if any(word in lowered for word in ("scraping", "sending", "scanning", "looking")):
            tone = "busy"
        elif any(word in lowered for word in ("failed", "error", "stopped")):
            tone = "bad"
        self.sidebar.set_status(text, tone)

    def _apply_license(self) -> None:
        self.sidebar.set_license(
            str(self.state.settings.get("license_tier", "Pro")),
            str(self.state.settings.get("license_expires", "—")),
        )

    # -- lifecycle ---------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        for page in self.pages.values():
            try:
                page.on_close()
            except Exception:  # noqa: BLE001 - closing must not raise
                pass
        self.state.persist()
        super().closeEvent(event)


def build_app(argv=None) -> tuple[QApplication, MainWindow]:
    """Create the QApplication + window without entering the event loop.

    Split out so tests (and the smoke check in CI) can build the whole UI
    offscreen and assert on it.
    """
    argv = list(argv if argv is not None else sys.argv)
    runtime.prepare()
    existing = QApplication.instance()
    app = existing or QApplication(argv)
    app.setApplicationName(APP_TITLE)
    app.setOrganizationName("Jlang.dev")
    app.setStyle("Fusion")
    app.setStyleSheet(theme.stylesheet())

    state = AppState()
    if "--demo" in argv:
        # A command-line override lasts for this run only. Persisting it would
        # leave every later launch quietly in demo mode.
        state.settings["demo_mode"] = True
        state.ephemeral.add("demo_mode")
    window = MainWindow(state)
    return app, window


#: Modules the app imports only when a feature is actually used — lazily,
#: inside functions, so a packaged build can be missing them and still start.
#: Every entry here has burned us or could: selenium resolves its chrome
#: classes through a lazy string map that PyInstaller cannot follow, so a
#: bundle can launch happily and then fail the moment Start Scraping is
#: pressed. Importing them up front is what turns that into a build failure.
RUNTIME_IMPORTS = (
    "selenium",
    "selenium.webdriver",
    "selenium.webdriver.chrome.webdriver",
    "selenium.webdriver.chrome.options",
    "selenium.webdriver.chrome.service",
    "selenium.webdriver.common.by",
    "selenium.webdriver.common.keys",
    "selenium.webdriver.support.ui",
    "selenium.webdriver.support.expected_conditions",
    "selenium.common.exceptions",
    "bs4",
    "lxml.etree",
    "google_maps_scraper",
    "contact_scraper",
    "phone_lookup",
    "generate_emails",
    "send_emails",
    "data_store",
    "industries",
    "pricing_store",
    "email_config",
    "tui.pitch_script",
    "salescall.objections",
    "smtplib",
    "email.mime.multipart",
    "email.mime.text",
    "csv",
    "zipfile",
    "webbrowser",
)


def _check_runtime_imports() -> list:
    """Import everything the app reaches for lazily, and build a ChromeOptions.

    A missing module here means a packaged app that starts fine and then dies
    on the first real action.
    """
    problems = []
    for name in RUNTIME_IMPORTS:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - that is the thing being tested
            problems.append(f"import {name}: {type(exc).__name__}: {exc}")

    # The scrapers all start by configuring Chrome. Constructing the options
    # object exercises selenium's lazy attribute map for real, which naming
    # the submodules alone does not.
    try:
        from selenium import webdriver

        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"webdriver.ChromeOptions(): {type(exc).__name__}: {exc}")
    return problems


def _check_pipeline_runs() -> list:
    """Drive a whole demo run: search, scan, compose, export.

    This is the app's actual job. It touches the CSV writer, the email
    template renderer, the industry classifier and the pricing store, so a
    bundle missing any of them fails here rather than in front of a customer.
    """
    import tempfile

    problems = []
    try:
        from tui.pipeline import DemoPipeline

        from . import services

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pipeline = DemoPipeline(data_root=root)
            businesses = pipeline.search("Roofing Contractors", "Columbus, OH")
            if not businesses:
                problems.append("demo search returned nothing")
            pipeline.scrape_contacts(businesses)
            if pipeline.last_listings_csv is None or not pipeline.last_listings_csv.exists():
                problems.append("the run wrote no listings CSV")

            with_email = [b for b in businesses if b.has_email]
            if not with_email:
                problems.append("the demo scan produced no email addresses")
            else:
                message = pipeline.build_message(with_email[0])
                if "<" not in message.html or not message.subject:
                    problems.append("composing an email produced no rendered HTML")

            csv_path = root / "selftest.csv"
            services.export_csv(csv_path, ["name"], [{"name": "Acme"}])
            xlsx_path = root / "selftest.xlsx"
            services.export_xlsx(xlsx_path, ["name"], [{"name": "Acme"}])
            for path in (csv_path, xlsx_path):
                if not path.exists() or not path.stat().st_size:
                    problems.append(f"export produced no {path.suffix} file")
    except Exception as exc:  # noqa: BLE001 - that is the thing being tested
        problems.append(f"demo pipeline: {type(exc).__name__}: {exc}")
    return problems


def selftest(argv=None) -> int:
    """Build the whole UI offscreen, visit every page, and report.

    The packaged build runs this in CI (``LocalLeadScraperPro.exe --selftest``)
    so a bundle that is missing a module or an asset fails the build instead of
    failing on someone's desk.
    """
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app, window = build_app(list(argv or []))
    window.show()
    problems = []
    for key in window.sidebar.keys():
        try:
            window.go_to(key)
            app.processEvents()
        except Exception as exc:  # noqa: BLE001 - that is the thing being tested
            problems.append(f"{key}: {type(exc).__name__}: {exc}")
    problems.extend(_check_runtime_imports())
    problems.extend(_check_pipeline_runs())

    # The assets the app cannot work without.
    from . import runtime

    # Look at the directory itself: available_templates() falls back to the
    # full industry list when the folder is missing, which would let an
    # unusable bundle pass this check.
    templates = runtime.user_asset("email_templates")
    rendered = sorted(Path(templates).glob("*.html")) if Path(templates).is_dir() else []
    if not rendered:
        problems.append(f"no email templates in {templates}")
    if not runtime.bundle_dir().exists():
        problems.append("bundle directory missing")
    for line in problems:
        print(f"FAIL {line}", file=sys.stderr)
    if problems:
        return 1
    print(f"OK  {len(window.pages)} pages, {len(rendered)} templates, "
          f"{len(RUNTIME_IMPORTS)} runtime imports, demo pipeline ran, "
          f"data dir {runtime.working_dir()}")
    return 0


def main(argv=None) -> int:
    """Entry point for ``python -m gui`` and for the packaged executable."""
    # Qt's default rounding makes 125%-scaled Windows desktops look soft.
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    if argv is None:
        argv = sys.argv
    if "--selftest" in argv:
        return selftest(argv)
    app, window = build_app(argv)
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
