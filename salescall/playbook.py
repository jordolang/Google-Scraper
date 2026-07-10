"""Build a personalized, staged call script for a single business.

A Playbook is what the cockpit renders live: a pre-call brief, ordered stages
(open → discover → pitch → close) where each step tells the caller what to
SAY, what to DO, when to PAUSE/LISTEN, what to ANTICIPATE, and the OPTIONS to
branch to — plus the full objection library, personalized to this business.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import QueueEntry, Tier, WebsiteIntel
from .objections import OBJECTIONS, ObjectionHandler

# Pricing (mirrors email_config.py).
LAUNCHPAD = "$499"
PRO = "$1,499+"

# Simple seasonal defaults — surface these in config later if needed.
SEASON = "the spring rush"
SEASON_TARGET = "spring"
FOLLOWUP = "later this week"


@dataclass(frozen=True)
class Step:
    say: str = ""                      # verbatim dialogue for the caller
    do: str = ""                       # instruction / stage direction
    cue: str = ""                      # PAUSE / LISTEN / IF YES→ etc.
    anticipate: tuple[str, ...] = ()   # likely prospect responses
    options: tuple[str, ...] = ()      # branch choices for the caller


@dataclass(frozen=True)
class Stage:
    name: str
    steps: tuple[Step, ...]


@dataclass(frozen=True)
class Playbook:
    business_name: str
    tier: Tier
    brief: dict
    stages: tuple[Stage, ...]
    objections: tuple[ObjectionHandler, ...]
    talking_points: tuple[str, ...]


def _trade(category: str) -> str:
    cat = (category or "contractor").lower()
    cat = re.sub(r"\b(service|services|contractor|company|llc|inc)\b", "", cat).strip()
    return cat or "contracting"


_SEV_ORDER = {"critical": 0, "warning": 1, "good": 2, "info": 3}


def _spoken_findings(entry: QueueEntry) -> list:
    """Pitch-bearing findings from website intel AND local SEO, worst first."""
    findings = []
    if entry.intel:
        findings += list(entry.intel.findings)
    if entry.local:
        findings += list(entry.local.findings)
    spoken = [f for f in findings if f.pitch]
    spoken.sort(key=lambda f: _SEV_ORDER.get(f.severity, 9))
    return spoken


def _site_hook(entry: QueueEntry) -> str:
    """The single strongest, most-damning thing to open with (full pitch)."""
    spoken = _spoken_findings(entry)
    if spoken:
        return spoken[0].pitch
    # No findings cached yet (e.g. intel not run) — safe, non-specific opener.
    return ("I went through how your business shows up online and there are a "
            "couple of spots that are quietly costing you calls.")


def _proof_clause(entry: QueueEntry) -> str:
    """A SHORT, grammatically clean data clause for embedding mid-sentence.

    Built from structured data (not finding prose) so it slots into objection
    responses as a clause instead of a whole paragraph. Tier-aware: never
    asserts something that contradicts the business's actual web presence.
    """
    b = entry.business
    local = entry.local
    intel = entry.intel

    if local and local.display_size > 1 and local.display_rank > local.display_size // 2:
        src = "on Google" if local.is_real else "locally"
        return (f"you're sitting #{local.display_rank} of {local.display_size} "
                f"{src} for '{local.field.lower()}' right now")
    if intel and intel.pagespeed_mobile is not None and intel.pagespeed_mobile < 50:
        return (f"your site scores a {intel.pagespeed_mobile} out of 100 on "
                f"Google's mobile speed test")
    if not b.has_website:
        if local:
            above = sum(1 for c in local.competitors_above if c.has_website)
            if above:
                verb = "has" if above == 1 else "have"
                n = "one" if above == 1 else str(above)
                return (f"{n} of the outfits ranking above you {verb} a real site "
                        f"and you've got nothing")
        return "you've got no website while your competitors are showing up above you"
    if local and local.display_rank == 1:
        return (f"you're #1 locally for '{local.field.lower()}' but the site behind "
                f"that ranking isn't built to convert it")
    # Safe last resort — true for virtually everyone, asserts nothing false.
    return ("the way customers find and judge you online has gaps that are costing "
            "you jobs")


def _fill(text: str, tokens: dict) -> str:
    try:
        return text.format(**tokens)
    except (KeyError, IndexError):
        return text


def _build_brief(entry: QueueEntry, tokens: dict) -> dict:
    b = entry.business
    intel = entry.intel
    local = entry.local
    points = [f.pitch for f in _spoken_findings(entry)
              if f.severity in ("critical", "warning")][:5]
    strengths = [f.headline for f in (intel.strengths if intel else ())][:3]
    local_summary = ""
    competitors_above = []
    if local and local.display_size > 1:
        tag = "Google rank" if local.is_real else "est. rank"
        local_summary = f"{tag} #{local.display_rank} of {local.display_size} in {local.field}"
        competitors_above = [
            f"#{c.rank} {c.name}"
            + (" (has site)" if c.has_website else " (no site)")
            for c in local.competitors_above[:3]
        ]
    return {
        "name": b.name,
        "category": b.category or "—",
        "trade": tokens["trade"],
        "city": b.city,
        "phone": b.phone or "NO PHONE ON FILE",
        "extra_phones": [p for p in b.raw_phones[1:]],
        "rating": f"{b.rating}★" if b.rating else "no rating",
        "reviews": b.reviews_count or "?",
        "website": b.website or "NONE",
        "has_email": b.has_email,
        "tier": int(entry.tier),
        "minutes": entry.suggested_minutes,
        "stack": ", ".join(intel.tech_stack) if intel and intel.tech_stack else "—",
        "hosting": intel.hosting if intel else "—",
        "pagespeed_mobile": intel.pagespeed_mobile if intel else None,
        "seo_score": intel.seo_score if intel else None,
        "top_points": points,
        "strengths": strengths,
        "local_summary": local_summary,
        "local_competitors_above": competitors_above,
        "local_distance": local.distance_from_origin if local else None,
        "local_percentile": local.percentile if local else None,
        "local_nearest": (
            f"{local.nearest_competitor.name} ({local.nearest_competitor.distance_miles} mi)"
            if local and local.nearest_competitor else ""
        ),
    }


def _open_stage(entry: QueueEntry, tokens: dict) -> Stage:
    b = entry.business
    no_site = not b.has_website
    greeting = (
        f"Hi — is this {tokens['name']}? My name's Jordan Lang, I run a web "
        f"development business right here in and around {b.city}. Do you have just a "
        f"minute? I promise I'm not calling to waste your time."
    )
    framing = (
        f"So here's what I do — I keep an eye on the top businesses around {b.city} in "
        f"the busiest local trades, and when I think I can actually help one of them, I "
        f"reach out — kind of like I'm doing right now. "
    )
    if no_site:
        observation = (
            "When I looked you up, I noticed you don't have a website yet. Now, I'm not "
            "interested in selling you a site if your business doesn't need one — but I "
            "am interested in getting you as much new business as you can handle, and "
            "honestly, most of us can all use a leg up from time to time. If you've got "
            "just a couple of minutes, can I tell you what I think I could do for you?"
        )
        anticipate = ("Sure, go ahead",
                      "We get all our work by word of mouth",
                      "We've been meaning to get one")
        options = ("Yes → DISCOVER",
                   "'Word of mouth' → 'That's great — a site just makes every referral "
                   "check you out and call. It builds on what you've already got.'",
                   "Hesitant → 'Even one minute — if it's not for you, I'll let you go.'")
    else:
        observation = (
            f"When I looked you up, I saw you've already got a site — {b.website}. I'm "
            f"not here to tell you to throw it out. What I am interested in is getting "
            f"you as much new business as you can handle, and honestly, most of us can "
            f"all use a leg up from time to time. If you've got just a couple of "
            f"minutes, can I share what I think I could do for you?"
        )
        anticipate = ("Sure, what've you got?",
                      "We already have a website",
                      "A buddy / family built it")
        options = ("Yes → DISCOVER",
                   "Defensive → Objections: 'Already have a website'",
                   "Hesitant → 'Even one minute — if it's not for you, I'll let you go.'")
    hook = Step(
        say=framing + observation,
        do="The heart of the open — humble, no pressure. You're offering, not selling.",
        cue="PAUSE — give them room to say yes. Then let them talk.",
        anticipate=anticipate,
        options=options,
    )
    return Stage("OPEN", (Step(
        say=greeting,
        do="Warm, unhurried open. Make sure you've got the owner / decision-maker.",
        cue="LISTEN — if it's not the owner, get a name and a good time to call back. "
            "Smile; they can hear it.",
        anticipate=("Speaking / this is him", "He's not in right now", "What's this about?"),
        options=("Not the owner → log callback ('c')",
                 "Gatekeeper → 'When's the best time to catch the owner?'"),
    ), hook))


def _discover_stage(entry: QueueEntry, tokens: dict) -> Stage:
    return Stage("DISCOVER", (
        Step(
            say=(f"Before I go on — where's most of your work coming from these days? "
                 f"Referrals, Google, Facebook? I just want to make sure what I'm about "
                 f"to say actually fits how you do business."),
            do="Ask, then genuinely listen. You're learning about them, not setting a trap.",
            cue="LISTEN — jot down their exact words. You'll build on them, not weaponize them.",
            anticipate=("Mostly word of mouth", "A little of everything", "Honestly, not sure"),
            options=("They name a channel → tie a site to making that channel work harder",
                     "'Not sure' → that's normal; gently show what they may be missing"),
        ),
        Step(
            say=("Here's the thing — the folks searching for work like yours online "
                 "right now are the ones ready to hire today. If I could turn even two "
                 "or three of those a month into real jobs for you, that adds up to a "
                 "good year. That's really all I do. Sound alright if I keep going?"),
            do="Frame it as helping, not pressure. Get a soft yes.",
            cue="PAUSE — wait for the nod. No need to rush to price.",
            anticipate=("Yeah, go ahead", "What's it run me?", "We're already pretty busy"),
            options=("'What's it cost?' → Objections: 'Too expensive' (value first, then range)",
                     "'Already busy' → 'Then a site lets you pick the better jobs and "
                     "raise your prices, not just your hours.'"),
        ),
    ))


def _pitch_stage(entry: QueueEntry, tokens: dict) -> Stage:
    points = [p for p in tokens["top_points"] if p][:1]
    steps = [
        Step(
            say=("I've been doing this for going on 25 years now, and I'll be straight "
                 "with you — I can put more in front of you than any ad budget or "
                 "marketing platform will, and without you pouring money into something "
                 "that runs a month and then makes you renew. I build you something you "
                 "actually own. It's 100% custom-built for your business, a one-time "
                 "thing — no monthly payments, no plans to keep paying for."),
            do="Sell ownership and trust, not a feature list. Warm and sure of yourself.",
            cue="Don't lead with a price. If they ask, go to the 'Too expensive' handler.",
            anticipate=("What's it cost?", "What does it include?", "How long does it take?"),
            options=("Asks price → Objections: 'Too expensive' (value first, then range)",
                     "Interested → go to CLOSE"),
        ),
        Step(
            say=("And there's something else — being able to tell somebody 'go check out "
                 "my website' doesn't just bring you business, it changes how you feel "
                 "about your own shop. You've built something worth pointing people to. "
                 "You order it, I design it inside about 24 hours, and you start showing "
                 "up on Google right after."),
            do="Paint the picture: pride and momentum. This is what sets up the close.",
            cue="Watch for the nod — this is where they start picturing it.",
            anticipate=("That fast?", "Really, 24 hours?", "And that's it?"),
            options=("Excited → go to CLOSE",
                     "Skeptical → 'Let me show you a few I've built — judge for yourself.'"),
        ),
    ]
    for p in points:
        steps.append(Step(
            say=p,
            do="Offer ONE thing you noticed as a friendly heads-up — not a lecture.",
            cue="Mention it once, gently, then let them respond. Don't pile on.",
            anticipate=("I didn't know that", "My guy never mentioned that", "Is that really a problem?"),
            options=("Skeptical → 'I'll send the full rundown so you can see it yourself.'",),
        ))
    return Stage("PITCH", tuple(steps))


def _close_stage(entry: QueueEntry, tokens: dict) -> Stage:
    return Stage("CLOSE", (
        Step(
            say=("So what do you think? I can send over a few of the sites I've built so "
                 "you can see the quality for yourself — or, if you're ready, I can get "
                 "a simple agreement over to you and start on yours today. Which sounds "
                 "better to you?"),
            do="Offer the two doors — see samples, or get started. Both move forward.",
            cue="Ask, then give them space to choose. Keep the pressure out of your voice.",
            anticipate=("Show me some examples", "Let's do it", "Let me think about it"),
            options=("Wants samples → send portfolio, set a follow-up time",
                     "Ready → capture email, send the agreement, press 'm'",
                     "'Think about it' → Objections: 'Need to think'"),
        ),
        Step(
            say=(f"Perfect — what's the best email to send that to? And I've got you at "
                 f"{entry.business.phone}; is that still the best number to reach you? "
                 f"Let me get this over to you right now while we're on the line."),
            do="Capture email, confirm the number. Keep it easy and friendly.",
            cue="Repeat the email back so it's right. Then thank them — warmly.",
            anticipate=("Here's my email", "Use this other number", "I'll watch for it"),
            options=("Got it → press 'm' → mark status",
                     "Won't give email → 'No problem, I'll text you the link instead.'"),
        ),
    ))


def _spoken_name(name: str) -> str:
    """Name as you'd say it mid-sentence — drop a trailing abbreviation period
    (e.g. 'K E Dittmar Company Inc.') so it never collides with sentence punctuation."""
    return name.rstrip().rstrip(".") if name else name


def build_playbook(entry: QueueEntry) -> Playbook:
    b = entry.business
    rating_phrase = (
        f"a strong {b.rating}-star reputation" if b.rating and b.rating >= 4.5
        else (f"a {b.rating}-star rating" if b.rating else "good reviews")
    )
    tokens = {
        "name": _spoken_name(b.name),
        "city": b.city,
        "trade": _trade(b.category),
        "launchpad": LAUNCHPAD,
        "pro": PRO,
        "site_hook": _site_hook(entry),
        "proof": _proof_clause(entry),
        "followup": FOLLOWUP,
        "season": SEASON,
        "season_target": SEASON_TARGET,
        "rating_phrase": rating_phrase,
        "top_points": [f.pitch for f in _spoken_findings(entry)
                       if f.severity in ("critical", "warning")],
    }

    stages = (
        _open_stage(entry, tokens),
        _discover_stage(entry, tokens),
        _pitch_stage(entry, tokens),
        _close_stage(entry, tokens),
    )

    objections = tuple(
        ObjectionHandler(
            label=o.label,
            triggers=o.triggers,
            response=_fill(o.response, tokens),
            next_action=_fill(o.next_action, tokens),
            fallback=_fill(o.fallback, tokens),
        )
        for o in OBJECTIONS
    )

    return Playbook(
        business_name=b.name,
        tier=entry.tier,
        brief=_build_brief(entry, tokens),
        stages=stages,
        objections=objections,
        talking_points=tuple(tokens["top_points"][:5]),
    )
