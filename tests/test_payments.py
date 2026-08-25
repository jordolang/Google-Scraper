"""The licence server: Stripe webhooks in, signed licences out.

Nothing here talks to Stripe. The gateway is replaced with a stub that records
what it was asked for, and webhooks are signed with the same HMAC Stripe uses,
so the signature path is exercised for real.
"""

from __future__ import annotations

import io
import json
import time

import pytest

from licensing import crypto, keys, plans, tokens
from payments import issuer
from payments.config import Settings
from payments.db import Database
from payments.server import HttpError, LicenseService, make_app
from payments.stripe_gateway import StripeGateway, sign_payload

WEBHOOK_SECRET = "whsec_test"
DAY = 86400.0


class StubStripe(StripeGateway):
    """Records checkout requests and answers with a predictable session."""

    def __init__(self):
        super().__init__("sk_test", WEBHOOK_SECRET)
        self.checkout_calls = []

    def create_checkout_session(self, **kwargs):
        self.checkout_calls.append(kwargs)
        return {"id": "cs_test_1", "url": "https://checkout.stripe.test/cs_test_1"}


@pytest.fixture
def keypair():
    return crypto.generate_keypair()


@pytest.fixture
def service(keypair):
    seed, _public = keypair
    settings = Settings.from_env({
        "LLSP_SIGNING_KEY": crypto.b64encode(seed),
        "LLSP_STRIPE_SECRET_KEY": "sk_test",
        "LLSP_STRIPE_WEBHOOK_SECRET": WEBHOOK_SECRET,
        "LLSP_LICENSE_DB": ":memory:",
        "LLSP_STRIPE_PRICE_PRO_SUBSCRIPTION_MONTHLY": "price_pro_m",
        "LLSP_STRIPE_PRICE_PRO_PERPETUAL_ONCE": "price_pro_once",
    })
    return LicenseService(settings, Database(":memory:"), StubStripe())


def event(kind: str, obj: dict) -> bytes:
    return json.dumps({"type": kind, "data": {"object": obj}}).encode("utf-8")


def deliver(service: LicenseService, kind: str, obj: dict, *, secret=WEBHOOK_SECRET):
    payload = event(kind, obj)
    return service.webhook(payload, sign_payload(secret, payload))


def purchase(service: LicenseService, sku="pro-subscription-monthly",
             email="mike@example.com", **overrides) -> str:
    session = {"payment_status": "paid", "customer": "cus_1",
               "subscription": "sub_1", "metadata": {"sku": sku},
               "customer_details": {"email": email, "name": "Mike"}}
    session.update(overrides)
    return deliver(service, "checkout.session.completed", session)["licence"]


# -- configuration -------------------------------------------------------

class TestSettings:
    def test_an_unconfigured_server_lists_what_is_missing(self):
        problems = Settings.from_env({}).problems()
        assert any("SIGNING_KEY" in line for line in problems)
        assert any("WEBHOOK_SECRET" in line for line in problems)
        assert any("price ids" in line for line in problems)

    def test_price_ids_are_read_from_the_environment(self):
        settings = Settings.from_env({
            "LLSP_STRIPE_PRICE_AGENCY_PERPETUAL_ONCE": "price_xyz"})
        assert settings.price_id("agency-perpetual-once") == "price_xyz"
        assert settings.price_id("solo-subscription-monthly") == ""

    def test_a_bad_signing_key_is_refused_loudly(self):
        settings = Settings.from_env({"LLSP_SIGNING_KEY": crypto.b64encode(b"short")})
        with pytest.raises(ValueError):
            settings.signing_key()


# -- webhook signatures --------------------------------------------------

