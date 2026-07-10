---
paths:
  - "**/*.py"
---

# NetSentinel — Development Rules for AI Agents

---

## COMMIT GATE — Mandatory Before Every Commit or Push

Invoke `/commit-gate` before every commit or push. The skill runs all 5 steps with hard gates:
ruff + mypy + pip-audit → full test suite → debug_launch → UI sign-off → explicit commit instruction.

**Step 5 reminder:** `git commit`, `git push`, and `git tag` require the user to say one of:
"commit to repo" · "push to repo" · "go ahead and commit" · "push it" · "commit it".
"looks good" or "lgtm" from the UI sign-off do **not** grant permission to commit.

### RULE-GIT1 (blocking): Never add a Co-Authored-By or co-author trailer
Git commits must carry the message only — no `Co-Authored-By:` line and no other
co-author/attribution trailer. The user runs multiple coding agents and does not
want any single agent credited in history.

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

### RULE-LINT5 (blocking): No CodeQL py/import-and-import-from or py/cyclic-import anywhere in the repo

Ruff's F401/F811/F841 (RULE-LINT1) does not catch either alert class. Enforced by
`tools/check_import_lint.py` (plain `ast`, no CodeQL dep) via `tests/test_import_lint.py`
and the RULE-CI1 pre-push hook.

- `py/import-and-import-from` — any module imported both as `import X` and `from X import Y`
  in the same file (RULE-LINT4 is the specific ui/styles case).
- `py/cyclic-import` — two or more first-party `modules/`/`ui/`/`workers/` modules whose
  *module-level* imports mutually depend on each other (deferred/`TYPE_CHECKING` imports
  don't count — they can't cause a load-time cycle).

Pre-existing debt is grandfathered in `BASELINE_IMPORT_AND_IMPORT_FROM` — do not add new
entries; fix new violations instead (rename to `from <parent-package> import <leaf>`).

### RULE-LINT6 (blocking): No CodeQL py/unused-global-variable in modules/, ui/, or workers/

Ruff's F841 only checks *local* (function-scope) variables — a module-level assignment
never read anywhere is invisible to it. Enforced by `find_unused_global_violations()` in
`tools/check_import_lint.py` (cross-file aware — a name is "used" if read anywhere in its
own file, listed in `__all__`, or imported/attribute-accessed elsewhere) via
`tests/test_import_lint.py` and the RULE-CI1 pre-push hook.

Pre-existing debt is grandfathered in `BASELINE_UNUSED_GLOBALS` — do not add new entries;
fix new violations instead (use the name, delete it, or add it to `__all__`).

**Known blind spot:** like CodeQL itself, this check cannot see a reference made only
through a string literal (`monkeypatch.setattr("mod.NAME", ...)`, `getattr(mod, "NAME")`).
If a new global is flagged but is genuinely consumed that way, verify with a real grep for
the literal name before adding it to the baseline — don't assume "the checker must be wrong."

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

### RULE 10: matplotlib charts use theme constants — no raw hex
Charts must use style constants from `ui/styles.py`, not raw hex literals (RULE-AH3).

**Critical — `BORDER` is QSS-only:** `BORDER` may be `rgba(255,255,255,0.08)` in the dark theme.
Qt stylesheets parse it, but **non-QSS consumers reject it**, so `BORDER` must never reach:
- **matplotlib** — `ax.spines[...].set_color`, `ec=`/`edgecolor=` (incl. inside `annotate(bbox=dict(...))`)
  → raises `ValueError: Invalid RGBA argument`.
- **`QColor(...)`** — `QColor("rgba(...)")` is *invalid* and silently renders opaque **black**
  (QPen/QBrush/QPainter pens, list-item backgrounds).
- **QSS alpha-append** — `f"background:{BORDER}22"` yields `rgba(...)22`, an invalid value Qt drops.

Use the plain-hex `CHART_SPINE` (matplotlib/QColor-safe, defined in both theme dicts) for any
spine, edge, divider, or pen colour that is not set through a Qt stylesheet string.

```python
from ui.styles import CHART_BG, CHART_PLOT_BG, CHART_GRID, CHART_SPINE, TEXT_SECONDARY

fig = Figure(facecolor=CHART_BG)
ax = fig.add_subplot(111)
ax.set_facecolor(CHART_PLOT_BG)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.spines["bottom"].set_color(CHART_SPINE)
ax.spines["left"].set_color(CHART_SPINE)
ax.tick_params(colors=TEXT_SECONDARY, labelsize=9)
ax.grid(True, color=CHART_GRID, linewidth=0.8, linestyle="-")
```

### RULE 11: Version bump checklist
Every version bump touches `app.py`, `cli.py`, `apm.yml`, `installer.iss`, `build.bat`/`build.sh`,
`README.md`, `modules/rest_api.py`, `tools/debug_launch.py`, and all 3 winget manifests.
`bump_version.py` updates all of them automatically — never hand-edit. Invoke `/bump`
(RULE-BUMP1); `tests/test_version_consistency.py` enforces consistency and must never be
bypassed.

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
declaring the work done. This is COMMIT GATE Step 3 and is a hard gate.

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
6. Wire `result_ready` signal to a `_on_<name>_result()` slot; inside that handler call:
   - `self._nav_set_scan_state("Nav Label", "fresh", ts=time.time(), verdict=<one-line summary>)`
   - At scan start: `self._nav_set_scan_state("Nav Label", "running")`
   - In the error slot: `self._nav_set_scan_state("Nav Label", "error", error=str(e))`
   - If the page is a Security Audit scan, add `"Nav Label"` to `_AUDIT_SCAN_LABELS` in `security_overview_page.py`
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

### RULE-TDD1 (blocking): New modules/ code must be written test-first via RED-GREEN-REFACTOR
No implementation code in `modules/` without a failing test first. The Iron Law: if you didn't watch the test fail, you don't know if it tests the right thing.

Invoke `/test-driven-development` at the start of any session that will add or change `modules/` files. The skill enforces hard gates (paste failing output before writing implementation; paste passing output before refactoring).

This rule does NOT apply to `ui/pages/` — PyQt6 widget lifecycle constraints make strict test-first impractical there. Use RULE-T7 for UI pages instead.

### RULE-T1 (blocking): Every new module must be built test-first; test file ships in the same PR
Every new file under `modules/` must have a corresponding `tests/test_<name>.py` covering at minimum one import test and one behavioural test. The test file must be written **before** the implementation (RED-GREEN-REFACTOR per RULE-TDD1), not added after the fact.

### RULE-T2 (blocking): Every new worker must have a start/stop lifecycle test
Every new file under `workers/` must have a test that (1) imports the worker, (2) instantiates it, (3) calls `start()`, waits briefly, calls `stop()`, and asserts `isRunning()` is `False`.

