"""
UI colour palette and QSS stylesheet for NetSentinel.

Two built-in themes:
  • Arctic Clean — professional light, cool-slate chrome with deep-indigo table headers
  • Midnight Pro — modern dark with bright royal-blue accent (GitHub Dark palette, default)

Theme is persisted in QSettings under "ui/theme".
All colour constants are injected into module globals at import time
so that ``from ui.styles import ACCENT`` always returns the active theme's value.
Call ``apply_theme(name)`` to switch the active theme immediately — it persists
the choice and emits ``get_theme_manager().theme_changed``, no restart required.
``set_active_theme_name()`` alone only persists; it does not restyle the running
app.
"""

import contextlib
import logging
import weakref

log = logging.getLogger(__name__)

# Dedicated instrumentation logger for theme-switch stage timing (RULE-T6 /
# theme-switch responsiveness investigation). A bare log.info() here would be
# silently dropped: nothing in the app calls logging.basicConfig(), so the
# root logger's effective level is the default WARNING and there is no
# handler to receive it. Mirrors the --trace-windows FileHandler pattern in
# app.py — its own logger + FileHandler under get_app_data_dir() (RULE 23),
# independent of root logging config.
_theme_switch_log = logging.getLogger("netsentinel.theme_switch")


def _ensure_theme_switch_log_handler() -> None:
    if _theme_switch_log.handlers:
        return
    try:
        from modules.utils import get_app_data_dir
        _path = str(get_app_data_dir() / "netsentinel_theme_switch.log")
        _h = logging.FileHandler(_path, mode="a", encoding="utf-8")
        _h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        _theme_switch_log.addHandler(_h)
        _theme_switch_log.setLevel(logging.INFO)
        _theme_switch_log.propagate = False
    except Exception:
        pass  # instrumentation is best-effort; must never break theme switching


# ── Palette definitions ───────────────────────────────────────────────────────

_ARCTIC_CLEAN = {
    # Structural — white sidebar + cool-slate chrome top bar (Arctic Clean)
    "NAV_BAR":            "#1E293B",
    "SIDEBAR_BG":         "#FFFFFF",
    "SIDEBAR_HOVER":      "rgba(0,120,212,0.06)",
    "SIDEBAR_SEL":        "#2C6CB0",
    "SIDEBAR_ITEM_FG":    "#334155",
    "SIDEBAR_SEL_BG":     "rgba(0,120,212,0.10)",
    "BG_DARK":            "#EEF2F7",
    "BG_CARD":            "#FFFFFF",
    "BG_HOVER":           "#EEF4FF",
    "BG_ALT_ROW":         "#F7F9FC",
    # Accent — refined slate blue (less neon than royal #0078D4)
    "ACCENT":             "#2C6CB0",
    "ACCENT_LITE":        "#3D86D4",
    "ACCENT_DARK":        "#1F4E80",
    # Text
    "TEXT_PRIMARY":       "#1A1A2E",
    "TEXT_SECONDARY":     "#475569",
    "TEXT_MUTED":         "#6D7A88",
    # Table headers — deep indigo (ported from Sentinel Light: white-on-header 11.6→15.2:1)
    "TH_BG":              "#14205A",
    "TH_TEXT":            "#FFFFFF",
    "TH_BORDER":          "#22307A",
    "TABLE_SEL":          "#CCE4F7",
    "TABLE_ROW_BORDER":   "#EAEAEA",
    # Status colours
    "RED":                "#D93025",
    "AMBER":              "#F59E0B",
    "GREEN":              "#2E7D32",
    "BLUE":               "#2C6CB0",
    "VIOLET":             "#6D4FC4",   # not_testable / "could not test" — distinct from ACCENT
    # Status badge backgrounds
    "RED_BG":             "#FDF2F2",
    "AMBER_BG":           "#FFFBF0",
    "GREEN_BG":           "#F2FBF4",
    # Dark ink for text sitting ON a saturated fill (AMBER/GREEN/RED button or
    # badge). AMBER is light in BOTH themes, so TEXT_PRIMARY/WHITE on an amber
    # fill is ~1.5:1 — unreadable. This token is dark in both themes by design.
    "TEXT_ON_FILL":       "#1A1A2E",
    # Borders / dividers
    "BORDER":             "#E2E8F0",
    "BORDER_LITE":        "#EBEBEB",
    "BORDER_MED":         "#B8C4CF",
    "CARD_HDR_BORDER":    "#ECECEC",
    # Buttons
    "BTN_HOVER_BG":       "#E8F4FF",
    "BTN_EXPORT_HOVER":   "#EBF7EC",
    "BTN_DISABLED_BORDER":"#B0C4D8",
    "BTN_DISABLED_FG":    "#7A8A9A",
    "INPUT_BTN_BG":       "#EEF2F6",
    "INPUT_PLACEHOLDER":  "#9BA8B4",
    # Scrollbar / progress
    "PROGRESS_TRACK":     "#E0E8EF",
    "SCROLLBAR_TRACK":    "#E8EDF2",
    "SCROLLBAR_HANDLE":   "#B0BEC8",
    # Labels / tooltips
    "LABEL_SUBTITLE":     "#9DB0C4",
    "TOOLTIP_BG":         "#EEF4FF",
    "TOOLTIP_BORDER":     "#2C6CB0",
    "TOOLTIP_FG":         "#1A1A2E",
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
    "SIDEBAR_SECTION_BG": "#F1F5F9",
    "SIDEBAR_SECTION_FG": "#64748B",
    # Special-purpose nav colours (keep here so one file owns all colours)
    "AUDIT_RED":          "#FF5252",
    "NAV_DIVIDER":        "#E2E8F0",
    # Navigation token rail — interactive states (theme-aware)
    "NAV_RAIL_HOVER_BG":      "rgba(0,120,212,0.07)",
    "NAV_RAIL_ACTIVE_BG":     "rgba(0,120,212,0.12)",
    "NAV_RAIL_FOCUS_BORDER":  "rgba(0,120,212,0.40)",
    "NAV_ITEM_HOVER_FG":      "#0F172A",
    "NAV_ITEM_ACTIVE_FG":     "#1F4E80",
    "NAV_FLYOUT_FOCUS_BORDER":"rgba(0,120,212,0.35)",
    "NAV_ITEM_PIN_HOVER_FG":  "#0F172A",
    "CARD_BORDER":            "#E2E8F0",
    # Pure white
    "WHITE":              "#FFFFFF",
    # Form inputs / notification banner surface (theme-aware)
    "INPUT_BORDER":       "#93A4B6",
    "BANNER_BG":          "#EDF3EE",
    # Status badges (enabled / disabled channel indicators)
    "BADGE_OK_FG":        "#065F46",
    "BADGE_OK_BG":        "#D1FAE5",
    "BADGE_OK_BORDER":    "#10B981",
    "BADGE_OFF_FG":       "#646A77",
    "BADGE_OFF_BG":       "#F3F4F6",
    "BADGE_OFF_BORDER":   "#D1D5DB",
    # Info box (Ookla banner etc.)
    "INFO_BOX_BG":        "#EBF4FF",
    "INFO_BOX_BORDER":    "#B3D4F5",
    "INFO_BOX_FG":        "#1A4A7A",
    # Inline warning text / background
    "INLINE_WARN_FG":     "#92400E",
    "INLINE_WARN_BG":     "#FEF3C7",
    # IP calculator alternating result-cell row
    "IP_CALC_ALT_ROW":    "#EEF2F7",
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
    "CHART_SPINE":        "#D4D4D4",
    "CHART_TITLE":        "#14205A",
    # Critical severity (CVE, risk — darker than RED for emphasis)
    "CVE_CRITICAL_FG":    "#8B0000",
    # Scan radar animation
    "RADAR_BG":           "#050F05",
    "RADAR_GRID":         "#0D2E0D",
    "RADAR_GREEN":        "#00FF41",
    "RADAR_TRAIL":        "#00CC33",
}

