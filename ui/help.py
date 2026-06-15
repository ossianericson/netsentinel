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
            "The 'What to do next' strip surfaces features you haven't tried yet — it updates as you explore.",
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
            "Results are logged to the Network Logger so you can track speed changes over days or weeks.",
            "The three-tier engine falls through automatically — if Ookla is not installed, speedtest-cli is tried, then the built-in fallback.",
        ],
    },
    "DNS & Stability": {
        "what": "Measures DNS resolver latency over time and detects outages as short as one ping interval.",
        "hidden": [
            "The 'Explain This' strip explains DNS and why slow DNS makes everything feel slow even on a fast connection.",
            "Outage timestamps are recorded even when the logger is running in the background with no visible indicator.",
            "Switch to the 'DNS Benchmark' tab to compare Cloudflare, Google, and Quad9 against your system resolver side-by-side.",
        ],
    },
    "What's Wrong?": {
        "what": "One-click root-cause analysis — sequences network, storm, rogue device, and STP checks to surface the most likely cause of your problem.",
        "hidden": [
            "Pick a symptom tile (Slow / Dropping / Can't Connect) before running — this scopes the checks to the most relevant modules.",
            "The 'Do this first' priority card at the top is the single most actionable finding. Fix that before looking at the rest.",
        ],
    },
    # ── Discover ───────────────────────────────────────────────────────────────
    "Devices": {
        "what": "Every device on your subnet with IP, MAC, vendor, hostname, and risk level.",
        "hidden": [
            "Right-click any row for quick actions: How to Fix, block from network, view availability history.",
            "The 'Explain This' strip at the bottom explains how ARP works and what a rogue device is.",
            "Click the column headers to sort by IP, risk level, or vendor.",
            "Vendor and model are resolved offline using the OUI database — no internet call needed.",
        ],
    },
    "WiFi Networks": {
        "what": "Scans visible SSIDs for hidden networks, rogue APs, WPS-enabled routers, and co-channel interference.",
        "hidden": [
            "Hidden SSIDs appear as '<hidden>' — a rogue AP advertising no SSID is still listed here.",
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
            "Click any node to jump to that device's row in the Devices page.",
        ],
    },
    "DHCP Leases": {
        "what": "Live view of all active DHCP leases on your network — flags unexpected or rogue DHCP servers.",
        "hidden": [
            "A rogue DHCP server flag means two devices are handing out IP addresses — this can cause connection failures across the whole network.",
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
            "Set up the MQTT broker address in Settings first — the page will show 'not connected' until that is done.",
            "Device presence events arrive within seconds of a device appearing or disappearing on the network.",
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
        ],
    },
    "Bandwidth Usage": {
        "what": "Per-device bandwidth usage collected during packet capture sessions.",
        "hidden": [
            "Packet capture requires Npcap on Windows — install it from npcap.com for this tab to populate.",
            "Click a row to see the breakdown of protocols that device is using.",
            "The top-talker list shows which device is consuming the most bandwidth — useful for finding rogue downloaders.",
            "For a real-time per-interface chart without Npcap, see Live Bandwidth (also in this section).",
        ],
    },
    "Active Connections": {
        "what": "Process-to-socket map showing which app owns each open connection — one-click firewall block per process.",
        "hidden": [
            "Click 'Block' on any process to add a Windows Firewall outbound rule — you can unblock it from the same row.",
            "Processes with many connections to non-local IPs are worth investigating — click the destination IP to run a WHOIS.",
            "The list refreshes every few seconds automatically — watch for processes that appear briefly and disappear.",
        ],
    },
    "Availability History": {
        "what": "RTT and UP/DEGRADED/DOWN state charts per device — 1 h / 12 h / 24 h / 7 d zoom.",
        "hidden": [
            "Data accumulates as long as the Network Logger is running — start it early and leave it on for evidence-grade output.",
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
        "what": "Per-device uptime percentages over 24 h, 7 d, and 30 d windows, derived from Network Logger ping history.",
        "hidden": [
            "Data accumulates from the Network Logger — run it continuously for meaningful SLA percentages.",
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
            "Click any row to expand full event details including timestamps, IP, and MAC address.",
        ],
    },
    "Network Logger": {
        "what": "'Log Sources' tab: configure what gets recorded (ping, DNS, modem, mesh, ARP, Syslog, SNMP) and start/stop logging. 'Activity Log' tab: unified chronological viewer for all sources.",
        "hidden": [
            "The logger runs even when the app window is minimised — check the status bar dot to confirm it is active.",
            "CSV files are saved to the logs/ folder in the app data directory — you can open them in Excel for custom analysis.",
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
            "Each grade dimension has an actionable 'Fix tip' — expand the row to see what to do.",
            "Run 'Grade My Network' after making changes to see whether they improved the score.",
        ],
    },
    "Network Health Report": {
        "what": "Generates a standalone HTML report with MTR hop table, packet-loss %, DNS latency, and timestamped outage log. Great for ISP support tickets.",
        "hidden": [
            "The report is a single self-contained HTML file — email it or attach it to a support ticket with no extra files needed.",
            "Run the Network Logger for at least an hour before generating the report so the outage log has enough data.",
        ],
    },
    "Network Doc": {
        "what": "Auto-assembled network documentation page — device list, cert inventory, topology diagram, and accumulated port scan results.",
        "hidden": [
            "Export as PDF or HTML to hand to an IT consultant or keep as a record before making network changes.",
            "The device count and cert status update automatically after every scan — you don't need to regenerate manually.",
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
            "Webhooks can point to Slack, Discord, or any service with an incoming webhook URL — no plugin needed.",
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
            "The 'Explain This' strip shows a step-by-step ARP spoofing diagram — useful for understanding how the attack works.",
            "Requires Npcap on Windows and admin rights — the tab shows a banner if these are missing.",
            "For an aggregate view of all security monitors including this one, see Security Overview in the Security Audit section.",
        ],
    },
    "SNMP Device Info": {
        "what": "Queries routers and switches via SNMP for port stats, CPU load, and uptime.",
        "hidden": [
            "Most home routers have SNMP disabled by default — enable it in the router admin panel first.",
            "Use SNMPv2c with the 'public' community string to start — change this if your router uses a custom community.",
        ],
    },
    "Tools & Wake-on-LAN": {
        "what": "Ping, traceroute, WHOIS, port check, and Wake-on-LAN utilities in one place.",
        "hidden": [
            "Wake-on-LAN requires the target device to have WoL enabled in its BIOS and the NIC driver settings.",
            "The WHOIS lookup works on both IP addresses and domain names.",
        ],
    },
    "Geolocation Map": {
        "what": "Offline world map showing where internet-facing IPs are located — no API key, no external calls.",
        "hidden": [
            "Uses the MaxMind GeoLite2-City database bundled with the app — all lookups are local.",
            "IPs that map to unexpected countries may indicate traffic going through a VPN exit node or a compromised proxy.",
        ],
    },
    "Broadcast Storm": {
        "what": "Listens for abnormal broadcast traffic and identifies the source device or loop.",
        "hidden": [
            "The 'Explain This' strip explains what causes a broadcast storm and how STP is supposed to prevent them.",
            "Storm level SAFE / WARNING / CRITICAL is shown with the broadcast packets-per-second rate.",
        ],
    },
    "Rogue Bridge (STP)": {
        "what": "Captures BPDU frames and alerts when an unexpected switch claims the STP root election.",
        "hidden": [
            "The 'Explain This' strip explains STP, what a root election is, and why rogue bridges cause 30-second periodic outages.",
            "Mesh Wi-Fi nodes connected via Ethernet cable are a common source of rogue bridge events.",
        ],
    },
    "IoT Behaviour": {
        "what": "Learns normal traffic per IoT device and alerts on port scans, new destinations, and traffic rate spikes.",
        "hidden": [
            "Run the baseline for at least 24 hours before expecting accurate alerts — the model needs time to learn normal behaviour.",
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
            "Confidence % reflects how many independent probes agreed — 80%+ is conclusive, below 50% means mixed signals.",
        ],
    },
    "Root Cause Correlator": {
        "what": "Synthesises all scan findings into a prioritised plain-English list of network problems, ranked by likely impact.",
        "hidden": [
            "Run a full scan first — the correlator works from the most recent scan results.",
            "The top-ranked finding is the single most impactful problem detected — fix that before looking at the rest.",
            "Findings are grouped by category (connectivity, security, performance) so you can tackle a whole category at once.",
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
        "what": "Run discovery and port scans on a repeating schedule — useful for overnight audits or compliance snapshots.",
        "hidden": [
            "Scheduled scans run even when the main window is not visible — the background service handles them.",
            "Combine with Config Snapshots to automatically save the state after each scheduled scan.",
        ],
    },
    "Custom Triggers": {
        "what": "Build your own event rules: if RTT exceeds a threshold for N consecutive pings, fire an action.",
        "hidden": [
            "Triggers can call webhooks, run scripts, or send desktop notifications — the same actions as Automation Hooks.",
        ],
    },
    "MQTT / Home Assistant": {
        "what": "Publishes device presence, uptime, and alerts to an MQTT broker for Home Assistant integration.",
        "hidden": [
            "Set the MQTT broker address and port in Settings — the page will show connection status once configured.",
            "Each device gets its own Home Assistant entity — ideal for automations like 'if the kids' tablet leaves the network, run a script'.",
        ],
    },
    "REST API": {
        "what": "Read-only HTTP API (default port 8765) — exposes /devices, /alerts, /uptime, /grade, /speed-history, /dashboard, and /health.",
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
            "For real-time ARP/DHCP/Storm monitors, use ARP Spoof Watch, DHCP Rogue Monitor, and Broadcast Storm in this section and in Analysis.",
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
        "what": "Monitors TLS certificate expiry per host and checks for accidental internet exposure of internal services.",
        "hidden": [
            "Certificates are checked hourly — you will see an alert badge 30 days before any cert expires.",
            "Exposure checks probe from the internet side — a result of 'exposed' means the port is reachable from outside your network.",
        ],
    },
    "Login Test": {
        "what": "Tests common default credentials against discovered services — for authorised use on networks you own.",
        "hidden": [
            "This test only tries documented factory-default passwords, not brute-force lists — it is designed for auditing your own devices.",
            "Results feed into Device Risk Score — a device with default credentials gets a critical risk flag.",
        ],
    },
    "OS Detection": {
        "what": "Fingerprints device operating systems using TCP/IP stack analysis.",
        "hidden": [
            "Accuracy improves when port scan data is available — run a TCP port scan first.",
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
            "Newly discovered CVEs appear with a 'New' badge — these are the ones to prioritise for patching.",
            "CVE Tracker needs data to track — run CVE Lookup first to discover vulnerabilities, then come back here to monitor remediation progress.",
        ],
    },
    "Exposed to Internet": {
        "what": "Checks whether services on your network are reachable from the public internet via your external IP.",
        "hidden": [
            "A result of 'exposed' means someone outside your network could connect to that port — check your router's port-forwarding rules.",
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
            "Shared folders that are visible without a password are flagged — these are a common data-exfiltration risk on home networks.",
        ],
    },
    "Recon Plugins": {
        "what": "Custom port-scanner and enumeration scripts — not hardware driver plugins. Drop a .py plugin file into the plugins/ directory to add new scan capabilities.",
        "hidden": [
            "See CONTRIBUTING.md for the plugin API — a plugin is a single Python class with a run() method.",
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
        "what": "Animated step-by-step diagrams of ARP, DNS, TCP, DHCP, and STP using your real device addresses.",
        "hidden": [
            "Click any step in the step list to jump directly to it — you don't have to watch the full animation.",
            "The '▸ Why this protocol matters' panel at the bottom links the animation to real threats NetSentinel detects.",
            "The 'See diagram' button in any Explain This panel jumps here with the right protocol pre-selected.",
        ],
    },
    "Lab Mode": {
        "what": "Guided exercises that walk you through diagnosing your live network step by step.",
        "hidden": [
            "When the Home page shows a live event card, clicking 'Investigate →' drops you straight into a one-step lab built from that event.",
            "After finishing an exercise, click 'Export Report (HTML)' to save a portable lab report.",
            "Hints don't penalise you — use them freely. The solution is always there if you're stuck.",
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
