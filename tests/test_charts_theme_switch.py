"""
Instant theme switching (Phase 5) — matplotlib chart widgets restyle live.

Drives the real ``apply_theme`` path (no Dashboard) and asserts, for the two
embedded chart widgets:
  * the canvas widget background (themed_ss-registered) flips both directions,
  * ``refresh_theme()`` re-reads the matplotlib figure facecolor from the active
    theme and does not raise,
  * the live colour accessors (``_target_colors`` / ``_risk_node_color``) resolve
    the ACTIVE theme rather than an import-time frozen value.

RULE-TP4-DASH does not apply — these are plain QWidget instances, not a Dashboard.
"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 not available", allow_module_level=True)

matplotlib = pytest.importorskip("matplotlib")
from matplotlib.colors import to_rgba  # noqa: E402

from ui import styles as _s  # noqa: E402


def _teardown(w) -> None:
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # non-fatal — C++ object already gone
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


class TestLiveGraphThemeSwitch:
    def test_canvas_and_figure_restyle_both_directions(self):
        from ui.live_graph import LiveGraphWidget, _target_colors

        arctic = _s.THEMES["Arctic Clean"]["CHART_BG"]
        midnight = _s.THEMES["Midnight Pro"]["CHART_BG"]
        assert arctic != midnight

        original = _s.get_active_theme_name()
        w = None
        try:
            _s.apply_theme("Arctic Clean")
            w = LiveGraphWidget()
            # Canvas background is themed_ss-registered → re-applied by apply_theme.
            assert arctic in w._canvas.styleSheet()
            assert _target_colors()["1.1.1.1"] == _s.THEMES["Arctic Clean"]["ACCENT"]

            _s.apply_theme("Midnight Pro")
            assert midnight in w._canvas.styleSheet() and arctic not in w._canvas.styleSheet()
            w.refresh_theme()   # dashboard forwards this on theme_changed
            assert w._fig.get_facecolor() == to_rgba(midnight)
            assert _target_colors()["1.1.1.1"] == _s.THEMES["Midnight Pro"]["ACCENT"]

            _s.apply_theme("Arctic Clean")
            w.refresh_theme()
            assert w._fig.get_facecolor() == to_rgba(arctic)
        finally:
            _s.apply_theme(original)
            if w is not None:
                _teardown(w)


class TestTopologyThemeSwitch:
    def test_canvas_and_figure_restyle_both_directions(self):
        from ui.topology_widget import TopologyWidget, _risk_node_color

        arctic = _s.THEMES["Arctic Clean"]["BG_DARK"]
        midnight = _s.THEMES["Midnight Pro"]["BG_DARK"]
        assert arctic != midnight

        original = _s.get_active_theme_name()
        w = None
        try:
            _s.apply_theme("Arctic Clean")
            w = TopologyWidget()
            assert arctic in w._canvas.styleSheet()
            assert _risk_node_color("HIGH") == _s.THEMES["Arctic Clean"]["RED"]

            _s.apply_theme("Midnight Pro")
            assert midnight in w._canvas.styleSheet() and arctic not in w._canvas.styleSheet()
            w.refresh_theme()   # no render yet → restyles empty axes, must not raise
            assert w._fig.get_facecolor() == to_rgba(midnight)
            assert _risk_node_color("HIGH") == _s.THEMES["Midnight Pro"]["RED"]

            _s.apply_theme("Arctic Clean")
            w.refresh_theme()
            assert w._fig.get_facecolor() == to_rgba(arctic)
        finally:
            _s.apply_theme(original)
            if w is not None:
                _teardown(w)


class TestSpeedGaugeThemeSwitch:
    """Phase 5 commit 2 — Speed Test gauge widget restyles live."""

    def test_canvas_figure_and_phase_colours_restyle(self):
        from ui.pages.speed_test_page import (
            SpeedGaugeWidget, _color_download, _color_upload,
        )

        arctic = _s.THEMES["Arctic Clean"]["BG_CARD"]
        midnight = _s.THEMES["Midnight Pro"]["BG_CARD"]
        assert arctic != midnight

        original = _s.get_active_theme_name()
        w = None
        try:
            _s.apply_theme("Arctic Clean")
            w = SpeedGaugeWidget()
            assert arctic in w._canvas.styleSheet()
            assert _color_download() == _s.THEMES["Arctic Clean"]["ACCENT"]

            _s.apply_theme("Midnight Pro")
            assert midnight in w._canvas.styleSheet() and arctic not in w._canvas.styleSheet()
            w.refresh_theme()
            assert w._fig.get_facecolor() == to_rgba(midnight)
            assert _color_download() == _s.THEMES["Midnight Pro"]["ACCENT"]
            assert _color_upload() == _s.THEMES["Midnight Pro"]["GREEN"]

            _s.apply_theme("Arctic Clean")
            w.refresh_theme()
            assert w._fig.get_facecolor() == to_rgba(arctic)
        finally:
            _s.apply_theme(original)
            if w is not None:
                _teardown(w)


class TestHistoryChartCardThemeSwitch:
    """Phase 5 commit 2 — history page's _ChartCard + series colours live."""

    def test_card_restyle_and_series_colours(self):
        from ui.pages.history_page import _ChartCard, _series_colors, _state_colors

        arctic = _s.THEMES["Arctic Clean"]["BG_CARD"]
        midnight = _s.THEMES["Midnight Pro"]["BG_CARD"]
        assert arctic != midnight

        original = _s.get_active_theme_name()
        w = None
        try:
            _s.apply_theme("Arctic Clean")
            w = _ChartCard("RTT", height=160)
            assert arctic in w._canvas.styleSheet()
            assert _series_colors()[0] == _s.THEMES["Arctic Clean"]["ACCENT"]
            assert _state_colors()["UP"] == _s.THEMES["Arctic Clean"]["GREEN"]

            _s.apply_theme("Midnight Pro")
            assert midnight in w._canvas.styleSheet() and arctic not in w._canvas.styleSheet()
            w.refresh_theme()
            assert w._fig.get_facecolor() == to_rgba(midnight)
            assert _series_colors()[0] == _s.THEMES["Midnight Pro"]["ACCENT"]
            assert _state_colors()["DOWN"] == _s.THEMES["Midnight Pro"]["RED"]
        finally:
            _s.apply_theme(original)
            if w is not None:
                _teardown(w)


