"""
UI colour palette and QSS stylesheet for NetSentinel.

Three built-in themes:
  • Arctic Clean  — professional light (default)
  • Midnight Pro  — modern dark with electric blue (GitHub Dark palette)
  • Obsidian Neon — warm dark with violet accent (Catppuccin Mocha-inspired)

Theme is persisted in QSettings under "ui/theme".
All colour constants are injected into module globals at import time
so that ``from ui.styles import ACCENT`` always returns the active theme's value.
Changing the theme requires a restart; call ``set_active_theme_name()`` then
restart the application.
"""

# ── Palette definitions ───────────────────────────────────────────────────────

_ARCTIC_CLEAN = {
    # Structural
    "NAV_BAR":            "#0C1014",
    "SIDEBAR_BG":         "#0D1117",
    "SIDEBAR_HOVER":      "#161B22",
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
    "TEXT_MUTED":         "#6D7A88",
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
    "BORDER_LITE":        "#EBEBEB",
    "BORDER_MED":         "#B8C4CF",
    "CARD_HDR_BORDER":    "#ECECEC",
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
    # Pro mode banner colours
    "PRO_BANNER_BORDER":  "#F4C2C2",
    "PRO_WARN_BG":        "#FFF0F0",
    # Sidebar section headers
    "SIDEBAR_SECTION_BG": "#0C1014",
    "SIDEBAR_SECTION_FG": "#6A8099",
    # Special-purpose nav colours (keep here so one file owns all colours)
    "AUDIT_RED":          "#FF5252",
    "NAV_DIVIDER":        "#060810",
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
    # Critical severity (CVE, risk — darker than RED for emphasis)
    "CRITICAL":           "#8B0000",
}

_DARK_PRO = {
    # Structural — GitHub Dark palette
    "NAV_BAR":            "#0D1117",
    "SIDEBAR_BG":         "#161B22",
    "SIDEBAR_HOVER":      "#21262D",
    "SIDEBAR_SEL":        "#2F81F7",
    "SIDEBAR_ITEM_FG":    "#8B949E",
    "SIDEBAR_SEL_BG":     "#1D3045",
    "BG_DARK":            "#0D1117",
    "BG_CARD":            "#161B22",
    "BG_HOVER":           "#1A2233",
    "BG_ALT_ROW":         "#111820",
    # Accent
    "ACCENT":             "#2F81F7",
    "ACCENT_LITE":        "#58A6FF",
    "ACCENT_DARK":        "#1A6BC4",
    # Text
    "TEXT_PRIMARY":       "#E6EDF3",
    "TEXT_SECONDARY":     "#8B949E",
    "TEXT_MUTED":         "#6E7681",
    # Table headers
    "TH_BG":              "#0D1520",
    "TH_TEXT":            "#E6EDF3",
    "TH_BORDER":          "#1E3A55",
    "TABLE_SEL":          "#1D3045",
    "TABLE_ROW_BORDER":   "#21262D",
    # Status colours
    "RED":                "#F85149",
    "AMBER":              "#E3B341",
    "GREEN":              "#3FB950",
    "BLUE":               "#2F81F7",
    # Status badge backgrounds
    "RED_BG":             "#2D0F0F",
    "AMBER_BG":           "#2A1A00",
    "GREEN_BG":           "#0D2D15",
    # Borders / dividers
    "BORDER":             "#30363D",
    "BORDER_LITE":        "#484F58",
    "BORDER_MED":         "#3A424B",
    "CARD_HDR_BORDER":    "#21262D",
    "NAV_DIVIDER":        "#070B0F",
    # Buttons
    "BTN_HOVER_BG":       "#1A2D42",
    "BTN_EXPORT_HOVER":   "#0D2A1A",
    "BTN_DISABLED_BORDER":"#30363D",
    "BTN_DISABLED_FG":    "#6E7681",
    "INPUT_BTN_BG":       "#21262D",
    # Scrollbar / progress
    "PROGRESS_TRACK":     "#0D1117",
    "SCROLLBAR_TRACK":    "#0D1117",
    "SCROLLBAR_HANDLE":   "#30363D",
    # Labels / tooltips
    "LABEL_SUBTITLE":     "#58A6FF",
    "TOOLTIP_BG":         "#0D1117",
    "TOOLTIP_BORDER":     "#30363D",
    # Notification bars
    "UPDATE_BAR_BG":      "#102030",
    "UPDATE_BAR_BORDER":  "#204050",
    "UPDATE_BAR_FG":      "#58A6FF",
    "ADMIN_WARN_FG":      "#E3B341",
    "ADMIN_WARN_BG":      "#2A1A00",
    "ADMIN_WARN_BORDER":  "#664400",
    "ADMIN_WARN_HOVER":   "#F0CC66",
    # Pro mode banner colours
    "PRO_BANNER_BORDER":  "#7A2020",
    "PRO_WARN_BG":        "#2D0A0A",
    # Sidebar section headers
    "SIDEBAR_SECTION_BG": "#0D1117",
    "SIDEBAR_SECTION_FG": "#6E7681",
    "AUDIT_RED":          "#F85149",
    # Pure white
    "WHITE":              "#E6EDF3",
    # Network benchmark grade colours
    "GRADE_A_BG":         "#14532d",
    "GRADE_B_FG":         "#3FB950",
    "GRADE_B_BG":         "#0D2D15",
    "GRADE_C_BG":         "#2A1A00",
    "GRADE_D_BG":         "#3D0F0F",
    "GRADE_F_FG":         "#F85149",
    "GRADE_F_BG":         "#2D0707",
    # Chart (matplotlib)
    "CHART_BG":           "#161B22",
    "CHART_PLOT_BG":      "#0D1117",
    "CHART_GRID":         "#21262D",
    "CHART_TITLE":        "#58A6FF",
    # Critical severity
    "CRITICAL":           "#FF6E6E",
}

