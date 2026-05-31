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
    "Overview": {
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
        ],
    },
    "Bandwidth Usage": {
        "what": "Per-device bandwidth usage collected during packet capture sessions.",
        "hidden": [
            "Packet capture requires Npcap on Windows — install it from npcap.com for this tab to populate.",
            "Click a row to see the breakdown of protocols that device is using.",
            "The top-talker list shows which device is consuming the most bandwidth — useful for finding rogue downloaders.",
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
    "Monitor Overview": {
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
        ],
    },
    "Port Scan (TCP)": {
        "what": "SYN stealth port scanner — identifies open TCP ports on discovered devices. Requires admin + Npcap.",
        "hidden": [
            "SYN scan is faster and quieter than a connect scan because it never completes the three-way handshake.",
            "Scan results feed into Device Risk Score and CVE Lookup automatically.",
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

# ---------------------------------------------------------------------------
# Helpers re-used by build_help_tab()
# ---------------------------------------------------------------------------
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT, ACCENT_DARK, AMBER, AMBER_BG, BG_ALT_ROW, BG_CARD, BORDER,
    CARD_HDR_BORDER, CARD_RADIUS, GREEN, GREEN_BG,
    NAV_BAR, RED, RED_BG,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)


def _page_header(title: str, subtitle: str = "") -> QFrame:
    """
    Returns a QFrame header container with 16/20/12px breathing room and a
    1px bottom divider.  title 18px bold TEXT_PRIMARY, subtitle 11px TEXT_SECONDARY.
    """
    container = QFrame()
    container.setObjectName("pageHeader")
    container.setStyleSheet(
        f"QFrame#pageHeader {{ background: transparent; border: none;"
        f" border-bottom: 1px solid {BORDER}; }}"
    )
    vbox = QVBoxLayout(container)
    vbox.setContentsMargins(20, 16, 20, 12)
    vbox.setSpacing(2)
    t = QLabel(title)
    t.setStyleSheet(
        f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold;"
        "padding:0; background:transparent; border:none;"
    )
    vbox.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px;"
            "padding:0; background:transparent; border:none;"
        )
        vbox.addWidget(s)
    return container


def build_help_tab(window) -> QWidget:
    """Static Help & Shortcuts reference page.

    Extracted from Dashboard._build_help_tab(). All ``self`` references have
    been replaced with ``window`` so the method can live outside the class
    while still setting attributes (e.g. ``window._update_lbl``) on the
    Dashboard instance.
    """
    from PyQt6.QtWidgets import QApplication

    page = QWidget()
    page.setObjectName("contentArea")
    outer = QVBoxLayout(page)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(10)

    # Page header
    outer.addWidget(_page_header(
        "Help & Shortcuts",
        "Quick-start guide, keyboard shortcuts, and feature reference",
    ))

    # Scrollable body
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setStyleSheet("background: transparent;")

    body = QWidget()
    body.setObjectName("contentArea")
    bl = QVBoxLayout(body)
    bl.setContentsMargins(0, 0, 12, 20)
    bl.setSpacing(12)

    def _section(title: str, rows: list[tuple[str, str]]) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(
            f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
            f"border-radius:{CARD_RADIUS};}}"
        )
        cl = QVBoxLayout(card)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        # title bar
        tb = QFrame()
        tb.setObjectName("cardHeader")
        tb.setFixedHeight(32)
        tb.setStyleSheet(
            f"background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};"
        )
        tbl = QHBoxLayout(tb)
        tbl.setContentsMargins(12, 0, 12, 0)
        t = QLabel(title)
        t.setStyleSheet(
            f"color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;"
        )
        tbl.addWidget(t)
        tbl.addStretch()
        cl.addWidget(tb)

        # rows
        tbl_w = QTableWidget(len(rows), 2)
        tbl_w.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl_w.horizontalHeader().setVisible(False)
        tbl_w.verticalHeader().setVisible(False)
        tbl_w.setShowGrid(False)
        tbl_w.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        tbl_w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        tbl_w.setStyleSheet(
            f"QTableWidget{{background:{BG_CARD};border:none;font-size:11px;}}"
            f"QTableWidget::item{{padding:4px 8px;color:{TEXT_PRIMARY};}}"
        )
        tbl_w.horizontalHeader().setStretchLastSection(True)
        tbl_w.setColumnWidth(0, 220)
        tbl_w.verticalHeader().setDefaultSectionSize(24)

        for i, (key, desc) in enumerate(rows):
            k = QTableWidgetItem(key)
            k.setFont(QFont("Consolas", 10))
            k.setForeground(QColor(ACCENT_DARK))
            k.setBackground(QColor(BG_ALT_ROW if i % 2 else BG_CARD))
            d = QTableWidgetItem(desc)
            d.setBackground(QColor(BG_ALT_ROW if i % 2 else BG_CARD))
            tbl_w.setItem(i, 0, k)
            tbl_w.setItem(i, 1, d)

        tbl_w.setFixedHeight(len(rows) * 24 + 2)
        cl.addWidget(tbl_w)
        return card

    # ── Getting started ──────────────────────────────────────────────────
    intro_card = QFrame()
    intro_card.setObjectName("card")
    intro_card.setStyleSheet(
        f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
        f"border-radius:{CARD_RADIUS};}}"
    )
    icl = QVBoxLayout(intro_card)
    icl.setContentsMargins(0, 0, 0, 0)
    icl.setSpacing(0)

    itb = QFrame()
    itb.setFixedHeight(32)
    itb.setStyleSheet(f"background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};")
    itbl = QHBoxLayout(itb)
    itbl.setContentsMargins(12, 0, 12, 0)
    itl = QLabel("Getting Started")
    itl.setStyleSheet(f"color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;")
    itbl.addWidget(itl)
    itbl.addStretch()
    icl.addWidget(itb)

    intro_text = QLabel(
        "<p style='margin:12px 16px 4px 16px; font-size:11px; "
        f"color:{TEXT_PRIMARY}; line-height:1.6;'>"
        "<b>1. Run as Administrator</b> — STP, Storm, ARP, and Bandwidth modules "
        "require raw packet capture (Npcap on Windows). Right-click the shortcut "
        "→ Run as Administrator, or the app will prompt you automatically.<br><br>"
        "<b>2. Click Run Scan</b> — the main scan button sweeps your subnet, "
        "flushes ARP/DNS caches, and populates all Standard tabs in parallel. "
        "Most scans finish in 10–30 seconds depending on network size.<br><br>"
        "<b>3. Switch to Standard mode</b> — click the mode pill in the top bar "
        "(shows Home ▾ by default) and choose Standard. This reveals MTR, Bandwidth, "
        "ARP Watch, DHCP, Network Map, Scheduled Scans, Trend Forecasts, and more.<br><br>"
        "<b>4. Switch to Pro mode for Security Audit</b> — choose Pro from the same "
        "mode pill to reveal SYN/UDP port scanners, OS detection, CVE lookup, credential "
        "testing, and cloud metadata probe. "
        "Only use on networks you own or have explicit written authorisation to test.<br><br>"
        "<b>5. Right-click anything</b> — every table row has a context menu "
        "with Copy IP, Copy MAC, Port Scan, How to Fix, Wake-on-LAN, and more.<br><br>"
        "<b>6. Generate a Network Health Report</b> — run the Stability Logger for at least "
        "30 minutes, then open Network Grade → Network Health Report. Exports a "
        "standalone HTML file with evidence-grade data — great for ISP support tickets."
        "</p>"
    )
    intro_text.setWordWrap(True)
    intro_text.setTextFormat(Qt.TextFormat.RichText)
    icl.addWidget(intro_text)
    bl.addWidget(intro_card)

    # ── First 10 Minutes walkthrough ─────────────────────────────────────
    walkthrough_card = QFrame()
    walkthrough_card.setObjectName("card")
    walkthrough_card.setStyleSheet(
        f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
        f"border-radius:{CARD_RADIUS};}}"
    )
    wcl = QVBoxLayout(walkthrough_card)
    wcl.setContentsMargins(0, 0, 0, 0)
    wcl.setSpacing(0)
    wtb = QFrame()
    wtb.setFixedHeight(32)
    wtb.setStyleSheet(f"background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};")
    wtbl = QHBoxLayout(wtb)
    wtbl.setContentsMargins(12, 0, 12, 0)
    wtl = QLabel("First 10 Minutes — Guided Walkthrough")
    wtl.setStyleSheet(f"color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;")
    wtbl.addWidget(wtl)
    wtbl.addStretch()
    wcl.addWidget(wtb)
    walkthrough_text = QLabel(
        f"<div style='margin:12px 16px 12px 16px; font-size:11px; "
        f"color:{TEXT_PRIMARY}; line-height:1.7;'>"
        f"<b style='color:{ACCENT};'>Step 1 — See what's on your network</b><br>"
        "Click <b>Run Scan</b> on the Home screen (or press Ctrl+R). NetSentinel sends "
        "ARP requests to every address in your subnet and builds a full device list. "
        "Most home networks finish in under 15 seconds.<br>"
        "<i>What to look for:</i> any device you don't recognise. Note its MAC address "
        "— the first 6 characters identify the manufacturer (e.g. <code>B8:27:EB</code> = Raspberry Pi).<br><br>"

        f"<b style='color:{ACCENT};'>Step 2 — Check your connection quality</b><br>"
        "Go to <b>DNS &amp; Outages</b>. You'll see a live RTT graph to your gateway and "
        "internet targets. A flat line under 10 ms to your router is healthy. "
        "Spikes above 200 ms, or gaps in the line, indicate packet loss.<br>"
        "<i>What to look for:</i> regular drops every 30–45 seconds often mean a "
        "device on your network is winning the STP Root Bridge election. "
        "See <i>Learn Networking</i> below for what that means.<br><br>"

        f"<b style='color:{ACCENT};'>Step 3 — Run the Health Check</b><br>"
        "Open <b>Health Check</b> and click <b>Run Diagnostics</b>. This tests ping "
        "to 5 targets, compares DNS speed across 4 resolvers, checks HTTP reachability, "
        "and runs a traceroute to your gateway.<br>"
        "<i>What to look for:</i> if the DNS comparison shows your ISP's resolver "
        "is 3–5× slower than Cloudflare (1.1.1.1), switching DNS in your router settings "
        "can noticeably speed up browsing.<br><br>"

        f"<b style='color:{ACCENT};'>Step 4 — Get your Network Grade</b><br>"
        "Open <b>Network Grade</b>. The A–F score across 8 dimensions tells you "
        "where your network ranks. Any dimension rated C or below has a "
        "<b>How to Fix</b> guide — click the row.<br>"
        "<i>What to look for:</i> a low Safety score means unknown or high-risk "
        "devices are present. A low STP score means a rogue bridge was detected.<br><br>"

        f"<b style='color:{ACCENT};'>Step 5 — Let it run in the background</b><br>"
        "Leave NetSentinel open for 30+ minutes while you use your network normally. "
        "The <b>Stability Log</b> and <b>Availability History</b> tabs build up "
        "timestamped evidence. After 30 minutes, <b>Network Grade → Network Health Report</b> "
        "produces a standalone HTML file you can attach to an ISP support ticket — "
        "with hop-by-hop packet loss, outage timestamps, and DNS latency data.<br><br>"

        f"<b style='color:{ACCENT};'>Tip — Right-click everything</b><br>"
        "Every table row in NetSentinel has a context menu. Right-click any device "
        "for <b>Copy IP</b>, <b>Copy MAC</b>, <b>Port Scan</b>, <b>How to Fix</b>, "
        "and <b>Wake-on-LAN</b>. Right-click any scan result for remediation guidance."
        "</div>"
    )
    walkthrough_text.setWordWrap(True)
    walkthrough_text.setTextFormat(Qt.TextFormat.RichText)
    wcl.addWidget(walkthrough_text)
    bl.addWidget(walkthrough_card)

    # ── Keyboard shortcuts ───────────────────────────────────────────────
    bl.addWidget(_section("Keyboard Shortcuts", [
        ("Ctrl + R",           "Run full scan"),
        ("Ctrl + Shift + M",   "Visual Diagnostic Overlay (Matrix)"),
        ("Ctrl + E",           "Export last scan results"),
        ("Ctrl + Q",           "Quit application"),
        ("F5",                 "Refresh current tab"),
        ("Right-click",        "Context menu on any table row"),
    ]))

    # ── Feature reference ────────────────────────────────────────────────
    bl.addWidget(_section("Standard Features (no admin required for most)", [
        ("Devices on Network",   "ARP scan — every device with IP, MAC, vendor, model, type, risk"),
        ("Rogue Bridge (STP)",   "Captures BPDUs and flags devices stealing the Root Bridge role"),
        ("Broadcast Storm",      "Measures broadcast/multicast flood levels by source device"),
        ("WiFi Networks",        "Hidden SSIDs, rogue APs, co-channel interference, WPS flags"),
        ("DNS & Outages",        "Live ping + DNS latency graph with STP reconvergence detection"),
        ("My Network Info",      "Local IPs, subnet, gateway, DNS servers, DHCP lease, adapter speeds"),
        ("Health Check",         "On-demand ping, DNS speed test, traceroute, HTTP check, DNS leak test"),
        ("Stability Log",        "Long-term logger — timestamped outage evidence for ISP disputes"),
        ("Availability History", "Per-target uptime log with expandable incident detail per row"),
        ("Network Grade",        "A–F score across 8 dimensions with an exportable Network Health Report"),
        ("Root Cause Analysis",  "Correlates STP, Storm, DNS, and Logger data — ISP vs local verdict"),
        ("IoT Behaviour",        "Baselines normal IoT traffic, alerts on port scanning or new servers"),
        ("IPv6 Devices",         "Link-local segment sweep via OS neighbour cache and ping"),
        ("Service Heartbeat",    "Monitor uptime and response time of any host:port — custom target list"),
        ("Active Connections",   "Live table of current TCP/UDP connections with process and remote IP"),
        ("WiFi Heatmap",         "Import floor plan, record signal-strength readings, IDW heatmap overlay per AP"),
        ("Geolocation Map",      "World-map plot of internet-facing IPs — MaxMind GeoLite2 local DB, no external API"),
        ("Custom Triggers",      'Alert expressions: avg(rtt["ip"], 5m) > 80 — visual builder, test now, cooldown'),
        ("Protocol Visualizer",  "Animated ARP, DNS, TCP, DHCP, and STP diagrams using your real scan data"),
        ("Lab Mode",             "Hands-on sandbox exercises for learning networking protocols step by step"),
    ]))

    bl.addWidget(_section("Advanced Features (Standard and Pro modes)", [
        ("Hop-by-Hop Trace",     "Continuous MTR — live per-hop loss % and RTT, updating every cycle"),
        ("Tools & Wake-on-LAN",  "TCP port scanner (Fast / Normal / Low), service banners, WoL sender"),
        ("Network Map",          "Visual topology diagram of devices and their relationships"),
        ("ARP Spoof Watch",      "Detects ARP poisoning and MITM attacks in real time"),
        ("DHCP Leases",          "DHCP lease inventory — all IPs handed out by your router"),
        ("DHCP Rogue Monitor",   "Actively probes for rogue DHCP servers via crafted Discover packets"),
        ("Bandwidth Usage",      "Per-device rx/tx bps monitor via live packet capture"),
        ("Scheduled Scans",      "Automated scans every N minutes with desktop notifications"),
        ("SNMP Device Info",     "Polls SNMPv1/v2c OIDs — no extra dependencies required"),
        ("Syslog Receiver",      "Collects syslog messages from routers, switches, and servers"),
        ("SNMP Trap Receiver",   "Receives SNMP trap messages from network devices"),
        ("Trend Forecasts",      "ML-based predictive forecasting of latency, packet loss, and uptime"),
        ("Config Snapshots",     "Timestamped network configuration snapshots with diff highlighting"),
        ("Maintenance Windows",  "Schedule maintenance periods to suppress alerts during planned downtime"),
        ("Automation Hooks",     "Fire webhook / run script when network events occur — device-down, high RTT, new device"),
        ("Network Documentation","Auto-generates HTML/Markdown snapshot: inventory, services, topology, TLS"),
        ("MQTT / Home Assistant","Publish device/metric events to MQTT broker; HA Discovery payloads"),
    ]))

    bl.addWidget(_section("Security Audit Features (Pro mode — admin required)", [
        ("Port Scan (TCP)",       "Raw SYN scanner — stealthy, fast, admin required"),
        ("Port Scan (UDP)",       "UDP service discovery"),
        ("OS Detection",          "OS fingerprinting via TTL + banner + SYN probe"),
        ("Device Risk Score",     "Per-device numeric risk score with remediation guidance"),
        ("Known CVEs",            "NVD API v2 CVE lookup for detected software/services"),
        ("Exposed to Internet",   "WAN IP, CGNAT detection, UPnP port mapping enumeration"),
        ("Login Test (SSH/SMB)",  "Credential testing against SSH and SMB services"),
        ("Full Device Discovery", "Parallel ARP + ICMP + TCP SYN + mDNS discovery"),
        ("Windows Shares (SMB)",  "NetBIOS + SMB share and user enumeration"),
        ("Private Endpoint Check","DNS/TCP/TLS reachability checker for cloud private endpoints"),
        ("Cloud Metadata Probe",  "Detects SSRF exposure via cloud VM metadata endpoint access"),
    ]))

    # ── What's New ───────────────────────────────────────────────────────
    app_ver = QApplication.applicationVersion()
    bl.addWidget(_section(f"What's New in v{app_ver}", [
        ("Flat-nav dead code removed (S13-5c)", "Removed the old progressive-disclosure nav mode system (_nav_mode, _cycle_mode, _set_mode, _rail_mode_btn). Navigation always uses the activity rail — no more silent no-ops when mode was 'home'."),
        ("18 Tier 2 scan/detection module tests (S9-2)", "140 new unit tests covering arp_monitor, bandwidth_monitor, cloud_metadata, dns_correlator, dns_zone_scanner, ha_detector, internet_exposure, os_fingerprint, port_scanner, process_monitor, rogue_device, smb_enumerator, snmp_poller, storm_analyser, stp_detector, syn_scanner, threat_intel, wifi_scanner."),
        ("Colour token inventory (S10-1)", "test_colour_inventory.py locks per-file hardcoded-hex budgets for 70 files. No new raw #RRGGBB strings can be introduced without updating the budget — prereq for the S10-2 purge sprint."),
    ]))

    # ── Requirements ─────────────────────────────────────────────────────
    bl.addWidget(_section("Requirements & Notes", [
        ("Administrator rights",  "Required for STP, Storm, ARP Watch, Bandwidth, SYN scan"),
        ("Npcap (Windows)",        "Required for raw packet capture — https://npcap.com (free)"),
        ("Python 3.10+",           "If running from source: pip install -r requirements.txt"),
        ("WINGET_PAT (CI only)",   "GitHub PAT with repo scope — needed only for automated winget submission in CI"),
    ]))

    # ── Risk Level Guide ──────────────────────────────────────────────────
    risk_card = QFrame()
    risk_card.setObjectName("card")
    risk_card.setStyleSheet(
        f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
        f"border-radius:{CARD_RADIUS};}}"
    )
    rcl = QVBoxLayout(risk_card)
    rcl.setContentsMargins(0, 0, 0, 0)
    rcl.setSpacing(0)
    rtb = QFrame()
    rtb.setFixedHeight(32)
    rtb.setStyleSheet(f"background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};")
    rtbl = QHBoxLayout(rtb)
    rtbl.setContentsMargins(12, 0, 12, 0)
    rtl = QLabel("Risk Level Guide")
    rtl.setStyleSheet(f"color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;")
    rtbl.addWidget(rtl)
    rtbl.addStretch()
    rcl.addWidget(rtb)

    _risk_rows = [
        ("CLEAN",   GREEN,    GREEN_BG,  "No threats or issues detected. All devices are expected."),
        ("LOW",     ACCENT,   BG_CARD,   "Minor or informational — no immediate action required."),
        ("MEDIUM",  AMBER,    AMBER_BG,  "Noteworthy — review soon. Examples: unknown device, degraded RTT."),
        ("WARNING", AMBER,    AMBER_BG,  "Active issue that should be investigated promptly."),
        ("HIGH",    RED,      RED_BG,    "Serious threat detected — ARP spoof, rogue bridge, rogue DHCP."),
        ("STORM",   RED,      RED_BG,    "Broadcast storm in progress — network performance is impacted now."),
        ("UNKNOWN", TEXT_MUTED, BG_CARD, "Device or result could not be classified. Check manually."),
    ]
    for lvl, fg, bg, meaning in _risk_rows:
        rw = QWidget()
        rw.setStyleSheet(f"background:{bg};")
        rwl = QHBoxLayout(rw)
        rwl.setContentsMargins(12, 4, 12, 4)
        rwl.setSpacing(10)
        badge = QLabel(lvl)
        badge.setFixedWidth(72)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"color:{fg};font-size:10px;font-weight:bold;"
            f"border:1px solid {fg};border-radius:3px;padding:1px 4px;"
            f"background:transparent;"
        )
        ml = QLabel(meaning)
        ml.setStyleSheet(f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;")
        rwl.addWidget(badge)
        rwl.addWidget(ml, 1)
        rcl.addWidget(rw)
    bl.addWidget(risk_card)

    # ── Common Scenarios ──────────────────────────────────────────────────
    bl.addWidget(_section("I want to…  (Common Scenarios)", [
        ("…see every device on my network",       "Devices on Network — run a scan"),
        ("…find out why my internet is slow",     "Network Grade → run benchmark; Stability Log for long-term evidence"),
        ("…detect if someone is on my WiFi",      "WiFi Networks + Devices on Network → look for unknown MACs"),
        ("…prove to my ISP the problem is theirs","Stability Log for 30+ min → Network Grade → Network Health Report"),
        ("…check if a device is hacked",          "Device Risk Score + Known CVEs (Security Audit section)"),
        ("…monitor uptime of my servers",         "Service Heartbeat → add hosts + ports to watch"),
        ("…see all open ports on a device",       "Tools & Wake-on-LAN → TCP Port Scan (Advanced section)"),
        ("…detect ARP spoofing / MITM attack",    "ARP Spoof Watch (Advanced section)"),
        ("…see who is using the most bandwidth",  "Bandwidth Usage (Advanced section)"),
        ("…check TLS certificate expiry",         "TLS & exposure (Security Audit section)"),
        ("…trace packet loss hop-by-hop",         "Hop-by-Hop Trace / MTR (Advanced section)"),
        ("…map WiFi coverage in a room",          "WiFi Heatmap (Tools) — import floor plan, walk space, render heatmap"),
        ("…see where threat IPs are located",     "Geolocation Map (Tools) — import from Threat Intel or add IPs manually"),
        ("…alert on custom metric thresholds",    "Custom Triggers (Reports & Alerts) — write expressions like avg(rtt,5m)>80"),
        ("…trigger automation when a host drops", "Automation Hooks (Advanced) — add webhook/script rule for device-down event"),
        ("…send events to Home Assistant",        "MQTT / Home Assistant (Advanced) — configure broker, enable Discovery"),
        ("…change the colour theme",              "⚙ Settings → Appearance — Colour Theme"),
        ("…see how ARP/DNS/TCP actually works",   "Protocol Visualizer (Education section) — animated diagrams using your real scan data"),
        ("…use NetSentinel from my phone",        "Web Dashboard — open http://localhost:8765/dashboard on any LAN device"),
        ("…get a weekly health summary",          "Automatic — weekly digest tray notification fires on startup once per 7 days"),
        ("…forecast when my network will degrade","Trend Forecasts (Standard/Pro) — ML-based latency and uptime prediction"),
    ]))

    # ── Glossary ──────────────────────────────────────────────────────────
    bl.addWidget(_section("Glossary — Key Terms", [
        ("ARP",            "Address Resolution Protocol — maps IP addresses to MAC addresses on a LAN"),
        ("ARP Spoofing",   "Attack where a device sends fake ARP replies to redirect traffic through it"),
        ("BPDU",           "Bridge Protocol Data Unit — packets used by switches to elect the Root Bridge"),
        ("CGNAT",          "Carrier-Grade NAT — ISP shares one public IP across many customers; you can't host servers"),
        ("CVE",            "Common Vulnerabilities and Exposures — public database of known security flaws"),
        ("DHCP",           "Dynamic Host Configuration Protocol — server that hands out IP addresses automatically"),
        ("DNS",            "Domain Name System — translates names like google.com to IP addresses"),
        ("DNS Leak",       "When your DNS queries go to your ISP's server instead of your chosen one (privacy risk)"),
        ("Jitter",         "Variation in packet arrival time — high jitter causes choppy voice/video calls"),
        ("MAC address",    "Hardware address burned into a network adapter — unique per device (first 3 bytes = vendor OUI)"),
        ("mDNS",           "Multicast DNS — lets devices announce themselves on the LAN without a central server"),
        ("MITM",           "Man-in-the-Middle — attacker intercepts traffic between two parties"),
        ("MTR",            "My TraceRoute — combines ping and traceroute, showing loss % at each hop"),
        ("Npcap",          "Windows packet capture driver required for raw network access (free, from npcap.com)"),
        ("OUI",            "Organizationally Unique Identifier — the first 3 bytes of a MAC that identify the vendor"),
        ("RTT",            "Round-Trip Time — how long a packet takes to travel to a host and back (in ms)"),
        ("SNMP",           "Simple Network Management Protocol — queries routers/switches for status data"),
        ("SSRF",           "Server-Side Request Forgery — server makes unintended requests; exploits cloud metadata APIs"),
        ("STP",            "Spanning Tree Protocol — prevents loops in switched networks by electing a Root Bridge"),
        ("Subnet",         "A range of IP addresses within a network, e.g. 192.168.1.0/24 = 256 addresses"),
        ("SYN scan",       "Port scan technique using half-open TCP connections — stealthy, fast, needs admin rights"),
        ("TLS",            "Transport Layer Security — encrypts connections (HTTPS, SMTPS, etc.); replaces SSL"),
        ("UPnP",           "Universal Plug and Play — lets devices open ports on your router automatically (security risk)"),
        ("WAN IP",         "Your external public IP address as seen by the internet"),
    ]))

    # ── Learn Networking ─────────────────────────────────────────────────
    learn_card = QFrame()
    learn_card.setObjectName("card")
    learn_card.setStyleSheet(
        f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
        f"border-radius:{CARD_RADIUS};}}"
    )
    lcl = QVBoxLayout(learn_card)
    lcl.setContentsMargins(0, 0, 0, 0)
    lcl.setSpacing(0)
    ltb = QFrame()
    ltb.setFixedHeight(32)
    ltb.setStyleSheet(f"background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};")
    ltbl = QHBoxLayout(ltb)
    ltbl.setContentsMargins(12, 0, 12, 0)
    ltl = QLabel("Learn Networking — How Your Network Actually Works")
    ltl.setStyleSheet(f"color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;")
    ltbl.addWidget(ltl)
    ltbl.addStretch()
    lcl.addWidget(ltb)
    learn_text = QLabel(
        f"<div style='margin:12px 16px 14px 16px; font-size:11px; "
        f"color:{TEXT_PRIMARY}; line-height:1.75;'>"

        f"<b style='font-size:12px; color:{ACCENT};'>Your home network at a glance</b><br>"
        "Your <b>router</b> sits between two worlds: the <b>WAN</b> (your ISP — the internet) "
        "and the <b>LAN</b> (your home devices). Every device on the LAN gets two addresses: "
        "a <b>MAC address</b> (burned into the hardware, identifies the manufacturer, never changes) "
        "and an <b>IP address</b> (assigned by DHCP, can change on reconnect). "
        "Your router runs <b>DHCP</b> to hand out IPs automatically and <b>DNS</b> to translate "
        "names like <i>google.com</i> into the IP addresses that packets actually travel to.<br><br>"

        f"<b style='font-size:12px; color:{ACCENT};'>How the scan works — ARP</b><br>"
        "<b>ARP</b> (Address Resolution Protocol) is how devices on a LAN find each other. "
        "When your computer wants to talk to 192.168.1.1, it broadcasts <i>"
        "\"Who has 192.168.1.1?\"</i> — every device on the subnet hears this. "
        "The device with that IP replies with its MAC address. "
        "NetSentinel sends an ARP request to every address in your subnet simultaneously, "
        "then listens for replies — revealing every active device without any special permissions.<br><br>"

        f"<b style='font-size:12px; color:{ACCENT};'>Reading RTT — what the numbers mean</b><br>"
        "<b>RTT</b> (Round-Trip Time) is how long a packet takes to travel to a host and "
        "return, measured in milliseconds. Good benchmarks: <b>&lt; 1 ms</b> to your router "
        "(same LAN); <b>&lt; 20 ms</b> to your ISP gateway; <b>&lt; 50 ms</b> to major internet "
        "servers. Over <b>100 ms</b> consistently to 8.8.8.8 means your connection is struggling. "
        "<b>Jitter</b> (variation between readings) matters for voice and video — "
        "a stable 30 ms line is better than one that swings between 5 ms and 200 ms.<br><br>"

        f"<b style='font-size:12px; color:{ACCENT};'>Spanning Tree Protocol (STP) — the hidden troublemaker</b><br>"
        "STP prevents network loops by electing one device as the <b>Root Bridge</b> — "
        "all traffic flows through it. Your router should win this election. "
        "But mesh WiFi nodes, smart TVs, and game consoles connected via Ethernet also "
        "participate in STP. If any device has a lower <i>Bridge ID</i> than your router, "
        "it wins the election — and your router blocks its own uplink port while the "
        "new root reconverges the network. This causes <b>15–45 second outages every few minutes</b> "
        "that ISP support always blames on WiFi interference. "
        "NetSentinel captures the BPDU packets that reveal which device is doing this.<br><br>"

        f"<b style='font-size:12px; color:{ACCENT};'>ARP spoofing — how MITM attacks work</b><br>"
        "Because ARP has no authentication, a device can send <i>fake</i> ARP replies: "
        "<i>\"I have the IP of your router — send traffic to my MAC instead.\"</i> "
        "Every device on the LAN updates its ARP cache with the lie. Now all your traffic "
        "flows through the attacker's machine, which reads it and forwards it on — "
        "a classic <b>Man-in-the-Middle (MITM)</b> attack. "
        "NetSentinel detects this by watching for IP-to-MAC mapping conflicts in ARP traffic.<br><br>"

        f"<b style='font-size:12px; color:{ACCENT};'>Broadcast storms — when traffic eats itself</b><br>"
        "ARP requests, mDNS queries, and DHCP discovery are all <b>broadcasts</b> — "
        "every device on the LAN must process each one. Normally this is a tiny background noise. "
        "But a network loop (two cables between the same two switches), a misconfigured device, "
        "or a compromised machine can generate thousands of broadcasts per second. "
        "Every device spends all its time processing broadcasts and has no capacity left for "
        "real traffic. This looks exactly like an ISP outage — but the problem is entirely local. "
        "The Broadcast Storm tab shows the flood rate and which device is the source.<br><br>"

        f"<b style='font-size:12px; color:{ACCENT};'>DNS — the phone book, and why it affects speed</b><br>"
        "Every website visit starts with a DNS lookup before a single byte of content loads. "
        "If your DNS resolver is slow, <i>every</i> page has a hidden delay. "
        "ISP-provided DNS servers are often 30–100 ms. "
        "Cloudflare (1.1.1.1) and Google (8.8.8.8) are typically under 10 ms from most locations. "
        "A <b>DNS leak</b> happens when your DNS queries bypass your VPN or privacy settings "
        "and go to your ISP instead — revealing every site you visit. "
        "The Health Check tab benchmarks all resolvers side-by-side on your current connection.<br><br>"

        f"<b style='font-size:12px; color:{ACCENT};'>Open ports — what they reveal</b><br>"
        "Every service on a device listens on a numbered <b>port</b>. "
        "Port 22 = SSH (remote terminal), 80 = HTTP, 443 = HTTPS, "
        "3389 = Windows Remote Desktop, 8080 = admin web interfaces. "
        "If a device has unexpected management ports open — especially from the WAN — "
        "it may be misconfigured or compromised. "
        "A <b>SYN scan</b> (Security Audit mode) sends a half-open TCP connection to each port "
        "and measures whether something replies — fast, precise, and requires admin rights "
        "because it bypasses the normal OS socket layer.<br><br>"

        f"<b style='font-size:12px; color:{ACCENT};'>The Network Grade — what each dimension measures</b><br>"
        "<b>Uptime</b> — % of time your internet target was reachable in the last 24h. "
        "<b>Latency</b> — average RTT to internet; A = under 20 ms, F = over 150 ms. "
        "<b>Jitter</b> — RTT variance; A = under 5 ms, F = over 50 ms. "
        "<b>DNS Speed</b> — fastest resolver found vs slowest. "
        "<b>Download Speed</b> — measured against your expected throughput. "
        "<b>Device Safety</b> — any HIGH or CRITICAL risk devices drag this down. "
        "<b>STP Health</b> — any rogue bridge detected = instant F. "
        "<b>Storm Level</b> — broadcast packets per second vs your LAN capacity."
        "</div>"
    )
    learn_text.setWordWrap(True)
    learn_text.setTextFormat(Qt.TextFormat.RichText)
    lcl.addWidget(learn_text)
    bl.addWidget(learn_card)

    # ── Appearance / Theme → redirect to Settings ─────────────────────────
    appear_callout = QFrame()
    appear_callout.setObjectName("card")
    appear_callout.setStyleSheet(
        f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
        f"border-radius:{CARD_RADIUS};}}"
    )
    acl = QVBoxLayout(appear_callout)
    acl.setContentsMargins(0, 0, 0, 0)
    acl.setSpacing(0)
    atb = QFrame()
    atb.setFixedHeight(32)
    atb.setStyleSheet(f"background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};")
    atbl = QHBoxLayout(atb)
    atbl.setContentsMargins(12, 0, 12, 0)
    atl = QLabel("Appearance & Customisation")
    atl.setStyleSheet(f"color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;")
    atbl.addWidget(atl)
    atbl.addStretch()
    acl.addWidget(atb)
    abody = QWidget()
    abody.setStyleSheet(f"background:{BG_CARD};")
    abl = QHBoxLayout(abody)
    abl.setContentsMargins(16, 10, 16, 12)
    abl.setSpacing(12)
    ainfo = QLabel(
        "Colour themes, display preferences, and shortcuts are managed in one place."
    )
    ainfo.setStyleSheet(f"font-size:11px;color:{TEXT_SECONDARY};background:transparent;")
    abl.addWidget(ainfo, 1)
    btn_go_settings = QPushButton("⚙  Open Settings")
    btn_go_settings.setStyleSheet(
        f"QPushButton{{background:{ACCENT};color:{NAV_BAR};"
        f"border:1px solid {ACCENT};border-radius:4px;"
        f"padding:5px 14px;font-size:11px;font-weight:bold;}}"
        f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
    )
    btn_go_settings.clicked.connect(
        lambda: window._open_settings_dialog()
    )
    abl.addWidget(btn_go_settings)
    acl.addWidget(abody)
    bl.addWidget(appear_callout)

    # ── Check for updates ─────────────────────────────────────────────────
    update_card = QFrame()
    update_card.setObjectName("card")
    update_card.setStyleSheet(
        f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
        f"border-radius:{CARD_RADIUS};}}"
    )
    ucl = QVBoxLayout(update_card)
    ucl.setContentsMargins(0, 0, 0, 0)
    ucl.setSpacing(0)
    utb = QFrame()
    utb.setFixedHeight(32)
    utb.setStyleSheet(f"background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};")
    utbl = QHBoxLayout(utb)
    utbl.setContentsMargins(12, 0, 12, 0)
    utl = QLabel("Updates")
    utl.setStyleSheet(f"color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;")
    utbl.addWidget(utl)
    utbl.addStretch()
    ucl.addWidget(utb)
    ubody = QHBoxLayout()
    ubody.setContentsMargins(12, 8, 12, 10)
    window._update_lbl = QLabel(f"Current version: v{app_ver}")
    window._update_lbl.setStyleSheet(f"font-size:11px;color:{TEXT_PRIMARY};")
    ubody.addWidget(window._update_lbl, 1)
    btn_update = QPushButton("Check for Updates")
    btn_update.setObjectName("btnNetRefresh")
    btn_update.setFixedWidth(140)
    btn_update.clicked.connect(window._check_for_updates)
    ubody.addWidget(btn_update)
    ucl.addLayout(ubody)
    bl.addWidget(update_card)

    bl.addStretch()
    scroll.setWidget(body)
    outer.addWidget(scroll, 1)
    return page
