---
applyTo: "**/*.py"
description: "Development rules, commit gates, and architectural constraints for NetSentinel. All RULE-* entries are blocking unless marked 'required'."
---

# NetSentinel — Development Rules for AI Agents

---

## COMMIT GATE — Mandatory Before Every Commit or Push

**These steps are BLOCKING. Do not commit, tag, or push until ALL are complete.**

### Step 1 — Run linters and static analysis (HARD GATE)
```powershell
python -m ruff check . --select=F401,F811,F841
python -m mypy modules/
pip-audit -r requirements.txt --desc
```
All three must exit 0 with no errors. Fix every violation before proceeding — these
are the same checks CI runs, so a failure here means a failed CI run after push.

- **ruff**: unused imports (F401/F811) and unused variables (F841). Fix by removing
  the unused name or adding `# noqa: F401` with a comment explaining the re-export.
- **mypy**: type errors in `modules/`. Add `ignore_errors = True` under a
  `[mypy-modules.<name>]` section in `mypy.ini` for Windows-specific APIs
  (winreg, ctypes.windll, subprocess.CREATE_NO_WINDOW) that only exist on Windows.
- **pip-audit**: known CVEs in dependencies. Update the affected package in
  `requirements.txt` and rerun to confirm the finding is resolved.

### Step 2 — Run the full test suite
```powershell
python -m pytest tests/ -q
```
All tests must pass. Fix any failures before proceeding.

### Step 3 — Verify the app starts (HARD GATE)
```powershell
python tools/debug_launch.py
```
Read `netsentinel_debug.log` and confirm:
- `Dashboard() instantiated OK` is present
- `window.show() called OK` is present
- No `UNHANDLED EXCEPTION` block in the log

**CRITICAL — always read `netsentinel_debug.log` (the main log), never the
timestamped variants (`netsentinel_debug_YYYYMMDD_HHMMSS.log`).** The timestamped
files are from older runs and may describe bugs that have since been fixed. The
`debug_launch.py` script now deletes all old timestamped logs before each run, so
only one timestamped log (the current run) and `netsentinel_debug.log` ever exist.

If old timestamped logs are present from a session before this rule was enforced, delete them:
```powershell
Remove-Item netsentinel_debug_????????_??????.log -Force -ErrorAction SilentlyContinue
```

**Do NOT proceed to Step 4 until this passes.** PyQt6 TypeError crashes (wrong
kwarg on addLayout, bad signal signature, missing import) only surface here —
not in the test suite. A clean test run does not prove the app starts.

### Step 4 — UI sign-off
Tell the user: "Tests pass, app launched cleanly — please verify the window looks correct and say 'looks good' to proceed."

Wait for the user's visual confirmation before Step 5.
Accepted phrases: "looks good", "lgtm", "fine", "ok".
Do NOT treat silence, a new question, or a feature request as approval.

### Step 5 — Explicit commit instruction (HARD GATE)
Do NOT run `git commit`, `git push`, `git tag`, or any destructive git operation unless the user explicitly says so.

Required trigger phrases: "commit to repo", "push to repo", "go ahead and commit", "push it", "commit it".
"looks good" or "lgtm" do **not** grant permission to commit.

---

## Non-Negotiable Rules

### RULE-LINT1 (blocking): No unused imports or unused local variables
Every `.py` file must have no unused imports (F401) and no unused local variables (F841).
Enforce with: `ruff check . --select=F401,F811,F841` (install via `pip install ruff`).
When `ruff` is available locally, run it as part of the commit gate before Step 1.

### RULE-LINT2 (blocking): Silent except blocks must have an explanatory comment
Every `except` block whose body is only `pass` must have an inline comment on the
`pass` line explaining WHY the exception is silenced.

```python
# WRONG — CodeQL py/empty-except
except Exception:
    pass

# CORRECT
except Exception:
    pass  # non-fatal — widget may have already been closed
```

Automated enforcement: `tests/test_no_bare_pass.py` (runs in standard pytest suite).

### RULE-LINT3 (blocking): No class may define the same method name twice
Defining a method twice in the same class body (even intentionally) is a silent bug —
Python uses the last definition, discarding the first. Always remove the redundant copy.

Automated enforcement: `tests/test_no_duplicate_methods.py` (runs in standard pytest suite).

### RULE-LINT4 (blocking): Inside methods that need runtime theme values, use `from ui import styles as _s`
Methods that read theme globals at call time (e.g. for `refresh_theme()`) must import
the module object as `from ui import styles as _s`, NOT as `import ui.styles as _s`.
The `import ui.styles` form conflicts with top-level `from ui.styles import (...)` and
triggers CodeQL `py/import-and-import-from`.

```python
# WRONG
def refresh_theme(self):
    import ui.styles as _s   # conflicts with top-level from ui.styles import ...

# CORRECT
def refresh_theme(self):
    from ui import styles as _s   # imports from the ui package; no conflict
```

### RULE 1: Single colour source
Never hardcode a hex colour string in any UI file. Every colour must be imported from `ui/styles.py`.
If a colour you need does not exist there, add it to `styles.py` first.

```python
# WRONG
label.setStyleSheet("color: #D93025;")

# CORRECT
from ui.styles import RED
label.setStyleSheet(f"color: {RED};")
```

### RULE 2: No QTabWidget for primary navigation
The application uses a permanent 48 px activity rail + 280 px animated flyout (`_FlyoutPanel`) + `QStackedWidget` (`_stack`). Do not add new `QTabWidget` instances to the main navigation flow.

### RULE 3: Table row height is 24px
All tables must keep `verticalHeader().setDefaultSectionSize(24)`. Information density is a design value.

### RULE 4: No blocking I/O on the main thread
All network operations must run in a `QThread` worker. Signals `result_ready` and `error` communicate back to the UI thread.

### RULE 5: Card wrapper for all data sections
Any new page must wrap content in at least one card widget (white background, `1px solid #D4D4D4` border, `0px` radius, 32px title bar).

### RULE 6: Status indicators must be coloured circles, not just text
Status columns use coloured `●` labels. Never use text-only status.

### RULE 9: New pages register in the correct rail section
- Discovery / inventory → "Discover" section
- Real-time monitoring → "Monitor" section
- Reports / export → "Reports" section
- Protocol analysis / deep-dive tools → "Analysis" section
- Scheduling / automation → "Automation" section
- Active probes / elevated-privilege → "Security Audit" section (`audit_item=True`; `admin_required=True` if root/admin needed)
- Student-facing educational tools → "Education" section
- Hardware integrations / physical device management → "Extend" section

