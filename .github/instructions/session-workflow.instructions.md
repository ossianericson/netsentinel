---
description: "Apply to every implementation session. Mandatory plan step before any code is written."
applyTo: "**"
---

# Session Rules — NetSentinel

## Before writing any code

Every session starts with a plan. No exceptions. State:
1. Which existing modules this touches and how
2. Any new data contracts — what shape, what owns it
3. Implementation steps in order
4. Any decisions the developer needs to make before proceeding

Then stop. Wait for approval. Then implement.

## Stability covenant

NetSentinel is feature-complete (v2.1.0+) and Microsoft Store ready — the priority has shifted
from adding capability to not regressing it:
- Ship the smallest diff that fixes the issue. No drive-by refactors.
- No new dependencies or features without an explicit user request.
- When a change could be additive-behind-a-flag or in-place, prefer the flag (RULE-EXP1) —
  it keeps the previously-verified path intact while the new one proves itself.

## During implementation

- If you hit an assumption not covered by the plan, stop and surface it
- Do not expand scope beyond the backlog item — new discoveries get noted at the end
- If an existing module needs changing, say what changes and why before changing it

## Source-of-truth precedence

APM rules (`.apm/instructions/*.md`) outrank skills; skills outrank session memory. Memory is
context, never authority — if a memory entry contradicts a rule, the rule wins and the memory
should be flagged as stale rather than acted on.

## At the end of each session

One paragraph:
- What was implemented
- What was not reached
- What the next session should pick up first
