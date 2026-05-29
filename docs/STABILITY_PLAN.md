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
| 1 | ✅ S0-1: Identify Qt-crash culprit | 1 | v1.9.56 | Root cause: QFileSystemWatcher OS threads in test_hardware_integration.py; fixed with MagicMock patch + explicit cleanup |
| 2 | ✅ S0-2: Session-scoped QApplication fixture | 1 | v1.9.56 | Was already in conftest.py; removed module-level QApplication from 7 test files (RULE-WIN3) |
| 3 | ✅ S0-3: QSettings isolation fixture | 1 | v1.9.56 | `isolated_settings` autouse fixture added to conftest.py |
| 4 | ✅ S0-4: Full suite green gate | 1 | v1.9.56 | 2136 passed, 4 skipped, exit 0 — no crash |
| 5 | ✅ S4-1: `test_codeql_prevention.py` | 1 | v1.9.56 | bare-except + URL-substring AST checks |
| 6 | ✅ S8-1: Mark robustness plan complete | 1 | v1.9.56 | PLUGIN_ROBUSTNESS_PLAN.md already in docs/completed/ |
| 7 | S1-1: Extract `ui/nav/` package | 2 | v1.9.57 | Biggest risk/reward |
| 8 | S1-2: Extract scan-result wiring | 2 | v1.9.57 | |
| 9 | S1-3: Extract help panel | 2 | v1.9.57 | |
| 10 | S1-4: Add dashboard LOC budget test | 2 | v1.9.57 | |
| 11 | S3-1: Extract HubCard to widget | 3 | v1.9.58 | Largest page file |
| 12 | S3-2: Extract OverviewTile | 3 | v1.9.58 | |
| 13 | S3-3: Extract home-page section widgets | 3 | v1.9.58 | |
| 14 | S2-1: Split metric_store | 4 | v1.9.59 | Schema migration is highest risk |
| 15 | S2-2: Split report_exporter | 4 | v1.9.59 | |
| 16 | S2-3: Split utils | 4 | v1.9.59 | |
| 17 | S2-4: Tests for new module files | 4 | v1.9.59 | |
| 18 | S5-1: Worker coverage audit | 5 | v1.9.60 | Enumerate gaps |
| 19 | S5-2: `test_worker_lifecycle_full.py` | 5 | v1.9.60 | |
| 20 | S5-3: `_running` flag audit | 5 | v1.9.60 | |
| 21 | S6-1: WAL growth guard | 5 | v1.9.60 | |
| 22 | S6-2: VACUUM on migration | 5 | v1.9.60 | |
| 23 | S6-3: Connection busy timeout | 5 | v1.9.60 | |
| 24 | S6-4: `test_metric_store_concurrency.py` | 5 | v1.9.60 | |
| 25 | S7-1: Lazy-import audit | 6 | v1.9.60 | |
| 26 | S7-2: Startup profiling script | 6 | v1.9.60 | |
| 27 | S7-3: Debug log rotation | 6 | v1.9.60 | |
| 28 | S4-2: Pre-commit check update in CLAUDE.md | 6 | v1.9.60 | |
| 29 | S8-2: Architecture docs update | 6 | v1.9.60 | |
| 30 | S8-3: Version history update | 6 | v1.9.60 | |
| — | **— APM audit findings (2026-05-29) — order TBD —** | — | — | Added at plan end; re-slot into sprints as capacity allows |
| 31 | S12-1: Add `modules.nspkg` + `modules.plugin_tools` to spec hiddenimports | TBD | TBD | 2-line fix; do immediately before next release build |
| 32 | S12-2: Deduplicate 4 duplicate spec entries | TBD | TBD | Companion to S12-1 |
| 33 | S12-3: `test_spec_hiddenimports.py` CI gate | TBD | TBD | Prevents future regressions |
| 34 | S11-2: Fix 4 stale `_FEATURES` page refs in `discover_page.py` | TBD | TBD | Quick: 4 string corrections |
| 35 | S11-3: Add 25 missing `_FEATURES` entries | TBD | TBD | Unlocks Feature Guide for half the app |
| 36 | S11-1: Add `_PAGE_HELP` entries for all 61 nav labels | TBD | TBD | Unblocks help-button UX for every page |
| 37 | S11-4: CI gate — nav/help/features parity check | TBD | TBD | Extend `test_nav_completeness.py` |
| 38 | S10-1: Inventory missing colour tokens; add to `ui/styles.py` | TBD | TBD | Must precede S10-2/S10-3 |
| 39 | S10-2: Purge hardcoded hex from `ui/pages/*.py` (37 files) | TBD | TBD | Run debug_launch.py after each file |
| 40 | S10-3: Purge hardcoded hex from `ui/widgets/*.py` + root `ui/` (7 files) | TBD | TBD | Companion to S10-2 |
| 41 | S10-4: Add hex-colour AST gate to `test_codeql_prevention.py` | TBD | TBD | Enable only after S10-2+S10-3 complete |
| 42 | S9-1: Tests for Tier 1 modules — utility/plumbing (8 modules) | TBD | TBD | No network mocks needed |
| 43 | S9-2: Tests for Tier 2 modules — scan/detection (18 modules) | TBD | TBD | Use `@pytest.mark.live` for real-network tests |
| 44 | S9-3: Tests for Tier 3 modules — report/enrichment (10 modules) | TBD | TBD | Mock MetricStore where needed |
| 45 | S9-4: `test_module_coverage_gate.py` — CI gate for module test completeness | TBD | TBD | Enable only after S9-1–S9-3 complete |

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
*Sprint 1 complete: v1.9.56 (2026-05-29).  Sprint 2 target: v1.9.57.  Full plan target: v1.9.61.*
*Items 31–45 added 2026-05-29 from APM rules/docs/codebase audit (197 gaps across 6 rule categories).  Version targets and sprint assignments TBD — re-slot as capacity allows.*
