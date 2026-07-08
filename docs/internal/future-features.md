# NetSentinel — Future Feature Inspiration

*Internal engineering reference — not a public roadmap. Items derived from benchmarking against
Nmap, Netdisco, LibreNMS, ntopng, Kismet, NetworkMiner, Angry IP Scanner, NetBox, Wireshark,
Icinga2, Checkmk, and Rumble (runZero). Status reviewed against **v2.1.25**: every item below is
tagged **Partial** (substrate already exists, only a slice remains) or **Unbuilt**. Items that
fully shipped since the last review were pulled from the tables and are listed under "Recently
shipped" so they are not proposed again.*

---

## Recently shipped — do not re-add

These graduated from this list into the product. Kept here as pointers so nobody re-proposes them:

- **O1 — Alert dependency trees** (suppress downstream alerts when a parent device is down) →
  `modules/alert_engine.py` (`set_dependency_map` / `_is_dependency_suppressed`); UI
  `ui/pages/notif_dep_card.py`; `tests/test_dependency_suppression.py`. *(Landed in
  `alert_engine.py`, not `alert_suppressor.py` as this doc once guessed.)*
- **O2 — Per-alert acknowledgement with comment and owner** → `MetricStore.acknowledge_alert()`;
  `alert_fired.acked_ts / acked_by / acked_comment`; UI `ui/widgets/alert_drawer.py`;
  `tests/test_alert_ack_comment.py`.
- **O3 — Scheduled downtime with auto-resume + UI** → `modules/maintenance_window.py`
  (`MaintenanceWindowManager`, `is_currently_active`); page `ui/pages/maintenance_page.py`.
- **D4 — Service banner grabbing at scale** → `modules/port_scanner.py` `probe_service()`
  (SSH / FTP / SMTP / HTTP Server header + more); Version/Banner inventory columns; version
  strings already feed `CVELookupWorker`.

---

## Discovery & Inventory

| # | Feature | Status | Priority | Benchmark source | Why it matters | Complexity |
|---|---|---|---|---|---|---|
| D1 | **Switch-port MAC table correlation** — "Where is this device physically connected?" (switch IP, interface, VLAN) | Partial | High | Netdisco | The #1 question in any managed LAN. **Built:** LLDP neighbor discovery + topology overlay (`modules/lldp_scanner.py`, `workers/lldp_worker.py`). **Remaining:** SNMP BRIDGE-MIB `dot1dTpFdb` FDB walk + VLAN mapping to answer "which switch port is this end-device MAC on." | Large |
| D2 | **Per-device installed software inventory** | Partial | Medium | Checkmk, LibreNMS | Knowing a device runs Apache 2.4.48 is more actionable than knowing port 80 is open. **Built:** credentialed SSH scan (dpkg/rpm/`Win32_Product`) + Software table (`modules/credentialed_scan.py`). **Remaining:** agentless SNMP `hrSWInstalled`/WMI path; feed collected versions into the CVE tracker. | Medium |
| D3 | **SNMP device configuration backup** — snapshot running-config, detect config drift | Unbuilt | Medium | LibreNMS (RANCID) | "Who changed the switch config and when?" `config_baseline.py` snapshots device *inventory* + scalar OIDs, not device running-configs. | Medium |
| D5 | **Full IPAM — IP prefix/subnet hierarchy with utilization tracking** | Unbuilt | Low | NetBox | `/24` segment grouping exists (`network_segments.py`) but not a navigable prefix hierarchy with used/total utilization. | Large |
| D6 | **Nmap NSE script execution UI** — right-click "Run script" on a device row; results parsed into the device record | Unbuilt | Low | Nmap NSE | Exposes 600+ NSE scripts with zero new module code. (Only nmap *XML export* exists today.) | Small |
| D7 | **IPv6 neighbor discovery completeness** — DHCPv6 leases, SLAAC address correlation, NDP table sweep | Partial | Low | Nmap, LibreNMS | **Built:** NDP table sweep (`get_ipv6_devices()`, `ping_sweep_ipv6()`) + a navigable "IPv6 Devices" page. **Remaining:** DHCPv6 lease parsing + SLAAC address correlation. | Medium |

---

## Visualization

| # | Feature | Status | Priority | Benchmark source | Why it matters | Complexity |
|---|---|---|---|---|---|---|
| V3 | **Protocol flow sequence diagram** — interactive timeline of packet exchanges between two hosts (Wireshark "Follow Stream" but visual) | Unbuilt | Medium | Wireshark flow graph | Protocol Visualizer has canned animations; a real-traffic sequence diagram from a live or uploaded pcap would be far more powerful. (Depends on N2 pcap import.) | Large |
| V6 | **Per-segment traffic heatmap** (time-of-day activity by subnet/device group) | Unbuilt | Low | ntopng | Shows which devices are active at 3 AM — powerful for IoT anomaly detection. (Only a WiFi *signal* heatmap exists today.) | Medium |

---

