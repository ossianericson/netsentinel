"""Tests for tools/monkey_test.py — import, dataclass construction, blacklist logic.

Run locally only:
    python -m pytest -m monkey

Never runs in CI (excluded by addopts in pyproject.toml).
"""
import importlib
import sys
import subprocess
from pathlib import Path

import pytest

TOOLS_ROOT = Path(__file__).parent.parent / "tools"

pytestmark = pytest.mark.monkey


def _import_monkey():
    """Import monkey_test without executing main()."""
    if "monkey_test" in sys.modules:
        return sys.modules["monkey_test"]
    spec = importlib.util.spec_from_file_location("monkey_test", TOOLS_ROOT / "monkey_test.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except ImportError as exc:
        pytest.skip(f"monkey_test dependency missing: {exc}")
    sys.modules["monkey_test"] = mod
    return mod


def test_import():
    mod = _import_monkey()
    assert hasattr(mod, "MonkeyTester")
    assert hasattr(mod, "Config")
    assert hasattr(mod, "Stats")
    assert hasattr(mod, "History")


def test_config_defaults():
    mod = _import_monkey()
    cfg = mod.Config()
    assert cfg.iterations == 200
    assert cfg.chaos == "moderate"
    assert cfg.seed is None
    assert cfg.mem_limit_mb == 1500


def test_config_custom():
    mod = _import_monkey()
    cfg = mod.Config(iterations=25, chaos="wild", seed=42, mem_limit_mb=512)
    assert cfg.iterations == 25
    assert cfg.chaos == "wild"
    assert cfg.seed == 42


def test_stats_initial():
    mod = _import_monkey()
    s = mod.Stats()
    assert s.completed == 0
    assert s.crashes == 0
    assert s.skipped == 0
    assert s.blacklisted == 0
    assert s.exceptions == 0


def test_history_instantiation():
    mod = _import_monkey()
    h = mod.History(maxsize=10)
    assert len(h.dump()) == 0


def test_blacklist_contains_close_glyph():
    mod = _import_monkey()
    close_glyph = ""
    assert any(close_glyph in entry for entry in mod._BLACKLIST)


def test_blacklist_contains_quit():
    mod = _import_monkey()
    assert any("quit" in entry.lower() for entry in mod._BLACKLIST)


def test_is_blacklisted_exact_match():
    mod = _import_monkey()
    assert mod._is_blacklisted("quit", "Button")


def test_is_blacklisted_partial_match():
    mod = _import_monkey()
    assert mod._is_blacklisted("run port scan now", "Button")


def test_is_blacklisted_safe_control():
    mod = _import_monkey()
    assert not mod._is_blacklisted("Overview", "Button")
    assert not mod._is_blacklisted("Speed Test", "Button")


def test_cli_help():
    result = subprocess.run(
        [sys.executable, str(TOOLS_ROOT / "monkey_test.py"), "--help"],
        capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0
    assert "--chaos" in result.stdout or "--chaos" in result.stderr


# ── Focus-guard escalation (Finding 1, 2026-07-10 soak) ───────────────────────

def _bare_tester(mod):
    """A MonkeyTester with only the attributes the focus methods touch — avoids
    launching the real app that a full __init__ would."""
    import logging
    t = object.__new__(mod.MonkeyTester)
    t.log = logging.getLogger("monkey-test-focus")
    t.stats = mod.Stats()
    return t


def test_describe_hwnd_returns_string():
    mod = _import_monkey()
    # 0 is never a valid window; must not raise, must return the class/proc/pid shape.
    desc = mod._describe_hwnd(0)
    assert "class=" in desc and "proc=" in desc and "pid=" in desc


def test_escalate_app_reclaim_succeeds_before_retries_exhausted(monkeypatch):
    mod = _import_monkey()
    t = _bare_tester(mod)
    app_hwnd = 0x1234

    monkeypatch.setattr(mod.time, "sleep", lambda *_a, **_k: None)
    force_calls = []
    monkeypatch.setattr(mod, "_force_foreground", lambda h: force_calls.append(h))
    # Foreground is wrong on attempt 1, correct on attempt 2.
    seq = iter([0x9999, app_hwnd])
    monkeypatch.setattr(mod, "_get_foreground_hwnd", lambda: next(seq))

    assert t._escalate_app_reclaim(app_hwnd, retries=3) is True
    assert force_calls == [app_hwnd, app_hwnd]   # stopped as soon as it succeeded


def test_escalate_app_reclaim_gives_up_after_bounded_retries(monkeypatch):
    mod = _import_monkey()
    t = _bare_tester(mod)
    app_hwnd = 0x1234

    monkeypatch.setattr(mod.time, "sleep", lambda *_a, **_k: None)
    force_calls = []
    monkeypatch.setattr(mod, "_force_foreground", lambda h: force_calls.append(h))
    monkeypatch.setattr(mod, "_get_foreground_hwnd", lambda: 0x9999)  # never reclaims

    assert t._escalate_app_reclaim(app_hwnd, retries=3) is False
    assert len(force_calls) == 3   # bounded — does NOT loop forever (was 447x/16.5min)


def test_assert_focus_system_window_escalates_and_never_dismisses(monkeypatch):
    """A system/desktop foreground thief must trigger app-reclaim escalation and must
    NEVER be sent to _dismiss_native_window (WM_CLOSE to Desktop opens Shut Down)."""
    import types
    mod = _import_monkey()
    t = _bare_tester(mod)
    app_hwnd = 0x1234
    thief = 0xC0DE
    t._win = types.SimpleNamespace(handle=app_hwnd, set_focus=lambda: None)
    t.cfg = types.SimpleNamespace(screenshots=False, output_dir=".")

    monkeypatch.setattr(mod.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "_force_foreground", lambda h: None)
    # Foreground is the thief until escalation runs; the guard must classify it system.
    monkeypatch.setattr(mod, "_get_foreground_hwnd", lambda: thief)
    monkeypatch.setattr(mod, "_is_system_hwnd", lambda h: True)

    dismiss_calls = []
    monkeypatch.setattr(t, "_dismiss_native_window",
                        lambda h: dismiss_calls.append(h) or True)
    escalate_calls = []
    monkeypatch.setattr(t, "_escalate_app_reclaim",
                        lambda h, **_k: escalate_calls.append(h) or True)

    result = t._assert_focus()

    assert escalate_calls == [app_hwnd]   # escalation was attempted on our window
    assert dismiss_calls == []            # thief was never WM_CLOSE'd
    assert result is True                 # escalation reported reclaim -> proceed


# ── Minimized-window false-restart (2026-07-23 wild-soak finding) ────────────

def test_window_ok_accepts_minimized_but_alive_window(monkeypatch):
    """A minimized-but-alive window must still pass _window_ok().

    Live-confirmed mechanism (RULE-DBG3): minimizing the real native-chrome window
    clears WS_VISIBLE, which drops it out of Desktop(backend="uia").windows()
    entirely -- there's no rectangle to size-check against toast popups, the
    window just isn't enumerated. A fresh UIA scan can never find it while
    minimized, so _window_ok() must fall back to the last-known cached HWND +
    raw win32 state (IsWindow + PID match + IsIconic) instead."""
    import types
    mod = _import_monkey()
    t = _bare_tester(mod)
    app_hwnd = 0x1234
    target_pid = 4242

    # No .exists() attribute -- matches the real UIAWrapper (it has none either;
    # the "fast path" always raises AttributeError today, caught by the method).
    t._win = types.SimpleNamespace(handle=app_hwnd)
    t._proc = types.SimpleNamespace(pid=target_pid)

    monkeypatch.setattr(mod.time, "sleep", lambda *_a, **_k: None)
    # Fresh UIA scan finds nothing -- reproduces the live-confirmed vanishing
    # act, not a size-check failure.
    monkeypatch.setattr(mod, "Desktop", lambda backend: types.SimpleNamespace(windows=lambda: []))

    user32 = mod.ctypes.windll.user32
    monkeypatch.setattr(user32, "IsWindow", lambda h: 1)

    def _fake_get_pid(hwnd, ref):
        mod.ctypes.cast(ref, mod.ctypes.POINTER(mod.ctypes.c_ulong))[0] = target_pid

    monkeypatch.setattr(user32, "GetWindowThreadProcessId", _fake_get_pid)
    monkeypatch.setattr(user32, "IsIconic", lambda h: 1)

    assert t._window_ok() is True


def test_window_ok_rejects_dead_pid_even_if_handle_reused(monkeypatch):
    """A stale HWND whose PID no longer matches ours must NOT be accepted --
    e.g. the value was recycled by an unrelated window after a real crash."""
    import types
    mod = _import_monkey()
    t = _bare_tester(mod)
    app_hwnd = 0x1234
    target_pid = 4242
    other_pid = 9999

    t._win = types.SimpleNamespace(handle=app_hwnd)
    t._proc = types.SimpleNamespace(pid=target_pid)

    monkeypatch.setattr(mod.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "Desktop", lambda backend: types.SimpleNamespace(windows=lambda: []))

    user32 = mod.ctypes.windll.user32
    monkeypatch.setattr(user32, "IsWindow", lambda h: 1)

    def _fake_get_pid(hwnd, ref):
        mod.ctypes.cast(ref, mod.ctypes.POINTER(mod.ctypes.c_ulong))[0] = other_pid

    monkeypatch.setattr(user32, "GetWindowThreadProcessId", _fake_get_pid)
    monkeypatch.setattr(user32, "IsIconic", lambda h: 1)

    assert t._window_ok(retries=1) is False


# ── _window_ok/_focus_heartbeat .exists() AttributeError (2026-07-23 chaos-script fix) ──

def test_window_ok_fast_path_skips_slow_scan_for_live_cached_window(monkeypatch):
    """A still-alive cached window must be accepted by the FAST path alone --
    the real UIAWrapper (Desktop().windows()'s return type) has no .exists()
    method at all, so `self._win.exists()` always raised AttributeError,
    silently swallowed, forcing every single check onto the slow full
    Desktop(backend="uia").windows() re-enumeration even when the cached
    handle is perfectly valid. Asserting Desktop() is never called is what
    catches the regression -- both paths return True either way."""
    import types
    mod = _import_monkey()
    t = _bare_tester(mod)
    app_hwnd = 0x1234
    target_pid = 4242

    class _FakeRect:
        left, top, right, bottom = 0, 0, 1000, 800

    class _FakeProc:
        def name(self):
            return "netsentinel.exe"

    # No .exists() attribute -- matches the real UIAWrapper.
    t._win = types.SimpleNamespace(
        handle=app_hwnd,
        rectangle=lambda: _FakeRect(),
        element_info=types.SimpleNamespace(process_id=target_pid),
    )
    t._proc = types.SimpleNamespace(pid=target_pid)

    monkeypatch.setattr(mod.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(mod.psutil, "Process", lambda pid: _FakeProc())

    # Deliberately finds nothing -- if the fast path fails to short-circuit
    # (the bug), _window_ok() falls through to False; the desktop_calls list
    # is the clean, exception-swallow-proof signal either way.
    desktop_calls = []

    def _record_desktop(backend):
        desktop_calls.append(backend)
        return types.SimpleNamespace(windows=lambda: [])

    monkeypatch.setattr(mod, "Desktop", _record_desktop)

    user32 = mod.ctypes.windll.user32
    monkeypatch.setattr(user32, "IsWindow", lambda h: 1)

    def _fake_get_pid(hwnd, ref):
        mod.ctypes.cast(ref, mod.ctypes.POINTER(mod.ctypes.c_ulong))[0] = target_pid

    monkeypatch.setattr(user32, "GetWindowThreadProcessId", _fake_get_pid)

    result = t._window_ok()

    assert desktop_calls == [], (
        "slow Desktop() re-scan ran even though the cached window is alive -- "
        "the fast path is not short-circuiting"
    )
    assert result is True


class _FakeStopEvent:
    """Stands in for threading.Event -- stops the heartbeat loop after one tick."""

    def __init__(self):
        self._flag = False
        self.wait_calls = 0

    def is_set(self):
        return self._flag

    def wait(self, timeout=None):
        self.wait_calls += 1
        self._flag = True  # exit the while-loop after this iteration
        return True


def test_focus_heartbeat_reasserts_foreground_on_valid_cached_window(monkeypatch):
    """The heartbeat's per-tick liveness check must actually call
    _force_foreground() for a valid cached window -- not silently no-op
    forever via the same swallowed .exists() AttributeError as _window_ok()."""
    import types
    mod = _import_monkey()
    t = _bare_tester(mod)
    app_hwnd = 0x1234
    target_pid = 4242

    t._win = types.SimpleNamespace(handle=app_hwnd)
    t._proc = types.SimpleNamespace(pid=target_pid)
    t.cfg = types.SimpleNamespace(focus_interval=0.0)
    t._stop = _FakeStopEvent()

    user32 = mod.ctypes.windll.user32
    monkeypatch.setattr(user32, "IsWindow", lambda h: 1)

    def _fake_get_pid(hwnd, ref):
        mod.ctypes.cast(ref, mod.ctypes.POINTER(mod.ctypes.c_ulong))[0] = target_pid

    monkeypatch.setattr(user32, "GetWindowThreadProcessId", _fake_get_pid)

    force_calls = []
    monkeypatch.setattr(mod, "_force_foreground", lambda h: force_calls.append(h))

    t._focus_heartbeat()

    assert force_calls == [app_hwnd]
    assert t._stop.wait_calls == 1


# ── RULE-DBG4: RSS sampling must include child processes ──────────────────────

def test_total_rss_mb_sums_main_and_children():
    """A single-PID sample is structurally blind to any leak inside a spawned
    child process (e.g. QtWebEngineProcess.exe for Network Map's Interactive
    view) — a live repro (docs/spikes/network-map-bandwidth-worker-leak-repro.py)
    found a real, unbounded leak that would have been invisible to every prior
    wild-soak RSS number, which sampled the main PID only."""
    import types
    mod = _import_monkey()
    t = _bare_tester(mod)

    def _mem(rss_bytes):
        return types.SimpleNamespace(rss=rss_bytes)

    main = types.SimpleNamespace(
        memory_info=lambda: _mem(200 * 1024 * 1024),
        children=lambda recursive=True: [
            types.SimpleNamespace(memory_info=lambda: _mem(50 * 1024 * 1024)),
            types.SimpleNamespace(memory_info=lambda: _mem(30 * 1024 * 1024)),
        ],
    )
    t._proc = main

    assert t._total_rss_mb() == pytest.approx(280.0)


def test_total_rss_mb_skips_a_child_that_vanishes():
    """A child exiting between children() and memory_info() must not crash
    the sample — it's excluded from that checkpoint's total, not fatal."""
    import types
    mod = _import_monkey()
    t = _bare_tester(mod)

    def _mem(rss_bytes):
        return types.SimpleNamespace(rss=rss_bytes)

    def _vanished():
        raise mod.psutil.NoSuchProcess(pid=999)

    main = types.SimpleNamespace(
        memory_info=lambda: _mem(100 * 1024 * 1024),
        children=lambda recursive=True: [types.SimpleNamespace(memory_info=_vanished)],
    )
    t._proc = main

    assert t._total_rss_mb() == pytest.approx(100.0)


def test_total_rss_mb_returns_zero_with_no_process():
    mod = _import_monkey()
    t = _bare_tester(mod)
    t._proc = None
    assert t._total_rss_mb() == 0.0


# ── Tracemalloc salvage before restart (wild-soak data-gap fix) ──────────────
#
# app.py truncates tracemalloc_snapshots.log fresh on every launch (RULE-TM1).
# _restart_app() kills the current app.py and relaunches a new one on a hang/
# crash/dead-window, so without a salvage step, every allocation snapshot
# since phase start is destroyed the instant the new process starts — and
# run_all_monkey_tests.ps1's end-of-phase copy only ever sees what
# accumulated since the LAST restart. These tests would fail against the
# pre-fix code (no _salvage_tracemalloc_log method at all).

def test_salvage_tracemalloc_log_copies_before_restart_truncates(monkeypatch, tmp_path):
    mod = _import_monkey()
    src = tmp_path / "tracemalloc_snapshots.log"
    src.write_text("tracemalloc top-20 snapshot #1\nsome allocation line\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_tracemalloc_log_path", lambda: src)

    t = _bare_tester(mod)
    out_dir = tmp_path / "phase_out"
    t.cfg = mod.Config(output_dir=str(out_dir), tracemalloc=True)
    t.stats.restarts = 1

    t._salvage_tracemalloc_log()

    dest = out_dir / "tracemalloc_pre_restart_1.log"
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")


def test_salvage_tracemalloc_log_numbers_files_per_restart(monkeypatch, tmp_path):
    """Two restarts in one phase must not clobber each other's salvaged log."""
    mod = _import_monkey()
    src = tmp_path / "tracemalloc_snapshots.log"
    monkeypatch.setattr(mod, "_tracemalloc_log_path", lambda: src)

    t = _bare_tester(mod)
    out_dir = tmp_path / "phase_out"
    t.cfg = mod.Config(output_dir=str(out_dir), tracemalloc=True)

    src.write_text("tracemalloc top-20 snapshot #1\nfirst-process data\n", encoding="utf-8")
    t.stats.restarts = 1
    t._salvage_tracemalloc_log()

    src.write_text("tracemalloc top-20 snapshot #7\nsecond-process data\n", encoding="utf-8")
    t.stats.restarts = 2
    t._salvage_tracemalloc_log()

    assert "first-process data" in (out_dir / "tracemalloc_pre_restart_1.log").read_text(encoding="utf-8")
    assert "second-process data" in (out_dir / "tracemalloc_pre_restart_2.log").read_text(encoding="utf-8")


def test_salvage_tracemalloc_log_noop_when_tracemalloc_disabled(monkeypatch, tmp_path):
    mod = _import_monkey()
    src = tmp_path / "tracemalloc_snapshots.log"
    src.write_text("data", encoding="utf-8")
    monkeypatch.setattr(mod, "_tracemalloc_log_path", lambda: src)

    t = _bare_tester(mod)
    out_dir = tmp_path / "phase_out"
    t.cfg = mod.Config(output_dir=str(out_dir), tracemalloc=False)
    t.stats.restarts = 1

    t._salvage_tracemalloc_log()

    assert not out_dir.exists()


def test_salvage_tracemalloc_log_noop_when_source_missing(monkeypatch, tmp_path):
    mod = _import_monkey()
    missing = tmp_path / "does_not_exist.log"
    monkeypatch.setattr(mod, "_tracemalloc_log_path", lambda: missing)

    t = _bare_tester(mod)
    out_dir = tmp_path / "phase_out"
    t.cfg = mod.Config(output_dir=str(out_dir), tracemalloc=True)
    t.stats.restarts = 1

    t._salvage_tracemalloc_log()   # must not raise

    assert not out_dir.exists()


def test_restart_app_salvages_tracemalloc_before_kill(monkeypatch, tmp_path):
    """_restart_app() must salvage before _kill_stale_netsentinel() runs — the
    kill is what triggers the relaunch that truncates the log."""
    mod = _import_monkey()
    t = _bare_tester(mod)
    out_dir = tmp_path / "phase_out"
    t.cfg = mod.Config(output_dir=str(out_dir), tracemalloc=True, use_source=True, max_restarts=3)
    t._proc = None
    t._win = None
    t._stop = mod.threading.Event()

    call_order = []
    monkeypatch.setattr(t, "_salvage_tracemalloc_log", lambda: call_order.append("salvage"))
    monkeypatch.setattr(t, "_kill_stale_netsentinel", lambda: call_order.append("kill"))
    monkeypatch.setattr(t, "_launch_source", lambda: False)   # short-circuit; relaunch failing is fine here

    t._restart_app()

    assert call_order == ["salvage", "kill"]


# ── ProcDump attach/detach (RULE-DBG2 wiring, 2026-07-31) ─────────────────────

class _FakePopen:
    """Stand-in for subprocess.Popen — no real process is ever spawned."""

    def __init__(self, args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self._poll_result = None   # None = still running, like the real Popen.poll()
        self.terminated = False

    def poll(self):
        return self._poll_result

    def terminate(self):
        self.terminated = True


def test_procdump_path_prefers_shutil_which(monkeypatch):
    mod = _import_monkey()
    t = _bare_tester(mod)
    monkeypatch.setattr(
        mod.shutil, "which",
        lambda name: r"C:\tools\procdump64.exe" if name == "procdump64" else None,
    )
    assert t._procdump_path() == r"C:\tools\procdump64.exe"


def test_procdump_path_falls_back_to_winget_glob(monkeypatch, tmp_path):
    mod = _import_monkey()
    t = _bare_tester(mod)
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)
    pkg_dir = (tmp_path / "AppData/Local/Microsoft/WinGet/Packages"
               / "Microsoft.Sysinternals.Suite_Microsoft.Winget.Source_8wekyb3d8bbwe")
    pkg_dir.mkdir(parents=True)
    exe = pkg_dir / "procdump64.exe"
    exe.write_text("", encoding="utf-8")
    monkeypatch.setattr(mod.Path, "home", classmethod(lambda cls: tmp_path))
    assert t._procdump_path() == str(exe)


def test_procdump_path_returns_none_when_not_found(monkeypatch, tmp_path):
    mod = _import_monkey()
    t = _bare_tester(mod)
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)
    monkeypatch.setattr(mod.Path, "home", classmethod(lambda cls: tmp_path))  # empty — nothing to glob
    assert t._procdump_path() is None


def test_attach_procdump_noop_when_disabled(monkeypatch, tmp_path):
    mod = _import_monkey()
    t = _bare_tester(mod)
    t.cfg = mod.Config(output_dir=str(tmp_path / "out"), procdump=False)
    t._procdump_proc = None
    t._procdump_warned = False

    def _fail_popen(*a, **kw):
        raise AssertionError("Popen must not be called when procdump=False")
    monkeypatch.setattr(mod.subprocess, "Popen", _fail_popen)

    t._attach_procdump(1234)   # must not raise / not spawn anything


def test_attach_procdump_warns_once_when_not_found(monkeypatch, tmp_path):
    mod = _import_monkey()
    t = _bare_tester(mod)
    t.cfg = mod.Config(output_dir=str(tmp_path / "out"), procdump=True)
    t._procdump_proc = None
    t._procdump_warned = False
    monkeypatch.setattr(t, "_procdump_path", lambda: None)

    def _fail_popen(*a, **kw):
        raise AssertionError("Popen must not be called when ProcDump isn't found")
    monkeypatch.setattr(mod.subprocess, "Popen", _fail_popen)

    t._attach_procdump(1234)

    assert t._procdump_warned is True


def test_attach_procdump_spawns_expected_command(monkeypatch, tmp_path):
    mod = _import_monkey()
    t = _bare_tester(mod)
    out_dir = tmp_path / "out"
    t.cfg = mod.Config(output_dir=str(out_dir), procdump=True)
    t._procdump_proc = None
    t._procdump_warned = False
    monkeypatch.setattr(t, "_procdump_path", lambda: r"C:\tools\procdump64.exe")

    captured = {}

    def _fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _FakePopen(args, **kwargs)
    monkeypatch.setattr(mod.subprocess, "Popen", _fake_popen)

    t._attach_procdump(4242)

    dump_dir = out_dir / "dumps"
    assert dump_dir.is_dir()
    # Hang mode (-h), not exception mode (-e 1): _attach_procdump()'s docstring
    # records why the switch was made — -e 1 fired on a benign *handled*
    # pybind11::attribute_error during native-extension startup, which it cannot
    # distinguish from a real fault, while -h targets the actual open bug
    # (hang / high-RSS stalls). This assertion was left on the retired contract.
    assert captured["args"] == [
        r"C:\tools\procdump64.exe", "-accepteula", "-ma", "-h", "-n", "5",
        "4242", str(dump_dir),
    ]
    assert t._procdump_proc is not None


def test_attach_procdump_terminates_previous_instance(monkeypatch, tmp_path):
    """A restart must not accumulate orphaned ProcDump processes from earlier legs."""
    mod = _import_monkey()
    t = _bare_tester(mod)
    t.cfg = mod.Config(output_dir=str(tmp_path / "out"), procdump=True)
    t._procdump_warned = False
    old = _FakePopen([])
    t._procdump_proc = old
    monkeypatch.setattr(t, "_procdump_path", lambda: r"C:\tools\procdump64.exe")
    monkeypatch.setattr(mod.subprocess, "Popen", _FakePopen)

    t._attach_procdump(9999)

    assert old.terminated is True


def test_detach_procdump_terminates_running_instance():
    mod = _import_monkey()
    t = _bare_tester(mod)
    running = _FakePopen([])
    t._procdump_proc = running

    t._detach_procdump()

    assert running.terminated is True
    assert t._procdump_proc is None


def test_detach_procdump_noop_when_already_exited():
    mod = _import_monkey()
    t = _bare_tester(mod)
    exited = _FakePopen([])
    exited._poll_result = 0   # already exited
    t._procdump_proc = exited

    t._detach_procdump()

    assert exited.terminated is False   # already dead — nothing to terminate
    assert t._procdump_proc is None


# --- IFEO GlobalFlag (+ust) preflight -----------------------------------------
# A leftover `gflags /i python.exe +ust` puts a stack trace on every heap
# allocation process-wide: startup 5.8s -> 99s, suite 9min -> 68min, and every
# RSS/timing number collected under it is an artifact. The probe that sets it
# only printed a revert reminder on its success path, so any early exit left it
# armed. These cover the gate that stops a chaos run from starting under it.

def test_coerce_global_flag_parses_hex_string():
    mod = _import_monkey()
    assert mod._coerce_global_flag("0x00001000") == 0x1000


def test_coerce_global_flag_parses_decimal_string():
    mod = _import_monkey()
    assert mod._coerce_global_flag("4096") == 0x1000


def test_coerce_global_flag_parses_dword_int():
    mod = _import_monkey()
    assert mod._coerce_global_flag(4096) == 0x1000


def test_coerce_global_flag_treats_zero_and_garbage_as_clear():
    mod = _import_monkey()
    assert mod._coerce_global_flag("0x00000000") == 0
    assert mod._coerce_global_flag("00000000") == 0
    assert mod._coerce_global_flag("") == 0
    assert mod._coerce_global_flag("nonsense") == 0
    assert mod._coerce_global_flag(None) == 0


def test_ifeo_global_flag_returns_zero_for_absent_image():
    """Unmocked registry read — an image with no IFEO key must read as clear.

    RULE-WIN11 corollary: the mockable half of this helper proves nothing about
    whether the real registry call works, so at least one test must run it.
    """
    mod = _import_monkey()
    assert mod._ifeo_global_flag("definitely-not-a-real-image-xyzzy.exe") == 0


def test_ust_traced_images_reports_only_images_with_the_ust_bit(monkeypatch):
    mod = _import_monkey()
    flags = {"python.exe": 0x1000, "NetSentinel.exe": 0x0, "other.exe": 0x40}
    monkeypatch.setattr(mod, "_ifeo_global_flag", lambda img: flags.get(img, 0))

    traced = mod._ust_traced_images(("python.exe", "NetSentinel.exe", "other.exe"))

    assert [img for img, _ in traced] == ["python.exe"]


def test_preflight_gflags_returns_none_when_clear(monkeypatch):
    mod = _import_monkey()
    monkeypatch.setattr(mod, "_ifeo_global_flag", lambda img: 0)
    assert mod._preflight_gflags(allow_gflags=False) is None


def test_preflight_gflags_aborts_and_names_the_clearing_command(monkeypatch):
    mod = _import_monkey()
    monkeypatch.setattr(mod, "_ifeo_global_flag",
                        lambda img: 0x1000 if img == "python.exe" else 0)

    msg = mod._preflight_gflags(allow_gflags=False)

    assert msg is not None
    assert "python.exe" in msg
    assert "-ust" in msg            # the actual fix, not just a complaint
    assert "--allow-gflags" in msg   # the deliberate-bypass escape hatch


def test_preflight_gflags_respects_explicit_bypass(monkeypatch):
    mod = _import_monkey()
    monkeypatch.setattr(mod, "_ifeo_global_flag", lambda img: 0x1000)
    assert mod._preflight_gflags(allow_gflags=True) is None


def test_preflight_gflags_ignores_unrelated_global_flags(monkeypatch):
    """Only the +ust bit distorts allocation timing — don't block on other flags."""
    mod = _import_monkey()
    monkeypatch.setattr(mod, "_ifeo_global_flag", lambda img: 0x40)
    assert mod._preflight_gflags(allow_gflags=False) is None


# --- soak instrumentation defaults --------------------------------------------

def test_soak_phases_do_not_enable_tracemalloc_by_default():
    """--tracemalloc must be opt-in (-Tracemalloc), never on by default.

    A 2026-08-02 A/B established tracemalloc itself caused the mid-soak hangs
    (0 hangs/0 restarts without it vs 1-2 on every prior run) and its
    per-allocation cost distorts the RSS numbers the soak exists to measure.
    Reverting this default silently costs a whole 4.5h+ run, so pin it.
    """
    ps1 = (TOOLS_ROOT / "run_all_monkey_tests.ps1").read_text(encoding="utf-8")
    assert "$useTracemalloc = $Tracemalloc -and (-not $Store)" in ps1, (
        "run_all_monkey_tests.ps1 must gate --tracemalloc on the -Tracemalloc "
        "switch. An unconditional '$useTracemalloc = -not $Store' turns "
        "allocation profiling back on for every soak phase."
    )
    assert ps1.count('$scriptArgs += "--tracemalloc"') == 1, (
        "more than one place injects --tracemalloc; the -Tracemalloc gate only "
        "covers the soak loop"
    )


def test_tracemalloc_switch_is_declared_and_forwarded():
    """The switch must exist on the harness AND be forwarded by the test.ps1 shim."""
    ps1 = (TOOLS_ROOT / "run_all_monkey_tests.ps1").read_text(encoding="utf-8")
    shim = (TOOLS_ROOT.parent / "test.ps1").read_text(encoding="utf-8")
    assert "[switch]$Tracemalloc" in ps1
    assert "[switch]$Tracemalloc" in shim
    assert "-Tracemalloc:$Tracemalloc" in shim, (
        "test.ps1 declares -Tracemalloc but does not pass it through, so it "
        "would be silently dropped (as -WildOnly already is)"
    )


# ── Restart-reason labelling (2026-08-11 chaos-run report defect) ─────────────

def test_restart_reason_is_threaded_through_not_hardcoded_as_a_crash():
    """A forced restart must be labelled by its real cause, not always "gone".

    The 12.5 h run of 2026-08-11 reported `restart x2` with "Window/process gone
    at iter 2181 — restarting app" and "App exited unexpectedly". Neither
    happened: the app was healthy and a foreign window held the foreground for
    20 consecutive iterations, so the focus escape hatch deliberately restarted
    it. `netsentinel_shutdown.log` had no closeEvent in that window, confirming
    the app never exited on its own — the harness killed it (exit code 15).

    Both messages were emitted unconditionally for any `_run_one() -> False`, so
    a working safety net was reported as a crash. That is not cosmetic: this
    report is what a release decision is read from, and "2 crashes" against a
    release candidate reads as blocking when the truth is "0 crashes".
    """
    mod = _import_monkey()
    src = (TOOLS_ROOT / "monkey_test.py").read_text(encoding="utf-8")

    # The focus escape hatch must record WHY it is forcing a restart.
    assert "_restart_reason" in src, (
        "no restart-reason channel exists; the focus-stuck path is still "
        "indistinguishable from a genuine window loss in the log"
    )
    # And the reporting sites must consume it rather than hardcoding a crash.
    assert 'log.warning(\n                        "[restart] Window/process gone' not in src

    tester = mod.MonkeyTester.__new__(mod.MonkeyTester)
    assert hasattr(tester, "_restart_reason") or "_restart_reason" in src


def test_focus_escape_hatch_sets_a_non_crash_reason():
    """The escape-hatch branch must name itself, so the log can tell the truth."""
    src = (TOOLS_ROOT / "monkey_test.py").read_text(encoding="utf-8")
    hatch = src[src.index("forcing a restart instead of stalling"):]
    # Within the escape hatch's own block, a reason must be recorded before the
    # `return False` that hands control to the restart path.
    upto_return = hatch[: hatch.index("return False")]
    assert "_restart_reason" in upto_return, (
        "the focus escape hatch returns False without recording a reason, so "
        "the restart path cannot distinguish it from a crash"
    )
