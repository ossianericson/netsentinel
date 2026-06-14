# NetSentinel — Feature Gap Analysis vs. Open-Source Benchmark Tools

**Date:** June 2026 | **Version baseline:** NetSentinel v2.1.5

---

## Executive Summary

NetSentinel occupies a genuinely rare position: a single local-first desktop application that unifies Layer 2 detection, active scanning, passive monitoring, educational tooling, and automation hooks without requiring a server, cloud account, or database administration. No single benchmark tool replicates this combination.

However, the benchmark tools reveal **four structural gaps** that represent real user pain points:

1. **Flow-level traffic analysis** — ntopng and LibreNMS give users per-application, per-host bandwidth breakdowns; NetSentinel shows interface totals only.
2. **Switch-port-level asset location** — Netdisco's "where is this device physically connected?" lookup (MAC table + LLDP correlation) is absent.
3. **Alert operational maturity** — dependency trees, on-call schedules, and downtime comments (Nagios/Icinga2/LibreNMS) are missing, causing alert fatigue in multi-device environments.
4. **Config/inventory persistence** — no IP Address Management (IPAM) hierarchy, no per-device software inventory, no device change log beyond scan snapshots. *(Partially addressed in v2.1.5: startup cache restore pre-populates Devices table and Network Map from `known_device` + topology snapshot so the app is never blank — see UX gap below.)*

The remaining gaps are either low-priority niche capabilities or represent deliberate scope decisions (no server backend, no multi-tenant support) that should be preserved.

---

## Benchmark Tools Reviewed

| Tool | Category | Relevance |
|---|---|---|
| Nmap / Zenmap | Discovery & port scanning | Direct overlap |
| Netdisco | Switch/SNMP topology | L2 asset location |
| LibreNMS | SNMP monitoring | Monitoring breadth |
| ntopng | Traffic analysis | Flow/DPI |
| Kismet | 802.11 passive | WiFi depth |
| NetworkMiner | Passive pcap analysis | Passive discovery |
| Angry IP Scanner | Simple scanner | UX baseline |
| NetBox | IPAM / DCIM | Inventory management |
| Wireshark / tshark | Protocol analysis | Protocol depth |
| Icinga2 / Nagios | Service monitoring | Alert maturity |
| Checkmk | SNMP + agent monitoring | Inventory + events |
| Rumble (runZero) | Unauthenticated fingerprinting | Discovery quality |

---

## NetSentinel Existing Strengths (Competitive Moat)

Before the gaps: capabilities NetSentinel has that **none** of the benchmark tools combine in one app:

- **All-in-one local desktop** — no server, no cloud, no accounts, single exe
- **Layer 2 depth without enterprise hardware** — STP/BPDU, ARP spoof, broadcast storm, 802.11 monitor, all from a home router setup
- **Educational mode** — protocol visualizer with exam objective badges (N+/CCNA/Sec+), lab scenarios with guided exercises; no competitor has this
- **Natural language device search** — conversational query across scan results
- **Service failure-layer classification** — "is this a DNS problem, a routing problem, or a remote outage?" — unique in this category
- **Modem + mesh visibility** — 5G modem signal (ZTE MC889) and mesh topology (TP-Link Deco XE75) in the same tool as network scanning
- **Hardware plugin ecosystem** — extensible without requiring a server-side plugin runner
- **Passive SSDP/mDNS enrichment** — device-type hints without sending packets
- **LLDP multi-hop topology** — rare in desktop tools

---

## Categorized Feature Backlog

### Category 1 — Missing Core Discovery & Inventory Features

