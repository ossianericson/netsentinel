# NetSentinel — Stability & Architecture Health Plan

**Goal:** The app must be crash-free, the test suite must be fully green, and the
codebase must be maintainable at its current scale — any file that makes automated
tooling (AI assistants, static analysis, IDEs) slow or unreliable is a reliability
risk because it prevents effective maintenance.

**Context:** This is the third plan in the plugin sprint series.
`PLUGIN_ECOSYSTEM_PLAN.md` delivered features (complete, v1.9.48).
`PLUGIN_ROBUSTNESS_PLAN.md` delivered structural correctness (complete, v1.9.54).
This plan delivers codebase health — the foundation that lets the next feature
sprint start from a solid base.

---

## Current State Audit (as of v1.9.54)

### Finding 1 — Test suite crashes mid-run (blocker)
Running the full 2,137-test suite with `python -m pytest tests/` exits with code
`-1073740791` (Windows `STATUS_STACK_BUFFER_OVERRUN`) at approximately 52% completion,
during or immediately after `test_network_logger.py`.

- The same tests **pass** when run in isolation or in any subset tried.
- The crash is therefore caused by cumulative global state corruption — most likely
  Qt object lifecycle: a `QApplication` or `QThread` created by an earlier test is
  garbage-collected or destroyed while the next test still holds a reference to a child
  object, corrupting the C++ heap.
- Impact: CI cannot be trusted. A test failure is indistinguishable from a crash.

### Finding 2 — dashboard.py is ungovernable (12,269 lines)
`RULE-AH1` sets a 600-line limit. `ui/dashboard.py` is 20× over limit.
At this size:
- Every AI-assisted edit requires loading >12K lines of context.
- A single syntax error in any nav handler crashes the entire application at startup.
- The file contains 9 distinct concerns: nav shell, nav builder, nav rail, flyout,
  page wiring, scan result handlers, tray icon, help panel, and settings persistence.
- Merge conflicts are nearly guaranteed for any concurrent feature work.

### Finding 3 — Multiple module-layer files violate RULE-AH1

| File | Lines | Budget | Over by |
|---|---|---|---|
| `modules/metric_store.py` | 1,522 | 600 | 2.5× |
| `modules/report_exporter.py` | 1,108 | 600 | 1.8× |
| `modules/utils.py` | 939 | 600 | 1.5× |
| `modules/speed_tester.py` | 615 | 600 | 1.0× |
| `modules/network_logger.py` | 624 | 600 | 1.0× |
| `modules/notification_router.py` | 566 | 600 | — |
| `modules/alert_engine.py` | 592 | 600 | — |
| `modules/credentialed_scan.py` | 565 | 600 | — |

`test_module_loc.py` has the three genuinely over-limit modules listed in its
`KNOWN_LARGE_MODULES` exemption dict — those exemptions need to be resolved, not
just raised.

### Finding 4 — Multiple UI page files are over limit

| File | Lines |
|---|---|
| `ui/pages/hardware_integration_page.py` | 3,522 |
| `ui/pages/home_page.py` | 3,027 |
| `ui/pages/overview_page.py` | 2,223 |
| `ui/pages/notifications_page.py` | 1,812 |
| `ui/pages/log_hub_page.py` | 1,648 |
| `ui/pages/settings_page.py` | 1,526 |
| `ui/pages/speed_test_page.py` | 1,336 |
| `ui/pages/inventory_page.py` | 1,168 |
| `ui/pages/geo_map_page.py` | 1,027 |
| `ui/pages/discover_page.py` | 1,016 |
| `ui/pages/home_automation_page.py` | 1,013 |
| `ui/pages/plugin_device_page.py` | 720 |
| `ui/pages/lab_mode_page.py` | 724 |
| `ui/pages/cve_page.py` | 694 |
| `ui/pages/wifi_heatmap_page.py` | 666 |
| `ui/pages/diagnosis_page.py` | 770 |
| `ui/pages/connections_page.py` | 814 |
| `ui/styles.py` | 888 |

UI pages are exempt from the 600-line module limit by convention, but files above
~1,000 lines gain no benefit from size: they can and should extract reusable
subcomponents.

### Finding 5 — Four CodeQL alerts required hotfixes in v1.9.53–v1.9.54
Empty `except:` blocks, unused imports, and an `nspkg` issue were all found by
CodeQL after shipping. There is no pre-commit gate that would have caught these.
`test_module_loc.py` and `test_interactive_states.py` prove static-analysis tests
work — the same pattern should cover CodeQL categories.

