# NetSentinel — Full Product Backlog

> Last updated: 2026-04-29 (full audit: items 9 and 20 moved to already-built; items 17/18 annotated with partial implementations; all items renumbered)  
> Purpose: Complete long-term roadmap. Items are ordered within each tier by impact-to-effort ratio.  
> Items already shipped are not listed here. Partial implementations are noted explicitly.

---

## What is already built (reference, not backlog)

| Capability | Module(s) |
|---|---|
| **Discovery & Inventory** | |
| Network device discovery (ARP scan) | `combined_discovery` |
| Device type + OUI classification | `device_classifier`, `mac_registry` |
| MAC vendor resolution (local → offenders.json → macvendors API) | `mac_lookup` |
| Device join/leave tracking (persistent history) | `device_tracker` |
| Per-device risk scoring | `risk_scorer` |
| SMB/NetBIOS enumeration | `smb_enumerator` |
| Name resolution (NetBIOS, mDNS, rDNS, SNMP, DHCP) | `name_resolver` |
| **Threat Detection** | |
| Rogue device detection | `rogue_device`, `combined_discovery` |
| ARP spoofing / gateway hijack | `arp_monitor` |
| Rogue bridge / STP root takeover detection | `stp_detector` |
| Broadcast storm analysis | `storm_analyser` |
| Rogue DHCP server detection | `dhcp_detector` |
| WiFi enumeration + rogue SSID | `wifi_scanner` |
| Active security audit (SYN/UDP/OS/CVE/creds) | `syn_scanner`, `os_fingerprint`, `cve_lookup`, `credentialed_scan` |
| TCP port scanner | `port_scanner` |
| Internet exposure + UPnP mapping | `internet_exposure` |
| Private endpoint exposure check | `private_endpoint_checker` |
| Cloud metadata exposure check | `cloud_metadata` |
| IoT behaviour baselining | `iot_baseline` |
| Home Automation Hub (OUI + port-probe HA detection) | `ha_detector`, `mac_lookup`, `ui/pages/home_automation_page.py` |
| **Monitoring & Metrics** | |
| DNS/RTT monitoring + outage detection | `dns_correlator`, `network_logger` |
| Availability monitoring + SLA uptime | `availability_monitor`, `ui/pages/uptime_page.py` |
| Service heartbeat monitoring (TCP check) | `service_monitor` |
| TLS/cert expiry monitoring | `cert_monitor`, `tls_checker` |
| SNMP polling + trap receiver | `snmp_poller`, `snmp_trap_receiver` |
| Syslog receiver | `syslog_receiver` |
| Per-device bandwidth monitoring (Scapy, per-MAC) | `bandwidth_monitor` |
| Live interface bandwidth (psutil, 60s rolling chart) | `workers/iface_bw_worker.py`, `ui/pages/live_bandwidth_page.py` |
| Stability log chart / analysis | `log_chart` |
| Predictive trend analysis (OLS regression, ETA-to-threshold) | `trend_analyser` |
| **Analysis & Intelligence** | |
| Root cause correlator (STP/Storm/DNS/Logger verdict) | `root_cause_correlator` |
| Alert engine (flap, cooldown, dependency suppression) | `alert_engine` |
| Maintenance window manager (alert suppression) | `maintenance_window` |
| Config baseline + drift detection | `config_baseline` |
| Network benchmark / health grade (A–F) | `network_benchmark` |
| Network diagnostics (ping, DNS leak, traceroute, HTTP) | `network_diagnostics` |
| Natural language device query | `nl_query` |
| **Infrastructure** | |
| Central SQLite metric store (schema v6, WAL, threading) | `metric_store` |
| Recurring scan scheduler | `scheduler` |
| Plugin system (load/execute custom report plugins) | `plugin_system` |
| Report generation + scheduler | `report_exporter`, `report_scheduler` |
| Notification routing (Toast / Webhook / Email) | `notification_router` |
| **UI Features** | |
| Speed test (Ookla-compatible, server select, arc gauge) | `speed_tester`, `ui/pages/speed_test_page.py` |
| Active Connections (process-to-socket map + geo) | `process_monitor`, `ui/pages/connections_page.py` |
| Kill Connection / per-process firewall block | `process_monitor`, `ui/pages/connections_page.py` |
| Network topology visualisation | `ui/topology_widget.py` |
| System tray guardian (badge, toasts, minimize-to-tray) | `ui/system_tray.py` |
| Run on startup toggle (Windows registry) | `ui/system_tray.py`, `ui/pages/settings_page.py` |
| Wake-on-LAN from the UI | `modules/utils.py` (`send_wol`), right-click context menu in Devices table, dedicated WoL card in Advanced → Tools |
| Three colour themes (Arctic Clean / Midnight Pro / Obsidian Neon) | `ui/styles.py` (`THEMES`, `get_active_theme_name`, `set_active_theme_name`), `ui/pages/settings_page.py` |
| DHCP lease inventory page | `modules/dhcp_lease_scanner.py`, `workers/dhcp_lease_worker.py`, `ui/pages/dhcp_lease_page.py` — platform-aware parser (dnsmasq/dhclient/nmcli/ARP+ipconfig); KPI tiles + sortable table; Discover subgroup |
| Push notifications (Pushover / ntfy / Telegram) | `modules/notification_router.py` (PushoverChannel, NtfyChannel, TelegramChannel + delivery functions); `ui/pages/notifications_page.py` (3 new channel cards with Test buttons; all tokens in OS keychain) |
| Threat intelligence feed integration | `modules/threat_intel.py` (ThreatIntelDB, Feodo+ET feeds, AbuseIPDB); `workers/threat_intel_worker.py`; `ui/pages/threat_intel_page.py` (KPI tiles, consent card, manual lookup, blocklist table; Security Audit section) |
| DNS zone mapping page | `modules/dns_zone_scanner.py`, `workers/dns_zone_worker.py`, `ui/pages/dns_zone_page.py` — AXFR zone transfer (raw TCP/53) + mDNS Bonjour/Avahi service enumeration; split-panel table; Discover subgroup |
| MAC clone / dual-claim detection | `modules/arp_monitor.py` — `MAC_CLONE` event type; `ARPSniffer` tracks per-MAC seen-IPs; fires when same MAC appears on two IPs simultaneously |
| CVE lifecycle tracker | `modules/metric_store.py` (cve_lifecycle + alert_fired tables, schema v7); `ui/pages/cve_page.py` — state machine (Open → Acknowledged → Accepted Risk → Remediated), import from scan, days-open counter, right-click state change |
| PDF report export | `modules/report_exporter.py` (`save_pdf_report()`): tries weasyprint → headless Edge → headless Chrome; "Export PDF" button in Reports page |
| Alert escalation | `modules/alert_engine.py` (`EscalationPolicy` dataclass, `set_escalation_policies()`, `check_escalations()`); `modules/metric_store.py` (alert_fired table, `record_alert_fired`, `acknowledge_alert`, `get_unacked_alerts`); escalation config card in Notifications page |
| REST API (read-only, local) | `modules/rest_api.py` (Flask, binds `127.0.0.1` by default, OS-keychain API key, 5 endpoints: `/health` `/devices` `/alerts` `/uptime/<ip>` `/speed-history`); `workers/rest_api_worker.py` (QThread daemon); REST API card in Settings page — enable toggle, port, external-access toggle + warning, show/regenerate key; disabled by default |