Use `self._nav_add_rail_item(label, widget)` (or with `admin_required`/`audit_item` kwargs) inside `_build_pro_nav()` after the correct `_nav_begin_section()` call. Do not call `_nav_add_page()` — that method is legacy dead code.

### RULE 10: matplotlib charts follow the light theme
```python
fig = Figure(facecolor="#FFFFFF")
ax = fig.add_subplot(111)
ax.set_facecolor("#FAFBFC")
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.spines["bottom"].set_color("#D4D4D4")
ax.spines["left"].set_color("#D4D4D4")
ax.tick_params(colors="#5A6A7A", labelsize=9)
ax.grid(True, color="#E8EDF2", linewidth=0.8, linestyle="-")
```

### RULE 11: Version bump checklist
When bumping the application version, update **ALL** of the following:

| File | What to change |
|---|---|
| `app.py` | `app.setApplicationVersion("X.Y.Z")` |
| `cli.py` | `_VERSION = "X.Y.Z"` |
| `apm.yml` | `version: X.Y.Z` |
| `installer.iss` | `#define MyAppVersion "X.Y.Z"` |
| `build.bat` | echo version string |
| `build.sh` | echo version string |
| `README.md` | badge/link + `### vX.Y.Z (current)` changelog entry |
| `modules/rest_api.py` | `"version"` in `/health` endpoint |
| `tools/debug_launch.py` | `app.setApplicationVersion("X.Y.Z")` |
| `.github/winget/NetSentinel.NetSentinel.yaml` | `PackageVersion: X.Y.Z` |
| `.github/winget/NetSentinel.NetSentinel.installer.yaml` | `PackageVersion:` + installer URL |
| `.github/winget/NetSentinel.NetSentinel.locale.en-US.yaml` | `PackageVersion: X.Y.Z` |

`tests/test_version_consistency.py` enforces this. Never bypass it.

### RULE 12: No Unicode replacement characters in README
Never paste text containing `?` (U+FFFD). Use actual Unicode: `—` not `-`, `→` not `->`.

### RULE 19: Semver comparison for update check
```python
# CORRECT — fires only when remote is strictly newer
def _ver(s):
    try:
        return tuple(int(x) for x in s.split("."))
    except ValueError:
        return (0,)
if latest and _ver(latest) > _ver(current):
    self._show_update_bar(latest)
```

### RULE 20: Winget CI job structure
The winget submission job must live in `release.yml` as `needs: [release]`. Never use a separate workflow triggered by `workflow_run`.

### RULE 21: Release checklist (autonomous — do not ask the user to do these)
For every shipped feature or fix:
- **21-A**: Bump version in all files (RULE 11); run version consistency test
- **21-B**: Update README (version, features table, project structure, changelog, "How it was built")
- **21-C**: Update in-app Help "What's New" to match changelog
- **21-D**: Update BACKLOG.md (remove completed items, add date)
- **21-E**: Add test file `tests/test_<module>.py` for every new module
- **21-F**: Register new pages in `_build_pro_nav()` + README
- **21-G**: Add new modules to architecture.instructions.md layout table
- **21-H**: Commit message format: `feat: <description>  vX.Y.Z`
- **21-I**: "Tag" means this EXACT four-step sequence — no exceptions, no shortcuts:
  1. `python bump_version.py X.Y.Z` (plain semver only — no suffixes like `-codeql`)
  2. `git push origin main`
  3. `git tag vX.Y.Z`
  4. `git push origin vX.Y.Z`

**CRITICAL — bump → branch → tag. Every single time.**
- Non-semver tags (e.g. `v1.9.52-codeql`) break `AppxManifest.xml` (requires `X.Y.Z.0`) and the version-consistency tests.
- Branch push must precede the tag push: `codeql.yml` and `docs.yml` trigger on `push: branches: [main]`; pushing only the tag means CI never runs on the commit.
- Never tag without bumping first. Even a one-line patch commit must bump to the next semver.

**Self-verification checklist before presenting to user:**
- [ ] Version bumped in all 9 files; consistency test passes
- [ ] README: badge, features, structure, changelog updated
- [ ] In-app Help "What's New" matches changelog
- [ ] BACKLOG.md: completed items removed, date updated
- [ ] All new modules have tests; full suite passes
- [ ] New pages registered in `_build_pro_nav()` and listed in README
- [ ] `git push origin main` done before `git push origin vX.Y.Z`

### RULE 22-A: Secrets in OS keychain
API keys, passwords, SMTP credentials, SNMP community strings, and tokens must be stored via `keyring`. Never write secrets to `QSettings`, `NetSentinel.ini`, or any file.

```python
import keyring
keyring.set_password("NetSentinel", "service/key_name", value)
value = keyring.get_password("NetSentinel", "service/key_name")
```

### RULE 23: All file writes use get_app_data_dir()
**This is the most critical path rule.** The exe may be installed in `C:\Program Files\NetSentinel\` which is read-only for standard users. Every file write must go through `get_app_data_dir()`.

```python
from modules.utils import get_app_data_dir

# WRONG — PermissionError in Program Files
log_path = os.path.join(os.path.dirname(sys.executable), "crash.log")

# CORRECT — always writable, per-user
log_path = get_app_data_dir() / "crash.log"
```

`get_app_data_dir()` returns:
- Windows: `%LOCALAPPDATA%\NetSentinel\`
- macOS: `~/Library/Application Support/NetSentinel/`
- Linux: `$XDG_CONFIG_HOME/NetSentinel/` (default `~/.config/NetSentinel/`)

`MetricStore._default_path()` uses a three-tier strategy: exe dir (portable) → `get_app_data_dir()` (installed) → `~/.config` (fallback). Never use only tier 1.

**sys.stdout/stderr guard in main():** At the very top of `main()` in `app.py`, before anything else:
```python
if sys.stderr is None:
    try:
        sys.stderr = open(str(get_app_data_dir() / "netsentinel_stderr.log"), "a")
    except Exception:
        import io
        sys.stderr = io.StringIO()
if sys.stdout is None:
    import io
    sys.stdout = io.StringIO()