_OBSIDIAN_NEON = {
    # Structural — warm charcoal with violet accent (Catppuccin Mocha-inspired)
    "NAV_BAR":            "#181825",
    "SIDEBAR_BG":         "#1E1E2E",
    "SIDEBAR_HOVER":      "#2A2A3F",
    "SIDEBAR_SEL":        "#7C3AED",
    "SIDEBAR_ITEM_FG":    "#A6ADC8",
    "SIDEBAR_SEL_BG":     "#2D1F4A",
    "BG_DARK":            "#181825",
    "BG_CARD":            "#1E1E2E",
    "BG_HOVER":           "#2A2A3F",
    "BG_ALT_ROW":         "#181825",
    # Accent
    "ACCENT":             "#8042ED",
    "ACCENT_LITE":        "#9D5CF6",
    "ACCENT_DARK":        "#5B21B6",
    # Text
    "TEXT_PRIMARY":       "#CDD6F4",
    "TEXT_SECONDARY":     "#A6ADC8",
    "TEXT_MUTED":         "#6C7086",
    # Table headers
    "TH_BG":              "#12101D",
    "TH_TEXT":            "#CDD6F4",
    "TH_BORDER":          "#302040",
    "TABLE_SEL":          "#2D1F4A",
    "TABLE_ROW_BORDER":   "#262638",
    # Status colours
    "RED":                "#F38BA8",
    "AMBER":              "#FAB387",
    "GREEN":              "#A6E3A1",
    "BLUE":               "#89DCEB",
    # Status badge backgrounds
    "RED_BG":             "#2D0F1A",
    "AMBER_BG":           "#2A1A00",
    "GREEN_BG":           "#0D2018",
    # Borders / dividers
    "BORDER":             "#302040",
    "BORDER_LITE":        "#4A3065",
    "BORDER_MED":         "#3A2F5A",
    "CARD_HDR_BORDER":    "#262638",
    "NAV_DIVIDER":        "#0D0B14",
    # Buttons
    "BTN_HOVER_BG":       "#2D1F4A",
    "BTN_EXPORT_HOVER":   "#0D2018",
    "BTN_DISABLED_BORDER":"#302040",
    "BTN_DISABLED_FG":    "#6C7086",
    "INPUT_BTN_BG":       "#262638",
    # Scrollbar / progress
    "PROGRESS_TRACK":     "#181825",
    "SCROLLBAR_TRACK":    "#181825",
    "SCROLLBAR_HANDLE":   "#302040",
    # Labels / tooltips
    "LABEL_SUBTITLE":     "#9D5CF6",
    "TOOLTIP_BG":         "#181825",
    "TOOLTIP_BORDER":     "#302040",
    # Notification bars
    "UPDATE_BAR_BG":      "#1A1030",
    "UPDATE_BAR_BORDER":  "#3A2060",
    "UPDATE_BAR_FG":      "#9D5CF6",
    "ADMIN_WARN_FG":      "#FAB387",
    "ADMIN_WARN_BG":      "#2A1500",
    "ADMIN_WARN_BORDER":  "#664400",
    "ADMIN_WARN_HOVER":   "#FAD0A0",
    # Pro mode banner colours
    "PRO_BANNER_BORDER":  "#7A2040",
    "PRO_WARN_BG":        "#2D0A18",
    # Sidebar section headers
    "SIDEBAR_SECTION_BG": "#181825",
    "SIDEBAR_SECTION_FG": "#6C7086",
    "AUDIT_RED":          "#F38BA8",
    # Pure white
    "WHITE":              "#CDD6F4",
    # Network benchmark grade colours
    "GRADE_A_BG":         "#0D2018",
    "GRADE_B_FG":         "#A6E3A1",
    "GRADE_B_BG":         "#0A1A10",
    "GRADE_C_BG":         "#2A1500",
    "GRADE_D_BG":         "#2D0F1A",
    "GRADE_F_FG":         "#F38BA8",
    "GRADE_F_BG":         "#2D0F1A",
    # Chart (matplotlib)
    "CHART_BG":           "#1E1E2E",
    "CHART_PLOT_BG":      "#181825",
    "CHART_GRID":         "#262638",
    "CHART_TITLE":        "#9D5CF6",
    # Critical severity
    "CRITICAL":           "#FF8080",
}

