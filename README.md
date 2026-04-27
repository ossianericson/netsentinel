# NetSentinel

> **Privacy-First Network Health Monitor & ISP Accountability Tool**  
> Diagnose connectivity faults · Prove ISP outages with timestamped evidence · Find every device on your network — all analysis runs locally, nothing leaves your machine.

![CI](https://github.com/ossianericson/netsentinel/actions/workflows/release.yml/badge.svg)

<!-- Screenshot or GIF here — shows the main dashboard on first launch -->

---

## Install

### Windows — one command
```powershell
winget install NetSentinel.NetSentinel
```
Or download the installer from the latest release:

### 👉 [Latest Release](https://github.com/ossianericson/netsentinel/releases/latest) — v1.0.4

| OS | File | How to run |
|---|---|---|
| **Windows** | `NetSentinel-Setup.exe` | Run installer, then right-click shortcut → **Run as Administrator** |
| **Windows** | `NetSentinel.exe` *(portable)* | Right-click → **Run as Administrator** |
| **macOS** | `NetSentinel-macOS.zip` | Unzip → right-click app → **Open** (first launch bypasses Gatekeeper) |
| **Linux** | `NetSentinel` | `chmod +x NetSentinel && sudo ./NetSentinel` |

> **Rogue Bridge (STP) & Broadcast Storm tabs** require [Npcap](https://npcap.com) (free, one-click installer) on Windows.

### First run on Windows — unblock the downloaded file

Windows marks files downloaded from the internet as blocked. Unblock before running.

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
- **Runs 100% locally** — no cloud account, no telemetry, no data sent anywhere

---

## Key features

### Standard tabs (no admin required)

| Tab | What it tells you |
|---|---|
| 🔍 **Devices on Network** | Every device on your subnet — IP, hostname, MAC, vendor, **device model** (e.g. "Google Nest Audio", "TP-Link Deco M5"), device type, and risk level. Right-click any device for a **🔧 How to Fix** guide. |
| 🌉 **Rogue Bridge (STP)** | Catches the hidden cause of 15–45 s periodic drop cycles: a mesh node or unmanaged switch claiming to be the network Root Bridge. Right-click any rogue entry for step-by-step disconnect instructions. |
| 🌊 **Broadcast Storm** | Measures broadcast/multicast flood levels that silently choke bandwidth. Right-click any storm source for remediation steps. |
| 📶 **WiFi Networks** | Hidden SSIDs, rogue access points, co-channel interference, WPS-enabled networks, connected client list. |
| 📡 **DNS & Outages** | Live ping + DNS latency graph. Identifies STP reconvergence signatures and DNS hijacking patterns in real time. |
| 🌐 **My Network Info** | Full snapshot: local IPs, subnet, gateway, DNS servers, DHCP lease, adapter speeds, WiFi signal. One-click OS settings shortcuts and router admin links. |
| ⚡ **Health Check** | On-demand diagnostics: ping to 5 targets, DNS speed comparison (System / Cloudflare / Google / Quad9), HTTP check, DNS leak test, public IP, download speed test, traceroute. |
| 📋 **Stability Log** | Runs unattended for hours or days. Timestamped CSV log of every ping, outage, DNS latency, and ARP change. Load any past log for automated plain-English analysis. Evidence-grade output for ISP disputes. |
| 📊 **Network Grade** | **A–F benchmark** across 8 dimensions compared to a "Perfect Home Network" baseline. Includes **📤 Generate ISP Report** — exports an HTML document for support tickets. |
| 🧩 **Root Cause Analysis** | Cross-correlates STP, Storm, Diagnostics, and Logger data. Automatically distinguishes a local network fault from an ISP infrastructure problem. |
| 🤖 **IoT Behaviour** | Learns normal traffic for each IoT device (cameras, smart speakers, TVs). Alerts when a device starts contacting new servers, scanning ports, or flooding traffic. |
| 🔷 **IPv6 Devices** | Link-local segment sweep — reads OS neighbour cache and pings every `fe80::/10` address. |

### Advanced Mode tabs

| Tab | What it gives you |
|---|---|
| 🔁 **Hop-by-Hop Trace (MTR)** | Continuous traceroute — live per-hop loss %, avg RTT, last RTT, updating every cycle. |
| 🔧 **Tools & Wake-on-LAN** | TCP port scanner (Fast/Normal/Low Impact), service version detection, banner grab, Wake-on-LAN magic packet sender, new-device baseline diff alert. |
| 🗺 **Network Map** | Visual topology diagram of your network. |
| 👁 **ARP Spoof Watch** | Detects ARP poisoning and MITM attacks. |
| 📜 **DHCP Leases** | Detects rogue DHCP servers. |
| 📊 **Bandwidth Usage** | Per-device rx/tx bps monitor using live packet capture. |
| ⏱ **Scheduled Scans** | Automated scans every N minutes with desktop notifications on new or changed devices. |
| 📟 **SNMP Device Info** | Polls basic SNMP OIDs — no extra dependencies. |

### Security Audit Mode tabs (for IT professionals)

Port Scan (SYN) · Port Scan (UDP) · OS Detection · Device Risk Score · Known CVEs · Exposed to Internet · Login Test (SSH/SMB) · Full Device Discovery · Windows Shares (SMB) · Plugin Modules · Private Endpoint Check · Cloud Metadata Probe

---

## ISP Accountability Report

The **📤 Generate ISP Report** button in the Network Grade tab exports a self-contained HTML file designed for ISP support tickets.

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
| Connection Uptime | ≥ 99.5 % |
| Average Latency | ≤ 20 ms |
| Jitter (Call Quality) | ≤ 5 ms |
| DNS Response Speed | ≤ 30 ms |
| Download Speed | ≥ 25 Mbps |
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
offenders.json              # MAC OUI risk database (200+ entries)
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
  mac_registry.py           # Curated OUI→model registry (Google, TP-Link, Apple, Amazon …)
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

ui/
  dashboard.py              # Main window — sidebar nav (Standard / Advanced / Security Audit)
  topology_widget.py        # Network topology map widget
  matrix_rain.py            # Visual Diagnostic Overlay (Ctrl+Shift+M) — colour = network grade
  live_graph.py             # Real-time latency graph
  styles.py                 # Dark theme QSS

workers/
  scan_worker.py            # QThread workers (28 total)
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

### v1.0.4 (current)
- **Network Grade (A–F)** — benchmark tab scoring 8 health dimensions; per-dimension grade, verdict, and fix tip
- **ISP Accountability Report** — 📤 exports MTR hop table, outage log, grade, and metrics as a standalone HTML file for ISP support escalation
- **How to Fix context menus** — right-click any device, rogue bridge, or storm source for numbered remediation steps
- **Root Cause Analysis tab** — cross-correlates STP, Storm, Diagnostics, and Logger findings; identifies ISP vs local fault
- **IoT Behavioural Baseline tab** — learns normal IoT device traffic; alerts on SYN scanning, new destinations, rate spikes
- **Device name registry** — curated OUI→model database: Google Nest, TP-Link Deco, Apple, Amazon Echo/Ring, Samsung, Netgear, Asus; multi-method resolver (mDNS, NetBIOS, SNMP, DHCP)
- **Visual Diagnostic Overlay grade colour** — green (A/B), amber (C), red (D/F) — Ctrl+Shift+M
- **winget distribution** — `winget install NetSentinel.NetSentinel`
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

ui/
  dashboard.py              # Main window — sidebar nav (Standard / Advanced / Security Audit)
  topology_widget.py        # Network topology map widget
  matrix_rain.py            # Visual Diagnostic Overlay (Ctrl+Shift+M) — colour = network grade
  live_graph.py             # Real-time latency graph
  styles.py                 # Dark theme QSS

workers/
  scan_worker.py            # QThread workers (28 total)
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

### v1.0.4 (current)
- **Network Grade (A–F)** — benchmark tab scoring 8 health dimensions against a calibrated baseline; per-dimension grade, verdict, and fix tip
- **ISP Accountability Report** — 📤 exports MTR hop table, outage log, grade, and metrics as a standalone HTML file for ISP support escalation
- **How to Fix context menus** — right-click any device, rogue bridge, or storm source for numbered remediation steps
- **Root Cause Analysis tab** — cross-correlates STP, Storm, Diagnostics, and Logger findings; identifies ISP vs local fault
- **IoT Behavioural Baseline tab** — learns normal IoT device traffic and alerts on deviations (port scanning, new destinations, rate spikes)
- **Device name registry** — curated OUI→model database: Google Nest, TP-Link Deco, Apple, Amazon Echo/Ring, Samsung, Netgear, Asus; multi-method resolver (mDNS, NetBIOS, SNMP, DHCP)
- **Visual Diagnostic Overlay grade colour** — green (A/B), amber (C), red (D/F) — Ctrl+Shift+M
- **winget distribution** — `winget install NetSentinel.NetSentinel`
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