```

### RULE 24: Speed tester backend cascade
`modules/speed_tester.py` must always try backends in this order:

1. **Ookla CLI** (`_find_ookla_cli()`) — searches 7 paths including `%LOCALAPPDATA%\Microsoft\WinGet\Links\`
2. **speedtest-cli library** — 8 download / 4 upload threads; `pre_allocate=False`; SSL-patched for Python 3.12
3. **Pure-Python HTTP** — 16 download / 8 upload `ThreadPoolExecutor` streams; no extra dependencies

The `SpeedTestResult` return type is identical for all three backends.
The frontend (`speed_test_page.py`, `speed_test_worker.py`) must never know which backend ran.

`ui/pages/ookla_cli_banner.py` shows a dismissible install strip when the CLI is absent.
The banner uses `winget install Ookla.Speedtest.CLI` in a background thread.

**Never bundle `speedtest.exe` inside the installer** — Ookla's EULA prohibits redistribution.
Use the WinGet `PackageDependency` in the installer manifest instead.

### RULE-UI1: Verify PyQt6 API signatures — never assume kwarg names match PyQt5
PyQt6 method signatures differ from PyQt5 and documentation examples. Incorrect
kwargs pass syntax checks but raise TypeError at runtime.

Critical difference to memorise:
```python
# WRONG — TypeError at runtime ("alignment" is not a valid kwarg for addLayout)
evl.addLayout(form_row, alignment=Qt.AlignmentFlag.AlignCenter)

# CORRECT — wrap in a QHBoxLayout with stretches instead
center = QHBoxLayout()
center.addStretch()
center.addLayout(form_row)
center.addStretch()
evl.addLayout(center)
```

Rule: after **any** UI change — including single-line layout tweaks — run
`python tools/debug_launch.py` and verify `window.show() called OK` before
declaring the work done. This is COMMIT GATE Step 2 and is a hard gate.

### RULE 25: Rail section icon standard
Rail section icons (the 48 px icon on the permanent left rail, set via `_nav_begin_section()`) must be **Lucide SVG names** from the `_LUCIDE` dict in `dashboard.py` — not Unicode symbols or photo-emoji.

✓ Correct: `_nav_begin_section("Monitor", "monitor")`
✗ Wrong:   `_nav_begin_section("Monitor", "📊")` or `_nav_begin_section("Monitor", "◉")`

If no existing Lucide name fits, add a new SVG entry to `_LUCIDE` before using it. Available names are listed in `architecture.instructions.md` under "Rail icon standard". Lucide icons render as clean SVG at any size and colour; Unicode and emoji do not.

This rule covers **rail section buttons only**. Flyout item prefix characters are governed by RULE-I4 (geometric Unicode).

---

## Adding a New Scan Module

1. Create `modules/<name>.py` — pure Python, no PyQt imports
2. Create `workers/<name>_worker.py` — QThread, emits `result_ready(object)` and `error(str)`
3. Create `ui/pages/<name>_page.py` — receives `store: MetricStore` as constructor parameter
4. Register in `dashboard._build_pro_nav()` via `_nav_add_rail_item(label, widget)` inside the correct section block
5. Add result cache `self._<name>_result = None` in Dashboard `__init__`
6. Wire `result_ready` signal to a `_on_<name>_result()` slot
7. All colours must come from `ui/styles.py`
8. Add `tests/test_<name>.py` with at least one passing test
9. Update architecture.instructions.md layout table
10. If the worker exposes `set_targets()`: follow RULE-FW1 — add inline target
    management UI on the page, persist via QSettings, emit `targets_changed`
    pyqtSignal, and wire startup loading + signal connection in app.py
11. **Do NOT manually update `_ALL_PAGES` in `tools/systematic_test.py`** — it is
    auto-derived from `ui/nav/builder.py` at runtime via `_discover_pages()`. The new
    page is covered automatically once step 4 is done. Run
    `python -m pytest tests/test_systematic_coverage.py -v` to confirm.

## Naming Conventions

| Element | Pattern |
|---|---|
| Table variables | `self._<module>_table` |
| Status label | `self._<module>_status` |
| Worker reference | `self._<module>_worker` |
| Result cache | `self._<module>_result` |
| Nav label (rail) | string passed to `_nav_add_rail_item(label, ...)` |

---

## Testing Enforcement

### RULE-T1 (blocking): Every new module must have a test file
Every new file under `modules/` must have a corresponding `tests/test_<name>.py` in the same PR, with at minimum one import test and one behavioural test.

### RULE-T2 (blocking): Every new worker must have a start/stop lifecycle test
Every new file under `workers/` must have a test that (1) imports the worker, (2) instantiates it, (3) calls `start()`, waits briefly, calls `stop()`, and asserts `isRunning()` is `False`.

### RULE-T3 (blocking): Every bug fix must include a regression test
Every bug fix PR must include a new test that reproduces the original failure and passes after the fix.

### RULE-T4 (blocking): Smoke test list must stay current
`app.py _smoke_test()` must be updated whenever a new module or worker is added.

### RULE-T5 (blocking): Signal-to-slot chains that cross an animation or async gap must have an integration test covering the full sequence
Unit tests on each part in isolation are insufficient. Any `signal → slot` chain where:
- the slot calls `_nav_rail_go_to()` (160ms crossfade) AND THEN reads `currentWidget()`, OR
- the slot triggers a `QTimer.singleShot()` and the next step depends on state set by that timer

must have a test that exercises the FULL call sequence, not just individual methods.

Pattern to test:
```python
# Test the wiring, not just the existence of the method
dash._on_welcome_scan()                          # trigger the full chain
assert getattr(dash, "_scan_from_home", False)   # assert downstream state
```

This rule exists because the guided tour (H1) was correctly implemented but failed silently:
`_on_welcome_scan` called `_nav_rail_go_to("Home")` then `_start_full_scan()` in the next line.
`_start_full_scan` checked `currentWidget() is _home_page` — but the 160ms crossfade animation
hadn't completed yet, so `currentWidget()` was still the old page, setting `_scan_from_home=False`
and preventing the tour from ever firing. Unit tests for each method passed; the integration test
would have caught it.

### Pytest markers (pyproject.toml addopts)
All markers are declared in `pyproject.toml`. The default `addopts` excludes these markers from every `pytest tests/` run:

| Marker | Excluded by default | When to run |
|---|---|---|
| `live` | Yes | `pytest -m live` — requires real network / device |
| `benchmark` | Yes | `pytest -m benchmark` — performance / scaling tests |
| `monkey` | Yes | `pytest -m monkey` — chaos tests; requires `pywinauto` (dev-only) |
| `slow` | No | Long-running; skip with `-m "not slow"` |
| `integration` | No | Multi-module end-to-end; always runs in CI |

**`monkey` marker specifics:** `tests/test_monkey_test.py` tests `tools/monkey_test.py`, which requires `pywinauto` and `psutil` (listed in `requirements-dev.txt`). These tests are **local-only** — never run in GitHub Actions.

**CRITICAL — Do NOT run monkey tests as part of any commit gate, build, or automated check.** The full monkey/chaos test takes tens of minutes. It is a human-initiated exploratory session — the user starts it manually when they want to run extended chaos coverage. Do not add it to CI, do not suggest running it before committing, and do not include it in any automated pipeline. The commit gate is ONLY Steps 1–4 above.

To run a monkey session manually (user-initiated only):
```powershell
python tools/monkey_test.py --source
python tools/systematic_test.py
```
`tools/monkey_test.py` raises `ImportError` (not `sys.exit`) when imported without `pywinauto`, so the `_import_monkey()` helper in the test file calls `pytest.skip()` gracefully if the dep is missing locally.

### RULE-T6 (blocking): Do not claim a feature works unless it was exercised in the running app
Screenshot automation and unit tests do NOT substitute for a real-user flow test. Before marking
a first-run, onboarding, or post-scan flow as complete:
1. Delete the QSettings key (`ui/first_run_done` or `tour/v1_done`) to simulate a clean install.
2. Launch the app and walk the actual flow (welcome overlay → Scan → tour bar → each step).
3. Confirm each step navigates to the correct page and the tour completes without errors.
State this explicitly in the session: "Verified in live app: [what was observed]." Do NOT
substitute "tests pass" or "screenshots show" for an actual walk-through of user-facing flows.

---

## Release Integrity

### RULE-BUMP1 (blocking): "version bump" always means run bump_version.py
When the user says "version bump", "bump version", "bump to X.Y.Z", or any variation:

1. Determine the target version — use the version the user specifies, or increment the patch digit (X.Y.Z+1) if none given.
2. Add a `### vX.Y.Z` entry at the top of `## Changelog` in `README.md` listing changes from this session (RULE-R1b).
3. Update "What's New" in `ui/dashboard.py` (`_section(f"What's New in v{app_ver}", [...])`) to match the changelog entry.
4. Run `python bump_version.py X.Y.Z` — this updates all tracked version files, runs the consistency tests, **and automatically stages + commits the version files**. **Never edit version strings by hand across files.**
5. If `bump_version.py` exits non-zero, fix the reported failures before continuing.
6. After `bump_version.py` exits 0, the version commit already exists locally. Push and tag:

