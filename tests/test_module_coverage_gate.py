"""S9-4: CI gate — every file in modules/ must have a corresponding test file.

When this test fails, add tests/test_<name>.py for the listed module(s).
Do NOT add to EXEMPT unless the module is a stub, re-export, or schema fragment
that is already covered by another test file (document the reason).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES_ROOT = ROOT / "modules"
TESTS_ROOT = ROOT / "tests"

# Modules that are covered by a differently-named test file or are re-export stubs.
# Add entries ONLY with a documented reason — never to silence a real gap.
EXEMPT: set[str] = {
    # Split fragments re-exported by metric_store.py; covered by test_metric_store.py
    "metric_store_schema",
    "metric_store_queries",
    # E3 split: uptime and metrics sub-mixins; covered by test_metric_store_queries_split.py
    "metric_store_queries_uptime",
    "metric_store_queries_metrics",
    # Split fragments re-exported by report_exporter.py; covered by test_report_exporter.py
    # report_html has its own test; report_pdf now has test_report_pdf.py
    "report_html",
}


def test_every_module_has_a_test_file():
    """Every modules/*.py must have a tests/test_<name>.py (RULE-T1).

    This gate prevents new modules from accruing without test coverage.
    When you add a module, add the test file in the same commit.
    """
    modules = {
        p.stem
        for p in MODULES_ROOT.glob("*.py")
        if not p.stem.startswith("_")
    }
    tests = {
        p.stem.removeprefix("test_")
        for p in TESTS_ROOT.glob("test_*.py")
    }
    missing = modules - tests - EXEMPT
    assert not missing, (
        "Modules missing a test file (RULE-T1 violation):\n"
        + "\n".join(f"  modules/{m}.py  →  add tests/test_{m}.py" for m in sorted(missing))
        + "\n\nAdd a test file for each listed module. "
        "See .claude/rules/tests.instructions.md for test conventions. "
        "Only add to EXEMPT if the module is a documented re-export stub."
    )


def test_exempt_list_contains_no_phantom_entries():
    """Every EXEMPT entry must name a real module file.

    Catches typos and stale entries when modules are renamed or deleted.
    """
    stale = [name for name in EXEMPT if not (MODULES_ROOT / f"{name}.py").exists()]
    assert not stale, (
        "Stale EXEMPT entries (module file no longer exists):\n"
        + "\n".join(f"  {name}" for name in sorted(stale))
        + "\n\nRemove these entries from EXEMPT in test_module_coverage_gate.py."
    )