_DARK_PRO = {
    # Structural — GitHub Dark palette
    "NAV_BAR":            "#0D1117",
    "SIDEBAR_BG":         "#161B22",
    "SIDEBAR_HOVER":      "#21262D",
    "SIDEBAR_SEL":        "#3B82F6",
    "SIDEBAR_ITEM_FG":    "#8B949E",
    "SIDEBAR_SEL_BG":     "#1D3045",
    "BG_DARK":            "#0D1117",
    "BG_CARD":            "#1C2128",
    "BG_HOVER":           "#1A2233",
    "BG_ALT_ROW":         "#111820",
    # Accent — brighter royal blue (ported from Sentinel Dark: accent-on-card 4.32→4.63:1, clears AA)
    "ACCENT":             "#3B82F6",
    "ACCENT_LITE":        "#60A5FA",
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
    "AMBER":              "#F5B942",
    "GREEN":              "#4CAF50",
    "BLUE":               "#3B82F6",
    "VIOLET":             "#A78BFA",   # not_testable / "could not test" — distinct from ACCENT
    # Status badge backgrounds
    "RED_BG":             "rgba(217,48,37,0.12)",
    "AMBER_BG":           "rgba(245,158,11,0.12)",
    "GREEN_BG":           "rgba(46,125,50,0.15)",
    # Dark ink for text sitting ON a saturated fill — see the Arctic Clean note.
    "TEXT_ON_FILL":       "#0D1117",
    # Borders / dividers
    "BORDER":             "rgba(255,255,255,0.08)",
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
    "INPUT_PLACEHOLDER":  "#484F58",
    # Scrollbar / progress
    "PROGRESS_TRACK":     "#0D1117",
    "SCROLLBAR_TRACK":    "#0D1117",
    "SCROLLBAR_HANDLE":   "#30363D",
    # Labels / tooltips
    "LABEL_SUBTITLE":     "#60A5FA",
    "TOOLTIP_BG":         "#0D1117",
    "TOOLTIP_BORDER":     "#30363D",
    "TOOLTIP_FG":         "#E6EDF3",
    # Notification bars
    "UPDATE_BAR_BG":      "#102030",
    "UPDATE_BAR_BORDER":  "#204050",
    "UPDATE_BAR_FG":      "#60A5FA",
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
    # Navigation token rail — interactive states (theme-aware)
    "NAV_RAIL_HOVER_BG":      "rgba(255,255,255,0.07)",
    "NAV_RAIL_ACTIVE_BG":     "rgba(255,255,255,0.10)",
    "NAV_RAIL_FOCUS_BORDER":  "rgba(255,255,255,0.40)",
    "NAV_ITEM_HOVER_FG":      "#E6EDF3",
    "NAV_ITEM_ACTIVE_FG":     "#FFFFFF",
    "NAV_FLYOUT_FOCUS_BORDER":"rgba(255,255,255,0.35)",
    "NAV_ITEM_PIN_HOVER_FG":  "#E6EDF3",
    "CARD_BORDER":            "rgba(255,255,255,0.08)",
    # Pure white
    "WHITE":              "#E6EDF3",
    # Form inputs / notification banner surface (theme-aware)
    "INPUT_BORDER":       "#525C69",
    "BANNER_BG":          "#1A2330",
    # Status badges (enabled / disabled channel indicators)
    "BADGE_OK_FG":        "#3FB950",
    "BADGE_OK_BG":        "#0D2D15",
    "BADGE_OK_BORDER":    "#238636",
    "BADGE_OFF_FG":       "#8B949E",
    "BADGE_OFF_BG":       "#21262D",
    "BADGE_OFF_BORDER":   "#30363D",
    # Info box (Ookla banner etc.)
    "INFO_BOX_BG":        "#102030",
    "INFO_BOX_BORDER":    "#204050",
    "INFO_BOX_FG":        "#60A5FA",
    # Inline warning text / background
    "INLINE_WARN_FG":     "#E3B341",
    "INLINE_WARN_BG":     "#2A1A00",
    # IP calculator alternating result-cell row
    "IP_CALC_ALT_ROW":    "#1A2233",
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
    "CHART_SPINE":        "#30363D",
    "CHART_TITLE":        "#60A5FA",
    # Critical severity
    "CVE_CRITICAL_FG":    "#FF6E6E",
    # Scan radar animation
    "RADAR_BG":           "#050F05",
    "RADAR_GRID":         "#0D2E0D",
    "RADAR_GREEN":        "#00FF41",
    "RADAR_TRAIL":        "#00CC33",
}

