"""
Feature Guide page — searchable index of every NetSentinel feature.

Gives users a single place to discover what the app can do, understand each
feature in one sentence, and navigate directly to it.  Grouped by theme;
filterable by name, description, group, page label, or synonym tag.
"""
from __future__ import annotations

import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from ui.styles import (
    ACCENT, AMBER, BG_CARD, BG_DARK, BG_HOVER, BORDER,
    CARD_RADIUS, GREEN, RED, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)

# ── Feature registry ───────────────────────────────────────────────────────────
# Each entry: group, icon, name, desc, page (nav label or None), requires, tags

_FEATURES: list[dict] = [
    # ── Start here ─────────────────────────────────────────────────────────────
    {
        "group": "Start here",
        "icon": "⊛",
        "name": "Devices",
        "desc": (
            "See every device on your network — names, IPs, MACs, and vendors — "
            "at a glance. Start here to understand what's connected and flag anything "
            "unexpected. Why this matters: you can't secure what you can't see."
        ),
        "page": "Devices",
        "requires": None,
        "tags": ["start", "devices", "network", "inventory", "scan"],
    },
    {
        "group": "Start here",
        "icon": "⊛",
        "name": "Network Grade",
        "desc": (
            "Scores your network A–F across speed, latency, DNS, packet loss, and "
            "device security in under two minutes. Why this matters: gives you a "
            "single number to track improvement over time."
        ),
        "page": "Network Grade",
        "requires": None,
        "tags": ["start", "grade", "score", "health"],
    },
    {
        "group": "Start here",
        "icon": "⊛",
        "name": "What's Wrong?",
        "desc": (
            "One-click root-cause diagnosis — pick a symptom and get a plain-English "
            "verdict with a prioritised fix list. Why this matters: skips hours of "
            "manual troubleshooting and tells you exactly what to do first."
        ),
        "page": "What's Wrong?",
        "requires": None,
        "tags": ["start", "diagnosis", "fix", "troubleshoot", "symptom"],
    },
    {
        "group": "Start here",
        "icon": "⊛",
        "name": "ARP Spoof Watch",
        "desc": (
            "Watches for man-in-the-middle attacks in real time by detecting MAC "
            "address conflicts on your network. Why this matters: this is the most "
            "common active attack on home and small-office networks."
        ),
        "page": "ARP Spoof Watch",
        "requires": "Npcap",
        "tags": ["start", "arp", "security", "attack", "mitm"],
    },
    {
        "group": "Start here",
        "icon": "⊛",
        "name": "Notifications",
        "desc": (
            "Configure alerts so NetSentinel tells you when something is wrong — "
            "by email, webhook, Pushover, ntfy, or Telegram. Why this matters: "
            "the app works 24/7, but you need to hear about problems even when "
            "the window is closed."
        ),
        "page": "Notifications",
        "requires": None,
        "tags": ["start", "alerts", "notify", "email", "webhook"],
    },
    # ── New in this version ────────────────────────────────────────────────────
    {
        "group": "New in this version",
        "icon": "★",
        "name": "Monitor Overview",
        "desc": (
            "Single-glance security posture — one tile per detection monitor. "
            "See what's running, what's clear, and jump to any detail page. "
            "Added in v1.9."
        ),
        "page": "Monitor Overview",
        "requires": None,
        "tags": ["new", "overview", "monitor", "security", "status"],
    },
    {
        "group": "New in this version",
        "icon": "★",
        "name": "Weekly Digest",
        "desc": (
            "Opt-in weekly summary of your network's health, alert history, and "
            "device changes — delivered via your configured notification channel "
            "at a time you choose. Added in v1.9."
        ),
        "page": "Notifications",
        "requires": None,
        "tags": ["new", "weekly", "digest", "summary", "report"],
    },
    {
        "group": "New in this version",
        "icon": "★",
        "name": "Recent Actions (Command Palette)",
        "desc": (
            "The command palette now shows your last 5 actions so you can re-run "
            "them with one click. Open with Ctrl+K or the search bar. Added in v1.9."
        ),
        "page": "Feature Guide",
        "requires": None,
        "tags": ["new", "command palette", "recent", "actions", "quick"],
    },
    # ── Monitoring ─────────────────────────────────────────────────────────────
    {
        "group": "Monitoring",
        "icon": "◈",
        "name": "Overview",
        "desc": (
            "Main cockpit: launch a Quick Network Assessment (M1–M5 bundle) from the "
            "full-width Scan Network bar, then watch tiles update live. Each result tile "
            "shows a last-scanned timestamp and a ↺ re-run button. The Security Scan panel "
            "below the tile grid is open by default — pick individual security tools and "
            "run them directly from here. Collapse it with the header toggle when not needed."
        ),
        "page": "Overview",
        "requires": None,
        "tags": ["dashboard", "tiles", "live", "status", "summary", "overview", "scan", "launch"],
    },
    {
        "group": "Monitoring",
        "icon": "⏺",
        "name": "Network Logger",
        "desc": (
            "Continuously pings your gateway and DNS server, recording RTT, jitter, "
            "DNS latency, HTTP status, and ARP events to CSV. Captures every outage "
            "with exact timestamps. Starts automatically on first launch."
        ),
        "page": "Network Logger",
        "requires": None,
        "tags": ["ping", "log", "csv", "stability", "latency", "outage", "uptime", "jitter", "arp"],
    },
    {
        "group": "Monitoring",
        "icon": "◎",
        "name": "Monitor — Unified Log View",
        "desc": (
            "All log sources in one chronological table. Toggle sources on/off with "
            "the chip bar at the top: Network RTT, 5G Modem signal, Mesh status, "
            "Syslog, and SNMP traps. Enable Modem or Mesh logging to persist signal "
            "history to the database — set the interval (1–60 min) per source. "
            "Search across all sources in real time."
        ),
        "page": "Network Logger",
        "requires": None,
        "tags": ["monitor", "log", "unified", "modem", "mesh", "syslog", "snmp", "signal", "history", "interval"],
    },
    {
        "group": "Monitoring",
        "icon": "◉",
        "name": "Connectivity Tests",
        "desc": (
            "One-click ping, DNS, HTTP, and MTR tests against your gateway and public DNS. "
            "Produces a plain-English verdict: 'Your ISP's DNS is slow' or "
            "'Packet loss at hop 3 — likely an ISP routing issue'."
        ),
        "page": "Connectivity Tests",
        "requires": None,
        "tags": ["ping", "dns", "http", "mtr", "traceroute", "connectivity", "test", "isp"],
    },
    {
        "group": "Monitoring",
        "icon": "▲",
        "name": "Live Bandwidth",
        "desc": (
            "Real-time per-interface download and upload speed with a 60-second rolling chart. "
            "Find out instantly which interface is saturated."
        ),
        "page": "Live Bandwidth",
        "requires": None,
        "tags": ["bandwidth", "speed", "live", "chart", "upload", "download", "interface", "throughput"],
    },
    {
        "group": "Monitoring",
        "icon": "◑",
        "name": "Service Heartbeat",
        "desc": (
            "Monitors the availability of any TCP service (web server, NAS, printer) "
            "and logs downtime with timestamps. Add hosts and ports directly on the page — "
            "no configuration file required."
        ),
        "page": "Service Heartbeat",
        "requires": None,
        "tags": ["service", "tcp", "port", "monitor", "heartbeat", "uptime", "availability", "nas", "server"],
    },
    {
        "group": "Monitoring",
        "icon": "◑",
        "name": "TLS Certificate Monitor",
        "desc": (
            "Tracks HTTPS certificate expiry for any hostname you add — warns you before "
            "certs expire so you never get a surprise browser error. Add hostnames directly "
            "on the page. Checks run hourly."
        ),
        "page": "TLS & Exposure",
        "requires": None,
        "tags": ["tls", "ssl", "cert", "certificate", "https", "expiry", "expire", "security"],
    },
    {
        "group": "Monitoring",
        "icon": "◎",
        "name": "Active Connections",
        "desc": (
            "Process-to-socket map showing every active TCP/UDP connection on this machine "
            "and which application opened it. One-click firewall block per connection."
        ),
        "page": "Active Connections",
        "requires": None,
        "tags": ["connections", "sockets", "tcp", "udp", "process", "firewall", "block", "network", "ports"],
        "badge": "updated", "badge_until": "2026-07-24",
    },
    {
        "group": "Monitoring",
        "icon": "◉",
        "name": "Availability History",
        "desc": (
            "Per-device uptime history showing UP/DEGRADED/DOWN state and RTT charts "
            "across 1h / 12h / 24h / 7d windows. Powered by the Network Logger CSV."
        ),
        "page": "Availability History",
        "requires": None,
        "tags": ["uptime", "history", "availability", "device", "rtt", "chart", "down", "degraded"],
        "badge": "updated", "badge_until": "2026-07-24",
    },
    {
        "group": "Monitoring",
        "icon": "⬡",
        "name": "Mesh & Router",
        "desc": (
            "Pulls live client data directly from your gateway and mesh nodes. "
            "When connected, Deco-assigned device names replace the rDNS hostnames in the "
            "Devices on Network table — these names are far more recognisable than reverse-DNS "
            "guesses. Two extra columns (Node and Band) automatically appear showing which mesh "
            "satellite each device is connected to and its wireless band (2.4G / 5G / 6G / Wired). "
            "Hover the Band cell for real-time upload / download KB/s from the router's own counters. "
            "Save your credentials once and the scan runs silently on every subsequent app start. "
            "TP-Link Deco is fully supported. The worker architecture accepts additional providers "
            "(Eero, Google Nest, Asus ZenWiFi, Netgear Orbi) via a single provider key."
        ),
        "page": "Hardware",
        "requires": None,
        "tags": [
            "mesh", "router", "deco", "tp-link", "gateway", "band", "node", "wifi", "client",
            "hostname", "name", "eero", "google nest", "asus", "orbi", "enrichment", "autorun",
        ],
    },
    {
        "group": "Monitoring",
        "icon": "⊕",
        "name": "Modem",
        "desc": (
            "Live 5G NR and LTE signal metrics polled directly from your WAN modem's local API. "
            "Displays RSRP, SINR, RSRQ, band, PCI, and ARFCN for both the 5G NR and LTE "
            "carriers, plus cell ID, eNB/gNB ID, public IP, and signal bars. "
            "Signal quality is colour-coded (Excellent / Good / Fair / Poor). "
            "A compact signal tile also appears on the Overview dashboard. "
            "Signal metrics are captured automatically at the start of every speed test so "
            "throughput results are permanently tied to the exact cell and signal conditions. "
            "Save credentials once and monitoring resumes silently on every app start. "
            "ZTE MC889 is fully supported; the worker architecture accepts additional modem models "
            "via a single provider key."
        ),
        "page": "Hardware",
        "requires": None,
        "tags": [
            "modem", "5g", "lte", "signal", "rsrp", "sinr", "rsrq", "band", "cell",
            "zte", "mc889", "wan", "endc", "nr5g", "arfcn", "earfcn", "pci", "enb",
            "speedtest", "enrichment", "autorun",
        ],
    },
    # ── Diagnostics ────────────────────────────────────────────────────────────
    {
        "group": "Diagnostics",
        "icon": "◆",
        "name": "Network Grade",
        "desc": (
            "Scores your network A–F across 8 dimensions: speed, latency, DNS, packet loss, "
            "device security, STP health, and more. Each dimension has an actionable fix tip."
        ),
        "page": "Network Grade",
        "requires": None,
        "tags": ["grade", "score", "benchmark", "health", "rating", "A-F", "speed", "latency", "dns"],
    },
    {
        "group": "Diagnostics",
        "icon": "⊟",
        "name": "Network Health Report",
        "desc": (
            "Generates a self-contained HTML report with MTR hop table, outage log, and "
            "network grade. Print to PDF and attach to an ISP support ticket."
        ),
        "page": "Network Health Report",
        "requires": None,
        "tags": ["isp", "report", "pdf", "html", "support", "ticket", "outage", "evidence", "mtr"],
    },
    {
        "group": "Diagnostics",
        "icon": "⊡",
        "name": "Network Timeline",
        "desc": (
            "Reverse-chronological unified event feed — device joins/leaves, fired alerts, "
            "CVE discoveries, and speed tests in a single scrollable view. "
            "Filter by source with one click."
        ),
        "page": None,
        "requires": None,
        "tags": ["timeline", "events", "history", "alerts", "devices", "cve", "feed"],
    },
    {
        "group": "Diagnostics",
        "icon": "◔",
        "name": "DNS & Stability",
        "desc": (
            "Measures DNS resolver latency on every ping cycle and detects micro-outages "
            "as short as one ping interval. Graphs RTT and DNS latency side by side."
        ),
        "page": "DNS & Stability",
        "requires": None,
        "tags": ["dns", "stability", "latency", "rtt", "resolver", "outage", "ping", "graph"],
    },
    {
        "group": "Diagnostics",
        "icon": "⊕",
        "name": "Root-Cause Analyser",
        "desc": (
            "Correlates all scan results and produces a prioritised list of root causes "
            "— so you see 'Your STP reconvergence is causing the DNS failures' instead of "
            "five separate alerts."
        ),
        "page": "What's Wrong?",
        "requires": None,
        "tags": ["diagnose", "root cause", "analysis", "correlate", "why", "problem", "fix", "slow", "dropping"],
    },
    {
        "group": "Diagnostics",
        "icon": "▲",
        "name": "Speed Test",
        "desc": (
            "Measures download and upload speed using Ookla CLI when available, "
            "with a pure-Python fallback requiring no extra dependencies. "
            "When a modem is connected, the signal snapshot (band, RSRP, SINR) captured "
            "at the moment the test ran is shown below the gauge and saved alongside the "
            "result — so every historical entry shows the exact cell conditions it ran under."
        ),
        "page": "Speed Test",
        "requires": None,
        "tags": ["speed", "bandwidth", "download", "upload", "ookla", "mbps", "test", "internet",
                 "signal", "rsrp", "band", "modem", "5g", "lte", "enrichment"],
        "badge": "updated", "badge_until": "2026-07-24",
    },
    {
        "group": "Diagnostics",
        "icon": "◈",
        "name": "WiFi Heatmap",
        "desc": (
            "Visual signal-strength heat map of your Wi-Fi coverage — walk around your "
            "space to record signal at each location and find dead zones."
        ),
        "page": "WiFi Heatmap",
        "requires": None,
        "tags": ["wifi", "wi-fi", "heatmap", "heat", "signal", "coverage", "wireless", "dead zone", "rssi", "strength", "map"],
    },
    {
        "group": "Diagnostics",
        "icon": "◉",
        "name": "WiFi Networks",
        "desc": (
            "Scans visible SSIDs and flags hidden networks, rogue APs, WPS-enabled networks, "
            "and co-channel interference. A 'Connected?' column marks the SSID your machine is "
            "currently on so you can find your network instantly in a crowded list. "
            "When Deco credentials are saved, four band-usage chips appear above the table showing "
            "real client counts per band (2.4 GHz / 5 GHz / 6 GHz / Wired) pulled directly from "
            "the router — more accurate than anything a passive scan can infer."
        ),
        "page": "WiFi Networks",
        "requires": None,
        "tags": [
            "wifi", "wi-fi", "ssid", "wireless", "network", "rogue", "ap", "wps",
            "channel", "interference", "hidden", "band", "connected", "deco", "clients",
        ],
    },
    {
        "group": "Diagnostics",
        "icon": "⊞",
        "name": "Network Map",
        "desc": (
            "Visual topology diagram populated automatically after every scan. "
            "Without mesh data: flat star with Internet → Gateway → all devices, colour-coded by risk level. "
            "With Deco credentials saved: upgrades to a three-tier mesh tree — "
            "Internet → Gateway/Master → Satellite nodes → Client devices grouped under their satellite. "
            "When a modem is connected, a 5G Modem node appears between Internet and Gateway showing "
            "the active band and signal bars, updating every 30 seconds. "
            "Devices not seen by the mesh attach directly to the gateway with a dashed edge."
        ),
        "page": "Network Map",
        "requires": None,
        "tags": [
            "topology", "map", "diagram", "network", "router", "switch", "visual", "layout",
            "mesh", "satellite", "deco", "tier", "tree", "hierarchy", "modem", "5g", "band",
        ],
    },
    {
        "group": "Diagnostics",
        "icon": "→",
        "name": "Hop-by-Hop Trace",
        "desc": (
            "MTR traceroute showing per-hop latency and packet loss to any destination — "
            "identifies exactly where in the internet path problems start."
        ),
        "page": "Hop-by-Hop Trace",
        "requires": None,
        "tags": ["mtr", "traceroute", "tracert", "hop", "latency", "packet loss", "isp", "route"],
    },
    # ── Security ───────────────────────────────────────────────────────────────
    {
        "group": "Security",
        "icon": "⊕",
        "name": "Rogue Device Detection",
        "desc": (
            "Reads the ARP table and flags any device whose MAC vendor is unexpected, "
            "that has no hostname, or that appeared since the last scan. "
            "Right-click a device row for How to Fix, block, or availability history."
        ),
        "page": "Devices",
        "requires": None,
        "tags": ["rogue", "device", "arp", "mac", "unknown", "intruder", "scan", "inventory"],
    },
    {
        "group": "Security",
        "icon": "⊗",
        "name": "Rogue Bridge (STP)",
        "desc": (
            "Captures BPDU frames and alerts when an unexpected switch wins the STP root "
            "election — a common cause of 30–50 second periodic outages on home networks "
            "with mesh Wi-Fi nodes connected via Ethernet."
        ),
        "page": "Rogue Bridge (STP)",
        "requires": "Npcap",
        "tags": ["stp", "bpdu", "bridge", "spanning tree", "root", "switch", "mesh", "outage", "periodic"],
    },
    {
        "group": "Security",
        "icon": "⊙",
        "name": "Broadcast Storm",
        "desc": (
            "Listens for abnormal broadcast traffic and identifies the source device or "
            "Ethernet loop causing a storm. Storm level is shown as SAFE / WARNING / CRITICAL."
        ),
        "page": "Broadcast Storm",
        "requires": "Npcap",
        "tags": ["broadcast", "storm", "flood", "loop", "ethernet", "traffic", "multicast"],
    },
    {
        "group": "Security",
        "icon": "◈",
        "name": "DHCP Lease Scanner",
        "desc": (
            "Detects rogue DHCP servers on your subnet — a device handing out fake gateway "
            "or DNS addresses to silently intercept traffic."
        ),
        "page": "DHCP Leases",
        "requires": None,
        "tags": ["dhcp", "lease", "rogue", "server", "gateway", "dns", "intercept", "mitm"],
        "badge": "updated", "badge_until": "2026-07-24",
    },
    {
        "group": "Security",
        "icon": "◉",
        "name": "ARP Spoof Watch",
        "desc": (
            "Watches ARP traffic in real time and alerts when a MAC address conflict is "
            "detected — a sign of a man-in-the-middle attack in progress."
        ),
        "page": "ARP Spoof Watch",
        "requires": "Npcap",
        "tags": ["arp", "spoof", "mitm", "mac", "conflict", "attack", "intercept", "poison"],
    },
    {
        "group": "Security",
        "icon": "◈",
        "name": "Monitor Overview",
        "desc": (
            "Single-glance security posture — one tile per detection monitor: "
            "ARP Spoof Watch, DHCP Rogue, Broadcast Storm, IoT anomalies, open ports, "
            "and CVE matches. All green means everything is either clear or running. "
            "Click any tile to go straight to that feature's detail page."
        ),
        "page": "Monitor Overview",
        "requires": None,
        "tags": ["overview", "status", "dashboard", "monitor", "arp", "dhcp", "storm", "iot", "cve", "ports", "security"],
        "badge": "updated", "badge_until": "2026-07-24",
    },
    {
        "group": "Security",
        "icon": "⊗",
        "name": "CVE Lookup",
        "desc": (
            "Cross-references discovered OS and service versions against the NVD CVE database "
            "and shows severity, CVSS score, and patch guidance for each match."
        ),
        "page": "CVE Lookup",
        "requires": None,
        "tags": ["cve", "vulnerability", "nvd", "cvss", "exploit", "patch", "security", "version"],
        "badge": "updated", "badge_until": "2026-07-24",
    },
    {
        "group": "Security",
        "icon": "⊙",
        "name": "Security Overview",
        "desc": (
            "Dashboard for the Security Audit section — KPI tiles for threat indicators, "
            "malicious IPs, and blocked domains; top-15 high-confidence findings table; "
            "one-click launch of Scan Network or security tools from one place."
        ),
        "page": "Security Overview",
        "requires": None,
        "tags": ["security", "overview", "dashboard", "threat", "kpi", "audit", "summary"],
    },
    {
        "group": "Security",
        "icon": "◆",
        "name": "Threat Intelligence",
        "desc": (
            "Checks internet-facing IPs from your scan against AbuseIPDB and threat feeds — "
            "flags known malicious hosts and overlays results on the Geolocation Map. "
            "Right-click any row to show the IP on the Geo Map, copy the indicator, or export."
        ),
        "page": "Threat Intel",
        "requires": None,
        "tags": ["threat", "intel", "ip", "abuseipdb", "malicious", "blacklist", "reputation", "geo"],
    },
    {
        "group": "Security",
        "icon": "◑",
        "name": "IoT Behaviour Baseline",
        "desc": (
            "Learns normal traffic patterns for IoT devices and alerts when behaviour "
            "changes — new destination IPs, new ports, or unusual traffic spikes."
        ),
        "page": "IoT Behaviour",
        "requires": "Npcap",
        "tags": ["iot", "baseline", "behaviour", "behavior", "anomaly", "smart home", "traffic", "device"],
    },
    {
        "group": "Security",
        "icon": "◐",
        "name": "802.11 Monitor Mode",
        "desc": (
            "Puts a supported NIC into monitor mode via Npcap and reads raw 802.11 "
            "management frames — beacons, probe requests/responses, auth, association, "
            "and deauth frames.  Purely passive: no packets transmitted.  Useful for "
            "surveying nearby APs and detecting rogue SSIDs or unusual probe activity.  "
            "Falls back silently if the adapter does not support monitor mode."
        ),
        "page": "802.11 Monitor",
        "requires": "Npcap",
        "tags": ["802.11", "wifi", "wireless", "monitor mode", "beacon", "probe", "ssid", "management frame", "passive", "npcap"],
    },
    # ── Learning ───────────────────────────────────────────────────────────────
    {
        "group": "Learning",
        "icon": "▶",
        "name": "Protocol Visualizer",
        "desc": (
            "Animated step-by-step diagrams of ARP, DNS, TCP, DHCP, and STP using "
            "your real device addresses. Each step shows the exact packet contents. "
            "Includes a 'Why this protocol matters' explainer panel."
        ),
        "page": "Protocol Visualizer",
        "requires": None,
        "tags": ["protocol", "animation", "arp", "dns", "tcp", "dhcp", "stp", "diagram", "learn", "visualize", "packet"],
    },
    {
        "group": "Learning",
        "icon": "⬡",
        "name": "Lab Mode",
        "desc": (
            "Guided exercises on your live network: find a rogue device, diagnose slow DNS, "
            "identify a broadcast storm, or map your subnet. Step-by-step with hints, "
            "solutions, and an exportable HTML report."
        ),
        "page": "Lab Mode",
        "requires": None,
        "tags": ["lab", "exercise", "guided", "learn", "scenario", "tutorial", "practice", "rogue", "dns"],
    },
    # ── Extend ─────────────────────────────────────────────────────────────────
    {
        "group": "Extend",
        "icon": "⬡",
        "name": "Hardware Hub",
        "desc": (
            "Live status dashboard for all integrated hardware — routers, modems, APs. "
            "Each imported plugin shows real-time signal metrics, node topology, and "
            "connected clients, with a full detail panel per device. Plugins auto-refresh "
            "every 5 minutes and enrich the Devices table with hostnames and mesh node data. "
            "A built-in guide and template walk you through writing and importing a plugin."
        ),
        "page": "Hardware",
        "requires": None,
        "tags": [
            "hardware", "router", "modem", "ap", "plugin", "script", "python",
            "integrate", "extend", "custom", "api", "community", "contribute",
        ],
    },
    # ── Hidden features ────────────────────────────────────────────────────────
    {
        "group": "Hidden features",
        "icon": "⌨",
        "name": "Quick Search  (Ctrl+K)",
        "desc": (
            "Press Ctrl+K or click the search icon in the nav rail to jump straight to "
            "Feature Guide with the search field focused — find any feature by name, "
            "description, or keyword instantly."
        ),
        "page": "Feature Guide",
        "requires": None,
        "tags": ["search", "ctrl+k", "keyboard", "shortcut", "navigate", "find", "feature guide"],
    },
    {
        "group": "Hidden features",
        "icon": "★",
        "name": "Pin nav items",
        "desc": (
            "Right-click any item in the sidebar flyout to pin it to the top of the nav "
            "for one-click access. Pins persist between sessions."
        ),
        "page": None,
        "requires": None,
        "tags": ["pin", "sidebar", "favourite", "favorite", "shortcut", "nav"],
    },
    {
        "group": "Hidden features",
        "icon": "↗",
        "name": "Device right-click actions",
        "desc": (
            "Right-click any row in the Devices table to access: Port Scan that device, "
            "Show on Geo Map, Check IP (AbuseIPDB), Wake-on-LAN, How to Fix, and Copy IP / MAC."
        ),
        "page": "Devices",
        "requires": None,
        "tags": ["right-click", "context menu", "device", "port scan", "geo map", "abuseipdb", "fix", "wol"],
    },
    {
        "group": "Hidden features",
        "icon": "●",
        "name": "Status bar — click to navigate",
        "desc": (
            "The coloured dots at the bottom-right of the window show live connection "
            "status, device count, last scan time, and logger state. "
            "Click any segment to jump to the relevant page. Hover for a tooltip."
        ),
        "page": None,
        "requires": None,
        "tags": ["status bar", "pulse", "click", "navigate", "indicator", "dot"],
    },
    {
        "group": "Hidden features",
        "icon": "▶",
        "name": "ARP event → Protocol animation",
        "desc": (
            "In Monitor, any Network RTT row with an ARP event shows a clickable "
            "'▶ ARP' button. Clicking jumps to the Protocol Visualizer pre-loaded "
            "with that exact event — real addresses, real timing."
        ),
        "page": "Network Logger",
        "requires": None,
        "tags": ["arp", "log", "animation", "protocol", "event", "jump"],
    },
    {
        "group": "Hidden features",
        "icon": "▸",
        "name": "Explain This panel",
        "desc": (
            "Every detection page (Rogue Device, DNS, STP, Broadcast Storm) has a "
            "'What just happened, technically?' strip at the bottom. Expanding it "
            "explains the protocol involved and links to an animated diagram."
        ),
        "page": None,
        "requires": None,
        "tags": ["explain", "help", "protocol", "educational", "strip", "panel"],
    },
    {
        "group": "Hidden features",
        "icon": "⬡",
        "name": "Live Lab injection",
        "desc": (
            "When the logger detects a new device, slow DNS, or repeated failures, "
            "the Home page shows an amber 'Something just happened' card. "
            "Clicking opens Lab Mode pre-loaded with a one-step exercise built from that real event."
        ),
        "page": "Home",
        "requires": None,
        "tags": ["live", "lab", "inject", "event", "home", "amber", "card", "real-time"],
    },
    # ── Advanced ───────────────────────────────────────────────────────────────
    {
        "group": "Advanced",
        "icon": "🌐",
        "name": "REST API",
        "desc": (
            "Read-only HTTP API (default port 8765) exposing 7 endpoints: /devices, /alerts, "
            "/uptime, /grade, /speed-history, /dashboard, /health. "
            "Use it with Grafana, Home Assistant, custom scripts, or any HTTP client. "
            "Enable and configure in Tools → REST API."
        ),
        "page": "REST API",
        "requires": None,
        "tags": ["api", "rest", "http", "grafana", "home assistant", "json", "endpoint", "script", "dashboard"],
    },
    {
        "group": "Advanced",
        "icon": "⊕",
        "name": "Syslog Receiver",
        "desc": (
            "Listens on UDP 514 for syslog messages from routers, switches, and servers. "
            "Enable the Syslog source toggle in Monitor to view them. "
            "Configure your router to forward syslog to this machine's IP."
        ),
        "page": "Network Logger",
        "requires": None,
        "tags": ["syslog", "udp", "router", "switch", "log", "514", "message"],
    },
    {
        "group": "Advanced",
        "icon": "⊕",
        "name": "SNMP Trap Receiver",
        "desc": (
            "Receives SNMP traps on UDP 162 from managed switches and routers. "
            "Enable the SNMP source toggle in Monitor to view them."
        ),
        "page": "Network Logger",
        "requires": None,
        "tags": ["snmp", "trap", "udp", "162", "managed", "switch", "router", "oid"],
    },
    {
        "group": "Advanced",
        "icon": "⊕",
        "name": "Automation Hooks",
        "desc": (
            "Trigger webhooks or run scripts automatically when network events occur — "
            "device down, high RTT, new device discovered. Built-in templates for Wake-on-LAN and logging."
        ),
        "page": "Automation Hooks",
        "requires": None,
        "tags": ["automation", "webhook", "script", "trigger", "event", "hook", "alert", "wol"],
    },
    {
        "group": "Advanced",
        "icon": "⏱",
        "name": "Scheduled Scans",
        "desc": (
            "Runs automatic network scans on a configurable interval with optional "
            "desktop notifications on completion."
        ),
        "page": "Scheduled Scans",
        "requires": None,
        "tags": ["schedule", "scan", "automatic", "interval", "timer", "periodic"],
    },
    {
        "group": "Advanced",
        "icon": "⊞",
        "name": "MQTT / Home Assistant",
        "desc": (
            "Publishes device events, availability states, and alerts to an MQTT broker. "
            "Supports Home Assistant MQTT Discovery — entities appear automatically with no YAML."
        ),
        "page": "MQTT / Home Assistant",
        "requires": None,
        "tags": ["mqtt", "home assistant", "homeassistant", "broker", "iot", "smart home", "discovery", "entity"],
    },
    {
        "group": "Advanced",
        "icon": "⊞",
        "name": "Geolocation Map",
        "desc": (
            "Plots internet-facing IPs from your scan on an offline world map using "
            "MaxMind GeoLite2 — no API key, no external calls. Threat Intel flags overlaid."
        ),
        "page": "Geolocation Map",
        "requires": None,
        "tags": ["geo", "geolocation", "map", "ip", "location", "world", "maxmind", "country", "city"],
    },
    {
        "group": "Advanced",
        "icon": "▣",
        "name": "Network Documentation",
        "desc": (
            "Auto-generates a self-contained HTML/Markdown network snapshot: device inventory, "
            "open services, topology diagram, and TLS certificate status."
        ),
        "page": "Network Doc",
        "requires": None,
        "tags": ["doc", "documentation", "report", "html", "markdown", "inventory", "snapshot", "export"],
    },
    {
        "group": "Advanced",
        "icon": "⊟",
        "name": "IP & Subnet Calculator",
        "desc": (
            "CIDR notation, subnet mask, broadcast address, and host range calculator "
            "with inline reference panels explaining subnetting and address classes."
        ),
        "page": "IP Calculator",
        "requires": None,
        "tags": ["ip", "subnet", "cidr", "calculator", "mask", "broadcast", "host", "range", "ipv4"],
    },
    {
        "group": "Advanced",
        "icon": "⌂",
        "name": "Tools & Wake-on-LAN",
        "desc": (
            "Network utility tools including Wake-on-LAN (send magic packet by MAC address), "
            "ping sweep, and per-host port check."
        ),
        "page": "Tools & Wake-on-LAN",
        "requires": None,
        "tags": ["wake on lan", "wol", "magic packet", "mac", "tool", "ping", "port check", "sweep"],
    },
    # ── Monitoring (missing entries) ───────────────────────────────────────────
    {
        "group": "Monitoring",
        "icon": "▶",
        "name": "Bandwidth Usage",
        "desc": (
            "Per-interface inbound/outbound bandwidth chart with 60-second rolling window. "
            "Shows the top talkers on each interface and flags unusual spikes. "
            "Useful for diagnosing 'something is eating my bandwidth' symptoms."
        ),
        "page": "Bandwidth Usage",
        "requires": None,
        "tags": ["bandwidth", "interface", "usage", "traffic", "chart", "rolling", "spike"],
    },
    {
        "group": "Monitoring",
        "icon": "⬡",
        "name": "Home Automation Devices",
        "desc": (
            "Scans for smart home devices (Philips Hue, Sonos, Chromecast, Nest, etc.) "
            "using mDNS and SSDP discovery. Lists device type, IP, and manufacturer. "
            "Useful for inventorying IoT devices without logging into each app."
        ),
        "page": "Home Automation",
        "requires": None,
        "tags": ["home automation", "iot", "smart home", "hue", "sonos", "chromecast", "mdns", "ssdp"],
    },
    {
        "group": "Monitoring",
        "icon": "▷",
        "name": "Inventory Changes",
        "desc": (
            "Shows devices that have appeared or disappeared since the last scan. "
            "Compare two scan snapshots to see exactly which MACs joined or left the network. "
            "Useful for tracking unauthorised devices or fleet changes."
        ),
        "page": "Inventory Changes",
        "requires": None,
        "tags": ["inventory", "changes", "new device", "left", "joined", "diff", "snapshot", "mac"],
    },
    {
        "group": "Monitoring",
        "icon": "◑",
        "name": "IPv6 Devices",
        "desc": (
            "Lists all devices responding to IPv6 neighbour discovery on your local network. "
            "Shows link-local and global unicast addresses side-by-side with the IPv4 address "
            "so you can verify dual-stack is working correctly."
        ),
        "page": "IPv6 Devices",
        "requires": None,
        "tags": ["ipv6", "dual stack", "neighbour discovery", "link-local", "unicast", "icmpv6"],
    },
    # ── Security (missing entries) ─────────────────────────────────────────────
    {
        "group": "Security",
        "icon": "◆",
        "name": "CVE Tracker",
        "desc": (
            "Tracks CVE lifecycle for each device across scans — open, mitigated, or resolved. "
            "Filters by severity and device. Stores CVE history in the database so you can "
            "prove remediation progress over time."
        ),
        "page": "CVE Tracker",
        "requires": None,
        "tags": ["cve", "vulnerability", "tracker", "lifecycle", "mitigated", "resolved", "history"],
    },
    {
        "group": "Security",
        "icon": "◈",
        "name": "Cloud Metadata Probe",
        "desc": (
            "Checks whether the AWS, Azure, or GCP Instance Metadata Service (IMDS) is "
            "reachable from this machine — a sign that you are running inside a cloud VM "
            "or that metadata endpoints are unexpectedly exposed."
        ),
        "page": "Cloud Metadata Probe",
        "requires": None,
        "tags": ["cloud", "aws", "azure", "gcp", "imds", "metadata", "exposure", "vm", "instance"],
    },
    {
        "group": "Security",
        "icon": "◆",
        "name": "DHCP Rogue Monitor",
        "desc": (
            "Detects rogue DHCP servers on your network by comparing DHCP offers against "
            "your known gateway. A rogue DHCP server is one of the easiest ways an attacker "
            "can redirect all traffic through a man-in-the-middle device."
        ),
        "page": "DHCP Rogue Monitor",
        "requires": "admin",
        "tags": ["dhcp", "rogue", "server", "mitm", "gateway", "redirect", "offer", "detect"],
    },
    {
        "group": "Security",
        "icon": "▲",
        "name": "Device Risk Score",
        "desc": (
            "Assigns each device a risk score based on open ports, CVEs, weak credentials, "
            "and unexpected services. Ranks devices highest-risk first so you know where to "
            "focus remediation effort."
        ),
        "page": "Device Risk Score",
        "requires": None,
        "tags": ["risk", "score", "device", "rank", "cve", "port", "credential", "remediation"],
    },
    {
        "group": "Security",
        "icon": "◆",
        "name": "Exposed to Internet",
        "desc": (
            "Tests which services on your local devices are reachable from outside your "
            "network by probing common ports from a public vantage point. "
            "Identifies unintentional port forwards and firewall misconfigurations."
        ),
        "page": "Exposed to Internet",
        "requires": None,
        "tags": ["exposed", "internet", "port forward", "firewall", "public", "reachable", "external"],
    },
    {
        "group": "Security",
        "icon": "⊕",
        "name": "Full Device Discovery",
        "desc": (
            "Comprehensive multi-method device enumeration: ARP, mDNS, NetBIOS, SNMP, "
            "and active TCP probes. Finds devices that hide from simple ping sweeps. "
            "Requires admin for SYN-based discovery."
        ),
        "page": "Full Device Discovery",
        "requires": "admin",
        "tags": ["discovery", "scan", "arp", "mdns", "netbios", "snmp", "full", "comprehensive"],
    },
    {
        "group": "Security",
        "icon": "▶",
        "name": "Login Test",
        "desc": (
            "Tests a list of credentials against SSH, SMB, FTP, and Telnet services on "
            "discovered devices. Use it to verify that default credentials have been changed "
            "and that services are not accepting weak passwords."
        ),
        "page": "Login Test",
        "requires": "admin",
        "tags": ["login", "credential", "ssh", "smb", "ftp", "telnet", "default password", "auth test"],
    },
    {
        "group": "Security",
        "icon": "◑",
        "name": "OS Detection",
        "desc": (
            "Fingerprints the operating system of each device using TCP/IP stack analysis "
            "(TTL, window size, options). Shows OS family and version estimate alongside "
            "each device in the scan results."
        ),
        "page": "OS Detection",
        "requires": "admin",
        "tags": ["os", "fingerprint", "detection", "operating system", "ttl", "tcp", "nmap"],
    },
    {
        "group": "Security",
        "icon": "▲",
        "name": "Port Scan (TCP)",
        "desc": (
            "SYN-based TCP port scan across all discovered devices. Shows open ports, "
            "service banners, and flags well-known risky services (Telnet, FTP, RDP, "
            "unauthenticated databases). Requires admin for raw socket access."
        ),
        "page": "Port Scan (TCP)",
        "requires": "admin",
        "tags": ["port scan", "tcp", "syn", "open port", "service", "banner", "telnet", "rdp", "ftp"],
    },
    {
        "group": "Security",
        "icon": "▲",
        "name": "Port Scan (UDP)",
        "desc": (
            "UDP port scan targeting common services (DNS, SNMP, NTP, TFTP). "
            "UDP scans are slower than TCP but find services that do not use TCP — "
            "often overlooked in quick audits."
        ),
        "page": "Port Scan (UDP)",
        "requires": "admin",
        "tags": ["port scan", "udp", "dns", "snmp", "ntp", "tftp", "service", "open port"],
    },
    {
        "group": "Security",
        "icon": "◆",
        "name": "Private Endpoint Check",
        "desc": (
            "Verifies that RFC 1918 private addresses on your network are not accidentally "
            "bridging to the public internet. Detects split-horizon DNS mismatches and "
            "services binding on both private and public interfaces."
        ),
        "page": "Private Endpoint Check",
        "requires": None,
        "tags": ["private", "rfc1918", "endpoint", "exposure", "bridge", "dns", "interface", "public"],
    },
    {
        "group": "Security",
        "icon": "⬡",
        "name": "Recon Plugins",
        "desc": (
            "Runs any installed plugin scripts in security-audit mode. Plugins can add "
            "custom scan logic, vendor-specific checks, or proprietary device probes. "
            "See the Hardware section to install and manage plugins."
        ),
        "page": "Recon Plugins",
        "requires": None,
        "tags": ["plugin", "recon", "custom", "scan", "audit", "extend", "vendor"],
    },
    {
        "group": "Security",
        "icon": "◆",
        "name": "Windows Shares (SMB)",
        "desc": (
            "Enumerates SMB shares on Windows devices — lists share names, access level, "
            "and whether they are accessible without authentication. "
            "Open shares are a common accidental data-exposure vector."
        ),
        "page": "Windows Shares (SMB)",
        "requires": None,
        "tags": ["smb", "windows", "share", "file share", "exposed", "access", "enumerate"],
    },
    # ── Advanced (missing entries) ─────────────────────────────────────────────
    {
        "group": "Advanced",
        "icon": "⊕",
        "name": "Config Snapshots",
        "desc": (
            "Takes a structured snapshot of all scanned devices and compares it against "
            "previous snapshots to show a diff: new devices, removed devices, changed ports "
            "or services. Useful for change-control audits and compliance evidence."
        ),
        "page": "Config Snapshots",
        "requires": None,
        "tags": ["config", "snapshot", "baseline", "diff", "change", "audit", "compliance", "compare"],
    },
    {
        "group": "Advanced",
        "icon": "⊕",
        "name": "Custom Triggers",
        "desc": (
            "Build custom alerting conditions using a visual expression editor — "
            "combine metric thresholds (RTT > 100 ms AND loss > 5%) with boolean logic. "
            "Triggers fire the Automation Hook pipeline when conditions are met."
        ),
        "page": "Custom Triggers",
        "requires": None,
        "tags": ["trigger", "custom", "alert", "expression", "threshold", "logic", "rtt", "loss"],
    },
    {
        "group": "Advanced",
        "icon": "▷",
        "name": "Maintenance Windows",
        "desc": (
            "Schedule time windows during which alerts are suppressed — for planned reboots, "
            "network changes, or overnight batch jobs. Suppression can be per-device or "
            "fleet-wide, and supports recurring schedules."
        ),
        "page": "Maintenance Windows",
        "requires": None,
        "tags": ["maintenance", "window", "suppress", "alert", "schedule", "recurring", "reboot"],
    },
    {
        "group": "Advanced",
        "icon": "◑",
        "name": "SNMP Device Info",
        "desc": (
            "Polls managed switches, routers, and servers via SNMP v1/v2c/v3. "
            "Retrieves interface counters, CPU/memory utilisation, and vendor MIB data. "
            "Configure community strings (stored in the OS keychain) in Settings."
        ),
        "page": "SNMP Device Info",
        "requires": None,
        "tags": ["snmp", "managed", "switch", "router", "mib", "counter", "cpu", "memory", "poll"],
    },
    {
        "group": "Advanced",
        "icon": "▶",
        "name": "Trend Forecasts",
        "desc": (
            "Uses OLS regression over stored RTT, packet loss, and jitter history to predict "
            "when a metric will breach a threshold. Shows 'ETA to degradation' so you can "
            "intervene before users notice a problem."
        ),
        "page": "Trend Forecasts",
        "requires": None,
        "tags": ["trend", "forecast", "predict", "regression", "rtt", "loss", "jitter", "eta", "degrade"],
    },
    # ── Hidden features (missing entries) ─────────────────────────────────────
    {
        "group": "Hidden features",
        "icon": "▸",
        "name": "Help & Reference",
        "desc": (
            "Contextual help panel accessible from the '?' button on every page. "
            "Shows a plain-English explanation of the current page and links to the "
            "relevant protocol or concept. Also contains keyboard shortcut reference."
        ),
        "page": "Help & Reference",
        "requires": None,
        "tags": ["help", "reference", "shortcut", "keyboard", "explain", "documentation", "?"],
    },
]