```powershell
# bump_version.py now auto-commits — only push and tag remain
python bump_version.py X.Y.Z
git push origin main
git tag vX.Y.Z
git push origin vX.Y.Z
```

Do NOT manually edit `app.py`, `cli.py`, `apm.yml`, `installer.iss`, winget manifests, etc. — `bump_version.py` handles all of them.

### RULE-R1b (blocking): Every version bump needs a README changelog entry
Add a `### vX.Y.Z` entry at the top of `## Changelog` in README.md *before* running `bump_version.py`. The script promotes the topmost header.

### RULE-R2 (blocking): Winget locale manifest must be full — never minimal
Every winget submission must include all locale fields: Description, Tags, Moniker, PublisherUrl, PublisherSupportUrl, PackageUrl, LicenseUrl, ReleaseNotesUrl.

### RULE-R3 (blocking): Ookla.Speedtest.CLI must be ExternalDependencies, not PackageDependencies
Using `PackageDependencies` blocks install when the package is not in the official winget index.

### RULE-R4 (blocking): MSIX Version format must be exactly 4 parts (X.Y.Z.0)
`AppxManifest.xml` Version must be `X.Y.Z.0`. `bump_version.py` generates this automatically. `test_version_consistency.py::test_appxmanifest_msix_version_format()` validates it.

### RULE-R5 (blocking): MSIX staging must copy the onefile exe — never glob a directory

### RULE-R6 (blocking): AppxManifest.xml Version= patch must be line-anchored — never unanchored
The PowerShell `-replace` in `release.yml` and the regex in `bump_version.py` **must** anchor to the
start of the line so they only replace the `<Identity>` element's `Version=` attribute.

An unanchored pattern like `Version="[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+"` also matches `Version="` as a
substring of `MinVersion="10.0.17763.0"` and `MaxVersionTested="10.0.22621.0"`, overwriting the
Windows build numbers with the app version and breaking
`test_appxmanifest_target_device_family_minversion` in CI.

**`release.yml` (PowerShell) — correct pattern:**
```powershell
# CORRECT — ^ anchors to start of each line; only matches Identity element's Version= line
(Get-Content "packaging\AppxManifest.xml") -replace '^\s+Version="[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+"', "    Version=`"$ver.0`"" |
  Set-Content "packaging\AppxManifest.xml"

# WRONG — unanchored; matches MinVersion= and MaxVersionTested= as substrings
(Get-Content "packaging\AppxManifest.xml") -replace 'Version="[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+"', "Version=`"$ver.0`"" |
  Set-Content "packaging\AppxManifest.xml"
```

**`bump_version.py` (Python) — correct pattern:**
```python
# CORRECT — ^\s+ + re.MULTILINE anchors to lines starting with whitespace then Version=
_sub(ROOT / "packaging" / "AppxManifest.xml",
     rf'(^\s+Version="){_VER4}(")',
     rf'\g<1>{ver}.0\g<2>',
     flags=re.MULTILINE)
```

Validated by `tests/test_version_consistency.py::test_appxmanifest_target_device_family_minversion`.
```powershell
# CORRECT
Copy-Item "dist\NetSentinel.exe" "$stage\NetSentinel\NetSentinel.exe"
# WRONG — dist\NetSentinel\ does not exist
Copy-Item -Recurse "dist\NetSentinel\*" "$stage\NetSentinel\"
```

---

## Winget Submission

### RULE-W1 (blocking): Silent installs must never run nested winget calls
Winget validation sandboxes run with `/VERYSILENT`; a nested `winget install` hangs → E_ABORT. Three-layer defence must remain:
1. `installer.iss` `[Run]` Ookla entry: `Check: ShouldInstallOokla;` where `ShouldInstallOokla()` returns `not WizardSilent()`.
2. `installer.iss` `[Setup]`: `PrivilegesRequiredOverridesAllowed = dialog commandline`.
3. All winget manifests: Silent/SilentWithProgress switches include `/TASKS="!installookla"`.

### RULE-W2 (blocking): PrivilegesRequiredOverridesAllowed must include `commandline`
Without `commandline`, Inno Setup attempts `ShellExecuteEx "runas"` in headless environments → E_ABORT.

---

## PyInstaller Bundle

### RULE-B1 (blocking): Every new ui/pages/, workers/, modules/ file must be added to hiddenimports in NetSentinel.spec
```
ui/pages/foo_page.py   → add "ui.pages.foo_page"   to hiddenimports
workers/foo_worker.py  → add "workers.foo_worker"   to hiddenimports
modules/foo.py         → add "modules.foo"          to hiddenimports
```
Omitting an entry produces a build that passes CI but crashes at runtime with `ModuleNotFoundError` — only reproducible from the installed package, not from source.

