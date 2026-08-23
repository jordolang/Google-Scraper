"""Everything the licence server reads from its environment.

Nothing here has a working default. A server that starts without a signing key
or a Stripe secret would happily hand out licences nobody paid for, so
:func:`Settings.problems` lists what is missing and ``python -m payments.server``
refuses to start until the list is empty.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

# -- environment variable names ------------------------------------------
SIGNING_KEY = "LLSP_SIGNING_KEY"            # base64url Ed25519 seed, 32 bytes
STRIPE_SECRET_KEY = "LLSP_STRIPE_SECRET_KEY"
STRIPE_WEBHOOK_SECRET = "LLSP_STRIPE_WEBHOOK_SECRET"
STRIPE_PRICE_PREFIX = "LLSP_STRIPE_PRICE_"  # + SKU, upper case, dashes as _
DATABASE_PATH = "LLSP_LICENSE_DB"
PUBLIC_URL = "LLSP_PUBLIC_URL"              # where this server is reachable
SUCCESS_URL = "LLSP_CHECKOUT_SUCCESS_URL"
CANCEL_URL = "LLSP_CHECKOUT_CANCEL_URL"
SUPPORT_EMAIL = "LLSP_SUPPORT_EMAIL"
BIND_HOST = "LLSP_BIND_HOST"
BIND_PORT = "LLSP_BIND_PORT"


@dataclass
class Settings:
    signing_key_b64: str = ""
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    database_path: str = "licenses.db"
    public_url: str = "http://127.0.0.1:8787"
    success_url: str = ""
    cancel_url: str = ""
    support_email: str = "support@jlang.dev"
    host: str = "127.0.0.1"
    port: int = 8787
    #: Stripe price ids keyed by SKU ("pro-subscription-monthly").
    price_ids: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls, environ: Optional[dict] = None) -> "Settings":
        env = dict(os.environ if environ is None else environ)
        settings = cls(
            signing_key_b64=env.get(SIGNING_KEY, ""),
            stripe_secret_key=env.get(STRIPE_SECRET_KEY, ""),
            stripe_webhook_secret=env.get(STRIPE_WEBHOOK_SECRET, ""),
            database_path=env.get(DATABASE_PATH, "licenses.db"),
            public_url=env.get(PUBLIC_URL, "http://127.0.0.1:8787").rstrip("/"),
            success_url=env.get(SUCCESS_URL, ""),
            cancel_url=env.get(CANCEL_URL, ""),
            support_email=env.get(SUPPORT_EMAIL, "support@jlang.dev"),
            host=env.get(BIND_HOST, "127.0.0.1"),
        )
        try:
            settings.port = int(env.get(BIND_PORT, "8787"))
        except ValueError:
            settings.port = 8787
        for name, value in env.items():
            if name.startswith(STRIPE_PRICE_PREFIX) and value:
                sku = name[len(STRIPE_PRICE_PREFIX):].lower().replace("_", "-")
                settings.price_ids[sku] = value
        settings.success_url = settings.success_url or f"{settings.public_url}/thanks"
        settings.cancel_url = settings.cancel_url or f"{settings.public_url}/pricing"
        return settings

    def problems(self) -> List[str]:
        """What must be fixed before this server should take real money."""
        missing = []
        if not self.signing_key_b64:
            missing.append(f"{SIGNING_KEY} is not set — run "
                           f"`python -m payments.cli keygen`")
        if not self.stripe_secret_key:
            missing.append(f"{STRIPE_SECRET_KEY} is not set")
        if not self.stripe_webhook_secret:
            missing.append(f"{STRIPE_WEBHOOK_SECRET} is not set — without it "
                           f"anyone who finds the webhook URL can mint licences")
        if not self.price_ids:
            missing.append(f"no {STRIPE_PRICE_PREFIX}* price ids are set")
        return missing

    def signing_key(self) -> bytes:
        from licensing import crypto

        raw = crypto.b64decode(self.signing_key_b64) if self.signing_key_b64 else b""
        if len(raw) != 32:
            raise ValueError(f"{SIGNING_KEY} must be a base64url 32-byte Ed25519 seed")
        return raw

    def price_id(self, sku: str) -> str:
        return self.price_ids.get(sku, "")
