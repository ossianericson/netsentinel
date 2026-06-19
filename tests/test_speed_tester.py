"""Tests for modules/speed_tester.py — SpeedTestResult dataclass and helpers."""
from __future__ import annotations

import pytest


def test_import():
    import modules.speed_tester  # noqa: F401


def test_speed_test_result_dataclass():
    from modules.speed_tester import SpeedTestResult
    r = SpeedTestResult(
        download_mbps=100.5,
        upload_mbps=50.2,
        ping_ms=12.3,
        server_name="NYC Server",
        server_city="New York",
        server_country="US",
        backend="ookla",
        timestamp="2026-01-01T12:00:00",
        modem_signal=None,
    )
    assert r.download_mbps == pytest.approx(100.5)
    assert r.upload_mbps == pytest.approx(50.2)
    assert r.ping_ms == pytest.approx(12.3)
    assert r.backend == "ookla"
    assert r.modem_signal is None


def test_speed_test_result_minimal():
    from modules.speed_tester import SpeedTestResult
    r = SpeedTestResult(
        download_mbps=0.0, upload_mbps=0.0, ping_ms=0.0,
        server_name="", server_city="", server_country="",
        backend="pure_python", timestamp="", modem_signal=None,
    )
    assert r.backend == "pure_python"


def test_speed_to_fraction_zero():
    from modules.speed_tester import speed_to_fraction
    assert speed_to_fraction(0.0, 1000.0) == pytest.approx(0.0)


def test_speed_to_fraction_full():
    from modules.speed_tester import speed_to_fraction
    result = speed_to_fraction(1000.0, 1000.0)
    assert result <= 1.0


def test_speed_to_fraction_clamps():
    from modules.speed_tester import speed_to_fraction
    result = speed_to_fraction(2000.0, 1000.0)
    assert result <= 1.0


def test_speed_to_fraction_mid():
    from modules.speed_tester import speed_to_fraction
    result = speed_to_fraction(500.0, 1000.0)
    assert 0.0 < result <= 1.0


def test_speed_server_dataclass():
    from modules.speed_tester import SpeedServer
    s = SpeedServer(id="12345", name="NYC Server",
                    city="New York", country="US",
                    host="speedtest.example.com", latency_ms=5.0)
    assert s.id == "12345"
    assert s.country == "US"
    assert s.latency_ms == pytest.approx(5.0)


def test_find_ookla_cli_returns_path_or_none():
    """_find_ookla_cli() must return a Path or None, never raise."""
    from modules.speed_tester import _find_ookla_cli
    result = _find_ookla_cli()
    assert result is None or hasattr(result, "__fspath__")
