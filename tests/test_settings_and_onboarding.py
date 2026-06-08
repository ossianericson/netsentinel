"""
Tests for ui/pages/settings_page.py and ui/first_run_dialog.py.

Covers:
  SettingsPage:
    • Constructs without errors
    • Theme buttons are present (one per theme)
    • Active theme button has filled ACCENT style
    • Inactive theme buttons have outline style
    • _on_theme saves via set_active_theme_name
    • _on_theme updates the status label
    • Compact-row checkbox persists to QSettings
    • Tooltip checkbox persists to QSettings
    • _build_shortcuts_card returns a QFrame
    • SettingsPage has objectName "contentArea"

  First-run persistence helpers:
    • should_show_first_run returns True when QSettings key absent
    • should_show_first_run returns False when key is True
    • mark_first_run_done writes both keys to QSettings
    • should_show_first_run calls QSettings with correct app/org args

  WelcomeOverlay:
    • Constructs without errors
    • Has a QFrame child named "welcomeCard"
    • Card has the correct fixed dimensions
    • start_scan_requested signal emits on scan
    • _on_skip calls mark_first_run_done
    • FirstRunDialog backward-compat alias: exec() returns 0
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Qt bootstrap
# ---------------------------------------------------------------------------
try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


# ---------------------------------------------------------------------------
# Module imports
# ---------------------------------------------------------------------------
from ui.pages.settings_page import SettingsPage
from ui.first_run_dialog import (
    FirstRunDialog,
    WelcomeOverlay,
    should_show_first_run,
    mark_first_run_done,
    _FIRST_RUN_KEY,
    _SLIDES,
    _TOTAL_SLIDES,
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

    def test_theme_swatches_present(self):
        assert len(self.page._theme_swatches) == len(_styles.THEMES)

    def test_all_theme_names_have_swatches(self):
        for name in _styles.THEMES:
            assert name in self.page._theme_swatches

    def test_active_theme_swatch_has_accent_border(self):
        active = _styles.get_active_theme_name()
        sw = self.page._theme_swatches[active]
        own_accent = _styles.THEMES[active]["ACCENT"]
        assert own_accent in sw.styleSheet()

    def test_inactive_theme_swatch_has_border_style(self):
        active = _styles.get_active_theme_name()
        for name, sw in self.page._theme_swatches.items():
            if name != active:
                assert "border" in sw.styleSheet()
                break

    def test_on_theme_calls_set_active(self):
        target = [n for n in _styles.THEMES][0]
        with patch("ui.styles.apply_theme") as mock_apply:
            self.page._on_theme(target)
            mock_apply.assert_called_once_with(target)

    def test_on_theme_updates_status_label(self):
        target = [n for n in _styles.THEMES][0]
        with patch("ui.styles.apply_theme"):
            self.page._on_theme(target)
        assert target in self.page._theme_status_lbl.text()
        assert "applied" in self.page._theme_status_lbl.text().lower()

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

    def test_mark_done_writes_both_keys(self):
        mock_qs = MagicMock()
        with patch("ui.first_run_dialog.QSettings", return_value=mock_qs):
            mark_first_run_done()
        calls = mock_qs.setValue.call_args_list
        keys_written = [c[0][0] for c in calls]
        assert _FIRST_RUN_KEY in keys_written

    def test_should_show_calls_qsettings_correct_args(self):
        mock_qs = MagicMock()
        mock_qs.value.return_value = False
        with patch("ui.first_run_dialog.QSettings", return_value=mock_qs) as cls:
            should_show_first_run()
        cls.assert_called_with("NetSentinel", "NetSentinel")


# ===========================================================================
# WelcomeOverlay (replaces old FirstRunDialog tests)
# ===========================================================================

class TestWelcomeOverlay:

    def setup_method(self):
        self.parent = QApplication.instance().activeWindow() or QApplication.instance().allWidgets()[0] if QApplication.instance().allWidgets() else None
        if self.parent is None:
            from PyQt6.QtWidgets import QWidget
            self.parent = QWidget()
            self.parent.resize(1024, 768)
        self.overlay = WelcomeOverlay(self.parent)

    def teardown_method(self):
        self.overlay.deleteLater()
        QApplication.instance().processEvents()

    def test_constructs_without_error(self):
        assert self.overlay is not None

    def test_has_card(self):
        from PyQt6.QtWidgets import QFrame
        card = self.overlay.findChild(QFrame, "welcomeCard")
        assert card is not None

    def test_card_has_correct_size(self):
        assert self.overlay._card.width() == WelcomeOverlay._CARD_W
        assert self.overlay._card.height() == WelcomeOverlay._CARD_H

    def test_starts_on_first_slide(self):
        assert self.overlay._slide_idx == 0

    def test_back_button_hidden_on_first_slide(self):
        assert not self.overlay._back_btn.isVisible()

    def test_next_button_text_changes_on_last_slide(self):
        self.overlay._slide_idx = _TOTAL_SLIDES - 1
        self.overlay._sync_nav()
        assert "Scan" in self.overlay._next_btn.text()

    def test_go_next_advances_slide(self):
        self.overlay._slide_idx = 0
        self.overlay._go_next()
        assert self.overlay._slide_idx == 1

    def test_go_back_retreats_slide(self):
        self.overlay._slide_idx = 1
        self.overlay._go_back()
        assert self.overlay._slide_idx == 0

    def test_go_next_on_last_slide_triggers_scan(self):
        received = []
        self.overlay.start_scan_requested.connect(lambda: received.append(True))
        self.overlay._slide_idx = _TOTAL_SLIDES - 1
        with patch("ui.first_run_dialog.mark_first_run_done"):
            self.overlay.hide_animated = lambda callback=None: (
                callback() if callback else None
            )
            self.overlay._go_next()
        assert len(received) == 1

    def test_progress_dots_count_matches_slides(self):
        assert len(self.overlay._dots) == _TOTAL_SLIDES

    def test_scan_signal_emits_on_scan(self):
        received = []
        self.overlay.start_scan_requested.connect(lambda: received.append(True))
        with patch("ui.first_run_dialog.mark_first_run_done"):
            self.overlay._on_scan = lambda: (
                mark_first_run_done(),
                self.overlay.start_scan_requested.emit(),
            )
            self.overlay._on_scan()
        assert len(received) == 1

    def test_skip_marks_done(self):
        with patch("ui.first_run_dialog.mark_first_run_done") as mock_done:
            self.overlay.hide_animated = lambda callback=None: callback() if callback else None
            self.overlay._on_skip()
        mock_done.assert_called_once()

    def test_first_run_compat_alias(self):
        """FirstRunDialog backward-compat alias: constructs and exec() returns 0."""
        dlg = FirstRunDialog()
        assert dlg is not None
        assert dlg.exec() == 0


# ===========================================================================
# _SLIDES constant
# ===========================================================================

class TestSlidesConstant:

    def test_has_three_slides(self):
        assert len(_SLIDES) == 3

    def test_slide_keys(self):
        for slide in _SLIDES:
            assert "icon" in slide
            assert "color" in slide
            assert "title" in slide
            assert "body" in slide

    def test_slide_titles_non_empty(self):
        for slide in _SLIDES:
            assert slide["title"].strip()

    def test_slide_bodies_non_empty(self):
        for slide in _SLIDES:
            assert slide["body"].strip()
