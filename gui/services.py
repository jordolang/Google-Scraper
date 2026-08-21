"""Glue between the Qt pages and the existing scraping / outreach code.

The GUI never imports Selenium or smtplib itself. Everything goes through
:class:`tui.pipeline.Pipeline`, which is already the seam the terminal UI uses,
so both front ends stay on exactly the same code path.
"""

from __future__ import annotations

import csv
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

from tui.pipeline import DemoPipeline, LivePipeline, Pipeline

from . import runtime


class GuiLivePipeline(LivePipeline):
    """Live pipeline that honours the "max results" cap while scraping.

    ``LivePipeline`` opens every listing the feed scrolls up. When the user
    asks for 50 per industry there is no point paying for the other 150, so the
    URL collection is trimmed before the detail pass starts.
    """

    def _scrape_with_progress(self, scraper, max_scrolls, progress, businesses=None,
                              on_business=None) -> None:
        if self.max_results > 0:
            collect = scraper._collect_all_business_urls
            limit = self.max_results
            scraper._collect_all_business_urls = lambda: collect()[:limit]
        kwargs = {} if on_business is None else {"on_business": on_business}
        return super()._scrape_with_progress(
            scraper, max_scrolls, progress, businesses, **kwargs
        )


def data_root_for(settings: Dict) -> Optional[Path]:
    """Where this run's CSVs belong.

    An explicit export folder wins. Otherwise demo runs go to ``data/_demo``
    so sample rows never mix with real scrapes, and live runs fall through to
    data_store's own default.
    """
    configured = (settings.get("data_root") or "").strip()
    if configured:
        base = Path(configured)
        return base / "_demo" if settings.get("demo_mode") else base
    if settings.get("demo_mode"):
        import data_store

        return data_store.data_root() / "_demo"
    return None


def make_pipeline(settings: Dict) -> Pipeline:
    """Build the pipeline the current settings ask for."""
    kwargs = {
        "from_email": settings.get("from_email") or "jordan@jlang.dev",
        "headless": bool(settings.get("headless", True)),
        "data_root": data_root_for(settings),
        # Packaged builds keep their editable copies outside the bundle.
        "templates_dir": str(runtime.user_asset("email_templates")),
        "template_path": str(runtime.user_asset("email_template.html")),
        # Without these a campaign would authenticate against whatever the
        # From: address implies, even though Settings says otherwise — and the
        # connection test, which does use them, would still pass.
        "smtp_server": settings.get("smtp_server") or None,
        "smtp_port": int(settings.get("smtp_port") or 0) or None,
        "smtp_username": settings.get("smtp_username") or None,
        "reply_to": settings.get("reply_to") or "",
        "scan_delay": float(settings.get("scan_delay") or 1.0),
        "max_results": int(settings.get("max_results") or 0),
    }
    if settings.get("demo_mode"):
        return DemoPipeline(**kwargs)
    return GuiLivePipeline(**kwargs)


def scroll_budget(max_results: int) -> int:
    """How many feed scrolls it takes to surface ``max_results`` listings."""
    if max_results <= 0:
        return 8
    # Google Maps loads roughly ten cards per scroll.
    return max(3, min(30, -(-max_results // 10) + 2))


def split_industries(text: str) -> List[str]:
    """Split the dashboard's industry field into individual search terms.

    Accepts a comma- or newline-separated list so one run can sweep several
    trades — "Roofing Contractors, Plumbers, Electricians".
    """
    parts = re.split(r"[,\n]", text or "")
    seen: List[str] = []
    for part in parts:
        cleaned = " ".join(part.split())
        if cleaned and cleaned.lower() not in {s.lower() for s in seen}:
            seen.append(cleaned)
    return seen


def available_templates(templates_dir: Optional[str] = None) -> List[Tuple[str, str]]:
    """(label, industry key) for every industry template on disk."""
    import industries

    found: List[Tuple[str, str]] = []
    directory = Path(templates_dir) if templates_dir else runtime.user_asset("email_templates")
    for industry in industries.all_industries():
        if (directory / f"{industry.key}.html").exists():
            found.append((industry.label, industry.key))
    if not found:  # templates dir missing (e.g. a stripped install)
        found = [(i.label, i.key) for i in industries.all_industries()]
    return found


# -- exports ---------------------------------------------------------------
def export_csv(path: Path, headers: Sequence[str], rows: Iterable[Sequence]) -> Path:
    """Write a UTF-8 CSV Excel opens cleanly (BOM keeps accents intact)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(list(headers))
        for row in rows:
            writer.writerow(["" if cell is None else str(cell) for cell in row])
    return path


def _col_name(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    name = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def export_xlsx(path: Path, headers: Sequence[str], rows: Iterable[Sequence],
                sheet_name: str = "Leads") -> Path:
    """Write a real .xlsx with nothing but the standard library.

    Excel export should keep working inside a packaged .exe, so rather than
    pulling in openpyxl this writes the handful of XML parts a spreadsheet
    needs: every cell is an inline string, which Excel, LibreOffice and Google
    Sheets all read.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = [list(headers)] + [list(row) for row in rows]

    body = []
    for r, row in enumerate(table, start=1):
        cells = []
        for c, value in enumerate(row):
            text = "" if value is None else str(value)
            cells.append(
                f'<c r="{_col_name(c)}{r}" t="inlineStr" s="{1 if r == 1 else 0}">'
                f"<is><t xml:space=\"preserve\">{escape(text)}</t></is></c>"
            )
        body.append(f'<row r="{r}">{"".join(cells)}</row>')

    widths = "".join(
        f'<col min="{i + 1}" max="{i + 1}" width="{_width_for(table, i)}" customWidth="1"/>'
        for i in range(len(headers))
    )
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<cols>{widths}</cols><sheetData>{"".join(body)}</sheetData></worksheet>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{escape(sheet_name[:31] or "Sheet1")}" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="1"><border/></borders>'
        '<cellStyleXfs count="1"><xf/></cellStyleXfs>'
        '<cellXfs count="2"><xf xfId="0"/><xf xfId="0" fontId="1" applyFont="1"/></cellXfs>'
        "</styleSheet>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        "</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    book_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as book:
        book.writestr("[Content_Types].xml", content_types)
        book.writestr("_rels/.rels", root_rels)
        book.writestr("xl/workbook.xml", workbook)
        book.writestr("xl/_rels/workbook.xml.rels", book_rels)
        book.writestr("xl/styles.xml", styles)
        book.writestr("xl/worksheets/sheet1.xml", sheet)
    return path


def _width_for(table: List[List], column: int) -> int:
    widest = 0
    for row in table[:200]:  # a sample is enough to size a column
        if column < len(row):
            widest = max(widest, len(str(row[column] or "")))
    return max(10, min(48, widest + 2))


def suggested_filename(prefix: str, extension: str) -> str:
    return f"{prefix}_{datetime.now():%Y%m%d_%H%M%S}.{extension}"


def default_export_dir(settings: Optional[Dict] = None) -> Path:
    """Where the Save dialogs should open."""
    if settings and settings.get("data_root"):
        return Path(settings["data_root"])
    import data_store

    try:
        return data_store.data_root()
    except Exception:  # pragma: no cover - depends on cwd permissions
        return Path.home()
