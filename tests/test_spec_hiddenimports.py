"""S12-3: CI gate — every modules/*.py file must appear in NetSentinel.spec hiddenimports.

A module missing from hiddenimports passes all source-run tests but raises
ModuleNotFoundError in production (PyInstaller onefile build). This test
catches the gap before the build step.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "NetSentinel.spec"

# Modules intentionally omitted from the build (init files, etc.)
_SKIP = {"__init__"}


def test_all_modules_in_spec_hiddenimports() -> None:
    if not SPEC_PATH.exists():
        return  # spec not present in source-only CI environments
    spec_text = SPEC_PATH.read_text(encoding="utf-8")
    missing = []
    for path in sorted((ROOT / "modules").glob("*.py")):
        if path.stem in _SKIP or path.stem.startswith("_"):
            continue
        key = f'"modules.{path.stem}"'
        if key not in spec_text:
            missing.append(key)
    assert not missing, (
        f"Add these to hiddenimports in NetSentinel.spec (RULE-B1): {missing}"
    )


def test_no_duplicate_hiddenimports() -> None:
    if not SPEC_PATH.exists():
        return
    spec_text = SPEC_PATH.read_text(encoding="utf-8")
    seen: dict[str, int] = {}
    duplicates = []
    for line in spec_text.splitlines():
        stripped = line.strip().rstrip(",")
        if stripped.startswith('"') and stripped.endswith('"'):
            entry = stripped.strip('"')
            if entry:
                seen[entry] = seen.get(entry, 0) + 1
    duplicates = [k for k, v in seen.items() if v > 1]
    assert not duplicates, (
        f"Duplicate hiddenimports in NetSentinel.spec (remove extras): {duplicates}"
    )
