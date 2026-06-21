"""Tests for workers/speed_test_worker.py (RULE-T2)."""
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


def test_fetch_servers_lifecycle():
    """One-shot worker; must finish within 10 s (errors expected in CI)."""
    from workers.speed_test_worker import FetchServersWorker
    errors = []
    w = FetchServersWorker(limit=3)
    w.error.connect(errors.append)
    w.start()
    finished = w.wait(10000)
    assert finished, "FetchServersWorker did not finish within 10 s"
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
