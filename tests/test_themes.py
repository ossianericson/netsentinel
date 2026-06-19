"""
Tests for the theme system in ui/styles.py.

Covers:
  • All three themes present in THEMES dict
  • Each palette has all required keys
  • Default theme is valid
  • get_active_theme_name fallback on QSettings failure
  • set_active_theme_name persists the value
  • set_active_theme_name rejects unknown theme names
  • Active theme constants injected into module globals
  • RISK_COLORS and RISK_BG use themed colour values
  • MAIN_STYLE is a non-empty string containing CSS
  • MAIN_STYLE reflects the active theme's BG_DARK value
  • Each palette's values are valid hex colour strings
  • Arctic Clean is a light theme (light BG_DARK)
  • Midnight Pro is a dark theme (dark BG_DARK, blue accent)
  • Obsidian Neon is a dark theme (dark BG_DARK, violet accent)
  • All themes produce non-empty MAIN_STYLE via _build_qss
  • Themes have distinct ACCENT values
  • Chart palette keys present in all themes
"""

import re
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Minimal Qt bootstrap — use offscreen if no display
# ---------------------------------------------------------------------------
pytest.importorskip("PyQt6.QtWidgets")


# ---------------------------------------------------------------------------
# Required palette keys — every theme MUST define all of these
# ---------------------------------------------------------------------------
_REQUIRED_KEYS = {
    "NAV_BAR", "SIDEBAR_BG", "SIDEBAR_HOVER", "SIDEBAR_SEL",
    "SIDEBAR_ITEM_FG", "SIDEBAR_SEL_BG",
    "BG_DARK", "BG_CARD", "BG_HOVER", "BG_ALT_ROW",
    "ACCENT", "ACCENT_LITE", "ACCENT_DARK",
    "TEXT_PRIMARY", "TEXT_SECONDARY", "TEXT_MUTED",
    "TH_BG", "TH_TEXT", "TH_BORDER", "TABLE_SEL", "TABLE_ROW_BORDER",
    "RED", "AMBER", "GREEN", "BLUE",
    "RED_BG", "AMBER_BG", "GREEN_BG",
    "BORDER", "BORDER_MED", "CARD_HDR_BORDER", "NAV_DIVIDER",
    "BTN_HOVER_BG", "BTN_EXPORT_HOVER", "BTN_DISABLED_BORDER", "BTN_DISABLED_FG",
    "INPUT_BTN_BG", "PROGRESS_TRACK", "SCROLLBAR_TRACK", "SCROLLBAR_HANDLE",
    "LABEL_SUBTITLE", "TOOLTIP_BG", "TOOLTIP_BORDER",
    "UPDATE_BAR_BG", "UPDATE_BAR_BORDER", "UPDATE_BAR_FG",
    "ADMIN_WARN_FG", "ADMIN_WARN_BG", "ADMIN_WARN_BORDER", "ADMIN_WARN_HOVER",
    "SIDEBAR_SECTION_BG", "SIDEBAR_SECTION_FG", "WHITE",
    "GRADE_A_BG", "GRADE_B_FG", "GRADE_B_BG", "GRADE_C_BG",
    "GRADE_D_BG", "GRADE_F_FG", "GRADE_F_BG",
    "CHART_BG", "CHART_PLOT_BG", "CHART_GRID", "CHART_TITLE",
}

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?$")


def _is_hex(val: str) -> bool:
    return isinstance(val, str) and bool(_HEX_RE.match(val))


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------
class TestThemeRegistry:
    def test_three_themes_present(self):
        from ui.styles import THEMES
        assert len(THEMES) >= 3

    def test_arctic_clean_present(self):
        from ui.styles import THEMES
        assert "Arctic Clean" in THEMES

    def test_midnight_pro_present(self):
        from ui.styles import THEMES
        assert "Midnight Pro" in THEMES

    def test_obsidian_neon_present(self):
        from ui.styles import THEMES
        assert "Obsidian Neon" in THEMES

    def test_default_theme_valid(self):
        from ui.styles import DEFAULT_THEME, THEMES
        assert DEFAULT_THEME in THEMES

    def test_default_theme_is_midnight_pro(self):
        from ui.styles import DEFAULT_THEME
        assert DEFAULT_THEME == "Midnight Pro"


