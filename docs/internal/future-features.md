# NetSentinel — Future Feature Inspiration

*Internal engineering reference — not a public roadmap. Items derived from benchmarking against Nmap, Netdisco, LibreNMS, ntopng, Kismet, NetworkMiner, Angry IP Scanner, NetBox, Wireshark, Icinga2, Checkmk, and Rumble (runZero). All items below are unimplemented as of v2.1.13.*

---

## Discovery & Inventory

| # | Feature | Priority | Benchmark source | Why it matters | Complexity |
|---|---|---|---|---|---|
| D1 | **Switch-port MAC table correlation** — "Where is this device physically connected?" (switch IP, interface, VLAN) | High | Netdisco | The #1 question in any managed LAN. Requires SNMP MAC table + LLDP correlation. | Large |
| D2 | **Per-device installed software inventory** (SNMP MIB-II hrSWInstalled or WMI/psutil) | Medium | Checkmk, LibreNMS | Knowing a device runs Apache 2.4.48 is more actionable than knowing port 80 is open. Feeds the CVE tracker directly. | Medium |
| D3 | **SNMP device configuration backup** — snapshot running-config, detect config drift | Medium | LibreNMS (RANCID) | "Who changed the switch config and when?" `config_baseline.py` handles device inventory but not device configs. | Medium |
| D4 | **Service banner grabbing at scale** — HTTP Server header, SSH version, FTP greeting, SMTP EHLO as inventory columns | Medium | Rumble, Nmap `-sV` | Version strings feed CVE correlation far better than port numbers alone. | Medium |
| D5 | **Full IPAM — IP prefix/subnet hierarchy with utilization tracking** | Low | NetBox | /24 segment grouping exists but not a navigable prefix hierarchy. | Large |
| D6 | **Nmap NSE script execution UI** — right-click "Run script" on a device row; results parsed into the device record | Low | Nmap NSE | Exposes 600+ NSE scripts with zero new module code. | Small |
| D7 | **IPv6 neighbor discovery completeness** — DHCPv6 leases, SLAAC address correlation, NDP table sweep | Low | Nmap, LibreNMS | `get_ipv6_devices()` and `ping_sweep_ipv6()` exist but IPv6 inventory is incomplete in the UI. | Medium |

---

## Visualization

| # | Feature | Priority | Benchmark source | Why it matters | Complexity |
|---|---|---|---|---|---|
| V3 | **Protocol flow sequence diagram** — interactive timeline of packet exchanges between two hosts (Wireshark "Follow Stream" but visual) | Medium | Wireshark flow graph | Protocol Visualizer has canned animations; a real-traffic sequence diagram from a live or uploaded pcap would be far more powerful. | Large |
| V6 | **Per-segment traffic heatmap** (time-of-day activity by subnet/device group) | Low | ntopng | Shows which devices are active at 3 AM — powerful for IoT anomaly detection. | Medium |

---

## Automation & Integration

| # | Feature | Priority | Benchmark source | Why it matters | Complexity |
|---|---|---|---|---|---|
| A1 | **Nagios/NRPE plugin compatibility** — `check_*` exit code → NetSentinel service status | High | Nagios, Icinga2 | Instant access to 6,000+ community checks (check_ssl, check_postgres, check_docker, …) without writing new workers. | Medium |
| A2 | **NetFlow/sFlow/IPFIX collector** — listen for flow exports from routers/switches | High | LibreNMS, ntopng | Enables per-host/per-app bandwidth history without DPI. OpenWRT, pfSense, MikroTik can all export NetFlow. | Large |
| A3 | **Slack / PagerDuty / OpsGenie notification channels** | Medium | LibreNMS, Icinga2 | Slack is table-stakes for SMB. Single webhook call. | Small |
| A4 | **Webhook inbound triggers** — HTTP POST to trigger scan, acknowledge alert, add maintenance window | Medium | LibreNMS REST, Icinga2 API | Enables Ansible/Terraform/N-central integration without polling. | Medium |
| A5 | **Ticket system integration** — auto-create tickets in Jira/Freshservice/Zendesk on alert fire | Low | Icinga2, Checkmk | Even a pre-formatted webhook template would cover most cases. | Small |
| A6 | **Prometheus `/metrics` endpoint** — device count, alert count, RTT p95, scan age | Low | LibreNMS community exporter | Homelab Prometheus+Grafana users want to pull NetSentinel data into existing dashboards. Single-file addition to the Flask API. | Small |
| A7 | **GraphQL API** | Low | NetBox | Allows integrations to request exactly the fields they need. Low priority given REST already covers most use cases. | Large |

---

## Operational / Alert Maturity