class TestWebhookSignatures:
    def test_a_valid_signature_is_accepted(self, service):
        assert purchase(service).startswith("LLSP-")

    def test_an_unsigned_webhook_is_refused(self, service):
        with pytest.raises(HttpError) as caught:
            service.webhook(event("checkout.session.completed", {}), "")
        assert caught.value.status == 400

    def test_a_forged_signature_is_refused(self, service):
        with pytest.raises(HttpError):
            deliver(service, "checkout.session.completed", {}, secret="wrong-secret")

    def test_a_replayed_webhook_is_refused(self, service):
        """An old capture must not still mint a licence."""
        payload = event("checkout.session.completed", {})
        stale = sign_payload(WEBHOOK_SECRET, payload,
                             int(time.time()) - 3600)
        with pytest.raises(HttpError):
            service.webhook(payload, stale)

    def test_a_modified_body_is_refused(self, service):
        payload = event("checkout.session.completed",
                        {"metadata": {"sku": "solo-subscription-monthly"}})
        signature = sign_payload(WEBHOOK_SECRET, payload)
        upgraded = payload.replace(b"solo-", b"agency-")
        with pytest.raises(HttpError):
            service.webhook(upgraded, signature)

    def test_unknown_events_are_acknowledged_not_errors(self, service):
        assert deliver(service, "customer.created", {}) == {"ignored": "customer.created"}


# -- the purchase lifecycle ----------------------------------------------

class TestPurchase:
    def test_a_paid_checkout_creates_a_licence(self, service):
        key = purchase(service)
        licence = service.db.licence(key)
        assert licence["tier"] == plans.PRO
        assert licence["model"] == plans.SUBSCRIPTION
        assert licence["email"] == "mike@example.com"
        assert licence["status"] == "active"
        assert licence["max_machines"] == plans.TIERS[plans.PRO].limits.max_machines
        assert keys.is_valid(key)

    def test_an_unpaid_session_creates_nothing(self, service):
        result = deliver(service, "checkout.session.completed", {
            "payment_status": "unpaid", "metadata": {"sku": "pro-subscription-monthly"}})
        assert "ignored" in result
        assert service.db.query("SELECT * FROM licences") == []

    def test_a_session_with_no_known_sku_creates_nothing(self, service):
        result = deliver(service, "checkout.session.completed", {
            "payment_status": "paid", "metadata": {"sku": "free-lunch"}})
        assert "ignored" in result

    def test_a_perpetual_purchase_never_expires_but_updates_do(self, service):
        key = purchase(service, sku="pro-perpetual-once")
        licence = service.db.licence(key)
        assert licence["model"] == plans.PERPETUAL
        assert licence["expires_at"] is None
        assert licence["updates_until"] > time.time()

    def test_an_upgrade_edits_the_existing_licence(self, service):
        key = purchase(service, sku="pro-subscription-monthly")
        result = deliver(service, "checkout.session.completed", {
            "payment_status": "paid", "customer": "cus_1",
            "metadata": {"sku": "pro-perpetual-once", "licence_key": key},
            "customer_details": {"email": "mike@example.com"}})
        assert result["upgraded"]
        assert result["licence"] == key
        assert service.db.licence(key)["model"] == plans.PERPETUAL
        assert len(service.db.query("SELECT * FROM licences")) == 1

    def test_a_renewal_moves_the_expiry(self, service):
        key = purchase(service)
        later = time.time() + 90 * DAY
        deliver(service, "invoice.paid", {
            "subscription": "sub_1", "lines": {"data": [{"period": {"end": later}}]}})
        assert service.db.licence(key)["expires_at"] == pytest.approx(later)

    def test_a_failed_payment_changes_nothing_yet(self, service):
        """Stripe retries for days; one bounced card is not a revocation."""
        key = purchase(service)
        before = service.db.licence(key)
        deliver(service, "invoice.payment_failed",
                {"subscription": "sub_1", "attempt_count": 1})
        assert service.db.licence(key)["status"] == before["status"]
        assert service.db.licence(key)["expires_at"] == before["expires_at"]

    def test_cancelling_keeps_the_period_already_paid_for(self, service):
        key = purchase(service)
        deliver(service, "customer.subscription.deleted", {"id": "sub_1"})
        assert service.db.licence(key)["status"] == "cancelled"
        # Still activatable until the paid period runs out.
        answer = service.activate({"key": key, "machine_id": "m1"})
        assert answer["token"]

    def test_a_cancelled_licence_stops_at_the_end_of_the_period(self, service):
        key = purchase(service)
        deliver(service, "customer.subscription.deleted", {"id": "sub_1"})
        service.db.update_licence(key, expires_at=time.time() - DAY)
        with pytest.raises(HttpError) as caught:
            service.activate({"key": key, "machine_id": "m1"})
        assert caught.value.status == 403

    def test_a_refund_ends_the_licence_and_frees_every_seat(self, service):
        key = purchase(service)
        service.activate({"key": key, "machine_id": "m1"})
        service.activate({"key": key, "machine_id": "m2"})
        deliver(service, "charge.refunded", {"customer": "cus_1", "id": "ch_1"})
        assert service.db.licence(key)["status"] == "refunded"
        assert service.db.seats_used(key) == 0
        with pytest.raises(HttpError):
            service.refresh({"key": key, "machine_id": "m1"})

    def test_a_chargeback_is_treated_like_a_refund(self, service):
        key = purchase(service)
        deliver(service, "charge.dispute.created", {"customer": "cus_1", "id": "ch_2"})
        assert service.db.licence(key)["status"] == "refunded"


