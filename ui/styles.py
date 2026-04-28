"""
UI colour palette and QSS stylesheet for NetSentinel.

Three built-in themes:
  • Arctic Clean  — professional light (default)
  • Midnight Pro  — modern dark with electric cyan
  • Obsidian Neon — high-contrast true-black with neon lime

Theme is persisted in QSettings under "ui/theme".
All colour constants are injected into module globals at import time
so that ``from ui.styles import ACCENT`` always returns the active theme's value.
Changing the theme requires a restart; call ``set_active_theme_name()`` then
restart the application.
"""

# ── Palette definitions ───────────────────────────────────────────────────────

_ARCTIC_CLEAN = {
    # Structural
    "NAV_BAR":            "#141B2D",
    "SIDEBAR_BG":         "#1F2B3E",
    "SIDEBAR_HOVER":      "#2A3A52",
    "SIDEBAR_SEL":        "#0078D4",
    "SIDEBAR_ITEM_FG":    "#A8B8C8",
    "SIDEBAR_SEL_BG":     "#243348",
    "BG_DARK":            "#F4F4F4",
    "BG_CARD":            "#FFFFFF",
    "BG_HOVER":           "#EEF4FF",
    "BG_ALT_ROW":         "#F7F9FC",
    # Accent
    "ACCENT":             "#0078D4",
    "ACCENT_LITE":        "#2B9FE8",
    "ACCENT_DARK":        "#005A9E",
    # Text
    "TEXT_PRIMARY":       "#1A1A2E",
    "TEXT_SECONDARY":     "#5A6A7A",
    "TEXT_MUTED":         "#9BA8B4",
    # Table headers
    "TH_BG":              "#1A3A5C",
    "TH_TEXT":            "#FFFFFF",
    "TH_BORDER":          "#254A6E",
    "TABLE_SEL":          "#CCE4F7",
    "TABLE_ROW_BORDER":   "#EAEAEA",
    # Status colours
    "RED":                "#D93025",
    "AMBER":              "#F59E0B",
    "GREEN":              "#2E7D32",
    "BLUE":               "#0078D4",
    # Status badge backgrounds
    "RED_BG":             "#FDF2F2",
    "AMBER_BG":           "#FFFBF0",
    "GREEN_BG":           "#F2FBF4",
    # Borders / dividers
    "BORDER":             "#D4D4D4",
    "BORDER_MED":         "#B8C4CF",
    "CARD_HDR_BORDER":    "#ECECEC",
    "NAV_DIVIDER":        "#0A0E1A",
    # Buttons
    "BTN_HOVER_BG":       "#E8F4FF",
    "BTN_EXPORT_HOVER":   "#EBF7EC",
    "BTN_DISABLED_BORDER":"#B0C4D8",
    "BTN_DISABLED_FG":    "#7A8A9A",
    "INPUT_BTN_BG":       "#EEF2F6",
    # Scrollbar / progress
    "PROGRESS_TRACK":     "#E0E8EF",
    "SCROLLBAR_TRACK":    "#E8EDF2",
    "SCROLLBAR_HANDLE":   "#B0BEC8",
    # Labels / tooltips
    "LABEL_SUBTITLE":     "#9DB0C4",
    "TOOLTIP_BG":         "#1A3A5C",
    "TOOLTIP_BORDER":     "#0A1E32",
    # Notification bars
    "UPDATE_BAR_BG":      "#E8F4FF",
    "UPDATE_BAR_BORDER":  "#B0C4D8",
    "UPDATE_BAR_FG":      "#004A8C",
    "ADMIN_WARN_FG":      "#92600A",
    "ADMIN_WARN_BG":      "#FFF3CD",
    "ADMIN_WARN_BORDER":  "#F0A500",
    "ADMIN_WARN_HOVER":   "#5A3A00",
    # Sidebar section headers
    "SIDEBAR_SECTION_BG": "#172333",
    "SIDEBAR_SECTION_FG": "#6A8099",
    # Pure white
    "WHITE":              "#FFFFFF",
    # Network benchmark grade colours
    "GRADE_A_BG":         "#14532d",
    "GRADE_B_FG":         "#4ade80",
    "GRADE_B_BG":         "#1a3a1a",
    "GRADE_C_BG":         "#451a03",
    "GRADE_D_BG":         "#7f1d1d",
    "GRADE_F_FG":         "#ff4444",
    "GRADE_F_BG":         "#3b0000",
    # Chart (matplotlib)
    "CHART_BG":           "#FFFFFF",
    "CHART_PLOT_BG":      "#FAFBFC",
    "CHART_GRID":         "#E8EDF2",
    "CHART_TITLE":        "#1A3A5C",
}