### RULE-T3 (blocking): Every bug fix starts with a failing regression test
Before writing any fix code, write a test that reproduces the original failure and watch it fail (RED). Then write the minimum fix to make it pass (GREEN). The failing test output must be observed — a test added after the fix cannot verify it catches the original bug.

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

Unit tests for each method in isolation cannot detect this failure: each method works correctly on
its own, but `currentWidget()` returns the wrong widget when read before the 160ms crossfade
completes. Only an integration test that drives the full call sequence catches it.

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

### RULE-BUMP1 (blocking): "version bump" always means invoke /bump
When the user says "version bump", "bump version", "bump to X.Y.Z", "ship it", "release", or
any variation, invoke `/bump X.Y.Z`. Never edit version strings across files by hand —
`bump_version.py` handles all of them. The skill handles the full workflow: CHANGELOG →
README → What's New → `bump_version.py` → monkey test (user-run, RULE-CHAOS1) →
`git push origin main` → tag → `git push origin vX.Y.Z`.

Key constraints the skill enforces:
- CHANGELOG.md entry must precede `bump_version.py` (the script promotes the topmost header)
- Branch push must precede the tag push — CI won't run on tag-only push
- Plain semver only — non-semver tags (e.g. `v1.9.52-codeql`) break `AppxManifest.xml`
- A clean monkey-test run is required before every version bump

### RULE-BUMP2 (blocking): Never pass --help or any flag to bump_version.py
`bump_version.py` takes the version positionally (`python bump_version.py X.Y.Z`) — it does
not parse flags. Passing `--help` or any other flag is treated as the version string and the
script rewrites every tracked file's version to that literal text (this happened once with
`--help`). Always invoke it with a bare semver argument, and prefer `/bump` (RULE-BUMP1) so the
skill supplies the argument correctly.

### RULE-R1b (blocking): Every version bump needs a CHANGELOG.md entry and a README.md summary update
Before running `bump_version.py`:
1. Add a `### vX.Y.Z` entry at the **top** of `CHANGELOG.md` — full detail, one bullet per logical change, following the format already in that file. `bump_version.py` promotes this topmost header to the new version number.
2. Update the short `### vX.Y.Z (current)` block under `## Changelog` in `README.md` to a 3–5 bullet plain-English summary of the most important changes. The full history lives in CHANGELOG.md; README.md shows only the current release highlights. `bump_version.py` also promotes this topmost header.

### RULE-R2 (blocking): Winget locale manifest must be full — never minimal
Every winget submission must include all locale fields: Description, Tags, Moniker, PublisherUrl, PublisherSupportUrl, PackageUrl, LicenseUrl, ReleaseNotesUrl.

### RULE-R3 (blocking): Ookla.Speedtest.CLI must be ExternalDependencies, not PackageDependencies
Using `PackageDependencies` blocks install when the package is not in the official winget index.

### RULE-R4 (blocking): MSIX Version format must be exactly 4 parts (X.Y.Z.0)
`AppxManifest.xml` Version must be `X.Y.Z.0`. `bump_version.py` generates this automatically. `test_version_consistency.py::test_appxmanifest_msix_version_format()` validates it.

### RULE-R5 (blocking): MSIX staging must copy the onefile exe — never glob a directory
```powershell
# CORRECT
Copy-Item "dist\NetSentinel.exe" "$stage\NetSentinel\NetSentinel.exe"
# WRONG — dist\NetSentinel\ does not exist
Copy-Item -Recurse "dist\NetSentinel\*" "$stage\NetSentinel\"
```

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

### RULE-TAG1 (blocking): Before re-pushing a tag, always move it to HEAD first
"Re-push the tag" / "retrigger CI" / "send tags again" (without a version bump) means `/bump`
Mode B, not a manual `git push origin --delete` + `git push`. GitHub Actions uses the workflow
file from the commit the tag points to — deleting and re-pushing without first moving the
local tag to HEAD (`git tag -d` + `git tag vX.Y.Z HEAD`) silently re-runs CI against the OLD
commit. Does not apply to normal version bumps (RULE-BUMP1) — those always tag the
just-committed HEAD. Full sequence: `/bump` Mode B.

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

### RULE-AX1 (blocking): Inline QPushButton stylesheets that set base `color:` must also set `color:` in explicit `:pressed` (and `:hover`) rules
An inline `setStyleSheet()` overrides the global QSS, so the base `color:` leaks
into the pressed state. **Mechanism / trap:** in Arctic Clean `WHITE == BG_CARD ==
#FFFFFF`, so `color:{WHITE}` with no explicit `:pressed { color: ... }` renders
white-on-white (invisible) when pressed. Always add `:pressed` (and `:hover`) rules
with `color:`, using `ui/styles.py` tokens (RULE-AH3).
Enforced by `tests/test_interactive_states.py` (AST scan of `ui/**/*.py`) — its
failure message gives the exact fix.

### RULE-QSS1 (blocking): Never set a bare (selector-less) stylesheet on a container widget — scope with an objectName selector
**Mechanism / trap:** a stylesheet with no selector — `w.setStyleSheet("background:transparent;")`
— is interpreted by Qt as `* { ... }` and applies to the widget **and every descendant**. Widget
stylesheets always override the application stylesheet regardless of specificity, so a bare
declaration on a page/frame container silently wipes the app-QSS styling of every child (this
shipped the invisible "Run Speed Test" button, July 2026 — a bare `background:transparent;` on
a scroll-content ancestor wiped `btnScan`'s blue background while its white text survived,
leaving white-on-white). This propagation is also why the codebase historically needed
`border:none; background:transparent` sprinkled on nearly every child label.

```python
# WRONG — bare declarations propagate to the whole subtree
content.setStyleSheet("background:transparent;")

# CORRECT — objectName-scoped; matches only the container itself
content.setObjectName("pageContent")
content.setStyleSheet("QWidget#pageContent { background: transparent; }")
```

Type selectors are NOT safe either: `QWidget { ... }` on a container still matches every
descendant. Only `#name`/`QWidget#name` scoping is safe. Bare declarations remain acceptable
on **leaf** widgets (a QLabel with no children).

Enforced by `tests/test_qss_scoping.py`:
- Tier 1 (zero tolerance): global-QSS buttons (`btnScan`, `btnScanHero`, `btnExport`,
  `btnDiag`, `btnNetRefresh`, `btnRouterLink`) under a bare-styled container.
- Tier 2 (ratchet): total bare-styled containers in `ui/` may only decrease.
  Never raise `BARE_CONTAINER_BASELINE`; lower it when you fix sites.

