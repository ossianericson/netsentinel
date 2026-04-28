---
applyTo: "**/*.py"
---

# NetSentinel — Development Rules for AI Agents

---

## COMMIT GATE — Mandatory Before Every Commit or Push

**These steps are BLOCKING. Do not commit, tag, or push until ALL three are complete.**

### Step 0 — Version consistency check (run FIRST if any version was changed)
If any version number was modified in this session, run this before anything else:
```powershell
python -m pytest tests/test_version_consistency.py -v
```
All six files must show the same version as `app.py`. Fix every mismatch before continuing.

### Step 1 — Run the full test suite
```powershell
python -m pytest tests/ -q
```
All tests must pass. Fix any failures before proceeding. Do not skip or ignore failures.

### Step 2 — Verify the app starts (GUI launch check)
```powershell
python tools/debug_launch.py
```
Read `netsentinel_debug.log` and confirm:
- `Dashboard() instantiated OK` is present
- `window.show() called OK` is present
- No `UNHANDLED EXCEPTION` block in the log

### Step 3 — UI sign-off
**Tell the user:** "Tests pass, app launched cleanly — please verify the window looks correct and say 'looks good' to proceed."

Wait for the user's visual confirmation before proceeding to Step 4.  
Accepted phrases for UI sign-off only: "looks good", "lgtm", "fine", "ok".  
Do NOT treat silence, a new question, or a feature request as approval.

### Step 4 — Explicit commit instruction (HARD GATE)
**Do NOT run `git commit`, `git push`, `git tag`, or any destructive git operation unless the user explicitly says so.**

Required trigger phrases (case-insensitive): "commit to repo", "push to repo", "go ahead and commit", "push it", "commit it".  
"looks good", "lgtm", or any non-git confirmation phrase does **not** grant permission to commit or push.  
If the user's message is ambiguous, ask: "Should I commit and push this to the repo?" — do not assume yes.

---

## UI Design Vision

NetSentinel targets the **Datadog / PRTG / Zabbix** aesthetic — a professional network monitoring console, not a form-based desktop app. Every screen must feel operational and information-dense.

### Top bar (action ribbon)
- Single-row, 52px tall, dark navy (`#141B2D`)
- Left zone: brand name + subtitle (text only)
- Centre: one **expanding** search/filter input — dark background (`SIDEBAR_HOVER`), 34px tall, blends seamlessly into the bar; no white boxes on dark backgrounds
- Rarely-changed controls (scan durations, module toggles) live in a **`⚙ Scan Settings` dropdown** — NOT inline in the bar
- Right zone: verdict badge → `⚠` admin icon (tooltip only, no text) → `Run Full Scan` → `Export` → mode toggles → utility icons
- All elements exactly 34px height — no mixed sizes in the same row

### Sidebar navigation
- `QListWidget` + `QStackedWidget` — never `QTabWidget`
- Width 220px, dark navy (`#1F2B3E`), section headers ALL CAPS

### Content pages
- Light off-white background (`#F4F4F4`)
- Every data section in a white card (`QFrame#card`) — 1px border, 0px radius
- Pages open with KPI summary tiles (large number + colour), then the main table

### Explicitly forbidden
- Inline spinboxes/checkboxes floating in the top bar
- White/light input boxes on the dark nav bar (use `SIDEBAR_HOVER` background)
- Mixed button heights in the same row
- Font sizes above 18px in data views
- Gradients, glow effects, drop shadows on data elements
- Dark backgrounds for content areas or tables

---

## Non-Negotiable Rules

### RULE 1: Single colour source
**Never** hardcode a hex colour string anywhere in `ui/dashboard.py`, `ui/live_graph.py`, or `ui/topology_widget.py`. Every colour must be imported from `ui/styles.py`. If a colour you need does not exist in `styles.py`, add it there first, then import it.

```python
# WRONG
label.setStyleSheet("color: #D93025;")

# CORRECT
from ui.styles import RED
label.setStyleSheet(f"color: {RED};")
```

### RULE 2: No QTabWidget for primary navigation
The application uses `QListWidget` (sidebar) + `QStackedWidget` (content). Do not replace this with `QTabWidget`. Do not add new `QTabWidget` instances to the main navigation flow.

### RULE 3: Table row height is 24px
All tables created with `_table()` must keep `verticalHeader().setDefaultSectionSize(24)`. Do not increase this. Information density is a primary design value.

### RULE 4: No blocking I/O on the main thread
All network operations must run in a `QThread` worker (see `workers/scan_worker.py`). Signals `result_ready` and `error` communicate back to the UI thread.

### RULE 5: Card wrapper for all data sections
Any new page added to the dashboard must wrap its content in at least one white card widget. A bare `QWidget` with a table floating on the content background is not acceptable.

