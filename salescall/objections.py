"""Objection-handling knowledge base.

Each handler gives the caller: what the prospect likely *said*, what to *say
back* (sharp, direct-closer tone, personalized at build time), the *next
action*, and a fallback if the prospect still resists.

Templates use {name}, {city}, {trade}, {launchpad}, {pro}, {followup},
{season_target}, and {proof} — a short, grammatically-clean data clause built
from this business's real intel/local-rank (see playbook._proof_clause).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ObjectionHandler:
    label: str                 # menu label, e.g. "Too expensive"
    triggers: tuple[str, ...]  # phrases that signal this objection
    response: str              # what the caller says (template)
    next_action: str           # what to do after saying it
    fallback: str = ""         # if they still push back


OBJECTIONS: tuple[ObjectionHandler, ...] = (
    ObjectionHandler(
        label="Too expensive / no budget",
        triggers=("too expensive", "can't afford", "no budget", "how much",
                  "costs too much", "what's it cost", "price"),
        response=(
            "Fair question — so let's talk straight. What's one {trade} job worth "
            "to you? ... Right. The Launchpad site starts at {launchpad}, and most "
            "{trade} guys land in the {pro} range for the full build. So we're "
            "talking one job — maybe two — and it's paid for itself. After that it's "
            "printing leads while you sleep. That's not a cost, it's the cheapest "
            "salesman you'll ever put on payroll."
        ),
        next_action="Anchor on job value FIRST, then drop the number. Tie it back to the one-job math.",
        fallback="Still stuck on price? 'Start with the {launchpad} Launchpad and grow into it — "
                 "or we split it. Either way, let's lock the 15 minutes and map it out.'",
    ),
    ObjectionHandler(
        label="Already have a website",
        triggers=("already have", "we have a site", "got a website", "have one"),
        response=(
            "I know — I looked at it. That's the point: {proof}. Having a site and "
            "having one that books jobs are two different animals, and yours is "
            "leaving money on the table. Give me 15 minutes and I'll show you exactly "
            "where — or I send you the full audit and you see it for yourself."
        ),
        next_action="Pivot straight to the proof finding. Offer the audit or the booked walk-through.",
        fallback="'Keep the site — just let me send the audit so you know what it's costing you.' "
                 "Capture email, book a soft follow-up.",
    ),
    ObjectionHandler(
        label="Already have a guy / nephew does it",
        triggers=("have a guy", "my nephew", "friend does", "someone handles", "in-house"),
        response=(
            "And how's that working out — {proof}? That's what a favor-built site "
            "gets you: nobody accountable when it breaks or when Google moves the "
            "goalposts. I do this full-time, I stand behind it, and you've got one "
            "person to call. Let me show you the difference — 15 minutes."
        ),
        next_action="Contrast pro accountability vs. the 'guy.' Use the proof point as the wedge.",
        fallback="'Let me audit what they built — free. If it's solid I'll tell you. If it's not, "
                 "you'll want to know.' Book it.",
    ),
    ObjectionHandler(
        label="Not interested",
        triggers=("not interested", "no thanks", "we're good", "all set"),
        response=(
            "No problem — one thing before I let you go. {proof}. That's real money "
            "walking to a competitor every month. If that doesn't bug you, I'll hang "
            "up happy. But if it does, give me 15 minutes and I'll fix it."
        ),
        next_action="Hit the proof fact, then re-offer the meeting once. If still no, exit clean.",
        fallback="'All good — I'll send the audit so it's on your radar.' Grab email, mark 'not_interested'.",
    ),
    ObjectionHandler(
        label="No time / busy / on a job",
        triggers=("busy", "no time", "on a job", "bad time", "in the field", "call back"),
        response=(
            "Good — busy means you're making money, that's exactly who I want to "
            "work with. I'm not doing this now. When are you off a job today or "
            "tomorrow? I'll call back with the whole breakdown ready — ten minutes, done."
        ),
        next_action="Book a SPECIFIC callback slot now. Press 'c' to log the time.",
        fallback="Won't commit to a time? 'I'll text you the audit link — best number for that?'",
    ),
    ObjectionHandler(
        label="Send me info / email me",
        triggers=("send me", "email me", "send info", "shoot me", "mail it"),
        response=(
            "I'll do you one better than a brochure — I'll send the actual audit of "
            "your online presence, specific to {name}. One thing so I aim it right: "
            "is the priority getting found on Google, or turning the visitors you "
            "already get into calls? ... Got it. I'll send it and we'll talk "
            "{followup} — what time works?"
        ),
        next_action="Qualify, capture email, then BOOK the follow-up. 'Send info' with no date is a polite no.",
        fallback="Never send without a booked time. Log the email + the callback together.",
    ),
    ObjectionHandler(
        label="Need to think / talk to partner",
        triggers=("think about", "talk to", "my wife", "my husband", "partner", "get back to you"),
        response=(
            "Of course — it's your call. But don't sit on it blind: let me send the "
            "breakdown so you're deciding on facts, not a sales call. Then give me 15 "
            "minutes {followup} with whoever else weighs in. Morning or afternoon?"
        ),
        next_action="Assume the next step. Book the follow-up and pull the real decision-maker in.",
        fallback="Find the decision-maker: 'Want me to walk both of you through it at once?'",
    ),
    ObjectionHandler(
        label="Happy with current setup",
        triggers=("happy with", "works fine", "no complaints", "satisfied", "good enough"),
        response=(
            "Glad to hear it — but 'fine' and 'bringing in jobs' aren't the same "
            "thing. {proof}. If your setup were really pulling its weight, that "
            "wouldn't be true. Let me show you the gap — and if I'm wrong, I'll say "
            "so and get out of your hair."
        ),
        next_action="Use the proof fact to crack the 'fine.' Offer the audit / walk-through.",
        fallback="'Let me just send the numbers — you decide if it's worth a conversation.' Grab email.",
    ),
    ObjectionHandler(
        label="How are you different / skeptical",
        triggers=("what makes you", "why you", "how are you different", "scam", "everybody calls"),
        response=(
            "Straight up: every other caller is reading a script. I did the work "
            "before I dialed — I pulled your speed, your SEO, where you rank. {proof}. "
            "I'm local, I build sites you own outright, and I can already tell you "
            "exactly where you're bleeding jobs. Nobody else on your call log can say that."
        ),
        next_action="Lead with the specific proof as credibility. Offer the full audit.",
        fallback="'Let me send the free audit — no strings. The work speaks for itself.'",
    ),
    ObjectionHandler(
        label="Seasonal / bad timing",
        triggers=("slow season", "busy season", "after winter", "next year", "spring", "off season"),
        response=(
            "That's exactly why now's the move. A site takes a few weeks to build "
            "and longer for Google to trust it — start in your slow stretch and the "
            "phone's ringing the second {season_target} hits. Wait, and you're "
            "building it while you're slammed and missing the rush entirely. Let's "
            "get it rolling now."
        ),
        next_action="Flip timing into urgency. Book the kickoff or a dated follow-up.",
        fallback="Book a dated follow-up tied to their season — log it as a callback.",
    ),
)


def find_objection(text: str) -> ObjectionHandler | None:
    low = text.lower()
    for handler in OBJECTIONS:
        if any(t in low for t in handler.triggers):
            return handler
    return None
