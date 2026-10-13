"""Check a sending domain's DNS for the records inboxes look for.

Gmail, Outlook and Yahoo now check three things before they trust mail from a
domain:

* **SPF** — a TXT record listing which servers may send for the domain.
* **DKIM** — a public key at ``<selector>._domainkey.<domain>`` the server
  signs each message with.
* **DMARC** — a TXT record at ``_dmarc.<domain>`` saying what to do when
  either check fails.

Missing any one of them is the most common reason cold email lands in spam.
:func:`check_domain` looks all three up (plus MX) and says, in plain words,
what is set, what is missing and how to fix it. Lookups go over DNS-over-HTTPS
with ``requests`` so the app needs no DNS library::

    for check in check_domain("jlang.dev", smtp_server="smtp.mail.me.com"):
        print(check.status, check.name, check.detail)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

DOH_URL = "https://dns.google/resolve"

PASS, WARN, FAIL = "pass", "warn", "fail"

#: What each sending service needs in SPF, and the DKIM selectors it signs with.
PROVIDERS: Dict[str, dict] = {
    "google": {
        "label": "Google Workspace / Gmail",
        "hosts": ("smtp.gmail.com", "google"),
        "spf": "include:_spf.google.com",
        "selectors": ("google",),
        "dkim_help": "Google Admin → Apps → Gmail → Authenticate email → Generate new record",
    },
    "icloud": {
        "label": "iCloud Mail",
        "hosts": ("smtp.mail.me.com", "icloud", "me.com"),
        "spf": "include:icloud.com",
        "selectors": ("sig1",),
        "dkim_help": "iCloud.com → Settings → Custom Email Domain → your domain shows the sig1 record",
    },
    "outlook": {
        "label": "Microsoft 365 / Outlook",
        "hosts": ("outlook", "office365", "smtp-mail.outlook.com"),
        "spf": "include:spf.protection.outlook.com",
        "selectors": ("selector1", "selector2"),
        "dkim_help": "Microsoft Defender portal → Email authentication settings → DKIM",
    },
    "yahoo": {
        "label": "Yahoo Mail",
        "hosts": ("yahoo",),
        "spf": "include:_spf.mail.yahoo.com",
        "selectors": ("s1024", "s2048"),
        "dkim_help": "Yahoo signs its own addresses; use a custom domain provider for your own.",
    },
    "resend": {
        "label": "Resend",
        "hosts": ("resend",),
        # Resend sends from a "send." subdomain with its own SPF record.
        "spf": "include:amazonses.com",
        "selectors": ("resend",),
        "dkim_help": "resend.com → Domains → your domain lists the exact records to add",
    },
}

#: Tried when the provider is unknown.
COMMON_SELECTORS = ("google", "sig1", "selector1", "selector2", "default", "k1",
                    "s1", "s2", "mail", "dkim", "resend", "mandrill", "smtp")

#: Free mailbox domains: their owners publish the records, and you cannot.
FREEMAIL = ("gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
            "icloud.com", "me.com", "mac.com", "live.com", "msn.com")


@dataclass
class Check:
    name: str
    status: str  # pass | warn | fail
    detail: str
    fix: str = ""


Resolver = Callable[[str, str], List[str]]


def doh_lookup(name: str, record_type: str) -> List[str]:
    """TXT/MX answers for ``name`` from Google's DNS-over-HTTPS resolver."""
    import requests

    response = requests.get(DOH_URL, params={"name": name, "type": record_type},
                            timeout=10)
    response.raise_for_status()
    answers = response.json().get("Answer") or []
    wanted = {"TXT": 16, "MX": 15, "CNAME": 5}.get(record_type)
    values = []
    for answer in answers:
        if wanted and answer.get("type") not in (wanted, 5):
            continue
        data = str(answer.get("data", ""))
        # TXT records arrive quoted and sometimes split into chunks.
        values.append(data.replace('" "', "").strip('"'))
    return values


def provider_for(smtp_server: str = "", send_via: str = "smtp",
                 mx: Sequence[str] = ()) -> Optional[str]:
    """Which service sends this mail, from the SMTP host or else the MX records."""
    if send_via == "resend":
        return "resend"
    haystacks = [smtp_server.lower()] + [m.lower() for m in mx]
    for key, provider in PROVIDERS.items():
        for haystack in haystacks:
            if haystack and any(host in haystack for host in provider["hosts"]):
                return key
    return None