| # | Feature Name | Priority | Benchmark Source(s) | Why It Matters for NetSentinel | Complexity |
|---|---|---|---|---|---|
| D0 ✅ | **Startup inventory cache restore** — Devices table and Network Map pre-populated from `known_device` (MetricStore) and last topology snapshot at launch; stale indicator shown until live scan runs | **Done** | — | Eliminates blank-on-startup UX gap. `known_device` is the persistence layer; topology snapshot provides edge data for the map. Shipped v2.1.5. | Small |
| D1 | **Switch-port MAC table correlation** — "Where is this device physically connected?" (switch IP, interface, VLAN) | **High** | Netdisco | The #1 question in any managed LAN: "which port is 192.168.1.42 on?" Netdisco answers this by correlating SNMP MAC address tables with LLDP topology. NetSentinel shows the device but not its physical location in the switch fabric. Critical for SMB users managing a 24-port switch. | Large |
| D2 | **Per-device installed software inventory** (via SNMP MIB-II hrSWInstalled or WMI/psutil) | **Medium** | Checkmk, LibreNMS | Knowing a device runs Apache 2.4.48 is more actionable than knowing port 80 is open. Checkmk's HW/SW inventory fills this. Could feed the CVE tracker directly. | Medium |
| D3 | **SNMP device configuration backup** — snapshot running-config from routers/switches, detect config drift | **Medium** | LibreNMS (RANCID integration) | IT admins want to know when a switch config changed. LibreNMS stores config snapshots and diffs them. NetSentinel has `config_baseline.py` for device inventory but not for device configs themselves. | Medium |
| D4 | **Unauthenticated protocol banner grabbing at scale** — extract service banners (HTTP Server header, SSH version string, FTP greeting, SMTP EHLO) and display as inventory columns | **Medium** | Rumble (runZero), Nmap `-sV` | NetSentinel does OS fingerprinting but doesn't surface service version strings in the Devices table. Rumble's key differentiator is the depth and speed of banner extraction. Version strings feed CVE correlation far better than port numbers alone. | Medium |
| D5 | **Full IPAM — IP prefix/subnet hierarchy with utilization tracking** | **Low** | NetBox | Prefix tree (e.g., 10.0.0.0/8 → 10.1.0.0/16 → 10.1.5.0/24) with per-prefix utilization %. NetBox is the gold standard. NetSentinel has /24 segment grouping (Sprint 4) but not a navigable prefix hierarchy. Relevant if targeting IT admins managing multiple subnets. | Large |
| D6 | **Nmap NSE script execution UI** — expose Nmap Scripting Engine categories (auth, vuln, discovery, safe) from within the app with results parsed into the device record | **Low** | Nmap NSE | NetSentinel wraps nmap for port scanning but doesn't surface the 600+ NSE scripts. A "Run script" right-click on a device row would unlock enormous capability with zero new code in the modules layer. | Small |
| D7 | **IPv6 neighbor discovery completeness** — DHCPv6 leases, SLAAC address correlation, NDP table sweep | **Low** | Nmap, LibreNMS | `utils_platform.py` has `get_ipv6_devices()` and `ping_sweep_ipv6()` but IPv6 inventory is incomplete in the UI (no NDP table, no SLAAC linkage). As IPv6 adoption grows in homelabs, this becomes a gap. | Medium |

---

### Category 2 — Missing Visualization Features

