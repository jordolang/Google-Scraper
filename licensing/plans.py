"""What we sell, and what each thing unlocks.

Two pricing models, three tiers, one 72-hour trial:

* **Subscription** — billed monthly or yearly. The licence carries an expiry
  that moves forward every time Stripe renews it. Stop paying and the app
  falls back to the free reader tier.
* **Perpetual** — paid once, never expires. What it *does* stop is updates:
  twelve months of them are included, after which the app keeps running the
  version you own forever, and a renewal (40% of the original price) buys
  another twelve months of new versions.

Both models are sold at the same three tiers, so the tier decides features and
the model decides how long you keep them.

Everything here is data, deliberately: the licence server and the desktop app
both read this module, so a price or a limit is changed in exactly one place.
Money is stored in integer cents — never floats — because ``0.1 + 0.2`` is not
a price.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# -- tiers ---------------------------------------------------------------

TRIAL = "trial"
SOLO = "solo"
PRO = "pro"
AGENCY = "agency"
#: What an expired or unlicensed install falls back to: the app opens, past
#: work is readable and exportable, nothing new is scraped or sent.
READER = "reader"

TIER_ORDER: Tuple[str, ...] = (READER, TRIAL, SOLO, PRO, AGENCY)


# -- billing models ------------------------------------------------------

SUBSCRIPTION = "subscription"
PERPETUAL = "perpetual"

#: Trial length. Three days, deliberately not seven: the pipeline is a
#: one-afternoon job, and a short clock is what makes people actually run it.
TRIAL_HOURS = 72


@dataclass(frozen=True)
class Limits:
    """The numbers a tier is allowed. ``None`` means "no ceiling"."""

    #: Businesses one Google Maps search may return.
    max_results_per_search: Optional[int] = 50
    #: Industries queued in a single batch run.
    max_industries_per_batch: Optional[int] = 1
    #: Emails the sender will deliver per calendar day. 0 = dry run only.
    max_emails_per_day: int = 0
    #: Machines that may hold an activation at once.
    max_machines: int = 1
    #: Rows an export writes before it truncates. ``None`` means all of them.
    max_export_rows: Optional[int] = None


@dataclass(frozen=True)
class Tier:
    key: str
    name: str
    blurb: str
    limits: Limits
    features: frozenset
    #: (monthly cents, yearly cents) — None where the tier is not sold.
    subscription_cents: Optional[Tuple[int, int]] = None
    #: One-time price in cents for the perpetual licence.
    perpetual_cents: Optional[int] = None
    #: Months of updates a perpetual purchase includes.
    perpetual_update_months: int = 12


# -- features ------------------------------------------------------------
# One string per gated capability. Pages and scripts ask for these by name, so
# a rename is a code change rather than a silent unlock.

SCRAPE_MAPS = "scrape.maps"                 # Google Maps search
SCRAPE_CONTACTS = "scrape.contacts"         # website contact scan
PHONE_LOOKUP = "scrape.phone_lookup"        # directory fallback lookup
EXPORT_CSV = "export.csv"
EXPORT_XLSX = "export.xlsx"
EXPORT_CRM = "export.crm"                   # webhook / CRM push
EMAIL_COMPOSE = "email.compose"
EMAIL_SEND = "email.send"                   # actually deliver, not dry-run
EMAIL_BRANDING = "email.branding"           # own logo/footer, no "made with"
CALL_COCKPIT = "cockpit.calls"              # the sales-call cockpit
SITE_INTEL = "cockpit.site_intel"           # PageSpeed / tech stack / SEO audit
LOCAL_SEO_RANK = "cockpit.local_seo"        # local-pack ranking
SCHOOL_PIPELINE = "pipeline.schools"        # K-12 fundraiser pipeline
AUTOMATION_CLI = "automation.cli"           # headless/scheduled runs
TEAM_SEATS = "team.seats"                   # more than one machine

ALL_FEATURES: Tuple[str, ...] = (
    SCRAPE_MAPS, SCRAPE_CONTACTS, PHONE_LOOKUP,
    EXPORT_CSV, EXPORT_XLSX, EXPORT_CRM,
    EMAIL_COMPOSE, EMAIL_SEND, EMAIL_BRANDING,
    CALL_COCKPIT, SITE_INTEL, LOCAL_SEO_RANK,
    SCHOOL_PIPELINE, AUTOMATION_CLI, TEAM_SEATS,
)

FEATURE_LABELS: Dict[str, str] = {
    SCRAPE_MAPS: "Google Maps search",
    SCRAPE_CONTACTS: "Website contact scan",
    PHONE_LOOKUP: "Phone-number lookup fallback",
    EXPORT_CSV: "CSV export",
    EXPORT_XLSX: "Excel (.xlsx) export",
    EXPORT_CRM: "CRM / webhook export",
    EMAIL_COMPOSE: "Email composer",
    EMAIL_SEND: "Send email over SMTP",
    EMAIL_BRANDING: "Your own branding on emails",
    CALL_COCKPIT: "Sales Call Cockpit",
    SITE_INTEL: "Website intelligence (PageSpeed, tech stack, SEO)",
    LOCAL_SEO_RANK: "Local SEO rank tracking",
    SCHOOL_PIPELINE: "K-12 fundraiser pipeline",
    AUTOMATION_CLI: "Scheduled / headless runs",
    TEAM_SEATS: "Extra machines",
}

#: Everything a paying customer could have — the trial shows all of it.
_FULL = frozenset(ALL_FEATURES)


TIERS: Dict[str, Tier] = {
    READER: Tier(
        key=READER,
        name="Reader",
        blurb="Open the app, read and export what you already collected.",
        limits=Limits(max_results_per_search=0, max_industries_per_batch=0,
                      max_emails_per_day=0, max_machines=1),
        features=frozenset({EXPORT_CSV}),
    ),
    TRIAL: Tier(
        key=TRIAL,
        name="72-hour trial",
        blurb=("Every feature, for three days. Searches cap at 25 results and "
               "email sending stays in dry-run — everything else is the real "
               "thing."),
        # Wide open on features, deliberately narrow on volume: the trial is
        # meant to prove the workflow, not to complete a campaign for free.
        limits=Limits(max_results_per_search=25, max_industries_per_batch=1,
                      max_emails_per_day=0, max_machines=1,
                      max_export_rows=25),
        features=_FULL,
    ),
    SOLO: Tier(
        key=SOLO,
        name="Solo",
        blurb="One operator, one town. Scrape, scan, and email your own list.",
        limits=Limits(max_results_per_search=200, max_industries_per_batch=2,
                      max_emails_per_day=100, max_machines=2),
        features=frozenset({
            SCRAPE_MAPS, SCRAPE_CONTACTS, PHONE_LOOKUP,
            EXPORT_CSV, EMAIL_COMPOSE, EMAIL_SEND, CALL_COCKPIT,
        }),
        subscription_cents=(3900, 39000),   # $39/mo, $390/yr (two months free)
        perpetual_cents=59900,              # $599 once
    ),
    PRO: Tier(
        key=PRO,
        name="Pro",
        blurb=("The whole toolkit: website intelligence, local SEO ranking, "
               "the school pipeline, and Excel exports."),
        limits=Limits(max_results_per_search=1000, max_industries_per_batch=8,
                      max_emails_per_day=500, max_machines=3),
        features=frozenset({
            SCRAPE_MAPS, SCRAPE_CONTACTS, PHONE_LOOKUP,
            EXPORT_CSV, EXPORT_XLSX, EMAIL_COMPOSE, EMAIL_SEND,
            CALL_COCKPIT, SITE_INTEL, LOCAL_SEO_RANK, SCHOOL_PIPELINE,
            TEAM_SEATS,
        }),
        subscription_cents=(8900, 89000),   # $89/mo, $890/yr
        perpetual_cents=129900,             # $1,299 once
    ),
    AGENCY: Tier(
        key=AGENCY,
        name="Agency",
        blurb=("Everything in Pro, unmetered, on ten machines — plus your own "
               "branding, CRM push, and scheduled runs."),
        limits=Limits(max_results_per_search=None, max_industries_per_batch=None,
                      max_emails_per_day=2000, max_machines=10),
        features=_FULL,
        subscription_cents=(19900, 199000),  # $199/mo, $1,990/yr
        perpetual_cents=299900,              # $2,999 once
    ),
}


# -- price lookup --------------------------------------------------------

MONTHLY = "monthly"
YEARLY = "yearly"
ONCE = "once"

#: How long a perpetual renewal costs relative to the original, in percent.
PERPETUAL_RENEWAL_PERCENT = 40


@dataclass(frozen=True)
class Price:
    """One buyable thing: a tier at a billing model and interval."""

    tier: str
    model: str
    interval: str
    cents: int

    @property
    def sku(self) -> str:
        """The identifier used in checkout URLs and in the licence itself."""
        return f"{self.tier}-{self.model}-{self.interval}"

    @property
    def display(self) -> str:
        """The price as a pricing page would print it: "$89/mo", "$1,299"."""
        dollars = self.cents / 100
        amount = f"${dollars:,.0f}" if self.cents % 100 == 0 else f"${dollars:,.2f}"
        suffix = {MONTHLY: "/mo", YEARLY: "/yr"}.get(self.interval, "")
        return f"{amount}{suffix}"


def catalog() -> List[Price]:
    """Every purchasable SKU, in the order a pricing page should show them."""
    out: List[Price] = []
    for key in (SOLO, PRO, AGENCY):
        tier = TIERS[key]
        if tier.subscription_cents:
            monthly, yearly = tier.subscription_cents
            out.append(Price(key, SUBSCRIPTION, MONTHLY, monthly))
            out.append(Price(key, SUBSCRIPTION, YEARLY, yearly))
        if tier.perpetual_cents:
            out.append(Price(key, PERPETUAL, ONCE, tier.perpetual_cents))
    return out


def price_for(sku: str) -> Optional[Price]:
    for price in catalog():
        if price.sku == sku:
            return price
    return None


def renewal_cents(tier_key: str) -> Optional[int]:
    """What another year of updates costs a perpetual owner."""
    tier = TIERS.get(tier_key)
    if tier is None or tier.perpetual_cents is None:
        return None
    return round(tier.perpetual_cents * PERPETUAL_RENEWAL_PERCENT / 100)


# -- tier helpers --------------------------------------------------------

def tier(key: str) -> Tier:
    """The named tier, or the reader tier for anything unrecognised.

    Unknown names come from licences issued by a future version of the server;
    falling back to reader keeps such an install usable and read-only rather
    than crashing it.
    """
    return TIERS.get((key or "").lower(), TIERS[READER])


def rank(key: str) -> int:
    """Position in :data:`TIER_ORDER`; unknown tiers sort as reader."""
    try:
        return TIER_ORDER.index((key or "").lower())
    except ValueError:
        return 0


def at_least(key: str, minimum: str) -> bool:
    return rank(key) >= rank(minimum)


def feature_matrix() -> List[Tuple[str, Dict[str, bool]]]:
    """(feature label, {tier key: included}) rows for a comparison table."""
    rows = []
    for feature in ALL_FEATURES:
        rows.append((FEATURE_LABELS[feature],
                     {key: feature in TIERS[key].features for key in TIER_ORDER}))
    return rows