def check_domain(domain: str, *, smtp_server: str = "", send_via: str = "smtp",
                 resolve: Resolver = doh_lookup) -> List[Check]:
    """SPF, DKIM, DMARC and MX for ``domain``, each with a verdict and a fix."""
    domain = (domain or "").strip().lower()
    if "@" in domain:
        domain = domain.rsplit("@", 1)[-1]
    if not domain:
        return [Check("Domain", FAIL, "No From address to check.",
                      "Enter your From email in Settings first.")]
    if domain in FREEMAIL:
        return [Check(
            "Domain", WARN,
            f"{domain} is a free mailbox, so its records belong to its owner and "
            "already pass. Free mailboxes are rate-limited and often filtered for "
            "cold outreach, though.",
            "Send from an address on your own domain (for example you@jlang.dev).")]

    checks: List[Check] = []
    try:
        mx = resolve(domain, "MX")
    except Exception as exc:  # noqa: BLE001 - network or resolver failure
        return [Check("DNS", FAIL, f"Could not look the domain up: {exc}",
                      "Check your internet connection and try again.")]
    provider_key = provider_for(smtp_server, send_via, mx)
    provider = PROVIDERS.get(provider_key or "", {})
    label = provider.get("label", "your email provider")

    if mx:
        checks.append(Check("MX", PASS, f"Mail for {domain} goes to "
                            + ", ".join(sorted({m.split()[-1].rstrip('.') for m in mx}))))
    else:
        checks.append(Check("MX", WARN, f"{domain} has no MX record, so replies "
                            "to it cannot be delivered.",
                            "Add the MX records your email provider gives you."))

    # -- SPF ---------------------------------------------------------------
    spf_host = f"send.{domain}" if provider_key == "resend" else domain
    spf = [t for t in _safe(resolve, spf_host, "TXT") if t.lower().startswith("v=spf1")]
    needed = provider.get("spf", "")
    if len(spf) > 1:
        checks.append(Check("SPF", FAIL, f"{spf_host} has {len(spf)} SPF records; "
                            "receivers treat that as no SPF at all.",
                            "Merge them into one TXT record that starts with v=spf1."))
    elif not spf:
        suggestion = f"v=spf1 {needed} ~all" if needed else "v=spf1 include:<your provider> ~all"
        checks.append(Check("SPF", FAIL, f"No SPF record on {spf_host}.",
                            f"Add a TXT record on {spf_host}: {suggestion}"))
    elif needed and needed.lower() not in spf[0].lower():
        checks.append(Check("SPF", WARN, f"SPF exists but does not list {label}: {spf[0]}",
                            f"Add {needed} before the final ~all or -all."))
    else:
        checks.append(Check("SPF", PASS, spf[0]))

    # -- DKIM --------------------------------------------------------------
    selectors = provider.get("selectors") or COMMON_SELECTORS
    found = None
    for selector in selectors:
        records = _safe(resolve, f"{selector}._domainkey.{domain}", "TXT")
        if any("p=" in r for r in records) or _safe(
                resolve, f"{selector}._domainkey.{domain}", "CNAME"):
            found = selector
            break
    if found:
        checks.append(Check("DKIM", PASS, f"Signing key found at {found}._domainkey.{domain}"))
    else:
        help_text = provider.get("dkim_help", "Your email provider's admin console "
                                 "gives you a DKIM record to add.")
        checks.append(Check("DKIM", FAIL if provider else WARN,
                            f"No DKIM key found for {label}"
                            + ("" if provider else " (checked the common selectors)") + ".",
                            help_text))

    # -- DMARC -------------------------------------------------------------
    dmarc = [t for t in _safe(resolve, f"_dmarc.{domain}", "TXT")
             if t.lower().startswith("v=dmarc1")]
    if not dmarc:
        checks.append(Check(
            "DMARC", FAIL, f"No DMARC record at _dmarc.{domain}.",
            f"Add a TXT record on _dmarc.{domain}: v=DMARC1; p=none; "
            f"rua=mailto:dmarc@{domain}  (start at p=none, tighten later)"))
    else:
        policy = _tag(dmarc[0], "p")
        status = PASS if policy in ("quarantine", "reject", "none") else WARN
        note = " Monitoring only; fine to start with." if policy == "none" else ""
        checks.append(Check("DMARC", status, dmarc[0] + note))
    return checks


def summary(checks: Sequence[Check]) -> str:
    """One line: how ready this domain is to send."""
    failing = [c.name for c in checks if c.status == FAIL]
    warning = [c.name for c in checks if c.status == WARN]
    if failing:
        return f"Fix before sending: {', '.join(failing)}."
    if warning:
        return f"Good to send. Worth a look: {', '.join(warning)}."
    return "All set: SPF, DKIM and DMARC are in place."


def _safe(resolve: Resolver, name: str, record_type: str) -> List[str]:
    try:
        return resolve(name, record_type)
    except Exception:  # noqa: BLE001 - one missing record is not an outage
        return []


def _tag(record: str, tag: str) -> str:
    for part in record.split(";"):
        key, _, value = part.strip().partition("=")
        if key.strip().lower() == tag:
            return value.strip().lower()
    return ""
