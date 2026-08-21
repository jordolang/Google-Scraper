#!/usr/bin/env python3
"""Render the app icon (.ico + .png) from the same mark the sidebar draws.

Run from the repo root:  python packaging/make_icon.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from gui import theme  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)


def draw(size: int) -> QPixmap:
    """A rounded navy tile with the blue mark on it — legible at 16px."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(theme.NAVY))
    radius = max(2, size // 6)
    painter.drawRoundedRect(0, 0, size, size, radius, radius)

    painter.setBrush(QColor(theme.BLUE))
    inset = max(2, round(size * 0.18))
    painter.drawEllipse(inset, inset, size - inset * 2, size - inset * 2)

    painter.setBrush(QColor("#FFFFFF"))
    dot = max(2, round(size * 0.24))
    painter.drawEllipse((size - dot) // 2, (size - dot) // 2, dot, dot)
    painter.end()
    return pixmap


def png_bytes(size: int) -> bytes:
    """The mark at one size, PNG-encoded."""
    from PySide6.QtCore import QBuffer

    buffer = QBuffer()
    buffer.open(QBuffer.ReadWrite)
    draw(size).save(buffer, "PNG")
    return bytes(buffer.data())


def write_ico(path: Path, sizes=SIZES) -> None:
    """Pack every size into one .ico.

    Qt's ICO writer only stores a single image, which Windows then scales — so
    the taskbar and Alt-Tab icons come out mushy. An .ico is just a directory
    of images, and Windows has read PNG-compressed entries since Vista, so the
    file is assembled here instead.
    """
    import struct

    images = [(size, png_bytes(size)) for size in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))  # reserved, type=icon, count
    offset = len(header) + 16 * len(images)
    entries, payload = b"", b""
    for size, data in images:
        entries += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,  # 0 means 256
            0 if size >= 256 else size,
            0, 0,      # palette size, reserved
            1, 32,     # colour planes, bits per pixel
            len(data), offset,
        )
        payload += data
        offset += len(data)
    path.write_bytes(header + entries + payload)


def main() -> int:
    app = QApplication.instance() or QApplication([])
    out_dir = Path(__file__).resolve().parent
    draw(256).save(str(out_dir / "app_icon.png"), "PNG")
    write_ico(out_dir / "app_icon.ico")
    print(f"wrote {out_dir / 'app_icon.ico'} and {out_dir / 'app_icon.png'}")
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
