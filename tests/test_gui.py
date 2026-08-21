"""Tests for the desktop (PySide6) front end.

Everything runs on Qt's offscreen platform, so the suite needs no display and
behaves the same locally, in CI and inside the Windows build job.
"""

from __future__ import annotations

import os
import struct
import zipfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="the desktop app needs PySide6")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from gui import scripts, services, settings_store  # noqa: E402
from gui.state import AppState  # noqa: E402
from gui.workers import Cancelled, JobRunner, RunControl  # noqa: E402
from tui.models import Business  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Never touch the real %APPDATA% settings file."""
    monkeypatch.setenv("LLSP_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("LLSP_DATA_DIR", str(tmp_path / "appdata"))


def pump(msecs: int = 30) -> None:
    loop = QEventLoop()
    QTimer.singleShot(msecs, loop.quit)
    loop.exec()


def drain(runner: JobRunner, timeout_ms: int = 30000) -> None:
    """Spin the event loop until a background job finishes."""
    waited = 0
    while runner.running and waited < timeout_ms:
        pump(50)
        waited += 50
    pump(100)
    assert not runner.running, "job did not finish in time"


# --------------------------------------------------------------------------- #
#  settings
# --------------------------------------------------------------------------- #
def test_settings_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("LLSP_CONFIG_DIR", str(tmp_path / "cfg"))
    stored = settings_store.load()
    stored["location"] = "Dublin, OH"
    stored["max_results"] = 25
    assert settings_store.save(stored) is not None

    reloaded = settings_store.load()
    assert reloaded["location"] == "Dublin, OH"
    assert reloaded["max_results"] == 25
    # Unknown keys are dropped, missing ones backfilled from the defaults.
    assert reloaded["headless"] == settings_store.DEFAULTS["headless"]


def test_settings_survive_a_corrupt_file(tmp_path, monkeypatch):
    monkeypatch.setenv("LLSP_CONFIG_DIR", str(tmp_path / "cfg"))
    settings_store.config_path().parent.mkdir(parents=True)
    settings_store.config_path().write_text("{not json", encoding="utf-8")
    assert settings_store.load() == settings_store.DEFAULTS


# --------------------------------------------------------------------------- #
#  worker plumbing
# --------------------------------------------------------------------------- #
def test_run_control_pauses_and_stops():
    control = RunControl()
    control.checkpoint()  # a fresh control never blocks

    control.pause()
    assert control.paused
    control.resume()
    assert not control.paused

    control.stop()
    assert control.stopping
    with pytest.raises(Cancelled):
        control.checkpoint()


def test_job_runner_streams_then_finishes(qapp):
    runner = JobRunner()
    lines, results = [], []
    runner.message.connect(lines.append)
    runner.finished.connect(results.append)

    def job(progress, on_event):
        for index in range(3):
            progress(f"step {index}")
        return "done"

    assert runner.start(job)
    drain(runner)
    assert lines == ["step 0", "step 1", "step 2"]
    assert results == ["done"]


def test_job_runner_reports_failure_without_raising(qapp):
    runner = JobRunner()
    failures = []
    runner.failed.connect(failures.append)

    def job(progress, on_event):
        raise ValueError("boom")

    runner.start(job)
    drain(runner)
    assert failures and "boom" in failures[0]


def test_job_runner_stop_cancels_mid_run(qapp):
    runner = JobRunner()
    cancelled = []
    runner.cancelled.connect(lambda: cancelled.append(True))
    seen = []

    def job(progress, on_event):
        import time

        for index in range(200):
            progress(str(index))
            seen.append(index)
            time.sleep(0.01)
        return "never gets here"

    runner.start(job)
    pump(80)
    runner.stop()
    drain(runner)
    assert cancelled == [True]
    assert len(seen) < 200  # it really was interrupted


# --------------------------------------------------------------------------- #
#  shared state
# --------------------------------------------------------------------------- #
def test_state_merges_and_deduplicates(qapp):
    state = AppState()
    added = state.add_businesses(
        [Business(name="Acme", address="1 Main"), Business(name="Beta", address="2 Oak")],
        "Roofers")
    assert len(added) == 2
    # The same business from a second search is not added twice.
    again = state.add_businesses([Business(name="Acme", address="1 Main")], "Roofers")
    assert again == []
    assert len(state.leads) == 2


def test_state_buckets_leads_by_industry(qapp):
    state = AppState()
    state.add_businesses([Business(name="A", address="1")], "Roofers")
    state.add_businesses([Business(name="B", address="2")], "Plumbers")
    assert state.industries() == ["Roofers", "Plumbers"]
    assert [lead.business.name for lead in state.leads_for("Plumbers")] == ["B"]


def test_state_call_queue_skips_emailed_and_numberless(qapp):
    state = AppState()
    state.add_businesses([
        Business(name="Callable", address="1", phone="(614) 555-0100"),
        Business(name="Emailed", address="2", phone="(614) 555-0101", emailed=True),
        Business(name="No number", address="3"),
    ], "Roofers")
    assert [lead.business.name for lead in state.callable_leads()] == ["Callable"]


def test_state_log_is_bounded(qapp):
    state = AppState()
    for index in range(5200):
        state.log("test", f"line {index}")
    assert len(state.log_lines) <= 5000


# --------------------------------------------------------------------------- #
#  exports
# --------------------------------------------------------------------------- #
def test_csv_export_writes_a_header_and_rows(tmp_path):
    path = services.export_csv(
        tmp_path / "out.csv", ["Name", "Email"], [["Acme", "a@b.c"]])
    text = path.read_text(encoding="utf-8-sig")
    assert text.splitlines()[0] == "Name,Email"
    assert "Acme,a@b.c" in text


def test_xlsx_export_is_a_readable_workbook(tmp_path):
    path = services.export_xlsx(
        tmp_path / "out.xlsx", ["Name", "Notes"],
        [["Beta & Co", 'He said "hi"'], ["Gamma", None]])
    with zipfile.ZipFile(path) as book:
        names = set(book.namelist())
        assert {"[Content_Types].xml", "xl/workbook.xml",
                "xl/worksheets/sheet1.xml"} <= names
        sheet = book.read("xl/worksheets/sheet1.xml").decode("utf-8")
    # An ampersand would otherwise make the workbook unreadable; quotes are
    # legal inside a text node and stay as typed.
    assert "Beta &amp; Co" in sheet
    assert 'He said "hi"' in sheet
    assert '<row r="1">' in sheet
    # A None cell becomes an empty string rather than the word "None".
    assert "None" not in sheet


def test_column_names_go_past_z():
    assert services._col_name(0) == "A"
    assert services._col_name(25) == "Z"
    assert services._col_name(26) == "AA"


def test_industry_field_splits_and_deduplicates():
    assert services.split_industries("Roofers, Plumbers\nRoofers , ,HVAC") == [
        "Roofers", "Plumbers", "HVAC"]
    assert services.split_industries("") == []


def test_scroll_budget_scales_with_the_result_cap():
    assert services.scroll_budget(0) == 8
    assert services.scroll_budget(10) < services.scroll_budget(200)
    assert services.scroll_budget(10_000) <= 30


# --------------------------------------------------------------------------- #
#  pipeline wiring
# --------------------------------------------------------------------------- #
def test_configured_smtp_account_reaches_the_sender():
    """A campaign must use the account Settings names, not an inferred one.

    The connection test on the Settings page passes these through directly, so
    if the pipeline dropped them a test could pass while every send failed.
    """
    pipeline = services.make_pipeline({
        "from_email": "jordan@jlang.dev",
        "smtp_username": "owner@icloud.com",
        "smtp_server": "smtp.example.net",
        "smtp_port": 2525,
        "reply_to": "replies@jlang.dev",
        "demo_mode": True,
    })
    sender = pipeline._sender()
    assert sender.smtp_username == "owner@icloud.com"
    assert (sender.smtp_server, sender.smtp_port) == ("smtp.example.net", 2525)
    assert sender.reply_to == "replies@jlang.dev"
    assert sender.from_email == "jordan@jlang.dev"


def test_unset_smtp_fields_still_auto_detect():
    pipeline = services.make_pipeline({"from_email": "someone@gmail.com", "demo_mode": True})
    sender = pipeline._sender()
    assert sender.smtp_server == "smtp.gmail.com"
    assert sender.smtp_username == "someone@gmail.com"
    assert sender.reply_to == ""


def test_reply_to_reaches_the_message_header():
    from send_emails import EmailSender

    sent = {}

    class FakeConnection:
        def send_message(self, msg):
            sent.update(msg)

    sender = EmailSender(from_email="jordan@jlang.dev", reply_to="replies@jlang.dev")
    sender.smtp_connection = FakeConnection()
    assert sender.send_email("them@example.com", "Subject", "<p>hi</p>", "Acme")
    assert sent["Reply-To"] == "replies@jlang.dev"

    # With no reply-to configured the header is left off entirely.
    plain = EmailSender(from_email="jordan@jlang.dev")
    plain.smtp_connection = FakeConnection()
    sent.clear()
    plain.send_email("them@example.com", "Subject", "<p>hi</p>", "Acme")
    assert "Reply-To" not in sent


def test_a_stopped_search_keeps_and_saves_what_it_found(tmp_path):
    """Stopping mid-search must not throw away the listings already opened."""
    from tui.pipeline import DemoPipeline
    from gui.workers import Cancelled

    pipeline = DemoPipeline(data_root=tmp_path)
    delivered = []

    def progress(_line):
        # Stand in for the GUI's stop: the pipeline calls progress constantly,
        # and that is where a cancellation surfaces.
        if len(delivered) >= 2:
            raise Cancelled()

    with pytest.raises(Cancelled):
        pipeline.search("Electricians", "Zanesville, OH",
                        progress=progress, on_business=delivered.append)

    # The caller kept every business handed to it before the stop...
    assert len(delivered) == 2
    # ...and those rows reached disk rather than vanishing with the run.
    assert pipeline.last_listings_csv is not None
    rows = pipeline.last_listings_csv.read_text(encoding="utf-8")
    for business in delivered:
        assert business.name in rows
    assert all(business.search_term == "Electricians" for business in delivered)


def test_on_business_fires_for_every_listing_of_a_completed_search(tmp_path):
    from tui.pipeline import DemoPipeline

    pipeline = DemoPipeline(data_root=tmp_path)
    delivered = []
    returned = pipeline.search("Plumbers", "Columbus, OH", on_business=delivered.append)
    assert [b.name for b in delivered] == [b.name for b in returned]


def test_demo_exports_stay_out_of_the_real_data_tree(tmp_path):
    """Sample rows must never mix with a real scrape's CSVs."""
    live = services.data_root_for({"data_root": str(tmp_path)})
    demo = services.data_root_for({"data_root": str(tmp_path), "demo_mode": True})
    assert live == tmp_path
    assert demo == tmp_path / "_demo"

    # With no export folder configured, demo still gets its own subtree.
    import data_store

    assert services.data_root_for({"demo_mode": True}) == data_store.data_root() / "_demo"
    assert services.data_root_for({}) is None  # live: data_store's own default


