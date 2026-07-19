"""Regression tests for the bounded shutdown drain (ui/shutdown.py).

Part 2 of the Store-build shutdown crash/hang plan. Three defects are covered:

1. **Unbounded serial waits.** closeEvent() waited per worker — 23 dashboard
   workers x (800 + 2000) ms plus 17 external x 1500 ms, one after another, with
   no global deadline. Worst case ~90 s of UI-thread block, which is the "closing
   hangs" report. The replacement signal-stops everything first, then spends ONE
   global deadline across all of them.

2. **terminate() on dashboard-owned workers.** _arp/_dhcp/_syn/_udp/_pe_worker do
   raw-socket / Npcap / scapy work; TerminateThread on such a thread leaves
   WinSock/Npcap OS locks held, corrupting the DLL_PROCESS_DETACH teardown that
   the final exit runs — the ACCESS_VIOLATION in the crash log. The "never
   terminate" lesson had been applied to the external path only.

3. **Workers in no shutdown list at all** (_lan_check_worker et al.), killed
   mid-syscall by the hard exit — covered in test_shutdown_worker_registration.py.

These run in-process: the drain is a module-level free function taking a plain
list, so no Dashboard is constructed (RULE-TP4-DASH) and the fakes below need no
Qt at all.
"""
from __future__ import annotations

import time

import pytest


@pytest.fixture(autouse=True)
def _hermetic_shutdown_log(tmp_path, monkeypatch):
    """Keep drain_workers()' own logging out of the developer's real AppData.

    drain_workers() calls shutdown_log() on every run, so without this every test
    in this module appends to the live netsentinel_shutdown.log.
    """
    from ui import shutdown as _sd

    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: tmp_path)
    _sd._reset_shutdown_log_for_test()
    yield
    _sd._reset_shutdown_log_for_test()


class _FakeWorker:
    """Records the calls the drain makes, and how long each wait was given."""

    def __init__(self, name: str = "w", *, stops_on_signal: bool = True,
                 wait_returns: bool = True):
        self.name = name
        self._running = True
        self._stops_on_signal = stops_on_signal
        self._wait_returns = wait_returns
        self.calls: list = []

    def isRunning(self) -> bool:
        return self._running

    def stop(self) -> None:
        self.calls.append("stop")
        if self._stops_on_signal:
            self._running = False

    def wait(self, ms) -> bool:
        self.calls.append(("wait", ms))
        if self._wait_returns:
            self._running = False
            return True
        # A worker genuinely stuck inside a blocking syscall consumes the whole
        # budget it was granted. Modelling that is what makes the global-deadline
        # test meaningful — a fake that returns instantly never spends the budget,
        # so every later worker would still find time left and the test would pass
        # even against a per-worker budget.
        time.sleep(ms / 1000.0)
        return False

    def terminate(self) -> None:
        self.calls.append("terminate")


def test_drain_signals_stop_to_every_worker_before_waiting_on_any():
    """Stop-all-then-wait, not stop/wait/stop/wait — a serial loop makes each
    worker's shutdown latency additive instead of overlapping."""
    from ui.shutdown import drain_workers

    order: list = []

    class _OrderedWorker(_FakeWorker):
        def stop(self):
            order.append(("stop", self.name))
            super().stop()

        def wait(self, ms):
            order.append(("wait", self.name))
            return super().wait(ms)

    workers = [_OrderedWorker(f"w{i}", stops_on_signal=False) for i in range(3)]
    drain_workers(workers, deadline_s=1.0)

    kinds = [k for k, _ in order]
    assert kinds.count("stop") == 3, "every worker must be signalled to stop"
    first_wait = kinds.index("wait")
    assert set(kinds[:first_wait]) == {"stop"}, (
        f"a wait() ran before all stop()s were issued — serial drain, so shutdown "
        f"latency is additive across workers. Order: {order}"
    )


def test_drain_never_calls_terminate():
    """TerminateThread on a worker inside a raw socket / Npcap call is the
    documented WinSock/Npcap lock-corruption vector (mirrors the external-worker
    test in test_shutdown_worker_registration.py, now generalised)."""
    from ui.shutdown import drain_workers

    stuck = _FakeWorker("stuck", stops_on_signal=False, wait_returns=False)
    drain_workers([stuck], deadline_s=0.2)

    assert "terminate" not in stuck.calls, (
        "dashboard-owned workers must NEVER be terminate()d — TerminateThread on "
        "a thread inside a raw socket / Npcap call corrupts OS teardown"
    )


