"""Tests for modules/alert_pattern_detector.py (S4-6 pattern-based suppression)."""
import datetime
from unittest.mock import MagicMock


def _ts_for(day_of_week: int, hour: int, week_offset: int = 0) -> int:
    """Return a Unix timestamp for a given weekday/hour in the past."""
    now = datetime.datetime.now()
    # Go back (week_offset + 1) weeks, then find the right weekday
    target = now - datetime.timedelta(weeks=week_offset + 1)
    diff = (day_of_week - target.weekday()) % 7
    target = target + datetime.timedelta(days=diff)
    target = target.replace(hour=hour, minute=0, second=0, microsecond=0)
    return int(target.timestamp())


def _make_alert(rule_name: str, host: str, day_of_week: int, hour: int,
                week_offset: int, severity: str = "CRITICAL") -> dict:
    return {
        "rule_name": rule_name,
        "host": host,
        "ts": _ts_for(day_of_week, hour, week_offset),
        "severity": severity,
    }


def _make_store(alerts):
    store = MagicMock()
    store.get_recent_alerts.return_value = alerts
    return store


# ── Import ────────────────────────────────────────────────────────────────────

def test_import():
    from modules.alert_pattern_detector import PatternDetector, SuppSuggestion
    assert PatternDetector
    assert SuppSuggestion


# ── No alerts — no suggestions ────────────────────────────────────────────────

def test_empty_store_returns_no_suggestions():
    from modules.alert_pattern_detector import PatternDetector
    store = _make_store([])
    detector = PatternDetector()
    assert detector.find_suggestions(store) == []


# ── One-off alert — no suggestion ────────────────────────────────────────────

def test_single_occurrence_no_suggestion():
    from modules.alert_pattern_detector import PatternDetector
    alerts = [_make_alert("Host Down", "192.168.1.1", 0, 2, 0)]  # only 1 week
    store = _make_store(alerts)
    detector = PatternDetector()
    assert detector.find_suggestions(store) == []


# ── Two occurrences — below threshold ────────────────────────────────────────

def test_two_occurrences_below_threshold():
    from modules.alert_pattern_detector import PatternDetector
    alerts = [
        _make_alert("Host Down", "192.168.1.1", 0, 2, 0),
        _make_alert("Host Down", "192.168.1.1", 0, 2, 1),
    ]
    store = _make_store(alerts)
    detector = PatternDetector()
    assert detector.find_suggestions(store) == []


# ── Three occurrences — suggestion returned ───────────────────────────────────

def test_three_occurrences_generates_suggestion():
    from modules.alert_pattern_detector import PatternDetector
    alerts = [
        _make_alert("Host Down", "192.168.1.1", 0, 2, 0),  # this week
        _make_alert("Host Down", "192.168.1.1", 0, 2, 1),  # last week
        _make_alert("Host Down", "192.168.1.1", 0, 2, 2),  # 2 weeks ago
    ]
    store = _make_store(alerts)
    detector = PatternDetector()
    suggestions = detector.find_suggestions(store)
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s.rule_name == "Host Down"
    assert s.host == "192.168.1.1"
    assert s.occurrences == 3


# ── Suggestion description is human-readable ──────────────────────────────────

def test_suggestion_has_description():
    from modules.alert_pattern_detector import PatternDetector
    alerts = [
        _make_alert("Service Down", "8.8.8.8", 2, 3, 0),
        _make_alert("Service Down", "8.8.8.8", 2, 3, 1),
        _make_alert("Service Down", "8.8.8.8", 2, 3, 2),
    ]
    store = _make_store(alerts)
    detector = PatternDetector()
    suggestions = detector.find_suggestions(store)
    assert suggestions
    s = suggestions[0]
    assert "Wednesday" in s.description or "03:00" in s.description
    assert len(s.suggested_label) > 0


# ── Window bounds include buffer ──────────────────────────────────────────────

def test_window_bounds_include_buffer():
    from modules.alert_pattern_detector import _window_bounds
    start_h, start_m, end_h, end_m = _window_bounds(2)
    # 2:00 with ±30 min buffer → start at 1:30, end at 3:30
    assert (start_h, start_m) == (1, 30)
    assert (end_h, end_m) == (3, 30)


def test_window_bounds_midnight_floor():
    from modules.alert_pattern_detector import _window_bounds
    start_h, start_m, end_h, end_m = _window_bounds(0)
    # Can't go before 00:00
    assert start_h == 0
    assert start_m == 0


# ── INFO alerts are ignored ───────────────────────────────────────────────────

def test_info_alerts_ignored():
    from modules.alert_pattern_detector import PatternDetector
    alerts = [
        _make_alert("New Device", "192.168.1.50", 3, 14, 0, severity="INFO"),
        _make_alert("New Device", "192.168.1.50", 3, 14, 1, severity="INFO"),
        _make_alert("New Device", "192.168.1.50", 3, 14, 2, severity="INFO"),
    ]
    store = _make_store(alerts)
    detector = PatternDetector()
    # INFO alerts should not produce suppression suggestions
    assert detector.find_suggestions(store) == []


# ── SuppSuggestion.day_name ───────────────────────────────────────────────────

def test_sugg_day_name():
    from modules.alert_pattern_detector import SuppSuggestion
    s = SuppSuggestion(
        rule_name="Test", host="x", day_of_week=0, hour_of_day=2,
        occurrences=3, suggested_label="lbl",
        window_start_h=1, window_start_m=30, window_end_h=3, window_end_m=30,
        description="test",
    )
    assert s.day_name == "Monday"

    s2 = SuppSuggestion(
        rule_name="Test", host="x", day_of_week=6, hour_of_day=2,
        occurrences=3, suggested_label="lbl",
        window_start_h=1, window_start_m=30, window_end_h=3, window_end_m=30,
        description="test",
    )
    assert s2.day_name == "Sunday"


# ── Store error handled gracefully ────────────────────────────────────────────

def test_store_error_returns_empty():
    from modules.alert_pattern_detector import PatternDetector
    store = MagicMock()
    store.get_recent_alerts.side_effect = RuntimeError("DB error")
    detector = PatternDetector()
    result = detector.find_suggestions(store)
    assert result == []
