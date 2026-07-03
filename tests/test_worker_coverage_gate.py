"""G13: CI gate — every file in workers/ must have a corresponding test file.

Mirrors test_module_coverage_gate.py (RULE-T1) for the workers/ package, which
was previously excluded from any coverage gate — new workers could ship with
no lifecycle or error-path test and nothing would catch it.

When this test fails, add tests/test_<name>.py for the listed worker(s).
Do NOT add to EXEMPT unless the module is a stub or re-export already covered
by another test file (document the reason).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKERS_ROOT = ROOT / "workers"
TESTS_ROOT = ROOT / "tests"

# Workers covered by a differently-named test file or that are re-export stubs.
# Add entries ONLY with a documented reason — never to silence a real gap.
EXEMPT: set[str] = set()


def test_every_worker_has_a_test_file():
    """Every workers/*.py must have a tests/test_<name>.py (RULE-T1/RULE-T2).

    This gate prevents new workers from accruing without lifecycle or
    error-path coverage. Add the test file in the same commit as the worker.
    """
    workers = {
        p.stem
        for p in WORKERS_ROOT.glob("*.py")
        if not p.stem.startswith("_")
    }
    tests = {
        p.stem.removeprefix("test_")
        for p in TESTS_ROOT.glob("test_*.py")
    }
    missing = workers - tests - EXEMPT
    assert not missing, (
        "Workers missing a test file (RULE-T1/RULE-T2 violation):\n"
        + "\n".join(f"  workers/{m}.py  →  add tests/test_{m}.py" for m in sorted(missing))
        + "\n\nAdd a test file for each listed worker. "
        "See .claude/rules/tests.instructions.md for test conventions. "
        "Only add to EXEMPT if the worker is a documented re-export stub."
    )


def test_exempt_list_contains_no_phantom_entries():
    """Every EXEMPT entry must name a real worker file.

    Catches typos and stale entries when workers are renamed or deleted.
    """
    stale = [name for name in EXEMPT if not (WORKERS_ROOT / f"{name}.py").exists()]
    assert not stale, (
        "Stale EXEMPT entries (worker file no longer exists):\n"
        + "\n".join(f"  {name}" for name in sorted(stale))
        + "\n\nRemove these entries from EXEMPT in test_worker_coverage_gate.py."
    )
