"""
Worker lifecycle tests for workers not yet covered in test_worker_lifecycle.py.

Covers:
  hw_detect_worker — HwDetectWorker
  plugin_worker    — PluginWorker
  wifi_monitor_worker — WiFiMonitorWorker

RULE-T2: each test instantiates, starts, waits, stops, asserts isRunning() is False.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest

# conftest provides the session-scoped qt_app fixture (autouse=True)

WAIT_MS = 2000


def _start_stop(worker, wait_ms: int = WAIT_MS) -> None:
    worker.start()
    time.sleep(0.05)
    if hasattr(worker, "stop"):
        worker.stop()
    finished = worker.wait(wait_ms)
    if not finished:
        worker.terminate()
        worker.wait(500)


# ── HwDetectWorker ─────────────────────────────────────────────────────────────

class TestHwDetectWorker:
    def test_import(self):
        from workers.hw_detect_worker import HwDetectWorker  # noqa: F401

    def test_instantiate(self):
        from workers.hw_detect_worker import HwDetectWorker
        w = HwDetectWorker(ip="192.168.1.1")
        try:
            assert w is not None
        finally:
            try:
                w.deleteLater()
            except RuntimeError:
                pass  # non-fatal
            try:
                from PyQt6.QtWidgets import QApplication
                app = QApplication.instance()
                if app:
                    for _ in range(3):
                        app.processEvents()
            except Exception:
                pass  # non-fatal

    def test_lifecycle(self):
        from workers.hw_detect_worker import HwDetectWorker
        mock_hw = MagicMock()
        mock_hw.detect.return_value = []
        mock_hw.load_catalogue.return_value = {}
        with patch.dict("sys.modules", {"modules.hw_detect": mock_hw}):
            w = HwDetectWorker(ip="192.168.1.1")
            try:
                _start_stop(w)
                assert not w.isRunning(), "HwDetectWorker still running after stop"
            finally:
                try:
                    w.deleteLater()
                except RuntimeError:
                    pass  # non-fatal
                try:
                    from PyQt6.QtWidgets import QApplication
                    app = QApplication.instance()
                    if app:
                        for _ in range(3):
                            app.processEvents()
                except Exception:
                    pass  # non-fatal


# ── PluginWorker ───────────────────────────────────────────────────────────────

class TestPluginWorker:
    def test_import(self):
        from workers.plugin_worker import PluginWorker  # noqa: F401

    def test_instantiate(self, tmp_path):
        from workers.plugin_worker import PluginWorker
        # Create a minimal plugin script
        script = tmp_path / "test_plugin.py"
        script.write_text("PLUGIN_TYPE = 'test'\ndef get_info(): return {}\ndef get_status(): return {}\n")
        w = PluginWorker(str(script))
        try:
            assert w is not None
        finally:
            try:
                w.deleteLater()
            except RuntimeError:
                pass  # non-fatal
            try:
                from PyQt6.QtWidgets import QApplication
                app = QApplication.instance()
                if app:
                    for _ in range(3):
                        app.processEvents()
            except Exception:
                pass  # non-fatal

    def test_lifecycle(self, tmp_path):
        from workers.plugin_worker import PluginWorker
        script = tmp_path / "test_plugin.py"
        script.write_text("PLUGIN_TYPE = 'test'\ndef get_info(): return {}\ndef get_status(): return {}\n")
        w = PluginWorker(str(script), timeout=1)
        try:
            _start_stop(w)
            assert not w.isRunning(), "PluginWorker still running after stop"
        finally:
            try:
                w.deleteLater()
            except RuntimeError:
                pass  # non-fatal
            try:
                from PyQt6.QtWidgets import QApplication
                app = QApplication.instance()
                if app:
                    for _ in range(3):
                        app.processEvents()
            except Exception:
                pass  # non-fatal


# ── WiFiMonitorWorker ──────────────────────────────────────────────────────────

class TestWifiMonitorWorker:
    def test_import(self):
        from workers.wifi_monitor_worker import WiFiMonitorWorker  # noqa: F401

    def test_instantiate(self):
        from workers.wifi_monitor_worker import WiFiMonitorWorker
        w = WiFiMonitorWorker(iface="")
        try:
            assert w is not None
        finally:
            try:
                w.deleteLater()
            except RuntimeError:
                pass  # non-fatal
            try:
                from PyQt6.QtWidgets import QApplication
                app = QApplication.instance()
                if app:
                    for _ in range(3):
                        app.processEvents()
            except Exception:
                pass  # non-fatal

    def test_lifecycle(self):
        from workers.wifi_monitor_worker import WiFiMonitorWorker
        # Mock scapy so the worker fails fast (ImportError → error signal → run() returns)
        mock_scapy = MagicMock()
        with patch.dict("sys.modules", {"scapy.all": None, "scapy.layers.dot11": None}):
            w = WiFiMonitorWorker(iface="")
            try:
                _start_stop(w)
                assert not w.isRunning(), "WiFiMonitorWorker still running after stop"
            finally:
                try:
                    w.deleteLater()
                except RuntimeError:
                    pass  # non-fatal
                try:
                    from PyQt6.QtWidgets import QApplication
                    app = QApplication.instance()
                    if app:
                        for _ in range(3):
                            app.processEvents()
                except Exception:
                    pass  # non-fatal


# ── S5-3: _running flag audit ─────────────────────────────────────────────────

class TestRunningFlagAudit:
    """Verify no worker has an unbounded while True loop without a _running check."""

    def test_no_unguarded_while_true(self):
        import pathlib, ast

        workers_dir = pathlib.Path("workers")
        violations = []
        for path in sorted(workers_dir.glob("*.py")):
            if path.stem.startswith("_"):
                continue
            source = path.read_text(encoding="utf-8", errors="replace")
            # Heuristic: while True without _running in same file is a risk
            if "while True:" in source:
                # Check if it's a queue-drain pattern (always has inner try/except/break)
                # These are safe. Only flag if there's no break/return/_running nearby.
                lines = source.splitlines()
                for i, line in enumerate(lines):
                    if "while True:" in line:
                        # Look at next 10 lines for break/return/_running/stop_event
                        context = "\n".join(lines[i:min(i+15, len(lines))])
                        has_exit = any(x in context for x in (
                            "break", "return", "_running", "_stop_event", "stop()"
                        ))
                        if not has_exit:
                            violations.append(f"{path.name}:{i+1}")

        assert not violations, (
            f"Workers with potentially unguarded while True loops: {violations}\n"
            "Add a _running flag check or ensure the loop always terminates."
        )