_GROUPS_ORDER = [
    "Monitoring", "Diagnostics", "Security",
    "Learning", "Hidden features", "Advanced",
]

_REQUIRES_COLOR = {
    "Npcap": AMBER,
    "admin": RED,
}


# ── Widget ─────────────────────────────────────────────────────────────────────

class FeatureGuidePage(QWidget):
    """Searchable index of every NetSentinel feature."""

    navigate_to = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Page header
        hdr = QLabel("Feature Guide")
        hdr.setFixedHeight(32)
        hdr.setStyleSheet(
            f"QLabel {{ background:{BG_DARK}; font-size:15px; font-weight:bold;"
            f" color:{TEXT_PRIMARY}; padding:0 16px; border-bottom:1px solid {BORDER}; }}"
        )
        root.addWidget(hdr)

        # Search bar
        search_row = QHBoxLayout()
        search_row.setContentsMargins(16, 10, 16, 6)
        search_row.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search features, synonyms, page names…")
        self._search.setStyleSheet(
            f"QLineEdit {{ border:1px solid {BORDER}; border-radius:4px;"
            f" padding:4px 10px; font-size:12px; background:{BG_CARD}; color:{TEXT_PRIMARY}; }}"
        )
        self._search.textChanged.connect(self._apply_filter)
        search_row.addWidget(self._search)

        sub = QLabel(f"{len(_FEATURES)} features")
        sub.setStyleSheet(f"font-size:11px; color:{TEXT_MUTED}; background:transparent;")
        search_row.addWidget(sub)
        root.addLayout(search_row)

        # Scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background:{BG_DARK}; border:none; }}")

        self._body = QWidget()
        self._body.setStyleSheet(f"background:{BG_DARK};")
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(16, 8, 16, 16)
        self._body_lay.setSpacing(4)

        scroll.setWidget(self._body)
        root.addWidget(scroll, 1)

        self._render_features(_FEATURES)

    def _render_features(self, features: list[dict]) -> None:
        while self._body_lay.count():
            item = self._body_lay.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        current_group = None
        for feat in features:
            g = feat["group"]
            if g != current_group:
                current_group = g
                grp_lbl = QLabel(g.upper())
                grp_lbl.setStyleSheet(
                    f"font-size:10px; font-weight:bold; color:{TEXT_SECONDARY};"
                    f" background:transparent; letter-spacing:1px; padding-top:10px;"
                )
                self._body_lay.addWidget(grp_lbl)

            card = self._make_card(feat)
            self._body_lay.addWidget(card)

        if not features:
            empty = QLabel("No features match your search.")
            empty.setStyleSheet(f"font-size:12px; color:{TEXT_MUTED}; background:transparent;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._body_lay.addWidget(empty)

        self._body_lay.addStretch()

    def _make_card(self, feat: dict) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        icon_lbl = QLabel(feat["icon"])
        icon_lbl.setFixedWidth(18)
        icon_lbl.setStyleSheet(
            f"font-size:14px; color:{TEXT_PRIMARY}; background:transparent; border:none;"
        )
        lay.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.setContentsMargins(0, 0, 0, 0)

        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        name_lbl = QLabel(feat["name"])
        name_lbl.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        name_row.addWidget(name_lbl)

        if feat.get("requires"):
            req_color = _REQUIRES_COLOR.get(feat["requires"], AMBER)
            req_lbl = QLabel(feat["requires"])
            req_lbl.setStyleSheet(
                f"font-size:9px; font-weight:bold; color:{req_color};"
                f" background:transparent; border:1px solid {req_color};"
                f" border-radius:3px; padding:0 4px;"
            )
            name_row.addWidget(req_lbl)

        badge = feat.get("badge")
        if badge:
            until_str = feat.get("badge_until")
            badge_active = True
            if until_str:
                try:
                    badge_active = datetime.date.today() <= datetime.date.fromisoformat(until_str)
                except ValueError:
                    badge_active = False
            if badge_active:
                badge_color = GREEN if badge == "new" else AMBER
                badge_lbl = QLabel("New" if badge == "new" else "Updated")
                badge_lbl.setStyleSheet(
                    f"font-size:9px; font-weight:bold; color:#fff;"
                    f" background:{badge_color}; border-radius:3px; padding:0 5px;"
                )
                name_row.addWidget(badge_lbl)

        name_row.addStretch()
        text_col.addLayout(name_row)

        desc_lbl = QLabel(feat["desc"])
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        text_col.addWidget(desc_lbl)
        lay.addLayout(text_col, 1)

        if feat.get("page"):
            btn = QPushButton("Open →")
            btn.setFixedHeight(26)
            btn.setFixedWidth(72)
            btn.setStyleSheet(
                f"QPushButton {{ background:transparent; border:1px solid {ACCENT};"
                f" color:{ACCENT}; border-radius:4px; font-size:11px; }}"
                f"QPushButton:hover {{ background:{ACCENT}; color:#FFFFFF; }}"
                f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
            )
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            _page = feat["page"]
            btn.clicked.connect(lambda _=False, p=_page: self.navigate_to.emit(p))
            lay.addWidget(btn)

        return card

    def focus_search(self) -> None:
        self._search.clear()
        self._search.setFocus()

    def _apply_filter(self, text: str) -> None:
        q = text.strip().lower()
        if not q:
            self._render_features(_FEATURES)
            return
        filtered = [
            f for f in _FEATURES
            if q in f["name"].lower()
            or q in f["desc"].lower()
            or q in f.get("group", "").lower()
            or q in (f.get("page") or "").lower()
            or any(q in t.lower() for t in f.get("tags", []))
        ]
        self._render_features(filtered)
