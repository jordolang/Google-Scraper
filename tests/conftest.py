"""Shared test fixtures.

Anything that scrapes or sends now exports to ``data/``.  Point that at a
throwaway directory for the whole suite so a test run never writes into the
repo's real data.

The licensing fixtures do the same job for licences: a scratch state directory
per test, a fixed machine id, and a licence service that is never actually
called. A test suite that reached the real service would be slow, flaky, and
would spend seats on whatever machine happened to run it.
"""

import pytest


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_SCRAPER_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


@pytest.fixture(autouse=True)
def isolated_licence(tmp_path, monkeypatch):
    """Per-test licence state, a stable fingerprint, and no network.

    Every outbound call is turned into :class:`ServiceUnreachable`, which is
    the state the app is built to survive — so a test that trips one exercises
    the offline path rather than hanging for a socket timeout.
    """
    from licensing import client, machine, manager, storage

    monkeypatch.setenv(storage.STATE_DIR_ENV, str(tmp_path / "licence"))
    monkeypatch.setenv(machine.MACHINE_ID_ENV, "pytest-machine")
    monkeypatch.setenv(client.SERVICE_URL_ENV, "http://licence.invalid")

    def refuse(self, path, body):
        raise client.ServiceUnreachable(
            f"the test suite does not call the licence service ({path})")

    monkeypatch.setattr(client.LicenseClient, "_post", refuse)
    machine.reset_cache()
    manager.reset_manager()
    _install_test_licence(monkeypatch)
    yield
    manager.reset_manager()
    machine.reset_cache()


def _install_test_licence(monkeypatch):
    """Give the suite a real, signed Agency licence.

    The tests exist to exercise the app, not the gates: an unlicensed test run
    would stop at the first "not on this licence" dialog and prove nothing
    about scraping, exporting or sending. The licence is signed with a keypair
    generated for this test session and trusted through the public-key
    environment override, so it is the genuine verification path — just with
    our own key.

    Tests that care about the gates (``test_licensing*.py``) point the state
    directory somewhere else and build their own managers, so they see a blank
    install rather than this one.
    """
    import time

    from licensing import crypto, plans, public_key, storage, tokens

    seed, public = crypto.generate_keypair()
    monkeypatch.setenv(public_key.PUBLIC_KEY_ENV, crypto.b64encode(public))
    now = time.time()
    token = tokens.LicenseToken(
        key="LLSP-TEST0-TEST0-TEST0-TEST0",
        tier=plans.AGENCY,
        model=plans.PERPETUAL,
        machine_id="pytest-machine",
        issued_at=now,
        refresh_after=now + 30 * 86400,
        expires_at=None,
        email="tests@jlang.dev",
    )
    storage.update(token=tokens.sign_token(token, seed))
