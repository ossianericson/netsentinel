"""Tests for workers/iface_bw_worker.py (RULE-T2)."""
import time
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
    from workers.iface_bw_worker import IfaceBwPoller  # noqa: F401


def test_instantiation():
    from workers.iface_bw_worker import IfaceBwPoller
    w = IfaceBwPoller(interval_s=60.0)
    assert not w.isRunning()
    _cleanup(w)


def test_signals_exist():
    from workers.iface_bw_worker import IfaceBwPoller
    w = IfaceBwPoller()
    assert hasattr(w, "stats_ready")
    assert hasattr(w, "error")
    _cleanup(w)


def test_start_stop_lifecycle():
    """Worker must stop within 5 s after stop() is called.

    Use interval_s=1.0 so _running is checked each second (not every 60 s).
    """
    from workers.iface_bw_worker import IfaceBwPoller
    errors = []
    w = IfaceBwPoller(interval_s=1.0)
    w.error.connect(errors.append)
    w.start()
    time.sleep(0.3)
    w.stop()
    finished = w.wait(5000)
    assert finished, "IfaceBwPoller did not stop within 5 s"
    assert not w.isRunning()
    _cleanup(w)
    # Errors are allowed (psutil unavailable); thread must still stop.
