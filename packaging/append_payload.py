#!/usr/bin/env python3
"""Put the browser payload into the built app, without slowing its startup.

PyInstaller's one-file mode unpacks everything it bundles to a temp folder on
*every* launch, so putting a few hundred megabytes of browser in `datas` would
add a long pause to each start. Carrying it separately leaves the executable's
own startup untouched — the app reads the archive and unpacks the browser
once, the first time it needs to drive one.

Where it goes depends on the platform:

* Windows ships one file, so the payload is appended to the .exe. Zip tolerates
  data in front of it (the central directory is found from the end), and
  PyInstaller's bootloader ignores data after its own archive, so the two live
  in one file happily.
* macOS ships a .app, which is a directory, so the payload is simply a file in
  `Contents/Resources`. Appending to the Mach-O would work but leave the code
  signature covering only part of the file; codesign cannot be re-run to repair
  that, because signing rewrites the binary and drops anything trailing it. A
  resource is sealed by the signature instead, so the bundle stays valid.

    python packaging/append_payload.py dist/LocalLeadScraperPro.exe
    python packaging/append_payload.py "dist/Local Lead Scraper Pro.app"
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "browser" / "browser-payload.zip"

#: The name the payload keeps inside a .app. gui/runtime.py looks for this.
BUNDLE_PAYLOAD_NAME = "browser-payload.zip"


def carries_browser(path: Path) -> bool:
    """Whether the payload can be read back out of `path`."""
    try:
        with zipfile.ZipFile(path) as archive:
            return any(n.startswith("browser/") for n in archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return False


def resign(bundle: Path) -> None:
    """Ad-hoc sign the bundle so the payload is sealed in with everything else.

    Apple Silicon will not run a binary whose signature does not match what is
    on disk, and adding a resource changes the bundle. Signing last is what
    keeps the two in step; `-` is an ad-hoc identity, which is all an unsigned
    app needs to launch once the user has cleared Gatekeeper.
    """
    subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", str(bundle)],
        check=True,
    )
    subprocess.run(
        ["codesign", "--verify", "--deep", str(bundle)], check=True,
    )
    print(f"signed {bundle.name} ad-hoc, with the payload sealed in")


def into_bundle(bundle: Path, payload: Path) -> int:
    """Carry the payload as a bundle resource, then re-sign."""
    resources = bundle / "Contents" / "Resources"
    resources.mkdir(parents=True, exist_ok=True)
    target = resources / BUNDLE_PAYLOAD_NAME
    shutil.copyfile(payload, target)

    if not carries_browser(target):
        print(f"the payload at {target} is not readable", file=sys.stderr)
        return 1

    if sys.platform == "darwin":
        resign(bundle)

    size = target.stat().st_size / 1048576
    print(f"{bundle.name}: carrying {target.name} ({size:.0f} MB) "
          f"in Contents/Resources")
    return 0


def onto_executable(executable: Path, payload: Path) -> int:
    """Append the payload to a single-file executable."""
    before = executable.stat().st_size
    with executable.open("ab") as exe, payload.open("rb") as data:
        shutil.copyfileobj(data, exe, 1024 * 1024)
    after = executable.stat().st_size

    # Prove it reads back, rather than discovering it on a user's machine.
    if not carries_browser(executable):
        print("the appended payload is not readable from the executable",
              file=sys.stderr)
        return 1

    print(f"{executable.name}: {before / 1048576:.0f} MB -> "
          f"{after / 1048576:.0f} MB with the browser appended")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--payload", type=Path, default=PAYLOAD)
    args = parser.parse_args()

    if not args.payload.exists():
        print(f"no payload at {args.payload} — run fetch_chromium.py first",
              file=sys.stderr)
        return 1

    target = args.executable
    if target.suffix == ".app" and target.is_dir():
        return into_bundle(target, args.payload)
    if not target.exists():
        print(f"no executable at {target}", file=sys.stderr)
        return 1
    return onto_executable(target, args.payload)


if __name__ == "__main__":
    raise SystemExit(main())
