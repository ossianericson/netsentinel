# Architecture

NetSentinel follows a strict three-layer separation. Network logic is testable without a display. The UI never writes to the database directly.

```
UI LAYER       ui/dashboard.py (shell/router), ui/pages/*.py (page widgets)
               Reads from MetricStore for display. Never writes directly.
               Never imports from modules/alert_engine.py.

DATA LAYER     modules/metric_store.py  ←→  NetSentinel.db (AppData)
               Single source of truth for all persisted metrics.
               WAL mode; safe for concurrent reads from background workers.

MODULE LAYER   modules/*.py
               Pure business logic — no PyQt imports, no direct DB writes.
               Every module is importable and testable with no display.
```

---

## Key design decisions

### Why QThread workers instead of asyncio

PyQt6's event loop owns the main thread. Python's `asyncio` event loop does not integrate cleanly with Qt — you would need `qasync` or similar glue and lose access to Qt signals/slots across thread boundaries. Every background operation uses a `QThread` subclass in `workers/` that emits `result_ready` and `error` signals. The UI thread connects slots to those signals. No shared mutable state, no locks.

### Why SQLite WAL mode

Multiple background worker threads read from `MetricStore` concurrently while the UI thread also reads for display. WAL (Write-Ahead Logging) allows concurrent readers during a write, unlike journal mode which blocks all readers. The singleton pattern in `MetricStore` ensures a single connection object; WAL handles the rest.

### Why OS keychain for secrets

`QSettings` is plaintext in the Windows Registry or an INI file. A `NetSentinel.ini` in AppData is readable by any process running as the same user. `keyring` delegates to the Windows Credential Manager, macOS Keychain, or libsecret on Linux — all of which enforce OS-level access control. SMTP credentials, SNMP community strings, API keys, and plugin credentials all go through `keyring`.

### Why the three-tier speed test cascade

Ookla CLI produces the most accurate results (server-side precision, 1 Gbps+ support) but cannot be bundled due to EULA. `speedtest-cli` is Python-native with 8 download / 4 upload threads and no EULA restriction. The pure-Python fallback uses 16 `ThreadPoolExecutor` TCP streams and works with zero additional dependencies — so the speed test always runs regardless of what is installed. The `SpeedTestResult` datatype is identical across all three; the frontend never knows which backend ran.

### Why a module LOC budget

Large files are a maintenance hazard: they attract more code, become harder to test in isolation, and cause merge conflicts. Every file in `modules/` is capped at 600 lines. The budget is enforced by `tests/test_module_loc.py`, which fails CI if any module exceeds it. 19 modules were split during development when they hit the limit. The test also documents which files have known higher budgets and why.

### Why the dashboard was decomposed

`ui/dashboard.py` began as a 13,483-line monolith. Decomposition over four sprints produced six inherited mixins and nine page-factory mixins:

| Mixin | File | Responsibility |
|---|---|---|
| `ScanResultMixin` | `ui/scan_wiring.py` | Scan result handlers; persistent device map merge |
| `AppHeaderMixin` | `ui/header.py` | Header construction; frameless-window behaviour |
| `TabBuilderMixin` | `ui/tabs.py` | Page factory; sidebar assembly (inherits all `_*TabsMixin`) |
| `_NavBuilderMixin` | `ui/nav/builder.py` | Rail/flyout build; runtime palette; pin methods |
| `_MonitorStateMixin` | `ui/monitor_state.py` | Verdict/badge/pill display; KPI tiles |
| `_PluginPageMixin` | `ui/plugin_page_mixin.py` | Plugin page lifecycle; HW auto-detect |

`dashboard.py` now stands at 1,967 lines. Each mixin has a single responsibility and its own test file.

---

## Module inventory

Key modules and their roles:

| Module | Role |
|---|---|
| `modules/combined_discovery.py` | Main scan orchestrator — coordinates ARP, ICMP, SYN, mDNS sweeps |
| `modules/metric_store.py` | SQLite time-series DB (singleton, WAL mode, schema v17) |
| `modules/metric_store_schema.py` | DDL, schema version, column migrations, dataclasses |
| `modules/metric_store_queries.py` | cert/service/device/HA/snapshot/grade query methods |
| `modules/metric_store_queries_uptime.py` | uptime/device-state query methods |
| `modules/metric_store_queries_metrics.py` | RTT/speed/CVE/alert/modem/mesh query methods |
| `modules/alert_engine.py` | Alert evaluation — fires rules, routes to NotificationRouter |
| `modules/alert_suppressor.py` | EscalationPolicy + default suppression rules |
| `modules/notification_router.py` | Routes alerts to configured channels |
| `modules/notification_channels.py` | Per-channel delivery (email, webhook, toast, Pushover, Ntfy, Telegram) |
| `modules/speed_tester.py` | 3-tier cascade public API |
| `modules/speed_tester_backends.py` | Ookla CLI + speedtest-cli + pure-Python backends |
| `modules/speed_tester_servers.py` | Server discovery via GeoLite2 + parallel ping |
| `modules/device_classifier.py` | OUI → device type + risk score |
| `modules/device_stability.py` | IP stability scoring + role inference (persistent device map) |
| `modules/network_segments.py` | Auto-detect /24 subnet groups; user-editable segment names |
| `modules/root_cause_correlator.py` | Prioritised plain-English findings from scan data |
| `modules/service_diagnostics.py` | DiagnosticEngine — DNS/TCP/HTTPS/ICMP/traceroute probes |
| `modules/service_diagnostics_probes.py` | Low-level probe implementations |
| `modules/service_mapper.py` | Maps device_type/vendor → expected services |
| `modules/topology_cytoscape.py` | Cytoscape.js element builder + stylesheet (pure Python) |
| `modules/topology_cytoscape_html.py` | HTML/JS page template for the Cytoscape map |
| `modules/topology_snapshot.py` | TopologySnapshot + TopologyDiff — change detection |
| `modules/health_score.py` | HealthScoreCalculator — ambient score from always-on monitor data |
| `modules/plugin_system.py` | Plugin loader + sandbox execution engine |
| `modules/plugin_registry.py` | Plugin discovery, metadata, enable/disable state |
| `modules/plugin_tools.py` | Validator CLI + signature check |
| `modules/app_traffic_classifier.py` | Port→category heuristics; per-host protocol breakdown |
| `modules/cdn_ranges.py` | Static CDN/streaming-provider IP range classifier |
| `modules/traffic_insights.py` | Usage narrative builders; plan utilization; QoS recommendation |
| `modules/utils.py` | `get_app_data_dir()`, `is_admin()`, ping sweep, Wake-on-LAN |
| `modules/utils_net.py` | `get_network_info()`, `get_dhcp_info()`, `get_interface_details()` |
| `modules/colours.py` | Colour constants for charts and HTML reports |

