# Licensing & Payments

How Local Lead Scraper Pro is sold, licensed, and kept honest — and why each
piece works the way it does.

---

## 1. The thinking behind it

Licensing a desktop app is a different problem from licensing a SaaS. A web app
can check on every request because it *is* the server. A desktop app that phones
home before it will open has invented a new way to fail: the customer is on a job
site with no signal, or behind a corporate proxy, or you are having a bad
afternoon with your hosting provider, and the software they paid for will not
start. That is a support ticket and a refund, and it is entirely self-inflicted.

So the design starts from one rule:

> **The app must run offline. Forever, if it has to. The network is for
> *changing* what a licence says, never for *reading* it.**

Everything else follows.

### Signed licences, verified locally

At activation the licence server signs a small blob — tier, expiry, machine,
who owns it — with an **Ed25519** private key. The app carries the matching
public key and verifies it locally. Editing the file breaks the signature;
forging one needs a key that exists in exactly one place. The app never asks
anyone's permission to open.

### Two clocks, doing different jobs

Every licence carries `expires_at` and `refresh_after`, and conflating them is
the classic mistake.

| Clock | What it means | Who moves it |
|---|---|---|
| `expires_at` | The paid period ends here. Perpetual licences have none. | Stripe, at each renewal |
| `refresh_after` | Ask for a newer licence around now. Days, not months. | Every re-issue |

`refresh_after` is the **revocation channel**. There is no blocklist to
distribute and no "call home or die" check: a refunded licence simply stops
being re-signed, and it ages out on its own. Between `refresh_after` and the end
of the offline grace window, the app keeps working normally — because a customer
with no internet is not a thief.

| | Refresh interval | Offline grace |
|---|---|---|
| Subscription | 7 days | 14 days |
| Perpetual | 30 days | **180 days** |

Perpetual gets six months because someone who paid once should never be locked
out of software they own by a server we happen to be running. If we ever shut
the service down, the last thing it does is issue perpetual licences with no
refresh date at all.

### The trial is a licence too

The 72-hour trial is a signed token at the `trial` tier, so the app has exactly
one code path for "what am I allowed to do". Two rules keep it to one per
machine:

* **The server owns the clock.** Ask for a trial and you get back the start time
  the server already recorded for that fingerprint. Deleting your local state
  and reinstalling resumes an expired trial as expired.
* **Offline starts are provisional.** No answer from the server means you get
  six hours immediately, extended to the full 72 the moment the app can check
  in. Long enough to survive an outage or a flight; too short for "delete the
  config folder" to be a business model.

### What a fingerprint is, and is not

Seat enforcement needs to recognise the same machine tomorrow. It does not need
to know anything *about* it. The fingerprint hashes three inputs and keeps 128
bits:

* a random id this install wrote once into its own config directory,
* the OS's own installation id (`MachineGuid`, `IOPlatformUUID`, `/etc/machine-id`),
* hostname and architecture, as a weak tiebreaker.

The server stores an opaque value it cannot reverse into a serial number or a
username. Crucially, the inputs are all things that *do not move* when someone
docks a laptop, joins a VPN, or swaps a network card — the usual way seat
enforcement quietly burns a customer's seats and generates angry email.

### Turning the clock back

Trial expiry and subscription expiry are both wall-clock comparisons, so the
obvious attack is to set the date to last year. The state file keeps the highest
timestamp the app has ever seen; time moving backwards past that mark (with six
hours of slack for real drift and sleepy laptops) puts the app in
`clock_tampered` and asks the customer to fix their clock. It is not
unbreakable. It costs almost nothing and stops the version of this that anyone
actually tries.

### Expired never means locked out

An expired, revoked or long-offline licence falls back to the **Reader** tier:
the app opens, past scrapes are readable, CSV export still works. Nothing new is
scraped and nothing is sent.

Holding someone's own data hostage over a lapsed card is how you turn a renewal
conversation into a chargeback. The leads they collected are theirs.

### What this deliberately does not do

Be clear-eyed about what licensing can achieve for a Python application shipped
as source and as a PyInstaller bundle:

* **A determined person can patch it out.** They can edit `manager.py`, or
  replace the embedded public key with their own. No amount of obfuscation
  changes that, and the effort spent trying is better spent on features.
* **There is no anti-debugging, no packing, no phone-home telemetry.** Those
  annoy customers reliably and pirates briefly.

