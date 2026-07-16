"""
Regression tests for the shutdown-crash fix (2026-07-16).

Bug: app.py creates ~16 always-on background QThread workers as locals. None
were registered with Dashboard.closeEvent(), whose real-shutdown path ends in
os._exit(0). The post-app.exec() stop() block was therefore dead code, so the
raw-socket receivers (SNMP trap / syslog / passive observer) could be mid
recvfrom() when os._exit() -> ExitProcess() ran DLL_PROCESS_DETACH, corrupting
WinSock teardown -> STATUS_ACCESS_VIOLATION (or a deadlock/hang).

Two invariants are covered here:

1. SnmpTrapWorker.stop() / SyslogWorker.stop() must *interrupt* the blocking
   recvfrom() by closing the socket synchronously, not merely flip a flag and
   rely on the 1 s socket timeout. If stop() only flipped the flag, closeEvent's
   bounded wait would time out and fall through to terminate() (TerminateThread),
   which is the exact WinSock-lock corruption vector we are removing.

2. Dashboard must register these workers and stop them WITHOUT terminate().
"""
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


def _wait_until_bound(w, timeout_s=3.0):
    """Poll until the worker's receiver socket is bound, or skip if it never binds."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = getattr(w, "_receiver", None)
        if r is not None and getattr(r, "_sock", None) is not None:
            return True
        if not w.isRunning():
            pytest.skip("worker exited before binding (UDP port unavailable in CI)")
        time.sleep(0.02)
    pytest.skip("worker never bound within timeout (UDP port unavailable in CI)")
    return False


def test_snmp_trap_worker_stop_closes_socket_synchronously():
    from workers.snmp_trap_worker import SnmpTrapWorker
    w = SnmpTrapWorker(port=16251)
    w.start()
    _wait_until_bound(w)
    # It is now bound and (about to be) blocked in recvfrom().
    w.stop()
    # stop() must have closed the receiver socket itself — either the receiver
    # is already torn down, or its socket handle is None. If stop() only flipped
    # the flag (the old, buggy behaviour), the socket would still be live here.
    r = getattr(w, "_receiver", None)
    assert r is None or getattr(r, "_sock", None) is None, (
        "stop() did not close the socket synchronously — a blocked recvfrom() "
        "would be left for closeEvent to terminate() (TerminateThread corruption)"
    )
    assert w.wait(2000), "worker did not exit promptly after socket close"
    assert not w.isRunning()
    _cleanup(w)


def test_syslog_worker_stop_closes_socket_synchronously():
    from workers.syslog_worker import SyslogWorker
    w = SyslogWorker(port=15541)
    w.start()
    _wait_until_bound(w)
    w.stop()
    r = getattr(w, "_receiver", None)
    assert r is None or getattr(r, "_sock", None) is None, (
        "stop() did not close the socket synchronously — a blocked recvfrom() "
        "would be left for closeEvent to terminate() (TerminateThread corruption)"
    )
    assert w.wait(2000), "worker did not exit promptly after socket close"
    assert not w.isRunning()
    _cleanup(w)


# The shutdown logic lives in module-level helpers (not Dashboard methods) so it
# is unit-testable without constructing a Dashboard — RULE-TP4-DASH forbids that,
# and PyQt6's sip layer blocks attribute access on a __new__'d QWidget anyway.

def test_register_external_worker_appends_without_duplicates():
    from ui.dashboard import _register_external_worker

    workers = []

    class _W:
        pass

    w = _W()
    _register_external_worker(workers, w)
    assert w in workers
    _register_external_worker(workers, w)   # idempotent — no duplicate registration
    assert workers.count(w) == 1
    _register_external_worker(workers, None)  # tolerate None (rest_api_worker may be None)
    assert None not in workers


def test_stop_external_workers_signals_stop_but_never_terminates():
    from ui.dashboard import _drain_external_workers

    calls = []

    class _FakeWorker:
        def __init__(self):
            self._running = True

        def isRunning(self):
            return self._running

        def stop(self):
            calls.append("stop")
            self._running = False   # a well-behaved stop() unblocks promptly

        def wait(self, ms):
            calls.append(("wait", ms))
            return True

        def terminate(self):
            calls.append("terminate")

    fw = _FakeWorker()
    _drain_external_workers([fw])

    assert "stop" in calls, "external worker was never signalled to stop"
    assert "terminate" not in calls, (
        "external workers must NEVER be terminate()d — TerminateThread on a "
        "worker inside a raw socket / Npcap call corrupts OS teardown"
    )
    assert not fw.isRunning()
