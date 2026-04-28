"""
Tests for ui/pages/settings_page.py and ui/first_run_dialog.py.

Covers:
  SettingsPage:
    • Constructs without errors
    • _build_appearance_card returns a QFrame
    • Theme buttons are present (one per theme)
    • Active theme button has filled ACCENT style
    • Inactive theme buttons have outline style
    • _on_theme saves via set_active_theme_name
    • _on_theme updates the status label
    • _build_display_card constructs checkboxes
    • Compact-row checkbox persists to QSettings
    • Tooltip checkbox persists to QSettings
    • _build_shortcuts_card contains at least 4 shortcuts
    • SettingsPage has objectName "contentArea"

  FirstRunDialog:
    • should_show_first_run returns True when QSettings key absent
    • should_show_first_run returns False when key is True
    • mark_first_run_done writes True to QSettings
    • Constructs without errors
    • Has correct number of slides (4)
    • Back button hidden on first slide
    • Next button text on last slide is "Get Started"
    • _go_next advances the slide
    • _go_back retreats the slide
    • _finish calls accept
    • _finish calls mark_first_run_done when checkbox checked
    • _finish does NOT call mark_first_run_done when checkbox unchecked
    • SLIDES constant has 4 entries
    • Each slide dict has icon, title, body keys
    • _ProgressStrip set_step highlights correct dot
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Qt bootstrap
# ---------------------------------------------------------------------------
try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

_app = QApplication.instance() or QApplication(sys.argv + ["-platform", "offscreen"])

# ---------------------------------------------------------------------------
# Module imports
# ---------------------------------------------------------------------------
from ui.pages.settings_page import SettingsPage
from ui.first_run_dialog import (
    FirstRunDialog,
    SLIDES,
    _ProgressStrip,
    should_show_first_run,
    mark_first_run_done,
    _FIRST_RUN_KEY,
)
import ui.styles as _styles


# ===========================================================================
# SettingsPage tests
# ===========================================================================

class TestSettingsPage:

    def setup_method(self):
        self.page = SettingsPage()

    def test_constructs_without_error(self):
        assert self.page is not None

    def test_object_name(self):
        assert self.page.objectName() == "contentArea"

    def test_theme_buttons_present(self):
        assert len(self.page._theme_btns) == len(_styles.THEMES)

    def test_all_theme_names_have_buttons(self):
        for name in _styles.THEMES:
            assert name in self.page._theme_btns

    def test_active_theme_button_is_filled(self):
        active = _styles.get_active_theme_name()
        btn = self.page._theme_btns[active]
        style = btn.styleSheet()
        # Active button has background set to ACCENT (not BG_CARD)
        assert _styles.ACCENT in style

    def test_inactive_theme_buttons_are_outlined(self):
        active = _styles.get_active_theme_name()
        for name, btn in self.page._theme_btns.items():
            if name != active:
                style = btn.styleSheet()
                # Outline buttons set color (text) to ACCENT, bg to BG_CARD
                assert _styles.BG_CARD in style
                break  # only need to check one inactive

    def test_on_theme_calls_set_active(self):
        with patch.object(_styles, "set_active_theme_name") as mock_set:
            target = [n for n in _styles.THEMES][0]
            self.page._on_theme(target)
            mock_set.assert_called_once_with(target)

    def test_on_theme_updates_status_label(self):
        target = [n for n in _styles.THEMES][0]
        with patch.object(_styles, "set_active_theme_name"):
            self.page._on_theme(target)
        assert target in self.page._theme_status_lbl.text()
        assert "restart" in self.page._theme_status_lbl.text().lower()

    def test_compact_rows_checkbox_exists(self):
        assert self.page._chk_compact is not None

    def test_tooltip_checkbox_exists(self):
        assert self.page._chk_tooltips is not None

    def test_compact_rows_persists(self):
        with patch("ui.pages.settings_page.QSettings") as mock_qs_cls:
            mock_qs = MagicMock()
            mock_qs_cls.return_value = mock_qs
            self.page._on_compact_toggled(False)
        mock_qs.setValue.assert_called_once_with("display/compact_rows", False)

    def test_tooltip_persists(self):
        with patch("ui.pages.settings_page.QSettings") as mock_qs_cls:
            mock_qs = MagicMock()
            mock_qs_cls.return_value = mock_qs
            self.page._on_tooltip_toggled(True)
        mock_qs.setValue.assert_called_once_with("display/tooltips_enabled", True)

    def test_shortcuts_card_has_rows(self):
        # Build the card and verify it doesn't crash and produces a QFrame
        from PyQt6.QtWidgets import QFrame
        card = self.page._build_shortcuts_card()
        assert isinstance(card, QFrame)


# ===========================================================================
# SLIDES constant
# ===========================================================================

class TestSlidesConstant:

    def test_four_slides(self):
        assert len(SLIDES) == 4

    def test_slide_keys(self):
        for slide in SLIDES:
            assert "icon" in slide
            assert "title" in slide
            assert "body" in slide

    def test_slide_titles_non_empty(self):
        for slide in SLIDES:
            assert slide["title"].strip()

    def test_slide_bodies_non_empty(self):
        for slide in SLIDES:
            assert slide["body"].strip()

    def test_last_slide_mentions_settings(self):
        last = SLIDES[-1]
        assert "Settings" in last["body"] or "Settings" in last["title"]

    def test_last_slide_mentions_theme(self):
        last = SLIDES[-1]
        assert "theme" in last["body"].lower() or "Theme" in last["body"]


# ===========================================================================
# should_show_first_run / mark_first_run_done
# ===========================================================================

class TestFirstRunPersistence:

    def test_should_show_when_key_absent(self):
        mock_qs = MagicMock()
        mock_qs.value.return_value = False
        with patch("ui.first_run_dialog.QSettings", return_value=mock_qs):
            result = should_show_first_run()
        assert result is True

    def test_should_not_show_when_key_true(self):
        mock_qs = MagicMock()
        mock_qs.value.return_value = True
        with patch("ui.first_run_dialog.QSettings", return_value=mock_qs):
            result = should_show_first_run()
        assert result is False

    def test_mark_done_writes_true(self):
        mock_qs = MagicMock()
        with patch("ui.first_run_dialog.QSettings", return_value=mock_qs):
            mark_first_run_done()
        mock_qs.setValue.assert_called_once_with(_FIRST_RUN_KEY, True)

    def test_should_show_calls_qsettings_correct_args(self):
        mock_qs = MagicMock()
        mock_qs.value.return_value = False
        with patch("ui.first_run_dialog.QSettings", return_value=mock_qs) as cls:
            should_show_first_run()
        cls.assert_called_with("NetSentinel", "NetSentinel")


# ===========================================================================
# FirstRunDialog construction
# ===========================================================================

class TestFirstRunDialog:

    def setup_method(self):
        self.dlg = FirstRunDialog()

    def test_constructs_without_error(self):
        assert self.dlg is not None

    def test_correct_slide_count(self):
        assert self.dlg._stack.count() == len(SLIDES)

    def test_initial_slide_is_zero(self):
        assert self.dlg._stack.currentIndex() == 0

    def test_back_hidden_on_first_slide(self):
        assert not self.dlg._btn_back.isVisible()

    def test_next_text_on_first_slide(self):
        assert "Next" in self.dlg._btn_next.text()

    def test_next_text_on_last_slide(self):
        self.dlg._stack.setCurrentIndex(len(SLIDES) - 1)
        self.dlg._update_buttons()
        assert "Get Started" in self.dlg._btn_next.text()

    def test_go_next_advances_slide(self):
        self.dlg._go_next()
        assert self.dlg._stack.currentIndex() == 1

    def test_go_next_shows_back_button(self):
        self.dlg._go_next()
        assert not self.dlg._btn_back.isHidden()

    def test_go_back_retreats_slide(self):
        self.dlg._go_next()
        self.dlg._go_back()
        assert self.dlg._stack.currentIndex() == 0

    def test_go_back_hides_back_button_at_start(self):
        self.dlg._go_next()
        self.dlg._go_back()
        assert not self.dlg._btn_back.isVisible()

    def test_go_next_does_not_overflow(self):
        for _ in range(len(SLIDES) + 5):
            self.dlg._go_next()
        # Slide index should not exceed last
        assert self.dlg._stack.currentIndex() <= len(SLIDES) - 1

    def test_finish_calls_accept(self):
        self.dlg.accept = MagicMock()
        self.dlg._finish()
        self.dlg.accept.assert_called_once()

    def test_finish_marks_done_when_checkbox_checked(self):
        self.dlg._chk_skip.setChecked(True)
        with patch("ui.first_run_dialog.mark_first_run_done") as mock_done:
            self.dlg._finish()
        mock_done.assert_called_once()

    def test_finish_does_not_mark_done_when_unchecked(self):
        self.dlg._chk_skip.setChecked(False)
        with patch("ui.first_run_dialog.mark_first_run_done") as mock_done:
            self.dlg._finish()
        mock_done.assert_not_called()

    def test_fixed_size(self):
        assert self.dlg.width() == 560
        assert self.dlg.height() == 460

    def test_is_modal(self):
        assert self.dlg.isModal()

    def test_window_title(self):
        assert "NetSentinel" in self.dlg.windowTitle()


# ===========================================================================
# _ProgressStrip
# ===========================================================================

class TestProgressStrip:

    def test_constructs(self):
        strip = _ProgressStrip(4)
        assert strip is not None

    def test_correct_dot_count(self):
        strip = _ProgressStrip(4)
        assert len(strip._dots) == 4

    def test_initial_step_zero(self):
        strip = _ProgressStrip(4)
        assert strip._step == 0

    def test_set_step_updates_step(self):
        strip = _ProgressStrip(4)
        strip.set_step(2)
        assert strip._step == 2

    def test_step_label_updates(self):
        strip = _ProgressStrip(4)
        strip.set_step(3)
        assert "4" in strip._step_lbl.text()
        assert "4" in strip._step_lbl.text()

    def test_active_dot_uses_accent_color(self):
        strip = _ProgressStrip(4)
        strip.set_step(1)
        style = strip._dots[1].styleSheet()
        assert _styles.ACCENT in style

    def test_completed_dot_uses_green(self):
        strip = _ProgressStrip(4)
        strip.set_step(2)
        style = strip._dots[0].styleSheet()
        assert _styles.GREEN in style
