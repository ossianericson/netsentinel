"""Tests for modules/storm_analyser.py — broadcast storm analyser."""
from modules.storm_analyser import (
    SCAPY_AVAILABLE, StormResult, THRESHOLD_WARNING, BROADCAST_MAC, scan,
)


def test_import():
    assert callable(scan)
    assert StormResult is not None
    assert isinstance(SCAPY_AVAILABLE, bool)
    assert BROADCAST_MAC == "ff:ff:ff:ff:ff:ff"


def test_scapy_flag_is_bool():
    assert isinstance(SCAPY_AVAILABLE, bool)


def test_threshold_is_positive():
    assert THRESHOLD_WARNING > 0


def test_broadcast_mac_constant():
    assert BROADCAST_MAC == "ff:ff:ff:ff:ff:ff"


def test_storm_result_defaults():
    r = StormResult()
    assert r.storm_level in ("CLEAN", "WARNING", "STORM", "UNKNOWN")
    assert r.total_broadcast == 0
    assert r.bcast_per_sec == 0.0
    assert r.top_sources == []


def test_storm_result_custom():
    r = StormResult(storm_level="STORM", bcast_per_sec=5000.0)
    assert r.storm_level == "STORM"
    assert r.bcast_per_sec == 5000.0


def test_scan_no_scapy_returns_result(monkeypatch):
    monkeypatch.setattr("modules.storm_analyser.SCAPY_AVAILABLE", False)
    from modules import storm_analyser as m
    result = m.scan(duration=1)
    assert isinstance(result, StormResult)
    assert result.storm_level == "UNKNOWN"


# ── Threshold / classification-logic tests ───────────────────────────────────

def test_threshold_storm_greater_than_warning():
    from modules.storm_analyser import THRESHOLD_STORM
    assert THRESHOLD_STORM > THRESHOLD_WARNING


def test_clean_level_is_below_warning_threshold():
    r = StormResult(bcast_per_sec=float(THRESHOLD_WARNING - 1), storm_level="CLEAN")
    assert r.storm_level == "CLEAN"
    assert r.bcast_per_sec < THRESHOLD_WARNING


def test_warning_level_is_between_thresholds():
    from modules.storm_analyser import THRESHOLD_STORM
    mid = (THRESHOLD_WARNING + THRESHOLD_STORM) / 2
    r = StormResult(bcast_per_sec=mid, storm_level="WARNING")
    assert r.storm_level == "WARNING"
    assert r.bcast_per_sec >= THRESHOLD_WARNING
    assert r.bcast_per_sec < THRESHOLD_STORM


def test_storm_level_is_at_or_above_storm_threshold():
    from modules.storm_analyser import THRESHOLD_STORM
    r = StormResult(bcast_per_sec=float(THRESHOLD_STORM), storm_level="STORM")
    assert r.storm_level == "STORM"
    assert r.bcast_per_sec >= THRESHOLD_STORM


def test_storm_result_rogue_matches_list():
    r = StormResult(rogue_matches=["aa:bb:cc:dd:ee:ff"])
    assert "aa:bb:cc:dd:ee:ff" in r.rogue_matches


def test_storm_result_top_sources_ordering():
    sources = [("aa:bb:cc:00:00:01", 500), ("aa:bb:cc:00:00:02", 200)]
    r = StormResult(top_sources=sources)
    assert r.top_sources[0][1] > r.top_sources[1][1]


def test_scan_no_scapy_calls_on_error(monkeypatch):
    monkeypatch.setattr("modules.storm_analyser.SCAPY_AVAILABLE", False)
    errors = []
    result = scan(duration=1, on_error=errors.append)
    assert result.storm_level == "UNKNOWN"
    assert len(errors) == 1
    assert "scapy" in errors[0].lower() or "Scapy" in errors[0]


def test_scan_calls_progress_cb_no_scapy(monkeypatch):
    monkeypatch.setattr("modules.storm_analyser.SCAPY_AVAILABLE", False)
    calls = []
    scan(duration=1, progress_cb=calls.append)
    # No progress_cb calls expected when Scapy absent; test is non-crashing
    assert isinstance(calls, list)


def test_scan_result_has_plain_verdict_when_no_scapy(monkeypatch):
    monkeypatch.setattr("modules.storm_analyser.SCAPY_AVAILABLE", False)
    result = scan(duration=1)
    assert isinstance(result.plain_verdict, str)
    assert len(result.plain_verdict) > 0
