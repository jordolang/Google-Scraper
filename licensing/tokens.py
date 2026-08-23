"""The signed licence file: what the app actually trusts.

A token is one line of text::

    LLSPv1.<base64url payload>.<base64url signature>

The payload is compact JSON — tier, model, expiry, seat, the machine it was
issued to — and the signature is Ed25519 over the exact payload bytes. The app
ships the public key; only the licence server has the private half.

The consequence worth stating plainly: **verification is offline**. A customer
on a plane, behind a corporate proxy, or on a job site with no signal opens the
app and it works. The network is needed to *get* a token and to refresh it, not
to use one.

Two clocks are baked into every token and they do different jobs:

``expires_at``
    When the entitlement itself ends. A subscription's expiry tracks the
    billing period; a perpetual licence has none.
``refresh_after``
    When the app should quietly ask the server for a newer token. Short — days,
    not months. This is the revocation channel: a refund, chargeback or seat
    release means the server declines to re-sign, and the token ages out on its
    own. :data:`OFFLINE_GRACE_DAYS` is how long past that an offline machine
    keeps working anyway, because a customer with no internet is not a thief.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from . import crypto, plans
from .errors import InvalidToken, SignatureInvalid

MAGIC = "LLSPv1"

#: How long a machine keeps working after ``refresh_after`` passes with no
#: successful refresh. Subscriptions get two weeks; a perpetual licence gets
#: half a year, because someone who paid once should never be locked out of
#: software they own by a server we happen to be running.
OFFLINE_GRACE_DAYS = 14
PERPETUAL_OFFLINE_GRACE_DAYS = 180

#: How far ahead the server sets ``refresh_after`` when it signs.
REFRESH_INTERVAL_DAYS = 7

DAY = 86400.0


@dataclass
class LicenseToken:
    """The verified contents of a licence file."""

    key: str                       # the printed purchase key
    tier: str                      # plans.SOLO / PRO / AGENCY / TRIAL
    model: str                     # plans.SUBSCRIPTION / PERPETUAL
    machine_id: str                # fingerprint this seat is bound to
    issued_at: float               # unix seconds
    refresh_after: float           # unix seconds
    expires_at: Optional[float] = None      # None = never (perpetual)
    updates_until: Optional[float] = None   # perpetual: end of the update window
    seat: int = 1                  # which seat of max_machines this is
    email: str = ""                # who bought it, for the "Licensed to" line
    name: str = ""
    #: Features granted beyond the tier's own set — how a one-off deal or a
    #: beta invite is expressed without inventing a new tier.
    extra_features: List[str] = field(default_factory=list)
    #: Free-form, forward-compatible. Unknown keys survive a round trip.
    meta: Dict[str, Any] = field(default_factory=dict)

    # -- derived ---------------------------------------------------------
    @property
    def perpetual(self) -> bool:
        return self.model == plans.PERPETUAL

    @property
    def grace_days(self) -> int:
        return PERPETUAL_OFFLINE_GRACE_DAYS if self.perpetual else OFFLINE_GRACE_DAYS

    @property
    def grace_ends_at(self) -> float:
        return self.refresh_after + self.grace_days * DAY

    def expired(self, now: Optional[float] = None) -> bool:
        if self.expires_at is None:
            return False
        return (now if now is not None else time.time()) >= self.expires_at

    def stale(self, now: Optional[float] = None) -> bool:
        """Past its refresh date — still valid, but the app should re-check."""
        return (now if now is not None else time.time()) >= self.refresh_after

    def grace_expired(self, now: Optional[float] = None) -> bool:
        """Offline for so long that the token can no longer be trusted."""
        return (now if now is not None else time.time()) >= self.grace_ends_at

    def features(self) -> frozenset:
        return frozenset(plans.tier(self.tier).features) | frozenset(self.extra_features)

    def limits(self) -> plans.Limits:
        return plans.tier(self.tier).limits

    # -- serialisation ---------------------------------------------------
    def payload(self) -> bytes:
        """The exact bytes that get signed.

        Sorted keys and no whitespace, so the same token serialises identically
        on every machine and Python version — a signature over "the same JSON"
        formatted differently is a signature over different bytes.
        """
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode("utf-8")

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "LicenseToken":
        known = {f: raw.get(f) for f in cls.__dataclass_fields__ if f in raw}
        missing = [f for f in ("key", "tier", "model", "machine_id",
                               "issued_at", "refresh_after") if f not in known]
        if missing:
            raise InvalidToken(f"the licence is missing {', '.join(missing)}")
        return cls(**known)


def sign_token(token: LicenseToken, private_seed: bytes) -> str:
    """Serialise and sign. Server side only."""
    payload = token.payload()
    signature = crypto.sign(private_seed, payload)
    return f"{MAGIC}.{crypto.b64encode(payload)}.{crypto.b64encode(signature)}"


def verify_token(blob: str, public_key: bytes) -> LicenseToken:
    """Parse and check a token, or raise.

    Raises :class:`SignatureInvalid` when the signature does not match — the
    licence is forged or was issued by a different install of the server — and
    :class:`InvalidToken` when the text is not a licence at all.
    """
    parts = (blob or "").strip().split(".")
    if len(parts) != 3 or parts[0] != MAGIC:
        raise InvalidToken("that is not a licence file")
    _, payload_b64, signature_b64 = parts
    try:
        payload = crypto.b64decode(payload_b64)
        signature = crypto.b64decode(signature_b64)
    except Exception as exc:  # noqa: BLE001 - any decode failure is the same failure
        raise InvalidToken(f"the licence file is damaged ({exc})") from exc
    # Signature first: never parse attacker-controlled JSON into anything that
    # matters before checking who wrote it.
    if not crypto.verify(public_key, payload, signature):
        raise SignatureInvalid()
    try:
        raw = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise InvalidToken(f"the licence payload is not readable ({exc})") from exc
    if not isinstance(raw, dict):
        raise InvalidToken("the licence payload is not an object")
    return LicenseToken.from_dict(raw)
