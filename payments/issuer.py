"""Turning a database row into a signed licence the app will accept.

This is the only place the private key is used. Everything about what a
customer is entitled to has already been decided by the time we get here — the
issuer's whole job is to state it, bind it to one machine, and set the two
clocks described in :mod:`licensing.tokens`.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from licensing import plans, tokens
from licensing.tokens import LicenseToken

#: How long a perpetual licence's token stays valid before it wants refreshing.
#: Longer than a subscription's, because there is no billing event to catch —
#: only refunds and chargebacks, which are rare and not urgent.
PERPETUAL_REFRESH_DAYS = 30

DAY = 86400.0


def issue(licence: Dict[str, Any], machine_id: str, *, seat: int = 1,
          now: Optional[float] = None) -> LicenseToken:
    """Build the token for ``licence`` on ``machine_id``. Does not sign it."""
    now = time.time() if now is None else now
    model = licence.get("model") or plans.SUBSCRIPTION
    refresh_days = (PERPETUAL_REFRESH_DAYS if model == plans.PERPETUAL
                    else tokens.REFRESH_INTERVAL_DAYS)
    expires_at = licence.get("expires_at")
    if model == plans.PERPETUAL:
        # A perpetual licence never expires. Its update window does, and that
        # is carried separately so the app can say "updates ended in March"
        # without ever refusing to open.
        expires_at = None
    return LicenseToken(
        key=str(licence.get("key") or ""),
        tier=str(licence.get("tier") or plans.SOLO),
        model=model,
        machine_id=machine_id,
        issued_at=now,
        refresh_after=now + refresh_days * DAY,
        expires_at=float(expires_at) if expires_at else None,
        updates_until=(float(licence["updates_until"])
                       if licence.get("updates_until") else None),
        seat=int(seat or 1),
        email=str(licence.get("email") or ""),
        name=str(licence.get("name") or ""),
        extra_features=list(licence.get("extra_features") or []),
    )


def issue_trial(machine_id: str, started_at: float, *,
                now: Optional[float] = None) -> LicenseToken:
    """A trial token: the trial tier, expiring 72 hours after it began.

    Note the expiry is measured from ``started_at``, not from now — a machine
    that reinstalls on day three gets a token that has already expired, which
    is the point.
    """
    now = time.time() if now is None else now
    ends_at = started_at + plans.TRIAL_HOURS * 3600.0
    return LicenseToken(
        key="",
        tier=plans.TRIAL,
        model=plans.SUBSCRIPTION,
        machine_id=machine_id,
        issued_at=now,
        # Never ask for a refresh after the trial is over; there is nothing to
        # refresh into.
        refresh_after=min(now + tokens.REFRESH_INTERVAL_DAYS * DAY, ends_at),
        expires_at=ends_at,
        seat=1,
    )


def sign(token: LicenseToken, signing_key: bytes) -> str:
    return tokens.sign_token(token, signing_key)


def issue_signed(licence: Dict[str, Any], machine_id: str, signing_key: bytes,
                 *, seat: int = 1, now: Optional[float] = None) -> str:
    return sign(issue(licence, machine_id, seat=seat, now=now), signing_key)


# -- what a purchase entitles someone to ---------------------------------

def terms_for(sku: str, *, now: Optional[float] = None) -> Dict[str, Any]:
    """The licence fields a given SKU should create.

    One function so that "what does buying this get you" is answered the same
    way by the webhook, by a manual grant from the CLI, and by the tests.
    """
    now = time.time() if now is None else now
    price = plans.price_for(sku)
    if price is None:
        raise ValueError(f"unknown SKU: {sku}")
    tier = plans.TIERS[price.tier]
    terms: Dict[str, Any] = {
        "tier": price.tier,
        "model": price.model,
        "sku": sku,
        "max_machines": tier.limits.max_machines,
        "expires_at": None,
        "updates_until": None,
    }
    if price.model == plans.SUBSCRIPTION:
        # Stripe is the source of truth for renewals; this is the first period,
        # replaced by ``current_period_end`` the moment an invoice is paid.
        days = 366 if price.interval == plans.YEARLY else 31
        terms["expires_at"] = now + days * DAY
    else:
        terms["updates_until"] = now + tier.perpetual_update_months * 30.5 * DAY
    return terms


def extend_subscription(licence: Dict[str, Any], period_end: float) -> Dict[str, Any]:
    """Fields to write when Stripe says a subscription renewed."""
    return {"expires_at": float(period_end), "status": "active"}


def extend_updates(licence: Dict[str, Any], months: int = 12,
                   now: Optional[float] = None) -> Dict[str, Any]:
    """Fields to write when a perpetual owner buys another year of updates."""
    now = time.time() if now is None else now
    current = float(licence.get("updates_until") or now)
    base = max(current, now)  # a renewal bought early adds on, never resets
    return {"updates_until": base + months * 30.5 * DAY}
