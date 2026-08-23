"""Operator tools for the licence server.

    python -m payments.cli keygen [--write-public licensing/public_key.py]
    python -m payments.cli grant --sku pro-perpetual-once --email me@example.com
    python -m payments.cli show LLSP-XXXXX-XXXXX-XXXXX-XXXXX
    python -m payments.cli list [--email me@example.com]
    python -m payments.cli revoke LLSP-… [--reason refunded]
    python -m payments.cli release LLSP-… --machine <id>
    python -m payments.cli pricing

``grant`` is the one that earns its keep: refunds, replacement keys, review
copies, the customer whose card failed at a conference — all of them are "issue
a licence without a Stripe charge", and doing that by hand in SQL is how a
support request becomes an outage.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List, Optional

from licensing import crypto, keys, plans

from . import issuer
from .config import Settings
from .db import Database


def _db(args) -> Database:
    return Database(args.database or Settings.from_env().database_path)


def _write_public_key(path_text: str, public_b64: str) -> None:
    """Rewrite ``EMBEDDED_PUBLIC_KEY`` in licensing/public_key.py, in place."""
    path = Path(path_text)
    marker = "EMBEDDED_PUBLIC_KEY = "
    text = path.read_text(encoding="utf-8")
    lines = [f'{marker}"{public_b64}"\n' if line.startswith(marker) else line
             for line in text.splitlines(keepends=True)]
    path.write_text("".join(lines), encoding="utf-8")
    print(f"public key written into {path}")


def cmd_set_public_key(args) -> int:
    """Embed an *existing* public key in the app, for release builds.

    ``keygen`` makes a new pair, which is exactly what a build must not do —
    every release would trust a different key and every installed licence would
    stop verifying. The release job keeps the public key in a repository
    variable and writes it in with this.
    """
    text = args.key.strip()
    try:
        raw = crypto.b64decode(text)
    except Exception as exc:  # noqa: BLE001 - any decode failure is the same failure
        print(f"that is not a base64url key: {exc}", file=sys.stderr)
        return 2
    from licensing import public_key as key_module

    if len(raw) != 32 or not key_module.usable(raw):
        print("that is not a usable Ed25519 public key (32 bytes, full order)",
              file=sys.stderr)
        return 2
    _write_public_key(args.write_public, crypto.b64encode(raw))
    return 0


def cmd_keygen(args) -> int:
    """Make the signing keypair. Run once, then guard the private half."""
    seed, public = crypto.generate_keypair()
    seed_b64, public_b64 = crypto.b64encode(seed), crypto.b64encode(public)
    if args.write_public:
        _write_public_key(args.write_public, public_b64)
    print("\n=== KEEP THIS SECRET — it is the only thing that mints licences ===")
    print(f"export LLSP_SIGNING_KEY={seed_b64}")
    print("\n=== Safe to publish; ships inside the app ===")
    print(f"LLSP_LICENSE_PUBKEY={public_b64}")
    print("\nStore the signing key in the server's environment and in one "
          "offline backup. If it is lost, every future licence needs a new "
          "key and every installed app needs an update; if it leaks, the same.")
    return 0


def cmd_grant(args) -> int:
    """Issue a licence with no payment attached."""
    price = plans.price_for(args.sku)
    if price is None:
        print(f"unknown sku {args.sku!r}. Try: python -m payments.cli pricing",
              file=sys.stderr)
        return 2
    database = _db(args)
    key = args.key or keys.generate()
    terms = issuer.terms_for(args.sku)
    if args.months:
        # A comp or a review copy usually wants its own clock.
        if terms["expires_at"]:
            terms["expires_at"] = time.time() + args.months * 30.5 * 86400
        else:
            terms["updates_until"] = time.time() + args.months * 30.5 * 86400
    if args.machines:
        terms["max_machines"] = args.machines
    database.create_licence(key=key, email=args.email, name=args.name or "",
                            extra_features=args.feature or [],
                            notes=args.note or "granted from the CLI", **terms)
    print(key)
    if args.json:
        print(json.dumps(database.licence(key), indent=2, default=str))
    return 0


def cmd_show(args) -> int:
    database = _db(args)
    licence = database.licence(keys.parse(args.key))
    if licence is None:
        print("no such licence", file=sys.stderr)
        return 1
    print(json.dumps(licence, indent=2, default=str))
    print("\nactivations:")
    for row in database.activations(licence["key"], include_released=True):
        state = "released" if row["released_at"] else "active"
        print(f"  seat {row['seat']}  {state:8}  {row['label'] or row['machine_id'][:12]}")
    print("\nrecent events:")
    for event in database.events(licence["key"], limit=10):
        stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(event["at"]))
        print(f"  {stamp}  {event['kind']:16} {event['detail']}")
    return 0


def cmd_list(args) -> int:
    database = _db(args)
    if args.email:
        rows = database.licences_for_email(args.email)
    else:
        rows = [dict(row) for row in database.query(
            "SELECT * FROM licences ORDER BY created_at DESC LIMIT ?", args.limit)]
    for licence in rows:
        expiry = (time.strftime("%Y-%m-%d", time.localtime(licence["expires_at"]))
                  if licence.get("expires_at") else "never")
        seats = f"{database.seats_used(licence['key'])}/{licence['max_machines']}"
        print(f"{licence['key']}  {licence['tier']:7} {licence['model']:12} "
              f"{licence['status']:9} seats {seats:6} expires {expiry}  "
              f"{licence['email']}")
    return 0


def cmd_revoke(args) -> int:
    database = _db(args)
    key = keys.parse(args.key)
    if database.licence(key) is None:
        print("no such licence", file=sys.stderr)
        return 1
    database.update_licence(key, status=args.reason)
    for row in database.activations(key):
        database.release(key, row["machine_id"])
    database.log(key, "revoked", args.reason)
    print(f"{key} is now {args.reason}; every seat released")
    return 0


def cmd_release(args) -> int:
    database = _db(args)
    key = keys.parse(args.key)
    print("released" if database.release(key, args.machine) else "no such activation")
    return 0


def cmd_pricing(args) -> int:
    for price in plans.catalog():
        tier = plans.TIERS[price.tier]
        print(f"{price.sku:32} {price.display:>10}  {tier.limits.max_machines} machines")
    print("\nStripe price ids are read from the environment as, for example:")
    print("  LLSP_STRIPE_PRICE_PRO_SUBSCRIPTION_MONTHLY=price_1234")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="payments.cli",
                                     description=__doc__.splitlines()[0])
    parser.add_argument("--database", default="", help="path to licenses.db")
    sub = parser.add_subparsers(dest="command", required=True)

    keygen = sub.add_parser("keygen", help="generate the Ed25519 signing keypair")
    keygen.add_argument("--write-public", default="",
                        help="path to licensing/public_key.py to update in place")
    keygen.set_defaults(func=cmd_keygen)

    embed = sub.add_parser("set-public-key",
                           help="embed an existing public key in the app (release builds)")
    embed.add_argument("key", help="the base64url public key")
    embed.add_argument("--write-public", default="licensing/public_key.py")
    embed.set_defaults(func=cmd_set_public_key)

    grant = sub.add_parser("grant", help="issue a licence without a payment")
    grant.add_argument("--sku", required=True)
    grant.add_argument("--email", default="")
    grant.add_argument("--name", default="")
    grant.add_argument("--key", default="", help="reuse a specific key")
    grant.add_argument("--months", type=int, default=0)
    grant.add_argument("--machines", type=int, default=0)
    grant.add_argument("--feature", action="append", help="extra feature to grant")
    grant.add_argument("--note", default="")
    grant.add_argument("--json", action="store_true")
    grant.set_defaults(func=cmd_grant)

    show = sub.add_parser("show", help="everything known about one licence")
    show.add_argument("key")
    show.set_defaults(func=cmd_show)

    listing = sub.add_parser("list", help="recent licences")
    listing.add_argument("--email", default="")
    listing.add_argument("--limit", type=int, default=50)
    listing.set_defaults(func=cmd_list)

    revoke = sub.add_parser("revoke", help="end a licence and free its seats")
    revoke.add_argument("key")
    revoke.add_argument("--reason", default="refunded",
                        choices=["refunded", "cancelled"])
    revoke.set_defaults(func=cmd_revoke)

    release = sub.add_parser("release", help="free one machine's seat")
    release.add_argument("key")
    release.add_argument("--machine", required=True)
    release.set_defaults(func=cmd_release)

    pricing = sub.add_parser("pricing", help="the catalogue and its Stripe ids")
    pricing.set_defaults(func=cmd_pricing)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
