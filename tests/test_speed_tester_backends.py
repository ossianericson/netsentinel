"""Tests for modules/speed_tester_backends.py — see also test_sprint20_splits.py."""


def test_import():
    import modules.speed_tester_backends as m
    assert hasattr(m, "SpeedServer")
    assert hasattr(m, "SpeedTestResult")
    assert hasattr(m, "_find_ookla_cli")
    assert hasattr(m, "_run_ookla_cli")
    assert hasattr(m, "_run_speedtest_cli")
    assert hasattr(m, "_run_python_test")
    assert hasattr(m, "_patch_ssl_for_312")
    # Server discovery moved to speed_tester_servers (S20-7b split)
    import modules.speed_tester_servers as srv
    assert hasattr(srv, "_fetch_servers_python")


def test_speed_server_fields():
    from modules.speed_tester_backends import SpeedServer
    s = SpeedServer(id="42", name="TestNet", city="Berlin",
                    country="DE", host="speedtest.example.com:8080", latency_ms=8.0)
    assert s.id == "42"
    assert s.latency_ms == 8.0


def test_speed_test_result_timestamp():
    from modules.speed_tester_backends import SpeedTestResult
    r = SpeedTestResult(
        download_mbps=50.0, upload_mbps=25.0, ping_ms=10.0,
        server_name="Test", server_city="Paris", server_country="FR",
    )
    assert r.timestamp != ""
    assert r.modem_signal is None


def test_find_ookla_cli_type():
    from modules.speed_tester_backends import _find_ookla_cli
    result = _find_ookla_cli()
    from pathlib import Path
    assert result is None or isinstance(result, Path)


def test_http_ua_string():
    from modules.speed_tester_backends import _HTTP_UA
    assert "speedtest" in _HTTP_UA.lower()
