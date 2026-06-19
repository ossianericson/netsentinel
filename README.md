[![Version](https://img.shields.io/github/v/release/ossianericson/netsentinel?include_prereleases&style=flat-square)](https://github.com/ossianericson/netsentinel/releases/latest)
[![License](https://img.shields.io/github/license/ossianericson/netsentinel?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square)](#install)
[![Microsoft Store](https://img.shields.io/badge/Microsoft%20Store-available-0078D4?style=flat-square&logo=microsoft)](https://apps.microsoft.com/detail/9NZ124C7HJWS)
[![winget](https://img.shields.io/badge/winget-NetSentinel.NetSentinel-blue?style=flat-square)](https://winstall.app/apps/NetSentinel.NetSentinel)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square)](https://python.org)
[![Tests](https://img.shields.io/badge/tests-4100%2B-brightgreen?style=flat-square)](tests/)

# NetSentinel

The free, open-source network monitor that works with **any** router, modem, or access point — not just the brands it was built for. Runs 100% locally.

<p align="center">
  <img src="assets/screenshots/hero.gif" alt="NetSentinel dashboard overview" width="860"/>
</p>

---

## Install

**Windows** — three options:

[<img src="https://get.microsoft.com/images/en-us%20dark.svg" alt="Get it from Microsoft" height="52"/>](https://apps.microsoft.com/detail/9NZ124C7HJWS)

Or via winget (keeps the app updated automatically):

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

The minimal interface is two constants and two required functions:

```python
HARDWARE_NAME = "My Router XYZ"   # displayed in the app
HARDWARE_TYPE = "router"           # router | modem | ap | switch | other

def get_info()    -> dict   # static metadata: model, firmware, IP
def get_status()  -> dict   # live data: WAN IP, uptime, signal, speed

# Optional — if present, clients appear on the plugin's device page
def get_clients() -> list   # connected devices: ip, mac, hostname
```

Optional constants: `HARDWARE_IP` (target address), `PYPI_PACKAGE` (pip dependency name), `CONFIG_SCHEMA` (typed settings the Hub card auto-generates a config form for), `ICON_PATH` (24×24 icon shown on the Hub card).

Any `.py` file that satisfies the required interface becomes a first-class NetSentinel integration.

### Bundled integrations

12 plugins ship with the app, all signed and hash-verified:

| Plugin | Hardware |
|---|---|
| `zte_plugin.py` | ZTE MC889 5G modem (SINR, RSRP, band, cell ID) |
| `deco_plugin.py` | TP-Link Deco XE75 mesh router (nodes, clients, topology) |
| `asus_plugin.py` | ASUS routers and ZenWiFi mesh (via `asusrouter` library) |
| `fritzbox_plugin.py` | AVM FRITZ!Box (DSL/cable, WAN IP, uptime, clients) |
| `unifi_plugin.py` | Ubiquiti UniFi (via UniFi API; requires local controller) |
| `netgear_plugin.py` | Netgear routers (Nighthawk, Orbi via SOAP API) |
| `mikrotik_plugin.py` | MikroTik RouterOS (REST API; v7.1+) |
| `openwrt_plugin.py` | OpenWrt (ubus JSON-RPC API) |
| `synology_plugin.py` | Synology NAS (DSM API; connection stats, uptime) |
| `ha_plugin.py` | Home Assistant (REST API; entity state and attributes) |
| `template_plugin.py` | Starter template for writing a new plugin |

### How users create integrations

The **Hardware Hub** (Extend section in the nav) has a dedicated **Write a Plugin** tab that walks through the process:

1. **Find your hardware's API** — GitHub search strings, Home Assistant integration library, and a five-step browser dev-tools workflow (F12 → Network tab → Copy as cURL) to capture the exact API calls your router admin panel makes
2. **Write the script** — click "⬡ New Plugin" to open the template wizard; fill in hardware name, type, IP, and any pip dependencies; a complete `.py` file is generated and opened in your system editor
3. **Test and import** — NetSentinel validates the plugin via AST (no code executed during validation), runs a live credential test in a background thread before registering, and executes subsequent polls in a sandboxed subprocess so a buggy script cannot crash the app
4. **Share** — submit a working script as a GitHub Issue; reviewed scripts are merged as built-in integrations

### The AI angle

An AI assistant (Claude, ChatGPT, Gemini) can write a working plugin for most hardware in about 10 minutes if you give it the right input. The Write a Plugin tab includes three copy-ready AI prompts:

- **Prompt A** — general: "write a script for my Brand Model at 192.168.1.1, I need WAN IP, uptime, clients, and speed"
- **Prompt B** — from cURL: paste the captured request from your browser dev tools and ask the AI to convert it to a full plugin (this produces the best results)
- **Prompt C** — debug: paste a broken script and error message and ask the AI to fix it

### Plugin ecosystem features

Every registered plugin gets a Hub card and a dedicated page under the Extend section. The full feature set:

| Capability | Notes |
|---|---|
| AST validation before import | No code executed during validation; checks required constants and function signatures |
| Live credential test before registration | Runs `get_info()` + `get_status()` in a background thread; only saves on success |
| Sandboxed subprocess execution | Buggy polls cannot crash the app; each poll runs in an isolated namespace |
| Multi-instance support | Same plugin type, multiple device IPs — each gets its own Hub card and nav entry |
| Per-instance OS keychain credentials | Password stored under a unique instance ID; zero cross-instance key collisions |
| CONFIG_SCHEMA typed config panel | Plugin declares `poll_interval`, `verify_ssl`, etc.; Hub card auto-generates the form |
| Health tracking + circuit breaker | Success/error counters visible on each card; auto-disables after 10 consecutive errors; amber "degraded" state after 24 h without a successful poll |
| Structured error classification | `AUTH:` / `DEPS:` / `NET:` / `TIMEOUT:` prefixes route to specific remediation text ("Re-enter Password", "pip install …", "Check IP") |
| Re-enter Password button | Appears on AUTH errors; reopens the credential dialog and restarts the worker on success |
| Plugin log console | "≡ Logs" toggle on each Hub card shows the last 100 structured poll log lines |
| Plugin validator CLI | `python -m modules.plugin_tools validate <plugin.py>` — static checks for required interface, PYPI_PACKAGE, top-level network calls, and unsafe imports |
| Bundled plugin signing | `data/plugin_hashes.json` SHA-256 list; tampered bundled files are blocked at load time |
| Unsigned plugin consent | One-time SHA-256-keyed warning dialog for non-bundled scripts; consent persisted in QSettings |
| Restricted import advisory | Warns when imports fall outside the safe-list; plugin can declare `SAFE_IMPORTS` to acknowledge custom dependencies |
| Plugin icon support | `icon.png` alongside the script or `ICON_PATH` constant; displayed as 24×24 on Hub cards and community catalog entries |
| Plugin rename | "✎" button renames the instance; change propagates atomically to nav flyout, breadcrumb, and command palette |
| Community Browse tab | Fetches a GitHub-hosted JSON index; per-entry SHA-256 verified before download; Install button copies to AppData and runs the normal registration flow |
| `.nspkg` bundle format | ZIP containing `plugin.py` + `manifest.json` + optional `icon.png`; "⬡ Import .nspkg" button in the Hub handles the full install flow |
| Startup dependency smoke-check | Missing `PYPI_PACKAGE` dependencies surface as card errors immediately on startup |

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
| **Hardware plugin protocol** | **12 bundled plugins included (TP-Link Deco, UniFi, FRITZ!Box, OpenWrt, MikroTik, Netgear, ASUS, Synology, Home Assistant, ZTE 5G modem). Import any router, modem, or AP via a Python script. Per-instance credentials, health tracking, circuit breaker, plugin log console, CONFIG_SCHEMA typed config, community Browse tab, and `.nspkg` bundle format all live. See [Works with any hardware](#works-with-any-hardware--open-plugin-protocol).** |
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

If you use NetSentinel in a course or lab and need curriculum-specific features, open an issue — feedback from educators shapes the roadmap directly.

---

## Quality

The project ships with **4 113+ automated tests** across 230 test files, covering detection logic, metric storage, version consistency, UI wiring, encoding hygiene, and CodeQL-prevention gates. Run the full suite with:

```bash
python -m pytest tests/ -v --tb=short
```

All tests are offline — no real network traffic, no live devices required.

---

## Architecture

See [docs/architecture.md](docs/architecture.md) for module layout, data flow, and design decisions.

The short version: [app.py](app.py) is the GUI entry point; [cli.py](cli.py) is the headless CLI; all detection logic is in [modules/](modules/); UI pages are in [ui/pages/](ui/pages/); background threads are in [workers/](workers/). All colour and style values live in [ui/styles.py](ui/styles.py) — no hex values appear elsewhere in the UI code.

`ui/dashboard.py` is the main window shell (1,967 lines). Its functionality is split across six inherited mixins: `ScanResultMixin` ([scan_wiring.py](ui/scan_wiring.py)), `AppHeaderMixin` ([header.py](ui/header.py)), `TabBuilderMixin` ([tabs.py](ui/tabs.py)), `_NavBuilderMixin` ([nav/builder.py](ui/nav/builder.py)), `_MonitorStateMixin` ([monitor_state.py](ui/monitor_state.py)), and `_PluginPageMixin` ([plugin_page_mixin.py](ui/plugin_page_mixin.py)).

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup, coding conventions, and PR process.

### Hardware plugins (no coding required beyond Python)

12 plugins ship with the app (see [Bundled integrations](#bundled-integrations) above). If your hardware is not on that list, the highest-value contribution is a working plugin script. Use the **Write a Plugin** tab in the Hardware Hub — the in-app guide, template wizard ("⬡ New Plugin"), and AI prompts get most people to a working script in under 30 minutes.

To submit: open a GitHub Issue titled `[Hardware Plugin] Brand Model XYZ`, attach the `.py` file, describe what `get_status()` returns, and list any `pip install` dependencies. Reviewed scripts are signed, added to `data/plugin_hashes.json`, and merged as built-in integrations.

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

See [CHANGELOG.md](CHANGELOG.md) for the full release history.

### v2.1.12 (current)

**Added**
- Status-icon shape constants (`STATUS_ICON_OK/WARN/CRIT/UNKNOWN`) in `ui/styles.py` — status no longer conveyed by colour alone in service heartbeat, uptime, and monitor verdict displays
- In-app feedback dialog (`ui/widgets/feedback_dialog.py`) — writes timestamped entries to `feedback.log` locally; no network calls; accessible via Ctrl+K "Give Feedback"
- Nav timing warnings and cProfile page-init instrumentation (`ui/perf_audit.py`)
- Focus rings on activity-rail buttons and flyout items for keyboard navigation

**Fixed**
- Stripped UTF-8 BOM from `ui/nav/rail.py` that caused silent `SyntaxError` in `ast.parse`-based test checks
- `test_no_duplicate_methods.py` now correctly exempts `@pyqtProperty` getter/setter pairs

---

## About

**NetSentinel — Network Security Scanner & Connectivity Monitor**

NetSentinel will always remain free and open source.

If you find this tool valuable, please consider supporting:

- **[Wikipedia](https://donate.wikimedia.org/)** — free knowledge for everyone
- **[Electronic Frontier Foundation](https://eff.org/donate)** — protecting digital rights

Thank you for using NetSentinel.

> **Disclaimer:** For use on networks you own or have explicit authorization to test.

Built by **Ossian Ericson** · [GitHub](https://github.com/ossianericson/netsentinel)

---

## License

MIT — see [LICENSE](LICENSE).
