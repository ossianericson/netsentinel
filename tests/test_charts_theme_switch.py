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