### Finding 6 — Worker lifecycle tests are incomplete (RULE-T2 audit)
`test_worker_lifecycle.py` covers some workers, but a full audit against
`workers/*.py` reveals gaps. Any worker without a lifecycle test is an
untested failure mode.

---

## S0 — Fix the Test Suite Crash (must do first)

### S0-1  Identify and isolate the Qt-heap-corruption trigger
The crash pattern (passes in isolation, fails in sequence) means one or more
tests create `QApplication` or `QThread` objects that are not properly destroyed
before the next test's setup. 

Steps:
1. Run `python -m pytest tests/ -p no:randomly --lf -v` to reproduce deterministically.
2. Add a session-scoped `autouse` fixture in `conftest.py` that logs each test name
   to a file immediately before it runs; the last entry before crash identifies the
   culprit.
3. Once identified: fix the teardown (add `app.quit()` + `del app` in the fixture,
   or move the QApplication to a session-scoped fixture shared across all tests
   that need it).

### S0-2  Session-scoped QApplication fixture
Many tests that import PyQt6 widgets construct a `QApplication` per-test in a module-
level `app = QApplication([])` call. Multiple `QApplication` instances in one process
cause undefined behaviour in Qt.

Required pattern: a single `conftest.py` session fixture:

```python
@pytest.fixture(scope="session")
def qapp():
    import sys
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    yield app
    # Do NOT call app.quit() here — session teardown is flaky in CI
```

Tests that construct Qt widgets must declare `def test_foo(qapp)` — never
`QApplication([])` at module level.

### S0-3  `tests/conftest.py` QSettings isolation
Tests that use `QSettings` must not pollute each other's state. Each test that
reads/writes QSettings must use a unique `organizationName`/`applicationName` pair
(or a temp registry key on Windows) so that settings from one test do not affect the
next.

Recommended pattern:
```python
@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    import uuid
    from PyQt6.QtCore import QSettings
    key = str(uuid.uuid4())[:8]
    monkeypatch.setenv("NS_TEST_SETTINGS_KEY", key)
    yield
    QSettings(f"NetSentinel-test-{key}", "test").clear()
```

### S0-4  Full-suite green gate
After S0-1–S0-3: `python -m pytest tests/ -q` must exit 0 with ≥2,137 tests.
This becomes a hard gate on every PR going forward.

---

## S1 — Split dashboard.py (Critical Architecture)

`dashboard.py` at 12,269 lines is the single greatest maintenance liability in
the codebase.  It must be split before any further feature work on navigation,
scan wiring, or the help system.

### S1-1  Extract `ui/nav/` package

```
ui/nav/__init__.py          # re-exports: _RailButton, FlyoutPanel, NavSection
ui/nav/rail.py              # _RailButton widget, _nav_rail_* methods
ui/nav/flyout.py            # _FlyoutPanel widget, section management
ui/nav/builder.py           # _build_pro_nav(), _nav_begin_section(), _nav_add_rail_item()
ui/nav/palette.py           # CommandPalette (currently in ui/command_palette.py — move here)
```

`dashboard.py` retains:
- `Dashboard(QMainWindow)` class definition (init, show, close)
- `_init_pages()` (page widget instantiation)
- `_restore_settings()` / `_save_settings()`
- Tray icon setup

Target for `dashboard.py` after split: **≤3,000 lines**.

### S1-2  Extract scan-result wiring to `ui/scan_wiring.py`
All `_on_*_result()` handlers (scan results flowing from workers to pages) live
inside `dashboard.py`. They form a standalone wiring layer — pure signal plumbing
with no UI logic. Extract them:

```python
# ui/scan_wiring.py
def wire_scan_results(window: "Dashboard") -> None:
    """Connect all worker result_ready signals to page handler methods."""
    ...
```

Called once in `Dashboard.__init__` after all pages are constructed. This removes
~2,000 lines from `dashboard.py` and makes the data-feed wiring auditable at a glance.

### S1-3  Extract help panel to `ui/help.py`
`_PAGE_HELP` dict, `_build_help_panel()`, and all `_section()` / `_entry()` helpers
live in `dashboard.py` but have no dependency on navigation state. Extract to
`ui/help.py`. `Dashboard` imports and calls `build_help_panel(window)`.

### S1-4  Update `test_module_loc.py` to track dashboard size
After the split, add `dashboard.py` to the LOC budget dict with a target of 3,000 lines
and a split comment. Prevents re-accumulation.

---

## S2 — Split Oversize Modules

