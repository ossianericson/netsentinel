"""RULE-GATE1: the commit gate must prove the suite FINISHED, not just exited 0.

These feed canned pytest output to `tools/run_test_suite.py::classify()` so the
five failure modes are covered in milliseconds instead of a ~9-minute real run.

The two truncation samples are not invented — they were reproduced live against
this repo's pytest before this file was written:

    os._exit(0) in a test  -> exit 0, output stops after the progress dots
    os.abort()  in a test  -> exit 3, output ends in a Fatal Python error block

The first is the one that matters: it is indistinguishable from success by exit
code alone, which is exactly the hole this gate closes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_MODULE_PATH = _REPO_ROOT / "tools" / "run_test_suite.py"


def _load():
    """Import tools/run_test_suite.py by path — tools/ is not a package."""
    spec = importlib.util.spec_from_file_location("run_test_suite", _MODULE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_test_suite"] = mod
    spec.loader.exec_module(mod)
    return mod


rts = _load()


# --- canned outputs ---------------------------------------------------------

CLEAN = "......................\n6224 passed, 5 skipped in 525.30s (0:08:45)\n"

FAILED = (
    "....F.....F...........\n"
    "FAILED tests/test_a.py::test_one - AssertionError\n"
    "2 failed, 6222 passed, 5 skipped in 530.11s\n"
)

ERRORED = "....E.....\n1 error, 10 passed in 12.00s\n"

# Reproduced live: pytest -q with a test calling os._exit(0). Progress dots,
# then nothing. Exit code 0.
TRUNCATED_SILENT = ".." + "." * 50 + "\n"

# Reproduced live: pytest -q with a test calling os.abort(). Exit code 3.
TRUNCATED_CRASH = (
    "..\n"
    "Fatal Python error: Aborted\n"
    "\n"
    "Current thread 0x00004cb0 (most recent call first):\n"
    '  File "tests/test_zz.py", line 3 in test_boom\n'
    '  File "_pytest/python.py", line 167 in pytest_pyfunc_call\n'
)

NO_TESTS = "no tests ran in 0.31s\n"


# --- the load-bearing case --------------------------------------------------

def test_silent_truncation_at_exit_zero_is_a_failure():
    """The whole reason this runner exists.

    An exit-code check passes this output. It is a truncated run.
    """
    v = rts.classify(TRUNCATED_SILENT, 0)
    assert not v.ok
    assert v.verdict == rts.FAIL_TRUNCATED_SILENT


def test_silent_truncation_diagnosis_names_the_mechanism_and_the_fix():
    """Fail-closed is only useful if the message says what to do next."""
    v = rts.classify(TRUNCATED_SILENT, 0)
    text = v.render(Path("pytest_suite_output.log"), "")
    assert "os._exit(0)" in text
    assert "RULE-TP4-DASH" in text
    assert "subprocess" in text
    assert "test_suite_completes.py" in text
    # The verdict must not be reported as a pass anywhere in the rendering.
    assert "[FAIL]" in text and "[PASS]" not in text


# --- the other modes --------------------------------------------------------

def test_clean_run_passes():
    v = rts.classify(CLEAN, 0)
    assert v.ok
    assert v.verdict == rts.PASS
    assert v.counts["passed"] == 6224


def test_native_abort_is_distinguished_from_the_silent_mask():
    """Both truncate, but they need different fixes — so different verdicts."""
    v = rts.classify(TRUNCATED_CRASH, 3)
    assert not v.ok
    assert v.verdict == rts.FAIL_TRUNCATED_CRASH
    text = v.render(None, "")
    assert "double free" in text or "SEH" in text
    assert "NEVER RAN" in text


def test_native_abort_excerpt_carries_the_faulting_frame():
    """A `| tail` pipeline throws this block away; the runner must keep it."""
    v = rts.classify(TRUNCATED_CRASH, 3)
    excerpt = rts.excerpt_for(v, TRUNCATED_CRASH)
    assert "Fatal Python error" in excerpt
    assert "test_boom" in excerpt


@pytest.mark.parametrize("output", [FAILED, ERRORED])
def test_ordinary_red_suite_is_reported_as_a_test_failure(output: str):
    """A finished-but-red run must NOT be confused with a truncated one."""
    v = rts.classify(output, 1)
    assert not v.ok
    assert v.verdict == rts.FAIL_TESTS


def test_zero_collected_tests_is_not_a_pass():
    v = rts.classify(NO_TESTS, 5)
    assert not v.ok
    assert v.verdict == rts.FAIL_NO_TESTS


def test_clean_summary_with_nonzero_exit_is_not_a_pass():
    """Teardown faults land here — the same lifetime bug class as an abort."""
    v = rts.classify(CLEAN, 1)
    assert not v.ok
    assert v.verdict == rts.FAIL_EXIT_CODE


# --- fail-closed ------------------------------------------------------------

@pytest.mark.parametrize(
    "junk",
    ["", "   \n\n", "ImportError while loading conftest\n", "5 skipped in 1.0s\n"],
)
def test_unparseable_output_fails_closed(junk: str):
    """Anything not positively recognised as finished-and-clean must fail.

    The last case is deliberate: a run reporting only skips has no test OUTCOME,
    so it is not evidence the session reached the end.
    """
    assert not rts.classify(junk, 0).ok


def test_counts_parse_across_summary_shapes():
    assert rts.parse_counts(CLEAN) == {"passed": 6224, "skipped": 5}
    assert rts.parse_counts(ERRORED) == {"error": 1, "passed": 10}
    assert rts.parse_counts("") == {}


def test_only_pass_verdict_maps_to_exit_zero(tmp_path: Path):
    """End-to-end through main(), which is what the commit gate actually runs."""
    log = tmp_path / "canned.log"

    log.write_text(CLEAN, encoding="utf-8")
    assert rts.main(["--check-file", str(log), "--exit-code", "0"]) == 0

    log.write_text(TRUNCATED_SILENT, encoding="utf-8")
    assert rts.main(["--check-file", str(log), "--exit-code", "0"]) == 1
