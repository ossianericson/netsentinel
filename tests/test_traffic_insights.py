"""
tests/test_traffic_insights.py — Unit tests for modules/traffic_insights.py (Sprint 6).
"""

from modules.traffic_insights import (
    build_qos_recommendation,
    build_usage_insights,
    compute_plan_utilization,
    find_category_overlap_window,
    format_bytes,
    format_hour_range,
    format_insight_summary,
)


def test_format_bytes_scales():
    assert format_bytes(500) == "500 B"
    assert format_bytes(2_500) == "2.5 KB"
    assert format_bytes(3_000_000) == "3.0 MB"
    assert format_bytes(187_000_000_000) == "187.0 GB"
    assert format_bytes(2_000_000_000_000) == "2.0 TB"


def test_format_hour_range():
    assert format_hour_range((19, 23)) == "7pm and 11pm"
    assert format_hour_range((0, 6)) == "12am and 6am"
    assert format_hour_range((12, 13)) == "12pm and 1pm"


# ── build_usage_insights / format_insight_summary (S6-3) ──────────────────

def test_build_usage_insights_no_data():
    insight = build_usage_insights({})
    assert insight.has_data is False
    assert "Not enough traffic data" in format_insight_summary(insight)


def test_build_usage_insights_dominant_category_and_peak_window():
    totals = {"Streaming": 680_000_000, "Web": 320_000_000}
    hourly = {19: 1000, 20: 5000, 21: 5000, 22: 4000, 23: 500, 9: 100}
    insight = build_usage_insights(totals, dominant_category_hourly=hourly)
    assert insight.has_data is True
    assert insight.dominant_category == "Streaming"
    assert round(insight.dominant_pct) == 68
    assert insight.peak_window is not None

    summary = format_insight_summary(insight)
    assert "streaming" in summary.lower()
    assert "68%" in summary


def test_build_usage_insights_week_over_week_change():
    totals = {"Gaming": 100_000}
    last_week = {"Gaming": 50_000}
    insight = build_usage_insights(totals, last_week_category_totals=last_week)
    assert insight.change_category == "Gaming"
    assert insight.change_pct == 100.0
    summary = format_insight_summary(insight)
    assert "increased" in summary
    assert "100%" in summary


def test_build_usage_insights_decrease():
    totals = {"Gaming": 50_000}
    last_week = {"Gaming": 100_000}
    insight = build_usage_insights(totals, last_week_category_totals=last_week)
    assert insight.change_pct == -50.0
    summary = format_insight_summary(insight)
    assert "decreased" in summary


def test_build_usage_insights_no_prior_week_data():
    totals = {"Gaming": 50_000}
    insight = build_usage_insights(totals, last_week_category_totals={})
    assert insight.change_pct == 100.0   # new traffic that didn't exist last week


# ── compute_plan_utilization (S6-4) ────────────────────────────────────────

def test_compute_plan_utilization_no_plan_configured():
    assert compute_plan_utilization(1_000_000_000, None) is None
    assert compute_plan_utilization(1_000_000_000, 0) is None


def test_compute_plan_utilization_with_plan():
    text = compute_plan_utilization(120_000_000_000, 1000.0)
    assert "12%" in text


# ── QoS overlap detection (S6-5) ───────────────────────────────────────────

def test_find_category_overlap_window_detects_overlap():
    gaming = {h: 0 for h in range(24)}
    voip = {h: 0 for h in range(24)}
    for h in range(9, 17):
        gaming[h] = 1000
        voip[h] = 800
    window = find_category_overlap_window(gaming, voip)
    assert window is not None
    assert window[0] == 9
    assert window[1] == 17


def test_find_category_overlap_window_no_overlap():
    gaming = {h: 0 for h in range(24)}
    voip = {h: 0 for h in range(24)}
    gaming[20] = 1000
    voip[9] = 800
    assert find_category_overlap_window(gaming, voip) is None


def test_find_category_overlap_window_empty_input():
    assert find_category_overlap_window({}, {}) is None


def test_build_qos_recommendation_text():
    gaming = {h: 0 for h in range(24)}
    voip = {h: 0 for h in range(24)}
    for h in range(9, 17):
        gaming[h] = 1000
        voip[h] = 800
    text = build_qos_recommendation("Gaming", gaming, "VoIP", voip)
    assert text is not None
    assert "Gaming" in text and "VoIP" in text
    assert "QoS" in text


def test_build_qos_recommendation_none_when_short_overlap():
    gaming = {h: 0 for h in range(24)}
    voip = {h: 0 for h in range(24)}
    gaming[10] = 1000
    voip[10] = 800
    assert build_qos_recommendation("Gaming", gaming, "VoIP", voip) is None
