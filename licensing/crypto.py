"""Signing and verification, with the fast backend when it is available.

Two backends implement the same three functions. ``cryptography`` is used when
it imports; otherwise the vendored RFC 8032 code in :mod:`licensing._ed25519`
runs instead. Both are checked against the RFC's own test vectors, and against
each other, in ``tests/test_licensing_crypto.py``.

Why bother with a fallback: verification happens on customers' machines inside
a PyInstaller bundle, and a licence that cannot be verified is a customer who
cannot open the app they paid for. Signing happens on our licence server, where
``cryptography`` is a hard requirement.
"""

from __future__ import annotations

import base64
import os
import secrets
from typing import Tuple

from . import _ed25519

try:  # pragma: no cover - which branch runs depends on the environment
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey,
    )
    from cryptography.exceptions import InvalidSignature

    _HAVE_CRYPTOGRAPHY = True
except BaseException:  # noqa: BLE001 - see below
    # BaseException, not Exception, on purpose. A cryptography built against a
    # missing cffi does not raise ImportError: its Rust extension panics, and
    # pyo3 surfaces that as a PanicException, which inherits from
    # BaseException. Catching only Exception there takes the whole app down at
    # import time — the exact failure the fallback exists to survive.
    _HAVE_CRYPTOGRAPHY = False

#: Set to "1" to exercise the vendored code even where ``cryptography`` exists.
FORCE_FALLBACK_ENV = "LLSP_ED25519_PURE"


def backend() -> str:
    """Which implementation :func:`sign` and :func:`verify` will use."""
    if _HAVE_CRYPTOGRAPHY and os.environ.get(FORCE_FALLBACK_ENV) != "1":
        return "cryptography"
    return "pure-python"


def generate_keypair() -> Tuple[bytes, bytes]:
    """A fresh (private seed, public key) pair, 32 bytes each."""
    seed = secrets.token_bytes(32)
    return seed, public_key(seed)


def public_key(seed: bytes) -> bytes:
    if backend() == "cryptography":
        key = Ed25519PrivateKey.from_private_bytes(seed)
        return key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    return _ed25519.public_key(seed)


def sign(seed: bytes, message: bytes) -> bytes:
    """Detached 64-byte signature over ``message``."""
    if len(seed) != 32:
        raise ValueError("an Ed25519 signing seed is 32 bytes")
    if backend() == "cryptography":
        return Ed25519PrivateKey.from_private_bytes(seed).sign(message)
    return _ed25519.sign(seed, message)


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    """Whether the signature is good. Returns False rather than raising, so a
    caller can treat "damaged" and "forged" the same way."""
    if len(public) != 32 or len(signature) != 64:
        return False
    if backend() == "cryptography":
        try:
            Ed25519PublicKey.from_public_bytes(public).verify(signature, message)
            return True
        except (InvalidSignature, ValueError):
            return False
    return _ed25519.verify(public, message, signature)


# -- text encodings ------------------------------------------------------
# Keys travel in configuration files, environment variables and CI secrets, so
# they need a form that survives copy-paste: unpadded base64url.

def b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def b64decode(text: str) -> bytes:
    padded = text.strip() + "=" * (-len(text.strip()) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))
