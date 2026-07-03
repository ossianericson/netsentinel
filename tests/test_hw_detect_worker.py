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
    assert hasattr(w, "error")
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


def test_emits_error_not_detected_on_failure(monkeypatch):
    """G10 regression test: before the fix, any exception during detection
    (e.g. the catalogue failing to load) was swallowed and reported as
    detected([]) — identical to 'no hardware matched', with no way for the
    Hardware page to distinguish a real probe failure from an empty result."""
    from workers.hw_detect_worker import HwDetectWorker

    def _raise(*_a, **_kw):
        raise RuntimeError("catalogue.json is corrupt")

    monkeypatch.setattr("modules.hw_detect.load_catalogue", _raise)

    detected_calls = []
    error_calls = []
    w = HwDetectWorker(ip="192.168.1.1")
    w.detected.connect(detected_calls.append)
    w.error.connect(error_calls.append)
    w.start()
    finished = w.wait(15000)
    assert finished, "HwDetectWorker did not finish within 15 s"
    assert not w.isRunning()
    # Cross-thread signals to plain Python callables are queued — pump the
    # event loop so the connected slots actually run before asserting.
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    assert error_calls == ["catalogue.json is corrupt"]
    assert detected_calls == []
    _cleanup(w)
