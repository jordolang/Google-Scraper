"""Call-script content for the Call Scripts tab.

Both halves of the screen come from files the user already owns:

* the step-by-step guide is ``pitch_script.md`` at the project root, split on
  its ``##`` headings, so editing the Markdown edits the app;
* the objection cards are :mod:`salescall.objections`, with their templates
  filled in for whichever business is being called.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from tui.models import Business
from tui.pitch_script import load_pitch_script


@dataclass
class ScriptStep:
    title: str
    body: str


@dataclass
class ObjectionCard:
    label: str
    response: str
    next_action: str
    fallback: str


def script_steps(markdown: Optional[str] = None) -> List[ScriptStep]:
    """Split the pitch script into the numbered steps shown in Call Progress."""
    text = markdown if markdown is not None else load_pitch_script()
    steps: List[ScriptStep] = []
    current: Optional[ScriptStep] = None
    for line in text.splitlines():
        heading = re.match(r"^##\s+(.*)$", line.strip())
        if heading:
            if current is not None:
                steps.append(current)
            title = heading.group(1).strip()
            # Headings are already numbered ("2. Opening"); the UI numbers the
            # list itself, so drop the duplicate prefix.
            title = re.sub(r"^\d+[.)]\s*", "", title)
            current = ScriptStep(title=title, body="")
        elif current is not None:
            current.body += line + "\n"
    if current is not None:
        steps.append(current)
    if not steps:  # a script with no ## headings is still worth showing
        steps = [ScriptStep(title="Script", body=text)]
    for step in steps:
        step.body = step.body.strip()
    return steps


def _trade(category: str) -> str:
    """A speakable trade word from a Maps category ("Roofing contractor")."""
    cleaned = (category or "").strip().lower()
    cleaned = re.sub(r"\b(service|services|contractor|contractors|company|co)\b", "", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned or "local business"


def _city(address: str) -> str:
    parts = [part.strip() for part in (address or "").split(",") if part.strip()]
    # "1234 Main St, Columbus, OH 43215" -> "Columbus"
    return parts[1] if len(parts) >= 2 else (parts[0] if parts else "your area")


def call_tokens(business: Optional[Business], pricing: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """The ``{name}`` / ``{trade}`` / ``{launchpad}`` values for one call."""
    business = business or Business()
    prices = dict(pricing or {})
    if not prices:
        try:
            import pricing_store

            prices = pricing_store.prices_for("general")
        except Exception:  # pragma: no cover - pricing.json is optional
            prices = {}
    return {
        "name": business.name or "there",
        "city": _city(business.address),
        "trade": _trade(business.category),
        "launchpad": prices.get("launchpad", "$499"),
        "pro": prices.get("professional", "Starting at $1,499+"),
        "followup": "Tuesday morning",
        "season_target": "next season",
        "proof": _proof(business),
    }


def _proof(business: Business) -> str:
    """A short, true clause about this business, used inside objection replies."""
    if not business.website:
        return "you have no website at all, so every search for you ends on someone else's page"
    if business.rating and business.reviews_count:
        return (
            f"you are sitting on {business.reviews_count} reviews at "
            f"{business.rating} stars and none of that shows up where buyers look"
        )
    return "the site is not doing the one job it has, which is booking work"


def fill(text: str, tokens: Dict[str, str]) -> str:
    """Fill a template, leaving unknown placeholders alone rather than raising."""
    try:
        return text.format(**tokens)
    except (KeyError, IndexError, ValueError):
        out = text
        for key, value in tokens.items():
            out = out.replace("{" + key + "}", str(value))
        return out


def objection_cards(business: Optional[Business] = None,
                    pricing: Optional[Dict[str, str]] = None) -> List[ObjectionCard]:
    """Every objection handler, personalised for this business."""
    try:
        from salescall.objections import OBJECTIONS
    except Exception:  # pragma: no cover - salescall is optional at runtime
        return []
    tokens = call_tokens(business, pricing)
    return [
        ObjectionCard(
            label=handler.label,
            response=fill(handler.response, tokens),
            next_action=fill(handler.next_action, tokens),
            fallback=fill(handler.fallback, tokens),
        )
        for handler in OBJECTIONS
    ]