# ── Theme registry ────────────────────────────────────────────────────────────

THEMES: dict = {
    "Arctic Clean":   _ARCTIC_CLEAN,
    "Midnight Pro":   _DARK_PRO,
}

DEFAULT_THEME = "Midnight Pro"


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
        pass  # non-fatal


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
        pass  # non-fatal


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


def alpha(hex_color: str, a) -> str:
    """Return a Qt ``rgba(r,g,b,a)`` string for a ``#RRGGBB`` colour.

    ``a`` is the opacity, given as either 0-255 (int, e.g. ``0x22``) or 0-1
    (float, e.g. ``0.13``).

    Use this ANYWHERE a translucent tint is wanted in a stylesheet. Never append
    hex alpha to a colour (``f"{ACCENT}22"``): Qt QSS parses 8-digit hex as
    ``#AARRGGBB`` (alpha-first), so ``#0078D422`` silently becomes fully
    transparent and ``#F59E0B22`` becomes an opaque dark red — not the intended
    translucent tint. Enforced by ``tests/test_qss_hex_alpha.py``.

    Values that are not a plain ``#RRGGBB`` hex (e.g. ``BORDER``, which is already
    an ``rgba(...)`` string) are returned unchanged, since alpha cannot be layered
    on them here (see RULE-10).
    """
    if not isinstance(hex_color, str) or not hex_color.startswith("#") or len(hex_color) < 7:
        return hex_color
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    frac = a / 255 if a > 1 else float(a)
    return f"rgba({r},{g},{b},{frac:.3f})"


# ── QSS recipe functions ──────────────────────────────────────────────────────
# The same few inline-QSS shapes (muted label, card wrapper, chip/badge, "X"
# dismiss button) get re-typed by hand at hundreds of call sites across ui/,
# each needing a parallel edit if the recipe ever changes. New code should call
# one of these instead of composing the f-string from scratch. Colour
# arguments default to `None` and are resolved to a theme constant *inside*
# the function body (not as a default-argument value) so each call always
# picks up the currently active theme, not whatever theme was active when
# ui/styles.py was first imported.

def qss_label(
    color: "str | None" = None,
    size: int = 11,
    *,
    weight: "str | None" = None,
    transparent: bool = True,
    border: str = "none",
) -> str:
    """QSS for a plain-text QLabel: colour + font-size, transparent background
    and no border by default. ``color`` defaults to TEXT_SECONDARY (the
    common "muted" case) — use :func:`qss_muted_label` for that shorthand.
    Pass ``weight="bold"`` for emphasis or ``border="1px solid ..."`` to keep
    a border instead of the default ``none``.
    """
    if color is None:
        color = TEXT_SECONDARY
    bits = [f"color:{color}", f"font-size:{size}px"]
    if weight:
        bits.append(f"font-weight:{weight}")
    if transparent:
        bits.append("background:transparent")
    bits.append(f"border:{border}")
    return "; ".join(bits) + ";"


def qss_muted_label(size: int = 11) -> str:
    """Shorthand for the extremely common muted secondary-text label recipe."""
    return qss_label(TEXT_SECONDARY, size)


