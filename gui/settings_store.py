"""Persisted user preferences for the desktop app.

Settings live next to the user's other application data — on Windows that is
``%APPDATA%\\LocalLeadScraperPro\\settings.json``, and on a Mac
``~/Library/Application Support/LocalLeadScraperPro/settings.json`` — so a
packaged app never has to write inside its own install folder.

Nothing secret is stored here. The SMTP password is read from the environment
(or a ``.env`` file) and otherwise only ever held in memory for the lifetime of
the window; see :mod:`gui.state`. API keys (Resend, Supabase) go in the app's
own ``.env`` via :func:`gui.runtime.save_env_values`.
"""

from __future__ import annotations

import json
import os
import sys
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
    # After the website scan, look up missing phones and emails on Yellow
    # Pages, the BBB, web search and Facebook.
    "auto_fill_contacts": True,
    "data_categories": [
        "Business Info", "Contact Info", "Services", "About Us",
        "Reviews/Testimonials", "Social Media Links", "Images",
        "Team/Staff", "Blog/News", "Certifications", "Hours of Operation",
    ],
    # -- outreach -------------------------------------------------------
    "from_email": "jordan@jlang.dev",
    "sender_name": "Jordan Lang",
    # Printed in every email's footer; US law (CAN-SPAM) expects a postal
    # address in commercial email.
    "sender_address": "",
    # An https page that unsubscribes people; blank = reply "Unsubscribe".
    "unsubscribe_url": "",
    # "smtp" or "resend". The Resend API key lives in the app's .env.
    "send_via": "smtp",
    # Supabase Storage for email images. The service key lives in the .env.
    "supabase_url": "",
    "supabase_bucket": "email-images",
    # The image shown in every email that has no preview of its own.
    "email_image": "",
    # Website previews drawn by Higgsfield (site_preview.MODELS key; "" =
    # default), and whether a campaign makes any missing ones before it sends.
    # The Higgsfield key ID and secret live in the .env.
    "preview_model": "",
    "auto_previews": False,
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
}

# Licence fields from older versions. The app is free now, so they are
# dropped from settings.json on load.
RETIRED_KEYS = ("license_tier", "license_expires")


def config_dir() -> Path:
    """Per-user directory for settings, chosen per platform."""
    override = os.environ.get("LLSP_CONFIG_DIR")
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    if appdata:  # Windows
        return Path(appdata) / APP_NAME
    if sys.platform == "darwin" and not os.environ.get("XDG_CONFIG_HOME"):
        # Settings sit with the rest of the app's files in Application Support.
        from .runtime import mac_support_dir

        return mac_support_dir(Path.home() / ".config" / APP_NAME)
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
            if key in DEFAULTS and _usable(value, DEFAULTS[key]):
                settings[key] = value
    return settings


def _usable(value, default) -> bool:
    """Whether a stored value can stand in for its default.

    A hand-edited (or half-written) settings file should cost the user that
    one setting, not the whole app — so anything of the wrong shape is
    ignored in favour of the default.
    """
    if value is None:
        return False
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, (int, float)):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(default, list):
        return isinstance(value, list)
    if isinstance(default, str):
        return isinstance(value, str)
    return type(value) is type(default)


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
