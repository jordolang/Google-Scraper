"""Per-recipient unsubscribe links, and the list of people who used them.

Every email carries its own link to the unsubscribe function in ``vercel/``
(deployed as its own small Vercel project)::

    https://<your-unsubscribe-site>.vercel.app/api/unsubscribe?h=<id>&s=<signature>

``h`` is a SHA-256 fingerprint of the recipient's address, so the address
itself never appears in a URL. ``s`` signs it with a secret only you and the
function know, so nobody can forge links to unsubscribe other people. The
email's footer link and its List-Unsubscribe header both point there, so one
click (from the footer, or the inbox's own Unsubscribe button) stores
``optouts/<id>.json`` in your Vercel Blob store. Before a campaign goes out,
:meth:`OptOutList.opted_out` reads that folder and says who to skip::

    optouts = OptOutList(url="https://lead-optout.vercel.app", secret="…")
    optouts.link_for("owner@shop.com")
    # 'https://lead-optout.vercel.app/api/unsubscribe?h=5c1f…&s=9ad2…'
    optouts.opted_out(["owner@shop.com", "info@bakery.com"])
    # {'owner@shop.com'}

Making a link needs no network at all. Reading the list uses the same Blob
token as image hosting (``BLOB_READ_WRITE_TOKEN``). Setup: docs/unsubscribe.md.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from typing import Dict, Iterable, Set

from image_host import BlobStore, ImageHostError

URL_ENV = "UNSUBSCRIBE_SITE_URL"
SECRET_ENV = "UNSUBSCRIBE_SECRET"
PREFIX = "optouts/"
ROUTE = "/api/unsubscribe"
#: Hex characters of the signature kept in the link (128 bits).
SIGNATURE_LENGTH = 32


class OptOutError(RuntimeError):
    """The unsubscribe list could not be reached or read."""


class OptOutsNotSetUp(OptOutError):
    """The unsubscribe site, secret or Blob token has not been filled in."""


class OptOutList:
    def __init__(self, url: str = "", secret: str = "", token: str = "",
                 timeout: float = 15) -> None:
        self.url = (url or os.environ.get(URL_ENV, "")).strip().rstrip("/")
        self.secret = (secret or os.environ.get(SECRET_ENV, "")).strip()
        self.store = BlobStore(token, timeout=timeout)
        self._links: Dict[str, str] = {}

    def configured(self) -> bool:
        return bool(self.url.startswith("https://") and self.secret
                    and self.store.configured())

    def _require(self) -> None:
        if not self.configured():
            raise OptOutsNotSetUp(
                "Unsubscribe links are not set up. Add your unsubscribe site URL "
                "and secret under Settings → Deliverability, and your Vercel Blob "
                "token under Settings → Image Hosting (see docs/unsubscribe.md).")

    # -- public --------------------------------------------------------------
    def link_for(self, email: str) -> str:
        """The recipient's own unsubscribe URL (the same one every time)."""
        address = normalise(email)
        if not address:
            raise OptOutError("No email address to make an unsubscribe link for.")
        self._require()
        if address not in self._links:
            digest = fingerprint(address)
            self._links[address] = (f"{self.url}{ROUTE}?h={digest}"
                                    f"&s={sign(self.secret, digest)}")
        return self._links[address]

    def opted_out(self, emails: Iterable[str]) -> Set[str]:
        """The addresses in ``emails`` that have unsubscribed (lower-cased)."""
        wanted = {fingerprint(a): a for a in {normalise(e) for e in emails} - {""}}
        if not wanted:
            return set()
        self._require()
        try:
            stored = {path[len(PREFIX):].split(".", 1)[0]
                      for path in self.store.list_pathnames(PREFIX)}
        except ImageHostError as exc:
            raise OptOutError(str(exc)) from exc
        return {wanted[digest] for digest in stored if digest in wanted}


def normalise(email: str) -> str:
    return (email or "").strip().lower()


def fingerprint(email: str) -> str:
    """SHA-256 of the normalised address: stable, and not the address itself."""
    return hashlib.sha256(normalise(email).encode("utf-8")).hexdigest()


def sign(secret: str, digest: str) -> str:
    """What the function checks before it records an unsubscribe."""
    mac = hmac.new(secret.encode("utf-8"), digest.encode("ascii"), hashlib.sha256)
    return mac.hexdigest()[:SIGNATURE_LENGTH]


def new_secret() -> str:
    """A fresh signing secret for UNSUBSCRIBE_SECRET."""
    return secrets.token_urlsafe(32)
