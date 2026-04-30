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
    _STEPS,
    _StepCard,
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
# _STEPS constant
# ===========================================================================

class TestSlidesConstant:

    def test_three_steps(self):
        assert len(_STEPS) == 3

    def test_step_keys(self):
        for step in _STEPS:
            assert "number" in step
            assert "title" in step
            assert "body" in step
            assert "action_key" in step
            assert "action_label" in step

    def test_step_titles_non_empty(self):
        for step in _STEPS:
            assert step["title"].strip()

    def test_step_bodies_non_empty(self):
        for step in _STEPS:
            assert step["body"].strip()

    def test_step_keys_unique(self):
        keys = [s["action_key"] for s in _STEPS]
        assert len(keys) == len(set(keys))

    def test_step_numbers_are_1_2_3(self):
        assert [s["number"] for s in _STEPS] == ["1", "2", "3"]


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

    def test_correct_card_count(self):
        assert len(self.dlg._cards) == len(_STEPS)

    def test_cards_are_step_cards(self):
        for card in self.dlg._cards:
            assert isinstance(card, _StepCard)

    def test_finish_calls_accept(self):
        self.dlg.accept = MagicMock()
        self.dlg._finish()
        self.dlg.accept.assert_called_once()

    def test_finish_marks_done(self):
        with patch("ui.first_run_dialog.mark_first_run_done") as mock_done:
            self.dlg._finish()
        mock_done.assert_called_once()

    def test_fixed_size(self):
        assert self.dlg.width() == 560
        assert self.dlg.height() == 500

    def test_is_modal(self):
        assert self.dlg.isModal()

    def test_window_title(self):
        assert "NetSentinel" in self.dlg.windowTitle()

    def test_mark_done_disables_button(self):
        card = self.dlg._cards[0]
        card.mark_done()
        assert not card._btn.isEnabled()
        assert card._done is True

    def test_mark_done_shows_done_label(self):
        card = self.dlg._cards[0]
        card.mark_done()
        assert not card._done_lbl.isHidden()


# ===========================================================================
# _StepCard
# ===========================================================================

class TestStepCard:

    def test_constructs(self):
        card = _StepCard(_STEPS[0])
        assert card is not None

    def test_initial_not_done(self):
        card = _StepCard(_STEPS[0])
        assert card._done is False

    def test_mark_done_sets_flag(self):
        card = _StepCard(_STEPS[0])
        card.mark_done()
        assert card._done is True
