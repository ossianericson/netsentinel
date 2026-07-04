"""Tests for tools/scan_navigate_test.py — import, whitelist safety, CLI wiring.

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


def _import_scan_navigate():
    """Import scan_navigate_test without executing main()."""
    if "scan_navigate_test" in sys.modules:
        return sys.modules["scan_navigate_test"]
    spec = importlib.util.spec_from_file_location(
        "scan_navigate_test", TOOLS_ROOT / "scan_navigate_test.py"
    )
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except ImportError as exc:
        pytest.skip(f"scan_navigate_test dependency missing: {exc}")
    sys.modules["scan_navigate_test"] = mod
    return mod


def test_import():
    mod = _import_scan_navigate()
    assert hasattr(mod, "ScanNavigateTester")
    assert hasattr(mod, "ScanNavConfig")


def test_subclasses_monkey_tester():
    mod = _import_scan_navigate()
    assert issubclass(mod.ScanNavigateTester, mod._mt.MonkeyTester)


def test_scan_targets_well_formed():
    mod = _import_scan_navigate()
    assert len(mod._SCAN_TARGETS) >= 5
    for target in mod._SCAN_TARGETS:
        assert isinstance(target["page"], str) and target["page"]
        assert isinstance(target["buttons"], list) and target["buttons"]
        for label in target["buttons"]:
            assert isinstance(label, str) and label


def test_scan_targets_exclude_credentialed_and_lockout_risk():
    """Login Test (credentialed_scan) can lock real accounts on repeated
    automated runs — it must never appear in the whitelist."""
    mod = _import_scan_navigate()
    pages = {t["page"] for t in mod._SCAN_TARGETS}
    assert "Login Test" not in pages
    all_buttons = " ".join(b for t in mod._SCAN_TARGETS for b in t["buttons"]).lower()
    assert "credential" not in all_buttons


def test_scan_targets_exclude_tls_exposure_no_repeatable_trigger():
    """TLS & Exposure's only button is an EmptyStateCard CTA that disappears
    after the first host is added — not a safe repeatable click target."""
    mod = _import_scan_navigate()
    pages = {t["page"] for t in mod._SCAN_TARGETS}
    assert "TLS & Exposure" not in pages


def test_away_pages_reuses_monkey_test_safe_list():
    mod = _import_scan_navigate()
    assert mod._AWAY_PAGES == list(mod._mt._SAFE_PAGES)


def test_pick_away_page_excludes_current(tmp_path):
    mod = _import_scan_navigate()
    cfg = mod.ScanNavConfig(seed=1, output_dir=str(tmp_path))
    tester = mod.ScanNavigateTester(cfg)
    for _ in range(20):
        away = tester._pick_away_page("Home")
        assert away != "Home"


def test_config_defaults():
    mod = _import_scan_navigate()
    cfg = mod.ScanNavConfig()
    assert cfg.iterations == 60
    assert cfg.interrupt_delay_min == 1.0
    assert cfg.interrupt_delay_max == 6.0
    assert cfg.settle_delay_min == 2.0
    assert cfg.settle_delay_max == 6.0


def test_cli_help():
    result = subprocess.run(
        [sys.executable, str(TOOLS_ROOT / "scan_navigate_test.py"), "--help"],
        capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "--interrupt-delay-min" in combined
    assert "--settle-delay-min" in combined
