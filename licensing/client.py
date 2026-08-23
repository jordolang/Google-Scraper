"""Talking to the licence service.

Five calls, all of them optional to the app's ability to run:

============  =====================================================
``trial``     ask for (or resume) this machine's 72-hour trial
``activate``  bind a purchase key to this machine, get a token back
``refresh``   swap an ageing token for a fresh one
``deactivate``free this machine's seat so another can take it
``checkout``  ask for a Stripe payment link for a chosen plan
============  =====================================================

Every one of them is allowed to fail. The desktop app treats an unreachable
service as "try again later", never as "you are not licensed" — the signed
token on disk is what grants access, and it keeps working through the offline
grace window without any of this.

Written against :mod:`urllib` rather than ``requests`` on purpose: this code
runs inside the PyInstaller bundle, and the fewer third-party imports the
licence path has, the fewer ways a build can produce an app that will not
open. It honours ``HTTPS_PROXY`` through urllib's own proxy handling.
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from .errors import ActivationFailed, SeatLimitReached, ServiceUnreachable, TrialExhausted

#: Where the licence service lives. Overridable so a self-hosted or staging
#: service can be pointed at without a rebuild.
SERVICE_URL_ENV = "LLSP_LICENSE_URL"
DEFAULT_SERVICE_URL = "https://licence.jlang.dev"

USER_AGENT = "LocalLeadScraperPro-licensing/1"
TIMEOUT_SECONDS = 12.0


def service_url() -> str:
    return (os.environ.get(SERVICE_URL_ENV) or DEFAULT_SERVICE_URL).rstrip("/")


class LicenseClient:
    """A thin, synchronous JSON client. Callers run it off the UI thread."""

    def __init__(self, base_url: str = "", timeout: float = TIMEOUT_SECONDS) -> None:
        self.base_url = (base_url or service_url()).rstrip("/")
        self.timeout = timeout

    # -- transport -------------------------------------------------------
    def _post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        )
        context = ssl.create_default_context() if url.startswith("https") else None
        try:
            with urllib.request.urlopen(request, timeout=self.timeout,
                                        context=context) as response:
                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            # A 4xx carries the service's own explanation; surface that rather
            # than "HTTP 409", which tells a customer nothing.
            detail = _read_error(exc)
            raise _from_status(exc.code, detail) from exc
        except (urllib.error.URLError, OSError, ssl.SSLError) as exc:
            raise ServiceUnreachable(
                f"Could not reach the licence service at {self.base_url} ({exc})."
            ) from exc
        try:
            parsed = json.loads(payload)
        except ValueError as exc:
            raise ActivationFailed(
                "The licence service sent a reply this version cannot read."
            ) from exc
        if not isinstance(parsed, dict):
            raise ActivationFailed("The licence service sent an unexpected reply.")
        return parsed

    # -- calls -----------------------------------------------------------
    def trial(self, machine_id: str, *, email: str = "",
              label: str = "") -> Dict[str, Any]:
        """Start or resume this machine's trial. Returns ``{token, started_at}``."""
        return self._post("/v1/trial", {"machine_id": machine_id, "email": email,
                                        "label": label})

    def activate(self, key: str, machine_id: str, *, label: str = "") -> Dict[str, Any]:
        """Bind a key to this machine. Returns ``{token}``."""
        return self._post("/v1/activate", {"key": key, "machine_id": machine_id,
                                           "label": label})

    def refresh(self, key: str, machine_id: str) -> Dict[str, Any]:
        """A newer token for an existing activation. Returns ``{token}``."""
        return self._post("/v1/refresh", {"key": key, "machine_id": machine_id})

    def deactivate(self, key: str, machine_id: str) -> Dict[str, Any]:
        """Release this machine's seat. Returns ``{released: true}``."""
        return self._post("/v1/deactivate", {"key": key, "machine_id": machine_id})

    def checkout(self, sku: str, *, email: str = "",
                 key: str = "") -> Dict[str, Any]:
        """A Stripe Checkout link for ``sku``. Returns ``{url}``.

        ``key`` is set when an existing customer is upgrading, so the purchase
        lands on the licence they already have instead of creating a second.
        """
        return self._post("/v1/checkout", {"sku": sku, "email": email, "key": key})


def _read_error(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8")
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            return str(parsed.get("error") or parsed.get("detail") or body)
        return body
    except Exception:  # noqa: BLE001 - an unreadable error body is still an error
        return f"HTTP {exc.code}"


def _from_status(status: int, detail: str):
    """Map the service's status codes onto the exceptions callers handle."""
    if status == 409:
        return SeatLimitReached(detail or SeatLimitReached.message)
    if status == 410:
        return TrialExhausted(detail or TrialExhausted.message)
    if status in (500, 502, 503, 504):
        return ServiceUnreachable(
            f"The licence service is having trouble ({status}). Try again shortly."
        )
    return ActivationFailed(detail or f"The licence service refused the request ({status}).")
