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
