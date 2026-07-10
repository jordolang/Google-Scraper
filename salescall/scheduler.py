"""Session + outcome tracking. Persists call results so a calling session can
be paused and resumed, and so progress survives a crash."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .models import Outcome, QueueEntry, Tier

SESSION_DIR = Path(".salescall_cache")
SESSION_FILE = SESSION_DIR / "session.json"


class Session:
    """Tracks dispositions for the current calling session."""

    def __init__(self) -> None:
        self.outcomes: dict[str, Outcome] = {}
        self._load()

    def _load(self) -> None:
        if not SESSION_FILE.exists():
            return
        try:
            data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return
        for slug, raw in data.get("outcomes", {}).items():
            self.outcomes[slug] = Outcome(**raw)

    def _save(self) -> None:
        SESSION_DIR.mkdir(exist_ok=True)
        payload = {
            "updated": datetime.now().isoformat(timespec="seconds"),
            "outcomes": {slug: asdict(o) for slug, o in self.outcomes.items()},
        }
        SESSION_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def record(self, outcome: Outcome) -> None:
        self.outcomes[outcome.business_slug] = outcome
        self._save()

    def is_done(self, slug: str) -> bool:
        o = self.outcomes.get(slug)
        return o is not None and o.disposition not in ("", "callback")

    def disposition(self, slug: str) -> str:
        o = self.outcomes.get(slug)
        return o.disposition if o else ""

    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for o in self.outcomes.values():
            counts[o.disposition] = counts.get(o.disposition, 0) + 1
        return counts


def pending_entries(queue: list[QueueEntry], session: Session) -> list[QueueEntry]:
    """Callable, not-yet-completed entries in priority order."""
    return [
        e for e in queue
        if e.tier != Tier.UNCALLABLE and not session.is_done(e.business.slug)
    ]


def make_outcome(entry: QueueEntry, disposition: str, notes: str = "",
                 duration_seconds: int = 0, callback_at: str = "") -> Outcome:
    return Outcome(
        business_slug=entry.business.slug,
        business_name=entry.business.name,
        disposition=disposition,
        notes=notes,
        duration_seconds=duration_seconds,
        timestamp=datetime.now().isoformat(timespec="seconds"),
        callback_at=callback_at,
    )
