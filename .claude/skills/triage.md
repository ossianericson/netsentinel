---
name: triage
description: >
  Investigate a bug and write a structured triage record to .triage/<slug>.md.
  Invoke when the user says "triage this bug", "investigate this crash", "write up a bug",
  "let's triage", or "figure out what's happening" when there is no immediate obvious fix.
  Produces a machine-readable record that survives session ends and can be handed to /debug or /tdd.
  Iron Law: investigate only — do NOT fix during this skill.
role: worker
user-invocable: true
---

# NetSentinel Bug Triage

## Iron Law

**Do not fix during triage. Investigation and fix are separate steps.**

Triage ends when you know *why* the bug happens. It does not end when the bug is fixed.
Fix work belongs to `/debug` (existing failure) or `/tdd` (new feature introducing the bug).

---

## Phase 1 — Intake

Extract the bug description from the user's message. Identify:

- **Symptom**: what the user observed (crash, wrong output, test failure, UI glitch)
- **Trigger**: what action or state produces it
- **Scope**: which module, page, or worker is involved

Generate a slug from the description:

```
slug = description.lower()
     .replace spaces and punctuation with hyphens
     .strip leading/trailing hyphens
     [:60 chars]
     strip trailing hyphens again
```

Check for collision: if `.triage/<slug>.md` exists, append `-2`, `-3`, etc. until unique.

Example: "crash on speed test page when modem disconnects" → `crash-on-speed-test-page-when-modem-disconnects`

---

## Phase 2 — Git diff first (no exceptions)

```powershell
git diff HEAD
git status
git log --oneline -5
```

Read all three before any other investigation. A crash that references code in the diff is
almost certainly caused by that change. Trust the diff over the narrative.

If the symptom touches recent changes: note the commit hash and affected files.

---

## Phase 3 — Reproduce and instrument

**Do not change production code yet.** Reproduce the symptom by:

1. Running the failing test: `python -m pytest tests/<test_file>.py -v -k "<test_name>"`
2. Or launching the app and triggering the condition: `python tools/debug_launch.py`
3. Reading the output — exact error type, traceback, line numbers

Record what happens verbatim. If the bug is not reproducible, say so explicitly — an
irreproducible bug cannot be triaged.

---

## Phase 4 — Root cause analysis

Trace the failure to its root cause mechanism. Not just the symptom — the mechanism.

Ask:
- What exact code path runs before the crash?
- What state assumption does that code make that is violated?
- Is this in the diff? In a dependency? In a platform/Qt constraint?

Common NetSentinel root cause categories to check:
- **Unparented QTimer** — fires on zombie object after widget deletion (RULE-WIN5)
- **Stale Edit cache** — Edit tool applied against pre-repair content (RULE-ENC2)
- **Wrong PyQt6 kwarg** — PyQt5 kwarg used, passes syntax check, TypeError at runtime (RULE-UI1)
- **Silent except: pass** — exception swallowed, symptom appears elsewhere (RULE-LINT2)
- **Duplicate method** — Python uses the last definition, first is silently discarded (RULE-LINT3)
- **Missing `from ui import styles as _s`** — CodeQL py/import-and-import-from (RULE-LINT4)
- **MetricStore outside singleton** — constructed in a page widget, not injected from app.py (ARCH RULE 2)

State the root cause as:
```
Root cause: [specific code] causes [exact symptom] because [mechanism — the chain of events].
```

If you cannot write a mechanistic explanation, you do not yet have the root cause.

---

## Phase 5 — TDD fix plan

Write the fix plan as RED/GREEN cycles, not as a patch:

```
Cycle 1 — RED:
  Test: [what test to write / which existing test to run that fails]
  Expected failure: [what the test outputs before the fix]

Cycle 1 — GREEN:
  Fix: [minimal code change that makes the test pass]
  Scope: [which file and function — one sentence]

Cycle 2 (if needed):
  [repeat pattern for second aspect of the fix]
```

Do not write the actual code here. The plan names what to change; `/tdd` or `/debug` implements it.

---

## Phase 6 — Write the triage record

Write `.triage/<slug>.md` with this exact structure:

```markdown
---
slug: <slug>
date: <YYYY-MM-DD>
status: open
reporter: <user or "session">
---

## Problem

**Symptom:** <one sentence — what the user saw>
**Trigger:** <what action or state produces it>
**Reproducible:** yes / no / intermittent

## Actual vs Expected

| | Description |
|---|---|
| **Actual** | <what happens> |
| **Expected** | <what should happen> |

## Reproduction

```
<exact command or steps to reproduce>
```

Error output:
```
<verbatim traceback or wrong output>
```

## Root Cause Analysis

**Root cause:** <mechanism — not just the symptom>

**Code location:** `<file>:<line>` — `<function name>`

**Category:** <one of: unparented QTimer / stale Edit cache / wrong PyQt6 kwarg /
               silent except / duplicate method / import conflict / MetricStore singleton /
               threading race / encoding / other: ...>

**Relevant RULE:** <RULE-XXX or "none identified">

## TDD Fix Plan

```
Cycle 1 — RED:
  Test: <test to write or run>
  Expected failure: <what the output looks like before the fix>

Cycle 1 — GREEN:
  Fix: <what to change>
  Scope: <file:function>
```

## Acceptance Criteria

- [ ] <specific observable outcome 1>
- [ ] <specific observable outcome 2>
- [ ] Full test suite passes: `python -m pytest tests/ -q`
- [ ] App launches cleanly: `python tools/debug_launch.py` → `window.show() called OK`

## Next step

Invoke `/debug` with this triage record in context, or `/tdd` if the fix involves writing
tests first.
```

---

## Output

After writing the file, state:

```
Triage record written: .triage/<slug>.md
Root cause: [one sentence]
Next step: /debug or /tdd
```

Do not begin implementing the fix. The session ends here unless the user explicitly asks
to continue to `/debug` or `/tdd`.

---

## Rationalization prevention

| Excuse | Reality |
|---|---|
| "The fix is obvious — I'll just apply it" | Write the triage record first. Obvious fixes that skip investigation cause RULE-TP4 violations |
| "The bug isn't reproducible, I'll guess" | State "not reproducible" in the record. A guess applied as a fix is not a fix |
| "I'll remember the root cause next session" | You won't. The triage record is the memory |
| "The slug doesn't matter" | The slug is how you find the record next session. Make it descriptive |
| "Phase 4 mechanism is obvious" | Write it out anyway. "obvious" mechanisms turn out to be wrong more often than written ones |