_MIDNIGHT_PRO = {
    # Structural
    "NAV_BAR":            "#0B0D10",
    "SIDEBAR_BG":         "#151A21",
    "SIDEBAR_HOVER":      "#1E2A36",
    "SIDEBAR_SEL":        "#40E0FF",
    "SIDEBAR_ITEM_FG":    "#8A9BB0",
    "SIDEBAR_SEL_BG":     "#1A3A5A",
    "BG_DARK":            "#101620",
    "BG_CARD":            "#151A21",
    "BG_HOVER":           "#1A2D42",
    "BG_ALT_ROW":         "#131820",
    # Accent
    "ACCENT":             "#40E0FF",
    "ACCENT_LITE":        "#6AECFF",
    "ACCENT_DARK":        "#25B8D8",
    # Text
    "TEXT_PRIMARY":       "#E9EEF5",
    "TEXT_SECONDARY":     "#8A9BB0",
    "TEXT_MUTED":         "#5A6A7A",
    # Table headers
    "TH_BG":              "#0D1520",
    "TH_TEXT":            "#E9EEF5",
    "TH_BORDER":          "#1E3A55",
    "TABLE_SEL":          "#1A3A5A",
    "TABLE_ROW_BORDER":   "#1E2A38",
    # Status colours
    "RED":                "#FF4D4D",
    "AMBER":              "#F59E0B",
    "GREEN":              "#4ADE80",
    "BLUE":               "#40E0FF",
    # Status badge backgrounds
    "RED_BG":             "#2D0F0F",
    "AMBER_BG":           "#2D1F00",
    "GREEN_BG":           "#0D2D15",
    # Borders / dividers
    "BORDER":             "#273140",
    "BORDER_MED":         "#2A3A4A",
    "CARD_HDR_BORDER":    "#1E2A38",
    "NAV_DIVIDER":        "#050708",
    # Buttons
    "BTN_HOVER_BG":       "#1A2D42",
    "BTN_EXPORT_HOVER":   "#0D2D1A",
    "BTN_DISABLED_BORDER":"#2A3A4A",
    "BTN_DISABLED_FG":    "#4A5A6A",
    "INPUT_BTN_BG":       "#1E2A38",
    # Scrollbar / progress
    "PROGRESS_TRACK":     "#0D1520",
    "SCROLLBAR_TRACK":    "#101620",
    "SCROLLBAR_HANDLE":   "#2A3A4A",
    # Labels / tooltips
    "LABEL_SUBTITLE":     "#5A7A9A",
    "TOOLTIP_BG":         "#0D1520",
    "TOOLTIP_BORDER":     "#1E3050",
    # Notification bars
    "UPDATE_BAR_BG":      "#102030",
    "UPDATE_BAR_BORDER":  "#204050",
    "UPDATE_BAR_FG":      "#6AECFF",
    "ADMIN_WARN_FG":      "#F0A500",
    "ADMIN_WARN_BG":      "#2A1A00",
    "ADMIN_WARN_BORDER":  "#704000",
    "ADMIN_WARN_HOVER":   "#FFD080",
    # Sidebar section headers
    "SIDEBAR_SECTION_BG": "#0D1218",
    "SIDEBAR_SECTION_FG": "#4A6080",
    # Pure white (off-white in dark mode)
    "WHITE":              "#E9EEF5",
    # Network benchmark grade colours
    "GRADE_A_BG":         "#14532d",
    "GRADE_B_FG":         "#4ade80",
    "GRADE_B_BG":         "#1a3a1a",
    "GRADE_C_BG":         "#451a03",
    "GRADE_D_BG":         "#7f1d1d",
    "GRADE_F_FG":         "#ff4444",
    "GRADE_F_BG":         "#3b0000",
    # Chart (matplotlib)
    "CHART_BG":           "#151A21",
    "CHART_PLOT_BG":      "#101620",
    "CHART_GRID":         "#1E2A38",
    "CHART_TITLE":        "#40E0FF",
}

