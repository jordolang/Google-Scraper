"""The one object the rest of the app asks "am I allowed to do this?".

Everything else in this package is machinery; :class:`LicenseManager` is the
face of it. A page calls :meth:`allows` before enabling a button and
:meth:`check` before starting work, and gets back an answer computed entirely
from the signed token on disk — no network, no blocking, no surprises when the
customer is on a plane.

The state machine, in the order it is decided:

======================  ====================================================
``clock_tampered``      the system clock went backwards past what we saw
``invalid``             the licence file is damaged or forged
``expired``             a subscription's paid period ended
``grace_expired``       offline too long past the token's refresh date
``active`` / ``stale``  a good licence; ``stale`` just wants a refresh soon
``trial`` / ``trial_expired``
``unlicensed``          nothing has ever been activated here
======================  ====================================================

Only ``active``, ``stale`` and ``trial`` grant features. Everything else falls
to the reader tier, where the app still opens and past work is still readable
and exportable — a customer whose card expired should never be locked away
from data they collected.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, List, Optional

from . import keys, machine, plans, public_key, storage, tokens, trial
from .client import LicenseClient
from .errors import (
    ActivationFailed, ClockTampered, InvalidToken, LicenseError,
    ServiceUnreachable, TrialExhausted,
)
from .tokens import LicenseToken

# Status constants — compared by name across the GUI, TUI and tests.
UNLICENSED = "unlicensed"
TRIAL = "trial"
TRIAL_EXPIRED = "trial_expired"
ACTIVE = "active"
STALE = "stale"
GRACE_EXPIRED = "grace_expired"
EXPIRED = "expired"
INVALID = "invalid"
CLOCK_TAMPERED = "clock_tampered"

#: Statuses that let the customer actually work.
GRANTING = (TRIAL, ACTIVE, STALE)


@dataclass(frozen=True)
class Status:
    """A snapshot of where this install stands. Cheap to build, safe to cache."""

    state: str
    tier: str
    model: str = ""
    expires_at: Optional[float] = None
    refresh_after: Optional[float] = None
    seat: int = 1
    key: str = ""
    email: str = ""
    #: Set when the state itself is the explanation — expired, tampered, forged.
    detail: str = ""

    @property
    def licensed(self) -> bool:
        """Whether the app should let the customer do paid work."""
        return self.state in GRANTING

    @property
    def paid(self) -> bool:
        return self.state in (ACTIVE, STALE)

    @property
    def perpetual(self) -> bool:
        return self.model == plans.PERPETUAL

    @property
    def tier_name(self) -> str:
        return plans.tier(self.tier).name

    def days_left(self, now: Optional[float] = None) -> Optional[int]:
        if self.expires_at is None:
            return None
        now = time.time() if now is None else now
        return max(0, int((self.expires_at - now) // 86400))

    def headline(self, now: Optional[float] = None) -> str:
        """One line for the sidebar."""
        if self.state == TRIAL:
            return trial.describe(now)
        if self.state in (ACTIVE, STALE):
            if self.perpetual:
                return f"{self.tier_name} — owned"
            days = self.days_left(now)
            if days is None:
                return self.tier_name
            return f"{self.tier_name} — renews in {days} day{'s' if days != 1 else ''}"
        return {
            TRIAL_EXPIRED: "Trial ended — choose a plan",
            EXPIRED: "Subscription ended — renew to continue",
            GRACE_EXPIRED: "Licence needs re-checking online",
            INVALID: "Licence file unreadable",
            CLOCK_TAMPERED: "System clock is wrong",
            UNLICENSED: "No licence — start your 72-hour trial",
        }.get(self.state, "Unlicensed")


class LicenseManager:
    """Reads state, answers questions, and (when asked) talks to the service."""

    def __init__(self, client: Optional[LicenseClient] = None,
                 public_key_bytes: Optional[bytes] = None,
                 now: Optional[Callable[[], float]] = None) -> None:
        self._client = client
        self._public_key = public_key_bytes
        self._now = now or time.time
        self._cached: Optional[Status] = None
        self._token: Optional[LicenseToken] = None

    # -- plumbing ---------------------------------------------------------
    @property
    def client(self) -> LicenseClient:
        if self._client is None:
            self._client = LicenseClient()
        return self._client

    def public_key(self) -> bytes:
        return self._public_key if self._public_key is not None else public_key.public_key()

    def machine_id(self) -> str:
        return machine.fingerprint()

    def invalidate(self) -> None:
        """Drop the cached status so the next read hits disk again."""
        self._cached = None
        self._token = None

    # -- reading the current state ---------------------------------------
    def token(self) -> Optional[LicenseToken]:
        """The verified token, or None when there is none we trust."""
        self.status()  # populates _token as a side effect of deciding state
        return self._token

    def status(self, refresh: bool = False) -> Status:
        if self._cached is not None and not refresh:
            return self._cached
        self._cached = self._compute()
        return self._cached

    def _compute(self) -> Status:
        self._token = None
        now = self._now()

        # A clock that has moved backwards invalidates every time-based check
        # below it, so it is decided first and nothing else is trusted.
        if not storage.check_clock(now):
            return Status(CLOCK_TAMPERED, plans.READER,
                          detail=ClockTampered.message)

        state = storage.load()
        blob = str(state.get("token") or "")
        if blob:
            key_bytes = self.public_key()
            if not key_bytes:
                # A build with no embedded key cannot verify anything. Say so
                # rather than silently treating a real licence as forged.
                return Status(INVALID, plans.READER,
                              detail=("This build has no licence key configured. "
                                      "Reinstall from a release download."))
            try:
                token = tokens.verify_token(blob, key_bytes)
            except InvalidToken as exc:
                return Status(INVALID, plans.READER, detail=str(exc))
            if token.machine_id and token.machine_id != self.machine_id():
                return Status(INVALID, plans.READER,
                              detail=("This licence was activated on a different "
                                      "computer. Activate this one to move the seat."))
            self._token = token
            if token.expired(now):
                return self._status_from(token, EXPIRED,
                                         "The paid period for this licence has ended.")
            if token.grace_expired(now):
                return self._status_from(
                    token, GRACE_EXPIRED,
                    ("This licence has not been able to check in for "
                     f"{token.grace_days} days. Connect to the internet once to "
                     "carry on."))
            if token.tier == plans.TRIAL:
                # A trial delivered as a token still reports as a trial, so the
                # UI shows a countdown rather than a subscription renewal date.
                return self._status_from(token, TRIAL, "")
            return self._status_from(token, STALE if token.stale(now) else ACTIVE, "")

        # No token: fall back to whatever the trial record says.
        if trial.active(now, state):
            return Status(TRIAL, plans.TRIAL, detail="")
        if trial.started(state):
            return Status(TRIAL_EXPIRED, plans.READER,
                          detail="Your 72-hour trial has ended.")
        return Status(UNLICENSED, plans.READER, detail="")

    def _status_from(self, token: LicenseToken, state: str, detail: str) -> Status:
        return Status(
            state=state,
            tier=token.tier if state in GRANTING else plans.READER,
            model=token.model,
            expires_at=token.expires_at,
            refresh_after=token.refresh_after,
            seat=token.seat,
            key=token.key,
            email=token.email,
            detail=detail,
        )

    # -- entitlements -----------------------------------------------------
    def features(self) -> frozenset:
        status = self.status()
        base = frozenset(plans.tier(status.tier).features)
        token = self._token
        if status.licensed and token is not None:
            return base | frozenset(token.extra_features)
        return base

    def limits(self) -> plans.Limits:
        return plans.tier(self.status().tier).limits

    def allows(self, feature: str) -> bool:
        """Whether this install may use ``feature`` right now."""
        return feature in self.features()

    def check(self, feature: str) -> None:
        """Raise :class:`LicenseError` unless ``feature`` is allowed.

        For the places where a silent no would be worse than an error — a
        scripted run, a background worker — the message names the tier that
        would unlock it.
        """
        if self.allows(feature):
            return
        label = plans.FEATURE_LABELS.get(feature, feature)
        upgrade = self.lowest_tier_with(feature)
        if upgrade:
            raise LicenseError(
                f"{label} is part of {plans.tier(upgrade).name}. "
                f"Your licence is {self.status().tier_name}."
            )
        raise LicenseError(f"{label} is not available on your licence.")

    def lowest_tier_with(self, feature: str) -> str:
        """The cheapest sold tier that includes ``feature``, or ""."""
        for key in (plans.SOLO, plans.PRO, plans.AGENCY):
            if feature in plans.TIERS[key].features:
                return key
        return ""

    def cap(self, value: int, limit: Optional[int]) -> int:
        """``value`` clipped to ``limit``; ``None`` means no ceiling."""
        if limit is None:
            return value
        return min(value, limit)

    def max_results(self, requested: int) -> int:
        return self.cap(requested, self.limits().max_results_per_search)

    def max_industries(self, requested: int) -> int:
        return self.cap(requested, self.limits().max_industries_per_batch)

    def emails_remaining_today(self) -> int:
        """How many more emails may be sent today under this licence."""
        allowed = self.limits().max_emails_per_day
        if allowed <= 0:
            return 0
        return max(0, allowed - storage.usage_today("emails"))

    def record_emails_sent(self, count: int) -> int:
        if count <= 0:
            return storage.usage_today("emails")
        return storage.bump_usage("emails", count)

    def restrictions(self) -> List[str]:
        """Plain-English notes for the UI: what this licence will not do."""
        limits = self.limits()
        status = self.status()
        notes: List[str] = []
        if not status.licensed:
            notes.append("Read-only: activate a licence to scrape or send.")
            return notes
        if limits.max_results_per_search is not None:
            notes.append(f"Up to {limits.max_results_per_search} results per search.")
        if limits.max_emails_per_day <= 0:
            notes.append("Email sending is dry-run only.")
        else:
            notes.append(f"Up to {limits.max_emails_per_day} emails per day.")
        if limits.max_industries_per_batch is not None:
            notes.append(f"{limits.max_industries_per_batch} "
                         f"{'industry' if limits.max_industries_per_batch == 1 else 'industries'} per batch.")
        if limits.max_export_rows is not None:
            notes.append(f"Exports are capped at {limits.max_export_rows} rows.")
        return notes

    # -- actions that touch the network -----------------------------------
    def start_trial(self, email: str = "") -> Status:
        """Begin the 72-hour trial, online if possible and locally if not."""
        if trial.record().get("exhausted"):
            raise TrialExhausted()
        machine_id = self.machine_id()
        try:
            answer = self.client.trial(machine_id, email=email,
                                       label=machine.describe())
        except ServiceUnreachable:
            # Provisional start: a few hours now, the full 72 once we can ask.
            trial.begin()
            self.invalidate()
            return self.status(refresh=True)
        except TrialExhausted:
            trial.exhaust()
            self.invalidate()
            raise
        blob = str(answer.get("token") or "")
        started_at = float(answer.get("started_at") or self._now())
        trial.confirm(started_at)
        if blob:
            storage.update(token=blob)
        self.invalidate()
        return self.status(refresh=True)

    def activate(self, typed_key: str) -> Status:
        """Bind a purchase key to this machine and store the token it returns."""
        key = keys.parse(typed_key)  # raises InvalidKey on a typo, before any I/O
        answer = self.client.activate(key, self.machine_id(),
                                      label=machine.describe())
        blob = str(answer.get("token") or "")
        if not blob:
            raise ActivationFailed("The licence service returned no licence.")
        self._store_verified(blob)
        return self.status(refresh=True)

    def refresh(self) -> Status:
        """Swap the stored token for a newer one. Safe to call often."""
        token = self.token()
        if token is None or not token.key:
            return self.status()
        answer = self.client.refresh(token.key, self.machine_id())
        blob = str(answer.get("token") or "")
        if blob:
            self._store_verified(blob)
        return self.status(refresh=True)

    def refresh_if_due(self) -> Status:
        """Refresh only when the token asks for it, swallowing offline errors.

        This is what the app calls at start-up: it must never block, never
        raise, and never turn a working install into a broken one because the
        service happened to be down.
        """
        status = self.status()
        needs = status.state in (STALE, GRACE_EXPIRED)
        if status.state == TRIAL and trial.needs_confirmation():
            try:
                return self.start_trial()
            except LicenseError:
                return status
        if not needs:
            return status
        try:
            return self.refresh()
        except LicenseError:
            return status

    def deactivate(self, *, local_only: bool = False) -> Status:
        """Release this machine.

        The seat is freed on the server first, because the failure that matters
        is a customer who wipes their local licence and then finds the seat
        still taken. ``local_only`` is the escape hatch for a machine that will
        never reach the service again.
        """
        token = self.token()
        if token is not None and token.key and not local_only:
            self.client.deactivate(token.key, self.machine_id())
        storage.clear()
        machine.reset_cache()
        self.invalidate()
        return self.status(refresh=True)

    def checkout_url(self, sku: str, email: str = "") -> str:
        """A Stripe Checkout link for ``sku``, for the app to open in a browser."""
        token = self.token()
        answer = self.client.checkout(sku, email=email or (token.email if token else ""),
                                      key=token.key if token else "")
        url = str(answer.get("url") or "")
        if not url:
            raise ActivationFailed("The licence service returned no checkout link.")
        return url

    # -- internals --------------------------------------------------------
    def _store_verified(self, blob: str) -> None:
        """Verify before writing, so a bad reply cannot brick a good install."""
        key_bytes = self.public_key()
        if key_bytes:
            tokens.verify_token(blob, key_bytes)  # raises on anything wrong
        storage.update(token=blob)
        self.invalidate()


_default: Optional[LicenseManager] = None


def get_manager() -> LicenseManager:
    """The process-wide manager. The GUI, TUI and scripts all share one.

    Named ``get_manager`` rather than ``manager`` so it cannot shadow the
    :mod:`licensing.manager` module for anyone doing ``from licensing import
    manager`` — that import should give the module, every time.
    """
    global _default
    if _default is None:
        _default = LicenseManager()
    return _default


def reset_manager() -> None:
    """Drop the shared manager — used by tests and after a config move."""
    global _default
    _default = None
