"""
nav/labels.py — the canonical nav label registry (P1).

Every user-visible page label and rail-section name lives here exactly once, as
a ``StrEnum`` member.  This is the single source of truth that both the nav
*registration* (``_build_pro_nav`` via ``_nav_add_rail_item``) and every nav
*consumer* (``_nav_rail_go_to``, ``_nav_set_scan_state``,
``navigate_requested.emit``, ``_AUDIT_SCAN_LABELS``, ``_FRESH_SECONDS`` …) import.

WHY THIS EXISTS — the bug class it kills:
The nav routes pages by string label.  A caller that passes a typo'd literal
(``_nav_rail_go_to("Threat Intell")``) does not raise — it silently no-ops,
producing a dead navigation with no type error and no test failure (RULE-NAV3,
RULE-NAV-RENAME).  Referencing ``NavLabel.THREAT_INTEL`` instead turns every
typo into an ``AttributeError`` at import time, and a rename becomes a one-line
value change that every call site inherits automatically.

``StrEnum`` members ARE ``str`` instances, so they are drop-in wherever a label
string is used today: QSettings values, JSON persistence (``scan_registry/state``),
``_nav_label_to_widget`` dict keys, and f-strings (breadcrumb) all behave
identically to the bare string.

INVARIANT (enforced by tests/test_nav_label_registry.py):
``set(NavLabel)`` must equal the set of labels registered in ``_build_pro_nav``.
Add a page there → add its member here (and vice-versa).  Dynamic plugin pages
(``_pg._label``) are the one exception — they are registered at runtime and have
no static member.
"""
from __future__ import annotations

from enum import StrEnum


class NavLabel(StrEnum):
    """Canonical page labels. Member value == the exact nav item label string."""

    # ── Getting Started ────────────────────────────────────────────────────────
    HOME = "Home"
    DASHBOARD = "Dashboard"
    SPEED_TEST = "Speed Test"
    DNS_STABILITY = "DNS & Stability"
    WHATS_WRONG = "What's Wrong?"
    TROUBLESHOOT = "Troubleshoot"

    # ── Discover ───────────────────────────────────────────────────────────────
    DEVICES = "Devices"
    NETWORK_MAP = "Network Map"
    WIFI_NETWORKS = "WiFi Networks"
    WIFI_HEATMAP = "WiFi Heatmap"
    DHCP_LEASES = "DHCP Leases"
    DNS_ZONE_MAP = "DNS Zone Map"
    HOME_AUTOMATION = "Home Automation"

    # ── Monitor ────────────────────────────────────────────────────────────────
    NETWORK_LOGGER = "Network Logger"
    LIVE_BANDWIDTH = "Live Bandwidth"
    APP_TRAFFIC = "App Traffic"
    ACTIVE_CONNECTIONS = "Active Connections"
    SYSLOG_VIEWER = "Syslog Viewer"
    SNMP_TRAP_RECEIVER = "SNMP Trap Receiver"
    MONITOR_STATUS = "Monitor Status"
    NETWORK_TIMELINE = "Network Timeline"
    AVAILABILITY_HISTORY = "Availability History"
    INVENTORY_CHANGES = "Inventory Changes"
    BANDWIDTH_USAGE = "Bandwidth Usage"
    SERVICE_HEARTBEAT = "Service Heartbeat"
    IPV6_DEVICES = "IPv6 Devices"
    UPTIME_SLA = "Uptime & SLA"

    # ── Reports ────────────────────────────────────────────────────────────────
    NETWORK_GRADE = "Network Grade"
    NETWORK_HEALTH_REPORT = "Network Health Report"
    NETWORK_DOC = "Network Doc"
    IP_CALCULATOR = "IP Calculator"
    NOTIFICATIONS = "Notifications"

    # ── Analysis ───────────────────────────────────────────────────────────────
    BROADCAST_STORM = "Broadcast Storm"
    ROGUE_BRIDGE_STP = "Rogue Bridge (STP)"
    IOT_BEHAVIOUR = "IoT Behaviour"
    MONITOR_802_11 = "802.11 Monitor"
    ARP_SPOOF_WATCH = "ARP Spoof Watch"
    HOP_BY_HOP_TRACE = "Hop-by-Hop Trace"
    SNMP_DEVICE_INFO = "SNMP Device Info"
    TOOLS_WOL = "Tools & Wake-on-LAN"
    PORT_SCANNER = "Port Scanner"
    GEOLOCATION_MAP = "Geolocation Map"
    TREND_FORECASTS = "Trend Forecasts"
    SERVICE_DIAGNOSTICS = "Service Diagnostics"
    ROOT_CAUSE_CORRELATOR = "Root Cause Correlator"

    # ── Automation ─────────────────────────────────────────────────────────────
    AUTOMATION_HOOKS = "Automation Hooks"
    SCHEDULED_SCANS = "Scheduled Scans"
    CUSTOM_TRIGGERS = "Custom Triggers"
    MQTT_HOME_ASSISTANT = "MQTT / Home Assistant"
    REST_API = "REST API"
    CONFIG_SNAPSHOTS = "Config Snapshots"
    MAINTENANCE_WINDOWS = "Maintenance Windows"

    # ── Security Audit ─────────────────────────────────────────────────────────
    SECURITY_OVERVIEW = "Security Overview"
    PORT_SCAN_TCP = "Port Scan (TCP)"
    PORT_SCAN_UDP = "Port Scan (UDP)"
    CVE_LOOKUP = "CVE Lookup"
    THREAT_INTEL = "Threat Intel"
    TLS_EXPOSURE = "TLS & Exposure"
    LOGIN_TEST = "Login Test"
    OS_DETECTION = "OS Detection"
    DEVICE_RISK_SCORE = "Device Risk Score"
    CVE_TRACKER = "CVE Tracker"
    EXPOSED_TO_INTERNET = "Exposed to Internet"
    FULL_DEVICE_DISCOVERY = "Full Device Discovery"
    WINDOWS_SHARES_SMB = "Windows Shares (SMB)"
    RECON_PLUGINS = "Recon Plugins"
    PRIVATE_ENDPOINT_CHECK = "Private Endpoint Check"
    CLOUD_METADATA_PROBE = "Cloud Metadata Probe"
    DHCP_ROGUE_MONITOR = "DHCP Rogue Monitor"

    # ── Education ──────────────────────────────────────────────────────────────
    PROTOCOL_VISUALIZER = "Protocol Visualizer"
    LAB_MODE = "Lab Mode"
    FEATURE_GUIDE = "Feature Guide"
    HELP_REFERENCE = "Help & Reference"

    # ── Extend ─────────────────────────────────────────────────────────────────
    HARDWARE = "Hardware"


