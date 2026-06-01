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

## Post-Sprint-4 Re-Audit (v1.9.59, 2026-05-30)

Four sprints delivered: test-suite stability (S0), nav extraction (S1-1), wiring extraction
(S1-2), partial help extraction (S1-3), module spec fixes (S12), discoverability (S11),
and three major page splits (S3-1, S3-2, S3-3).  Below is what the audit now shows.

### Finding 7 — dashboard.py decomposition is only 18% complete (13,483 → 10,046 lines)

| Sprint | Lines removed | dashboard.py total |
|--------|-------------|---------------------|
| Baseline (v1.9.54) | — | 13,483 |
| Sprint 1 | — | ~12,800 (minor cleanup) |
| Sprint 3 S1-1 | −683 | 12,117 |
| Sprint 4 S1-2 | −1,163 | 10,046 (+ 14 orphaned decorators removed) |
| **Goal** | **−7,046** | **≤3,000** |

Remaining 7,046 lines to extract.  The largest discrete blocks:

| Method | Lines | Natural extraction |
|--------|-------|--------------------|
| `_build_tabs()` | 884 | → `ui/tabs/` package |
| `_build_help_tab()` | 585 | → `ui/help.py` (S1-3 remainder) |
| `_build_logger_tab()` | 325 | → `ui/tabs/` package |
| `_apply_mesh_enrichment()` | 291 | → `ui/scan_wiring.py` or page enrichment module |
| `_build_header()` | 246 | → `ui/header.py` |
| `_build_m1_tab()` | 220 | → `ui/tabs/` package |
| `_build_network_info_tab()` | 162 | → `ui/tabs/` package |
| `__init__` | 166 | Irreducible core |
| `_build_benchmark_tab()` | 115 | → `ui/tabs/` package |
| `_build_advanced_tools_tab()` | 125 | → `ui/tabs/` package |
| `_restore_settings()` | 109 | → `ui/app_settings.py` |

The tab-builder family (`_build_tabs`, `_build_m1_tab`, and ~10 sibling methods) accounts
for roughly 3,000 lines.  This is the single highest-leverage remaining extraction.

### Finding 8 — `KNOWN_LARGE_UI_FILES` budget for dashboard.py is stale and permits re-growth

`test_module_loc.py::KNOWN_LARGE_UI_FILES["dashboard.py"]` is set to **13,700** — the
original baseline.  At 10,046 lines, dashboard.py is 3,654 lines below its own budget.
This means the test would not catch dashboard.py growing back to 13,000 lines.

**Required action:** tighten the budget to `current_actual + 200` after every sprint that
reduces dashboard.py, and set a hard 3,000-line target once the tab-builder extraction lands.

### Finding 9 — Sprint 4 created untracked large new files

| File | Lines | Tracking status |
|------|-------|-----------------|
| `ui/widgets/hub_card.py` | 1,902 | Not in `KNOWN_LARGE_UI_FILES` |
| `ui/widgets/overview_tile.py` | 1,620 | Not in `KNOWN_LARGE_UI_FILES` |
| `ui/scan_wiring.py` | 1,168 | Not tracked |

`test_module_loc.py::UI_DEFAULT_BUDGET` is 1,000 lines — these new files exceed it and are
not exempt.  The CI gate is blind to them.  Add all three to `KNOWN_LARGE_UI_FILES` with
budgets and split notes; tighten over time.

`hub_card.py` in particular is a candidate for further split: the ~700-line helper-function
section (`_load_health`, `_record_success`, `_load_paths`, etc.) has no widget-level logic
and could become a dedicated `ui/widgets/hub_helpers.py`.

### Finding 10 — S3-3 and S1-3 are only partial — their targets remain incomplete

**S3-3** (home_page.py): The `_GradeRing` / `_EventsTicker` helper classes were extracted
(−280 lines), but `home_page.py` is still **2,747 lines**.  The `HomePage` class itself
contains six 200–500 line `_build_*` section methods (hero, suggestions strip, digest card,
quick tips, session banner, dashboard strip).  Each is a standalone UI concern.  The intent
of S3-3 was to extract these sections as reusable `QWidget` subclasses.  That work was not done.

**S1-3** (help panel): Only the `_PAGE_HELP` dict (455 lines) was moved to `ui/help.py`.
The `_build_help_tab()` method (585 lines) and all its helper functions (`_section()`,
`_entry()`, `_subsection()`, etc.) remain in `dashboard.py`.

### Finding 11 — 19 of 22 workers have no lifecycle test (RULE-T2, unchanged since original audit)

Current untested workers (as of v1.9.59):
`availability_worker`, `cert_worker`, `dhcp_lease_worker`, `diagnosis_worker`,
`dns_zone_worker`, `ha_worker`, `hw_detect_worker`, `iface_bw_worker`, `plugin_worker`,
`process_worker`, `report_scheduler_worker`, `rest_api_worker`, `scan_worker`,
`service_worker`, `snmp_trap_worker`, `speed_test_worker`, `syslog_worker`,
`threat_intel_worker`, `wifi_monitor_worker`.

### Finding 12 — Five large UI pages are untracked and growing

Original audit (v1.9.54) captured hardware_integration, home, overview, and connections.
These pages have since grown or emerged and are not in any tracking structure:

| File | Lines | Status |
|------|-------|--------|
| `notifications_page.py` | 1,812 | Not in KNOWN_LARGE_UI_FILES |
| `log_hub_page.py` | 1,648 | Not tracked |
| `settings_page.py` | 1,526 | Not tracked |
| `speed_test_page.py` | 1,336 | Not tracked |
| `discover_page.py` | 1,319 | Not tracked (grew from 1,016) |
| `hardware_integration_page.py` | 1,701 | Target was ~800; still at 2.1× target |

### Finding 13 — Mock patch location drift is a future test fragility risk

Sprint 4 moved hub_card helper functions (`_save_health`, `_load_health`, etc.) to
`ui/widgets/hub_card.py`.  Tests that patch these functions must now target
`ui.widgets.hub_card.*` not `ui.pages.hardware_integration_page.*`.  Four test files
were fixed, but:

- No comment or convention document tells new test authors where to find each function.
- `hardware_integration_page.py` re-exports all hub_card symbols, which can mislead
  authors into patching the wrong namespace.

**Required action:** Add a `# Mock target: ui.widgets.hub_card.*` comment block at the
top of `hardware_integration_page.py`, and a note in the test conventions document.

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

## S9 — Module Test Coverage (RULE-T1 Completion)

**Source:** APM rules/docs/codebase audit — 2026-05-29.

36 of 70 module files have no corresponding test file. This is a blocking RULE-T1
violation and means more than half the business logic layer has zero automated
regression coverage. Any change to an untested module is undetectable until it
reaches the user.