def test_frozen_runs_export_somewhere_that_survives_the_process(tmp_path, monkeypatch):
    """A one-file bundle's own directory is deleted on exit; exports can't go there."""
    import importlib

    from gui import runtime

    monkeypatch.setenv("LLSP_DATA_DIR", str(tmp_path / "appdata"))
    monkeypatch.delenv("GOOGLE_SCRAPER_DATA_DIR", raising=False)
    monkeypatch.setattr(runtime, "frozen", lambda: True)
    monkeypatch.setattr(runtime, "bundle_dir", lambda: tmp_path / "bundle")
    monkeypatch.chdir(tmp_path)

    runtime.prepare()
    import data_store

    importlib.reload(data_store)
    assert data_store.data_root() == tmp_path / "appdata" / "data"
    assert (tmp_path / "bundle") not in data_store.data_root().parents


def test_imported_rows_remember_who_was_already_emailed(tmp_path):
    """Re-loading an export must not put delivered leads back in the queue."""
    import csv

    import data_store
    from tui.models import Business

    path = tmp_path / "listings.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(data_store.LISTING_FIELDS),
                                extrasaction="ignore", restval="")
        writer.writeheader()
        writer.writerow({"name": "Contacted Co", "emailed": "yes",
                         "emailed_to": "hi@contacted.example"})
        writer.writerow({"name": "Fresh Co"})

    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    flags = {row["name"]: data_store.was_emailed(row) for row in rows}
    assert flags == {"Contacted Co": True, "Fresh Co": False}
    # And Business.from_dict alone does not carry it — which is why the
    # importer sets it explicitly.
    assert Business.from_dict(rows[0]).emailed is False


