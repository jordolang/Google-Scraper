"""End-to-end tests that drive the desktop window itself, in demo mode.

These build the real MainWindow offscreen and click through the same flow a
user would: search, select, scan, export, compose. Nothing touches the network,
a browser, or SMTP.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="the desktop app needs PySide6")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from gui.app import build_app, selftest  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("LLSP_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("LLSP_DATA_DIR", str(tmp_path / "appdata"))


class SilentMessageBox:
    """Stands in for QMessageBox: records what was asked, answers, returns.

    A real modal blocks the event loop forever with nobody there to click it.
    Prompts are answered "yes", so the tests follow the path a user who
    confirms would take.
    """

    Yes = QMessageBox.Yes
    No = QMessageBox.No
    Ok = QMessageBox.Ok
    calls: list = []

    @classmethod
    def _record(cls, kind, args):
        cls.calls.append((kind, [arg for arg in args if isinstance(arg, str)]))

    @classmethod
    def information(cls, *args, **kwargs):
        cls._record("information", args)
        return cls.Ok

    @classmethod
    def warning(cls, *args, **kwargs):
        cls._record("warning", args)
        return cls.Ok

    @classmethod
    def critical(cls, *args, **kwargs):
        cls._record("critical", args)
        return cls.Ok

    @classmethod
    def question(cls, *args, **kwargs):
        cls._record("question", args)
        return cls.Yes


@pytest.fixture(autouse=True)
def no_modal_dialogs(monkeypatch):
    """Swap QMessageBox out in every page module for the duration of a test."""
    import importlib
    import pkgutil

    import gui.pages

    SilentMessageBox.calls = []
    modules = [gui.pages]
    for info in pkgutil.iter_modules(gui.pages.__path__):
        modules.append(importlib.import_module(f"gui.pages.{info.name}"))
    for module in modules:
        if hasattr(module, "QMessageBox"):
            monkeypatch.setattr(module, "QMessageBox", SilentMessageBox)
    return SilentMessageBox


@pytest.fixture
def window(qapp, tmp_path):
    _app, window = build_app([])
    window.state.settings["demo_mode"] = True
    window.state.settings["data_root"] = str(tmp_path / "exports")
    window.resize(1280, 820)
    window.show()
    yield window
    for page in window.pages.values():
        page.on_close()
    window.close()


def pump(msecs: int = 30) -> None:
    loop = QEventLoop()
    QTimer.singleShot(msecs, loop.quit)
    loop.exec()


def drain(runner, timeout_ms: int = 60000) -> None:
    waited = 0
    while runner.running and waited < timeout_ms:
        pump(50)
        waited += 50
    pump(100)
    assert not runner.running, "job did not finish in time"


def run_search(window, terms="Roofing Contractors, Plumbers") -> None:
    dashboard = window.pages["dashboard"]
    dashboard.location.setText("Columbus, Ohio, USA")
    dashboard.industry.setCurrentText(terms)
    dashboard.start()
    drain(dashboard.runner)


# --------------------------------------------------------------------------- #
#  shell
# --------------------------------------------------------------------------- #
def test_every_sidebar_destination_opens(window):
    for key in window.sidebar.keys():
        window.go_to(key)
        pump(10)
        assert window.stack.currentWidget() is window.pages[key]


def test_selftest_entry_point_passes():
    assert selftest([]) == 0


# --------------------------------------------------------------------------- #
#  search
# --------------------------------------------------------------------------- #
def test_search_fills_a_tab_per_industry(window):
    run_search(window)
    dashboard = window.pages["dashboard"]

    assert window.state.industries() == ["Roofing Contractors", "Plumbers"]
    assert dashboard.tabs.count() == 2
    assert dashboard.stat_industries.value.text() == "2"
    assert dashboard.progress.value() == 100
    assert "Completed" in dashboard.stat_status.value.text()
    # Each industry produced its own set of businesses.
    assert len(window.state.leads) == 10
    assert len(dashboard._rows) == 5  # only the visible tab's rows


def test_search_writes_a_listings_csv(window, tmp_path):
    run_search(window, "Roofing Contractors")
    exports = list((tmp_path / "exports").rglob("listings*.csv"))
    assert exports, "the run should have exported its listings"
    assert "Roofing" in exports[0].read_text(encoding="utf-8")


def test_empty_industry_field_is_refused(window, no_modal_dialogs):
    dashboard = window.pages["dashboard"]
    dashboard.industry.setCurrentText("   ")
    dashboard.start()
    assert not dashboard.runner.running
    assert any(kind == "warning" for kind, _text in no_modal_dialogs.calls)


def test_select_all_flows_into_the_scraper(window):
    run_search(window, "Roofing Contractors")
    dashboard = window.pages["dashboard"]
    dashboard._set_all(True)
    pump(10)

    assert len(window.state.selected_leads()) == 5
    assert dashboard.next_button.isEnabled()
    assert "(5 Selected)" in dashboard.next_button.text()

    window.go_to("scraper")
    assert len(window.pages["scraper"]._targets) == 5


# --------------------------------------------------------------------------- #
#  website scan
# --------------------------------------------------------------------------- #
def test_scan_populates_contacts_and_insight_counts(window):
    run_search(window, "Roofing Contractors")
    window.pages["dashboard"]._set_all(True)
    window.go_to("scraper")

    scraper = window.pages["scraper"]
    scraper.start()
    drain(scraper.runner)

    scanned = window.state.scanned_leads()
    assert len(scanned) == 5
    assert any(lead.business.emails for lead in scanned)
    # The Live Progress panel adds up what the scan found.
    assert scraper.ov_completed.value.text() == "5"
    assert int(scraper.ov_points.value.text()) > 0
    assert scraper.progress.value() == 100
    # Category counts come off a business that actually had data.
    with_data = [lead for lead in scanned if lead.business.insights]
    assert with_data and with_data[0].business.insights["services"] > 0


def test_scan_can_be_stopped_midway(window):
    run_search(window, "Roofing Contractors")
    window.pages["dashboard"]._set_all(True)
    window.go_to("scraper")

    scraper = window.pages["scraper"]
    scraper.start()
    pump(120)
    scraper.stop()
    drain(scraper.runner)

    assert not scraper.runner.running
    assert scraper.start_button.isEnabled()  # the page is usable again


def test_scan_pause_toggles_the_control(window):
    run_search(window, "Roofing Contractors")
    window.pages["dashboard"]._set_all(True)
    window.go_to("scraper")
    scraper = window.pages["scraper"]
    scraper.start()
    pump(60)

    scraper.toggle_pause()
    assert scraper.runner.control.paused
    assert "Resume" in scraper.pause_button.text()
    scraper.toggle_pause()
    assert not scraper.runner.control.paused

    scraper.stop()
    drain(scraper.runner)


# --------------------------------------------------------------------------- #
#  grids
# --------------------------------------------------------------------------- #
def test_listings_filter_and_search_narrow_the_grid(window):
    run_search(window)
    window.go_to("listings")
    panel = window.pages["listings"].listings

    assert len(panel.matching()) == 10
    panel.search.setText("Plumber")
    assert panel.matching()
    assert all("plumber" in lead.business.name.lower()
               for lead in panel.matching())

    panel.search.clear()
    panel.filter.setCurrentIndex(1)  # "Has email" — nothing is scanned yet
    assert panel.matching() == []


def test_listings_pagination_splits_the_rows(window):
    run_search(window)
    window.go_to("listings")
    panel = window.pages["listings"].listings
    panel.page_size.setCurrentText("25")
    panel.refresh()
    assert panel.page_label.text() == "1 / 1"

    panel.page_size.setCurrentText("All")
    panel.refresh()
    assert len(panel._visible) == 10


def test_data_results_export_writes_every_matching_row(window, tmp_path, monkeypatch):
    run_search(window, "Roofing Contractors")
    window.pages["dashboard"]._set_all(True)
    window.go_to("scraper")
    window.pages["scraper"].start()
    drain(window.pages["scraper"].runner)

    target = tmp_path / "results.xlsx"
    monkeypatch.setattr(
        "gui.pages.listings.QFileDialog.getSaveFileName",
        staticmethod(lambda *args, **kwargs: (str(target), "")))

    panel = window.pages["listings"].results
    panel.refresh()
    panel.export("xlsx")
    assert target.exists() and target.stat().st_size > 0


# --------------------------------------------------------------------------- #
#  outreach
# --------------------------------------------------------------------------- #
def test_recipients_are_the_leads_with_an_email(window):
    run_search(window, "Roofing Contractors")
    window.pages["dashboard"]._set_all(True)
    window.go_to("scraper")
    window.pages["scraper"].start()
    drain(window.pages["scraper"].runner)

    window.go_to("outreach")
    campaigns = window.pages["outreach"].campaigns
    assert campaigns._recipients
    assert all(lead.business.has_email for lead in campaigns._recipients)


def test_dry_run_composes_without_sending(window):
    run_search(window, "Roofing Contractors")
    window.pages["dashboard"]._set_all(True)
    window.go_to("scraper")
    window.pages["scraper"].start()
    drain(window.pages["scraper"].runner)

    window.go_to("outreach")
    campaigns = window.pages["outreach"].campaigns
    campaigns.send_method.setCurrentIndex(1)  # dry run
    campaigns.delay.setValue(0)
    campaigns.send()
    drain(campaigns.runner)

    assert window.state.campaign_stats["sent"] == 0
    assert not any(lead.business.emailed for lead in window.state.leads)
    assert any("DRY RUN" in line for line in window.state.log_lines)


def test_call_scripts_walk_the_pitch(window):
    run_search(window, "Roofing Contractors")
    window.go_to("outreach")
    calls = window.pages["outreach"].calls

    assert calls.queue_picker.count() == 5
    assert calls._steps
    first = calls.guide_title.text()
    calls.go_step(1)
    assert calls.guide_title.text() != first
    assert calls.objection_picker.count() > 0
    assert "{" not in calls.objection_view.toPlainText()


def test_marking_a_call_complete_logs_it(window):
    run_search(window, "Roofing Contractors")
    window.go_to("outreach")
    calls = window.pages["outreach"].calls
    calls.notes.setPlainText("Asked me to call back Tuesday.")
    calls.mark_complete()

    assert any(lead.call_status == "called" for lead in window.state.leads)
    assert any("call" in line for line in window.state.log_lines)


# --------------------------------------------------------------------------- #
#  settings
# --------------------------------------------------------------------------- #
def test_settings_page_saves_and_reloads(window, tmp_path):
    settings = window.pages["settings"]
    settings.from_email.setText("someone@example.com")
    settings.headless.setChecked(False)
    settings.save()

    assert window.state.settings["from_email"] == "someone@example.com"
    assert window.state.settings["headless"] is False
    from gui import settings_store

    assert settings_store.load()["from_email"] == "someone@example.com"


def test_password_is_never_written_to_disk(window):
    settings = window.pages["settings"]
    settings.password.setText("hunter2-app-specific")
    settings.save()

    from gui import settings_store

    stored = settings_store.config_path().read_text(encoding="utf-8")
    assert "hunter2" not in stored
    assert window.state.password == "hunter2-app-specific"
