"""
WCAG 2.1 colour-contrast ratio tests for all three NetSentinel themes.

For every known text/background pairing used in the global QSS and common
inline stylesheets this test asserts the minimum WCAG contrast ratio:
  • 4.5 : 1  — WCAG AA, normal text (< 18 pt regular / < 14 pt bold)
  • 3.0 : 1  — WCAG AA large text (≥ 18 pt regular or ≥ 14 pt bold)

The test is purely arithmetic — no QApplication or display needed.

How to extend: add a new entry to _PAIRS with
  (description, fg_token, bg_token, min_ratio)
where fg_token / bg_token are keys in ui.styles.THEMES["Arctic Clean"].
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# WCAG 2.1 relative luminance helpers
# ---------------------------------------------------------------------------

def _channel(c: float) -> float:
    """Linearise an sRGB channel value [0,1]."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


import re as _re
_RGBA_RE = _re.compile(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)")


def _resolve_hex(colour: str, bg_hex: str = "#FFFFFF") -> str:
    """Composite an rgba() over bg_hex and return the effective #RRGGBB.

    PyQt6 QSS rgba() values are translucent overlays; for WCAG contrast
    purposes we composite them over the dominant background (white by default).
    Pure #RRGGBB values pass through unchanged.
    """
    m = _RGBA_RE.match(colour)
    if m:
        r0, g0, b0, a = int(m[1]), int(m[2]), int(m[3]), float(m[4])
        bg = bg_hex.lstrip("#")
        br, bg_, bb = int(bg[0:2], 16), int(bg[2:4], 16), int(bg[4:6], 16)
        r = round(r0 * a + br * (1 - a))
        g = round(g0 * a + bg_ * (1 - a))
        b = round(b0 * a + bb * (1 - a))
        return f"#{r:02X}{g:02X}{b:02X}"
    return colour


def _rel_lum(hex_color: str) -> float:
    """Return the WCAG 2.1 relative luminance of a #RRGGBB or rgba() colour.

    rgba() values are composited over white before computing luminance.
    """
    h = _resolve_hex(hex_color).lstrip("#")
    r = _channel(int(h[0:2], 16) / 255)
    g = _channel(int(h[2:4], 16) / 255)
    b = _channel(int(h[4:6], 16) / 255)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    """Return the WCAG 2.1 contrast ratio between fg and bg hex colours."""
    l1 = _rel_lum(fg)
    l2 = _rel_lum(bg)
    lighter = max(l1, l2)
    darker  = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# ---------------------------------------------------------------------------
# Pair catalogue
# (description, fg_token, bg_token, min_ratio)
# ---------------------------------------------------------------------------

WCAG_AA       = 4.5   # normal text
WCAG_AA_LARGE = 3.0   # large / bold text (≥ 18 pt or ≥ 14 pt bold)

