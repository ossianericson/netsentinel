"""Tests for the S8-4 trend-history pure helpers in ui/pages/speed_test_page.py."""
from unittest.mock import MagicMock

import pytest

try:
    import PyQt6  # noqa: F401
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

from ui.pages.speed_test_page import (
    _compute_speed_comparison,
    _format_hour_12h,
    _ordinal,
    _rolling_average_download,
    _time_of_day_insight,
)


def _point(ts, dl):
    p = MagicMock()
    p.ts = ts
    p.download_mbps = dl
    return p


# ── _format_hour_12h ──────────────────────────────────────────────────────────

def test_format_hour_12h_midnight_and_noon():
    assert _format_hour_12h(0) == "12am"
    assert _format_hour_12h(12) == "12pm"


def test_format_hour_12h_am_pm():
    assert _format_hour_12h(3) == "3am"
    assert _format_hour_12h(15) == "3pm"


# ── _rolling_average_download ─────────────────────────────────────────────────

def test_rolling_average_single_point_equals_itself():
    points = [_point(1_000_000, 50.0)]
    assert _rolling_average_download(points, 7.0) == [50.0]


def test_rolling_average_window_includes_only_trailing_points():
    day = 86400
    points = [
        _point(0, 10.0),
        _point(8 * day, 20.0),   # outside a 7-day window from the first point
    ]
    avgs = _rolling_average_download(points, 7.0)
    # Second point's window (last 7 days ending at its own ts) excludes the first.
    assert avgs[1] == 20.0


def test_rolling_average_averages_points_within_window():
    day = 86400
    points = [_point(0, 10.0), _point(1 * day, 20.0), _point(2 * day, 30.0)]
    avgs = _rolling_average_download(points, 7.0)
    assert avgs[2] == pytest.approx((10.0 + 20.0 + 30.0) / 3)


def test_rolling_average_empty_list():
    assert _rolling_average_download([], 7.0) == []


# ── _time_of_day_insight ───────────────────────────────────────────────────────

def test_time_of_day_insight_none_with_too_few_points():
    points = [_point(i, 50.0) for i in range(3)]
    assert _time_of_day_insight(points) is None


def test_time_of_day_insight_none_with_too_few_distinct_hours():
    import datetime as _dt
    base = _dt.datetime(2024, 1, 1, 9, 0).timestamp()
    points = [_point(base + i, 50.0) for i in range(6)]   # all same hour
    assert _time_of_day_insight(points) is None


def test_time_of_day_insight_identifies_fastest_and_slowest_hours():
    import datetime as _dt

    def _ts_at_hour(day, hour):
        return _dt.datetime(2024, 1, day, hour, 0).timestamp()

    points = []
    for day in range(1, 6):
        points.append(_point(_ts_at_hour(day, 3), 200.0))   # fast at 3am
        points.append(_point(_ts_at_hour(day, 20), 20.0))   # slow at 8pm
        points.append(_point(_ts_at_hour(day, 12), 100.0))  # mid at noon
    insight = _time_of_day_insight(points)
    assert insight is not None
    assert "3am" in insight
    assert "8pm" in insight


# ── _ordinal ────────────────────────────────────────────────────────────────

def test_ordinal_basic_cases():
    assert _ordinal(1) == "1st"
    assert _ordinal(2) == "2nd"
    assert _ordinal(3) == "3rd"
    assert _ordinal(4) == "4th"


def test_ordinal_teens_use_th():
    assert _ordinal(11) == "11th"
    assert _ordinal(12) == "12th"
    assert _ordinal(13) == "13th"
    assert _ordinal(21) == "21st"


# ── _compute_speed_comparison ─────────────────────────────────────────────────

def test_comparison_none_with_no_recent_history():
    assert _compute_speed_comparison([], 1_000_000.0, 50.0) is None


def test_comparison_ranks_new_test_among_recent():
    day = 86400
    now = 30 * day
    history = [_point(now - 5 * day, 80.0), _point(now - 2 * day, 60.0), _point(now, 100.0)]
    text = _compute_speed_comparison(history, now, 100.0)
    assert text is not None
    assert "1st fastest" in text
    assert "Monthly average is 80 Mbps" in text


def test_comparison_reports_down_pct_vs_last_month():
    day = 86400
    now = 60 * day
    # Last 30 days: avg 50; prior 30 days (30-60 days ago): avg 100 → down 50%
    history = [
        _point(now - 1 * day, 50.0),
        _point(now - 40 * day, 100.0),
        _point(now - 45 * day, 100.0),
    ]
    text = _compute_speed_comparison(history, now, 50.0)
    assert text is not None
    assert "down 50%" in text


def test_comparison_reports_up_pct_vs_last_month():
    day = 86400
    now = 60 * day
    history = [
        _point(now - 1 * day, 150.0),
        _point(now - 40 * day, 100.0),
    ]
    text = _compute_speed_comparison(history, now, 150.0)
    assert "up 50%" in text


def test_comparison_no_prior_period_omits_trend_clause():
    day = 86400
    now = 10 * day
    history = [_point(now - 1 * day, 90.0)]
    text = _compute_speed_comparison(history, now, 90.0)
    assert text is not None
    assert "last month" not in text