---

## Tier 1 — Quick wins (high value, low effort)

> All Tier 1 quick wins shipped. See already-built reference table above.

---

## Tier 2 — High value, moderate effort

### 5. Automation hooks — run local script on event
Trigger a local PowerShell / batch / Python script when a named device connects, disconnects, or an alert fires.

- Rule builder: `[Device condition]` → `[Script path]` → `[Args]`
- Non-blocking `subprocess.Popen`; stdout/stderr to an Automation Log panel
- Built-in templates: Wake-on-LAN, send notification, log to file
- Example: phone MAC joins → wake workstation

### 7. Network documentation auto-generator
One-click "Document My Network" — useful for IT admins and home labbers.

- Network diagram (export topology widget as SVG/PNG)
- Device inventory table (hostname, IP, MAC, vendor, OS, role, last seen)
- Open port inventory per host + certificate inventory with expiry dates
- _Builds on:_ `report_exporter.py` + `topology_widget.py`

### 8. Compliance report templates
One-click assessment against common control frameworks.

- **CIS Controls v8 Level 1** — inventory completeness, admin accounts, patch posture, open ports
- **PCI-DSS scope** — devices in card-data scope by subnet/VLAN, missing TLS, rogue wireless
- **Generic asset inventory** — full device table exportable to CSV/Excel
- _Builds on:_ `report_exporter.py`