def safe_tooltip(text: str) -> str:
    """Wrap plain tooltip text for a QListWidgetItem/QTableWidgetItem so it
    stays readable in Arctic Clean.

    Item-view tooltips (set via ``QListWidgetItem.setToolTip()`` /
    ``QTableWidgetItem.setToolTip()``) render against a background that does
    not follow the app's ``QToolTip`` QSS rule (``TOOLTIP_BG``) — verified
    live: it renders solid black regardless of theme. Midnight Pro's
    ``TOOLTIP_FG`` is already light, so it reads fine by coincidence; Arctic
    Clean's ``TOOLTIP_FG`` is dark navy, which is illegible on that black
    background. Forcing a fixed light foreground via inline HTML (which
    Qt's rich-text tooltip renderer honours regardless of the QSS/palette
    issue) fixes both themes. Plain ``QWidget.setToolTip()`` calls are
    unaffected and must not use this — only item-view tooltips.

    Newlines in *text* are converted to ``<br>`` — plain ``\n`` has no effect
    once the string is rich text, so multi-line tooltips would otherwise
    collapse onto one line.
    """
    import html as _html
    safe = _html.escape(text).replace("\n", "<br>")
    return f"<span style='color:{WHITE};'>{safe}</span>"


def qss_frame(
    object_name: str,
    bg: "str | None" = None,
    border: "str | None" = None,
    *,
    radius: "int | str | None" = 4,
    border_left: "str | None" = None,
    hover_border: "str | None" = None,
) -> str:
    """QSS for a card/banner QFrame wrapper, always scoped to
    ``#object_name`` (RULE-QSS1-safe — never a bare selector). ``bg``/
    ``border`` default to BG_CARD/BORDER. ``radius`` accepts either a plain
    int (rendered as ``Npx``), a pre-unit string like ``CARD_RADIUS``
    (``"8px"``), or ``None`` to omit ``border-radius`` entirely (square
    corners). Pass ``border_left`` (a colour) to add a 3px accent stripe,
    e.g. for a success/warning banner. Pass ``hover_border`` (a colour) to
    add a ``:hover { border-color: ... }`` rule.
    """
    if bg is None:
        bg = BG_CARD
    if border is None:
        border = BORDER
    decl = [f"background:{bg}", f"border:1px solid {border}"]
    if radius is not None:
        r = radius if isinstance(radius, str) else f"{radius}px"
        decl.append(f"border-radius:{r}")
    if border_left:
        decl.append(f"border-left:3px solid {border_left}")
    qss = f"QFrame#{object_name} {{ {'; '.join(decl)}; }}"
    if hover_border:
        qss += f"QFrame#{object_name}:hover {{ border-color:{hover_border}; }}"
    return qss


def qss_chip(fg: str, bg: str, border: str, *, radius: int = 10, size: int = 10,
             bold: bool = True, padding: str = "0 10px") -> str:
    """QSS for a small pill/badge label — the chip/badge recipe duplicated as
    local ``_chip_style()``/``_tag_chip_style()`` helpers in several pages.
    New chip styling should call this instead of reinventing the same
    font-size / border-radius / padding block.
    """
    weight = "font-weight:bold; " if bold else ""
    return (
        f"font-size:{size}px; {weight}color:{fg}; background:{bg};"
        f" border:1px solid {border}; border-radius:{radius}px; padding:{padding};"
    )


def qss_dismiss_button(
    size: int = 10,
    fg: "str | None" = None,
    hover_fg: "str | None" = None,
    *,
    padding: "str | None" = None,
    press_bg: "str | None" = None,
) -> str:
    """QSS for the small flat "X" dismiss/close QPushButton recipe: background
    stays transparent in the base and hover states, text lightens from
    secondary to primary on hover/press. Only ``font-size`` (and occasionally
    the colour pair) varies across the dozens of dismiss buttons this was
    copy-pasted from. Pass ``padding="0"`` for the fixed-size variants that
    need it explicit.

    Pass ``press_bg`` for the sibling variant used by several banner-dismiss
    buttons, where the pressed state shows a highlighted background (and
    hover does not force ``background:transparent``) instead of staying
    fully transparent throughout.
    """
    if fg is None:
        fg = TEXT_SECONDARY
    if hover_fg is None:
        hover_fg = TEXT_PRIMARY
    pad = f" padding:{padding};" if padding is not None else ""
    base = f"QPushButton {{ color:{fg}; background:transparent; border:none; font-size:{size}px;{pad} }}"
    if press_bg is not None:
        return (
            base
            + f"QPushButton:hover {{ color:{hover_fg}; }}"
            + f"QPushButton:pressed {{ background:{press_bg}; color:{fg}; }}"
        )
    return (
        base
        + f"QPushButton:hover {{ color:{hover_fg}; background:transparent; }}"
        + f"QPushButton:pressed {{ color:{hover_fg}; background:transparent; }}"
    )


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

# ── Theme-independent visualization constants ─────────────────────────────────────
# Fixed semantic colours for specific visualizations and status indicators.
MAP_LAND_BG        = "#1E2D3D"   # geo map — land fill (dark ocean-contrast)
MAP_LAND_BORDER    = "#3A4F63"   # geo map — land border (subtle outline)

IP_CALC_NET_BIT_BG = "#14205A"   # ip calculator — network bit cell (matches Arctic TH_BG)
IP_CALC_HOST_BIT_BG = "#2D4A2D"  # ip calculator — host bit cell (green tint)
IP_CALC_NET_FG     = "#7EB8F7"   # ip calculator — network bit foreground (light blue)
IP_CALC_HOST_FG    = "#88CC88"   # ip calculator — host bit foreground (light green)

LOG_SOURCE_PLUGIN  = "#A78BFA"   # log hub — plugin source label colour (violet)

