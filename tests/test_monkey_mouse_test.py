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
    assert cfg.header_bias == 0.25


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


def test_cli_help():
    result = subprocess.run(
        [sys.executable, str(TOOLS_ROOT / "monkey_mouse_test.py"), "--help"],
        capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "--header-bias" in combined
    assert "--drag-prob" in combined