### RULE-QSS2 (blocking): Never append hex alpha to a colour in QSS — use `alpha()` or a `*_BG` token
**Mechanism / trap:** Qt Style Sheets parse an 8-digit hex colour as **`#AARRGGBB`** (alpha
first), NOT the CSS `#RRGGBBAA` (alpha last) the syntax visually implies. So
`f"background:{ACCENT}22"` — intended as "~13% opacity" — produces `#0078D422`, which Qt
reads as `alpha=0x00, rgb=(0x78,0xD4,0x22)` → fully transparent (nothing renders). A colour
whose first byte is high renders opaque and wrong: `{AMBER}22` → `alpha=0xF5, rgb=(158,11,34)`
= opaque dark crimson (shipped the home "live challenge" banner bright red instead of
translucent amber, July 2026, and left ~60 hover tints silently invisible).

```python
# WRONG — 8-digit hex; Qt reads it as #AARRGGBB and scrambles the colour
w.setStyleSheet(f"background:{ACCENT}22;")

# CORRECT — alpha() emits a proper rgba() string; or use a named *_BG token
from ui.styles import alpha, AMBER_BG
w.setStyleSheet(f"background:{alpha(ACCENT, 0x22)};")   # translucent accent
w.setStyleSheet(f"background:{AMBER_BG};")              # named translucent amber
```

Sibling trap: a plain-hex token that is **light** in one theme (`SIDEBAR_SECTION_BG` is
near-white in Arctic) draws a harsh white border on the dark header bar — chrome on the dark
nav bar in both themes must use a WHITE-alpha hairline (`alpha(WHITE, 0x22)`), not a
theme-swinging plain-hex token.

Enforced by `tests/test_qss_hex_alpha.py` (zero tolerance across `ui/`, excluding `ui/styles.py`
whose `alpha()` docstring shows the antipattern as a counter-example).

### RULE-QSS3 (required): Use the `qss_*` recipe functions instead of hand-typing common inline QSS shapes
`ui/styles.py` exposes `qss_label()`/`qss_muted_label()`, `qss_frame()` (card/banner wrapper),
`qss_chip()` (pill badge), and `qss_dismiss_button()` (flat "X" close). Use these instead of
composing the f-string from scratch; don't reintroduce the raw literal shape in a file that
already migrated onto them.

Enforced by `tests/test_qss_recipe_adoption.py` (ratchet, scoped to `home_page.py`,
`overview_tile.py`, `settings_cards.py`).

### RULE-PERF1 (blocking): Never set `QHeaderView.ResizeMode.ResizeToContents` as a table's default column resize mode
**Mechanism:** the single-argument `setSectionResizeMode(ResizeToContents)` (applied to all
columns) tells Qt to recompute every column's ideal width — a full `sizeHintForColumn()` pass,
calling `QStyledItemDelegate::sizeHint()` per cell, which for text cells calls into DirectWrite
font-metrics/glyph-layout — on **every** relevant model change: row insert, `dataChanged`, and
critically `sortByColumn()`. For a table with hundreds-to-thousands of rows this is multiple
seconds of synchronous main-thread work during which Qt's event loop cannot process input or
repaint — Windows reports the app as "Not Responding" (`IsHungAppWindow` true), indistinguishable
from a real crash to the user, though it always recovers once the recalculation finishes.

```python
# WRONG — recomputes every column's width via per-cell sizeHint() on every model change
t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

# CORRECT — computed once per section, no recurring recalculation
t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
```

`Interactive` still gives Qt's normal default column width and lets the user drag-resize; it
just stops recomputing width from cell contents on every data change. For a content-fitted
initial width, call `resizeColumnsToContents()` **once** right after populating the table —
never leave `ResizeToContents` active as the ongoing mode.

Check with `grep -rn "ResizeMode.ResizeToContents" ui/` before adding any table that can hold
more than ~50 rows or is ever re-sorted.

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
cannot see them. When you add a new key to `_ARCTIC_CLEAN` / `_DARK_PRO`:

1. Add the same key to **both** theme dicts.
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
`group` must be one of the groups currently defined in `ui/pages/discover_data.py`:
`"Start here"`, `"New in this version"`, `"Monitoring"`, `"Diagnostics"`, `"Security"`, `"Automation"`, `"Learning"`, `"Extend"`, `"Hidden features"`.

Note casing: `"Hidden features"` (lowercase 'f'), not `"Hidden Features"`.
Groups appear in the Feature Guide in the order entries are listed in `_FEATURES` — no separate ordering constant exists.

**Group → nav section mapping (canonical):**

| Feature Guide group | Corresponding nav section | When to use |
|---|---|---|
| `"Start here"` | Getting Started | Core daily-use tools (Overview, Speed Test, DNS, What's Wrong?) |
| `"Monitoring"` | Monitor | Passive background monitors, live data streams, infrastructure (Syslog, SNMP, Trends) |
| `"Diagnostics"` | Discover, Reports, Analysis (utilities) | Network inventory, health reports, visualization tools, network utilities |
| `"Security"` | Security Audit + Analysis (threat detection) | ALL threat-detection features regardless of nav section — admin probes, Npcap monitors, rogue detection |
| `"Automation"` | Automation | Scheduling, hooks, integrations, API (REST API, MQTT, Automation Hooks, Custom Triggers, Scheduled Scans, Config Snapshots, Maintenance Windows) |
| `"Learning"` | Education | Protocol visualizer, lab mode, feature guide, help |
| `"Extend"` | Extend | Hardware integrations and plugin ecosystem |
| `"Hidden features"` | — | Discoverability tips for features that are not full pages |
| `"New in this version"` | — | Entries highlighted as recently added |

**Key rules:**
- Group by **user purpose**, not by nav placement. A threat-detection tool belongs in `"Security"` even if its page lives in the Analysis nav section (e.g. ARP Spoof Watch, IoT Behaviour, 802.11 Monitor, Broadcast Storm, Rogue Bridge).
- `"Automation"` maps directly to the Automation nav section. All scheduling, hook, and integration features go here.
- `"Diagnostics"` covers network inventory (Discover nav), health/report tools (Reports nav), and network utility tools.
- A feature already in `"Start here"` may also appear in `"Security"` for discoverability — having it in both is intentional (e.g. ARP Spoof Watch).

---

## Dashboard Data Feed Wiring

### RULE-DW1 (blocking): Every page data-feed method must be explicitly wired from the correct result handler
Two canonical wiring locations:
- `dashboard.py _on_*_result` handlers — for scan workers started by the user.
- `app.py` closures after `window = Dashboard(...)` — for always-on background workers.

To find the full feed-point map, grep `app.py` for `window._` (always-on workers)
and `dashboard.py` for `_on_*_result` (user-triggered scans) — those two call
sites are the authoritative wiring; do not rely on a hand-maintained list.

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

### RULE-SPRINT1 (blocking): Use /sprint when starting or closing a sprint
When the user says "start sprint", "work on next sprint", or any variation: invoke `/sprint start`.
The skill runs `git log` first (hard gate), finds the active plan doc, and states the sprint scope.

When a sprint's work is complete: invoke `/sprint end`.
The skill confirms the RULE-SD1 5-item done checklist and updates the plan document
(mark ✅, add deferred notes, record next queue) before closing the session.

---

## Debugging & Troubleshooting

### RULE-DBG (blocking): Use /debug when investigating any crash or unexpected behaviour
Invoke `/debug` at the start of any debugging session. The skill enforces:
git diff first (hard gate) → stated hypothesis with mechanism → fix 1 → fix 2 →
two-attempt isolation if both fail → ghost window event filter for FOUC symptoms.

Never patch code before reading the diff. Never apply fix 2 if it is materially the same as fix 1.

### RULE-DBG2 (required): For "app is unresponsive" bugs, reach for `procdump -h` before writing custom instrumentation
When a bug's symptom is "the app hangs / freezes / stops responding" (as opposed to a crash
or a wrong-output bug), the fastest path to a real answer is a full memory dump captured at
the exact moment of the hang, analyzed with a real debugger — not a bespoke Python watcher
script reinvented per session.

