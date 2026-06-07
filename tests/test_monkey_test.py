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
    assert cfg.mem_limit_mb == 800


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