### S9-1  Tier 1 — utility and plumbing modules
Lowest-risk files; no network I/O. Add import test + at least one behavioural test
for each:
- `modules/colours.py` — test colour constant names and hex format
- `modules/exporter.py` — test CSV/JSON serialisation with mock data
- `modules/log_chart.py` — test chart data builder with stub log entries
- `modules/mac_lookup.py` — test OUI prefix extraction (no network required)
- `modules/name_resolver.py` — test fallback resolution chain with mocked calls
- `modules/nl_query.py` — test query parsing for known patterns
- `modules/protocol_animator.py` — test scene building returns valid AnimNode/AnimStep
- `modules/web_dashboard.py` — test `build_html()` returns valid HTML string

### S9-2  Tier 2 — scan and detection modules
Each requires mocked scapy/nmap/socket to avoid live network calls:
- `modules/arp_monitor.py`
- `modules/bandwidth_monitor.py`
- `modules/dhcp_detector.py`
- `modules/dhcp_lease_scanner.py`
- `modules/dns_correlator.py`
- `modules/dns_zone_scanner.py`
- `modules/ha_detector.py`
- `modules/internet_exposure.py`
- `modules/os_fingerprint.py`
- `modules/port_scanner.py`
- `modules/private_endpoint_checker.py`
- `modules/rogue_device.py`
- `modules/smb_enumerator.py`
- `modules/snmp_poller.py`
- `modules/storm_analyser.py`
- `modules/stp_detector.py`
- `modules/syn_scanner.py`
- `modules/wifi_scanner.py`

Mark all with `@pytest.mark.live` if they require real network; ensure CI skips them.

### S9-3  Tier 3 — report, enrichment and display modules
- `modules/cloud_metadata.py` — test IMDS URL construction, mock `requests`
- `modules/diagnostic_card.py` — test PNG/HTML generation with stub grade data
- `modules/digest_builder.py` — test 7-day summary output with stub MetricStore
- `modules/hw_detect.py` — test device list parsing with mock pyserial/usb data
- `modules/lab_scenarios.py` — test scenario list completeness and result dataclasses
- `modules/network_diagnostics.py` — test ping/DNS result schema
- `modules/process_monitor.py` — test socket-map parsing with mock psutil data
- `modules/report_exporter.py` (supplemental; S2-2 split may change structure)
- `modules/speed_tester.py` — test backend cascade fallback logic
- `modules/threat_intel.py` — test DB lookup with stub data; mock AbuseIPDB calls

### S9-4  Coverage gate for module tests
Add `tests/test_module_coverage_gate.py`:

```python
EXEMPT = {"metric_store_schema", "metric_store_io", ...}  # post-split fragments

def test_every_module_has_a_test_file():
    modules = {p.stem for p in (ROOT / "modules").glob("*.py") if not p.stem.startswith("_")}
    tests   = {p.stem.replace("test_", "") for p in (ROOT / "tests").glob("test_*.py")}
    missing = modules - tests - EXEMPT
    assert not missing, f"Modules with no test file: {sorted(missing)}"
```

This gate prevents regressions silently accruing new untested modules.

---

## S10 — Hardcoded Colour Purge (RULE-1 / RULE-AH3)

**Source:** APM rules/docs/codebase audit — 2026-05-29.

44 UI files contain raw hex colour strings (`#005A9E`, `#EAEAEA`, `#fff`, etc.) in
`setStyleSheet()` calls and widget constructors. RULE-1 and RULE-AH3 both prohibit
this. The practical risk is theme-switching breakage: colours hardcoded in page
files override the theme tokens in `ui/styles.py`, causing widgets to ignore
Midnight Pro and Obsidian Neon themes entirely.

### S10-1  Inventory missing tokens in `ui/styles.py`
Before touching page files, audit all hex strings found in the 44 files and
determine which are already present in `ui/styles.py` under a different name, and
which are genuinely missing. Add missing tokens to `ui/styles.py` with descriptive
names. Never add a token whose value duplicates an existing one — use the existing
name. Common gaps identified in the audit:
- `#254A6E` — deep navy (used in automation, connections pages)
- `#005A9E`, `#005FA3`, `#006BBD` — accent dark variants → map to `ACCENT_DARK`
- `#EAEAEA`, `#ECECEC` — light grey borders → map to `BORDER` or add `BORDER_LIGHT`
- `#9BA8B4`, `#B0C4D8` — muted blue-grey → map to `TEXT_SECONDARY` or add token
- `#1e2d3d`, `#3a4f63` — dark chart backgrounds → add to `modules/colours.py`

### S10-2  Batch-replace hardcoded hex in `ui/pages/*.py`
Work file-by-file. For each replacement:
1. Identify the token name in `ui/styles.py`.
2. Ensure `from ui.styles import TOKEN` is at the top of the file.
3. Replace the hex string with the token inside the f-string or direct call.
4. Run `python tools/debug_launch.py` after every file — do not batch across files.

Priority order (largest violation count first):
`baseline_page`, `geo_map_page`, `dhcp_lease_page`, `diagnosis_page`, `dns_zone_page`,
`home_page`, `hardware_integration_page`, then remaining 30 pages.

### S10-3  Batch-replace hardcoded hex in `ui/widgets/*.py` and root `ui/` files
Same process as S10-2. Affected: `coach_mark.py`, `density_toggle.py`,
`device_popover.py`, `explainer_panel.py`, `page_header.py`, `protocol_canvas.py`,
`pulsing_dot.py`, `dashboard.py`, `live_graph.py`, `first_run_dialog.py`,
`system_tray.py`, `npcap_banner.py`.

### S10-4  Enforce via `test_codeql_prevention.py` extension
Extend the existing `test_codeql_prevention.py` (created in S4-1) with:

```python
_HEX_PATTERN = re.compile(r'["\'](#[0-9A-Fa-f]{3,6})["\']')
_ALLOWED_FILES = {Path("ui/styles.py"), Path("modules/colours.py")}

def test_no_hardcoded_hex_outside_style_files():
    offenders = []
    for path in ROOT.glob("ui/**/*.py"):
        if path.relative_to(ROOT) in _ALLOWED_FILES:
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if _HEX_PATTERN.match(repr(node.value)):
                    offenders.append((path.name, node.lineno, node.value))
    assert not offenders, f"Hardcoded hex colours: {offenders[:10]}"
```

This gate is CI-blocking once S10-2 and S10-3 are complete.

---

## S11 — Page Help & Feature Discoverability (RULE-D1 + RULE-D2)

**Source:** APM rules/docs/codebase audit — 2026-05-29.

Two discoverability rules are violated across the board:
- **RULE-D1**: zero `_PAGE_HELP` entries exist in `dashboard.py` (61 nav labels need one each)
- **RULE-D2**: 25 of 61 pages have no `_FEATURES` entry; 4 existing entries reference stale nav labels