class NavSection(StrEnum):
    """Canonical rail-section names (the argument to ``_nav_begin_section``)."""

    GETTING_STARTED = "Getting Started"
    DISCOVER = "Discover"
    MONITOR = "Monitor"
    REPORTS = "Reports"
    ANALYSIS = "Analysis"
    AUTOMATION = "Automation"
    SECURITY_AUDIT = "Security Audit"
    EDUCATION = "Education"
    EXTEND = "Extend"


#: Labels that are valid navigation targets but intentionally have NO registered
#: stacked page, so they never appear in ``_nav_label_to_widget``:
#:   • "Settings" opens a modal dialog (Dashboard._open_settings_dialog), not a
#:     page.  Some call sites still emit it via ``navigate_to``; the runtime guard
#:     and the static literal-validation test treat it as known, not dead nav.
#: Keep this set as small as possible — every entry is a route that silently
#: no-ops rather than showing a page.
SPECIAL_LABELS: frozenset[str] = frozenset({"Settings"})

#: Every statically-registered page label, for O(1) membership checks in the
#: runtime guard and the registry-parity test.  Plugin pages are excluded (they
#: are registered dynamically and have no static member).
ALL_LABELS: frozenset[str] = frozenset(NavLabel)
ALL_SECTIONS: frozenset[str] = frozenset(NavSection)

#: Union of everything a nav-label literal is allowed to be (registry + specials).
KNOWN_LABELS: frozenset[str] = ALL_LABELS | SPECIAL_LABELS

__all__ = [
    "NavLabel", "NavSection",
    "SPECIAL_LABELS", "ALL_LABELS", "ALL_SECTIONS", "KNOWN_LABELS",
]
