"""The licence system as the app experiences it: keys, tokens, trials, gates.

Every test here drives a :class:`~licensing.manager.LicenseManager` built on a
throwaway keypair and a scratch state directory, so nothing touches a real
licence and nothing needs the network.
"""

from __future__ import annotations

import time

import pytest

from licensing import crypto, keys, machine, plans, storage, tokens, trial
from licensing.errors import (
    ClockTampered, InvalidKey, InvalidToken, LicenseError, SignatureInvalid,
    TrialExhausted,
)
from licensing.manager import (
    ACTIVE, CLOCK_TAMPERED, EXPIRED, GRACE_EXPIRED, INVALID, STALE, TRIAL,
    TRIAL_EXPIRED, UNLICENSED, LicenseManager,
)

DAY = 86400.0


@pytest.fixture(autouse=True)
def isolated_license_state(tmp_path, monkeypatch):
    """A blank install: scratch state directory, fixed machine id, no licence.

    The suite-wide fixture in ``conftest.py`` hands every other test a working
    Agency licence so they can exercise the app. These tests are about the
    licence system itself, so they start from nothing and install exactly what
    each case is testing.
    """
    state_dir = tmp_path / "licence-under-test"
    monkeypatch.setenv(storage.STATE_DIR_ENV, str(state_dir))
    monkeypatch.setenv(machine.MACHINE_ID_ENV, "test-machine")
    machine.reset_cache()
    storage.clear()
    yield state_dir
    machine.reset_cache()


@pytest.fixture
def keypair():
    return crypto.generate_keypair()


def make_token(seed, **overrides) -> str:
    """A signed licence, defaulting to a healthy monthly Pro subscription."""
    now = overrides.pop("now", time.time())
    fields = {
        "key": "LLSP-AAAAA-AAAAA-AAAAA-AAAAA",
        "tier": plans.PRO,
        "model": plans.SUBSCRIPTION,
        "machine_id": "test-machine",
        "issued_at": now,
        "refresh_after": now + 7 * DAY,
        "expires_at": now + 30 * DAY,
        "email": "mike@example.com",
    }
    fields.update(overrides)
    return tokens.sign_token(tokens.LicenseToken(**fields), seed)


def install(seed, **overrides) -> str:
    blob = make_token(seed, **overrides)
    storage.update(token=blob)
    return blob


# -- purchase keys -------------------------------------------------------

class TestKeys:
    def test_generated_keys_are_valid_and_canonical(self):
        for _ in range(20):
            key = keys.generate()
            assert keys.is_valid(key)
            assert keys.parse(key) == key
            assert key.startswith("LLSP-")
            assert len(key.split("-")) == 5

    def test_accepts_what_a_human_types(self):
        key = keys.generate()
        body = key[len("LLSP-"):]
        for variant in (key.lower(), body, key.replace("-", " "),
                        f"  {key}  ", key.replace("-", "")):
            assert keys.parse(variant) == key

    def test_confusable_characters_are_folded(self):
        """O for 0 and I for 1 are the two mistakes people actually make."""
        key = keys.generate()
        if "0" in key or "1" in key:
            typo = key.replace("0", "O").replace("1", "I")
            assert keys.parse(typo) == key

    def test_a_single_wrong_character_fails_the_checksum(self):
        key = keys.generate()
        for position in range(len("LLSP-"), len(key)):
            if key[position] == "-":
                continue
            wrong = "B" if key[position] != "B" else "C"
            broken = key[:position] + wrong + key[position + 1:]
            assert not keys.is_valid(broken), f"typo at {position} slipped through"

    def test_rejects_wrong_lengths_and_alphabets(self):
        for text in ("", "LLSP", "LLSP-AAAAA", "LLSP-AAAAA-AAAAA-AAAAA-AAAAAA"):
            with pytest.raises(InvalidKey):
                keys.parse(text)

    def test_masking_hides_the_middle_but_stays_recognisable(self):
        key = keys.generate()
        masked = keys.masked(key)
        assert masked.startswith(key.split("-")[0] + "-" + key.split("-")[1])
        assert masked.endswith(key.split("-")[-1])
        assert "•" in masked
        assert keys.masked("nonsense") == "—"