| # | Feature | Priority | Benchmark source | Why it matters | Complexity |
|---|---|---|---|---|---|
| O1 | **Alert dependency trees** — suppress downstream alerts when a parent device (gateway, switch) goes down | High | Nagios, Icinga2, LibreNMS | A single router outage generates 30+ alerts without dependency suppression. `alert_suppressor.py` is the right extension point. | Medium |
| O2 | **Per-alert acknowledgement with comment and owner** | High | Nagios, Icinga2, LibreNMS | Without ack, the same alert re-notifies every check cycle. | Medium |
| O3 | **Scheduled downtime with reason** — start time, end time, comment, auto-resume | Medium | Nagios, Icinga2 | `maintenance_window.py` exists but the UX for defining windows is not discoverable. May be a UX gap, not a feature gap. | Small |
| O4 | **Alert deduplication / event correlation** — 15 "host unreachable" events → one "segment outage" incident | Medium | Checkmk Event Console, OpenNMS | Reduces noise dramatically for multi-device environments. | Large |
| O5 | **Per-device audit log / change history** — every device record change with timestamp and source | Medium | NetBox, LibreNMS | "Who changed the alert threshold for the NAS and when?" | Medium |
| O6 | **SLA / uptime reporting** — 30-day/90-day availability % per device, breach report | Medium | LibreNMS, Checkmk | MetricStore already stores all the data. Report builder on top of `metric_store_queries_uptime.py`. | Small |
| O7 | **On-call rotation scheduling** | Low | Icinga2, PagerDuty | Overkill for home use; relevant if NetSentinel becomes primary monitoring for an SMB. | Large |

---

## Protocol & Security Analysis

| # | Feature | Priority | Benchmark source | Why it matters | Complexity |
|---|---|---|---|---|---|
| P1 | **WPS attack detection** — Pixie Dust / bruteforce attempt alerts from passive 802.11 capture | Medium | Kismet | `wifi_monitor_page.py` captures frames but has no WPS-specific alert rules. | Medium |
| P2 | **PMKID / EAPOL handshake capture alerts** — detect WPA handshake capture attempts | Medium | Kismet | Passive detection, no credentials required. A real home-network threat. | Medium |
| P3 | **Deauth / disassociation flood detection** | Medium | Kismet, commercial IDS | Small addition to existing 802.11 monitor alert rules. High user-visible value. | Small |
| P4 | **TLS certificate transparency log monitoring** — alert on unexpected certs issued for your domain | Low | Various CT tools | Background worker polling crt.sh. Small addition to `cert_monitor.py`. | Small |
| P5 | **DNS rebinding attack detection** — flag public domains resolving to RFC 1918 addresses | Low | Various DNS tools | `dns_correlator.py` monitors latency but not response content. | Small |
| P6 | **Passive OS fingerprinting** (p0f-style) — identify OS from SYN packets without sending probes | Low | NetworkMiner, p0f | Complements active OS fingerprinting in `os_fingerprint.py`. | Medium |

---

## Nice-to-Have

| # | Feature | Priority | Benchmark source | Why it matters | Complexity |
|---|---|---|---|---|---|
| N1 | **Bluetooth/BLE device scanning** | Low | Kismet | Completes the "what's in my airspace" view for IoT environments. | Medium |
| N2 | **PCAP file import and offline analysis** | Low | Wireshark, NetworkMiner | Post-incident analysis reusing the protocol visualizer and topology builder. | Large |
| N3 | **Cable / physical port mapping** — editable table overlay on the topology | Low | NetBox | Documentation feature for small office wiring. | Medium |
| N4 | **Named scan profile templates** — save "Quick audit", "Full security scan", etc. | Low | Nmap profiles, Zenmap | Reduces friction for repeat audits. | Small |
| N5 | **Mobile companion / PWA dashboard** | Low | ntopng | The `/dashboard` page partially covers this; a PWA manifest would finish it. | Medium |

---

## Dark Horses

### eBPF-based kernel network observability (Linux only)

Cilium Hubble and Pixie use Linux eBPF to capture per-process, per-connection flow data with near-zero overhead — no raw sockets, no Npcap. Would give `process_monitor.py` dramatically richer data and enable per-application latency measurement: "Firefox's DNS resolution took 340ms, curl's took 8ms." No desktop GUI tool in this category does this. Could ship as an optional hardware plugin (libbpf / pybpf dependency).

### Local LLM-powered "Network Analyst" mode

A chat interface fed the current scan JSON, RTT time series, alert history, and device topology — letting the user ask "why is my video conferencing choppy?" and getting an answer that cites specific data points. `nl_query.py` and `root_cause_correlator.py` already do structured analysis; an LLM reasoning layer is a force multiplier, not a rewrite. Requires Ollama as an optional dependency. Works fully offline.

### Topology DNA / structural change fingerprinting

`topology_snapshot.py` captures snapshots and `topology_diff.py` computes diffs. The missing layer is a structural fingerprint — a hash of the adjacency graph (hop counts, LLDP neighbor relationships) compared over time. A new intermediate hop or missing LLDP neighbor triggers a high-severity alert. This is a passive Man-in-the-Middle detection primitive that no other home network tool offers. The infrastructure is ~80% built; could ship as a new alert type in `alert_engine.py`.

---

## Priority Order

**Highest ROI**
- O1 Alert dependency trees (eliminates alert fatigue, `alert_suppressor.py` is the extension point)
- O2 Alert acknowledgement (pairs with O1)
- Dark Horse 3 — Topology DNA (80% built, unique security value)

**Strategic differentiation**
- D1 Switch-port MAC table correlation (most-requested in managed LAN environments)
- P3 Deauth flood detection (small code change, high user value)
- A3 Slack notification channel (single webhook call)
- O6 SLA / uptime reporting (data already in MetricStore)

**Capability expansion**
- A2 NetFlow/sFlow collector (enables per-host traffic history without DPI)
- D2 Per-device software inventory (feeds CVE tracker with version strings)
- Dark Horse 2 — Local LLM analyst (no-network, differentiating, pilot as plugin)
- A1 Nagios plugin compatibility (6,000 community checks for free)