# --------------------------------------------------------------------------- #
#  call scripts
# --------------------------------------------------------------------------- #
def test_script_steps_split_on_headings():
    steps = scripts.script_steps(
        "# Title\nintro\n\n## 1. Opening\nsay hello\n\n## 2. Close\nask for the job\n")
    assert [step.title for step in steps] == ["Opening", "Close"]
    assert steps[0].body == "say hello"


def test_script_steps_fall_back_to_the_whole_document():
    steps = scripts.script_steps("just some prose, no headings")
    assert len(steps) == 1
    assert "just some prose" in steps[0].body


def test_call_tokens_describe_the_business():
    tokens = scripts.call_tokens(Business(
        name="Columbus Roofing Pros", category="Roofing contractor",
        address="1234 Main St, Columbus, OH 43215", rating="4.8",
        reviews_count="125", website="https://example.com"))
    assert tokens["name"] == "Columbus Roofing Pros"
    assert tokens["city"] == "Columbus"
    assert tokens["trade"] == "roofing"
    assert "125 reviews" in tokens["proof"]


def test_objection_cards_are_personalised():
    cards = scripts.objection_cards(Business(name="Acme", category="Plumber"))
    assert cards
    assert all("{" not in card.response for card in cards)
    assert any("plumber" in card.response.lower() for card in cards)