Without `_PAGE_HELP`, the `?` help button on every page is silently empty.
Without `_FEATURES`, nearly half the app's pages are invisible to the Feature Guide.

### S11-1  Add `_PAGE_HELP` entries for all 61 nav labels
`_PAGE_HELP` entries live in `ui/dashboard.py`. Add all 61 entries following the
pattern in RULE-D1. Each entry needs a short title (≤60 chars) and one or two plain-
English sentences. Group entries by nav section so they can be reviewed at a glance.
Example for a currently-missing entry:
```python
_PAGE_HELP["Threat Intel"] = (
    "Threat Intelligence Lookup",
    "Query IPs found in your scan against AbuseIPDB and the local threat database. "
    "First use requires consent to enable external lookups."
)
```

### S11-2  Fix 4 stale `_FEATURES` page references in `discover_page.py`
The `"page"` field in `_FEATURES` must exactly match the nav label string passed to
`_nav_add_rail_item()`. Four entries are broken:

| Current (broken) | Correct nav label |
|---|---|
| `"Diagnose"` | `"What's Wrong?"` |
| `"Logs"` | `"Network Logger"` |
| `"Network Timeline"` | `None` (not navigable) |
| `"Threat Intelligence"` | `"Threat Intel"` |

### S11-3  Add 25 missing `_FEATURES` entries in `discover_page.py`
Every page listed below must have an entry added to `_FEATURES` (all six fields
mandatory per RULE-D2). Assign to the most accurate `group`:

| Page label | Suggested group |
|---|---|
| Bandwidth Usage | `"Monitoring"` |
| CVE Tracker | `"Security"` |
| Cloud Metadata Probe | `"Security"` |
| Config Snapshots | `"Advanced"` |
| Custom Triggers | `"Advanced"` |
| DHCP Rogue Monitor | `"Security"` |
| Device Risk Score | `"Security"` |
| Exposed to Internet | `"Security"` |
| Full Device Discovery | `"Security"` |
| Help & Reference | `"Hidden Features"` |
| Home Automation | `"Monitoring"` |
| IPv6 Devices | `"Monitoring"` |
| Inventory Changes | `"Monitoring"` |
| Login Test | `"Security"` |
| Maintenance Windows | `"Advanced"` |
| OS Detection | `"Security"` |
| Port Scan (TCP) | `"Security"` |
| Port Scan (UDP) | `"Security"` |
| Private Endpoint Check | `"Security"` |
| Recon Plugins | `"Security"` |
| SNMP Device Info | `"Advanced"` |
| Threat Intel | `"Security"` |
| Trend Forecasts | `"Advanced"` |
| Windows Shares (SMB) | `"Security"` |

### S11-4  CI gate for help + feature parity
Extend `tests/test_nav_completeness.py` with two new checks:
1. Every label in `_nav_item_labels` has a non-empty `_PAGE_HELP` entry.
2. Every label in `_nav_item_labels` has a `_FEATURES` entry whose `"page"` either
   matches the label exactly or is `None` (intentionally non-navigable).

---

## S12 — PyInstaller Spec Integrity (RULE-B1)

**Source:** APM rules/docs/codebase audit — 2026-05-29.

Two modules are missing from `hiddenimports` in `NetSentinel.spec`. Both exist on
disk and are documented in the architecture, but will produce `ModuleNotFoundError`
at runtime in an installed build — a failure mode that does not appear in source
runs or the test suite, only in production.

Four additional spec entries are duplicated, which adds noise but is otherwise
harmless.

### S12-1  Add missing hiddenimports
In `NetSentinel.spec`, add to the `hiddenimports` list:
- `"modules.nspkg"`
- `"modules.plugin_tools"`

### S12-2  Deduplicate spec entries
Remove the duplicate occurrences of:
- `"modules.deco_client"` (appears twice)
- `"modules.diagnostic_card"` (appears twice)
- `"modules.wifi_heatmap"` (appears twice)
- `"ui.pages.trigger_builder_page"` (appears twice)

### S12-3  CI gate for spec completeness
Add `tests/test_spec_hiddenimports.py`:

```python
def test_all_modules_in_spec_hiddenimports():
    spec = Path("NetSentinel.spec").read_text()
    missing = []
    for path in sorted(Path("modules").glob("*.py")):
        if path.stem.startswith("_"):
            continue
        key = f'"modules.{path.stem}"'
        if key not in spec:
            missing.append(key)
    assert not missing, f"Missing from hiddenimports: {missing}"
```

Run as part of the pre-release checklist (not the main suite — spec is build
artefact, not source).

---

## S13 — dashboard.py Tab Builder Extraction (Critical remaining S1 work)

`_build_tabs()` (884 lines) and the sibling tab-builder methods account for ~3,000 lines of
dashboard.py.  They build the UI for each security audit result tab (Port Scan, CVE, SYN,
UDP, OS fingerprint, exposure, etc.) and have zero dependency on the nav shell.  Extracting
them is the single highest-leverage step remaining on the S1 goal.

### S13-1  Extract `ui/tabs/` package

```
ui/tabs/__init__.py         # re-exports tab factory functions
ui/tabs/scan_tabs.py        # _build_m1_tab, _build_tabs (all security scan tabs)
ui/tabs/diag_tabs.py        # _build_diagnostics_tab, _build_benchmark_tab, _build_logger_tab
ui/tabs/network_tabs.py     # _build_network_info_tab, _build_advanced_tools_tab
```

Each file contains pure UI-construction functions that take `window: Dashboard` as their
first argument (same pattern used by `ScanResultMixin`).  Called once from `Dashboard._build_ui()`.

Target: `dashboard.py` ≤ 7,000 lines after this split.

### S13-2  Extract `_build_help_tab()` to `ui/help.py` (complete S1-3)

`_build_help_tab()` (585 lines) and its `_section()`, `_entry()`, `_subsection()` helpers
are still in `dashboard.py`.  Extract to `ui/help.py` as `build_help_tab(window)`.
The `_PAGE_HELP` dict is already there from S1-3 partial.

Target: removes 600+ lines from `dashboard.py`.

### S13-3  Extract `_build_header()` and `_build_update_bar()` to `ui/header.py`

The top application bar builder (`_build_header`, 246 lines, plus `_build_mode_bar`,
`_build_update_bar`, `_toggle_maximize`, `changeEvent`, `resizeEvent`, `showEvent`,
`_install_snap_subclass`, `_install_edge_grips`) is a self-contained frameless-window
concern.  Extract to `ui/header.py`.

Target: removes ~500 lines from `dashboard.py`.

### S13-4  Extract settings persistence to `ui/app_settings.py`

`_restore_settings()` (109 lines), `_save_settings()`, and related QSettings methods form
a standalone persistence layer.  Extract to `ui/app_settings.py` as
`restore_settings(window)` and `save_settings(window)`.