# ---------------------------------------------------------------------------
# Palette completeness
# ---------------------------------------------------------------------------
class TestPaletteCompleteness:
    @pytest.mark.parametrize("theme_name", ["Arctic Clean", "Midnight Pro", "Obsidian Neon"])
    def test_all_required_keys_present(self, theme_name):
        from ui.styles import THEMES
        palette = THEMES[theme_name]
        missing = _REQUIRED_KEYS - set(palette.keys())
        assert not missing, f"{theme_name} missing keys: {missing}"

    @pytest.mark.parametrize("theme_name", ["Arctic Clean", "Midnight Pro", "Obsidian Neon"])
    def test_all_values_are_hex_colours(self, theme_name):
        from ui.styles import THEMES
        palette = THEMES[theme_name]
        bad = {k: v for k, v in palette.items() if not _is_hex(v)}
        assert not bad, f"{theme_name} has non-hex values: {bad}"


# ---------------------------------------------------------------------------
# Theme persistence
# ---------------------------------------------------------------------------
class TestThemePersistence:
    def test_get_active_theme_returns_default_when_no_settings(self):
        from ui.styles import DEFAULT_THEME, get_active_theme_name
        with patch("PyQt6.QtCore.QSettings") as MockQS:
            MockQS.return_value.value.return_value = DEFAULT_THEME
            name = get_active_theme_name()
        assert name == DEFAULT_THEME

    def test_get_active_theme_falls_back_on_exception(self):
        from ui.styles import DEFAULT_THEME, get_active_theme_name
        with patch("PyQt6.QtCore.QSettings", side_effect=RuntimeError("no app")):
            name = get_active_theme_name()
        assert name == DEFAULT_THEME

    def test_get_active_theme_falls_back_on_unknown_value(self):
        from ui.styles import DEFAULT_THEME, get_active_theme_name
        with patch("PyQt6.QtCore.QSettings") as MockQS:
            MockQS.return_value.value.return_value = "NonExistentTheme"
            name = get_active_theme_name()
        assert name == DEFAULT_THEME

    def test_set_active_theme_calls_qsettings(self):
        from ui.styles import set_active_theme_name
        with patch("PyQt6.QtCore.QSettings") as MockQS:
            inst = MockQS.return_value
            set_active_theme_name("Midnight Pro")
            inst.setValue.assert_called_once_with("ui/theme", "Midnight Pro")

    def test_set_active_theme_rejects_unknown(self):
        from ui.styles import set_active_theme_name
        with pytest.raises(ValueError, match="Unknown theme"):
            set_active_theme_name("Rainbow Unicorn")

    def test_set_active_theme_silent_on_qsettings_error(self):
        from ui.styles import set_active_theme_name
        with patch("PyQt6.QtCore.QSettings", side_effect=RuntimeError("no app")):
            set_active_theme_name("Obsidian Neon")  # must not raise


# ---------------------------------------------------------------------------
# Module-level constants reflect the active theme
# ---------------------------------------------------------------------------
class TestActiveThemeConstants:
    def test_active_theme_name_is_valid(self):
        from ui.styles import _ACTIVE_THEME, THEMES
        assert _ACTIVE_THEME in THEMES

    def test_accent_matches_active_palette(self):
        import ui.styles as s
        assert s.ACCENT == s.THEMES[s._ACTIVE_THEME]["ACCENT"]

    def test_bg_dark_matches_active_palette(self):
        import ui.styles as s
        assert s.BG_DARK == s.THEMES[s._ACTIVE_THEME]["BG_DARK"]

    def test_text_primary_matches_active_palette(self):
        import ui.styles as s
        assert s.TEXT_PRIMARY == s.THEMES[s._ACTIVE_THEME]["TEXT_PRIMARY"]

    def test_border_matches_active_palette(self):
        import ui.styles as s
        assert s.BORDER == s.THEMES[s._ACTIVE_THEME]["BORDER"]

    def test_chart_bg_matches_active_palette(self):
        import ui.styles as s
        assert s.CHART_BG == s.THEMES[s._ACTIVE_THEME]["CHART_BG"]


