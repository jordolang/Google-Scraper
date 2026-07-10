"""Orchestrate every analyzer into a single WebsiteIntel record."""

from __future__ import annotations

from ..models import Business, Finding, WebsiteIntel
from .errors import capture_runtime_errors
from .fetch import fetch_page
from .hosting import detect_hosting
from .pagespeed import PageSpeedResult, run_pagespeed
from .seo import analyze_seo
from .techstack import detect_stack


def _pagespeed_findings(mobile: PageSpeedResult, desktop: PageSpeedResult) -> list[Finding]:
    findings: list[Finding] = []
    perf = mobile.performance

    if perf is not None:
        if perf < 50:
            findings.append(Finding(
                key="pagespeed_mobile_poor", severity="critical",
                headline=f"Mobile PageSpeed {perf}/100 — failing",
                detail=f"LCP {mobile.lcp_seconds}s, TBT {mobile.tbt_ms}ms, CLS {mobile.cls}",
                pitch=f"Google scores your mobile speed a {perf} out of 100 — that's a "
                      f"failing grade. Pull it up on your phone and count: it takes "
                      f"{mobile.lcp_seconds or 'several'} seconds to show anything. Over "
                      f"half of mobile visitors leave before 3 seconds. Every one of "
                      f"those was a roof you didn't get to quote.",
            ))
        elif perf < 80:
            findings.append(Finding(
                key="pagespeed_mobile_mid", severity="warning",
                headline=f"Mobile PageSpeed {perf}/100 — mediocre",
                detail=f"LCP {mobile.lcp_seconds}s",
                pitch=f"Your mobile speed scores {perf}/100 — not broken, but slow "
                      f"enough that you're leaking leads to faster competitors.",
            ))
        else:
            findings.append(Finding(
                key="pagespeed_mobile_good", severity="good",
                headline=f"Mobile PageSpeed {perf}/100 — solid",
                detail=f"LCP {mobile.lcp_seconds}s",
                pitch="Speed's actually good here — don't lead with performance; "
                      "lead with design, conversion, or SEO instead.",
            ))

    if mobile.seo is not None and mobile.seo < 80:
        findings.append(Finding(
            key="pagespeed_seo_low", severity="warning",
            headline=f"Google SEO score {mobile.seo}/100",
            detail="Lighthouse SEO audit below 80.",
            pitch=f"Google's own SEO checker gives the site a {mobile.seo} out of 100 "
                  f"— it's fighting you on visibility before a customer ever sees it.",
        ))

    if desktop.performance is not None and perf is not None and desktop.performance - perf > 25:
        findings.append(Finding(
            key="pagespeed_mobile_gap", severity="warning",
            headline="Big desktop-vs-mobile speed gap",
            detail=f"Desktop {desktop.performance} vs mobile {perf}",
            pitch="It might look fine on your office computer — but your customers "
                  "are on phones, and that's where it falls apart.",
        ))
    return findings


def analyze_website(
    url: str,
    *,
    run_errors: bool = True,
    run_speed: bool = True,
    run_desktop: bool = False,
) -> WebsiteIntel:
    page = fetch_page(url)
    if not page.reachable:
        return WebsiteIntel(
            url=url, reachable=False,
            error=page.error or "unreachable",
            findings=(Finding(
                key="site_unreachable", severity="critical",
                headline="Website won't load",
                detail=page.error,
                pitch="I tried to pull up your site before calling and it wouldn't "
                      "load at all. If I can't reach it, neither can your customers "
                      "— that's a storefront with the doors locked.",
            ),),
        )

    findings: list[Finding] = []
    findings += analyze_seo(page)

    stack, stack_findings = detect_stack(page)
    findings += stack_findings

    hosting, host_findings = detect_hosting(page)
    findings += host_findings

    mobile = desktop = PageSpeedResult(strategy="skipped")
    if run_speed:
        mobile = run_pagespeed(page.final_url or url, "mobile")
        if run_desktop:
            desktop = run_pagespeed(page.final_url or url, "desktop")
        findings += _pagespeed_findings(mobile, desktop)

    if run_errors:
        findings += capture_runtime_errors(page.final_url or url)

    return WebsiteIntel(
        url=page.final_url or url,
        reachable=True,
        tech_stack=stack,
        hosting=hosting,
        pagespeed_mobile=mobile.performance,
        pagespeed_desktop=desktop.performance,
        seo_score=mobile.seo,
        findings=tuple(findings),
    )


def analyze_business(business: Business, **kwargs) -> WebsiteIntel:
    """Analyze a business's site, or synthesize the no-website pitch."""
    if not business.has_website or not business.website:
        return WebsiteIntel(
            url=None, reachable=False,
            findings=(Finding(
                key="no_website_at_all", severity="critical",
                headline="No website at all",
                detail="No real website found in scrape data.",
                pitch=f"Right now when someone Googles a {business.category.lower() or 'contractor'} "
                      f"in {business.city}, you're just a pin on the map with no front "
                      f"door — no story, no photos of your work, no way to win the job "
                      f"before the other guy. Your competitors with a real site are "
                      f"getting that click, and that call. You've got the reviews to "
                      f"back it up; you're just invisible past the map.",
            ),),
        )
    return analyze_website(business.website, **kwargs)
