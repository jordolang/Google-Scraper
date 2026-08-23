"""The licence and payment service behind Local Lead Scraper Pro.

This package is the *server* half of the system. It never ships inside the
desktop app: it runs on one small host, takes Stripe webhooks, and signs the
licence tokens that :mod:`licensing` verifies offline on customers' machines.

* :mod:`payments.server` — the WSGI service and its six endpoints.
* :mod:`payments.stripe_gateway` — Checkout, the billing portal, webhook
  signature verification.
* :mod:`payments.issuer` — what a SKU entitles someone to, and the signing.
* :mod:`payments.db` — the SQLite store: licences, activations, trials, events.
* :mod:`payments.cli` — keygen, manual grants, revocations, support lookups.
* :mod:`payments.config` — the environment it reads, and what it refuses to
  start without.
"""

from __future__ import annotations
