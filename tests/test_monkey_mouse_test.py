"""Tests for tools/monkey_mouse_test.py — import, dataclass construction, zone logic.

Run locally only:
    python -m pytest -m monkey

Never runs in CI (excluded by addopts in pyproject.toml).
"""
import importlib
import sys
import subprocess
from collections import namedtuple
from pathlib import Path

import pytest

TOOLS_ROOT = Path(__file__).parent.parent / "tools"

pytestmark = pytest.mark.monkey

_FakeRect = namedtuple("_FakeRect", ["left", "top", "right", "bottom"])


def _import_monkey_mouse():
    """Import monkey_mouse_test without executing main()."""
    if "monkey_mouse_test" in sys.modules:
        return sys.modules["monkey_mouse_test"]
    spec = importlib.util.spec_from_file_location(
        "monkey_mouse_test", TOOLS_ROOT / "monkey_mouse_test.py"
    )
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except ImportError as exc:
        pytest.skip(f"monkey_mouse_test dependency missing: {exc}")
    sys.modules["monkey_mouse_test"] = mod
    return mod


def test_import():
    mod = _import_monkey_mouse()
    assert hasattr(mod, "MouseMonkeyTester")
    assert hasattr(mod, "MouseConfig")


def test_subclasses_monkey_tester():
    mod = _import_monkey_mouse()
    assert issubclass(mod.MouseMonkeyTester, mod._mt.MonkeyTester)


def test_config_defaults():
    mod = _import_monkey_mouse()
    cfg = mod.MouseConfig()
    # Inherited defaults from monkey_test.Config still apply
    assert cfg.iterations == 200
    assert cfg.chaos == "moderate"
    # New mouse-specific fields
    assert cfg.drag_prob == 0.12
    assert cfg.scroll_prob == 0.20
    assert cfg.right_click_prob == 0.08
    assert cfg.double_click_prob == 0.08
    assert cfg.header_bias == 0.15
    assert cfg.start_page == "Home"
    assert cfg.page_switch_every == 12


def test_config_custom():
    mod = _import_monkey_mouse()
    cfg = mod.MouseConfig(iterations=10, chaos="wild", header_bias=0.5)
    assert cfg.iterations == 10
    assert cfg.chaos == "wild"
    assert cfg.header_bias == 0.5


def test_rect_contains():
    mod = _import_monkey_mouse()
    r = _FakeRect(left=0, top=0, right=100, bottom=50)
    assert mod._rect_contains(r, 50, 25)
    assert not mod._rect_contains(r, 500, 500)
    # padding extends the boundary
    assert mod._rect_contains(r, 105, 25, pad=10)
    assert not mod._rect_contains(r, 105, 25, pad=2)


def test_header_types_excludes_generic_button():
    mod = _import_monkey_mouse()
    assert "Header" in mod._HEADER_TYPES
    assert "HeaderItem" in mod._HEADER_TYPES
    assert "Button" not in mod._HEADER_TYPES


def test_page_pool_includes_devices_and_safe_pages():
    mod = _import_monkey_mouse()
    assert "Devices" in mod._PAGE_POOL
    assert "Home" in mod._PAGE_POOL
    assert "Overview" in mod._PAGE_POOL
    # every entry from monkey_test's vetted read-only list must carry over
    assert set(mod._mt._SAFE_PAGES).issubset(set(mod._PAGE_POOL))


def test_tester_init_arms_start_page_flag(tmp_path):
    """__init__ never launches anything (that's run()'s job), so it's safe
    to instantiate directly and check the deterministic-start-page state."""
    mod = _import_monkey_mouse()
    cfg = mod.MouseConfig(seed=1, output_dir=str(tmp_path))
    tester = mod.MouseMonkeyTester(cfg)
    assert tester._start_page_done is False
    assert tester._last_page_switch == 0


def test_dismiss_startup_overlays_rearms_start_page_flag(tmp_path, monkeypatch):
    """_dismiss_startup_overlays runs on both initial startup AND every
    auto-restart (inherited from MonkeyTester) — it must re-arm the flag
    both times so a restarted app also gets navigated back to start_page."""
    mod = _import_monkey_mouse()
    cfg = mod.MouseConfig(seed=1, output_dir=str(tmp_path))
    tester = mod.MouseMonkeyTester(cfg)
    tester._start_page_done = True
    monkeypatch.setattr(mod._mt.MonkeyTester, "_dismiss_startup_overlays", lambda self: None)
    tester._dismiss_startup_overlays()
    assert tester._start_page_done is False


def test_cli_help():
    result = subprocess.run(
        [sys.executable, str(TOOLS_ROOT / "monkey_mouse_test.py"), "--help"],
        capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "--header-bias" in combined
    assert "--drag-prob" in combined
    assert "--start-page" in combined
    assert "--page-switch-every" in combined
