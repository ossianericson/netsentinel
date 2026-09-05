"""Shutdown instrumentation and the bounded worker drain for Dashboard.closeEvent().

Everything here is a module-level free function operating on plain lists, so the
shutdown path is unit-testable without constructing a Dashboard (RULE-TP4-DASH:
closeEvent() ends in a hard process exit, which under pytest would terminate the
test session itself).

Two jobs:

**Observability.** closeEvent() previously logged nothing at all, so a hang
anywhere inside it was indistinguishable from a normal quit — and debug_launch's
"event loop exited" line is unreachable because the hard exit fires first.
`shutdown_log()` writes to ``netsentinel_shutdown.log`` under get_app_data_dir()
(RULE 23), recording entry, per-worker stop/wait durations, which workers were
still running when the deadline expired, checkpoint duration, and total elapsed.
That last one is the point: the workers still running at exit time are exactly
the threads the hard exit is about to kill mid-syscall.

**A bounded drain.** `drain_workers()` replaces a serial per-worker loop that had
no global deadline — 23 dashboard workers x (800 + 2000) ms plus 17 external x
1500 ms, worst case ~90 s of blocked UI thread. It signal-stops everything first
so the workers shut down concurrently, then spends ONE deadline across all of
them. It never calls terminate(): TerminateThread on a thread inside a raw
socket (SNMP-trap / syslog / passive observer) or an Npcap capture leaves WinSock
/ Npcap OS locks held, which is what corrupts the DLL_PROCESS_DETACH teardown the
final exit runs — the ACCESS_VIOLATION seen in netsentinel_crash.log.
"""
from __future__ import annotations

import logging
import os
import sys
import time

DEFAULT_DRAIN_DEADLINE_S = 3.0

#: Every Dashboard attribute that may hold a QThread worker, drained on close.
#:
#: The trailing group was previously in NO shutdown list at all — each was
#: started during normal use and then killed mid-syscall by the process exit,
#: which is the documented ACCESS_VIOLATION vector. Adding an attribute here is
#: the whole registration step: a name absent from this tuple is a thread nobody
#: stops. Enforced by tests/test_shutdown_drain.py.
DASHBOARD_WORKER_ATTRS: tuple = (
    # Transient / one-shot scan workers (previously drained).
    "_net_info_worker", "_diag_worker", "_prescan_worker",
    "_mtr_worker", "_ps_worker", "_ipv6_worker", "_cloud_worker",
    "_arp_worker", "_dhcp_worker", "_bw_worker", "_sched_worker",
    "_snmp_worker", "_snmp_if_worker", "_syn_worker", "_udp_worker", "_cve_worker",
    "_exposure_worker", "_os_worker", "_cred_worker",
    "_discovery_worker", "_smb_worker", "_pe_worker",
    "_plugin_worker",
    # The persistent logger worker (stop_logger(), not stop()).
    "_logger_worker",
    # Previously orphaned — see the module docstring.
    "_lan_check_worker",     # _LanProbe: 2x connect() @ 3s timeout, repeats every 30s
    "_hw_detect_worker",     # HwDetectWorker: gateway HTTP probes
    "_vendor_batch_worker",  # _VendorBatchWorker: OUI lookups, may be online
    "_avail_worker",         # AvailabilityWorker: 60 s ping/RTT cycle
    "_lldp_worker",          # LldpWorker: passive Npcap sniff
    "_zte_worker",           # modem polling worker
    "_dns_bench_worker",     # DnsBenchmarkWorker: resolver latency probes
)


def collect_dashboard_workers(dash) -> list:
    """Every live worker the Dashboard owns, as one flat de-duplicated list.

    A worker can be reachable both by attribute and through ``_workers``; draining
    it twice would spend the shared deadline on a thread that is already stopping.
    """
    collected: list = []
    seen: set = set()

    def _add(w) -> None:
        if w is None or id(w) in seen:
            return
        seen.add(id(w))
        collected.append(w)

    for attr in DASHBOARD_WORKER_ATTRS:
        _add(getattr(dash, attr, None))
    for w in list(getattr(dash, "_workers", []) or []):
        _add(w)
    return collected

_shutdown_log = logging.getLogger("netsentinel.shutdown")
_handler_ready = False


