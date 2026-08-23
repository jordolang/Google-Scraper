"""A dependency-free Ed25519, used when :mod:`cryptography` is not installed.

This is the reference implementation from RFC 8032 appendix A, transcribed and
commented. It exists so that licence verification — the one thing that has to
work on every customer's machine, packaged or not — never depends on a wheel
that PyInstaller might fail to collect. :mod:`licensing.crypto` prefers the
real ``cryptography`` backend and falls back to this.

It is not constant-time. That matters for signing (which happens on our server,
where ``cryptography`` is a hard dependency and this code never runs) and not
for verification, which handles only the public key and a signature the
attacker already has.

``tests/test_licensing_crypto.py`` checks it against the RFC 8032 test vectors
and cross-checks it against ``cryptography`` when that is importable.
"""

from __future__ import annotations

import hashlib
from typing import Optional, Tuple

# Field prime and group order, per RFC 8032 §5.1.
P = 2 ** 255 - 19
Q = 2 ** 252 + 27742317777372353535851937790883648493

Point = Tuple[int, int, int, int]  # extended coordinates (X, Y, Z, T)


def _sha512(data: bytes) -> bytes:
    return hashlib.sha512(data).digest()


def _sha512_modq(data: bytes) -> int:
    return int.from_bytes(_sha512(data), "little") % Q


def _modp_inv(x: int) -> int:
    return pow(x, P - 2, P)


D = -121665 * _modp_inv(121666) % P
_SQRT_M1 = pow(2, (P - 1) // 4, P)


def _recover_x(y: int, sign: int) -> Optional[int]:
    """The x that goes with a compressed y, or None if there is no such point."""
    if y >= P:
        return None
    x2 = (y * y - 1) * _modp_inv(D * y * y + 1) % P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P != 0:
        x = x * _SQRT_M1 % P
    if (x * x - x2) % P != 0:
        return None
    if (x & 1) != sign:
        x = P - x
    return x


_G_Y = 4 * _modp_inv(5) % P
_G_X = _recover_x(_G_Y, 0)
assert _G_X is not None  # the base point is on the curve by construction
G: Point = (_G_X, _G_Y, 1, _G_X * _G_Y % P)
NEUTRAL: Point = (0, 1, 1, 0)


def _point_add(p1: Point, p2: Point) -> Point:
    a = (p1[1] - p1[0]) * (p2[1] - p2[0]) % P
    b = (p1[1] + p1[0]) * (p2[1] + p2[0]) % P
    c = 2 * p1[3] * p2[3] * D % P
    dd = 2 * p1[2] * p2[2] % P
    e, f, g, h = b - a, dd - c, dd + c, b + a
    return (e * f % P, g * h % P, f * g % P, e * h % P)


def _point_mul(scalar: int, point: Point) -> Point:
    result = NEUTRAL
    while scalar > 0:
        if scalar & 1:
            result = _point_add(result, point)
        point = _point_add(point, point)
        scalar >>= 1
    return result


def _point_equal(p1: Point, p2: Point) -> bool:
    if (p1[0] * p2[2] - p2[0] * p1[2]) % P != 0:
        return False
    return (p1[1] * p2[2] - p2[1] * p1[2]) % P == 0


def _point_compress(point: Point) -> bytes:
    zinv = _modp_inv(point[2])
    x = point[0] * zinv % P
    y = point[1] * zinv % P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _point_decompress(data: bytes) -> Optional[Point]:
    if len(data) != 32:
        return None
    y = int.from_bytes(data, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % P)


def _secret_expand(secret: bytes) -> Tuple[int, bytes]:
    if len(secret) != 32:
        raise ValueError("an Ed25519 private key is 32 bytes")
    h = _sha512(secret)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(secret: bytes) -> bytes:
    """The 32-byte public key for a 32-byte seed."""
    a, _ = _secret_expand(secret)
    return _point_compress(_point_mul(a, G))


def sign(secret: bytes, message: bytes) -> bytes:
    """A 64-byte detached signature over ``message``."""
    a, prefix = _secret_expand(secret)
    encoded_public = _point_compress(_point_mul(a, G))
    r = _sha512_modq(prefix + message)
    encoded_r = _point_compress(_point_mul(r, G))
    h = _sha512_modq(encoded_r + encoded_public + message)
    s = (r + h * a) % Q
    return encoded_r + int.to_bytes(s, 32, "little")


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    """Whether ``signature`` is a valid Ed25519 signature. Never raises."""
    if len(public) != 32 or len(signature) != 64:
        return False
    point_a = _point_decompress(public)
    if point_a is None:
        return False
    encoded_r = signature[:32]
    s = int.from_bytes(signature[32:], "little")
    if s >= Q:
        return False
    point_r = _point_decompress(encoded_r)
    if point_r is None:
        return False
    h = _sha512_modq(encoded_r + public + message)
    return _point_equal(_point_mul(s, G), _point_add(point_r, _point_mul(h, point_a)))
