"""Fingerprint the platform a site is built on, with a sales angle for each.

Each known platform maps to a Finding whose pitch names what the owner
probably *likes* about it and the pain point we lever against.
"""

from __future__ import annotations

from .fetch import PageData
from ..models import Finding

# platform -> (signatures, severity, headline, pitch)
# Signatures are matched case-insensitively against html + headers + cookies.
_SIGNATURES: dict[str, dict] = {
    "Wix": {
        "patterns": ["wix.com", "_wixcss", "wixstatic.com", "x-wix-", "static.parastorage.com"],
        "severity": "warning",
        "headline": "Built on Wix",
        "pitch": "You're on Wix — and I get the appeal, it was quick to stand up "
                 "and you don't touch code. But here's the trap: you're renting "
                 "it. You can never move that site, Wix caps how fast it loads and "
                 "how high you rank, and you're paying every month forever for a "
                 "site you'll never own. You've outgrown the training wheels.",
    },
    "Squarespace": {
        "patterns": ["squarespace.com", "static1.squarespace", "sqs_", "this.squarespace"],
        "severity": "warning",
        "headline": "Built on Squarespace",
        "pitch": "Squarespace looks clean — that's the part you probably like. But "
                 "it boxes you into their templates, the SEO controls are shallow, "
                 "and you're locked into their monthly bill with no way to take "
                 "your site with you. Pretty, but a rental.",
    },
    "GoDaddy Website Builder": {
        "patterns": ["godaddy.com/websites", "gdwebsites", "websitebuilder.godaddy"],
        "severity": "critical",
        "headline": "GoDaddy Website Builder",
        "pitch": "This is the GoDaddy drag-and-drop builder — honestly the weakest "
                 "of the bunch. It's slow, it's cookie-cutter, and you're likely "
                 "paying GoDaddy for a stack of add-ons you never use. You're "
                 "overpaying for underperforming.",
    },
    "Weebly": {
        "patterns": ["weebly.com", "weeblysite", "editmysite.com"],
        "severity": "warning",
        "headline": "Built on Weebly",
        "pitch": "Weebly is basic and getting phased out by its own owner. It's "
                 "fine as a starter, but it's a dead-end platform now — no real "
                 "SEO muscle and limited support going forward.",
    },
    "WordPress": {
        "patterns": ["wp-content", "wp-includes", "/wp-json", "wordpress"],
        "severity": "info",
        "headline": "Built on WordPress",
        "pitch": "WordPress is solid — but it's only as good as who built and "
                 "maintains it. These usually rot: outdated plugins, security "
                 "holes, slow load times, and a $30/mo plugin pile nobody manages. "
                 "I'll tell you exactly what shape yours is in.",
    },
    "Shopify": {
        "patterns": ["cdn.shopify.com", "shopify", "myshopify.com"],
        "severity": "info",
        "headline": "Built on Shopify",
        "pitch": "Shopify's great for selling products, but it's overkill and "
                 "pricey for a service business — you're paying for a store engine "
                 "you don't need.",
    },
    "Webflow": {
        "patterns": ["webflow.io", "assets.website-files.com", "wf-"],
        "severity": "info",
        "headline": "Built on Webflow",
        "pitch": "Webflow's a designer tool — looks modern, but it gets expensive "
                 "and most owners can't update it themselves without paying their "
                 "designer every time.",
    },
    "Duda": {
        "patterns": ["dudamobile", "duda.co", "_duda_"],
        "severity": "warning",
        "headline": "Built on Duda",
        "pitch": "Duda is usually resold by a marketing agency at a big markup — "
                 "you may be paying $150–300/mo for a template site. I can build "
                 "you something you own outright for less over time.",
    },
    "Joomla": {
        "patterns": ["joomla", "/components/com_"],
        "severity": "warning",
        "headline": "Built on Joomla (legacy)",
        "pitch": "Joomla is legacy tech — most of the web left it years ago. It's "
                 "hard to maintain and a security liability at this point.",
    },
    "Drupal": {
        "patterns": ["drupal", "sites/default/files", "x-drupal"],
        "severity": "info",
        "headline": "Built on Drupal",
        "pitch": "Drupal is heavy enterprise tech — almost certainly more than a "
                 "local business needs, and expensive to keep updated.",
    },
}

# Modern custom-build signatures (a positive signal, not a sales lever).
_MODERN = {
    "React": ["react", "__next", "_next/static"],
    "Next.js": ["__next_data__", "/_next/"],
    "Vue": ["vue.js", "__vue__", "data-v-"],
}


def detect_stack(page: PageData) -> tuple[tuple[str, ...], list[Finding]]:
    if not page.reachable:
        return (), []

    haystack = " ".join([
        page.html.lower(),
        " ".join(f"{k}:{v}" for k, v in page.headers.items()).lower(),
        " ".join(page.cookies).lower(),
    ])

    detected: list[str] = []
    findings: list[Finding] = []

    for platform, spec in _SIGNATURES.items():
        if any(sig in haystack for sig in spec["patterns"]):
            detected.append(platform)
            findings.append(Finding(
                key=f"stack_{platform.lower().replace(' ', '_')}",
                severity=spec["severity"],
                headline=spec["headline"],
                detail=f"Platform fingerprint matched: {platform}",
                pitch=spec["pitch"],
            ))

    for tech, sigs in _MODERN.items():
        if any(sig in haystack for sig in sigs) and tech not in detected:
            detected.append(tech)

    if not detected:
        findings.append(Finding(
            key="stack_unknown", severity="info",
            headline="Custom / unrecognized build",
            detail="No common builder fingerprint matched.",
            pitch="This looks hand-built or on an obscure platform — worth asking "
                  "who maintains it and what they pay, because custom sites that "
                  "go unmaintained are the riskiest of all.",
        ))

    return tuple(detected), findings
