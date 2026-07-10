"""Meta-test: the pytest suite must run to completion, not silently truncate.

Regression guard for the os._exit(0) test-suite mask (RULE-T3).

Background: `tests/test_lazy_pages.py` constructs a real Dashboard(store=None).
The autouse `_flush_qt_events` fixture (conftest.py) then calls `w.close()` on it,
which reaches `Dashboard.closeEvent()` -> `os._exit(0)` (ui/dashboard.py) and exits
the *pytest process itself* with code 0 — no summary line, no session-finish. From
commit 6d52b36 until this guard, the back ~60% of the suite silently never ran and
CI was falsely green.

`os._exit(0)` in closeEvent is load-bearing on Windows (a fully-constructed Dashboard
cannot be created-and-destroyed in-process without a Qt/QThread teardown crash), so
the fix is to run every Dashboard-constructing test in a subprocess child instead of
patching production teardown. This test proves the mask is gone: a subprocess pytest
run of test_lazy_pages.py must reach a real summary line and report a result for every
collected test.

See project_test_suite_osexit_mask memory.
"""

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TARGET = "tests/test_lazy_pages.py"
_UTF8_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}

# pytest end-of-session summary counts, e.g. "5 passed in 0.4s" or
# "3 passed, 2 failed in 0.4s". These only appear if the session finished.
_COUNT_RE = re.compile(r"(\d+)\s+(passed|failed|error|errors|xpassed)\b")


def _run_pytest(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *args],
        capture_output=True,
        text=True,
        env=_UTF8_ENV,
        cwd=str(_REPO_ROOT),
        timeout=300,
    )


def _collected_count() -> int:
    """Number of tests pytest collects from the target file (collection only
    imports the module — it does not construct a Dashboard, so it is safe)."""
    res = _run_pytest(["--collect-only", "-q", _TARGET])
    m = re.search(r"(\d+)\s+tests?\s+collected", res.stdout)
    if m:
        return int(m.group(1))
    # Fallback: count node-id lines in -q collect output.
    return sum(1 for ln in res.stdout.splitlines() if "::test_" in ln)


def test_lazy_pages_run_reaches_summary():
    """Running test_lazy_pages.py as a subprocess must reach a real pytest
    summary line — proving os._exit(0) no longer terminates the session."""
    res = _run_pytest(["-q", _TARGET])
    combined = res.stdout + res.stderr
    assert _COUNT_RE.search(combined), (
        "No pytest summary line found — the run truncated before session finish "
        "(os._exit(0) mask regression). Output was:\n" + combined
    )


def test_lazy_pages_every_collected_test_reports_a_result():
    """Every collected test must be accounted for in the summary counts. If the
    suite truncates mid-file, the reported total is less than the collected count."""
    expected = _collected_count()
    assert expected > 0, "collection returned zero tests — cannot validate completion"

    res = _run_pytest(["-q", _TARGET])
    combined = res.stdout + res.stderr
    reported = sum(int(n) for n, _ in _COUNT_RE.findall(combined))
    assert reported == expected, (
        f"Only {reported} of {expected} collected tests reported a result — the "
        f"suite truncated (os._exit(0) mask regression). Output was:\n" + combined
    )


# ── RULE-TP4-DASH enforcement: no pytest-collected test may build a Dashboard ──

_TESTS_DIR = Path(__file__).resolve().parent


def _constructs_dashboard(src: str) -> bool:
    """True if the source contains a `Dashboard(...)` construction call."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else (
                fn.attr if isinstance(fn, ast.Attribute) else None
            )
            if name == "Dashboard":
                return True
    return False


def test_no_collected_test_constructs_dashboard_in_process():
    """RULE-TP4-DASH: a real Dashboard reaches closeEvent -> os._exit(0) and silently
    terminates the pytest session. Any Dashboard-constructing test must run in a
    subprocess child (see tests/_lazy_pages_child.py, which is not a test_*.py file and
    so is not collected). This guard fails if a collected test file constructs one."""
    offenders = [
        f.name
        for f in sorted(_TESTS_DIR.glob("test_*.py"))
        if _constructs_dashboard(f.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        "These pytest-collected test files construct a real Dashboard in-process, which "
        "hits closeEvent -> os._exit(0) and silently terminates the whole suite "
        f"(RULE-TP4-DASH): {offenders}. Move the Dashboard construction into a subprocess "
        "child like tests/_lazy_pages_child.py."
    )
