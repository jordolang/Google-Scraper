# 📞 Sales Call Cockpit

Turns scraped business data into a prioritized phone-call campaign with deep
per-business website intelligence and a live, interactive teleprompter.

> 💡 **The cockpit is now reachable from the unified outreach app** —
> `python app.py` → Sales Call Cockpit, or `python sales_calls.py` for a
> shortcut straight into it. The standalone Rich-terminal commands below
> remain available as `python sales_calls.py --classic {prep|sheet|call}`.

## Quick start

```bash
pip install -r requirements.txt

# 1. (Recommended) free Google PageSpeed key for reliable speed scores in batch
export PAGESPEED_API_KEY="your-key"   # https://developers.google.com/speed/docs/insights/v5/get-started

# 2. Analyze + cache every business's website (run once per scrape)
python3 sales_calls.py prep

# 3. See the prioritized call schedule
python3 sales_calls.py sheet

# 4. Start calling — the live cockpit
python3 sales_calls.py call
```

Run with no arguments for an interactive menu.

## How it prioritizes

| Tier | Who | Why first |
|------|-----|-----------|
| **1** | No website **and** no email | Cleanest, most urgent pitch ("you're invisible online") |
| **2** | No website | High need |
| **3** | Weak site / no contact captured | Consultative upsell |
| **4** | Established site | Intel-driven upsell |
| — | No valid phone | Parked (can't call) |

Within a tier, businesses are ranked by reviews + rating (social proof / ability to pay).

## What the website intel gathers

For every business with a site (`salescall/intel/`):

- **PageSpeed / Core Web Vitals** — real mobile performance, LCP, CLS, TBT, SEO score (Google API)
- **Runtime errors** — JS console errors + failed network/API calls (headless Chrome)
- **Tech stack** — Wix / WordPress / Squarespace / Shopify / Webflow / GoDaddy / custom
- **Hosting** — provider + rough monthly cost + lock-in angle
- **SEO** — title/meta/H1/schema/Open Graph/sitemap/HTTPS/mobile-viewport/alt coverage/thin content

Every finding carries a **spoken sales translation** — what the caller actually *says* about it.

## Local SEO ranking (`salescall/localseo.py`)

The scraped businesses **are** the local competitive set for your origin search
(default **Zanesville, OH** — override with `SALESCALL_ORIGIN_LATLNG="lat,lng"`).
GPS coordinates are pulled from each Maps URL, so for every business you get:

- **Local rank within its career field** — e.g. "#15 of 28 roofers near the origin"
- **Competitors ranked above them** (and whether each has a website)
- **Closest competitor** by real driving-distance proxy (miles)
- **Competitiveness percentile** within the field

Ranking uses the factors Google actually weighs for the local pack —
**prominence (reviews + rating), proximity, and web presence**.

### Real SERP positions (`salescall/serp.py`)

Set **`SERPAPI_KEY`** in `.env` and `prep` fetches the **actual Google Maps
local-pack positions** for each "{field} {location}" query, matches your
businesses by name, and caches them (`.salescall_cache/serp_rankings.json`).
When a real position is known, the cockpit shows it as fact ("Google rank
#4 of 20"); otherwise it falls back to the proxy and marks it with `~`
("~#15/28"). Provider is pluggable (SerpApi default; Brightdata/DataForSEO
drop in at `_PROVIDERS`). Free tier is ~100 searches/mo — one search per
career field, cached.

Review counts are now captured by the scraper (`reviews_count`), which sharpens
both the proxy ranking and call-priority scoring.

## The cockpit (live call)

Per call it shows a **pre-call brief** (snapshot + intel + top talking points), then
walks the playbook stage-by-stage (**OPEN → DISCOVER → PITCH → CLOSE**). Each step shows:

- 🎙 **SAY** — verbatim dialogue, personalized to the business
- ▶ **DO** — stage direction
- ⏸ **CUE** — when to pause / listen
- 👂 **ANTICIPATE** — likely responses
- 🔀 **OPTIONS** — branches

Controls: `n`/Enter next · `p` prev · `o` objection handlers · `m` mark outcome ·
`c` log callback · `b` brief · `s` skip · `q` quit · `?` help.

Outcomes persist to `.salescall_cache/session.json`, so you can pause and resume.

## Architecture

```
salescall/
  models.py        frozen dataclasses (Business, WebsiteIntel, Finding, QueueEntry, Outcome)
  data_loader.py   merge google_maps_results_*.csv + contact_details_*.csv → clean records
  prioritize.py    tiering + scoring + suggested call durations
  intel/           website analysis engine (fetch, seo, techstack, hosting, pagespeed, errors)
  objections.py    objection-handling knowledge base
  playbook.py      per-business staged call script
  console.py       rich-terminal interactive cockpit
  scheduler.py     session + outcome persistence
  cache.py         per-business intel cache
sales_calls.py     entry point (prep / sheet / call)
```

## Roadmap / extension points

- **Twilio click-to-dial** — `console.py` is provider-agnostic; a dial hook slots in cleanly.
- **Brightdata / anti-bot scraping** — `intel/fetch.py` is the single choke point to upgrade.
- **Per-business proposal/email auto-send** on a "booked" disposition (reuses `send_emails.py`).
