"""Public addresses for the images the email templates are designed around.

A template names its banner image in a comment, e.g.
``<!-- llsp-hero: heroes/roofing.jpg -->``, and the file lives in this repo's
``email_assets/`` folder. Email clients only show images that sit at a public
https address, so :func:`url_for` turns that name into one:

* With image hosting set up (Settings → Image Hosting), the file is uploaded to
  your own Supabase bucket once and that address is remembered.
* Otherwise the copy published with the app's public GitHub repository is used.

Either way nothing has to be pasted in by hand.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable, Dict, Optional

#: Where every bundled asset is published (the repository is public).
PUBLIC_BASE = "https://raw.githubusercontent.com/jordolang/Google-Scraper/main/email_assets/"

#: Remembered uploads: {name: {"sha": <sha256 of the file>, "url": <address>}}.
CACHE_NAME = "email_assets.json"


def asset_dir() -> Path:
    """The bundled ``email_assets`` folder (inside the app when packaged)."""
    try:
        from gui import runtime

        packaged = runtime.bundle_dir() / "email_assets"
        if packaged.is_dir():
            return packaged
    except Exception:  # noqa: BLE001 - the GUI package is optional here
        pass
    return Path(__file__).resolve().parent / "email_assets"


def public_url(name: str) -> str:
    """The address of ``name`` in the public repository."""
    return PUBLIC_BASE + name.lstrip("/")


def local_path(name: str) -> Path:
    return asset_dir() / name


def _cache_path() -> Path:
    try:
        from gui import runtime

        return runtime.app_data_dir() / CACHE_NAME
    except Exception:  # noqa: BLE001
        return Path.home() / ".local_lead_scraper" / CACHE_NAME


def _load(path: Path) -> Dict[str, dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def hosted_resolver(host, cache_path: Optional[Path] = None,
                    on_error: Callable[[str], None] = lambda message: None
                    ) -> Callable[[str], str]:
    """A ``name -> url`` function that puts each asset on ``host`` once.

    ``host`` is an :class:`image_host.ImageHost`. When it isn't configured, or an
    upload fails, the public repository address is used instead, so a batch is
    never held up by image hosting.
    """
    cache_file = cache_path or _cache_path()

    def resolve(name: str) -> str:
        source = local_path(name)
        if host is None or not host.configured() or not source.is_file():
            return public_url(name)
        data = source.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        cache = _load(cache_file)
        hit = cache.get(name)
        if hit and hit.get("sha") == sha and hit.get("url"):
            return hit["url"]
        try:
            url = host.upload_bytes(data, Path(name).name)
        except Exception as exc:  # noqa: BLE001 - network or config trouble
            on_error(f"Couldn't upload {name} to your image host ({exc}); "
                     "using the public copy.")
            return public_url(name)
        cache[name] = {"sha": sha, "url": url}
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        except OSError:
            pass
        return url

    return resolve
