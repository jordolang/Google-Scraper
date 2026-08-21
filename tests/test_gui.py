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