## Automation & Integration

| # | Feature | Status | Priority | Benchmark source | Why it matters | Complexity |
|---|---|---|---|---|---|---|
| A1 | **Nagios/NRPE plugin compatibility** — `check_*` exit code → NetSentinel service status | Unbuilt | High | Nagios, Icinga2 | Instant access to 6,000+ community checks (check_ssl, check_postgres, check_docker, …) without writing new workers. | Medium |
| A2 | **NetFlow/sFlow/IPFIX collector** — listen for flow exports from routers/switches | Unbuilt | High | LibreNMS, ntopng | Enables per-host/per-app bandwidth history without DPI. OpenWRT, pfSense, MikroTik can all export NetFlow. | Large |
| A3 | **Slack / PagerDuty / OpsGenie notification channels** | Partial | Medium | LibreNMS, Icinga2 | Slack is table-stakes for SMB. **Built:** generic `WebhookChannel` (POSTs the canonical NetSentinel JSON). **Remaining:** emit Slack's block/text payload shape so it renders natively (+ optional PagerDuty Events API / OpsGenie). | Small |
| A4 | **Webhook inbound triggers** — HTTP POST to trigger scan, acknowledge alert, add maintenance window | Unbuilt | Medium | LibreNMS REST, Icinga2 API | Enables Ansible/Terraform/N-central integration without polling. REST API is read-only (GET) today. | Medium |
| A5 | **Ticket system integration** — auto-create tickets in Jira/Freshservice/Zendesk on alert fire | Unbuilt | Low | Icinga2, Checkmk | Even a pre-formatted webhook template would cover most cases. | Small |
| A6 | **Prometheus `/metrics` endpoint** — device count, alert count, RTT p95, scan age | Unbuilt | Low | LibreNMS community exporter | Homelab Prometheus+Grafana users want to pull NetSentinel data into existing dashboards. Single-file addition to the Flask API. | Small |
| A7 | **GraphQL API** | Unbuilt | Low | NetBox | Allows integrations to request exactly the fields they need. Low priority given REST already covers most use cases. | Large |

---

## Operational / Alert Maturity

| # | Feature | Status | Priority | Benchmark source | Why it matters | Complexity |
|---|---|---|---|---|---|---|
| O4 | **Alert deduplication / event correlation** — 15 "host unreachable" events → one "segment outage" incident | Partial | Medium | Checkmk Event Console, OpenNMS | **Built:** same-cycle HOST_DOWN consolidation (≥5 simultaneous → one "(network)" alert) + per-rule cooldown dedup (`alert_engine.evaluate_cycle`). **Remaining:** persistent incident objects, cross-rule-type + subnet/time-window correlation. | Large |
| O5 | **Per-device audit log / change history** — every device record change with timestamp and source | Partial | Medium | NetBox, LibreNMS | "Who changed the alert threshold for the NAS and when?" **Built:** `device_events` table + `record_device_change_event` + `get_device_change_events`, tested. **Remaining:** the writer is only called from tests — wire it into the live scan/diff path, and add a per-device change-history view in the UI. | Medium |
| O6 | **SLA / uptime reporting** — 30/90-day availability % per device, breach report | Partial | Medium | LibreNMS, Checkmk | **Built:** Uptime & SLA page (24h/7d/30d), `query_uptime_table`, REST `/uptime/<ip>`. **Remaining:** 90-day window, a configurable SLA target, and a breach report/list. | Small |
| O7 | **On-call rotation scheduling** | Unbuilt | Low | Icinga2, PagerDuty | Overkill for home use; relevant if NetSentinel becomes primary monitoring for an SMB. Closest primitive today is the static `EscalationPolicy`. | Large |

---

## Protocol & Security Analysis

