"""Upload images to a public bucket so emails can show them by URL.

Email clients will not show an image from your computer; it has to live at a
public https address. This uploads to Supabase Storage (free tier is plenty)
and hands back that address::

    host = ImageHost(url="https://abcd.supabase.co", key="…", bucket="email-images")
    host.upload_file("~/Pictures/preview.png")
    # 'https://abcd.supabase.co/storage/v1/object/public/email-images/2026/10/preview-3f9a1c.png'

The key is the project's secret key (``sb_secret_…``, or the legacy
``service_role`` key), which can write to the bucket.
It stays on this computer (in the app's ``.env``), never in an email.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

URL_ENV = "SUPABASE_URL"
KEY_ENV = "SUPABASE_SERVICE_KEY"
BUCKET_ENV = "SUPABASE_BUCKET"
DEFAULT_BUCKET = "email-images"

#: What email clients reliably display.
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp"}
#: Large images are slow to load and count against you with spam filters.
MAX_BYTES = 5 * 1024 * 1024


class ImageHostError(RuntimeError):
    """An upload that did not work, with a message a person can act on."""


class ImageHost:
    def __init__(self, url: str = "", key: str = "", bucket: str = "") -> None:
        self.url = (url or os.environ.get(URL_ENV, "")).strip().rstrip("/")
        self.key = (key or os.environ.get(KEY_ENV, "")).strip()
        self.bucket = (bucket or os.environ.get(BUCKET_ENV, "") or DEFAULT_BUCKET).strip()

    def configured(self) -> bool:
        return bool(self.url.startswith("https://") and self.key and self.bucket)

    def public_url(self, path: str) -> str:
        return f"{self.url}/storage/v1/object/public/{self.bucket}/{path}"

    def upload_file(self, path: str | Path, name: Optional[str] = None) -> str:
        source = Path(path).expanduser()
        if not source.is_file():
            raise ImageHostError(f"{source} does not exist.")
        suffix = source.suffix.lower()
        if suffix not in IMAGE_TYPES:
            raise ImageHostError("Use a PNG, JPG, GIF or WebP image.")
        return self.upload_bytes(source.read_bytes(), name or source.name,
                                 IMAGE_TYPES[suffix])

    def upload_bytes(self, data: bytes, name: str, content_type: str = "") -> str:
        """Upload ``data``; returns its public URL."""
        if not self.configured():
            raise ImageHostError(
                "Image hosting is not set up. Add your Supabase project URL and "
                "service key under Settings → Image Hosting.")
        if len(data) > MAX_BYTES:
            raise ImageHostError("That image is over 5 MB; shrink it before using it in email.")
        content_type = content_type or mimetypes.guess_type(name)[0] or "image/png"
        path = object_path(name, data)
        import requests

        headers = {
            "apikey": self.key,
            "Content-Type": content_type,
            "Cache-Control": "max-age=31536000",
            "x-upsert": "true",
        }
        # Legacy service_role keys are JWTs and go in Authorization too. The
        # newer sb_secret_ keys are not JWTs and must only go in apikey.
        if not self.key.startswith("sb_"):
            headers["Authorization"] = f"Bearer {self.key}"
        response = requests.post(
            f"{self.url}/storage/v1/object/{self.bucket}/{path}",
            data=data, headers=headers, timeout=60,
        )
        if response.status_code >= 300:
            raise ImageHostError(explain(response.status_code, response.text, self.bucket))
        return self.public_url(path)


def object_path(name: str, data: bytes) -> str:
    """``2026/10/preview-3f9a1c.png``: dated, readable, and never clobbering."""
    stem, _, ext = Path(name).name.rpartition(".")
    slug = re.sub(r"[^a-z0-9]+", "-", (stem or name).lower()).strip("-")[:40] or "image"
    digest = hashlib.sha256(data).hexdigest()[:8]
    return f"{datetime.now():%Y/%m}/{slug}-{digest}.{(ext or 'png').lower()}"


def explain(status: int, body: str, bucket: str) -> str:
    """Turn a Supabase error into the step that fixes it."""
    lowered = (body or "").lower()
    if status in (401, 403) or "jwt" in lowered or "signature" in lowered:
        return ("Supabase refused the key. Use a secret key (sb_secret_…) or the "
                "legacy service_role key from Project Settings → API Keys, not "
                "the publishable or anon key.")
    if status == 404 or "bucket not found" in lowered:
        return (f"There is no bucket called {bucket!r}. In Supabase, open Storage → "
                f"New bucket, name it {bucket}, and turn on Public bucket.")
    return f"Upload failed ({status}): {body[:200]}"
