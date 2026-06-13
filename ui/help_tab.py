"""
help_tab.py — build_help_tab() and helper functions for the Help & Reference panel.

Extracted from ui/help.py (Sprint 17) to keep help.py within a manageable size.
The _PAGE_HELP dict remains in ui/help.py.

Usage in dashboard.py:
    from ui.help_tab import build_help_tab
"""
from __future__ import annotations
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
        # Navigation
        ("Ctrl + K",           "Open command palette — fuzzy-search any page or action"),
        ("Ctrl + F",           "Focus sidebar search"),
        ("Escape",             "Close flyout panel / dismiss command palette"),
        # Scanning
        ("Ctrl + R",           "Run full scan"),
        ("Ctrl + E",           "Export last scan results"),
        # Application
        ("Ctrl + Q",           "Quit application"),
        ("F5",                 "Refresh current page"),
        ("Ctrl + Shift + M",   "Visual Diagnostic Overlay (Matrix mode)"),
        # Tables & rows
        ("Right-click row",    "Context menu: Copy IP / Copy MAC / How to Fix / Port Scan / WoL"),
        ("Click column header","Sort table by that column"),
        # macOS equivalents
        ("⌘ + K",             "Command palette (macOS)"),
        ("⌘ + R",             "Run full scan (macOS)"),
        ("⌘ + E",             "Export (macOS)"),
        ("⌘ + Q",             "Quit (macOS)"),
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
        ("CVE Lookup",            "NVD API v2 CVE lookup for detected software/services"),
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
        ("Classification confidence indicators", "The Type column in the Devices table now shows a confidence indicator: ★ user override (blue), ● high confidence (green), ◑ medium (amber), ○ low/unknown (grey). Hover for the exact confidence percentage."),
        ("Override Device Type", "Right-click any device in the snapshot table and choose 'Override Device Type…' to permanently pin a device to any type. Your correction survives all future enrichment runs. Clear it any time via the same menu or the device drawer."),
        ("Classification section in device drawer", "Click a device row to open the detail drawer — a new Classification section at the top shows the current type, evidence used (OUI, hostname, passive observation), confidence level, and a Clear Override button when an override is active."),
        ("Network segment grouping", "Devices are automatically grouped into colour-coded /24 subnets. Use the pill filter bar above the Devices table to filter by segment, and right-click a pill to rename or recolour it."),
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
        ("…check if a device is hacked",          "Device Risk Score + CVE Lookup (Security Audit section)"),
        ("…monitor uptime of my servers",         "Service Heartbeat → add hosts + ports to watch"),
        ("…see all open ports on a device",       "Tools & Wake-on-LAN → TCP Port Scan (Advanced section)"),
        ("…detect ARP spoofing / MITM attack",    "ARP Spoof Watch (Advanced section)"),
        ("…see who is using the most bandwidth",  "Bandwidth Usage (Advanced section)"),
        ("…check TLS certificate expiry",         "TLS & Exposure (Security Audit section)"),
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
