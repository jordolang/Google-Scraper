"""Generate a "here's your new website" preview image for each business.

Each business gets one image: a realistic screenshot of a homepage built for
it, made by Higgsfield's image API from a standard prompt per industry. No
copywriting AI is involved. The prompt is a fixed template filled with the
business's name, category and town, plus a short scene for its industry.

The image is downloaded and re-uploaded to your image host (see
:mod:`image_host`), because Higgsfield's own links expire after seven days and
an email someone opens next month still has to show it. The public URL lands
on ``business.hero_image``, which the email templates already show near the
top::

    maker = PreviewMaker()                       # keys from the app's .env
    url = maker.make(business)                   # also sets business.hero_image

From the command line, for a contacts CSV::

    python site_preview.py data/contacts.csv     # adds a preview_image column

Credentials come from the Higgsfield Console (console.higgsfield.ai → API
keys): ``HF_API_KEY_ID`` and ``HF_API_KEY_SECRET``.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

API_ROOT = "https://api.higgsfield.ai"
KEY_ID_ENV = "HF_API_KEY_ID"
KEY_SECRET_ENV = "HF_API_KEY_SECRET"
MODEL_ENV = "HF_PREVIEW_MODEL"

#: Terminal request states, from docs.higgsfield.ai/docs/concepts/requests.
DONE, FAILED_STATES = "completed", ("failed", "nsfw", "canceled", "cancelled")


@dataclass(frozen=True)
class Model:
    key: str
    label: str
    path: str
    body: Callable[[str], dict]


def _recraft(prompt: str) -> dict:
    return {"prompt": prompt, "resolution": "2k", "aspect_ratio": "16:9",
            "output_format": "jpg"}


def _soul(prompt: str) -> dict:
    return {"prompt": prompt, "resolution": "1080p", "aspect_ratio": "16:9"}


#: The image models on Higgsfield's public API that suit a website mockup.
#: Recraft V4.1 Utility Pro is the default: it is the API's model for clean,
#: front-facing product shots and mockups, renders legible text, and outputs 2K.
MODELS: Dict[str, Model] = {
    "recraft-utility-pro": Model(
        "recraft-utility-pro", "Recraft V4.1 Utility Pro (best for mockups)",
        "/recraft/v4.1/utility/pro/text-to-image", _recraft),
    "soul-v2": Model(
        "soul-v2", "Higgsfield Soul 2.0 (photographic)",
        "/higgsfield-ai/soul/v2/standard", _soul),
}
DEFAULT_MODEL = "recraft-utility-pro"


#: Per industry: what the hero photo shows, and the site's colours. Keys
#: match :mod:`industries` and the email templates.
SCENES: Dict[str, Tuple[str, str]] = {
    "automotive": (
        "a clean, well-lit auto repair bay with a car on a lift",
        "trustworthy navy and steel-blue"),
    "beauty_personal_care": (
        "a bright, airy salon interior with styling chairs and soft natural light",
        "elegant blush and cream"),
    "creative_design": (
        "a modern studio workspace with a large monitor showing design work",
        "bold, minimal with one vivid accent"),
    "events_hospitality": (
        "an elegantly set event venue with warm string lights",
        "rich, celebratory gold and deep green"),
    "food_beverage": (
        "an appetising close-up of the house speciality on a rustic table",
        "warm, inviting"),
    "general": (
        "a friendly, professional storefront on a sunny street",
        "clean white and blue"),
    "health_wellness": (
        "a calm, modern clinic or studio with plants and soft daylight",
        "fresh teal and white"),
    "home_trade_services": (
        "a skilled tradesperson at work on a finished, beautiful home project",
        "solid orange and charcoal"),
    "professional_services": (
        "a bright, modern office with a client meeting",
        "confident navy and white"),
    "real_estate_property": (
        "a stunning home exterior at golden hour",
        "sophisticated slate and white"),
    "retail_boutique": (
        "a curated boutique display of products on shelves",
        "stylish neutral with a warm accent"),
}

PROMPT = (
    "A crisp, realistic full-page screenshot of a modern, professionally "
    "designed small-business website homepage for \"{name}\", {category} in "
    "{location}. Flat front-on screenshot of the page only: no browser chrome, "
    "no device, no hands, no perspective. Top navigation bar with the logo "
    "text \"{name}\" on the left and the links Home, Services, About, Reviews, "
    "Contact, and a {cta} button on the right. Full-width hero section with a "
    "large photo of {photo}, the headline \"{name}\" in large bold type, a short "
    "subheading, and a prominent \"{cta}\" button. Below it, a row of three "
    "service cards with icons, then a strip of five-star review cards. Generous "
    "whitespace, a modern sans-serif typeface, sharp legible text, consistent "
    "spacing, a {palette} colour palette, high-end web design in the style of a 2026 agency portfolio. No "
    "watermarks, no lorem ipsum, no misspellings."
)

#: The button text per industry, so a restaurant isn't told to "Book a repair".
CTAS: Dict[str, str] = {
    "automotive": "Book a Service",
    "beauty_personal_care": "Book Now",
    "events_hospitality": "Check Availability",
    "food_beverage": "View Menu",
    "health_wellness": "Book an Appointment",
    "home_trade_services": "Get a Free Quote",
    "real_estate_property": "View Listings",
    "retail_boutique": "Shop Now",
}


class PreviewError(RuntimeError):
    """A preview that could not be made, with a message a person can act on."""


def _clean(value: str, limit: int = 80) -> str:
    """Strip quotes and control characters so text can't break the prompt."""
    value = re.sub(r"[\"“”\x00-\x1f]", "", str(value or "")).strip()
    return value[:limit]