# ── Theme registry ────────────────────────────────────────────────────────────

THEMES: dict = {
    "Arctic Clean":  _ARCTIC_CLEAN,
    "Midnight Pro":  _DARK_PRO,
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


# ── Accent colour override (SET-2) ────────────────────────────────────────────

def get_accent_override() -> "str | None":
    """Return a persisted hex accent colour override, or None if not set."""
    try:
        from PyQt6.QtCore import QSettings
        qs  = QSettings("NetSentinel", "NetSentinel")
        val = qs.value("ui/accent_override", "")
        return val if val and val.startswith("#") and len(val) in (7, 9) else None
    except Exception:
        return None


def set_accent_override(hex_color: "str | None") -> None:
    """Persist or clear the accent colour override.  Takes effect on next launch."""
    try:
        from PyQt6.QtCore import QSettings
        qs = QSettings("NetSentinel", "NetSentinel")
        if hex_color:
            qs.setValue("ui/accent_override", hex_color)
        else:
            qs.remove("ui/accent_override")
    except Exception:
        pass


def _compute_accent_variants(hex_color: str) -> "tuple[str, str, str]":
    """Return (ACCENT, ACCENT_LITE, ACCENT_DARK) derived from a base hex colour."""
    import colorsys
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255
    hue, lig, sat = colorsys.rgb_to_hls(r, g, b)
    lite_l = min(1.0, lig * 1.40)
    dark_l = max(0.0, lig * 0.68)
    def _to_hex(rv: float, gv: float, bv: float) -> str:
        return f"#{int(rv * 255):02X}{int(gv * 255):02X}{int(bv * 255):02X}"
    lite = _to_hex(*colorsys.hls_to_rgb(hue, lite_l, sat))
    dark = _to_hex(*colorsys.hls_to_rgb(hue, dark_l, sat))
    return hex_color, lite, dark


# ── Apply active theme — injects all palette keys into this module's globals ──

_ACTIVE_THEME: str = get_active_theme_name()
globals().update(THEMES[_ACTIVE_THEME])

# Apply accent override if the user has saved a custom accent colour
_accent_override = get_accent_override()
if _accent_override:
    _a, _al, _ad = _compute_accent_variants(_accent_override)
    globals().update({"ACCENT": _a, "ACCENT_LITE": _al, "ACCENT_DARK": _ad})

# ── Theme-independent chart constants ──────────────────────────────────────────────
# These represent fixed semantic data dimensions, not UI chrome, so they
# do not change with the active theme.
CHART_DOWN   = "#2196F3"   # bandwidth download line (Material Blue)
CHART_UP     = "#4CAF50"   # bandwidth upload line (Material Green)
CHART_AXIS   = "#888888"   # matplotlib axis tick / label text
CHART_PURPLE = "#8E44AD"   # 6th data-series colour (history charts)

# ── Layout / typography tokens ────────────────────────────────────────────────
# Theme-independent. Import these instead of hardcoding values in page files.
CARD_RADIUS = "8px"   # border-radius for all content cards and panels
FONT_XS = "10px"      # labels, timestamps, section headers
FONT_SM = "11px"      # body text, table cells, descriptions
FONT_MD = "12px"      # default widget font (matches QSS base)
FONT_LG = "14px"      # page titles, hero labels
FONT_XL = "20px"      # large metric values (KPI tiles)

# ── Splash screen colours (theme-independent — shown before theme loads) ─────
# GitHub Dark palette. These constants are the single source of truth for all
# hex colours used in app.py's splash screen painter.
SPLASH_BG          = "#0D1117"   # canvas fill
SPLASH_TITLE_FG    = "#E6EDF3"   # "NetSentinel" title text
SPLASH_SUBTITLE_FG = "#8B949E"   # subtitle / version tagline
SPLASH_VERSION_FG  = "#30363D"   # version number (bottom of card)
SPLASH_MSG_FG      = "#484F58"   # loading progress messages

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
#appBar {{
    background-color: {NAV_BAR};
    border-bottom: 1px solid {NAV_DIVIDER};
    min-height: 42px;
    max-height: 42px;
}}
#appBar QLabel {{
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
    padding: 6px 10px;
    border-radius: 6px;
    margin: 1px 6px;
    font-size: 13px;
    font-weight: 600;
    border-left: none;
    outline: 0;
}}
QListWidget#sideNav::item:selected {{
    background-color: {SIDEBAR_SEL};
    color: {WHITE};
    border-left: 3px solid {ACCENT_LITE};
    border-top: none;
    border-bottom: none;
    border-right: none;
    font-weight: bold;
    border-radius: 0px;
    padding-left: 7px;
    outline: 0;
}}
QListWidget#sideNav::item:focus {{
    outline: 0;
}}
QListWidget#sideNav::item:hover:!selected {{
    background-color: {SIDEBAR_HOVER};
    color: {WHITE};
    border-radius: 6px;
}}

