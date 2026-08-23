"""The signing primitives, checked against RFC 8032 and against each other.

Everything else in the licensing system rests on these two functions being
right, so they are tested against the specification's own vectors rather than
against our own output — a self-consistent wrong implementation would pass a
round-trip test happily.
"""

from __future__ import annotations

import binascii

import pytest

from licensing import _ed25519, crypto

# RFC 8032 §7.1, TEST 1 / TEST 2 / TEST 3.
VECTORS = [
    (
        "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
        "",
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590"
        "a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
    ),
    (
        "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
        "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
        "72",
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e"
        "15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00",
    ),
    (
        "c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
        "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
        "af82",
        "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d"
        "16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a",
    ),
]


@pytest.mark.parametrize("seed_hex,public_hex,message_hex,signature_hex", VECTORS)
def test_matches_rfc8032_vectors(seed_hex, public_hex, message_hex, signature_hex):
    seed = binascii.unhexlify(seed_hex)
    message = binascii.unhexlify(message_hex)
    assert _ed25519.public_key(seed) == binascii.unhexlify(public_hex)
    assert _ed25519.sign(seed, message) == binascii.unhexlify(signature_hex)
    assert _ed25519.verify(binascii.unhexlify(public_hex), message,
                           binascii.unhexlify(signature_hex))


def test_rejects_a_tampered_message():
    seed = binascii.unhexlify(VECTORS[1][0])
    public = binascii.unhexlify(VECTORS[1][1])
    signature = _ed25519.sign(seed, b"invoice for $89")
    assert _ed25519.verify(public, b"invoice for $89", signature)
    assert not _ed25519.verify(public, b"invoice for $0", signature)


def test_rejects_junk_without_raising():
    """A damaged licence file must be a False, never an exception."""
    assert not _ed25519.verify(b"", b"x", b"")
    assert not _ed25519.verify(b"\x00" * 31, b"x", b"\x00" * 64)
    assert not crypto.verify(b"short", b"x", b"\x00" * 64)
    assert not crypto.verify(b"\x00" * 32, b"x", b"tiny")


def test_degenerate_public_keys_are_treated_as_no_key():
    """RFC 8032 verification accepts anything against a small-order key.

    Both backends do — it is the specification's behaviour, not a bug in
    either. What must not happen is *shipping* such a key, so the key loader
    refuses one and the app falls back to reader mode instead of accepting
    forged licences.
    """
    from licensing import public_key as key_module

    # Whether a given message sails through depends on the hash landing on an
    # even scalar, so this looks for one rather than hard-coding a message and
    # hoping. Some message always works.
    forged = [message for message in (b"x", b"y", b"z", b"1", b"2", b"pro")
              if crypto.verify(b"\x00" * 32, message, b"\x00" * 64)]
    assert forged, "expected RFC 8032 verification to accept a small-order key"
    assert not key_module.usable(b"\x00" * 32)  # which is why the loader refuses it
    _seed, real = crypto.generate_keypair()
    assert key_module.usable(real)


def test_public_key_env_override(monkeypatch):
    from licensing import public_key as key_module

    _seed, real = crypto.generate_keypair()
    monkeypatch.setenv(key_module.PUBLIC_KEY_ENV, crypto.b64encode(real))
    assert key_module.public_key() == real
    assert key_module.configured()

    monkeypatch.setenv(key_module.PUBLIC_KEY_ENV, "not-base64-@@@")
    assert key_module.public_key() == b""
    monkeypatch.setenv(key_module.PUBLIC_KEY_ENV, crypto.b64encode(b"\x00" * 32))
    assert not key_module.configured()


def test_backends_agree(monkeypatch):
    """Whichever backend a machine has, it must reach the same verdict."""
    seed, public = crypto.generate_keypair()
    message = b"tier=pro;machine=abc"
    signature = crypto.sign(seed, message)

    monkeypatch.setenv(crypto.FORCE_FALLBACK_ENV, "1")
    assert crypto.backend() == "pure-python"
    assert crypto.public_key(seed) == public
    assert crypto.verify(public, message, signature)
    assert crypto.sign(seed, message) == signature  # Ed25519 is deterministic
    assert not crypto.verify(public, message + b"!", signature)


def test_base64_round_trip_survives_stripping():
    """Keys get copied out of emails and CI logs; padding does not survive."""
    seed, public = crypto.generate_keypair()
    text = crypto.b64encode(public)
    assert "=" not in text
    assert crypto.b64decode(text) == public
    assert crypto.b64decode(f"  {text}  ") == public


def test_signing_seed_must_be_32_bytes():
    with pytest.raises(ValueError):
        crypto.sign(b"too short", b"message")
