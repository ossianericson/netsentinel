---
name: debug
description: >
  Apply the NetSentinel systematic debug protocol when investigating a crash, test failure,
  traceback, unexpected behaviour, or "this is broken" report. Invoke whenever the user says
  "something is broken", "this is crashing", "help me debug", "figure out what's wrong",
  "why is this failing", or when a test fails unexpectedly or the app throws an exception.
  Enforces: git diff first → stated hypothesis → two-attempt isolation → anti-loop memory →
  ghost window diagnosis if FOUC or ghost-window symptoms appear.
role: worker
user-invocable: true
---

# NetSentinel Debug Protocol

## Iron Law

**Read the diff before writing any plan. State a hypothesis before changing any code.
Stop after two failed fixes and isolate rather than patch.**

---

## Phase 1 — Git diff first (ALWAYS, NO EXCEPTIONS)

Before reading any file, writing any plan, or forming any theory:

```powershell
git diff HEAD
git status
```

Read the full output. A crash that references code in the diff is almost certainly caused
by that change. Trust the diff over the narrative the user provides.

**Hard gate:** Do not proceed to Phase 2 until you have read the diff output. If `git diff HEAD`
is empty (no uncommitted changes), also run `git log --oneline -5` to see recent commits and
run `git diff HEAD~1 HEAD` to inspect the last commit.

---

## Phase 2 — State the hypothesis before touching code

Write this block explicitly before making any file edit:

```
Hypothesis: [specific change in the diff] causes [exact symptom] because [mechanism].
Fix: [what will be changed — one sentence].
Expected outcome: [crash gone / different crash / test passes / log line disappears].
```

Rules:
- The hypothesis must name the specific diff hunk or function that is the suspected cause.
- The mechanism must explain HOW the change causes the symptom — not just correlation.
- If you cannot write a mechanistic explanation, you do not yet have a hypothesis. Keep reading.

**Do not skip this block.** A fix written without a hypothesis is a guess. A guess that fails
consumes one of the two allowed attempts.

---

## Phase 3 — Apply fix 1

Apply the minimal change that addresses the hypothesis. Run the affected test or relaunch the app.

Record the result:
```
Fix 1: [what was changed]
Result: [passed / failed / different error]
```

If Fix 1 passes: run the full test suite + commit gate. Done.

If Fix 1 fails: go to Phase 4. Do **not** apply another patch yet.

---

## Phase 4 — Apply fix 2 (if Fix 1 failed)

Before attempting Fix 2, check: is the proposed Fix 2 materially the same as Fix 1?
If yes — it is blocked. A repeated fix is not a fix; it is a loop.

Revise the hypothesis:
```
Revised hypothesis: [updated explanation of why Fix 1 was wrong].
Fix 2: [different approach].
Expected outcome: [what changes].
```

Apply Fix 2. Record the result:
```
Fix 2: [what was changed]
Result: [passed / failed / different error]
```

If Fix 2 passes: run the full test suite + commit gate. Done.

If Fix 2 fails: **STOP. Do not attempt Fix 3.** Go to Phase 5.

---

## Phase 5 — Two-attempt isolation (triggered after two failures)

Two failed fixes means the hypothesis was wrong both times. Patching further without
re-establishing a clean baseline produces a tangle of unrelated changes that are harder
to debug than the original problem.

**Mandatory sequence:**

1. **Revert all changes** from both failed fixes:
   ```powershell
   git checkout -- .
   ```
   Confirm the baseline is clean: `git diff HEAD` must show nothing.

2. **Confirm the original failure still reproduces.** Run the failing test or relaunch.
   If it no longer reproduces, one of the reverted fixes was actually correct — binary-search
   by re-applying them one at a time.

3. **Re-apply one file at a time.** Start with the file most likely to contain the cause
   based on the error message. Apply a minimal change. Test. If it passes, done.
   If it fails, revert that file and try the next candidate.

4. **Binary-search the culprit block.** Within a file, comment out halves of the relevant
   function until the symptom disappears. The last removal that made it pass identifies the
   culprit block.

---

## Phase 6 — Ghost window / FOUC diagnosis

Use this phase only when the symptom is: a widget appearing before the main window, a flash
of the wrong widget, or a widget that renders off-screen or invisible.

Inject a global Show event filter immediately after `QApplication` is created:

```python
from PyQt6.QtCore import QObject, QEvent

class _ShowTracker(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show:
            print(f"SHOW: {obj.metaObject().className()} name={obj.objectName()!r}")
        return False

_tracker = _ShowTracker()
app.installEventFilter(_tracker)
```

Read the terminal output after launch. The widget that prints SHOW before the main window
(`Dashboard`) is the culprit. Remove the filter before committing — it must not ship.

---

## Anti-loop memory

Before each attempt, review all previous attempts in this session:

```
Prior attempts:
  Fix 1: [description] → [result]
  Fix 2: [description] → [result]
  ...
```

If the proposed next fix is materially the same as any prior attempt, it is **blocked**.
State why it is the same and propose a genuinely different approach instead.

---

## Restart conditions

Stop immediately and restart from Phase 1 if:

- You applied a fix before stating a hypothesis
- The hypothesis does not name a specific diff hunk or function
- Two different patches were applied without re-establishing a clean baseline between them
- The same approach was tried more than once
- The proposed fix is described as "just try X and see" with no mechanistic explanation

---

## Output format

```
Phase 1 — Diff read: [summary of relevant changes found]
Phase 2 — Hypothesis: [full hypothesis block]
Phase 3 — Fix 1: [change made] → [result]
Phase 4 — Fix 2 (if needed): [revised hypothesis + change made] → [result]
Phase 5 — Isolation (if needed): [file-by-file results]
Resolution: [what the root cause was and what fixed it]
```
