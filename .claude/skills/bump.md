---
name: bump
description: >
  Run the full NetSentinel version bump and release workflow. Invoke whenever the user says
  "version bump", "bump version", "bump to X.Y.Z", "bump the version", "ship it", "release",
  "tag and release", or any variation. Handles CHANGELOG, README, What's New in-app,
  bump_version.py, push, and tag in the correct order. Also covers "re-push the tag",
  "retrigger CI", "send tags again" (retag mode, no version bump).
role: worker
user-invocable: true
---

# NetSentinel Version Bump & Release

## Two modes

| User says | Mode |
|---|---|
| "bump to X.Y.Z", "version bump", "release" | **Full bump** — new version number, CHANGELOG, push + tag |
| "re-push the tag", "retrigger CI", "send tags again" | **Retag** — same version, move tag to HEAD, no CHANGELOG |

---

## Mode A: Full bump

### Step 0 — Determine the target version

Use the version the user specifies. If none given, increment the current patch digit (X.Y.Z → X.Y.Z+1).
Run to confirm current version:
```powershell
python -c "import re; print(re.search(r'setApplicationVersion\(\"(.+?)\"\)', open('app.py').read()).group(1))"
```

### Step 1 — Run the commit gate first

Before touching any version file, the working tree must be clean.
Invoke `/commit-gate` (Steps 1–3 only — the bump itself IS the commit, so no separate git commit instruction is needed yet).

If the commit gate fails, fix the failures before proceeding.

### Step 2 — Write the CHANGELOG.md entry

Add a `### vX.Y.Z` entry at the **top** of `CHANGELOG.md`, following the format already in that file.

Required structure (omit empty groups):
```
### vX.Y.Z
**Added**
- One line per new feature or module

**Changed**
- One line per behaviour change

**Fixed**
- One line per bug fix

**Security**
- One line per security hardening (always last)
```

Rules for entries:
- One line per logical change. Combine related commits into one entry.
- Use backticks for code references: module names, page labels, file paths.
- Start each bullet with a capital letter; no trailing period.
- Do NOT include version-bump machinery ("bump to vX.Y.Z", "update winget manifests").
- Do NOT pad ("various improvements", "minor fixes").

### Step 3 — Update README.md changelog summary

Under `## Changelog` in `README.md`, update the topmost `### vX.Y.Z (current)` block to a
3–5 bullet plain-English summary of the most important changes. This is the public-facing
highlights; full history lives in CHANGELOG.md.

### Step 4 — Update "What's New" in ui/help_tab.py

Find the `_section(f"What's New in v{app_ver}", [...])` call in `ui/help_tab.py` and update
it to match the CHANGELOG entry for this version.

### Step 5 — Run bump_version.py

```powershell
python bump_version.py X.Y.Z
```

This updates all tracked version files, runs consistency tests, and **auto-commits** the version
files. Do NOT manually edit `app.py`, `cli.py`, `apm.yml`, `installer.iss`, winget manifests —
`bump_version.py` handles all of them.

If `bump_version.py` exits non-zero: fix the reported failures before continuing.

`bump_version.py` handles every tracked version file (RULE 11) — don't hand-edit any of them.

### Step 6 — Get a clean 30-minute monkey test from the user (RULE-CHAOS1)

Version bumps require a clean monkey session before the tag push. **The agent does not launch
the session** — ask the user to run it themselves and paste the results:

```powershell
tools/run_all_monkey_tests.ps1
# or:
python tools/monkey_test.py --source --seed 99 --duration 1800
```

If the pasted results show crashes or hangs: fix them, re-run Steps 1–5, then ask the user to
re-run the monkey test. If clean: proceed to Step 7.

Do NOT skip this step and do NOT proceed to Step 7 until the user has pasted a clean result.

### Step 7 — Push branch and tag

`bump_version.py` auto-commits, so only push and tag remain:

```powershell
git push origin main
git tag vX.Y.Z
git push origin vX.Y.Z
```

**Critical — branch push must precede the tag push.** `codeql.yml` and `docs.yml` trigger on
`push: branches: [main]`; pushing only the tag means CI never runs on the commit.

**Non-semver tags are blocked.** Tags like `v1.9.52-codeql` break `AppxManifest.xml`
(requires `X.Y.Z.0`) and the version-consistency tests. Plain semver only.

### Self-verification checklist

Before presenting the result to the user, confirm every box:

- [ ] CHANGELOG.md has a `### vX.Y.Z` entry with full detail
- [ ] README.md `## Changelog` block updated with 3–5 bullet summary
- [ ] "What's New" in `ui/help_tab.py` matches the changelog
- [ ] `bump_version.py X.Y.Z` exited 0; consistency test passed
- [ ] User pasted a clean 30-minute monkey test result (seed 99)
- [ ] `git push origin main` completed before tag push
- [ ] `git tag vX.Y.Z` and `git push origin vX.Y.Z` completed

If architecture docs need updating (new modules, new pages), do those before
Step 5 so the bump commit includes everything.

---

## Mode B: Retag (same version, retrigger CI)

When the user says "re-push the tag", "retrigger CI", or "send tags again" **without** a
version bump, the tag must be moved to HEAD before pushing. Simply deleting and re-pushing
the tag without moving it re-pushes to the **same old commit** — CI silently runs the
old workflow.

```powershell
# Confirm current tag vs HEAD before touching anything
$tagCommit  = git rev-parse vX.Y.Z
$headCommit = git rev-parse HEAD
if ($tagCommit -ne $headCommit) {
    Write-Host "Tag is behind HEAD — moving it"
}

# Move tag to HEAD
git push origin --delete vX.Y.Z   # remove from remote
git tag -d vX.Y.Z                  # remove locally
git tag vX.Y.Z HEAD                # re-create at HEAD
git push origin vX.Y.Z             # push — triggers CI
```

**Why this matters:** GitHub Actions uses the workflow file from the commit the tag points to.
If the tag still points to an older commit (e.g. before a `release.yml` fix was merged),
CI runs the old, unfixed workflow — silently, with no error.

This mode does NOT apply to normal version bumps (Mode A). A bump always creates a brand-new
tag at the just-committed HEAD.

---

## Rationalization prevention

| Excuse | Reality |
|---|---|
| "I'll update CHANGELOG after" | CHANGELOG must precede `bump_version.py` — the script promotes the topmost header |
| "Monkey test takes too long, I'll skip it" | Every version bump requires it. Fix crashes before shipping |
| "I'll push the tag first, branch after" | Branch push must come first — CI won't run on tag-only push |
| "README is close enough, I'll fix it later" | The bump commit is the canonical record. Fix it now |
