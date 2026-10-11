#!/usr/bin/env python3
"""Pack the Mac app into a drag-to-install .dmg.

Run on a Mac after PyInstaller (and append_payload.py) have built the bundle::

    python packaging/make_dmg.py "dist/Local Lead Scraper Pro.app" out.dmg

The disk image opens to a window with the app on the left, an Applications
shortcut on the right, an arrow between them, and the first-launch steps for
an app that isn't from the App Store printed underneath. ``create-dmg`` (from
Homebrew) lays the window out; if it is missing or Finder won't cooperate, a
plain image with the same contents is made instead, so a build never fails
over cosmetics.

``--background-only out.png`` just renders the background, which works on any
platform (it is how the tests and the README screenshot make it).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

VOLUME = "Local Lead Scraper Pro"
WIDTH, HEIGHT = 660, 440
ICON_SIZE = 112
APP_POS = (165, 190)
APPS_POS = (495, 190)

#: Shown under the icons. macOS 15 dropped the right-click → Open shortcut for
#: apps that aren't notarised, so the steps go through Privacy & Security.
FIRST_LAUNCH = (
    "First launch: open the app once, click Done, then go to",
    "System Settings → Privacy & Security and click Open Anyway.",
)


def render_background(path: Path, scale: int = 1) -> Path:
    """Draw the window background (and a @2x copy when ``scale`` is 2)."""
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
    from PySide6.QtWidgets import QApplication

    from gui import theme

    app = QApplication.instance() or QApplication([])  # noqa: F841 - fonts need it
    image = QImage(WIDTH * scale, HEIGHT * scale, QImage.Format_ARGB32)
    image.fill(QColor("#F8FAFC"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(scale, scale)

    # A navy band across the top with the app's name.
    painter.fillRect(QRectF(0, 0, WIDTH, 64), QColor(theme.NAVY))
    title = QFont()
    title.setPixelSize(22)
    title.setBold(True)
    painter.setFont(title)
    painter.setPen(QColor("#FFFFFF"))
    painter.drawText(QRectF(0, 0, WIDTH, 64), Qt.AlignCenter, VOLUME)

    # The arrow from the app to Applications.
    pen = QPen(QColor(theme.BLUE), 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    start = QPointF(APP_POS[0] + ICON_SIZE / 2 + 24, APP_POS[1])
    end = QPointF(APPS_POS[0] - ICON_SIZE / 2 - 24, APP_POS[1])
    painter.drawLine(start, end)
    head = QPainterPath()
    head.moveTo(end + QPointF(-16, -12))
    head.lineTo(end)
    head.lineTo(end + QPointF(-16, 12))
    painter.drawPath(head)

    hint = QFont()
    hint.setPixelSize(15)
    hint.setBold(True)
    painter.setFont(hint)
    painter.setPen(QColor("#0F172A"))
    painter.drawText(QRectF(0, 285, WIDTH, 24), Qt.AlignCenter,
                     "Drag the app onto Applications to install")

    small = QFont()
    small.setPixelSize(12)
    painter.setFont(small)
    painter.setPen(QColor("#475569"))
    for index, line in enumerate(FIRST_LAUNCH):
        painter.drawText(QRectF(0, 350 + index * 20, WIDTH, 20), Qt.AlignCenter, line)
    painter.end()

    path.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(path)):
        raise RuntimeError(f"could not write {path}")
    return path


def _plain_dmg(app: Path, out: Path, readme: Path) -> None:
    """A dmg with the app, an Applications link and the read-me; no layout."""
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / VOLUME
        stage.mkdir()
        subprocess.run(["ditto", str(app), str(stage / app.name)], check=True)
        (stage / "Applications").symlink_to("/Applications")
        shutil.copy(readme, stage / readme.name)
        subprocess.run(["hdiutil", "create", "-volname", VOLUME, "-srcfolder",
                        str(stage), "-ov", "-format", "UDZO", str(out)], check=True)


def write_readme(folder: Path) -> Path:
    readme = folder / "Read Me First.txt"
    readme.write_text(
        f"{VOLUME}\n\n"
        "1. Drag the app onto the Applications folder.\n"
        "2. Open it from Applications. macOS says it can't check the app; click Done.\n"
        "3. Open System Settings → Privacy & Security, scroll down, and click\n"
        "   Open Anyway next to the app's name. Confirm with your password.\n\n"
        "You only do this once. The app is free and isn't from the App Store,\n"
        "which is why macOS asks.\n",
        encoding="utf-8")
    return readme


def make_dmg(app: Path, out: Path) -> Path:
    if not app.is_dir():
        raise SystemExit(f"{app} is not an app bundle")
    out.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        background = render_background(tmp / "background.png")
        readme = write_readme(tmp)
        tool = shutil.which("create-dmg")
        if tool:
            stage = tmp / "stage"
            stage.mkdir()
            subprocess.run(["ditto", str(app), str(stage / app.name)], check=True)
            # The steps are printed on the background, so no read-me icon
            # crowds the window here.
            command = [
                tool, "--volname", VOLUME,
                "--background", str(background),
                "--window-pos", "200", "120",
                "--window-size", str(WIDTH), str(HEIGHT + 28),
                "--icon-size", str(ICON_SIZE),
                "--text-size", "13",
                "--icon", app.name, *map(str, APP_POS),
                "--hide-extension", app.name,
                "--app-drop-link", *map(str, APPS_POS),
                "--no-internet-enable",
                str(out), str(stage),
            ]
            result = subprocess.run(command)
            if result.returncode == 0 and out.exists():
                return out
            print("create-dmg could not lay the window out; making a plain dmg",
                  file=sys.stderr)
            out.unlink(missing_ok=True)
        _plain_dmg(app, out, readme)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("app", nargs="?", help="path to the .app bundle")
    parser.add_argument("out", nargs="?", help="the .dmg to write")
    parser.add_argument("--background-only", metavar="PNG",
                        help="just render the window background to PNG")
    args = parser.parse_args(argv)
    if args.background_only:
        print(render_background(Path(args.background_only)))
        return 0
    if not (args.app and args.out):
        parser.error("give the .app bundle and the .dmg to write")
    print(make_dmg(Path(args.app), Path(args.out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
