"""Where the app finds its files, running from source or from a packaged .exe.

Inside a PyInstaller bundle the code lives in a temporary folder that is wiped
on exit, and the working directory is wherever the user happened to double-click
from. So on a frozen build we:

* copy the editable assets (email templates, the pitch script) into a per-user
  folder the first time they are needed, and
* make that folder the working directory, so every relative path the existing
  code uses — ``data/``, ``pricing.json``, ``.env`` — lands somewhere writable.

Run from source, nothing moves: the repo is already the right place.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Iterable, Optional

APP_NAME = "LocalLeadScraperPro"

#: Files and folders the user is meant to be able to edit.
SEEDED_ASSETS = ("email_templates", "email_template.html", "pitch_script.md")


def frozen() -> bool:
    """True when running from a packaged executable."""
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> Path:
    """Read-only resources: the PyInstaller payload, or the repo root."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent


def app_data_dir() -> Path:
    """Writable per-user folder for exports, settings and edited assets."""
    override = os.environ.get("LLSP_DATA_DIR")
    if override:
        return Path(override)
    local = os.environ.get("LOCALAPPDATA")
    if local:  # Windows
        return Path(local) / APP_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / APP_NAME


_RESOLVED_DIR: Optional[Path] = None


def working_dir() -> Path:
    """The directory relative paths resolve against."""
    if frozen():
        return _RESOLVED_DIR or app_data_dir()
    return Path.cwd()


def user_asset(name: str) -> Path:
    """Return the editable copy of ``name``, seeding it from the bundle once.

    Running from source this is just the file in the repo, so editing a
    template edits the one the app uses.
    """
    source = bundle_dir() / name
    if not frozen():
        return source
    target = app_data_dir() / name
    if not target.exists() and source.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    return target


def seed_assets(names: Iterable[str] = SEEDED_ASSETS) -> None:
    for name in names:
        try:
            user_asset(name)
        except OSError:  # pragma: no cover - a read-only profile is survivable
            pass


def prepare() -> Path:
    """Get the process ready to run; returns the working directory."""
    if frozen():
        target = _writable_dir(app_data_dir())
        os.chdir(target)
        # data_store anchors data/ to its own module directory, which inside a
        # one-file bundle is the temp folder PyInstaller deletes on exit. Point
        # it at the user's folder before anything writes a CSV.
        os.environ.setdefault("GOOGLE_SCRAPER_DATA_DIR", str(target / "data"))
        globals()["_RESOLVED_DIR"] = target
        seed_assets()
        # The pitch script is looked up relative to the tui package, which the
        # bundle flattens; point it at the editable copy instead.
        try:
            from tui import pitch_script

            script = app_data_dir() / "pitch_script.md"
            if script.exists():
                pitch_script.DEFAULT_SCRIPT_PATH = script
        except Exception:  # pragma: no cover - the fallback script still works
            pass
    return working_dir()


def _writable_dir(preferred: Path) -> Path:
    """``preferred`` if it can be created, else a temp folder that can.

    A locked-down or roaming profile should not stop the app from starting;
    it just means this session's files land somewhere else.
    """
    import tempfile

    for candidate in (preferred, Path(tempfile.gettempdir()) / APP_NAME):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write-test"
            probe.touch()
            probe.unlink()
            return candidate
        except OSError:
            continue
    return Path(tempfile.gettempdir())


def env_files() -> list[Path]:
    """Every place a ``.env`` with EMAIL_PASSWORD might sensibly live."""
    candidates = [Path.cwd() / ".env", app_data_dir() / ".env"]
    if frozen():
        candidates.append(Path(sys.executable).resolve().parent / ".env")
    seen: list[Path] = []
    for path in candidates:
        if path not in seen:
            seen.append(path)
    return seen
