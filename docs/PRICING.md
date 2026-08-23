# Pricing

Two ways to pay for the same software, three tiers, one 72-hour trial.

All of it lives in [`licensing/plans.py`](../licensing/plans.py) as data — the
desktop app, the licence server and the pricing page read the same module, so a
price changes in one place.

---

## The two models

### Subscription — "keep it current"

Billed monthly or yearly. The licence expiry follows the billing period; stop
paying and the app drops to Reader (your data stays readable, scraping and
sending stop). Always the newest version.

### Perpetual — "own it"

Paid once. **Never expires.** Includes twelve months of updates; after that the
version you own keeps working forever and simply stops changing. Another year of
updates costs 40% of the original.

Two models rather than one because this product has two genuinely different
buyers, and making either of them use the other's pricing loses the sale:

* The **agency operator** running campaigns every week wants the newest scraper
  the day Google changes its markup. A subscription is correct, and cheap
  relative to one closed deal.
* The **owner-operator** who buys tools outright — the one who has been burned
  by six subscriptions and audits them every January — will not rent a scraper.
  A one-time price converts that person; a subscription-only page loses them
  entirely.

The perpetual price is set above a year of subscription (roughly 1.5×), so it
reads as "worth it if you'll use this for two years" rather than as a way to
undercut the recurring plan.

---

## The tiers

| | **Solo** | **Pro** | **Agency** |
|---|---|---|---|
| Monthly | **$39** | **$89** | **$199** |
| Yearly | **$390** *(2 months free)* | **$890** | **$1,990** |
| One-time (perpetual) | **$599** | **$1,299** | **$2,999** |
| Machines | 2 | 3 | 10 |
| Results per search | 200 | 1,000 | unlimited |
| Industries per batch | 2 | 8 | unlimited |
| Emails per day | 100 | 500 | 2,000 |
| Google Maps search | ✓ | ✓ | ✓ |
| Website contact scan | ✓ | ✓ | ✓ |
| Phone-number lookup | ✓ | ✓ | ✓ |
| CSV export | ✓ | ✓ | ✓ |
| Email composer + SMTP send | ✓ | ✓ | ✓ |
| Sales Call Cockpit | ✓ | ✓ | ✓ |
| Website intelligence (PageSpeed, tech stack, SEO) | — | ✓ | ✓ |
| Local SEO rank tracking | — | ✓ | ✓ |
| K-12 fundraiser pipeline | — | ✓ | ✓ |
| Excel (.xlsx) export | — | ✓ | ✓ |
| Your own branding on emails | — | — | ✓ |
| CRM / webhook export | — | — | ✓ |
| Scheduled / headless runs | — | — | ✓ |

### The 72-hour trial

Every feature, three days, with two limits: searches return 25 results and email
sending stays in dry-run.

The shape is deliberate. Trials that hide features teach people what the product
*cannot* do; trials that hand over a complete lead list get used once and
abandoned. Full capability with capped output means someone can run the entire
workflow — scrape, scan, prioritise, rehearse a call, compose an email — and see
exactly what they would be buying, without walking away with the deliverable.

Three days rather than fourteen because this is an afternoon's work, and a
fourteen-day trial is mostly a fortnight of forgetting.

---

## Why these numbers

Anchored on what the market charges (see
[COMPETITIVE_ANALYSIS.md](COMPETITIVE_ANALYSIS.md) for sources):

* **Lead Scrape**, the closest desktop competitor, is $97/yr Standard and
  $247/yr Business, 2 computers, a year of updates. Solo at $390/yr sits above
  it — justified by the cockpit, the site audits and the email sender, none of
  which it has.
* **Cloud scrapers** run $19–$199/mo plus per-record fees; **Outscraper** is
  ~$3/1,000 records and roughly $9–11/1,000 once emails are enriched.
* **Outreach platforms** — Instantly from ~$37/mo, Lemlist ~$69/mo, Apollo to
  ~$119/user/mo — sell the sending half only.
* **Local-SEO tools** — BrightLocal $39–$79/mo — sell the audit half only.

A user of the competition typically pays for two or three of those at once. Pro
at $89/mo replaces a scraper subscription, per-record fees and a light audit
tool, which is the sentence the pricing page should lead with.

**The structural advantage is no per-record pricing.** Scraping 10,000
businesses costs $60 on Outscraper and $0 here — the work happens on the
customer's own machine. That is worth saying out loud on the pricing page,
because it is the one number where this product wins by an order of magnitude.

Deliberately **not** priced per lead: it would be unenforceable in a desktop app
and would punish exactly the heavy users who should be the happiest customers.
Volume limits are per-search ceilings, which shape *how* the tool is used rather
than metering its output.

### Room to move

| Lever | When |
|---|---|
| A $19/mo "Starter" (one industry, 50 results, no send) | If Solo proves too big a first step |
| Per-seat Agency pricing above 10 machines | When a real agency asks |
| Founding-customer perpetual at 30% off, first 50 buyers | Launch, to build the reference list |
| Annual "updates renewal" upsell at 40% | Month 13 of every perpetual licence |

---

## Refunds, upgrades and seats

* **Refunds** end the licence immediately and free every seat (`charge.refunded`
  and `charge.dispute.created` both do this). A 14-day no-questions policy is
  worth publishing — the competition offers one and it costs less than the
  arguments.
* **Cancelling** keeps the licence working to the end of the period already
  paid for. Cutting access off at cancellation is taking back time someone
  bought.
* **A failed payment changes nothing** on the first bounce. Stripe retries for
  days, and the usual cause is an expired card. The expiry date already handles
  the case where the retries never succeed.
* **Upgrades** edit the existing licence rather than issuing a second one — the
  key a customer already has keeps working.
* **Seats** are freed from the app ("Deactivate this computer") or by support
  (`payments.cli release`). Reactivating the same machine never takes a second
  seat.