def _town(address: str, fallback: str = "") -> str:
    match = re.search(r"([A-Za-z][A-Za-z .'-]+),\s*([A-Z]{2})\b", str(address or ""))
    if match:
        return f"{match.group(1).split(',')[-1].strip()}, {match.group(2)}"
    return fallback


def industry_key_for(business) -> str:
    key = getattr(business, "industry_key", "") or ""
    if key:
        return key
    try:
        import industries

        return industries.classify(business.category, business.name)
    except Exception:  # noqa: BLE001 - classification is best-effort
        return "general"


def build_prompt(business, industry_key: str = "") -> str:
    """The standard prompt for ``business``; same input, same prompt."""
    key = industry_key or industry_key_for(business)
    category = _clean(business.category, 60).lower() or "local business"
    category = ("an " if category[0] in "aeiou" else "a ") + category
    photo, palette = SCENES.get(key, SCENES["general"])
    return PROMPT.format(
        name=_clean(business.name) or "Your Business",
        category=category,
        location=_clean(_town(business.address, getattr(business, "search_location", ""))
                        or "your area", 60),
        photo=photo, palette=palette,
        cta=CTAS.get(key, "Contact Us"),
    )


class HiggsfieldClient:
    """Submit an image request to Higgsfield and wait for the result."""

    def __init__(self, key_id: str = "", key_secret: str = "", model: str = "",
                 *, session=None, sleep: Callable[[float], None] = time.sleep) -> None:
        self.key_id = (key_id or os.environ.get(KEY_ID_ENV, "")).strip()
        self.key_secret = (key_secret or os.environ.get(KEY_SECRET_ENV, "")).strip()
        model = model or os.environ.get(MODEL_ENV, "") or DEFAULT_MODEL
        self.model = MODELS.get(model, MODELS[DEFAULT_MODEL])
        self._session = session
        self._sleep = sleep

    def configured(self) -> bool:
        return bool(self.key_id and self.key_secret)

    @property
    def session(self):
        if self._session is None:
            import requests

            self._session = requests.Session()
        return self._session

    def _headers(self) -> dict:
        return {"Authorization": f"Key {self.key_id}:{self.key_secret}",
                "Content-Type": "application/json", "Accept": "application/json"}

    def submit(self, prompt: str) -> dict:
        if not self.configured():
            raise PreviewError(
                "Higgsfield is not set up. Add your API key ID and secret under "
                "Settings → Website Previews.")
        import uuid

        headers = dict(self._headers(), **{"Idempotency-Key": str(uuid.uuid4())})
        response = self.session.post(API_ROOT + self.model.path, headers=headers,
                                     json=self.model.body(prompt), timeout=60)
        if response.status_code >= 300:
            raise PreviewError(explain(response.status_code, response.text))
        return response.json()

    def wait(self, request: dict, *, timeout: float = 300.0, every: float = 3.0) -> str:
        """Poll until the request finishes; returns the first image URL."""
        status_url = request.get("status_url") or (
            f"{API_ROOT}/requests/{request.get('request_id')}/status")
        waited = 0.0
        while True:
            response = self.session.get(status_url, headers=self._headers(), timeout=30)
            if response.status_code >= 300:
                raise PreviewError(explain(response.status_code, response.text))
            data = response.json()
            status = str(data.get("status", "")).lower()
            if status == DONE:
                images = data.get("images") or []
                if images and images[0].get("url"):
                    return images[0]["url"]
                raise PreviewError("Higgsfield finished but returned no image.")
            if status in FAILED_STATES:
                detail = data.get("error") or status
                if status == "nsfw":
                    detail = "the content filter rejected this one"
                raise PreviewError(f"Higgsfield could not make this image: {detail}.")
            if waited >= timeout:
                raise PreviewError("Higgsfield took too long; try again later.")
            self._sleep(every)
            waited += every

    def generate(self, prompt: str) -> str:
        return self.wait(self.submit(prompt))

    def download(self, url: str) -> bytes:
        response = self.session.get(url, timeout=60)
        if response.status_code >= 300:
            raise PreviewError(f"Could not download the image ({response.status_code}).")
        return response.content