# -- tokens --------------------------------------------------------------

class TestTokens:
    def test_round_trip(self, keypair):
        seed, public = keypair
        blob = make_token(seed)
        token = tokens.verify_token(blob, public)
        assert token.tier == plans.PRO
        assert token.machine_id == "test-machine"
        assert plans.SITE_INTEL in token.features()

    def test_a_forged_payload_is_rejected(self, keypair):
        seed, public = keypair
        blob = make_token(seed, tier=plans.SOLO)
        magic, payload, signature = blob.split(".")
        upgraded = tokens.LicenseToken(
            key="LLSP-AAAAA-AAAAA-AAAAA-AAAAA", tier=plans.AGENCY,
            model=plans.SUBSCRIPTION, machine_id="test-machine",
            issued_at=time.time(), refresh_after=time.time() + 7 * DAY)
        tampered = f"{magic}.{crypto.b64encode(upgraded.payload())}.{signature}"
        with pytest.raises(SignatureInvalid):
            tokens.verify_token(tampered, public)

    def test_a_licence_from_another_issuer_is_rejected(self, keypair):
        _seed, public = keypair
        other_seed, _other_public = crypto.generate_keypair()
        with pytest.raises(SignatureInvalid):
            tokens.verify_token(make_token(other_seed), public)

    def test_garbage_is_rejected_as_damage_not_forgery(self, keypair):
        _seed, public = keypair
        for text in ("", "hello", "LLSPv1.only-two-parts", "LLSPv9.a.b"):
            with pytest.raises(InvalidToken):
                tokens.verify_token(text, public)

    def test_perpetual_licences_never_expire_and_grace_generously(self, keypair):
        seed, public = keypair
        token = tokens.verify_token(
            make_token(seed, model=plans.PERPETUAL, expires_at=None), public)
        assert token.expires_at is None
        assert not token.expired(time.time() + 3650 * DAY)
        assert token.grace_days == tokens.PERPETUAL_OFFLINE_GRACE_DAYS
        assert token.grace_days > tokens.OFFLINE_GRACE_DAYS

    def test_payload_bytes_are_stable(self, keypair):
        """Two serialisations of the same licence must be byte-identical."""
        seed, _public = keypair
        now = time.time()
        first = make_token(seed, now=now)
        second = make_token(seed, now=now)
        assert first == second


# -- the trial -----------------------------------------------------------

class TestTrial:
    def test_unstarted_trial_grants_nothing(self, keypair):
        _seed, public = keypair
        manager = LicenseManager(public_key_bytes=public)
        status = manager.status()
        assert status.state == UNLICENSED
        assert not status.licensed
        assert not manager.allows(plans.SCRAPE_MAPS)

    def test_provisional_trial_is_short_until_confirmed(self):
        trial.begin()
        assert trial.needs_confirmation()
        left = trial.seconds_left()
        assert 0 < left <= trial.PROVISIONAL_HOURS * 3600
        trial.confirm(time.time())
        assert not trial.needs_confirmation()
        assert trial.seconds_left() > trial.PROVISIONAL_HOURS * 3600

    def test_confirmed_trial_runs_72_hours(self):
        started = time.time()
        trial.confirm(started)
        assert trial.active(started + 71 * 3600)
        assert not trial.active(started + 73 * 3600)
        assert plans.TRIAL_HOURS == 72

    def test_the_server_start_time_wins_over_a_fresh_local_one(self):
        """Reinstalling must resume the old clock, not start a new one."""
        long_ago = time.time() - 100 * 3600
        trial.begin()                       # a fresh local start
        trial.confirm(long_ago)             # …then the server's memory
        assert not trial.active()
        assert trial.seconds_left() == 0

    def test_an_exhausted_trial_cannot_be_restarted(self):
        trial.exhaust()
        with pytest.raises(TrialExhausted):
            trial.begin()
        assert not trial.active()

    def test_countdown_reads_naturally(self):
        started = time.time()
        trial.confirm(started)
        assert "hours left" in trial.describe(started + 3600)
        assert "minute" in trial.describe(started + 71.9 * 3600)
        assert trial.describe(started + 100 * 3600) == "Your trial has ended."

    def test_trial_grants_every_feature_but_caps_the_output(self, keypair):
        _seed, public = keypair
        trial.confirm(time.time())
        manager = LicenseManager(public_key_bytes=public)
        assert manager.status().state == TRIAL
        for feature in plans.ALL_FEATURES:
            assert manager.allows(feature), feature
        assert manager.max_results(500) == 25
        assert manager.emails_remaining_today() == 0   # dry run only
        assert manager.limits().max_export_rows == 25


