# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Local Lead Scraper Pro desktop app.

Build from the repo root on Windows:

    pip install -r requirements.txt -r requirements-gui.txt pyinstaller
    python packaging/make_icon.py
    pyinstaller --clean --noconfirm packaging/LocalLeadScraperPro.spec

The result is a single file, ``dist/LocalLeadScraperPro.exe``, that needs no
Python install on the target machine. Google Chrome is still required for live
scraping — Selenium drives the user's own browser.
"""

import os

from PyInstaller.utils.hooks import collect_submodules

SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
ROOT = os.path.dirname(SPEC_DIR)


def rooted(*parts):
    return os.path.join(ROOT, *parts)


# Assets the app reads at runtime. The editable ones are copied out to
# %LOCALAPPDATA%\LocalLeadScraperPro on first launch (see gui/runtime.py).
datas = [
    (rooted("email_templates"), "email_templates"),
    (rooted("email_template.html"), "."),
    (rooted("pitch_script.md"), "."),
    (rooted("VERSION"), "."),
]
datas = [(src, dest) for src, dest in datas if os.path.exists(src)]

# The pipeline imports the scraping stack lazily, inside functions, so name the
# packages explicitly rather than relying on the import graph.
#
# Selenium has to be collected whole, not listed submodule by submodule.
# Since 4.x it resolves its driver classes through a lazy string map:
#
#     "ChromeOptions": ("selenium.webdriver.chrome.options", "Options"),
#
# Those are strings in a dict, resolved by __getattr__ at call time, so
# PyInstaller's static analysis cannot see them. Naming a couple of submodules
# by hand produced a build that launched fine and then died with
# "No module named 'selenium.webdriver.chrome.options'" the moment anyone
# pressed Start Scraping. collect_submodules is what makes that impossible.
hiddenimports = (
    collect_submodules("selenium")
    + collect_submodules("bs4")
    + collect_submodules("salescall")
    + [
        "lxml",
        "lxml.etree",
        "lxml._elementpath",
        "soupsieve",
        "dotenv",
        # The project's own modules, imported lazily by tui/pipeline.py and the
        # GUI pages so the app can start without a browser driver present.
        "contact_scraper",
        "google_maps_scraper",
        "phone_lookup",
        "generate_emails",
        "send_emails",
        "data_store",
        "industries",
        "pricing_store",
        "email_config",
        "tui.pitch_script",
        # Stdlib reached for only when a feature runs: sending, exporting,
        # previewing.
        "smtplib",
        "email.mime.multipart",
        "email.mime.text",
        "zipfile",
        "webbrowser",
    ]
)

# Nothing here is used by the GUI, and each one costs megabytes.
# Only the clearly-unused ones: the GUI is QtCore/QtGui/QtWidgets, and Qt's
# own core modules are left alone so the bootloader keeps every DLL it needs.
excludes = [
    "textual", "rich", "tkinter", "pytest", "matplotlib", "numpy", "pandas",
    "PIL", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick", "PySide6.QtQuick", "PySide6.QtQuick3D",
    "PySide6.QtQml", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtBluetooth", "PySide6.QtDesigner",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets",
]

a = Analysis(
    [rooted("run_gui.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="LocalLeadScraperPro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,               # a GUI app must not flash a console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(SPEC_DIR, "app_icon.ico"),
    version=os.path.join(SPEC_DIR, "version_info.txt"),
)