class TestRttMiniChartThemeSwitch:
    """Phase 5 commit 2 — home-automation RTT mini-chart restyles live."""

    def test_canvas_and_figure_restyle(self):
        from ui.pages.home_automation_page import _RttMiniChart

        arctic = _s.THEMES["Arctic Clean"]["BG_CARD"]
        midnight = _s.THEMES["Midnight Pro"]["BG_CARD"]
        assert arctic != midnight

        original = _s.get_active_theme_name()
        w = None
        try:
            _s.apply_theme("Arctic Clean")
            w = _RttMiniChart()
            assert arctic in w._canvas.styleSheet()

            _s.apply_theme("Midnight Pro")
            assert midnight in w._canvas.styleSheet() and arctic not in w._canvas.styleSheet()
            w.refresh_theme()   # no data → redraws empty, must not raise
            assert w._fig.get_facecolor() == to_rgba(midnight)
        finally:
            _s.apply_theme(original)
            if w is not None:
                _teardown(w)


class TestGeoAndWifiLiveColours:
    """Phase 5 commit 2 — map/heatmap live colour accessors track the theme."""

    def test_marker_and_dbm_colours_follow_active_theme(self):
        from ui.pages.geo_map_page import _marker_color, _CAT_THREAT
        from ui.pages.wifi_heatmap_page import _dbm_color

        original = _s.get_active_theme_name()
        try:
            _s.apply_theme("Arctic Clean")
            assert _marker_color()[_CAT_THREAT] == _s.THEMES["Arctic Clean"]["RED"]
            assert _dbm_color(-50.0) == _s.THEMES["Arctic Clean"]["GREEN"]

            _s.apply_theme("Midnight Pro")
            assert _marker_color()[_CAT_THREAT] == _s.THEMES["Midnight Pro"]["RED"]
            assert _dbm_color(-50.0) == _s.THEMES["Midnight Pro"]["GREEN"]
            assert _dbm_color(-90.0) == _s.THEMES["Midnight Pro"]["RED"]
        finally:
            _s.apply_theme(original)
