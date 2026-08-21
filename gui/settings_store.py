"""Persisted user preferences for the desktop app.

Settings live next to the user's other application data — on Windows that is
``%APPDATA%\\LocalLeadScraperPro\\settings.json`` — so a packaged .exe never
has to write inside Program Files.

Nothing secret is stored here. The SMTP password is read from the environment
(or a ``.env`` file) and otherwise only ever held in memory for the lifetime of
the window; see :mod:`gui.state`.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

APP_NAME = "LocalLeadScraperPro"

DEFAULTS: Dict[str, Any] = {
    # -- search ---------------------------------------------------------
    "location": "Columbus, Ohio, USA",
    "industries": "Roofing Contractors",
    "radius_miles": 25,
    "max_results": 50,
    # -- scraping -------------------------------------------------------
    "headless": True,
    "demo_mode": False,
    "scan_delay": 1.0,
    "data_categories": [
        "Business Info", "Contact Info", "Services", "About Us",
        "Reviews/Testimonials", "Social Media Links", "Images",
        "Team/Staff", "Blog/News", "Certifications", "Hours of Operation",
    ],
    # -- outreach -------------------------------------------------------
    "from_email": "jordan@jlang.dev",
    "reply_to": "",
    "smtp_username": "",
    "smtp_server": "",
    "smtp_port": 0,
    "campaign_name": "Website Offer - Roofing",
    "email_delay": 30.0,
    "daily_limit": 50,
    "dry_run": True,
    # -- storage --------------------------------------------------------
    "data_root": "",
    # -- licence banner shown in the sidebar ----------------------------
    "license_tier": "Pro",
    "license_expires": "12/31/2025",
}


def config_dir() -> Path:
    """Per-user directory for settings, chosen per platform."""
    override = os.environ.get("LLSP_CONFIG_DIR")
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    if appdata:  # Windows
        return Path(appdata) / APP_NAME
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / APP_NAME


def config_path() -> Path:
    return config_dir() / "settings.json"


def load() -> Dict[str, Any]:
    """Return stored settings, backfilled with :data:`DEFAULTS`."""
    settings = dict(DEFAULTS)
    try:
        raw = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return settings
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key in DEFAULTS and value is not None:
                settings[key] = value
    return settings


def save(settings: Dict[str, Any]) -> Path | None:
    """Write settings atomically; returns the path, or None if it failed."""
    payload = {key: settings.get(key, default) for key, default in DEFAULTS.items()}
    path = config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.replace(tmp, path)
        return path
    except OSError:
        return None
