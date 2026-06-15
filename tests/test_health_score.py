"""
tests/test_health_score.py — Unit tests for modules/health_score.py
"""
from datetime import datetime
from unittest.mock import MagicMock

import pytest


# ── Import guard ──────────────────────────────────────────────────────────────

try:
    from modules.health_score import HealthScoreCalculator, HealthSnapshot
except ImportError:
    pytest.skip("modules.health_score not available", allow_module_level=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rtt_point(rtt_ms: float):
    """Create a mock RTT data point with .rtt_ms attribute (matches MetricStore output)."""
    p = MagicMock()
    p.rtt_ms = rtt_ms
    return p


def _make_store(uptime_rows=None, rtt_hosts=None, rtt_points=None, alerts=None,
                raise_uptime=False, raise_rtt=False, raise_alerts=False):
    """
    Return a mock MetricStore.

    Uptime rows use {"24h": pct} format matching query_uptime_table output.
    RTT points are objects with .rtt_ms attribute matching query_rtt_history output.
    """
    store = MagicMock()

    if raise_uptime:
        store.query_uptime_table.side_effect = RuntimeError("db error")
    else:
        store.query_uptime_table.return_value = uptime_rows or []

    if raise_rtt:
        store.query_all_rtt_hosts.side_effect = RuntimeError("db error")
    else:
        store.query_all_rtt_hosts.return_value = rtt_hosts or []
        store.query_rtt_history.return_value = rtt_points or []

    if raise_alerts:
        store.get_recent_alerts.side_effect = RuntimeError("db error")
    else:
        store.get_recent_alerts.return_value = alerts or []

    return store


# ── Import / instantiation ────────────────────────────────────────────────────

def test_import():
    assert HealthScoreCalculator is not None
    assert HealthSnapshot is not None


def test_calculator_instantiation():
    calc = HealthScoreCalculator()
    assert calc is not None


# ── HealthSnapshot dataclass ──────────────────────────────────────────────────

def test_snapshot_fields():
    snap = HealthSnapshot(
        score=80,
        state="green",
        headline="All clear",
        sub_text="Everything is fine.",
        checked_at=datetime.now(),
        stable_hours=3.0,
    )
    assert snap.score == 80
    assert snap.state == "green"
    assert snap.headline == "All clear"
    assert isinstance(snap.checked_at, datetime)


# ── Unknown / None store ──────────────────────────────────────────────────────

def test_compute_none_store_returns_unknown():
    """Passing None as store always returns 'unknown'."""
    calc = HealthScoreCalculator()
    snap = calc.compute(None)
    assert snap.state == "unknown"
    assert isinstance(snap.score, int)


def test_compute_all_sources_error_returns_unknown():
    """When all three MetricStore queries raise, compute returns 'unknown'."""
    calc = HealthScoreCalculator()
    store = _make_store(raise_uptime=True, raise_rtt=True, raise_alerts=True)
    snap = calc.compute(store)
    assert snap.state == "unknown"


# ── Green state ───────────────────────────────────────────────────────────────

def test_compute_green_high_availability():
    """100% uptime + fast RTT + no alerts → green."""
    calc = HealthScoreCalculator()
    # Uptime rows use "24h" key (matches query_uptime_table output format)
    uptime_rows = [
        {"host": "8.8.8.8", "24h": 100.0},
        {"host": "1.1.1.1", "24h": 100.0},
    ]
    rtt_hosts = ["8.8.8.8", "1.1.1.1"]
    rtt_points = [_rtt_point(10.0), _rtt_point(12.0)]
    store = _make_store(uptime_rows=uptime_rows, rtt_hosts=rtt_hosts, rtt_points=rtt_points)
    snap = calc.compute(store)
    assert snap.state == "green"
    assert snap.score >= 75


def test_green_state_headline_is_all_clear():
    """S2-4: green state headline must communicate 'all clear' or stability."""
    calc = HealthScoreCalculator()
    uptime_rows = [{"host": "8.8.8.8", "24h": 100.0}]
    rtt_points = [_rtt_point(5.0)]
    store = _make_store(uptime_rows=uptime_rows, rtt_hosts=["8.8.8.8"], rtt_points=rtt_points)
    snap = calc.compute(store)
    assert snap.state == "green"
    headline_lower = snap.headline.lower()
    assert any(kw in headline_lower for kw in ("all clear", "looks good", "stable", "healthy"))


# ── Amber state ───────────────────────────────────────────────────────────────

def test_compute_amber_with_several_alerts():
    """Enough alerts should push score to amber range (45-74)."""
    calc = HealthScoreCalculator()
    # 4 alerts → alert_score = 100 - 4*15 = 40
    # score = int(80*0.45 + 40*0.35 + 80*0.20) = int(36+14+16) = 66 → amber
    alerts = [{"id": i} for i in range(4)]
    store = _make_store(alerts=alerts)   # no uptime/rtt — defaults to 80
    snap = calc.compute(store)
    assert snap.state in ("amber", "red")


def test_alerts_lower_score():
    """Adding alerts must lower the score compared to no alerts."""
    calc = HealthScoreCalculator()
    uptime_rows = [{"host": "8.8.8.8", "24h": 90.0}]

    store_alerts = _make_store(uptime_rows=uptime_rows, alerts=[{"id": i} for i in range(3)])
    store_clean = _make_store(uptime_rows=uptime_rows)

    snap_alerts = calc.compute(store_alerts)
    snap_clean = calc.compute(store_clean)

    assert snap_alerts.score < snap_clean.score


# ── Red state ─────────────────────────────────────────────────────────────────

def test_compute_red_many_alerts_low_uptime():
    """Very low availability + many alerts → red (score < 45)."""
    calc = HealthScoreCalculator()
    uptime_rows = [{"host": "8.8.8.8", "24h": 20.0}]
    # 7+ alerts → alert_score = 0
    alerts = [{"id": i} for i in range(7)]
    store = _make_store(uptime_rows=uptime_rows, alerts=alerts)
    snap = calc.compute(store)
    assert snap.state == "red"
    assert snap.score < 45


# ── Score boundaries ──────────────────────────────────────────────────────────

def test_score_is_bounded_0_to_100():
    calc = HealthScoreCalculator()

    # Best case: perfect uptime, fast RTT, no alerts
    uptime_rows = [{"host": "8.8.8.8", "24h": 100.0}]
    store = _make_store(uptime_rows=uptime_rows,
                        rtt_hosts=["8.8.8.8"],
                        rtt_points=[_rtt_point(1.0)])
    snap = calc.compute(store)
    assert 0 <= snap.score <= 100

    # Worst case: zero uptime, many alerts
    store_bad = _make_store(uptime_rows=[{"host": "8.8.8.8", "24h": 0.0}],
                            alerts=[{"id": i} for i in range(20)])
    snap_bad = calc.compute(store_bad)
    assert 0 <= snap_bad.score <= 100


# ── Metadata fields ───────────────────────────────────────────────────────────

def test_snapshot_has_checked_at():
    calc = HealthScoreCalculator()
    snap = calc.compute(None)
    assert isinstance(snap.checked_at, datetime)


def test_snapshot_sub_text_non_empty():
    calc = HealthScoreCalculator()
    snap = calc.compute(None)
    assert isinstance(snap.sub_text, str)
    assert len(snap.sub_text) > 0


def test_snapshot_headline_non_empty():
    calc = HealthScoreCalculator()
    snap = calc.compute(None)
    assert isinstance(snap.headline, str)
    assert len(snap.headline) > 0