_OBSIDIAN_NEON = {
    # Structural
    "NAV_BAR":            "#050505",
    "SIDEBAR_BG":         "#0A0A0A",
    "SIDEBAR_HOVER":      "#1A1A1A",
    "SIDEBAR_SEL":        "#B6FF3B",
    "SIDEBAR_ITEM_FG":    "#888888",
    "SIDEBAR_SEL_BG":     "#0D1A00",
    "BG_DARK":            "#080808",
    "BG_CARD":            "#111111",
    "BG_HOVER":           "#1A2500",
    "BG_ALT_ROW":         "#0D0D0D",
    # Accent
    "ACCENT":             "#B6FF3B",
    "ACCENT_LITE":        "#CCFF6A",
    "ACCENT_DARK":        "#88CC00",
    # Text
    "TEXT_PRIMARY":       "#FFFFFF",
    "TEXT_SECONDARY":     "#AAAAAA",
    "TEXT_MUTED":         "#666666",
    # Table headers
    "TH_BG":              "#0A0A0A",
    "TH_TEXT":            "#B6FF3B",
    "TH_BORDER":          "#222222",
    "TABLE_SEL":          "#1A2500",
    "TABLE_ROW_BORDER":   "#1A1A1A",
    # Status colours
    "RED":                "#FF3BD4",
    "AMBER":              "#FFB800",
    "GREEN":              "#B6FF3B",
    "BLUE":               "#40E0FF",
    # Status badge backgrounds
    "RED_BG":             "#200016",
    "AMBER_BG":           "#201000",
    "GREEN_BG":           "#0D1A00",
    # Borders / dividers
    "BORDER":             "#333333",
    "BORDER_MED":         "#444444",
    "CARD_HDR_BORDER":    "#222222",
    "NAV_DIVIDER":        "#000000",
    # Buttons
    "BTN_HOVER_BG":       "#1A2500",
    "BTN_EXPORT_HOVER":   "#0D1800",
    "BTN_DISABLED_BORDER":"#333333",
    "BTN_DISABLED_FG":    "#555555",
    "INPUT_BTN_BG":       "#1A1A1A",
    # Scrollbar / progress
    "PROGRESS_TRACK":     "#0A0A0A",
    "SCROLLBAR_TRACK":    "#0A0A0A",
    "SCROLLBAR_HANDLE":   "#333333",
    # Labels / tooltips
    "LABEL_SUBTITLE":     "#666666",
    "TOOLTIP_BG":         "#050505",
    "TOOLTIP_BORDER":     "#333333",
    # Notification bars
    "UPDATE_BAR_BG":      "#0A1A00",
    "UPDATE_BAR_BORDER":  "#336600",
    "UPDATE_BAR_FG":      "#B6FF3B",
    "ADMIN_WARN_FG":      "#FFB800",
    "ADMIN_WARN_BG":      "#1A1000",
    "ADMIN_WARN_BORDER":  "#664400",
    "ADMIN_WARN_HOVER":   "#FFCC44",
    # Sidebar section headers
    "SIDEBAR_SECTION_BG": "#050505",
    "SIDEBAR_SECTION_FG": "#558800",
    # Pure white
    "WHITE":              "#FFFFFF",
    # Network benchmark grade colours
    "GRADE_A_BG":         "#0A2200",
    "GRADE_B_FG":         "#B6FF3B",
    "GRADE_B_BG":         "#0A1800",
    "GRADE_C_BG":         "#1A1000",
    "GRADE_D_BG":         "#200010",
    "GRADE_F_FG":         "#FF3BD4",
    "GRADE_F_BG":         "#200010",
    # Chart (matplotlib)
    "CHART_BG":           "#111111",
    "CHART_PLOT_BG":      "#080808",
    "CHART_GRID":         "#1A1A1A",
    "CHART_TITLE":        "#B6FF3B",
}

# ── Theme registry ────────────────────────────────────────────────────────────

THEMES: dict = {
    "Arctic Clean":  _ARCTIC_CLEAN,
    "Midnight Pro":  _MIDNIGHT_PRO,
    "Obsidian Neon": _OBSIDIAN_NEON,
}

DEFAULT_THEME = "Arctic Clean"


