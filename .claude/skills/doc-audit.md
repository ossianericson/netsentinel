---
name: doc-audit
description: >
  Read-only health check for the APM governance layer itself — catches rule/doc
  rot before it spreads. Invoke when the user says "audit the rules", "check the
  docs", "are the APM rules in sync", "doc audit", or periodically alongside
  /check. Verifies: no stale rules: block in apm.yml, version tokens agree across
  sources, no fossil CLAUDE.md, generated outputs match .apm source, and the
  architecture map covers every package. Never edits files.
role: worker
user-invocable: true
---

# NetSentinel Doc / Rules Audit

## Iron Law

**Read only. Zero file edits.** This skill answers "is the governance layer still
coherent?" The canonical rule source is `.apm/instructions/*.md`; everything in
`.claude/rules/`, `AGENTS.md`, `GEMINI.md`, and `.github/instructions/` is a
generated output. `CLAUDE.md` is no longer generated and must not come back.

---

## Step 1 — No stale `rules:` block in apm.yml

```powershell
Select-String -Path apm.yml -Pattern '^rules:' -Quiet
```

Expected: `False`. `apm.yml` holds `name/version/description/targets/dependencies`
only — coding rules live in `.apm/instructions/`. A `rules:` block here is dead
weight the compiler ignores and a contradiction trap. Record `✓ clean` or
`⚠ rules: block present — move rules to .apm/instructions/ and delete it`.

---

## Step 2 — Version tokens agree across all sources

```powershell
$app  = (Select-String -Path app.py -Pattern 'setApplicationVersion\("([^"]+)"\)').Matches.Groups[1].Value
$apm  = (Select-String -Path apm.yml -Pattern '^version:\s*(\S+)').Matches.Groups[1].Value
$vis  = (Select-String -Path .apm/instructions/project-vision.instructions.md -Pattern 'Current version:\s*\*\*v([^*]+)\*\*').Matches.Groups[1].Value
"app.py=$app  apm.yml=$apm  project-vision=$vis"
```

All three must be equal. A mismatch means a bump touched one source but not another
(RULE-AH5). Record `✓ all v<X>` or `⚠ drift: <values>`.

---

## Step 3 — No fossil CLAUDE.md

```powershell
Test-Path CLAUDE.md, tests/CLAUDE.md
```

Both must be `False`. Current APM does not generate `CLAUDE.md` — Claude Code reads
`.claude/rules/` directly. A root `CLAUDE.md` would duplicate every rule into context
twice. Record `✓ none` or `⚠ fossil present — remove (it loads rules a second time)`.

---

## Step 4 — Generated outputs match the .apm source

```powershell
$env:PATH += ";C:\Users\ossia\AppData\Local\Programs\apm\bin"
apm compile --all 2>&1 | Select-String "completed successfully"
git status --short .claude/rules AGENTS.md GEMINI.md .github/instructions
```

Compile must succeed. If `git status` then shows changes, the committed generated
outputs were stale (someone edited `.apm/instructions/` without recompiling, or
edited a generated file directly — RULE-APM1). Record `✓ in sync` or
`⚠ N generated files drifted — recompiled; review the diff`.

---

## Step 5 — Architecture map covers every package + structure tests pass

```powershell
python -m pytest tests/test_apm_rules_coverage.py tests/test_version_consistency.py -q 2>&1 | Select-Object -Last 3
```

Both must pass. `test_apm_rules_coverage` is directory-level (RULE-GARDEN1): it
checks each tracked package is named in the layout map, not each file. Record
`✓ passed` or `⚠ N failed` with the first message.

---

## Step 5b — Source ↔ output reconciliation

Two checks that catch a dead source file or an unmanaged orphan — neither of which
Step 4 detects, since `apm compile` silently ignores a misnamed source and has no
opinion about extra files sitting in `.claude/rules/`.

```powershell
# (a) every .apm/instructions/*.md must be named *.instructions.md, or apm compile ignores it
Get-ChildItem .apm/instructions -Filter "*.md" | Where-Object { $_.Name -notmatch "\.instructions\.md$" }

# (b) every file in .claude/rules/ must correspond to an .apm source (else it's an orphan)
$sources = Get-ChildItem .apm/instructions -Filter "*.instructions.md" | ForEach-Object { $_.BaseName -replace "\.instructions$", "" }
$outputs = Get-ChildItem .claude/rules -Filter "*.md" | ForEach-Object { $_.BaseName -replace "\.instructions$", "" }
Compare-Object $sources $outputs
```

Both commands should return nothing. Record `✓ no dead sources / no orphans` or
`⚠ <list>` — a dead source needs renaming to the `*.instructions.md` suffix; an
orphan needs either an `.apm/instructions/` source created for it or deletion.

---

## Step 6 — Print the dashboard

```
NetSentinel Doc Audit — YYYY-MM-DD

apm.yml rules block   [✓/⚠]  clean / stale block present
Version tokens        [✓/⚠]  all v<X> / drift: <values>
Fossil CLAUDE.md      [✓/⚠]  none / present
Generated outputs     [✓/⚠]  in sync / N drifted (recompiled)
Source/output sync    [✓/⚠]  no dead sources or orphans / N found
Structure tests       [✓/⚠]  passed / N failed
```

Symbol guide: `✓` clean, no action · `⚠` advisory, fix at next natural break.

---

## What this skill does NOT do

- Does not edit `.apm/instructions/` or any rule file (that is normal /<edit> work).
- Does not run the full test suite or the commit gate (use `/check` / `/commit-gate`).
- Does not commit anything.

---

## Rationalization prevention

| Excuse | Reality |
|---|---|
| "The rules were fine last week" | Bumps and concurrent sessions drift them silently — 30 seconds to confirm |
| "I'll just edit CLAUDE.md / .claude/rules to fix it" | Those are generated. Edit `.apm/instructions/` and recompile (RULE-APM1) |
| "A rules: block in apm.yml is harmless" | It's ignored by the compiler but contradicts the live rules — delete it |