def _ensure_shutdown_log_handler() -> None:
    """Attach the file handler once. Best-effort — never raises.

    Its own logger + FileHandler under get_app_data_dir(), independent of root
    logging config: nothing in the app calls logging.basicConfig(), so a bare
    log.info() would be dropped at the default WARNING root level.
    """
    global _handler_ready
    if _handler_ready:
        return
    _handler_ready = True          # set first: a failed attempt must not retry per call
    try:
        from modules.utils import get_app_data_dir
        _h = logging.FileHandler(
            str(get_app_data_dir() / "netsentinel_shutdown.log"), mode="a", encoding="utf-8"
        )
        _h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        _shutdown_log.addHandler(_h)
        _shutdown_log.setLevel(logging.INFO)
        _shutdown_log.propagate = False
    except Exception:
        pass  # instrumentation is best-effort; must never break the shutdown path


def shutdown_log(msg: str, *args) -> None:
    """Record one shutdown-path line. Swallows everything — see RULE-LINT2."""
    try:
        _ensure_shutdown_log_handler()
        _shutdown_log.info(msg, *args)
    except Exception:
        pass  # a broken log must never be able to stall or crash shutdown


def _flush_shutdown_log() -> None:
    for h in list(_shutdown_log.handlers):
        try:
            h.flush()
        except Exception:
            pass  # best-effort — process may be tearing down


def _reset_shutdown_log_for_test() -> None:
    """Drop handlers so a test can re-point the log at a tmp_path."""
    global _handler_ready
    for h in list(_shutdown_log.handlers):
        try:
            h.close()
        except Exception:
            pass  # best-effort — handler may already be closed
        _shutdown_log.removeHandler(h)
    _handler_ready = False


def collect_page_pollers(dash) -> list:
    """Background pollers owned by Overview tiles, which nothing else stops.

    LiveBandwidthTile / TopTalkersTile (IfaceBwPoller) and DnsStabilityTile
    (_DnsPoller) start their worker in ``showEvent`` and detach it in
    ``hideEvent``. Qt delivers no hideEvent on the process-exit path, so that
    teardown never runs and these threads — one of which polls every second —
    are always live when the process exits.
    """
    page = getattr(dash, "_overview_page", None)
    tiles = getattr(page, "_tiles", None) if page is not None else None
    if not tiles:
        return []
    found: list = []
    try:
        candidates = list(tiles.values())
    except Exception:
        return []
    for tile in candidates:
        w = getattr(tile, "_worker", None)
        if w is not None and w not in found:
            found.append(w)
    return found


def collect_hardware_pollers(dash) -> list:
    """Hardware-integration (USB/serial/GPIO) plugin poll workers.

    HardwareIntegrationPage.closedown() stops these with its own serial
    ``stop(); wait(2000)`` per worker, which ran after the drain and therefore
    outside the global deadline — a measured flat 2.0 s of a ~5 s close. Draining
    them with everything else keeps the whole shutdown inside one budget.
    """
    page = getattr(dash, "_hardware_integration_page", None)
    workers = getattr(page, "_poll_workers", None) if page is not None else None
    if not workers:
        return []
    try:
        return [w for w in workers.values() if w is not None]
    except Exception:
        return []