Target: removes ~250 lines from `dashboard.py`.

### S13-5  Tighten `KNOWN_LARGE_UI_FILES["dashboard.py"]` budget after each split

After S13-1: set budget to **7,200**.
After S13-2: set budget to **6,500**.
After S13-3: set budget to **6,000**.
After S13-4: set budget to **5,700**.
Final target once all S1+S13 splits are complete: **3,000**.

---

## S14 — Complete Oversize Page Reductions

The original S3 sprint intended to reduce large page files.  Sprint 4 delivered
S3-1, S3-2, S3-3 but not their targets.  This section tracks the remaining reductions.

### S14-1  Complete home_page.py split (2,747 → ≤1,200)

The `HomePage` class contains six large `_build_*` section methods that are standalone
UI concerns.  Extract each as a `QWidget` subclass to `ui/widgets/home_widgets.py`
(which already exists from S3-3):

- `_build_hero_section()` → `HeroCard(QWidget)` — grade ring + sparkline + metrics
- `_build_suggestions_strip()` → `SuggestionsStrip(QWidget)` — "What to do next" cards
- `_build_digest_card()` → `DigestCard(QWidget)` — weekly digest notification
- `_build_tips_card()` → `TipsCard(QWidget)` — dismissible quick tips
- `_build_since_last_session()` → `SessionBanner(QWidget)` — new devices / outages
- `_build_dashboard_strip()` → `DashboardStrip(QWidget)` — browser dashboard link

Each extracted widget is independently testable.  Target: home_page.py ≤ 1,200 lines.

### S14-2  Complete hardware_integration_page.py reduction (1,701 → ≤900)

The S3-1 target was ~800 lines; actual is 1,701.  The remaining 800+ lines of excess are:
- `_build_guide_section()` and its "How to write a plugin" content blocks (~400 lines)
- `_build_hub_grid()` and card layout management (~300 lines)
- Worker setup for community download threads (~100 lines)

The guide section has no dependency on the hub grid.  Extract to `ui/widgets/plugin_guide.py`.

### S14-3  Add 5 untracked large pages to `KNOWN_LARGE_UI_FILES`

All five pages below exceed `UI_DEFAULT_BUDGET` (1,000 lines) and are invisible to the
LOC gate:

| Page | Lines | Split target | Split note |
|------|-------|--------------|------------|
| `notifications_page.py` | 1,812 | 900 | Extract per-channel config panels |
| `log_hub_page.py` | 1,648 | 900 | Extract `LogSourcePanel` base class |
| `settings_page.py` | 1,526 | 800 | Extract per-section `QWidget` subclasses |
| `speed_test_page.py` | 1,336 | 800 | Extract modem signal panel |
| `discover_page.py` | 1,319 | 800 | Extract feature card widget |

Add all five to `KNOWN_LARGE_UI_FILES` in `test_module_loc.py` immediately — even before
splitting — so they cannot grow further without a failing test.

---

## S15 — New Widget File Governance

Sprint 4 created three large new files that are not yet tracked by any LOC gate.

### S15-1  Register Sprint 4 new files in `KNOWN_LARGE_UI_FILES`

Add to `test_module_loc.py::KNOWN_LARGE_UI_FILES`:

```python
# Hub card widget + all plugin helper functions.
# Further split: helper functions → ui/widgets/hub_helpers.py (target: hub_card.py ≤ 900)
"hub_card.py": 1950,

# All Overview tile classes + _TILE_CLASSES/_DEFAULT_ORDER.
# Single concern, appropriate size for now.  Watch for growth.
"overview_tile.py": 1650,

# ScanResultMixin — all _on_*_result handlers.
# If new scan types are added, split by domain: security_wiring.py, monitor_wiring.py.
"scan_wiring.py": 1200,
```

Note: these budgets apply to the `ui/` root and `ui/widgets/` directories.  Update
the LOC test to also check `ui/widgets/*.py` and `ui/scan_wiring.py`.

### S15-2  Split `hub_card.py` (1,902 → ≤ 900 + helpers)

The 700-line helper section in `hub_card.py` (`_load_health`, `_record_success`,
`_load_paths`, `_save_paths`, `_load_instances`, etc.) has no widget-level logic — it is
purely data persistence and health tracking.  Extract to `ui/widgets/hub_helpers.py`.

```
ui/widgets/hub_helpers.py    # all helper functions and constants (lines 25–700)
ui/widgets/hub_card.py       # HubCard, _ModemDetailPanel, _RouterDetailPanel, PipInstallDialog (~800 lines)
```

`hardware_integration_page.py` import block updates accordingly.

### S15-3  Document mock-patch canonical locations

Add to `tests/CLAUDE.md` (test conventions):

```
## Mock patch canonical locations

When patching functions that live in ui/widgets/ but are re-exported by ui/pages/:
  → Patch at the DEFINITION site, not the re-export site.

  # WRONG — patches the re-export namespace, not where the code runs
  patch("ui.pages.hardware_integration_page._save_health", ...)

  # CORRECT — patches where _record_success actually looks up _save_health
  patch("ui.widgets.hub_card._save_health", ...)

Files currently re-exporting from hub_card:
  ui/pages/hardware_integration_page.py → all hub_card symbols
```

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
structural changes (S1/S13), then module splits (S2), then data-layer health (S6),
then worker coverage (S5), then test/prevention coverage (S9, S10).

