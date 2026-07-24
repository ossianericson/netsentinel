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
