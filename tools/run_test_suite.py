"""COMMIT GATE Step 2 runner — proves the suite FINISHED, not just that it exited 0.

RULE-GATE1. `python -m pytest tests/ -q` has two observed failure modes that a
plain exit-code check cannot tell apart from success:

    os._exit(0) mid-run (RULE-TP4-DASH)  -> exit 0, NO summary line   <- invisible
    native abort / double free           -> exit 3, NO summary line
    normal test failure                  -> exit 1, summary present

Only the third is what "the gate failed" normally means. The first is the
dangerous one: it reads as a clean pass and once hid ~60% of the suite for
months. Piping the run through `tail` makes it worse — the shell then sees
*tail's* exit code (always 0), and the `Fatal Python error` block that would
explain the death is discarded with the rest of the scrollback.

So this runner gates on three independent conditions instead of one:

    1. a real pytest summary line exists   (proves the session reached the end)
    2. failed/error counts are zero        (proves the tests actually passed)
    3. the process exit code is 0          (catches everything else)

It fails CLOSED: output it cannot parse is a failure, never a pass. Every
failure prints which condition broke, what that means mechanically, and the
path to the full untruncated log.

Usage:
    python tools/run_test_suite.py              # run the suite and gate on it
    python tools/run_test_suite.py --check-file LOG   # classify an existing log
    python tools/run_test_suite.py -- -x -k foo       # extra args go to pytest
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_LOG = _REPO_ROOT / "pytest_suite_output.log"

# pytest's end-of-session counts, e.g. "6224 passed, 5 skipped in 525.30s".
# These are only ever printed if the session actually reached the end.
_COUNT_RE = re.compile(
    r"(\d+)\s+(passed|failed|errors?|xpassed|xfailed|skipped|deselected)\b"
)
# pytest exits 5 when it collected nothing. That is not a pass either.
_NO_TESTS_RE = re.compile(r"no tests ran", re.IGNORECASE)
# Written by faulthandler on a native abort (double free, SEH, os.abort()).
_FATAL_RE = re.compile(r"Fatal Python error:.*", re.IGNORECASE)

# Verdicts. PASS is the only one that exits 0.
PASS = "PASS"
FAIL_TESTS = "FAIL_TESTS"
FAIL_TRUNCATED_SILENT = "FAIL_TRUNCATED_SILENT"
FAIL_TRUNCATED_CRASH = "FAIL_TRUNCATED_CRASH"
FAIL_TRUNCATED = "FAIL_TRUNCATED"
FAIL_NO_TESTS = "FAIL_NO_TESTS"
FAIL_EXIT_CODE = "FAIL_EXIT_CODE"


@dataclass
class Verdict:
    """Classification of one pytest run. `ok` gates the process exit code."""

    verdict: str
    ok: bool
    headline: str
    mechanism: str
    next_step: str
    counts: dict[str, int] = field(default_factory=dict)

    def render(self, log_path: Path | None = None, excerpt: str = "") -> str:
        """Human- and agent-readable diagnosis. Never truncates the mechanism."""
        mark = "PASS" if self.ok else "FAIL"
        lines = [
            "",
            "=" * 72,
            f"[{mark}] COMMIT GATE Step 2 — {self.verdict}",
            "=" * 72,
            f"  What happened : {self.headline}",
            f"  Why it matters: {self.mechanism}",
            f"  Next step     : {self.next_step}",
        ]
        if self.counts:
            rendered = ", ".join(f"{v} {k}" for k, v in sorted(self.counts.items()))
            lines.append(f"  Reported      : {rendered}")
        if log_path is not None:
            lines.append(f"  Full log      : {log_path}")
        if excerpt:
            lines += ["", "  ---- relevant output ----"]
            lines += [f"  {ln}" for ln in excerpt.splitlines()]
        lines.append("=" * 72)
        return "\n".join(lines)


def parse_counts(output: str) -> dict[str, int]:
    """Extract pytest's summary counts. Empty dict means no summary was found."""
    counts: dict[str, int] = {}
    for num, word in _COUNT_RE.findall(output):
        key = "error" if word.startswith("error") else word
        counts[key] = counts.get(key, 0) + int(num)
    return counts