| # | Item | Sprint | Version Target | Notes |
|---|---|---|---|---|
| 1 | ✅ S0-1: Identify Qt-crash culprit | 1 | v1.9.56 | Root cause: QFileSystemWatcher OS threads; fixed with MagicMock patch |
| 2 | ✅ S0-2: Session-scoped QApplication fixture | 1 | v1.9.56 | Removed module-level QApplication from 7 test files (RULE-WIN3) |
| 3 | ✅ S0-3: QSettings isolation fixture | 1 | v1.9.56 | `isolated_settings` autouse fixture added to conftest.py |
| 4 | ✅ S0-4: Full suite green gate | 1 | v1.9.56 | 2136 passed, 4 skipped, exit 0 |
| 5 | ✅ S4-1: `test_codeql_prevention.py` | 1 | v1.9.56 | bare-except + URL-substring AST checks |
| 6 | ✅ S8-1: Mark robustness plan complete | 1 | v1.9.56 | PLUGIN_ROBUSTNESS_PLAN.md already in docs/completed/ |
| 7 | ✅ S1-1: Extract `ui/nav/` package (widget classes) | 3 | v1.9.58 | `_RailButton`, `_FlyoutPanel` etc. → `ui/nav/rail.py`; dashboard.py −683 lines |
| 8 | ✅ S1-2: Extract scan-result wiring | 4 | v1.9.59 | ScanResultMixin → `ui/scan_wiring.py`; dashboard.py −1,163 lines (10,046); 14 orphaned decorators removed |
| 9 | ✅ S1-3 partial: Extract `_PAGE_HELP` dict to `ui/help.py` | 2 | v1.9.58 | 455 lines removed; `_build_help_tab()` (585 lines) still in dashboard.py — completed by S13-2 |
| 10 | ✅ S1-4: Add dashboard LOC budget test | 2 | v1.9.58 | `test_module_loc.py::KNOWN_LARGE_UI_FILES["dashboard.py"] = 13700` — budget must be tightened (see S13-5) |
| 11 | ✅ S3-1: Extract HubCard to widget | 4 | v1.9.59 | Hub card family → `ui/widgets/hub_card.py` (1,902 lines); hardware_integration_page.py 4,055→1,701 lines |
| 12 | ✅ S3-2: Extract OverviewTile | 4 | v1.9.59 | All tile classes → `ui/widgets/overview_tile.py` (1,620 lines); overview_page.py 2,536→633 lines |
| 13 | ✅ S3-3 partial: Extract home helper widgets | 4 | v1.9.59 | 4 helper classes → `ui/widgets/home_widgets.py`; home_page.py 3,027→2,747 lines; section widgets NOT extracted — see S14-1 |
| 14 | ✅ S8-2: Architecture docs update | 4 | v1.9.59 | CLAUDE.md + .apm/instructions + .github/instructions all updated with Sprint 4 new modules |
| — | **— Sprint 5 (target v1.9.60) —** | — | — | — |
| 15 | ✅ S15-1: Register Sprint 4 new files in `KNOWN_LARGE_UI_FILES` | 5 | v1.9.60 | hub_card.py (2250), overview_tile.py (1950), scan_wiring.py (1300); 5 untracked pages added (S14-3); paths now relative to ui/ to support subdirs |
| 16 | ✅ S13-5a: Tighten dashboard.py budget to 11,312 | 5 | v1.9.60 | Actual was 11,112 (not 10,046 as plan estimated); budget set to actual+200 |
| 17 | ✅ S2-1: Split metric_store (1,673 → 623/449/547 lines) | 5 | v1.9.60 | metric_store_schema.py (DDL+dataclasses) + metric_store_queries.py (MetricStoreQueryMixin); 54+20 tests pass; budget tightened to 650 |
| 18 | ✅ S2-2: Split report_exporter (1,241 → 716/376/118 lines) | 5 | v1.9.60 | report_html.py (CSS+HTML helpers) + report_pdf.py (PDF cascade); 61 tests pass; budget tightened to 750 |
| 19 | ✅ S2-3: Split utils (1,055 → 421/458/171 lines) | 5 | v1.9.60 | utils_net.py (get_network_info etc.) + utils_platform.py (IPv6 scanning); utils.py exemption removed (now ≤600); 28+11 tests pass |
| 20 | ✅ S2-4: Tests for new module files | 5 | v1.9.60 | test_metric_store_schema.py (12), test_metric_store_queries.py (20), test_utils_net.py (6), test_utils_platform.py (5), test_report_html.py (16) |
| 21 | ✅ S6-1: WAL growth guard | 5 | v1.9.60 | `_checkpoint_wal_if_needed()` in MetricStore.__init__; triggers at 50 MB |
| 22 | ✅ S6-2: VACUUM on schema upgrade | 5 | v1.9.60 | `PRAGMA VACUUM` added to `apply_sqlite_schema()` in metric_store_schema.py |
| 23 | ✅ S6-3: Connection busy timeout | 5 | v1.9.60 | `PRAGMA busy_timeout = 5000` in MetricStore._conn property |
| 24 | ✅ S6-4: `test_metric_store_concurrency.py` | 5 | v1.9.60 | 5 tests: concurrent write, busy_timeout, WAL checkpoint trigger, schema+VACUUM, read consistency |
| 25 | ✅ S5-1: Worker coverage audit | 5 | v1.9.60 | 16 of 20 workers covered in test_worker_lifecycle.py; 3 gaps found: hw_detect, plugin, wifi_monitor |
| 26 | ✅ S5-2: `test_worker_lifecycle_full.py` | 5 | v1.9.60 | HwDetectWorker, PluginWorker, WiFiMonitorWorker; 10 tests pass |
| 27 | ✅ S5-3: `_running` flag audit | 5 | v1.9.60 | scan_worker.py `while True` loops confirmed as queue-drain patterns (always break); no violations |
| — | **— Sprint 6 (target v1.9.61) —** | — | — | — |
| 28 | ✅ S13-1: Extract `ui/tabs.py` — `TabBuilderMixin` | 6 | v1.9.61 | `_build_tabs`, `_build_m1_tab`–`_build_advanced_tools_tab` etc. → `TabBuilderMixin`; dashboard.py 9,776→6,540 lines (−3,236) |
| 29 | ✅ S13-2: Complete `_build_help_tab()` extraction to `ui/help.py` | 6 | v1.9.61 | 587-line method extracted as `build_help_tab(window)`; `_page_header` helper moved too |
| 30 | ✅ S13-3: Extract `AppHeaderMixin` to `ui/header.py` | 6 | v1.9.61 | `_build_header`, `_DragHeader`, `_install_snap_subclass`, `_install_edge_grips`, `_build_update_bar`, etc. → `AppHeaderMixin` (659 lines) |
| 31 | ✅ S13-4: Extract settings persistence to `ui/app_settings.py` | 6 | v1.9.61 | `save_settings()`, `restore_settings()`, `center_on_screen()` extracted; dashboard.py −166 lines |
| 32 | ✅ S13-5b: Tighten dashboard.py budget to 6,740 (actual 6,540+200) | 6 | v1.9.61 | Far exceeded target of 7,200; budget updated in test_module_loc.py |
| 33 | ✅ S14-1: home_page.py split (3,032 → 2,238 lines) | 7 | v1.9.61 | FreshnessStrip + GettingStartedCard extracted to home_widgets.py; encoding mojibake fixed |
| 34 | ✅ S14-2: hardware_integration_page.py → plugin_guide.py (1,934 → 1,782 lines) | 7 | v1.9.62 | 4-step guide widget extracted to plugin_guide.py |
| 35 | ✅ S15-2: Split hub_card.py → hub_helpers.py (2,209 → 1,665 lines) | 6 | v1.9.61 | Pure helpers extracted to `ui/widgets/hub_helpers.py` (577 lines); patch targets updated in 3 test files |
| 36 | ✅ S15-3: Document mock-patch canonical locations in tests/CLAUDE.md | 6 | v1.9.61 | Section added; hub_card vs hub_helpers re-export relationship documented |
| 37 | ✅ S7-1: Lazy-import audit | 6 | v1.9.61 | All optional imports already guarded; `requests` in deco_client/zte_client is a required dep — no violations |
| 38 | ✅ S7-2: Startup profiling script | 6 | v1.9.61 | `tools/startup_profile.py` created — stage timing with 3 s threshold warning |
| 39 | ✅ S7-3: Debug log rotation | 6 | v1.9.61 | `tools/debug_launch.py` rotates to `netsentinel_debug_YYYYMMDD_HHMMSS.log`; last 5 kept |
| 40 | ✅ S4-2: Pre-commit Step 0 added to CLAUDE.md commit gate | 6 | v1.9.61 | `test_codeql_prevention.py` + `test_interactive_states.py` run before full suite |
| 41 | ✅ S8-3: Version history in CLAUDE.md updated | 6 | v1.9.61 | Sprint summary table v1.9.40–v1.9.60 added to CLAUDE.md |
| — | **— Sprint 7+ (target v1.9.62+) —** | — | — | — |
| 42 | ✅ S14-3a: notifications_page.py → notif_channel_panels.py (2,025 → 296 lines) | 7 | v1.9.62 | _NotifChannelsMixin with all card builders, log panel, test helpers |
| 43 | ✅ S14-3b: log_hub_page.py → log_source_panel.py (1,848 → 892 lines) | 7 | v1.9.62 | _LogSourcePanelMixin + shared constants/helpers in log_source_panel.py |
| 44 | ✅ S14-3c: settings_page.py → settings_cards.py (1,730 → 275 lines) | 7 | v1.9.62 | _SettingsCardsMixin + workers + helpers in settings_cards.py |
| 45 | S13-5c: Tighten dashboard.py budget to 5,000 | 7 | v1.9.62 | After all S13 and S14 splits land — dashboard at 6,540; further extraction needed |
| — | **— Sprint 8 (target v1.9.62) —** | — | — | — |
| 62 | ✅ LOC budget tightening — Sprint 7 follow-up | 8 | v1.9.62 | notifications_page→496, settings_page→482, log_hub_page→1092, hardware_integration_page added at 1986; 4 new Sprint 7 files tracked (notif_channel_panels 1843, log_source_panel 1137, settings_cards 1533) |
| 63 | ✅ tabs.py sub-mixin split (3,302→949 lines) | 8 | v1.9.62 | `_ScanTabsMixin`→`ui/tabs_scan.py` (739 lines); `_NetworkTabsMixin`→`ui/tabs_network.py` (347 lines); `_DiagTabsMixin`→`ui/tabs_diag.py` (1,182 lines); helper functions→`ui/tabs_helpers.py` (222 lines); tabs.py budget tightened to 1,149 |
| 64 | ✅ NetSentinel.spec: add 4 new tabs sub-modules | 8 | v1.9.62 | `ui.tabs_helpers`, `ui.tabs_scan`, `ui.tabs_network`, `ui.tabs_diag` added to hiddenimports (RULE-B1) |
| — | **— Sprint 9 (target v1.9.62) —** | — | — | — |
| 65 | ✅ S14-2 complete: hardware_integration_page.py (1,786→741 lines) | 9 | v1.9.62 | credential_dialog.py + plugin_wizard_mixin.py + hardware_browse_mixin.py extracted; 3 test files updated; spec + architecture docs updated |
| 66 | ✅ S9-1: Tests for Tier 1 modules (8 modules) | 9 | v1.9.62 | test_colours.py, test_exporter.py, test_log_chart.py, test_mac_lookup.py, test_name_resolver.py, test_nl_query.py, test_protocol_animator.py, test_web_dashboard.py — 54 new tests |
| 67 | ✅ S13-5c: dashboard.py dead code removal — flat-nav mode system purged | 10 | v1.9.62 | Removed `_nav_mode`, `_nav_goto_label`, `_update_mode_pill`, `_cycle_mode`, `_set_mode`, `_rail_mode_btn`; `_nav_go_to` simplified to direct rail delegate; 5 files changed; 2449 tests pass |
| — | **— TBD sprints —** | — | — | — |
| 46 | ✅ S10-1: Inventory missing colour tokens | 10 | v1.9.62 | `test_colour_inventory.py` — per-file budget tables for 63 UI files + 7 module files; 3 tests; baseline locked for purge sprints |
| 47 | ✅ S10-2: Purge hardcoded hex from `ui/pages/*.py` (37+ files) | 12 | v1.9.62 | ALL 63 tracked UI files purged to 0 hex violations |
| 48 | ✅ S10-3: Purge hardcoded hex from `ui/widgets/*.py` + root `ui/` | 12 | v1.9.62 | Included in S10-2 complete purge (63 files total) |
| 49 | ✅ S10-4: Add hex-colour AST gate to `test_codeql_prevention.py` | 14 | v1.9.64 | `test_no_hardcoded_hex_in_ui_files()` — AST walker catches new violations before CI; Sprint 14 |
| 50 | ✅ S9-1: Tests for Tier 1 modules — utility/plumbing (8 modules) | 9 | v1.9.62 | Delivered Sprint 9 |
| 51 | ✅ S9-2: Tests for Tier 2 modules — scan/detection (18 modules) | 10 | v1.9.62 | arp_monitor, bandwidth_monitor, cloud_metadata, dns_correlator, dns_zone_scanner, ha_detector, internet_exposure, os_fingerprint, port_scanner, process_monitor, rogue_device, smb_enumerator, snmp_poller, storm_analyser, stp_detector, syn_scanner, threat_intel, wifi_scanner — 140 new tests |
| 52 | ✅ S9-3: Tests for Tier 3 modules — report/enrichment (10 modules) | 12 | v1.9.62 | diagnostic_card, digest_builder, hw_detect, lab_scenarios, network_diagnostics, private_endpoint_checker, speed_tester, combined_discovery + dhcp_detector/dhcp_lease_scanner — 73 new tests |
| 53 | ✅ S9-4: `test_module_coverage_gate.py` — CI gate for module test completeness | 14 | v1.9.64 | All 70 modules covered (2 exempt: metric_store_schema, metric_store_queries, report_html); Sprint 14 |
| 54 | S3-4: Update `test_module_loc.py` to remove exemptions post-split | TBD | TBD | Remove each KNOWN_LARGE_MODULES entry as its split lands |
| — | **— APM audit findings (2026-05-29) — delivered below —** | — | — | — |
| 55 | ✅ S12-1: Add `modules.nspkg` + `modules.plugin_tools` to spec hiddenimports | 2 | v1.9.58 | Done; `ui.help` also added |
| 56 | ✅ S12-2: Deduplicate 4 duplicate spec entries | 2 | v1.9.58 | Removed deco_client, diagnostic_card, wifi_heatmap, trigger_builder_page duplicates |
| 57 | ✅ S12-3: `test_spec_hiddenimports.py` CI gate | 2 | v1.9.58 | 2 tests: all-modules-present + no-duplicates |
| 58 | ✅ S11-2: Fix 7 stale `_FEATURES` page refs in `discover_page.py` | 2 | v1.9.58 | Fixed: Logs→Network Logger (×4), Diagnose→What's Wrong?, Threat Intelligence→Threat Intel |
| 59 | ✅ S11-3: Add 23 missing `_FEATURES` entries | 2 | v1.9.58 | All nav-registered pages now have Feature Guide entries |
| 60 | ✅ S11-1: Fix `_PAGE_HELP` quality issues | 3 | v1.9.58 | Removed duplicate "Bandwidth Usage" key; all 64 nav labels confirmed |
| 61 | ✅ S11-4: CI gate — nav/help/features parity check | 3 | v1.9.58 | Two new tests in `test_nav_completeness.py`; stale "Connectivity Tests" ref fixed |

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

