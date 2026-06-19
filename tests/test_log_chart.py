"""Tests for modules/log_chart.py — RTT chart data builder."""
import pytest


def test_log_chart_import():
    from modules import log_chart
    assert log_chart is not None


def test_build_figure_and_render_chart_exist():
    from modules.log_chart import build_figure, render_chart
    assert callable(build_figure)
    assert callable(render_chart)


def test_is_nan_helper():
    from modules.log_chart import _is_nan
    assert _is_nan(float("nan")) is True
    assert _is_nan(None) is True
    assert _is_nan("") is True
    assert _is_nan(0.0) is False
    assert _is_nan(42.5) is False


def test_build_figure_raises_on_empty_summary():
    """build_figure raises ValueError when there are no entries."""
    pytest.importorskip("matplotlib")
    from modules.log_chart import build_figure
    from dataclasses import dataclass, field

    @dataclass
    class EmptySummary:
        entries: list = field(default_factory=list)
        outages: dict = field(default_factory=dict)
        slow_periods: dict = field(default_factory=dict)
        csv_path: object = None

    with pytest.raises(ValueError, match="No log entries"):
        build_figure(EmptySummary())