# ── Danger-button interaction states ──────────────────────────────────────────
# Fixed semantic colours for Stop / destructive action buttons.
# These do not vary by theme; the base RED constant varies per theme.
RED_HOVER = "#E53935"   # danger-button hover state — Material Red 600
RED_DARK  = "#B71C1C"   # danger-button pressed state — Material Red 900

GRADE_B_COLOR      = "#4CAF8A"   # network grade — B grade colour (green-teal)

BLACK              = "#000000"   # pure black (specific UI use cases)
ORANGE             = "#FFA726"   # orange (plugin device type indicator)
STATUS_OFFLINE     = "#636366"   # status dot — offline/inactive (neutral gray)

# NOTE: BADGE_OK_*, BADGE_OFF_*, INFO_BOX_*, INLINE_WARN_*, and IP_CALC_ALT_ROW are
# theme-aware and live in the per-theme palette dicts above (injected into globals).

# ── Accent colour presets (user-selectable colours in Settings) ────────────────
TEAL               = "#00897B"   # teal preset accent
DEEP_ORANGE        = "#E65100"   # deep orange preset accent
ACCENT_PURPLE      = "#7C3AED"   # purple preset accent

# ── Certification brand colours (ObjectiveBadge — fixed, not theme-specific) ──
CERT_NETPLUS_BG    = "#C23B22"   # CompTIA Network+ red
CERT_CISCO_BG      = "#00BCEB"   # Cisco CCNA teal
CERT_SEC_BG        = "#6929C4"   # CompTIA Security+ purple

# ── HTML report export colours (embedded in generated HTML/CSS strings) ───────
HTML_GREEN         = "#27AE60"   # positive / pass row
HTML_RED           = "#E74C3C"   # negative / fail row
HTML_AMBER         = "#F39C12"   # warning row
HTML_TEXT          = "#333333"   # primary HTML body text
HTML_MUTED         = "#CCCCCC"   # muted border / box-shadow
HTML_BG_LIGHT      = "#F5F5F5"   # HTML page background
HTML_BG_ALT        = "#F9F9F9"   # HTML alternate row background

# ── Dark overlay / dialog colours (first-run wizard, coach-mark overlay) ─────
OVERLAY_BG         = "#1C1C1E"   # dark modal background
OVERLAY_BG2        = "#2C2C2E"   # dark modal card fill
OVERLAY_BG3        = "#3A3A3C"   # dark modal hover / border
OVERLAY_FG2        = "#8E8E93"   # dark modal secondary text
OVERLAY_FG3        = "#AEAEB2"   # dark modal tertiary text
OVERLAY_BLUE       = "#0A84FF"   # dark modal primary action (iOS-style blue)
OVERLAY_BLUE2      = "#409CFF"   # dark modal hover/active blue
OVERLAY_ORANGE     = "#FF9F0A"   # dark modal highlight / feature colour

# ── Protocol canvas colours (fixed dark background regardless of theme) ───────
CANVAS_BG          = "#0D1117"   # canvas background
CANVAS_FG          = "#E6EDF3"   # canvas text / packet labels
CANVAS_ACCENT      = "#2F81F7"   # canvas accent — client node / request packets
CANVAS_GREEN       = "#3FB950"   # canvas green — gateway / success / root bridge
CANVAS_AMBER       = "#E3B341"   # canvas amber — DNS / warning packets
CANVAS_GRAY        = "#8B949E"   # canvas gray — server / switch nodes
CANVAS_DIM         = "#484F58"   # canvas dim — broadcast / inactive border
CANVAS_TRAIL       = "#79C0FF"   # canvas motion-trail dots behind the travelling packet
CANVAS_PULSE       = "#F0F6FC"   # canvas arrival-pulse ring on packet delivery
CANVAS_GRID        = "#161B22"   # canvas backdrop dot-grid (near-invisible on CANVAS_BG)
CANVAS_NODE_FILL   = "#161B22"   # canvas node card base fill, under the per-role alpha tint

# ── Colour-blind accessible status icons (S10-2) ──────────────────────────────
# Used alongside colour in status cells so the state is conveyed by shape too.
# Import these instead of hardcoding the Unicode characters in individual pages.
STATUS_ICON_OK      = "✓"   # healthy / up / passing
STATUS_ICON_WARN    = "⚠"   # warning / slow / degraded
STATUS_ICON_CRIT    = "✗"   # critical / down / failing
STATUS_ICON_UNKNOWN = "○"   # no data / unknown

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
/* Labels never paint the page background — they sit on whatever surface their
   container paints (card, header, tile). Without this, every unstyled QLabel
   inherits the QWidget rule above and draws a BG_DARK box over its card
   (RULE-QSS1). Labels that need a badge background set it explicitly. */