_PAIRS: list[tuple[str, str, str, float]] = [
    # ── Default widget / content area ────────────────────────────────────────
    ("Default widget text on page bg",      "TEXT_PRIMARY",    "BG_DARK",       WCAG_AA),
    ("Card body text",                       "TEXT_PRIMARY",    "BG_CARD",       WCAG_AA),
    ("Alt-row text",                         "TEXT_PRIMARY",    "BG_ALT_ROW",    WCAG_AA),
    ("Secondary text on card",               "TEXT_SECONDARY",  "BG_CARD",       WCAG_AA),
    ("Muted text on card (small labels)",    "TEXT_MUTED",      "BG_CARD",       WCAG_AA_LARGE),

    # ── Tables ────────────────────────────────────────────────────────────────
    ("Table header text",                    "TH_TEXT",         "TH_BG",         WCAG_AA),
    ("Table selected text",                  "TEXT_PRIMARY",    "TABLE_SEL",     WCAG_AA_LARGE),
    ("Table hover row text",                 "TEXT_PRIMARY",    "BG_HOVER",      WCAG_AA_LARGE),

    # ── Standard QPushButton interactive states ───────────────────────────────
    # Button labels are large/bold text — WCAG_AA_LARGE (3.0:1) applies.
    ("Button normal (accent text on card)",  "ACCENT",          "BG_CARD",       WCAG_AA_LARGE),
    ("Button pressed (white on accent)",     "WHITE",           "ACCENT",        WCAG_AA_LARGE),
    ("Button pressed (white on accent-dark)","WHITE",           "ACCENT_DARK",   WCAG_AA),

    # ── Named scan buttons ────────────────────────────────────────────────────
    # Hover uses ACCENT_DARK (darker) for sufficient contrast on all three themes.
    ("btnScan normal",                       "WHITE",           "ACCENT",        WCAG_AA_LARGE),
    ("btnScan hover",                        "WHITE",           "ACCENT_DARK",   WCAG_AA_LARGE),
    ("btnScan pressed",                      "WHITE",           "ACCENT_DARK",   WCAG_AA),
    ("btnDiag normal",                       "WHITE",           "ACCENT",        WCAG_AA_LARGE),
    ("btnDiag hover",                        "WHITE",           "ACCENT_DARK",   WCAG_AA_LARGE),
    ("btnDiag pressed",                      "WHITE",           "ACCENT_DARK",   WCAG_AA),

    # ── Export button ─────────────────────────────────────────────────────────
    ("btnExport normal (green on card)",     "GREEN",           "BG_CARD",       WCAG_AA_LARGE),
    ("btnExport hover",                      "GREEN",           "BTN_EXPORT_HOVER", WCAG_AA_LARGE),

    # ── Navigation sidebar ───────────────────────────────────────────────────
    ("Sidebar item text",                    "SIDEBAR_ITEM_FG", "SIDEBAR_BG",    WCAG_AA_LARGE),
    ("Sidebar selected text",                "WHITE",           "SIDEBAR_SEL",   WCAG_AA_LARGE),
    ("Sidebar hover text",                   "SIDEBAR_ITEM_FG", "SIDEBAR_HOVER", WCAG_AA_LARGE),

    # ── App bar / NAV_BAR ────────────────────────────────────────────────────
    ("AppBar label",                         "WHITE",           "NAV_BAR",       WCAG_AA),
    ("Status bar text",                      "LABEL_SUBTITLE",  "NAV_BAR",       WCAG_AA_LARGE),

    # ── Tooltip ──────────────────────────────────────────────────────────────
    ("Tooltip text",                         "TOOLTIP_FG",      "TOOLTIP_BG",    WCAG_AA),

    # ── Notification / info bars ─────────────────────────────────────────────
    ("Update bar text",                      "UPDATE_BAR_FG",   "UPDATE_BAR_BG", WCAG_AA),
    ("Admin warning text",                   "ADMIN_WARN_FG",   "ADMIN_WARN_BG", WCAG_AA),

    # ── Disabled state ───────────────────────────────────────────────────────
    ("Disabled button text on card",         "BTN_DISABLED_FG", "BG_CARD",       WCAG_AA_LARGE),

    # ── ComboBox dropdown ────────────────────────────────────────────────────
    ("ComboBox dropdown selected text",      "TEXT_PRIMARY",    "BG_HOVER",      WCAG_AA_LARGE),
]


# ---------------------------------------------------------------------------
# Trap test: WHITE == BG_CARD in Arctic Clean (invisible if combined)
# ---------------------------------------------------------------------------

def test_white_equals_bg_card_in_arctic_clean_is_a_known_trap():
    """
    WHITE and BG_CARD are both #FFFFFF in Arctic Clean.
    This test documents the trap: placing any WHITE-coloured widget on a
    BG_CARD background produces 1:1 contrast (invisible text).
    The WCAG pair tests above intentionally never include WHITE-on-BG_CARD.
    If this assertion starts failing, WHITE or BG_CARD has been changed —
    re-audit any widget that uses color:{WHITE} on a card background.
    """
    from ui.styles import THEMES
    ac = THEMES["Arctic Clean"]
    assert ac["WHITE"] == ac["BG_CARD"], (
        "WHITE and BG_CARD are no longer identical in Arctic Clean — "
        "re-check all WHITE-on-BG_CARD placements."
    )
    assert contrast_ratio(ac["WHITE"], ac["BG_CARD"]) < 1.1, (
        "Expected WHITE-on-BG_CARD to have contrast ~1:1 (the known trap)."
    )


# ---------------------------------------------------------------------------
# Parametrised contrast tests across all themes
# ---------------------------------------------------------------------------

def _theme_names():
    from ui.styles import THEMES
    return list(THEMES.keys())


@pytest.mark.parametrize("theme_name", _theme_names())
@pytest.mark.parametrize("desc,fg_tok,bg_tok,min_ratio", _PAIRS,
                         ids=[p[0] for p in _PAIRS])
def test_contrast_ratio(theme_name: str, desc: str, fg_tok: str, bg_tok: str,
                        min_ratio: float):
    """Assert WCAG contrast ratio >= min_ratio for the given fg/bg token pair."""
    from ui.styles import THEMES
    palette = THEMES[theme_name]
    fg = palette[fg_tok]
    bg = palette[bg_tok]
    ratio = contrast_ratio(fg, bg)
    assert ratio >= min_ratio, (
        f"[{theme_name}] {desc!r}: "
        f"{fg_tok}={fg} on {bg_tok}={bg} → ratio={ratio:.2f} "
        f"(need ≥ {min_ratio})"
    )
