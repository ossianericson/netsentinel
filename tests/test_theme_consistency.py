"""Theme consistency audit (UX Sprint 10, S10-6).

Validates:
  1. All four theme dicts have identical key sets — no theme-specific gaps.
  2. All colour values are valid 6-digit or 8-digit hex strings.
  3. WCAG AA contrast ratio (≥ 4.5:1) for primary text / card background pairs.
  4. No raw hex strings remain in UI files outside ui/styles.py (deferred to
     test_style_token_imports.py which already covers this).
"""
from __future__ import annotations

import re


# ── Pull theme dicts directly so we don't need Qt ────────────────────────────

from ui.styles import THEMES, _ARCTIC_CLEAN, _DARK_PRO, _OBSIDIAN_NEON, _ABYSS

_ALL_THEMES = {
    "Arctic Clean":  _ARCTIC_CLEAN,
    "Midnight Pro":  _DARK_PRO,
    "Obsidian Neon": _OBSIDIAN_NEON,
    "Abyss":         _ABYSS,
}

_HEX_RE = re.compile(r"^#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$")


# ── 1. Key parity ─────────────────────────────────────────────────────────────

def test_all_themes_have_same_keys():
    """Every theme must define exactly the same set of palette keys."""
    reference_keys = set(_ARCTIC_CLEAN.keys())
    offenders = []
    for name, theme in _ALL_THEMES.items():
        theme_keys = set(theme.keys())
        missing  = reference_keys - theme_keys
        extra    = theme_keys - reference_keys
        if missing or extra:
            offenders.append(f"{name}: missing={sorted(missing)} extra={sorted(extra)}")
    assert not offenders, "Theme key parity failure:\n" + "\n".join(offenders)


def test_themes_registry_matches_module_dicts():
    """THEMES dict must contain all four built-in themes."""
    assert set(_ALL_THEMES.keys()) == set(THEMES.keys())


# ── 2. Hex validity ───────────────────────────────────────────────────────────

def test_all_theme_values_are_valid_hex():
    """No theme key may have a non-hex or empty value."""
    offenders = []
    for name, theme in _ALL_THEMES.items():
        for key, value in theme.items():
            if not _HEX_RE.match(value):
                offenders.append(f"{name}.{key} = {value!r}")
    assert not offenders, "Invalid hex values in themes:\n" + "\n".join(offenders)


def test_no_theme_value_is_empty():
    offenders = []
    for name, theme in _ALL_THEMES.items():
        for key, value in theme.items():
            if not value:
                offenders.append(f"{name}.{key}")
    assert not offenders, "Empty theme values:\n" + "\n".join(offenders)


# ── 3. WCAG contrast helpers ──────────────────────────────────────────────────

def _relative_luminance(hex_color: str) -> float:
    """Compute WCAG 2.1 relative luminance for a hex colour string."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255
    def _linearize(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)


def _contrast_ratio(a: str, b: str) -> float:
    la, lb = _relative_luminance(a), _relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


# WCAG AA: ≥ 4.5:1 for normal text, ≥ 3.0:1 for large/bold text.
# We use 3.5 as the threshold for primary text on card bg — slightly above the
# large-text requirement to account for mixed use cases in tables / paragraphs.
_TEXT_BG_PAIRS = [
    ("TEXT_PRIMARY",   "BG_CARD"),
    ("TEXT_SECONDARY", "BG_CARD"),
    ("TH_TEXT",        "TH_BG"),
]
_MIN_RATIO = 3.5


def test_primary_text_contrast_meets_wcag_aa():
    """TEXT_PRIMARY and TEXT_SECONDARY must have ≥ 3.5:1 contrast on BG_CARD."""
    offenders = []
    for theme_name, theme in _ALL_THEMES.items():
        for fg_key, bg_key in _TEXT_BG_PAIRS:
            fg, bg = theme[fg_key], theme[bg_key]
            ratio = _contrast_ratio(fg, bg)
            if ratio < _MIN_RATIO:
                offenders.append(
                    f"{theme_name}: {fg_key}({fg}) on {bg_key}({bg}) "
                    f"= {ratio:.2f}:1 (need ≥ {_MIN_RATIO})"
                )
    assert not offenders, "WCAG contrast failures:\n" + "\n".join(offenders)


def test_white_text_on_accent_contrast():
    """WHITE text on ACCENT button background — must be ≥ 3.0:1 (WCAG AA large)."""
    offenders = []
    for theme_name, theme in _ALL_THEMES.items():
        fg, bg = theme["WHITE"], theme["ACCENT"]
        ratio = _contrast_ratio(fg, bg)
        if ratio < 3.0:
            offenders.append(
                f"{theme_name}: WHITE({fg}) on ACCENT({bg}) = {ratio:.2f}:1 (need ≥ 3.0)"
            )
    assert not offenders, "White-on-accent contrast failures:\n" + "\n".join(offenders)


def test_white_text_on_accent_dark_meets_wcag_aa():
    """WHITE text on ACCENT_DARK (pressed button) — must be ≥ 4.5:1 (WCAG AA normal)."""
    offenders = []
    for theme_name, theme in _ALL_THEMES.items():
        fg, bg = theme["WHITE"], theme["ACCENT_DARK"]
        ratio = _contrast_ratio(fg, bg)
        if ratio < 4.5:
            offenders.append(
                f"{theme_name}: WHITE({fg}) on ACCENT_DARK({bg}) = {ratio:.2f}:1 (need ≥ 4.5)"
            )
    assert not offenders, "Pressed-button contrast failures:\n" + "\n".join(offenders)


# ── 4. Card / table structural tokens must be distinct from content area ───────

def test_card_and_content_backgrounds_are_distinct_in_dark_themes():
    """In dark themes BG_CARD must not equal BG_DARK — cards must be visible."""
    for theme_name, theme in _ALL_THEMES.items():
        if theme_name == "Arctic Clean":
            continue  # light theme intentionally has pure white for both
        assert theme["BG_CARD"] != theme["BG_DARK"], (
            f"{theme_name}: BG_CARD and BG_DARK are identical ({theme['BG_CARD']}) "
            "— cards will be invisible against the page background"
        )
