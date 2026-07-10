"""Tests for modules/speed_tester_backends.py — see also test_sprint20_splits.py."""

import json
from pathlib import Path

import pytest


class _FakeStdout:
    def __init__(self, lines):
        self._lines = list(lines)
        self.closed = False

    def __iter__(self):
        return iter(self._lines)

    def close(self):
        self.closed = True


class _FakeStderr:
    def __init__(self, text=""):
        self._text = text
        self.closed = False

    def read(self):
        return self._text

    def close(self):
        self.closed = True


class _FakeProc:
    """Mimics subprocess.Popen just enough to drive _run_ookla_cli's cleanup paths."""

    def __init__(self, lines):
        self.stdout = _FakeStdout(lines)
        self.stderr = _FakeStderr("")
        self.killed = False
        self.wait_calls = []

    def poll(self):
        return 0 if self.killed else None

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)


def test_run_ookla_cli_cleans_up_process_on_error_event(monkeypatch):
    """A JSON 'error' event must still kill/reap the process and close its pipes."""
    from modules import speed_tester_backends as m

    import platform
    platform.system()  # warm platform's internal subprocess-based cache before patching Popen

    error_line = json.dumps({"type": "error", "message": "boom"}) + "\n"
    fake = _FakeProc([error_line])
    monkeypatch.setattr(m.subprocess, "Popen", lambda *a, **kw: fake)

    with pytest.raises(RuntimeError, match="Ookla CLI error"):
        m._run_ookla_cli(Path("ookla"), server_id=None, on_progress=None)

    assert fake.killed is True
    assert fake.wait_calls, "proc.wait() must be called after kill() to reap the child"
    assert fake.stdout.closed is True
    assert fake.stderr.closed is True


def test_import():
    from modules import speed_tester_backends as m
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
