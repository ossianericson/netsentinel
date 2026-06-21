"""Tests for workers/lldp_worker.py (RULE-T2)."""
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


def test_import():
    from workers.lldp_worker import LldpWorker  # noqa: F401


def test_instantiation():
    from workers.lldp_worker import LldpWorker
    w = LldpWorker(iface="eth0")
    assert not w.isRunning()
    _cleanup(w)


def test_signals_exist():
    from workers.lldp_worker import LldpWorker
    w = LldpWorker(iface="eth0")
    assert hasattr(w, "result_ready")
    assert hasattr(w, "error")
    assert hasattr(w, "progress")
    _cleanup(w)


def test_start_stop_lifecycle():
    """LldpWorker exits immediately without admin; must complete within 5 s."""
    from workers.lldp_worker import LldpWorker
    results = []
    errors = []
    w = LldpWorker(iface="eth0", passive=True)
    w.result_ready.connect(results.append)
    w.error.connect(errors.append)
    w.start()
    # Worker exits quickly if not admin (emits result_ready([]) and returns)
    finished = w.wait(5000)
    assert finished, "LldpWorker did not finish within 5 s"
    assert not w.isRunning()
    _cleanup(w)
    # Without admin rights the worker emits result_ready([]) and exits cleanly.
