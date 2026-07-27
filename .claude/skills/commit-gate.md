---
name: commit-gate
description: >
  Run the 5-step NetSentinel commit gate before any commit or push.
  Invoke whenever the user says "commit", "push", "let's commit", "ready to commit",
  "commit to repo", "push to repo", or any variation. Also invoke proactively before
  issuing any git commit or git push command. This is a BLOCKING requirement —
  no code reaches the repo without all 5 steps passing.
role: worker
user-invocable: true
---

# NetSentinel Commit Gate

## Iron Law

**No commit, push, or tag until all 5 steps pass.** Steps 1, 3, and 5 are hard gates — they block
forward progress. Steps 2 and 4 require human confirmation before proceeding.

---

## Step 1 — Linters + static analysis (HARD GATE)

Run all three. All must exit 0.

```powershell
ruff check . --select=F401,F811,F841
python -m mypy modules/
pip-audit -r requirements.txt --desc
```

**Critical:** Run `ruff` as the direct CLI (`ruff check .`), NOT `python -m ruff`. The installed
CLI is on the PATH; `python -m ruff` can pick up the wrong interpreter.

### Fix guidance

| Tool | Failure | Fix |
|---|---|---|
| `ruff` F401/F811 | Unused import | Remove the name, or add `# noqa: F401` with a comment explaining the re-export |
| `ruff` F841 | Unused local variable | Remove the assignment |
| `mypy` | Type error in `modules/` | Add `ignore_errors = True` under `[mypy-modules.<name>]` in `mypy.ini` for Windows-only APIs (`winreg`, `ctypes.windll`, `CREATE_NO_WINDOW`) |
| `pip-audit` | Known CVE | Update the affected package in `requirements.txt`; re-run to confirm resolved |

**Hard gate:** Do not proceed to Step 2 until all three exit 0.

---

## Step 2 — Full test suite (HARD GATE)

```powershell
python tools/run_test_suite.py
```

Takes ~9 minutes. It runs `pytest tests/ -q`, streams output live, tees the full log to
`pytest_suite_output.log`, and prints a verdict block. **Proceed only on `[PASS]`.**

**Never run bare `pytest | tail` for this step (RULE-GATE1).** A pipe returns *tail's* exit
code, so the shell reports 0 no matter what pytest did, and it discards the `Fatal Python
error` block that explains a crash. The runner exists because two real failure modes print
no summary line at all:

| Mode | Exit code | Verdict |
|---|---|---|
| `os._exit(0)` mid-run (RULE-TP4-DASH) | **0** — looks like success | `FAIL_TRUNCATED_SILENT` |
| Native abort / double free | 3 | `FAIL_TRUNCATED_CRASH` |
| Ordinary red suite | 1 | `FAIL_TESTS` |

The runner fails **closed**: unparseable output is a failure, never a pass. Each verdict names
the mechanism and the next step — read the block, don't just re-run.

**Do not** skip or filter tests to make them appear to pass. A red test anywhere is a failure —
"pre-existing / not my diff" does not clear it.

**One green run is not proof for the truncation modes.** Crash position drifts between runs
(observed drifting across 52/55/58 tests into the same output line), so when investigating a
`FAIL_TRUNCATED_*` verdict, confirm a fix with two consecutive clean runs.

---

## Step 3 — App launch verification (HARD GATE)

```powershell
python tools/debug_launch.py
```

Then read `netsentinel_debug.log` (the non-timestamped file) and confirm **all three**:

- `Dashboard() instantiated OK` is present
- `window.show() called OK` is present
- No `UNHANDLED EXCEPTION` block anywhere in the log

**Critical — read `netsentinel_debug.log` only, never the timestamped variants
(`netsentinel_debug_YYYYMMDD_HHMMSS.log`).** Timestamped files are from older runs.
`debug_launch.py` deletes them before each run; only one timestamped log (the current run)
and `netsentinel_debug.log` ever exist.

If old timestamped logs remain from a session before this rule was enforced, delete them:
```powershell
Remove-Item netsentinel_debug_????????_??????.log -Force -ErrorAction SilentlyContinue
```

**Why this step is mandatory:** PyQt6 TypeError crashes (wrong kwarg on `addLayout`, bad signal
signature, missing import) only surface here — not in the test suite. A clean test run does
**not** prove the app starts.

**Hard gate:** Do not proceed to Step 4 until `window.show() called OK` is confirmed in the log.

---

## Step 4 — UI sign-off (human gate)

Tell the user:

> "Tests pass, app launched cleanly — please verify the window looks correct and say 'looks good' to proceed."

Wait for the user's explicit confirmation before Step 5.

**Accepted phrases:** "looks good", "lgtm", "fine", "ok"

**Not accepted:** silence, a new question, a feature request, or "let's keep going".
Do NOT treat any of these as approval. Ask again if needed.

---

## Step 5 — Explicit commit instruction (HARD GATE)

Do **NOT** run `git commit`, `git push`, `git tag`, or any destructive git operation unless
the user explicitly says so using one of these phrases:

> "commit to repo" · "push to repo" · "go ahead and commit" · "push it" · "commit it"

**"looks good"** and **"lgtm"** from Step 4 do **not** grant permission to commit.
They are UI approval only — Step 5 requires a separate explicit instruction.

---

## Failure modes and restarts

### Step 1 fails (ruff/mypy/pip-audit)
Fix the violations. Do not suppress without understanding why. Re-run the failing tool to confirm
exit 0 before continuing. Do not proceed to Step 2 while violations remain.

### Step 2 fails (tests)
Fix the failing tests. Do not continue. The full gate must be re-run from Step 1 after any
code change — a fix that clears the tests might introduce new lint violations.

A `FAIL_TRUNCATED_SILENT` verdict is **not** a flaky run — it means a test reached
`Dashboard.closeEvent()` → `os._exit(0)` in-process and killed the session. Run
`python -m pytest tests/test_suite_completes.py -q` to name the offending file, then move its
Dashboard construction into a subprocess child (RULE-TP4-DASH). Re-running the suite without
fixing it just reproduces the truncation at a different position.

### Step 3 fails (app won't start)
This is the most important failure. PyQt6 crashes here do not appear in tests. Common causes:
- Wrong kwarg names on Qt layout calls (RULE-UI1 — never assume PyQt5 kwargs work in PyQt6)
- Missing import in a newly created module
- Signal connected to a slot with the wrong signature

Read the full log. The `UNHANDLED EXCEPTION` block contains the traceback. Fix the root cause —
do not re-run `debug_launch.py` speculatively.

### Step 3 passes after Step 2 fix
Always re-run Step 1 (ruff) after any code change that fixed Step 2 tests. Fixes sometimes
introduce unused imports.

---

## Output

State the result of each step explicitly:

```
Step 1 (ruff): ✓ exit 0
Step 1 (mypy): ✓ exit 0
Step 1 (pip-audit): ✓ exit 0
Step 2 (run_test_suite): ✓ [PASS] N passed
Step 3 (debug_launch): ✓ window.show() called OK
Step 4: waiting for user UI confirmation
Step 5: waiting for explicit commit instruction
```