---

## UX Baseline

### RULE-UX1 (required): New pages must show content within 200 ms
Display cached data, last-known state, or a skeleton placeholder within 200 ms of navigation. Use MetricStore cache as initial render source.

### RULE-UX2 (required): Destructive and slow actions must have a visible loading state
Any action >500 ms must show a spinner, progress bar, or disabled "Running…" button before it starts.

### RULE-UX3 (required): Every scan result row must have a right-click context menu
Minimum: "Copy" and "How to Fix". Use `customContextMenuRequested` signal.

### RULE-UX4 (required): Ctrl+F must always focus the sidebar search
Never intercept or consume Ctrl+F in a page widget.

### RULE-UX5 (blocking): Pages requiring scan data must show an empty state with an inline CTA
Static "Run a scan first" text with no action button is a blocking UX violation.

Required pattern:
1. Add `scan_requested = pyqtSignal()` to the page.
2. Build a `QStackedWidget`: page 0 = empty state + primary `QPushButton` emitting `scan_requested`; page 1 = normal content.
3. Default to page 0. Switch to page 1 when data arrives.
4. Wire signal in `app.py`: `window._my_page.scan_requested.connect(window._start_full_scan)`.

Button label conventions: "Scan & Grade", "Scan & Document", "Start Monitoring", "Run Diagnostics", "Run Scan".
DO NOT auto-trigger scans on navigation.

### RULE-UX6 (blocking): Every `item:selected` and `QMenu::item:selected` QSS rule must set both background AND color using theme tokens
```python
# WRONG — white-on-white on dark themes
QTableWidget::item:selected { background: #CCE4F7; }
# CORRECT
QTableWidget::item:selected { background: {TABLE_SEL}; color: {TEXT_PRIMARY}; }
QMenu::item:selected        { background: {BG_HOVER};  color: {TEXT_PRIMARY}; }
```

### RULE-AX1 (blocking): Inline QPushButton stylesheets with a base `color:` must declare explicit `:pressed` (and `:hover`) rules with `color:`
In Qt, a widget's own `setStyleSheet()` overrides the application-level QSS entirely — including the global `QPushButton:pressed` fallback in `ui/styles.py`. If an inline stylesheet sets `color:` in the base rule but omits `:pressed`, Qt reuses the base foreground for the pressed state.

Critical trap — Arctic Clean theme: `WHITE == BG_CARD == #FFFFFF`. Any button with `color:{WHITE}` in its base rule but no explicit `:pressed { color: ... }` renders invisible (white text on white background) when pressed.

Required pattern:
```python
btn.setStyleSheet(
    f"QPushButton {{ background:{ACCENT}; color:{WHITE}; ... }}"
    f"QPushButton:hover    {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
    f"QPushButton:pressed  {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
)
```

Rules:
1. Every inline QPushButton stylesheet that sets `color:` in the base rule **MUST** also set `color:` in an explicit `QPushButton:pressed` rule.
2. Every inline QPushButton stylesheet that sets `color:` in the base rule **SHOULD** also set `color:` in an explicit `QPushButton:hover` rule.
3. All colour values must use tokens from `ui/styles.py` — never hardcoded hex (also enforced by RULE-AH3).

Automated enforcement: `tests/test_interactive_states.py` performs static AST analysis across all `ui/**/*.py` files and fails on any violation. Run: `python -m pytest tests/test_interactive_states.py -v`

Fix: add `QPushButton:pressed {{ background-color: {ACCENT_DARK}; color: {WHITE}; }}` using theme tokens from `ui/styles.py`.

---

## Dual-Audience Rules

### RULE-A1 (required): Every feature must have a plain-English summary and a technical detail view
Plain-English summary visible by default; full technical detail accessible via collapsible section or "Details" button.

### RULE-A2 (required): Error messages must be translated — no raw exceptions shown to users
Translate every worker error to: what failed, why it likely failed, what the user should try next.

### RULE-A3 (required): Severity labels must use the canonical set only
Only: `Info`, `Warning`, `High`, `Critical`. Never invent new severity strings.

---

## Architecture Health

### RULE-AH1 (required): Module files must not exceed 600 lines
Split at 600 lines. Measure: `wc -l modules/<name>.py`.

### RULE-AH2 (required): Workers must not block their thread >5 seconds without a progress signal
Emit `progress(str)` or `status(str)` at least every 5 s. Use `msleep()` + `_running` flag check in loops.

### RULE-AH3 (blocking): No raw hex colour strings outside ui/styles.py and modules/colours.py
CI failure condition. All UI colours → `ui/styles.py`. Chart/report colours → `modules/colours.py`.

### RULE-AH6 (blocking): After adding a new key to any theme dict in styles.py, update all consumer imports
`ui/styles.py` injects theme dict keys into module globals via `globals().update()`. Static analysers
cannot see them. When you add a new key to `_ARCTIC_CLEAN` / `_DARK_PRO` / `_OBSIDIAN_NEON` / `_ABYSS`:

1. Add the same key to **all four** theme dicts.
2. Run `python -m pytest tests/test_style_imports.py -v` — this catches any UI file that references
   the new name as a bare variable without importing it.
3. Add the name to the explicit `from ui.styles import (...)` block in every file that uses it.

Conversely, when **renaming or removing** a theme dict key, find every file that imports the old name
and update the import before committing:
```powershell
python -c "
import ast; from pathlib import Path
for f in Path('ui').rglob('*.py'):
    src = f.read_text(encoding='utf-8')
    try: tree = ast.parse(src)
    except: continue
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module == 'ui.styles':
            if any(a.name == 'OLD_NAME' for a in n.names): print(f)
"
```

### RULE-AH4 (required): Optional dependencies must be lazy-imported with a graceful fallback
Wrap in `try/except ImportError` inside the function that needs them. Never at module level.

### RULE-AH5 (blocking): User-visible names in code must match the names used in docs and UI
Theme names, page labels, feature names must be identical in code, docstrings, README, BACKLOG, and apm.yml.

---

## Navigation Wiring

### RULE-NAV1 (blocking): Every registered page must be reachable from _build_pro_nav()
One nav builder: `_build_pro_nav()`. Do not recreate `_build_home_nav()` or `_build_standard_nav()`.
- Add page widget in `_init_pages()`.
- Add `_nav_add_rail_item("Label", self._new_page)` in `_build_pro_nav()` under the correct section.
- Run `python -m pytest tests/test_nav_completeness.py -v` before merging.

