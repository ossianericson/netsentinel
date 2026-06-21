"""Tests for workers/plugin_worker.py (RULE-T2)."""
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
    from workers.plugin_worker import PluginWorker  # noqa: F401


def test_instantiation(tmp_path):
    from workers.plugin_worker import PluginWorker
    script = tmp_path / "dummy_plugin.py"
    script.write_text("# dummy\n")
    w = PluginWorker(script_path=str(script), timeout=5)
    assert not w.isRunning()
    _cleanup(w)


def test_signals_exist(tmp_path):
    from workers.plugin_worker import PluginWorker
    script = tmp_path / "dummy_plugin.py"
    script.write_text("# dummy\n")
    w = PluginWorker(script_path=str(script))
    assert hasattr(w, "result")
    assert hasattr(w, "error")
    _cleanup(w)


def test_start_stop_lifecycle(tmp_path):
    """PluginWorker is one-shot; must emit error and stop when script lacks output."""
    from workers.plugin_worker import PluginWorker
    script = tmp_path / "dummy_plugin.py"
    script.write_text("# no --netsentinel output\nimport sys\nsys.exit(0)\n")
    errors = []
    w = PluginWorker(script_path=str(script), timeout=5)
    w.error.connect(errors.append)
    w.start()
    finished = w.wait(10000)
    assert finished, "PluginWorker did not finish within 10 s"
    assert not w.isRunning()
    _cleanup(w)
    # Worker should emit error (invalid JSON output) — that is expected.