---

## Workers

All network I/O runs in `workers/` (`QThread` subclasses). They emit `result_ready` and `error` signals back to the UI thread. Blocking I/O on the main thread is forbidden — `RULE-WIN1` prevents `subprocess.PIPE` on startup paths where it causes `STATUS_ACCESS_VIOLATION` on Windows.

Key workers:

| Worker | Fires every | Notes |
|---|---|---|
| `scan_worker.py` | On demand | Orchestrates combined discovery |
| `health_worker.py` | 60 s | Ambient health score from always-on data |
| `availability_worker.py` | Configurable | RTT ping per tracked device |
| `app_traffic_worker.py` | 10 s | Per-host protocol sniffer |
| `bandwidth_worker.py` | Continuous | Per-MAC rx/tx capture |
| `lldp_worker.py` | 15 s | LLDP neighbor sniff |
| `speed_test_worker.py` | On demand | 3-tier cascade speed test |
| `service_diagnostics_worker.py` | On demand | DiagnosticEngine.run() |
| `passive_observer_worker.py` | Continuous | SSDP + mDNS passive listener |

---

## File write locations

All file writes go through `get_app_data_dir()` from `modules/utils.py`:

- **Windows:** `%LOCALAPPDATA%\NetSentinel\`
- **macOS:** `~/Library/Application Support/NetSentinel/`
- **Linux:** `$XDG_CONFIG_HOME/NetSentinel/` (default `~/.config/NetSentinel/`)

The installed binary lives in `C:\Program Files\NetSentinel\` — a read-only directory for standard users. Writing to the exe directory at runtime would silently fail or raise `PermissionError`. The only exception is `network_logger.py`, which writes CSVs to `~/Documents/NetSentinel/logs/` by design (user-accessible log files).

---

## Test architecture

The test suite has 5,469 tests across 411 files. Key categories:

| Category | Files | What it catches |
|---|---|---|
| Encoding hygiene | `test_source_encoding.py` | Mojibake (UTF-8 decoded as cp1252) in string literals |
| Interactive state | `test_interactive_states.py` | QPushButton with `color:` but no `:pressed` rule (white-on-white on light themes) |
| Module LOC budget | `test_module_loc.py` | Any module exceeding 600 lines |
| Duplicate methods | `test_no_duplicate_methods.py` | Same method defined twice in a class (silent Python discard) |
| Bare pass in except | `test_no_bare_pass.py` | Silent exception swallowing without an explanatory comment |
| Version consistency | `test_version_consistency.py` | Version string mismatch across all 12 tracked files |
| Signal integration | Various `test_*_wiring.py` | Signal→slot chains that cross animation delays (160ms nav crossfade) |
| UI wiring | Various | Page-to-scan result connections wired in `app.py` |
| Style token imports | `test_style_token_imports.py` | Colour tokens used in UI files without a matching import from `ui/styles.py` |
| Nav completeness | `test_nav_completeness.py` | Every registered page reachable from `_build_pro_nav()` |

Run the full suite:

```bash
python -m pytest tests/ -v --tb=short
```

All tests are offline — no real network traffic or live devices required.

---

## Adding a new scan module

1. `modules/<name>.py` — pure Python, no PyQt imports; cap at 600 lines
2. `workers/<name>_worker.py` — QThread, emits `result_ready(object)` and `error(str)`
3. `ui/pages/<name>_page.py` — receives `store: MetricStore` as constructor parameter
4. Register in `dashboard._build_pro_nav()` under the correct nav section
5. Add `tests/test_<name>.py` with at least one import test and one behavioural test
6. Add the module to `hiddenimports` in `NetSentinel.spec` (omitting it causes `ModuleNotFoundError` in the installed binary only)

The new page is automatically discovered by `tools/systematic_test.py` via `_discover_pages()` — no manual list to update.

---

## Navigation model

Main window: permanent 48 px activity rail + 280 px animated flyout + `QStackedWidget`.

- Sections declared with `_nav_begin_section(name, lucide_icon_name)` inside `_build_pro_nav()`
- Pages registered with `_nav_add_rail_item(label, widget, admin_required, audit_item)`
- `_nav_rail_go_to(label)` switches the stack and updates the breadcrumb strip
- Ctrl+K opens the command palette (fuzzy-match any page); Ctrl+F focuses sidebar search; Esc closes the flyout
- Right-click any flyout item to pin it; pinned items appear in a "Pinned" rail section at index 0

Full coding conventions and all development rules: [`.claude/rules/`](../.claude/rules/) (APM source: `.apm/instructions/`)
