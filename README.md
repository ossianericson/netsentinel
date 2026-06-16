[![Version](https://img.shields.io/github/v/release/ossianericson/netsentinel?include_prereleases&style=flat-square)](https://github.com/ossianericson/netsentinel/releases/latest)
[![License](https://img.shields.io/github/license/ossianericson/netsentinel?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square)](#install)
[![winget](https://img.shields.io/badge/winget-NetSentinel.NetSentinel-blue?style=flat-square)](https://winstall.app/apps/NetSentinel.NetSentinel)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square)](https://python.org)
[![Tests](https://img.shields.io/badge/tests-3900%2B-brightgreen?style=flat-square)](tests/)

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

**On the roadmap for structured learning:**
- CompTIA Network+ / CCNA curriculum alignment tags on each feature page, plus an exportable study-session report
- Classroom export — signed scan reports with machine fingerprint for instructor aggregation and graded lab submissions

If you use NetSentinel in a course or lab and need curriculum-specific features, open an issue — feedback from educators shapes the roadmap directly.

---

## Quality

The project ships with **3 921+ automated tests** across 209 test files, covering detection logic, metric storage, version consistency, UI wiring, encoding hygiene, and CodeQL-prevention gates. Run the full suite with:

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

### v2.1.11
**Added**
- `modules/cdn_ranges.py` — static CDN/streaming-provider IP range classifier (Netflix/YouTube/Twitch/Disney+) for App Traffic device drill-downs
- `modules/traffic_insights.py` — household usage narrative, ISP plan utilization, and QoS overlap recommendation builders
- `modules/service_bandwidth_overlay.py` — bandwidth-sharing context note for Service Diagnostics
- `ui/widgets/usage_insights_card.py` — home page "Usage insights" card (weekly category breakdown, plan utilization, dismissible QoS suggestion)
- `app_traffic_sample` table (schema v17) persists App Traffic history; new "Last 24 Hours by Category" chart on the App Traffic page with click-to-drill-down by device and CDN
- "Internet Plan" settings card — optional monthly data cap feeding plan utilization on the home page

### v2.1.10
**Added**
- Persistent device map: after each scan, pinned and static-candidate offline devices (infrastructure roles, IP-stable seen 3+ times) are appended to the Inventory snapshot with freshness state `pinned`, `cached` (<24 h), or `stale` (<7 d); implemented in `ScanResultMixin._merge_scan_with_persistent()` (`ui/scan_wiring.py`)
- "Hide offline" toggle in the Current Devices card header hides `cached`/`stale` rows without discarding the persistent map; resets on navigation

**Fixed**
- `ui/scan_wiring.py`: `_store_ref` used before assignment in `_on_m1_result` inventory block; replaced with `_inv_store` to fix silent `UnboundLocalError` that prevented segment detection from running

### v2.1.9
**Fixed**
- `modules/topology_cytoscape.py`: removed re-export block that created a cyclic import with `topology_cytoscape_html` (CodeQL #1526, #1528)
- `modules/topology_cytoscape_html.py`: promoted lazy `build_cytoscape_elements` imports to module-level now that the cycle is broken (CodeQL #1524, #1525)
- `tests/test_topology_cytoscape_html.py`: unified import form to `from modules import topology_cytoscape_html` to resolve CodeQL `py/import-and-import-from` (#1527)

### v2.1.8
**Changed**
- Overview tiles: staleness callout shown when data is >24 h old ("Data from X days ago — rescan?" in amber); 30 min+ shown in amber, 2 h+ in red
- Notifications page: split into "Configure" tab (channel cards, alert rules, dependency tree) and "Alert History" tab; switching to history auto-refreshes the log
- Alert history: storm banner appears when ≥5 alerts from the same /24 subnet arrive within 60 s, with a direct link to the dependency tree card
- Auto-resume: monitors (ARP Watch, Live Bandwidth, Scheduled Scans) that were running on last close are restarted on the next launch with an opt-out amber banner

**Fixed**
- `ui/nav/builder.py`: removed invalid `_nav_add_subgroup()` calls in `_build_pro_nav()` that crashed the app with `KeyError: -1` (legacy flat-nav method called in rail-nav context)

### v2.1.7
**Added**
- `modules/topology_cytoscape_html.py` — HTML/JS page template builder for Cytoscape map split from `topology_cytoscape.py` (RULE-AH1)
- `ui/pages/notif_dep_card.py` — `_NotifDepMixin`: alert dependency tree card; parent–child alert suppression with `_AddDepDialog`; QSettings persistence (O1)
- `ui/widgets/alert_drawer.py`: inline acknowledge form with name/comment fields; ack info badge shown on already-acknowledged alerts
- `ui/pages/network_map_page.py`: "Lock Layout" toggle — freezes node positions so re-scans update data without resetting the Cytoscape layout; incremental `window.updateTopology()` used after first load to prevent positional drift

**Fixed**
- `modules/topology_cytoscape.py`: `build_elements_for_update()` exported for incremental topology refreshes without full HTML reload

### v2.1.6
**Added**
- `modules/snmp_poller.py`: Cat2-V4 SNMP interface error metrics — `ifInErrors`/`ifOutErrors` polled per interface; stored in MetricStore and surfaced in SNMP Device Info page

**Fixed**
- Cat1-D0 startup cache restore — Network Map and topology widget now render from MetricStore cache on startup without requiring a rescan
- Interactive Network Map blank after scan — Cytoscape.js JS error when master mesh node was referenced as a parent (no separate node exists; master now routes devices to the gateway node)
- Classic and Interactive topology satellite assignments now match the Devices table — both views prefer pre-computed `d.mesh_unit` attribute set by `_apply_mesh_enrichment()` over an independent `mesh_enrichment` dict lookup

### v2.1.5
**Fixed**
- RULE 10 contradiction with RULE-AH3 resolved; all matplotlib chart backgrounds now use `ui/styles.py` tokens
- `QTimer.singleShot` calls replaced with parented `QTimer(self)` instances across widget classes (RULE-WIN5 hardening)
- `app.py` wiring refactor — always-on worker signals connected after `Dashboard` construction per RULE-DW2
- Network Map interactive view: hierarchical top-down Cytoscape.js layout and LLDP hint + WebEngine fallback polish

### v2.1.4
**Added**
- `modules/lldp_scanner.py` — LLDP/CDP neighbor scanner; passive sniff + active frame mode; raw TLV parser; `LldpNeighbor` dataclass with `is_infrastructure` property (Sprint 5)
- `workers/lldp_worker.py` — `LldpWorker` QThread; 15-second sniff in 3-second slices; emits `result_ready(list[LldpNeighbor])`; no-op when not admin (Sprint 5)
- `modules/topology_snapshot.py` — `TopologySnapshot`, `TopologyDiff`; save/load/diff topology state; change detection for new/removed/moved devices (Sprint 4)
- `ui/topology_widget.py`: LLDP overlay layer — draws LLDP infrastructure nodes (squares) and leaf nodes (diamonds) with teal edges from gateway; info banner when admin rights are needed (Sprint 5)
- `ui/topology_widget.py`: topology diff overlay — new devices highlighted green, removed devices dimmed red; diff legend in lower-left corner (Sprint 4)
- `ui/topology_widget.py`: zoom controls (+ / − / Reset) in lower-right corner; zoom-to-fit on first render; mouse-wheel zoom (Sprint 2)
- `ui/topology_widget.py`: node click → `DeviceDrawer` — clicking any device node on the topology map opens the device detail side drawer (Sprint 1)
- `ui/topology_widget.py`: health overlays on edges — edge colour reflects link state (green = healthy, amber = degraded, red = down) from availability monitor data (Sprint 3)
- `ui/scan_wiring.py`: `_on_lldp_result()` slot and `_start_lldp_discovery()` — wired into `_on_m1_result()` to auto-launch LLDP scan after every device discovery (Sprint 5)
- `tests/test_lldp_scanner.py` — 11 tests covering import, dataclass, TLV parsing (chassis MAC, system name, capabilities, management IPv4, truncated data), mocked sniff, and worker lifecycle (RULE-T1, RULE-T2) (Sprint 5)
- `tests/test_topology_snapshot.py` — tests for `TopologySnapshot` save/load/diff (Sprint 4)

**Changed**
- `modules/topology_layout.py`: layout now keyed on scan-derived `compute_scan_id()` hash so saved positions survive interface changes without poisoning unrelated scans (Sprint 2)
- Topology map segment pill colours now reflect `NetworkSegment.colour` from `modules/network_segments.py` (Sprint 2)

### v2.1.3
**Added**
- MetricStore schema v13: `device_classification_overrides` table — user-set type overrides survive all enrichment re-runs permanently
- `modules/device_classifier.py`: `get_all_device_types()` — sorted list of every valid device type label for UI dropdowns
- `inventory_page.py`: `_TypeOverrideDialog` — right-click "Override Device Type…" on any device in the snapshot table; type combobox with Set/Clear/Cancel
- `inventory_page.py`: confidence indicator prefix in Type column (★ user override, ● high ≥70%, ◑ medium 30–70%, ○ low <30%) with coloured foreground and tooltip
- `inventory_page.py`: Classification section in device detail drawer — current type, override badge, confidence level, evidence list, Clear Override button
- `ui/scan_enrichment.py`: override guard in `_apply_dhcp_fingerprints()` and `_on_passive_observation()` — user-set overrides block all automatic enrichment upgrades
- `tests/test_device_classifier.py`: 5 new tests for `get_all_device_types()`

### v2.1.2
**Added**
- `modules/network_segments.py` — `NetworkSegment` dataclass, `auto_detect_segments()`, `classify_device_segment()`, `merge_segments()`; groups scan devices into colour-coded /24 subnets (Sprint 4)
- MetricStore schema v11: `network_segments` table (CIDR unique, `auto_created` flag, user-editable name/colour)
- `inventory_page.py`: colour-coded segment pill bar above the device table with multi-select filter; Segment `●` column; `_SegmentEditorDialog` for right-click segment editing
- `ui/scan_wiring.py`: segments auto-detected and persisted after every full scan; stored user-defined segments win over auto-detected ones on CIDR conflict
- `tests/test_network_segments.py`: 15 tests covering detection, classification, merge logic, and scaling guard

### v2.1.1
**Fixed**
- `modules/rogue_device.py`: proxy-ARP deduplication — IPs sharing the gateway MAC are collected in `proxy_arp_ips` and excluded from device results so the gateway never appears twice
- `modules/rogue_device.py`: gateway device always classified as `Router / Gateway` via `is_gateway` parameter, chip-OUI heuristic, and consumer-hostname sanity check — misclassification from `Lite-On` OUI or `Playstation 4` hostname resolved
- `ui/scan_enrichment.py`: gateway hostname guard in plugin enrichment loop — plugin client entries whose IP matches the gateway are skipped so the gateway hostname cannot be overwritten
- `ui/scan_enrichment.py`: gateway MAC filtered from `_plugin_enrichments` so the router's own MAC never appears as a client device in enrichment data
- `ui/scan_enrichment.py`: IP-keyed hostname sync (`_apply_mesh_enrichment`) skips the gateway `DeviceInfo` object to prevent the mesh/table-cell sync from overwriting the gateway hostname
- `ui/scan_enrichment.py`: post-enrichment device-type cell sync writes `DeviceInfo.device_type` back to the Devices table for all devices with a known type — guards against the race where the cell was written before `is_gateway` classification ran
- `tests/test_scan_enrichment.py`: regression test for shared-MAC (proxy-ARP) sync — two `DeviceInfo` objects with the same MAC; gateway hostname protected, non-gateway hostname updated

### v2.1.0
**Added**
- `modules/service_mapper.py` — device_type/vendor → `ServiceInfo` list mapping engine; feeds Service Diagnostics and Service Heartbeat (Sprint 2)
- `modules/service_diagnostics.py` — `DiagnosticEngine` with service catalog (Netflix, YouTube, Steam, Xbox, PS5, Disney+, Twitch, Spotify) and failure-layer classification: device → local_network → dns → isp → routing → remote_outage (Sprint 3)
- `modules/service_diagnostics_probes.py` — low-level DNS/TCP/HTTPS/ICMP/traceroute probes used by `DiagnosticEngine` (Sprint 3)
- `workers/service_diagnostics_worker.py` — `ServiceDiagnosticsWorker` QThread wrapping `DiagnosticEngine.run()` (Sprint 3)
- `ui/pages/service_diagnostics_page.py` — Service Diagnostics page in the Monitor section; service picker combobox, traceroute toggle, live probe results with per-layer verdict cards (Sprint 4)
- `DiagnosisPage`: "A service is unreachable" symptom tile — runs `ServiceDiagnosticsWorker`, translates `failure_layer` into a synthetic finding card with plain-English remediation steps (Sprint 5)
- `ServicePage`: "Diagnose →" right-click context menu item — maps the selected service host to a `SERVICE_CATALOG` entry and navigates to `ServiceDiagnosticsPage` with that service pre-selected (Sprint 5)
- `ServiceDiagnosticsPage.set_service(id)` — public method to pre-select a service programmatically and focus the Run button (Sprint 5)
- `tests/test_sprint5_integration.py` — 22 tests covering layer translation, CTA map, `_find_service_id()`, widget state, and `set_service()` pre-selection

**Fixed**
- `ui/scan_enrichment.py`: vendor/type enrichment now populates on first scan — async OUI lookup for Unknown devices without requiring a re-scan (Sprint 1)
- `modules/service_diagnostics_probes.py`: IPv6 address cast to `str` before assignment; `CREATE_NO_WINDOW` guarded with `getattr` for non-Windows platforms; traceroute reach-check now correctly references `result.host` instead of unbound `host` variable

### v2.0.1
**Fixed**
- Sorting any table column no longer crashes with `TypeError` — PyQt6 `Qt.SortOrder` enum now correctly accessed via `.value` before storing to `QSettings`
- `setTextAlignment()` calls in `dhcp_lease_page`, `dns_zone_page`, and `threat_intel_page` now pass the `Qt.AlignmentFlag` enum directly instead of wrapping in `int()`
- All tables using the shared `_table()` helper now auto-size columns to content (`ResizeToContents`) instead of a fixed 120 px default; last column stretches to fill available space
- Network Grade table columns (Dimension, Grade, Your Value, Ideal, Verdict) no longer truncate text

### v2.0.0
**Added**
- `packaging/AppxManifest.xml`: declared `windows.startupTask` (uap5, disabled by default) — enables user-controlled auto-start via Settings → Apps → Startup for Microsoft Store builds
- `app.py`: `--startup-logger` flag — starts the app minimised to the system tray and auto-starts the Network Logger; fired by the Windows startup task when the user opts in

**Changed**
- `ui/system_tray.py`: "Launch at Startup" registry entry now registers `--startup-logger` instead of `--minimised`, so enabling auto-start also begins background logging
- `ui/pages/settings_cards.py`: startup checkbox label updated to reflect that auto-start runs as a background logger

### v1.9.99
**Fixed**
- `ui/header.py`: snap-layout maximize button no longer crashes with `RPC_E_WRONG_THREAD` (0x8001010d) when a native file dialog is open — `_toggle_maximize()` is now invoked via `QMetaObject.invokeMethod` with `QueuedConnection` so it always runs on the Qt main thread
- `app.py`: `tplinkrouterc6u` (Deco hardware plugin dep) is now pre-imported on the main STA thread before any background workers start — eliminates `RPC_E_WRONG_THREAD` crash loop on app restart after a wild chaos run
- `tools/monkey_test.py`: raised `_UNRESPONSIVE_SECS` from 20 s to 45 s — "Update Feeds" on Threat Intel page takes ~26 s on a slow connection; the 20 s threshold caused false-positive test terminations
- Navigation animations and live chart redraws: eliminated a linear memory accumulation where old `FuncAnimation` / `Line2D` objects were never released between redraws

### v1.9.98
**Fixed**
- `ui/pages/cve_page.py`: CVE Tracker now shows an empty state with "Run Scan" CTA when no CVEs are tracked — previously showed a blank page
- `ui/pages/threat_intel_page.py`: added `focus_on_host()` slot to pre-filter the threat feed to a specific IP (called from CVE Tracker cross-navigation)
- `ui/dashboard.py`: About dialog displayed literal `&amp;` entity — replaced with plain `&`

**Changed**
- `ui/pages/cve_page.py`: right-click context menu now includes "Check in Threat Intel" — navigates to Threat Intel page pre-filtered to the selected IP
- `ui/tabs.py`: wired `lookup_threat_intel_for` signal on CVE page to `focus_on_host()` on Threat Intel page with automatic nav jump
- `ui/pages/live_bandwidth_page.py`: removed unused `scan_requested` signal (was defined but never emitted)
- `ui/pages/dns_zone_page.py`: removed unused `scan_requested` signal (was defined but never emitted)

### v1.9.97
**Changed**
- `ui/pages/discover_data.py`: Feature Guide groups reworked by user purpose — `"Advanced"` group eliminated; threat-detection features (Rogue Bridge STP, Broadcast Storm, ARP Spoof Watch, IoT Behaviour Baseline, 802.11 Monitor, DHCP Lease Scanner, Rogue Device Detection, Active Monitors) consolidated into `"Security"`; scheduling and integration tools (REST API, Automation Hooks, Scheduled Scans, MQTT, Config Snapshots, Custom Triggers, Maintenance Windows) into new `"Automation"` group; monitoring infrastructure (Syslog, SNMP Traps, SNMP Device Info, Trend Forecasts) into `"Monitoring"`; utility/visualization tools (Geo Map, Network Doc, IP Calculator, Tools & Wake-on-LAN) into `"Diagnostics"`
- RULE-D2 updated: canonical group mapping is now purpose-based, not nav-placement-based; `"Automation"` replaces `"Advanced"` as a valid group name

### v1.9.96
**Fixed**
- `ui/pages/discover_data.py`: corrected Feature Guide group assignments for 8 entries — Npcap-gated Analysis tools (Rogue Bridge STP, Broadcast Storm, ARP Spoof Watch, IoT Behaviour Baseline, 802.11 Monitor Mode) moved from `"Security"` to `"Advanced"`; Active Monitors moved to `"Monitoring"`; Rogue Device Detection and DHCP Lease Scanner moved to `"Diagnostics"` — group assignments now match the nav section each page lives in

**Changed**
- RULE-D2 in APM instructions updated with canonical Feature Guide group → nav section mapping table

### v1.9.95
**Fixed**
- `tools/test_setup.ps1`: replaced UTF-8 box-drawing characters with ASCII equivalents to prevent PowerShell 5.1 parse error during test harness teardown

**Validation**
- Chaos/stability run (2026-06-10): 10,001 UIA interactions across mild (1,000 iter, seed 1), moderate (3,000 iter, seed 42), and wild (6,000 iter, seed 99) chaos levels — 0 exceptions, 0 crashes; all 62 pages navigable before and after chaos (systematic pre/post both passed)

### v1.9.94
**Changed**
- `ui/pages/home_page.py`: removed theme-chooser banner from the home page
- `ui/header.py`: removed theme cycle button from the top navigation bar
- `ui/widgets/home_session_widgets.py`: merged "Connect your router" and "Connect your modem" Getting Started steps into a single "Connect your hardware" step

**Fixed**
- `ui/pages/inventory_page.py`: Devices page now shows a "Current Devices" snapshot card after a scan — IP, hostname, MAC, manufacturer, type, and risk without requiring hardware plugins; also uses resolved hostname in the event log

### v1.9.93
**Fixed**
- `ui/widgets/coach_mark.py`: added `_HighlightRing` — blue border ring drawn around the target widget while each coach mark step is active, so users can see exactly what to click
- `ui/dashboard.py`: post-scan tour (Steps 2–9) now fires immediately after "Got it" on Step 1, without waiting for scan to complete — tour is reliable regardless of scan outcome
- `ui/dashboard.py`: added Hardware Hub as Step 9 of 9 in the onboarding tour; tour navigates to Overview on completion

### v1.9.92
**Fixed**
- `release.yml`: add `update_release: true` to `softprops/action-gh-release` — prevents "already_exists" failure when a tag is re-pushed or CI is retriggered for an existing release

### v1.9.91
**Fixed**
- `ui/command_palette.py`: command palette now opens non-modally (`show()` instead of `exec()`) — clicking anywhere outside the palette dismisses it; app is no longer locked while the palette is open
- `ui/widgets/page_header.py`: `_HelpPopover.show_at()` now clamps position to `screen.availableGeometry()` so the help popover never renders partially off-screen near screen edges
- Resolved 100+ CodeQL code-scanning alerts across `modules/`, `workers/`, `tools/`, and `ui/` — empty `except` blocks documented, unused variables removed, URL-substring patterns replaced with `urlparse` checks
- Test suite: eliminated intermittent `STATUS_STACK_BUFFER_OVERRUN` heap corruption caused by unparented `QTimer.singleShot()` in `__init__` and Qt widgets deleted by Python GC instead of `deleteLater()`
- CI pipeline: ruff (F401/F811/F841), mypy, pip-audit all now pass as Step 1 of the commit gate; CVE findings in dependencies resolved

**Changed**
- `tools/monkey_test.py`: `_dismiss_blocking_dialogs()` detects Windows common file dialogs (class `#32770`) and dismisses them immediately — eliminates spurious `SetCursorPos` stale-reference exceptions
- `tools/monkey_test.py`: `_act_edit()` strips pywinauto key-sequence special characters before `type_keys()` — eliminates `KeySequenceError` on port-number fields
- `tools/monkey_test.py`: default `mem_limit_mb` raised 800 → 1500 MB to match observed wild-chaos peak RSS
- `tplinkrouterc6u` dependency updated to `~=5.22`
- 9h / 12h / 24h chaos test bat launchers added with ready-to-paste analysis prompt

**Security**
- pip-audit CVE findings resolved; `requirements.txt` updated to patched versions

**Validated**
- 9-hour overnight chaos run: 10,001 UIA interactions across mild / moderate / wild chaos levels; zero application crashes; all 61 pages pass systematic pre/post coverage; app confirmed production-stable — Microsoft Store submission ready

### v1.9.90
**Fixed**
- `ui/command_palette.py`: command palette now opens non-modally (`show()` instead of `exec()`) — clicking anywhere outside the palette dismisses it; app is no longer locked while the palette is open
- `ui/command_palette.py`: app-level `installEventFilter` in `showEvent` / `removeEventFilter` in `hideEvent` so outside-click detection fires correctly in non-modal mode
- `ui/widgets/page_header.py`: `_HelpPopover.show_at()` now clamps position to `screen.availableGeometry()` so the help popover never renders partially off-screen near screen edges
- `tests/test_monkey_test.py`: marked `pytest.mark.monkey` and excluded from CI `addopts` — pywinauto not available in GitHub Actions; run locally with `pytest -m monkey`
- `tools/monkey_test.py`: dependency checks now raise `ImportError` instead of `sys.exit()` when imported without `pywinauto`, allowing graceful `pytest.skip()` in tests
- `tools/monkey_test.py`: `_dismiss_blocking_dialogs()` now detects Windows common file dialogs (class `#32770`) and dismisses them immediately with localised cancel-button labels (English + Swedish) — eliminates spurious `SetCursorPos` stale-reference exceptions caused by Browse… dialogs staying open across iterations
- `tools/monkey_test.py`: `_act_edit()` strips pywinauto key-sequence special characters (`+^%~(){}`) from generated text before calling `type_keys()` — eliminates `KeySequenceError` on port-number and address input fields

**Changed**
- APM instructions updated: Roadmap / backlog section removed — there is no active backlog; monkey/chaos tests explicitly documented as user-initiated only, never part of commit gate
- APM instructions and README synced with current codebase: removed phantom widget entries, added `ui/app_settings.py`, `ui/guided_tour.py`, `ui/onboarding.py` to layout table, documented `monkey` pytest marker
- `tools/monkey_test.py`: default `mem_limit_mb` raised from 800 → 1500 MB — matches observed peak RSS for a 6,000-iteration wild-chaos session; prevents false-positive memory warnings on standalone invocations

**Validated**
- 9-hour overnight chaos run (June 2026): 10,001 UIA interactions across mild (1,000 iter), moderate (3,000 iter), and wild (6,000 iter) chaos levels with seeds 1 / 42 / 99; zero application crashes; all 16 exceptions caught were test-harness artefacts (Windows file dialog stale references and pywinauto key-sequence syntax — both fixed above); systematic coverage of all 61 pages passed identically before and after the chaos run. Application confirmed production-stable; Microsoft Store submission ready.

### v1.9.89
**Added**
- `tools/monkey_test.py` — pywinauto UIA + psutil chaos/monkey harness; `--source`, `--connect`, and exe-path modes; mild/moderate/wild chaos levels; spatial + glyph titlebar blacklist; memory/CPU health monitor; screenshot on crash; seed-reproducible runs
- `tests/test_monkey_test.py` — 11 unit tests covering import, `Config`, `Stats`, `History`, blacklist logic, and CLI smoke test; marked `pytest.mark.monkey` — excluded from CI by default, run locally with `pytest -m monkey`
- `requirements-dev.txt` — documents `pywinauto`, `psutil`, and `Pillow` as dev-only dependencies

### v1.9.88
**Added**
- `ui/widgets/diagnostic_card_widget.py` — `render_card_widget()` extracted from `modules/diagnostic_card.py` to eliminate PyQt6 dependency in the module layer (ARCH RULE 1)
- `tests/test_metric_store_queries_metrics.py` — 14 behavioural tests for `_MetricsQueriesMixin` (RTT, speed test, CVE, alerts, modem, mesh, plugin log)
- `tests/test_metric_store_queries_uptime.py` — 12 behavioural tests for `_UptimeQueriesMixin` (state IPs, uptime %, uptime table, device state history, device events)

### v1.9.87
**Fixed**
- `report_exporter.py`: removed phantom `save_nmap_report` from `__all__` (never existed); `credentialed_scan_helpers.py`: replaced non-existent `run_ssh_commands` export with actual private names
- `speed_tester_backends.py`: SSL shim now sets `minimum_version = TLSv1_2`, blocking TLSv1/TLSv1.1 (CodeQL `py/insecure-protocol`)
- `network_log_writer.py`: host-presence check converted from `in` operator to set superset `>=` to eliminate CodeQL `py/incomplete-url-substring-sanitization` false positive
- `report_isp.py`: implicit three-way string concatenation in list wrapped in parentheses to silence CodeQL `py/implicit-string-concatenation-in-list`
- `test_source_encoding.py`: regex character-class patterns for Windows-1252 curly quotes fixed — ASCII `''""` inside single-quoted raw strings silently dropped the quote chars from the class; now uses Unicode escapes `‘’“”`
- `debug_launch.py`: log file registered with `atexit` to ensure closure even on exception (CodeQL `py/file-not-closed`)
- `dashboard.py`: removed unused `n_findings` variable; empty `except` block now logs at DEBUG level instead of silently passing

**Changed**
- README Quality section updated: test count corrected from "1 550+" to "3 064+ across 154 test files"

### v1.9.86
**Fixed**
- `scan_wiring.py`: `AMBER_BG` / `RED_BG` `NameError` crash on internet exposure scan results
- `hub_helpers.py`: stale "Plugin" nav item after settings reset — `_is_temp_artifact` now catches `pytest-of-` temp paths via case-insensitive match regardless of file existence
- `hardware_integration_page.py`: "How to write a plugin script" guide moved to a dedicated **Write a Plugin** tab, giving it full vertical screen estate

**Added**
- Settings → Maintenance: **Skip all guided hints** button marks all 7 coach-mark keys as seen in one click

### v1.9.85
**Changed**
- `ui/onboarding.py` (Sprint H11): rewrote 9-step sequence to value-first order — scan fires on step 1 (Overview), step 2 shows real device list, steps 4–5 show Speed Test and Logger already running; old shell-orientation steps (nav rail, breadcrumb, health badge) removed
- `ui/onboarding.py`: `_step1_fire_scans()` replaces `_fire_background_scans()` — scan + speed test (500ms) + logger (1s) all start at step 1, steps 2–9 display results of those already-running processes
- `ui/onboarding.py`: step 8 (Ctrl+K) stays on Home with `next_enabled_immediately=True` — user has page context before the palette is introduced
- `tests/test_onboarding.py`: fully rewritten to validate new step sequence, nav labels, auto-action placement, and coach mark suppression

**Added**
- `docs/ONBOARDING-VISUAL-FIX-PLAN-V3.md` — comprehensive visual fix plan: screenshot audit, Apple-level acceptance criteria, sprint J1–J5 scope for home page surgery and empty state polish

### v1.9.84
**Fixed**
- `ui/onboarding.py` step 6 (Network Grade): tile grid now shows immediately instead of the "Scan" CTA — `_auto_grade()` calls `_show_tiles()` + `set_scanning(True)` before emitting `scan_requested`
- `ui/onboarding.py` step 7 (Logger): replaced three broken spotlight targets (`_sources_frame`, `_chk_autostart`, `_outage_table`) that resolved to `None` with `_sources_bar` and `_table` which both exist
- `ui/pages/speed_test_page.py`: empty-state "Run Speed Test →" CTA now hides while a test is in progress (`_hist_stack` switches to table view on `_run_test()`)

**Added**
- `ui/pages/log_hub_page.py`: `self._sources_bar` attribute exposes the source-toggle bar widget for spotlight targeting
- `ui/pages/home_page.py`: hardware nudge bar (`_hw_nudge_bar`) shown after onboarding completes until first hardware plugin is configured; dismissible; auto-hides via `on_hardware_added()`

### v1.9.83
**Added**
- `_HelpPopover` in `ui/widgets/page_header.py` now shows a three-section layout: "What it does" (from `_PAGE_HELP`), up to two usage tips from the page's `hidden` tips list, and global keyboard shortcuts (Ctrl+K, Ctrl+F, Esc) — wired to every page header via `_proactive_wire_page_help_btns()`

**Changed**
- `_wire_page_help_btn()` in `ui/nav/builder.py` now passes `hidden` tips to `set_help()` so the ? popover shows contextual tips per page
- `ui/help_tab.py` "What's New" section updated to reflect H9 changes

**Removed**
- Quick Tips card (`_tips_card`) removed from `HomePage` — keyboard shortcut hints are now surfaced via the ? button on every page header; `home/tips_dismissed` QSettings key no longer written

### v1.9.82
**Added**
- `_recurring_intro_card` on `HomePage` — one-time "Home page upgraded" banner shown when recurring mode activates for the first time (5th scan), explaining the layout change; dismissed with × and persisted via `home/recurring_mode_intro_shown`
- `_setup_complete_card` on `HomePage` — celebration card replacing `GettingStartedCard` once all 6 setup steps are done; two CTAs: "Explore features →" (Feature Guide) and "View this week's summary →" (Overview)
- `completion_done` signal on `GettingStartedCard` — emitted 2 s after all steps complete; parent handles card swap and sets `setup/all_done`
- `FreshnessStrip.update_logger_tooltip()` — enriches the Logger pill tooltip with "logging since X" when logger is active
- Logger "since" tracking in `_HomeDataMixin.set_monitor_pills()` — records `_logger_active_since` on first activation and passes elapsed time to the Logger pill tooltip

### v1.9.81
**Added**
- Contextual coach marks — 5 per-feature one-shot overlays keyed to individual `coach/*` QSettings flags (independent of global first-run onboarding): Log Hub sources bar, Network Grade ring, Diagnosis symptom tiles, Home page monitoring pills, Devices table right-click hint
- `tests/test_coach_marks.py` — 22 tests covering flag hygiene, skip conditions, and method presence for all 5 coach marks

### v1.9.80
**Changed**
- `overview_page.py` — tile grid wrapped in `QStackedWidget`; shows `EmptyStateCard` on first launch instead of 12 empty tiles
- `snmp_trap_page.py` — custom inline empty state replaced with `EmptyStateCard` ("Waiting for SNMP traps" + "Configure SNMP →")
- `wifi_monitor_page.py` — frame table wrapped in `QStackedWidget`; shows `EmptyStateCard` with "Start Monitoring →" CTA before first capture
- `geo_map_page.py` — map + IP table wrapped in `QStackedWidget`; shows `EmptyStateCard` with "Scan to discover IPs →" before any IPs are plotted; `scan_requested` signal wired in `app.py`
- `timeline_page.py` — event feed wrapped in `QStackedWidget`; shows `EmptyStateCard` with "Run a scan →" before any events exist; `scan_requested` signal wired in `app.py`
- `speed_test_page.py` — plain-label empty state upgraded to `EmptyStateCard` ("No speed tests recorded yet" + "Run Speed Test →")
- `trend_page.py` — analysis content wrapped in `QStackedWidget`; shows `EmptyStateCard` with "Start Logger →" before first trend result; `scan_requested` signal wired in `app.py`

### v1.9.79
**Added**
- `tests/test_diagnosis_page.py` — verify_step rendering tests, focused-mode DiagnosisWorker parameter

**Changed**
- Diagnosis finding cards now render `verify_step` text and a "Verify this fix" button that runs a focused re-check
- `DiagnosisWorker` accepts `focused_on` parameter to run only checks relevant to a specific finding headline
- Post-scan sheet dismissal is now per-scan (reappears on next scan); `FreshnessStrip` shows `[N findings]` link to re-open the sheet
- Diagnosis page shows an amber inline warning when Network Logger has less than 2 hours of data

### v1.9.78
**Added**
- `tests/test_getting_started_card.py` — step order, `_checklist_states` keys, `notify_hw_detected` and pill-type assertions
- `tests/test_log_hub_empty_state.py` — `start_logger_requested` signal, content stack page count, CTA button presence

**Changed**
- Getting Started card step order: scan is now first, hardware steps second (with updated copy emphasising what you lose without them), logger added as step 6
- Hardware steps renamed: "Connect your router" and "Connect your modem" with value-focused subtitles
- `WelcomeOverlay` slide 2 ("Discover & protect") now mentions connecting router and modem
- FreshnessStrip monitoring pills converted from `QLabel` to `QPushButton` (flat); clicking an inactive pill navigates to the relevant page; on/off tooltips added
- After a hardware plugin is registered, the Getting Started card updates immediately without a restart
- When `hw_detect_worker` detects a ZTE modem or Deco router on the network, the corresponding Getting Started card step shows an amber "detected nearby" indicator
- Log Hub empty state replaced with `EmptyStateCard` + "Start Network Logger →" CTA; page switches to the live table as soon as any source is enabled
- Diagnosis page shows a dismissible amber warning when the Network Logger has never been started

### v1.9.77
**Changed**
- Architecture documentation corrected to match actual codebase: 7 missing `ui/` files added (`header.py`, `tabs.py`, `tabs_helpers.py`, `tabs_scan.py`, `tabs_network.py`, `tabs_diag.py`, `tabs_recon.py`), 2 duplicate entries removed, `settings_cards.py` and `settings_appearance.py` descriptions fixed, non-existent `mesh_worker.py` and `zte_worker.py` removed from workers layout

### v1.9.76
**Changed**
- Settings > Appearance: theme selector replaced with visual mini swatch cards (128×90 px each) showing a scaled colour preview of each theme — nav bar, sidebar, content area, card and accent colours
- Theme banner on first run and header theme-cycle button now apply themes instantly via `apply_theme()` instead of persisting only and asking for a restart
- Header theme toggle button icon updates immediately to reflect the newly selected theme

### v1.9.75
**Fixed**
- `settings_cards.py`: Configuration Status chips were rendering black — `_chip_style()` returned plain strings instead of f-strings so colour variable names were never interpolated
- `hub_helpers.py`: Plugin instances stored with stale PyInstaller `_MEI` temp-dir paths are now resolved to the stable `AppData/plugins/` copy on load; added `_resolve_path()` helper and updated `_load_instances()` migration to fix paths before saving
- `hardware_integration_page.py`: Credential dialog was silently skipped when re-registering a plugin after a settings reset (old keyring entry still present); new registrations now always show the dialog
- `deco_client.py`: Deco XE75 authentication now falls back to HTTPS with `verify_ssl=False` when HTTP times out (newer firmware redirects API traffic to HTTPS); default timeout raised to 30 s
- `deco_plugin.py`: `_fmt_err` classified timeout errors inside auth calls as `AUTH:` — network keywords now checked before auth keywords so "Read timed out" errors show correctly as "Cannot reach the device"
- `plugin_page_mixin.py`: `_reload_section` called `load_section` with wrong kwarg `on_navigate=` (correct: `on_click=`); silently swallowed `TypeError` meant the Extend flyout was never updated after adding a plugin
- `credential_dialog.py`: Dialog positioned relative to the page widget inside a scroll area, causing it to appear off-screen; now uses `QApplication.activeWindow()` so it always centers on the main window

### v1.9.74
**Added**
- `ui/styles.py`: `apply_theme()`, `apply_accent_override()`, `get_theme_manager()`, `get_app_qss()` — live theme switching without restart
- `ui/dashboard.py`: `_on_theme_changed()` slot re-applies MAIN_STYLE cascade, refreshes all stack pages and nav rail
- `ui/nav/rail.py`: `refresh_theme()` on `_RailButton`, `_FlyoutItem`, `_FlyoutPanel`; `paintEvent` reads live module globals
- `ui/widgets/page_header.py`: `refresh_theme()` on `PageHeaderBar` and chips
- `tests/test_themes.py`: `TestApplyTheme` class — 8 new tests for live theme API

**Changed**
- Settings → Appearance: theme and accent changes now apply immediately (no restart required)
- `app.py`: QMenu/QToolTip QSS injected via `get_app_qss()` so it reflects the active theme at runtime

### v1.9.73
**Added**
- `ui/nav/builder.py` — `_proactive_wire_page_help_btns()` wires the `?` help button on every page at startup rather than lazily on first visit (F3)

**Changed**
- `ui/help_tab.py` — keyboard shortcuts table expanded to 15 entries with navigation, scan, app, table, and macOS platform variants (F2)
- `ui/pages/settings_cards.py` — keyboard shortcuts card expanded to 11 entries with grouped categories (F2)
- `ui/pages/settings_page.py` — settings search now performs full-text match against per-card keyword strings in addition to card titles; typing "smtp", "dark", or "ctrl" now surfaces the relevant card (F4)
- `app.py` — fixed `_home_automation_page` → `_ha_page` and `_trigger_builder_page` → `_trigger_page` in E2 scan_requested wiring

### v1.9.72
**Added**
- `modules/metric_store_queries_uptime.py` — `_UptimeQueriesMixin` with 5 uptime/device-state query methods (E3 split)
- `modules/metric_store_queries_metrics.py` — `_MetricsQueriesMixin` with 10 RTT/speed/CVE/alert/modem/mesh query methods (E3 split)
- `tests/test_metric_store_queries_split.py` — 15 tests covering E3 split composition and behaviour
- `ui/styles.py` — "Abyss" WCAG AA high-contrast theme: true black backgrounds, steel teal accent, all text tokens ≥ 4.5:1 contrast ratio (F1)

**Changed**
- `modules/metric_store_queries.py` — reduced from 619 to 299 lines; now a facade inheriting `_UptimeQueriesMixin` + `_MetricsQueriesMixin` (E3)
- `tests/test_worker_lifecycle.py` — added `SpeedTestWorker`, `CombinedDiscoveryWorker`, and `BandwidthWorker` full start/stop lifecycle tests (E1)
- `ui/header.py` — added "Abyss" icon `◼` to theme toggle cycle (F1)
- `ui/pages/home_page.py` — added "Abyss" entry to theme picker strip (F1)

### v1.9.70
**Added**
- `modules/lab_scenarios.py` — 6 new lab scenarios: Measure DNS Resolver Speed, Find an Open Port, Detect a DHCP Conflict, Measure Network Jitter, Identify Device Manufacturers, Read a Network Topology Map (Sprint B2; total now 10 scenarios)
- `ui/pages/lab_mode_page.py` — `_run_port()` and `_run_dhcp()` scan runners added to `_LabScanWorker` for new `"port"` and `"dhcp"` scan types

**Changed**
- `ui/pages/home_page.py` — monitoring pills (ARP Watch, DHCP Watch, Broadcast Storm, Network Logger) now carry plain-English `setToolTip()` text explaining what each monitor does and how to enable it (Sprint C1)
- `ui/pages/home_page.py` — "Monitoring is off" nudge replaced with a clearer label + "▶ Start Network Logger" button that emits `start_monitoring_requested` (Sprint C1)
- `ui/widgets/alert_drawer.py` — "WHAT TO DO" section added to the drawer body with per-alert-type actionable fix text for PORT_SCAN, ARP, DHCP, DEVICE, HOST_DOWN, SERVICE_DOWN, RTT_THRESHOLD, THREAT_INTEL, CVE, BANDWIDTH alerts; "Fix this →" primary button replaces "Go to page →" when fix text is available (Sprint C3)

### v1.9.69
**Added**
- `ui/widgets/empty_state_card.py` — reusable `EmptyStateCard` widget with icon, "What this page shows", "Why it matters", and CTA button (Sprint A2)
- `data/glossary.json` — 30 plain-English definitions for network terminology (ARP, STP, Jitter, DNS, CVSS, DHCP, Latency, etc.) (Sprint A4)
- `ui/widgets/jargon_tooltip.py` — `JargonTooltip` QLabel subclass: underlines a term and shows its definition on hover (Sprint A4)
- `tests/test_empty_state_card.py` — widget construction, signal emission, and content tests
- `tests/test_jargon_tooltip.py` — glossary file validation and widget behaviour tests

**Changed**
- `ui/pages/inventory_page.py`, `uptime_page.py`, `cert_page.py` — bare empty states replaced with `EmptyStateCard` (informative what/why copy and CTA) (Sprint A2)
- `ui/pages/security_overview_page.py` — findings section empty message replaced with structured "What this shows / Why it matters" widget with Threat Intelligence navigation link
- `ui/pages/overview_page.py` — CTA bar description updated to explain what the scan discovers; grade panel dimension buttons enriched with glossary tooltip definitions
- `ui/pages/protocol_viz_page.py` — protocol selector button tooltips enriched with glossary definitions; `select_protocol(key)` public API added (Sprint B1)
- `ui/pages/lab_mode_page.py` — `explore_protocol = pyqtSignal(str)` added; "See how X works →" button on each scenario card navigates to Protocol Visualizer pre-selected to the relevant protocol (Sprint B1)
- `ui/pages/diagnosis_page.py` — `JargonTooltip` chip shown on finding cards for DNS, Jitter, STP, Packet Loss categories; `category` extracted at card-build time
- `modules/lab_scenarios.py` — `LabScenario.protocol` optional field added; all 4 built-in scenarios populated (ARP, DNS, STP)
- `app.py` — `explore_protocol` signal from `LabModePage` wired: navigates to Protocol Visualizer and pre-selects the protocol

**Fixed**
- `ui/tabs_recon.py` — `@pyqtSlot("QPoint")` replaced with `@pyqtSlot(QPoint)` (string-form type resolution fails in PyQt6 without QPoint import; crashed Dashboard on startup)
- `tests/test_colours.py` — `test_semantic_colours_match_ui_styles` now compares against the Arctic Clean palette directly (not the active theme) so the test passes regardless of which theme is persisted in QSettings

### v1.9.68
**Added**
- `modules/plugin_registry.py`: Windows MAX_PATH guard — `install_plugin()` truncates filename stems to 80 chars before writing (PB-12)
- `tests/test_hardware_integration.py`: 8 new tests covering `CONFIG_SCHEMA` end-to-end — AST extraction, configure button visibility, widget types (int/bool/str), config save roundtrip, worker poll-interval override, and config kwarg injection into `get_status()` (PB-7)
- `ui/widgets/hub_helpers.py`: `CONFIG_SCHEMA` commented example added to hardware plugin template so the New Plugin wizard shows users how to declare a typed config schema

### v1.9.67
**Fixed**
- `notification_channels.py`: Pushover, ntfy, and Telegram delivery failures now reported in alert history (`_deliver_pushover_tracked`, `_deliver_ntfy_tracked`, `_deliver_telegram_tracked`); removed optimistic mark-delivered and dead untracked imports from router
- `metric_store_queries.py`: `query_uptime_table()` reduced from N+1+N×M queries to 1+len(windows) GROUP BY queries; `query_uptime_pct()` now returns `None` (not `100.0`) when no samples exist; uptime page and history page handle `None` with `"—"` placeholder
- `metric_store_queries.py`: replaced `SELECT *` with explicit column lists in `list_cve_lifecycles()`, `get_unacked_alerts()`, `get_recent_alerts()`
- `home_page.py`: un-parented `QTimer.singleShot(2500, banner.hide)` replaced with parented `QTimer(banner)` to prevent crash on early widget deletion
- `maintenance_window.py`: documented UTC requirement for `start_ts`/`end_ts` in `is_currently_active` docstring
- `test_source_encoding.py`: extended mojibake detection to cover 4-byte emoji sequences (`ðŸ` prefix, e.g. 🌙→ðŸŒ™)
- Added RULE-ENC2 — agents must re-read files before editing when an external process may have modified them since last read
- `requirements.txt`: bumped `pytest-cov` from ~=5.0 to ~=7.1 (Dependabot PR #8)
- Resolved 30 CodeQL code-scanning alerts: removed unused imports across 7 modules, replaced empty `except` blocks with `contextlib.suppress()` or `logging.debug()` calls, removed dead `disabled` variable in Windows user parser, added `__all__` for intentional re-exports

### v1.9.66

**Changed**
- `ui/dashboard.py`: 6,472→**1,967 lines** (−4,505 total across Sprints 16–19) — three further mixin extractions complete the STABILITY_PLAN.md final goal; inherits `ScanResultMixin`, `AppHeaderMixin`, `TabBuilderMixin`, `_NavBuilderMixin`, `_MonitorStateMixin`, `_PluginPageMixin`, `QMainWindow` (Sprint 19)
- `ui/scan_wiring.py`: 1,279→676 lines — inherits `ScanEnrichmentMixin`; 12 duplicate enrichment methods removed (Sprint 18)
- `ui/scan_enrichment.py`: 634→1,230 lines — `_apply_mesh_enrichment`, `_regroup_m1_by_satellite`, `_filter_m1_by_nl`, and 7 M1 table helpers added from `dashboard.py` (Sprint 18)
- `ui/tabs_diag_extra.py`: 749→346 lines — `_DiagExtraTabsMixin` inheritance wired; `_DiagTabsMixin` now inherits `(_DiagExtraTabsMixin, _LoggerTabMixin)` (Sprint 16)
- `ui/nav/__init__.py`: re-exports `_NavBuilderMixin` and `_AUTO_HELP_PAGES` from new `builder.py` (Sprint 19)

**Added**
- `ui/tabs_recon.py` — `_ReconTabsMixin`: 29 security-audit recon tab builders (SYN, UDP, OS, Risk, CVE, Exposure, Credentialed, Discovery, SMB, Plugins, Private Endpoint); wired into `TabBuilderMixin` (Sprint 18)
- `ui/nav/builder.py` — `_NavBuilderMixin`: all nav structure building, runtime switching, command palette, pin management, page-visit tracking (Sprint 19)
- `ui/monitor_state.py` — `_MonitorStateMixin`: verdict/badge/pill display, KPI tiles, `VerdictPanel`, `RiskBadge`, `_color_for_level` (Sprint 19)
- `ui/plugin_page_mixin.py` — `_PluginPageMixin`: plugin page lifecycle, hardware auto-detect, integration banner, `_launch_modules_impl` (Sprint 19)

### v1.9.65

**Changed**
- `ui/tabs_diag.py`: logger tab + retention helpers extracted to `ui/tabs_logger.py` (`_LoggerTabMixin`); `tabs_diag.py` 1,182→448 lines (S15)
- `ui/pages/home_page.py`: 2,238→1,128 lines — `_MiniCard` + `_AlertRow` moved to `home_widgets.py`; all data handlers extracted to `_HomeDataMixin` in `home_data_mixin.py`; `_HomeSuggestionsMixin` wired (S15)

**Added**
- `ui/tabs_logger.py` — `_LoggerTabMixin`: Network Logger tab builder, logger start/stop handlers, live-challenge handlers, retention helpers (Sprint 15)
- `ui/pages/home_data_mixin.py` — `_HomeDataMixin`: all data update and public slot methods for `HomePage` (Sprint 15)

### v1.9.64

**Added**
- `tests/test_port_scanner.py` — 15 tests for `modules/port_scanner.py` (RULE-T1 compliance)
- `tests/test_report_pdf.py` — 6 tests for `modules/report_pdf.py` (RULE-T1 compliance)
- `tests/test_module_coverage_gate.py` — CI gate: every `modules/*.py` must have a `tests/test_*.py`; all 70 modules now covered (S9-4)
- `tests/test_codeql_prevention.py`: `test_no_hardcoded_hex_in_ui_files` — AST-based RULE-AH3 enforcement gate (S10-4); catches raw hex string literals in `ui/` before CI

**Changed**
- `NetSentinel.spec`: 13 Sprint 13 new modules registered in `hiddenimports` (RULE-B1 compliance — `ui.scan_enrichment`, `ui.tabs_analysis`, `ui.tabs_diag_extra`, `ui.pages.discover_data`, `ui.pages.help_content`, `ui.pages.home_suggestions`, `ui.pages.notif_extra_channels`, `ui.pages.settings_appearance`, `ui.widgets.device_detail_pane`, `ui.widgets.device_detail_panels`, `ui.widgets.kpi_bar`, `ui.widgets.modem_signal_panel`, `ui.widgets.overview_tile_monitor`)
- `tests/test_module_loc.py`: 12 Sprint 13 new UI files added to `KNOWN_LARGE_UI_FILES` LOC budget; `dashboard.py` budget tightened from 6,740 → 6,672

### v1.9.63

**Added**
- `ui/tabs_analysis.py` — `_AnalysisTabsMixin`: IPv6, Cloud Metadata, Root Cause Correlator, IoT Baseline, and Benchmark tab builders extracted from `ui/dashboard.py`
- `ui/widgets/kpi_bar.py` — `_KpiBarMixin`: KPI bar widget + update logic extracted from `ui/dashboard.py`
- `ui/pages/discover_data.py` — `_FEATURES` list and `_GROUPS_ORDER` data extracted from `ui/pages/discover_page.py` (page reduced from 1,360 → 229 lines)
- `ui/pages/help_content.py` — `_PAGE_HELP` dict extracted from `ui/help.py`
- `ui/pages/home_suggestions.py` — `_HomeSuggestionsMixin` extracted from `ui/pages/home_page.py`
- `ui/pages/settings_appearance.py` — `_SettingsAppearanceMixin` extracted from `ui/pages/settings_cards.py`
- `ui/pages/notif_extra_channels.py` — `_NotifExtraChannelsMixin` extracted from `ui/pages/notif_channel_panels.py`
- `ui/scan_enrichment.py` — `ScanEnrichmentMixin` extracted from `ui/scan_wiring.py`
- `ui/widgets/overview_tile_monitor.py` — monitoring tile classes extracted from `ui/widgets/overview_tile.py`
- `ui/widgets/device_detail_panels.py` — `_ModemDetailPanel`, `_RouterDetailPanel` extracted from `ui/widgets/hub_card.py`
- `ui/widgets/device_detail_pane.py` — device detail widgets extracted from `ui/pages/inventory_page.py`
- `ui/widgets/modem_signal_panel.py` — `_ModemSignalPanelMixin` extracted from `ui/pages/speed_test_page.py`
- `ui/tabs_diag_extra.py` — `_DiagExtraTabsMixin`: MTR, advanced tools, logger handlers extracted from `ui/tabs_diag.py`

**Changed**
- `ui/pages/discover_page.py` — 1,360 → 229 lines; `_FEATURES` data moved to `ui/pages/discover_data.py`
- `NetSentinel.spec` — 13 new `hiddenimports` entries for all extracted modules
- `tests/test_module_loc.py` — LOC budgets tightened for 12 split files; 14 new file entries added

### v1.9.62

**Added**
- `tests/test_colour_inventory.py` — per-file hardcoded-hex budget tables for 63 UI files + 7 module files; locks the S10-1 baseline for purge sprints (S10-1)
- 18 new Tier 2 scan/detection module test files — `test_arp_monitor.py`, `test_bandwidth_monitor.py`, `test_cloud_metadata.py`, `test_dns_correlator.py`, `test_dns_zone_scanner.py`, `test_ha_detector.py`, `test_internet_exposure.py`, `test_os_fingerprint.py`, `test_port_scanner_module.py`, `test_process_monitor.py`, `test_rogue_device.py`, `test_smb_enumerator.py`, `test_snmp_poller.py`, `test_storm_analyser.py`, `test_stp_detector.py`, `test_syn_scanner.py`, `test_threat_intel.py`, `test_wifi_scanner.py` — 140 new tests (S9-2)

**Changed**
- `ui/dashboard.py`, `ui/tabs.py`, `ui/header.py`, `ui/app_settings.py` — removed dead flat-nav mode system: `_nav_mode`, `_nav_goto_label`, `_update_mode_pill`, `_cycle_mode`, `_set_mode`, hidden `_rail_mode_btn`; `_nav_go_to` simplified to direct rail delegate (S13-5c)

### v1.9.61

**Added**
- `ui/tabs.py` — `TabBuilderMixin` extracted from `dashboard.py`; all scan, log, network, and tools tab content builders (S13-1; dashboard.py 9,776 → 6,540 lines)
- `ui/header.py` — `AppHeaderMixin` extracted from `dashboard.py`; top bar construction + frameless-window logic (S13-3)
- `ui/app_settings.py` — `save_settings()`, `restore_settings()`, `center_on_screen()` extracted from `dashboard.py` (S13-4)
- `ui/help.py` — `build_help_tab()` extracted from `dashboard.py`; Help & Shortcuts page builder (S13-2)
- `ui/widgets/hub_helpers.py` — pure data-persistence and utility helpers extracted from `hub_card.py` (S15-2; hub_card.py 2,209 → 1,665 lines)
- `tools/startup_profile.py` — stage-by-stage startup timing script (S7-2)

**Changed**
- `tools/debug_launch.py` — log rotation: keeps last 5 timestamped launch logs; `netsentinel_debug.log` always points to latest (S7-3)
- `CLAUDE.md` — added Step 0 (static checks) to commit gate; expanded version history table with sprint summaries (S4-2, S8-3)
- `tests/CLAUDE.md` — added mock-patch canonical locations guide (S15-3)
- `tests/test_module_loc.py` — LOC budgets tightened for all Sprint 6 extracted files

### v1.9.60

**Added**
- `modules/metric_store_schema.py` — DDL, schema version, column migrations, and all dataclasses extracted from `metric_store.py` (S2-1 split)
- `modules/metric_store_queries.py` — `MetricStoreQueryMixin` with all read/query methods extracted from `metric_store.py` (S2-1 split)
- `modules/report_html.py` — CSS template and HTML generation helpers extracted from `report_exporter.py` (S2-2 split)
- `modules/report_pdf.py` — `save_pdf_report()` with weasyprint/headless-browser cascade extracted from `report_exporter.py` (S2-2 split)
- `modules/utils_net.py` — `get_network_info()`, `get_dhcp_info()`, `get_interface_details()` extracted from `utils.py` (S2-3 split)
- `modules/utils_platform.py` — `get_ipv6_devices()`, `ping_sweep_ipv6()` extracted from `utils.py` (S2-3 split)
- `tests/test_metric_store_schema.py`, `test_metric_store_queries.py`, `test_metric_store_concurrency.py` — 37 new tests covering schema, queries, and concurrent-write safety (RULE-T1)
- `tests/test_utils_net.py`, `test_utils_platform.py`, `test_report_html.py` — 27 new tests for split modules (RULE-T1)
- `tests/test_worker_lifecycle_full.py` — lifecycle tests for `HwDetectWorker`, `PluginWorker`, `WiFiMonitorWorker`; `_running`-flag audit (RULE-T2, S5-2)

**Changed**
- `modules/metric_store.py`: 1,673 → 623 lines; inherits `MetricStoreQueryMixin`; WAL checkpoint at startup if `-wal` > 50 MB (S6-1); `PRAGMA VACUUM` after schema migration (S6-2); `PRAGMA busy_timeout = 5000` on every connection (S6-3)
- `modules/report_exporter.py`: 1,241 → 716 lines; HTML/PDF logic delegated to split modules; all public names re-exported for backwards compatibility
- `modules/utils.py`: 1,055 → 421 lines; network info and IPv6 scanning delegated to split modules; all names re-exported for backwards compatibility
- `tests/test_module_loc.py`: LOC gate updated — dashboard.py budget tightened to 11,312; 9 new entries for Sprint 4 and previously-untracked large files; test function supports `ui/widgets/` subdirectory paths
- `NetSentinel.spec`: 7 new `hiddenimports` entries for all split modules

### v1.9.59

**Changed**
- `ui/dashboard.py`: 23 `_on_*_result` scan-result handlers extracted to `ui/scan_wiring.py` as `ScanResultMixin`; `Dashboard` now inherits the mixin — dashboard.py reduced from 13,483 → 10,046 lines; 14 orphaned `@pyqtSlot` decorators removed
- `ui/pages/hardware_integration_page.py`: `HubCard`, `_ModemDetailPanel`, `_RouterDetailPanel`, `PipInstallDialog`, and all plugin helper functions extracted to `ui/widgets/hub_card.py` — hardware_integration_page.py reduced 4,055 → 1,701 lines
- `ui/pages/overview_page.py`: all 14 Overview tile classes, `_BaseTile`, `_TILE_CLASSES`, `_DEFAULT_ORDER` extracted to `ui/widgets/overview_tile.py` — overview_page.py reduced 2,536 → 633 lines
- `ui/pages/home_page.py`: `_GradeRing`, `_MiniSparkline`, `_GradeSparkline`, `_EventsTicker`, and grade history helpers extracted to `ui/widgets/home_widgets.py` — home_page.py reduced 3,027 → 2,747 lines
- `NetSentinel.spec`: 4 new `hiddenimports` entries added (`ui.scan_wiring`, `ui.widgets.home_widgets`, `ui.widgets.hub_card`, `ui.widgets.overview_tile`)
- `docs/STABILITY_PLAN.md`: post-Sprint-4 re-audit — 7 new findings (F7–F13), three new plan sections (S13/S14/S15), three new architecture principles (P9–P11)

**Fixed**
- Mock patch targets in `test_plugin_health.py`, `test_plugin_resilience.py`, `test_plugin_migration.py`, `test_hub_card_errors.py` updated from `ui.pages.hardware_integration_page.*` → `ui.widgets.hub_card.*` after hub_card extraction
- `ui/pages/overview_page.py`: `_DEFAULT_ORDER` and `_TILE_CLASSES` constants were missing from import after tile extraction — added to import block
- `ui/pages/home_page.py`: BOM character stripped after PowerShell file write caused `ast.parse` to fail in style-token test
- 14 orphaned `@pyqtSlot` decorators in `dashboard.py` removed — one was causing `TypeError: decorated slot has no signature compatible with timeout()` at startup

### v1.9.57

**Fixed**
- `ui/topology_widget.py`: invalid escape sequence (`\ `) in module docstring replaced with raw string — eliminates `DeprecationWarning` in full test run

### v1.9.56

**Fixed**
- Test suite crash (`STATUS_STACK_BUFFER_OVERRUN`) at ~52% run: `QFileSystemWatcher` OS threads in `test_hardware_integration.py` were accumulating without cleanup; fix mocks the watcher and adds explicit `_tick_timer.stop()` + multi-pass `deleteLater()` cleanup
- Removed module-level `QApplication` creation from 7 test files (`test_hardware_integration`, `test_home_page`, `test_mesh_grouping_toggle`, `test_notifications_page`, `test_overview_page`, `test_settings_and_onboarding`, `test_themes`) — conftest.py's session fixture now owns the `QApplication`
- `test_hub_card_errors.py` rewrote widget creation to use factory fixtures with `deleteLater()` cleanup; removed module-scoped `qapp` fixture that duplicated conftest

**Added**
- `tests/test_codeql_prevention.py` — static AST checks for bare `except:` blocks (CodeQL `py/bare-except`) and URL substring comparisons in test files (CodeQL `py/incomplete-url-substring-sanitization`)
- `tests/conftest.py` QSettings isolation fixture (`isolated_settings`, autouse) — each test gets a unique org/app name so QSettings state cannot leak between tests
- `tests/conftest.py` crash logger fixture (`_crash_logger` / `_log_test_name`) — writes test names to `ns_test_crash_log.txt` before each run to identify last test before a process-level crash
- `RULE-WIN3` and `RULE-WIN4` in `CLAUDE.md` — document the Qt test lifecycle rules learned from the crash investigation

### v1.9.55

**Fixed**
- `data/plugin_hashes.json` hashes now computed on LF-normalised content via `_file_hash()` in `modules/plugin_tools.py` — `TestBundledPluginHashSync` was failing on Linux/macOS CI because hashes generated on Windows (CRLF) differed from checkout content (LF)
- `TestBundledPluginHashSync` and `TestVerifySignature.test_verified_when_hash_matches` updated to use `_file_hash()` for cross-platform consistency
- Documented the gap: `.apm/instructions/` are the true sources; `bump_version.py`'s `apm compile` step regenerates `.claude/rules/` from them — manual edits to `.claude/rules/` are overwritten
- Updated `RULE-21-I` in `.apm/instructions/development-rules.instructions.md` (canonical source): "tag" now means the exact four-step sequence: `bump_version.py` → push branch → tag → push tag

### v1.9.54

**Fixed**
- Resolved all open CodeQL alerts: `py/empty-except` comments added in `hardware_integration_page.py`, `dashboard.py`, `plugin_device_page.py`, `plugin_polling_worker.py`, `plugin_tools.py`, `nspkg.py`, `deco_plugin.py`, `zte_plugin.py`
- `py/unnecessary-pass` removed from `plugin_polling_worker.py` `SystemExit` handler
- `py/variable-redefined` fixed in `modules/nspkg.py` (dead `plugin_dest` assignment removed)
- `py/unused-global-variable` removed `_MANIFEST_VERSION` from `modules/nspkg.py`
- Removed `import os` (unused) from all 8 non-credential bundled plugins; regenerated `data/plugin_hashes.json`
- Removed unused imports from `hardware_integration_page.py`, `plugin_tools.py`, `plugin_polling_worker.py`, and all affected test files
- Updated `RULE-21-I`: "tag" now means exactly: `bump_version.py` → push branch → push tag, every time without exception

### v1.9.53

**Fixed**
- `data/plugin_hashes.json`: regenerated after P1-3 edited bundled plugins; stale hashes caused `_start_poll_worker_inst` to silently return early — no plugin produced data on startup
- `ui/pages/hardware_integration_page.py`: added explanatory comments to five bare `except: pass` blocks (CodeQL `py/empty-except` #740–#745)
- `tests/test_plugin_tools.py`: `TestBundledPluginHashSync` regression guard — fails immediately when any bundled plugin is edited without regenerating the hash database

### v1.9.52

**Added**
- `HubCard`: `✎` rename button on every hub card — click to set a new display name inline; nav item label, breadcrumb, pinned set, and command palette all update atomically (P3-4)
- `HardwareIntegrationPage`: `plugin_renamed` signal (path, old_label, new_label) emitted on confirmed rename
- `ui/dashboard.py` `_on_plugin_page_renamed`: handler propagates display-name change to `_nav_label_to_widget`, `_nav_page_to_section`, `_nav_sections["Extend"]` entries, and `_nav_pinned_labels` atomically (P3-4)
- `tests/test_credential_robustness.py` — 8 tests: `_instance_id` determinism and uniqueness; multi-instance independence; credential dialog IP pre-fill; rename registry update; stable key algorithm (P4-4)
- `tests/test_plugin_isolation.py` — 5 tests: module namespace isolation between poll cycles; independent namespaces for concurrent workers; concurrent poll guard (P5-3, P5-4)
- `tests/test_plugin_resilience.py` — 10 tests: backoff interval calculation; backoff reset after success; AUTH-exempt circuit breaker; FILE: error classification; instance-ID keying consistency (P6-1, P6-3, P6-5, P7-5)

### v1.9.50

**Fixed**
- `workers/plugin_polling_worker.py`: replaced `os.environ["NETSENTINEL_PLUGIN_IP"]` with direct module-attribute injection (`mod._NETSENTINEL_INSTANCE_IP`, `mod._NETSENTINEL_INSTANCE_ID`) after `exec_module` — each instance gets its own namespace, zero cross-instance IP pollution (RULE-PL1)
- `ui/pages/hardware_integration_page.py` `_PluginConnectionTester`: injects `_NETSENTINEL_INSTANCE_IP` into the module after `exec_module`; env-var shim kept with proper `finally` restore for backwards-compat
- `plugins/deco_plugin.py`, `plugins/zte_plugin.py`: `_load_credentials()` reads `globals().get("_NETSENTINEL_INSTANCE_IP")` first (correct idiom — `sys.modules[__name__]` fails for modules loaded via `module_from_spec`), then falls back to env var, then `HARDWARE_IP`
- `HubCard`: adds `🔑 Re-enter Password` button shown only on `AUTH:` errors; clicking reopens the credential dialog with current IP pre-filled and restarts the worker on success — no need to delete and re-add a plugin when a password changes (P4-1)
- Credential dialog: saves password to `NetSentinel/plugin/<instance_id>` (per-instance keyring, P4-2) in addition to the legacy `NetSentinel/hardware/<ip>` key; bundled plugins check the per-instance key first
- `ui/dashboard.py`: `_reload_section(name, force_open)` helper consolidates flyout-reload logic previously duplicated across `_on_plugin_page_added` and `_on_plugin_page_removed` (RULE-PL3)
- `ui/dashboard.py` `_on_plugin_page_added`: calls `_nav_rail_go_to(label)` after flyout reload so the new plugin's device page is shown immediately on add (P3-2)
- `workers/plugin_polling_worker.py`: file-missing error now emits `FILE: plugin file not found at <path>` prefix so `_classify_error` can route it to a "Re-import" action (P6-2 prefix)

**Added**
- `tests/test_env_var_isolation.py` — 6 tests: module attribute preferred over env var; env var restored on success and failure; concurrent `exec_module` loads have independent namespaces; worker leaves `os.environ` unchanged; FILE: prefix on missing plugin file

### v1.9.48

**Added**
- `modules/nspkg.py` — `.nspkg` plugin bundle format (ZIP with `plugin.py` + `manifest.json` + optional `icon.png`); `unpack_nspkg()` validates manifest and extracts to AppData/plugins (P3-5)
- Hardware Hub "⬡ Import .nspkg" button — imports a `.nspkg` bundle, verifies manifest, shows unsigned-plugin consent, then calls the normal registration flow
- P2-2 `CONFIG_SCHEMA` support — plugins declare typed config fields (`poll_interval`, `verify_ssl`, etc.); `HubCard` auto-generates a ⚙ config panel; values saved per-instance in QSettings and passed to `get_status(config=…)` on each poll
- Community plugin Browse tab (P3-4) — fetches a GitHub-hosted JSON index in a background thread; per-entry SHA-256 verified before download; Install button copies plugin to AppData/plugins and calls the normal registration flow
- `_CommunityIndexThread` / `_CommunityDownloadThread` — non-blocking background workers for P3-4
- `tests/test_nspkg.py` — 13 tests covering bundle unpacking, manifest validation, safe filename, icon extraction, and error paths
- `tests/test_community_index.py` — 9 tests covering index fetch, SHA-256 mismatch, non-list response, and download success

**Fixed**
- CodeQL `py/empty-except` #696 — `ui/dashboard.py` modem log write now has an explanatory comment

### v1.9.47

**Added**
- `modules/plugin_tools.py` — plugin validator CLI (`python -m modules.plugin_tools validate <plugin.py>`); static checks for required constants, function signatures, PYPI_PACKAGE, top-level network calls, and imports outside safe list (P3-1)
- `tools/generate_plugin_hashes.py` + `data/plugin_hashes.json` — build-time SHA-256 hash list for bundled plugins; runtime signature verification in `_start_poll_worker_inst` blocks tampered plugins (P4-2); `TestBundledPluginHashSync` CI guard prevents stale-hash silent failures
- Plugin instance rename — `✎` button on each Hub card renames the instance inline; change propagates atomically to nav flyout label, breadcrumb, pinned section, and command palette (P3-4)
- P4-3 restricted import advisory — `validate_plugin()` warns when imports fall outside `_DEFAULT_SAFE_IMPORTS`; plugin may declare `SAFE_IMPORTS = [...]` to acknowledge custom imports
- Hardware Hub "⬡ New Plugin" button — 6-field template wizard dialog generates a filled-in `.py` file in the user plugins dir, then offers to open it in the system editor (P3-2)
- Plugin icon support — `HubCard` and catalog cards display a 24×24 PNG icon when `icon.png` is found alongside the plugin file or `ICON_PATH` constant is declared (P2-3)
- `_validate_script` now extracts `icon_path` from sibling `icon.png`/`icon.jpg`/`icon.svg` and from `ICON_PATH` constant
- `tests/test_plugin_tools.py` — 23 tests covering validator, signature check, and CLI (RULE-T1)
- `tests/test_import_bundled.py` — 28 tests covering `_validate_script`, `_path_hash`, `_instance_id`, AppData copy logic, PYPI_PACKAGE check, and `_classify_error` (closes RULE-T1 gap)

### v1.9.46

**Added**
- `workers/plugin_polling_worker.py`: `log_line` signal emits structured per-poll log entries (`[HH:MM:SS] get_info() → …`, errors, result status)
- Hardware Hub `HubCard`: `≡ Logs` toggle button expands a collapsible 130 px console showing the last 100 plugin log lines; wired via `_start_poll_worker_inst`
- `_migrate_stale_paths()` extracted to module level so it is directly testable and callable without a widget instance
- `_is_consented()` / `_record_consent()`: sha256-based one-time consent store for non-bundled plugins (P4-1)
- P4-1 unsigned plugin warning dialog — shown once per unique plugin file before `_on_browse` registers a non-bundled script; consent persisted in QSettings
- `tests/test_plugin_validator.py` — 16 tests for `_validate_script` and `_classify_error` (RULE-T1)
- `tests/test_plugin_health.py` — 15 tests for health tracking, circuit-breaker, and path-hash helpers (RULE-T1)
- `tests/test_plugin_migration.py` — 6 tests for `_migrate_stale_paths` path-replacement logic (RULE-T1)
- `tests/test_hub_card_errors.py` — 13 tests for `HubCard.set_error` routing and `PluginDevicePage` banner pip-install detection (RULE-T1)

### v1.9.45

**Added**
- Home page unified "Getting Started" checklist — hardware setup (ZTE MC889, Deco XE75) and core setup steps (scan, grade, ARP) in one prominent card; "Add →" buttons open the credential dialog directly without navigating away; card hides after all 5 steps are ticked

**Changed**
- `modem_page.py`, `mesh_router_page.py`, `workers/zte_worker.py`, `workers/mesh_worker.py` removed; ZTE MC889 and TP-Link Deco XE75 are managed exclusively via the hardware plugin system
- `hardware_integration_page.py`: modem and mesh tabs removed; credential dialog wired into `_import_bundled` so password is requested on first add and stored in OS keychain

**Fixed**
- `home_page.py`: `_check_recurring_mode` was iterating dict keys (always truthy) instead of values when testing whether all setup steps are complete
- `first_run_dialog.py`: removed unused `QRect` import (CodeQL `py/unused-import` #694)

### v1.9.44

**Added**
- `ui/first_run_dialog.py`: 3-slide Apple-style welcome wizard (Welcome → Discover & Protect → Monitor) with progress dots, Back/Next navigation, and "Scan my network →" CTA on the final slide
- `PluginDevicePage` modem view: `SignalBar` widgets for RSRP and SINR in 5G NR and LTE sections, matching the visual quality of the dedicated Modem page

**Changed**
- Extend nav section: "Modem" and "Mesh & Router" legacy items removed; hardware plugin pages (e.g. ZTE MC889, TP-Link Deco XE75) are the sole nav entries under Extend
- Home page hardware setup cards now navigate to Hardware page instead of legacy Modem/Mesh pages
- Startup window geometry: fresh installs open at 1280×800 centered on the primary screen instead of a random position
- `mesh_router_page.py`: `_on_scan_clicked`, `_on_forget_clicked`, and `_on_result` now fall back to placeholder IP when the field is empty (matching modem page behaviour)

**Fixed**
- `ModemPage` and `MeshRouterPage` incorrectly auto-filling the gateway IP instead of showing a blank field on first launch
- Extend section nav items for Modem/Mesh appearing even when no device was configured
- Home page "Set up →" links for 5G Modem and Mesh Router silently failing when legacy nav items were not registered

### v1.9.43

**Added**
- `tests/test_hardware_integration.py` — 35 tests covering `HardwareIntegrationPage` crash scenarios (startup, delete-while-timer-pending, password save/forget, plugin import lifecycle)
- Hardware plugin dependency auto-install: `PYPI_PACKAGE` constant added to 6 bundled plugins (asus, fritzbox, mikrotik, netgear, openwrt, unifi); clicking "＋ Add" now opens `PipInstallDialog` automatically if the library is missing
- `HubCard` inline install button: missing-dependency errors now show a blue "⬇ Install X" button instead of raw "run: pip install X" text; clicking installs the library and re-polls immediately

**Fixed**
- `hardware_integration_page.py`: `RecursionError` crash — `on_native_modem_data` was emitting `plugin_result`, creating an infinite signal loop via `_on_hardware_plugin_result` → `_on_modem_signal` → `on_native_modem_data`
- `hardware_integration_page.py`: `AttributeError: 'NoneType' has no attribute 'upper'` in `on_modem_card_data` when `network_type` key is present but `None`
- `hardware_integration_page.py`: startup crash `AttributeError: 'str' object has no attribute 'get'` in `_display_name` when QSettings data is corrupt or a plain string
- `hardware_integration_page.py`: `RuntimeError: wrapped C/C++ object deleted` when a `HubCard` was removed while its 3-second refresh `QTimer` was still pending
- Bundled ZTE/Deco plugin password not propagating to the card after a QSettings wipe; cards now auto-import bundled plugins on first launch
- Qt stylesheet parse warnings reduced across `modem_page.py`, `mesh_router_page.py`, `plugin_device_page.py`, and `hardware_integration_page.py`

### v1.9.42

- **wmic → CimInstance migration** — all credentialed-scan Windows commands ported from deprecated `wmic` to `powershell -NoProfile Get-CimInstance`; fully compatible with Windows 11 24H2 where wmic is removed
- **REST API hardening** — CORS restricted to `localhost` origins only; query-parameter auth removed (header-only `X-API-Key`); switched from Flask dev server to waitress WSGI for production-grade serving
- **CLI output path validation** — `cli.py` now resolves output paths with `Path.resolve()` and creates missing parent directories; exits cleanly with a user-readable error if the path is invalid
- **GeoLite2-City onboarding hint** — first-run wizard gains a geo-map info banner explaining the MaxMind DB download step
- **MSIX cosign signing in CI** — release workflow signs the MSIX artifact with `cosign sign-blob` (keyless OIDC) and uploads the `.bundle` file to the release; verification command included in release notes
- **HTML coverage reports in CI** — pytest runs produce `htmlcov/` which is uploaded as a per-platform artifact (`coverage-windows`, `coverage-macos`, `coverage-linux`)
- **FORCE_JAVASCRIPT_ACTIONS_TO_NODE24 removed** — env var dropped from all 5 CI jobs now that the runner default is Node 24

### v1.9.41

- **Notification channel test buttons** (SET-1) — Settings > Active Integrations now shows a "Send test" button next to Email, Webhook, and Pushover rows; each fires a live test message off the main thread and shows a toast with the result
- **Accent colour picker** (SET-2) — Settings > Appearance gains a row of 6 preset accent swatches and a "Custom…" colour dialog; the override is saved to QSettings `ui/accent_override` and applied to `ACCENT`, `ACCENT_LITE`, `ACCENT_DARK` at next launch
- **Settings export / import** (SET-3) — Settings > Maintenance gains "Export settings (JSON)" and "Import settings" buttons backed by the new `modules/settings_io.py`; secrets remain in the OS keychain and are never written to the export file
- **Signal strength bar widget** (POLISH-12) — new `ui/widgets/signal_bar.py` QPainter widget draws 5 phone-style vertical bars for RSRP, RSRQ, SINR, SNR; wired into Modem page signal cards (5G NR and LTE sections)
- **Reports chart preview** (POLISH-14) — Reports page shows a matplotlib sparkline of device count and network grade for the last 7 days above the schedule config
- **Geo Map risk heatmap** (VIZ-8) — a "Show risk heatmap" toggle draws radial colour glow behind Threat Intel (red) and Exposed Service (amber) dots to highlight geographic risk concentrations
- **Keyboard shortcut hints in tooltips** (EDU-2) — Settings button tooltip shows `Ctrl+,`, sidebar search shows `Ctrl+F`, Monitor section rail button shows `Ctrl+L → Network Logger`, scan button tooltip lists Ctrl+K and Ctrl+F hints

### v1.9.40

- **Geo map enriched detail panel** (VIZ-1) — clicking a mapped IP now shows a full enriched panel: flag + country/city, ASN/org, threat-intel risk chip, up to three TI indicator rows, alert count from the last 24 h, and a "View in Threat Intel →" button that navigates directly to the Threat Intel page
- **Bandwidth event annotations** (VIZ-2) — rate-spike and new-device events are now annotated directly on the Live Bandwidth chart with a dashed vertical line and a rotated label; annotations age across the 60-second rolling window
- **Protocol visualizer name overlay** (VIZ-7) — AnimNodes whose labels contain an IP address are automatically enriched with the device hostname from the last inventory scan, displayed as two-line "hostname / IP" labels in the protocol animation
- **Alert badge decay** (ANIM-9) — when a rail-section badge is cleared, it fades out over 400 ms (OutCubic easing) rather than disappearing instantly; reduce-motion preference bypasses the animation
- **Inventory scan comparison** (ACT-3) — Inventory page gains a "⊞ Compare" toolbar button that opens a modal diff dialog showing added, removed, and changed devices between any two saved baseline snapshots
- **Speed test baseline** (ACT-4) — right-click any Speed Test history row to "★ Set as Baseline"; starred row shows a ★ marker in column 0 and subsequent rows display download/upload delta arrows (↑/↓) relative to the baseline
- **Baseline schedule strip** (ACT-7) — Config Baseline page gains an "Auto-snapshot every N days" strip; setting is persisted to QSettings and drives the existing scheduler
- **Certificate snooze** (ACT-8) — right-click any certificate row to snooze its expiry warning for 7, 30, or 90 days; snoozed certs are greyed out with the snooze expiry shown in the Status column

### v1.9.39

- **Group-by-process toggle** (FILTER-7) — Connections page gains a "⊞ Group by Process" button; when active, rows collapse into per-executable aggregates showing port range, external-IP count, and dominant status; click any group row to expand an inline sub-table of individual connections
- **Threat Intel text search** (FILTER-8) — live 200 ms debounced filter bar on the Threat Intel page; searches indicator, category, and feed columns simultaneously; shows "X / Y" match count
- **Timeline text search** (FILTER-9) — 180 px search box in the Timeline chip row; filters event title and detail with 200 ms debounce and a running match count
- **Log Hub CSV export** (FILTER-10) — "↓ Export" button exports only the currently visible (filtered) log entries to a user-chosen CSV file; honours all active source and text filters
- **Inventory tag-chip filter** (FILTER-11) — device tags from the known-device registry appear as toggleable chips below the search bar; clicking a chip shows only devices carrying that tag; multiple chips use OR logic
- **Notifications bulk actions** (FILTER-12) — selecting multiple rows in the Alert History table reveals a bulk action bar: Dismiss (marks all selected acknowledged), Snooze 1 h, Snooze 8 h, and Deselect All
- **Timeline click-to-navigate** (ACT-5) — Timeline event rows for Devices, Alerts, CVEs, and Speed Tests are now clickable; clicking navigates directly to the corresponding page
- **DHCP "Find in Inventory"** (ACT-6) — right-click any DHCP lease row for a context menu with "▶ Find in Inventory →"; selects the device in the Inventory page and switches to it in one action
- **Per-page ? help panel** (EDU-1) — every page header now supports an optional `?` button (22 × 22, checkable); clicking opens a 280 px popover below the button showing the page title and a plain-English description of what it does and how to start

### v1.9.38

- **Grade Ring** (HOME-1) — animated QPainter arc replaces the QLabel grade circle on the home page; arc sweeps 600 ms OutExpo on each new grade, score counts up below the letter
- **Overview tiles** — three new configurable tiles: Top Talkers (top-3 interfaces by session bandwidth), Recent Events (last 5 device-state events with one-click link to Timeline), Trend Forecast (critical / warning / clean counts from the latest trend report)
- **Events ticker** (HOME-3) — slim 28 px bar in the recurring home section shows last 3 device events from the past 24 h; clicking opens Timeline
- **Speed mini-sparkline** (HOME-4) — speed card on the home page now shows a 72×16 bar sparkline of the last 10 test results
- **Tile hover lift** (ANIM-7) — overview tiles rise 2 px on cursor enter (120 ms OutQuart), return on leave (80 ms OutCubic); respects OS reduce-motion setting
- **Monitor Overview sparklines** (VIZ-6) — each status tile shows a 6-bar hourly event-count sparkline; refreshes every 5 minutes from MetricStore
- **Smooth progress bar** (ANIM-8) — scan progress indicator is now `_SmoothProgressBar` with 250 ms InOutSine easing on value transitions

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