def classify(output: str, exit_code: int) -> Verdict:
    """Map (pytest output, exit code) onto a verdict. Pure — no I/O.

    Fails closed: anything not positively recognised as a finished, clean
    session is a failure.
    """
    counts = parse_counts(output)
    # A summary is only meaningful if it reports an actual test OUTCOME. A run
    # that printed "5 skipped" and died still has no proof it finished.
    has_outcome = any(k in counts for k in ("passed", "failed", "error"))
    crashed = bool(_FATAL_RE.search(output))

    if not has_outcome:
        if _NO_TESTS_RE.search(output):
            return Verdict(
                FAIL_NO_TESTS, False,
                "pytest collected and ran zero tests.",
                "An empty run trivially has no failures, so it would pass any "
                "exit-code check while proving nothing about the code.",
                "Check the path/-k/-m arguments — the gate must run tests/ with "
                "the pyproject addopts markers intact.",
                counts,
            )
        if crashed:
            return Verdict(
                FAIL_TRUNCATED_CRASH, False,
                "The suite died mid-run with a native fault — no summary line.",
                "A double free or SEH fault aborts the interpreter. Output stops "
                "wherever it got to, so the tests after that point NEVER RAN and "
                "their state is unknown. Crash position drifts between runs, so "
                "one clean re-run is not proof the bug is gone.",
                "Read the 'Fatal Python error' block below for the faulting "
                "frame. Suspect Qt object double-ownership first (RULE-WIN4/WIN8: "
                "a widget deleted by both its C++ parent and conftest's "
                "_flush_qt_events sweep).",
                counts,
            )
        if exit_code == 0:
            return Verdict(
                FAIL_TRUNCATED_SILENT, False,
                "The suite exited 0 but never printed a summary line — it was "
                "killed mid-run and only LOOKS like a pass.",
                "This is the RULE-TP4-DASH mask: os._exit(0) inside "
                "Dashboard.closeEvent() terminates the pytest process itself "
                "with code 0. No summary, no session-finish, and every test "
                "after that point silently never ran. This exact mode hid ~60% "
                "of the suite from commit 6d52b36 until mid-2026.",
                "Find the test that constructs a real Dashboard in-process and "
                "move it into a subprocess child (tests/_lazy_pages_child.py is "
                "the pattern). `pytest tests/test_suite_completes.py` names it.",
                counts,
            )
        return Verdict(
            FAIL_TRUNCATED, False,
            f"No pytest summary line, and the process exited {exit_code}.",
            "Without a summary the session did not reach the end, so an unknown "
            "number of tests never ran. Absence of reported failures is not "
            "evidence of success.",
            "Read the tail of the full log below — the process was terminated "
            "by something outside pytest (OOM, an external kill, a hard timeout).",
            counts,
        )

    failed = counts.get("failed", 0)
    errors = counts.get("error", 0)
    if failed or errors:
        return Verdict(
            FAIL_TESTS, False,
            f"The suite finished and reported {failed} failed, {errors} error(s).",
            "This is an ordinary red suite — the session completed, so the "
            "counts are trustworthy.",
            "Fix the failing tests. Per the commit gate, 'pre-existing / not my "
            "diff' does not clear a red test; re-run the gate from Step 1 after "
            "any code change.",
            counts,
        )

    if exit_code != 0:
        return Verdict(
            FAIL_EXIT_CODE, False,
            f"Summary reports no failures, but pytest exited {exit_code}.",
            "The session finished and the tests passed, so the nonzero code came "
            "from pytest itself — a plugin error, an internal error, or a "
            "teardown fault after the last test reported.",
            "Read the tail of the full log. Do not treat this as a pass: a "
            "teardown-time crash here is the same object-lifetime bug class that "
            "aborts the suite outright on a different run.",
            counts,
        )

    return Verdict(
        PASS, True,
        f"Suite completed cleanly: {counts.get('passed', 0)} passed.",
        "A summary line was present, failure counts were zero, and the exit "
        "code was 0 — all three gate conditions held.",
        "Proceed to COMMIT GATE Step 3 (python tools/debug_launch.py).",
        counts,
    )


def excerpt_for(verdict: Verdict, output: str, tail_lines: int = 25) -> str:
    """Pick the output slice that explains this verdict."""
    if verdict.verdict == FAIL_TRUNCATED_CRASH:
        idx = output.find("Fatal Python error")
        if idx != -1:
            # The faulting frame is the first thing after the banner; 30 lines
            # covers the Python stack without dumping every thread.
            return "\n".join(output[idx:].splitlines()[:30])
    if verdict.ok:
        return ""
    return "\n".join(output.splitlines()[-tail_lines:])


def run_pytest(extra_args: list[str], log_path: Path) -> tuple[str, int]:
    """Run the suite, streaming output to both the console and `log_path`.

    Streaming matters: the full run takes ~9 minutes, and a silent terminal is
    indistinguishable from a hang.
    """
    cmd = [sys.executable, "-m", "pytest", "tests/", "-q", *extra_args]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    print(f"$ {' '.join(cmd)}\n", flush=True)

    chunks: list[str] = []
    with subprocess.Popen(
        cmd,
        cwd=str(_REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        # Runtime output, not source — a decode error here must not mask the
        # crash we are trying to report (contrast RULE-ENC1, which forbids
        # errors='replace' when READING source files).
        errors="replace",
        bufsize=1,
    ) as proc:
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            chunks.append(line)
        code = proc.wait()

    output = "".join(chunks)
    log_path.write_text(output, encoding="utf-8")
    return output, code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the test suite and gate on real completion (RULE-GATE1).",
    )
    parser.add_argument(
        "--check-file",
        metavar="LOG",
        help="Classify an existing pytest log instead of running the suite.",
    )
    parser.add_argument(
        "--exit-code",
        type=int,
        default=0,
        help="Exit code that produced --check-file's log (default 0).",
    )
    parser.add_argument(
        "--log",
        default=str(_DEFAULT_LOG),
        help=f"Where to write the full run log (default {_DEFAULT_LOG.name}).",
    )
    parser.add_argument(
        "pytest_args",
        nargs="*",
        help="Extra arguments forwarded to pytest (after --).",
    )
    args = parser.parse_args(argv)

    if args.check_file:
        log_path = Path(args.check_file)
        output = log_path.read_text(encoding="utf-8", errors="replace")
        code = args.exit_code
    else:
        log_path = Path(args.log)
        output, code = run_pytest(args.pytest_args, log_path)

    verdict = classify(output, code)
    print(verdict.render(log_path, excerpt_for(verdict, output)), flush=True)
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