def explain(status: int, body: str) -> str:
    """Turn a Higgsfield error into the step that fixes it."""
    lowered = (body or "").lower()
    if status in (401, 403):
        return ("Higgsfield refused the API key. Check the key ID and secret under "
                "Settings → Website Previews (console.higgsfield.ai → API keys).")
    if status == 402 or "credit" in lowered or "balance" in lowered:
        return ("Your Higgsfield account is out of credits. Top up at "
                "higgsfield.ai, then try again.")
    if status == 429:
        return "Higgsfield is rate-limiting requests; wait a minute and try again."
    return f"Higgsfield error ({status}): {(body or '')[:200]}"


class PreviewMaker:
    """Make, host and attach a website preview for a business."""

    def __init__(self, client: Optional[HiggsfieldClient] = None, host=None) -> None:
        self.client = client or HiggsfieldClient()
        if host is None:
            from image_host import ImageHost

            host = ImageHost()
        self.host = host

    def make(self, business, *, industry_key: str = "") -> str:
        """Generate the preview, host it, set ``business.hero_image``; returns the URL."""
        url = self.client.generate(build_prompt(business, industry_key))
        if self.host is not None and self.host.configured():
            data = self.client.download(url)
            name = re.sub(r"[^a-z0-9]+", "-", (business.name or "business").lower())
            url = self.host.upload_bytes(data, f"preview-{name.strip('-') or 'site'}.jpg",
                                         "image/jpeg")
        business.hero_image = url
        return url

    @property
    def hosts_images(self) -> bool:
        return bool(self.host is not None and self.host.configured())


def main(argv=None) -> int:
    """``python site_preview.py contacts.csv``: add a preview_image column."""
    import argparse
    import csv

    from tui.models import Business

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("csv", help="contacts CSV to read and update in place")
    parser.add_argument("--model", choices=sorted(MODELS), default="")
    parser.add_argument("--limit", type=int, default=0, help="stop after N previews")
    parser.add_argument("--redo", action="store_true", help="replace existing previews")
    args = parser.parse_args(argv)

    with open(args.csv, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = list(reader.fieldnames or [])
    if "preview_image" not in fields:
        fields.append("preview_image")
    maker = PreviewMaker(HiggsfieldClient(model=args.model))
    if not maker.hosts_images:
        print("Note: no image host set, so links expire in 7 days. "
              "Set SUPABASE_URL and SUPABASE_SERVICE_KEY to keep them.")
    made = 0
    for row in rows:
        if not row.get("name") or (row.get("preview_image") and not args.redo):
            continue
        if args.limit and made >= args.limit:
            break
        business = Business.from_dict(row)
        try:
            row["preview_image"] = maker.make(business)
            made += 1
            print(f"✓ {business.name}: {row['preview_image']}")
        except PreviewError as exc:
            print(f"✗ {business.name}: {exc}")
            if "credits" in str(exc) or "refused" in str(exc):
                break
    with open(args.csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Made {made} preview(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