### S2-1  Split `modules/metric_store.py` (1,522 → ≤600)

```
modules/metric_store.py          # Core: MetricStore class, queries, schema constants
modules/metric_store_schema.py   # Schema migrations (v1→v8), CREATE TABLE statements
modules/metric_store_io.py       # Export/import helpers (CSV, JSON dump/restore)
```

`MetricStore` imports from `metric_store_schema` and `metric_store_io`. Public API
is unchanged — all existing imports `from modules.metric_store import MetricStore`
continue to work.

### S2-2  Split `modules/report_exporter.py` (1,108 → ≤600)

```
modules/report_exporter.py      # Public API: save_pdf_report(), save_csv_report()
modules/report_html.py          # HTML generation helpers (card, badge, section)
modules/report_pdf.py           # PDF-specific layout (reportlab wrapper)
```

### S2-3  Split `modules/utils.py` (939 → ≤600)

```
modules/utils.py                # Core: get_app_data_dir(), is_admin(), ping_sweep
modules/utils_net.py            # Network helpers: get_network_info(), get_dhcp_info()
modules/utils_platform.py       # Platform-specific: registry reads, WMI helpers
```

### S2-4  Add `tests/test_metric_store_schema.py` and `tests/test_metric_store_io.py`
New module files require new test files (RULE-T1). Minimum: import test + one
behavioural test per new module.

---

## S3 — Split Oversize UI Pages

