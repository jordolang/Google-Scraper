"""Website intelligence engine.

Given a business website, produce a WebsiteIntel record: tech stack, hosting,
PageSpeed/Core Web Vitals, SEO findings, runtime errors — each finding carrying
a ready-to-say sales translation.
"""

from .engine import analyze_website, analyze_business

__all__ = ["analyze_website", "analyze_business"]
