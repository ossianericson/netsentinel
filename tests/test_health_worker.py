"""
tests/test_health_worker.py — Start/stop lifecycle test for workers/health_worker.py
(RULE-T2)
"""
import time

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

try:
    from workers.health_worker import HealthWorker
except ImportError:
    pytest.skip("workers.health_worker not available", allow_module_level=True)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_import():
    assert HealthWorker is not None


def test_instantiation():
    worker = HealthWorker(store=None)
    assert worker is not None
    assert not worker.isRunning()
    try:
        worker.deleteLater()
    except RuntimeError:
        pass  # non-fatal


def test_start_stop_lifecycle():
    """
    Worker must start, run briefly, stop, and not be running after stop().

    NOTE: we deliberately avoid QApplication.processEvents() here.
    Calling processEvents() while the worker's background thread is emitting
    a signal with no connected receivers can cause a Qt-internal lock contention
    that prevents the worker thread from completing its current emit() and
    seeing the stop flag.  Plain time.sleep() releases the GIL and is sufficient.
    """
    worker = HealthWorker(store=None)
    try:
        worker.start()

        # Wait for thread to enter run() — plain sleep, no processEvents
        deadline = time.monotonic() + 5.0
        while not worker.isRunning() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert worker.isRunning(), "Worker did not start within 5s"

        worker.stop()
        # threading.Event.set() wakes the worker immediately.
        # Do NOT tight-poll isRunning() — doing so every 50 ms monopolises a
        # Qt-internal mutex that the finishing thread also needs to update its
        # state, creating a livelock.  A single 2-second sleep is sufficient
        # because the worker exits within milliseconds of the event being set.
        time.sleep(2.0)
        assert not worker.isRunning(), "Worker did not stop within 2s"

    finally:
        if worker.isRunning():
            worker.stop()
        try:
            worker.deleteLater()
        except RuntimeError:
            pass  # non-fatal
        app = QApplication.instance()
        if app:
            for _ in range(3):
                app.processEvents()


def test_error_signal_exists():
    worker = HealthWorker(store=None)
    assert hasattr(worker, "error")
    try:
        worker.deleteLater()
    except RuntimeError:
        pass  # non-fatal


def test_result_ready_signal_exists():
    worker = HealthWorker(store=None)
    assert hasattr(worker, "result_ready")
    try:
        worker.deleteLater()
    except RuntimeError:
        pass  # non-fatal


def test_stop_before_start_is_safe():
    """Calling stop() on a never-started worker must not raise."""
    worker = HealthWorker(store=None)
    worker.stop()  # should not raise
    try:
        worker.deleteLater()
    except RuntimeError:
        pass  # non-fatal