def hard_exit(code: int = 0) -> None:
    """End the process without running DLL_PROCESS_DETACH. Never returns.

    Even with every worker drained, some thread will occasionally still be inside
    Npcap or WinSock at exit time. ``os._exit()`` calls ExitProcess, which runs
    ``DLL_PROCESS_DETACH`` for every loaded DLL — and a thread killed while
    holding the CRT heap lock, the loader lock, or a WinSock/Npcap internal lock
    faults or deadlocks that teardown. That is the ACCESS_VIOLATION the Store
    build reports to Windows Error Reporting on close.

    This is also the only honest place to mark the session record clean (A1). It
    cannot go in ``atexit``: the call below never returns, so no ``atexit`` handler
    ever runs. Everything that reaches here is a deliberate shutdown, and anything
    that does not reach here — an OOM kill, a native FailFast, a hang the OS ends —
    correctly leaves the record unclean for the next launch to find.

    ``TerminateProcess`` skips the detach sequence and CRT teardown entirely:
    there is no teardown left to corrupt, so no fault and no WER report. This
    does NOT replace draining the workers — the drain is the real fix; this
    removes the residual structural exposure that no amount of draining closes.

    RULE-WIN11: types are declared on a LOCAL ``WinDLL`` handle. Undeclared,
    ctypes would default ``GetCurrentProcess()``'s ``(HANDLE)-1`` pseudo-handle to
    a 32-bit int, TerminateProcess would fail with ERROR_INVALID_HANDLE, and the
    call would silently do nothing. Assigning argtypes to
    ``ctypes.windll.kernel32.*`` is forbidden — those function objects are cached
    process-globals shared with every other caller.
    """
    try:
        from modules.session_record import end_session_clean
        end_session_clean()
    except Exception as exc:
        shutdown_log("session record: end_session_clean() failed: %s", exc)
    _flush_shutdown_log()
    if sys.platform == "win32":
        try:
            import ctypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.GetCurrentProcess.restype = ctypes.c_void_p
            k32.GetCurrentProcess.argtypes = []
            k32.TerminateProcess.restype = ctypes.c_int
            k32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            k32.TerminateProcess(k32.GetCurrentProcess(), ctypes.c_uint(code))
        except Exception:
            pass  # fall through to os._exit below if ctypes/kernel32 is unavailable
    os._exit(code)


def _signal_stop(worker) -> str:
    """Ask *worker* to stop by whichever cooperative API it exposes."""
    for attr in ("stop", "stop_logger"):
        fn = getattr(worker, attr, None)
        if callable(fn):
            fn()
            return attr
    quit_fn = getattr(worker, "quit", None)
    if callable(quit_fn):
        quit_fn()              # ask the worker's event loop to exit
        return "quit"
    return "none"


def drain_workers(workers: list, deadline_s: float = DEFAULT_DRAIN_DEADLINE_S,
                  label: str = "workers") -> list:
    """Signal-stop every worker, then wait for all of them against ONE deadline.

    Returns the workers still running when the deadline expired — the threads the
    caller is about to kill mid-syscall, and the single most useful line in the
    shutdown log.

    Deliberately never calls terminate(); see the module docstring. Tolerates
    workers whose C++ half is already gone (RuntimeError on any call) and workers
    exposing stop_logger()/quit() instead of stop().
    """
    if not workers:
        return []

    t0 = time.monotonic()

    # Phase 1 — signal every worker to stop before waiting on any of them, so
    # their shutdowns overlap. A stop/wait/stop/wait loop makes the total latency
    # the SUM of each worker's stop time instead of the maximum.
    for w in list(workers):
        try:
            if w.isRunning():
                how = _signal_stop(w)
                if how == "none":
                    shutdown_log("  %s: %r exposes no stop()/stop_logger()/quit()", label, w)
        except RuntimeError:
            pass  # underlying C++ QThread already gone
        except Exception as exc:
            shutdown_log("  %s: stop() raised on %r: %s", label, w, exc)

    # Phase 2 — one global deadline shared by all workers. Each wait() gets only
    # the time actually left, so total wall time is bounded by deadline_s no
    # matter how many workers there are.
    deadline = t0 + deadline_s
    still_running = []
    for w in list(workers):
        remaining_ms = int(max(0.0, deadline - time.monotonic()) * 1000)
        try:
            if not w.isRunning():
                continue
            if remaining_ms <= 0:
                still_running.append(w)      # budget spent — do not block further
                continue
            t_w = time.monotonic()
            if not w.wait(remaining_ms):
                still_running.append(w)
                shutdown_log(
                    "  %s: %s still running after %.0fms wait (deadline shared)",
                    label, type(w).__name__, (time.monotonic() - t_w) * 1000,
                )
        except RuntimeError:
            pass  # underlying C++ QThread already gone
        except Exception as exc:
            shutdown_log("  %s: wait() raised on %r: %s", label, w, exc)

    shutdown_log(
        "%s drain: %d worker(s), %.0fms elapsed, %d still running%s",
        label, len(workers), (time.monotonic() - t0) * 1000, len(still_running),
        (" -> " + ", ".join(sorted({type(w).__name__ for w in still_running}))) if still_running else "",
    )
    return still_running
