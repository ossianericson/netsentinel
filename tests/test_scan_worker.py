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


def test_prescan_emits_error_not_done_on_failure(monkeypatch):
    """G5 regression test: before the fix, an exception inside run() (e.g.
    get_local_ip() raising) left done() never fired — the dashboard's
    'Pre-scan in progress…' verdict hung forever with no recovery. run()
    must now catch the exception and emit error(), never done()."""
    from workers.scan_worker import PreScanWorker

    def _raise(*_a, **_kw):
        raise RuntimeError("no network adapter found")

    monkeypatch.setattr("modules.utils.get_local_ip", _raise)

    done_calls = []
    error_calls = []
    w = PreScanWorker(flush_caches=False)
    w.done.connect(lambda: done_calls.append(True))
    w.error.connect(error_calls.append)
    w.start()
    finished = w.wait(10000)
    assert finished, "PreScanWorker did not finish within 10 s"
    assert not w.isRunning()
    # Cross-thread signals to plain Python callables are queued — pump the
    # event loop so the connected slots actually run before asserting.
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    assert error_calls == ["no network adapter found"]
    assert done_calls == []
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


# ── Module2Worker / Module3Worker subprocess cleanup (finding #16) ───────────
#
# These workers spawn a helper multiprocessing.Process to isolate Scapy/Npcap
# from the main process. Bug: the child was only reaped (terminate()+join())
# on the *normal* exit path — an exception raised before that point, or a
# forced QThread.terminate() during app close, orphaned the child. The fix
# adds a try/finally safety net (both workers) and a cooperative stop_event/
# mp_stop path for Module3Worker (which previously had no stop() at all,
# unlike Module2Worker).

class _FakeMpProcess:
    """Stands in for multiprocessing.Process — never actually runs `target`,
    just tracks start/terminate/join/is_alive so the QThread's own cleanup
    logic can be exercised without spawning a real OS process."""

    def __init__(self, target=None, args=(), daemon=None):
        self.target = target
        self.args = args
        self.daemon = daemon
        self.pid = 4242
        self.exitcode = 0
        self.terminate_called = False
        self._started = False

    def start(self):
        self._started = True

    def is_alive(self):
        return self._started and not self.terminate_called

    def terminate(self):
        self.terminate_called = True

    def join(self, timeout=None):
        pass


class _StopAwareMpProcess(_FakeMpProcess):
    """Simulates a well-behaved child: exits (is_alive() -> False) once mp_stop
    (the last positional arg, by convention) is set — mirrors a real child
    process that polls mp_stop and exits within its own poll interval."""

    def is_alive(self):
        if not self._started or self.terminate_called:
            return False
        mp_stop = self.args[-1]
        return not mp_stop.is_set()


class _CrashOnceMpProcess(_FakeMpProcess):
    """Like _FakeMpProcess, but is_alive() raises on its first call — simulates
    an unexpected exception occurring mid-scan, before the worker reaches its
    normal terminate()/join() reap code."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._is_alive_calls = 0

    def is_alive(self):
        self._is_alive_calls += 1
        if self._is_alive_calls == 1:
            raise RuntimeError("boom mid-scan")
        return not self.terminate_called


def test_module3_worker_has_stop_method():
    from workers.scan_worker import Module3Worker
    w = Module3Worker(duration=1)
    assert hasattr(w, "stop")
    assert not w.isRunning()
    _cleanup(w)


def test_module3_worker_stop_exits_without_waiting_full_duration(monkeypatch):
    """stop() must propagate to the child via mp_stop and exit promptly,
    instead of running for the full duration + 15s deadline."""
    import multiprocessing as _mp_real
    from workers.scan_worker import Module3Worker

    monkeypatch.setattr(_mp_real, "Process", _StopAwareMpProcess)

    w = Module3Worker(duration=30)
    w.stop()  # set the cooperative flag before start() — no race, Event persists
    w.start()
    finished = w.wait(5000)
    assert finished, "Module3Worker did not honour stop() promptly"
    assert not w.isRunning()
    _cleanup(w)


def test_module3_worker_exception_path_still_reaps_process(monkeypatch):
    """Regression for finding #16: an exception raised before the normal
    terminate()/join() line must still result in the child being reaped."""
    import multiprocessing as _mp_real
    from workers.scan_worker import Module3Worker

    created = []
    monkeypatch.setattr(_mp_real, "Process", lambda **kw: created.append(_CrashOnceMpProcess(**kw)) or created[-1])

    errors = []
    w = Module3Worker(duration=30)
    w.error.connect(errors.append)
    w.start()
    finished = w.wait(5000)
    assert finished
    assert not w.isRunning()

    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()

    assert errors and "Module 3 error" in errors[0]
    assert created and created[0].terminate_called is True, (
        "child process must be terminated even when an exception interrupts the scan loop"
    )
    _cleanup(w)


def test_module2_worker_exception_path_still_reaps_process(monkeypatch):
    """Same regression as above, for Module2Worker (STP scan)."""
    import multiprocessing as _mp_real
    from workers.scan_worker import Module2Worker

    created = []
    monkeypatch.setattr(_mp_real, "Process", lambda **kw: created.append(_CrashOnceMpProcess(**kw)) or created[-1])

    errors = []
    w = Module2Worker(gateway_mac="aa:bb:cc:dd:ee:ff", duration=30)
    w.error.connect(errors.append)
    w.start()
    finished = w.wait(5000)
    assert finished
    assert not w.isRunning()

    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()

    assert errors and "Module 2 error" in errors[0]
    assert created and created[0].terminate_called is True, (
        "child process must be terminated even when an exception interrupts the scan loop"
    )
    _cleanup(w)
