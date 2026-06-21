"""Tests for workers/scan_worker.py (RULE-T2)."""
from unittest.mock import patch

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


# ── Import guard ──────────────────────────────────────────────────────────────

def test_import():
    from workers.scan_worker import Module1Worker  # noqa: F401


def test_import_prescan():
    from workers.scan_worker import PreScanWorker  # noqa: F401


def test_import_network_info():
    from workers.scan_worker import NetworkInfoWorker  # noqa: F401


# ── Module1Worker ─────────────────────────────────────────────────────────────

def test_module1_instantiation(tmp_path):
    from workers.scan_worker import Module1Worker
    w = Module1Worker(offenders_path=tmp_path / "offenders.json")
    assert not w.isRunning()
    _cleanup(w)


def test_module1_lifecycle(tmp_path, monkeypatch):
    """Module1Worker is one-shot: starts, runs scan, emits result, exits.

    The underlying scan is mocked so the test completes quickly on all platforms
    (macOS CI hangs >30 s when resolve_batch blocks on mDNS/NetBIOS lookups
    against real ARP entries in the CI runner's network stack).
    """
    from workers.scan_worker import Module1Worker

    _empty = {
        "devices": [], "gateway_ip": None,
        "high_risk_count": 0, "total_count": 0,
        "plain_verdict": "No devices.", "proxy_arp_ips": set(),
    }
    monkeypatch.setattr("modules.rogue_device.scan", lambda *_a, **_kw: _empty)

    errors = []
    w = Module1Worker(offenders_path=tmp_path / "offenders.json")
    w.error.connect(errors.append)
    w.start()
    finished = w.wait(10000)
    assert finished, "Module1Worker did not finish within 10 s"
    assert not w.isRunning()
    _cleanup(w)


# ── PreScanWorker ─────────────────────────────────────────────────────────────

def test_prescan_instantiation():
    from workers.scan_worker import PreScanWorker
    w = PreScanWorker(flush_caches=False)
    assert not w.isRunning()
    _cleanup(w)


def test_prescan_lifecycle():
    """PreScanWorker is one-shot: ping sweep + done() then exits."""
    from workers.scan_worker import PreScanWorker
    w = PreScanWorker(flush_caches=False)
    w.start()
    finished = w.wait(10000)
    assert finished, "PreScanWorker did not finish within 10 s"
    assert not w.isRunning()
    _cleanup(w)


# ── NetworkInfoWorker ─────────────────────────────────────────────────────────

def test_network_info_lifecycle():
    """NetworkInfoWorker is one-shot: collects info then exits."""
    from workers.scan_worker import NetworkInfoWorker
    errors = []
    w = NetworkInfoWorker()
    w.error.connect(errors.append)
    w.start()
    finished = w.wait(5000)
    assert finished, "NetworkInfoWorker did not finish within 5 s"
    assert not w.isRunning()
    _cleanup(w)


# ── Regression: device_found must not crash on DeviceInfo objects ─────────────

def test_module1_device_found_emits_with_deviceinfo_objects(tmp_path, monkeypatch):
    """Regression: Module1Worker must emit result (not error) when scan() returns
    DeviceInfo dataclass objects in the devices list.

    The original bug: device_found.emit() used
        getattr(d, "ip", d.get("ip", ""))
    Python evaluates ALL arguments eagerly, so d.get("ip", "") ran on DeviceInfo
    objects (which have no .get()), raising AttributeError before result.emit(data)
    was reached.  This silently killed the scan — table went blank on every scan
    but showed cached data on restart.
    """
    from modules.rogue_device import DeviceInfo
    from workers.scan_worker import Module1Worker

    fake_device = DeviceInfo(ip="192.168.1.10", mac="aa:bb:cc:dd:ee:ff",
                              vendor="Acme", hostname="test-host",
                              device_type="Windows PC")
    fake_scan_result = {
        "devices":         [fake_device],
        "total_count":     1,
        "high_risk_count": 0,
    }

    errors: list = []
    results: list = []
    found: list = []

    monkeypatch.setattr("workers.scan_worker.scan", lambda *_a, **_kw: fake_scan_result,
                        raising=False)

    # Patch inside the run() closure path as well
    with patch("modules.rogue_device.scan", return_value=fake_scan_result):
        w = Module1Worker(offenders_path=tmp_path / "offenders.json")
        w.error.connect(errors.append)
        w.result.connect(results.append)
        w.device_found.connect(found.append)
        w.start()
        finished = w.wait(10000)
        # Drain the Qt event queue — cross-thread signal delivery is queued
        app = QApplication.instance()
        if app:
            for _ in range(5):
                app.processEvents()

    assert finished, "Module1Worker did not finish within 10 s"

    # The critical assertion: no error must have been emitted.
    # Any AttributeError on DeviceInfo.get() would surface here.
    assert errors == [], (
        f"Module1Worker emitted error — likely DeviceInfo.get() bug: {errors}"
    )
    # result must be emitted so _on_m1_result populates the Devices table
    assert results, "Module1Worker did not emit result — Devices table would be blank"
    assert results[0]["devices"] == [fake_device]

    # device_found must carry correct fields extracted from DeviceInfo
    assert found, "device_found signal was never emitted"
    assert found[0]["ip"]   == "192.168.1.10"
    assert found[0]["name"] == "test-host"
    assert found[0]["type"] == "Windows PC"

    _cleanup(w)
