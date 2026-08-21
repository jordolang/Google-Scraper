#!/usr/bin/env python3
"""Launch the Windows desktop app.

    python run_gui.py            # the app
    python run_gui.py --demo     # sample data: no browser, network or SMTP
    python run_gui.py --selftest # build every screen offscreen and exit

This is also the entry point PyInstaller bundles. It uses absolute imports on
purpose: a frozen script runs as ``__main__`` with no package around it, so
``python -m gui``'s relative imports are not available to it.
"""

import sys
from pathlib import Path

# Running from a checkout, make sure the repo root is importable however the
# script was invoked.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gui.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
