# NetSentinel — Claude Code context

## Version management

**Always use `bump_version.py` for version changes.** It patches all tracked files atomically and runs consistency tests.

```powershell
python bump_version.py 1.57      # bump to specific version
python -m pytest tests/test_version_consistency.py -v   # verify
```

Never pass flags like `--current` to bump_version.py — it has no flags; the first positional arg is the new version string.

Current version sequence: v1.4.0 → v1.5.0 → v1.5.1 → v1.5.5 → v1.5.6 → v1.5.7 ...
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
4. ✅ apm.yml documents RULE-R4: "MSIX Version format must be exactly 4 parts (X.Y.Z.0)"
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
