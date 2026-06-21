"""Tests for workers/hw_detect_worker.py (RULE-T2)."""
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
    from workers.hw_detect_worker import HwDetectWorker  # noqa: F401


def test_instantiation():
    from workers.hw_detect_worker import HwDetectWorker
    w = HwDetectWorker(ip="192.168.1.1")
    assert not w.isRunning()
    _cleanup(w)


def test_instantiation_with_mac():
    from workers.hw_detect_worker import HwDetectWorker
    w = HwDetectWorker(ip="192.168.1.1", gateway_mac="aa:bb:cc:dd:ee:ff")
    assert w._ip == "192.168.1.1"
    assert w._gateway_mac == "aa:bb:cc:dd:ee:ff"
    _cleanup(w)


def test_signal_exists():
    from workers.hw_detect_worker import HwDetectWorker
    w = HwDetectWorker(ip="192.168.1.1")
    assert hasattr(w, "detected")
    _cleanup(w)


def test_start_stop_lifecycle():
    """HwDetectWorker is one-shot; probes HTTP+HTTPS (3s each) so allow 15 s."""
    from workers.hw_detect_worker import HwDetectWorker
    results = []
    w = HwDetectWorker(ip="192.168.1.1")
    w.detected.connect(results.append)
    w.start()
    finished = w.wait(15000)
    assert finished, "HwDetectWorker did not finish within 15 s"
    assert not w.isRunning()
    _cleanup(w)
    # Errors are swallowed internally; detected([]) is always emitted.
