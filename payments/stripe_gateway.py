"""Stripe, over its REST API, with no SDK.

Three things are needed from Stripe and all three are small:

* create a Checkout Session (one POST, form-encoded),
* create a Billing Portal session so customers manage their own cards,
* verify the signature on an incoming webhook (HMAC-SHA256, stdlib ``hmac``).

Skipping the SDK keeps the server's dependency list at "the standard library
and ``urllib``", which matters because this service is the thing that must be
running for anyone to activate. Fewer moving parts, fewer 3am upgrades.

**The webhook signature is not optional.** ``/v1/stripe/webhook`` is a public
URL that mints licences; without :func:`verify_signature` anybody who finds it
can grant themselves an Agency perpetual. The server refuses to start when
``LLSP_STRIPE_WEBHOOK_SECRET`` is unset for exactly this reason.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

API_BASE = "https://api.stripe.com/v1"
TIMEOUT_SECONDS = 20.0

#: How far apart the webhook's timestamp and our clock may be. Stripe's own
#: recommendation; it is what stops a captured webhook being replayed later.
SIGNATURE_TOLERANCE_SECONDS = 300


class StripeError(Exception):
    """Stripe said no, or could not be reached."""


class StripeGateway:
    def __init__(self, secret_key: str, webhook_secret: str = "",
                 api_base: str = API_BASE) -> None:
        self.secret_key = secret_key
        self.webhook_secret = webhook_secret
        self.api_base = api_base.rstrip("/")

    # -- transport -------------------------------------------------------
    def _post(self, path: str, form: List[Tuple[str, str]]) -> Dict[str, Any]:
        url = f"{self.api_base}{path}"
        body = urllib.parse.urlencode(form).encode("utf-8")
        request = urllib.request.Request(url, data=body, method="POST", headers={
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/x-www-form-urlencoded",
            # Stripe pins behaviour per version; naming it means an account-level
            # version bump cannot change the shape of what we parse.
            "Stripe-Version": "2024-06-20",
        })
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise StripeError(_explain(exc)) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise StripeError(f"could not reach Stripe: {exc}") from exc
        except ValueError as exc:
            raise StripeError(f"Stripe sent a reply we could not parse: {exc}") from exc

    # -- checkout --------------------------------------------------------
    def create_checkout_session(self, *, price_id: str, mode: str,
                                success_url: str, cancel_url: str,
                                email: str = "", metadata: Optional[Dict[str, str]] = None,
                                client_reference: str = "") -> Dict[str, Any]:
        """A hosted payment page.

        ``mode`` is ``subscription`` for recurring prices and ``payment`` for
        the perpetual licence — the same call shape either way, which is why
        both pricing models cost one code path rather than two.
        """
        form: List[Tuple[str, str]] = [
            ("mode", mode),
            ("line_items[0][price]", price_id),
            ("line_items[0][quantity]", "1"),
            ("success_url", success_url),
            ("cancel_url", cancel_url),
            ("allow_promotion_codes", "true"),
        ]
        if email:
            form.append(("customer_email", email))
        if client_reference:
            form.append(("client_reference_id", client_reference))
        if mode == "payment":
            # Without this a one-off payment creates no Customer, and a
            # perpetual owner has nothing to log into for receipts.
            form.append(("customer_creation", "always"))
            form.append(("invoice_creation[enabled]", "true"))
        for name, value in (metadata or {}).items():
            form.append((f"metadata[{name}]", value))
            if mode == "subscription":
                # Metadata on the session does not survive onto the
                # subscription, and renewals only ever mention the
                # subscription — so it has to be stamped on both.
                form.append((f"subscription_data[metadata][{name}]", value))
        return self._post("/checkout/sessions", form)

    def create_portal_session(self, customer_id: str, return_url: str) -> Dict[str, Any]:
        """Where a subscriber changes their card or cancels, on Stripe's pages."""
        return self._post("/billing_portal/sessions",
                          [("customer", customer_id), ("return_url", return_url)])

    # -- webhooks --------------------------------------------------------
    def verify_signature(self, payload: bytes, header: str,
                         now: Optional[float] = None) -> bool:
        """Whether ``payload`` really came from Stripe, unmodified and recently.

        The header looks like ``t=1699999999,v1=abc...,v1=def...``. Several v1
        signatures appear while a secret is being rotated, so any match counts.
        """
        if not self.webhook_secret or not header:
            return False
        timestamp = ""
        signatures: List[str] = []
        for part in header.split(","):
            name, _, value = part.strip().partition("=")
            if name == "t":
                timestamp = value
            elif name == "v1":
                signatures.append(value)
        if not timestamp or not signatures:
            return False
        try:
            sent_at = float(timestamp)
        except ValueError:
            return False
        now = time.time() if now is None else now
        if abs(now - sent_at) > SIGNATURE_TOLERANCE_SECONDS:
            return False
        signed = f"{timestamp}.".encode("utf-8") + payload
        expected = hmac.new(self.webhook_secret.encode("utf-8"), signed,
                            hashlib.sha256).hexdigest()
        # compare_digest, not ==, so a wrong signature cannot be found one byte
        # at a time by timing the reply.
        return any(hmac.compare_digest(expected, candidate) for candidate in signatures)

    def parse_event(self, payload: bytes, header: str,
                    now: Optional[float] = None) -> Dict[str, Any]:
        """Verify and decode a webhook, or raise :class:`StripeError`."""
        if not self.verify_signature(payload, header, now):
            raise StripeError("webhook signature did not verify")
        try:
            event = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise StripeError(f"webhook payload was not JSON: {exc}") from exc
        if not isinstance(event, dict) or "type" not in event:
            raise StripeError("webhook payload was not a Stripe event")
        return event


def sign_payload(secret: str, payload: bytes, timestamp: Optional[int] = None) -> str:
    """Build a ``Stripe-Signature`` header. Used by the tests, and by
    ``stripe trigger`` equivalents when testing a deployment by hand."""
    stamp = int(time.time() if timestamp is None else timestamp)
    signed = f"{stamp}.".encode("utf-8") + payload
    digest = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"t={stamp},v1={digest}"


def _explain(exc: urllib.error.HTTPError) -> str:
    try:
        parsed = json.loads(exc.read().decode("utf-8"))
        error = parsed.get("error") or {}
        return str(error.get("message") or parsed)
    except Exception:  # noqa: BLE001 - an unreadable Stripe error is still an error
        return f"Stripe returned HTTP {exc.code}"