# -- activation ----------------------------------------------------------

class TestActivation:
    def test_activation_returns_a_licence_the_app_can_verify(self, service, keypair):
        _seed, public = keypair
        key = purchase(service)
        answer = service.activate({"key": key, "machine_id": "mach-1",
                                   "label": "Mike-PC"})
        token = tokens.verify_token(answer["token"], public)
        assert token.tier == plans.PRO
        assert token.machine_id == "mach-1"
        assert token.key == key
        assert token.expires_at > time.time()

    def test_seats_are_enforced(self, service):
        key = purchase(service)
        allowed = plans.TIERS[plans.PRO].limits.max_machines
        for index in range(allowed):
            service.activate({"key": key, "machine_id": f"mach-{index}"})
        with pytest.raises(HttpError) as caught:
            service.activate({"key": key, "machine_id": "one-too-many"})
        assert caught.value.status == 409
        assert "seats" in caught.value.message

    def test_reactivating_the_same_machine_does_not_take_a_new_seat(self, service):
        key = purchase(service)
        first = service.activate({"key": key, "machine_id": "mach-1"})
        second = service.activate({"key": key, "machine_id": "mach-1"})
        assert first["seat"] == second["seat"]
        assert service.db.seats_used(key) == 1

    def test_a_released_seat_can_be_taken_by_another_machine(self, service):
        key = purchase(service)
        for index in range(plans.TIERS[plans.PRO].limits.max_machines):
            service.activate({"key": key, "machine_id": f"mach-{index}"})
        service.deactivate({"key": key, "machine_id": "mach-0"})
        assert service.activate({"key": key, "machine_id": "new-laptop"})["token"]

    def test_refresh_needs_a_live_activation(self, service):
        key = purchase(service)
        service.activate({"key": key, "machine_id": "mach-1"})
        assert service.refresh({"key": key, "machine_id": "mach-1"})["token"]
        service.deactivate({"key": key, "machine_id": "mach-1"})
        with pytest.raises(HttpError) as caught:
            service.refresh({"key": key, "machine_id": "mach-1"})
        assert caught.value.status == 403

    def test_an_unknown_key_is_a_404(self, service):
        with pytest.raises(HttpError) as caught:
            service.activate({"key": keys.generate(), "machine_id": "m1"})
        assert caught.value.status == 404

    def test_a_missing_field_is_a_400(self, service):
        with pytest.raises(HttpError) as caught:
            service.activate({"key": purchase(service)})
        assert caught.value.status == 400


# -- trials --------------------------------------------------------------

class TestTrials:
    def test_a_first_trial_runs_the_full_72_hours(self, service, keypair):
        _seed, public = keypair
        answer = service.trial({"machine_id": "fresh-machine"})
        assert (answer["ends_at"] - answer["started_at"]) == plans.TRIAL_HOURS * 3600
        token = tokens.verify_token(answer["token"], public)
        assert token.tier == plans.TRIAL

    def test_asking_twice_resumes_the_same_clock(self, service):
        first = service.trial({"machine_id": "same-machine"})
        second = service.trial({"machine_id": "same-machine"})
        assert first["started_at"] == second["started_at"]

    def test_a_used_up_trial_is_gone(self, service):
        """Reinstalling four days later must not buy another 72 hours."""
        service.trial({"machine_id": "old-machine"})
        with service.db.write() as connection:
            connection.execute("UPDATE trials SET started_at = ? WHERE machine_id = ?",
                               (time.time() - 100 * 3600, "old-machine"))
        with pytest.raises(HttpError) as caught:
            service.trial({"machine_id": "old-machine"})
        assert caught.value.status == 410