# -- the state machine ---------------------------------------------------

class TestStatus:
    def test_a_healthy_licence_is_active(self, keypair):
        seed, public = keypair
        install(seed)
        status = LicenseManager(public_key_bytes=public).status()
        assert status.state == ACTIVE
        assert status.tier == plans.PRO
        assert status.licensed and status.paid
        assert "renews in" in status.headline()

    def test_a_licence_past_its_refresh_date_still_works(self, keypair):
        seed, public = keypair
        now = time.time()
        install(seed, refresh_after=now - DAY, expires_at=now + 20 * DAY)
        manager = LicenseManager(public_key_bytes=public)
        assert manager.status().state == STALE
        assert manager.status().licensed
        assert manager.allows(plans.SCRAPE_MAPS)

    def test_offline_past_the_grace_window_falls_back_to_reader(self, keypair):
        seed, public = keypair
        now = time.time()
        install(seed,
                refresh_after=now - (tokens.OFFLINE_GRACE_DAYS + 1) * DAY,
                expires_at=now + 300 * DAY)
        manager = LicenseManager(public_key_bytes=public)
        status = manager.status()
        assert status.state == GRACE_EXPIRED
        assert not status.licensed
        assert status.tier == plans.READER
        assert not manager.allows(plans.SCRAPE_MAPS)
        # …but past work is still readable and exportable.
        assert manager.allows(plans.EXPORT_CSV)

    def test_an_expired_subscription_falls_back_to_reader(self, keypair):
        seed, public = keypair
        now = time.time()
        install(seed, refresh_after=now + DAY, expires_at=now - DAY)
        manager = LicenseManager(public_key_bytes=public)
        assert manager.status().state == EXPIRED
        assert manager.allows(plans.EXPORT_CSV)
        assert not manager.allows(plans.EMAIL_SEND)

    def test_a_perpetual_licence_survives_a_long_time_offline(self, keypair):
        seed, public = keypair
        now = time.time()
        install(seed, model=plans.PERPETUAL, expires_at=None,
                refresh_after=now - 100 * DAY,
                updates_until=now - 30 * DAY)
        manager = LicenseManager(public_key_bytes=public)
        status = manager.status()
        assert status.state == STALE
        assert status.licensed
        assert status.perpetual
        assert status.headline() == "Pro — owned"

    def test_a_licence_for_another_machine_is_refused(self, keypair):
        seed, public = keypair
        install(seed, machine_id="somebody-elses-laptop")
        status = LicenseManager(public_key_bytes=public).status()
        assert status.state == INVALID
        assert "different computer" in status.detail

    def test_a_build_with_no_public_key_says_so(self, keypair):
        seed, _public = keypair
        install(seed)
        manager = LicenseManager(public_key_bytes=b"")
        status = manager.status()
        assert status.state == INVALID
        assert "no licence key configured" in status.detail

    def test_winding_the_clock_back_is_caught(self, keypair):
        seed, public = keypair
        install(seed)
        manager = LicenseManager(public_key_bytes=public)
        assert manager.status().state == ACTIVE

        # Time travel: a year into the past, well beyond the drift allowance.
        past = LicenseManager(public_key_bytes=public,
                              now=lambda: time.time() - 365 * DAY)
        status = past.status()
        assert status.state == CLOCK_TAMPERED
        assert not status.licensed
        assert ClockTampered.message in status.detail

    def test_small_clock_drift_is_tolerated(self, keypair):
        seed, public = keypair
        install(seed)
        LicenseManager(public_key_bytes=public).status()
        drifted = LicenseManager(public_key_bytes=public,
                                 now=lambda: time.time() - 3600)
        assert drifted.status().state == ACTIVE

    def test_trial_expiry_is_reported_as_a_trial_not_a_failure(self, keypair):
        _seed, public = keypair
        trial.confirm(time.time() - 100 * 3600)
        manager = LicenseManager(public_key_bytes=public)
        assert manager.status().state == TRIAL_EXPIRED
        assert "trial has ended" in manager.status().detail