### RULE-NAV2 (blocking): There is one nav mode — do not add new nav builders
All pages go into `_build_pro_nav()` only.

### RULE-NAV3 (blocking): Page-emitted navigate_to signals must route via _nav_rail_go_to, not _nav_goto_label
`_nav_goto_label()` silently fails when `_nav_mode == "home"` (the default). Always call `self._nav_rail_go_to(label)` in dashboard handlers.

---

## Discoverability

### RULE-D1 (required): Every new page must have a _PAGE_HELP entry in dashboard.py
```python
_PAGE_HELP["My Page Label"] = (
    "Short title (≤ 60 chars)",
    "One or two sentences explaining what the page does and how to start."
)
```
Add in the same commit that creates the page.

### RULE-D2 (required): Every new page must have a _FEATURES entry in discover_page.py
Required fields (all six mandatory — missing any crashes on startup):
```python
{"group": "Monitoring", "icon": "⬡", "name": "...", "desc": "...", "page": "Nav Label", "requires": None}
```
`group` must be one of: `"Monitoring"`, `"Diagnostics"`, `"Security"`, `"Learning"`, `"Hidden Features"`, `"Advanced"`.

---

## Dashboard Data Feed Wiring

### RULE-DW1 (blocking): Every page data-feed method must be explicitly wired from the correct result handler
Two canonical wiring locations:
- `dashboard.py _on_*_result` handlers — for scan workers started by the user.
- `app.py` closures after `window = Dashboard(...)` — for always-on background workers.

Known feed points (May 2026): see `apm.yml` RULE-DW1 for the full map.

### RULE-DW2 (blocking): Always-on worker signals must be wired in app.py, not inside Dashboard
Workers started before Dashboard exists must be connected in `app.py` immediately after `window = Dashboard(...)`.

### RULE-DW3 (blocking): Never call internal tile or subwidget methods directly on a page object
Call the page's public proxy methods only:
```python
# WRONG
window._overview_page.update_services(results)   # tile method, not on page
# CORRECT
window._overview_page.on_svc_done(results)        # proxy method
```

### RULE-DW4 (blocking): Post-scan enrichment must sync DeviceInfo objects and refresh all dependent views
When mesh/mDNS/DHCP/NetBIOS enrichment updates hostnames: (1) update `DeviceInfo.hostname` in-place in `_m1_result["devices"]`, (2) rebuild `_net_devices_table`, (3) call `_avail_worker.set_targets()` with fresh labels, (4) re-render topology last.

---

## Feature Wiring

### RULE-FW1 (blocking): Workers with set_targets() require inline target management UI, QSettings persistence, and app.py wiring
1. Inline add/remove form on the page (RULE-UX5 stack pattern).
2. Persist targets via QSettings key `"<feature>/targets"` as JSON array.
3. `targets_changed = pyqtSignal(list)` on the page.
4. In `app.py`: load saved targets on startup → `worker.set_targets()`; connect `targets_changed` → `worker.set_targets`.

### RULE-FW2 (blocking): Every REST API route must appear in rest_api_page endpoint reference in the same session
Add to `_ENDPOINTS` in `RestApiPage._update_endpoint_ref()` in the same session that adds the route to `modules/rest_api.py`.

---

## Sprint Planning

### RULE-SPRINT1 (blocking): Git log first when starting a sprint
Whenever the user says "work on the next sprint", "start Sprint N", or any variation,
the **mandatory first step** is:
```powershell
git log --oneline -5
```
Read the output to understand what was delivered in previous sprints.
Only then pick up the next available items from the plan.
Do **not** start by reading files or checking current state before reviewing git history.

### RULE-SPRINT2 (blocking): Update the active plan document when a sprint ends
When a sprint's work is complete (all items done or explicitly deferred), locate the
active backlog, plan, or sprint-tracking document and update it before closing the
session.  Do **not** assume a specific filename — look for the document that contains
the implementation-order table or sprint queue for the current body of work.

Required updates (regardless of document name or format):
1. Mark every completed item with ✅.
2. Add a note for any items that were scoped but not completed, with the target sprint.
3. Update the footer or summary line with the sprint completion date.
4. Record the next sprint's planned queue so the next session can start without research.

This keeps the plan current so any future agent or session can start immediately
with the right context, without re-deriving what was already done.

---

## Debugging & Troubleshooting

### RULE-DBG1 (blocking): Git Diff First — read the diff before writing any diagnostic plan
```powershell
git diff HEAD
git status
```
A crash that references code in the diff is almost certainly caused by that change. Trust the diff over the narrative.

### RULE-DBG2 (blocking): Plan Before Fix — state the hypothesis before changing any code
Format:
```
Hypothesis: [specific change] causes [symptom] because [mechanism].
Fix: [what we will change].
Expected outcome: [crash gone / different crash / test passes].
```

### RULE-DBG3 (blocking): Two-Attempt Isolation Rule — stop patching after two failed fixes
After two failed attempts: revert all changes → confirm baseline is clean → re-apply one file at a time → binary-search the culprit block.

### RULE-DBG4 (blocking): Anti-Loop Memory — never repeat a failed fix
Before each attempt, review all previous attempts. If the proposed fix is materially the same as one already tried, it is blocked.

### RULE-DBG5 (blocking): FOUC / ghost window diagnosis — inject a global Show event filter before guessing layout causes
```python
from PyQt6.QtCore import QObject, QEvent
class _ShowTracker(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show:
            print(f"SHOW: {obj.metaObject().className()} name={obj.objectName()}")
        return False
_tracker = _ShowTracker()
app.installEventFilter(_tracker)
```
Read terminal output. The widget that prints before the main window is the culprit. Remove the filter before committing.

---

## Windows Platform Rules

### RULE-WIN1 (blocking): No subprocess with PIPE on Windows startup paths
`subprocess.check_output()` / `capture_output=True` on startup causes `STATUS_ACCESS_VIOLATION` (Win32 HANDLE race in `_readerthread`).

Required alternatives:
- Local IPs/masks/speed → `psutil.net_if_addrs()` + `psutil.net_if_stats()`
- Gateway/DNS/DHCP → `winreg HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\{GUID}`
- Gateway MAC → `ctypes.windll.iphlpapi.SendARP()`

Never reintroduce subprocess PIPE in `get_network_info()`, `get_dhcp_info()`, or `get_interface_details()`.

### RULE-WIN2 (blocking): nativeEvent HTMAXBUTTON requires full NC message interception on frameless windows
Returning `HTMAXBUTTON` from `nativeEvent(WM_NCHITTEST)` on a frameless window crashes via `STATUS_ACCESS_VIOLATION`. Must also intercept `WM_NCMOUSEMOVE`, `WM_NCLBUTTONDOWN`, `WM_NCLBUTTONUP` with `wParam==HTMAXBUTTON`. Do not re-add a partial implementation covering only `WM_NCHITTEST`.