# -- checkout ------------------------------------------------------------

class TestCheckout:
    def test_a_subscription_uses_subscription_mode(self, service):
        answer = service.checkout({"sku": "pro-subscription-monthly",
                                   "email": "mike@example.com"})
        assert answer["url"].startswith("https://checkout.stripe.test/")
        call = service.stripe.checkout_calls[-1]
        assert call["mode"] == "subscription"
        assert call["price_id"] == "price_pro_m"
        assert call["metadata"]["sku"] == "pro-subscription-monthly"

    def test_a_perpetual_purchase_uses_payment_mode(self, service):
        service.checkout({"sku": "pro-perpetual-once"})
        assert service.stripe.checkout_calls[-1]["mode"] == "payment"

    def test_an_upgrade_carries_the_existing_key(self, service):
        key = purchase(service)
        service.checkout({"sku": "pro-perpetual-once", "key": key})
        call = service.stripe.checkout_calls[-1]
        assert call["metadata"]["licence_key"] == key
        assert call["client_reference"] == key

    def test_an_unknown_plan_is_a_400(self, service):
        with pytest.raises(HttpError) as caught:
            service.checkout({"sku": "platinum-forever"})
        assert caught.value.status == 400

    def test_a_plan_with_no_stripe_price_is_a_500_not_a_free_licence(self, service):
        with pytest.raises(HttpError) as caught:
            service.checkout({"sku": "agency-subscription-monthly"})
        assert caught.value.status == 500


# -- issuance rules ------------------------------------------------------

class TestIssuer:
    def test_terms_match_the_catalogue(self):
        terms = issuer.terms_for("agency-subscription-yearly")
        assert terms["tier"] == plans.AGENCY
        assert terms["max_machines"] == 10
        assert terms["expires_at"] > time.time() + 360 * DAY

    def test_an_unknown_sku_raises(self):
        with pytest.raises(ValueError):
            issuer.terms_for("nope")

    def test_perpetual_tokens_carry_no_expiry_even_if_the_row_has_one(self):
        """A perpetual owner must never be locked out by a stray date."""
        token = issuer.issue({"key": "K", "tier": plans.PRO,
                              "model": plans.PERPETUAL,
                              "expires_at": time.time() - DAY}, "m1")
        assert token.expires_at is None

    def test_an_early_update_renewal_adds_on_rather_than_resetting(self):
        future = time.time() + 100 * DAY
        fields = issuer.extend_updates({"updates_until": future})
        assert fields["updates_until"] > future + 300 * DAY

    def test_a_trial_token_expires_from_when_the_trial_began(self):
        began = time.time() - 70 * 3600
        token = issuer.issue_trial("m1", began)
        assert token.expires_at == began + plans.TRIAL_HOURS * 3600
        assert token.refresh_after <= token.expires_at


# -- the WSGI layer ------------------------------------------------------