def test_fill_leaves_unknown_placeholders_alone():
    assert scripts.fill("hi {name} {unknown}", {"name": "Acme"}) == "hi Acme {unknown}"


def test_a_stop_does_not_abort_the_cleanup_that_saves_results():
    """Cancellation fires once; the pipeline's finally blocks still finish.

    The exports live in `finally` and call progress() themselves — if every
    later call re-raised, a stop would kill the very write it is meant to
    preserve.
    """
    control = RunControl()
    control.stop()
    with pytest.raises(Cancelled):
        control.checkpoint()
    control.checkpoint()  # cleanup path: no longer raises
    control.checkpoint()


def test_stopping_a_scan_still_folds_contacts_into_the_listings(tmp_path):
    from gui.workers import RunControl
    from tui.pipeline import DemoPipeline

    pipeline = DemoPipeline(data_root=tmp_path)
    businesses = pipeline.search("Electricians", "Zanesville, OH")
    control = RunControl()
    seen = []

    def progress(line):
        seen.append(line)
        if len([s for s in seen if s.startswith("[")]) >= 2:
            control.stop()
        control.checkpoint()

    with pytest.raises(Cancelled):
        pipeline.scrape_contacts(businesses, progress=progress)

    # Both files exist, and the listings row carries the scanned address.
    assert pipeline.last_contacts_csv is not None
    assert pipeline.last_contacts_csv.exists()
    listings = pipeline.last_listings_csv.read_text(encoding="utf-8")
    scanned = [b for b in businesses if b.emails]
    assert scanned, "the run should have scanned at least one business"
    assert scanned[0].primary_email in listings


