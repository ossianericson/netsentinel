---
applyTo: "**/*.py"
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
The application uses `QListWidget` (sidebar) + `QStackedWidget` (content). Do not add new `QTabWidget` instances to the main navigation flow.

### RULE 3: Table row height is 24px
All tables must keep `verticalHeader().setDefaultSectionSize(24)`. Information density is a design value.

### RULE 4: No blocking I/O on the main thread
All network operations must run in a `QThread` worker. Signals `result_ready` and `error` communicate back to the UI thread.

### RULE 5: Card wrapper for all data sections
Any new page must wrap content in at least one card widget (white background, `1px solid #D4D4D4` border, `0px` radius, 32px title bar).

### RULE 6: Status indicators must be coloured circles, not just text
Status columns use coloured `●` labels. Never use text-only status.

### RULE 9: New pages register in the correct sidebar section
- Regular monitoring → "Standard" section
- Advanced/optional → "Advanced" section
- Offensive/elevated-privilege → "Security Audit" section

Use `self._nav_add_page(icon, label, widget)` after the correct `self._nav_add_section()` call.

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
| `ui/dashboard.py` | `_build_help_tab()` — "What's New" content |
| `tools/debug_launch.py` | `app.setApplicationVersion("X.Y.Z")` |
| `modules/rest_api.py` | `"version": "X.Y.Z"` in `/health` endpoint |
| `.github/winget/NetSentinel.NetSentinel.yaml` | `PackageVersion: X.Y.Z` |
| `.github/winget/NetSentinel.NetSentinel.installer.yaml` | `PackageVersion: X.Y.Z` |
| `.github/winget/NetSentinel.NetSentinel.locale.en-US.yaml` | `PackageVersion: X.Y.Z` |

`tests/test_version_consistency.py` enforces the Python-side files. Never bypass it.

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
- **21-F**: Register new pages in sidebar + README
- **21-G**: Add new modules to architecture.instructions.md layout table
- **21-H**: Commit message format: `feat: <description>  vX.Y.Z`

**Self-verification checklist before presenting to user:**
- [ ] Version bumped in all 9 files; consistency test passes
- [ ] README: badge, features, structure, changelog updated
- [ ] In-app Help "What's New" matches changelog
- [ ] BACKLOG.md: completed items removed, date updated
- [ ] All new modules have tests; full suite passes
- [ ] New pages registered in sidebar and listed in README

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

### RULE 25: Sidebar icon standard
All icons in `_nav_add_page()` must be geometric Unicode symbols — not photo-emoji.

✓ Acceptable: `⬡ ▲ ⚡ ⚙ ⊞ ⊙ ⊕ ◉ ◈ ⇄ ◎ ✓ ✚ ℹ ≡ ≣ ↗ ⊳ ⊲ ⌂ ⤳ ⏱`
✗ Forbidden: `🏠 📊 🔍 📡 🖥 🗺 💊 📋 🌪 🤖 👁 📟 📥 📜`

Rationale: geometric symbols render consistently at 12px in the collapsed 48px rail; emoji rendering varies by OS and looks chaotic at small sizes.

Section header icons (in `_nav_add_section()`) may use emoji since they are never shown in collapsed mode.

---

## Adding a New Scan Module

1. Create `modules/<name>.py` — pure Python, no PyQt imports
2. Create `workers/<name>_worker.py` — QThread, emits `result_ready(object)` and `error(str)`
3. Create `ui/pages/<name>_page.py` — receives `store: MetricStore` as constructor parameter
4. Register in `dashboard._build_tabs()` via `_nav_add_page(icon, label, widget)`
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
| Nav row index | `self._nav_<module>_row` |

---

## Testing Enforcement (RULES T1–T4) — BLOCKING

These are not optional. A PR is not complete without them.

### RULE T1: Every new module file needs a test file
Every new `modules/<name>.py` must have a corresponding `tests/test_<name>.py`
in the same PR. Minimum coverage: one import test + one behavioural test for
the primary function or class.