def test_drain_honours_one_global_deadline_not_a_per_worker_budget():
    """The whole drain is bounded by deadline_s regardless of worker count.

    The old code gave each worker its own 800 ms (+2000 ms post-terminate) budget,
    so wall time scaled with the number of workers. With 20 stuck workers and a
    0.5 s deadline the drain must still return in ~0.5 s, not 20 x 0.5 s.
    """
    from ui.shutdown import drain_workers

    workers = [
        _FakeWorker(f"w{i}", stops_on_signal=False, wait_returns=False)
        for i in range(20)
    ]

    t0 = time.monotonic()
    still = drain_workers(workers, deadline_s=0.5)
    elapsed = time.monotonic() - t0

    # A per-worker budget would be 20 x 0.5s = 10s here. Wall time is the invariant
    # that matters: it is what blocks the UI thread and produces the close hang.
    assert elapsed < 1.5, (
        f"drain took {elapsed:.2f}s for 20 stuck workers against a 0.5s deadline — "
        f"the budget is still per-worker, not global"
    )
    assert len(still) == 20, "workers that never stopped must be reported back"


def test_drain_returns_workers_still_running_for_the_shutdown_log():
    """Which workers outlived their wait is the single most useful shutdown
    datum — it names the thread that the hard exit is about to kill mid-syscall."""
    from ui.shutdown import drain_workers

    good = _FakeWorker("good", stops_on_signal=True)
    bad = _FakeWorker("bad", stops_on_signal=False, wait_returns=False)

    still = drain_workers([good, bad], deadline_s=0.2)

    assert good not in still
    assert bad in still


def test_drain_tolerates_dead_cpp_objects_and_missing_stop():
    """A QThread whose C++ half is gone raises RuntimeError on any call; a worker
    may expose stop_logger()/quit() instead of stop(). Neither may abort the drain."""
    from ui.shutdown import drain_workers

    class _Dead:
        def isRunning(self):
            raise RuntimeError("wrapped C/C++ object has been deleted")

    class _LoggerStyle(_FakeWorker):
        stop = None                # no stop(); exposes stop_logger() instead

        def __init__(self):
            super().__init__("logger", stops_on_signal=True)

        def stop_logger(self):
            self.calls.append("stop_logger")
            self._running = False

    survivor = _FakeWorker("survivor")
    logger_style = _LoggerStyle()

    drain_workers([_Dead(), logger_style, survivor], deadline_s=0.5)

    assert "stop" in survivor.calls, "a dead sibling aborted the drain"
    assert "stop_logger" in logger_style.calls, "stop_logger() fallback not used"


def test_drain_of_empty_list_is_a_no_op():
    from ui.shutdown import drain_workers
    assert drain_workers([], deadline_s=0.5) == []


ORPHANED_WORKERS = (
    # Every one of these was created and started but appeared in NO shutdown
    # list, so the hard exit killed it mid-syscall. _lan_check_worker is the
    # worst: it fires at T+8s and does 2x socket.connect() with settimeout(3),
    # i.e. up to 6 s inside WinSock, and repeats every 30 s — squarely inside the
    # "closed it right after launch" window the crash reports come from.
    "_lan_check_worker",
    "_hw_detect_worker",
    "_vendor_batch_worker",
    "_avail_worker",
    "_lldp_worker",
    "_zte_worker",
    "_dns_bench_worker",
)


def test_previously_orphaned_workers_are_in_the_shutdown_stop_list():
    from ui.shutdown import DASHBOARD_WORKER_ATTRS

    missing = [a for a in ORPHANED_WORKERS if a not in DASHBOARD_WORKER_ATTRS]
    assert not missing, (
        f"workers absent from the closeEvent stop list: {missing}. Each is started "
        f"during normal use and would be killed mid-syscall by the process exit — "
        f"the documented ACCESS_VIOLATION vector."
    )


def test_collect_dashboard_workers_skips_none_and_deduplicates():
    """None is the normal 'never started' value for most of these attributes, and
    a worker can be reachable both by attribute and via the _workers list."""
    from ui.shutdown import collect_dashboard_workers

    class _Dash:
        pass

    shared = _FakeWorker("shared")
    dash = _Dash()
    dash._lan_check_worker = None            # never started — must not appear
    dash._avail_worker = shared
    dash._workers = [shared]                 # same object, second route
    dash._logger_worker = _FakeWorker("logger")

    collected = collect_dashboard_workers(dash)

    assert None not in collected
    assert collected.count(shared) == 1, "a worker reachable twice was added twice"
    assert dash._logger_worker in collected, "the persistent logger worker was missed"


def test_collect_page_pollers_finds_overview_tile_workers():
    """Home-tile pollers (IfaceBwPoller x2, _DnsPoller) start in showEvent and are
    torn down in hideEvent — but Qt delivers no hideEvent on the process-exit path,
    so that teardown is unreachable and they were alive at exit every single time."""
    from ui.shutdown import collect_page_pollers

    class _Tile:
        def __init__(self, worker):
            self._worker = worker

    bw = _FakeWorker("iface_bw")
    dns = _FakeWorker("dns")

    class _Overview:
        _tiles = {"live_bandwidth": _Tile(bw), "dns_stability": _Tile(dns),
                  "device_count": _Tile(None)}

    class _Dash:
        _overview_page = _Overview()

    found = collect_page_pollers(_Dash())

    assert bw in found and dns in found
    assert None not in found