**Preferred tool: Sysinternals ProcDump, hang-detection mode.**
```powershell
# Installs the whole Sysinternals suite (includes procdump) via winget, one-time:
winget install --id Microsoft.Sysinternals.Suite --accept-source-agreements --accept-package-agreements

# -h = use the OS's own IsHungAppWindow signal to trigger a dump automatically.
# -ma = full memory dump. -n 5 = capture up to 5 dumps (in case the hang recurs/oscillates).
procdump64.exe -accepteula -ma -h -n 5 <pid> <dump_folder>
```
Then reproduce the bug normally. ProcDump captures a full dump the instant Windows marks
the window as hung — no custom polling loop, no manual timing, no race to catch it in time.

**Analyze with `cdb.exe`** (Windows Debugging Tools, often already present at
`C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\cdb.exe` if Windows SDK / WDK is
installed):
```powershell
cdb.exe -z <dump_file> -c "~*kb;q"     # stack trace for every thread
```
Even without Python-level debug symbols, the native call chain is usually enough to identify
the real blocking mechanism — e.g. distinguishing a kernel wait/socket read from expensive
synchronous Qt layout work from a COM call. Compare the stack across 2+ dumps: an identical
repeating pattern is strong confirmation you've found the real mechanism, not a one-off artifact.

**Why this beats a custom watcher+signal approach:** a hand-rolled watcher polling
`IsHungAppWindow` that fires `GenerateConsoleCtrlEvent` to force a `KeyboardInterrupt` does
**not** work reliably for PyQt6 apps — Qt's native C++ event loop (`QCoreApplication::exec()`)
doesn't regularly yield back to Python's signal-checking mechanism, so the interrupt never
lands on a catchable frame. Lead with the well-tested system tool; don't reinvent the
diagnostic every time a new hang is reported.

This generalizes beyond hangs: for crash-type bugs, `procdump -e` (dump on unhandled
exception) or the app's own `faulthandler` output is the equivalent move instead of custom
exception-hook instrumentation.

### RULE-DBG3 (required): Prefer live reproduction over static/log-only archaeology
When investigating a bug, launch the app, drive the actual flow, and watch it break before
reaching for logs, code reading, or static analysis alone. Static archaeology is a fallback
when live reproduction is genuinely not possible (e.g. CI-only failure), not the default
starting point.

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
When a Qt widget goes out of scope at test end, Python's refcounting calls the C++ destructor
*immediately and synchronously*. On Windows this can corrupt the Qt event loop's internal
state, causing `STATUS_STACK_BUFFER_OVERRUN` 400+ tests later.

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

For widgets with `QFileSystemWatcher`, `QTimer`, or OS-level background threads: stop those
resources BEFORE `deleteLater()` (e.g. `w._tick_timer.stop()`; mock `QFileSystemWatcher` in
test setup to prevent real file-watching threads).

**Never** delete Qt widgets by letting them go out of scope or calling the C++ destructor
directly. **Always** `deleteLater()` followed by `processEvents()`.

### RULE-TP4-DASH (blocking): No pytest-collected test may construct a real Dashboard in-process

**Mechanism:** a fully-constructed `Dashboard` cannot be created-and-destroyed in-process on
Windows without a Qt/QThread teardown crash — which is exactly why `Dashboard.closeEvent()`
ends in `os._exit(0)` (RULE-WIN4). Under pytest the autouse `_flush_qt_events` fixture
(`tests/conftest.py`) calls `w.close()` on every top-level widget after each test; on a
Dashboard that reaches `closeEvent()` → **`os._exit(0)` terminates the pytest process itself
with code 0** — no summary, no session-finish. The suite silently truncates and CI goes falsely
green (this hid ~60% of the suite from commit `6d52b36` until mid-2026).

**Correct pattern:** run any Dashboard-constructing test in a subprocess child that owns its
exit code (`tests/_lazy_pages_child.py`): construct the Dashboard, run assertions, then
`dash.close()` on success (drains workers, then `os._exit(0)` cleanly ends the *child*). A
failed assertion raises before `close()` → child exits 1 → parent asserts on the return code.
Keep the child QApplication alive in a module global — a discarded `_ensure_app()` return value
is GC'd and tears down the C++ app under the Dashboard mid-construction.

Enforced by `tests/test_suite_completes.py` (`test_no_collected_test_constructs_dashboard_in_process`
+ the two run-to-completion guards).

### RULE-WIN5 (blocking): Never use unparented QTimer.singleShot(n, self.method) anywhere in a widget — use a parented QTimer
`QTimer.singleShot(n, slot)` creates a standalone timer with **no Qt parent**. If the widget is
deleted before the timer fires (fixture teardown, rapid navigation, or test cleanup faster than
`n` ms), the timer fires on a zombie C++ object, raises uncaught `RuntimeError` through the
Qt C++ timer callback machinery, and corrupts the heap. The crash surfaces as
`STATUS_STACK_BUFFER_OVERRUN` hundreds of tests later — not at the callsite. This rule applies
to every method in a widget class, not only `__init__`.

```python
# WRONG — unparented; fires on zombie if widget is deleted within n ms
def _set_status(self, msg):
    self._status_label.setText(msg)
    QTimer.singleShot(5000, lambda: self._status_label.setText(""))  # fires on zombie!

# CORRECT — parented QTimer is auto-destroyed when the widget is deleted
def _set_status(self, msg):
    self._status_label.setText(msg)
    _t = QTimer(self)
    _t.setSingleShot(True)
    _t.timeout.connect(lambda: self._status_label.setText(""))
    _t.start(5000)
```

