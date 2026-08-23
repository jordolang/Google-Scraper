"""Where the licence, the trial clock and the send counters live on disk.

One JSON file next to the app's settings — ``license.json`` — holding three
things:

``token``
    The signed licence blob. Tamper-evident by construction: change a byte and
    the signature stops matching, so this file needs no protection of its own.

``trial``
    When the 72-hour trial started on this machine, countersigned by the
    licence server so deleting the file does not buy a second one (the server
    remembers the fingerprint and re-issues the *same* start time).

``clock``
    The latest timestamp the app has ever seen. Winding the system clock back
    to freeze a trial or revive an expired licence moves time backwards past
    this mark, which is exactly what :class:`~licensing.errors.ClockTampered`
    is for. Stored as a plain number: someone who edits it by hand has to know
    to, which is already past the "set the date back" attack this catches.

Writes are atomic (temp file + ``os.replace``) for the same reason
``gui.settings_store`` does it: a power cut mid-write must not cost a customer
their licence.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

FILENAME = "license.json"
SCHEMA_VERSION = 1

#: Test/CI hook: point the whole licensing state at a scratch directory.
STATE_DIR_ENV = "LLSP_LICENSE_DIR"


def state_dir() -> Path:
    override = os.environ.get(STATE_DIR_ENV)
    if override:
        return Path(override)
    from gui import settings_store  # lazy: keeps this importable without Qt

    return settings_store.config_dir()


def state_path() -> Path:
    return state_dir() / FILENAME


def _blank() -> Dict[str, Any]:
    return {"version": SCHEMA_VERSION, "token": "", "trial": {}, "clock": 0.0,
            "usage": {}}


def load() -> Dict[str, Any]:
    """Read the state file, returning a blank one if it is missing or broken."""
    state = _blank()
    try:
        raw = json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return state
    if not isinstance(raw, dict):
        return state
    for key, default in state.items():
        value = raw.get(key, default)
        if type(value) is type(default) or (isinstance(default, float)
                                            and isinstance(value, (int, float))):
            state[key] = value
    return state


def save(state: Dict[str, Any]) -> Optional[Path]:
    """Write the state atomically; None if the disk said no."""
    path = state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(state, stream, indent=2, sort_keys=True)
        os.replace(temporary, path)
        return path
    except OSError:
        return None


def update(**values) -> Optional[Path]:
    state = load()
    state.update(values)
    return save(state)


def clear() -> None:
    """Remove all local licensing state. Used by "deactivate this computer"."""
    try:
        state_path().unlink()
    except OSError:
        pass


# -- monotonic clock guard ----------------------------------------------

#: Clocks drift, and a machine that has been asleep can come back a little
#: behind. Only a jump bigger than this counts as tampering.
CLOCK_SLACK_SECONDS = 6 * 3600.0


def check_clock(now: Optional[float] = None) -> bool:
    """Record the current time; False if it moved meaningfully backwards.

    Called on every start-up. Returning a bool rather than raising leaves the
    caller free to decide the consequence — the desktop app warns and falls
    back to reader mode, a test just asserts.
    """
    now = time.time() if now is None else now
    state = load()
    seen = float(state.get("clock") or 0.0)
    if now + CLOCK_SLACK_SECONDS < seen:
        return False
    if now > seen:
        state["clock"] = now
        save(state)
    return True


def high_water_mark() -> float:
    return float(load().get("clock") or 0.0)


# -- usage counters ------------------------------------------------------
# Per-day send counts, so the daily email cap survives a restart. Kept here
# rather than in settings because a customer editing settings.json to raise a
# limit is a support problem; editing this one is answered by the server's own
# per-account send stats.

def bump_usage(name: str, amount: int = 1, day: Optional[str] = None) -> int:
    """Add to today's counter for ``name`` and return the new total."""
    day = day or time.strftime("%Y-%m-%d")
    state = load()
    usage = state.get("usage") or {}
    today = usage.get(day) or {}
    total = int(today.get(name, 0)) + int(amount)
    today[name] = total
    # Keep a week; the file is not an analytics store.
    usage = {key: value for key, value in usage.items() if key >= _week_ago(day)}
    usage[day] = today
    state["usage"] = usage
    save(state)
    return total


def usage_today(name: str, day: Optional[str] = None) -> int:
    day = day or time.strftime("%Y-%m-%d")
    return int(((load().get("usage") or {}).get(day) or {}).get(name, 0))


def _week_ago(day: str) -> str:
    try:
        stamp = time.mktime(time.strptime(day, "%Y-%m-%d"))
    except ValueError:
        return day
    return time.strftime("%Y-%m-%d", time.localtime(stamp - 7 * 86400))
