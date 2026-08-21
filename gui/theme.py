"""Colour tokens and the Qt stylesheet for the desktop app.

The palette is lifted straight from the product mockups: a deep-navy
navigation rail down the left, a light workspace to the right of it, white
cards with hairline borders, and a single blue accent for anything the user is
meant to press.
"""

from __future__ import annotations

# -- palette ---------------------------------------------------------------
NAVY = "#0F1B33"          # sidebar / title bar
NAVY_DEEP = "#0A1428"     # sidebar footer + hover wells
NAVY_LINE = "#1E2C48"     # dividers inside the sidebar
BLUE = "#2563EB"          # primary action
BLUE_DARK = "#1D4ED8"     # pressed / active nav pill
BLUE_SOFT = "#EFF4FF"     # selected table row, tab underline wash
CANVAS = "#F4F6FA"        # workspace background
CARD = "#FFFFFF"
BORDER = "#E2E8F0"
BORDER_STRONG = "#CBD5E1"
INK = "#0F172A"           # primary text
INK_SOFT = "#475569"      # secondary text
MUTED = "#7C8BA1"         # labels, captions
GREEN = "#16A34A"
GREEN_SOFT = "#E7F7EC"
AMBER = "#D97706"
RED = "#DC2626"
RED_SOFT = "#FDECEC"

# Fonts: Segoe UI is the Windows system face; the rest are fallbacks so the
# app still looks deliberate when it is run on macOS or Linux.
UI_FONT = '"Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif'
MONO_FONT = '"Cascadia Mono", "Consolas", "DejaVu Sans Mono", monospace'


