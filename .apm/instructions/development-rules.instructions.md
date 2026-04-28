---
applyTo: "**/*.py"
---

# NetSentinel — Development Rules for AI Agents

---

## COMMIT GATE — Mandatory Before Every Commit or Push

**These steps are BLOCKING. Do not commit, tag, or push until ALL three are complete.**

### Step 1 — Run the full test suite
```powershell
python -m pytest tests/ -q
```
All tests must pass. Fix any failures before proceeding.

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

```python
card = QFrame()
card.setObjectName("card")
card_lay = QVBoxLayout(card)
card_lay.setContentsMargins(0, 0, 0, 0)
card_lay.setSpacing(0)

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
Whenever displaying device status, scan verdict, or risk level in a table, the first or second column must contain a coloured indicator.

```python
dot = QLabel("●")
dot.setStyleSheet(f"color: {GREEN}; font-size: 12px;")
table.setCellWidget(row, 0, dot)
```

### RULE 9: New pages must register in the correct sidebar section
- Regular monitoring features → "Standard" section
- Advanced/optional tools → "Advanced" section
- Offensive/elevated-privilege features → "Security Audit" section

Use `self._nav_add_page(label, widget)` after the correct `self._nav_add_section()` call.

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
ax.set_title("Title", color="#1A3A5C", fontsize=11, fontweight="bold")
```

## Version Bump Checklist

**RULE 11: When bumping the application version, update ALL of the following — no exceptions.**

| File | What to change |
|---|---|
| `app.py` | `app.setApplicationVersion("X.Y.Z")` |
| `cli.py` | `_VERSION = "X.Y.Z"` |
| `apm.yml` | `version: X.Y.Z` |
| `installer.iss` | `#define MyAppVersion "X.Y.Z"` |
| `build.bat` | echo version string in banner line |
| `build.sh` | echo version string in banner line |
| `README.md` | badge/link and `### vX.Y.Z (current)` changelog entry |
| `ui/dashboard.py` | `_build_help_tab()` — "What's New" section content |
| `tools/debug_launch.py` | `app.setApplicationVersion("X.Y.Z")` |

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

### 21-A: Version files (always)
If new work warrants a version bump (any user-visible feature or fix):
1. Bump the version in ALL files listed in RULE 11 (app.py, cli.py, apm.yml, installer.iss, build.bat, build.sh, debug_launch.py)
2. Run `tests/test_version_consistency.py` — fail = do not proceed

### 21-B: README.md (always — no exceptions)
| Section | What to update |
|---|---|
| Install badge / version line | New version number |
| `## Features` / feature tables | New sidebar pages; updated capability descriptions |
| `## Project structure` code block | New files in modules/, ui/pages/, workers/, tests/ |
| `## What's new` changelog | Rename old `(current)`; add new `### vX.Y.Z (current)` at top |
| `## How it was built` timeline | Append row for significant milestones — never delete existing rows |

### 21-C: In-app Help "What's New" (always)
In `ui/dashboard.py _build_help_tab()`: card title = `What's New in vX.Y.Z`; bullet list matches README changelog exactly.

### 21-D: BACKLOG.md (always)
- Remove completed Tier 1 / Tier 2 items; add new items discovered during implementation
- Update the `Last updated:` date; promote Tier 2 items if Tier 1 is empty

### 21-E: Test coverage (always)
- New module → `tests/test_<module_name>.py` must exist with at least one passing test
- Run full suite; report new count to user

### 21-F: Sidebar + docs registration (when adding pages)
- `_nav_add_page()` in dashboard.py in correct section (RULE 9)
- Listed in README `## Features` table and `## Project structure` block

### 21-G: Architecture instructions (when adding modules)
- Add module to the `modules/` layout table in `.github/instructions/architecture.instructions.md`

### 21-H: Commit message format
```
feat: <description>  vX.Y.Z
- <item 1>
- <item 2>
```

### Self-verification checklist (check ALL before presenting to user)
- [ ] Version bumped in all 7 files; consistency test passes
- [ ] README: badge, features table, project structure, changelog updated
- [ ] README: "How it was built" table untouched
- [ ] In-app Help "What's New" matches changelog
- [ ] BACKLOG.md: completed items removed, new items added, date updated
- [ ] All new modules have tests; full suite passes
- [ ] New pages registered in sidebar and listed in README

**Do not ask the user to do any of these. Do them.**

---

## README Character Encoding — RULE 12

**Never paste text that contains Unicode replacement characters (U+FFFD `?`) or broken multi-byte sequences.**
Always use actual Unicode characters: `—` not `-`, `→` not `->`. When editing README.md verify no `?` replacement characters exist before committing.

---

## Build Origin Story — RULE 12b