This rule applies to **any delay**, including 0 ms. `QTimer.singleShot(0, slot)` is equally
dangerous because `processEvents()` in test teardown can fire it before the `deleteLater()`
deferred-delete event is processed.

`QTimer.singleShot(n, slot)` **is safe** in:
- `showEvent` / `closeEvent` handlers (widget is alive when shown; timer is short-lived)
- Transient UI feedback slots (e.g., reset a button label after 2 s) where the lambda
  captures only local widget references and uses a defensive `try/except RuntimeError`

**Enforcement:** grep-check before committing to catch any new violations:
```powershell
# Flag any QTimer.singleShot that binds to self — all must be parented QTimer(self)
Select-String -Path ui -Include "*.py" -Recurse -Pattern "QTimer\.singleShot\(.*self\."
```
Any hit outside a `showEvent`/`closeEvent` body must be converted to a parented `QTimer(self)`.

### RULE-WIN6 (blocking): Test fixtures must patch ALL persistent-storage readers for the page under test
When monkeypatching a page's storage functions, patch **every** function that reads from
QSettings, the filesystem, or any other persistent store — not only the ones the test body
obviously exercises. A missed reader can silently pull in real device data from the developer's
machine, causing `__init__` to spawn timers/workers that outlive fixture teardown and corrupt
the heap during unrelated tests.

**Checklist:** search `__init__` and everything it calls at construction time for any
`_load_`/`_read_`/`_fetch_`/`get_` function touching QSettings or the filesystem; patch each
to a safe empty value; also patch `QFileSystemWatcher` and any auto-started `QThread`/worker.

```python
# WRONG — _load_instances not patched; real QSettings data spawns 3-second timers
monkeypatch.setattr("ui.pages.hardware_integration_page._load_paths", lambda: [])

# CORRECT — all readers patched; __init__ constructs with a clean slate
monkeypatch.setattr("ui.pages.hardware_integration_page._load_paths",     lambda: [])
monkeypatch.setattr("ui.pages.hardware_integration_page._load_instances", lambda: [])
monkeypatch.setattr("ui.pages.hardware_integration_page._load_last_result", lambda _: None)
```

QObject subclasses that are **not** QWidget (e.g. `QThread`, `GuidedTour`) are invisible to
`topLevelWidgets()` and escape `conftest._flush_qt_events` — track them explicitly and call
`deleteLater()` + 3× `processEvents()` in `teardown_method` or the fixture finaliser.

### RULE-WIN7 (blocking): Never call `.setVisible(...)` / `.show()` on a freshly-constructed widget before it is added to its layout
A widget built with no `parent=` has no parent until `addWidget()`/`insertWidget()` runs —
until then Qt treats it as an independent top-level window, so calling `.setVisible(True)`
(or any truthy expression) on it first flashes it on screen with full native OS chrome
(title bar + min/max/close) for a fraction of a second.

```python
# WRONG — btn is parentless and toggled visible before addWidget; flashes as its own window
btn = QPushButton("...")
btn.setVisible(condition)
layout.addWidget(btn)

# CORRECT — addWidget first, so the widget is already parented when setVisible runs
btn = QPushButton("...")
layout.addWidget(btn)
btn.setVisible(condition)
```
`setVisible(False)` before `addWidget` is harmless (nothing paints) — the risk is only a
non-`False` argument. Enforced by `tests/test_widget_visibility_order.py` (AST guard over `ui/`).

