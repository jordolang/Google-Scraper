"""The Ed25519 public key this build trusts.

Empty in the repository on purpose. The private half never lives here — it is
generated once with ``python -m payments.cli keygen``, kept in the licence
server's environment and in a CI secret, and only the public half is written
back into this file by the release job::

    python -m payments.cli keygen --write-public licensing/public_key.py

A build that ships with this still empty verifies nothing, so every install
falls back to reader mode. ``LocalLeadScraperPro.exe --selftest`` fails a
frozen build in that state rather than letting it reach a customer.

:data:`PUBLIC_KEY_ENV` overrides it at run time, which is what a self-hosted
licence service or a staging build uses.
"""

from __future__ import annotations

import os

from . import _ed25519, crypto

PUBLIC_KEY_ENV = "LLSP_LICENSE_PUBKEY"

#: base64url, no padding. Written by the release job; see the module docstring.
EMBEDDED_PUBLIC_KEY = ""


def public_key() -> bytes:
    """The 32 raw bytes to verify licences with, or b"" when unconfigured."""
    text = (os.environ.get(PUBLIC_KEY_ENV) or EMBEDDED_PUBLIC_KEY or "").strip()
    if not text:
        return b""
    try:
        raw = crypto.b64decode(text)
    except Exception:  # noqa: BLE001 - a malformed key is an unconfigured key
        return b""
    if len(raw) != 32 or not usable(raw):
        return b""
    return raw


def usable(raw: bytes) -> bool:
    """Whether ``raw`` is a real verification key rather than a degenerate one.

    Ed25519 verification, as RFC 8032 specifies it, accepts signatures against
    small-order public keys — an all-zero key "verifies" an all-zero signature.
    That is not a hole in the licence system (an attacker cannot choose the key
    the app was built with) but it is a fine way to ship a build that accepts
    anything, so a key that is not a full-order point is treated as no key at
    all and the app falls back to reader mode.
    """
    point = _ed25519._point_decompress(raw)
    if point is None:
        return False
    # [8]A is the identity exactly when A lies in the order-8 torsion subgroup.
    multiplied = _ed25519._point_mul(8, point)
    return not _ed25519._point_equal(multiplied, _ed25519.NEUTRAL)


def configured() -> bool:
    return bool(public_key())
