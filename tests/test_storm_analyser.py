"""Tests for modules/storm_analyser.py — broadcast storm analyser."""
import pytest
from modules.storm_analyser import (
    SCAPY_AVAILABLE, StormResult, THRESHOLD_WARNING, BROADCAST_MAC,
)


def test_import():
    import modules.storm_analyser as m
    assert hasattr(m, "scan")
    assert hasattr(m, "StormResult")
    assert hasattr(m, "SCAPY_AVAILABLE")
    assert hasattr(m, "BROADCAST_MAC")


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
    import modules.storm_analyser as m
    result = m.scan(duration=1)
    assert isinstance(result, StormResult)
    assert result.storm_level == "UNKNOWN"