9. **LOC budgets must be tightened after every split, not set once at baseline.**
   A budget set at creation time (e.g., dashboard.py = 13,700 at v1.9.54) becomes
   meaningless after the file shrinks.  Every sprint that reduces a file must tighten
   the budget to `current_actual + 200`.  Otherwise the test catches only dramatic
   regression, not slow re-accumulation.

10. **New large files need budgets at creation time, not retroactively.**
    When a split creates a new file that is itself large (e.g., hub_card.py at 1,902),
    add it to `KNOWN_LARGE_UI_FILES` in the same PR that creates it.  A file with no
    budget entry silently grows without bound.

11. **Extraction tools must capture decorator lines, not just def lines.**
    When extracting methods from a class using AST node positions, `node.lineno` is
    the `def` line — decorator lines at `node.lineno - N` are NOT included.  Any
    extraction script must scan backwards from `node.lineno` to include all
    `@decorator` lines.  Failure to do so leaves orphaned decorators that accidentally
    decorate unrelated functions, causing `TypeError: decorated slot has no signature
    compatible` at runtime.

---

*Plan created 2026-05-29.  Continues from PLUGIN_ROBUSTNESS_PLAN.md (v1.9.54).*
*Re-audited 2026-05-30 post-Sprint-4 (13 new findings added, S13/S14/S15 sections added).*
*Sprint 1: v1.9.57.  Sprint 2: v1.9.58.  Sprint 3: v1.9.58.  Sprint 4: v1.9.59.  Sprint 5: v1.9.60.  Sprint 6: v1.9.61.  Sprint 7: v1.9.61.  Sprint 8: v1.9.62 (tabs.py split complete 2026-05-31).  Sprint 12: v1.9.62 (hex purge complete 2026-05-31).*