UI pages are harder to split (they're stateful widget trees). Prioritise by: (a) size,
(b) reusability of extracted component, (c) test isolation benefit.

### S3-1  Extract `HubCard` to `ui/widgets/hub_card.py`
`hardware_integration_page.py` (3,522 lines) is dominated by the `_HubCard` class
and its subwidgets (`_LogConsole`, `_ConfigPanel`). Extract:

```
ui/widgets/hub_card.py         # _HubCard, _LogConsole, _ConfigPanel
ui/widgets/credential_dialog.py # _CredentialDialog (used by hardware page + future pages)
ui/pages/hardware_integration_page.py  # HardwareIntegrationPage shell (~800 lines)
```

### S3-2  Extract `OverviewTile` and tile layout to `ui/widgets/overview_tile.py`
`overview_page.py` (2,223 lines) contains tile definitions, tile data binding, and
the drag-to-reorder layout. The tile framework is reusable. Extract:

```
ui/widgets/overview_tile.py     # OverviewTile base class, TileGrid
ui/pages/overview_page.py       # OverviewPage: tile instantiation, data binding (~600 lines)
```

### S3-3  Extract home-page sections to `ui/widgets/home_widgets.py`
`home_page.py` (3,027 lines) contains: hero banner, suggestions strip, weekly digest
card, quick tips card, since-last-session banner, and dashboard strip. Extract the
individual section widgets to `ui/widgets/home_widgets.py`. Each section becomes a
standalone `QWidget` subclass that can be tested in isolation.

### S3-4  Update `test_module_loc.py` to remove exemptions post-split
After each split completes, remove the entry from `KNOWN_LARGE_MODULES` and verify
the 600-line default budget is enforced for the new files.

---

## S4 — CodeQL Prevention Infrastructure

### S4-1  `tests/test_codeql_prevention.py`
Static analysis test that catches the four categories that triggered alerts in
v1.9.53–v1.9.54, before CodeQL sees them:

```python
def test_no_bare_except_blocks():
    """Detect bare `except:` — CodeQL py/bare-except."""
    ...

def test_no_unused_imports():
    """Detect unused top-level imports — CodeQL py/unused-import."""
    ...

def test_no_url_substring_comparisons():
    """Detect `x in url_string` patterns — CodeQL py/incomplete-url-substring-sanitization."""
    # Already partially covered by tests.instructions.md convention, but not enforced.
    ...
```

Uses `ast.parse` + `ast.walk` on every `.py` file in `modules/` and `ui/`. Runs
as part of the standard suite with no extra dependencies.

### S4-2  Pre-commit hook entry in CLAUDE.md
Add to CLAUDE.md commit gate:

```
Step 0 (before tests) — Run static checks:
  python -m pytest tests/test_codeql_prevention.py tests/test_interactive_states.py -q
```

Both tests catch categories that CI catches too late.

---

## S5 — Worker Lifecycle Audit (RULE-T2 Completion)

### S5-1  Enumerate all workers and cross-reference against test coverage

```
workers/
  availability_worker.py    — test_worker_lifecycle.py ✓?
  cert_worker.py            — ?
  dhcp_lease_worker.py      — ?
  diagnosis_worker.py       — ?
  dns_zone_worker.py        — ?
  ha_worker.py              — ?
  hw_detect_worker.py       — ?
  iface_bw_worker.py        — ?
  mesh_worker.py            — ?
  plugin_polling_worker.py  — test_plugin_polling_worker.py ✓
  plugin_worker.py          — ?
  process_worker.py         — ?
  report_scheduler_worker.py — ?
  rest_api_worker.py        — ?
  scan_worker.py            — ?
  service_worker.py         — ?
  snmp_trap_worker.py       — ?
  speed_test_worker.py      — ?
  syslog_worker.py          — ?
  threat_intel_worker.py    — ?
  wifi_monitor_worker.py    — ?
  zte_worker.py             — ?
```

### S5-2  `tests/test_worker_lifecycle_full.py`
For every worker not covered in S5-1 audit: add start/stop/isRunning lifecycle test
following the RULE-T2 pattern. Minimum: instantiate, start, wait ≤50 ms, stop,
assert `isRunning()` is False within 2 s.

### S5-3  `_running` flag audit
Scan all workers for loops without a `self._running` check. Any `while True:` or
`for ...:` in a `run()` method that does not check `_running` is a worker that
cannot be stopped gracefully. Fix each instance.

---

## S6 — MetricStore Health

### S6-1  WAL file growth guard
SQLite WAL mode produces a `-wal` file that grows unbounded if `PRAGMA wal_checkpoint`
is never called. Add a startup check: if `NetSentinel.db-wal` exceeds 50 MB, run
`PRAGMA wal_checkpoint(TRUNCATE)` before opening the connection.

### S6-2  VACUUM on schema upgrade
`MetricStore._migrate()` runs on each schema version bump. Add a `PRAGMA
VACUUM;` call at the end of every migration that adds or removes columns.
Prevents the DB growing indefinitely from deleted rows.

### S6-3  Connection timeout / busy handler
Currently if two threads hit MetricStore simultaneously (e.g. background scan + REST API),
the second operation raises `sqlite3.OperationalError: database is locked`.
Add `conn.execute("PRAGMA busy_timeout = 5000")` immediately after every `sqlite3.connect`
call in `MetricStore._connect()`.

### S6-4  `tests/test_metric_store_concurrency.py`
- Two threads write to MetricStore simultaneously; assert no `OperationalError`
- WAL checkpoint called when WAL exceeds threshold; assert WAL size decreases
- VACUUM called after migration; assert DB file size is stable or smaller

---

## S7 — Application Startup Reliability

### S7-1  Lazy-import expensive optional modules
Several modules import heavy optional libraries at module level. Example:
`modules/geo_locator.py` imports `geoip2` at the top. If `geoip2` is not installed,
importing the module raises `ImportError` and prevents any page that touches geo data
from loading — even if the user never navigates to that page.

Audit: any `import` in `modules/*.py` that is for an optional feature must be moved
inside the function that needs it, wrapped in `try/except ImportError` (RULE-AH4).

### S7-2  Startup profiling fixture
Add a `tools/startup_profile.py` script that times each stage of startup:

```python
# Outputs lines like:
# [0.000]  QApplication created
# [0.124]  MetricStore opened
# [0.480]  Dashboard.__init__ started
# [1.203]  _init_pages complete (83 pages)
# [2.100]  window.show() called
```

This makes regressions in startup time visible. If startup exceeds 3 s, the profile
output shows which stage is slow.

### S7-3  `netsentinel_debug.log` rotation
Currently the debug log grows unbounded. Add rotation: keep the last 5 launch logs,
each named `netsentinel_debug_YYYYMMDD_HHMMSS.log`. The `tools/debug_launch.py`
script should write to a timestamped file and create a `netsentinel_debug.log`
symlink (or copy on Windows) pointing to the latest run.

---

## S8 — Documentation Health

### S8-1  Mark PLUGIN_ROBUSTNESS_PLAN as complete
All items in `PLUGIN_ROBUSTNESS_PLAN.md` are shipped (v1.9.52, confirmed by test
files existing and passing).  Update the plan to mark v1.9.49 items ✅ and add
completion note.  Move to `docs/completed/` alongside `PLUGIN_ECOSYSTEM_PLAN.md`.

### S8-2  Architecture docs reflect current structure
`CLAUDE.md` and `architecture.md` still list files in the original flat structure.
After S1 and S3 splits, update both docs to reflect `ui/nav/` package,
`ui/widgets/hub_card.py`, and the new module layout.

### S8-3  Version history in project-vision.md
`project-vision.md` still shows "v1.9.40 → v1.9.41 → v1.9.42" as condensed history.
Update to reflect actual history: v1.9.40 → ... → v1.9.54 with one-line summaries
of each sprint focus.

---

## Implementation Order

Phased to minimise risk: test infrastructure first (S0), then the most critical
structural changes (S1), then module splits (S2, S3), then prevention (S4–S8).

| # | Item | Sprint | Version Target | Notes |
|---|---|---|---|---|
| 1 | S0-1: Identify Qt-crash culprit | 1 | v1.9.55 | Bisect using conftest logger |
| 2 | S0-2: Session-scoped QApplication fixture | 1 | v1.9.55 | Prerequisite for S0-4 |
| 3 | S0-3: QSettings isolation fixture | 1 | v1.9.55 | |
| 4 | S0-4: Full suite green gate | 1 | v1.9.55 | Hard gate — no further work until green |
| 5 | S4-1: `test_codeql_prevention.py` | 1 | v1.9.55 | Fast win, no structural change |
| 6 | S8-1: Mark robustness plan complete | 1 | v1.9.55 | Housekeeping |
| 7 | S1-1: Extract `ui/nav/` package | 2 | v1.9.56 | Biggest risk/reward |
| 8 | S1-2: Extract scan-result wiring | 2 | v1.9.56 | |
| 9 | S1-3: Extract help panel | 2 | v1.9.56 | |
| 10 | S1-4: Add dashboard LOC budget test | 2 | v1.9.56 | |
| 11 | S3-1: Extract HubCard to widget | 3 | v1.9.57 | Largest page file |
| 12 | S3-2: Extract OverviewTile | 3 | v1.9.57 | |
| 13 | S3-3: Extract home-page section widgets | 3 | v1.9.57 | |
| 14 | S2-1: Split metric_store | 4 | v1.9.58 | Schema migration is highest risk |
| 15 | S2-2: Split report_exporter | 4 | v1.9.58 | |
| 16 | S2-3: Split utils | 4 | v1.9.58 | |
| 17 | S2-4: Tests for new module files | 4 | v1.9.58 | |
| 18 | S5-1: Worker coverage audit | 5 | v1.9.59 | Enumerate gaps |
| 19 | S5-2: `test_worker_lifecycle_full.py` | 5 | v1.9.59 | |
| 20 | S5-3: `_running` flag audit | 5 | v1.9.59 | |
| 21 | S6-1: WAL growth guard | 5 | v1.9.59 | |
| 22 | S6-2: VACUUM on migration | 5 | v1.9.59 | |
| 23 | S6-3: Connection busy timeout | 5 | v1.9.59 | |
| 24 | S6-4: `test_metric_store_concurrency.py` | 5 | v1.9.59 | |
| 25 | S7-1: Lazy-import audit | 6 | v1.9.60 | |
| 26 | S7-2: Startup profiling script | 6 | v1.9.60 | |
| 27 | S7-3: Debug log rotation | 6 | v1.9.60 | |
| 28 | S4-2: Pre-commit check update in CLAUDE.md | 6 | v1.9.60 | |
| 29 | S8-2: Architecture docs update | 6 | v1.9.60 | |
| 30 | S8-3: Version history update | 6 | v1.9.60 | |

---

## Architecture Principles Extracted From This Audit

These augment the principles in `PLUGIN_ROBUSTNESS_PLAN.md`:

5. **File size is a proxy for blast radius.**  A 12,000-line file means any crash
   in any of its functions brings down the whole file's responsibility.  Split at
   1,000 lines for UI pages and 600 lines for modules — not as a style preference
   but as a reliability requirement.

6. **The test suite must complete its full run.**  A test suite that crashes before
   finishing cannot be trusted.  A green partial run is not a green suite.  Fix
   test isolation before fixing test failures.

7. **Global state in tests = flaky CI.**  `QApplication`, `QSettings`, module-level
   singletons, and `os.environ` are all process-global.  Every test that touches
   them must set up and tear down its own state.  Fixtures must enforce this — test
   authors must not be trusted to remember it.

8. **Splits are safer than cleanups.**  Splitting a large file into two small files
   is less risky than refactoring the internals of a large file.  Do the split first.
   The refactor — if needed at all — is a separate PR.

---

*Plan created 2026-05-29.  Continues from PLUGIN_ROBUSTNESS_PLAN.md (v1.9.54).*
*Sprint 1 target: v1.9.55.  Full plan target: v1.9.60.*