The standard card pattern:
```python
card = QFrame()
card.setObjectName("card")
card_lay = QVBoxLayout(card)
card_lay.setContentsMargins(0, 0, 0, 0)
card_lay.setSpacing(0)

# Title bar
title_bar = QFrame()
title_bar.setObjectName("cardHeader")
title_bar.setFixedHeight(32)
tb_lay = QHBoxLayout(title_bar)
tb_lay.setContentsMargins(12, 0, 10, 0)
title_lbl = QLabel("Card Title")
title_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; font-weight:bold; font-size:13px;")
tb_lay.addWidget(title_lbl)
tb_lay.addStretch()

card_lay.addWidget(title_bar)
card_lay.addWidget(your_table_or_content)
```

### RULE 6: Status indicators must be coloured circles, not just text
Whenever displaying device status, scan verdict, or risk level in a table, the first or second column must contain a coloured indicator. Use `QLabel` with a circular stylesheet or a `QTableWidgetItem` with a coloured icon, not just coloured text.

```python
# Pattern for a status dot in a table cell
dot = QLabel("●")
dot.setStyleSheet(f"color: {GREEN}; font-size: 12px;")
table.setCellWidget(row, 0, dot)
```

### RULE 7: Admin warning is a thin bar, not a card
The admin warning must be `setFixedHeight(28)`. It must not grow. Do not add word-wrap or multi-line text that expands the height.

### RULE 8: Buttons in the top bar are 34px high
The top application bar is `setFixedHeight(52)`. All action buttons inside it use `setFixedHeight(34)`. Do not use 54px buttons — they overflow the bar.

### RULE 9: New pages must register in the correct sidebar section
- Regular monitoring features → "Standard" section
- Advanced/optional tools → "Advanced" section (hidden until Advanced Mode enabled)
- Offensive/elevated-privilege features → "Security Audit" section (hidden until Audit Mode enabled)

Use `self._nav_add_page(label, widget, hidden=True/False)` after the correct `self._nav_add_section()` call.

### RULE 10: matplotlib charts follow the light theme
```python
# Correct chart setup
fig = Figure(facecolor="#FFFFFF")
ax = fig.add_subplot(111)
ax.set_facecolor("#FAFBFC")
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.spines["bottom"].set_color("#D4D4D4")
ax.spines["left"].set_color("#D4D4D4")
ax.tick_params(colors="#5A6A7A", labelsize=9)
ax.grid(True, color="#E8EDF2", linewidth=0.8, linestyle="-")
ax.set_title("Title", color="#1A3A5C", fontsize=11, fontweight="bold")
```

## Version Bump Checklist

### RULE 11-A: Never bump the version mid-branch

**Version bumps happen exactly once: at merge/release time, not during feature development.**

- All work on a feature branch shares the same version number (the one it branched from, or the one it will ship as).
- Do **not** create separate version entries in `apm.yml`, `README.md`, or any other file for each individual backlog item implemented on the same branch.
- Do **not** increment `X.Y.Z` between backlog items on the same branch — accumulate all changes under one combined changelog entry.
- The version is only incremented once, in the single commit that merges or releases the branch.

**Correct pattern:**
```
branch: feature/my-feature
  commit A — item 7 done — version stays 1.4.0, apm.yml gets a new bullet in 1.4.0 changes
  commit B — item 8 done — version stays 1.4.0, apm.yml gets another bullet in 1.4.0 changes
  commit C — item 9 done — version stays 1.4.0, same
merge → 1.4.0 ships
```

**Wrong pattern (do not do this):**
```
branch: feature/my-feature
  commit A — item 7 done — bumps to 1.4.1  ← WRONG
  commit B — item 8 done — bumps to 1.4.2  ← WRONG
  commit C — item 9 done — bumps to 1.4.3  ← WRONG
```

**RULE 11: When bumping the application version, update ALL of the following — no exceptions.**

> **AI AGENT TRIGGER:** If you change the version string in ANY of the files below, you MUST immediately
> check and update every other file in this table before proceeding with anything else.
> Do not wait to be asked. Do not commit until all files are in sync.
> Run `python -m pytest tests/test_version_consistency.py -v` to verify before moving on.

Every version number lives in exactly these locations. Update them all atomically in one commit.

| File | What to change |
|---|---|
| `app.py` | `app.setApplicationVersion("X.Y.Z")` |
| `cli.py` | `_VERSION = "X.Y.Z"` |
| `apm.yml` | `version: X.Y.Z` |
| `installer.iss` | `#define MyAppVersion "X.Y.Z"` |
| `build.bat` | echo version string in banner line |
| `build.sh` | echo version string in banner line |
| `README.md` | badge/link on line ~25 and `### vX.Y.Z (current)` changelog entry |
| `ui/dashboard.py` | `_build_help_tab()` — "What's New" section content |
| `tools/debug_launch.py` | `app.setApplicationVersion("X.Y.Z")` |

### What to put in each version entry

**README.md changelog** (`## What's new` section):
- Rename previous `### vX.Y.Z (current)` to `### vX.Y.Z`
- Add new `### vX.Y.Z (current)` at the top with bullet points for each user-visible change
- Do not skip versions — every released tag must have an entry

**In-app Help page** (`_build_help_tab()` in `ui/dashboard.py`):
- Update the "What's New" `_section(...)` card with the same bullet points
- The version string in the card title must match `QApplication.applicationVersion()`