### RULE T2: Every new worker needs a start/stop lifecycle test
Every new `workers/<name>_worker.py` must have at minimum:
1. An import test
2. An instantiation test
3. A `start()` → brief wait → `stop()` → assert `not w.isRunning()` test

Rationale: catches hidden import errors that only surface inside a PyInstaller bundle.

### RULE T3: Every bug fix needs a regression test
Every bug fix must include a new `tests/test_*.py` entry that:
- Fails on the pre-fix code
- Passes on the fixed code

### RULE T4: _smoke_test() in app.py must stay current
Add every new module and worker to `_smoke_test()` in `app.py` whenever one is
created. The smoke test must import the module and verify it doesn't crash on import.

---

## Release Integrity (RULES R1–R3) — BLOCKING

### RULE R1: installer.iss version matches app.py before tagging
Before pushing any git tag, `installer.iss` `MyAppVersion` must already equal the
version in `app.py`. The CI patch step is a safety net, not the process.
Run `tests/test_version_consistency.py` locally before tagging.

### RULE R2: Winget locale manifest must always be the full version
Both the static `.github/winget/NetSentinel.NetSentinel.locale.en-US.yaml` and the
CI-generated copy must contain all fields: `Description`, `Tags`, `Moniker`,
`PublisherUrl`, `PublisherSupportUrl`, `PackageUrl`, `LicenseUrl`, `ReleaseNotesUrl`.
The minimal skeleton loses community repo metadata on every release.

### RULE R3: Ookla.Speedtest.CLI is ExternalDependencies, never PackageDependencies
In all winget manifests. `PackageDependencies` blocks the install if the package
is absent from the index. A broken install is the highest-severity user-facing bug.

---

## UX Baseline (RULES UX1–UX4)

### RULE UX1: New pages must show content within 200 ms
Use MetricStore cached data for the initial render. Start the worker after the
page is visible and update via signal. Never show a blank panel on navigation.

### RULE UX2: Slow and destructive actions must have a visible loading state
Any action > 500 ms must show a spinner, progress bar, or `"Running…"` button
state before the operation starts. Never leave the UI silently waiting.

### RULE UX3: Every scan result table must have a right-click context menu
Minimum items: **Copy** (copies row as text) and **How to Fix** (opens a
plain-English remediation panel). Use `customContextMenuRequested` signal.

### RULE UX4: Ctrl+F always focuses the sidebar search
New pages must not intercept or consume Ctrl+F. The global shortcut bound to
`Dashboard._focus_nav_search()` must remain effective from every page.

### RULE UX5: Never use setFixedHeight on widgets that contain text
Do not call `setFixedHeight()` on any widget whose content is text or contains
child text labels. Fixed heights cause text to overflow or be clipped when the
font size or number of lines changes.

**WRONG:**
```python
card.setFixedHeight(90)   # clips text if value label is large
```

**CORRECT:**
```python
card.setMinimumHeight(100)   # allows the widget to grow with its content
card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
```

This applies to: cards, status bars, table headers, banner strips, dialog rows,
and any layout item that renders a `QLabel`. Use `setFixedHeight` only for purely
graphic widgets (icon buttons, coloured separators, chart canvases) where height
is controlled by the drawing surface, not by text content.

### RULE UX6: Always use parented QTimer — never QTimer.singleShot(delay, slot)
`QTimer.singleShot(0, self._method)` creates an **unparented** timer. On Linux,
Qt's event loop may process the widget's `DeferredDelete` before the timer fires,
leaving a dangling pointer that corrupts the heap (SIGABRT ~30 tests later).
Windows is more forgiving, so this bug only manifests in CI or on Linux/macOS.

**WRONG:**
```python
QTimer.singleShot(0, self._preload)   # unparented — can fire after widget deleted
```

