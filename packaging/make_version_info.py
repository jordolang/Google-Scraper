#!/usr/bin/env python3
"""Regenerate packaging/version_info.txt from the VERSION file.

The Windows VERSIONINFO resource wants a four-part numeric version, while the
project versions itself as "1.2" / "1.2a", so the letter suffix is dropped and
the rest is zero-padded.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = '''# Windows VERSIONINFO resource for LocalLeadScraperPro.exe.
# Regenerate with: python packaging/make_version_info.py
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={quad},
    prodvers={quad},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        "040904B0",
        [StringStruct("CompanyName", "Jlang.dev"),
         StringStruct("FileDescription", "Local Lead Scraper Pro"),
         StringStruct("FileVersion", "{version}"),
         StringStruct("InternalName", "LocalLeadScraperPro"),
         StringStruct("LegalCopyright", "MIT licensed"),
         StringStruct("OriginalFilename", "LocalLeadScraperPro.exe"),
         StringStruct("ProductName", "Local Lead Scraper Pro"),
         StringStruct("ProductVersion", "{version}")])
    ]),
    VarFileInfo([VarStruct("Translation", [1033, 1200])])
  ]
)
'''


def version_quad(version: str) -> tuple:
    digits = "".join(char if char.isdigit() else "." for char in version)
    parts = [int(part) for part in digits.split(".") if part]
    parts += [0] * (4 - len(parts))
    return tuple(parts[:4])


def main() -> int:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip() or "0.0"
    out = ROOT / "packaging" / "version_info.txt"
    out.write_text(
        TEMPLATE.format(quad=version_quad(version), version=version), encoding="utf-8")
    print(f"wrote {out} for version {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
