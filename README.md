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

### 👉 [Latest Release](https://github.com/ossianericson/netsentinel/releases/latest) — v1.3.1

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
## How it was built

**Sunday, 26 April 2026. 12:30 PM. After lunch.**

Not "prototyped". Not "scaffolded". Built — from a blank folder to a cross-platform, multi-mode network security tool with a full CI/CD pipeline, three executable targets, and automated GitHub Releases for Windows, macOS, and Linux.

Here is the commit log. Every timestamp is real.

| Time | What shipped |
|---|---|
| **12:58** | First commit — `Layer2 Ghost Hunter v1.0.0`. ARP scan, basic risk flagging. |
| **13:08** | GitHub Actions release workflow. Tag → executable → release. Done before the first feature worked end-to-end. |
| **14:15** | Hostname resolution, MAC OUI fingerprinting (200+ vendors), IPv6 rogue router detection, gateway exclusion. |
| **16:02** | Full rebrand to NetSentinel. v2.0.0. Overhauled UI, new tabs. |
| **17:18** | CVE lookup (NVD API v2), Nmap XML export, Internet Exposure scanner, persistent settings, Matrix rain Easter egg. |
| **18:12** | Natural language query engine, scan politeness levels, WPS detection, plugin system, sidebar navigation. |
| **19:49** | v1.0.0 tag. IPv6 full scan, cloud metadata detection (AWS/Azure/GCP), logger RTT chart renderer, CLI (`cli.py`), Windows service (`svc.py`). |
| **20:35** | Bug fix: hard crash at ~240/254 hosts — race condition on ping-sweep counter + Windows handle exhaustion. Fixed with a threading lock and `max_workers=32`. |
| **21:22** | Bug fix: missing `_on_bpdu_found` slot; harden storm fallback. |
| **21:28–21:38** | CI fixes: artifact overwrite, CLI + service builds. |
| **22:11** | Final runtime bugs: topology widget crash, bandwidth monitor crash, About dialog version. Shipped as v1.0.2. |
| **22:50** | 88 behavioural pytest tests, CONTRIBUTING.md, credential docs. Shipped as v1.0.3. |

**9 hours and 52 minutes. 21 commits. Three executable targets. Three operating systems. A full test suite.**

The tool exists because a problem is real — consumer mesh nodes silently winning STP Root Bridge elections, causing the exact intermittent drops every ISP helpdesk blames on WiFi. No single existing tool exposed this to a non-expert. So one was built.

The commit history is public. The timestamps don't lie.

---
## Key features

### Standard tabs (no admin required)

| Tab | What it tells you |
|---|---|
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
### UI & Customisation

| Feature | Details |
|---|---|
| 🎨 **Three Colour Themes** | Arctic Clean (professional light), Midnight Pro (deep charcoal + electric cyan), Obsidian Neon (true black + neon lime). Click **⚙** in the top bar → **App Settings (Theme & Display)…**; takes effect on next launch. |
| ❓ **Help & Reference** | Click **❓** in the top bar to open Help from any page. Contains Risk Level Guide (CLEAN→STORM), Common Scenarios lookup table, and a 24-term networking glossary. |
| 👋 **First-Run Onboarding** | 4-slide welcome dialog on first launch. Explains Standard / Advanced / Security Audit sections and directs new users to App Settings. “Don’t show again” persisted to QSettings. |

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

### Security Audit Mode tabs (for IT professionals)

| Tab | What it gives you |
|---|---|
| 🔒 **TLS Certificates** | Per-host certificate expiry monitoring. Hourly checks. Badges: OK / EXPIRING (< 30 days) / EXPIRED / UNREACHABLE. Alerts fire automatically; results persisted to MetricStore. |
| 🔎 **Port Scan (SYN)** | Raw SYN scanner via Scapy — stealth half-open scan, faster than TCP connect. Requires admin. |
| 🔎 **Port Scan (UDP)** | UDP port scanner. Identifies DNS, SNMP, NTP, mDNS and other UDP services. Requires admin. |
| 💻 **OS Detection** | OS fingerprinting via TTL + banner grab + TCP SYN probe. |
| ⚠ **Device Risk Score** | Numeric risk score per device based on open ports, OUI flags, OS, and exposure. |
| 🛡 **Known CVEs** | NVD API v2 CVE lookup for detected OS/service versions. Rate-limited; offline-safe. |
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

```bash
# Windows — builds GUI + CLI + Windows service
build.bat

# macOS / Linux — builds GUI + CLI
chmod +x build.sh && ./build.sh
```

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
    notifications_page.py   # Notification routing rules — Toast / Webhook / Email channels + delivery log
    baseline_page.py        # Config Baseline Snapshots — take, compare, diff viewer
    trend_page.py           # Predictive Trend Forecasts — OLS regression results table
    maintenance_page.py     # Maintenance Windows — schedule, manage, suppression log

workers/
  scan_worker.py            # QThread workers (28 total)
  availability_worker.py    # Background device availability monitor (QThread, 60 s interval)
  cert_worker.py            # TLS cert check worker (QThread, hourly)
  service_worker.py         # Service heartbeat worker (QThread, 60 s interval)
  snmp_trap_worker.py       # SNMP trap listener worker (QThread, passive UDP)
  syslog_worker.py          # Syslog listener worker (QThread, passive UDP)
  report_scheduler_worker.py  # Scheduled report generation worker (QThread)
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

### v1.3.1 (current)

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