**Sprint 3 delivered (2026-05-30):** S1-1 (nav widget classes → `ui/nav/rail.py`; −683 lines), S11-1 (PAGE_HELP duplicate key fixed), S11-4 (CI parity gates added).

**Sprint 4 delivered (2026-05-30):** S1-2 (ScanResultMixin → `ui/scan_wiring.py`; dashboard.py −1,163 lines; 14 orphaned decorators removed), S3-1 (hub_card.py created; hardware_integration_page.py 4,055→1,701), S3-2 (overview_tile.py created; overview_page.py 2,536→633), S3-3 partial (home_widgets.py created; home_page.py 3,027→2,747; section widgets NOT extracted). S8-2 done (architecture docs synced).

**Sprint 5 delivered (2026-05-30):** S15-1+S13-5a (LOC gate updated: 9 new entries, dashboard budget tightened to 11,312), S2-1 (metric_store split: schema+queries extracted; 623+449+547 lines; WAL/VACUUM/busy_timeout health improvements), S2-2 (report_exporter split: report_html+report_pdf; 716+376+118 lines), S2-3 (utils split: utils_net+utils_platform; 421+458+171 lines), S2-4+S6-4 (90 new tests across 5 new test files), S5-2 (test_worker_lifecycle_full.py; HwDetect+Plugin+WiFiMonitor workers), S5-3 (scan_worker queue-drain patterns confirmed safe). 2226 tests pass, 4 skipped.

**Sprint 6 delivered (2026-05-30):** S13-1 (TabBuilderMixin → `ui/tabs.py`; dashboard.py 9,776→6,540 lines, −3,236), S13-2 (build_help_tab → `ui/help.py`; −587 lines), S13-3 (AppHeaderMixin → `ui/header.py`; −659 lines), S13-4 (settings persistence → `ui/app_settings.py`; −166 lines), S13-5b (dashboard budget tightened to 6,740), S15-2 (hub_helpers.py from hub_card.py; hub_card.py 2,209→1,665), S15-3 (mock-patch docs in tests/CLAUDE.md), S7-1 (lazy-import audit — clean), S7-2 (tools/startup_profile.py), S7-3 (debug_launch.py log rotation), S4-2 (Step 0 pre-commit gate), S8-3 (version history table in CLAUDE.md). 2231 tests pass, 4 skipped.

**Sprint 7 delivered (2026-05-30):** S14-1 ✅ home_page.py 3,032→2,238 lines; S14-2 ✅ hardware_integration_page.py 1,934→1,782 lines (plugin_guide.py extracted); S14-3a ✅ notifications_page.py 2,025→296 lines (notif_channel_panels.py); S14-3b ✅ log_hub_page.py 1,848→892 lines (log_source_panel.py); S14-3c ✅ settings_page.py 1,730→275 lines (settings_cards.py). 2243 tests pass, 4 skipped.

**Sprint 8 delivered (2026-05-31):** LOC budget tightening for all Sprint 7 splits (notifications→496, settings→482, log_hub→1092, hardware_integration added at 1986, notif_channel_panels+log_source_panel+settings_cards all tracked); tabs.py sub-mixin split (3,302→949 lines) — `_ScanTabsMixin` → `ui/tabs_scan.py` (739 lines), `_NetworkTabsMixin` → `ui/tabs_network.py` (347 lines), `_DiagTabsMixin` → `ui/tabs_diag.py` (1,182 lines), helper functions → `ui/tabs_helpers.py` (222 lines); spec updated with 4 new hiddenimports. 2247 tests pass, 4 skipped.

**Sprint 9 delivered (2026-05-31):** S14-2 complete ✅ hardware_integration_page.py 1,786→741 lines — `ui/widgets/credential_dialog.py` (show_credential_dialog + show_unsigned_warning), `ui/pages/plugin_wizard_mixin.py` (_PluginWizardMixin), `ui/pages/hardware_browse_mixin.py` (_HardwareBrowseMixin) extracted; S9-1 ✅ 54 new tests across 8 Tier 1 modules; S13-5c deferred (old flat-nav + tabs.py intertwined; needs coordinated removal). 2309 tests pass, 4 skipped.