def test_settings_ignore_values_of_the_wrong_type(tmp_path, monkeypatch):
    monkeypatch.setenv("LLSP_CONFIG_DIR", str(tmp_path / "cfg"))
    settings_store.config_path().parent.mkdir(parents=True)
    settings_store.config_path().write_text(
        '{"max_results": "fifty", "headless": "yes", "location": "Dublin, OH",'
        ' "data_categories": 7}', encoding="utf-8")

    loaded = settings_store.load()
    assert loaded["location"] == "Dublin, OH"          # right type, kept
    assert loaded["max_results"] == settings_store.DEFAULTS["max_results"]
    assert loaded["headless"] is settings_store.DEFAULTS["headless"]
    assert loaded["data_categories"] == settings_store.DEFAULTS["data_categories"]


def test_data_points_count_each_contact_once():
    from tui.models import ScanEvent

    event = ScanEvent(
        1, 1, "Acme", emails=["a@b.c"], phones=["1", "2"], contact_names=["Dana"],
        insights={"contact_info": 4, "services": 3, "images": 5},
    )
    # 4 contacts + 3 services + 5 images — the contact tally in insights is
    # the same four, not another four.
    assert event.data_points == 12


def test_version_quad_rejects_what_it_cannot_represent():
    import sys

    sys.path.insert(0, "packaging")
    from make_version_info import version_quad

    assert version_quad("1.2") == (1, 2, 0, 0)
    assert version_quad("1.2a") == (1, 2, 0, 0)   # fix-level letter is dropped
    assert version_quad("2") == (2, 0, 0, 0)
    assert version_quad("1.2.3.4") == (1, 2, 3, 4)
    for bad in ("", "v1.2", "1.2.3.4.5", "release"):
        with pytest.raises(ValueError):
            version_quad(bad)


def test_service_counting_stays_inside_the_services_section():
    import contact_scraper

    html = ("<nav><ul><li>Home</li><li>About</li><li>Contact</li></ul></nav>"
            "<h2>Our Services</h2><ul><li>Roof Repair</li><li>New Roofs</li>"
            "<li>Gutters</li></ul>"
            "<h2>About Us</h2><ul><li>Founded 1998</li></ul>"
            "<footer><ul><li>Privacy</li><li>Terms</li></ul></footer>")
    counts = contact_scraper.page_insights(html, "Our Services About Us")
    assert counts["services"] == 3  # not the nav, not the footer


def test_social_links_need_a_real_domain_match():
    import contact_scraper

    html = ('<a href="https://notfacebook.com/x">no</a>'
            '<a href="https://www.facebook.com/real">yes</a>'
            '<a href="https://linkedin.com/company/real">yes</a>')
    assert contact_scraper.social_links(html) == [
        "https://www.facebook.com/real", "https://linkedin.com/company/real"]


def test_the_spec_collects_selenium_whole():
    """Naming selenium submodules by hand ships a build that cannot scrape.

    Selenium resolves its driver classes through a lazy string map that
    PyInstaller cannot follow, so a hand-written list silently omits whatever
    was not thought of — which is how a packaged build launched fine and then
    died on "No module named 'selenium.webdriver.chrome.options'".
    """
    text = (Path(__file__).resolve().parent.parent
            / "packaging" / "LocalLeadScraperPro.spec").read_text(encoding="utf-8")
    # Comments explain the trap by quoting it, so read the code alone.
    spec = "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("#"))
    assert 'collect_submodules("selenium")' in spec
    for lazy in ("chrome.options", "chrome.webdriver", "chrome.service"):
        assert f'"selenium.webdriver.{lazy}"' not in spec, (
            f"selenium.webdriver.{lazy} is listed by hand; collect_submodules "
            "covers it and cannot miss its siblings")


