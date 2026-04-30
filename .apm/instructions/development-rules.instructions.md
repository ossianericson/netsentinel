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

### Step 2 — Verify the app starts
```powershell
python tools/debug_launch.py
```
Read `netsentinel_debug.log` and confirm:
- `Dashboard() instantiated OK` is present
- `window.show() called OK` is present
- No `UNHANDLED EXCEPTION` block in the log

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

## Naming Conventions

| Element | Pattern |
|---|---|
| Table variables | `self._<module>_table` |
| Status label | `self._<module>_status` |
| Worker reference | `self._<module>_worker` |
| Result cache | `self._<module>_result` |
| Nav row index | `self._nav_<module>_row` |
