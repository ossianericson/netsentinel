---
applyTo: "**"
---

# NetSentinel — Architecture & Codebase Reference

## Technology Stack

| Layer | Technology |
|---|---|
| GUI framework | PyQt6 (Python) |
| Charts / graphs | matplotlib (QtAgg backend embedded in QWidget) |
| Network scanning | scapy, nmap, python-nmap |
| Packaging | PyInstaller (produces single-exe builds) |
| Distribution | Inno Setup installer + WinGet (Ookla.Speedtest.CLI as PackageDependency) |
| Config persistence | QSettings / INI file (NetSentinel.ini) |
| Data persistence | SQLite via MetricStore (WAL mode, schema v8) |
| Secrets | OS keychain via `keyring` (RULE 22-A) |
| Logging | Python `logging` module + custom CSV logger |

## Repository Layout

```
netsentinel/
├── app.py                  # Entry point — creates QApplication, launches Dashboard
├── cli.py                  # Headless CLI interface
├── svc.py                  # Windows service wrapper
├── requirements.txt
├── apm.yml                 # APM manifest
├── installer.iss           # Inno Setup — includes optional Ookla CLI winget task
├── .github/
│   ├── winget/             # WinGet manifests (Ookla.Speedtest.CLI PackageDependency)
│   └── workflows/
│       └── release.yml     # CI: build → release → winget submit (RULE 20)
├── modules/                # All backend logic (no PyQt imports)
│   ├── alert_engine.py
│   ├── availability_monitor.py
│   ├── bandwidth_monitor.py
│   ├── cert_monitor.py
│   ├── combined_discovery.py   # Main scan orchestrator
│   ├── config_baseline.py
│   ├── cve_lookup.py
│   ├── device_classifier.py    # OUI → device type + risk score
│   ├── device_tracker.py
│   ├── dhcp_detector.py
│   ├── dhcp_lease_scanner.py
│   ├── dns_correlator.py       # Ping/DNS latency + outage detection
│   ├── ha_detector.py
│   ├── internet_exposure.py
│   ├── iot_baseline.py
│   ├── mac_registry.py         # OUI database (offenders.json)
│   ├── metric_store.py         # SQLite time-series DB (singleton)
│   ├── network_benchmark.py
│   ├── network_logger.py       # Background ping logger (CSV → ~/Documents/NetSentinel/logs)
│   ├── notification_router.py
│   ├── os_fingerprint.py
│   ├── port_scanner.py
│   ├── rest_api.py             # Read-only Flask API (127.0.0.1, API key in keychain)
│   ├── risk_scorer.py
│   ├── rogue_device.py
│   ├── root_cause_correlator.py    # Prioritised plain-English findings from scan data
│   ├── diagnostic_card.py          # Shareable PNG/HTML card (grade, ISP, top 3 findings)
│   ├── lab_scenarios.py            # Lab exercise definitions and result dataclasses
│   ├── protocol_animator.py        # AnimNode/AnimStep scene builders for protocol viz
│   ├── report_exporter.py          # generate_card_html(), generate_lab_html(), save_*()
│   ├── web_dashboard.py            # build_html() — self-contained /dashboard HTML page
│   ├── scheduler.py
│   ├── snmp_poller.py
│   ├── snmp_trap_receiver.py
│   ├── speed_tester.py         # 3-tier: Ookla CLI → speedtest-cli → pure-Python
│   ├── storm_analyser.py
│   ├── stp_detector.py
│   ├── syn_scanner.py
│   ├── threat_intel.py
│   ├── tls_checker.py
│   ├── trend_analyser.py
│   └── utils.py                # get_app_data_dir(), is_admin(), ping_sweep, etc.
├── ui/
│   ├── styles.py               # SINGLE SOURCE OF TRUTH for all colours and QSS
│   ├── dashboard.py            # Main window + activity-rail nav (_nav_add_rail_item pattern)
│   ├── live_graph.py           # Matplotlib RTT line chart
│   ├── topology_widget.py      # Matplotlib network topology map
│   ├── system_tray.py
│   └── pages/
│       ├── baseline_page.py
│       ├── cert_page.py
│       ├── connections_page.py
│       ├── cve_page.py
│       ├── dhcp_lease_page.py
│       ├── diagnosis_page.py       # "What's Wrong?" DiagnosisPage — symptom tiles → scan → findings
│       ├── dns_zone_page.py
│       ├── geo_map_page.py         # Offline MaxMind geolocation map
│       ├── history_page.py
│       ├── home_automation_page.py
│       ├── home_page.py            # Landing page — hero, suggestions, tips, dashboard strip
│       ├── inventory_page.py
│       ├── ip_calc_page.py
│       ├── lab_mode_page.py        # LabModePage — four guided exercises
│       ├── live_bandwidth_page.py
│       ├── maintenance_page.py
│       ├── notifications_page.py
│       ├── ookla_cli_banner.py     # Dismissible install banner for Ookla CLI
│       ├── overview_page.py
│       ├── protocol_viz_page.py    # Interactive ARP/DNS/TCP/DHCP/STP animation
│       ├── reports_page.py
│       ├── service_page.py
│       ├── settings_page.py
│       ├── snmp_trap_page.py
│       ├── speed_test_page.py
│       ├── syslog_page.py
│       ├── threat_intel_page.py
│       ├── trend_page.py
│       ├── uptime_page.py
│       └── wifi_heatmap_page.py    # Floor plan import + IDW interpolation + PNG export
├── workers/                    # QThread wrappers (signals only, no logic)
│   ├── availability_worker.py
│   ├── cert_worker.py
│   ├── dhcp_lease_worker.py
│   ├── dns_zone_worker.py
│   ├── ha_worker.py
│   ├── iface_bw_worker.py
│   ├── report_scheduler_worker.py
│   ├── rest_api_worker.py
│   ├── scan_worker.py
│   ├── service_worker.py
│   ├── snmp_trap_worker.py
│   ├── speed_test_worker.py    # FetchServersWorker + SpeedTestWorker
│   ├── syslog_worker.py
│   └── threat_intel_worker.py
└── tests/
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
Rail section buttons use **Lucide SVG icons** (MIT) defined in the `_LUCIDE` dict in `dashboard.py`. Available names: `home activity grid monitor shield bar-chart book-open settings search wifi network zap server map-pin terminal layers globe log alert-triangle eye pin x chevron-right scan lock tool bell cpu`.

Add new icons to `_LUCIDE` before using them in `_nav_begin_section()`. Do not use Unicode symbols or photo-emoji as rail section icons.

### Scan workers
All network operations run in `workers/` (QThread subclasses). Emit `result_ready` and `error` signals. **Never** do blocking I/O on the main thread.

### Risk levels (canonical)
`HIGH` > `STORM` > `MEDIUM` > `WARNING` > `LOW` > `CLEAN` > `UNKNOWN`
Colours in `RISK_COLORS` and `RISK_BG` in `ui/styles.py`.

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

`Ookla.Speedtest.CLI` is declared as a `PackageDependency` in the installer manifest.
WinGet installs it automatically alongside NetSentinel.
The Inno Setup installer has an optional task that runs `winget install Ookla.Speedtest.CLI --silent`.
`OoklaCliBanner` in `ui/pages/ookla_cli_banner.py` handles in-app one-click install for portable users.

**Never bundle `speedtest.exe` inside the installer** — it has a proprietary Ookla EULA.
