"""The licence service: a WSGI app with no framework.

    POST /v1/trial        start or resume a machine's 72-hour trial
    POST /v1/activate     bind a purchase key to a machine, get a licence
    POST /v1/refresh      swap an ageing licence for a fresh one
    POST /v1/deactivate   free a seat
    POST /v1/checkout     a Stripe payment link for a SKU
    POST /v1/stripe/webhook   Stripe tells us what was paid, cancelled, refunded
    GET  /v1/pricing      the catalogue, so a web page can render it
    GET  /healthz         liveness

Run it directly for development::

    python -m payments.server

or hand ``application`` to gunicorn/uWSGI in production. It is a plain WSGI
callable, so anything that speaks WSGI will serve it.

Two design notes worth keeping in mind while reading:

**The webhook is the only thing that creates a paid licence.** Not the checkout
call, not a success redirect — those are things a customer's browser can be
made to say. Money is only real when Stripe says it is, signed.

**Refusing to answer is not the same as refusing access.** Every endpoint here
can be down for a week without stopping a licensed customer working: the app
holds a signed token and an offline grace window precisely so this service is
not in the critical path.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from licensing import keys, plans
from licensing.tokens import LicenseToken

from . import issuer
from .config import Settings
from .db import Database
from .stripe_gateway import StripeError, StripeGateway

JSON_TYPE = "application/json; charset=utf-8"
MAX_BODY_BYTES = 64 * 1024  # a licence request is a few hundred bytes


class HttpError(Exception):
    """An answer that is not 200, with a message the app will show verbatim."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class LicenseService:
    """The request handlers, free of any HTTP so they can be tested directly."""

    def __init__(self, settings: Settings, database: Optional[Database] = None,
                 stripe: Optional[StripeGateway] = None,
                 now: Optional[Callable[[], float]] = None) -> None:
        self.settings = settings
        self.db = database or Database(settings.database_path)
        self.stripe = stripe or StripeGateway(settings.stripe_secret_key,
                                              settings.stripe_webhook_secret)
        self._now = now or time.time
        self._signing_key = settings.signing_key() if settings.signing_key_b64 else b""

    # -- helpers ----------------------------------------------------------
    def _sign(self, token: LicenseToken) -> str:
        if not self._signing_key:
            raise HttpError(500, "This licence server has no signing key configured.")
        return issuer.sign(token, self._signing_key)

    def _licence_or_404(self, key: str) -> Dict[str, Any]:
        licence = self.db.licence(key)
        if licence is None:
            raise HttpError(404, "No licence with that key. Check it, or contact "
                                 f"{self.settings.support_email}.")
        return licence

    @staticmethod
    def _require(body: Dict[str, Any], *names: str) -> Tuple[str, ...]:
        values = []
        for name in names:
            value = str(body.get(name) or "").strip()
            if not value:
                raise HttpError(400, f"{name} is required")
            values.append(value)
        return tuple(values)

    def _usable(self, licence: Dict[str, Any]) -> None:
        """Raise unless this licence may still hand out tokens."""
        status = licence.get("status")
        if status == "refunded":
            raise HttpError(403, "This licence was refunded and is no longer active.")
        if status == "cancelled":
            expires = licence.get("expires_at")
            # A cancelled subscription keeps working to the end of the period
            # that was already paid for. Cutting it off at cancellation would be
            # taking back time the customer bought.
            if not expires or self._now() >= float(expires):
                raise HttpError(403, "This subscription has ended. Renew to continue.")

    # -- endpoints --------------------------------------------------------
    def trial(self, body: Dict[str, Any]) -> Dict[str, Any]:
        (machine_id,) = self._require(body, "machine_id")
        record = self.db.start_trial(machine_id, str(body.get("email") or ""),
                                     str(body.get("label") or ""))
        started_at = float(record["started_at"])
        ends_at = started_at + plans.TRIAL_HOURS * 3600.0
        if self._now() >= ends_at:
            # 410 Gone: the app turns this into "already trialled" and stops
            # asking, rather than retrying a request that can never succeed.
            raise HttpError(410, "This computer has already used its 72-hour trial.")
        token = issuer.issue_trial(machine_id, started_at, now=self._now())
        return {"token": self._sign(token), "started_at": started_at,
                "ends_at": ends_at}

    def activate(self, body: Dict[str, Any]) -> Dict[str, Any]:
        key_text, machine_id = self._require(body, "key", "machine_id")
        key = keys.parse(key_text)  # InvalidKey -> 400, below
        licence = self._licence_or_404(key)
        self._usable(licence)
        # The seat limit is enforced inside db.activate(), not checked here
        # first: counting seats and then inserting is two steps, and two
        # activations arriving together would both see room on a full licence.
        record = self.db.activate(key, machine_id, str(body.get("label") or ""),
                                  max_machines=int(licence.get("max_machines") or 1))
        if record is None:
            machines = ", ".join(row["label"] or row["machine_id"][:8]
                                 for row in self.db.activations(key))
            used = self.db.seats_used(key)
            raise HttpError(409, f"All {used} seats on this licence are in use "
                                 f"({machines}). Deactivate one first.")
        token = issuer.issue(licence, machine_id, seat=int(record.get("seat") or 1),
                             now=self._now())
        return {"token": self._sign(token), "seat": record.get("seat"),
                "tier": licence["tier"], "model": licence["model"]}

    def refresh(self, body: Dict[str, Any]) -> Dict[str, Any]:
        key_text, machine_id = self._require(body, "key", "machine_id")
        key = keys.parse(key_text)
        licence = self._licence_or_404(key)
        self._usable(licence)
        record = self.db.activation(key, machine_id)
        if record is None or record.get("released_at"):
            # The seat was released elsewhere — most often the customer moved
            # to a new machine. Say so plainly; the app offers to re-activate.
            raise HttpError(403, "This computer is no longer activated on that "
                                 "licence. Activate it again to continue.")
        self.db.touch(key, machine_id)
        token = issuer.issue(licence, machine_id, seat=int(record.get("seat") or 1),
                             now=self._now())
        return {"token": self._sign(token)}

    def deactivate(self, body: Dict[str, Any]) -> Dict[str, Any]:
        key_text, machine_id = self._require(body, "key", "machine_id")
        key = keys.parse(key_text)
        self._licence_or_404(key)
        return {"released": self.db.release(key, machine_id)}

    def pricing(self) -> Dict[str, Any]:
        """The catalogue, straight from :mod:`licensing.plans`."""
        return {
            "trial_hours": plans.TRIAL_HOURS,
            "prices": [
                {"sku": price.sku, "tier": price.tier, "model": price.model,
                 "interval": price.interval, "cents": price.cents,
                 "display": price.display}
                for price in plans.catalog()
            ],
            "tiers": [
                {"key": key, "name": plans.TIERS[key].name,
                 "blurb": plans.TIERS[key].blurb,
                 "features": sorted(plans.TIERS[key].features),
                 "max_machines": plans.TIERS[key].limits.max_machines}
                for key in (plans.SOLO, plans.PRO, plans.AGENCY)
            ],
        }

    def checkout(self, body: Dict[str, Any]) -> Dict[str, Any]:
        (sku,) = self._require(body, "sku")
        price = plans.price_for(sku)
        if price is None:
            raise HttpError(400, f"There is no plan called {sku}.")
        price_id = self.settings.price_id(sku)
        if not price_id:
            raise HttpError(500, f"No Stripe price is configured for {sku}.")
        mode = "subscription" if price.model == plans.SUBSCRIPTION else "payment"
        metadata = {"sku": sku, "tier": price.tier, "model": price.model}
        # An upgrade carries the existing key so the webhook edits that licence
        # instead of issuing a second one to the same person.
        upgrade_key = str(body.get("key") or "").strip()
        if upgrade_key and keys.is_valid(upgrade_key):
            metadata["licence_key"] = keys.parse(upgrade_key)
        try:
            session = self.stripe.create_checkout_session(
                price_id=price_id, mode=mode,
                success_url=self.settings.success_url,
                cancel_url=self.settings.cancel_url,
                email=str(body.get("email") or ""),
                metadata=metadata,
                client_reference=metadata.get("licence_key", ""),
            )
        except StripeError as exc:
            raise HttpError(502, f"Could not start checkout: {exc}") from exc
        url = session.get("url")
        if not url:
            raise HttpError(502, "Stripe did not return a checkout link.")
        return {"url": url, "sku": sku, "session_id": session.get("id", "")}

    # -- webhook ----------------------------------------------------------
    def webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        try:
            event = self.stripe.parse_event(payload, signature, self._now())
        except StripeError as exc:
            # 400, not 500: Stripe retries 5xx, and retrying a bad signature
            # forever helps nobody.
            raise HttpError(400, str(exc)) from exc
        kind = str(event.get("type") or "")
        obj = ((event.get("data") or {}).get("object") or {})
        handler = {
            "checkout.session.completed": self._on_checkout_completed,
            "invoice.paid": self._on_invoice_paid,
            "invoice.payment_failed": self._on_payment_failed,
            "customer.subscription.deleted": self._on_subscription_deleted,
            "charge.refunded": self._on_refunded,
            "charge.dispute.created": self._on_refunded,
        }.get(kind)
        if handler is None:
            # Unknown events are fine and expected — Stripe sends plenty. 200
            # so it stops retrying.
            return {"ignored": kind}
        return handler(obj)

    def _on_checkout_completed(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """The moment a purchase becomes real: create or upgrade the licence."""
        metadata = session.get("metadata") or {}
        sku = str(metadata.get("sku") or "")
        if not sku or plans.price_for(sku) is None:
            return {"ignored": "no known sku on the session"}
        if str(session.get("payment_status") or "paid") not in ("paid", "no_payment_required"):
            return {"ignored": "session is not paid"}
        email = str((session.get("customer_details") or {}).get("email")
                    or session.get("customer_email") or "")
        name = str((session.get("customer_details") or {}).get("name") or "")
        customer = _id_of(session.get("customer"))
        subscription = _id_of(session.get("subscription"))
        terms = issuer.terms_for(sku, now=self._now())

        existing_key = str(metadata.get("licence_key") or
                           session.get("client_reference_id") or "")
        if existing_key and self.db.licence(existing_key):
            updated = {**terms, "status": "active", "email": email or None,
                       "stripe_customer": customer, "stripe_sub": subscription}
            self.db.update_licence(existing_key,
                                   **{k: v for k, v in updated.items() if v is not None})
            self.db.log(existing_key, "upgraded", sku)
            return {"licence": existing_key, "upgraded": True}

        key = keys.generate()
        self.db.create_licence(key=key, email=email, name=name,
                               stripe_customer=customer, stripe_sub=subscription,
                               **terms)
        # The key is what the customer needs; the success page and the receipt
        # email both read it from here.
        return {"licence": key, "created": True, "email": email}

    def _on_invoice_paid(self, invoice: Dict[str, Any]) -> Dict[str, Any]:
        """A renewal. Move the expiry to the end of the period just paid for."""
        subscription = _id_of(invoice.get("subscription"))
        if not subscription:
            return {"ignored": "invoice has no subscription"}
        licence = self.db.licence_by_subscription(subscription)
        if licence is None:
            return {"ignored": "no licence for that subscription"}
        period_end = _period_end(invoice)
        if not period_end:
            return {"ignored": "invoice has no period end"}
        self.db.update_licence(licence["key"],
                               **issuer.extend_subscription(licence, period_end))
        self.db.log(licence["key"], "renewed",
                    time.strftime("%Y-%m-%d", time.gmtime(period_end)))
        return {"licence": licence["key"], "expires_at": period_end}

    def _on_payment_failed(self, invoice: Dict[str, Any]) -> Dict[str, Any]:
        """Note it, change nothing.

        A failed payment is usually an expired card, and Stripe will retry for
        days. Revoking on the first failure would lock out a paying customer
        over a bank's fraud check; the licence's own expiry already covers the
        case where the retries never succeed.
        """
        subscription = _id_of(invoice.get("subscription"))
        licence = self.db.licence_by_subscription(subscription) if subscription else None
        if licence is None:
            return {"ignored": "no licence for that subscription"}
        self.db.log(licence["key"], "payment_failed",
                    str(invoice.get("attempt_count") or ""))
        return {"licence": licence["key"], "noted": True}

    def _on_subscription_deleted(self, subscription: Dict[str, Any]) -> Dict[str, Any]:
        licence = self.db.licence_by_subscription(_id_of(subscription.get("id")))
        if licence is None:
            return {"ignored": "no licence for that subscription"}
        # Cancelled, not dead: _usable() keeps it working until the period the
        # customer already paid for runs out.
        self.db.update_licence(licence["key"], status="cancelled")
        self.db.log(licence["key"], "cancelled", "")
        return {"licence": licence["key"], "cancelled": True}

    def _on_refunded(self, charge: Dict[str, Any]) -> Dict[str, Any]:
        """A refund or chargeback ends the licence now, and frees every seat."""
        customer = _id_of(charge.get("customer"))
        if not customer:
            return {"ignored": "charge has no customer"}
        rows = self.db.query("SELECT * FROM licences WHERE stripe_customer = ?", customer)
        affected = []
        for row in rows:
            key = row["key"]
            self.db.update_licence(key, status="refunded")
            for activation in self.db.activations(key):
                self.db.release(key, activation["machine_id"])
            self.db.log(key, "refunded", str(charge.get("id") or ""))
            affected.append(key)
        return {"licences": affected}


def _id_of(value: Any) -> str:
    """Stripe sends either an id or the expanded object; accept both."""
    if isinstance(value, dict):
        return str(value.get("id") or "")
    return str(value or "")


def _period_end(invoice: Dict[str, Any]) -> Optional[float]:
    lines = ((invoice.get("lines") or {}).get("data") or [])
    for line in lines:
        period = line.get("period") or {}
        if period.get("end"):
            return float(period["end"])
    if invoice.get("period_end"):
        return float(invoice["period_end"])
    return None


# -- WSGI ----------------------------------------------------------------

def make_app(service: LicenseService) -> Callable:
    """Wrap a :class:`LicenseService` in the smallest WSGI app that will do."""

    def application(environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/")
        try:
            status, payload = _route(service, method, path, environ)
        except HttpError as exc:
            status, payload = exc.status, {"error": exc.message}
        except Exception as exc:  # noqa: BLE001 - a handler bug must not 500 silently
            service.db.log("", "server_error", f"{type(exc).__name__}: {exc}")
            status, payload = 500, {"error": "The licence service hit an internal error."}
        body = json.dumps(payload).encode("utf-8")
        start_response(f"{status} {_REASONS.get(status, 'OK')}", [
            ("Content-Type", JSON_TYPE),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
        ])
        return [body]

    return application


def _route(service: LicenseService, method: str, path: str,
           environ) -> Tuple[int, Dict[str, Any]]:
    if method == "GET":
        if path in ("/healthz", "/health"):
            return 200, {"ok": True, "time": time.time()}
        if path == "/v1/pricing":
            return 200, service.pricing()
        raise HttpError(404, "no such endpoint")
    if method != "POST":
        raise HttpError(405, "method not allowed")

    raw = _read_body(environ)
    if path == "/v1/stripe/webhook":
        signature = environ.get("HTTP_STRIPE_SIGNATURE", "")
        return 200, service.webhook(raw, signature)

    body = _parse_json(raw)
    handlers = {
        "/v1/trial": service.trial,
        "/v1/activate": service.activate,
        "/v1/refresh": service.refresh,
        "/v1/deactivate": service.deactivate,
        "/v1/checkout": service.checkout,
    }
    handler = handlers.get(path)
    if handler is None:
        raise HttpError(404, "no such endpoint")
    from licensing.errors import InvalidKey

    try:
        return 200, handler(body)
    except InvalidKey as exc:
        raise HttpError(400, str(exc)) from exc


def _read_body(environ) -> bytes:
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0
    if length > MAX_BODY_BYTES:
        raise HttpError(413, "request body too large")
    stream = environ.get("wsgi.input")
    return stream.read(length) if stream and length else b""


def _parse_json(raw: bytes) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise HttpError(400, f"body was not JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise HttpError(400, "body must be a JSON object")
    return parsed


_REASONS = {200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found",
            405: "Method Not Allowed", 409: "Conflict", 410: "Gone",
            413: "Payload Too Large", 500: "Internal Server Error",
            502: "Bad Gateway"}


def application(environ, start_response):  # pragma: no cover - production entry
    """WSGI entry point for gunicorn: ``gunicorn payments.server:application``."""
    global _APP
    if _APP is None:
        settings = Settings.from_env()
        problems = settings.problems()
        if problems:
            raise RuntimeError("licence server is not configured: "
                               + "; ".join(problems))
        _APP = make_app(LicenseService(settings))
    return _APP(environ, start_response)


_APP = None


def main(argv: Optional[List[str]] = None) -> int:  # pragma: no cover - dev server
    """``python -m payments.server`` — the development server."""
    from wsgiref.simple_server import make_server

    settings = Settings.from_env()
    problems = settings.problems()
    if problems:
        print("The licence server is not configured:")
        for line in problems:
            print(f"  - {line}")
        print("\nSee docs/LICENSING.md for the full list.")
        return 1
    app = make_app(LicenseService(settings))
    print(f"licence service on http://{settings.host}:{settings.port}")
    with make_server(settings.host, settings.port, app) as server:
        server.serve_forever()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
