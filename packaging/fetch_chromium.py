#!/usr/bin/env python3
"""Build the browser payload that gets appended to the executable.

The app drives Chrome. Requiring one to be installed is the normal way to do
that, but it is still something outside the .exe — so this fetches a Chromium
build and the chromedriver from the *same* snapshot revision, and packs them
into one archive.

Same revision matters: a driver only drives its own major version of Chrome,
so pairing them at build time removes the version mismatch entirely.

Chromium, not Google Chrome: Chromium is the open-source project (BSD), which
can be redistributed inside another product. The Chrome binaries Google
publishes are not.

    python packaging/fetch_chromium.py --platform Win_x64

Writes packaging/browser/browser-payload.zip, which build_windows.bat and CI
append to the built executable.
"""

from __future__ import annotations

import argparse
import json
import shutil
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD_DIR = ROOT / "browser"
PAYLOAD = PAYLOAD_DIR / "browser-payload.zip"
BASE = "https://commondatastorage.googleapis.com/chromium-browser-snapshots"

#: What each platform's snapshot calls its browser archive, and the driver
#: names to try. The driver is not called the same thing everywhere — ARM64
#: Windows ships chromedriver_win64.zip while x64 ships chromedriver_win32.zip
#: — so the candidates are probed rather than assumed.
ARCHIVES = {
    "Win_x64": ("chrome-win.zip", ("chromedriver_win32.zip", "chromedriver_win64.zip")),
    "Win_Arm64": ("chrome-win.zip", ("chromedriver_win64.zip", "chromedriver_win32.zip")),
    "Linux_x64": ("chrome-linux.zip", ("chromedriver_linux64.zip",)),
    # Apple Silicon is "Mac_Arm", not Mac_Arm64 — both ship the same archive
    # names, so only the platform prefix differs.
    "Mac": ("chrome-mac.zip", ("chromedriver_mac64.zip",)),
    "Mac_Arm": ("chrome-mac.zip", ("chromedriver_mac64.zip",)),
}


#: Where the bucket lists what it holds, as opposed to serving one file.
LISTING = "https://www.googleapis.com/storage/v1/b/chromium-browser-snapshots/o"

#: How far back to look for a complete snapshot, in commit positions. Builds
#: land every ten to thirty commits, so this is a handful of candidates.
LOOK_BACK = 400

#: Stop after this many candidates: if the newest few are all incomplete the
#: bucket is having a bad day, and forty HEAD requests will not fix it.
MAX_CANDIDATES = 8


def latest_revision(platform: str) -> str:
    with urllib.request.urlopen(f"{BASE}/{platform}/LAST_CHANGE", timeout=60) as response:
        return response.read().decode().strip()


def published(platform: str, revision: str, name: str) -> bool:
    """Whether this snapshot actually serves ``name`` yet."""
    request = urllib.request.Request(
        f"{BASE}/{platform}/{revision}/{name}", method="HEAD")
    try:
        urllib.request.urlopen(request, timeout=60)
        return True
    except Exception:  # noqa: BLE001 - a 404 is an answer, not a failure
        return False


def first_available(platform: str, revision: str, names) -> str:
    """The driver archive this snapshot publishes, or ``""`` if none does."""
    for name in names:
        if published(platform, revision, name):
            return name
    return ""


def recent_revisions(platform: str, ceiling: int, look_back: int = LOOK_BACK) -> list:
    """Snapshot revisions in ``[ceiling - look_back, ceiling]``, newest first.

    A revision number is a Chromium commit position, and the bucket keeps only
    the positions that were actually built — about one in twenty — so counting
    the number down would spend most of its requests on directories that never
    existed. Ask the bucket which ones are real instead.

    Returns an empty list if the listing API cannot be reached; the caller
    still has LAST_CHANGE to fall back on.
    """
    floor = max(0, ceiling - look_back)
    query = urllib.parse.urlencode({
        "delimiter": "/",
        "prefix": f"{platform}/",
        # Prefixes sort as text. Every revision in the window has the same
        # digit count, so within it the text order is the numeric order —
        # shorter, older numbers sort after and are dropped by the range test.
        "startOffset": f"{platform}/{floor}",
        "fields": "prefixes",
        "maxResults": "1000",
    })
    try:
        with urllib.request.urlopen(f"{LISTING}?{query}", timeout=60) as response:
            prefixes = json.load(response).get("prefixes", [])
    except Exception as exc:  # noqa: BLE001 - degrade to LAST_CHANGE alone
        print(f"  could not list {platform} snapshots ({type(exc).__name__})")
        return []

    revisions = set()
    for prefix in prefixes:
        digits = prefix.strip("/").rsplit("/", 1)[-1]
        if digits.isdigit() and floor <= int(digits) <= ceiling:
            revisions.add(int(digits))
    return sorted(revisions, reverse=True)


