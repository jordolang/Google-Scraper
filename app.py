#!/usr/bin/env python3
"""Unified launcher for the Jlang.dev outreach suite.

    python app.py                 # home screen: pick a tool
    python app.py --start cockpit # jump straight to the call cockpit
    python app.py --demo          # pipeline uses sample data

See ``python app.py --help`` for all options.
"""

from tui.app import main

if __name__ == "__main__":
    main()
