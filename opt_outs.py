"""Per-recipient unsubscribe links, and the list of people who used them.

Each address the app emails gets a row in the Supabase table
``outreach_recipients`` with a random token. The email's footer link and its
List-Unsubscribe header both point at the ``unsubscribe`` Edge Function with
that token, so one click (from the footer, or the inbox's own Unsubscribe
button) marks the address. Before a campaign goes out, :meth:`OptOutList.opted_out`
says who to skip::

    optouts = OptOutList(url="https://abcd.supabase.co")
    optouts.link_for("owner@shop.com")
    # 'https://abcd.supabase.co/functions/v1/unsubscribe?t=Jx3…'
    optouts.opted_out(["owner@shop.com", "info@bakery.com"])
    # {'owner@shop.com'}

It uses the same Supabase project and secret key as image hosting
(``SUPABASE_URL`` / ``SUPABASE_SERVICE_KEY``). The table and function live in
``supabase/`` in this repository.
"""

from __future__ import annotations

import os
import secrets
from typing import Dict, Iterable, Set

from image_host import KEY_ENV, URL_ENV

TABLE = "outreach_recipients"
FUNCTION = "unsubscribe"
# PostgREST's own "no such table" code, and the HTTP status it comes with.
_MISSING_TABLE = "PGRST205"


class OptOutError(RuntimeError):
    """The unsubscribe list could not be reached or read."""


class OptOutsNotSetUp(OptOutError):
    """The Supabase project has no ``outreach_recipients`` table yet."""


class OptOutList:
    def __init__(self, url: str = "", key: str = "", timeout: float = 15) -> None:
        self.url = (url or os.environ.get(URL_ENV, "")).strip().rstrip("/")
        self.key = (key or os.environ.get(KEY_ENV, "")).strip()
        self.timeout = timeout
        self._links: Dict[str, str] = {}
        self._session = None

    def configured(self) -> bool:
        return bool(self.url.startswith("https://") and self.key)

    def unsubscribe_url(self, token: str) -> str:
        return f"{self.url}/functions/v1/{FUNCTION}?t={token}"

    # -- public --------------------------------------------------------------
    def link_for(self, email: str) -> str:
        """The recipient's own unsubscribe URL, creating their row if needed."""
        address = normalise(email)
        if not address:
            raise OptOutError("No email address to make an unsubscribe link for.")
        if address in self._links:
            return self._links[address]
        token = self._token(address)
        if not token:
            # Two sends racing for the same new address: ignore-duplicates
            # keeps whichever row landed first, so read it back.
            self._post([{"email": address, "token": new_token()}])
            token = self._token(address)
        if not token:
            raise OptOutError(f"Could not save an unsubscribe link for {address}.")
        self._links[address] = self.unsubscribe_url(token)
        return self._links[address]

    def opted_out(self, emails: Iterable[str]) -> Set[str]:
        """The addresses in ``emails`` that have unsubscribed (lower-cased)."""
        wanted = sorted({normalise(e) for e in emails} - {""})
        found: Set[str] = set()
        for start in range(0, len(wanted), 50):
            chunk = wanted[start:start + 50]
            quoted = ",".join('"' + e.replace('"', '') + '"' for e in chunk)
            rows = self._get({
                "select": "email",
                "unsubscribed_at": "not.is.null",
                "email": f"in.({quoted})",
            })
            found.update(row["email"] for row in rows)
        return found

    # -- REST ----------------------------------------------------------------
    def _token(self, address: str) -> str:
        rows = self._get({"select": "token", "email": f"eq.{address}"})
        return rows[0]["token"] if rows else ""

    def _headers(self) -> Dict[str, str]:
        headers = {"apikey": self.key, "Content-Type": "application/json"}
        # Same rule as image hosting: legacy service_role keys are JWTs and go
        # in Authorization too; sb_secret_ keys must only go in apikey.
        if not self.key.startswith("sb_"):
            headers["Authorization"] = f"Bearer {self.key}"
        return headers

    def _request(self, method: str, extra_headers=None, **kwargs):
        if not self.configured():
            raise OptOutsNotSetUp(
                "Supabase is not set up. Add your project URL and secret key under "
                "Settings → Image Hosting.")
        import requests

        if self._session is None:
            self._session = requests.Session()
        try:
            response = self._session.request(
                method, f"{self.url}/rest/v1/{TABLE}",
                headers={**self._headers(), **(extra_headers or {})},
                timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise OptOutError(f"Could not reach Supabase: {exc}") from exc
        if response.status_code >= 300:
            body = response.text or ""
            if _MISSING_TABLE in body or response.status_code == 404:
                raise OptOutsNotSetUp(
                    f"Your Supabase project has no {TABLE} table yet. See "
                    "docs/unsubscribe.md to set it up.")
            raise OptOutError(f"Supabase said {response.status_code}: {body[:200]}")
        return response

    def _get(self, params: Dict[str, str]) -> list:
        return self._request("GET", params=params).json()

    def _post(self, rows: list) -> None:
        self._request(
            "POST", json=rows, params={"on_conflict": "email"},
            extra_headers={"Prefer": "resolution=ignore-duplicates,return=minimal"})


def normalise(email: str) -> str:
    return (email or "").strip().lower()


def new_token() -> str:
    """22 URL-safe characters: unguessable, and short enough for a link."""
    return secrets.token_urlsafe(16)