### Automated enforcement

`tests/test_version_consistency.py` checks all six files above against `app.py` at test time.
If any file is missed, the test suite will fail. **Never bypass this test.**

```powershell
python -m pytest tests/test_version_consistency.py -v
```

### Commit message format for version bumps
```
chore: bump version to vX.Y.Z

- <change 1>
- <change 2>
```

---

## Update-Check Comparison — RULE 19

**RULE 19: The in-app update checker must use strict semver tuple comparison — never string equality.**

The check fires only when the remote version is **strictly newer** than the running version.

```python
# CORRECT
def _ver(s):
    try:
        return tuple(int(x) for x in s.split("."))
    except ValueError:
        return (0,)
if latest and _ver(latest) > _ver(current):
    self._show_update_bar(latest)

# WRONG — fires when local is ahead of remote (e.g. dev build)
if latest and latest != current:
    self._show_update_bar(latest)
```

This applies to BOTH check locations in `ui/dashboard.py`:
- The background thread started from `__init__` (startup check)
- The `_check_for_updates()` method (manual Help tab button)

---

## Winget CI Gate — RULE 20

**RULE 20: The winget submission job must always live inside `release.yml` as a final job with `needs: [release]`. Never use a separate workflow file triggered by `workflow_run`.**

Correct structure in `.github/workflows/release.yml`:
```yaml
jobs:
  build-windows: ...
  build-macos:   ...
  build-linux:   ...
  release:
    needs: [build-windows, build-macos, build-linux]
    ...
  submit-winget:
    needs: [release]   # ← only runs after a successful release
    runs-on: windows-latest
    steps: ...
```

Reasoning:
- A separate `winget-submit.yml` triggered via `workflow_run: types: [completed]` queues on **every** build completion (including failures), creating noise in the Actions tab.
- `needs: [release]` ensures the job never queues unless the full build + release chain succeeded.
- Do NOT add a `workflow_dispatch` input to the winget job — manual retries are not needed because a re-tag will re-trigger the whole chain.

---

## Release Checklist — RULE 21

**RULE 21: When any new feature, fix, or improvement is shipped — with or without an explicit version bump request — the agent MUST autonomously complete every item in this checklist WITHOUT being asked. Do not wait for the user to direct individual steps.**

This rule exists because the user should never have to say "update the README", "update the changelog", "update What's New", "update BACKLOG", or any equivalent. The agent does all of it automatically as part of shipping.

---

### 21-A: Version files (always)

If new work warrants a version bump (any user-visible feature or fix):
1. Bump the version in ALL files listed in RULE 11 (app.py, cli.py, apm.yml, installer.iss, build.bat, build.sh, debug_launch.py)
2. Run `tests/test_version_consistency.py` to confirm — **fail = do not proceed**

If the work is minor/internal and the user has not asked for a bump, note that a bump may be warranted and ask once.

---

### 21-B: README.md (always — no exceptions)

The README must be updated for **every** set of changes before committing. Check each section:

| Section | What to update |
|---|---|
| Install badge / version line (~line 25) | New version number `v X.Y.Z` |
| `## Features` / feature tables | Add any new sidebar pages; update capability descriptions |
| `## Project structure` code block | Add any new files in `modules/`, `ui/pages/`, `workers/`, `tests/` |
| `## What's new` changelog | Rename old `(current)` tag; add new `### vX.Y.Z (current)` section at top |
| `## How it was built` timeline table | Append a row for significant milestones (do not delete existing rows — RULE 13) |

Rules for the changelog entry:
- Group by theme (e.g. "Alerting & Notifications", "UI", "Backend", "Tests")
- Use plain bullet points — one line per user-visible change
- Do not include internal refactors, test fixes, or comment changes in the changelog

---

### 21-C: In-app Help "What's New" (always)

In `ui/dashboard.py`, find the `_build_help_tab()` method and update the "What's New" `_section(...)` card:
- The card title must say `What's New in vX.Y.Z`
- The bullet list must match the README changelog entry (same items, same grouping)
- The version string must match `app.setApplicationVersion(...)` exactly

---

### 21-D: BACKLOG.md (always)

- **Remove** any Tier 1 or Tier 2 items that were completed in this release
- **Add** any new backlog items discovered or discussed during implementation
- Update the `Last updated:` date at the top
- If Tier 1 is now empty, promote the top Tier 2 item(s) to Tier 1

---

### 21-E: Test coverage (always)

For every new module or page:
- Create `tests/test_<module_name>.py` if it does not already exist
- New public functions must have at least one passing test
- Run the full suite (`python -m pytest tests/ -q`) — all must pass before proceeding
- Report the new test count to the user ("X tests passing")

---

### 21-F: Sidebar registration (when adding pages)

When a new UI page is added:
- It must be registered in `ui/dashboard.py` with `_nav_add_page()`
- It must appear in the correct section (Standard / Advanced / Security Audit — RULE 9)
- It must be listed in the README `## Features` table under the correct section
- It must be listed in the README `## Project structure` block

