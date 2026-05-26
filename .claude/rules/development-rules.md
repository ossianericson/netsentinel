---
paths:
  - "**/*.py"
---

# NetSentinel — Development Rules for AI Agents

---

## COMMIT GATE — Mandatory Before Every Commit or Push

**These steps are BLOCKING. Do not commit, tag, or push until ALL are complete.**

### Step 1 — Run the full test suite
```powershell
python -m pytest tests/ -q
```
All tests must pass. Fix any failures before proceeding.

### Step 2 — Verify the app starts (HARD GATE)
```powershell
python tools/debug_launch.py
```
Read `netsentinel_debug.log` and confirm:
- `Dashboard() instantiated OK` is present
- `window.show() called OK` is present
- No `UNHANDLED EXCEPTION` block in the log

**Do NOT proceed to Step 3 until this passes.** PyQt6 TypeError crashes (wrong
kwarg on addLayout, bad signal signature, missing import) only surface here —
not in the test suite. A clean test run does not prove the app starts.

### Step 3 — UI sign-off
Tell the user: "Tests pass, app launched cleanly — please verify the window looks correct and say 'looks good' to proceed."

Wait for the user's visual confirmation before Step 4.
Accepted phrases: "looks good", "lgtm", "fine", "ok".
Do NOT treat silence, a new question, or a feature request as approval.

### Step 4 — Explicit commit instruction (HARD GATE)
Do NOT run `git commit`, `git push`, `git tag`, or any destructive git operation unless the user explicitly says so.

Required trigger phrases: "commit to repo", "push to repo", "go ahead and commit", "push it", "commit it".
"looks good" or "lgtm" do **not** grant permission to commit.

---

## Non-Negotiable Rules

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

### RULE 11: Version bump — ALWAYS use bump_version.py (BLOCKING)
**NEVER manually edit version strings in individual files.** The project has a canonical bump script:

```powershell
# Step 1 — add a changelog entry to README.md first (RULE-R1b)
# Step 2 — run the bump script
python bump_version.py X.Y.Z
# Step 3 — verify
python -m pytest tests/test_version_consistency.py -v
```

`bump_version.py` at the project root updates ALL tracked version files atomically:
`app.py`, `cli.py`, `apm.yml`, `installer.iss`, `build.bat`, `build.sh`, `README.md`,
`modules/rest_api.py`, `tools/debug_launch.py`, `CLAUDE.md`,
`packaging/AppxManifest.xml`, and all three `.github/winget/` manifests.

**Do NOT:**
- Call `bump_version.py --help` (there is no --help flag; it treats the argument as the target version)
- Use PowerShell `-replace` or `sed` to patch individual files
- Pass any string other than a valid semver (e.g. `X.Y.Z`) as the argument

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
- **21-I**: Push branch to origin BEFORE tagging: `git push origin main` then `git tag vX.Y.Z` then `git push origin vX.Y.Z`

**CRITICAL — branch push must precede the tag push.**
`codeql.yml` and `docs.yml` trigger on `push: branches: [main]`. If only the tag is
pushed, those workflows never fire. Always push the branch first so CI runs on the
commit, then push the tag to trigger the release build.

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

---

## Release Integrity

### RULE-R1b (blocking): Every version bump needs a README changelog entry
Add a `### vX.Y.Z` entry at the top of `## Changelog` in README.md *before* running `bump_version.py`. The script promotes the topmost header.

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

## Backlog Tracking

### RULE-BACKLOG1 (required): Mark completed backlog items in BACKLOG-UX-V7.md immediately upon completion

When any item from `docs/BACKLOG-UX-V7.md` is finished (all code written, tests pass, app starts):

1. Add `✅ ` prefix to the item row in **Section 7 — Prioritization Table** and append the version: `| ✅ ITEM-ID — Description | ... | Sprint · vX.Y.Z |`
2. Add `✅ ` prefix to the same item in the **Section 8 sprint list**.
3. When all items in a sprint are done, update the sprint header line to: `### Sprint N — Title ✅ SHIPPED vX.Y.Z`

Do this in the same session that the code is written — never defer to a follow-up commit.

### RULE-BACKLOG2 (required): Confirm the target backlog item before starting work

When the user asks to "work on" or "start" a sprint or backlog item, before writing any code:
- State which exact item IDs you are about to implement (e.g. "Starting ACT-3, ACT-4, ACT-7, ACT-8, VIZ-1, VIZ-2, VIZ-7, ANIM-9").
- If any item is ambiguous or has a dependency not yet shipped, say so and ask.

This prevents working on the wrong scope in long sessions.