def test_every_lazily_imported_module_is_checked_by_the_selftest():
    """The self-test's import list must keep up with the code.

    Anything imported inside a function is invisible to PyInstaller's analysis
    and therefore a candidate for going missing from the bundle. If it is not
    in RUNTIME_IMPORTS, nothing catches that before a user does.
    """
    import re

    from gui.app import RUNTIME_IMPORTS

    root = Path(__file__).resolve().parent.parent
    lazy = set()
    for path in sorted((root / "gui").rglob("*.py")) + [root / "tui" / "pipeline.py"]:
        for line in path.read_text(encoding="utf-8").splitlines():
            # An import indented inside a function body, not at module level.
            match = re.match(r"\s+from ([a-zA-Z_][\w.]*) import |\s+import ([\w.]+)", line)
            if not match:
                continue
            name = (match.group(1) or match.group(2)).split(".")[0]
            if name in {"gui", "tui", "typing", "pathlib", "datetime", "PySide6",
                        "__future__", "tempfile", "importlib", "re", "json", "os", "sys"}:
                continue
            lazy.add(name)

    checked = {name.split(".")[0] for name in RUNTIME_IMPORTS}
    missing = sorted(lazy - checked)
    assert not missing, (
        f"lazily imported but not covered by the packaged self-test: {missing}")


def test_failure_advice_matches_what_actually_failed():
    """A build fault must not be reported as the user's missing browser.

    The catch-all "install Chrome" hint is what sent someone chasing a browser
    they already had when the real problem was a module missing from the
    package.
    """
    build_fault = services.explain_failure(
        "ModuleNotFoundError: No module named 'selenium.webdriver.chrome.options'")
    assert "packaging fault" in build_fault
    assert "Install Chrome" not in build_fault

    assert "Chrome was not found" in services.explain_failure(
        "WebDriverException: unable to locate Chrome binary")
    assert "do not match" in services.explain_failure(
        "session not created: This version of ChromeDriver only supports Chrome 140")
    assert "did not load in time" in services.explain_failure("TimeoutException: timed out")
    assert "app-specific" in services.explain_failure("SMTP authentication failed 535")
    # Anything unrecognised still points at the logs.
    assert "Logs page" in services.explain_failure("something unexpected")


def test_one_phone_number_yields_one_entry():
    """The two phone regexes overlap; a number must not appear twice.

    "(614) 555-0142" matched the US pattern whole and the international one
    from the digit after the bracket, so the scan produced a real number and a
    malformed twin — and `set` ordering meant the twin could come first and
    end up as the number on the call sheet.
    """
    import re

    import contact_scraper

    scraper = contact_scraper.ContactScraper.__new__(contact_scraper.ContactScraper)
    scraper.phone_patterns = [
        re.compile(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'),
        re.compile(r'\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}'),
    ]

    assert scraper.extract_phones("Call (614) 555-0142 today") == ["(614) 555-0142"]
    # Two genuinely different numbers stay two, in the order they appear.
    assert scraper.extract_phones(
        "Office (614) 555-0142 or mobile 614-555-0199"
    ) == ["(614) 555-0142", "614-555-0199"]
    # A leading 1 is the same number, not another one.
    assert scraper.extract_phones("1-800-555-0143 or 800-555-0143") == ["1-800-555-0143"]
    assert scraper.extract_phones("no numbers here") == []
    # Deterministic: the same text must not reorder between runs.
    text = "Call (614) 555-0142 or (614) 555-0199"
    assert scraper.extract_phones(text) == scraper.extract_phones(text)


# --------------------------------------------------------------------------- #
#  packaging assets
# --------------------------------------------------------------------------- #
def test_icon_is_a_multi_size_ico():
    path = Path("packaging/app_icon.ico")
    if not path.exists():
        pytest.skip("icon not generated yet (packaging/make_icon.py)")
    data = path.read_bytes()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert (reserved, kind) == (0, 1)
    assert count >= 4  # 16px through 256px, so Windows never has to guess
