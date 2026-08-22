#!/usr/bin/env python3
"""Download the chromedriver that ships inside the executable.

Selenium fetches a driver over the network on first use ("Selenium Manager").
That is a download the user did not ask for, needs internet for, and cannot do
behind a locked-down network — so the build puts one in the bundle instead.

Run before PyInstaller:

    python packaging/fetch_chromedriver.py            # host platform
    python packaging/fetch_chromedriver.py --platform win64

The driver lands in packaging/drivers/, which the spec bundles and
gui/runtime.py puts on PATH at startup.
"""

from __future__ import annotations

import argparse
import io
import json
import platform
import stat
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DRIVERS = ROOT / "drivers"
INDEX = ("https://googlechromelabs.github.io/chrome-for-testing/"
         "last-known-good-versions-with-downloads.json")

#: Chrome for Testing's platform names, keyed by what Python reports.
PLATFORMS = {
    ("Windows", "64bit"): "win64",
    ("Windows", "32bit"): "win32",
    ("Linux", "64bit"): "linux64",
    ("Darwin", "arm64"): "mac-arm64",
    ("Darwin", "64bit"): "mac-x64",
}


def host_platform() -> str:
    system = platform.system()
    if system == "Darwin":
        return "mac-arm64" if platform.machine() == "arm64" else "mac-x64"
    bits = "64bit" if sys.maxsize > 2**32 else "32bit"
    return PLATFORMS.get((system, bits), "linux64")


def driver_url(target: str) -> tuple[str, str]:
    """The download URL for the current stable driver, and its version."""
    with urllib.request.urlopen(INDEX, timeout=60) as response:
        data = json.load(response)
    stable = data["channels"]["Stable"]
    for entry in stable["downloads"]["chromedriver"]:
        if entry["platform"] == target:
            return entry["url"], stable["version"]
    raise SystemExit(f"Chrome for Testing publishes no chromedriver for {target}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", default=host_platform(),
                        help="Chrome for Testing platform name (default: this machine)")
    args = parser.parse_args()

    url, version = driver_url(args.platform)
    print(f"chromedriver {version} for {args.platform}")
    with urllib.request.urlopen(url, timeout=300) as response:
        payload = response.read()

    DRIVERS.mkdir(parents=True, exist_ok=True)
    written = []
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for member in archive.namelist():
            name = Path(member).name
            if not name.startswith("chromedriver"):
                continue
            target = DRIVERS / name
            target.write_bytes(archive.read(member))
            # The bundled copy has to stay executable on macOS and Linux.
            target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP)
            written.append(target)

    if not written:
        raise SystemExit("the archive contained no chromedriver binary")
    for target in written:
        print(f"  wrote {target.relative_to(ROOT.parent)} "
              f"({target.stat().st_size / 1048576:.1f} MB)")
    (DRIVERS / "VERSION").write_text(version + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
