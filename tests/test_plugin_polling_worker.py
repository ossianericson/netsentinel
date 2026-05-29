"""
Tests for workers/plugin_polling_worker.py — RULE-T2 compliance.

Covers: import, instantiation, lifecycle (start/stop), in-process execution,
error emission for missing file, and error emission for broken plugin code.
"""
from __future__ import annotations

import sys
import textwrap
import time
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

# ── QApplication fixture ─────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


# ── helpers ──────────────────────────────────────────────────────────────────


def _wait(condition, timeout=5.0, step=0.05) -> bool:
    """Poll condition, pumping Qt events on each iteration."""
    from PyQt6.QtWidgets import QApplication
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if condition():
            return True
        time.sleep(step)
    return False


# ── import ────────────────────────────────────────────────────────────────────


def test_import():
    from workers.plugin_polling_worker import PluginPollingWorker  # noqa: F401


# ── lifecycle (start / stop) ─────────────────────────────────────────────────


def test_start_stop(qapp, tmp_path):
    """Worker must start, run, and stop cleanly without hanging."""
    # Write a minimal valid plugin to a temp file
    plugin = tmp_path / "dummy_plugin.py"
    plugin.write_text(textwrap.dedent("""
        HARDWARE_NAME = "Dummy"
        HARDWARE_TYPE = "other"
        HARDWARE_IP   = "127.0.0.1"

        def get_info():
            return {"name": HARDWARE_NAME, "type": HARDWARE_TYPE, "ip": HARDWARE_IP}

        def get_status():
            return {"wan_ip": None, "uptime_sec": None, "download_mbps": None,
                    "upload_mbps": None, "signal_dbm": None, "connected_clients": 0,
                    "extra": {}}

        def get_clients():
            return []
    """))

    from workers.plugin_polling_worker import PluginPollingWorker

    worker = PluginPollingWorker(path=str(plugin), hw_type="other")
    worker.start()
    assert _wait(lambda: worker.isRunning()), "worker did not start within 3 s"
    worker.stop()
    worker.wait(3000)
    assert not worker.isRunning(), "worker did not stop within 3 s"


# ── result emission ───────────────────────────────────────────────────────────


def test_result_emitted(qapp, tmp_path):
    """Worker emits result signal when plugin returns valid data."""
    plugin = tmp_path / "ok_plugin.py"
    plugin.write_text(textwrap.dedent("""
        HARDWARE_NAME = "OK"
        HARDWARE_TYPE = "other"
        HARDWARE_IP   = "127.0.0.1"

        def get_info():
            return {"name": "OK", "type": "other", "ip": "127.0.0.1"}

        def get_status():
            return {"wan_ip": "1.2.3.4", "uptime_sec": 100, "download_mbps": None,
                    "upload_mbps": None, "signal_dbm": None, "connected_clients": 2,
                    "extra": {}}

        def get_clients():
            return [{"ip": "10.0.0.2", "mac": "aa:bb:cc:dd:ee:ff", "hostname": "pc"}]
    """))

    from workers.plugin_polling_worker import PluginPollingWorker

    received: list[dict] = []
    worker = PluginPollingWorker(path=str(plugin), hw_type="other")
    worker.result.connect(received.append)
    worker.start()
    assert _wait(lambda: len(received) >= 1, timeout=5), "no result emitted within 5 s"
    worker.stop()
    worker.wait(3000)

    data = received[0]
    assert data["info"]["name"] == "OK"
    assert data["status"]["connected_clients"] == 2
    assert len(data["clients"]) == 1


# ── error emission — missing file ─────────────────────────────────────────────


def test_error_missing_file(qapp, tmp_path):
    """Worker emits error when the plugin file does not exist."""
    from workers.plugin_polling_worker import PluginPollingWorker

    errors: list[str] = []
    worker = PluginPollingWorker(path=str(tmp_path / "nonexistent.py"), hw_type="other")
    worker.error.connect(errors.append)
    worker.start()
    assert _wait(lambda: len(errors) >= 1, timeout=5), "no error emitted within 5 s"
    worker.stop()
    worker.wait(3000)
    assert "not found" in errors[0].lower() or "nonexistent" in errors[0].lower()


# ── error emission — broken plugin ────────────────────────────────────────────


def test_error_broken_plugin(qapp, tmp_path):
    """Worker emits error when get_status() raises an unhandled exception."""
    plugin = tmp_path / "broken_plugin.py"
    plugin.write_text(textwrap.dedent("""
        HARDWARE_NAME = "Broken"
        HARDWARE_TYPE = "other"
        HARDWARE_IP   = "127.0.0.1"

        def get_info():
            return {"name": "Broken", "type": "other", "ip": "127.0.0.1"}

        def get_status():
            raise RuntimeError("deliberate test failure")

        def get_clients():
            return []
    """))

    from workers.plugin_polling_worker import PluginPollingWorker

    errors: list[str] = []
    worker = PluginPollingWorker(path=str(plugin), hw_type="other")
    worker.error.connect(errors.append)
    worker.start()
    assert _wait(lambda: len(errors) >= 1, timeout=5), "no error emitted within 5 s"
    worker.stop()
    worker.wait(3000)
    assert "deliberate test failure" in errors[0]


# ── trigger_now ───────────────────────────────────────────────────────────────


def test_trigger_now_delivers_result_quickly(qapp, tmp_path):
    """trigger_now() wakes the worker immediately without waiting the full interval."""
    plugin = tmp_path / "fast_plugin.py"
    plugin.write_text(textwrap.dedent("""
        HARDWARE_NAME = "Fast"
        HARDWARE_TYPE = "other"
        HARDWARE_IP   = "127.0.0.1"

        def get_info():
            return {"name": "Fast", "type": "other", "ip": "127.0.0.1"}

        def get_status():
            return {"wan_ip": None, "uptime_sec": None, "download_mbps": None,
                    "upload_mbps": None, "signal_dbm": None, "connected_clients": 0,
                    "extra": {}}

        def get_clients():
            return []
    """))

    from workers.plugin_polling_worker import PluginPollingWorker

    received: list[dict] = []
    # Use a 3600-s interval so the worker would never self-trigger in the test
    worker = PluginPollingWorker(path=str(plugin), hw_type="other")
    worker._interval_s = 3600
    worker.result.connect(received.append)
    worker.start()
    assert _wait(lambda: len(received) >= 1, timeout=5), "initial poll did not fire"
    before = len(received)
    worker.trigger_now()
    assert _wait(lambda: len(received) > before, timeout=5), "trigger_now did not fire"
    worker.stop()
    worker.wait(3000)