### RULE-WIN3 (blocking): Qt test files must never create QApplication at module level
Creating `QApplication` at module import time (collection phase) bypasses conftest.py's session fixture and can cause cumulative C-level heap/stack corruption (`STATUS_STACK_BUFFER_OVERRUN`) that surfaces hundreds of tests later.

```python
# WRONG — runs at import time before any fixture
_app = QApplication.instance() or QApplication(sys.argv + ["-platform", "offscreen"])

# CORRECT — conftest.py owns the session QApplication; just import the class
try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)
```

`conftest.py` provides a session-scoped `qt_app` fixture (autouse=True). All test files that need `QApplication` must use `QApplication.instance()` at call time, not store it at module level.

### RULE-WIN4 (blocking): Qt widgets in tests must use deleteLater() — never rely on Python GC
When a Qt widget goes out of scope at the end of a test function, Python's reference counting calls the C++ destructor *immediately and synchronously*. On Windows, this can corrupt the Qt event loop's internal state, causing `STATUS_STACK_BUFFER_OVERRUN` 400+ tests later.

Required pattern for ALL test fixtures that create Qt widgets:

```python
@pytest.fixture
def my_widget():
    w = MyWidget()
    yield w
    try:
        w.deleteLater()
    except RuntimeError:
        pass
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()
```

For widgets with `QFileSystemWatcher`, `QTimer`, or OS-level background threads: stop those resources BEFORE `deleteLater()`:

```python
# Stop timer to prevent it firing after deletion
if hasattr(w, "_tick_timer"):
    w._tick_timer.stop()
# Mock QFileSystemWatcher in test setup to prevent OS file-watching threads
monkeypatch.setattr(
    "ui.pages.some_page.QFileSystemWatcher",
    lambda *a, **kw: MagicMock(),
)
```

**Never** delete Qt widgets by letting them go out of scope or by calling the C++ destructor directly. **Always** use `deleteLater()` followed by `processEvents()`.

### RULE-WIN5 (blocking): Never use QTimer.singleShot(n, self.method) in __init__ — use a parented QTimer
`QTimer.singleShot(n, slot)` creates a standalone timer with **no Qt parent**. If the widget is
deleted before the timer fires (fixture teardown, rapid navigation, or test cleanup faster than
`n` ms), the timer fires on a zombie C++ object, raises uncaught `RuntimeError` through the
Qt C++ timer callback machinery, and corrupts the heap. The crash surfaces as
`STATUS_STACK_BUFFER_OVERRUN` hundreds of tests later — not at the callsite.

```python
# WRONG — unparented; fires on zombie if widget is deleted within n ms
def __init__(self):
    self._setup_ui()
    QTimer.singleShot(300, self._load_history)

# CORRECT — parented QTimer is auto-destroyed when the widget is deleted
def __init__(self):
    self._setup_ui()
    _t = QTimer(self)
    _t.setSingleShot(True)
    _t.timeout.connect(self._load_history)
    _t.start(300)
```

This rule applies to **any delay**, including 0 ms. `QTimer.singleShot(0, slot)` is equally
dangerous because `processEvents()` in test teardown can fire it before the `deleteLater()`
deferred-delete event is processed.

`QTimer.singleShot(n, slot)` **is safe** in:
- `showEvent` / `closeEvent` handlers (widget is alive when shown; timer is short-lived)
- Transient UI feedback slots (e.g., reset a button label after 2 s) where the lambda
  captures only local widget references and uses a defensive `try/except RuntimeError`

### RULE-WIN6 (blocking): Test fixtures must patch ALL persistent-storage readers for the page under test
When monkeypatching a page's storage functions in a test fixture, identify and patch **every**
function that reads from QSettings, the filesystem, or any other persistent store — not only
the ones that are obviously exercised by the test body.

A missed reader can silently pull in real device data from the developer's machine, causing
the page's `__init__` to spawn timers or workers for those devices. Those objects outlive
fixture teardown and corrupt the heap during unrelated tests.

**Checklist when writing a `_reset_qsettings` (or equivalent) fixture:**

1. Search the page's `__init__` and every method it calls at construction time for any
   function whose name starts with `_load_`, `_read_`, `_fetch_`, or `get_` that touches
   QSettings or the filesystem.
2. Patch each one to return a safe empty value (`[]`, `{}`, `None`).
3. Also patch `QFileSystemWatcher` and any `QThread`/worker that the page auto-starts.

```python
# WRONG — _load_instances not patched; real QSettings data spawns 3-second timers
monkeypatch.setattr("ui.pages.hardware_integration_page._load_paths", lambda: [])

# CORRECT — all readers patched; __init__ constructs with a clean slate
monkeypatch.setattr("ui.pages.hardware_integration_page._load_paths",     lambda: [])
monkeypatch.setattr("ui.pages.hardware_integration_page._load_instances", lambda: [])
monkeypatch.setattr("ui.pages.hardware_integration_page._load_last_result", lambda _: None)
```

QObject subclasses that are **not** QWidget (e.g. `QThread`, `GuidedTour`) are invisible to
`topLevelWidgets()` and therefore escape `conftest._flush_qt_events`. Track them explicitly
and call `deleteLater()` + 3× `processEvents()` in `teardown_method` or fixture finaliser.

---

## QSettings State Hygiene

### RULE-QS1 (blocking): Never gate data access on QSettings-persisted mode — use always-populated sources
Code that branches on a QSettings-restored value to decide which data source to read silently misbehaves on fresh installs. Use `_nav_item_labels` (always populated) rather than `_nav_sections` (mode-dependent).

### RULE-QS2 (required): Works in winget release but fails locally = QSettings state divergence
Diagnostic: `Remove-Item "HKCU:\Software\NetSentinel" -Recurse -Force` to reproduce clean-install state. If bug disappears, apply RULE-QS1.

---

## Startup / DWM Compositing

### RULE-STARTUP1 (blocking): Startup show sequence — off-screen move (non-maximized) then geometry restore
```python
if getattr(window, '_pending_show_maximized', False):
    window.showMaximized()
    _splash.close()
else:
    _saved_rect = window.geometry()
    window.move(-_saved_rect.width() - 200, -_saved_rect.height() - 200)
    window.show()
    _splash.close()
    window.setGeometry(_saved_rect)
```
WHY: on 2nd+ launch, saved geometry is off-center; `window.show()` at that position sticks out from behind the splash. Off-screen move hides it until the splash closes.
`_pending_show_maximized` must be set in `_restore_settings()` — do NOT call `showMaximized()` inside `_restore_settings()` itself.