| # | Feature | Status | Priority | Benchmark source | Why it matters | Complexity |
|---|---|---|---|---|---|---|
| P1 | **WPS attack detection** — Pixie Dust / bruteforce attempt alerts from passive 802.11 capture | Unbuilt | Medium | Kismet | `wifi_monitor_page.py` captures frames but has no WPS-IE parsing or attack alert rules. (`wifi_scanner.py` only flags networks that *have* WPS enabled.) | Medium |
| P2 | **PMKID / EAPOL handshake capture alerts** — detect WPA handshake capture attempts | Unbuilt | Medium | Kismet | Passive detection, no credentials required. A real home-network threat. EAPOL frames are not even parsed today. | Medium |
| P3 | **Deauth / disassociation flood detection** | Partial | Medium | Kismet, commercial IDS | High user-visible value. **Built:** deauth frames are already captured/labeled in the 802.11 monitor (`workers/wifi_monitor_worker.py`). **Remaining:** per-source rate/threshold flood detection + an alert rule. | Small |
| P4 | **TLS certificate transparency log monitoring** — alert on unexpected certs issued for your domain | Unbuilt | Low | Various CT tools | Background worker polling crt.sh. Small addition alongside `cert_monitor.py` (which today only checks your own hosts' cert expiry). | Small |
| P5 | **DNS rebinding attack detection** — flag public domains resolving to RFC 1918 addresses | Unbuilt | Low | Various DNS tools | `dns_correlator.py` monitors latency and discards resolved IPs; it never inspects response content. | Small |
| P6 | **Passive OS fingerprinting** (p0f-style) — identify OS from SYN packets without sending probes | Unbuilt | Low | NetworkMiner, p0f | Complements the *active* fingerprinting in `os_fingerprint.py` (TTL + Scapy SYN probe). | Medium |

---

## Nice-to-Have

| # | Feature | Status | Priority | Benchmark source | Why it matters | Complexity |
|---|---|---|---|---|---|---|
| N1 | **Bluetooth/BLE device scanning** | Unbuilt | Low | Kismet | Completes the "what's in my airspace" view for IoT environments. | Medium |
| N2 | **PCAP file import and offline analysis** | Unbuilt | Low | Wireshark, NetworkMiner | Post-incident analysis reusing the protocol visualizer and topology builder. Unblocks V3. | Large |
| N3 | **Cable / physical port mapping** — editable table overlay on the topology | Unbuilt | Low | NetBox | Documentation feature for small office wiring. | Medium |
| N4 | **Named scan profile templates** — save "Quick audit", "Full security scan", etc. | Unbuilt | Low | Nmap profiles, Zenmap | Reduces friction for repeat audits. | Small |
| N5 | **Mobile companion / PWA dashboard** | Partial | Low | ntopng | **Built:** responsive `/dashboard` (`modules/web_dashboard.py` — viewport meta, media queries, 30 s auto-refresh). **Remaining:** `manifest.json` + service worker to make it installable/offline. | Medium |

---

## Dark Horses

### eBPF-based kernel network observability (Linux only) — *Unbuilt*

Cilium Hubble and Pixie use Linux eBPF to capture per-process, per-connection flow data with
near-zero overhead — no raw sockets, no Npcap. Would give `process_monitor.py` (today psutil-based)
dramatically richer data and enable per-application latency measurement: "Firefox's DNS resolution
took 340ms, curl's took 8ms." No desktop GUI tool in this category does this. Could ship as an
optional hardware plugin (libbpf / pybpf dependency).

### Local LLM-powered "Network Analyst" mode — *Unbuilt*

A chat interface fed the current scan JSON, RTT time series, alert history, and device topology —
letting the user ask "why is my video conferencing choppy?" and getting an answer that cites
specific data points. `nl_query.py` and `root_cause_correlator.py` already do structured analysis,
but both are explicitly rule/keyword-based (zero-dependency, offline) — an LLM reasoning layer is a
force multiplier, not a rewrite. Requires Ollama as an optional dependency. Works fully offline.

### Topology DNA / structural change fingerprinting — *Partial*

`topology_snapshot.py` captures snapshots and computes diffs (`TopologyDiff` / `diff_snapshots`
live inside that same module — there is no separate `topology_diff.py`). The missing layer is a
structural fingerprint — a hash of the adjacency graph (hop counts, LLDP neighbor relationships)
compared over time. A new intermediate hop or missing LLDP neighbor triggers a high-severity alert.
This is a passive Man-in-the-Middle detection primitive that no other home network tool offers.
**Built:** snapshot + IP/edge diff. **Remaining:** the adjacency-graph structural hash; real
hop/LLDP adjacency (edges today are synthetic gateway→device star edges); and the alert layer in
`alert_engine.py`.

---

## Priority Order

*Inspiration, not a committed roadmap — the product is feature-complete (v2.1.0+) and Microsoft
Store ready. Building any of these needs an explicit go-ahead. Order reflects ROI: the "Highest
ROI" tier is where substrate already exists and only a slice remains.*

**Highest ROI (near-done — substrate already exists)**
- O5 Device audit-log UI — backend + tests already built; wire the capture path + add a view
- O6 SLA 90-day window + breach report — the data is already in MetricStore
- A3 Slack payload — a thin shim over the existing `WebhookChannel`
- P3 Deauth flood detection — the 802.11 monitor already captures the frames
- N5 PWA manifest — `/dashboard` is already responsive

**Strategic differentiation (larger, net-new)**
- D1 Switch-port MAC table correlation (SNMP BRIDGE-MIB) — the managed-LAN "where is this plugged in" answer; LLDP half is already done
- A2 NetFlow/sFlow collector — enables per-host traffic history without DPI
- Dark Horse — Topology DNA fingerprint — snapshot/diff already built; adds a unique passive-MitM primitive

**Capability expansion**
- D2 Per-device software inventory — feed the CVE tracker with version strings
- A6 Prometheus `/metrics` endpoint — single-file addition to the Flask API
- Dark Horse — Local LLM analyst — no-network, differentiating, pilot as an optional plugin
- A1 Nagios plugin compatibility — 6,000 community checks for free
