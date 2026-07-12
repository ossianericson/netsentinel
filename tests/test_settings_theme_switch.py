"""
Instant theme switching (Phase 4c) — settings + home-session surfaces restyle live.

Drives the real ``apply_theme`` -> ``_reapply_themed`` path (no Dashboard) and asserts:
  * a themed_ss-registered SettingsPage widget flips BG_CARD both directions
    (the registry path — proves settings_cards/settings_page conversions took),
  * the shape-I category chips restyle when the page's ``refresh_theme`` re-invokes
    the state-dependent setter (chips are deliberately NOT registered),
  * a StandardWelcomePage capability card flips live and its icon colour is resolved
    from the ACTIVE theme via ``getattr(_s, name)`` (the _FEATURES token-name conversion).

RULE-TP4-DASH does not apply — these are page/widget instances, not a Dashboard.
"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QLabel
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 not available", allow_module_level=True)

from ui import styles as _s
from ui.pages.settings_page import SettingsPage
from ui.widgets.home_session_widgets import StandardWelcomePage


def _teardown(w) -> None:
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # non-fatal — C++ object already gone
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


class TestSettingsLiveThemeSwitch:
    def test_registered_settings_widget_restyles_both_directions(self):
        """The themed_ss-registered search box flips BG_CARD on apply_theme."""
        arctic = _s.THEMES["Arctic Clean"]["BG_CARD"]
        midnight = _s.THEMES["Midnight Pro"]["BG_CARD"]
        assert arctic != midnight

        original = _s.get_active_theme_name()
        page = None
        try:
            _s.apply_theme("Arctic Clean")
            page = SettingsPage()
            ss_arctic = page._settings_search.styleSheet()
            assert arctic in ss_arctic and midnight not in ss_arctic

            _s.apply_theme("Midnight Pro")   # _reapply_themed runs inside apply_theme
            ss_mid = page._settings_search.styleSheet()
            assert midnight in ss_mid and arctic not in ss_mid

            _s.apply_theme("Arctic Clean")
            ss_back = page._settings_search.styleSheet()
            assert arctic in ss_back and midnight not in ss_back
        finally:
            _s.apply_theme(original)
            if page is not None:
                _teardown(page)

    def test_category_chips_restyle_on_refresh_theme(self):
        """Shape-I chips aren't registered; refresh_theme re-applies them with live tokens."""
        original = _s.get_active_theme_name()
        page = None
        try:
            _s.apply_theme("Arctic Clean")
            page = SettingsPage()
            active_chip = page._cat_btns[page._active_category]
            assert _s.THEMES["Arctic Clean"]["ACCENT"] in active_chip.styleSheet()

            _s.apply_theme("Midnight Pro")
            page.refresh_theme()   # dashboard fans this out on theme change
            assert _s.THEMES["Midnight Pro"]["ACCENT"] in active_chip.styleSheet()
        finally:
            _s.apply_theme(original)
            if page is not None:
                _teardown(page)


class TestHomeSessionLiveThemeSwitch:
    def test_capability_card_and_icon_resolve_live_theme(self):
        """Card frame flips BG_CARD; the icon colour resolves the active theme's AMBER."""
        original = _s.get_active_theme_name()
        card = None
        try:
            _s.apply_theme("Arctic Clean")
            # _FEATURES stores the icon colour as a token NAME ("AMBER").
            card = StandardWelcomePage._make_card("⚡", "Speed test", "AMBER", ["x"])
            app = QApplication.instance()
            if app:
                app.processEvents()

            assert _s.THEMES["Arctic Clean"]["BG_CARD"] in card.styleSheet()
            icon_lbl = next(
                lbl for lbl in card.findChildren(QLabel) if lbl.text() == "⚡"
            )
            assert _s.THEMES["Arctic Clean"]["AMBER"] in icon_lbl.styleSheet()

            _s.apply_theme("Midnight Pro")
            assert _s.THEMES["Midnight Pro"]["BG_CARD"] in card.styleSheet()
            assert _s.THEMES["Midnight Pro"]["AMBER"] in icon_lbl.styleSheet()
        finally:
            _s.apply_theme(original)
            if card is not None:
                _teardown(card)