def test_collect_page_pollers_tolerates_a_missing_overview_page():
    """The overview page is absent in headless/partial builds — must not raise."""
    from ui.shutdown import collect_page_pollers

    class _Dash:
        pass

    assert collect_page_pollers(_Dash()) == []


def test_collect_hardware_pollers_finds_plugin_poll_workers():
    """HardwareIntegrationPage.closedown() was a serial per-worker wait(2000) run
    AFTER the drain, i.e. outside the global deadline — measured at a flat 2.0 s
    of the ~5 s close in the live trials. Folding these workers into the one
    drain list is what actually makes the deadline global."""
    from ui.shutdown import collect_hardware_pollers

    a, b = _FakeWorker("poll_a"), _FakeWorker("poll_b")

    class _HwPage:
        _poll_workers = {"a": a, "b": b}

    class _Dash:
        _hardware_integration_page = _HwPage()

    found = collect_hardware_pollers(_Dash())
    assert a in found and b in found


def test_collect_hardware_pollers_tolerates_a_missing_hardware_page():
    from ui.shutdown import collect_hardware_pollers

    class _Dash:
        pass

    assert collect_hardware_pollers(_Dash()) == []


def test_hard_exit_declares_ctypes_types_on_a_local_windll_handle():
    """RULE-WIN11: an undeclared ctypes return/arg defaults to a 32-bit C int, so
    GetCurrentProcess()'s (HANDLE)-1 pseudo-handle truncates to 0x00000000FFFFFFFF
    and TerminateProcess fails with ERROR_INVALID_HANDLE before doing anything.
    A silent failure here means the process falls through to the old exit path.

    Also RULE-WIN11: the handle must be a LOCAL WinDLL. ctypes.windll.kernel32.*
    function objects are cached process-globals; assigning argtypes to them
    changes behaviour for every other caller in the process.
    """
    import ast
    import inspect
    import textwrap

    from ui import shutdown as _sd

    fn = ast.parse(textwrap.dedent(inspect.getsource(_sd.hard_exit))).body[0]

    assigned = {
        node.targets[0].attr
        for node in ast.walk(fn)
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Attribute)
        and node.targets[0].attr in {"restype", "argtypes"}
    }
    assert {"restype", "argtypes"} <= assigned, (
        "hard_exit() does not declare both restype and argtypes on its ctypes "
        "functions — a truncated HANDLE makes TerminateProcess a silent no-op"
    )

    # Compare against the CODE only. The docstring legitimately names the
    # forbidden ctypes.windll.kernel32 pattern to explain why it is forbidden,
    # and a raw-source substring check would flag that prose as a violation.
    if ast.get_docstring(fn) is not None:
        fn.body = fn.body[1:]
    code = ast.unparse(fn)

    assert "WinDLL(" in code, "hard_exit() must build a LOCAL WinDLL handle"
    assert "windll.kernel32" not in code, (
        "hard_exit() mutates the process-global ctypes.windll.kernel32 function "
        "objects — RULE-WIN11 requires a local WinDLL handle"
    )


def test_hard_exit_falls_back_to_os_exit_off_windows(monkeypatch):
    """TerminateProcess is Win32-only; every other platform must still exit."""
    from ui import shutdown as _sd

    calls = []
    monkeypatch.setattr(_sd.os, "_exit", lambda code: calls.append(code))
    monkeypatch.setattr(_sd.sys, "platform", "linux")

    _sd.hard_exit(0)

    assert calls == [0], "non-Windows path did not fall through to os._exit(0)"


def test_shutdown_log_writes_under_app_data_dir(tmp_path, monkeypatch):
    """RULE 23: the shutdown log must go to get_app_data_dir(), never the exe dir."""
    from ui import shutdown as _sd

    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: tmp_path)
    _sd._reset_shutdown_log_for_test()
    _sd.shutdown_log("closeEvent entry: %d workers", 7)
    _sd._flush_shutdown_log()

    logs = list(tmp_path.glob("netsentinel_shutdown.log"))
    assert logs, f"no shutdown log written under {tmp_path}"
    assert "closeEvent entry: 7 workers" in logs[0].read_text(encoding="utf-8")


def test_shutdown_log_never_raises_even_if_the_path_is_unwritable(monkeypatch):
    """Instrumentation must never be able to break the shutdown path itself."""
    from ui import shutdown as _sd

    def _boom():
        raise OSError("disk full")

    monkeypatch.setattr("modules.utils.get_app_data_dir", _boom)
    _sd._reset_shutdown_log_for_test()
    _sd.shutdown_log("this must not raise")   # no assertion needed — must not throw