---

### 21-G: `.github/instructions/architecture.instructions.md` (when adding modules)

When a new module is added to `modules/`:
- Add it to the `modules/` layout table in the architecture instructions file
- One-line description only — keep entries concise

---

### 21-H: Commit message (when committing)

Format every version-bump commit as:
```
feat: <short description of main feature>  vX.Y.Z

- <item 1>
- <item 2>
...
```

For non-version fix commits:
```
fix: <what was broken and how it was fixed>
```

---

### Checklist summary (copy-paste for self-verification before commit)

Before marking work done and presenting to the user for sign-off, the agent must be able to answer **YES** to every applicable item:

- [ ] Version bumped in all 7 files (RULE 11) and consistency test passes
- [ ] README: version badge updated
- [ ] README: feature tables updated (new pages/capabilities listed)
- [ ] README: project structure updated (new files listed)
- [ ] README: changelog entry added for this version
- [ ] README: "How it was built" table untouched (RULE 13)
- [ ] In-app Help "What's New" matches the changelog
- [ ] BACKLOG.md: completed items removed, new items added, date updated
- [ ] All new modules have tests; full suite passes
- [ ] New pages registered in sidebar + listed in README
- [ ] No password / API key / token written to QSettings, MetricStore, or any file (RULE 22)
- [ ] No credential visible in any log output (RULE 22-B)
- [ ] All new secret-input QLineEdit fields use EchoMode.Password (RULE 22-D)
- [ ] Serialised dicts/dataclasses strip secret fields before write or display (RULE 22-C)
- [ ] Every new modules/*.py is listed in NetSentinel.spec hiddenimports (RULE 23)
- [ ] Every new workers/*.py is listed in NetSentinel.spec hiddenimports (RULE 23)
- [ ] Every new ui/pages/*.py is listed in NetSentinel.spec hiddenimports (RULE 23)
- [ ] Every new requirements.txt package is in the collect_all loop in NetSentinel.spec (RULE 23)

**Do not ask the user to do any of these. Do them.** or proper UTF-8 Unicode codepoints. Never paste text that contains Unicode replacement characters (U+FFFD `?`) or broken multi-byte sequences.**

The corruption pattern seen in this project:
- `??` in Markdown = a 4-byte emoji (e.g. 🔍, 🌊, 📊) that was corrupted to two `?` replacement chars
- `?` mid-sentence = an em-dash `—`, en-dash `–`, arrow `→`, or multiplier `×` corrupted to one `?`

Rules:
- Always use the actual Unicode character, not an approximation: `—` not `-`, `→` not `->`, `×` not `x`
- Copy emojis from the `_nav_add_page()` calls in `ui/dashboard.py` — they are the canonical source for tab emoji labels
- When editing README.md, verify no `?` replacement characters exist before committing
- If an editor strips non-ASCII, write the Unicode escape (e.g. `\u2014` for `—`) then convert before saving

---

## Build Origin Story — Do Not Remove

The `## How it was built` section in `README.md` documents that NetSentinel was built in a single afternoon on **Saturday, 26 April 2026** using Claude Sonnet 4.6 as a development accelerator, and expanded the following day (Sunday 27 April) into v1.0.4.

**This section must be preserved in all future README edits.** It is important product storytelling context.

Rules:
- Never delete or truncate the `## How it was built` section from `README.md`
- Never merge it into another section or rename it away
- When new significant milestones are added, append a row to the timeline table rather than replacing it
- The distinction between "the engineering work" (architecture, decisions, diagnosis) and "the model handled the typing" must remain verbatim — do not rephrase or soften it

---

## Naming Conventions

| Element | Pattern |
|---|---|
| Table variables | `self._<module>_table` |
| Status label | `self._<module>_status` |
| Worker reference | `self._<module>_worker` |
| Result cache | `self._<module>_result` |
| Nav row index | `self._nav_<module>_row` |

## Adding a New Scan Module

1. Create `modules/<name>.py` — pure Python, no PyQt imports
2. Create a worker in `workers/scan_worker.py` or inline QThread subclass
3. Add page builder method `_build_<name>_tab()` in `ui/pages/<name>_page.py`
4. Register the page in `_build_tabs()` under the correct sidebar section
5. Add result cache `self._<name>_result = None` in `__init__`
6. Wire the worker's `result_ready` signal to a `_on_<name>_result()` slot
7. All colours used must come from `ui/styles.py`

### RULE 16: Never use `setFixedHeight` on buttons inside fixed-height bars
Buttons placed inside a fixed-height container (e.g. 28px warning bars, 52px top bar) must **not** use `setFixedHeight()`. The fixed parent height already constrains vertical space; adding a smaller `setFixedHeight` on the child causes PyQt6 to clip the button's text on the right edge rather than wrapping.

```python
# WRONG — 20px child inside 28px parent → text clipped
btn.setFixedHeight(20)

# CORRECT — let the button fill the bar vertically
btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
```

Also ensure the layout's right margin is at least **16px** (not 10px) so button text is never flush against the widget boundary.

### RULE 17: Always pass a parent when constructing widgets inside tab/page builders
In PyQt6, a `QWidget` (or `QFrame`) created without a parent is briefly treated as a top-level window. If this happens inside `_build_*_tab()` during startup, the widget flashes on screen as a thin floating window for a few milliseconds before `addWidget()` reparents it. Always pass `parent=w` (the container widget) at construction time.

```python
# WRONG — no parent → brief top-level flash at startup
lay.addWidget(MyBanner())

# CORRECT — parent set immediately, never becomes top-level
lay.addWidget(MyBanner(parent=w))
```

### RULE 18: Always store KPI tile parent widgets in a local variable
When using a helper that returns `(tile_widget, value_label)`, always capture the tile widget in a named variable before calling `addWidget()`. Never call `.parent()` on the label to retrieve it — PyQt6 may garbage-collect the C++ object if the Python reference is dropped, causing a `RuntimeError: wrapped C/C++ object has been deleted`.

```python
# WRONG — tile widget dropped, .parent() crashes
_, self._kpi_total = _kpi_tile("Total")
row.addWidget(self._kpi_total.parent())   # ❌ RuntimeError

# CORRECT — tile kept alive in a local variable
tile_total, self._kpi_total = _kpi_tile("Total")
row.addWidget(tile_total)                 # ✓
```

---

## RULE 22: Credential & Secret Security — NON-NEGOTIABLE

**This rule is absolute and permanent. It has zero exceptions. Every new feature, every new module, every future backlog item must comply unconditionally.**

NetSentinel is a local desktop tool. It must NEVER become a credential store, a keylogger, or a data exfiltration risk. The following rules are binding for all code written for this project:

### 22-A: Never persist credentials to disk in plaintext

```python
# WRONG — credential written to SQLite, INI, JSON, or any file
store.set("email_password", password_text)
settings.setValue("smtp/password", password_edit.text())
json.dump({"api_key": key}, f)

# CORRECT — use the OS credential store exclusively
import keyring
keyring.set_password("NetSentinel", "smtp_password", password_text)
password = keyring.get_password("NetSentinel", "smtp_password")
```

- **`QSettings` / `NetSentinel.ini`**: forbidden for any password, API key, token, or secret.
- **`MetricStore` / `NetSentinel.db`**: forbidden for any password, API key, token, or secret.
- **Any plain file** (JSON, CSV, txt, log): forbidden for any password, API key, token, or secret.
- **Only permitted storage**: OS keychain via `keyring` library — Windows Credential Manager, macOS Keychain, Linux Secret Service.

### 22-B: Never log credentials

```python
# WRONG
logging.debug(f"Connecting with password={password}")
print(f"API key: {api_key}")

# CORRECT — log the action, never the value
logging.debug("SMTP login attempt for user=%s", username)
```

- Log files (`netsentinel_debug.log`, CSV logger) must never contain passwords, tokens, or API keys.
- String representations of config objects that contain credentials must mask the secret field:

```python
def __repr__(self):
    return f"EmailChannel(host={self.host}, user={self.username}, password=***)"
```

### 22-C: Scrub credentials from serialisation

When serialising configuration to share with the delivery log, export, or any UI display:

```python
# CORRECT — existing pattern in notification_router.py, must be followed everywhere
d = dataclasses.asdict(channel)
d.pop("password", None)
d.pop("api_key", None)
d.pop("token", None)
```

Any dict, dataclass, or object that holds a secret **must** have the secret field removed before it is:
- Written to MetricStore
- Written to a log file
- Serialised to JSON for export
- Displayed in any UI widget (table, label, tooltip)

### 22-D: UI password fields must always be masked

```python
# CORRECT
password_edit = QLineEdit()
password_edit.setEchoMode(QLineEdit.EchoMode.Password)
```

Never use `QLineEdit.EchoMode.Normal` for a field that accepts a password, API key, or token.

### 22-E: No credentials in source code or version control

- Hardcoded passwords, API keys, tokens, and secrets are forbidden in all source files.
- `.gitignore` must exclude `NetSentinel.ini`, `NetSentinel.db`, and any file matching `*.key`, `*.pem`, `*.pfx`, `*.p12`, `secrets.*`.
- CI/CD pipeline secrets must use GitHub Actions secrets — never inline in workflow YAML.

### 22-F: Scope of credentials to localhost only

For features that start local services (REST API, SNMP trap receiver, syslog receiver):
- Bind exclusively to `127.0.0.1` — never `0.0.0.0` unless the user explicitly enables it with a visible warning in the UI.
- API keys for local endpoints must be randomly generated (minimum 32 bytes, `secrets.token_hex(32)`) and stored in the OS keychain, not in INI or DB.

### 22-G: Dependency on `keyring`

`keyring` must be added to `requirements.txt` when any feature that stores user-supplied secrets is shipped. If `keyring` is unavailable at runtime, the feature must degrade gracefully (show a warning, disable the secret field) rather than falling back to plaintext storage.

```python
try:
    import keyring
    _KEYRING_AVAILABLE = True
except ImportError:
    _KEYRING_AVAILABLE = False

def save_secret(service: str, key: str, value: str) -> bool:
    if not _KEYRING_AVAILABLE:
        # Never fall back to plaintext — fail safe
        return False
    keyring.set_password("NetSentinel", f"{service}/{key}", value)
    return True
```

### 22-H: Checklist addition — security review before every commit

Add this check to the pre-commit gate (RULE 21 checklist):
- [ ] No password / API key / token written to QSettings, MetricStore, or any file
- [ ] No credential visible in any log output
- [ ] All new `QLineEdit` fields for secrets use `EchoMode.Password`
- [ ] Serialised dicts/dataclasses strip secret fields before write or display
- [ ] No hardcoded credentials in source files

---

## RULE 25: Exe debugging protocol — exact steps in order

**This rule exists because "it works in source" was said 10+ times while the exe was broken. Follow this exact protocol whenever the exe behaves differently from `python app.py`.**

### 25-A: The build environment MUST match GitHub Actions

GitHub Actions uses **Python 3.11**. The local build MUST use `.venv311`:
```powershell
# One-time setup (already done on this machine):
py -3.11 -m venv .venv311
.venv311\Scripts\pip install -r requirements.txt pyinstaller

# Every build:
.venv311\Scripts\python.exe -m PyInstaller --clean -y NetSentinel.spec
```
**Never build with the system `python` command** — it may be a different version and will produce different bytecode. If the system python is 3.12+ and the exe crashes on ssl/asyncio/typing, the build environment is wrong.

### 25-B: PyInstaller ALWAYS needs `--clean -y` — no exceptions

Without `--clean`: PyInstaller reuses cached `.pyc` bytecode from `build\NetSentinel\`. Source fixes are invisible in the exe even though the build says "uptodate". Every build command must be:
```powershell
.venv311\Scripts\python.exe -m PyInstaller --clean -y NetSentinel.spec
```
`build.bat` already enforces this. Never bypass it with a direct `pyinstaller` call.

### 25-C: Always wipe `dist\` AND kill the running exe before rebuilding

```powershell
Stop-Process -Name "NetSentinel" -Force -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
```
- If the exe is running, `NetSentinel.db` is locked → build fails with PermissionError
- Old files in `dist\` from one-folder/one-file mode switches cause confusion about what you're actually testing

### 25-D: When the exe crashes or misbehaves — build debug first, THEN diagnose

```powershell
# Build with console window ON so errors print visibly:
$env:NETSENTINEL_DEBUG="1"
.venv311\Scripts\python.exe -m PyInstaller --clean -y NetSentinel.spec

# Run from terminal (not double-click) to see the console output:
.\dist\NetSentinel.exe
```
Read the console output. The Python traceback will name the exact file and line. Fix that. Do not guess.

### 25-E: Known exe-specific failure patterns and their fixes

| Symptom | Root cause | Fix |
|---------|-----------|-----|
| Speed test crashes with `fileno` or `ssl` error | `speedtest-cli 2.1.x` calls `ssl.wrap_socket()` removed in Python 3.12+ | `ssl.wrap_socket` shim in `modules/speed_tester.py` — requires Python 3.11 build env. The shim is at the top of the file and patches `ssl.wrap_socket` at import time. It ONLY works in the exe if built with Python 3.11 (`.venv311`). If built with Python 3.12+, the shim is irrelevant because `speedtest-cli` itself is also broken at a deeper level. |
| App starts but shows crash dialog immediately | `sys.stderr` is `None` in windowed builds; `_qt_message_handler` writes to it | Guard: `if sys.stderr is not None:` in `app.py` |
| Close button does nothing / app hangs on close | `QThread.terminate()` called without `w.wait()` after — QThread object destroyed while OS thread handle still alive → `STATUS_STACK_BUFFER_OVERRUN` | Call `w.wait(2000)` after every `w.terminate()` in `closeEvent` |
| CMD flash windows at startup or during scan | `subprocess.CREATE_NO_WINDOW` insufficient alone on some Windows builds | Add `STARTUPINFO` with `SW_HIDE` to every subprocess call on Windows |
| Exe starts but feature is broken despite source fix | PyInstaller cache reuse — `build\NetSentinel\` has old `.pyc` files | Always use `--clean -y`. Delete `build\NetSentinel\` manually if needed |
| Exe takes 40–60s to start | One-file mode: every launch decompresses to `%TEMP%` | Use `runtime_tmpdir` pointing to a fixed location so extraction is cached |
| Module `X` not found in exe | Module added to source but not to `hiddenimports` in `NetSentinel.spec` | Add to spec — see RULE 23 |

### 25-F: After every fix — verify with timestamps, not assumptions

```powershell
Get-Item dist\NetSentinel.exe | Select-Object LastWriteTime, @{n='MB';e={[math]::Round($_.Length/1MB,1)}}
```
The timestamp must be newer than when the fix was applied. If it is not, the build did not run or used cache.

---

## RULE 24: Never claim a fix is working without proof — HARD GATE

**This rule exists because telling the user "it's fixed" without verifying causes repeated failed builds, wasted time, and broken trust.**

### 24-A: You may NOT say a fix is working unless you have verified it

"Verified" means one of:
- The exe timestamp in `dist\` is newer than before the fix AND the post-build smoke test passed
- `python app.py` was run via `tools/debug_launch.py` and the log shows no `UNHANDLED EXCEPTION`
- The specific failing feature was tested and produced the expected output

Saying "the fix is in this build" or "this should work now" without running any of the above is **forbidden**.

### 24-B: When a build hangs or fails, always get the debug log first

Do NOT retry the same command hoping it will work. If a build stalls at 0% CPU or fails:

```powershell
# Step 1 — kill the stuck build
# Step 2 — get the actual error
python -m PyInstaller NetSentinel.spec --log-level DEBUG 2>&1 | Tee-Object build_debug.log
# Step 3 — read build_debug.log to find the real failure line
# Step 4 — fix the root cause, then rebuild
```

Never re-run the same failing build command more than once without reading the error output first.

### 24-C: When an exe is reported broken by the user, reproduce it before claiming a fix

If the user reports an error in the compiled exe:
1. Read the exact error message carefully
2. Find the exact line in source that causes it (grep/read the file — do not guess)
3. Fix the root cause — not a try/except wrapper around it
4. Rebuild and confirm the new exe timestamp before telling the user it is fixed

### 24-D: Do not confuse "source works" with "exe works"

`python app.py` running cleanly does NOT mean the exe works. They are different execution environments. Always verify the specific failing behaviour in the exe, not just in source.

---

## RULE 23: NetSentinel.spec must stay in sync with the codebase — NON-NEGOTIABLE

**This rule exists because PyInstaller's static import tracer cannot follow dynamic imports, conditional imports, or any module not directly reachable from `app.py` at parse time. If a module is not in `hiddenimports`, the compiled exe will crash or silently malfunction — even though `python app.py` works perfectly.**

### 23-A: Update the spec whenever a file is added or removed

Every time you create or delete any of the following, you MUST update `NetSentinel.spec` in the same commit — not later, not in a follow-up:

| File added/removed | What to update in spec |
|---|---|
| `modules/<name>.py` | Add/remove `"modules.<name>"` from `hiddenimports` |
| `workers/<name>.py` | Add/remove `"workers.<name>"` from `hiddenimports` |
| `ui/pages/<name>.py` | Add/remove `"ui.pages.<name>"` from `hiddenimports` |
| `ui/<name>.py` | Add/remove `"ui.<name>"` from `hiddenimports` |
| New package in `requirements.txt` | Add the package to the `collect_all(...)` loop AND add key submodules to `hiddenimports` |

### 23-B: New packages need collect_all

When a new third-party package is added to `requirements.txt`, add it to the `collect_all` loop in the spec:

```python
for _pkg in ("scapy", "PyQt6", "matplotlib", "flask", "keyring", "<new_package>"):
    _d, _b, _h = collect_all(_pkg)
    datas         += _d
    binaries      += _b
    hiddenimports += _h
```

Also add the package's key runtime submodules explicitly to `hiddenimports` — `collect_all` catches data files and binaries but sometimes misses lazy-loaded submodules.

### 23-C: New data files need a datas entry

If a new file is needed at runtime (JSON, INI, database seed, icon, certificate), add it to `datas` in the spec:

```python
datas = [
    ("offenders.json", "."),
    ("assets/icons", "assets/icons"),
    ("new_data_file.json", "."),   # ← add here
]
```

### 23-D: Why `python app.py` works but the exe does not

This is the most common source of confusion:

- `python app.py` uses the **live filesystem** — Python finds every `.py` file by walking `sys.path`.
- `NetSentinel.exe` is a **frozen zip** — only what PyInstaller bundled at build time is present.
- Fixes pushed to source files are **invisible to the exe** until `build.bat --gui` is re-run.
- Code on a **feature branch** is invisible to anyone building from `master` or a different branch.

### 23-E: Checklist addition — spec sync before every commit

Add this check to the pre-commit gate (RULE 21 checklist):
- [ ] Every new `modules/*.py` file is listed in `NetSentinel.spec` `hiddenimports`
- [ ] Every new `workers/*.py` file is listed in `NetSentinel.spec` `hiddenimports`
- [ ] Every new `ui/pages/*.py` file is listed in `NetSentinel.spec` `hiddenimports`
- [ ] Every new `requirements.txt` package is in the `collect_all` loop in `NetSentinel.spec`
- [ ] Every new runtime data file is in the `datas` list in `NetSentinel.spec`

---

## Long-Term Architecture Rules

These rules govern the overall system architecture as new features (continuous monitoring, alerting, history graphs) are added. Violating them now creates structural debt that is hard to undo.

### ARCH RULE 1: Three-layer separation

The application has three distinct layers. Each layer has one responsibility:

```
UI LAYER       ui/dashboard.py (shell/router), ui/pages/*.py (page widgets)
               • Reads from MetricStore for display
               • Emits user actions to workers via signals
               • NEVER writes to MetricStore directly
               • NEVER imports from modules/alert_engine.py

DATA LAYER     modules/metric_store.py  ←→  NetSentinel.db
               • Single source of truth for all persisted metrics
               • Safe for concurrent reads from multiple threads/processes

MODULE LAYER   modules/*.py
               • Pure business logic — NO PyQt imports, NO direct DB writes
               • Returns typed dataclasses or plain dicts
               • Workers (workers/*.py) call modules and write results to MetricStore
```

### ARCH RULE 2: MetricStore is a singleton — never construct it inside a widget

`MetricStore` is instantiated **once** in `app.py` (GUI process) or `svc.py` (service process) and passed as a constructor dependency to any worker or page that needs it.

```python
# WRONG — never do this inside a page widget or module
store = MetricStore()

# CORRECT — receive it as a parameter
class AvailabilityMonitorWorker(QThread):
    def __init__(self, store: MetricStore, ...):
        self._store = store
```

### ARCH RULE 3: Alert engine has no UI imports

`modules/alert_engine.py` must not import from `PyQt6` or `ui/`. It is pure Python. The worker (`workers/alert_worker.py`) wraps it in a QThread and emits Qt signals when alerts fire. The UI layer subscribes to those signals.

### ARCH RULE 4: Background loops use QThread in GUI, threading.Thread in svc.py

| Process | Long-running loop pattern |
|---|---|
| `app.py` (GUI) | `QThread` subclass in `workers/` — emits signals |
| `svc.py` (service) | `threading.Thread` — writes to MetricStore directly |

Never use `QTimer` for blocking I/O. Never use bare `threading.Thread` for long-running loops inside the GUI process.

### ARCH RULE 5: Multi-process SQLite safety

`MetricStore._write_lock` is a `threading.Lock()` — it serialises writes **within one process only**. When both `app.py` and `svc.py` run simultaneously, SQLite WAL file locking handles cross-process write safety automatically. Do not add cross-process locking; WAL mode is sufficient.

### ARCH RULE 6: New page widgets go in ui/pages/

Dashboard pages added as part of the backlog roadmap (history graphs, alert feed, device inventory) must be implemented as standalone classes in `ui/pages/<name>_page.py`, not as `_build_*_tab()` methods appended to `dashboard.py`.

`dashboard.py` instantiates each page class and passes in the shared `MetricStore` instance. No page logic lives in `dashboard.py` itself.

```python
# CORRECT pattern in dashboard.py
from ui.pages.history_page import HistoryPage
self._history_page = HistoryPage(store=self._store)
self._nav_add_page("📈", "History", self._history_page)
```

### ARCH RULE 7: MetricStore backend is configurable — never hardcode sqlite3 calls in pages

All database interactions go through the `MetricStore` public API (`record_rtt`, `query_rtt_history`, etc.). Page widgets and workers never call `sqlite3` directly. This is what makes the `backend_url` migration flag work.

---

## Pre-Push Gate — GUI Verification

### RULE 13: Never push UI changes without a local launch sign-off

**After any change to `ui/`, `app.py`, or any module imported at startup, the agent must:**

1. Run `python tools/debug_launch.py` — this writes all Qt warnings and Python exceptions to `netsentinel_debug.log`
2. Read `netsentinel_debug.log` to confirm "Dashboard() instantiated OK" and "window.show() called OK" appear
3. **Wait for the user to confirm the window opened and looks correct before committing or pushing**

The user's sign-off phrase is: **"looks good"** (or similar confirmation).  
Do NOT commit, tag, or push until that sign-off is received.

**Why:** The smoke test (`python app.py --smoke`) only checks imports — it does not run `Dashboard.__init__()` or any `_build_*` method. Runtime crashes in UI construction are invisible to the smoke test.

```powershell
# Correct pre-push workflow for UI changes:
python tools/debug_launch.py          # launches the GUI + logs everything
# -- user verifies the window --
# -- user says "looks good" --
# THEN commit and push
```

### RULE 14: Read `netsentinel_debug.log` after every crash

When `python app.py` exits with code 1 and no traceback appears in the terminal:

```powershell
python tools/debug_launch.py ; Get-Content netsentinel_debug.log
```

The log captures:
- Every Qt stylesheet parse warning (with the widget name)
- Every Python exception with full traceback
- Stepwise progress markers so the exact line of failure is visible

Never ask the user to take a screenshot. Always read the log file directly.

### RULE 15: `assets/icons/` must be in the PyInstaller spec datas
The `datas` list in `NetSentinel.spec` **must** include `("assets/icons", "assets/icons")` so the window icon and splash image are bundled into the packaged executable. If you add new image/icon assets under `assets/`, add them to `datas` in the same PR.

```python
# Correct — in NetSentinel.spec
datas = [
    ("offenders.json", "."),
    ("assets/icons", "assets/icons"),
]
```

Verify after any spec change:
```powershell
Select-String -Path NetSentinel.spec -Pattern 'assets/icons'
```
Expected: at least one `datas` entry and one `icon=` entry.
