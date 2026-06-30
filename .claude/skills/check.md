---
name: check
description: >
  Read-only project health snapshot for session starts. No gates, no blocking, no UI sign-off.
  Invoke when the user says "check the project", "health check", "how's the repo", "status check",
  "quick check", "what's the state of things", or at the start of any session before touching code.
  Runs in ~30 seconds and prints a single dashboard table. Never edits files.
role: worker
user-invocable: true
---

# NetSentinel Health Check

## Iron Law

**Read only. Zero file edits. Never blocks progress.**

This skill answers "is the repo in good shape right now?" It does not run the full commit gate,
does not require UI sign-off, and does not gate on any result. If something is broken, it tells
you — then you decide what to do.

---

## Step 1 — Test count (instant, no execution)

```powershell
python -m pytest tests/ --collect-only -q 2>&1 | Select-String "selected"
```

This collects without running. Reports the total test count in ~2 seconds.
Record: `N tests collected` (or `ERROR — collection failed` if imports are broken).

---

## Step 2 — Lint advisory (non-blocking)

```powershell
ruff check . --select=F401,F811,F841 --quiet
```

Record: `0 violations` or `N violations` with a one-line summary of the first violation.
This is advisory — violations are shown but do not stop the check.

---

## Step 3 — Structure tests (fast subset only)

Run only the three structure-enforcement tests. Do not run the full suite.

```powershell
python -m pytest tests/test_module_loc.py tests/test_nav_completeness.py tests/test_source_encoding.py -q 2>&1 | tail -5
```

Record each as: `✓ passed` or `⚠ N failed` with the first failure message.

---

## Step 4 — Git status

```powershell
git status --short
git log --oneline -1
```

Record:
- Modified files count and staged files count
- Last commit hash, message, and how long ago (use `git log -1 --format="%h %s (%cr)"`)

---

## Step 5 — Print the dashboard

Output this exact format, substituting real values:

```
NetSentinel Health — YYYY-MM-DD

Tests         [✓/⚠/✗] N collected (no failures — not executed)
Lint          [✓/⚠]   N violations  (advisory)
LOC budget    [✓/⚠]   pass / N files over budget
Nav pages     [✓/⚠]   all reachable / N orphaned
Encoding      [✓/⚠]   no mojibake / N files affected
Git status    [✓/⚠]   N modified, N staged
Last commit   <hash> <message> (<time ago>)
```

Symbol guide:
- `✓` — clean, no action needed
- `⚠` — advisory warning, may need attention before next commit
- `✗` — hard failure (collection error, import broken), needs immediate attention

---

## Interpretation guide

| Row | ✓ threshold | What to do if ⚠ |
|---|---|---|
| Tests | Collection succeeds | Run `python -m pytest tests/ -q` to find failures; fix before committing |
| Lint | 0 violations | Run `ruff check . --select=F401,F811,F841` for details; fix before committing |
| LOC budget | All modules ≤ 600 lines | Plan a split (RULE-AH1); don't raise the budget entry |
| Nav pages | All pages reachable | Run `test_nav_completeness.py -v` for orphan details; fix before merging |
| Encoding | No mojibake detected | Run `test_source_encoding.py -v` for file list; re-encode with UTF-8 |
| Git status | 0 modified / 0 staged | Intended state; if unexpected, review with `git diff HEAD` |

---

## What this skill does NOT do

- Does not run the full test suite (use `/commit-gate` Step 2 for that)
- Does not launch the app (use `/commit-gate` Step 3 for that)
- Does not block on UI sign-off (use `/commit-gate` Step 4 for that)
- Does not commit anything
- Does not write any file

---

## Rationalization prevention

| Excuse | Reality |
|---|---|
| "I know the project is fine, I was just here" | Run it anyway — 30 seconds, no ceremony |
| "I'll run the full commit gate instead" | `/commit-gate` blocks on UI confirmation. `/check` answers the question without ceremony |
| "Lint warnings are noise" | They become RULE-LINT1 violations at commit time. See them now, fix at a natural break |
| "I'll check git status manually" | This check combines status, lint, structure, and encoding in one read |
