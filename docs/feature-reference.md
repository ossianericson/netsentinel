# Feature Reference

Complete list of all NetSentinel pages and features, organised by navigation section. **Admin** means the feature requires running as Administrator (Windows) or `sudo` (macOS/Linux). **Npcap** means the feature additionally requires [Npcap](https://npcap.com) on Windows or `libpcap` on macOS/Linux.

---

## Getting Started

| Feature | What it does | Requirements | Key module |
|---|---|---|---|
| **Overview** | Configurable tile dashboard — uptime, RTT, speed, alerts, top talkers, recent events. Drag to reorder; layout persists. | — | `ui/pages/overview_page.py` |
| **Speed Test** | 3-tier cascade: Ookla CLI → speedtest-cli → pure-Python. Saves 20 modem signal fields per test; click a history row to restore the signal panel. | — | `modules/speed_tester.py` |
| **DNS & Connectivity** | Live latency graph; benchmarks Cloudflare, Google, Quad9 and your system resolver side-by-side; DNS leak test shows which resolver handles your queries. | — | `modules/dns_correlator.py` |
| **Home** | "Since you were last here" banner (new devices, outages); "What to do next" suggestions after each scan; weekly digest; health score card. | — | `ui/pages/home_page.py` |
| **What's Wrong?** | One-click root-cause diagnosis. Symptom tiles: slow internet, dropping connection, no connection, service unreachable. Sequences DNS, storm, STP, and ISP checks and surfaces a prioritised plain-English finding. | — | `ui/pages/diagnosis_page.py` |

---

## Discover

| Feature | What it does | Requirements | Key module |
|---|---|---|---|
| **Devices** | Full device inventory with IP, MAC, hostname, vendor, type, and risk level. Segment filter pills (colour-coded /24 subnets). Persistent device map — pinned and recently-seen offline devices stay visible. Right-click: Port Scan, Wake-on-LAN, How to Fix, Label Device. | — | `ui/pages/inventory_page.py` |
| **Network Map** | Cytoscape.js interactive topology map with drag-to-reposition, lock layout, and classic matplotlib fallback. Mesh-aware: Deco node assignment shown when credentials are configured. | — | `ui/pages/network_map_page.py` |
| **Wi-Fi** | 802.11 network enumeration: hidden SSIDs, rogue APs, WPS-enabled networks, co-channel interference, signal levels, connected client list. | — | `modules/wifi_scanner.py` |
| **DHCP Leases** | Parses the OS DHCP lease table; flags any rogue DHCP server on the segment. | — | `modules/dhcp_lease_scanner.py` |
| **DNS Zone Map** | DNS zone enumeration via AXFR and mDNS. | — | `modules/dns_zone_scanner.py` |
| **Home Automation** | Home Assistant device state display via REST API integration. | — | `ui/pages/home_automation_page.py` |

---

## Monitor

| Feature | What it does | Requirements | Key module |
|---|---|---|---|
| **Active Monitors** | Aggregated view of all monitoring streams — health score, ARP watch, live bandwidth, scheduled scans. | — | `ui/pages/monitor_overview_page.py` |
| **Network Logger** | Unified chronological log combining RTT, 5G modem, mesh, syslog, and SNMP trap streams. Source toggle bar. Emits `live_challenge_detected` → Lab Mode. | — | `ui/pages/log_hub_page.py` |
| **Network Timeline** | Chronological event log across all monitoring sources with source-colour coding. | — | `ui/pages/timeline_page.py` |
| **Live Bandwidth** | 60-second rolling upload/download chart per interface. | — | `ui/pages/live_bandwidth_page.py` |
| **App Traffic** | Per-host protocol breakdown (Web/DNS/Streaming/Gaming/VPN/P2P) via port heuristics. CDN tagging (Netflix, YouTube, Twitch, Disney+). | Npcap | `modules/app_traffic_classifier.py` |
| **Active Connections** | Process-to-socket map with one-click firewall block/unblock per process. | — | `modules/process_monitor.py` |
| **Availability History** | Persistent RTT and UP/DEGRADED/DOWN charts per device with 1 h / 12 h / 24 h / 7 d zoom. | — | `modules/availability_monitor.py` |
| **Inventory Changes** | Config baseline snapshots and structured diff viewer: added/removed/changed devices between scans. | — | `modules/config_baseline.py` |
| **Bandwidth Usage** | Per-device bandwidth statistics over time. | — | `modules/bandwidth_monitor.py` |
| **Service Heartbeat** | TCP/HTTP/HTTPS probe per configured service. Alerts on failure. "Diagnose →" action opens Service Diagnostics pre-loaded for that service. | — | `modules/service_monitor.py` |
| **Service Diagnostics** | DNS/TCP/HTTPS/ICMP/traceroute probes for streaming and gaming services. Failure-layer classification: device → local_network → dns → isp → routing → remote_outage. | — | `modules/service_diagnostics.py` |
| **IPv6 Devices** | IPv6 neighbor discovery via NDP and ping sweep. | — | `modules/utils_platform.py` |
| **Uptime & SLA** | Uptime percentage per device; availability history charts. | — | `modules/metric_store_queries_uptime.py` |
| **Syslog Viewer** | UDP syslog message receiver, parser, and viewer. | — | `modules/syslog_receiver.py` |
| **SNMP Trap Receiver** | SNMP trap listener with structured event display. | — | `modules/snmp_trap_receiver.py` |

---

## Reports

| Feature | What it does | Requirements | Key module |
|---|---|---|---|
| **Network Grade** | A–F grade across 8 dimensions: uptime, latency, jitter, DNS speed, download speed, device safety, STP health, storm level. Compared against a "perfect home network" baseline. | — | `modules/risk_scorer.py` |
| **Health Report** | Ambient health score with sparkline; per-dimension breakdown; trend over time. | — | `modules/health_score.py` |
| **Network Doc** | One-click HTML/Markdown network documentation snapshot: devices, segments, topology, grade, ISP info. | — | `modules/net_doc_generator.py` |
| **IP Calculator** | IPv4 subnet calculator with CIDR reference panel; first/last address, broadcast, host count, mask. | — | `ui/pages/ip_calculator_page.py` |
| **Notifications** | Alert channel configuration (Toast, Email, Webhook, Pushover, Ntfy, Telegram), alert rules, escalation policy, weekly digest, alert history log with delivery status. | — | `modules/notification_router.py` |
| **Shareable Card** | Exports a 520×300 diagnostic card (grade, ISP, top 3 findings) as PNG, clipboard image, or standalone HTML. | — | `modules/diagnostic_card.py` |

---

## Analysis

| Feature | What it does | Requirements | Key module |
|---|---|---|---|
| **Broadcast Storm** | Measures broadcast and multicast flood levels; identifies the source device. | Admin + Npcap | `modules/storm_analyser.py` |
| **Rogue Bridge (STP)** | Captures BPDUs; identifies which device claims the root bridge, port roles, and reconvergence timing. The cause of periodic 30–45 s reconnection drops. | Admin + Npcap | `modules/stp_detector.py` |
| **IoT Behaviour** | Learns normal traffic per IoT device; alerts on port scans, new destinations, and traffic rate spikes. | — | `modules/iot_baseline.py` |
| **802.11 Monitor** | Passive 802.11 frame capture — probe requests, association frames, EAPOL. | Admin + Npcap | `ui/pages/wifi_monitor_page.py` |
| **ARP Spoof Watch** | Watches for IP–MAC mapping conflicts that indicate a MITM attack in progress. | Admin + Npcap | `modules/arp_monitor.py` |
| **Hop-by-Hop Trace** | MTR-style hop table with per-hop RTT and packet loss. | — | `modules/network_diagnostics.py` |
| **SNMP Device Info** | SNMP MIB-II poller for device sysDescr, sysName, interface counters. | — | `modules/snmp_poller.py` |
| **Tools & Wake-on-LAN** | Wake-on-LAN magic packet; ping sweep; interface info; network benchmark. | — | `modules/utils.py` |
| **Geolocation Map** | Plots internet-facing IPs on an offline world map using MaxMind GeoLite2-City. No API key, no external calls. | — | `modules/geo_locator.py` |
| **Trend Forecasts** | OLS regression over RTT/loss/jitter with ETA-to-threshold predictive alerting. | — | `modules/trend_analyser.py` |
| **Root Cause Correlator** | Prioritised plain-English findings from full scan data. Global verdict: "Your internet is slow because..." | — | `modules/root_cause_correlator.py` |
| **Wi-Fi Heatmap** | Floor plan import; per-BSSID IDW signal interpolation; PNG export. | — | `modules/wifi_heatmap.py` |

---

## Automation

| Feature | What it does | Requirements | Key module |
|---|---|---|---|
| **Automation Hooks** | Shell command triggers on network events: device down, high RTT, new device discovered, alert fired. | — | `modules/automation_hooks.py` |
| **Scheduled Scans** | Configurable scan schedule; results persist in MetricStore. | — | `modules/scheduler.py` |
| **Custom Triggers** | Expression builder for alerting conditions beyond the built-in ruleset. | — | `modules/trigger_expression.py` |
| **MQTT** | MQTT broker client with Home Assistant Discovery payloads; OS-keychain credentials; test publish. | — | `modules/mqtt_publisher.py` |
| **REST API** | Read-only Flask API at `http://127.0.0.1:8765`; API key in OS keychain; `/devices`, `/alerts`, `/uptime`, `/health` endpoints. | — | `modules/rest_api.py` |
| **Config Snapshots** | Structured diff of device inventory between two points in time. | — | `modules/config_baseline.py` |
| **Maintenance Windows** | Alert suppression per device or fleet-wide during scheduled maintenance. | — | `modules/maintenance_window.py` |

---

## Security Audit

All features in this section require running as Administrator / `sudo`. Most also require Npcap/libpcap.

| Feature | What it does | Key module |
|---|---|---|
| **Security Overview** | Aggregate security findings dashboard: rogue devices, open ports, CVEs, exposure score, TLS status. | `ui/pages/security_overview_page.py` |
| **Port Scanner** | SYN stealth scan — half-open TCP; faster and quieter than a connect scan. Requires Scapy + admin. | `modules/syn_scanner.py` |
| **CVE Lookup** | Cross-references discovered OS and service versions against the NVD database; per-device CVE lifecycle tracking. | `modules/cve_lookup.py` |
| **Threat Intelligence** | ThreatIntelDB: Feodo Tracker, Emerging Threats, URLhaus blocklists; AbuseIPDB v2 lookup (consent-gated, requires own API key). | `modules/threat_intel.py` |
| **TLS Certificates** | Hourly expiry checks per host; 30-day pre-expiry alerts; OK / EXPIRING / EXPIRED badges. | `modules/tls_checker.py` |
| **Login Test** | Credentialed scan: tests SSH, SMB, FTP, Telnet with provided credentials. | `modules/credentialed_scan.py` |
| **OS Detection** | Active OS fingerprinting from TCP/IP stack behaviour. | `modules/os_fingerprint.py` |
| **Risk Score** | Per-device risk scoring across open ports, OS age, CVE count, and OUI flags. | `modules/risk_scorer.py` |
| **Internet Exposure** | RFC 1918 boundary exposure checker; detects services bound to WAN-facing interfaces. | `modules/internet_exposure.py` |
| **Full Discovery** | Parallel ARP + ICMP + TCP SYN + mDNS + passive SSDP/mDNS sweep for maximum census accuracy. | `modules/combined_discovery.py` |
| **SMB Enumeration** | SMB/Windows Share enumeration; flags accessible shares. | `modules/smb_enumerator.py` |
| **Scan Plugins** | Custom Python security checks against the device list. Drop `.py` into `plugins/`; runs in sandbox. | `modules/plugin_system.py` |
| **Private Endpoint** | Checks for RFC 1918 services inadvertently exposed to the broader network segment. | `modules/private_endpoint_checker.py` |
| **Cloud Metadata** | Probes AWS/Azure/GCP IMDS endpoints (`169.254.169.254`, etc.) to detect exposed cloud metadata APIs. | `modules/cloud_metadata.py` |
| **DHCP Rogue** | Passive detection of unauthorized DHCP servers on the segment via DHCP fingerprinting. | `modules/dhcp_fingerprint.py` |

---

## Education

| Feature | What it does | Key module |
|---|---|---|
| **Protocol Visualizer** | Animated step-by-step diagrams of 10 protocols: ARP, DNS, TCP, DHCP, STP, OSPF, NAT, VLAN 802.1Q, TLS 1.3, and ICMP traceroute — using real scan data from your own network. CompTIA N+ / CCNA objective badges on each diagram. | `ui/pages/protocol_viz_page.py`, `modules/protocol_animator_extra.py` |
| **Lab Mode** | Four guided exercises: Find the Rogue Device, Diagnose Slow DNS, Identify the Broadcast Storm Source, Map Your Subnet. Progressive hints, solution reveal, exportable HTML result reports. Live challenges injected from Network Logger events. | `ui/pages/lab_mode_page.py` |
| **Feature Guide** | Searchable catalog of all 83+ features across 9 groups with filter bar and direct Open buttons. | `ui/pages/discover_page.py` |
| **Help** | Per-page help popovers (? button). 24-term networking glossary accessible from any page. "Common Scenarios" lookup table mapping 17 user goals to the correct feature. | `ui/help.py` |

---

## Extend

| Feature | What it does | Key module |
|---|---|---|
| **Hardware Hub** | Central hub for hardware integration plugins. Import, configure, and monitor any plugin. Hub cards with health tracking, circuit breaker, credential management, and plugin log console. | `ui/pages/hardware_integration_page.py` |
| **12 bundled plugins** | TP-Link Deco, ZTE 5G modem, FRITZ!Box, UniFi, OpenWrt, MikroTik, Netgear, ASUS, Synology, Home Assistant. All signed and hash-verified. | `modules/deco_client.py`, `modules/zte_client.py`, etc. |
| **Plugin authoring** | In-app Write a Plugin tab: API discovery guide, template wizard ("⬡ New Plugin"), AI-ready prompts, validator CLI, community Browse tab, `.nspkg` import. | `ui/pages/plugin_wizard_mixin.py` |
