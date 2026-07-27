---
name: sprint
description: >
  Manage sprint start and sprint end rituals for NetSentinel. Two modes:
  START — invoke when the user says "start sprint N", "work on next sprint", "let's begin sprint",
  "what's next", or any sprint-start variation. Reads git history first, finds the plan doc,
  and primes context before any code is touched.
  END — invoke when the user says "sprint done", "close this sprint", "wrap up", "mark sprint complete",
  or any sprint-end variation. Updates the active plan document before closing the session.
  Pass "start" or "end" as the argument, or infer from context.
role: worker
user-invocable: true
---

# NetSentinel Sprint Rituals

## Iron Law

**Start a sprint by reading git history first, not by reading files.**
**End a sprint by updating the plan doc, not by assuming it will happen next time.**

---

## Mode: START

### Step 1 — Read git history (HARD GATE, no exceptions)

```powershell
git log --oneline -10
```

Read the full output before opening any source file. The log tells you:
- What was actually delivered (not what was planned)
- The version at the last commit
- Any fix/hotfix commits since the last sprint

Do not start by reading `CLAUDE.md`, source files, or the plan document before completing this step.

### Step 2 — Find the active plan document

Look for files that contain a sprint queue or implementation-order table. Common names:
- `PLAN.md`
- `SPRINT.md`
- Any `.md` file in the project root that contains `Sprint` or `TODO` headings
- `docs/internal/claims-audit.md` for deferred/considered-but-not-built items (BACKLOG.md was retired in v2.1.33; its remaining items now live here)

Do not assume a filename — search. If multiple candidates exist, open the one with the most
recent modification date.

```powershell
Get-ChildItem *.md | Where-Object { Select-String -Path $_.FullName -Pattern "sprint|TODO|backlog" -Quiet } | Sort-Object LastWriteTime -Descending | Select-Object -First 5
```

### Step 3 — Read context and identify next items

Read the plan document. Identify:
1. Items marked as completed (✅) — skip these
2. Items in the next sprint queue — these are the candidates
3. Any items marked as deferred from the previous sprint — handle these first

Cross-reference with the git log from Step 1. If the log shows commits for items not yet
marked ✅ in the plan, update the plan before starting new work (see Mode: END).

### Step 4 — State the sprint scope

Before touching any code, state explicitly:

```
Sprint scope:
  Items from plan: [list the exact items being picked up]
  Deferred from last sprint: [any items, or "none"]
  Excluded this sprint: [any items being intentionally skipped and why]
  Expected output: [what will exist when the sprint is done]
```

Get confirmation from the user if the scope is ambiguous.

### Step 5 — Apply RULE-STAB1 (20% stabilization budget)

If the previous sprint had N items, reserve 1 slot explicitly for stabilization:
- Run the 30-minute monkey test (if not run recently)
- Add the behavioral integration test (RULE-T7) for the feature most likely to regress
- Fix any failing tests introduced by the previous sprint

State which slot is reserved for stabilization before starting feature work.

---

## Mode: END

### Step 1 — Confirm sprint done criteria (RULE-SD1)

A sprint is "done" only when all five pass. Check each explicitly:

```
1. python tools/run_test_suite.py        → [ ] [PASS] / [ ] fail   (RULE-GATE1)
2. python tools/debug_launch.py          → [ ] window.show() called OK / [ ] fail
3. test_nav_completeness + test_systematic_coverage → [ ] pass / [ ] fail (only if new pages added)
4. Behavioral integration test (RULE-T7) → [ ] exists and passes / [ ] missing
5. Verified in live app                  → [ ] stated / [ ] not yet done
```

If any item is unchecked, complete it before proceeding to Step 2.

### Step 2 — Find and update the active plan document

Find the same plan document identified during sprint start.

Required updates:
1. Mark every completed item with ✅
2. For any scoped item not completed: add a note `→ deferred to Sprint N+1` with a one-line reason
3. Update the footer or summary line with today's date
4. Add the next sprint's planned queue so the next session starts without research

### Step 3 — State completion explicitly

Write this block:

```
Sprint N complete as of [date].
Completed: [list of ✅ items]
Deferred: [list of deferred items with reasons, or "none"]
Next sprint queue: [list of planned items for Sprint N+1]
```

### Step 4 — Recommend commit gate

After updating the plan doc, the working tree has changes. Recommend invoking `/commit-gate`
to commit the sprint work and the updated plan doc together if that has not already been done.

---

## Rationalization prevention

| Excuse | Reality |
|---|---|
| "I already know what was done last sprint" | Run `git log` anyway — commits reveal what was actually merged, not what was planned |
| "I'll update the plan doc after one more thing" | You won't. The plan doc rots the moment it diverges from reality |
| "There's no plan doc, I'll keep it in my head" | If there is no plan doc, create one now. An unwritten plan is not a plan |
| "Sprint N+1 will be obvious from context" | Write the next queue explicitly. The next session starts cold |
| "The stabilization slot is optional if things look clean" | RULE-STAB1 is a scheduled slot, not an "if time permits" |