The `## How it was built` section in `README.md` must be preserved in all future edits. Never delete or truncate it.

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
3. Add page builder method as a standalone class in `ui/pages/<name>_page.py`
4. Register the page in `_build_tabs()` under the correct sidebar section
5. Add result cache `self._<name>_result = None` in `__init__`
6. Wire the worker's `result_ready` signal to a `_on_<name>_result()` slot
7. All colours used must come from `ui/styles.py`

---

## Long-Term Architecture Rules

### ARCH RULE 1: Three-layer separation

```
UI LAYER       ui/dashboard.py (shell/router), ui/pages/*.py (page widgets)
               • Reads from MetricStore for display
               • NEVER writes to MetricStore directly
               • NEVER imports from modules/alert_engine.py

DATA LAYER     modules/metric_store.py  ←→  NetSentinel.db
               • Single source of truth for all persisted metrics

MODULE LAYER   modules/*.py
               • Pure business logic — NO PyQt imports, NO direct DB writes
```

### ARCH RULE 2: MetricStore is a singleton

`MetricStore` is instantiated **once** in `app.py` or `svc.py` and injected as a dependency. Never construct it inside a page widget or module.

```python
# WRONG
store = MetricStore()   # inside a page widget

# CORRECT — receive it as a parameter
class HistoryPage(QWidget):
    def __init__(self, store: MetricStore, ...):
        self._store = store
```

### ARCH RULE 3: Alert engine has no UI imports

`modules/alert_engine.py` must not import from `PyQt6` or `ui/`. The worker wrapping it in a QThread emits Qt signals. The UI subscribes to those signals.

### ARCH RULE 4: Background loop patterns

| Process | Pattern |
|---|---|
| `app.py` (GUI) | `QThread` subclass in `workers/` |
| `svc.py` (service) | `threading.Thread` |

Never use `QTimer` for blocking I/O.

### ARCH RULE 5: Multi-process SQLite safety

`MetricStore._write_lock` serialises writes within one process. Cross-process write safety comes from SQLite WAL file locking — do not add cross-process locking.

### ARCH RULE 6: New pages go in ui/pages/

New backlog pages (history graphs, alert feed, device inventory) are standalone classes in `ui/pages/<name>_page.py`. Dashboard instantiates them and passes in the shared `MetricStore`.

### ARCH RULE 7: All DB access through MetricStore API

Never call `sqlite3` directly in page widgets or workers. Use `MetricStore` public methods only. This is what enables the `backend_url` migration flag to work.

---

## Pre-Push Gate — GUI Verification

### RULE 13: Never push UI changes without a local launch sign-off

After any change to `ui/`, `app.py`, or any module imported at startup:

1. Run `python tools/debug_launch.py`
2. Read `netsentinel_debug.log` — confirm "Dashboard() instantiated OK" and "window.show() called OK"
3. Wait for user to confirm the window looks correct before committing

### RULE 14: Read `netsentinel_debug.log` after every crash

```powershell
python tools/debug_launch.py ; Get-Content netsentinel_debug.log
```

Never ask the user for a screenshot. Always read the log directly.

### RULE 15: `assets/icons/` must be in the PyInstaller spec datas

```python
datas = [
    ("offenders.json", "."),
    ("assets/icons", "assets/icons"),
]
```

Verify:
```powershell
Select-String -Path NetSentinel.spec -Pattern 'assets/icons'
```

### RULE 16: Never use `setFixedHeight` on buttons inside fixed-height bars
Buttons inside a bar that already has a fixed height (e.g. the 42px top bar) must **not** call `setFixedHeight()`. Instead use `setSizePolicy(Minimum, Expanding)` so the button fills the bar naturally. Also ensure the layout right-margin is ≥ 16px so text is not clipped.

```python
# WRONG — clips text, fights the bar's own height constraint
btn.setFixedHeight(20)

# CORRECT — fills the available height without fighting the layout
btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
layout.setContentsMargins(12, 0, 16, 0)  # right margin ≥ 16px
```

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

## Naming Conventions

| Element | Pattern |
|---|---|
| Table variables | `self._<module>_table` |
| Status label | `self._<module>_status` |
| Worker reference | `self._<module>_worker` |
| Result cache | `self._<module>_result` |
| Nav row index | `self._nav_<module>_row` |

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

## Adding a New Scan Module

1. Create `modules/<name>.py` — pure Python, no PyQt imports
2. Create a worker in `workers/scan_worker.py` or inline QThread subclass
3. Add page builder method `_build_<name>_tab()` in `dashboard.py`
4. Register the page in `_build_tabs()` under the correct sidebar section
5. Add result cache `self._<name>_result = None` in `__init__`
6. Wire the worker's `result_ready` signal to a `_on_<name>_result()` slot
7. All colours used must come from `ui/styles.py`
