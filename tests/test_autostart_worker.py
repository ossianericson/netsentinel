"""Tests for workers/autostart_worker.py (RULE-T2)."""
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
    from workers.autostart_worker import AutostartWorker  # noqa: F401


def test_instantiation():
    from workers.autostart_worker import AutostartWorker
    w = AutostartWorker()
    assert not w.isRunning()
    _cleanup(w)


def test_signal_exists():
    from workers.autostart_worker import AutostartWorker
    w = AutostartWorker()
    assert hasattr(w, "result_ready")
    assert hasattr(w, "error")
    _cleanup(w)


def test_start_stop_lifecycle_query(monkeypatch):
    """RULE-T2: start() -> wait() -> isRunning() is False."""
    from modules import autostart
    from workers.autostart_worker import AutostartWorker

    monkeypatch.setattr(autostart, "autostart_backend", lambda: "run_key")
    monkeypatch.setattr(autostart, "get_run_on_startup", lambda: False)

    results = []
    w = AutostartWorker(enable=None)
    w.result_ready.connect(results.append)
    w.start()
    finished = w.wait(5000)
    assert finished, "AutostartWorker did not finish within 5 s"
    assert not w.isRunning()
    QApplication.instance().processEvents()  # deliver the queued cross-thread signal
    assert len(results) == 1
    assert results[0].backend == "run_key"
    _cleanup(w)


def test_start_stop_lifecycle_set(monkeypatch):
    from modules import autostart
    from workers.autostart_worker import AutostartWorker

    monkeypatch.setattr(autostart, "autostart_backend", lambda: "run_key")
    calls = []
    monkeypatch.setattr(autostart, "set_run_on_startup", lambda enabled: calls.append(enabled))
    monkeypatch.setattr(autostart, "get_run_on_startup", lambda: True)

    results = []
    w = AutostartWorker(enable=True)
    w.result_ready.connect(results.append)
    w.start()
    finished = w.wait(5000)
    assert finished
    assert not w.isRunning()
    QApplication.instance().processEvents()  # deliver the queued cross-thread signal
    assert calls == [True]
    assert results[0].enabled is True
    _cleanup(w)


def test_ro_initialize_only_called_for_startup_task_backend(monkeypatch):
    """run_key backend must never touch modules.startup_task (mirrors
    test_autostart.py's equivalent guard, at the worker layer)."""
    from modules import autostart, startup_task
    from workers.autostart_worker import AutostartWorker

    monkeypatch.setattr(autostart, "autostart_backend", lambda: "run_key")
    monkeypatch.setattr(autostart, "get_run_on_startup", lambda: False)

    def _boom(*a, **kw):
        raise AssertionError("run_key backend must never call modules.startup_task")

    monkeypatch.setattr(startup_task, "ro_initialize", _boom)
    monkeypatch.setattr(startup_task, "ro_uninitialize", _boom)

    errors = []
    w = AutostartWorker(enable=None)
    w.error.connect(errors.append)
    w.start()
    w.wait(5000)
    assert errors == []
    _cleanup(w)