What the system *does* achieve is the thing that matters commercially: honest
customers can pay easily, seats are countable, refunds and chargebacks actually
end access, trials cannot be farmed by reinstalling, and nobody who paid ever
gets locked out by our infrastructure. That is the whole job.

---

## 2. How the pieces fit

```
                    ┌──────────────────────────────────────┐
   Customer ────────▶  Stripe Checkout (hosted, in their   │
                    │  browser — no card ever touches us)  │
                    └───────────────┬──────────────────────┘
                                    │ signed webhook
                                    ▼
   ┌───────────────────────────────────────────────────────┐
   │  Licence service  (payments/)                         │
   │   • creates the licence, generates LLSP-… key         │
   │   • counts seats, records activations                 │
   │   • signs licences with the Ed25519 private key       │
   └───────────────┬───────────────────────────────────────┘
                   │ activate / refresh (occasionally)
                   ▼
   ┌───────────────────────────────────────────────────────┐
   │  Desktop app  (licensing/)                            │
   │   • verifies offline with the public key              │
   │   • answers allows() / check() / max_results()        │
   │   • works for the whole grace window with no network  │
   └───────────────────────────────────────────────────────┘
```

### The client half — `licensing/`

| Module | Job |
|---|---|
| `plans.py` | The catalogue: tiers, both pricing models, the feature map. Read by the app *and* the server, so a price lives in one place. |
| `manager.py` | `LicenseManager` — the object everything asks. `allows()`, `check()`, `max_results()`, `activate()`, `refresh_if_due()`. |
| `tokens.py` | The signed licence format and its two clocks. |
| `trial.py` | The 72 hours, and the one-per-machine rule. |
| `keys.py` | The `LLSP-…` key people type, with a checksum. |
| `machine.py` | The fingerprint. |
| `storage.py` | The local state file, the clock guard, daily send counters. |
| `crypto.py` | Ed25519, with a vendored pure-Python fallback (below). |
| `client.py` | The five calls to the service, over `urllib`. |
| `console.py` | `--licence status / plans / trial / activate / deactivate`. |

**Why a vendored Ed25519.** `cryptography` is a compiled wheel, and a
PyInstaller build that fails to collect it produces an app that starts and then
cannot verify a licence — every customer in reader mode. `licensing/_ed25519.py`
is the RFC 8032 reference implementation; `crypto.py` prefers the real library
and falls back to it. Both are tested against the RFC's own vectors and against
each other. (Verification takes about 5 ms in pure Python. It happens once.)

### The server half — `payments/`

| Module | Job |
|---|---|
| `server.py` | Six endpoints, as a plain WSGI app. No framework. |
| `stripe_gateway.py` | Checkout, billing portal, webhook signature verification. No SDK. |
| `issuer.py` | What a SKU entitles someone to, and the signing. |
| `db.py` | SQLite: licences, activations, trials, and an append-only event log. |
| `cli.py` | keygen, manual grants, revocations, support lookups. |
| `config.py` | The environment it reads — and refuses to start without. |

**The webhook is the only thing that creates a paid licence.** Not the checkout
call, not the success redirect. Those are things a customer's browser can be
made to say. Money is real when Stripe says it is, signed, within the
five-minute replay window.

---

## 3. Running the service

### One-time setup

```bash
# 1. Generate the signing keypair and write the public half into the app
python -m payments.cli keygen --write-public licensing/public_key.py

#    Store the printed LLSP_SIGNING_KEY in the server's environment and in one
#    offline backup. Lose it and every future licence needs a new key plus an
#    app update; leak it and the same, urgently.

# 2. Create the products in Stripe, one price per SKU
python -m payments.cli pricing        # lists the nine SKUs to create

# 3. Point the server at them
export LLSP_SIGNING_KEY=…
export LLSP_STRIPE_SECRET_KEY=sk_live_…
export LLSP_STRIPE_WEBHOOK_SECRET=whsec_…
export LLSP_STRIPE_PRICE_SOLO_SUBSCRIPTION_MONTHLY=price_…
export LLSP_STRIPE_PRICE_SOLO_SUBSCRIPTION_YEARLY=price_…
export LLSP_STRIPE_PRICE_SOLO_PERPETUAL_ONCE=price_…
# …and the six for Pro and Agency
export LLSP_LICENSE_DB=/var/lib/llsp/licenses.db
export LLSP_PUBLIC_URL=https://licence.jlang.dev

# 4. Run it
python -m payments.server                      # development
gunicorn payments.server:application           # production
```

