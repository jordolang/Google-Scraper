"""Fetch a web page and the small set of side resources SEO analysis needs."""

from __future__ import annotations

from dataclasses import dataclass, field

import requests

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_TIMEOUT = 15


@dataclass(frozen=True)
class PageData:
    """Raw materials fetched from a site, consumed by the analyzers."""

    url: str
    final_url: str = ""
    reachable: bool = False
    status: int = 0
    https: bool = False
    headers: dict[str, str] = field(default_factory=dict)
    cookies: tuple[str, ...] = ()
    html: str = ""
    elapsed_ms: int = 0
    robots_ok: bool = False
    sitemap_ok: bool = False
    error: str = ""


def _normalize(url: str) -> str:
    return url if "//" in url else f"https://{url}"


def _head_ok(session: requests.Session, base: str, path: str) -> bool:
    try:
        resp = session.get(f"{base.rstrip('/')}/{path}", timeout=8, allow_redirects=True)
        return resp.status_code == 200 and bool(resp.text.strip())
    except requests.RequestException:
        return False


def fetch_page(url: str) -> PageData:
    """Fetch the page plus robots.txt / sitemap.xml presence."""
    target = _normalize(url)
    session = requests.Session()
    session.headers.update({"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"})

    try:
        resp = session.get(target, timeout=_TIMEOUT, allow_redirects=True)
    except requests.RequestException as exc:
        return PageData(url=target, reachable=False, error=f"{type(exc).__name__}: {exc}")

    final = resp.url
    origin = f"{requests.utils.urlparse(final).scheme}://{requests.utils.urlparse(final).netloc}"

    return PageData(
        url=target,
        final_url=final,
        reachable=True,
        status=resp.status_code,
        https=final.lower().startswith("https://"),
        headers={k.lower(): v for k, v in resp.headers.items()},
        cookies=tuple(c.name for c in resp.cookies),
        html=resp.text or "",
        elapsed_ms=int(resp.elapsed.total_seconds() * 1000),
        robots_ok=_head_ok(session, origin, "robots.txt"),
        sitemap_ok=_head_ok(session, origin, "sitemap.xml"),
    )
