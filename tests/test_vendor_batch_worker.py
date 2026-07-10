"""Tests for ui/scan_wiring.py _VendorBatchWorker cooperative stop (finding #17).

Bug summary: _start_vendor_lookups() called existing.terminate() on a re-scan,
which can hard-kill the QThread while it is blocked inside lookup_vendor()'s
blocking HTTP call — an unsafe forced termination of a thread mid-syscall.
The fix replaces terminate() with a cooperative stop flag the run() loop
checks between MACs, so the in-flight (bounded, 5s-timeout) lookup finishes
naturally instead of being killed mid-syscall.
"""
import types

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

pytestmark = pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")


def _cleanup(w):
    app = QApplication.instance()
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # non-fatal — already deleted
    if app:
        for _ in range(3):
            app.processEvents()


def test_vendor_batch_worker_has_cooperative_stop():
    from ui.scan_wiring import _VendorBatchWorker
    w = _VendorBatchWorker(["aa:bb:cc:11:22:33"])
    assert hasattr(w, "stop")
    assert not w.isRunning()
    _cleanup(w)


def test_vendor_batch_worker_stop_lifecycle(monkeypatch):
    """start() -> stop() -> wait() must leave the thread not running."""
    from ui.scan_wiring import _VendorBatchWorker
    import modules.mac_lookup as mac_lookup

    monkeypatch.setattr(mac_lookup, "lookup_vendor", lambda mac: "Test Vendor")

    w = _VendorBatchWorker(["aa:bb:cc:11:22:33", "aa:bb:cc:11:22:34"])
    w.start()
    w.stop()
    finished = w.wait(5000)
    assert finished, "_VendorBatchWorker did not stop within 5 s"
    assert not w.isRunning()
    _cleanup(w)


def test_vendor_batch_worker_stop_skips_remaining_macs(monkeypatch):
    """Once stop() is set, the run loop must not start lookups for further MACs."""
    from ui.scan_wiring import _VendorBatchWorker
    import modules.mac_lookup as mac_lookup

    processed = []

    def _lookup(mac):
        processed.append(mac)
        return "Test Vendor"

    monkeypatch.setattr(mac_lookup, "lookup_vendor", _lookup)

    w = _VendorBatchWorker(["aa:bb:cc:11:22:33"])
    w.stop()  # stop before starting — simulates the flag already being set
    w.start()
    w.wait(5000)

    assert processed == []
    _cleanup(w)


def test_start_vendor_lookups_stops_existing_worker_cooperatively(monkeypatch):
    """_start_vendor_lookups must call stop(), not terminate(), on a running worker."""
    from ui.scan_wiring import ScanResultMixin
    import ui.scan_wiring as sw

    class _FakeExistingWorker:
        def __init__(self):
            self.stopped = False
            self.terminated = False
            self.disconnect_called = False
            self.vendor_resolved = self

        def isRunning(self):
            return True

        def stop(self):
            self.stopped = True

        def terminate(self):
            self.terminated = True

        def wait(self, ms=None):
            pass

        def disconnect(self):
            self.disconnect_called = True

    class _FakeNewWorker:
        def __init__(self, macs, parent=None):
            self.macs = macs
            self.parent = parent
            self.vendor_resolved = types.SimpleNamespace(connect=lambda *_a: None)
            self.started = False

        def start(self):
            self.started = True

    monkeypatch.setattr(sw, "_VendorBatchWorker", _FakeNewWorker)

    existing = _FakeExistingWorker()
    obj = types.SimpleNamespace(
        _vendor_batch_worker=existing,
        _on_vendor_resolved=lambda mac, vendor: None,
    )

    devices = [{"mac": "00:1a:2b:11:22:44", "vendor": "Unknown"}]  # non-randomized OUI
    ScanResultMixin._start_vendor_lookups(obj, devices)

    assert existing.stopped is True, "existing worker must be stopped cooperatively"
    assert existing.terminated is False, "existing worker must not be force-terminated"
    assert existing.disconnect_called is True
    assert obj._vendor_batch_worker.started is True