---

## Icon & Brand Assets

### RULE-I1 (blocking): Never hand-edit PNG or ICO icon files — regenerate via generate_icons.py
```powershell
python generate_icons.py
```
All assets in `assets/icons/` are programmatically generated. Hand edits are overwritten on next build.

### RULE-I2 (required): Icon design language must stay consistent — hexagon, shield, blue/cyan palette
Pointy-top hexagon · white shield inside · `#0078D4` fill · `#005A9E` border · `#00B4D8` cyan ripples at ≥48 px · transparent background for tiles · no gradients, no shadows, no emoji.

### RULE-I3 (required): Top-bar brand icon must use netsentinel.png — never a letter fallback in production
Use PyInstaller-aware path: `Path(sys._MEIPASS) if frozen else Path(__file__).parent.parent`.

### RULE-I4 (blocking): Flyout item prefix icons must be geometric Unicode — never emoji
The prefix character in each flyout item label (the string passed to `_nav_add_rail_item()`) must be a geometric Unicode symbol. Emoji render inconsistently across Windows versions.

Use: `■ □ ▲ △ ● ○ ◆ ◇ ▶ ▷ ⬡ ⬢ ≡ ⌕ ⊕` etc.

This rule covers **flyout item labels only**. Rail section icons (the 48 px permanent-rail buttons) are governed by RULE-25 (Lucide SVG).

---

## Source File Encoding

### RULE-ENC1 (blocking): Python source files must be saved as UTF-8 — never open and resave in Windows-1252
Mojibake occurs when a file correctly encoded as UTF-8 is opened by a Windows text editor
that defaults to Windows-1252 / Latin-1, misreads the multi-byte sequences as individual
characters, and resaves. The result: characters like —, →, ·, ☀, ×, ⚠, ⚙, ⌨ are
replaced by garbled sequences such as â€", â†', Â·, â˜€, Ãƒâ€", âš .

**Canonical symptoms:**
- Close buttons show as garbled sequences instead of ×
- Em dashes show as â€" or Ã—
- Arrows show as â†' instead of →
- Icons show as multi-char garbage instead of ☀, ⚠, 🌙
- Emoji (4-byte UTF-8) show as 4-char garbage: 🌙→ðŸŒ™, 📌→ðŸ"Œ

**Two classes of mojibake:**

*2–3-byte (BMP characters):* `â€"` for `—`, `â†'` for `→`, `Â·` for `·`, etc.
*4-byte (emoji / supplementary plane):* Byte F0 9F... becomes `ðŸ` prefix + 2 more chars.
  - `🌙` (U+1F319) → `ðŸŒ™` — the moon emoji in theme buttons
  - `📌` (U+1F4CC) → `ðŸ"Œ` — pin emoji in Quick Tips

**Prevention:**
- Always save .py files with UTF-8 encoding in your editor
- VS Code: set `"files.encoding": "utf8"` in settings (this is the default)
- Never open NetSentinel source files in Notepad (Windows 10 and earlier uses ANSI/cp1252)
- Git: `git config core.autocrlf` should be `true` (Windows) or `input` (macOS/Linux)
- **AI agents: always re-read a file with the Read tool before calling Edit if any external**
  **process (fix_encoding.py, another chat session, git operation) may have modified it.**
  **The Edit tool writes based on the agent's cached content — a stale cache silently**
  **overwrites external repairs.** (See RULE-ENC2.)

**Detection:** `test_source_encoding.py` automatically detects both classes of mojibake in
string literals, including the 4-byte emoji prefix `ðŸ` (U+00F0 + U+0178).
Run before committing:
```powershell
python -m pytest tests/test_source_encoding.py -v
```

**Fix:** Re-encode the garbled characters back to their correct Unicode equivalents.
The decode procedure: encode each garbled char as cp1252, decode the resulting bytes as
UTF-8. Example:
```python
# Quick repair of a garbled string — run once, not in production code
garbled = 'â€"'           # garbled em dash
fixed   = garbled.encode('cp1252').decode('utf-8')  # → '—'
```

### RULE-ENC2 (blocking): Re-read any file before editing it if an external process may have modified it
The Edit tool applies changes against the agent's cached file content and writes the full
modified buffer back to disk.  If any external process has modified the file since the last
Read — another chat session, `fix_encoding.py`, a git operation, a linter — the Edit will
silently overwrite those external changes.

**This is how encoding repairs get undone:** fix_encoding.py repairs a file, but the agent's
context still has the pre-repair version. The next Edit call writes the old content + the
change, discarding the fix.

**Rule:** Before calling Edit on any file, call Read on it first (even if you have read it
earlier in the session) when any of these conditions are true:
- Another chat session or tool has been running concurrently
- A repair or formatting tool (`fix_encoding.py`, `black`, `isort`, etc.) was run
- A git operation (`checkout`, `reset`, `rebase`) has occurred
- The user mentions the file was just fixed or changed externally

```python
# Wrong — stale context may overwrite external repairs:
Edit(file="ui/pages/home_page.py", old_string="...", new_string="...")

# Correct — re-read first to refresh context:
Read("ui/pages/home_page.py")   # even if read earlier in the session
Edit(file="ui/pages/home_page.py", old_string="...", new_string="...")
```

After any repair tool runs, also verify with `python -m pytest tests/test_source_encoding.py -v`
before proceeding to ensure the repair is intact.

---

## APM Source File Hygiene

### RULE-APM1 (blocking): Never edit CLAUDE.md or .claude/rules/ directly — edit .apm/instructions/ only
`CLAUDE.md` and every file under `.claude/rules/` are **generated files**. They are regenerated from the APM source files by `bump_version.py` (via `apm compile`). Any edit to a generated file will be silently overwritten on the next version bump.

**The canonical source files are:**
```
.apm/instructions/architecture.instructions.md        ← architecture rules, file layout, nav patterns
.apm/instructions/development-rules.instructions.md   ← RULE-*, commit gate, testing, Windows rules
.apm/instructions/project-vision.instructions.md      ← product goals, features, backlog
```

Regeneration is automatic when `bump_version.py` runs, but can also be triggered manually:
```powershell
apm compile   # if APM CLI is installed
```

**Diagnosis:** If you edited CLAUDE.md and your change disappeared, you edited the wrong file. Add the rule to the matching `.apm/instructions/` file instead.

Do NOT create new files under `.claude/rules/` — they will not be regenerated and will diverge from the APM source.
