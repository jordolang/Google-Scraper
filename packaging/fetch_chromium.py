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
    "Mac": ("chrome-mac.zip", ("chromedriver_mac64.zip",)),
}


def latest_revision(platform: str) -> str:
    with urllib.request.urlopen(f"{BASE}/{platform}/LAST_CHANGE", timeout=60) as response:
        return response.read().decode().strip()


def first_available(platform: str, revision: str, names) -> str:
    """The driver archive this snapshot actually publishes."""
    for name in names:
        url = f"{BASE}/{platform}/{revision}/{name}"
        try:
            request = urllib.request.Request(url, method="HEAD")
            urllib.request.urlopen(request, timeout=60)
            return name
        except Exception:  # noqa: BLE001 - a 404 just means try the next name
            continue
    raise SystemExit(
        f"{platform} r{revision} publishes none of {', '.join(names)}")


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

    revision = args.revision or latest_revision(args.platform)
    browser_zip, driver_names = ARCHIVES[args.platform]
    print(f"Chromium snapshot {args.platform} r{revision}")

    driver_zip = first_available(args.platform, revision, driver_names)
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

    size = PAYLOAD.stat().st_size / 1048576
    print(f"wrote {PAYLOAD.relative_to(ROOT.parent)} ({size:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