class TestHttp:
    def call(self, app, method, path, body=b"", headers=None):
        environ = {"REQUEST_METHOD": method, "PATH_INFO": path,
                   "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)}
        environ.update(headers or {})
        captured = {}

        def start_response(status, _headers):
            captured["status"] = int(status.split()[0])

        chunks = app(environ, start_response)
        return captured["status"], json.loads(b"".join(chunks))

    def test_health_and_pricing_are_public(self, service):
        app = make_app(service)
        status, body = self.call(app, "GET", "/healthz")
        assert status == 200 and body["ok"]
        status, body = self.call(app, "GET", "/v1/pricing")
        assert status == 200
        assert len(body["prices"]) == len(plans.catalog())
        assert body["trial_hours"] == 72

    def test_errors_come_back_as_json_the_app_can_show(self, service):
        app = make_app(service)
        status, body = self.call(app, "POST", "/v1/activate",
                                 json.dumps({"key": "LLSP-NOPE", "machine_id": "m"}).encode())
        assert status == 400
        assert "error" in body

    def test_unknown_paths_and_methods(self, service):
        app = make_app(service)
        assert self.call(app, "GET", "/v1/secrets")[0] == 404
        assert self.call(app, "DELETE", "/v1/activate")[0] == 405

    def test_an_oversized_body_is_refused(self, service):
        app = make_app(service)
        blob = b"x" * 200_000
        status, _body = self.call(app, "POST", "/v1/activate", blob)
        assert status == 413

    def test_a_handler_crash_does_not_leak_internals(self, service, monkeypatch):
        app = make_app(service)
        def explode(_body):
            raise RuntimeError("database on fire at /var/lib/secret")
        monkeypatch.setattr(service, "trial", explode)
        status, body = self.call(app, "POST", "/v1/trial", b"{}")
        assert status == 500
        assert "fire" not in body["error"]
        assert "internal error" in body["error"]


# -- the operator CLI ----------------------------------------------------

class TestCli:
    def test_set_public_key_writes_the_constant(self, tmp_path):
        """Release builds embed an existing key; keygen would mint a new one."""
        from payments import cli

        source = tmp_path / "public_key.py"
        source.write_text('EMBEDDED_PUBLIC_KEY = ""\nOTHER = 1\n', encoding="utf-8")
        _seed, public = crypto.generate_keypair()
        encoded = crypto.b64encode(public)

        assert cli.main(["set-public-key", encoded,
                         "--write-public", str(source)]) == 0
        written = source.read_text(encoding="utf-8")
        assert f'EMBEDDED_PUBLIC_KEY = "{encoded}"' in written
        assert "OTHER = 1" in written        # nothing else was touched

    @pytest.mark.parametrize("bad", ["", "not base64 @@@", "AAAA"])
    def test_set_public_key_refuses_a_key_that_would_verify_nothing(
            self, tmp_path, bad):
        from payments import cli

        source = tmp_path / "public_key.py"
        source.write_text('EMBEDDED_PUBLIC_KEY = ""\n', encoding="utf-8")
        assert cli.main(["set-public-key", bad, "--write-public", str(source)]) == 2
        assert source.read_text(encoding="utf-8") == 'EMBEDDED_PUBLIC_KEY = ""\n'

    def test_set_public_key_refuses_a_small_order_key(self, tmp_path):
        """A degenerate key verifies forged licences; it must never be embedded."""
        from payments import cli

        source = tmp_path / "public_key.py"
        source.write_text('EMBEDDED_PUBLIC_KEY = ""\n', encoding="utf-8")
        assert cli.main(["set-public-key", crypto.b64encode(b"\x00" * 32),
                         "--write-public", str(source)]) == 2

    def test_the_repository_ships_no_embedded_key(self):
        """The committed constant stays empty: keys come from the build, and a
        key in git is a key in every fork."""
        import licensing.public_key as key_module

        assert key_module.EMBEDDED_PUBLIC_KEY == ""

    def test_grant_issues_a_licence_with_no_payment(self, tmp_path, capsys):
        from payments import cli

        database = str(tmp_path / "licences.db")
        assert cli.main(["--database", database, "grant",
                         "--sku", "pro-perpetual-once",
                         "--email", "reviewer@example.com"]) == 0
        key = capsys.readouterr().out.strip().splitlines()[-1]
        assert keys.is_valid(key)
        licence = Database(database).licence(key)
        assert licence["model"] == plans.PERPETUAL
        assert licence["email"] == "reviewer@example.com"

    def test_revoke_ends_a_licence_and_frees_its_seats(self, tmp_path, capsys):
        from payments import cli

        database = str(tmp_path / "licences.db")
        cli.main(["--database", database, "grant", "--sku",
                  "pro-subscription-monthly", "--email", "x@example.com"])
        key = capsys.readouterr().out.strip().splitlines()[-1]
        store = Database(database)
        store.activate(key, "m1")
        assert cli.main(["--database", database, "revoke", key]) == 0
        refreshed = Database(database)
        assert refreshed.licence(key)["status"] == "refunded"
        assert refreshed.seats_used(key) == 0


# -- concurrency ---------------------------------------------------------

class TestConcurrentWrites:
    """Two requests writing at once must not share a transaction.

    The licence service runs under a threaded WSGI worker, so a Stripe webhook
    and a customer activation genuinely can land in Database.write() at the
    same moment. sqlite3 serialises individual statements but not
    transactions: without a lock both threads sit inside one, and whichever
    leaves first decides the fate of the other's work.
    """

    def test_a_failed_request_cannot_roll_back_a_successful_one(self, tmp_path):
        """The damaging case: money taken, licence row silently discarded."""
        import threading

        database = Database(str(tmp_path / "concurrent.db"))
        started = threading.Event()

        def succeeds():
            with database.write() as connection:
                connection.execute(
                    "INSERT INTO events (at, licence_key, kind) VALUES (?,?,?)",
                    (1.0, "PAID", "checkout.session.completed"))
                started.set()
                time.sleep(0.3)          # still open when the other arrives

        def fails():
            started.wait(timeout=2)
            time.sleep(0.05)
            try:
                with database.write() as connection:
                    connection.execute(
                        "INSERT INTO events (at, licence_key, kind) VALUES (?,?,?)",
                        (2.0, "JUNK", "boom"))
                    raise RuntimeError("this request failed")
            except RuntimeError:
                pass

        winner = threading.Thread(target=succeeds)
        loser = threading.Thread(target=fails)
        winner.start(); loser.start()
        winner.join(timeout=5); loser.join(timeout=5)

        surviving = [row["licence_key"]
                     for row in database.query("SELECT licence_key FROM events")]
        assert surviving == ["PAID"], (
            f"expected only the successful write to survive, got {surviving}")

    def test_parallel_writers_all_land(self, tmp_path):
        import threading

        database = Database(str(tmp_path / "parallel.db"))
        errors = []

        def write(index):
            try:
                with database.write() as connection:
                    connection.execute(
                        "INSERT INTO events (at, licence_key, kind) VALUES (?,?,?)",
                        (float(index), f"K{index}", "probe"))
                    time.sleep(0.02)
            except Exception as exc:  # noqa: BLE001 - the thing being tested
                errors.append(f"{type(exc).__name__}: {exc}")

        threads = [threading.Thread(target=write, args=(i,)) for i in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert not errors, errors
        assert database.query("SELECT COUNT(*) AS c FROM events")[0]["c"] == 12
        assert not database._connection.in_transaction

    def test_concurrent_activations_each_get_their_own_seat(self, tmp_path):
        """Seat numbers come from a read-then-write; they must not collide."""
        import threading

        database = Database(str(tmp_path / "seats.db"))
        database.create_licence(key="LLSP-SEATS", tier=plans.AGENCY,
                                model=plans.SUBSCRIPTION, max_machines=10)
        barrier = threading.Barrier(6)

        def activate(index):
            barrier.wait(timeout=5)
            database.activate("LLSP-SEATS", f"machine-{index}", f"box {index}")

        threads = [threading.Thread(target=activate, args=(i,)) for i in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        seats = sorted(row["seat"] for row in database.activations("LLSP-SEATS"))
        assert len(seats) == 6
        assert len(set(seats)) == 6, f"seat numbers collided: {seats}"

    def test_a_full_licence_cannot_be_overrun_by_a_race(self, tmp_path):
        """Eight machines rushing a three-seat licence must yield three.

        The check and the insert used to be separate calls, so simultaneous
        activations all read the old count and all got in — a customer paying
        for three seats and receiving as many as they could open at once.
        """
        import threading

        database = Database(str(tmp_path / "overrun.db"))
        database.create_licence(key="LLSP-FULL", tier=plans.PRO,
                                model=plans.SUBSCRIPTION, max_machines=3)
        barrier = threading.Barrier(8)
        admitted = []
        lock = threading.Lock()

        def rush(index):
            barrier.wait(timeout=5)
            record = database.activate("LLSP-FULL", f"machine-{index}",
                                       max_machines=3)
            if record is not None:
                with lock:
                    admitted.append(index)

        threads = [threading.Thread(target=rush, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert len(admitted) == 3, f"{len(admitted)} machines admitted, expected 3"
        assert database.seats_used("LLSP-FULL") == 3

    def test_reactivating_under_the_limit_is_not_refused(self, tmp_path):
        """A machine already holding a seat keeps it even on a full licence."""
        database = Database(str(tmp_path / "reactivate.db"))
        database.create_licence(key="LLSP-RE", tier=plans.SOLO,
                                model=plans.SUBSCRIPTION, max_machines=2)
        first = database.activate("LLSP-RE", "m1", max_machines=2)
        database.activate("LLSP-RE", "m2", max_machines=2)
        again = database.activate("LLSP-RE", "m1", max_machines=2)
        assert again is not None
        assert again["seat"] == first["seat"]
        assert database.activate("LLSP-RE", "m3", max_machines=2) is None
