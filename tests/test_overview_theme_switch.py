"""
Instant theme switching (Phase 4b) — overview tiles restyle live, both directions.

Drives the real ``apply_theme`` → ``_reapply_themed`` path (no GUI) and asserts a
themed_ss-registered tile frame flips its BG_CARD between the two themes, and that
a data-driven tile colour is resolved from the LIVE theme at data time (proving the
handler reads ``_s.TOKEN`` rather than a frozen import value).
"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 not available", allow_module_level=True)

from ui import styles as _s
from ui.widgets.overview_tile import DeviceCountTile


def _teardown(w) -> None:
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # non-fatal — C++ object already gone
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


class TestOverviewLiveThemeSwitch:
    def test_tile_frame_restyles_live_both_directions(self):
        """The themed_ss-registered tile frame flips BG_CARD on apply_theme."""
        arctic = _s.THEMES["Arctic Clean"]["BG_CARD"]
        midnight = _s.THEMES["Midnight Pro"]["BG_CARD"]
        assert arctic != midnight

        original = _s.get_active_theme_name()
        tile = None
        try:
            _s.apply_theme("Arctic Clean")
            tile = DeviceCountTile(store=None)
            app = QApplication.instance()
            if app:
                app.processEvents()

            ss_arctic = tile.styleSheet()
            assert arctic in ss_arctic and midnight not in ss_arctic

            _s.apply_theme("Midnight Pro")   # _reapply_themed runs inside apply_theme
            ss_mid = tile.styleSheet()
            assert midnight in ss_mid and arctic not in ss_mid

            _s.apply_theme("Arctic Clean")
            ss_back = tile.styleSheet()
            assert arctic in ss_back and midnight not in ss_back
        finally:
            _s.apply_theme(original)
            if tile is not None:
                _teardown(tile)

    def test_data_driven_health_colour_reads_live_theme(self):
        """update_cycle resolves the health colour from the ACTIVE theme, not a frozen import."""
        original = _s.get_active_theme_name()
        tile = None
        try:
            _s.apply_theme("Midnight Pro")
            tile = DeviceCountTile(store=None)
            tile.update_cycle({"192.168.1.1": "DOWN"})   # a DOWN host -> health RED
            red_mid = _s.THEMES["Midnight Pro"]["RED"]
            assert red_mid in tile._health_bar.styleSheet()
        finally:
            _s.apply_theme(original)
            if tile is not None:
                _teardown(tile)