# ── Theme persistence ─────────────────────────────────────────────────────────

def get_active_theme_name() -> str:
    """Return the saved theme name, falling back to DEFAULT_THEME on any error."""
    try:
        from PyQt6.QtCore import QSettings
        qs   = QSettings("NetSentinel", "NetSentinel")
        name = qs.value("ui/theme", DEFAULT_THEME)
        return name if name in THEMES else DEFAULT_THEME
    except Exception:
        return DEFAULT_THEME


def set_active_theme_name(name: str) -> None:
    """Persist the chosen theme name to QSettings (takes effect on restart)."""
    if name not in THEMES:
        raise ValueError(f"Unknown theme {name!r}. Valid: {list(THEMES)}")
    try:
        from PyQt6.QtCore import QSettings
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("ui/theme", name)
    except Exception:
        pass


# ── Apply active theme — injects all palette keys into this module's globals ──

_ACTIVE_THEME: str = get_active_theme_name()
globals().update(THEMES[_ACTIVE_THEME])

# ── Computed colour maps (built after palette is applied) ─────────────────────

RISK_COLORS = {
    "HIGH":    RED,     # type: ignore[name-defined]
    "STORM":   RED,     # type: ignore[name-defined]
    "MEDIUM":  AMBER,   # type: ignore[name-defined]
    "WARNING": AMBER,   # type: ignore[name-defined]
    "LOW":     BLUE,    # type: ignore[name-defined]
    "CLEAN":   GREEN,   # type: ignore[name-defined]
    "UNKNOWN": TEXT_SECONDARY,  # type: ignore[name-defined]
}

RISK_BG = {
    "HIGH":    RED_BG,    # type: ignore[name-defined]
    "STORM":   RED_BG,    # type: ignore[name-defined]
    "MEDIUM":  AMBER_BG,  # type: ignore[name-defined]
    "WARNING": AMBER_BG,  # type: ignore[name-defined]
    "LOW":     BTN_HOVER_BG,   # type: ignore[name-defined]
    "CLEAN":   GREEN_BG,  # type: ignore[name-defined]
    "UNKNOWN": BG_CARD,   # type: ignore[name-defined]
}


# ── QSS stylesheet ────────────────────────────────────────────────────────────