### RULE-WIN8 (blocking): Reassigning the Python handle to a parented widget does NOT free the old one — delete it explicitly before replacing
**Mechanism:** a `QWidget`/`QDialog` created with `parent=self` is owned by its parent in
C++ (Qt's object tree). Dropping the only *Python* reference to it — e.g. `self._x = NewWidget(parent=self)`
overwriting the previous `self._x` — does **not** destroy it: the parent still holds a C++
child pointer, so the widget (and everything it owns: list items, cached query results, child
widgets) lives until the parent is destroyed. In a long-lived window that means "until app
exit." Recreating such a widget on a repeatable user action (open a dialog, rebuild a panel)
leaks one full instance per action. This is unbounded, invisible to Python's GC and to
`tracemalloc` (which only sees the Python-side proxies, not the C++ objects), and surfaces as
steadily climbing RSS → eventual Windows "Not Responding" under memory pressure. The Ctrl+K
command palette leaked this way: every reopen after a close built a fresh `CommandPalette(parent=self)`
without freeing the previous hidden one, driving a moderate soak from ~600 MB past 1.2 GB and
into a 45 s hang.

```python
# WRONG — old palette stays alive as a C++ child of self forever
def _open(self):
    self._palette = CommandPalette(items, parent=self)   # previous one leaks

# CORRECT — delete the stale instance before creating the replacement
def _open(self):
    old = getattr(self, "_palette", None)
    if old is not None:
        try: old.deleteLater()
        except RuntimeError: pass  # already gone
    self._palette = CommandPalette(items, parent=self)
```

Alternative: set `Qt.WidgetAttribute.WA_DeleteOnClose` so the widget self-destructs on close
(then clear the handle in a `destroyed` slot). Either way, a parented widget you recreate on a
repeatable action must have a defined destruction point. Regression coverage for the palette:
`tests/test_command_palette_leak.py`.

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

### RULE-TM1 (blocking): tracemalloc must trace 1 frame and be activated inside the event loop, never inline before app.exec()

The `NETSENTINEL_TRACEMALLOC=1` path in `app.py main()` (set by `tools/monkey_test.py
--tracemalloc` for the multi-hour memory soak) must obey two constraints:

1. **`tracemalloc.start(1)` — 1 frame only.** `start(N)` captures an N-frame Python
   traceback on *every* allocation; cost scales with N. The snapshot loop groups by
   `"lineno"` (`statistics("lineno")` / `compare_to(..., "lineno")`), which uses only the
   TOP frame — so extra frames are pure overhead with an identical leak report. The old
   `start(25)` slowed the process ~7×.
2. **Activate via `QTimer.singleShot(3000, _activate)` — never inline.** The window's first
   paint/layout storm runs once `app.exec()` starts pumping events. Starting tracemalloc
   *before* `app.exec()` means that whole storm runs under allocation tracing. With `start(25)`
   this dragged window-appear time from ~11 s to ~78 s — **past `monkey_test.py`'s 60 s connect
   timeout**, so every `--tracemalloc` soak phase died at launch with exit 2 ("Timed out waiting
   for window") and the hours-long soak never ran. The snapshot loop's own 60 s warmup means a
   3 s deferral loses no leak data.

Symptom to recognise: soak phases exit 2 with an empty `monkey_summary.json` while the
non-tracemalloc coverage sweep connects fine. Verify a fix by launching with
`NETSENTINEL_TRACEMALLOC=1` and confirming the window appears in ~11 s (not ~78 s) and CPU
settles to idle after it shows.

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
Mojibake occurs when a UTF-8 file is opened by an editor that defaults to Windows-1252/Latin-1,
misreads the multi-byte sequences as individual characters, and resaves — turning —, →, ·, ⚠,
emoji, etc. into garbled sequences (`â€"`, `â†'`, `ðŸŒ™`...).

**Prevention:**
- Always save `.py` files as UTF-8 (VS Code default `"files.encoding": "utf8"`)
- Never open source files in Notepad on Windows 10 and earlier (ANSI/cp1252 default)
- `git config core.autocrlf` should be `true` (Windows) or `input` (macOS/Linux)
- Re-read a file with the Read tool before Edit if any external process may have touched it
  since the last Read — a stale cache silently overwrites external repairs (RULE-ENC2)

**Detection:** `python -m pytest tests/test_source_encoding.py -v` before committing.

**Fix:** re-encode the garbled characters as cp1252 bytes, then decode as UTF-8:
```python
garbled = 'â€"'                                      # garbled em dash
fixed   = garbled.encode('cp1252').decode('utf-8')   # -> '—'
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

### RULE-ENC3 (blocking): PowerShell must never write Python source files with a UTF-8 BOM
Windows PowerShell 5.1 writes UTF-8 with BOM (`EF BB BF`) when you use `Set-Content`,
`Out-File`, or `[System.IO.File]::WriteAllText` without explicit encoding. A BOM at the start
of a `.py` file causes `ast.parse` to raise `SyntaxError: invalid non-printable character
U+FEFF`, which silently empties the import set in `test_style_token_imports.py`.

**Never use PowerShell to write Python source files in general.** When forced to (e.g.
regex-replacing a problematic character), strip any BOM immediately afterward:

```powershell
# Strip UTF-8 BOM from a Python source file written by PowerShell
$bytes = [System.IO.File]::ReadAllBytes('path/to/file.py')
if ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
    $nobom = $bytes[3..($bytes.Length-1)]
    [System.IO.File]::WriteAllBytes('path/to/file.py', $nobom)
}
```

Then verify the file still parses:
```powershell
python -c "import ast; ast.parse(open('path/to/file.py', encoding='utf-8').read()); print('OK')"
```

And re-run `test_style_token_imports.py` to confirm no false-positive "missing import" failures.

---

## APM Source File Hygiene

### RULE-APM1 (blocking): Never edit `.claude/rules/` directly — edit `.apm/instructions/` only
Everything under `.claude/rules/` (read by Claude Code) is a **generated output**.
It is regenerated by `apm install` + `apm compile` — automatically via the
PostToolUse hook in `.claude/settings.json` whenever `apm.yml` or any
`.apm/instructions/*.md` file is edited, and again on every `bump_version.py` run.
Any edit to a generated file is silently overwritten on the next compile.

`apm.yml` `targets:` is `claude` only — this project does not use Copilot or
Gemini, so `AGENTS.md`, `GEMINI.md`, and `.github/instructions/` are not
generated and must not be recreated or checked in.

`CLAUDE.md` is **no longer used** — current APM does not generate it (Claude Code
reads `.claude/rules/` directly). Do not recreate a root `CLAUDE.md`; it would
duplicate the rules into context twice.

**The canonical source files are:**
```
.apm/instructions/architecture.instructions.md        ← architecture rules, file layout, nav patterns
.apm/instructions/development-rules.instructions.md   ← RULE-*, commit gate, testing, Windows rules
.apm/instructions/project-vision.instructions.md      ← product goals, features, backlog
.apm/instructions/session-workflow.instructions.md    ← plan-first, stability covenant, source precedence
.apm/instructions/changelog.instructions.md           ← CHANGELOG.md / README.md entry format
.apm/instructions/tests.instructions.md               ← URL-assertion, scaling-guard, LOC-budget, coverage-ratchet conventions
```

To regenerate manually: `apm install && apm compile --clean`.

**Diagnosis:** If you edited a rule and the change disappeared, you edited a
generated output. Make the change in the matching `.apm/instructions/` file instead.

---

## Process Quality

### RULE-REQ1 (blocking): Every feature must define measurable acceptance criteria before implementation starts

Before writing a single line of code, write the done-state as a numbered list of observable
outcomes. Vague requirements ("add onboarding", "improve the Network Map") have no finish line
and will be rebuilt indefinitely.

**Required format:**
```
Feature: <name>
Done when:
  1. <specific observable outcome — widget state, log line, or user action>
  2. <second outcome>
  3. Verified in live app with [QSettings key / flag / condition] reset to simulate clean state.
```

### RULE-REQ2 (blocking): Do not start a replacement/redesign of an existing feature without a written failure report

If an existing implementation is being replaced, write one paragraph stating:
- what specifically fails (user can't do X, test Y fails, crash in scenario Z)
- what was tried to fix it
- why replacement is the right response vs. iterating

This prevents "rewrite because it feels incomplete" replacing "rewrite because criterion 3 is
unachievable with the current design."

### RULE-SPIKE1 (blocking): Platform-specific or low-level API features require a spike document before implementation

Any feature that touches: Windows native APIs (`nativeEvent`, `ctypes.windll`, `winreg`,
`WM_*` messages), PyInstaller frozen-exe behaviour, or OS-level packaging (MSIX, AppxManifest)
requires a spike document written to `docs/spikes/<feature>.md` before the first implementation
commit.

**Minimum spike content:**
1. What Windows API / constraint is involved
2. Known incompatibilities with PyInstaller frozen exe (check this explicitly)
3. PyQt6-specific constraints (frameless windows, QApplication state, nativeEvent side effects)
4. Proof-of-concept result: works / doesn't work / deferred

**Do NOT implement platform-specific features without completing the spike first, even if the
implementation feels obvious.**

### RULE-SPIKE2 (blocking): If a platform feature has already been reverted once, it requires a spike document before the next attempt

A revert is evidence that the constraints were not fully understood at implementation time.
The second attempt must open with a spike document that explains why this attempt will not
hit the same constraint.

Pattern to check in git log before re-attempting:
```powershell
git log --oneline | Select-String "revert.*<feature-name>"
```
If any revert exists, the spike document is mandatory.

### RULE-NAV-RENAME (blocking): Nav label renames require a 3-step migration — never rename in-place

The nav system routes pages by string label (`_nav_rail_go_to("Label")`). A rename that
updates the definition but not all callers silently creates dead navigation paths — no
type error, no test failure, just a broken link.

**Mandatory rename protocol:**
1. Add the new label to `_build_pro_nav()` alongside the old one (two entries temporarily).
2. Find and update every caller: `_nav_rail_go_to`, `navigate_to` signals, `_PAGE_HELP` keys,
   `_FEATURES` entries in `discover_data.py`, help text, README.
3. Remove the old label entry from `_build_pro_nav()`.
4. Run `python -m pytest tests/test_nav_completeness.py -v` to confirm no orphans.

Never skip step 1 — the two-entry temporary state is what makes step 2 safe to verify
before step 3 removes the safety net.

### RULE-T7 (blocking): Every UI page feature must have one behavioral integration test

Unit tests on module functions and worker lifecycle tests do not catch behavioral regressions
in running UI pages. For every substantive new UI feature, add one test that:

1. Instantiates the page (or a mock of the dashboard)
2. Injects realistic mock data (the same data shape the worker would emit)
3. Calls the slot/method that handles the data
4. Asserts a specific widget state (table row count, label text, stack index, node count)

```python
# Example: Network Map — nodes appear after scan result
def test_network_map_shows_nodes_after_scan(qt_app, monkeypatch):
    page = NetworkMapPage(store=mock_store)
    devices = [DeviceInfo(ip="192.168.1.1", mac="aa:bb:cc:dd:ee:ff", ...)]
    page.on_scan_result({"devices": devices})
    assert page._node_count() == 1  # the page must expose a testable accessor
```

### RULE-STAB1 (required): Budget 20% of every sprint for stabilization of the previous sprint

The feat → fix → fix pattern repeats for every major feature area. Fix commits after a sprint
are not anomalies — they are predictable and preventable.

**Concrete rule:** When planning a sprint, if the previous sprint had 5 items, reserve 1 slot
explicitly for: running the 30-minute monkey test, fixing any failures it reveals, and adding
the behavioral test (RULE-T7) for the feature most likely to regress.

This is not "if there's time" — it is a scheduled slot. Skipping it means the next sprint
starts with unacknowledged debt that will surface as fix commits.

### RULE-EXP1 (required): Iterative or uncertain UI patterns must be gated behind a QSettings flag before shipping

When a UI feature is being actively redesigned (onboarding, tour flows, home page layout,
theme switching), implement the new version behind a `QSettings("experimental/<feature>", False)`
flag. The old implementation stays active by default. The new implementation only activates
when the flag is True.

```python
# In the page or mixin:
_use_new_onboarding = QSettings().value("experimental/onboarding_v2", False, type=bool)
if _use_new_onboarding:
    self._build_new_onboarding()
else:
    self._build_legacy_onboarding()
```

Only remove the flag and delete the old implementation after the new one passes RULE-REQ1
acceptance criteria verified in the live app.

### RULE-CHAOS1 (required): A clean 30-minute monkey session is required before every version bump

Random UI interaction at scale finds bugs unit tests cannot: cross-thread timing, focus-steal
edge cases, unexpected widget-lifecycle interactions. This is a required step, not optional —
Step 0 for version bumps specifically (not required for individual fix commits).

**Agent does not launch the session.** Ask the user to run it themselves and paste the
results: `tools/run_all_monkey_tests.ps1`, or `python tools/monkey_test.py --source --seed 99
--duration 1800` (covers all 62 pages at wild chaos level at least twice). Clean run → proceed
with `bump_version.py`. Crashes/hangs in the pasted results → fix them first, then ask for a
re-run before bumping.

### RULE-PACE1 (required): No more than 8 commits in a single day without a stabilization pause

High-velocity days correlate directly with increased fix density in the subsequent 2–3 days. When 8 commits are reached in a calendar day,
the mandatory next action is:

1. Run the full commit gate (Steps 1–3)
2. Run a 15-minute monkey test
3. Confirm no new CodeQL alerts: `git diff main -- '*.py' | grep -E "pass$|except Exception"` 

Only then continue with new feature work. This pause catches the regressions that pile up
when the write-commit loop is compressed below verification threshold.

### RULE-AH1-ENFORCE (blocking): File size limit is enforced in CI — raising the budget is not a valid fix

`test_module_loc.py` enforces the 600-line budget per module. When a file approaches the limit,
the correct action is to plan a split (extract a `_helpers.py` or `_mixin.py`), not to raise
the budget entry in `KNOWN_LARGE_MODULES`.

Raising the budget entry is only valid when:
- The file is a generated file (not editable)
- A split plan has been written and approved, with a target sprint to complete it
- The entry comment explains WHY the budget is being raised and WHEN it will be reduced

### RULE-QC3 (blocking): New nav pages must pass reachability tests before the feat commit

Before writing any `feat:` commit that includes a new page, run both:

```powershell
python -m pytest tests/test_nav_completeness.py -v
python -m pytest tests/test_systematic_coverage.py -v
```

Both must pass. These tests confirm:
1. The page label appears in `_build_pro_nav()` output with a widget assigned.
2. The page is reachable via `_nav_rail_go_to("Label")` at runtime.

Failing to do this produces orphaned pages that appear in the nav but are silently
unreachable — no type error, no crash, just a dead link.

### RULE-CI1 (blocking): Install a git pre-push hook that runs the commit gate

The commit gate (Step 1: ruff + import-lint + mypy) must run before code reaches
GitHub CI — not after. Install a pre-push hook once per clone by running this
in PowerShell at the repo root:

```powershell
# UTF8Encoding($false) = no BOM. A BOM before the `#!/bin/sh` shebang breaks
# the OS's ability to recognize the shebang at all (RULE-ENC3 is the same
# gotcha for .py files -- [System.Text.Encoding]::UTF8 always writes a BOM).
$content = "#!/bin/sh`nruff check . --select=F401,F811,F841 || exit 1`npython tools/check_import_lint.py || exit 1`npython -m mypy modules/ || exit 1`necho '[pre-push] gate passed.'"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText(".git/hooks/pre-push", $content, $utf8NoBom)
```

If the hook blocks a push: fix the violations — never use `git push --no-verify`.

A hook eliminates the discipline requirement — the gate runs automatically on every push
regardless of session context.

### RULE-CI2 (required): GitHub branch protection must require CodeQL to pass before merge

In GitHub repository settings → Branches → main → "Require status checks to pass before
merging", add the CodeQL workflow as a required check.

Once set, no push with open CodeQL alerts can be merged to main — eliminating the entire
category of `fix: resolve N CodeQL alerts` commits. This is a one-time repository
configuration, not a per-commit action.

If CodeQL is not already running, see `.github/workflows/codeql.yml`.

### RULE-SD1 (blocking): A sprint is "done" only when this 5-item checklist passes

A `feat:` commit is not the end of a sprint. Sprint done means all five pass:

1. `python -m pytest tests/ -q` — all tests pass, no new failures
2. `python tools/debug_launch.py` — `window.show() called OK` present in log
3. `python -m pytest tests/test_nav_completeness.py tests/test_systematic_coverage.py -v` — new pages reachable
4. The behavioral integration test for the new feature (RULE-T7) exists and passes
5. State explicitly in session: "Verified in live app: [what was observed]" (RULE-T6)

Steps 1–2 are the existing commit gate. Steps 3–5 are sprint-specific additions the commit
gate does not cover. None can be skipped.

The commit gate verifies code quality; it does not verify feature correctness. Steps 3–5
cover the behavioral gap between "the code is clean" and "the feature works as described."

### RULE-TP4 (required): Write the prevention RULE before writing the fix commit

When a bug is discovered — in tests, in the live app, or via the monkey test — the sequence is:

1. Identify the root cause mechanism (not just the symptom).
2. Write a `RULE-*` entry in `.apm/instructions/development-rules.instructions.md` that
   captures: what the violation looks like, why it causes the bug, and the correct pattern.
3. Then write the fix commit.

Writing the rule first, while the failure is being actively debugged, produces mechanistic
rules ("X causes Y via mechanism Z"). Writing it after produces shallow rules ("don't do X").
Compare RULE-WIN5 — which explains the zombie C++ object corruption chain step by step — vs
a post-hoc rule that just says "use parented timers."

The technical mechanism is clearest during debugging. Writing the rule after the fact means
writing from memory, which produces shallower rules.

### RULE-SS1 (blocking): Every Security Audit result handler must call _nav_set_scan_state

The Security Overview Scan Status card, flyout dot badges, and rail button badge all read from
`_scan_registry`. If a scan result handler does not call `_nav_set_scan_state`, the page shows
"Never run" in the Scan Status card even after the scan completed — a silent mismatch between
actual scan state and displayed state.

**Required pattern in every `_on_*_result()` handler for a Security Audit scan:**
```python
def _on_syn_result(self, result):
    # ... populate table ...
    self._nav_set_scan_state(
        "Port Scan (TCP)",
        "fresh",
        ts=time.time(),
        verdict=f"{len(result.open_ports)} open ports",
    )

def _start_syn_scan(self):
    self._nav_set_scan_state("Port Scan (TCP)", "running")
    self._syn_worker.start()

def _on_syn_error(self, msg: str):
    self._nav_set_scan_state("Port Scan (TCP)", "error", error=msg)
```

**Label matching:** the string passed to `_nav_set_scan_state` must exactly match the entry
in `_AUDIT_SCAN_LABELS` in `security_overview_page.py` and the nav item label registered via
`_nav_add_rail_item()`. A mismatch produces a silent "Never run" row in the Scan Status card.

**Adding a new Security Audit scan tool:**
1. Add the exact nav label to `_AUDIT_SCAN_LABELS` in `security_overview_page.py` (adds a row to the Scan Status card).
2. If the scan needs no user-supplied host (can run automatically), also add it to `_AUDIT_SEQUENCE` in `security_overview_page.py` — this includes it in the "▶ Run Security Audit" coordinator. Currently only 2 scans qualify: Port Scan (TCP) and Exposed to Internet.
3. Wire `_nav_set_scan_state` calls in all three slots: start, result, error.

Enforcement: `tests/test_scan_status_labels.py` and `tests/test_nav_scan_badges.py` cover the
registry update logic. No automated test enforces that every audit handler calls this — rely on
code review and the fact that a missing call produces a visibly wrong "Never run" in the UI.

### RULE-ENFORCE1 (required): Rules that rely on agent memory or discipline fail — prefer tool enforcement

Documented rules are only effective when the agent reads them this session and time pressure
does not override them.

The only reliable enforcement is toolchain enforcement:

| Enforcement type | Reliability | Examples |
|---|---|---|
| CI gate (GitHub Actions) | High — blocks merge | CodeQL check, test suite |
| Pre-push hook (git) | High — blocks push | ruff, mypy (RULE-CI1) |
| Test suite assertion | High — fails CI | `test_nav_completeness.py`, `test_module_loc.py` |
| CLAUDE.md documentation | Low — requires discipline | Most RULE-* entries |

When adding a new RULE-*: immediately ask "can this be enforced by a test or a hook?" If yes,
write the test/hook in the same commit as the rule. A rule with no enforcement mechanism is
documentation, not a gate.

Currently tool-enforced (high reliability):
- RULE-LINT1 → `ruff` in commit gate
- RULE-LINT5 → `tools/check_import_lint.py` + `tests/test_import_lint.py`, CI and RULE-CI1 pre-push hook
- RULE-LINT6 → `tools/check_import_lint.py` (`find_unused_global_violations`) + `tests/test_import_lint.py`, CI and RULE-CI1 pre-push hook; local-variable half via tightened `dummy-variable-rgx` in `pyproject.toml`
- RULE-AH1 → `test_module_loc.py`
- RULE-NAV1 → `test_nav_completeness.py`
- RULE-AX1 → `test_interactive_states.py`
- RULE-QSS1 → `test_qss_scoping.py`
- RULE-QSS2 → `test_qss_hex_alpha.py`
- RULE-QSS3 → `test_qss_recipe_adoption.py`
- RULE-ENC1 → `test_source_encoding.py`
- RULE-WIN3/5 → test suite heap corruption surfaces violations automatically
- RULE-WIN7 → `test_widget_visibility_order.py`
- RULE-WIN8 → `test_command_palette_leak.py` (palette case only — no general AST guard yet)
- RULE-TP4-DASH → `test_suite_completes.py` (AST guard + run-to-completion guards)

Rules that should be converted to tool enforcement (future work):
- RULE-D2 → add startup assertion that crashes if a registered page has no `_FEATURES` entry
- RULE-T1 → add test that every `modules/*.py` has a corresponding `tests/test_*.py`
- RULE-T7 → add test that every `ui/pages/*.py` has at least one behavioral test referencing it

### RULE-GARDEN1 (required): When a rule gains a tool enforcer, compress its prose to a pointer in the same commit
These instruction files load into context every session, so prose has a recurring
cost. The moment a rule is backed by a CI gate, test, or hook, its long "how to fix"
explanation is redundant — the tool's failure message is the live instruction.

When you add or discover a test/hook that enforces a rule:
1. Trim that rule to **invariant + correct one-line pattern + "Enforced by `tests/<file>.py`"** — aim for ≤ 6 lines.
2. Move any detailed remediation steps into the test's assertion message, not the rule.
3. Add the rule to the "Currently tool-enforced" list in RULE-ENFORCE1.

**Exception — keep full prose for mechanism rules.** When the prose explains *why* a
bug happens (the corruption chain in RULE-WIN5, the HANDLE race in RULE-WIN1, the
mojibake/encoding mechanics in RULE-ENC1, the DWM timing in RULE-STARTUP1), that
explanation *is* the value and a test cannot replace it — leave it intact.

This rule is what keeps the de-bloat from regrowing: prune at the moment a rule
becomes tool-enforced, not in a periodic cleanup that never happens.