**CORRECT:**
```python
_t = QTimer(self)          # parented — destroyed automatically with the widget
_t.setSingleShot(True)
_t.timeout.connect(self._preload)
_t.start(0)
```

Additionally, add a `RuntimeError` guard at the top of any deferred slot:
```python
def _preload(self) -> None:
    try:
        self.objectName()   # raises RuntimeError if C++ object already deleted
    except RuntimeError:
        return
    ...
```

---

## Dual Audience — Home User and Professional (RULES A1–A3)

### RULE A1: Plain-English summary + technical detail view for every feature
Scan results must have two levels: a plain-English summary visible by default,
and full technical detail (MACs, RTTs, OIDs, raw values) behind a collapsible
section or "Details" button. Never hide data entirely.

### RULE A2: Error messages must be translated — no raw exceptions in the UI
All worker `error` signals must be caught and rendered as actionable text: what
failed, why, and what the user should try. No raw tracebacks, `AttributeError`,
or Python internals may appear in any QLabel, QMessageBox, or status bar.

### RULE A3: Severity labels use the canonical four only
All risk/severity strings visible in the UI must be one of: **Info, Warning,
High, Critical**. Map any non-standard string to the canonical set. Do not
invent new labels (`SEVERE`, `NOTICE`, `ALERT`, etc.).

---

## Long-Term Architecture Health (RULES AH1–AH4)

### RULE AH1: Module files must not exceed 600 lines
If a file under `modules/` reaches 600 lines, split it. Large files indicate
mixed concerns. Measure with `(Get-Content modules\<name>.py).Count` on Windows.

### RULE AH2: Workers must not block for more than 5 seconds without a progress signal
Any operation expected to take > 5 seconds must emit `progress(str)` or `status(str)`
at least once every 5 seconds. Long polling loops must use `msleep()` and check
a `_running` flag on each iteration.

### RULE AH3: Zero raw hex strings outside ui/styles.py and modules/colours.py — CI enforced
```
# This must return 0 matches before any commit:
grep -rP '"#[0-9a-fA-F]{6}"' modules/ ui/ --include="*.py" \
  --exclude="styles.py" --exclude="colours.py"
```
UI colours → `ui/styles.py`. Export/chart/HTML colours → `modules/colours.py`.
Add the colour to the appropriate file first if it does not exist.

### RULE AH4: Optional dependencies must be lazy-imported with a graceful fallback
Do not import optional packages (`nmap`, `scapy`, `speedtest`, npcap-dependent
libs) at module level. Lazy-import inside the function that needs them:

```python
def _run_nmap_scan(host):
    try:
        import nmap
    except ImportError:
        return []   # graceful fallback — caller handles empty result
    ...
```
The fallback must degrade gracefully (empty results, error signal, or install
banner) — never crash on import.

---

## UI Wiring Completeness (RULES W1–W6)

These rules prevent silent dead code — buttons that do nothing, signals that fire
into the void, and nav items that are unreachable.

### RULE W1: Every QPushButton must have a `.clicked.connect()` within the same init block
**Exception:** buttons that are explicitly disabled until a precondition is met, which
must have a `# WIRED LATER:` comment with the reason.

**Checklist when adding a button:**
- [ ] `btn.clicked.connect(...)` exists in the same `__init__` or `_setup_ui` scope
- [ ] Target method exists in the same or parent class
- [ ] If the target is in a different class, the wiring goes in the constructor of the
  outermost class (e.g. `dashboard.py` wires `home_page._btn_scan.clicked.connect(...)`)

```python
# WRONG — silent dead button
self._btn_scan = QPushButton("Scan now")

# CORRECT — wired immediately
self._btn_scan = QPushButton("Scan now")
self._btn_scan.clicked.connect(self._start_full_scan)

# ALSO CORRECT — wired by parent class, documented
self._btn_scan = QPushButton("Scan now")
# WIRED BY PARENT: Dashboard.__init__ connects _btn_scan → _start_full_scan
```