Point a Stripe webhook endpoint at `https://…/v1/stripe/webhook` and subscribe
to `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`,
`customer.subscription.deleted`, `charge.refunded`, `charge.dispute.created`.

The server refuses to start with anything missing. In particular it will not run
without a webhook secret, because an unverified webhook endpoint is a public URL
that mints Agency licences.

### Day to day

```bash
python -m payments.cli list --email someone@example.com
python -m payments.cli show LLSP-XXXXX-XXXXX-XXXXX-XXXXX   # seats, events, history
python -m payments.cli grant --sku pro-perpetual-once --email reviewer@site.com \
                             --months 3 --note "review copy"
python -m payments.cli release LLSP-… --machine <id>        # free a stuck seat
python -m payments.cli revoke LLSP-… --reason refunded
```

Every one of those writes to the event log, so "what happened to this licence"
is answerable from the database rather than from memory.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/trial` | start or resume this machine's 72 hours |
| POST | `/v1/activate` | bind a key to a machine, return a signed licence |
| POST | `/v1/refresh` | re-issue an ageing licence |
| POST | `/v1/deactivate` | free a seat |
| POST | `/v1/checkout` | a Stripe payment link for a SKU |
| POST | `/v1/stripe/webhook` | signed events from Stripe |
| GET | `/v1/pricing` | the catalogue, for a pricing page |
| GET | `/healthz` | liveness |

---

## 4. Building the app

The frozen app verifies licences against the constant in
`licensing/public_key.py`, not against an environment variable — a customer's
machine has no environment to read. So the key has to be written into the source
*before* PyInstaller runs.

The repository ships that constant empty on purpose, and the build workflows
fill it in:

```yaml
# Repository variable (Settings → Secrets and variables → Actions → Variables)
LLSP_LICENSE_PUBKEY: <the base64url public key from keygen>
```

```bash
python -m payments.cli set-public-key "$LLSP_LICENSE_PUBKEY"
```

**Use `set-public-key`, never `keygen`, in a build.** `keygen` mints a *new*
pair, so every release would trust a different key and every licence already
issued would stop verifying on upgrade. `keygen` is a once-ever command.

`--selftest` checks the result. A build with no key is a warning on an ordinary
PR — there is nothing to embed and the bundle must still be buildable — and a
**failure** when a release is being published, which the workflows signal by
setting `LLSP_REQUIRE_LICENCE_KEY=1` whenever a tag is in play. A keyless
release would put every customer in reader mode with no way out, so it should
never leave CI.

To build a signed bundle locally:

```bash
python -m payments.cli set-public-key "$LLSP_LICENSE_PUBKEY"
pyinstaller --clean --noconfirm packaging/LocalLeadScraperPro.spec
LLSP_REQUIRE_LICENCE_KEY=1 dist/LocalLeadScraperPro --selftest
git checkout licensing/public_key.py     # do not commit the filled-in key
```

---

## 5. Stripe or a merchant of record?

The implementation targets **Stripe**, and for launch that is the right call:
2.9% + 30¢, the best API, and money in your own account. What it does not do is
make you tax-compliant. With Stripe you are the seller of record, which means
VAT in the EU, GST in Australia, and sales tax in the forty-odd US states that
tax digital goods — your problem, at your risk.

A merchant of record (Paddle, Lemon Squeezy) charges roughly 5% + 50¢ and takes
all of that on. The extra ~2% is cheap insurance once you are selling
internationally in volume.

Suggested path: **start on Stripe, add Stripe Tax when US sales spread across
states, and move to an MoR if international sales become a meaningful share of
revenue.** The gateway is one 200-line module behind a small interface
(`payments/stripe_gateway.py`), so switching is a contained job rather than a
rewrite — that separation is deliberate.

---

## 6. Adding a gate to a new feature

```python
from licensing import get_manager, plans

# In the GUI — shows the upgrade dialog and returns False when not allowed
from gui.licensing_ui import require
if not require(self, plans.SITE_INTEL, action="Running a website audit"):
    return

# In a script or the TUI — prints why, exits non-zero
from licensing import console
console.require_or_exit(plans.EMAIL_SEND, action="Sending email")

# A numeric limit — clip, do not refuse
count = get_manager().max_results(requested)
```

Add the feature constant to `licensing/plans.py`, put it in the tiers that
should have it, and give it a label. The Licence page picks it up automatically.

Prefer **clipping to refusing**. A Solo licence asked for six industries should
run the two it covers and say so, not stop with an error. Refusals belong on
features, ceilings belong on volume.
