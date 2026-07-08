---
name: pr-description
description: >
  Draft a structured, concise PR body. Invoke when the user says "write a PR description",
  "draft a PR body", "open a PR" / "open this PR" / "let's open the PR", "fill in the PR
  template", "summarize this branch as a PR", or "create the PR write-up".
role: worker
user-invocable: true
---

# PR Description — Structured, Concise PR Bodies

## Concision targets

Aim for **100–180 lines**. 250+ lines is a smell. If your draft exceeds
200 lines, tighten: cut every sentence that doesn't change the reviewer's
understanding.

| Section | Ceiling |
|---|---|
| TL;DR | 2–4 sentences |
| Problem (WHY) | max 5 bullets |
| Approach (WHAT) | table OR 3–6 bullets; skip if purely additive |
| Implementation (HOW) | one short paragraph per file, or a table |
| Diagrams | 0–2 mermaid blocks; each preceded by a one-sentence legend |
| Trade-offs | 2–4 bullets |
| Validation | real command output; use `<details>` if long |
| How to test | max 5 numbered steps |

## Required body structure

```
## TL;DR
<2–4 sentences>

## Problem (WHY)
- <bullet>

## Approach (WHAT)
<table or bullets — skip with "Additive: see Implementation" if no design decision>

## Implementation (HOW)
<one paragraph per changed file — intent and risk, not a diff re-statement>

## Diagrams (if non-trivial control flow)
<!-- legend sentence -->
```mermaid
...
```

## Trade-offs
- <option chosen vs rejected>

## Validation
<details><summary>Test run</summary>

```
python -m pytest tests/ -q
```
<paste output>
</details>

<details><summary>App launch check</summary>

```
python tools/debug_launch.py
```
<paste relevant log lines>
</details>

## How to test
- [ ] Step 1
- [ ] Step 2
```

## Inputs to gather before drafting

| Input | Command |
|---|---|
| Files changed | `git diff --name-status main...HEAD` |
| Full diff | `git diff main...HEAD` |
| Commit messages | `git log --no-merges main..HEAD --oneline` |
| Test results | `python -m pytest tests/ -q` |
| App launch check | `python tools/debug_launch.py` — confirm `window.show() called OK` |

Do not draft until all inputs are in hand. Do not invent facts not
present in the diff or commit messages.

## NetSentinel-specific validation sections

Every PR body **must** include both of the following in Validation:

1. **Test run** — `python -m pytest tests/ -q` output (or "no new modules,
   existing suite unchanged").
2. **App launch check** — relevant lines from `netsentinel_debug.log`
   confirming `Dashboard() instantiated OK` and `window.show() called OK`.
   Required for any change touching `ui/`, `workers/`, or `app.py`.

## Mermaid diagrams

Include a diagram only when control flow or data flow is non-obvious.
One diagram for architecture/pipeline changes; two only when relationships
between components are complex. Zero for docs-only or pure-refactor PRs.

Validate every block before saving:
```powershell
# requires Node.js
npx --yes -p @mermaid-js/mermaid-cli mmdc -i diag.mmd -o diag.svg --quiet
```

**Known GitHub renderer gotcha:** square brackets in flowchart edge labels
must be quoted. `A -->|[EXEC]| B` passes `mmdc` but fails on GitHub.
Use `A -->|"[EXEC]"| B`.

## Anti-patterns — refuse these

- Pasting commit messages as the body.
- Marketing tone ("significantly enhances", "best-in-class"). Strip on sight.
- Diagrams without a legend, or unvalidated mermaid blocks.
- Restating the diff line-by-line in Implementation — that is what the
  Files Changed tab is for.
- Skipping Trade-offs or How-to-test because "the PR is small".
- TL;DR longer than four sentences.
- Claiming tests pass without pasting actual output.
