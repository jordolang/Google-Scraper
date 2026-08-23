"""The licence as the desktop app presents it.

Runs offscreen like the rest of the GUI suite. The point of these tests is the
wiring, not the widgets: that a gate actually stops a run, that the banner says
the right thing in each state, and that nothing in the window claims a tier the
licence does not grant.
"""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="the desktop app needs PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from licensing import (  # noqa: E402
    crypto, keys, machine, manager as manager_module, plans, storage, tokens, trial,
)
from licensing.manager import LicenseManager  # noqa: E402

DAY = 86400.0


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("LLSP_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("LLSP_DATA_DIR", str(tmp_path / "appdata"))
    # A blank install, deliberately: conftest gives the rest of the suite a
    # working licence, and these tests install their own per case.
    monkeypatch.setenv(storage.STATE_DIR_ENV, str(tmp_path / "licence-under-test"))
    monkeypatch.setenv(machine.MACHINE_ID_ENV, "gui-test-machine")
    machine.reset_cache()
    storage.clear()
    manager_module.reset_manager()
    yield
    manager_module.reset_manager()
    machine.reset_cache()


def licence(monkeypatch, tier=plans.PRO, **overrides):
    """Install a signed licence and make the shared manager trust it."""
    seed, public = crypto.generate_keypair()
    now = time.time()
    fields = {
        "key": keys.generate(), "tier": tier,
        "model": plans.SUBSCRIPTION, "machine_id": "gui-test-machine",
        "issued_at": now, "refresh_after": now + 7 * DAY,
        "expires_at": now + 30 * DAY, "email": "mike@example.com",
    }
    fields.update(overrides)
    storage.update(token=tokens.sign_token(tokens.LicenseToken(**fields), seed))
    monkeypatch.setattr(manager_module, "_default",
                        LicenseManager(public_key_bytes=public))
    return manager_module.get_manager()


class TestBanner:
    def test_a_healthy_licence_shows_nothing(self, qapp, monkeypatch):
        licence(monkeypatch)
        from gui.licensing_ui import LicenseBanner

        banner = LicenseBanner()
        banner.refresh()
        assert not banner.isVisibleTo(banner.parentWidget() or banner)

    def test_a_trial_counts_down(self, qapp, monkeypatch):
        trial.confirm(time.time())
        licence(monkeypatch, tier=plans.TRIAL,
                expires_at=time.time() + 71 * 3600)
        from gui.licensing_ui import LicenseBanner

        banner = LicenseBanner()
        banner.refresh()
        assert "Trial" in banner.message.text()
        assert "hour" in banner.message.text()

    def test_an_expired_subscription_says_so(self, qapp, monkeypatch):
        licence(monkeypatch, expires_at=time.time() - DAY)
        from gui.licensing_ui import LicenseBanner

        banner = LicenseBanner()
        banner.refresh()
        assert "ended" in banner.message.text()
        assert banner.action.text() == "Renew"

    def test_a_licence_about_to_renew_warns_gently(self, qapp, monkeypatch):
        licence(monkeypatch, expires_at=time.time() + 3.5 * DAY)
        from gui.licensing_ui import LicenseBanner

        banner = LicenseBanner()
        banner.refresh()
        assert "renews in 3 days" in banner.message.text()


class TestWindow:
    def test_the_sidebar_shows_the_real_licence(self, qapp, monkeypatch):
        licence(monkeypatch, tier=plans.SOLO)
        from gui.app import build_app

        _app, window = build_app([])
        assert "Solo" in window.sidebar.license_label.text()

    def test_an_unlicensed_install_does_not_claim_pro(self, qapp, monkeypatch):
        """The rail used to read a settings string and always said "Pro"."""
        from gui.app import build_app

        _app, window = build_app([])
        assert "Pro" not in window.sidebar.license_label.text()
        assert "Reader" in window.sidebar.license_label.text()

    def test_the_licence_page_is_reachable_and_renders_every_state(
            self, qapp, monkeypatch):
        licence(monkeypatch, tier=plans.AGENCY, model=plans.PERPETUAL,
                expires_at=None)
        from gui.app import build_app

        _app, window = build_app([])
        window.go_to("license")
        page = window.pages["license"]
        assert "owned" in page.state_label.text()
        assert page.row_model.value.text().startswith("One-time")
        assert not page.deactivate_button.isEnabled() is False  # a key is present

    def test_settings_no_longer_edits_the_licence(self, qapp, monkeypatch):
        licence(monkeypatch, tier=plans.SOLO)
        from gui.app import build_app
        from gui import settings_store

        _app, window = build_app([])
        page = window.pages["settings"]
        assert not hasattr(page, "license_tier")
        assert "license_tier" not in settings_store.DEFAULTS
        window.go_to("settings")
        assert "Solo" in page.license_summary.text()


class TestGates:
    def test_scraping_is_capped_by_the_licence(self, qapp, monkeypatch):
        licence(monkeypatch, tier=plans.SOLO)
        from gui import services

        settings = {"max_results": 5000}
        assert services.licensed_max_results(settings) == 200

    def test_zero_means_the_licence_ceiling_not_unlimited(self, qapp, monkeypatch):
        licence(monkeypatch, tier=plans.SOLO)
        from gui import services

        assert services.licensed_max_results({"max_results": 0}) == 200

    def test_agency_is_uncapped(self, qapp, monkeypatch):
        licence(monkeypatch, tier=plans.AGENCY)
        from gui import services

        assert services.licensed_max_results({"max_results": 0}) == 0
        assert services.licensed_max_results({"max_results": 9999}) == 9999

    def test_trial_exports_are_truncated_with_a_count(self, qapp, monkeypatch):
        trial.confirm(time.time())
        licence(monkeypatch, tier=plans.TRIAL, expires_at=time.time() + 3600)
        from gui import services

        rows, dropped = services.licensed_rows([[n] for n in range(60)])
        assert len(rows) == 25
        assert dropped == 35

    def test_paid_exports_are_whole(self, qapp, monkeypatch):
        licence(monkeypatch, tier=plans.SOLO)
        from gui import services

        rows, dropped = services.licensed_rows([[n] for n in range(60)])
        assert len(rows) == 60
        assert dropped == 0

    def test_require_lets_a_licensed_feature_through(self, qapp, monkeypatch):
        licence(monkeypatch, tier=plans.PRO)
        from gui.licensing_ui import require

        assert require(None, plans.SITE_INTEL)

    def test_require_blocks_and_explains(self, qapp, monkeypatch):
        licence(monkeypatch, tier=plans.SOLO)
        import gui.licensing_ui as licensing_ui

        shown = {}

        class FakeBox:
            # The enum members require() reaches for, as attributes on the
            # class exactly as Qt exposes them.
            Information = object()
            AcceptRole = object()
            RejectRole = object()

            def __init__(self, _parent=None):
                pass

            def setWindowTitle(self, text):
                shown["title"] = text

            def setIcon(self, _icon):
                pass

            def setText(self, text):
                shown["text"] = text

            def addButton(self, label, _role):
                return label

            def exec(self):
                shown["shown"] = True

            def clickedButton(self):
                return "Not now"

        monkeypatch.setattr(licensing_ui, "QMessageBox", FakeBox)
        assert not licensing_ui.require(None, plans.SITE_INTEL)
        assert shown["shown"]
        assert "Pro" in shown["text"]


class TestConsole:
    def test_status_prints_the_plan(self, capsys, monkeypatch):
        manager = licence(monkeypatch, tier=plans.PRO)
        from licensing import console

        key = manager.status().key
        assert console.run(["status"]) == 0
        printed = capsys.readouterr().out
        assert "Pro" in printed
        assert keys.masked(key) in printed     # the key is masked, not printed
        assert key not in printed

    def test_plans_lists_both_pricing_models(self, capsys, monkeypatch):
        from licensing import console

        assert console.run(["plans"]) == 0
        printed = capsys.readouterr().out
        assert "$89/mo" in printed and "$1,299" in printed
        assert "never expires" in printed

    def test_require_explains_on_stderr_and_returns_false(self, capsys, monkeypatch):
        licence(monkeypatch, tier=plans.SOLO)
        from licensing import console

        assert not console.require(plans.AUTOMATION_CLI)
        assert "not covered" in capsys.readouterr().err

    def test_an_unknown_command_is_a_usage_error(self, capsys):
        from licensing import console

        assert console.run(["frobnicate"]) == 2


class TestSelftestLicenceKeyGuard:
    """The guard that decides whether a keyless bundle fails the build.

    Its first version keyed off "is this a release?", which failed every
    release before licensing went live — the tag was cut, all four builds
    failed the self-test, and no assets were published. These pin the
    behaviour that replaced it.
    """

    def test_a_source_build_is_never_a_problem(self):
        from gui.app import licence_key_problem

        assert licence_key_problem(frozen=False, configured=False) == ""
        assert licence_key_problem(frozen=False, configured=True) == ""

    def test_a_packaged_build_with_a_key_is_fine(self):
        from gui.app import licence_key_problem

        assert licence_key_problem(frozen=True, configured=True) == ""

    def test_a_packaged_build_without_a_key_is_reported(self):
        from gui.app import licence_key_problem

        complaint = licence_key_problem(frozen=True, configured=False)
        assert "no licence public key" in complaint
        # Names the command that fixes it, not the one that would mint a new
        # keypair and invalidate every licence already issued.
        assert "set-public-key" in complaint
        assert "keygen" not in complaint

    def test_the_workflows_require_the_key_only_when_they_embed_one(self):
        """The build workflows must not tie the requirement to a release tag.

        Read from the workflow files themselves: this is the exact regression
        that cut tag v1.7 with no release attached.
        """
        import re
        from pathlib import Path

        from gui.app import REQUIRE_LICENCE_KEY_ENV

        root = Path(__file__).resolve().parent.parent
        for name in ("windows-build.yml", "macos-build.yml"):
            text = (root / ".github" / "workflows" / name).read_text(encoding="utf-8")
            assert REQUIRE_LICENCE_KEY_ENV in text, name
            for line in text.splitlines():
                if REQUIRE_LICENCE_KEY_ENV in line and not line.strip().startswith("#"):
                    assert "RELEASE_TAG" not in line, (
                        f"{name}: the licence-key requirement is back on the "
                        f"release tag, which blocks every release until "
                        f"LLSP_LICENSE_PUBKEY is set")
            # The key itself must never reach the self-test's environment:
            # licensing.public_key reads it from there, so a failed embed
            # would pass on the runner's environment alone.
            check_step = text.split("--selftest")[0].rsplit("- name:", 1)[-1]
            assert "LLSP_LICENSE_PUBKEY" not in check_step, name