/* ── Content area ── */
QWidget#contentArea {{
    background-color: {BG_DARK};
}}

/* ── Cards ── */
QFrame#card {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-top: 1px solid {BORDER_LITE};
    border-left: 1px solid {BORDER_LITE};
    border-radius: 8px;
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
QHeaderView::section:hover {{
    background-color: {SIDEBAR_HOVER};
    color: {TH_TEXT};
    cursor: pointer;
}}
QHeaderView::sort-indicator {{
    subcontrol-origin: content;
    subcontrol-position: right center;
    width: 14px;
    height: 14px;
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

/* ── Primary scan button (header / inline compact) ── */
QPushButton#btnScan {{
    background-color: {ACCENT};
    color: {WHITE};
    border: none;
    border-radius: 6px;
    padding: 0 18px;
    font-size: 12px;
    font-weight: bold;
    min-height: 26px;
    max-height: 26px;
}}
QPushButton#btnScan:hover {{
    background-color: {ACCENT_LITE};
    color: {WHITE};
}}
QPushButton#btnScan:pressed {{
    background-color: {ACCENT_DARK};
    color: {WHITE};
}}
QPushButton#btnScan:disabled {{
    background-color: {BTN_DISABLED_BORDER};
    color: {BTN_DISABLED_FG};
}}