| # | Feature Name | Priority | Benchmark Source(s) | Why It Matters for NetSentinel | Complexity |
|---|---|---|---|---|---|
| V1 ✅ | **Traffic overlay on topology map** — colour-code nodes by current bandwidth utilization ("Weathermap" for the home lab) | **High** | LibreNMS Weathermap plugin, ntopng | ✅ **Done (2026-06-14):** `BandwidthOverlayWorker` + Cytoscape.js node CSS classes (`traffic-high/medium/low`) wired into `network_map_page.py` "Traffic Overlay" toggle. Scapy/Npcap required; graceful error fallback. | Medium |
| V2 ✅ | **Per-host application traffic breakdown** — which apps/protocols each device is using (Netflix, BitTorrent, SSH, DNS, etc.) displayed as a stacked bar or pie | **High** | ntopng (via nDPI), Wireshark statistics | ✅ **Done (2026-06-14):** `modules/app_traffic_classifier.py` — port→category heuristics (15 categories, 80+ well-known ports, `classify_port()`, `AppTrafficSniffer`, `AppTrafficMonitor`, `AppTrafficSnapshot`/`AppHostSnapshot`/`AppFlowEntry` dataclasses). `workers/app_traffic_worker.py` — QThread wrapper emitting `snapshot_ready`. `ui/pages/app_traffic_page.py` — horizontal stacked bar chart (all hosts, colour-coded by category) + per-host drill-down detail table. Category colours in `modules/colours.py` (`APP_CATEGORY_COLORS`). Requires Npcap + admin; degrades gracefully without Scapy. | Large |
| V3 | **Protocol flow sequence diagram** — interactive timeline showing packet exchanges between two hosts (like Wireshark's "Follow Stream" but visual) | **Medium** | Wireshark flow graph | The Protocol Visualizer page has animated ARP/DNS/TCP/DHCP diagrams but they're canned animations. A real-traffic sequence diagram from a live or uploaded pcap would be a powerful educational and diagnostic tool. | Large |
| V4 ✅ | **Interface error / discard metrics graph** — per-port CRC errors, input errors, output drops, collisions from SNMP ifTable | **Medium** | LibreNMS, Checkmk | ✅ **Done (2026-06-14):** `modules/snmp_poller.py` extended with `IfErrorEntry` dataclass + `poll_if_errors()` (GET-based ifTable walk for indices 1..ifNumber). `SNMPIfErrorWorker` added to `workers/scan_worker.py`. SNMP Device Info tab extended with "Interface Error & Discard Counters" card: per-interface table + grouped matplotlib bar chart (In/Out Errors, In/Out Discards per interface). Clicking a device row auto-fills the host field. | Medium |
| V5 ✅ | **Scan comparison / diff view** — per-port colour-coded diff between two scan results (new ports opened with service names, suspicious port warnings, devices added/removed) | **Medium** | Nmap ndiff, Netdisco history | ✅ **Done (2026-06-14):** `baseline_page.py` diff display upgraded to per-port rows with `_WELL_KNOWN_PORTS` service name enrichment, `_SUSPICIOUS_PORTS` red/amber colouring, and ⚠ risk tags. | Medium |
| V6 | **Per-segment traffic heatmap** (time-of-day activity by subnet/device group) | **Low** | ntopng | Shows which devices are active at 3 AM — powerful for IoT anomaly detection when combined with the existing IoT baselines. | Medium |

---

### Category 3 — Missing Automation & Integration Features

| # | Feature Name | Priority | Benchmark Source(s) | Why It Matters for NetSentinel | Complexity |
|---|---|---|---|---|---|
| A1 | **Nagios/NRPE plugin compatibility** — accept results from the 6,000+ community Nagios check plugins as service monitors | **High** | Nagios, Icinga2 | The Nagios plugin ecosystem is the broadest in monitoring. A compatibility shim (`check_*` exit code → NetSentinel service status) would instantly add check_ssl, check_postgres, check_docker, check_vmware, and hundreds more without writing new workers. | Medium |
| A2 | **NetFlow/sFlow/IPFIX collector** — listen for flow exports from routers/switches and store per-source/destination/protocol flow records | **High** | LibreNMS, ntopng, OpenNMS | Consumer routers (OpenWRT, pfSense, Mikrotik) can export NetFlow. Collecting it gives per-host/per-application bandwidth history without deep packet inspection. Complements the existing bandwidth monitor which is interface-total only. | Large |
| A3 | **Slack / PagerDuty / OpsGenie notification channels** | **Medium** | LibreNMS, Icinga2 | The alert pipeline supports Pushover, Ntfy, Telegram. Adding Slack (webhook) and PagerDuty (API) targets IT admins who already have these tools in their workflow. Slack is table-stakes for SMB. | Small |
| A4 | **Webhook inbound triggers** — receive scan requests or configuration changes via HTTP POST (e.g., from CI/CD pipelines or network change management tools) | **Medium** | LibreNMS REST API, Icinga2 API | The REST API is read-only. A narrow write surface (trigger scan, acknowledge alert, add maintenance window) would allow integration with tools like Ansible, Terraform, or N-central without polling. | Medium |
| A5 | **Ticket system integration** — create tickets in Jira, Freshservice, or Zendesk when an alert fires | **Low** | Icinga2, Checkmk | Enterprise IT admins expect alerts to flow into their ticketing system. Even a simple webhook template pre-formatted for Jira/ServiceNow would cover this. | Small |
| A6 | **Prometheus metrics endpoint** — expose key metrics (device count, alert count, RTT p95, scan age) on `/metrics` in Prometheus scrape format | **Low** | LibreNMS (community exporter plugin) | Homelabbers running Prometheus+Grafana stacks want to pull NetSentinel data into their existing dashboards. An exporter endpoint is a single-file addition to the Flask REST API. | Small |
| A7 | **GraphQL API** — structured query interface for automation scripts and third-party integrations | **Low** | NetBox | The current REST API returns fixed JSON shapes. GraphQL would let integrations request exactly the fields they need. Low priority given the REST API already covers most use cases. | Large |

---

### Category 4 — Missing Operational / Alert Maturity Features

| # | Feature Name | Priority | Benchmark Source(s) | Why It Matters for NetSentinel | Complexity |
|---|---|---|---|---|---|
| O1 | **Alert dependency trees** — when a parent device (gateway, switch) goes down, suppress alerts for all downstream devices | **High** | Nagios, Icinga2, LibreNMS | Without dependency awareness, a single router outage generates 30+ alerts (one per device). This is the #1 cause of alert fatigue. Nagios solved this in 2002. NetSentinel's `alert_suppressor.py` handles maintenance windows but not dependency-based suppression. | Medium |
| O2 | **Per-alert acknowledgement with comment and owner** — "I know about this, it's expected, tracking as JIRA-123" | **High** | Nagios, Icinga2, LibreNMS | Without acknowledgement, the same alert re-notifies on every check cycle. IT admins need to silence an active alert while it's being worked. | Medium |
| O3 | **Scheduled downtime with reason** — "this device will be offline Sat 02:00–04:00 for firmware update" with auto-resume | **Medium** | Nagios, Icinga2 | NetSentinel has `maintenance_window.py` for maintenance windows but the UX for defining them is not clearly discoverable. The Nagios model (enter start time, end time, comment, owner) is more intuitive for IT admins. This may be a UX gap rather than a feature gap. | Small |
| O4 | **Alert deduplication and event correlation** — group related alerts into a single incident (e.g., 15 "host unreachable" events → one "network segment outage" incident) | **Medium** | Checkmk Event Console, OpenNMS Correlation | Reduces noise significantly. Checkmk's Event Console matches syslog/trap patterns to known event types and deduplicates based on host+type+count thresholds. | Large |
| O5 | **Per-device audit log / change history** — every change to a device record (hostname rename, tag added, alert threshold changed) logged with timestamp and source | **Medium** | NetBox, LibreNMS | "Who changed the alert threshold for the NAS and when?" Currently no answer. Valuable for IT admins managing shared tools. | Medium |
| O6 | **SLA / uptime reporting** — calculate 30-day/90-day availability percentage per device with breach reporting | **Medium** | LibreNMS, Checkmk | The availability monitor tracks uptime but doesn't produce an SLA report. IT managers want "this server was 99.7% available in May." | Small |
| O7 | **On-call rotation scheduling** — define who gets paged at which hours, with automatic escalation | **Low** | Icinga2, PagerDuty | Overkill for home use but relevant for SMB IT admins using NetSentinel as their primary monitoring tool. | Large |

---

### Category 5 — Missing Protocol & Security Analysis Features

| # | Feature Name | Priority | Benchmark Source(s) | Why It Matters for NetSentinel | Complexity |
|---|---|---|---|---|---|
| P1 | **WPS attack detection** — Pixie Dust, WPS bruteforce attempt alerts from passive 802.11 capture | **Medium** | Kismet | Kismet detects WPS attack patterns from passive capture. NetSentinel's `wifi_monitor_page.py` captures frames but doesn't implement WPS-specific alert rules. Relevant for home security users. | Medium |
| P2 | **PMKID / EAPOL handshake capture alerts** — detect WPA handshake capture attempts (someone testing your password offline) | **Medium** | Kismet | A nearby attacker capturing EAPOL handshakes is a real home-network threat. Passive detection requires no attack and no credentials. | Medium |
| P3 | **Deauthentication / disassociation flood detection** — detect deauth attacks that knock devices off WiFi | **Medium** | Kismet, commercial IDS | High user impact. A neighbor running a WiFi jammer or running MDM tools shows as a deauth flood. Currently not in the 802.11 monitor alert rules. | Small |
| P4 | **TLS certificate transparency log monitoring** — alert when a certificate is issued for your domain that you didn't request | **Low** | Various CT log tools | Detects domain hijacking and phishing infrastructure. A background worker polling crt.sh for user-specified domains is a small addition to `cert_monitor.py`. | Small |
| P5 | **DNS rebinding attack detection** — flag DNS responses where a public domain resolves to an RFC 1918 address | **Low** | Various DNS tools | DNS rebinding bypasses browser same-origin policy. The `dns_correlator.py` monitors DNS latency but not response content for rebinding patterns. | Small |
| P6 | **Passive OS fingerprinting from TCP/IP stack behavior** (p0f-style) — identify OS from SYN packets without sending any probe | **Low** | NetworkMiner, p0f | Complements the active OS fingerprinting in `os_fingerprint.py` for cases where active scanning is not desired. | Medium |

---

### Category 6 — Nice-to-Have Enhancements

| # | Feature Name | Priority | Benchmark Source(s) | Why It Matters | Complexity |
|---|---|---|---|---|---|
| N1 | **Bluetooth device scanning** — enumerate nearby BT/BLE devices with MAC, name, class | **Low** | Kismet | IoT environments increasingly have Bluetooth devices. A passive BLE scan window alongside the WiFi scan would complete the "what's in my airspace" view. | Medium |
| N2 | **PCAP file import and offline analysis** — load a .pcap and run NetSentinel's parsers against it for post-incident analysis | **Low** | Wireshark, NetworkMiner | "I captured traffic during the incident, now help me understand it." Would reuse the protocol visualizer and topology builder against historical data. | Large |
| N3 | **Cable / physical port mapping** — document which device is plugged into which switch port, with patch panel labels | **Low** | NetBox | Pure documentation feature. Could be a simple editable table overlay on the topology. Useful for small office wiring documentation. | Medium |
| N4 | **Customizable scan profile templates** — save and name scan configurations (e.g., "Quick audit", "Full security scan", "Lab exercise scan") with specific scan depth, targets, and module selection | **Low** | Nmap profiles, Zenmap | Nmap/Zenmap popularized named scan profiles. NetSentinel has a fixed scan flow; letting users save presets would improve repeatability and reduce friction for repeat audits. | Small |
| N5 | **Mobile companion app / PWA dashboard** — read-only view of current network status from a phone | **Low** | ntopng (mobile-responsive web UI) | The browser dashboard at `/dashboard` partially covers this. A PWA manifest + push notification integration would make it fully mobile. | Medium |

---

## Dark Horse Recommendations

### Dark Horse 1 — eBPF-based kernel network observability (Linux)

**The opportunity:** Tools like Cilium Hubble and Pixie use Linux eBPF to capture per-process, per-connection flow data with near-zero overhead — no packet capture, no special drivers, no root-level raw sockets. They answer "which process on which host opened a connection to 1.2.3.4:443 and how long did it take?" at the kernel level.

**For NetSentinel:** An optional eBPF backend for the `process_monitor.py` module would give dramatically richer process-to-connection data on Linux without the polling overhead of psutil. More importantly, it would enable **per-application latency measurement** — you'd know that Firefox's DNS resolution took 340ms but curl's took 8ms — which is exactly the kind of finding the "What's Wrong?" diagnosis page needs.

**Why this is a dark horse:** None of the benchmark tools integrate eBPF into a desktop GUI. It's a cloud-native technology being applied to home networks. The user installs one kernel module; NetSentinel handles the rest. This would be a genuine first in this category.

**Feasibility:** Linux only. Requires a libbpf Python binding (bcc or pybpf). Could be exposed as an optional hardware plugin so it's not a hard dependency.

---

### Dark Horse 2 — Local LLM-powered "Network Analyst" mode

**The opportunity:** Tools like Ollama (local LLM runner) are now fast enough to run 7B-parameter models on consumer hardware. No benchmark tool combines a local LLM with real scan data to produce conversational root cause analysis.

**For NetSentinel:** A "Network Analyst" chat interface that receives the current scan result JSON, the RTT time series, the alert history, and the device topology — and lets the user ask "why is my video conferencing choppy?" or "is this new device I don't recognize a threat?" in plain English. The LLM would have structured context (not a raw chat) and would be prompted to cite specific data points ("Your RTT to 8.8.8.8 spiked to 450ms at 14:23, coinciding with device 192.168.1.45 generating 340 ARP requests/sec").

**Why this is a dark horse:** The NL query module (`nl_query.py`) and the root cause correlator already do structured analysis. Adding an LLM reasoning layer on top of existing structured outputs is a force multiplier, not a rewrite. It would transform the "What's Wrong?" page from a symptom picker into a genuine conversational diagnostic tool — something no open-source competitor offers.

**Feasibility:** Requires Ollama as an optional dependency (user installs separately). A new `modules/llm_analyst.py` module would query the local Ollama REST API with structured prompts. The UI would be a simple chat panel in the Diagnosis section. Works offline, no data leaves the machine — preserves the local-first value proposition.

---

### Dark Horse 3 — Topology DNA / structural change fingerprinting

**The opportunity:** No tool in this category automatically detects and explains *structural* network changes — the difference between "device A went offline" (which every monitoring tool catches) and "the network's physical topology changed: a new switch appeared between your router and your NAS, and you didn't put it there."

**For NetSentinel:** `topology_snapshot.py` (Sprint 4) already captures topology snapshots and `topology_diff.py` computes diffs. The missing layer is a **topology fingerprint** — a hash of the structural graph (adjacency matrix, hop counts, LLDP neighbor relationships) that can be compared across time. A structural change — new intermediate hop, missing LLDP neighbor, new switch between trusted devices — would trigger a high-severity alert with a visual before/after diff.

**Why this is a dark horse:** This is a Man-in-the-Middle detection primitive that doesn't require any crypto, signatures, or certificate pinning. If someone inserts a rogue switch or a transparent proxy between the router and a device, the LLDP topology changes. No other home network tool detects this. The infrastructure (LLDP scanner, topology snapshots, Cytoscape diff) is already 80% built.

**Feasibility:** Small. Requires hashing the adjacency structure of the LLDP/ARP topology graph and comparing to the last known-good baseline. Could ship as a new alert type in `alert_engine.py` within a single sprint.

---

## Priority Recommendations — Next Three Sprints

### Sprint Priority 1 (Highest ROI)

| Item | Rationale |
|---|---|
| **O1 — Alert dependency trees** | Eliminates the biggest operational pain point for any user monitoring 5+ devices. Existing `alert_suppressor.py` is the right extension point. |
| **O2 — Alert acknowledgement** | Pairs with O1. Without ack, dependency suppression alone doesn't prevent re-notification after recovery. |
| **V1 — Bandwidth overlay on topology** | Requires wiring the existing bandwidth monitor to the Cytoscape topology — high visual impact, low new code. |
| **Dark Horse 3 — Topology DNA** | 80% of the infrastructure exists. One sprint to close. Unique capability, high security value. |

### Sprint Priority 2 (Strategic Differentiation)

| Item | Rationale |
|---|---|
| **D1 — Switch-port MAC table correlation** | The most-requested capability in managed LAN environments. Requires SNMP MAC table polling — new but well-scoped. |
| **P3 — Deauth flood detection** | Small addition to existing 802.11 monitor alert rules. High user-visible value for home security. |
| **A3 — Slack notification channel** | Single webhook call. Highest-demand missing channel for SMB IT admins. |
| **O6 — SLA / uptime reporting** | MetricStore already stores all the data. A report builder on top of `metric_store_queries_uptime.py`. |

### Sprint Priority 3 (Capability Expansion)

| Item | Rationale |
|---|---|
| **A2 — NetFlow/sFlow collector** | Enables per-host/per-app traffic history without DPI. High value for homelab users with OpenWRT/pfSense. Large but strategically important. |
| **D2 — Per-device software inventory** | Feeds the CVE tracker with version strings rather than port guesses. Pairs with SNMP poller. |
| **Dark Horse 2 — Local LLM analyst** | Requires Ollama as optional dep. Differentiating capability that no competitor offers. Pilot as an optional plugin. |
| **A1 — Nagios plugin compatibility** | Instant access to 6,000 community checks. Medium complexity, enormous leverage. |

---

## Feature Coverage Summary

| Domain | NetSentinel Coverage | Primary Gap |
|---|---|---|
| Device Discovery | ◆◆◆◆◇ Strong | Switch-port physical location (D1) |
| Traffic Analysis | ◆◆◆◇◇ Good | NetFlow/sFlow collector (A2) |
| Topology Visualization | ◆◆◆◇◇ Good | Traffic overlay (V1), protocol flow graph (V3) |
| Alert & Monitoring | ◆◆◆◇◇ Good | Dependency suppression (O1), acknowledgement (O2) |
| Security / WiFi | ◆◆◆◆◇ Strong | Deauth/WPS detection (P3, P1) |
| Inventory Management | ◆◆◆◇◇ Good | Software inventory (D2), IPAM (D5), audit log (O5) — startup cache restore shipped v2.1.5 |
| Automation / API | ◆◆◆◇◇ Good | NetFlow (A2), Nagios compat (A1), Prometheus (A6) |
| Education | ◆◆◆◆◆ Best-in-class | No meaningful gap |
| Reporting | ◆◆◆◆◇ Strong | SLA reporting (O6), scan comparison (V5) |
| Operational Maturity | ◆◆◇◇◇ Developing | Dependency trees (O1), ack (O2), event dedup (O4) |

---

*This analysis is based on NetSentinel v2.1.4 features as documented in CLAUDE.md and current capabilities of the listed open-source tools as of mid-2026. Priorities assume the stated target audience of IT admins, homelab users, and students.*