def usable_revision(platform: str, browser_zip: str, driver_names) -> tuple:
    """Return ``(revision, driver_zip)`` for the newest complete snapshot.

    LAST_CHANGE advances as soon as a build starts publishing, so the newest
    revision intermittently serves the browser but not yet the driver (or the
    other way round). A build that picks that moment fails on an upload race
    it had no part in — which platform loses is luck. So the newest revision
    is a candidate rather than a verdict, and the search falls back to the
    complete snapshot below it.
    """
    latest = latest_revision(platform)
    if not latest.isdigit():
        raise SystemExit(
            f"{platform}/LAST_CHANGE is not a revision number: {latest!r}")

    candidates = [int(latest)]
    candidates += [r for r in recent_revisions(platform, int(latest) - 1)
                   if r not in candidates]

    for revision in candidates[:MAX_CANDIDATES]:
        revision = str(revision)
        driver_zip = first_available(platform, revision, driver_names)
        if driver_zip and published(platform, revision, browser_zip):
            if revision != latest:
                print(f"  r{latest} is incomplete; falling back to r{revision}")
            return revision, driver_zip

    raise SystemExit(
        f"no complete {platform} snapshot at or below r{latest}: none of the "
        f"{len(candidates[:MAX_CANDIDATES])} newest publish {browser_zip} "
        f"plus one of {', '.join(driver_names)}")


def download(url: str, attempts: int = 4) -> bytes:
    """Fetch a large file, resuming where a dropped connection left off.

    These archives are hundreds of megabytes; a single read() that dies
    two thirds of the way through would otherwise fail the whole build.
    """
    print(f"  fetching {url}")
    buffer = bytearray()
    expected = None
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url)
        if buffer:
            request.add_header("Range", f"bytes={len(buffer)}-")
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                if expected is None:
                    length = response.headers.get("Content-Length")
                    expected = int(length) if length else None
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    buffer += chunk
        except Exception as exc:  # noqa: BLE001 - any transport failure retries
            print(f"    attempt {attempt} stopped at {len(buffer) / 1048576:.0f} MB"
                  f" ({type(exc).__name__}); resuming")
            if attempt == attempts:
                raise
            continue
        if expected is None or len(buffer) >= expected:
            break
        print(f"    short read: {len(buffer)}/{expected} bytes; resuming")
    print(f"    got {len(buffer) / 1048576:.0f} MB")
    return bytes(buffer)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", default="Win_x64", choices=sorted(ARCHIVES))
    parser.add_argument("--revision", default="", help="snapshot revision (default: latest)")
    args = parser.parse_args()

    browser_zip, driver_names = ARCHIVES[args.platform]
    if args.revision:
        # An explicitly named revision is a request, not a starting point:
        # take it or say why it cannot be used.
        revision = args.revision
        driver_zip = first_available(args.platform, revision, driver_names)
        if not driver_zip:
            raise SystemExit(
                f"{args.platform} r{revision} publishes none of "
                f"{', '.join(driver_names)}")
    else:
        revision, driver_zip = usable_revision(
            args.platform, browser_zip, driver_names)
    print(f"Chromium snapshot {args.platform} r{revision}")

    browser = download(f"{BASE}/{args.platform}/{revision}/{browser_zip}")
    driver = download(f"{BASE}/{args.platform}/{revision}/{driver_zip}")

    if PAYLOAD_DIR.exists():
        shutil.rmtree(PAYLOAD_DIR)
    PAYLOAD_DIR.mkdir(parents=True)

    # One archive holding both, plus a note of what is in it. Stored, not
    # deflated again: the two inputs are already compressed, and re-packing
    # them costs minutes for nothing.
    with zipfile.ZipFile(PAYLOAD, "w", zipfile.ZIP_STORED) as payload:
        payload.writestr("browser/manifest.json", json.dumps({
            "revision": revision,
            "platform": args.platform,
            "browser_archive": browser_zip,
            "driver_archive": driver_zip,
        }, indent=2))
        payload.writestr(f"browser/{browser_zip}", browser)
        payload.writestr(f"browser/{driver_zip}", driver)

    verify(PAYLOAD)
    size = PAYLOAD.stat().st_size / 1048576
    print(f"wrote {PAYLOAD.relative_to(ROOT.parent)} ({size:.0f} MB)")
    return 0


def verify(payload: Path) -> None:
    """Fail here rather than shipping an executable that cannot scrape.

    A truncated or half-written archive would otherwise be appended to the
    .exe and only reveal itself when someone pressed Start Scraping.
    """
    with zipfile.ZipFile(payload) as archive:
        broken = archive.testzip()
        if broken is not None:
            raise SystemExit(f"the payload is corrupt at {broken}")
        names = archive.namelist()
        manifest = json.loads(archive.read("browser/manifest.json"))

    browser = [n for n in names if "chrome-" in n and n.endswith(".zip")]
    driver = [n for n in names if "chromedriver" in n and n.endswith(".zip")]
    if not browser:
        raise SystemExit("the payload carries no browser archive")
    if not driver:
        raise SystemExit("the payload carries no chromedriver archive")
    print(f"  verified r{manifest['revision']}: "
          f"{Path(browser[0]).name} + {Path(driver[0]).name}")


if __name__ == "__main__":
    raise SystemExit(main())