/* ── Hero scan button (home page call-to-action) ── */
QPushButton#btnScanHero {{
    background-color: {ACCENT};
    color: {WHITE};
    border: none;
    border-radius: 8px;
    padding: 10px 28px;
    font-size: 13px;
    font-weight: bold;
    min-height: 38px;
}}
QPushButton#btnScanHero:hover {{
    background-color: {ACCENT_LITE};
    color: {WHITE};
}}
QPushButton#btnScanHero:pressed {{
    background-color: {ACCENT_DARK};
    color: {WHITE};
}}
QPushButton#btnScanHero:disabled {{
    background-color: {BTN_DISABLED_BORDER};
    color: {BTN_DISABLED_FG};
}}

/* ── Standard buttons ── */
QPushButton {{
    background-color: {BG_CARD};
    color: {ACCENT};
    border: 1px solid {ACCENT};
    border-radius: 6px;
    padding: 5px 14px;
    font-size: 11px;
}}
QPushButton:hover {{
    background-color: {BTN_HOVER_BG};
    border-color: {ACCENT_LITE};
}}
QPushButton:pressed {{
    background-color: {ACCENT};
    color: {WHITE};
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
    padding: 0 14px;
    font-size: 11px;
    font-weight: bold;
    min-height: 24px;
    max-height: 24px;
}}
QPushButton#btnExport:hover {{
    background-color: {BTN_EXPORT_HOVER};
    color: {GREEN};
}}
QPushButton#btnExport:pressed {{
    background-color: {BTN_EXPORT_HOVER};
    color: {GREEN};
}}
QPushButton#btnExport:disabled {{
    color: {TEXT_MUTED};
    border-color: {BORDER};
}}

/* ── Diagnostics / action button ── */
QPushButton#btnDiag {{
    background-color: {ACCENT};
    color: {WHITE};
    border: none;
    border-radius: 4px;
    padding: 5px 16px;
    font-size: 11px;
    font-weight: bold;
}}
QPushButton#btnDiag:hover {{
    background-color: {ACCENT_LITE};
    color: {WHITE};
}}
QPushButton#btnDiag:pressed {{
    background-color: {ACCENT_DARK};
    color: {WHITE};
}}
QPushButton#btnDiag:disabled {{
    background-color: {BTN_DISABLED_BORDER};
    color: {BTN_DISABLED_FG};
}}

/* ── Utility / refresh buttons ── */
QPushButton#btnNetRefresh {{
    background-color: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 18px;
    font-size: 12px;
    font-weight: 500;
    min-height: 34px;
}}
QPushButton#btnNetRefresh:hover {{
    background-color: {BTN_HOVER_BG};
    border-color: {ACCENT};
    color: {ACCENT};
}}
QPushButton#btnNetRefresh:pressed {{
    background-color: {ACCENT};
    color: {WHITE};
    border-color: {ACCENT_DARK};
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
QPushButton#btnRouterLink:pressed {{
    color: {ACCENT_DARK};
}}

/* ── Checkable mode toggles ── */
QPushButton#btnNetRefresh:checked {{
    background-color: {ACCENT};
    color: {WHITE};
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
    selection-color: {TEXT_PRIMARY};
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
QPushButton:focus, QCheckBox:focus, QRadioButton:focus {{
    outline: none;
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
