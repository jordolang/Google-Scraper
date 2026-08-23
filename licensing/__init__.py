"""Licensing for Local Lead Scraper Pro.

The short version for anyone wiring a new feature up:

    from licensing import get_manager, plans

    if get_manager().allows(plans.SITE_INTEL):
        ...                     # enable the button
    get_manager().check(plans.EMAIL_SEND)  # or raise with a message worth showing

Everything is decided from a signed licence file on disk, so these calls are
cheap and work offline. The network is only involved when someone activates,
starts a trial, or the token is old enough to want refreshing.

The pieces, in the order they matter:

* :mod:`licensing.plans` — the tiers, the two pricing models, the feature map.
* :mod:`licensing.manager` — :class:`~licensing.manager.LicenseManager`, the
  object everything else talks to.
* :mod:`licensing.tokens` — the signed licence format and its two clocks.
* :mod:`licensing.trial` — the 72-hour trial and its one-per-machine rule.
* :mod:`licensing.keys` — the ``LLSP-…`` key customers actually type.
* :mod:`licensing.machine` — the fingerprint a seat is bound to.
* :mod:`licensing.storage` — the local state file and the clock guard.
* :mod:`licensing.client` — the five calls to the licence service.
"""

from __future__ import annotations

from . import errors, keys, machine, manager, plans, storage, tokens, trial  # noqa: F401
from .errors import (  # noqa: F401
    ActivationFailed, ClockTampered, InvalidKey, InvalidToken, LicenseError,
    SeatLimitReached, ServiceUnreachable, SignatureInvalid, TrialExhausted,
)
from .manager import (  # noqa: F401
    ACTIVE, CLOCK_TAMPERED, EXPIRED, GRACE_EXPIRED, GRANTING, INVALID, STALE,
    TRIAL, TRIAL_EXPIRED, UNLICENSED, LicenseManager, Status, get_manager,
    reset_manager,
)

__all__ = [
    "LicenseManager", "Status", "get_manager", "reset_manager",
    "plans", "keys", "tokens", "trial", "machine", "storage", "errors",
    "manager",
    "LicenseError", "InvalidKey", "InvalidToken", "SignatureInvalid",
    "ActivationFailed", "SeatLimitReached", "ServiceUnreachable",
    "TrialExhausted", "ClockTampered",
    "ACTIVE", "STALE", "TRIAL", "TRIAL_EXPIRED", "EXPIRED", "GRACE_EXPIRED",
    "INVALID", "CLOCK_TAMPERED", "UNLICENSED", "GRANTING",
]