QLabel {{
    background: transparent;
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
/* ── Item views ──
   Covers the standalone QListView instances Qt creates internally that no
   other selector reaches — notably a QCompleter's completion popup.

   Do NOT style a completer popup at its call site: QCompleter.popup() LAZILY
   CONSTRUCTS the view and keeps ownership of it. Materialising it during page
   construction hands a top-level widget to Qt that the completer will later
   destroy, while tests/conftest.py's _flush_qt_events sweeps topLevelWidgets()
   and deleteLater()s it too — a double free that aborts the process inside the
   DeferredDelete drain, ~3,000 tests later (RULE-WIN4). Confirmed by bisect on
   2026-07-26. A global rule applies whenever Qt eventually builds the popup,
   with nothing materialised early.

   Safe as a bare type selector: every QListWidget in ui/ either sets its own
   widget stylesheet (which always beats the app stylesheet) or is #sideNav
   below, whose ID selector outranks this. */
QListView {{
    background: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    outline: none;
    font-size: 11px;
}}
QListView::item {{
    padding: 3px 6px;
    color: {TEXT_PRIMARY};
}}
QListView::item:selected {{
    background: {BG_HOVER};
    color: {TEXT_PRIMARY};
}}

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
/* QDateTimeEdit also covers its QDateEdit / QTimeEdit subclasses. The whole
   family are siblings of QSpinBox under QAbstractSpinBox, so the QSpinBox
   selector alone never reached them (RULE-UX6 bug class). */
QSpinBox, QDoubleSpinBox, QDateTimeEdit, QComboBox {{
    background-color: {BG_CARD};
    border: 1px solid {INPUT_BORDER};
    border-radius: 3px;
    padding: 3px 22px 3px 6px;
    color: {TEXT_PRIMARY};
    min-width: 52px;
    font-size: 11px;
}}
QSpinBox:focus, QDoubleSpinBox:focus, QDateTimeEdit:focus, QComboBox:focus {{
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
/* ── Text edit (log / analysis boxes) ──
   QPlainTextEdit is a SIBLING of QTextEdit (both derive from
   QAbstractScrollArea), so it must be named explicitly — a QTextEdit type
   selector does not reach it. */
QTextEdit, QPlainTextEdit {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 3px;
    color: {TEXT_PRIMARY};
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 11px;
}}

/* ── Tab widget ──
   Secondary/inner tabs only; primary navigation is the activity rail (RULE 2).

   Global coverage is load-bearing here: `QTabBar::tab` is a subcontrol painted
   by the style, so the QWidget background-color base rule above never
   reaches it. Without these rules an unstyled QTabWidget falls back to Qt's
   NATIVE palette, which is not theme-aware — that shipped unreadable
   dark-on-dark tabs on Security Audit → Windows Shares (SMB) and Login Test.
   Sites carrying their own inline QSS still win; this is the correct-by-default
   floor. Enforced by tests/test_qss_tab_styling.py. */
QTabWidget::pane {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 3px;
}}
QTabBar {{
    background: transparent;
}}
QTabBar::tab {{
    background: {BG_CARD};
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER};
    border-bottom: none;
    border-top-left-radius: 3px;
    border-top-right-radius: 3px;
    padding: 5px 14px;
    margin-right: 2px;
    font-size: 11px;
}}
QTabBar::tab:hover {{
    background: {BG_HOVER};
    color: {TEXT_PRIMARY};
}}
QTabBar::tab:selected {{
    background: {BG_CARD};
    color: {TEXT_PRIMARY};
    font-weight: 600;
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:disabled {{
    background: {BG_CARD};
    color: {TEXT_MUTED};
}}

/* ── Tool button ──
   Sibling of QPushButton under QAbstractButton, so the QPushButton selector
   does not reach it. Every current site styles itself inline (the two on the
   dark app bar must, since TEXT_PRIMARY is dark navy in Arctic Clean); this
   rule is the safe floor for content-area tool buttons added later. */
QToolButton {{
    background: transparent;
    color: {TEXT_PRIMARY};
    border: none;
    border-radius: 4px;
    padding: 3px 6px;
    font-size: 11px;
}}
QToolButton:hover {{
    background: {BG_HOVER};
    color: {TEXT_PRIMARY};
}}
QToolButton:pressed {{
    background: {ACCENT};
    color: {WHITE};
}}
QToolButton:disabled {{
    background: transparent;
    color: {BTN_DISABLED_FG};
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
    border: 1px solid {INPUT_BORDER};
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
    border: 1px solid {INPUT_BORDER};
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
    color: {TOOLTIP_FG};
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


# ── Live theme management ─────────────────────────────────────────────────────

_theme_manager = None


def get_theme_manager():
    """Return the lazy singleton ThemeManager QObject (theme_changed signal)."""
    global _theme_manager
    if _theme_manager is None:
        from PyQt6.QtCore import QObject, pyqtSignal as _sig
        class _ThemeManager(QObject):
            theme_changed = _sig(str)
        _theme_manager = _ThemeManager()
    return _theme_manager


# ── Live QSS registry ──────────────────────────────────────────────────────────

_THEMED_REGISTRY: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


class _LiveTokens:
    """Mapping over this module's live globals for str.format_map."""

    def __getitem__(self, key: str):
        try:
            return globals()[key]
        except KeyError:
            raise KeyError(
                f"Unknown style token {{{key}}} in themed_ss template — "
                f"must be a name defined in ui/styles.py"
            ) from None


_LIVE_TOKENS = _LiveTokens()


def _render(template) -> str:
    if callable(template):
        return template()
    return template.format_map(_LIVE_TOKENS)


def themed_ss(widget, template) -> None:
    """setStyleSheet now + auto re-apply on every theme/accent change.

    template: plain str with {TOKEN} placeholders (converted from an f-string by
    dropping the 'f' — literal QSS braces stay doubled), or a zero-arg callable
    returning a QSS string. The callable MUST NOT capture the widget or self —
    that would strongly reference the WeakKeyDictionary key and leak the entry.
    Re-registering a widget replaces its template. GUI thread only.
    """
    widget.setStyleSheet(_render(template))   # render first: bad template raises
    _THEMED_REGISTRY[widget] = template        # only after a successful render


def _reapply_themed() -> None:
    import time as _time
    _t0 = _time.perf_counter()
    for w, t in list(_THEMED_REGISTRY.items()):   # snapshot: GC/re-entrancy safe
        try:
            w.setStyleSheet(_render(t))
        except RuntimeError:
            _THEMED_REGISTRY.pop(w, None)  # C++ object deleted, wrapper alive
    log.debug(
        "themed_ss: reapplied %d sheet(s) in %.1fms",
        len(_THEMED_REGISTRY), (_time.perf_counter() - _t0) * 1000,
    )


# ── QSpinBox stepper glyph palette ──────────────────────────────────────────────
#
# Qt's QSS engine cannot reliably theme the up/down (or +/-) stepper glyph:
# the CSS border-triangle trick doesn't render (Qt's QSS border painter draws
# each edge as an independent rectangle -- it does not miter corners into a
# point the way a browser does), and the moment ANY ::up-button/::down-button
# subcontrol rule is declared, Qt stops using native palette-based primitive
# drawing for that control entirely -- the glyph renders nothing at all,
# arrow or +/-, regardless of buttonSymbols. Confirmed by direct isolated
# rendering tests before this fix landed (not just contrast math).
#
# The fix: style only the base QSpinBox box via QSS (background/color --
# unaffected, since those aren't subcontrol rules) and set the widget's
# QPalette ButtonText/Button roles in Python instead, which the native
# primitive draw DOES respect.
#
# Stepper glyph is +/- (PlusMinus), not arrows -- clearer at this control
# size (user preference). Set centrally here so every caller gets it
# automatically, rather than each call site remembering to opt in.
#
# Width AND a second, more serious bug: the app's real on-screen Qt style is
# "windows11" (confirmed via app.style().objectName() on a live QApplication
# -- offscreen/CI probing silently falls back to "Fusion", a DIFFERENT style
# with different button geometry, so geometry math done against an offscreen
# probe does not reflect what actually renders). Under windows11, PlusMinus
# draws as two 21px square buttons SIDE BY SIDE (not stacked like arrows).
#
# Declaring `border`, `border-radius`, OR `padding` in a QSpinBox's QSS --
# even just one of the three, even `border: none` -- desyncs Qt's internal
# QLineEdit child (the actual editable text field QAbstractSpinBox composes
# itself from) from where the native +/- buttons are drawn: the LineEdit's
# real widget geometry (SC_SpinBoxEditField) ends up extending several
# pixels INTO the button subcontrol rects, confirmed via
# QWidget.childAt(<button center>) returning the QLineEdit instead of None.
# Since real mouse events are routed by the window system to the deepest
# child widget AT THAT SCREEN POSITION, a live click on a visually-correct
# "+" glyph lands on the LineEdit (just moves the text cursor) instead of
# the spinbox's button handler -- the button LOOKS right and PAINTS right
# but does not respond to clicks. (QTest.mouseClick() cannot catch this: it
# posts synthetic events directly to the named widget, bypassing the
# geometry-based child dispatch a real click goes through -- childAt() is
# the reliable check, not a mouseClick()-driven value assertion.) No amount
# of widening the widget fixes this -- the overlap is a constant offset
# regardless of total width. The only verified-safe QSpinBox QSS is
# background-color/color/font-size ONLY; get the left text inset via
# lineEdit().setTextMargins() below, never via QSS `padding`.
#
# Width is still real and separate: even with the click-safe QSS above,
# the fixed +/- button column (2 x 21px under windows11) needs enough total
# widget width to avoid the value text visually running under it. These
# constants are the minimum widths confirmed clean by live-rendering.
SPINBOX_WIDTH_WITH_SUFFIX = 100   # worst case text e.g. "3600 s", "60 min", "5000 pps"
SPINBOX_WIDTH_PLAIN = 72          # up to ~3 digits, no suffix, e.g. "120"
SPINBOX_WIDTH_WIDE_PLAIN = 92     # 4-5 digits, no suffix, e.g. port "65535", "8760"

_SPINBOX_PALETTE_REGISTRY: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def style_spinbox(widget) -> None:
    """Give a QSpinBox a themed, visible, CLICKABLE +/- stepper glyph.

    Call once after constructing any QSpinBox. Registers the widget for
    live re-theming, mirroring themed_ss(). Does not set widget width --
    callers must use SPINBOX_WIDTH_WITH_SUFFIX / SPINBOX_WIDTH_PLAIN (or a
    wider value) so the +/- buttons don't overlap the text.

    Callers' own QSS for this widget must be limited to background-color/
    color/font-size -- never border, border-radius, or padding (including
    `border: none`) -- or the +/- buttons render correctly but stop
    responding to clicks; see the module-level comment above."""
    from PyQt6.QtGui import QPalette, QColor
    from PyQt6.QtWidgets import QAbstractSpinBox
    widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.PlusMinus)
    pal = widget.palette()
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT_PRIMARY))
    pal.setColor(QPalette.ColorRole.Button, QColor(INPUT_BTN_BG))
    widget.setPalette(pal)
    le = widget.lineEdit()
    if le is not None:
        le.setTextMargins(6, 0, 2, 0)
    _SPINBOX_PALETTE_REGISTRY[widget] = True


def _reapply_spinbox_palettes() -> None:
    from PyQt6.QtGui import QPalette, QColor
    for w in list(_SPINBOX_PALETTE_REGISTRY):   # snapshot: GC/re-entrancy safe
        try:
            pal = w.palette()
            pal.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT_PRIMARY))
            pal.setColor(QPalette.ColorRole.Button, QColor(INPUT_BTN_BG))
            w.setPalette(pal)
        except RuntimeError:
            _SPINBOX_PALETTE_REGISTRY.pop(w, None)  # C++ object deleted, wrapper alive


