---
applyTo: "**"
description: "NetSentinel architecture reference — tech stack, repository layout, key patterns, and data contracts."
---

# NetSentinel — Architecture & Codebase Reference

## Technology Stack

| Layer | Technology |
|---|---|
| GUI framework | PyQt6 (Python) |
| Charts / graphs | matplotlib (QtAgg backend embedded in QWidget) |
| Network scanning | scapy, nmap, python-nmap |
| Packaging | PyInstaller (produces single-exe builds) |
| Distribution | Inno Setup installer + WinGet (Ookla.Speedtest.CLI as ExternalDependencies) |
| Config persistence | QSettings / INI file (NetSentinel.ini) |
| Data persistence | SQLite via MetricStore (WAL mode, schema v8) |
| Secrets | OS keychain via `keyring` (RULE 22-A) |
| Logging | Python `logging` module + custom CSV logger |

## Repository Layout

> **This map is directory-level by design.** Per-file purpose lives in each file's
> own module docstring — the place that cannot drift from the code. `apm` and the
> coverage test (`tests/test_apm_rules_coverage.py`) enforce only that every tracked
> package below stays listed. To find the file that does X: `grep` the relevant
> directory, or read the package's `__init__`/docstrings.

```
netsentinel/
├── app.py                  # Entry point — creates QApplication, injects MetricStore, launches Dashboard
├── cli.py                  # Headless CLI interface
├── svc.py                  # Windows service wrapper
├── bump_version.py         # Version bump across all tracked files (RULE-R1); triggers apm install + compile
├── apm.yml                 # APM manifest (targets only — rules live in .apm/instructions/)
├── installer.iss           # Inno Setup — optional Ookla CLI winget task
├── .github/                # winget manifests + workflows/release.yml (CI: build → release → winget)
│
├── modules/                # Backend logic — pure Python, NO PyQt imports, NO direct DB writes (~125 files)
│   #  Each file is a self-contained scanner/monitor/helper named for its job.
│   #  Notable anchors (split families & single-purpose hubs):
│   ├── metric_store*.py        # SQLite time-series DB singleton + schema/query mixins (the DATA layer)
│   ├── combined_discovery.py   # Main scan orchestrator
│   ├── speed_tester*.py        # 3-tier backend cascade (Ookla CLI → speedtest-cli → pure-Python)
│   ├── alert_*.py / notification_*.py  # Alert engine, baselines, suppression, channels, router
│   ├── device_*.py / *_scanner.py / *_monitor.py  # Detection & classification families
│   ├── topology_*.py / report_*.py / service_*.py  # Map, export, and service-diagnostics families
│   ├── colours.py              # Chart/report colour constants (RULE-AH3 module source)
│   └── utils.py / utils_net.py / utils_platform.py  # Core helpers incl. get_app_data_dir() (RULE 23)
│
├── ui/                     # PyQt6 UI — reads MetricStore for display, never writes it (the UI layer)
│   ├── styles.py               # SINGLE SOURCE OF TRUTH for all colours and QSS (RULE 1 / RULE-AH3)
│   ├── dashboard.py            # Main window shell (~1,754 lines) — inherits the mixins below
│   ├── scan_wiring.py / scan_enrichment.py / header.py / monitor_state.py / plugin_page_mixin.py / export_mixin.py  # Dashboard mixins
│   ├── tabs*.py                # TabBuilderMixin + _*TabsMixin sub-mixins (page factory / sidebar assembly)
│   ├── nav/                    # Activity-rail nav package — rail.py (widgets) + builder.py (_NavBuilderMixin, scan registry)
│   ├── pages/                  # One widget per nav page (Devices, Speed Test, Security Overview, …)
│   └── widgets/                # Reusable widgets, tiles, cards, dialogs, overlays
│
├── workers/                # QThread wrappers — emit result_ready/error, NO blocking I/O on main thread (RULE 4)
│
├── tests/                  # pytest suite (structure-enforcement tests live here too)
└── tools/
    ├── debug_launch.py         # GUI smoke-launch → netsentinel_debug.log (COMMIT GATE Step 3)
    ├── monkey_test.py          # Chaos/monkey tester (pywinauto UIA; --source/--connect/exe modes)
    └── audit_check.py          # Runtime audit of scan-registry / Scan Center wiring
```

