"""Page help content for the tip bar and Help & Reference panel.

Each key is the exact nav label passed to _nav_add_rail_item().
Each value is a dict with:
  "what"   — one sentence describing what the page does
  "hidden" — list of hidden-feature tips shown in the tip bar
"""
from __future__ import annotations

_PAGE_HELP: dict[str, dict] = {
    # ── Getting Started ────────────────────────────────────────────────────────
    "Home": {
        "what": "Your network at a glance — live status, device count, speed, and stability.",
        "hidden": [
            "The 'What to do next' strip mostly surfaces findings to act on (open ports, unknown devices, a low grade) — it occasionally nudges an untried feature too.",
            "When the logger detects something interesting, an amber card appears here. Click 'Investigate →' to open a live Lab exercise.",
            "Click the mini cards (Speed, Stability, Devices) to jump directly to those pages.",
        ],
    },
    "Dashboard": {
        "what": "Live summary of all scan results — device list, graded health, port scan summary, and bandwidth at a glance.",
        "hidden": [
            "The 'Share Card' button exports a 520×300 summary card as PNG, clipboard image, or standalone HTML — useful for ISP escalations.",
            "All tiles here update live from background workers — you don't need to re-scan to see fresh data.",
        ],
    },
    "Speed Test": {
        "what": "Measures your actual download speed using Ookla CLI, speedtest-cli, or a built-in pure-Python fallback.",
        "hidden": [
            "Results are saved to Network Timeline and feed Trend Forecasts, so you can track speed changes over days or weeks.",
            "The three-tier engine falls through automatically — if Ookla is not installed, speedtest-cli is tried, then the built-in fallback.",
        ],
    },
    "DNS & Stability": {
        "what": "Measures DNS resolver latency over time and detects outages as short as one ping interval.",
        "hidden": [
            "The 'What just happened, technically?' strip explains DNS and why slow DNS makes everything feel slow even on a fast connection.",
            "Outage timestamps are recorded even when the logger is running in the background with no visible indicator.",
            "Switch to the 'DNS Benchmark' tab to compare Cloudflare, Google, and Quad9 against your system resolver side-by-side.",
        ],
    },
    "What's Wrong?": {
        "what": "One-click root-cause analysis — sequences network, storm, rogue device, and STP checks to surface the most likely cause of your problem.",
        "hidden": [
            "Pick a symptom tile (Slow / Dropping / Can't Connect) before running — this scopes the checks to the most relevant modules.",
            "The 'Do this first' priority card at the top is the single most actionable finding. Fix that before looking at the rest.",
            "Use the 'Quick test: Is this my ISP or my router?' button to get a plain-English verdict in under 30 seconds.",
        ],
    },
    "Troubleshoot": {
        "what": "Symptom-first routing hub — describe your problem in everyday language and NetSentinel routes you to the right diagnostic tool with context pre-set.",
        "hidden": [
            "Tiles that say 'Diagnose this →' pre-select the matching symptom on What's Wrong? so you skip the tile selection step.",
            "Click 'Run a full diagnosis' at the top if you're not sure which symptom applies — it runs all checks.",
        ],
    },
    # ── Discover ───────────────────────────────────────────────────────────────
    "Devices": {
        "what": "Every device on your subnet with IP, MAC, vendor, hostname, and risk level.",
        "hidden": [
            "Right-click any row for quick actions: Port Scan, Geolocation Map, AbuseIPDB check, Wake-on-LAN, CVE Tracker, How to Fix, Copy.",
            "The 'What just happened, technically?' strip at the bottom explains how ARP works and what a rogue device is.",
            "Click the column headers to sort by IP, risk level, or vendor.",
            "Vendor and model are resolved offline first (OUI database); an online api.macvendors.com lookup only fires for unmatched MACs — turn it off in Settings → Network Scanning for fully offline resolution.",
        ],
    },
    "WiFi Networks": {
        "what": "Scans visible SSIDs for hidden networks, rogue APs, WPS-enabled routers, and co-channel interference.",
        "hidden": [
            "Hidden SSIDs appear as '[HIDDEN]' — a rogue AP advertising no SSID is still listed here.",
            "WPS-enabled networks are flagged because WPS PIN attacks can bypass WPA2 in minutes.",
            "Co-channel interference is flagged when two strong APs on the same channel are detected — switch one to a non-overlapping channel.",
        ],
    },
    "WiFi Heatmap": {
        "what": "Visual signal-strength heatmap — drag the floor plan, click positions to capture dBm readings.",
        "hidden": [
            "Click any point on the floor plan to record the current signal level at that position — walk through rooms while clicking.",
            "Red = strong, blue = weak. Areas below −75 dBm are likely to cause connection drops.",
            "Export the heatmap as PNG to attach to a support ticket or share with a Wi-Fi installer.",
        ],
    },
    "Network Map": {
        "what": "Auto-generated topology diagram showing how discovered devices relate to each other.",
        "hidden": [
            "The topology is rebuilt after every scan — devices are positioned based on ARP and gateway relationships.",
            "Click any node to open a drawer with that device's details, right on this page — no need to navigate away.",
        ],
    },
    "DHCP Leases": {
        "what": "Live view of all active DHCP leases on your network, read from the OS lease table.",
        "hidden": [
            "This page lists leases only — it doesn't compare or flag them. For real-time rogue DHCP server detection, see DHCP Rogue Monitor in Security Audit.",
            "Lease data is read from the OS lease table — no packet capture needed, works without Npcap.",
            "For real-time detection of rogue DHCP OFFER packets on the wire, see DHCP Rogue Monitor in Security Audit — that requires Npcap and catches attacks that don't complete a full lease.",
        ],
    },
    "DNS Zone Map": {
        "what": "Enumerates DNS zones via AXFR and discovers local services via mDNS to map your network's naming landscape.",
        "hidden": [
            "AXFR (zone transfer) only works if the DNS server is configured to allow it — many modern servers disable this by default.",
            "mDNS discovery finds services on the .local domain without any server configuration — printers, Bonjour services, and IoT hubs all show up here.",
            "A successful AXFR from an internal DNS server reveals every hostname in the zone — useful for auditing stale DNS records.",
        ],
    },
    "Home Automation": {
        "what": "Device join/leave events, alerts, and per-device uptime states forwarded to Home Assistant or an MQTT broker.",
        "hidden": [
            "Until a network scan finds matching smart-home devices, the page shows an empty state with a shortcut to configure MQTT / Home Assistant.",
            "Device presence is fed by the same background availability poll used elsewhere (about every 60 seconds by default), not a sub-second push.",
        ],
    },
    # ── Monitor ────────────────────────────────────────────────────────────────
    "Live Bandwidth": {
        "what": "Rolling 60-second upload/download chart per network interface — updates every second.",
        "hidden": [
            "Switch between interfaces using the dropdown if you have both Wi-Fi and Ethernet active.",
            "Spikes that correlate with Broadcast Storm events help confirm a storm is saturating the link.",
            "For per-device bandwidth breakdown showing which device is consuming the most, see Bandwidth Usage (also in this section) — that requires Npcap for packet capture.",
        ],
    },
    "App Traffic": {
        "what": "Per-host protocol breakdown — which categories of traffic (Web, DNS, Streaming, Gaming, VPN, P2P…) each device is using, sampled every 10 seconds.",
        "hidden": [
            "Requires Npcap on Windows (install from npcap.com) and administrator privileges for packet capture.",
            "Select a specific host from the dropdown to drill into its protocol detail table.",
            "Traffic is classified by destination TCP/UDP port — devices using non-standard ports appear as 'Other'.",
            "Leave monitoring running for a few minutes to distinguish constant background traffic from bursty sessions.",
            "Unexpected 'P2P' or 'VPN' traffic from a device you don't control is worth investigating.",
            "The 'Last 24 Hours by Category' chart persists across restarts — click any bar to see which devices and streaming providers (Netflix/YouTube/Twitch) used the most data.",
        ],
    },
    "Bandwidth Usage": {
        "what": "Per-device bandwidth usage collected during packet capture sessions.",
        "hidden": [
            "Packet capture requires Npcap on Windows — install it from npcap.com for this tab to populate.",
            "For a per-protocol breakdown of a device's traffic, see App Traffic (also in this section).",
            "The top-talker list shows which device is consuming the most bandwidth — useful for finding rogue downloaders.",
            "For a real-time per-interface chart without Npcap, see Live Bandwidth (also in this section).",
        ],
    },
    "Active Connections": {
        "what": "Process-to-socket map showing which app owns each open connection — one-click firewall block per process.",
        "hidden": [
            "Click 'Block' on any process to add a Windows Firewall outbound rule — you can unblock it from the same row.",
            "Right-click a remote IP for cross-page lookups: Threat Intel, Geo Map, Inventory, and Device Info.",
            "Check 'Auto (5s)' to refresh automatically — off by default, so watch for processes that appear briefly and disappear once it's on.",
        ],
    },
    "Availability History": {
        "what": "RTT and UP/DEGRADED/DOWN state charts per device — 1 h / 12 h / 24 h / 7 d zoom.",
        "hidden": [
            "This data accumulates automatically in the background regardless of whether Network Logger is running.",
            "Use the 7-day view to find patterns: if a device drops every night at 2 AM, that is a strong clue about what is rebooting it.",
        ],
    },
    "Inventory Changes": {
        "what": "Shows devices that appeared or disappeared since the last scan — instant diff view.",
        "hidden": [
            "Compare any two scan snapshots from the dropdown to see exactly which MACs joined or left.",
            "New devices are highlighted in green, departures in red — export the diff as CSV for change-control records.",
        ],
    },
    "Service Heartbeat": {
        "what": "Monitors specific hosts and ports on a schedule — alerts when a service goes down.",
        "hidden": [
            "Add your router's management page, NAS, or home server here to get notified the moment they become unreachable.",
            "Heartbeat checks run on their own schedule independent of the main scanner — no need to rescan to refresh them.",
        ],
    },
    "IPv6 Devices": {
        "what": "Discovers IPv6-addressed devices on your network using NDP and multicast probes.",
        "hidden": [
            "Many home networks have IPv6 active without the owner knowing — this tab reveals the full device census.",
            "Link-local addresses (fe80::) are not routable — global unicast addresses (2xxx:) are the ones exposed to the internet.",
        ],
    },
    "Uptime & SLA": {
        "what": "Per-device uptime percentages over 24 h, 7 d, and 30 d windows, derived from an always-on background availability poll.",
        "hidden": [
            "This data accumulates automatically in the background — you don't need to run Network Logger for meaningful SLA percentages.",
            "Devices below 99% uptime over 7 days are worth investigating — check Availability History for the exact outage timestamps.",
            "Use the 30-day view for SLA reporting — export the table as CSV for compliance records.",
        ],
    },
    "Syslog Viewer": {
        "what": "Live viewer for syslog messages (UDP 514) from routers, switches, and servers on your network.",
        "hidden": [
            "Configure your router to send syslog to this machine's IP — the port is 514 UDP by default.",
            "Filter by severity or hostname using the filter bar — Error and Warning messages are the most actionable.",
            "Syslog can also be viewed inside the Network Logger 'Activity Log' tab alongside ping and DNS data.",
        ],
    },
    "SNMP Trap Receiver": {
        "what": "Receives SNMP trap notifications (UDP 162) from managed switches, routers, and servers.",
        "hidden": [
            "Configure your managed switch to send traps to this machine's IP — use community string 'public' to start.",
            "Critical and Warning traps from managed switches often signal hardware failures or link-state changes before they cause an outage.",
            "Traps can also be viewed alongside other events in the Network Logger 'Activity Log' tab.",
        ],
    },
    "Network Timeline": {
        "what": "Reverse-chronological unified event feed — device joins/leaves, fired alerts, CVE discoveries, and speed tests in a single scrollable view. Filter by source with one click.",
        "hidden": [
            "Use the source filter to isolate a specific event type — e.g. show only CVE discoveries or only speed test results.",
            "Clicking a row navigates to the page that produced it (e.g. a CVE event opens CVE Tracker) — nothing expands in place here.",
        ],
    },
    "Network Logger": {
        "what": "'Log Sources' tab: configure what gets recorded (ping, DNS, modem, mesh, ARP, Syslog, SNMP) and start/stop logging. 'Activity Log' tab: unified chronological viewer for all sources.",
        "hidden": [
            "The logger runs even when the app window is minimised — check the status bar dot to confirm it is active.",
            "CSV files are saved to Documents\\NetSentinel\\logs\\ (not the app data directory) — you can open them in Excel for custom analysis.",
            "Enable 'Auto-start on launch' so logging begins the moment the app opens without any manual step.",
            "Any row with an ARP event shows a '▶ ARP' button — click it to jump to the Protocol Visualizer pre-loaded with that event.",
            "Filter the Activity Log by hostname using the filter box — useful on busy networks.",
        ],
    },
    "Modem": {
        "what": "Live 5G NR and LTE signal metrics polled from your WAN modem — SINR, RSRP, RSRQ, band, and cell ID. Enter your modem's local IP and credentials to connect.",
        "hidden": [
            "Each speed test automatically snapshots the current modem signal — click any history row to restore the signal panel for that moment.",
            "Signal history is stored in the database so you can correlate slow speeds with poor SINR or band changes over time.",
            "ZTE MC889 is fully supported out of the box; the worker architecture accepts additional modem models via plugins.",
        ],
    },
    "Mesh & Router": {
        "what": "Live signal stats, client counts, and topology from your TP-Link Deco XE75 mesh system. Enter your Deco admin credentials to connect.",
        "hidden": [
            "Once connected, the Devices table gains real hostnames instead of 'Unknown Device' — the enrichment runs automatically after every scan.",
            "The Network Map upgrades from a flat star to a three-tier mesh tree showing which node each device is connected to.",
            "Client-to-node assignment helps locate dead spots: devices that roam to a distant node despite a nearby node being available.",
        ],
    },
    "Monitor Status": {
        "what": "Aggregated dashboard across all monitoring streams — one view of all live data sources.",
        "hidden": [
            "Cards refresh independently as each worker reports — a stale card shows the last known value with a timestamp.",
        ],
    },
    # ── Reports ────────────────────────────────────────────────────────────────
    "Network Grade": {
        "what": "Scores your network A–F across speed, latency, DNS, packet loss, device security, and STP health.",
        "hidden": [
            "Each grade dimension shows an actionable 'Fix tip' directly in its row — nothing to expand.",
            "Run 'Grade My Network' after making changes to see whether they improved the score.",
        ],
    },
    "Network Health Report": {
        "what": "Generates a standalone HTML report with device uptime, TLS certificate status, service heartbeat status, and recent device events (last 24h). Good for a periodic fleet-health snapshot.",
        "hidden": [
            "The report is a single self-contained HTML file — email it or attach it to a support ticket with no extra files needed.",
            "For an ISP support ticket instead, use the separate 'Copy ISP Complaint' / export tools on the Network Grade page — that report covers traceroute, DNS latency, and the outage log.",
        ],
    },
    "Network Doc": {
        "what": "Auto-assembled network documentation page — device list, cert inventory, topology diagram, and accumulated port scan results.",
        "hidden": [
            "Export as HTML to hand to an IT consultant or keep as a record before making network changes.",
            "The device count and cert status tiles update automatically after every scan — but the generated HTML/Markdown document itself only refreshes when you click 'Generate' again.",
        ],
    },
    "IP Calculator": {
        "what": "Subnet calculator with CIDR notation reference, subnetting rules, and address class tables.",
        "hidden": [
            "Enter any IP/prefix (e.g. 192.168.1.50/24) to instantly see the network address, broadcast, usable range, and host count.",
            "The reference panels explain CIDR and subnetting concepts — useful if you are studying for Network+ or CCNA.",
        ],
    },
    "Notifications": {
        "what": "Configure where alerts go — desktop notifications, webhook URLs, and email targets.",
        "hidden": [
            "Webhooks POST a generic JSON payload — works with custom scripts or Zapier/IFTTT-style catchers, but isn't natively shaped for Slack's or Discord's incoming-webhook schema without a small relay in between.",
            "Test the webhook before relying on it — use the 'Send Test' button to confirm delivery.",
        ],
    },
    # ── Analysis ───────────────────────────────────────────────────────────────
    "Hop-by-Hop Trace": {
        "what": "MTR-style traceroute showing per-hop latency and packet-loss — identifies exactly which ISP hop is the problem.",
        "hidden": [
            "Run the trace twice — once when things are good and once when they are slow — then compare the hop-by-hop RTTs.",
            "High loss at a hop that still delivers traffic is usually ICMP rate-limiting, not a real problem. Loss that persists on all hops after it is the real issue.",
        ],
    },
    "ARP Spoof Watch": {
        "what": "Watches for MAC address conflicts that indicate a man-in-the-middle attack on the local segment.",
        "hidden": [
            "The 'What just happened, technically?' strip shows a step-by-step ARP spoofing diagram — useful for understanding how the attack works.",
            "Requires Npcap on Windows and admin rights — the tab shows a banner if these are missing.",
            "For an aggregate view of all security monitors including this one, see Security Overview in the Security Audit section.",
        ],
    },
    "SNMP Device Info": {
        "what": "Queries routers and switches via SNMP for system description, interface/port stats, and uptime.",
        "hidden": [
            "Most home routers have SNMP disabled by default — enable it in the router admin panel first.",
            "Use SNMPv2c with the 'public' community string to start — change this if your router uses a custom community.",
        ],
    },
    "Tools & Wake-on-LAN": {
        "what": "Wake-on-LAN sender and New Device Alerts baseline diff.",
        "hidden": [
            "Wake-on-LAN requires the target device to have WoL enabled in its BIOS and the NIC driver settings.",
        ],
    },
    "Port Scanner": {
        "what": "TCP connect-scan of common ports on any host. No admin required.",
        "hidden": [
            "Right-click a device in Devices or Network Info → Port Scan to pre-fill the host here.",
            "For a deeper admin-required scan with CVE lookups, see Port Scan (TCP) in the Security Audit section.",
        ],
    },
    "Geolocation Map": {
        "what": "Offline world map showing where internet-facing IPs are located — no API key, no external calls.",
        "hidden": [
            "Uses the MaxMind GeoLite2-City database — download it once (free, no account required) and all lookups after that are local, with no external calls.",
            "IPs that map to unexpected countries may indicate traffic going through a VPN exit node or a compromised proxy.",
        ],
    },
    "Broadcast Storm": {
        "what": "Listens for abnormal broadcast traffic and identifies the source device or loop.",
        "hidden": [
            "The 'What just happened, technically?' strip explains what causes a broadcast storm and how STP is supposed to prevent them.",
            "Storm level CLEAN / WARNING / STORM is shown with the broadcast packets-per-second rate.",
        ],
    },
    "Rogue Bridge (STP)": {
        "what": "Captures BPDU frames and alerts when an unexpected switch claims the STP root election.",
        "hidden": [
            "The 'What just happened, technically?' strip explains STP, what a root election is, and why rogue bridges cause 30-second periodic outages.",
            "Mesh Wi-Fi nodes connected via Ethernet cable are a common source of rogue bridge events.",
        ],
    },
    "IoT Behaviour": {
        "what": "Learns normal traffic per device — IoT or otherwise — and alerts on port scans, new destinations, and traffic rate spikes.",
        "hidden": [
            "The baseline learning window is 30 seconds to 10 minutes (default 60s) — longer windows capture more of each device's normal traffic pattern before the anomaly monitor starts alerting.",
            "Alerts fire when a device contacts a destination it has never used before — common after firmware updates.",
        ],
    },
    "802.11 Monitor": {
        "what": "Passive 802.11 frame capture using Npcap monitor mode — captures management, control, and data frames.",
        "hidden": [
            "Requires Npcap and a Wi-Fi adapter that supports monitor mode — not all adapters do.",
            "Use this to see probe requests from devices looking for networks, which reveals device history even before they connect.",
        ],
    },
    "Trend Forecasts": {
        "what": "Extrapolates RTT and packet-loss trends to predict future degradation based on historical data.",
        "hidden": [
            "Forecasts are only meaningful after several days of Network Logger data — short runs produce wide confidence intervals.",
        ],
    },
    "Service Diagnostics": {
        "what": "Probes DNS, TCP reachability, latency, and network path to determine whether a streaming or gaming service is reachable and where any failure originates.",
        "hidden": [
            "Enable 'Include traceroute' to see every network hop between you and the service — useful when your ISP routes traffic unexpectedly.",
            "The failure layer badge tells you in plain English who is responsible: 'Device problem', 'ISP issue', 'Remote outage', etc.",
            "Confidence % is a fixed value per diagnosis scenario, reflecting how diagnostic that failure pattern typically is — it isn't computed from how many probes agreed at runtime.",
        ],
    },
    "Root Cause Correlator": {
        "what": "Synthesises all scan findings into a prioritised plain-English list of network problems, ranked by likely impact.",
        "hidden": [
            "Run a full scan first — the correlator works from the most recent scan results.",
            "The top-ranked finding is the single most impactful problem detected — fix that before looking at the rest.",
            "Findings are a flat list sorted by severity — the Category column shows the specific problem type (e.g. 'Rogue Network Bridge'), not a broad bucket.",
        ],
    },
    # ── Automation ─────────────────────────────────────────────────────────────
    "Automation Hooks": {
        "what": "Webhook and script triggers on network events — device down, high RTT, new device discovered.",
        "hidden": [
            "Hooks fire in the background — configure a webhook URL and watch your Slack or Discord channel for events.",
            "Script hooks run any executable on your machine, so you can trigger Home Assistant scenes, send emails, or log to a database.",
        ],
    },
    "Scheduled Scans": {
        "what": "Run device discovery on a repeating schedule — useful for overnight audits or compliance snapshots.",
        "hidden": [
            "Scheduled scans run even when the main window is minimized — a background thread inside the app handles them, so NetSentinel itself must stay running (this is not a separate Windows service).",
            "Combine with Config Snapshots to automatically save the state after each scheduled scan.",
        ],
    },
    "Custom Triggers": {
        "what": "Build your own event rules: if RTT exceeds a threshold for N consecutive pings, fire an action.",
        "hidden": [
            "Enabled triggers are checked automatically every minute and fire a desktop notification when true — for webhooks or scripts, use Automation Hooks instead.",
        ],
    },
    "MQTT / Home Assistant": {
        "what": "Publishes device presence, uptime, and alerts to an MQTT broker for Home Assistant integration.",
        "hidden": [
            "Set the MQTT broker address and port right on this page's Broker Configuration card — the page will show connection status once configured.",
            "Each device gets its own Home Assistant entity — ideal for automations like 'if the kids' tablet leaves the network, run a script'.",
        ],
    },
    "REST API": {
        "what": "Read-only HTTP API (default port 8765) — exposes /devices, /alerts, /uptime/<ip>, /grade, /speed-history, /dashboard, /health, /service-catalog, and /service-diagnostics/<service_id>.",
        "hidden": [
            "The API key is stored in the OS keychain — copy it from the REST API page to use in your scripts.",
            "Use the /dashboard endpoint to embed a live network summary in a Grafana panel or Home Assistant card.",
        ],
    },
    "Config Snapshots": {
        "what": "Takes point-in-time snapshots of your scan results — compare current state to a baseline.",
        "hidden": [
            "Take a snapshot right after a clean setup, then compare against it after any change to see exactly what shifted.",
        ],
    },
    "Maintenance Windows": {
        "what": "Suppress alerts during planned downtime so you don't get paged for your own maintenance.",
        "hidden": [
            "Windows are one-time or recurring — set a recurring window for regular router reboots or backup jobs.",
        ],
    },
    # ── Security Audit ─────────────────────────────────────────────────────────
    "Security Overview": {
        "what": "Aggregate security dashboard — KPI tiles for threat indicators, top findings table, and one-click audit launch.",
        "hidden": [
            "The grade circle updates after every scan — run a full security scan to get your latest grade.",
            "Each finding in the top-15 table names the source page — click any row and navigate there directly to investigate.",
            "For real-time ARP/DHCP/Storm monitors, use DHCP Rogue Monitor here in Security Audit, and ARP Spoof Watch / Broadcast Storm over in Analysis.",
        ],
    },
    "Port Scan (TCP)": {
        "what": "SYN stealth port scanner — identifies open TCP ports on discovered devices. Requires admin + Npcap.",
        "hidden": [
            "SYN scan is faster and quieter than a connect scan because it never completes the three-way handshake.",
            "Scan results feed into Device Risk Score and CVE Lookup automatically.",
            "After running a port scan, go to CVE Lookup to cross-reference discovered service versions against the NVD vulnerability database.",
        ],
    },
    "Port Scan (UDP)": {
        "what": "UDP port scanner — identifies open UDP services including DNS, SNMP, and NTP.",
        "hidden": [
            "UDP scanning is slower than TCP because closed ports respond with ICMP unreachable, which routers often rate-limit.",
            "Focus on ports 53, 161, 123, and 5353 for the most common home-network UDP services.",
        ],
    },
    "CVE Lookup": {
        "what": "Cross-references discovered OS and service versions against the NVD database on demand.",
        "hidden": [
            "CVE data is fetched from services.nvd.nist.gov — this is the only external call in this tab.",
            "Run a port scan first so there are service versions to look up — CVE Lookup needs version strings to match against.",
            "To track whether CVEs get fixed over time, see CVE Tracker (also in Security Audit) — it records open/mitigated/resolved state per device across scans.",
        ],
    },
    "Threat Intel": {
        "what": "Checks IP addresses from your scan results against threat intelligence feeds for known malicious hosts.",
        "hidden": [
            "Click any flagged IP to see which feed reported it and when it was last seen.",
        ],
    },
    "TLS & Exposure": {
        "what": "Monitors TLS certificate expiry per host — internet-exposure checking is a separate page (see 'Exposed to Internet').",
        "hidden": [
            "Certificates are checked hourly — you will see an alert badge 30 days before any cert expires.",
            "For internet-exposure results, open the 'Exposed to Internet' page instead — it reads your router's UPnP port-mapping table rather than probing from outside.",
        ],
    },
    "Login Test": {
        "what": "Connects to a device via SSH using credentials you supply, and collects installed packages, running services, users, and patch level — for authorised use on networks you own.",
        "hidden": [
            "This is a manual, single-host credentialed scan — you provide the username/password (or key) yourself; there is no default-credential or brute-force list.",
            "Results feed into Device Risk Score — a device that a Login Test successfully authenticates to gets flagged, since it proves the device is remotely loggable-into with the credentials tried.",
        ],
    },
    "OS Detection": {
        "what": "Fingerprints device operating systems using TCP/IP stack analysis.",
        "hidden": [
            "Fingerprinting always probes the same fixed port set (80, 443, 22, 8080) — it doesn't currently reuse results from a prior port scan.",
        ],
    },
    "Device Risk Score": {
        "what": "Calculates a per-device risk score based on open ports, OS age, CVEs, and default credentials.",
        "hidden": [
            "Scores update automatically as port scan, CVE lookup, and login test results come in.",
            "Click any device row to see the specific findings that are driving its score up.",
        ],
    },
    "CVE Tracker": {
        "what": "Tracks active CVEs for your network devices over time — shows newly discovered vulnerabilities since last scan.",
        "hidden": [
            "Newly discovered CVEs start in the 'Open' state — those are the ones to prioritise for patching.",
            "CVE Tracker needs data to track — run CVE Lookup first to discover vulnerabilities, then come back here to monitor remediation progress.",
        ],
    },
    "Exposed to Internet": {
        "what": "Checks whether services on your network are reachable from the public internet, by reading your router's UPnP port-mapping table — no active probes are sent from outside your network.",
        "hidden": [
            "A result of 'exposed' means a UPnP mapping forwards that port from your public IP to a LAN device — check your router's port-forwarding rules.",
        ],
    },
    "Full Device Discovery": {
        "what": "Parallel ARP + ICMP + TCP SYN + mDNS sweep for maximum device census accuracy. Requires admin + Npcap.",
        "hidden": [
            "This finds devices that don't respond to ARP alone — smart TVs and IoT devices that block pings are often missed by standard discovery.",
        ],
    },
    "Windows Shares (SMB)": {
        "what": "Enumerates accessible SMB shares on Windows devices on your network.",
        "hidden": [
            "Any non-hidden disk share is flagged as a risk — the scanner doesn't currently distinguish password-protected shares from open ones.",
        ],
    },
    "Recon Plugins": {
        "what": "Custom port-scanner and enumeration scripts — not hardware driver plugins. Drop a .py plugin file into the plugins/ directory to add new scan capabilities.",
        "hidden": [
            "See docs/plugin-authoring.md for the plugin API — a plugin is a Python module with a PLUGIN_META dict and a module-level run(devices, **kwargs) function, not a class.",
            "These are recon/scan scripts, not hardware integrations. For routers and modems, use the Hardware section.",
        ],
    },
    "Private Endpoint Check": {
        "what": "Verifies that cloud private endpoints are not accidentally exposed on your local network.",
        "hidden": [
            "Useful if you run cloud VMs with VPN-connected private endpoints — this confirms the endpoint is not leaking.",
        ],
    },
    "Cloud Metadata Probe": {
        "what": "Detects cloud metadata service exposure (169.254.169.254) on the local subnet.",
        "hidden": [
            "A reachable metadata endpoint from a device that should not have cloud access indicates a misconfigured VM or container.",
        ],
    },
    "DHCP Rogue Monitor": {
        "what": "Watches for unauthorised DHCP servers responding on your network — a sign of a misconfigured device or attack.",
        "hidden": [
            "Requires Npcap on Windows — the monitor listens for DHCP OFFER frames on the wire.",
            "A rogue DHCP server can redirect your DNS to a malicious resolver — this is a common attack on public Wi-Fi.",
            "For a snapshot of all current leases and assigned IPs without Npcap, see DHCP Leases in the Discover section.",
        ],
    },
    # ── Education ──────────────────────────────────────────────────────────────
    "Protocol Visualizer": {
        "what": "Animated step-by-step diagrams of ARP, DNS, TCP, DHCP, and STP using your real device addresses, with a per-step Frame Anatomy breakdown and PNG/storyboard export.",
        "hidden": [
            "Use the ◀◀ / ▶ / ▶▶ step buttons to jump forward or backward through the animation without watching it play in real time.",
            "The '▸ Why this protocol matters' panel at the bottom links the animation to real threats NetSentinel detects.",
            "The 'See diagram' button in any 'What just happened, technically?' panel jumps here with the right protocol pre-selected.",
            "Click 'Frame Anatomy' below the canvas to see the real Ethernet/IP/protocol fields for the current step, with click-to-expand field tables.",
            "Right-click the canvas (or use the title-bar buttons) to copy the current frame as an image, save it as PNG, or export a full storyboard filmstrip of every step — useful for coursework submissions.",
        ],
    },
    "Lab Mode": {
        "what": "Guided exercises that walk you through diagnosing your live network step by step.",
        "hidden": [
            "When the Home page shows a live event card, clicking 'Investigate →' drops you straight into a one-step lab built from that event.",
            "After finishing an exercise, click 'Export Report (HTML)' to save a portable lab report.",
            "Hints don't penalise you — use them freely. The solution is always there if you're stuck.",
            "Each lab's picker card shows a ✓ and completion date once you finish it, and the strip at the top tracks how many of the 10 labs you've completed.",
            "The active exercise shows a live animated diagram of the protocol you're learning, driven by your real network addresses — the same engine as the Protocol Visualizer.",
        ],
    },
    "Feature Guide": {
        "what": "Every NetSentinel feature in one place — searchable, with descriptions and direct navigation.",
        "hidden": [
            "Use the search bar to find features by keyword — 'heatmap', 'arp', 'stp', or 'hidden' all work.",
            "Features marked with a badge (Npcap, admin) need extra setup — hover the badge for details.",
            "Click 'Open →' on any feature card to jump directly to that page.",
        ],
    },
    "Help & Reference": {
        "what": "Quick-start guide, keyboard shortcuts, What's New, and the update checker.",
        "hidden": [
            "The keyboard shortcut table lists every Ctrl+key binding in the app — Ctrl+K, Ctrl+F, and Ctrl+L are the most useful.",
        ],
    },
    # ── Extend ─────────────────────────────────────────────────────────────────
    "Hardware": {
        "what": "Manages hardware integration plugins — connect routers, modems, and custom devices via Python plugin scripts.",
        "hidden": [
            "Click '⬡ New Plugin' to generate a filled-in template — the wizard asks for the device type and fills in the scaffold.",
            "Each plugin card shows a health indicator: green = recent success, amber = degraded (no success in 24 h), red = circuit-breaker open.",
            "Click '≡ Logs' on any plugin card to view the last 100 structured poll log lines for debugging connection issues.",
        ],
    },
}
