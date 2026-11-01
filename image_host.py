"""Upload images to Vercel Blob so emails can show them by URL.

Email clients will not show an image from your computer; it has to live at a
public https address. This uploads to a Vercel Blob store and hands back that
address::

    host = ImageHost(token="vercel_blob_rw_…")
    host.upload_file("~/Pictures/preview.png")
    # 'https://<store>.public.blob.vercel-storage.com/email-images/2026/10/preview-3f9a1c.png'

The token is the store's read-write token (``BLOB_READ_WRITE_TOKEN``, from
Vercel → Storage → your Blob store). It stays on this computer, in the app's
``.env``, and never goes into an email. The store must be **public** so the
images can be shown to anyone who opens the email.

:class:`BlobStore` is the small Vercel Blob client underneath; the unsubscribe
list (:mod:`opt_outs`) uses it too.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, Optional

TOKEN_ENV = "BLOB_READ_WRITE_TOKEN"
FOLDER_ENV = "BLOB_FOLDER"
DEFAULT_FOLDER = "email-images"

API_URL = "https://vercel.com/api/blob"
#: The Blob API version the official @vercel/blob SDK (2.x) speaks.
API_VERSION = "13"
TOKEN_PREFIX = "vercel_blob_rw_"

#: What email clients reliably display.
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp"}
#: Large images are slow to load and count against you with spam filters.
MAX_BYTES = 5 * 1024 * 1024


class ImageHostError(RuntimeError):
    """An upload that did not work, with a message a person can act on."""


def store_id_from_token(token: str) -> str:
    """``vercel_blob_rw_<storeId>_<secret>`` → ``<storeId>``."""
    parts = (token or "").split("_")
    return parts[3] if len(parts) > 4 and token.startswith(TOKEN_PREFIX) else ""


class BlobStore:
    """Just enough of the Vercel Blob REST API: put and list."""

    def __init__(self, token: str = "", timeout: float = 60) -> None:
        self.token = (token or os.environ.get(TOKEN_ENV, "")).strip().strip('"')
        self.timeout = timeout
        self._session = None

    def configured(self) -> bool:
        return bool(store_id_from_token(self.token))

    @property
    def store_id(self) -> str:
        return store_id_from_token(self.token)

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        return {
            "authorization": f"Bearer {self.token}",
            "x-api-version": API_VERSION,
            "x-vercel-blob-store-id": self.store_id,
            **(extra or {}),
        }

    def _request(self, method: str, query: Dict[str, str], **kwargs):
        if not self.configured():
            raise ImageHostError(
                "Vercel Blob is not set up. Paste your store's read-write token "
                "(vercel_blob_rw_…) under Settings → Image Hosting.")
        import requests

        if self._session is None:
            self._session = requests.Session()
        try:
            response = self._session.request(
                method, f"{API_URL}/", params=query, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise ImageHostError(f"Could not reach Vercel Blob: {exc}") from exc
        if response.status_code >= 300:
            raise ImageHostError(explain(response.status_code, response.text))
        return response

    def put(self, pathname: str, data: bytes, content_type: str,
            *, cache_seconds: int = 31536000) -> str:
        """Store ``data`` at exactly ``pathname`` (overwriting); returns its URL."""
        response = self._request(
            "PUT", {"pathname": pathname}, data=data,
            headers=self._headers({
                "x-vercel-blob-access": "public",
                "x-content-type": content_type,
                "x-add-random-suffix": "0",
                "x-allow-overwrite": "1",
                "x-cache-control-max-age": str(cache_seconds),
            }))
        url = (response.json() or {}).get("url", "")
        if not url:
            raise ImageHostError("Vercel Blob accepted the upload but returned no address.")
        return url

    def list_pathnames(self, prefix: str) -> Iterator[str]:
        """Every stored pathname that starts with ``prefix``."""
        cursor = ""
        while True:
            query = {"prefix": prefix, "limit": "1000"}
            if cursor:
                query["cursor"] = cursor
            page = self._request("GET", query, headers=self._headers()).json() or {}
            for blob in page.get("blobs", []):
                yield blob.get("pathname", "")
            cursor = page.get("cursor") or ""
            if not page.get("hasMore") or not cursor:
                return


class ImageHost:
    def __init__(self, token: str = "", folder: str = "") -> None:
        self.store = BlobStore(token)
        self.folder = (folder or os.environ.get(FOLDER_ENV, "")
                       or DEFAULT_FOLDER).strip().strip("/")

    def configured(self) -> bool:
        return self.store.configured()

    @property
    def identity(self) -> str:
        """Which store uploads land in; a cached URL from another store is stale."""
        return f"vercel-blob:{self.store.store_id}" if self.configured() else ""

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
                "Image hosting is not set up. Paste your Vercel Blob read-write "
                "token (vercel_blob_rw_…) under Settings → Image Hosting.")
        if len(data) > MAX_BYTES:
            raise ImageHostError("That image is over 5 MB; shrink it before using it in email.")
        content_type = content_type or mimetypes.guess_type(name)[0] or "image/png"
        path = object_path(name, data)
        if self.folder:
            path = f"{self.folder}/{path}"
        return self.store.put(path, data, content_type)


def object_path(name: str, data: bytes) -> str:
    """``2026/10/preview-3f9a1c.png``: dated, readable, and never clobbering."""
    stem, _, ext = Path(name).name.rpartition(".")
    slug = re.sub(r"[^a-z0-9]+", "-", (stem or name).lower()).strip("-")[:40] or "image"
    digest = hashlib.sha256(data).hexdigest()[:8]
    return f"{datetime.now():%Y/%m}/{slug}-{digest}.{(ext or 'png').lower()}"


def explain(status: int, body: str) -> str:
    """Turn a Vercel Blob error into the step that fixes it."""
    lowered = (body or "").lower()
    if status in (401, 403) and "private" in lowered:
        return ("Your Vercel Blob store is private, so emails couldn't show its "
                "images. Create a store with Public access in Vercel → Storage "
                "and use its read-write token.")
    if status in (401, 403) or ("token" in lowered and "invalid" in lowered):
        return ("Vercel Blob refused the token. Copy the read-write token "
                "(vercel_blob_rw_…) from Vercel → Storage → your Blob store → "
                ".env.local tab, and paste it under Settings → Image Hosting.")
    if status == 404 or "store_not_found" in lowered or "not found" in lowered:
        return ("Vercel can't find that Blob store. It may have been deleted; "
                "check Vercel → Storage and copy a current read-write token.")
    if status == 429:
        return "Vercel Blob is rate-limiting uploads; wait a minute and try again."
    return f"Upload failed ({status}): {(body or '')[:200]}"