## Key Architectural Patterns

### Three-layer separation (ARCH RULE 1)

```
UI LAYER       ui/dashboard.py (shell/router), ui/pages/*.py (page widgets)
               • Reads from MetricStore for display
               • NEVER writes to MetricStore directly
               • NEVER imports from modules/alert_engine.py

DATA LAYER     modules/metric_store.py  ←→  NetSentinel.db (AppData)
               • Single source of truth for all persisted metrics

MODULE LAYER   modules/*.py
               • Pure business logic — NO PyQt imports, NO direct DB writes
```

`modules/utils.py` is the canonical entry point for vendor lookup, hostname resolution, and
device classification — it re-exports `lookup_vendor` (from `mac_lookup`), `resolve`/
`resolve_batch`/`rdns` (from `name_resolver`), and `classify`/`classify_device`/
`classify_with_evidence`/`classify_registry_first` (from `device_classifier`). Prefer importing
these from `modules.utils` in new code; the underlying modules remain valid for existing callers.

### File write locations (ARCH RULE 23)
All file writes must use `get_app_data_dir()` from `modules/utils.py`:
- Windows: `%LOCALAPPDATA%\NetSentinel\`
- macOS: `~/Library/Application Support/NetSentinel/`
- Linux: `$XDG_CONFIG_HOME/NetSentinel/`

The exe directory is **read-only** when installed via WinGet or Inno Setup into `Program Files`.
The only exception is `network_logger.py` which writes CSVs to `~/Documents/NetSentinel/logs/` by design (user-accessible log files).

### MetricStore singleton (ARCH RULE 2)
`MetricStore` is instantiated **once** in `app.py` or `svc.py` and injected as a dependency.
Never construct it inside a page widget or module.

**Raw SQL stays inside the MetricStore family.** `_execute_write()`/`_execute_read()` are
private primitives — every other module or `ui/` file must call a public MetricStore method
instead (add one in `metric_store.py` or `metric_store_writes_device.py` if missing). Enforced
by `tests/test_metric_store_encapsulation.py`.

**Single-writer rule for scan-driven `known_device` updates:** `DeviceTracker.process_scan()`
(`modules/device_tracker.py`) is the only caller of `MetricStore.record_ip_observation()` for
scan results — do not call it a second time for the same scan (a prior bug in
`ui/scan_wiring.py` did this and double-incremented `device_ip_history.seen_count`, skewing
`ip_stability`). `known_device.scan_count`/`ip_stability`/`inferred_role` are likewise derived
only inside `process_scan()`. Full invariant documented in the `metric_store.py` module
docstring.

### Speed tester cascade (ARCH RULE 24)
`modules/speed_tester.py` tries backends in order:
1. **Ookla CLI binary** — `_find_ookla_cli()` searches 7 locations including WinGet Links dir
2. **speedtest-cli library** — 8 download / 4 upload threads; SSL-patched for Python 3.12
3. **Pure-Python HTTP** — 16 download / 8 upload `ThreadPoolExecutor` TCP streams

Frontend (`SpeedTestResult` dataclass) is identical regardless of backend.

### Dashboard navigation model
Main window: permanent 48 px activity rail (`_nav_rail`) + 280 px animated flyout (`_FlyoutPanel`) + `QStackedWidget` (`_stack`).

- **Sections** declared with `_nav_begin_section(name, lucide_icon_name)` inside `_build_pro_nav()`
- **Pages** registered with `_nav_add_rail_item(label, widget, admin_required, audit_item)`
- `_nav_finalize_rail()` builds `_RailButton` widgets from `_nav_sections` and inserts them into the rail layout
- `_nav_rail_toggle(section_name)` opens/closes the flyout for a section; persists last-open section to `QSettings("nav/last_section")`
- `_nav_rail_go_to(label)` switches the stack and updates the breadcrumb strip
- If `_nav_pinned_labels` is non-empty, a "Pinned" section is injected at index 0 of `_nav_sections` before `_nav_finalize_rail()`
- Ctrl+F focuses the sidebar search box; Ctrl+K opens the command palette; Esc closes the flyout

### Rail icon standard
Rail section buttons use **Lucide SVG icons** (MIT) defined in the `_LUCIDE` dict in `dashboard.py`. Available names: `home activity grid monitor shield bar-chart book-open settings search wifi network zap server map-pin terminal layers globe log alert-triangle eye pin x chevron-right scan lock tool bell cpu plug`.

Add new icons to `_LUCIDE` before using them in `_nav_begin_section()`. Do not use Unicode symbols or photo-emoji as rail section icons.

**Nav section placement guide** (use the correct section when adding new pages):
- Getting Started — daily-use core tools (Overview, Speed Test, DNS, Home, What's Wrong?)
- Discover — network inventory and topology (Devices, Network Map, WiFi, DHCP, DNS Zone Map, Home Automation)
- Monitor — live data and history streams (Active Monitors, Network Logger, Network Timeline, Live Bandwidth, App Traffic, Active Connections, Availability History, Inventory Changes, Bandwidth Usage, Service Heartbeat, IPv6 Devices, Uptime & SLA, Syslog Viewer, SNMP Trap Receiver)
- Reports — grading, ISP reports, docs, notifications (Network Grade, Health Report, Network Doc, IP Calculator, Notifications)
- Analysis — deep packet / protocol tools, advanced diagnostics (Broadcast Storm, Rogue Bridge (STP), IoT Behaviour, 802.11 Monitor, ARP Spoof Watch, Hop-by-Hop Trace, SNMP Device Info, Tools & Wake-on-LAN, Geolocation Map, Trend Forecasts, Service Diagnostics, Root Cause Correlator)
- Automation — scheduled scans, hooks, MQTT, REST API, integrations (Automation Hooks, Scheduled Scans, Custom Triggers, MQTT, REST API, Config Snapshots, Maintenance Windows)
- Security Audit — RED-labelled; elevated-privilege scan tools (Security Overview, Port Scan, CVE, Threat Intel, TLS, Login Test, OS Detection, Risk Score, Exposure, Discovery, SMB, Plugins, Private Endpoint, Cloud Metadata, DHCP Rogue)
- Education — learning tools (Protocol Visualizer, Lab Mode, Feature Guide, Help)
- Extend — hardware integrations and physical device management (Hardware)

### Scan Registry / Audit Status system
`_NavBuilderMixin` (in `ui/nav/builder.py`) maintains a per-page scan state registry that drives flyout dot badges, rail button badges, tooltips, and the Security Overview Scan Status card.

**API:**
```python
self._nav_set_scan_state(
    label: str,      # exact nav page label, e.g. "Port Scan (TCP)"
    state: str,      # "never" | "running" | "fresh" | "stale" | "error"
    ts: float = None,    # epoch seconds of last completion (None → now)
    verdict: str = None, # one-line result summary for tooltip / Scan Status card
    error: str = None,   # error message when state == "error"
)
```

**State → flyout dot colour:**
- `"fresh"` → `GREEN`
- `"stale"` → `AMBER`
- `"running"` → `ACCENT`
- `"error"` → `RED`
- `"never"` → `""` (dot hidden)

**Freshness thresholds** (`_FRESH_SECONDS` class dict on `_NavBuilderMixin`):
Port scans default to 2 h; CVE/TLS to 24 h; unknown labels use `_DEFAULT_FRESH_SECONDS = 3600` (1 h).
`_check_and_stale_registry()` runs every 5 minutes and promotes `"fresh"` → `"stale"` when the threshold is exceeded.

**QSettings persistence** — key `scan_registry/state` (JSON). Restored on startup via `_restore_scan_registry()`; any entry stored as `"running"` is reset to `"never"` on restore (mid-scan interrupted by exit).

**`_AUDIT_SCAN_LABELS`** (in `security_overview_page.py`) — 9-item tuple of all nav page labels shown in the Scan Status card rows: `"Port Scan (TCP)"`, `"Port Scan (UDP)"`, `"CVE Lookup"`, `"Threat Intel"`, `"TLS & Exposure"`, `"Login Test"`, `"OS Detection"`, `"Exposed to Internet"`, `"Full Device Discovery"`. These must exactly match the strings passed to `_nav_set_scan_state()` in `ScanResultMixin`.

**Security Scan panel** — `_SecurityScanPanel._TOOLS` (in `ui/widgets/overview_tile.py`) is a
6-item checkbox list on the Overview page ("Threat Intel", "TLS & Exposure", "Device Risk
Score", "CVE Lookup", "Port Scan (TCP)", "Exposed to Internet") that the user checks/unchecks
before clicking "Run". Selected labels emit via `run_clicked` → `overview_page.py`'s
`security_scan_requested` signal (wired in `ui/tabs.py`) → `dashboard.py._run_security_scans()`.

**Security Audit Coordinator** — `dashboard.py._advance_security_audit()` pops labels one at a
time from `_pending_security_tools` and dispatches by comparing against `NavLabel` enum members
(`L.PORT_SCAN_TCP`, `L.EXPOSED_TO_INTERNET`) — only those two currently have working dispatch
code; any other label falls through the "unrecognised label — skip silently" branch.
`_security_audit_total` tracks progress for the Security Overview progress bar.

### Scan workers
All network operations run in `workers/` (QThread subclasses). Emit `result_ready` and `error` signals. **Never** do blocking I/O on the main thread.

### Risk levels — two separate systems

**Internal scan risk scoring** (used in scan results, `RISK_COLORS`/`RISK_BG` in `ui/styles.py`):
`HIGH` > `STORM` > `MEDIUM` > `WARNING` > `LOW` > `CLEAN` > `UNKNOWN`

**UI severity labels** (used in alert displays, CVE pages, RULE-A3):
`Critical` > `High` > `Warning` > `Info`

These are distinct systems that coexist. Do not mix them — never display internal risk level strings like "STORM" or "CLEAN" to users as severity labels, and do not use UI severity labels (e.g. "Critical") as internal risk level values in RISK_COLORS lookups.

## Colour Palette (ui/styles.py constants)

```python
NAV_BAR     = "#141B2D"   # top application bar
SIDEBAR_BG  = "#1F2B3E"   # left sidebar
BG_DARK     = "#F4F4F4"   # main content area
BG_CARD     = "#FFFFFF"   # card backgrounds
BG_HOVER    = "#EEF4FF"   # table row hover
BG_ALT_ROW  = "#F7F9FC"   # zebra alternate row
ACCENT      = "#0078D4"   # primary brand blue
TH_BG       = "#1A3A5C"   # table header navy
TH_TEXT     = "#FFFFFF"
TEXT_PRIMARY   = "#1A1A2E"
TEXT_SECONDARY = "#5A6A7A"
BORDER      = "#D4D4D4"
RED    = "#D93025"
AMBER  = "#F59E0B"
GREEN  = "#2E7D32"
```

## WinGet Distribution

`Ookla.Speedtest.CLI` is declared as `ExternalDependencies` (NOT `PackageDependencies`) in all winget manifests.
See RULE-R3: using `PackageDependencies` blocks the install when the package is not in the official winget index.
The Inno Setup installer has an optional task that runs `winget install Ookla.Speedtest.CLI --silent`.
`OoklaCliBanner` in `ui/pages/ookla_cli_banner.py` handles in-app one-click install for portable users.

**Never bundle `speedtest.exe` inside the installer** — it has a proprietary Ookla EULA.
