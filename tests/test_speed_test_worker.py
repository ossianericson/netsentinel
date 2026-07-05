"""Tests for workers/speed_test_worker.py (RULE-T2)."""
from unittest.mock import MagicMock, patch

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


def _cleanup(w):
    app = QApplication.instance()
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # non-fatal — already deleted
    if app:
        for _ in range(3):
            app.processEvents()


# ── Import guard ──────────────────────────────────────────────────────────────

def test_import_fetch_servers():
    from workers.speed_test_worker import FetchServersWorker  # noqa: F401


def test_import_speed_test():
    from workers.speed_test_worker import SpeedTestWorker  # noqa: F401


# ── FetchServersWorker ────────────────────────────────────────────────────────

def test_fetch_servers_instantiation():
    from workers.speed_test_worker import FetchServersWorker
    w = FetchServersWorker(limit=5)
    assert not w.isRunning()
    _cleanup(w)


def test_fetch_servers_signals_exist():
    from workers.speed_test_worker import FetchServersWorker
    w = FetchServersWorker()
    assert hasattr(w, "servers_ready")
    assert hasattr(w, "error")
    assert hasattr(w, "status_changed")
    _cleanup(w)


@pytest.mark.live
def test_fetch_servers_lifecycle():
    """One-shot worker hitting the real network; retry+backoff can extend this
    past 10 s under transient failures, so it is excluded from default CI runs
    (see tests.instructions.md — network-dependent tests use the `live` marker).
    Mocked-backend variants below cover the lifecycle without real network I/O."""
    from workers.speed_test_worker import FetchServersWorker
    errors = []
    w = FetchServersWorker(limit=3)
    w.error.connect(errors.append)
    w.start()
    finished = w.wait(30000)
    assert finished, "FetchServersWorker did not finish within 30 s"
    assert not w.isRunning()
    _cleanup(w)


# ── SpeedTestWorker ───────────────────────────────────────────────────────────

def test_speed_test_instantiation():
    from workers.speed_test_worker import SpeedTestWorker
    w = SpeedTestWorker()
    assert not w.isRunning()
    _cleanup(w)


def test_speed_test_signals_exist():
    from workers.speed_test_worker import SpeedTestWorker
    w = SpeedTestWorker()
    assert hasattr(w, "result_ready")
    assert hasattr(w, "error")
    _cleanup(w)


@pytest.mark.slow
def test_speed_test_lifecycle():
    """One-shot worker; runs a full speed test — can take up to 2 min."""
    from workers.speed_test_worker import SpeedTestWorker
    errors = []
    w = SpeedTestWorker()
    w.error.connect(errors.append)
    w.start()
    finished = w.wait(120000)
    assert finished, "SpeedTestWorker did not finish within 120 s"
    assert not w.isRunning()
    _cleanup(w)


# ── Mocked-backend lifecycle tests ────────────────────────────────────────────

def _drain(w):
    """Stop worker and drain queued signals into the main thread."""
    w.quit()
    w.wait(2000)
    app = QApplication.instance()
    if app:
        for _ in range(10):
            app.processEvents()


def test_fetch_servers_worker_mocked_success():
    """FetchServersWorker emits servers_ready with mocked backend."""
    from workers.speed_test_worker import FetchServersWorker

    results: list = []
    with patch("modules.speed_tester.fetch_servers", return_value=[]):
        w = FetchServersWorker(limit=3)
        w.servers_ready.connect(results.append)
        w.start()
        w.wait(3000)
        _drain(w)
        assert not w.isRunning()
        assert results == [[]]
        _cleanup(w)


def test_fetch_servers_worker_mocked_error():
    """FetchServersWorker emits error when backend raises."""
    from workers.speed_test_worker import FetchServersWorker

    errors: list = []
    with patch("modules.speed_tester.fetch_servers", side_effect=RuntimeError("no route")):
        w = FetchServersWorker(limit=3)
        w.error.connect(errors.append)
        w.start()
        w.wait(3000)
        _drain(w)
        assert not w.isRunning()
        assert len(errors) == 1
        assert "no route" in errors[0]
        _cleanup(w)


def test_speed_test_worker_mocked_success():
    """SpeedTestWorker emits result_ready with mocked backend."""
    from workers.speed_test_worker import SpeedTestWorker

    mock_result = MagicMock()
    mock_result.download_mbps = 100.0
    mock_result.upload_mbps = 50.0
    mock_result.ping_ms = 10.0
    mock_result.modem_signal = None

    results: list = []
    with patch("modules.speed_tester.run_test", return_value=mock_result):
        w = SpeedTestWorker(server_id=None, zte_host=None, zte_password=None, modem_snapshot=None)
        w.result_ready.connect(results.append)
        w.start()
        w.wait(3000)
        _drain(w)
        assert not w.isRunning()
        assert len(results) == 1
        _cleanup(w)


def test_speed_test_worker_mocked_error():
    """SpeedTestWorker emits error when backend raises."""
    from workers.speed_test_worker import SpeedTestWorker

    errors: list = []
    with patch("modules.speed_tester.run_test", side_effect=RuntimeError("mock failure")):
        w = SpeedTestWorker()
        w.error.connect(errors.append)
        w.start()
        w.wait(3000)
        _drain(w)
        assert not w.isRunning()
        assert len(errors) == 1
        assert "mock failure" in errors[0]
        _cleanup(w)
