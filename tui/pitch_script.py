"""Loads the website pitch-script guide shown inside the TUI.

The script content lives in a user-editable Markdown file (``pitch_script.md``
at the project root by default) so it can be tweaked without touching code. If
that file is missing, a built-in default is used so the guide is always
available.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

# Path to the editable Markdown script, resolved relative to the project root
# (the parent of the ``tui`` package).
DEFAULT_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "pitch_script.md"

# Fallback used only if the Markdown file can't be found or read.
_FALLBACK = """# 📞 Website Pitch Script

_The editable script file `pitch_script.md` was not found, so this is a short
built-in version. Create `pitch_script.md` in the project root to customize it._

## 1. Opening
"Hi, is this **[Business]**? My name's Jordan with Jlang.dev — I build websites
for local businesses. Do you have a quick minute?"

## 2. The Hook
"I came across **[Business]** and noticed you don't have a website yet — most
people check online before they call, and a simple professional site turns those
searches into booked jobs."

## 3. The Offer
"The Launchpad Package is normally **$499**, but since I reached out directly you
get my email-exclusive rate of **$400** — a complete, professional site, live
fast. There's an optional attribution credit that brings it to **$350**."

## 4. Close
"Want me to get started at the $400 rate? I just need your logo, a few photos,
and your hours."
"""


def load_pitch_script(path: Optional[Path | str] = None) -> str:
    """Return the pitch-script Markdown text.

    Reads ``path`` (defaults to ``pitch_script.md`` at the project root) and
    falls back to a built-in default if the file is missing or unreadable.
    """
    script_path = Path(path) if path is not None else DEFAULT_SCRIPT_PATH
    try:
        text = script_path.read_text(encoding="utf-8").strip()
        return text or _FALLBACK
    except (OSError, UnicodeDecodeError):
        return _FALLBACK