def stylesheet() -> str:
    """Return the application-wide QSS."""
    return f"""
* {{
    font-family: {UI_FONT};
    font-size: 13px;
    color: {INK};
}}

QMainWindow, QWidget#Workspace {{
    background: {CANVAS};
}}

/* ---- sidebar ---------------------------------------------------------- */
QWidget#Sidebar {{
    background: {NAVY};
    border: none;
}}
QLabel#SidebarBrand {{
    color: #FFFFFF;
    font-size: 14px;
    font-weight: 700;
}}
QLabel#SidebarCaption, QLabel#SidebarStatus {{
    color: #8FA3C4;
    font-size: 11px;
}}
QFrame#SidebarRule {{
    background: {NAVY_LINE};
    max-height: 1px;
    border: none;
}}
QPushButton#NavItem {{
    background: transparent;
    border: none;
    border-radius: 7px;
    color: #C6D4EC;
    padding: 9px 12px;
    text-align: left;
    font-size: 13px;
}}
QPushButton#NavItem:hover {{
    background: {NAVY_DEEP};
    color: #FFFFFF;
}}
QPushButton#NavItem:checked {{
    background: {BLUE_DARK};
    color: #FFFFFF;
    font-weight: 600;
}}

/* ---- page furniture --------------------------------------------------- */
QLabel#PageTitle {{
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 0.4px;
    color: {INK};
}}
QFrame#Card {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QFrame#Card[flat="true"] {{
    background: {CANVAS};
}}
QLabel#CardTitle {{
    font-size: 12px;
    font-weight: 700;
    color: {INK};
}}
QLabel#FieldLabel {{
    font-size: 11px;
    color: {MUTED};
    font-weight: 600;
}}
QLabel#StatLabel {{
    font-size: 11px;
    color: {MUTED};
    font-weight: 600;
}}
QLabel#StatValue {{
    font-size: 14px;
    font-weight: 700;
    color: {INK};
}}
QLabel#StatValueGreen {{
    font-size: 14px;
    font-weight: 700;
    color: {GREEN};
}}
QLabel#Hint {{
    color: {MUTED};
    font-size: 11px;
}}
QLabel#Link {{
    color: {BLUE};
}}

/* ---- inputs ----------------------------------------------------------- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {CARD};
    border: 1px solid {BORDER_STRONG};
    border-radius: 6px;
    padding: 6px 9px;
    selection-background-color: {BLUE};
    selection-color: #FFFFFF;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {BLUE};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
    background: #F1F5F9;
    color: {MUTED};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {INK_SOFT};
    width: 0; height: 0;
    margin-right: 8px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    width: 16px;
    border: none;
    background: transparent;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-position: top right; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-position: bottom right; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: none; width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {INK_SOFT};
    margin-right: 6px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: none; width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {INK_SOFT};
    margin-right: 6px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: #EEF2F7;
    border-radius: 3px;
}}

QComboBox QAbstractItemView {{
    background: {CARD};
    border: 1px solid {BORDER_STRONG};
    selection-background-color: {BLUE_SOFT};
    selection-color: {INK};
    outline: none;
}}

/* ---- buttons ---------------------------------------------------------- */
QPushButton {{
    background: {CARD};
    border: 1px solid {BORDER_STRONG};
    border-radius: 6px;
    padding: 7px 14px;
    color: {INK};
}}
QPushButton:hover {{ background: #F8FAFC; }}
QPushButton:pressed {{ background: #EEF2F7; }}
QPushButton:disabled {{ color: #A2AEBF; background: #F1F5F9; border-color: {BORDER}; }}

QPushButton#Primary {{
    background: {BLUE};
    border: 1px solid {BLUE};
    color: #FFFFFF;
    font-weight: 600;
}}
QPushButton#Primary:hover {{ background: {BLUE_DARK}; border-color: {BLUE_DARK}; }}
QPushButton#Primary:disabled {{ background: #A9C0F0; border-color: #A9C0F0; color: #F2F6FF; }}

QPushButton#Success {{
    background: {GREEN};
    border: 1px solid {GREEN};
    color: #FFFFFF;
    font-weight: 600;
}}
QPushButton#Success:hover {{ background: #12833C; }}
QPushButton#Success:disabled {{ background: #A6DCB9; border-color: #A6DCB9; color: #F1FBF4; }}

QPushButton#Danger {{
    background: {RED};
    border: 1px solid {RED};
    color: #FFFFFF;
    font-weight: 600;
}}
QPushButton#Danger:hover {{ background: #B91C1C; }}
QPushButton#Danger:disabled {{ background: #EFAFAF; border-color: #EFAFAF; color: #FDF2F2; }}

/* ---- tabs ------------------------------------------------------------- */
QTabWidget::pane {{
    border: none;
    background: transparent;
}}
QTabBar {{ qproperty-drawBase: 0; }}
QTabBar::tab {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-bottom: 2px solid {BORDER};
    padding: 7px 16px;
    margin-right: 4px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    color: {INK_SOFT};
}}
QTabBar::tab:selected {{
    color: {BLUE};
    border-bottom: 2px solid {BLUE};
    background: {BLUE_SOFT};
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{ background: #F8FAFC; }}

/* ---- tables ----------------------------------------------------------- */
QTableWidget, QTableView {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    gridline-color: {BORDER};
    selection-background-color: {BLUE_SOFT};
    selection-color: {INK};
    alternate-background-color: #FAFBFD;
}}
QTableWidget::item, QTableView::item {{
    padding: 5px 6px;
    border: none;
}}
QHeaderView::section {{
    background: #F8FAFC;
    color: {INK_SOFT};
    padding: 7px 6px;
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    font-weight: 600;
    font-size: 11px;
}}
QTableCornerButton::section {{
    background: #F8FAFC;
    border: none;
    border-bottom: 1px solid {BORDER};
}}

/* ---- progress --------------------------------------------------------- */
QProgressBar {{
    background: #E8EDF5;
    border: none;
    border-radius: 6px;
    height: 12px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {GREEN};
    border-radius: 6px;
}}
QProgressBar#Blue::chunk {{ background: {BLUE}; }}

/* ---- log view --------------------------------------------------------- */
QPlainTextEdit#Log {{
    background: #FBFCFE;
    border: 1px solid {BORDER};
    border-radius: 6px;
    font-family: {MONO_FONT};
    font-size: 11px;
    color: {INK_SOFT};
}}

/* ---- misc ------------------------------------------------------------- */
QCheckBox {{ spacing: 7px; color: {INK_SOFT}; }}
QCheckBox::indicator {{
    width: 14px; height: 14px;
    border: 1px solid {BORDER_STRONG};
    border-radius: 3px;
    background: {CARD};
}}
QCheckBox::indicator:checked {{
    background: {BLUE};
    border-color: {BLUE};
    image: none;
}}
QCheckBox::indicator:disabled {{ background: #EDF1F7; }}

QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #C7D2E0; border-radius: 5px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: #AEBCCE; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: #C7D2E0; border-radius: 5px; min-width: 24px;
}}
QToolTip {{
    background: {NAVY};
    color: #FFFFFF;
    border: none;
    padding: 5px 8px;
}}
QSplitter::handle {{ background: transparent; }}
"""
