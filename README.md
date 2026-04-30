# NetSentinel

> **Network Security Scanner, Rogue Device Detector & ISP Accountability Tool for Windows**  
> Find every device on your LAN — detect rogue bridges, broadcast storms, ARP spoofing, and IoT anomalies — prove ISP outages with timestamped evidence — all analysis runs 100% locally, nothing leaves your machine.

**Keywords:** network scanner, rogue device detection, STP monitor, broadcast storm analyser, ARP spoof detector, IoT security baseline, DNS outage detection, ISP accountability, network health grade, port scanner, CVE lookup, Windows network tool, PyQt6, Npcap

![CI](https://github.com/ossianericson/netsentinel/actions/workflows/release.yml/badge.svg)
[![winget](https://img.shields.io/badge/winget-NetSentinel.NetSentinel-blue)](https://winstall.app/apps/NetSentinel.NetSentinel)
![License](https://img.shields.io/github/license/ossianericson/netsentinel)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

<!-- Screenshot or GIF here — shows the main dashboard on first launch -->

---

## Install

### Windows — one command
```powershell
winget install NetSentinel.NetSentinel
```
Or download the installer from the latest release:

### 👉 [Latest Release](https://github.com/ossianericson/netsentinel/releases/latest) — v1.5.1

| OS | File | How to run |
|---|---|---|
| **Windows** | `NetSentinel-Setup.exe` | Run installer, then right-click shortcut → **Run as Administrator** |
| **Windows** | `NetSentinel.exe` *(portable)* | Right-click → **Run as Administrator** |
| **macOS** | `NetSentinel-macOS.zip` | Unzip → right-click app → **Open** (first launch bypasses Gatekeeper) |
| **Linux** | `NetSentinel` | `chmod +x NetSentinel && sudo ./NetSentinel` |

> **Rogue Bridge (STP) & Broadcast Storm tabs** require [Npcap](https://npcap.com) (free, one-click installer) on Windows.

### Updating

If you installed via winget:
```powershell
winget upgrade NetSentinel.NetSentinel
```
Or download the new installer from the [latest release](https://github.com/ossianericson/netsentinel/releases/latest).

### First run on Windows — if you downloaded the .exe directly

Windows marks files downloaded from the internet as blocked. **This does not apply to winget installs.** Unblock before running.

**Option A — PowerShell (fastest):**
```powershell
Unblock-File -Path "$env:USERPROFILE\Downloads\NetSentinel.exe"
```
Then right-click → **Run as Administrator**.

**Option B — Explorer:**
1. Right-click `NetSentinel.exe` → **Properties**
2. Tick **Unblock** at the bottom of the General tab
3. Click **OK** → right-click → **Run as Administrator**

**SmartScreen warning ("Windows protected your PC")?**  
Click **More info** → **Run anyway**. Verify the file against the SHA-256 hash on the release page.

---

## Why NetSentinel exists

Modern home networks have a hidden problem: mesh routers, smart speakers, and IoT devices now silently participate in **enterprise Layer-2 protocols** — STP, IPv6 RA, mDNS — with zero user-visible indication. A Google Nest node connected via Ethernet can win the STP Root Bridge election and force your real router to block its own uplink port every 30 seconds. The result: the exact intermittent drops and DNS failures that every ISP helpdesk dismisses as "WiFi interference."

Meanwhile, diagnosing a real ISP outage requires five separate tools that don't talk to each other and produce no evidence you can hand to a support technician.

NetSentinel is the single tool that:
- **Identifies** every device — IP, hostname, MAC, vendor, model (e.g. "Google Nest Audio", "TP-Link Deco M5"), device type, and risk level
- **Proves** outages with timestamped CSV logs you can attach to ISP support tickets
- **Generates an ISP Accountability Report** — MTR hop table, packet loss %, DNS latency, outage log — formatted for support escalation
- **Grades your network** A–F across Uptime, Latency, Jitter, DNS Speed, Download Speed, Device Safety, STP Health, and Broadcast Storm Level
- **Finds the Layer-2 culprit** — rogue Root Bridges, broadcast storms, hidden SSIDs, ARP spoofing
- **Monitors IoT behaviour** — learns what's normal for each device and alerts when a smart device starts behaving like a compromised host
- **Continuously tracks availability** — background monitor records every device's UP/DEGRADED/DOWN state to a local SQLite database every 60 s, with full event history
- **Runs 100% locally** — no cloud account, no telemetry, no data sent anywhere

---
## Key features

### Standard tabs (no admin required)

| Tab | What it tells you |
|---|---|
| 📌 **Pinned (Quick Access)** | Top-level section always open on startup — Overview, DNS & Outages, Live Bandwidth, Speed Test, Devices on Network, Availability History, Active Connections. Instant one-click access without expanding any subgroup. |
| 🏠 **Overview Dashboard** | Configurable live tile dashboard — Device Count, Fleet Uptime, Service Status, TLS Health, RTT Summary, Network Grade, Alert Feed, Device Events. Drag tiles to reorder in Edit Layout mode; layout persists across sessions. |
| 🔍 **Devices on Network** | Every device on your subnet — IP, hostname, MAC, vendor, **device model** (e.g. "Google Nest Audio", "TP-Link Deco M5"), device type, and risk level. Right-click any device for a **🔧 How to Fix** guide. |
| 📶 **WiFi Networks** | Hidden SSIDs, rogue access points, co-channel interference, WPS-enabled networks, connected client list. |
| 📡 **DNS & Outages** | Live ping + DNS latency graph. Identifies STP reconvergence signatures and DNS hijacking patterns in real time. |
| 🗓 **Availability History** | Persistent RTT and UP/DEGRADED/DOWN state charts with 1h / 12h / 24h / 7d zoom. Auto-recorded by the background monitor every 60 s — no manual action needed. |
| 📜 **Inventory Changes** | Full log of every device JOINED, LEFT, UP, DOWN, DEGRADED, and RECOVERED event with severity filter and 1h–30d zoom. |
| ⏱ **Uptime & SLA** | Per-device uptime % for 24h / 7d / 30d. Fleet average, best/worst device KPI tiles. Colour-coded rows (green ≥99 %, amber ≥95 %, red <95 %). |
| 🔌 **Service Heartbeat** | TCP port reachability checks every 60 s per configured service. SERVICE_DOWN alert with cooldown. KPI tiles and per-service RTT column. |
| 📄 **Auto Reports** | Scheduled HTML status reports at a configurable interval and output directory. Covers device uptime, TLS certs, services, and device events. “Generate Now” button; auto-prune to keep the last N reports. |
| 🌐 **My Network Info** | Full snapshot: local IPs, subnet, gateway, DNS servers, DHCP lease, adapter speeds, WiFi signal. One-click OS settings shortcuts and router admin links. |
| 📊 **Network Grade** | **A–F benchmark** across 8 dimensions compared to a “Perfect Home Network” baseline. Includes **📊 Generate ISP Report** — exports an HTML document for support tickets. |
| 💊 **Health Check** | On-demand diagnostics: ping to 5 targets, DNS speed comparison (System / Cloudflare / Google / Quad9), HTTP check, DNS leak test, public IP, download speed test, traceroute. |
| 📋 **Stability Log** | Runs unattended for hours or days. Timestamped CSV log of every ping, outage, DNS latency, and ARP change. Load any past log for automated plain-English analysis. Evidence-grade output for ISP disputes. |
| 🔷 **IPv6 Devices** | Link-local segment sweep — reads OS neighbour cache and pings every `fe80::/10` address. |
| 🔍 **Root Cause Analysis** | Cross-correlates STP, Storm, Diagnostics, and Logger data. Automatically distinguishes a local network fault from an ISP infrastructure problem. |
| ⚡ **Broadcast Storm** | Measures broadcast/multicast flood levels that silently choke bandwidth. Right-click any storm source for remediation steps. |
| 🤖 **IoT Behaviour** | Learns normal traffic for each IoT device (cameras, smart speakers, TVs). Alerts when a device starts contacting new servers, scanning ports, or flooding traffic. |
| 🌉 **Rogue Bridge (STP)** | Catches the hidden cause of 15–45 s periodic drop cycles: a mesh node or unmanaged switch claiming to be the network Root Bridge. Right-click any rogue entry for step-by-step disconnect instructions. || 🔔 **Notifications** | Per-channel delivery rules for Toast, Webhook, and Email alerts. Minimum severity filter per channel, rule-type allowlist, delivery log, and test buttons. |
| 📸 **Config Snapshots** | Point-in-time snapshots of the full device fleet with structured diff between any two snapshots — added/removed devices, port changes, SNMP drift. |
| 📈 **Trend Forecasts** | OLS regression over stored RTT/loss/jitter data predicts when metrics will breach thresholds. ETA column colour-coded CRITICAL / WARNING / CLEAN. |
| 🔧 **Maintenance Windows** | Suppress all alerts for a device (or fleet-wide) during a defined maintenance period. Suppression log, auto-refresh, purge of expired windows. |
| ⚡ **Custom Triggers** | Write custom alert conditions using a metric expression language — e.g. `avg(rtt["ip"], 5m) > 80 AND loss%["ip"] > 5`. Visual rule builder with live plain-English preview, per-rule severity and cooldown. Rules evaluated every monitoring cycle. |
| 📶 **WiFi Heatmap** | Import a floor plan image and walk your space collecting signal-strength readings per scan. IDW interpolation renders a colour-coded heatmap overlay showing coverage gaps per access point. Export as PNG. |
| 🗺 **Geolocation Map** | Plot internet-facing IPs on an offline world map using a local MaxMind GeoLite2-City database — no external API calls, no telemetry. One-click import from Threat Intelligence blocklist results. |

### UI & Customisation

| Feature | Details |
|---|---|
| ◆ **3-mode progressive navigation** | The sidebar operates in three modes cycled by a pill at the top: **Home** (5 essentials + grade circle + recent alerts), **Standard** (full flat list under section headers), and **Pro** (adds Security Audit items with admin badges). The active mode is saved across sessions. |
| 🔒 **Single-instance guard** | Launching a second copy of NetSentinel restores and focuses the already-running window instead of opening a duplicate. Works across minimised and tray-hidden states. |
| 🔕 **Boot alert warmup** | Network alerts are suppressed for the first 10 seconds after startup to prevent spurious notifications before the first monitoring cycle completes. |
| 🔔 **Tray restore on any click** | Clicking the tray icon (single or double), or clicking a notification bubble, always restores and focuses the main window. |
| 🎨 **Three Colour Themes** | Arctic Clean (professional light), Midnight Pro (deep charcoal + electric cyan), Obsidian Neon (true black + neon lime). Click **⚙** in the top bar → **App Settings (Theme & Display)…**; takes effect on next launch. |
| ❓ **Help & Reference** | Click **❓** in the top bar to open Help from any page. Contains Risk Level Guide (CLEAN→STORM), Common Scenarios lookup table, and a 24-term networking glossary. |
| 👋 **First-Run Onboarding** | 3-step action wizard on first launch. Each step has a one-click action button: Scan your network → Run a speed test → See your Network Grade. Completing steps populates the Home page mini-cards live; skippable at any time. State persisted to QSettings. |

### Advanced Mode tabs

| Tab | What it gives you |
|---|---|
| 🔁 **Hop-by-Hop Trace (MTR)** | Continuous traceroute — live per-hop loss %, avg RTT, last RTT, updating every cycle. |
| 🔧 **Tools & Wake-on-LAN** | TCP port scanner (Fast/Normal/Low Impact), service version detection, banner grab, Wake-on-LAN magic packet sender, new-device baseline diff alert. |
| 🗺 **Network Map** | Visual topology diagram of your network. |
| 🛡 **ARP Spoof Watch** | Detects ARP poisoning and MITM attacks. |
| 📦 **DHCP Leases** | Detects rogue DHCP servers. |
| 📊 **Bandwidth Usage** | Per-device rx/tx bps monitor using live packet capture. |
| ⏱ **Scheduled Scans** | Automated scans every N minutes with desktop notifications on new or changed devices. |
| 📟 **SNMP Device Info** | Polls basic SNMP OIDs (sysDescr, sysName, sysUpTime, ifTable) — no pysnmp dependency. |
| 📥 **SNMP Trap Receiver** | Passive UDP listener (port 162, falls back to 16200 without admin). Decodes SNMPv1/v2c traps with stdlib-only BER/ASN.1 parser. Live trap table with varbind detail dialog. |
| 📜 **Syslog Viewer** | Passive UDP/514 listener (falls back to 5140 without admin). RFC 3164 and RFC 5424 decoding. Severity/facility colour-coding, text + severity filter, double-click detail dialog. |
| ⚙ **Automation Hooks** | Event-driven rules that fire a webhook URL or run a local script when network events occur (device down, high RTT, new device, alert fired). Rules stored locally; no cloud dependency. |
| 📄 **Network Documentation** | Auto-generates a formatted HTML or Markdown snapshot of your full network — device inventory, services, open ports, topology description, and TLS status — on demand or on schedule. |
| 📡 **MQTT / Home Assistant** | Publishes device discovery, availability, and metric events to any MQTT broker. Pre-formatted Home Assistant MQTT Discovery payloads; configurable topic prefix, QoS, and broker credentials (OS keychain). |

### Security Audit Mode tabs (for IT professionals)

| Tab | What it gives you |
|---|---|
| 🧠 **Threat Intelligence** | Feodo Tracker + Emerging Threats blocklist feeds. AbuseIPDB v2 manual lookup (consent-gated, OUI-only, key in OS keychain). KPI tiles: blocklist hits, high-confidence IPs, last update. |
| 🔒 **TLS Certificates** | Per-host certificate expiry monitoring. Hourly checks. Badges: OK / EXPIRING (< 30 days) / EXPIRED / UNREACHABLE. Alerts fire automatically; results persisted to MetricStore. |
| 🔎 **Port Scan (SYN)** | Raw SYN scanner via Scapy — stealth half-open scan, faster than TCP connect. Requires admin. |
| 🔎 **Port Scan (UDP)** | UDP port scanner. Identifies DNS, SNMP, NTP, mDNS and other UDP services. Requires admin. |
| 💻 **OS Detection** | OS fingerprinting via TTL + banner grab + TCP SYN probe. |
| ⚠ **Device Risk Score** | Numeric risk score per device based on open ports, OUI flags, OS, and exposure. |
| 🛡 **Known CVEs** | NVD API v2 CVE lookup for detected OS/service versions. Rate-limited; offline-safe. |
| 📋 **CVE Tracker** | CVE lifecycle state machine per host/service: Open → Acknowledged → Accepted Risk → Remediated. Import from scan, days-open counter, owner field. Right-click to change state or open NVD. |
| 🌍 **Exposed to Internet** | WAN IP, CGNAT detection, UPnP port-mapping enumeration. |
| 🔑 **Login Test (SSH/SMB)** | Credential test against discovered SSH and SMB services. |
| 🔭 **Full Device Discovery** | Parallel ARP + ICMP + TCP SYN + mDNS sweep — highest-accuracy device census. |
| 🗂 **Windows Shares (SMB)** | NetBIOS + SMB share and user enumeration. |
| 🔌 **Plugin Modules** | Run custom scan modules. Drop a `.py` file into the `plugins/` folder — no restart needed. |
| 🔒 **Private Endpoint Check** | DNS/TCP/TLS reachability checker for cloud private endpoints. |
| ☁ **Cloud Metadata Probe** | Detects cloud VM SSRF metadata endpoint exposure (AWS/Azure/GCP). |

---

## ISP Accountability Report

The **📊 Generate ISP Report** button in the Network Grade tab exports a self-contained HTML file designed for ISP support tickets.

It bundles:
- Overall network health grade and score
- Performance breakdown with colour-coded A–F grades per dimension
- Traceroute / MTR hop table with per-hop packet loss — loss first appearing at hop 2+ is in the ISP's network
- Timestamped outage log from the Stability Logger
- Key metrics: uptime %, average latency, jitter, download speed, public IP
- Plain-English guide for the support technician

Print to PDF: **Ctrl+P → Save as PDF**.

---

## Network Grade — A to F

The **📊 Network Grade** tab scores your connection against a calibrated "Perfect Home Network" baseline:

| Dimension | Ideal |
|---|---|
| Connection Uptime | = 99.5 % |
| Average Latency | = 20 ms |
| Jitter (Call Quality) | = 5 ms |
| DNS Response Speed | = 30 ms |
| Download Speed | = 25 Mbps |
| Network Device Safety | 0 high-risk devices |
| Spanning Tree (STP) Health | 0 rogue bridges |
| Broadcast Storm Level | < 50 broadcast pkt/s |

Each dimension shows your value, the ideal target, a letter grade, a plain-English verdict, and an actionable fix tip. The weighted overall grade also drives the Visual Diagnostic Overlay colour (green for A/B, amber for C, red for D/F).

---

## How to Fix — right-click anywhere

Right-click any device, BPDU source, or storm source in the scan results for a **🔧 How to Fix** dialog with numbered remediation steps. The Root Cause Analysis tab also shows a **How to Fix It** column for every finding.

---

## IoT Behavioural Baseline

1. **Learn** (30–600 s): captures which IP addresses, ports, and packet rates each device normally uses
2. **Monitor**: continuously watches traffic and raises alerts:
   - **SYN_SCAN** — device port-scanning the network (compromised IoT signature)
   - **NEW_DEST** — device contacting a server it has never contacted before
   - **NEW_PORT** — device using an unusual port
   - **METADATA_PROBE** — device querying cloud metadata endpoints (potential SSRF)
   - **RATE_SPIKE** — traffic 5× above baseline

---

## Background Network Logger — evidence for ISP disputes

Start the logger and leave the app running. Each cycle logs:

| Option | What it records | Overhead |
|---|---|---|
| *(base)* | Ping RTT + pass/slow/fail per target | minimal |
| **Jitter** | 3× pings, standard deviation | ~3× ping time |
| **DNS latency** | System resolver round-trip | ~50 ms |
| **HTTP check** | Captive portal detect | ~100–300 ms |
| **ARP watch** | ARP table snapshot, alerts on new/changed MACs | ~100 ms |

Logs save to `~/Documents/NetSentinel/logs/`. Load any log for automated plain-English analysis including every outage start, end, and duration.

---

## Run from source

```bash
git clone https://github.com/ossianericson/netsentinel
cd netsentinel
pip install -r requirements.txt
python app.py          # add sudo / Run as Administrator for full packet capture
```

## Build your own executable

**Requirements before building:**
- Python 3.11 must be installed (`winget install Python.Python.3.11` on Windows). Python 3.12+ breaks the `speedtest-cli` dependency — the build must use 3.11.
- `build.bat` auto-creates a `.venv311` virtual environment and installs all dependencies including `speedtest-cli`. No manual pip steps needed.

```bash
# Windows — builds GUI + CLI + Windows service
build.bat

# macOS / Linux — builds GUI + CLI
chmod +x build.sh && ./build.sh
```

> **Speed test note:** `speedtest-cli 2.1.x` uses `ssl.wrap_socket()` which was removed in Python 3.12.
> Always build with Python 3.11. If you see speed test errors in the exe, verify your build venv:
> ```powershell
> .venv311\Scripts\python.exe --version   # must show 3.11.x
> ```

Output:
| Executable | Platform |
|---|---|
| `dist/NetSentinel.exe` | Windows GUI |
| `dist/NetSentinel-cli.exe` | Windows CLI (~80% smaller) |
| `dist/NetSentinel-svc.exe` | Windows service |
| `dist/NetSentinel` | Linux/macOS GUI |
| `dist/NetSentinel-cli` | Linux/macOS CLI |

---

## CLI — headless / CI mode

```bash
python cli.py scan --format html --output report.html
python cli.py scan --cidr 10.0.0.0/24 --format json --output devices.json
python cli.py diagnose
python cli.py log --interval 30 --targets 8.8.8.8 1.1.1.1 --dns --arp
python cli.py ports 192.168.1.1 --mode fast
python cli.py log-chart ~/Documents/NetSentinel/logs/netlog_20260426_120000.csv
```

**Exit codes (scan):** `0` = OK, `1` = error, `2` = HIGH-RISK devices found

---

## Windows Service — 24/7 background logger

```powershell
pip install pywin32
python -m pywin32_postinstall -install   # once, as Administrator
python svc.py install
python svc.py start
```

Config: `%PROGRAMDATA%\NetSentinel\netsentinel-svc.ini`  
Logs: `%PROGRAMDATA%\NetSentinel\logs\netlog_YYYYMMDD.csv`  
Load any service log in the Stability Log tab for full analysis.

---

## Local REST API

NetSentinel exposes a read-only HTTP API so external tools can query your network data.

**Disabled by default.** Enable in **Settings → Local REST API**.

| Setting | Default |
|---|---|
| Bind address | `127.0.0.1` (localhost only) |
| Port | `8765` |
| External access | Off — requires explicit toggle + acknowledges warning label |
| API key | Generated once with `secrets.token_hex(32)`, stored in OS keychain |

**Endpoints:**

```
GET /health                    — heartbeat (no auth required)
GET /devices                   — full device inventory
GET /alerts?hours=24           — recent fired alerts
GET /uptime/<ip>?hours=24      — uptime history for one host
GET /speed-history?hours=168   — speed test history
```

**Authentication:**
```
X-API-Key: <your-key>
# or
?api_key=<your-key>
```

**Example (curl):**
```bash
curl -H "X-API-Key: abc123..." http://127.0.0.1:8765/devices
```

**Example (Home Assistant REST sensor):**
```yaml
sensor:
  - platform: rest
    resource: http://127.0.0.1:8765/devices
    headers:
      X-API-Key: !secret netsentinel_api_key
```

---

## Project structure

```
app.py                      # GUI launcher
cli.py                      # Headless CLI
svc.py                      # Windows Service
offenders.json              # MAC OUI risk database (8 vendor groups, 115 OUI prefixes)
installer.iss               # Inno Setup Windows installer script

modules/
  rogue_device.py           # M1 — ARP scan, OUI fingerprinting, IPv6 RA snooping
  stp_detector.py           # M2 — STP/BPDU capture (requires Npcap)
  storm_analyser.py         # M3 — Broadcast storm detection
  wifi_scanner.py           # M4 — Hidden SSID, rogue AP, co-channel interference
  dns_correlator.py         # M5 — Live ping + DNS latency correlator
  network_diagnostics.py    # M6 — On-demand diagnostics, speed test, traceroute
  network_logger.py         # M7 — Long-term ping logger, outage detection, analysis
  network_benchmark.py      # Network health grader — A–F score across 8 dimensions
  root_cause_correlator.py  # Cross-module root cause analysis (ISP vs local split)
  iot_baseline.py           # IoT behavioural baseline learning and anomaly monitoring
  mac_registry.py           # Curated OUI/model registry (Google, TP-Link, Apple, Amazon, etc.)
  name_resolver.py          # Multi-method device name resolution (mDNS, NetBIOS, SNMP, DHCP)
  port_scanner.py           # TCP connect scanner, service version probes
  device_classifier.py      # Device-type classifier (IP Camera, NAS, Smart TV, etc.)
  risk_scorer.py            # Per-device risk scoring with numeric score and remediation
  os_fingerprint.py         # OS fingerprinting: TTL+banner + TCP SYN probe
  syn_scanner.py            # SYN scanner + UDP scanner (Scapy, requires admin)
  cve_lookup.py             # NVD API v2 CVE lookup, rate-limited, offline-safe
  internet_exposure.py      # WAN IP, CGNAT detection, UPnP port-mapping enumeration
  credentialed_scan.py      # SSH credentialed deep scan
  combined_discovery.py     # Parallel discovery: ARP + ICMP + TCP SYN + mDNS
  smb_enumerator.py         # NetBIOS + SMB share/user enumeration
  report_exporter.py        # HTML, JSON, CSV, Nmap XML, ISP Accountability Report
  log_chart.py              # RTT chart renderer (matplotlib PNG)
  utils.py                  # Cache flush, ping sweep, network info, WoL, device baseline
  arp_monitor.py            # ARP spoof / MITM detector
  dhcp_detector.py          # Rogue DHCP server detector
  bandwidth_monitor.py      # Per-device rx/tx bps monitor
  tls_checker.py            # SSL/TLS certificate checker
  snmp_poller.py            # SNMPv1/v2c poller (no pysnmp dependency)
  scheduler.py              # Scheduled scan engine with desktop notifications
  nl_query.py               # Natural language device filter (zero external deps)
  plugin_system.py          # Plugin loader — drop .py into plugins/
  private_endpoint_checker.py  # DNS/TCP/TLS checker for cloud private endpoints
  cloud_metadata.py            # Cloud VM / SSRF metadata exposure detection
  metric_store.py           # Persistent SQLite time-series database (RTT, device state, events)
  availability_monitor.py   # Continuous background availability monitor (UP/DEGRADED/DOWN state machine)
  device_tracker.py         # New/disappeared device detection — diffs scan results against known-device inventory
  alert_engine.py           # Threshold alerting engine (RTT/loss/down/new-device rules, cooldown, callbacks)
  cert_monitor.py           # TLS certificate expiry monitor — hourly checks, EXPIRING/EXPIRED alerts
  service_monitor.py        # TCP port heartbeat monitor — SERVICE_DOWN alerts with cooldown
  snmp_trap_receiver.py     # Passive SNMP trap listener — stdlib BER/ASN.1 decoder, SNMPv1/v2c
  syslog_receiver.py        # Passive syslog listener — RFC 3164 / RFC 5424 decoder
  report_scheduler.py       # Scheduled HTML report generation — configurable interval + pruning
  notification_router.py    # Per-channel notification delivery rules (Toast / Webhook / Email)
  config_baseline.py        # Config snapshot builder, diff engine (added/removed/changed devices)
  trend_analyser.py         # OLS regression over RTT/loss/jitter time-series; ETA-to-threshold
  maintenance_window.py     # Maintenance window manager — alert suppression during defined periods
  dhcp_lease_scanner.py     # DHCP lease inventory parser (dnsmasq / dhclient / nmcli / ARP+ipconfig)
  dns_zone_scanner.py       # AXFR zone transfer + mDNS Bonjour/Avahi enumeration
  threat_intel.py           # Threat intelligence DB (Feodo Tracker, ET, AbuseIPDB)
  rest_api.py               # Local read-only Flask REST API (127.0.0.1 default, OS-keychain API key)
  automation_hooks.py       # Event-driven automation: webhook/script triggers on network events
  net_doc_generator.py      # Auto-generates HTML/Markdown network documentation snapshots
  mqtt_publisher.py         # MQTT event publisher — Home Assistant Discovery + metric topics
  geo_locator.py            # Local IP geolocation via MaxMind GeoLite2-City.mmdb (no external API)
  wifi_heatmap.py           # WiFi signal-strength heatmap — IDW interpolation, JSON survey storage
  trigger_expression.py     # Custom alert trigger expression language, parser, and rule evaluator

ui/
  dashboard.py              # Main window — sidebar nav (Standard / Advanced / Security Audit)
  first_run_dialog.py       # 4-slide first-run onboarding dialog (shown once on first launch)
  npcap_banner.py           # Inline banner shown when Npcap is not installed on Windows
  topology_widget.py        # Network topology map widget
  matrix_rain.py            # Visual Diagnostic Overlay (Ctrl+Shift+M) — colour = network grade
  live_graph.py             # Real-time latency graph
  styles.py                 # Single source of truth for all colours, fonts, and QSS (3 themes)
  pages/
    overview_page.py        # Configurable live tile dashboard (drag-to-reorder)
    history_page.py         # Availability History charts (RTT + UP/DEGRADED/DOWN, 1h–7d zoom)
    inventory_page.py       # Inventory change log (JOINED/LEFT/UP/DOWN/DEGRADED/RECOVERED events)
    uptime_page.py          # Uptime & SLA table (24h / 7d / 30d per device)
    service_page.py         # Service Heartbeat monitor (TCP port checks every 60 s)
    reports_page.py         # Auto Reports — scheduled HTML report generation
    cert_page.py            # TLS Certificates — expiry monitor with OK/EXPIRING/EXPIRED badges
    snmp_trap_page.py       # SNMP Trap Receiver — passive trap listener and decode table
    syslog_page.py          # Syslog Viewer — passive UDP syslog listener
    settings_page.py        # App Settings — theme picker, display preferences, keyboard shortcuts
    notifications_page.py   # Notification routing rules — Toast / Webhook / Email / Pushover / ntfy / Telegram; escalation policy; delivery log
    baseline_page.py        # Config Baseline Snapshots — take, compare, diff viewer
    trend_page.py           # Predictive Trend Forecasts — OLS regression results table
    maintenance_page.py     # Maintenance Windows — schedule, manage, suppression log
    dhcp_lease_page.py      # DHCP Lease Inventory — platform-aware lease table
    dns_zone_page.py        # DNS Zone Map — AXFR + mDNS enumeration
    threat_intel_page.py    # Threat Intelligence — blocklist feeds, AbuseIPDB lookup
    cve_page.py             # CVE Tracker — lifecycle state machine per host/service
    home_automation_page.py # Home Automation Hub — HA/MQTT/Hue/Sonos detection
    connections_page.py     # Active Connections — process-to-socket map
    live_bandwidth_page.py  # Live Bandwidth — 60s rolling interface chart
    speed_test_page.py      # Speed Test — Ookla-compatible, arc gauge, history
    automation_page.py      # Automation Hooks — event-driven webhook/script trigger rules
    network_doc_page.py     # Network Documentation — auto-generates HTML/Markdown network docs
    mqtt_page.py            # MQTT / Home Assistant — publishes device events to MQTT broker
    wifi_heatmap_page.py    # WiFi Heatmap — floor plan import + IDW signal-strength overlay
    geo_map_page.py         # Geolocation Map — world-map visualisation of internet-facing IPs
    trigger_builder_page.py # Custom Triggers — visual rule builder for alert expressions

workers/
  scan_worker.py            # QThread workers (28 total)
  availability_worker.py    # Background device availability monitor (QThread, 60 s interval)
  cert_worker.py            # TLS cert check worker (QThread, hourly)
  service_worker.py         # Service heartbeat worker (QThread, 60 s interval)
  snmp_trap_worker.py       # SNMP trap listener worker (QThread, passive UDP)
  syslog_worker.py          # Syslog listener worker (QThread, passive UDP)
  report_scheduler_worker.py  # Scheduled report generation worker (QThread)
  dhcp_lease_worker.py     # DHCP lease refresh worker (QThread)
  dns_zone_worker.py       # DNS zone scan worker (QThread)
  threat_intel_worker.py   # Threat intel feed updater worker (QThread)
  rest_api_worker.py       # Local REST API server worker (QThread daemon)
  iface_bw_worker.py       # Interface bandwidth sampler worker (QThread, 1s interval)
```

---

## Adding rogue device signatures

Edit [`offenders.json`](offenders.json) or submit a PR (see [CONTRIBUTING.md](CONTRIBUTING.md)):

```json
{
  "vendor": "Your Device Brand",
  "ouis": ["aa:bb:cc"],
  "known_issues": ["STP BPDU injection — claims Root Bridge via Ethernet"],
  "risk_level": "HIGH",
  "forum_reference": "https://...",
  "remediation": "Disconnect its Ethernet cable and use Wi-Fi backhaul only."
}
```

---

## What's new

### v1.5.1 (current)

**Alert rules opt-in only**
- All 9 built-in alert rules now default to `enabled=False` — no alert fires on a fresh install
- Settings → Notifications has a new **Alert Rules** card with a checkbox per rule and a plain-English description
- Rule enabled states persisted in QSettings; missing key treated as disabled
- Delivery channels (toast, email, webhook, Pushover, ntfy, Telegram) only receive alerts for rules the user has explicitly enabled
- Desktop toast channel also defaults to off

**HomePage fixes**
- Upload speed label changed from clipped `↑ 88 Mbps` to `/ up 88 Mbps` (arrow glyph was clipped on some fonts)
- Scan now and ISP Report buttons now have explicit `setStyleSheet()` calls — no longer render as flat text
- Mode pill gains a visible border (`1px solid`, `border-radius:4px`, `padding:0 8px`) so it reads as a clickable button
- Devices mini-card shows `Run a scan to discover devices` when count is 0; `All healthy` only when count > 0

**Bug fixes**
- `NotificationsPage._rule_checkboxes` initialised before card builders run — fixes `AttributeError` crash on launch
- `_restore()` wrapped in `try/finally` with `_restoring` guard — prevents mid-restore `_save()` calls clobbering QSettings values
- Added `LICENSE` file — fixes WinGet `URL-Validation-Error` on manifest PR

---

### v1.50

**Progressive-disclosure navigation**
- Three sidebar modes cycled by a mode pill: **Home** (5 essentials, no clutter), **Standard** (full feature set under static ALL-CAPS section headers), **Pro** (adds Security Audit items with `·admin` badges)
- Mode persisted to QSettings; restores on next launch
- Section headers are non-interactive dividers — no collapse/expand click targets

**Home page**
- Dedicated landing page shown in Home mode: network grade circle (A–F, colour-coded), three mini-cards (Download speed, Stability/packet-loss, Devices online), recent-alerts strip
- Mini-cards update live from the monitoring cycle: coloured value labels (green/amber/red), sub-line with units, status badge
- Alert strip prepends new alerts as rows (max 3 shown); permanent footer shows when no further alerts occurred in the last 24 h

**First-run action wizard**
- Replaced 4-slide informational walkthrough with a 3-step action wizard
- Step 1 (blue): Scan your network — calls `_start_full_scan()` on the parent dashboard
- Step 2 (amber): Run a speed test — navigates to Speed Test page
- Step 3 (green): See your Network Grade — navigates to Network Grade page
- Each completed step shows a ✓ Done badge; finishing marks first-run done in QSettings

**Speed Test — multi-backend engine**
- 3-tier backend cascade: Ookla CLI binary (1 Gbps+) → speedtest-cli (8 download / 4 upload threads) → pure-Python 16-stream HTTP fallback (no extra deps)
- Ookla CLI auto-detected next to exe, in `%LOCALAPPDATA%\NetSentinel\`, or on PATH; Windows `CREATE_NO_WINDOW`
- `ssl.wrap_socket` shim preserves Python 3.12 compatibility for speedtest-cli 2.1.x

**AppData path hardening**
- `get_app_data_dir()` added to `modules/utils.py` — platform-aware per-user data directory (`%LOCALAPPDATA%\NetSentinel` / `~/Library/Application Support/NetSentinel` / `~/.config/NetSentinel`)
- `MetricStore._default_path()` upgraded to 3-tier strategy — portable → AppData → `~/.config`; no longer crashes with `PermissionError` when installed in `C:\Program Files\`
- Crash log and faulthandler output now write to `get_app_data_dir()` instead of the exe directory

**Windowed-build stability**
- `sys.stderr = None` guard at top of `main()` — redirects to `netsentinel_stderr.log` in AppData instead of `AttributeError` crashing the process

**Sidebar UX**
- 35 mixed emoji replaced with consistent geometric Unicode symbols — icon strip is readable in collapsed (48 px) mode
- Ctrl+F shortcut focuses the sidebar search box from any page; auto-expands collapsed sidebar
- Search box now always visible in collapsed mode with `⌕` placeholder

**WiFi Signal-Strength Heatmap** (Tools section)
- Import any floor plan image (PNG/JPEG/BMP) as a canvas background
- Walk your space clicking where you stand — each click records the current WiFi scan result with per-BSSID dBm values at that spatial position
- IDW (Inverse Distance Weighting) interpolation generates a smooth `RdYlGn` heatmap overlay
- AP selector combo shows all discovered BSSIDs; "All APs" averages across all access points
- Coverage stats card: Excellent / Good / Fair / Weak / Very Weak % breakdown per survey
- Surveys saved as JSON to `%LOCALAPPDATA%\NetSentinel\heatmap_surveys\`; export heatmap as PNG

**Geolocation Map** (Tools section)
- Plots internet-facing IPs on a world map using a local MaxMind GeoLite2-City `.mmdb` database — no API key, no external calls, fully offline
- One-click DB download from `download.maxmind.com` with progress bar; host allowlist enforced (host-validation security fix)
- Colour-coded marker categories: Threat Intel (red), Exposed Services (amber), Manual Entry (blue)
- `set_threat_entries()` method: Threat Intelligence page can push blocklist IPs directly to the map
- Detail panel shows country, city, lat/lon, organisation, and any linked service entries
- Bogon / RFC1918 addresses automatically filtered from map plot

**Custom Trigger Expressions** (Reports & Alerts section)
- Expression language: `avg(rtt["ip"], 5m) > 80`, `loss%["ip"] > 5 AND state["ip"] != "UP"`, `uptime%["ip"] < 95`
- Supported metrics: `rtt`, `loss%`, `jitter`, `state`, `uptime%`; aggregates: `avg`, `max`, `min` with `s`/`m`/`h` windows
- Visual rule builder dialog — name, severity (INFO/WARNING/CRITICAL), expression editor, live plain-English preview label, cooldown, 6 built-in examples
- Test Now button evaluates selected rule against live MetricStore data off-thread
- `evaluate_all()` integrates with dashboard monitoring cycle to fire alerts automatically
- Rules stored as JSON to `%LOCALAPPDATA%\NetSentinel\trigger_rules.json`

**Automation Hooks** (Advanced section)
- Event-driven rules: fire a webhook HTTP POST or execute a local script/command when a network event occurs
- Supported triggers: device-down, high RTT, new device discovered, alert fired
- Rules editor with method (GET/POST), URL, payload template, and per-event-type enable toggles
- Test button fires a rule immediately; execution log with timestamp, status, and response

**Network Documentation** (Advanced section)
- Generates a formatted HTML or Markdown document snapshot of your full network on demand or on schedule
- Covers: device inventory table, service status, open ports, TLS certificate status, topology summary
- Output saved to `%LOCALAPPDATA%\NetSentinel\` or a user-chosen directory; open in browser with one click

**MQTT / Home Assistant Publisher** (Advanced section)
- Publishes device discovery, availability (`online`/`offline`), and metric events to any MQTT broker
- Home Assistant MQTT Discovery payloads auto-formatted for binary_sensor (availability) and sensor (RTT, loss%, jitter) device types
- Configurable broker host/port/topic prefix/QoS; credentials stored in OS keychain (RULE 22-A)
- Connection status indicator; publish log in the UI

**Credentialed Scan — WMI enrichment**
- `_parse_windows()` now captures BIOS serial number via `wmic bios get SerialNumber`
- Active session detection via `query session` output: correctly identifies STATE as last column; filters `Active`/`Conn` states, skips `Disc`
- `CredScanResult.serial_number` and `CredScanResult.active_sessions` fields available to all callers

### v1.4.0

**Navigation restructure**
- Standard section reorganised into 7 named subgroups: Discover, Live Monitor, Threat Detection, Health & History, Diagnostics, Reports & Alerts, Tools
- Threat Detection (Broadcast Storm, Rogue Bridge, IoT Behaviour) promoted to position 3 — no longer buried at the bottom of a flat list
- All corrupted sidebar emoji characters fixed

**Active Connections** (`🔗`)
- Process-to-socket map: every TCP/UDP connection on the machine with PID, executable name, remote IP, geo-location (country/city via ip-api.com), and connection status
- One-click firewall block per process via `netsh advfirewall` — blocked rules panel shows all active NS-Block-* rules with unblock support
- KPI row: Total / Established / External / FW Blocked; 5-second live poll

**Live Bandwidth** (`📶`)
- 60-second rolling dual area chart (Upload + Download Mbps) per network interface
- Interface selector, KPI tiles (current up/down speed, peak up/down), session totals table
- Live Bandwidth tile added to the Overview Dashboard

**Security hardening**
- SMTP email password migrated from QSettings (plaintext INI) to OS keychain via `keyring` — auto-migrates existing stored passwords on first run
- SNMP community string field masked (`EchoMode.Password`) and persisted to OS keychain
- `keyring~=25.0` added to `requirements.txt`

### v1.3.1

**Overview Dashboard**
- Configurable live tile grid on the Overview page: Device Count, Fleet Uptime, Service Status, RTT Summary, TLS Health, Network Grade, Alert Feed, Device Events
- Drag tiles to reorder in Edit Layout mode — layout persists across sessions via QSettings

**Three Colour Themes**
- Arctic Clean (professional light), Midnight Pro (deep charcoal + electric cyan), Obsidian Neon (true black + neon lime)
- All colours enforced through `ui/styles.py` — no hardcoded hex values anywhere in the codebase
- Theme picker in the `⚙` top-bar **App Settings** dialog; applies on next launch

**Settings & Customisation**
- Dedicated App Settings dialog (theme picker, compact-row toggle, tooltip toggle, full keyboard shortcut reference)
- Accessible from the `⚙` top-bar dropdown → **App Settings (Theme & Display)…** — always one click away from any page
- Theme applies on next launch; three choices: Arctic Clean, Midnight Pro, Obsidian Neon

**Help & Reference**
- Opened via `❓` button in the top bar — available from every page without leaving your current context
- Risk Level Guide — colour-coded badge + plain-English meaning for every level (CLEAN → STORM → UNKNOWN)
- Common Scenarios — "I want to…" lookup table mapping 12 user goals to the correct feature
- Glossary — 24 networking terms defined in plain English (ARP, BPDU, CGNAT, CVE, mDNS, STP, TLS, etc.)

**First-run onboarding**
- 4-slide welcome dialog shown once on first launch — explains Standard / Advanced / Security Audit sections, directs to the `⚙` top-bar menu for customisation
- "Don't show again" checkbox persisted to QSettings

**Notification Routing Rules**
- Per-channel delivery rules for Toast, Webhook (HTTP/S POST), and Email (SMTP) notifications
- Each channel has an `enabled` toggle, minimum severity filter (`INFO` → `CRITICAL`), and rule-type allowlist
- Delivery log with timestamp, channel, severity, and message — configurable max entries; exportable
- Settings persisted to QSettings; passwords never serialised to disk
- "Test" button for Webhook and Email to verify connectivity immediately

**Config Baseline Snapshots**
- Point-in-time snapshots of the full device fleet — IP, hostname, MAC, open ports, OS, SNMP fields
- Compare any two snapshots to produce a structured diff: added/removed devices, port changes, field changes, SNMP drift
- Diff table with colour-coded rows (green = added, red = removed, amber = changed)
- Snapshots stored in MetricStore (schema v4 `config_snapshot` table); labelled and timestamped

**Predictive Trend Alerting**
- Ordinary-least-squares linear regression over stored RTT/loss/jitter time-series data (stdlib only — no numpy)
- Per-metric results: current value, mean, slope/hour, R², ETA to threshold, severity (CLEAN / WARNING / CRITICAL)
- Configurable window (6 h – 7 d); reports sorted CRITICAL → CLEAN then by ETA
- Full trend results table with ETA column colour-coded by severity

**Maintenance Windows**
- Define scheduled or ad-hoc maintenance periods (label, host list, start/end time, active toggle)
- Empty host list = suppress all-host alerts; specific hosts listed = suppress only those
- All alerts for suppressed hosts are silently dropped by AlertEngine before cooldown evaluation
- Suppression log: timestamp, window label, host, rule name, severity, message
- Persisted to QSettings (JSON); purge-expired helper removes windows older than N days
- Auto-refresh every 60 s; three KPI tiles (Active / Scheduled / Suppressed this session)

**Version consistency enforcement**
- `tests/test_version_consistency.py` — 6 automated tests that compare every version-bearing file against `app.py`; version drift in `cli.py`, `apm.yml`, `debug_launch.py`, `installer.iss`, `build.bat`, or `build.sh` now fails the test suite immediately

**CI/CD & reliability fixes**
- winget submission moved into `release.yml` as a final `submit-winget` job with `needs: [release]`
- Winget can no longer trigger on a failed build — the separate `winget-submit.yml` has been removed
- Update-available bar now uses strict semver tuple comparison (`_ver(latest) > _ver(current)`) — no longer fires falsely when a dev build is ahead of the latest GitHub release
- 988 automated tests

### v1.2.0

**UI & navigation**
- Collapsible sidebar sections (Standard / Advanced / Security Audit) with ▼/▶ toggle and icon-only collapse mode
- Sub-groups within sections: Network Health, Traffic & Behaviour, Deep Analysis
- Sidebar search/filter bar — type to narrow nav items instantly
- Slim 42px top bar: brand | search | verdict | Run Scan | Export | ⚙ settings dropdown
- KPI summary bar height reduced; sidebar section headers ALL CAPS enterprise style
- App icon now appears correctly in taskbar, title bar, and desktop shortcut

**Persistent monitoring (new)**
- **Availability History page** — persistent RTT & UP/DEGRADED/DOWN state charts with 1h / 12h / 24h / 7d zoom
- **Background availability monitor** — records every device's state to a local SQLite database every 60 s automatically on launch
- **MetricStore** — local SQLite time-series database stores RTT samples, device state history, and state-change events across sessions
- **New/disappeared device detection** — each scan automatically diffs against the persistent known-device inventory; new MACs and gone devices trigger status-bar alerts and are logged as JOINED/LEFT events
- **Threshold alerting engine** — configurable rules fire on high RTT, host down, host degraded, packet loss, new device, or device gone; cooldown prevents duplicate alerts; desktop toast via system tray when available
- **Inventory change history page** — log of every JOINED/LEFT/UP/DOWN/DEGRADED/RECOVERED event with filter checkboxes and 1h…30d zoom windows
- **TLS certificate monitor** — hourly cert checks per host; expiry badges (OK / EXPIRING / EXPIRED / UNREACHABLE); alerts fire when a cert has fewer than 30 days remaining or has expired; results persisted to MetricStore
- **Flap/oscillation detection** — AlertEngine tracks state-transition history per host; fires `FLAP` alert when a host oscillates UP↔DOWN/DEGRADED too rapidly (configurable count + time window); HOST_DOWN alerts automatically suppressed while a host is classified as flapping
- **Uptime & SLA page** — per-device uptime % for 24h / 7d / 30d; fleet average, best/worst device KPI tiles; colour-coded rows (green ≥99%, amber ≥95%, red <95%); auto-refreshes on each availability cycle
- **Service heartbeat monitor** — TCP port reachability checks every 60 s per service; SERVICE_DOWN alert rule with cooldown; `ServiceCheckPoint` history in MetricStore (schema v3); dedicated "Service Heartbeat" page with KPI tiles and RTT column
- **Auto-report generation** — scheduled HTML status reports (configurable interval + output directory); covers device uptime, TLS certs, services, and device events; "Generate Now" button; pruning to keep last N reports
- **SNMP trap receiver** — passive UDP listener (port 162) for SNMPv1 and SNMPv2c traps; stdlib-only BER/ASN.1 decoder; live trap table with KPI tiles and varbind detail dialog; falls back to port 16200 when not admin

**Other improvements**
- Auto update check on startup — blue notification bar if a newer version is available
- Linux `.desktop` file + `install-linux.sh` included in Linux builds
- Enterprise design system enforced: single colour source (`ui/styles.py`), no hardcoded hex values anywhere
- APM instruction files encode architecture rules and AI agent constraints
- Winget distribution: `winget install NetSentinel.NetSentinel`
- **Syslog receiver** — passive UDP/514 listener for RFC 3164 and RFC 5424 syslog from routers, switches, and Linux hosts; severity/facility decoding; live table with severity colour-coding, text + severity filter, double-click detail dialog; falls back to port 5140 when not admin

### v1.0.4
- **Network Grade (A–F)** — benchmark tab scoring 8 health dimensions; per-dimension grade, verdict, and fix tip
- **ISP Accountability Report** — exports MTR hop table, outage log, grade, and metrics as a standalone HTML file for ISP support escalation
- **How to Fix context menus** — right-click any device, rogue bridge, or storm source for numbered remediation steps
- **Root Cause Analysis tab** — cross-correlates STP, Storm, Diagnostics, and Logger findings; identifies ISP vs local fault
- **IoT Behavioural Baseline tab** — learns normal IoT device traffic; alerts on SYN scanning, new destinations, rate spikes
- **Device name registry** — curated OUI/model database: Google Nest, TP-Link Deco, Apple, Amazon Echo/Ring, Samsung, Netgear, Asus; multi-method resolver (mDNS, NetBIOS, SNMP, DHCP)
- **Visual Diagnostic Overlay grade colour** — green (A/B), amber (C), red (D/F) — Ctrl+Shift+M
- **Windows installer** — Inno Setup `.exe` with Start Menu shortcuts and PATH registration

### v1.0.3
- Microsoft Store compliance display-string updates; 88 pytest test suite; CONTRIBUTING.md

### v1.0.2
- Topology map widget; per-device bandwidth monitor

### v1.0.1
- Full-scan stability fix; Scapy process isolation; crash logging via faulthandler

### v1.0.0
- IPv6 subnet scan; cloud metadata detection; logger RTT chart PNG export

---

## Privacy

No telemetry. No cloud. No accounts. All scanning and analysis runs on your machine.

The only external endpoints contacted are ones **you explicitly trigger**:

| Endpoint | Purpose |
|---|---|
| `speed.cloudflare.com` | Download speed test |
| `connectivitycheck.gstatic.com` | HTTP connectivity check (logger, off by default) |
| `bash.ws` | DNS leak test |
| `services.nvd.nist.gov` | CVE lookup (Security Audit Mode, on demand) |

---

## Author

[**Ossian Ericson**](https://github.com/ossianericson) — [github.com/ossianericson](https://github.com/ossianericson)

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).