@contextlib.contextmanager
def _suspend_repaints():
    """Disable repaints on every top-level widget while re-theming, so nothing
    paints a stale-colour frame mid-switch. No-op if there is no QApplication
    yet — some tests exercise this module without a running Qt app."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        yield
        return
    widgets = app.topLevelWidgets()
    for w in widgets:
        w.setUpdatesEnabled(False)
    try:
        yield
    finally:
        for w in widgets:
            w.setUpdatesEnabled(True)


def apply_theme(name: str) -> None:
    """Switch the active theme immediately — no restart required."""
    if name not in THEMES:
        raise ValueError(f"Unknown theme {name!r}. Valid: {list(THEMES)}")
    import time as _time
    _ensure_theme_switch_log_handler()
    _t_start = _time.perf_counter()
    with _suspend_repaints():
        import sys as _sys
        _m = _sys.modules[__name__]
        globals().update(THEMES[name])
        globals()["_ACTIVE_THEME"] = name
        _acc = get_accent_override()
        if _acc:
            _a, _al, _ad = _compute_accent_variants(_acc)
            globals().update({"ACCENT": _a, "ACCENT_LITE": _al, "ACCENT_DARK": _ad})
        _m.RISK_COLORS.clear()
        _m.RISK_COLORS.update({
            "HIGH":    _m.RED,    "STORM":   _m.RED,
            "MEDIUM":  _m.AMBER,  "WARNING": _m.AMBER,
            "LOW":     _m.BLUE,   "CLEAN":   _m.GREEN,
            "UNKNOWN": _m.TEXT_SECONDARY,
        })
        _m.RISK_BG.clear()
        _m.RISK_BG.update({
            "HIGH":    _m.RED_BG,     "STORM":   _m.RED_BG,
            "MEDIUM":  _m.AMBER_BG,   "WARNING": _m.AMBER_BG,
            "LOW":     _m.BTN_HOVER_BG, "CLEAN":  _m.GREEN_BG,
            "UNKNOWN": _m.BG_CARD,
        })
        _t_build_qss_start = _time.perf_counter()
        globals()["MAIN_STYLE"] = _build_qss()
        _t_build_qss_done = _time.perf_counter()
        _reapply_themed()
        _reapply_spinbox_palettes()
        _t_reapply_done = _time.perf_counter()
        set_active_theme_name(name)
        get_theme_manager().theme_changed.emit(name)
    _theme_switch_log.info(
        "apply_theme(%s): stage1 build_qss=%.1fms stage2 reapply_themed=%.1fms "
        "stage1+2 subtotal=%.1fms (stages 3-4 timed separately in "
        "Dashboard._on_theme_changed)",
        name,
        (_t_build_qss_done - _t_build_qss_start) * 1000,
        (_t_reapply_done - _t_build_qss_done) * 1000,
        (_time.perf_counter() - _t_start) * 1000,
    )


def apply_accent_override(hex_val: "str | None") -> None:
    """Apply or clear an accent colour override immediately."""
    set_accent_override(hex_val)
    import sys as _sys
    _m = _sys.modules[__name__]
    if hex_val:
        _a, _al, _ad = _compute_accent_variants(hex_val)
        globals().update({"ACCENT": _a, "ACCENT_LITE": _al, "ACCENT_DARK": _ad})
    else:
        _t = _m.THEMES[_m._ACTIVE_THEME]
        globals().update({
            "ACCENT":      _t["ACCENT"],
            "ACCENT_LITE": _t["ACCENT_LITE"],
            "ACCENT_DARK": _t["ACCENT_DARK"],
        })
    globals()["MAIN_STYLE"] = _build_qss()
    _reapply_themed()
    get_theme_manager().theme_changed.emit(_m._ACTIVE_THEME)


def get_app_qss() -> str:
    """Return application-level QSS (QMenu + QToolTip) reading live theme globals."""
    import sys as _sys
    _m = _sys.modules[__name__]
    return (
        f"QMenu {{ background:{_m.BG_CARD}; color:{_m.TEXT_PRIMARY};"
        f" border:1px solid {_m.BORDER}; padding:4px; font-size:12px; }}"
        f"QMenu::item {{ padding:4px 16px; color:{_m.TEXT_PRIMARY}; background:{_m.BG_CARD}; }}"
        f"QMenu::item:selected {{ background:{_m.BG_HOVER}; color:{_m.TEXT_PRIMARY}; }}"
        # RULE-QSS4: a QMenu rule does not reach QMenu::separator. Without this,
        # every addSeparator() divider is painted from Qt's native palette in
        # both themes. Per-site sheets still override it where they differ.
        f"QMenu::separator {{ height:1px; background:{_m.BORDER}; margin:3px 6px; }}"
        f"QToolTip {{ background:{_m.TOOLTIP_BG}; color:{_m.TOOLTIP_FG};"
        f" border:1px solid {_m.TOOLTIP_BORDER}; border-radius:3px; padding:4px 8px;"
        f" font-size:11px; }}"
    )
