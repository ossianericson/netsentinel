# NetSentinel

> **Network Security Scanner & Connectivity Monitor**  
> Detect rogue devices · Diagnose faults · Monitor uptime · Explore your full network — all offline, all in plain English.

Built by **Ossian Ericson** · [linkedin.com/in/ossian-ericson](https://www.linkedin.com/in/ossian-ericson/)

> NetSentinel was built in one afternoon using Claude Sonnet 4.6 as a development accelerator. The architecture, the module boundaries, the isolation decisions, the crash diagnosis — that's the work. The model handled the typing.
>
> That distinction matters. I wrote about it here:  
> [The Spec Is the Product. The Model Is Scaffolding.](https://medium.com/@ossian.ericson/the-spec-is-the-product-the-model-is-scaffolding-a78029c0062b) — *March 2026*

---

## Legal & Authorized Use

> **This tool is intended for use on networks and systems you own or have explicit written authorization to test.**
>
> Scanning, probing, or monitoring networks without authorization may violate the Computer Fraud and Abuse Act (CFAA), the UK Computer Misuse Act, the EU NIS2 Directive, and equivalent laws in your jurisdiction. The author accepts no liability for unlawful use.
>
> NetSentinel is designed for home network troubleshooting, authorized network administration, and security auditing of infrastructure you are responsible for.

---

## Download & Run — no Python, no setup

### 👉 [Latest Release](https://github.com/ossianericson/netsentinel/releases/latest) — v1.0.3-2

| OS | File | How to run |
|---|---|---|
| **Windows** | `NetSentinel.exe` | Right-click → **Run as Administrator** for full scan. |
| **macOS** | `NetSentinel-macOS.zip` | Unzip → right-click the app → **Open** (first launch bypasses Gatekeeper). |
| **Linux** | `NetSentinel` | `chmod +x NetSentinel && sudo ./NetSentinel` |

> **Windows — STP & Storm tabs** need [Npcap](https://npcap.com) (free, one-click installer).

### First run on Windows — unblock the downloaded file

Windows marks files downloaded from the internet as blocked. You must unblock before the exe will run properly.

**Option A — PowerShell (fastest):**
```powershell
Unblock-File -Path "$env:USERPROFILE\Downloads\NetSentinel.exe"
```
Then right-click → **Run as Administrator**.

**Option B — Explorer (no terminal needed):**
1. Right-click `NetSentinel.exe` → **Properties**
2. At the bottom of the General tab, tick **Unblock**
3. Click **OK**, then right-click → **Run as Administrator**

**SmartScreen warning ("Windows protected your PC")?**  
Click **More info** → **Run anyway**. This appears because the exe is not yet code-signed.  
You can verify the file is safe by checking its SHA-256 hash against the release page.

---

## What it does

NetSentinel is a desktop network troubleshooting suite. One tool that replaces a drawer full of separate utilities.

| Tab | What it gives you |
|---|---|
| 🔍 **Device Fingerprinter** | Full subnet scan — every device by IP, hostname, MAC, vendor, **device type** (IP Camera, NAS, Smart TV, Domain Controller, etc.), and risk level. Flags rogue routers using IPv6 RA snooping and a 115+ entry OUI database. |
| 🌉 **STP / BPDU Detector** | Catches devices claiming to be the network Root Bridge — the hidden cause of 15–45 s periodic drop cycles in homes with mesh nodes or managed switches. |
| 🌊 **Storm Analyser** | Measures broadcast/multicast flood levels that silently choke available bandwidth. |
| 📶 **WiFi Scanner** | Finds hidden SSIDs, rogue access points, co-channel interference, **WPS-enabled networks** (PIN brute-force risk), and connected client list across 2.4 GHz and 5 GHz. |
| 📡 **DNS Correlator** | Live ping + DNS latency graph. Identifies STP reconvergence signatures and DNS hijacking patterns. |
| 🌐 **Network Info** | Full network snapshot: local IPs, subnet masks, gateway, DNS servers, DHCP lease details, adapter speeds, WiFi SSID, signal strength, and one-click OS settings shortcuts + router admin links. |
| ⚡ **Diagnostics** | On-demand health check: ping to 5 targets, DNS speed (System / Cloudflare / Google / Quad9), HTTP connectivity, DNS leak test, public IP, ~2 MB download speed test, traceroute (15 hops). |
| 📋 **Network Logger** | Runs unattended for hours or days. Pings your targets on a configurable interval, logs every result to CSV, detects and summarises outages. Optional per-cycle extras: jitter, DNS latency, HTTP check, ARP change watch. Loads any past log with full automated plain-English diagnosis. **Render any log as a PNG chart** without opening the GUI. |
| 🔷 **IPv6 Devices** | Link-local segment sweep — reads the OS neighbour cache, then actively pings every interface's `fe80::/10` range. Shows every IPv6 device with address, MAC, state, and discovery source. |
| 🔁 **MTR** *(Advanced Mode)* | Continuous hop-by-hop traceroute — live per-hop loss %, avg RTT, and last RTT, updating every cycle until you stop it. |
| 🔧 **Advanced Tools** *(Advanced Mode)* | TCP port scanner with **Fast / Normal / Stealth** mode dial, protocol-aware service version detection, banner grab, HIGH-risk flags, Wake-on-LAN magic packet sender, and new-device baseline diff alert card. |
| ☁ **Cloud Metadata** *(Recon Mode)* | Detects whether this machine is running inside AWS, Azure, or GCP. Probes IMDSv1/v2, Azure IMDS, and GCP metadata; flags unsafe IMDSv1 access and network devices acting as SSRF metadata proxies. |

A colour-coded verdict (🟢 / 🟡 / 🔴) with a plain-English explanation is always visible.

---

## Why this exists

Diagnosing a home or small-office network problem today means opening five different tools — a terminal for `ping` and `traceroute`, a browser for the router admin page, `netsh` or `ip` for adapter info, a separate WiFi analyser app, and maybe Wireshark if you're brave enough. None of them talk to each other. None give a verdict. And none of them run quietly in the background proving to your ISP that you actually had 14 outages last Tuesday.

Meanwhile, consumer mesh routers, smart speakers, and 5G modems now silently participate in **enterprise protocols** — STP, IPv6 RA, mDNS — with zero user-visible indication. A Google Nest Point connected via Ethernet can win the STP Root Bridge election and force your real router to block its own uplink port every 2 seconds. The result: the exact intermittent drops and DNS failures that every ISP helpdesk will blame on "WiFi interference."

NetSentinel puts everything in one place:
- **See** every device on your network with vendor, risk level, and plain-English verdict
- **Prove** outages with timestamped CSV logs you can hand to your ISP
- **Find** the Layer-2 culprit — rogue root bridges, broadcast storms, hidden SSIDs
- **Measure** DNS speed, download throughput, and traceroute hops on demand
- **Monitor** adapter health, DHCP lease state, and WiFi signal without opening the OS settings maze
- **Watch** your network overnight — jitter, DNS latency, ARP changes — without any other tool running

---

## Key features in depth

### Pre-scan cache flush
Before every scan, NetSentinel automatically:
1. Flushes DNS resolver cache (`ipconfig /flushdns` / `dscacheutil -flushcache` / `resolvectl`)
2. Clears the ARP table (`arp -d *`)
3. Clears IPv6 neighbour cache
4. Concurrently pings all 254 hosts in your /24 to repopulate ARP with live devices

Result: the scan shows **what is on your network right now**, not what was there six hours ago.

### Rogue device detection — false-positive safe
- OUI database of 115+ OUI prefixes across 8 vendor groups with known Layer-2 misbehaviours
- IPv6 Router Advertisement snooping catches rogue routers even with unknown MACs
- **Mesh satellite nodes** (TP-Link Deco, Google Nest, Eero, etc.) are rated by their vendor risk level and are **not** additionally escalated just because they send normal mesh RA frames

### Network Info tab
- **Adapter table:** name, type (Wi-Fi / Ethernet), MAC, IPv4, link speed, WiFi signal %
- **DHCP lease:** server IP, lease obtained, lease expires, duration in hours
- **OS shortcuts:** one-click buttons to open Windows Settings deep-links (Wi-Fi, Ethernet, VPN, Firewall) directly
- **Router admin links:** auto-derived from your gateway IP, three URL variants
- **Device list:** full scan results shown in one place after fingerprint scan

### Background Network Logger

Start the logger, leave the app running. Each cycle it can optionally measure:

| Option | What it adds | Overhead |
|---|---|---|
| *(base)* | Ping RTT + pass/slow/fail per target | minimal |
| **Jitter** | 3× pings per host, standard deviation | ~3× ping time |
| **DNS latency** | System resolver round-trip once per cycle | ~50 ms |
| **HTTP check** | GET `/generate_204` captive portal detect | ~100–300 ms |
| **ARP watch** | Snapshot ARP table, alert on new/changed MACs | ~100 ms |

All options are **off by default** — enable only what you need for long unattended runs.

CSV format (base):
```
timestamp,host,rtt_ms,status
2026-04-26T14:32:01,8.8.8.8,12.4,OK
2026-04-26T14:33:01,8.8.8.8,-1,FAIL
```

With all options enabled:
```
timestamp,host,rtt_ms,status,jitter_ms,dns_ms,http_status,http_ms,arp_event
2026-04-26T14:32:01,8.8.8.8,12.4,OK,1.2,18.3,204,87.1,
2026-04-26T14:33:01,8.8.8.8,-1,FAIL,,,,, NEW 192.168.1.44=aa:bb:cc:dd:ee:ff
```

Logs are saved to `~/Documents/NetSentinel/logs/netlog_YYYYMMDD_HHMMSS.csv`.

Load any past log to see: total pings, uptime %, average RTT, average jitter, average DNS latency, every outage (start/end/duration/consecutive fails), and any ARP change events.

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
# Windows — builds all three: GUI + CLI + Windows service
build.bat

# macOS / Linux — builds GUI + CLI (service is Windows-only)
chmod +x build.sh && ./build.sh
```

**Selective builds:**
```bat
build.bat --gui   :: GUI only
build.bat --cli   :: CLI only
build.bat --svc   :: Windows service only
build.bat --debug :: debug GUI build (console window)
```
```bash
./build.sh --gui  # GUI only
./build.sh --cli  # CLI only
./build.sh --debug
```

**Windows service pre-requisite** — install pywin32 before running `build.bat` or `build.bat --svc`:
```powershell
pip install pywin32
python -m pywin32_postinstall -install   # run as Administrator, once
```
If pywin32 is not installed, `build.bat` will skip the service build with a notice and complete the rest normally.

Output:
| Executable | Platform | Description |
|---|---|---|
| `dist/NetSentinel.exe` | Windows | Full GUI application |
| `dist/NetSentinel-cli.exe` | Windows | CLI — no GUI stack, ~80% smaller |
| `dist/NetSentinel-svc.exe` | Windows | Windows service installer |
| `dist/NetSentinel` | Linux/macOS | Full GUI application |
| `dist/NetSentinel-cli` | Linux/macOS | CLI |

---

## CLI — headless mode

All core features are available without a display via `cli.py`.
No QApplication, no display server, no Npcap required (except for Recon-mode scans).

```bash
# Device fingerprint scan — save HTML report
python cli.py scan --format html --output report.html

# Scan a specific CIDR and export JSON (CI-friendly: exit 2 if HIGH-RISK devices found)
python cli.py scan --cidr 10.0.0.0/24 --format json --output devices.json

# Run full diagnostics and print to stdout
python cli.py diagnose

# Start background ping logger with DNS and ARP watch (Ctrl+C to stop)
python cli.py log --interval 30 --targets 8.8.8.8 1.1.1.1 --dns --arp

# TCP port scan a host
python cli.py ports 192.168.1.1 --mode fast

# Check private endpoint reachability (DNS / TCP / TLS)
python cli.py check-endpoints api.myapp.azurewebsites.net:443:MyAPI db.internal:5432:DB

# Detect if this machine is running inside a cloud VM (AWS/Azure/GCP)
python cli.py cloud-metadata

# IPv6 link-local sweep during a device scan
python cli.py scan --ipv6

# Render a log CSV as a PNG RTT chart
python cli.py log-chart ~/Documents/NetSentinel/logs/netlog_20260426_120000.csv

# Render and open an interactive window
python cli.py log-chart netlog.csv --show

# Save to a specific path
python cli.py log-chart netlog.csv --output /tmp/report.png
```

**Exit codes (scan command):** `0` = OK, `1` = error, `2` = HIGH-RISK devices found

All commands accept `-q` (quiet — no progress) and `-v` (verbose — per-device detail).  
Run `python cli.py <command> --help` for full option reference.

---

## Windows Service — background logger

Install `svc.py` as a Windows service to log connectivity 24/7 — even with no user logged in.

**Prerequisites (run as Administrator):**
```powershell
pip install pywin32
python -m pywin32_postinstall -install
```

**Install and start:**
```powershell
python svc.py install   # installs; auto-starts at boot
python svc.py start     # start now
```

**Other commands:**
```powershell
python svc.py stop      # stop the service
python svc.py restart   # restart
python svc.py remove    # uninstall
python svc.py status    # show RUNNING / STOPPED (no admin required)
python svc.py debug     # run in the foreground — Ctrl+C to stop
```

**Config file** (created automatically on first run):
```
%PROGRAMDATA%\NetSentinel\netsentinel-svc.ini
```

```ini
[logger]
interval_s        = 60
targets           = 8.8.8.8, 1.1.1.1, google.com
slow_threshold_ms = 150
enable_jitter     = false
enable_dns        = true
enable_http       = false
enable_arp        = true
```

**Log files** rotate daily:
```
%PROGRAMDATA%\NetSentinel\logs\netlog_YYYYMMDD.csv
```

Logs are in the same CSV format as the GUI Network Logger — load them in the GUI's *Load log* dialog for automated plain-English diagnosis.

---

## Project structure

```
app.py                      # Entry point (v1.0.3) — GUI launcher + --smoke + --headless
cli.py                      # Headless CLI — scan / diagnose / log / ports / check-endpoints / cloud-metadata / log-chart
svc.py                      # Windows Service — installs NetworkLogger as a background service
offenders.json              # MAC OUI database — 200+ known rogue device vendors
requirements.txt
NetSentinel.spec            # PyInstaller spec — GUI executable
NetSentinelCLI.spec         # PyInstaller spec — CLI executable (no GUI stack, ~80% smaller)
NetSentinelSvc.spec         # PyInstaller spec — Windows service executable (Windows only)
build.bat / build.sh        # Build scripts — build all three executables in one step

modules/
  rogue_device.py           # Module 1 — ARP scan, OUI fingerprinting, IPv6 RA snooping
  stp_detector.py           # Module 2 — STP/BPDU capture (requires Npcap / admin)
  storm_analyser.py         # Module 3 — Broadcast storm detection
  wifi_scanner.py           # Module 4 — Hidden SSID, rogue AP, co-channel interference
  dns_correlator.py         # Module 5 — Live ping + DNS latency correlator
  network_diagnostics.py    # Module 6 — On-demand diagnostics, speed test, traceroute
  network_logger.py         # Module 7 — Long-term background ping logger (CSV) + automated log analysis
  port_scanner.py           # Module 8 — TCP connect port scanner, service version probes, Fast/Normal/Stealth modes
  device_classifier.py      # Device-type classifier (IP Camera, NAS, Smart TV, Router, etc.)
  risk_scorer.py            # Per-device risk scorer: numeric score, severity, findings, remediation
  os_fingerprint.py         # Two-tier OS fingerprinting: TTL+banner (no admin) + TCP stack SYN probe (admin+Scapy)
  syn_scanner.py            # SYN stealth scanner + UDP scanner (Scapy, requires admin + Npcap)
  cve_lookup.py             # NVD API v2 CVE lookup — rate-limited, in-memory cache, offline-safe
  internet_exposure.py      # WAN IP + CGNAT detection + UPnP/IGD port-mapping enumeration
  credentialed_scan.py      # SSH credentialed deep scan — packages, services, users, patch level, sudo, failed logins
  combined_discovery.py     # Ultra-fast parallel discovery: ARP cache + ARP sweep + ICMP + TCP SYN + mDNS
  smb_enumerator.py         # NetBIOS name query + SMB share/user/session enumeration (Tier 1 + Tier 2)
  nl_query.py               # Natural language query engine — rule-based, zero deps, instant offline
  plugin_system.py          # Plugin loader — drop .py files into plugins/; PLUGIN_META + run() contract
  private_endpoint_checker.py  # DNS/TCP/TLS checker for Azure, AWS, GCP private endpoints; PaaS hint detection
  cloud_metadata.py            # Cloud VM detection — AWS IMDSv1/v2, Azure IMDS, GCP metadata; SSRF network exposure
  log_chart.py                 # RTT chart renderer — matplotlib PNG from a LogSummary; outages red, slow amber
  report_exporter.py        # Report generator — HTML, JSON, CSV, Nmap XML formats
  utils.py                  # Cache flush, ping sweep, network info, DHCP, adapter details, WoL, device baseline
  arp_monitor.py            # Module 9 — ARP spoof / MITM detector; baseline + live sniff; detects IP takeover and gateway MAC changes (requires Scapy + admin)
  dhcp_detector.py          # Module 10 — Rogue DHCP server detector; sends DHCPDISCOVER and flags multiple DHCPOFFER replies (requires Scapy + admin)
  bandwidth_monitor.py      # Per-device bandwidth monitor; counts bytes per MAC using Scapy AsyncSniffer; reports rx/tx bps per sample window (requires Scapy + admin)
  tls_checker.py            # SSL/TLS certificate checker; fetches cert on open HTTPS ports; reports expiry, issuer, self-signed status (stdlib ssl, no admin)
  snmp_poller.py            # SNMPv1/v2c basic poller; raw UDP, no pysnmp dependency; polls sysDescr, sysUpTime, sysName, ifNumber
  scheduler.py              # Scheduled scan engine; fires full device scan every N minutes; desktop notification on new/changed devices

ui/
  dashboard.py              # Main window — left sidebar nav: Standard (9) / Advanced (+8) / Recon (+12 tabs)
  topology_widget.py        # Network topology map widget
  matrix_rain.py            # Matrix rain Easter egg overlay (Ctrl+Shift+M)
  live_graph.py             # Real-time latency graph
  styles.py                 # Dark theme QSS

workers/
  scan_worker.py            # QThread workers: PreScan, NetworkInfo, Diagnostics, Logger, PortScan, MTR,
                            #   ARP, DHCP, Bandwidth, Scheduler, SNMP, SYNScan, UDPScan, OSFingerprint,
                            #   CVELookup, InternetExposure, CredentialedScan, CombinedDiscovery, SMBEnum,
                            #   Plugin, PrivateEndpoint, IPv6, CloudMetadata (28 workers total)
```

---

## Adding new rogue device signatures

Edit [`offenders.json`](offenders.json) or submit a pull request (see [CONTRIBUTING.md](CONTRIBUTING.md) for the full schema and PR checklist):

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

## Privacy

No telemetry. No cloud. No accounts. All scanning and analysis runs entirely on your machine.

The following external endpoints are contacted **only when you explicitly trigger them** from the Diagnostics tab or logger:
- `speed.cloudflare.com` — download speed test (Diagnostics tab)
- `connectivitycheck.gstatic.com` — HTTP connectivity check in logger (only if HTTP option enabled)
- `bash.ws` — DNS leak detection (Diagnostics tab only)

---

## What's in v1.0.3-2

### New in v1.0.3-2 — Microsoft Store submission

No capability changes. Four display-string updates required for Microsoft Store policy compliance:

- **"Stealth" scan mode renamed to "Low Impact"** — port scanner UI label and tooltip updated; internal key unchanged
- **"Recon Mode" renamed to "Security Audit Mode"** — sidebar button, tooltip, and section header updated; all variable and method names unchanged
- **"Sneaky" and "Paranoid" politeness levels renamed to "Careful" and "Minimum Impact"** — display strings only; internal dict keys unchanged
- **Authorized use statement added to About dialog** — first sentence of the About body now reads: *"Designed for use on networks you own or are authorized to administer."*

### New in v1.0.3-1

- **pytest added to `requirements.txt`** — fixes CI installs that lacked a test runner

### New in v1.0.3
- **Behavioural test suite** — 88 pytest tests covering `utils.py`, `network_logger.py`, `report_exporter.py`, and `cli.py` exit codes; all network calls mocked; runs in CI on every build
- **CONTRIBUTING.md** — offenders.json schema, plugin authoring guide, dev setup, PR checklist
- **Credential handling documented** — `credentialed_scan.py` now explicitly documents that credentials are in-memory only, never written to disk, and never included in any report output
- **Documentation fixes:** corrected `fe80::/10` prefix (was `/8`), corrected OUI count (115+), added v1.0.2 changelog entry, linked CONTRIBUTING.md from the offenders.json section

### New in v1.0.2
- **Topology widget** — network topology map added as a dedicated tab in Advanced Mode
- **Bandwidth monitor** — per-device rx/tx bps tab added in Advanced Mode
- **Bug fixes:** About dialog crash; bandwidth worker thread cleanup on tab close

### New in v1.0.1
- **Full-scan stability** — fixed hard crash at ~240/254 hosts caused by a race condition on the ping-sweep counter and Windows handle exhaustion from 60+ concurrent subprocesses; `max_workers` reduced to 32 with a threading lock
- **Scapy/Npcap isolation** — STP (Module 2) and Storm (Module 3) scanners now run in a separate `multiprocessing.Process` so a Npcap driver fault cannot kill the main GUI process; safe fallback results are emitted on failure
- **Crash logging** — `faulthandler` writes C-level crash tracebacks to `netsentinel_crash.log` next to the exe; unhandled Python exceptions are also logged via `sys.excepthook`
- **Bug fixes:** missing `import threading` in `utils.py`; restored missing `_on_bpdu_found` slot in dashboard; `_on_m5_result` dead-code cleanup

### New in v1.0.0
- **IPv6 subnet scan** (`scan --ipv6`, GUI: 🔷 IPv6 Devices tab) — reads OS neighbour cache, then actively pings `fe80::/10` on every network interface; results show ip6 / MAC / state / source; merges with Device Fingerprinter
- **Cloud metadata detection** (`cloud-metadata`, GUI: ☁ Cloud Metadata tab in Recon Mode) — probes AWS IMDSv1/v2, Azure IMDS, GCP metadata server in < 1 s; detects unsafe IMDSv1 access; flags network devices acting as SSRF metadata proxies
- **Logger RTT chart** (`log-chart FILE`, GUI: 📊 View Chart button in Network Logger) — renders log CSV as dark-themed PNG: RTT lines per target, outages shaded red, slow periods amber, DNS latency on second axis, uptime % bar chart; `--show` opens interactive window

### New in v0.9.5
- **CLI** (`cli.py`) — headless `scan`, `diagnose`, `log`, `ports`, `check-endpoints` commands; CI-friendly exit codes
- **Windows Service** (`svc.py`) — installs `NetworkLogger` as a background Windows service; daily CSV rotation; config via `%PROGRAMDATA%\NetSentinel\netsentinel-svc.ini`; `debug` mode works without pywin32
- **Private Endpoints — PaaS hints** — Azure App Service, Kudu, AWS Elastic Beanstalk, AWS App Runner, GCP Cloud Run, GCP App Engine suffixes detected with provider-specific guidance
- **Private Endpoints — resolver shown** — system DNS server used for resolution is appended to the Findings column
- **Device Fingerprinter — NL search bar** — live plain-English filter above the device table
- **DNS Correlator — DNS latency plotted** — DNS RTT points now appear on the live graph alongside ping targets
- **Bug fixes:** CVE version column, storm rogue-MAC pre-population, JSON storm export field names, port scan mode persistence, MatrixRain overlay hidden at startup

### Standard Mode (9 tabs — no admin required)
| Tab | Capability |
|---|---|
| 🔍 Device Fingerprinter | ARP scan, OUI lookup, IPv6 RA snooping, **device-type classification** (IP Camera, NAS, Smart TV, Domain Controller, iPhone, etc.), per-device risk score |
| 🌉 STP / BPDU Detector | Catches rogue Root Bridge elections that cause periodic 15–45 s drop cycles |
| 🌊 Storm Analyser | Measures broadcast/multicast flood levels |
| 📶 WiFi Scanner | Hidden SSIDs, rogue APs, co-channel interference, **WPS detection**, connected client list |
| 📡 DNS Correlator | Live ping + DNS latency graph, STP reconvergence signature detection |
| 🌐 Network Info | Full network snapshot: IPs, gateway, DNS, DHCP lease, adapter speeds, WiFi signal |
| ⚡ Diagnostics | Ping, DNS speed (4 resolvers), HTTP check, DNS leak test, traceroute, speed test |
| 📋 Network Logger | Long-term unattended ping logger → CSV; automated outage analysis; jitter, DNS, ARP watch options; **📊 View Chart** button renders loaded log as PNG |
| 🔷 IPv6 Devices | Link-local sweep: OS neighbour cache + active ping6 across all interfaces; ip6 / MAC / state / source table |

### Advanced Mode (+8 tabs)
| Tab | Capability |
|---|---|
| 🔁 MTR | Continuous hop-by-hop traceroute with live loss % and RTT per hop |
| 🔧 Advanced Tools | TCP port scanner (Fast/Normal/Stealth + **adjustable politeness**), protocol-aware service version detection, Wake-on-LAN, baseline diff alert |
| 🗺 Topology | Visual network topology map |
| 🛡 ARP Monitor | Live ARP table change detection |
| 📦 DHCP Monitor | DHCP lease tracking |
| 📊 Bandwidth | Per-interface bandwidth monitor |
| 🕐 Scheduler | Scheduled scan automation |
| 📡 SNMP | SNMP v1/v2c device polling |

### Recon Mode (+12 tabs — admin + Npcap recommended)
| Tab | Capability |
|---|---|
| ⚡ SYN Scan | Scapy raw-socket SYN stealth scan — top-1000 ports, common 26, or full 1–65535; configurable rate (pps) |
| 📻 UDP Scan | UDP scan — ICMP unreachable = closed, no-response = open\|filtered (Nmap convention) |
| 🖥 OS Fingerprint | Two-tier: TTL+banner (no admin) + TCP window/options/DF-bit SYN probe (admin+Scapy) |
| 🎯 Risk Scorer | Per-device score 0–100, CRITICAL/HIGH/MEDIUM/LOW band, top finding + remediation steps |
| 🛡 CVE Lookup | NVD API v2 — CVEs for detected service versions; rate-limited, cached, offline-safe |
| 🌐 Internet Exposure | WAN IP, CGNAT detection, UPnP/IGD port-mapping enumeration (LAN-only SSDP) |
| 🔑 Credentialed Scan | SSH into Linux/macOS/Windows — installed packages, services, users, patch level, NOPASSWD sudo, failed logins |
| 🚀 Fast Discovery | All discovery methods in parallel: ARP cache + ARP sweep + ICMP ping + TCP SYN + mDNS — /24 in < 3 s |
| 🗂 SMB / NetBIOS | NetBIOS name query + SMB2 banner (Tier 1, no creds); full share/user/session enumeration (Tier 2, with creds) |
| 🔒 Private Endpoints | DNS resolution (vs. public resolver), TCP reachability, TLS cert validity for Azure / AWS / GCP private endpoints |
| 🔌 Plugins | Drop `.py` plugins into `plugins/` folder — auto-loaded, run against scan results, plain-English output |
| ☁ Cloud Metadata | Detect if this machine is inside a cloud VM (AWS IMDSv1/v2, Azure IMDS, GCP); flag network devices acting as SSRF metadata proxies |

### Natural language query
Ask plain-English questions about scan results:
> *"show me risky devices"* · *"find exposed RDP"* · *"which cameras have telnet open"* · *"list domain controllers"*

Rule-based engine — no ML, no internet, no extra dependencies.

### Scan politeness levels
| Level | Delay | Port order | Use case |
|---|---|---|---|
| Aggressive | none | sequential | lab / fastest |
| Normal | none | sequential | default |
| Polite | 0–100 ms jitter | sequential | shared networks |
| Sneaky | 0.5–3 s jitter | randomised | evade basic IDS |
| Paranoid | 5–15 s jitter | randomised | maximum stealth |

### Plugin system
Drop a `.py` file into the `plugins/` folder next to the exe. NetSentinel loads it instantly — no rebuild required. A working example plugin is created on first run.

### Navigation
Left sidebar — all modules always visible in three labelled groups (Standard / Advanced / Recon). No horizontal scrolling. Same layout as Wireshark, ntopng, PRTG.

### Export formats
HTML · JSON · CSV · **Nmap XML** (accepted by Metasploit `db_import`, Burp Suite, Faraday, Dradis)

### UX
- **Persistent settings** — `NetSentinel.ini` next to the exe (portable, travels on USB); restores last mode, window size, scan targets, port scan settings
- **Matrix rain** Easter egg — `Ctrl+Shift+M`

---

## Roadmap

All roadmap items now shipped in v1.0.0 except code-signing. Future ideas:

| # | Item | Status |
|---|---|---|
| 1 | Code-signing (eliminates SmartScreen / Gatekeeper friction on first run) | Planned — see [SignPath Foundation](https://about.signpath.io/product/open-source) for free OSS signing |
| 2 | ~~Full IPv6 subnet scan support~~ | ✅ Shipped in v1.0.0 |
| 3 | ~~Cloud metadata endpoint detection (AWS IMDSv1/v2, Azure IMDS)~~ | ✅ Shipped in v1.0.0 |
| 4 | ~~Logger RTT chart visualiser (render CSV as graph without opening the GUI)~~ | ✅ Shipped in v1.0.0 |

---

## Requirements

| Dependency | Purpose |
|---|---|
| Python 3.9+ | Runtime |
| PyQt6 6.11+ | GUI framework |
| matplotlib 3.10+ | Live latency graph + RTT chart renderer |
| Scapy 2.7+ | STP/BPDU capture, SYN/UDP stealth scans, OS fingerprinting (Recon mode) |
| [Npcap](https://npcap.com) *(Windows only)* | Packet capture driver for Scapy |
| pywin32 308+ *(Windows service only)* | Required only for `svc.py` — not needed for GUI or CLI |

Install: `pip install -r requirements.txt`  
Windows service only: `pip install pywin32` then `python -m pywin32_postinstall -install` (as Administrator)

---

## License

MIT — free to use, modify and distribute.

---

## Author

**Ossian Ericson**  
[linkedin.com/in/ossian-ericson](https://www.linkedin.com/in/ossian-ericson/)

---

## Why this was built

Your mesh router is probably secretly participating in STP Root Bridge elections. When it wins, your real router blocks its own uplink port for 30 seconds. You get a drop. You call your ISP. They say "WiFi interference." It happens again in two minutes — on a timer.

No consumer tool surfaced this to a non-expert. So one was built.

The commit history shows it went from a blank folder to cross-platform releases in one Saturday afternoon, if you're curious about the pace.

| Time | What shipped |
|---|---|
| **12:58** | First commit — ARP scan, basic risk flagging. |
| **13:08** | GitHub Actions pipeline — tag → exe → release, before the first feature worked end-to-end. |
| **14:15** | Hostname resolution, MAC OUI fingerprinting (115 OUI prefixes, 8 vendor groups), IPv6 rogue router detection. |
| **16:02** | Full rebrand to NetSentinel. Overhauled UI, dark theme. |
| **17:18** | CVE lookup, Nmap XML export, Internet Exposure scanner, persistent settings. |
| **18:12** | Natural language query engine, scan politeness levels, WPS detection, plugin system. |
| **19:49** | v1.0.0. IPv6 full scan, cloud metadata (AWS/Azure/GCP), RTT chart renderer, CLI, Windows service. |
| **20:35** | Hard crash at ~240/254 hosts — race condition + Windows handle exhaustion. Fixed. |
| **22:11** | Topology widget, bandwidth monitor, About dialog bugs. Shipped as v1.0.2. |
| **22:50** | 88 behavioural pytest tests, CONTRIBUTING.md, credential handling docs, doc accuracy fixes (fe80::/10, OUI count). Shipped as v1.0.3-1. |
| **23:26** | Microsoft Store submission prep — four display-string renames (`Stealth` → `Low Impact`, `Recon Mode` → `Security Audit Mode`, `Sneaky` → `Careful`, `Paranoid` → `Minimum Impact`) and authorized-use statement added to About dialog. No capability changes. Shipped as v1.0.3-2. |

*Built because no single tool existed that combined device fingerprinting, Layer-2 fault detection, long-term connectivity logging, and security monitoring in one place — without requiring a lab setup, a cloud account, or a PhD in Wireshark.*
