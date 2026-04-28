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
| Config persistence | QSettings / INI file (NetSentinel.ini) |
| Logging | Python `logging` module + custom CSV logger |

## Repository Layout

```
netsentinel/
├── app.py                  # Entry point — creates QApplication, launches Dashboard
├── cli.py                  # Headless CLI interface
├── svc.py                  # Windows service wrapper
├── requirements.txt
├── apm.yml                 # APM manifest
├── modules/                # All backend logic (no PyQt imports)
│   ├── arp_monitor.py      # Live ARP spoof detection
│   ├── bandwidth_monitor.py
│   ├── cloud_metadata.py
│   ├── combined_discovery.py  # Main scan orchestrator
│   ├── credentialed_scan.py
│   ├── cve_lookup.py
│   ├── device_classifier.py   # OUI → device type + risk score
│   ├── dhcp_detector.py
│   ├── dns_correlator.py      # Ping/DNS latency + outage detection
│   ├── internet_exposure.py
│   ├── iot_baseline.py
│   ├── mac_registry.py        # OUI database (offenders.json)
│   ├── network_logger.py      # Background ping logger
│   ├── os_fingerprint.py
│   ├── port_scanner.py
│   ├── risk_scorer.py
│   ├── rogue_device.py
│   ├── scheduler.py
│   ├── snmp_poller.py
│   ├── storm_analyser.py
│   ├── stp_detector.py
│   ├── syn_scanner.py
│   ├── tls_checker.py
│   ├── notification_router.py  # Per-channel alert delivery (Toast/Webhook/Email), delivery log
│   ├── config_baseline.py      # Config snapshot builder + diff engine
│   ├── trend_analyser.py       # OLS regression over RTT/loss/jitter; ETA-to-threshold alerting
│   ├── maintenance_window.py   # Maintenance window manager — alert suppression
│   └── utils.py               # get_network_info, is_admin, etc.
├── ui/
│   ├── styles.py           # SINGLE SOURCE OF TRUTH for all colours and QSS
│   ├── dashboard.py        # Main window — all tab pages built here
│   ├── live_graph.py       # Matplotlib RTT line chart (Module 5)
│   ├── topology_widget.py  # Matplotlib network topology map
│   └── matrix_rain.py      # Easter egg (Ctrl+Shift+M)
├── workers/
│   └── scan_worker.py      # QThread workers for background scans
└── tests/
```

## Key Architectural Patterns

### Single stylesheet
All colours, fonts, and QSS rules live in `ui/styles.py`. **Never** hardcode hex colours or font sizes anywhere else in the codebase. Always import from `ui/styles.py`.

### Dashboard navigation model
The main window uses a `QListWidget` sidebar (`objectName="sideNav"`) + `QStackedWidget` — **not** `QTabWidget`. Pages are registered via `_nav_add_page()`. Section headers via `_nav_add_section()`.

Sidebar sections:
- **Standard** — core scan modules (always visible)
- **Advanced** — MTR, topology, ARP watch, DHCP, bandwidth (hidden until Advanced Mode toggled)
- **Security Audit** — SYN/UDP scan, OS detect, CVE, credentials (hidden until Audit Mode toggled)

### Scan workers
All network operations run in `workers/scan_worker.py` (QThread subclasses). They emit `result_ready` and `error` signals. The Dashboard connects these signals to UI update slots. **Never** do blocking I/O on the main thread.

### Module result objects
Each scan module returns a dict with at minimum:
- `devices` — list of device dicts
- `verdict` — plain-English summary string
- `level` — `"CLEAN"` | `"LOW"` | `"MEDIUM"` | `"HIGH"` | `"STORM"`

### Risk levels (canonical)
`HIGH` > `STORM` > `MEDIUM` > `WARNING` > `LOW` > `CLEAN` > `UNKNOWN`

Colours are defined in `RISK_COLORS` and `RISK_BG` in `ui/styles.py`.

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

## Settings Persistence
`Dashboard._save_settings()` / `_restore_settings()` use `QSettings` to persist: scan mode (standard/advanced/audit), checkbox states, spinbox values, window geometry, and last-used directory.

---

## Security Architecture — Non-Negotiable Constraints

These constraints are permanent. Every new module, worker, page, and backlog item must be designed with them as hard requirements — not afterthoughts.

### Credential storage model

```
User types secret (password / API key / token)
         │
         ▼
QLineEdit (EchoMode.Password — ALWAYS)
         │
         ▼
  keyring.set_password("NetSentinel", "<service>/<key>", value)
         │
         ▼
  OS credential store
  ├── Windows: Windows Credential Manager (DPAPI-encrypted)
  ├── macOS:   Keychain
  └── Linux:   libsecret / KWallet
```

**Nothing else is permitted.** QSettings, MetricStore, INI files, JSON, CSV, and log files are all strictly forbidden as secret stores.

### What goes where

| Data type | Permitted storage |
|---|---|
| User preferences (theme, scan interval, checkbox state) | QSettings / NetSentinel.ini ✓ |
| Metric time-series (RTT, loss, bandwidth, alerts) | MetricStore / NetSentinel.db ✓ |
| Device inventory (IP, MAC, hostname, risk) | MetricStore / NetSentinel.db ✓ |
| Notification channel config (host, port, username) | QSettings ✓ |
| **Passwords, API keys, tokens, secrets** | **OS keychain via `keyring` ONLY** |
| **Anything above in logs or exports** | **Forbidden — strip before write** |

### Network binding rule

Any local server feature (REST API, SNMP trap receiver, syslog receiver) **must** bind to `127.0.0.1` by default. Binding to `0.0.0.0` or a specific interface requires:
1. An explicit user toggle in the Settings page
2. A visible warning label in the UI explaining the exposure risk

### Outbound HTTP hygiene

Modules that call external HTTP APIs (`cve_lookup`, `mac_lookup`, `trend_analyser`, `notification_router`, future threat-intel feeds):
- Must enforce a per-request timeout (never hang indefinitely)
- Must rate-limit requests (minimum 1-second gap between calls to the same host)
- Must never send local device data (IPs, MACs, hostnames) to external APIs without explicit user consent documented in the Settings UI
- CVE lookups: send only CPE strings, never raw IP addresses
- MAC lookups: send only the OUI prefix (first 3 octets), never the full MAC

### Future backlog items — security design requirements

Every backlog item that involves secrets or network exposure must be implemented as follows:

| Feature | Security requirement |
|---|---|
| Push notifications (Pushover / Telegram / ntfy) | API key/bot token stored in OS keychain only; never in QSettings or DB |
| REST API (local) | API key: `secrets.token_hex(32)`, stored in keychain; bind 127.0.0.1 by default |
| WMI enrichment | Windows credentials stored in keychain; never hardcoded or in INI |
| Distributed probe agent | Mutual TLS or pre-shared key stored in keychain; no bare HTTP |
| Automation hooks (script runner) | Script paths stored in QSettings; no credential passing via command-line args |
| Compliance reports | Reports must not embed raw credentials or device passwords in exported output |
| DHCP lease import | DHCP server credentials stored in keychain; lease data (IPs/MACs) stays local |
| Agent-based monitoring | Agent registration token stored in keychain; TLS required for agent↔dashboard channel |
