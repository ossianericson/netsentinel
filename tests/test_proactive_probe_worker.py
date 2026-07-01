"""Tests for workers/proactive_probe_worker.py (RULE-T2)."""
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
    from workers.proactive_probe_worker import ProactiveProbeWorker  # noqa: F401


def test_instantiation():
    from workers.proactive_probe_worker import ProactiveProbeWorker
    w = ProactiveProbeWorker(probe=lambda: "ok")
    assert not w.isRunning()
    _cleanup(w)


def test_signals_exist():
    from workers.proactive_probe_worker import ProactiveProbeWorker
    w = ProactiveProbeWorker(probe=lambda: "ok")
    assert hasattr(w, "probe_done")
    assert hasattr(w, "error")
    _cleanup(w)


def test_start_stop_lifecycle():
    """Worker must stop within 3 s after stop() is called."""
    from workers.proactive_probe_worker import ProactiveProbeWorker
    w = ProactiveProbeWorker(probe=lambda: "ok", interval_s=60)
    w.start()
    time.sleep(0.3)
    w.stop()
    finished = w.wait(3000)
    assert finished, "ProactiveProbeWorker did not stop within 3 s"
    assert not w.isRunning()
    _cleanup(w)


def test_probe_done_emitted_with_probe_result():
    from workers.proactive_probe_worker import ProactiveProbeWorker
    results = []
    w = ProactiveProbeWorker(probe=lambda: {"value": 42}, interval_s=60)
    w.probe_done.connect(results.append)
    w.start()
    deadline = time.time() + 3
    app = QApplication.instance()
    while not results and time.time() < deadline:
        if app:
            app.processEvents()
        time.sleep(0.05)
    w.stop()
    w.wait(3000)
    assert results == [{"value": 42}]
    _cleanup(w)


def test_error_emitted_when_probe_raises():
    from workers.proactive_probe_worker import ProactiveProbeWorker

    def _boom():
        raise RuntimeError("probe failed")

    errors = []
    w = ProactiveProbeWorker(probe=_boom, interval_s=60)
    w.error.connect(errors.append)
    w.start()
    deadline = time.time() + 3
    app = QApplication.instance()
    while not errors and time.time() < deadline:
        if app:
            app.processEvents()
        time.sleep(0.05)
    w.stop()
    w.wait(3000)
    assert errors == ["probe failed"]
    _cleanup(w)


def test_instantiated_in_app_py_for_scheduled_speed_test():
    """Sprint 3 wires this worker in for scheduled speed tests (grep-verified)."""
    from pathlib import Path
    app_src = Path(__file__).resolve().parent.parent / "app.py"
    text = app_src.read_text(encoding="utf-8")
    assert "ProactiveProbeWorker(" in text
    assert "run_scheduled_speed_test" in text