**Sprint 10 delivered (2026-05-31):** S13-5c ✅ flat-nav dead-code removal — `_nav_mode`, `_nav_goto_label`, `_update_mode_pill`, `_cycle_mode`, `_set_mode`, `_rail_mode_btn` removed; `_nav_go_to` simplified to rail delegate; 5 files (dashboard.py, tabs.py, header.py, app_settings.py + ui/); S9-2 ✅ 18 Tier 2 scan/detection module tests — 140 new tests across arp_monitor, bandwidth_monitor, cloud_metadata, dns_correlator, dns_zone_scanner, ha_detector, internet_exposure, os_fingerprint, port_scanner, process_monitor, rogue_device, smb_enumerator, snmp_poller, storm_analyser, stp_detector, syn_scanner, threat_intel, wifi_scanner; S10-1 ✅ colour token inventory — test_colour_inventory.py with per-file budgets for 63 UI files + 7 module files. 2452 tests pass, 4 skipped.

**Sprint 11 partial (2026-05-31):** S10-2 started — `INPUT_PLACEHOLDER` token added to all 3 themes in `ui/styles.py`; 5 pages purged to 0 hex violations: `home_page.py` (13→0), `diagnosis_page.py` (9→0), `threat_intel_page.py` (16→0), `dns_zone_page.py` (13→0), `dhcp_lease_page.py` (7→0); inventory budgets lowered. Token mapping used: `#fff/#FFFFFF→WHITE`, `#005A9E/#006BBD/#005FA3/#1A6FC4→ACCENT_DARK`, `#ECECEC→CARD_HDR_BORDER`, `#B0C4D8→BTN_DISABLED_BORDER`, `#9BA8B4→INPUT_PLACEHOLDER`, `#F4F4F4→BG_DARK`, `#E0E8EF/#E0E7F0→PROGRESS_TRACK`. Session ended at token limit.

**Sprint 12 delivered (2026-05-31):** S10-2 ✅ complete — ALL 63 tracked UI files purged to 0 hex violations (53 new constants added to `ui/styles.py`: MAP_LAND_*, IP_CALC_*, LOG_SOURCE_PLUGIN, GRADE_B_COLOR, BLACK, ORANGE, STATUS_OFFLINE, INLINE_WARN_*, BADGE_OK/OFF_*, TEAL, DEEP_ORANGE, ACCENT_PURPLE, INFO_BOX_*, HTML_*, OVERLAY_*, CANVAS_*); inventory budgets all lowered to 0 in test_colour_inventory.py (ratchet locked). S9-3 ✅ 73 new tests across 10 Tier 3 modules — dhcp_detector, dhcp_lease_scanner, diagnostic_card, digest_builder, hw_detect, lab_scenarios, network_diagnostics, private_endpoint_checker, speed_tester, combined_discovery (test files: test_dhcp_detector.py, test_dhcp_lease_scanner.py, test_diagnostic_card.py, test_digest_builder.py, test_hw_detect.py, test_lab_scenarios.py, test_network_diagnostics.py, test_private_endpoint_checker.py, test_speed_tester.py, test_combined_discovery.py). 2525 tests pass, 5 skipped.

**Sprint 13 delivered (2026-05-31):** 13 new extraction files — `discover_data.py` (1,142 lines), `help_content.py`, `home_suggestions.py`, `notif_extra_channels.py`, `settings_appearance.py`, `scan_enrichment.py`, `tabs_analysis.py`, `tabs_diag_extra.py`, `device_detail_pane.py`, `device_detail_panels.py`, `kpi_bar.py`, `modem_signal_panel.py`, `overview_tile_monitor.py`; discover_page.py 1,360→229 lines. 2553 tests pass, 5 skipped.

**Sprint 14 delivered (2026-05-31):** S10-4 ✅ hex-colour AST gate added to `test_codeql_prevention.py` (`test_no_hardcoded_hex_in_ui_files`); S9-4 ✅ `test_module_coverage_gate.py` created — all 70 modules now covered; RULE-T1 ✅ `test_port_scanner.py` (15 tests) + `test_report_pdf.py` (6 tests) added; RULE-B1 ✅ all 13 Sprint 13 new modules registered in `NetSentinel.spec` hiddenimports; LOC gate ✅ all 12 untracked Sprint 13 files added to `KNOWN_LARGE_UI_FILES`; dashboard.py budget tightened from 6,740 to 6,672. 2577 tests pass, 5 skipped.

**Sprint 15 delivered (2026-05-31):** S3-4 ✅ KNOWN_LARGE_MODULES audit — all module budgets valid, no exemptions to remove; `tabs_diag.py` split ✅ logger tab + retention helpers extracted to `ui/tabs_logger.py` (772 lines); `tabs_diag.py` 1,182→448 lines; LOC budgets updated; `home_page.py` reduction ✅ 2,238→1,128 lines — `_MiniCard` + `_AlertRow` → `home_widgets.py`; all data handlers → `ui/pages/home_data_mixin.py` (_HomeDataMixin, 907 lines); `_HomeSuggestionsMixin` wired; spec + architecture docs updated. 2581 tests pass, 5 skipped.

**Sprint 16 delivered (2026-06-01):** `_DiagExtraTabsMixin` inheritance wired ✅ — `tabs_diag_extra.py` logger dead-code removed (749→346 lines); `_DiagTabsMixin` now inherits `(_DiagExtraTabsMixin, _LoggerTabMixin)`; duplicate MTR/tools/alert-routing methods removed from `tabs_diag.py` (448→133 lines); LOC budgets tightened (tabs_diag→333, tabs_diag_extra→546, tabs_logger→972). Sprint 15 new-file budgets confirmed correct at actual+200. 2581 tests pass, 5 skipped.

**Sprint 17 delivered (2026-06-01):** `notif_channel_panels.py` ✅ — duplicate pushover/ntfy/telegram/escalation/digest builders removed (were shadowing `notif_extra_channels.py`); `_NotifAlertHistoryMixin` extracted to new `notif_alert_history.py` (761 lines); `_NotifExtraChannelsMixin` wired into `NotificationsPage`; `notif_channel_panels.py` 1,646→614 lines. `home_widgets.py` ✅ — session/onboarding widgets (FreshnessStrip, GettingStartedCard, _GradeBreakdownDialog, StandardWelcomePage, ProWelcomePage) extracted to `home_session_widgets.py` (813 lines); `home_widgets.py` 1,316→524 lines. `help.py` ✅ — `build_help_tab()` + helpers extracted to `help_tab.py` (657 lines); `help.py` 1,132→484 lines. LOC budgets tightened; all 3 new files registered in spec + architecture docs. 2587 tests pass, 5 skipped.

**Sprint 18 queue:** Further dashboard.py reduction toward 3,000 line target (currently 6,472); review `help_tab.py` (657 lines), `notif_alert_history.py` (761 lines), `home_session_widgets.py` (813 lines) — all acceptable for now; address any new findings from runtime audit.
