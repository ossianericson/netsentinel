"""
Feature Guide page — searchable index of every NetSentinel feature.

Gives users a single place to discover what the app can do, understand each
feature in one sentence, and navigate directly to it.  Grouped by theme;
filterable by name, description, group, page label, or synonym tag.
"""
from __future__ import annotations

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
    # ── Monitoring ─────────────────────────────────────────────────────────────
    {
        "group": "Monitoring",
        "icon": "◈",
        "name": "Overview",
        "desc": (
            "Main cockpit: launch a Quick Network Assessment (M1–M5 bundle) from the "
            "full-width Scan Network bar, then watch tiles update live. Each result tile "
            "shows a last-scanned timestamp and a ↺ re-run button. A collapsible Security "
            "Scan panel below the grid lets you select and open individual security tools."
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
        "requires": "Npcap",
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
    },
    {
        "group": "Monitoring",
        "icon": "⬡",
        "name": "Mesh & Router",
        "desc": (
            "Live client list from your gateway and mesh nodes — shows which node each "
            "device is connected to, the wireless band (2.4G / 5G / 6G / Wired), and "
            "real-time upload / download rates. Results enrich the Devices on Network table. "
            "TP-Link Deco supported; Eero, Google Nest, Asus ZenWiFi planned."
        ),
        "page": "Mesh & Router",
        "requires": None,
        "tags": ["mesh", "router", "deco", "tp-link", "gateway", "band", "node", "wifi", "client"],
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
        "name": "ISP Report",
        "desc": (
            "Generates a professional, self-contained HTML report with MTR hop table, "
            "outage log, and network grade. Print to PDF and attach to an ISP support ticket."
        ),
        "page": "ISP Report",
        "requires": None,
        "tags": ["isp", "report", "pdf", "html", "support", "ticket", "outage", "evidence", "mtr"],
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
        "page": "Diagnose",
        "requires": None,
        "tags": ["diagnose", "root cause", "analysis", "correlate", "why", "problem", "fix", "slow", "dropping"],
    },
    {
        "group": "Diagnostics",
        "icon": "▲",
        "name": "Speed Test",
        "desc": (
            "Measures download and upload speed using Ookla CLI when available, "
            "with a pure-Python fallback requiring no extra dependencies. History is charted."
        ),
        "page": "Speed Test",
        "requires": None,
        "tags": ["speed", "bandwidth", "download", "upload", "ookla", "mbps", "test", "internet"],
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
            "and co-channel interference."
        ),
        "page": "WiFi Networks",
        "requires": None,
        "tags": ["wifi", "wi-fi", "ssid", "wireless", "network", "rogue", "ap", "wps", "channel", "interference", "hidden"],
    },
    {
        "group": "Diagnostics",
        "icon": "⊞",
        "name": "Network Map",
        "desc": (
            "Interactive topology diagram showing device relationships — routers, switches, "
            "and endpoints — populated automatically after a full scan."
        ),
        "page": "Network Map",
        "requires": None,
        "tags": ["topology", "map", "diagram", "network", "router", "switch", "visual", "layout"],
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
        "icon": "⊗",
        "name": "CVE Lookup",
        "desc": (
            "Cross-references discovered OS and service versions against the NVD CVE database "
            "and shows severity, CVSS score, and patch guidance for each match."
        ),
        "page": "CVE Lookup",
        "requires": None,
        "tags": ["cve", "vulnerability", "nvd", "cvss", "exploit", "patch", "security", "version"],
    },
    {
        "group": "Security",
        "icon": "◆",
        "name": "Threat Intelligence",
        "desc": (
            "Checks internet-facing IPs from your scan against AbuseIPDB and threat feeds — "
            "flags known malicious hosts and overlays results on the Geolocation Map."
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
            "Right-click any row in the Devices table to access: How to Fix (plain-English "
            "remediation), block from network, view availability history, and more."
        ),
        "page": "Devices",
        "requires": None,
        "tags": ["right-click", "context menu", "device", "fix", "block", "remediation"],
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
            "In Logs → Network Log, any row with an ARP event shows a clickable "
            "'▶ ARP' button. Clicking jumps to the Protocol Visualizer pre-loaded "
            "with that exact event — real addresses, real timing."
        ),
        "page": "Logs",
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
            "View in Logs → Syslog tab. Configure your router to forward syslog to this machine's IP."
        ),
        "page": "Syslog Viewer",
        "requires": None,
        "tags": ["syslog", "udp", "router", "switch", "log", "514", "message"],
    },
    {
        "group": "Advanced",
        "icon": "⊕",
        "name": "SNMP Trap Receiver",
        "desc": (
            "Receives SNMP traps on UDP 162 from managed switches and routers. "
            "View in Logs → SNMP Traps tab."
        ),
        "page": "SNMP Trap Receiver",
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
