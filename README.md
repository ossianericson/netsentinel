[![Version](https://img.shields.io/github/v/release/ossianericson/netsentinel?style=flat-square)](https://github.com/ossianericson/netsentinel/releases/latest)
[![License](https://img.shields.io/github/license/ossianericson/netsentinel?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square)](#install)
[![winget](https://img.shields.io/badge/winget-NetSentinel.NetSentinel-blue?style=flat-square)](https://winstall.app/apps/NetSentinel.NetSentinel)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square)](https://python.org)
[![Tests](https://img.shields.io/badge/tests-1550%2B-brightgreen?style=flat-square)](tests/)

# NetSentinel

The free, open-source network monitor that works with **any** router, modem, or access point — not just the brands it was built for. Runs 100% locally.

<p align="center">
  <img src="assets/screenshots/hero.gif" alt="NetSentinel dashboard overview" width="860"/>
</p>

---

## Install

**Windows** — prefer winget (keeps the app updated automatically):

```powershell
winget install NetSentinel.NetSentinel
```

**macOS / Linux / manual Windows** — download the binary for your platform from the [latest release](https://github.com/ossianericson/netsentinel/releases/latest).

### Windows notes

Layer 2 features (STP, broadcast storm, ARP monitor) require [Npcap](https://npcap.com) — free, one-click installer maintained by the Nmap project. Standard features work without it.

If Windows blocks the installer on first run, right-click the downloaded file → **Properties** → check **Unblock** → **OK**, then run it. This does not apply to winget installs.

### macOS notes

> **Note:** Most features work on macOS. Gatekeeper bypass is required on first launch — right-click the app → **Open**.

Layer 2 features (STP, storm detection, ARP monitor) require libpcap:

```bash
brew install libpcap
```

Run with `sudo` to enable packet capture features. On Apple Silicon, ensure you are using a native arm64 Python build — x86_64 Python via Rosetta may have issues with Scapy and libpcap.

To run from source instead of the pre-built binary:

```bash
git clone https://github.com/ossianericson/netsentinel
cd netsentinel
pip install -r requirements.txt
sudo python app.py
```

### Linux notes

> **Note:** Tested on Ubuntu 22.04+ and Debian 12+.

Layer 2 features require libpcap:

```bash
sudo apt-get install libpcap-dev   # Debian/Ubuntu
sudo dnf install libpcap-devel     # Fedora/RHEL
```

If the app fails on launch with a Qt platform plugin error:

```bash
sudo apt-get install libxcb-cursor0
QT_QPA_PLATFORM=xcb sudo ./NetSentinel
```

To run from source instead of the pre-built binary:

```bash
git clone https://github.com/ossianericson/netsentinel
cd netsentinel
pip install -r requirements.txt
sudo python app.py
```

---

## Why NetSentinel exists

Most home network problems require a different tool for each symptom — a CLI ping tool, a separate ARP scanner, a Wi-Fi analyzer, a traceroute utility, and whatever your ISP recommends this week. None of them produce evidence you can hand to a support technician. None of them talk to each other.

The specific incident that started this project: a Google Nest speaker connected via Ethernet was winning the STP root bridge election on the local network. Every 30–45 seconds it forced the actual router to block its own uplink port and reconverge — producing exactly the intermittent drops and DNS failures that ISP helpdesks dismiss as "Wi-Fi interference." Tracking it down required jumping between five separate tools and produced no shareable evidence.

NetSentinel handles discovery, Layer 2 detection, long-term logging, and report generation in one place. No account, no cloud, no telemetry. Free forever.

**Replaces:**
- Nmap — device discovery, port scanning, OS fingerprinting
- Wireshark — broadcast storm detection and ARP monitoring (simplified, read-only)
- PingPlotter / MTR — hop-by-hop trace, stability logging, outage evidence
- Wi-Fi analyzer apps — hidden SSIDs, rogue APs, co-channel interference, signal heatmap
- Manual ISP support documentation — the ISP Accountability Report replaces the copy-paste grind

All analysis runs 100% locally. Nothing leaves your machine unless you explicitly trigger an external check.

---

## Works with any hardware — open plugin protocol

Most network monitoring tools are locked to their own ecosystem. Ubiquiti works with UniFi. Synology works with Synology. If your hardware is not on the supported list, you are out of luck.

NetSentinel takes a different approach: **an open plugin protocol that any Python script can implement.**

The full interface is four functions and two variables:

```python
HARDWARE_NAME = "My Router XYZ"   # displayed in the app
HARDWARE_TYPE = "router"           # router | modem | ap | switch | other

def get_info()    -> dict   # static metadata: model, firmware, IP
def get_status()  -> dict   # live data: WAN IP, uptime, signal, speed
def get_clients() -> list   # connected devices: ip, mac, hostname (optional)
```

That is the entire contract. Any `.py` file that satisfies it becomes a first-class NetSentinel integration.

### How users create integrations

The **Integrate Hardware** page (Extend section in the nav) walks through the process in four steps:

1. **Find your hardware's API** — GitHub search strings, Home Assistant integration library, and a five-step browser dev-tools workflow (F12 → Network tab → Copy as cURL) to capture the exact API calls your router admin panel makes
2. **Write the script** — a ready-to-run Python template you fill in, or hand to an AI
3. **Test and import** — NetSentinel validates the plugin via AST (no code executed during validation), then runs it in a sandboxed subprocess so a buggy script cannot crash the app; output appears inline
4. **Share** — submit a working script as a GitHub Issue; reviewed and merged as a built-in integration for all users

### The AI angle

An AI assistant (Claude, ChatGPT, Gemini) can write a working plugin for most hardware in about 10 minutes if you give it the right input. The page includes three copy-ready AI prompts:

- **Prompt A** — general: "write a script for my Brand Model at 192.168.1.1, I need WAN IP, uptime, clients, and speed"
- **Prompt B** — from cURL: paste the captured request from your browser dev tools and ask the AI to convert it to a full plugin (this produces the best results)
- **Prompt C** — debug: paste a broken script and error message and ask the AI to fix it

### Current status and roadmap

| Capability | Status |
|---|---|
| Plugin import with AST validation | ✅ Live in v1.9.8 |
| Sandboxed subprocess test with inline output | ✅ Live in v1.9.8 |
| In-app guidance, template, and AI prompts | ✅ Live in v1.9.8 |
| Plugin clients → Devices table (with source badge) | 🔜 Next milestone |
| Plugin status → Overview hardware tile | 🔜 Next milestone |
| Plugin device names → Topology diagram | 🔜 Next milestone |
| Community plugin library (built-in integrations) | 🔜 Depends on submissions |

The test-and-validate workflow is live now. Data flowing from a plugin into the rest of the app is the next development sprint.

### Validation approach

The two reference integrations built into NetSentinel (TP-Link Deco mesh, ZTE MC889 5G modem) are being rebuilt using only the in-app plugin guide and an AI assistant — no internal documentation. If the workflow produces working scripts for those devices, it works for anything. Results and scripts will be published as the first entries in the community plugin library.

---

## Quick start

1. Install NetSentinel — see [Install](#install) above
2. On Windows, install [Npcap](https://npcap.com) if you want STP, broadcast storm, or ARP monitor features
3. Run as Administrator — right-click the app → **Run as Administrator** on Windows; `sudo python app.py` on macOS/Linux
4. Click **Scan** in the top bar to discover all devices on your network
5. Open the **Network Grade** tab for an A–F assessment across 8 health dimensions

---

## Features

### Works without admin rights

| Feature | What it tells you |
|---|---|
| Device discovery | Every device's IP, MAC, hostname, vendor, and model (e.g. "Google Nest Audio", "TP-Link Deco M5") with device type and risk level |
| Network grade A–F | Benchmark across uptime, latency, jitter, DNS speed, download speed, device safety, STP health, and storm level vs. a "perfect home network" baseline |
| ISP Accountability Report | MTR hop table, packet-loss %, DNS latency, and timestamped outage log formatted as a standalone HTML file for support escalation |
| Stability logger | Runs unattended for hours or days — timestamped CSV log of every ping, DNS latency, and ARP change; evidence-grade output for ISP disputes |
| Availability history | Persistent RTT and UP/DEGRADED/DOWN state charts per device with 1 h / 12 h / 24 h / 7 d zoom |
| DNS benchmarking | Compares your system resolver against Cloudflare, Google, and Quad9 side-by-side; includes DNS leak test |
| Speed test | 3-tier engine: Ookla CLI → speedtest-cli → pure-Python fallback with no extra dependencies |
| TLS certificate monitor | Hourly expiry checks per host; alerts 30 days before expiry; OK / EXPIRING / EXPIRED badges |
| Active connections | Process-to-socket map with one-click firewall block/unblock per process |
| Live bandwidth chart | 60-second rolling upload/download chart per interface |
| CVE lookup | Cross-references discovered OS and service versions against the NVD database on demand |
| Wi-Fi network scan | Hidden SSIDs, rogue APs, WPS-enabled networks, co-channel interference, connected client list |
| IoT behaviour baseline | Learns normal traffic per IoT device; alerts on port scans, new destinations, and traffic rate spikes |
| DHCP lease inventory | Lists all active DHCP leases; flags any rogue DHCP server on the segment |
| Geolocation map | Plots internet-facing IPs on an offline world map using MaxMind GeoLite2-City — no API key, no external calls |
| Topology diagram | Visual topology diagram: flat star by default; upgrades to a three-tier mesh tree (Gateway → Satellites → Clients grouped by satellite) when Deco credentials are configured — devices invisible to the mesh attach directly to the gateway so nothing is dropped |
| Mesh router integration | Pulls live data from your mesh gateway — Deco-assigned device names replace rDNS guesses in the Devices on Network table; Node and Band columns appear automatically; per-device upload/download rates from the router's own counters. Runs silently after each scan when credentials are saved. TP-Link Deco fully supported; architecture supports Eero, Google Nest, Asus ZenWiFi, Netgear Orbi |
| **Hardware plugin protocol** | **Import any router, modem, or AP via a 4-function Python script. In-app guide covers finding the API, writing the script with AI assistance, testing in a sandboxed subprocess, and submitting to the community library. Plugin data flowing into Devices and Overview is the next milestone — see [Works with any hardware](#works-with-any-hardware--open-plugin-protocol) above.** |
| Automation hooks | Webhook and script triggers on network events — device down, high RTT, new device discovered |
| REST API | Read-only local HTTP API at `http://127.0.0.1:8765` — query devices, alerts, and uptime from Home Assistant or scripts |
| "What's Wrong?" diagnosis | One-click root-cause analysis across slow / dropping / can't-connect symptoms — sequences network, storm, rogue device, and STP checks then surfaces a prioritised plain-English finding |
| Shareable diagnostic card | "Share Card" button on the Overview page — exports a 520×300 summary card (grade, ISP, top 3 findings) as PNG, clipboard image, or standalone HTML; zero external dependencies |
| Lab / Scenario Mode | Four guided exercises — Find the Rogue Device, Diagnose Slow DNS, Identify the Broadcast Storm Source, Map Your Subnet — with progressive hints, solution reveal, and exportable HTML result report |

### Requires admin + Npcap (Windows) / libpcap (macOS, Linux)

| Feature | What it tells you |
|---|---|
| STP root bridge detection | Identifies which device is claiming the root bridge via BPDU capture — the hidden cause of periodic 30–45 s reconnection drops |
| Broadcast storm detection | Measures broadcast and multicast flood levels that silently choke bandwidth; pinpoints the source device |
| ARP spoofing detection | Watches for MAC address conflicts that indicate a MITM attack in progress on the local segment |
| Per-device bandwidth monitor | Exact rx/tx bps per device via live packet capture |
| SYN stealth port scanner | Half-open TCP scan — faster and quieter than a connect scan; requires Scapy + admin |
| Full device discovery | Parallel ARP + ICMP + TCP SYN + mDNS sweep for maximum device census accuracy |

---

## For educators and students

NetSentinel runs real scans against a live network, which means every result maps directly to a protocol or concept covered in CompTIA Network+ and CCNA curricula.

**Concepts visible in real time:**
- **ARP** — the ARP Spoof Watch tab shows every ARP request and reply on the segment; the device table shows the current MAC-to-IP mapping your system holds
- **DNS** — the DNS & Outages tab graphs resolver latency live; the DNS benchmarking tool compares four resolvers simultaneously; the DNS leak test shows exactly which resolver handles your queries
- **STP** — the Rogue Bridge tab captures BPDUs and identifies the current root bridge, port roles, and reconvergence timing
- **TCP** — the port scanner and Active Connections tab show three-way handshake outcomes (open/filtered/closed) and live socket states per process
- **DHCP** — the DHCP Lease Inventory tab parses the OS lease table and flags any unauthorized DHCP server on the segment
- **ICMP** — the Stability Logger and Availability History tabs plot round-trip times and packet loss across days or weeks
- **Layer 2 vs. Layer 3** — STP, ARP, and broadcast storm features operate at Layer 2 (MAC/frame); device discovery, DNS, and traceroute operate at Layer 3 (IP); each tab makes the distinction explicit

**Built-in reference material:**
- **Protocol Visualizer** — animated step-by-step diagrams of ARP resolution, DNS lookup, TCP handshake, DHCP lease, and STP election using real scan data from your own network (not placeholder addresses)

<p align="center">
  <img src="assets/screenshots/protocol-visualizer.gif" alt="Protocol Visualizer — animated packet trace" width="720"/>
</p>

- **Lab / Scenario Mode** — four guided exercises (Find the Rogue Device, Diagnose Slow DNS, Identify the Broadcast Storm Source, Map Your Subnet) with progressive hints, solution reveal, and exportable HTML result reports
- IP and subnet calculator with reference panels explaining CIDR notation, subnetting rules, and address classes
- 24-term networking glossary (ARP, BPDU, CGNAT, CVE, mDNS, STP, TLS, and more) — accessible via the help button from any page without leaving current context
- In-app "Common Scenarios" lookup table mapping 17 user goals to the correct feature

**On the roadmap for structured learning:**
- CompTIA Network+ / CCNA curriculum alignment tags on each feature page, plus an exportable study-session report
- Classroom export — signed scan reports with machine fingerprint for instructor aggregation and graded lab submissions

If you use NetSentinel in a course or lab and need curriculum-specific features, open an issue — feedback from educators shapes the roadmap directly.

---

## Quality

The project ships with **1 550+ automated tests** covering detection logic, metric storage, version consistency, and UI wiring. Run the full suite with:

```bash
python -m pytest tests/ -v --tb=short
```

All tests are offline — no real network traffic, no live devices required.

---

## Architecture

See [docs/architecture.md](docs/architecture.md) for module layout, data flow, and design decisions.

The short version: [app.py](app.py) is the GUI entry point; [cli.py](cli.py) is the headless CLI; all detection logic is in [modules/](modules/); UI pages are in [ui/pages/](ui/pages/); background threads are in [workers/](workers/). All colour and style values live in [ui/styles.py](ui/styles.py) — no hex values appear elsewhere in the UI code.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup, coding conventions, and PR process.

### Hardware plugins (no coding required beyond Python)

If you own a router, modem, or AP that is not yet supported, the highest-value contribution is a working plugin script. Use the **Integrate Hardware** page in the app — the four-step guide and AI prompts get most people to a working script in under 30 minutes.

To submit: open a GitHub Issue titled `[Hardware Plugin] Brand Model XYZ`, attach the `.py` file, describe what `get_status()` returns, and list any `pip install` dependencies. Reviewed scripts are merged as built-in integrations.

**Template for the issue:**

```
Hardware: Brand Model XYZ
Firmware tested: vX.Y.Z
Access method: HTTP REST / HTML scrape / SNMP / SSH
pip dependencies: requests, beautifulsoup4   (or none)
get_status() returns: wan_ip, uptime_sec, connected_clients, download_mbps, upload_mbps

[attach your .py file]
```

### Rogue device signatures (edit a JSON file, no Python needed)

To flag a device that misbehaves on home networks, edit [`offenders.json`](offenders.json) and submit a pull request:

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

No telemetry. No cloud. No accounts. All scanning and analysis runs on your machine.

The only external endpoints contacted are ones you explicitly trigger:

| Endpoint | Purpose |
|---|---|
| `speed.cloudflare.com` | Download speed test |
| `services.nvd.nist.gov` | CVE lookup (Security Audit mode, on demand) |
| `bash.ws` | DNS leak test |
| `api.github.com` | Update check on startup |

All other analysis — device discovery, ARP monitoring, STP detection, bandwidth logging, availability tracking — is local.

---

## Changelog

### v1.9.26

- **Hardware plugin protocol** — open integration standard for any router, modem, or AP; import a `.py` file that implements `get_info()`, `get_status()`, and optionally `get_clients()` and it becomes a testable integration; validation uses AST only (no untrusted code executed at import time); Test button runs the script in a sandboxed subprocess so a buggy plugin cannot crash the app; **Integrate Hardware** page (new Extend nav section) walks through finding your device's local API, writing the script with AI assistance (three copy-ready AI prompts included), testing locally, and submitting to the community library; plugin data flowing into the Devices table and Overview tiles is the next development milestone
- Mesh router integration — live client data pulled directly from TP-Link Deco via its local API (no cloud, no account); Deco-assigned device names replace reverse-DNS hostnames in the Devices on Network table; Node and Band columns appear automatically; per-device upload/download KB/s shown as a tooltip; credentials saved to OS keychain and the scan re-runs silently on every subsequent app start; Network Map upgrades to a three-tier mesh tree (Gateway → Satellites → Clients) when mesh data is present; WiFi Networks page gains real band-usage KPI chips (2.4 GHz / 5 GHz / 6 GHz / Wired client counts from the router) and a "Connected?" column; architecture supports adding Eero, Google Nest, Asus ZenWiFi, and Netgear Orbi via the same `MeshWorker` provider key
- Protocol Visualizer — animated step-through of 9 real protocols (DHCP, ARP, DNS, TCP, TLS, HTTP, ICMP, NTP, OSPF); each step shows the packet name, frame detail, and a labelled dot travelling between nodes; play/pause/step controls; tabbed with a protocol context panel
- Log Hub — live network logger output in a filterable table; streams real events as they happen; interesting events (DNS failures, slow gateway, consecutive connection failures) automatically generate a Lab Mode exercise surfaced as a home screen card
- Feature Guide — 44-feature catalogue grouped by category accessible from Education nav and the home screen; filter bar with synonym tags (search "heatmap", "arp", "stp"); badges for features requiring Npcap or admin rights; Open buttons navigate directly to the feature
- Contextual page tips — a persistent tip bar below the breadcrumb row shows "ⓘ Tips for {page} ▾" on every page that has content; clicking expands a panel with what the page does and hidden interactions; auto-expands on first visit to complex pages (Logs, Lab Mode, Protocol Visualizer, Automation Hooks, and others); pages with no tips show "ⓘ Open Feature Guide →" which navigates there directly
- Smart home screen suggestions — the home screen detects unvisited high-value pages and surfaces them as discovery cards; visit tracking persists across sessions; live challenge cards appear when the network logger detects something interesting
- Status bar tooltips — all four pulse indicators (connection, devices, scan time, logger state) now show a tooltip describing what they measure and naming the page they link to
- REST API remote access guidance — Settings page now shows 3-step instructions for accessing the REST API from other devices on the LAN, including the `ipconfig` tip to find the host IP
- Empty-state with inline CTA on four pages — Network Grade, ISP Report, Network Doc, Availability History each show an action button instead of a dead-end "run a scan first" message
- Complete dashboard wiring audit — all overview tiles animate live from background workers; SNMP Trap, Syslog, and Threat Intelligence pages receive live data automatically

### v1.6.4

- One-click "What's Wrong?" diagnosis — symptom tiles (slow / dropping / can't connect), sequences network diagnostics → storm → rogue device → STP checks, surfaces a "Do this first" priority finding card; distinct green healthy state
- Shareable diagnostic card — "Share Card ▾" button on Overview, enabled after first benchmark run; QMenu with Save PNG, Copy PNG, and Save HTML; card shows grade circle, ISP, top 3 findings, device count, and timestamp
- Lab / Scenario Mode — four guided exercises (Find the Rogue Device, Diagnose Slow DNS, Identify the Broadcast Storm Source, Map Your Subnet) with progressive hints, solution reveal, and exportable HTML result report; accessible from the new Education nav section
- Network Doc page now receives real data after every scan — device list, cert inventory from MetricStore, topology widget, and accumulated port scan results; previously showed 0 devices even after a full scan
- MQTT / HA page wiring — device join/leave events, alerts, and per-device uptime states now flow to the MQTT publisher automatically; AvailabilityWorker starts after the first scan and drives live updates to Availability History and Home Automation Hub
- Fixed `ModuleNotFoundError` crash on startup in installed builds — `diagnosis_page` and `diagnosis_worker` were missing from PyInstaller `hiddenimports`
- Release cleanup — standalone Windows portable exe and CLI dropped from GitHub Releases; Windows users install via `winget install NetSentinel.NetSentinel`

### v1.6.2

- Top-bar brand icon — replaced the "N" letter placeholder with the actual app icon (24×24, smooth-scaled from `assets/icons/netsentinel.png`)
- New icon design — hexagon + shield identity across all sizes: ICO (7 resolutions), MS Store tiles, Start Menu tiles, installer splash, macOS/Linux PNG
- `generate_icons.py` — new script regenerates all raster assets from the embedded design; run after any brand change

---

## License

MIT — see [LICENSE](LICENSE).