### 9. Home Assistant / MQTT integration
HA Hub detection already exists. Publishing events back closes the loop.

- MQTT publish: device join/leave events, alert fired, uptime state changes
- Home Assistant sensor entities via MQTT discovery protocol
- Allows HA automations to act on NetSentinel data (e.g. lock IoT VLAN if rogue detected)
- _Builds on:_ `ha_detector.py`

### 10. WMI enrichment — serial number + logged-in user
`credentialed_scan.py` already collects OS version via WMIC. Small addition.

- `wmic bios get serialnumber` → asset serial
- `query session /server:<ip>` → active interactive user
- Surface in device detail panel for Windows hosts

### 11. VLAN discovery and map
Useful for SMB/enterprise networks running 802.1Q VLANs.

- Parse 802.1Q VLAN tags from captured frames (Scapy)
- SNMP `dot1qVlanStaticTable` walk on managed switches
- Topology view colour-code nodes by VLAN
- Alert when a device moves between VLANs unexpectedly

### 12. Switch port mapping (LLDP/CDP)
Identify which physical switch port each device is connected to.

- Capture LLDP/CDP frames passively (Scapy); parse neighbour identity, port ID, VLAN
- SNMP `ifTable` + `dot1dTpFdbTable` walk to map MAC → bridge port
- Surface in device detail panel: "Connected to: sw-core Gi0/1"

---

## Tier 3 — Significant projects

### 13. Trigger expression language
Complex multi-metric alert conditions for power users.

- `avg(rtt["192.168.1.1"], 5m) > 50 AND loss%["192.168.1.1"] > 5`
- Visual rule builder (dropdown-based) + raw expression editor
- _Extends:_ `alert_engine.py`

### 14. NetFlow / sFlow collector
Requires flow export enabled on the router/switch — not universally applicable.

- UDP collector on 2055 (NetFlow) / 6343 (sFlow)
- Per-conversation table: src IP, dst IP, protocol, bytes, packets
- "Top talkers" treemap chart

### 15. Agent-based monitoring
Install a lightweight agent on Windows/Linux hosts for CPU/disk/memory — bypasses SNMP limits.

- Thin Python agent over HTTPS to the local REST API (item 5 required first)
- Reports: CPU%, memory%, disk%, top processes, service status

### 16. WiFi signal strength heatmap
`wifi_scanner.py` already captures RSSI per AP.

- User marks position on a floor-plan image (PNG import)
- App records RSSI readings tagged to position; heatmap overlay on the floor plan
- Identifies dead zones and optimal AP placement

### 17. Distributed probe / remote agent
`svc.py` and `cli.py` already exist as headless runners.

- Agent sends JSON results over WebSocket or HTTP POST to the main instance
- Main dashboard shows remote probes as separate network zones

### 18. Multi-site management
Requires distributed probe (item 17) to be useful.

- Each site is a separate database / profile
- Site switcher in the top navigation bar

### 19. Plugin marketplace / community registry
Plugin system exists; this adds discovery.

- Hosted JSON index of community plugins (GitHub-based)
- "Browse Plugins" panel in Settings — install with one click

---

## Ecosystem / ultra-long-term

- **Mobile companion** — iOS/Android app receiving push notifications + live dashboard (requires REST API, item 5)
- **Geolocation map** — plot public IPs on a world map (MaxMind GeoLite2)
- **QoS policy advisor** — analyse traffic mix, generate DSCP/QoS rule suggestions
- **802.1X port-auth detection** — detect and report EAP frames on the LAN
- **BGP route monitoring** — watch for unexpected route changes from an upstream provider
- **Ticketing integration** — create Jira/ServiceNow/PagerDuty tickets when critical alerts fire