# ---------------------------------------------------------------------------
# RISK_COLORS and RISK_BG
# ---------------------------------------------------------------------------
class TestRiskMaps:
    def test_risk_colors_has_all_keys(self):
        from ui.styles import RISK_COLORS
        for key in ("HIGH", "STORM", "MEDIUM", "WARNING", "LOW", "CLEAN", "UNKNOWN"):
            assert key in RISK_COLORS

    def test_risk_bg_has_all_keys(self):
        from ui.styles import RISK_BG
        for key in ("HIGH", "STORM", "MEDIUM", "WARNING", "LOW", "CLEAN", "UNKNOWN"):
            assert key in RISK_BG

    def test_risk_high_uses_red(self):
        from ui.styles import RISK_COLORS, RED
        assert RISK_COLORS["HIGH"] == RED

    def test_risk_clean_uses_green(self):
        from ui.styles import RISK_COLORS, GREEN
        assert RISK_COLORS["CLEAN"] == GREEN


# ---------------------------------------------------------------------------
# MAIN_STYLE
# ---------------------------------------------------------------------------
class TestMainStyle:
    def test_main_style_is_non_empty(self):
        from ui.styles import MAIN_STYLE
        assert isinstance(MAIN_STYLE, str)
        assert len(MAIN_STYLE) > 500

    def test_main_style_contains_qwidget(self):
        from ui.styles import MAIN_STYLE
        assert "QWidget" in MAIN_STYLE

    def test_main_style_contains_active_bg_dark(self):
        from ui.styles import MAIN_STYLE, BG_DARK
        assert BG_DARK in MAIN_STYLE

    def test_main_style_contains_active_accent(self):
        from ui.styles import MAIN_STYLE, ACCENT
        assert ACCENT in MAIN_STYLE

    def test_build_qss_produces_non_empty_string(self):
        from ui.styles import _build_qss
        result = _build_qss()
        assert isinstance(result, str) and len(result) > 200


# ---------------------------------------------------------------------------
# Theme visual character
# ---------------------------------------------------------------------------
class TestThemeCharacter:
    def test_arctic_clean_has_light_bg(self):
        """Arctic Clean BG_DARK should be a light colour (starts with #F)."""
        from ui.styles import THEMES
        assert THEMES["Arctic Clean"]["BG_DARK"].startswith("#F")

    def test_midnight_pro_has_dark_bg(self):
        """Midnight Pro BG_DARK should be dark (luminance < 40)."""
        from ui.styles import THEMES
        bg = THEMES["Midnight Pro"]["BG_DARK"].lstrip("#")
        r, g, b = int(bg[0:2], 16), int(bg[2:4], 16), int(bg[4:6], 16)
        luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
        assert luminance < 40, f"Expected dark BG, got luminance={luminance}"

    def test_obsidian_neon_has_dark_bg(self):
        """Obsidian Neon BG_DARK should be dark (luminance < 40)."""
        from ui.styles import THEMES
        bg = THEMES["Obsidian Neon"]["BG_DARK"].lstrip("#")
        r, g, b = int(bg[0:2], 16), int(bg[2:4], 16), int(bg[4:6], 16)
        luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
        assert luminance < 40, f"Expected dark BG, got luminance={luminance}"

    def test_midnight_pro_has_blue_accent(self):
        """Midnight Pro uses GitHub-inspired blue accent."""
        from ui.styles import THEMES
        assert THEMES["Midnight Pro"]["ACCENT"] == "#2F81F7"

    def test_obsidian_neon_has_violet_accent(self):
        """Obsidian Neon uses a violet accent (WCAG AA-compliant on dark card)."""
        from ui.styles import THEMES
        accent = THEMES["Obsidian Neon"]["ACCENT"]
        # Violet family — hue between ~250° and ~300°; lightened from #7C3AED for
        # ≥3:1 contrast against BG_CARD (#1E1E2E) per WCAG AA large text.
        assert accent.startswith("#"), "ACCENT must be a hex colour"
        r = int(accent[1:3], 16)
        g = int(accent[3:5], 16)
        b = int(accent[5:7], 16)
        assert b > r > g, f"Violet accent must satisfy B>R>G, got R={r} G={g} B={b}"

    def test_themes_have_distinct_accents(self):
        from ui.styles import THEMES
        accents = [t["ACCENT"] for t in THEMES.values()]
        assert len(set(accents)) == len(THEMES), "Each theme should have a unique ACCENT"

    def test_themes_have_distinct_bg_dark(self):
        from ui.styles import THEMES
        bgs = [t["BG_DARK"] for t in THEMES.values()]
        assert len(set(bgs)) == len(THEMES)

    def test_obsidian_neon_red_is_pink(self):
        """Obsidian Neon uses Catppuccin Mocha pink-red for alerts."""
        from ui.styles import THEMES
        assert THEMES["Obsidian Neon"]["RED"] == "#F38BA8"

    def test_arctic_clean_red_is_standard(self):
        from ui.styles import THEMES
        assert THEMES["Arctic Clean"]["RED"] == "#D93025"


