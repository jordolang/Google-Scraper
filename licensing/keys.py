"""The licence key a customer is given, types in, and reads over the phone.

    LLSP-4KJ7N-Q2WX8-B9MTR-6HDVC

Five groups of five characters in Crockford's base32 alphabet, which drops the
letters that get misread — I, L, O and U are simply not in it — and treats the
digits 0/1 as interchangeable with O/I on input. The last group is a checksum,
so a mistyped key is rejected instantly instead of producing a failed
activation and a support email.

The key is an *identifier*, not a secret with meaning: the entitlements live in
the signed token the server issues at activation (see :mod:`licensing.tokens`).
That split is what lets the same key be re-issued to a customer who reinstalls,
and lets us revoke by refusing to sign a new token.
"""

from __future__ import annotations

import re
import secrets
from typing import Optional

from .errors import InvalidKey

PREFIX = "LLSP"
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32: no I, L, O, U
GROUP = 5
BODY_GROUPS = 3       # random groups, before the checksum group
CHECKSUM_GROUP = 1

#: Characters people substitute for the ones the alphabet excludes.
_CONFUSIONS = {"I": "1", "L": "1", "O": "0", "U": "V"}


def _normalise(text: str) -> str:
    """Upper-case, strip anything that is not a body character, fix look-alikes."""
    cleaned = re.sub(r"[^0-9A-Za-z]", "", text or "").upper()
    if cleaned.startswith(PREFIX):
        cleaned = cleaned[len(PREFIX):]
    return "".join(_CONFUSIONS.get(char, char) for char in cleaned)


def _checksum(body: str) -> str:
    """Five characters derived from the body, so typos do not reach the server.

    Not a security control — anyone can compute it. It exists to catch the
    transposed character in a key read aloud.
    """
    import hashlib

    digest = hashlib.sha256((PREFIX + body).encode("ascii")).digest()
    value = int.from_bytes(digest[:8], "big")
    out = []
    for _ in range(GROUP):
        out.append(ALPHABET[value % len(ALPHABET)])
        value //= len(ALPHABET)
    return "".join(out)


def generate() -> str:
    """A fresh licence key. Called by the licence server, once per purchase."""
    body = "".join(secrets.choice(ALPHABET) for _ in range(GROUP * BODY_GROUPS))
    return format_key(body + _checksum(body))


def format_key(raw: str) -> str:
    """Group a 20-character body into the printed form."""
    raw = _normalise(raw)
    groups = [raw[i:i + GROUP] for i in range(0, len(raw), GROUP)]
    return "-".join([PREFIX] + groups)


def is_valid(text: str) -> bool:
    """Whether ``text`` is a well-formed key. Never raises."""
    try:
        parse(text)
        return True
    except InvalidKey:
        return False


def parse(text: str) -> str:
    """Return the canonical printed key, or raise :class:`InvalidKey`.

    Accepts what a human is likely to produce: lower case, missing prefix,
    spaces instead of dashes, an O typed for a zero.
    """
    body = _normalise(text)
    expected = GROUP * (BODY_GROUPS + CHECKSUM_GROUP)
    if len(body) != expected:
        raise InvalidKey(
            f"A licence key has {expected} characters after the prefix; "
            f"this one has {len(body)}."
        )
    if any(char not in ALPHABET for char in body):
        raise InvalidKey("That key contains characters no licence key uses.")
    payload, checksum = body[:-GROUP], body[-GROUP:]
    if checksum != _checksum(payload):
        raise InvalidKey("That key failed its checksum — one character is off.")
    return format_key(body)


def masked(text: str) -> str:
    """The key with its middle hidden, for logs and screenshots."""
    try:
        key = parse(text)
    except InvalidKey:
        return "—"
    groups = key.split("-")
    return "-".join(groups[:2] + ["•" * GROUP] * (len(groups) - 3) + groups[-1:])


def looks_like_key(text: str) -> Optional[str]:
    """The canonical key if ``text`` contains one, else None. For paste handling."""
    try:
        return parse(text)
    except InvalidKey:
        return None
