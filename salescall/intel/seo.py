"""On-page SEO analysis. Every finding includes a spoken sales translation."""

from __future__ import annotations

from bs4 import BeautifulSoup

from ..models import Finding
from .fetch import PageData


def analyze_seo(page: PageData) -> list[Finding]:
    if not page.reachable or not page.html:
        return []

    soup = BeautifulSoup(page.html, "lxml")
    findings: list[Finding] = []

    # HTTPS / security padlock — a customer-visible trust signal.
    if not page.https:
        findings.append(Finding(
            key="no_https",
            severity="critical",
            headline="No HTTPS — 'Not Secure' warning",
            detail="Site served over plain HTTP.",
            pitch="Pull your site up in Chrome — see that 'Not Secure' tag by the "
                  "address bar? Every customer sees that. It quietly tells people "
                  "you're not safe to do business with. That alone scares off leads.",
        ))

    # Title tag.
    title = (soup.title.string or "").strip() if soup.title else ""
    if not title:
        findings.append(Finding(
            key="no_title", severity="critical", headline="Missing page title",
            detail="No <title> tag.",
            pitch="Google literally has no headline to show for you in search "
                  "results — you're handing clicks to your competitors.",
        ))
    elif len(title) > 65 or len(title) < 15:
        findings.append(Finding(
            key="title_length", severity="warning",
            headline=f"Title tag length off ({len(title)} chars)",
            detail=f"Title: {title[:80]}",
            pitch="Your Google headline is getting cut off or is too thin — it's "
                  "not pulling its weight where customers actually decide to click.",
        ))

    # Meta description.
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if not meta_desc or not meta_desc.get("content", "").strip():
        findings.append(Finding(
            key="no_meta_desc", severity="warning",
            headline="Missing meta description",
            detail="No meta description tag.",
            pitch="The blurb under your name in Google search? It's blank or "
                  "auto-scraped. We control that and turn it into a reason to call you.",
        ))

    # H1 headings.
    h1s = soup.find_all("h1")
    if len(h1s) == 0:
        findings.append(Finding(
            key="no_h1", severity="warning", headline="No H1 heading",
            detail="Page has no <h1>.",
            pitch="Google reads the H1 to understand what you do — yours is "
                  "missing, so it's guessing. We make it unmistakable.",
        ))
    elif len(h1s) > 1:
        findings.append(Finding(
            key="multi_h1", severity="info", headline=f"{len(h1s)} H1 tags",
            detail="Multiple H1s dilute keyword focus.", pitch="",
        ))

    # Mobile viewport.
    if not soup.find("meta", attrs={"name": "viewport"}):
        findings.append(Finding(
            key="no_viewport", severity="critical",
            headline="Not mobile-optimized (no viewport)",
            detail="No responsive viewport meta tag.",
            pitch="Over 60% of roofing searches happen on a phone. Without mobile "
                  "setup, your site looks broken on a phone — pinch-to-zoom, tiny "
                  "text. That customer bounces straight to the next guy.",
        ))

    # Structured data (schema.org) — drives rich results / local SEO.
    has_schema = bool(soup.find_all("script", attrs={"type": "application/ld+json"})) \
        or "itemtype" in page.html.lower()
    if not has_schema:
        findings.append(Finding(
            key="no_schema", severity="warning", headline="No structured data",
            detail="No schema.org / JSON-LD markup.",
            pitch="You're missing the markup Google uses to show your star "
                  "rating, hours, and service area right in search — that's free "
                  "real estate your competitors may already own.",
        ))

    # Open Graph (how links look when shared).
    if not soup.find("meta", attrs={"property": "og:title"}):
        findings.append(Finding(
            key="no_og", severity="info", headline="No Open Graph tags",
            detail="Links shared on Facebook/texts render with no preview.",
            pitch="When someone shares your site in a text or on Facebook, it "
                  "shows up as a naked link with no image — looks sketchy.",
        ))

    # Image alt coverage.
    imgs = soup.find_all("img")
    if imgs:
        missing_alt = sum(1 for i in imgs if not i.get("alt", "").strip())
        if missing_alt / len(imgs) > 0.5:
            findings.append(Finding(
                key="img_alt", severity="info",
                headline=f"{missing_alt}/{len(imgs)} images missing alt text",
                detail="Hurts accessibility and image SEO.", pitch="",
            ))

    # Crawl basics.
    if not page.robots_ok:
        findings.append(Finding(
            key="no_robots", severity="info", headline="No robots.txt",
            detail="No robots.txt found.", pitch="",
        ))
    if not page.sitemap_ok:
        findings.append(Finding(
            key="no_sitemap", severity="warning", headline="No XML sitemap",
            detail="No sitemap.xml found.",
            pitch="Google has no map of your pages, so new content can take weeks "
                  "to show up — or never gets indexed at all.",
        ))

    # Word count — thin content.
    text_len = len(soup.get_text(separator=" ", strip=True).split())
    if text_len < 200:
        findings.append(Finding(
            key="thin_content", severity="warning",
            headline=f"Thin content (~{text_len} words)",
            detail="Very little indexable text.",
            pitch="There's barely any text for Google to rank — a page this thin "
                  "won't ever compete for 'roofer near me' style searches.",
        ))

    return findings
