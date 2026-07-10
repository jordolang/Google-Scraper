"""Infer where a site is hosted (and roughly what it costs them)."""

from __future__ import annotations

from .fetch import PageData
from ..models import Finding

# host label -> (header/cookie/html signatures, monthly cost hint, pitch)
_HOSTS: dict[str, dict] = {
    "Wix (hosted)": {
        "sigs": ["x-wix-", "wixstatic", "wix.com"],
        "cost": "~$17–39/mo, billed forever",
        "pitch": "Wix bundles hosting into a monthly bill you pay forever — and you "
                 "can never take the site with you if you leave.",
    },
    "Squarespace (hosted)": {
        "sigs": ["squarespace"],
        "cost": "~$16–49/mo, billed forever",
        "pitch": "Squarespace hosting is locked to their platform — leave and you "
                 "lose the site. It's rent, not ownership.",
    },
    "GoDaddy": {
        "sigs": ["godaddy", "secureserver.net"],
        "cost": "$10–25/mo + constant upsells",
        "pitch": "GoDaddy is famous for nickel-and-diming — SSL, email, backups, "
                 "security all sold as separate add-ons. Most owners are paying for "
                 "a pile of stuff they never use.",
    },
    "Bluehost": {
        "sigs": ["bluehost"],
        "cost": "$10–30/mo (renews higher)",
        "pitch": "Bluehost reels you in cheap then the renewal price jumps. "
                 "Performance is mediocre on their shared plans.",
    },
    "HostGator": {
        "sigs": ["hostgator"],
        "cost": "$10–25/mo (renews higher)",
        "pitch": "HostGator is bargain shared hosting — slow, oversold servers, "
                 "and a renewal-price jump after year one.",
    },
    "Cloudflare (CDN)": {
        "sigs": ["cf-ray", "cloudflare"],
        "cost": "often free tier",
        "pitch": "They're behind Cloudflare — whoever set this up knew a little. "
                 "Worth acknowledging; the lever is what's *behind* the CDN.",
    },
    "AWS / cloud": {
        "sigs": ["x-amz", "amazons3", "cloudfront", "awselb"],
        "cost": "variable, often over-provisioned",
        "pitch": "This is on AWS — capable, but for a local business it's usually "
                 "over-engineered and someone's billing them for capacity they "
                 "never touch.",
    },
    "Vercel/Netlify": {
        "sigs": ["vercel", "netlify"],
        "cost": "often free–$20/mo",
        "pitch": "Modern hosting — whoever built this used current tools.",
    },
}


def detect_hosting(page: PageData) -> tuple[str, list[Finding]]:
    if not page.reachable:
        return "", []

    server = page.headers.get("server", "")
    powered = page.headers.get("x-powered-by", "")
    haystack = " ".join([
        server.lower(), powered.lower(),
        " ".join(page.headers.keys()).lower(),
        " ".join(page.cookies).lower(),
        page.html[:5000].lower(),
    ])

    detected: list[str] = []
    findings: list[Finding] = []
    for host, spec in _HOSTS.items():
        if any(sig in haystack for sig in spec["sigs"]):
            detected.append(host)
            findings.append(Finding(
                key=f"host_{host.split()[0].lower()}",
                severity="info",
                headline=f"Hosting: {host} ({spec['cost']})",
                detail=f"Server header: {server or 'n/a'}; X-Powered-By: {powered or 'n/a'}",
                pitch=spec["pitch"],
            ))

    label = ", ".join(detected) if detected else (server or "Unknown host")
    if not detected and server:
        findings.append(Finding(
            key="host_generic", severity="info",
            headline=f"Hosting server: {server}",
            detail="Could not match a known provider signature.",
            pitch="Ask who hosts this and what they pay — there's almost always a "
                  "monthly bill they've forgotten the details of.",
        ))
    return label, findings