def _build_qss() -> str:
    """Build the QSS string from the currently active theme's module-level constants."""
    # fmt: off
    return f"""
/* ── Global base ── */
QMainWindow, QDialog {{
    background-color: {BG_DARK};
}}
QWidget {{
    background-color: {BG_DARK};
    color: {TEXT_PRIMARY};
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 12px;
}}

/* ── Top application bar (objectName="appBar") ── */
QWidget#appBar {{
    background-color: {NAV_BAR};
    border-bottom: 1px solid {NAV_DIVIDER};
    min-height: 42px;
    max-height: 42px;
}}
QWidget#appBar QLabel {{
    background: transparent;
    color: {WHITE};
}}

/* ── Sidebar nav list ── */
QListWidget#sideNav {{
    background-color: {SIDEBAR_BG};
    border: none;
    outline: none;
}}
QListWidget#sideNav::item {{
    color: {SIDEBAR_ITEM_FG};
    padding: 5px 12px;
    border-radius: 0px;
    margin: 0px;
    font-size: 12px;
    border-left: 3px solid transparent;
}}
QListWidget#sideNav::item:selected {{
    background-color: {SIDEBAR_SEL_BG};
    color: {WHITE};
    border-left: 3px solid {SIDEBAR_SEL};
    font-weight: bold;
}}
QListWidget#sideNav::item:hover:!selected {{
    background-color: {SIDEBAR_HOVER};
    color: {WHITE};
}}

/* ── Content area ── */
QWidget#contentArea {{
    background-color: {BG_DARK};
}}

/* ── Cards ── */
QFrame#card {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 0px;
}}
QFrame#cardHeader {{
    background-color: {BG_CARD};
    border-bottom: 1px solid {CARD_HDR_BORDER};
    border-top: none;
    border-left: none;
    border-right: none;
    min-height: 32px;
    max-height: 32px;
}}

/* ── Tables ── */
QTableWidget {{
    background-color: {BG_CARD};
    alternate-background-color: {BG_ALT_ROW};
    border: 1px solid {BORDER};
    border-radius: 0px;
    gridline-color: {BORDER};
    color: {TEXT_PRIMARY};
    outline: none;
    selection-background-color: {TABLE_SEL};
    selection-color: {TEXT_PRIMARY};
    font-size: 11px;
}}
QTableWidget::item {{
    padding: 3px 6px;
    border-bottom: 1px solid {TABLE_ROW_BORDER};
}}
QTableWidget::item:hover {{
    background-color: {BG_HOVER};
}}
QHeaderView::section {{
    background-color: {TH_BG};
    color: {TH_TEXT};
    padding: 5px 8px;
    border: none;
    border-right: 1px solid {TH_BORDER};
    font-weight: bold;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
QHeaderView::section:last {{
    border-right: none;
}}
QTreeWidget {{
    background-color: {BG_CARD};
    alternate-background-color: {BG_ALT_ROW};
    border: 1px solid {BORDER};
    color: {TEXT_PRIMARY};
    outline: none;
    font-size: 11px;
}}
QTreeWidget::item:selected {{
    background-color: {TABLE_SEL};
    color: {TEXT_PRIMARY};
}}

/* ── Primary scan button ── */
QPushButton#btnScan {{
    background-color: {ACCENT};
    color: {NAV_BAR};
    border: none;
    border-radius: 3px;
    padding: 5px 20px;
    font-size: 12px;
    font-weight: bold;
}}
QPushButton#btnScan:hover {{
    background-color: {ACCENT_LITE};
}}
QPushButton#btnScan:pressed {{
    background-color: {ACCENT_DARK};
}}
QPushButton#btnScan:disabled {{
    background-color: {BTN_DISABLED_BORDER};
    color: {BTN_DISABLED_FG};
}}

/* ── Standard buttons ── */
QPushButton {{
    background-color: {BG_CARD};
    color: {ACCENT};
    border: 1px solid {ACCENT};
    border-radius: 4px;
    padding: 5px 14px;
    font-size: 11px;
}}
QPushButton:hover {{
    background-color: {BTN_HOVER_BG};
    border-color: {ACCENT_LITE};
}}
QPushButton:pressed {{
    background-color: {ACCENT};
    color: {NAV_BAR};
}}
QPushButton:disabled {{
    background-color: {BG_CARD};
    color: {BTN_DISABLED_FG};
    border-color: {BTN_DISABLED_BORDER};
}}

/* ── Export button ── */
QPushButton#btnExport {{
    background-color: {BG_CARD};
    color: {GREEN};
    border: 1px solid {GREEN};
    border-radius: 4px;
    padding: 5px 14px;
    font-size: 11px;
    font-weight: bold;
}}
QPushButton#btnExport:hover {{
    background-color: {BTN_EXPORT_HOVER};
}}
QPushButton#btnExport:disabled {{
    color: {TEXT_MUTED};
    border-color: {BORDER};
}}

/* ── Diagnostics / action button ── */
QPushButton#btnDiag {{
    background-color: {ACCENT};
    color: {NAV_BAR};
    border: none;
    border-radius: 4px;
    padding: 5px 16px;
    font-size: 11px;
    font-weight: bold;
}}
QPushButton#btnDiag:hover {{
    background-color: {ACCENT_LITE};
}}
QPushButton#btnDiag:disabled {{
    background-color: {BTN_DISABLED_BORDER};
    color: {BTN_DISABLED_FG};
}}

/* ── Utility / refresh buttons ── */
QPushButton#btnNetRefresh {{
    background-color: {BG_CARD};
    color: {ACCENT};
    border: 1px solid {BORDER_MED};
    border-radius: 4px;
    padding: 4px 12px;
    font-size: 11px;
}}
QPushButton#btnNetRefresh:hover {{
    background-color: {BTN_HOVER_BG};
    border-color: {ACCENT};
}}

/* ── Router link buttons ── */
QPushButton#btnRouterLink {{
    background-color: transparent;
    color: {ACCENT};
    border: none;
    padding: 2px 4px;
    font-size: 11px;
    text-decoration: underline;
}}
QPushButton#btnRouterLink:hover {{
    color: {ACCENT_LITE};
}}

/* ── Checkable mode toggles ── */
QPushButton#btnNetRefresh:checked {{
    background-color: {ACCENT};
    color: {NAV_BAR};
    border-color: {ACCENT_DARK};
}}

/* ── Scrollbars ── */
QScrollBar:vertical {{
    background: {SCROLLBAR_TRACK};
    width: 8px;
    border-radius: 4px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {SCROLLBAR_HANDLE};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: {SCROLLBAR_TRACK};
    height: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {SCROLLBAR_HANDLE};
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {ACCENT};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── Labels ── */
QLabel#lblTitle {{
    font-size: 13px;
    font-weight: bold;
    color: {WHITE};
    background: transparent;
}}
QLabel#lblSubtitle {{
    font-size: 11px;
    color: {LABEL_SUBTITLE};
}}
QLabel#lblStatus {{
    font-size: 11px;
    color: {TEXT_SECONDARY};
    padding: 0 6px;
}}

/* ── Verdict panel ── */
QFrame#verdictFrame {{
    border-radius: 4px;
    border-left: 4px solid {ACCENT};
    padding: 2px;
}}
QLabel#verdictText {{
    font-size: 12px;
    padding: 8px 12px;
    color: {TEXT_PRIMARY};
}}

/* ── Progress bar ── */
QProgressBar {{
    background: {PROGRESS_TRACK};
    border: 1px solid {BORDER};
    border-radius: 3px;
    height: 6px;
    text-align: center;
    font-size: 10px;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 3px;
}}

/* ── SpinBox / ComboBox ── */
QSpinBox, QComboBox {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER_MED};
    border-radius: 3px;
    padding: 3px 22px 3px 6px;
    color: {TEXT_PRIMARY};
    min-width: 52px;
    font-size: 11px;
}}
QSpinBox:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    selection-background-color: {BG_HOVER};
    color: {TEXT_PRIMARY};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    width: 16px;
    background: {INPUT_BTN_BG};
    border-left: 1px solid {BORDER};
}}
QSpinBox::up-button {{ border-top-right-radius: 3px; border-bottom: 1px solid {BORDER}; }}
QSpinBox::down-button {{ border-bottom-right-radius: 3px; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: {ACCENT};
}}

/* ── Text edit (log / analysis boxes) ── */
QTextEdit {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 3px;
    color: {TEXT_PRIMARY};
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 11px;
}}

/* ── Group box ── */
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 4px;
    margin-top: 10px;
    padding: 6px;
    font-weight: bold;
    color: {TEXT_SECONDARY};
    font-size: 11px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {TEXT_SECONDARY};
}}

/* ── CheckBox ── */
QCheckBox {{
    color: {TEXT_PRIMARY};
    spacing: 5px;
    font-size: 11px;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {BORDER_MED};
    border-radius: 2px;
    background: {BG_CARD};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

/* ── Line edit ── */
QLineEdit {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER_MED};
    border-radius: 3px;
    padding: 4px 8px;
    color: {TEXT_PRIMARY};
    font-size: 11px;
    selection-background-color: {TABLE_SEL};
}}
QLineEdit:focus {{
    border-color: {ACCENT};
}}

/* ── ToolTip ── */
QToolTip {{
    background: {TOOLTIP_BG};
    color: {WHITE};
    border: 1px solid {TOOLTIP_BORDER};
    border-radius: 3px;
    padding: 4px 8px;
    font-size: 11px;
}}

/* ── Status bar ── */
QStatusBar {{
    background: {NAV_BAR};
    color: {LABEL_SUBTITLE};
    font-size: 11px;
    border-top: 1px solid {NAV_DIVIDER};
}}

/* ── Splitter handle ── */
QSplitter::handle {{
    background: {BORDER};
}}

/* ── Admin warning bar (thin strip) ── */
QWidget#adminWarningBar {{
    background-color: {ADMIN_WARN_BG};
    border-bottom: 1px solid {ADMIN_WARN_BORDER};
    min-height: 28px;
    max-height: 28px;
}}

/* ── Section separator labels in sidebar ── */
QLabel#sideNavSection {{
    color: {SIDEBAR_SECTION_FG};
    font-size: 10px;
    font-weight: bold;
    padding: 10px 12px 2px 12px;
    background: {SIDEBAR_SECTION_BG};
    letter-spacing: 1px;
    text-transform: uppercase;
}}
"""
    # fmt: on


MAIN_STYLE: str = _build_qss()