# -- entitlements --------------------------------------------------------

class TestEntitlements:
    @pytest.mark.parametrize("tier,feature,expected", [
        (plans.SOLO, plans.SCRAPE_MAPS, True),
        (plans.SOLO, plans.SITE_INTEL, False),
        (plans.SOLO, plans.EXPORT_XLSX, False),
        (plans.PRO, plans.SITE_INTEL, True),
        (plans.PRO, plans.SCHOOL_PIPELINE, True),
        (plans.PRO, plans.AUTOMATION_CLI, False),
        (plans.AGENCY, plans.AUTOMATION_CLI, True),
        (plans.AGENCY, plans.EMAIL_BRANDING, True),
    ])
    def test_tier_features(self, keypair, tier, feature, expected):
        seed, public = keypair
        install(seed, tier=tier)
        assert LicenseManager(public_key_bytes=public).allows(feature) is expected

    def test_check_names_the_tier_that_would_unlock_it(self, keypair):
        seed, public = keypair
        install(seed, tier=plans.SOLO)
        manager = LicenseManager(public_key_bytes=public)
        manager.check(plans.SCRAPE_MAPS)  # allowed: no exception
        with pytest.raises(LicenseError) as caught:
            manager.check(plans.SITE_INTEL)
        assert "Pro" in str(caught.value)
        assert "Solo" in str(caught.value)

    def test_extra_features_are_granted_on_top_of_the_tier(self, keypair):
        """A one-off deal or a beta invite, without inventing a tier for it."""
        seed, public = keypair
        install(seed, tier=plans.SOLO, extra_features=[plans.SITE_INTEL])
        manager = LicenseManager(public_key_bytes=public)
        assert manager.allows(plans.SITE_INTEL)
        assert not manager.allows(plans.AUTOMATION_CLI)

    def test_extra_features_die_with_the_licence(self, keypair):
        seed, public = keypair
        now = time.time()
        install(seed, tier=plans.SOLO, extra_features=[plans.SITE_INTEL],
                expires_at=now - DAY)
        assert not LicenseManager(public_key_bytes=public).allows(plans.SITE_INTEL)

    def test_result_caps_clip_rather_than_refuse(self, keypair):
        seed, public = keypair
        install(seed, tier=plans.SOLO)
        manager = LicenseManager(public_key_bytes=public)
        assert manager.max_results(50) == 50
        assert manager.max_results(5000) == 200
        assert manager.max_industries(9) == 2

    def test_agency_has_no_ceiling(self, keypair):
        seed, public = keypair
        install(seed, tier=plans.AGENCY)
        manager = LicenseManager(public_key_bytes=public)
        assert manager.max_results(100_000) == 100_000
        assert manager.max_industries(50) == 50

    def test_daily_email_allowance_is_spent_and_remembered(self, keypair):
        seed, public = keypair
        install(seed, tier=plans.SOLO)
        manager = LicenseManager(public_key_bytes=public)
        assert manager.emails_remaining_today() == 100
        manager.record_emails_sent(30)
        assert manager.emails_remaining_today() == 70
        # A second manager reads the same file: a restart does not refill it.
        assert LicenseManager(public_key_bytes=public).emails_remaining_today() == 70
        manager.record_emails_sent(200)
        assert manager.emails_remaining_today() == 0

    def test_restrictions_read_as_english(self, keypair):
        seed, public = keypair
        install(seed, tier=plans.PRO)
        lines = LicenseManager(public_key_bytes=public).restrictions()
        assert any("1000 results" in line for line in lines)
        assert any("500 emails" in line for line in lines)


