"""Tests for workers/app_traffic_worker.py (RULE-T2)."""
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
    from workers.app_traffic_worker import AppTrafficWorker  # noqa: F401


def test_instantiation():
    from workers.app_traffic_worker import AppTrafficWorker
    w = AppTrafficWorker(interval_s=60.0)
    assert not w.isRunning()
    _cleanup(w)


def test_start_stop_lifecycle():
    """Worker uses threading.Event; stop() must cause exit within 3 s."""
    from workers.app_traffic_worker import AppTrafficWorker
    errors = []
    w = AppTrafficWorker(interval_s=60.0)
    w.error.connect(errors.append)
    w.start()
    time.sleep(0.3)
    w.stop()
    finished = w.wait(3000)
    assert finished, "AppTrafficWorker did not stop within 3 s"
    assert not w.isRunning()
    _cleanup(w)
    # Errors are allowed (Scapy/Npcap unavailable in CI); thread must still stop.


def test_set_label_map():
    from workers.app_traffic_worker import AppTrafficWorker
    w = AppTrafficWorker()
    w.set_label_map({"aa:bb:cc:dd:ee:ff": "laptop"})
    assert w._label_map == {"aa:bb:cc:dd:ee:ff": "laptop"}
    _cleanup(w)


def test_set_label_map_reaches_the_running_monitor():
    """Regression: AppTrafficMonitor keeps its own reference to the map it was
    constructed with, so rebinding the worker's dict alone left a monitor that
    started before the first scan stamping bare MACs on every snapshot."""
    from workers.app_traffic_worker import AppTrafficWorker

    class _FakeMonitor:
        def __init__(self):
            self.label_map = {}

    w = AppTrafficWorker()
    monitor = _FakeMonitor()
    w._monitor = monitor            # simulate run() having built the monitor

    w.set_label_map({"aa:bb:cc:dd:ee:ff": "Living Room TV"})

    assert monitor.label_map == {"aa:bb:cc:dd:ee:ff": "Living Room TV"}
    _cleanup(w)


def test_set_label_map_is_safe_before_the_monitor_exists():
    from workers.app_traffic_worker import AppTrafficWorker
    w = AppTrafficWorker()
    assert w._monitor is None
    w.set_label_map({"aa:bb:cc:dd:ee:ff": "laptop"})   # must not raise
    _cleanup(w)
