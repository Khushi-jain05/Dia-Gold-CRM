"""Application theme - palette and Qt style sheet.

A warm 'gold on charcoal' look that fits a jewellery brand, applied globally so
the app looks identical on macOS and Windows.
"""
from __future__ import annotations

# Palette ---------------------------------------------------------------
GOLD = "#C9A227"
GOLD_DARK = "#A9861B"
GOLD_SOFT = "#F3E9C6"
INK = "#20222B"          # sidebar / headers
INK_2 = "#2B2E39"        # sidebar hover
CANVAS = "#F4F5F7"       # main background
CARD = "#FFFFFF"
BORDER = "#E2E4EA"
TEXT = "#2C2E36"
MUTED = "#8A8F9C"
DANGER = "#C0392B"

APP_QSS = f"""
* {{
    font-family: "Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    color: {TEXT};
}}

QMainWindow, QWidget#Content {{
    background: {CANVAS};
}}

/* ---- Sidebar ---- */
QWidget#Sidebar {{
    background: {INK};
    border: none;
}}
QLabel#Brand {{
    color: #FFFFFF;
    font-size: 18px;
    font-weight: 800;
    padding: 18px 18px 2px 18px;
}}
QLabel#BrandSub {{
    color: {GOLD};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    padding: 0 18px 14px 18px;
}}
QLineEdit#NavSearch {{
    background: {INK_2};
    border: 1px solid #3A3D4A;
    border-radius: 8px;
    padding: 7px 10px;
    color: #FFFFFF;
    margin: 0 12px 8px 12px;
}}
QLineEdit#NavSearch:focus {{ border: 1px solid {GOLD}; }}

QTreeWidget#Nav {{
    background: transparent;
    border: none;
    outline: 0;
    padding: 4px 6px;
}}
QTreeWidget#Nav::item {{
    color: #C9CCD6;
    padding: 7px 6px;
    border-radius: 7px;
    margin: 1px 4px;
}}
QTreeWidget#Nav::item:hover {{ background: {INK_2}; color: #FFFFFF; }}
QTreeWidget#Nav::item:selected {{ background: {GOLD}; color: {INK}; font-weight: 700; }}
QTreeWidget#Nav::branch {{ background: transparent; }}
QTreeWidget#Nav QTreeView::branch:has-children:!has-siblings:closed,
QTreeWidget#Nav QTreeView::branch:closed:has-children:has-siblings {{ image: none; }}

QLabel#NavGroup {{
    color: {MUTED};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
    padding: 14px 18px 4px 18px;
}}

/* ---- Top bar ---- */
QWidget#TopBar {{
    background: {CARD};
    border-bottom: 1px solid {BORDER};
}}
QLabel#Crumb {{ font-size: 15px; font-weight: 700; }}
QLabel#UserChip {{
    color: {MUTED};
    padding-right: 6px;
}}

/* ---- Buttons ---- */
QPushButton {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 14px;
    font-weight: 600;
}}
QPushButton:hover {{ border-color: {GOLD}; }}
QPushButton:disabled {{ color: {MUTED}; background: #F0F0F2; }}
QPushButton#Primary {{
    background: {GOLD};
    border: 1px solid {GOLD_DARK};
    color: {INK};
}}
QPushButton#Primary:hover {{ background: {GOLD_DARK}; color: #FFFFFF; }}
QPushButton#Danger:hover {{ border-color: {DANGER}; color: {DANGER}; }}
QPushButton#Ghost {{ background: transparent; border: none; color: {MUTED}; }}
QPushButton#Ghost:hover {{ color: {GOLD_DARK}; }}

/* ---- Tabs (open screens) ---- */
QTabWidget#Screens::pane {{ border: none; background: {CANVAS}; }}
QTabBar::tab {{
    background: transparent;
    color: {MUTED};
    padding: 9px 16px;
    border: none;
    border-bottom: 2px solid transparent;
    font-weight: 600;
}}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {GOLD}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::close-button {{ background: transparent; padding: 2px; }}
QTabBar::close-button:hover {{ background: {BORDER}; border-radius: 6px; }}

/* ---- Tables ---- */
QTableWidget, QTreeWidget {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
    gridline-color: #EEEFF3;
    selection-background-color: {GOLD_SOFT};
    selection-color: {TEXT};
}}
QHeaderView::section {{
    background: #FAFAFB;
    color: {MUTED};
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid {BORDER};
    font-weight: 700;
    font-size: 11px;
}}
QTableWidget::item {{ padding: 6px 8px; }}

/* ---- Inputs ----
   min-height matters: Qt applies padding INSIDE the widget, so without a
   minimum the contents rect gets squeezed and the text clips vertically. */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QPlainTextEdit {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 5px 9px;
    min-height: 20px;
    selection-background-color: {GOLD_SOFT};
}}
QPlainTextEdit {{ min-height: 54px; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled,
QDoubleSpinBox:disabled, QDateEdit:disabled {{ background: #F0F0F2; color: {MUTED}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QDateEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {GOLD}; }}

/* Leave ::drop-down and ::down-arrow entirely unstyled so Fusion draws its
   native chevron. Overriding them (the CSS triangle trick) collapsed the arrow
   into a stray dash, making combo boxes look like plain text fields. */

/* ---- Check boxes ---- */
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: {CARD};
}}
QCheckBox::indicator:hover {{ border-color: {GOLD}; }}
QCheckBox::indicator:checked {{
    background: {GOLD};
    border: 1px solid {GOLD_DARK};
}}
QCheckBox::indicator:disabled {{ background: #F0F0F2; }}

/* ---- Group boxes (child grids on a form) ---- */
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    background: {CARD};
    margin-top: 14px;
    padding: 12px 10px 10px 10px;
    font-weight: 700;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    color: {MUTED};
    font-size: 11px;
    letter-spacing: 1px;
}}

/* ---- Cards ---- */
QFrame#Card {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QLabel#CardValue {{ font-size: 26px; font-weight: 800; color: {INK}; }}
QLabel#CardLabel {{ color: {MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
QLabel#H1 {{ font-size: 22px; font-weight: 800; color: {INK}; }}
QLabel#Muted {{ color: {MUTED}; }}

QStatusBar {{ background: {CARD}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #C7CAD3; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {GOLD}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QMessageBox, QDialog {{ background: {CANVAS}; }}
"""
