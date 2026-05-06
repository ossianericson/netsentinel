# NetSentinel — Claude Code context

## Session workflow

Every session starts with a plan. No exceptions.

Before writing any code, state:
1. Which existing modules this touches and how
2. Any new data contracts — what shape, what owns it
3. Implementation steps in order
4. Any decisions the developer needs to make before proceeding

Then stop. Wait for approval. Then implement.

During implementation:
- If you hit an assumption not covered by the plan, stop and surface it
- Do not expand scope beyond the backlog item — new discoveries get noted at the end
- If an existing module needs changing, say what changes and why before changing it

At the end of each session, write one paragraph covering:
- What was implemented
- What was not reached
- What the next session should pick up first

## Code rules — scope of enforcement

Rules like RULE-AH3 (single colour source), RULE-UX5 (empty-state with inline CTA), and RULE-T4 (smoke test registration) apply to **new code only**. Do not audit or retrofit existing files for compliance — the app is working and the churn has no runtime value.

Apply these rules when:
- Creating a new page (`ui/pages/*.py`)
- Creating a new module (`modules/*.py`) or worker (`workers/*_worker.py`)
- Substantially rewriting an existing file as part of a planned feature

Do not apply these rules as a standalone task against files that are not being touched for a feature.

## Version management

**Always use `bump_version.py` for version changes.** It patches all tracked files atomically and runs consistency tests.

```powershell
python bump_version.py 1.57      # bump to specific version
python -m pytest tests/test_version_consistency.py -v   # verify
```

Never pass flags like `--current` to bump_version.py — it has no flags; the first positional arg is the new version string.

Current version: **v1.7.2**

Version history (condensed): v1.4.0 → v1.5.0 → v1.5.1 → v1.5.5 → v1.5.6 → v1.5.7 → v1.6.2 → v1.6.4 → v1.6.6 → v1.6.7 → v1.6.8 → v1.6.9 → v1.6.10 → v1.7.0 → v1.7.1 → v1.7.2
Note: tags v1.55 and v1.56 were published as two-part (missing dot); treat as v1.5.5/v1.5.6.

## Releasing

The CI workflow (`release.yml`) triggers on `v*` tags. Steps:

```powershell
python bump_version.py X.Y
git add -A
git commit -m "chore: bump to vX.Y"
git push
git tag vX.Y
git push origin vX.Y
```

## CI / GitHub Actions

- No `gh` CLI installed. Use GitHub REST API via WebFetch to inspect runs:
  - Run list: `https://api.github.com/repos/ossianericson/netsentinel/actions/runs?per_page=5`
  - Jobs for a run: `https://api.github.com/repos/ossianericson/netsentinel/actions/runs/{run_id}/jobs`
  - Job logs return 403 unauthenticated — diagnose from YAML + repo files instead.

## Build architecture

- PyInstaller builds **onefile** executables on all platforms (no `COLLECT()` in spec).
  - Windows GUI: `dist\NetSentinel.exe` (single file)
  - Windows CLI: `dist\NetSentinel-cli.exe`
  - Windows service: `dist\NetSentinel-svc.exe`
- **MSIX packaging**: because it's onefile, the staging step must copy the single exe:
  ```powershell
  Copy-Item "dist\NetSentinel.exe" "$stage\NetSentinel\NetSentinel.exe"
  ```
  Not `Copy-Item -Recurse "dist\NetSentinel\*"` (that path doesn't exist — it's a file, not a dir).

## Build stability — preventing future CI failures

**Problem diagnosed May 1, 2026:** Windows MSIX build failed because AppxManifest.xml Version had 5 parts (`1.5.7.0.0`) instead of 4 parts (`1.5.7.0`). The `makeappx.exe` tool strictly rejects 5-part versions.

**Root causes:**
1. bump_version.py was generating `{ver}.0.0` (5 parts) instead of `{ver}.0` (4 parts)
2. AppxManifest.xml documentation was unclear about the format
3. No automated test validated the MSIX version format
4. release.yml had the same buggy version patching logic

**Fixes applied:**
1. ✅ bump_version.py now generates `{ver}.0` (correct 4-part format)
2. ✅ AppxManifest.xml has clear comments explaining the requirement
3. ✅ test_version_consistency.py has new test `test_appxmanifest_msix_version_format()` that validates exactly 4 parts
4. ✅ apm.yml documents RULE-R4 (MSIX version format 4 parts) and RULE-R5 (staging copy pattern)
5. ✅ release.yml now uses correct format `$ver.0` in Patch version strings step

**How to prevent regression:**
- Always run `python -m pytest tests/test_version_consistency.py -v` after bumping versions
- The MSIX test will fail immediately if the version has the wrong number of parts
- bump_version.py is now the single source of truth — never manually edit AppxManifest.xml Version

## Winget submission — E_ABORT root causes and fix

**Problem**: Every winget submission since v1.5.1 failed with exit code `-2147467260` (E_ABORT, 0x80004004). v1.4.0 was the last approved submission.

**Root cause 1 — nested winget call during silent install**: The `installookla` [Run] task in `installer.iss` has `Flags: checkedonce` (selected by default) and runs `cmd.exe /c winget install Ookla.Speedtest.CLI` with `waituntilterminated`. The winget validation sandbox runs the installer with `/VERYSILENT` — the nested winget call hangs or times out → E_ABORT.

**Root cause 2 — UAC elevation in headless environment**: `PrivilegesRequiredOverridesAllowed = dialog` (without `commandline`) caused Inno Setup to attempt UAC elevation via `ShellExecuteEx "runas"` during headless silent installs. That fails in sandboxes → E_ABORT.

**Three-layer fix (all three must remain in place)**:
1. `installer.iss [Setup]`: `PrivilegesRequiredOverridesAllowed = dialog commandline`
2. `installer.iss [Code]`: `ShouldInstallOokla()` returns `not WizardSilent()` — used as `Check:` on the Ookla [Run] entry
3. All winget manifests (static `.github/winget/` AND CI-generated in `release.yml`): Silent and SilentWithProgress switches include `/TASKS="!installookla"`

Belt-and-suspenders: items 2 and 3 both prevent the Ookla task from running during silent installs. Item 1 prevents UAC from aborting the install in headless environments.

**Never remove any of these three defences without understanding the above.**

## Key files

| File | Purpose |
|---|---|
| `bump_version.py` | Canonical version bumper — always start here |
| `.github/workflows/release.yml` | Build + MSIX + installer + GitHub Release + winget submission |
| `packaging/AppxManifest.xml` | MSIX manifest — version is 4-part (`X.Y.Z.0`), patched by workflow |
| `NetSentinel.spec` | PyInstaller onefile spec for GUI |
| `NetSentinelCLI.spec` | PyInstaller spec for CLI |
| `NetSentinelSvc.spec` | PyInstaller spec for Windows service |
| `installer.iss` | Inno Setup installer script |
| `tests/test_version_consistency.py` | Ensures all version strings stay in sync + validates MSIX 4-part format |
| `ui/pages/discover_page.py` | Feature Guide — 24-entry `_FEATURES` list; add an entry here for every new page (RULE-D2) |
| `ui/pages/log_hub_page.py` | Log Hub — live logger output table; emits `live_challenge_detected` to wire Lab Mode live injection |
| `ui/pages/protocol_viz_page.py` | Protocol Visualizer — animated protocol diagram; uses `ProtocolSceneData` from `modules/protocol_animator.py` |
| `ui/widgets/protocol_canvas.py` | QPainter animation engine for protocol diagrams |
| `ui/widgets/explainer_panel.py` | Reusable inline explanation widget used by Lab Mode and Protocol Visualizer |