### RULE W2: Every pyqtSignal must have at least one .connect() in the codebase
Before adding a new `pyqtSignal`, search the codebase for where it will be connected.
A signal with no connections is dead code.

**Audit command (run before commit):**
```powershell
# Find signals that are emitted but never connected:
# 1. List all emit() call sites
# 2. Verify each has a matching .connect() somewhere
grep -rn "\.emit(" ui/ workers/ --include="*.py" | sed 's/\.emit(.*//' | sort -u
```

### RULE W3: Every new UI page must be reachable from at least one nav mode
When creating a new page (`ui/pages/<name>_page.py`):
- Add it to `_build_tabs()` via `_nav_add_page(icon, label, widget)`
- Verify it appears in Home, Standard, or Pro nav (at minimum one)
- Verify `_nav_go_to("Label")` can find it

Pages registered only in `_build_tabs()` but not in any `_build_*_nav()` are
**invisible** — the user can never reach them.

### RULE W4: Nav mode content must match the mockup exactly
The three nav modes are defined by `ui/dashboard.py` `_build_home_nav()`,
`_build_standard_nav()`, `_build_pro_nav()`. Each mode's content is frozen:

| Mode | Nav items | Home page |
|---|---|---|
| Home | Home · Speed Test · DNS & Stability · Devices · Reports | Hero card + 3 mini-cards + alerts |
| Standard | Quick Access · Discover · Monitor · Reports & Export | "WHAT EACH SECTION GIVES YOU" feature grid |
| Pro | Quick Access · Standard · ⚠ Security Audit (TCP/UDP scan, CVE, Threat Intel, TLS & exposure, Login Test) | "SECURITY AUDIT CAPABILITIES" 4-card grid |

**Pro mode must NOT contain ISP Report** — it is Standard-mode only.
**Pro nav label for the cert/threat page is "TLS & exposure"** — not "TLS Certificates".

### RULE W5: Signal-to-slot cross-page connections must be made in app.py or dashboard.__init__
Never connect a signal from PageA to a slot in PageB inside either page's own code.
Cross-page wiring belongs at the top level:

```python
# In dashboard.__init__ — correct location
self._speed_test_page.test_completed.connect(self._home_page.on_speed_result)
self._home_page._btn_scan.clicked.connect(self._start_full_scan)

# WRONG — PageA should not import or reference PageB
class SpeedTestPage:
    def _on_result_ready(self, r):
        self._home_page.on_speed_result(r)  # ← PageA should not own PageB
```

### RULE W6: Wiring audit — run before every commit
Open `ui/dashboard.py` and `app.py`, then verify:

1. **Every `QPushButton` in `ui/pages/`** — grep: `QPushButton\(` — has a corresponding
   `.clicked.connect(` in the same file OR a `# WIRED BY:` comment.

2. **Every `pyqtSignal` in `ui/pages/` and `workers/`** — grep: `pyqtSignal` — has a
   `.connect(` somewhere in `dashboard.py` or `app.py`.

3. **Every `_nav_ref` and `_nav_add_page` label** — the widget argument must already
   be registered in `self._stack` (added via `_build_tabs()`). Grep for the widget name
   and confirm `self._stack.addWidget(...)` exists.

4. **Every slot listed in a page's public API** (methods starting with `on_`) must have
   a corresponding `.connect(` somewhere. Slots with no connection are dead code.

**Quick audit script:**
```powershell
# Find on_* slots that are never connected
$slots = Select-String -Path ui\pages\*.py -Pattern "def on_\w+" | ForEach-Object { $_.Matches[0].Value -replace "def ","" }
foreach ($slot in $slots) {
    $hits = Select-String -Path ui\dashboard.py,app.py -Pattern "\.connect.*$slot|$slot.*connect"
    if (-not $hits) { Write-Warning "UNWIRED SLOT: $slot" }
}
```

