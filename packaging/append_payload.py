#!/usr/bin/env python3
"""Append the browser payload to the built executable.

PyInstaller's one-file mode unpacks everything it bundles to a temp folder on
*every* launch, so putting a few hundred megabytes of browser in `datas` would
add a long pause to each start. Appending it instead leaves the executable's
own startup untouched — the app reads the archive out of its own file and
unpacks the browser once, the first time it needs to drive one.

Zip tolerates data in front of it (the central directory is found from the
end), and PyInstaller's bootloader is unaffected by data after its archive, so
the two live in one file happily.

    python packaging/append_payload.py dist/LocalLeadScraperPro.exe
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "browser" / "browser-payload.zip"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--payload", type=Path, default=PAYLOAD)
    args = parser.parse_args()

    if not args.executable.exists():
        print(f"no executable at {args.executable}", file=sys.stderr)
        return 1
    if not args.payload.exists():
        print(f"no payload at {args.payload} — run fetch_chromium.py first",
              file=sys.stderr)
        return 1

    before = args.executable.stat().st_size
    with args.executable.open("ab") as exe, args.payload.open("rb") as payload:
        shutil.copyfileobj(payload, exe, 1024 * 1024)
    after = args.executable.stat().st_size

    # Prove it reads back, rather than discovering it on a user's machine.
    with zipfile.ZipFile(args.executable) as archive:
        names = archive.namelist()
    if not any(name.startswith("browser/") for name in names):
        print("the appended payload is not readable from the executable",
              file=sys.stderr)
        return 1

    print(f"{args.executable.name}: {before / 1048576:.0f} MB -> "
          f"{after / 1048576:.0f} MB, carrying {len(names)} payload entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