# -- pricing -------------------------------------------------------------

class TestPricing:
    def test_both_pricing_models_exist_for_every_tier(self):
        skus = {price.sku for price in plans.catalog()}
        for tier in (plans.SOLO, plans.PRO, plans.AGENCY):
            assert f"{tier}-subscription-monthly" in skus
            assert f"{tier}-subscription-yearly" in skus
            assert f"{tier}-perpetual-once" in skus

    def test_yearly_is_cheaper_than_twelve_months(self):
        for tier in (plans.SOLO, plans.PRO, plans.AGENCY):
            monthly = plans.price_for(f"{tier}-subscription-monthly").cents
            yearly = plans.price_for(f"{tier}-subscription-yearly").cents
            assert yearly < monthly * 12

    def test_perpetual_costs_more_than_a_year_of_subscription(self):
        """Otherwise nobody would ever subscribe."""
        for tier in (plans.SOLO, plans.PRO, plans.AGENCY):
            yearly = plans.price_for(f"{tier}-subscription-yearly").cents
            once = plans.price_for(f"{tier}-perpetual-once").cents
            assert once > yearly

    def test_tiers_get_more_expensive_and_more_capable(self):
        previous_price, previous_features = 0, set()
        for tier in (plans.SOLO, plans.PRO, plans.AGENCY):
            price = plans.price_for(f"{tier}-subscription-monthly").cents
            features = set(plans.TIERS[tier].features)
            assert price > previous_price
            assert previous_features <= features, f"{tier} drops a feature"
            previous_price, previous_features = price, features

    def test_prices_display_as_money(self):
        assert plans.price_for("pro-subscription-monthly").display == "$89/mo"
        assert plans.price_for("pro-subscription-yearly").display == "$890/yr"
        assert plans.price_for("pro-perpetual-once").display == "$1,299"

    def test_renewal_is_a_fraction_of_the_original(self):
        once = plans.TIERS[plans.PRO].perpetual_cents
        assert plans.renewal_cents(plans.PRO) == round(once * 0.40)
        assert plans.renewal_cents(plans.TRIAL) is None

    def test_unknown_tiers_degrade_to_reader_rather_than_crashing(self):
        """A licence from a newer server must not break an older app."""
        assert plans.tier("enterprise-quantum").key == plans.READER
        assert plans.rank("nonsense") == 0
        assert plans.at_least(plans.AGENCY, plans.PRO)
        assert not plans.at_least(plans.SOLO, plans.PRO)


# -- storage -------------------------------------------------------------

class TestStorage:
    def test_a_corrupt_state_file_costs_nothing(self):
        storage.state_path().parent.mkdir(parents=True, exist_ok=True)
        storage.state_path().write_text("{not json", encoding="utf-8")
        state = storage.load()
        assert state["token"] == ""
        assert storage.save(state) is not None

    def test_clear_removes_everything(self, keypair):
        seed, _public = keypair
        install(seed)
        assert storage.load()["token"]
        storage.clear()
        assert storage.load()["token"] == ""

    def test_usage_counters_are_per_day(self):
        assert storage.bump_usage("emails", 5, day="2026-01-01") == 5
        assert storage.bump_usage("emails", 5, day="2026-01-01") == 10
        assert storage.usage_today("emails", day="2026-01-02") == 0

    def test_the_clock_high_water_mark_only_moves_forward(self):
        now = time.time()
        assert storage.check_clock(now)
        assert storage.high_water_mark() >= now
        assert not storage.check_clock(now - 30 * DAY)
        assert storage.high_water_mark() >= now   # a rollback does not lower it
