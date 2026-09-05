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
| Data persistence | SQLite via MetricStore (WAL mode, schema v21) |
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
│   ├── network_environment.py  # home/vpn/corporate/large_subnet detection + scope/authorization fingerprinting (ARCH RULE 26)
│   ├── adaptive_timing.py      # Gateway-RTT-derived probe timeout profile (ARCH RULE 26)
│   ├── colours.py              # Chart/report colour constants (RULE-AH3 module source)
│   └── utils.py / utils_net.py / utils_platform.py  # Core helpers incl. get_app_data_dir() (RULE 23)
│
├── ui/                     # PyQt6 UI — reads MetricStore for display, never writes it (the UI layer)
│   ├── styles.py               # SINGLE SOURCE OF TRUTH for all colours and QSS (RULE 1 / RULE-AH3)
│   ├── dashboard.py            # Main window shell (~1,754 lines) — inherits the mixins below
│   ├── scan_wiring.py / scan_enrichment.py / header.py / monitor_state.py / plugin_page_mixin.py / export_mixin.py  # Dashboard mixins
│   ├── scan_settings.py        # Env-aware scan defaults — flush-caches, scan scope, authorization, rate caps (ARCH RULE 26)
│   ├── native_chrome.py / uia_warmup.py  # Win32 window/startup plumbing — ctypes only, zero Qt objects in the
│   │                           # native callbacks. native_chrome = the DEFAULT window on Windows since
│   │                           # v2.1.30 (WM_NCCALCSIZE; gives real Aero Snap). Non-Windows keeps the
│   │                           # frameless path in header.py. (RULE-WIN9 chrome; RULE-WIN10 UIA warmup)
│   ├── tabs*.py                # TabBuilderMixin + _*TabsMixin sub-mixins (page factory / sidebar assembly)
│   ├── nav/                    # Activity-rail nav package — rail.py (widgets) + builder.py (_NavBuilderMixin, scan registry)
│   ├── pages/                  # One widget per nav page (Devices, Speed Test, Security Overview, …)
│   └── widgets/                # Reusable widgets, tiles, cards, dialogs, overlays (incl. environment_banner.py)
│
├── workers/                # QThread wrappers — emit result_ready/error, NO blocking I/O on main thread (RULE 4)
│
├── tests/                  # pytest suite (structure-enforcement tests live here too)
└── tools/
    ├── debug_launch.py         # GUI smoke-launch → netsentinel_debug.log (COMMIT GATE Step 3)
    ├── monkey_test.py          # Chaos/monkey tester (pywinauto UIA; --source/--connect/exe modes)
    ├── run_all_monkey_tests.ps1  # One-command chaos runner — coverage cycle + mild/moderate/wild soak (see below)
    └── audit_check.py          # Runtime audit of scan-registry / Scan Center wiring
