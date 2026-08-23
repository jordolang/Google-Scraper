"""The 72-hour trial, and the bookkeeping that keeps it to one per machine.

The trial is a licence like any other — a signed token at the ``trial`` tier —
so the app has exactly one code path for "what am I allowed to do". What is
special is how it is obtained and how it is prevented from being obtained
twice.

**One per machine, decided by the server.** The app asks for a trial with its
fingerprint; the server records that fingerprint against a start time. Ask
again and the same start time comes back, so deleting the local state file
buys nothing: the trial resumes where it was, expired if it expired.

**Starting offline.** Refusing to start until the licence server answers would
punish the customer for our downtime, so a first run with no answer gets a
*provisional* trial: it works immediately, but only for
:data:`PROVISIONAL_HOURS` until the app manages to check in. That is long
enough to survive an outage or a flight, and short enough that "delete the
config folder for another 72 hours" is not a strategy. The moment the server
confirms, the full 72 hours applies from the original start.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from . import plans, storage
from .errors import TrialExhausted

HOURS = 3600.0

#: How much of the trial a machine gets before the server has confirmed it.
PROVISIONAL_HOURS = 6.0


def record(state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The stored trial block: ``{started_at, confirmed, exhausted}``."""
    raw = (state if state is not None else storage.load()).get("trial") or {}
    return {
        "started_at": float(raw.get("started_at") or 0.0),
        "confirmed": bool(raw.get("confirmed")),
        "exhausted": bool(raw.get("exhausted")),
    }


def started(state: Optional[Dict[str, Any]] = None) -> bool:
    return record(state)["started_at"] > 0


def begin(started_at: Optional[float] = None, *, confirmed: bool = False) -> Dict[str, Any]:
    """Start the trial, or return the one already running.

    ``started_at`` comes from the server when there is one, so a machine that
    trialled the app six months ago on a different install gets its original
    start time back — and an immediately expired trial.
    """
    state = storage.load()
    current = record(state)
    if current["exhausted"]:
        raise TrialExhausted()
    now = time.time()
    # An earlier start always wins: the server's memory beats a fresh local
    # clock, which is the whole anti-reset mechanism.
    begin_at = current["started_at"] or float(started_at or now)
    if started_at:
        begin_at = min(begin_at, float(started_at))
    updated = {
        "started_at": begin_at,
        "confirmed": bool(current["confirmed"] or confirmed),
        "exhausted": False,
    }
    state["trial"] = updated
    storage.save(state)
    return updated


def confirm(started_at: float) -> Dict[str, Any]:
    """Apply the server's answer: the real start time, full length unlocked."""
    return begin(started_at, confirmed=True)


def exhaust() -> None:
    """Mark the trial as spent — the server says this machine already had one."""
    state = storage.load()
    trial = record(state)
    trial["exhausted"] = True
    state["trial"] = trial
    storage.save(state)


def window(state: Optional[Dict[str, Any]] = None) -> Tuple[float, float]:
    """(start, end) of the trial in unix seconds; (0, 0) if never started."""
    current = record(state)
    start = current["started_at"]
    if not start:
        return 0.0, 0.0
    hours = plans.TRIAL_HOURS if current["confirmed"] else PROVISIONAL_HOURS
    return start, start + hours * HOURS


def seconds_left(now: Optional[float] = None,
                 state: Optional[Dict[str, Any]] = None) -> float:
    """How much trial remains. Zero once it is over, never negative."""
    _, end = window(state)
    if not end:
        return 0.0
    return max(0.0, end - (time.time() if now is None else now))


def active(now: Optional[float] = None,
           state: Optional[Dict[str, Any]] = None) -> bool:
    current = record(state) if state is not None else record()
    if current["exhausted"]:
        return False
    return seconds_left(now, state) > 0


def needs_confirmation(state: Optional[Dict[str, Any]] = None) -> bool:
    """A provisional trial that should check in with the server."""
    current = record(state)
    return bool(current["started_at"]) and not current["confirmed"]


def describe(now: Optional[float] = None,
             state: Optional[Dict[str, Any]] = None) -> str:
    """"14 hours left in your trial" — the string the banner shows."""
    left = seconds_left(now, state)
    if left <= 0:
        return "Your trial has ended."
    if left < HOURS:
        minutes = max(1, int(left // 60))
        return f"{minutes} minute{'s' if minutes != 1 else ''} left in your trial."
    hours = int(left // HOURS)
    return f"{hours} hour{'s' if hours != 1 else ''} left in your trial."