# ---------------------------------------------------------------------------
# apply_theme / apply_accent_override / get_app_qss
# ---------------------------------------------------------------------------
class TestApplyTheme:
    def test_apply_theme_updates_globals(self):
        import ui.styles as s
        original = s._ACTIVE_THEME
        try:
            target = "Midnight Pro" if original != "Midnight Pro" else "Arctic Clean"
            s.apply_theme(target)
            assert s.ACCENT == s.THEMES[target]["ACCENT"]
            assert s.BG_DARK == s.THEMES[target]["BG_DARK"]
        finally:
            s.apply_theme(original)

    def test_apply_theme_rebuilds_main_style(self):
        import ui.styles as s
        original = s._ACTIVE_THEME
        try:
            s.apply_theme("Abyss")
            assert s.THEMES["Abyss"]["BG_DARK"] in s.MAIN_STYLE
        finally:
            s.apply_theme(original)

    def test_apply_theme_updates_risk_colors_in_place(self):
        import ui.styles as s
        original = s._ACTIVE_THEME
        ref = s.RISK_COLORS  # grab reference before switch
        try:
            target = "Midnight Pro" if original != "Midnight Pro" else "Arctic Clean"
            s.apply_theme(target)
            assert ref is s.RISK_COLORS, "RISK_COLORS must be updated in-place"
            assert s.RISK_COLORS["HIGH"] == s.RED
        finally:
            s.apply_theme(original)

    def test_apply_theme_emits_signal(self):
        from unittest.mock import MagicMock
        from ui.styles import apply_theme, get_theme_manager
        original = __import__("ui.styles", fromlist=["_ACTIVE_THEME"])._ACTIVE_THEME
        slot = MagicMock()
        get_theme_manager().theme_changed.connect(slot)
        try:
            target = "Midnight Pro" if original != "Midnight Pro" else "Arctic Clean"
            apply_theme(target)
            slot.assert_called_with(target)
        finally:
            apply_theme(original)
            get_theme_manager().theme_changed.disconnect(slot)

    def test_apply_theme_rejects_unknown(self):
        from ui.styles import apply_theme
        with pytest.raises(ValueError, match="Unknown theme"):
            apply_theme("Rainbow Unicorn")

    def test_get_app_qss_reflects_current_theme(self):
        import ui.styles as s
        original = s._ACTIVE_THEME
        try:
            target = "Midnight Pro" if original != "Midnight Pro" else "Arctic Clean"
            s.apply_theme(target)
            qss = s.get_app_qss()
            assert s.BG_CARD in qss
            assert s.TEXT_PRIMARY in qss
        finally:
            s.apply_theme(original)

    def test_apply_accent_override_updates_accent(self):
        import ui.styles as s
        _ = s.ACCENT
        try:
            s.apply_accent_override("#FF5500")
            assert s.ACCENT == "#FF5500"
        finally:
            s.apply_accent_override(None)

    def test_apply_accent_override_none_restores_default(self):
        import ui.styles as s
        theme_default = s.THEMES[s._ACTIVE_THEME]["ACCENT"]
        s.apply_accent_override("#FF5500")
        s.apply_accent_override(None)
        assert s.ACCENT == theme_default