```

### Chaos/monkey test log location (RULE-CHAOS3)

`run_all_monkey_tests.ps1` (`.\test.ps1` wrapper) — the "let it run for hours" harness — **always**
writes to `%USERPROFILE%\Documents\NetSentinel\test_output\run_<timestamp>\`, never to the repo's
own `test_output\`. Full docs: `docs/chaos-testing.md`.

- **`run_<timestamp>\AI_REPORT.md`** — start here. Rewritten after every phase (survives a hang or
  Ctrl+C), has the phase results table (Peak RSS column — watch for a climb across mild → moderate
  → wild) and, for any crashed/errored phase, embedded crash-file contents + tracebacks.
- Per-phase subfolders (`sweep_00/`, `soak_01_mild/`, `soak_01_moderate/`, `soak_01_wild/`,
  `sweep_soak_final/`, ...) hold the raw `monkey.log` / `systematic.log` and `monkey_summary.json`
  behind each report row.
- To find the run: `Get-ChildItem "$env:USERPROFILE\Documents\NetSentinel\test_output" -Directory |
  Sort-Object LastWriteTime -Descending | Select -First 1`, or just take the newest `run_*` folder.
- The repo-root `test_output\monkey.log` is a **different, unrelated** file — leftover from ad-hoc
  single-shot `python tools\monkey_test.py` invocations without `--output-dir`. It is not what a
  `run_all_monkey_tests.ps1` session writes to; do not mistake it for the current/latest run.
- Independently verify "0 crashes / 0 exceptions" claims against
  `%LOCALAPPDATA%\NetSentinel\netsentinel_crash.log` / `netsentinel_exceptions.log` **mtime**, not
  just the harness's self-reported counts (RULE-CHAOS2 — a native fault doesn't always surface as
  a caught exception).

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

**Batched multi-row writes:** `_BatchWritesMixin` (`metric_store_writes_batch.py`) provides
`record_app_traffic_samples()` and `record_availability_cycle()` — one-transaction batch
versions of the single-row `record_app_traffic_sample()` / `record_rtt()` + `record_device_state()`
calls, used respectively by `ui/tabs.py::_on_app_traffic_sample` (every ~10 s on the GUI thread)
and `modules/availability_monitor.py::run_cycle` (every 60 s) to replace one SQLite commit per
row with one commit per burst.

### Speed tester cascade (ARCH RULE 24)
`modules/speed_tester.py` tries backends in order:
1. **Ookla CLI binary** — `_find_ookla_cli()` searches 7 locations including WinGet Links dir
2. **speedtest-cli library** — 8 download / 4 upload threads; SSL-patched for Python 3.12
3. **Pure-Python HTTP** — 16 download / 8 upload `ThreadPoolExecutor` TCP streams

Frontend (`SpeedTestResult` dataclass) is identical regardless of backend.

### Network environment detection & scan authorization (ARCH RULE 26)
`modules/network_environment.py` classifies the active network before any active probe runs —
`NetworkEnvironment.kind`: `"home"` / `"vpn"` / `"corporate"` / `"large_subnet"` — and derives
`scope_cidr` (the real local subnet, whatever width; never forced to `/24`, so a flat corporate
L2 keeps scanning all its devices) plus `network_fingerprint()` (gateway MAC + subnet, used as
the per-network authorization key — two different physical "home" networks are asked about
separately).

`ui/scan_settings.py` is the single control surface for environment-aware scan defaults, all
overridable via Settings → Network Scanning:
- `effective_flush_caches()` — default ON for home, OFF for vpn/corporate/large_subnet
- `effective_scan_scope_cidr()` — bounds active probing to `scope_cidr` on non-home networks
- `is_network_authorized()` / `set_network_authorized()` — QSettings `scan/net_auth/<fingerprint>`
- `effective_syn_rate_cap()` — 50 pps unauthorized, 150 pps authorized+managed (vpn/corporate),
  unrestricted authorized+home/large_subnet
- shared `get_excluded_hosts()`/`set_excluded_hosts()`/`is_host_excluded()` host exclusion list,
  read by the SYN/UDP/Credentialed scan workers alike

**Authorization gate is intentionally asymmetric.** Port Scan (TCP/UDP) is a SOFT gate — an
unauthorized network never blocks the scan, only caps its rate, behind a one-time-per-fingerprint
modal (`ui/tabs_recon.py::_ensure_active_probe_authorization()`). Login Test is a HARD gate —
refuses to run at all when unauthorized, plus an always-shown, never-persisted extra confirmation
specifically on vpn/corporate networks — because a login attempt has no meaningful "reduced" form
and account lockout is a sharper, less-recoverable harm than an extra port probe. Home networks
never see either dialog.

`modules/adaptive_timing.py::measure_gateway_rtt()` (median of 3 ICMP pings to the gateway) +
`derive_profile()` derive a per-probe `TimingProfile` (`timeout = clamp(rtt_ms/1000 * 8, floor,
ceiling)`) so probe timeouts scale with real network latency instead of a fixed home-LAN
constant — threaded into `rogue_device.scan()` and `name_resolver.resolve()`.

`ui/widgets/environment_banner.py` shows a dismissible Home banner (keyed per environment
fingerprint) plus a one-time pre-scan "Scan Anyway / Cancel" notice when the detected network
looks unfamiliar or large.

`known_device.hostname_resolved_at` (schema v21) backs a 7-day hostname-resolution TTL cache in
`rogue_device.scan()` — a cache-hit device skips `resolve_batch()` entirely (still runs through
vendor/device-type reclassification) so repeat scans on large/VPN networks don't re-pay full
resolution cost every time.

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
    state: str,      # "never" | "running" | "fresh" | "stale" | "error" | "not_testable"
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
- `"not_testable"` → `VIOLET` — the probe was structurally blocked (e.g. a VPN/firewall dropped
  every packet) rather than run-and-clean; kept distinct from `"error"` so risk scoring and the
  Security Overview grade don't read a blocked probe as a confirmed-safe result. Set on the
  dataclass result (`not_testable: bool` / `not_testable_reason: str`) by the module, read by the
  UI result handler — never inferred in the UI layer.
- `"never"` → `""` (dot hidden)

**Freshness thresholds** (`_FRESH_SECONDS` class dict on `_NavBuilderMixin`):
Port scans default to 2 h; CVE/TLS to 24 h; unknown labels use `_DEFAULT_FRESH_SECONDS = 3600` (1 h).
`_check_and_stale_registry()` runs every 5 minutes and promotes `"fresh"` → `"stale"` when the threshold is exceeded.

**QSettings persistence** — key `scan_registry/state` (JSON). Restored on startup via `_restore_scan_registry()`; any entry stored as `"running"` is reset to `"never"` on restore (mid-scan interrupted by exit).

**`_AUDIT_SCAN_LABELS`** (in `security_overview_page.py`) — 16-item tuple of all nav page labels shown in the Scan Status card rows: `"Port Scan (TCP)"`, `"Port Scan (UDP)"`, `"CVE Lookup"`, `"Threat Intel"`, `"TLS & Exposure"`, `"Login Test"`, `"OS Detection"`, `"Exposed to Internet"`, `"Full Device Discovery"`, `"Device Risk Score"`, `"CVE Tracker"`, `"Windows Shares (SMB)"`, `"Recon Plugins"`, `"Private Endpoint Check"`, `"Cloud Metadata Probe"`, `"DHCP Rogue Monitor"`. These must exactly match the strings passed to `_nav_set_scan_state()` in `ScanResultMixin`; `modules/scan_guidance_audit.py`'s `AUDIT_CARD_PARITY` check (`python app.py --audit`) enforces the set stays reconciled against every registered audit page that actually reports scan state.

**Security Scan panel** — `_SecurityScanPanel._TOOLS` (in `ui/widgets/overview_tile.py`) is a
6-item checkbox list on the Overview page ("Threat Intel", "TLS & Exposure", "Device Risk
Score", "CVE Lookup", "Port Scan (TCP)", "Exposed to Internet") that the user checks/unchecks
before clicking "Run". Selected labels emit via `run_clicked` → `overview_page.py`'s
`security_scan_requested` signal (wired in `ui/tabs.py`) → `dashboard.py._run_security_scans()`.

**Security Audit Coordinator** — `dashboard.py._advance_security_audit()` pops labels one at a
time from `_pending_security_tools` and dispatches by comparing against `NavLabel` enum members.
Six labels have working dispatch code — `L.PORT_SCAN_TCP`, `L.EXPOSED_TO_INTERNET`,
`L.THREAT_INTEL`, `L.DEVICE_RISK_SCORE`, `L.CVE_LOOKUP`, `L.TLS_EXPOSURE` — matching
`_SecurityScanPanel._TOOLS`'s 6-item list above 1:1; any other label falls through the
"unrecognised label — skip silently" branch. Each branch either advances the queue itself or
hands off to a downstream result handler that does (e.g. `scan_wiring.py::_on_syn_result()` for
`PORT_SCAN_TCP`, `dashboard.py::_on_threat_intel_scan_complete/_error/_not_testable()` for
`THREAT_INTEL`) — `modules/scan_guidance_audit.py`'s `AUDIT_QUEUE_TERMINATES` check enforces every
branch reaches an advance call. There is no numeric progress bar for this coordinator — the
status bar shows "Security audit complete — see Security Overview for findings." once the queue
empties.

### Scan workers
All network operations run in `workers/` (QThread subclasses). Emit `result_ready` and `error` signals. **Never** do blocking I/O on the main thread.

### Risk levels — two separate systems

**Internal scan risk scoring** (used in scan results, `RISK_COLORS`/`RISK_BG` in `ui/styles.py`):
`HIGH` > `STORM` > `MEDIUM` > `WARNING` > `LOW` > `CLEAN` > `UNKNOWN`

**UI severity labels** (used in alert displays, CVE pages, RULE-A3):
`Critical` > `High` > `Warning` > `Info`

These are distinct systems that coexist. Do not mix them — never display internal risk level strings like "STORM" or "CLEAN" to users as severity labels, and do not use UI severity labels (e.g. "Critical") as internal risk level values in RISK_COLORS lookups.

## Colour Palette (ui/styles.py constants)

Two themes exist, switchable instantly at runtime (`ui/styles.py::apply_theme()`); neither is
hardcoded UI truth. **`DEFAULT_THEME = "Midnight Pro"`** ([styles.py:324](ui/styles.py#L324)) —
the app is dark by default on a fresh install. Arctic Clean is the alternate light theme, opted
into via the Settings page theme swatch.

**Midnight Pro (dark, default):**
```python
NAV_BAR     = "#0D1117"   # top application bar
SIDEBAR_BG  = "#161B22"   # left sidebar
BG_DARK     = "#0D1117"   # main content area
BG_CARD     = "#1C2128"   # card backgrounds
BG_HOVER    = "#1A2233"   # table row hover
BG_ALT_ROW  = "#111820"   # zebra alternate row
ACCENT      = "#3B82F6"   # primary brand blue (brighter royal blue)
TH_BG       = "#0D1520"   # table header navy
TH_TEXT     = "#E6EDF3"
TEXT_PRIMARY   = "#E6EDF3"
TEXT_SECONDARY = "#8B949E"
BORDER      = "rgba(255,255,255,0.08)"   # QSS-only — see RULE 10
RED    = "#F85149"
AMBER  = "#F5B942"
GREEN  = "#4CAF50"
VIOLET = "#A78BFA"   # not_testable / "could not test" — distinct from ACCENT
```

**Arctic Clean (light, alternate):**
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
VIOLET = "#6D4FC4"   # not_testable / "could not test" — distinct from ACCENT
```

## WinGet Distribution

`Ookla.Speedtest.CLI` is declared as `ExternalDependencies` (NOT `PackageDependencies`) in all winget manifests.
See RULE-R3: using `PackageDependencies` blocks the install when the package is not in the official winget index.
The Inno Setup installer has an optional task that runs `winget install Ookla.Speedtest.CLI --silent`.
`OoklaCliBanner` in `ui/pages/ookla_cli_banner.py` handles in-app one-click install for portable users.

**Never bundle `speedtest.exe` inside the installer** — it has a proprietary Ookla EULA.
