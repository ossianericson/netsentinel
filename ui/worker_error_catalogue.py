"""The fixed message behind every worker-error label (S5, RULE-A2 / D5).

A worker's ``error`` signal carries only a ``str`` (S3.2). For most scan workers the exception
was already flattened to text inside ``modules/`` (``result.error``, ``on_error(...)``) or in a
child process (the STP and storm scans) before the worker saw it, and Windows localizes that
text — so nothing here may be chosen by reading it. Each site instead names its entry, and
``ui/error_display.py::show_worker_error`` shows ``⚠ what. why next_step`` with the raw string
kept as tooltip, Copy action and app-log detail.

What an entry may claim: ``why`` lists the causes that site's producer can actually raise,
read from its code — not a diagnosis of this particular failure. Where only an unexpected
error reaches the signal (the worker's catch-all ``except``), it says so rather than guessing.

**An exception in hand (S6).** Where a site caught the exception itself, ``explains`` names the
``modules/error_text`` kinds whose structural diagnosis replaces this entry's why/next — the
entry's own text stays the fallback for everything else. Opt in only to kinds whose wording is
right at that site (``FILE_KINDS`` for a save).

``tests/test_worker_error_catalogue.py`` holds the fixed wording to 140 visible characters (most
of these labels do not wrap) and an explained message to 220, checks every ``explains`` kind is
real, resolves every site's reference statically, and fails on an entry no site uses. The syslog and SNMP trap pages do not appear here: they reuse their app-health
condition text (``modules/app_health_catalogue.py``) so the page and the Home strip agree.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet

# Every entry is listed: CodeQL counts a global as used only by same-module reads or __all__
# (RULE-LINT6), and sites read these as WE.<NAME> from other files.
__all__ = [
    "WorkerErrorSpec", "ALL", "FILE_KINDS",
    "NETWORK_INFO", "DIAGNOSTICS",
    "DEVICES", "STP", "BROADCAST_STORM", "WIFI_NETWORKS", "DNS_PING",
    "ARP_WATCH", "DHCP_WATCH", "BANDWIDTH", "SNMP_POLL", "SNMP_INTERFACES", "SCHEDULED_SCANS",
    "NETWORK_LOGGER",
    "IPV6", "CLOUD_METADATA", "PORT_SCANNER", "CONNECTIONS", "HA_SCAN", "MAC_LOOKUP",
    "DHCP_LEASES", "DNS_ZONE", "GEOLITE_DOWNLOAD",
    "PORT_SCAN_TCP", "PORT_SCAN_UDP", "OS_DETECTION", "EXPOSED_TO_INTERNET", "LOGIN_TEST",
    "FULL_DEVICE_DISCOVERY", "WINDOWS_SHARES", "PRIVATE_ENDPOINT",
    "PRESCAN", "BASELINE_SNAPSHOT", "ISP_QUICK_TEST", "SERVICE_DIAGNOSTICS", "SPEED_TEST",
    "DNS_BENCHMARK", "TREND_ANALYSIS", "NETWORK_DOC", "TRAFFIC_OVERLAY", "LIVE_PROTOCOL",
    "WIFI_MONITOR", "WIFI_HEATMAP_SCAN", "THREAT_FEED_REFRESH", "ABUSEIPDB_LOOKUP", "HARDWARE_DETECT",
    "COMMUNITY_INDEX", "COMMUNITY_DOWNLOAD", "PLUGIN_REGISTRY",
    "EXPORT_BASELINE_DIFF", "EXPORT_CVE_CSV", "EXPORT_DIAGNOSIS_REPORT", "EXPORT_INVENTORY_EVENTS",
    "EXPORT_INVENTORY_COMPARISON", "EXPORT_INVENTORY_SELECTION", "EXPORT_MAP_IMAGE",
    "EXPORT_MAP_SHARE", "EXPORT_ALERT_HISTORY",
    "EXPORT_ALL_DATA", "EXPORT_LOG_VIEW", "EXPORT_LOG_RANGE", "EXPORT_PDF_REPORT", "PDF_NO_ENGINE",
    "EXPORT_ISP_REPORT", "PLUGIN_TEMPLATE",
    "COPY_NETWORK_SUMMARY", "COPY_GRADE_CARD", "COPY_ISP_COMPLAINT", "COPY_ISP_FORUM_POST",
    "AUTO_REPORT", "EXPORT_REPORT", "SCAN_STARTUP", "TOPOLOGY_RENDER", "DEVICE_FILTER", "BASELINE_CHECK",
    "LOG_CHART", "LOG_ANALYSIS", "ROOT_CAUSE", "IOT_LEARN", "IOT_MONITOR", "IOT_LEARN_RUN",
    "IOT_MONITOR_RUN", "NETWORK_GRADE", "RISK_SCORE",
    "UPDATE_CHECK", "HA_LOAD", "HA_SAVE", "HA_ADD",
    "PLUGIN_CATALOGUE_INSTALL", "PLUGIN_REGISTER", "PLUGIN_BUNDLE_IMPORT", "PLUGIN_ERROR",
    "PLUGIN_CONNECTION_TEST",
    "HEATMAP_FLOOR_PLAN", "HEATMAP_SURVEY_LOAD", "HEATMAP_SURVEY_SAVE", "EXPORT_HEATMAP_IMAGE",
    "TOPOLOGY_SNAPSHOT",
    "LIVE_BANDWIDTH", "APP_TRAFFIC", "SPEED_SERVER_LIST", "ABUSEIPDB_NOT_TESTABLE",
]


@dataclass(frozen=True)
class WorkerErrorSpec:
    """``key`` names the site's logger (``netsentinel.worker_error.<key>``); the rest is for people."""

    key: str
    what: str
    why: str
    next_step: str
    #: ``modules/error_text`` kinds that may replace why/next when the site passes the exception.
    explains: FrozenSet[str] = frozenset()


_PACKET_CAPTURE = "It needs Npcap installed and NetSentinel running as administrator."

# ── Dashboard ────────────────────────────────────────────────────────────────

NETWORK_INFO = WorkerErrorSpec(
    "network_info", "Network details could not be read",
    "Reading the adapter, gateway or DHCP settings failed.",
    "Refresh to try again.",
)
DIAGNOSTICS = WorkerErrorSpec(
    "diagnostics", "Diagnostics did not finish",
    "One of the health checks hit an unexpected error.",
    "Run diagnostics again.",
)

# ── Scan modules 1–5 (plugin_page_mixin) ─────────────────────────────────────

DEVICES = WorkerErrorSpec(
    "devices", "The device scan failed",
    "Reading the ARP table or identifying devices hit an error.",
    "Run the scan again.",
)
STP = WorkerErrorSpec(
    "stp", "The STP check could not run", _PACKET_CAPTURE, "Check both, then scan again.",
)
BROADCAST_STORM = WorkerErrorSpec(
    "broadcast_storm", "The broadcast storm check could not run", _PACKET_CAPTURE,
    "Check both, then scan again.",
)
WIFI_NETWORKS = WorkerErrorSpec(
    "wifi_networks", "The Wi-Fi scan failed",
    "Windows did not return nearby networks. Wi-Fi may be off or missing.",
    "Turn Wi-Fi on, then scan again.",
)
DNS_PING = WorkerErrorSpec(
    "dns_ping", "The ping and DNS check failed",
    "Measuring ping or DNS response times hit an error.",
    "Run the scan again.",
)

# ── Monitors ─────────────────────────────────────────────────────────────────

ARP_WATCH = WorkerErrorSpec(
    "arp_watch", "ARP Spoof Watch could not run", _PACKET_CAPTURE, "Check both, then start it again.",
)
DHCP_WATCH = WorkerErrorSpec(
    "dhcp_watch", "Rogue DHCP detection could not run", _PACKET_CAPTURE,
    "Check both, then start it again.",
)
BANDWIDTH = WorkerErrorSpec(
    "bandwidth", "Bandwidth monitoring could not run", _PACKET_CAPTURE,
    "Check both, then start it again.",
)
SNMP_POLL = WorkerErrorSpec(
    "snmp_poll", "The SNMP poll failed",
    "The query hit an error before any device answered.",
    "Check the community string, then poll again.",
)
SNMP_INTERFACES = WorkerErrorSpec(
    "snmp_interfaces", "The interface error poll failed",
    "The device did not answer SNMP, or the query hit an error.",
    "Check the host and community string.",
)
SCHEDULED_SCANS = WorkerErrorSpec(
    "scheduled_scans", "Scheduled scanning stopped",
    "A scheduled device scan hit an unexpected error.",
    "Start the scheduler again.",
)
NETWORK_LOGGER = WorkerErrorSpec(
    # The ping loop runs on its own thread and never reaches this signal; only
    # NetworkLogger.start() creating the CSV under Documents does.
    "network_logger", "The Network Logger stopped",
    "Its log file in Documents could not be created.",
    "Check that Documents is writable, then start it again.",
)

# ── Analysis and diagnostics tools ───────────────────────────────────────────

IPV6 = WorkerErrorSpec(
    "ipv6", "The IPv6 scan failed",
    "Reading the IPv6 neighbour table or pinging hit an error.",
    "Run it again.",
)
CLOUD_METADATA = WorkerErrorSpec(
    "cloud_metadata", "The cloud metadata probe failed",
    "Probing the metadata addresses hit an unexpected error.",
    "Run it again.",
)
PORT_SCANNER = WorkerErrorSpec(
    "port_scanner", "The port scan failed",
    "Connecting to the host's ports hit an unexpected error.",
    "Check the host, then scan again.",
)
CONNECTIONS = WorkerErrorSpec(
    "connections", "Active connections could not be listed",
    "Windows refused or failed the connection query.",
    "Refresh, or run NetSentinel as administrator.",
)
HA_SCAN = WorkerErrorSpec(
    "ha_scan", "The home automation scan failed",
    "Probing devices for home automation services hit an error.",
    "Run the scan again.",
)
MAC_LOOKUP = WorkerErrorSpec(
    "mac_lookup", "The online vendor lookup failed",
    "The lookup hit an unexpected error.",
    "Try again in a moment.",
)
DHCP_LEASES = WorkerErrorSpec(
    "dhcp_leases", "The DHCP lease scan failed",
    "Lease data could not be read. It may need administrator rights.",
    "Check the adapter is up, then refresh.",
)
DNS_ZONE = WorkerErrorSpec(
    "dns_zone", "The DNS zone scan failed",
    "The server may refuse zone transfers, or mDNS was blocked.",
    "Check the server and domain, then scan again.",
)
GEOLITE_DOWNLOAD = WorkerErrorSpec(
    "geolite_download", "The GeoLite2 download failed",
    "The server was unreachable, or the download link was rejected.",
    "Check your connection and the link.",
)

# ── Security Audit ───────────────────────────────────────────────────────────

PORT_SCAN_TCP = WorkerErrorSpec(
    "port_scan_tcp", "Port Scan (TCP) could not run",
    "It needs Npcap, administrator rights and a host name that resolves.",
    "Check those, then scan again.",
)
PORT_SCAN_UDP = WorkerErrorSpec(
    "port_scan_udp", "Port Scan (UDP) could not run",
    "It needs Npcap, administrator rights and a host name that resolves.",
    "Check those, then scan again.",
)
OS_DETECTION = WorkerErrorSpec(
    "os_detection", "OS detection failed",
    "Probing the hosts hit an unexpected error.",
    "Run it again.",
)
EXPOSED_TO_INTERNET = WorkerErrorSpec(
    "exposed_to_internet", "The internet exposure check failed",
    "UPnP router discovery or the public IP lookup failed.",
    "Check your connection, then run it again.",
)
LOGIN_TEST = WorkerErrorSpec(
    "login_test", "The login test failed",
    "SSH refused the login or timed out, or no SSH client is available.",
    "Check host, port, user name and password.",
)
FULL_DEVICE_DISCOVERY = WorkerErrorSpec(
    "full_device_discovery", "Full device discovery failed",
    "The address range may be invalid, or the sweep hit an error.",
    "Check the range, then run it again.",
)
WINDOWS_SHARES = WorkerErrorSpec(
    "windows_shares", "Windows share enumeration failed",
    "The host refused the connection or login, or SMB is blocked.",
    "Check host and credentials, then retry.",
)
PRIVATE_ENDPOINT = WorkerErrorSpec(
    "private_endpoint", "The private endpoint check failed",
    "Checking the endpoints hit an unexpected error.",
    "Run it again.",
)

# ── Remaining worker-error slots (S6.3a) ─────────────────────────────────────

PRESCAN = WorkerErrorSpec(
    # flush_network_caches → get_local_ip → ping_sweep_subnet; only an exception reaches the signal.
    "prescan", "The pre-scan failed",
    "Finding or pinging the local network failed. The adapter may be down.",
    "Check your connection, then scan again.",
)
BASELINE_SNAPSHOT = WorkerErrorSpec(
    "baseline_snapshot", "The snapshot could not be taken",
    "Discovering devices on the network hit an unexpected error.",
    "Check your connection, then take it again.",
)
ISP_QUICK_TEST = WorkerErrorSpec(
    "isp_quick_test", "The quick test could not run",
    "Pinging your router or the internet hit an unexpected error.",
    "Run the quick test again.",
)
SERVICE_DIAGNOSTICS = WorkerErrorSpec(
    # "No service selected." or DiagnosticEngine raising; a failing service is a result, not an error.
    "service_diagnostics", "Service diagnostics did not finish",
    "No service was selected, or a check hit an unexpected error.",
    "Pick a service and run it again.",
)
SPEED_TEST = WorkerErrorSpec(
    # All three backends failed; the last (pure-Python HTTP) raises when no server answers.
    "speed_test", "The speed test failed",
    "No test server answered. The internet may be down or a firewall blocking it.",
    "Check your connection and retry.",
)
DNS_BENCHMARK = WorkerErrorSpec(
    "dns_benchmark", "The DNS benchmark failed",
    "Querying the DNS servers hit an unexpected error.",
    "Run it again.",
)
TREND_ANALYSIS = WorkerErrorSpec(
    "trend_analysis", "Trend analysis failed",
    "Reading history from the database or fitting the trends hit an unexpected error.",
    "Run the analysis again.",
)
NETWORK_DOC = WorkerErrorSpec(
    # generate_network_doc renders the HTML and writes it under the app-data reports folder.
    "network_doc", "The network document could not be generated",
    "Building it or writing it to the reports folder failed.",
    "Try again.",
)
TRAFFIC_OVERLAY = WorkerErrorSpec(
    "traffic_overlay", "Traffic Overlay could not start", _PACKET_CAPTURE,
    "Check both, then turn it on again.",
)
LIVE_PROTOCOL = WorkerErrorSpec(
    # Admin and Npcap are checked first; this is Scapy missing or the sniffer refusing to start.
    "live_protocol", "Live capture could not start", _PACKET_CAPTURE, "Check both, then try again.",
)
WIFI_MONITOR = WorkerErrorSpec(
    # No wireless interface, Scapy missing, or sniff() refusing monitor mode on the adapter.
    "wifi_monitor", "802.11 capture could not start",
    "It needs Npcap with raw 802.11 support and a Wi-Fi adapter that allows it.",
    "Check both, then start again.",
)
WIFI_HEATMAP_SCAN = WorkerErrorSpec(
    "wifi_heatmap_scan", "The Wi-Fi sample could not be taken",
    "Reading nearby networks hit an unexpected error.",
    "Check Wi-Fi is on, then add the sample again.",
)
THREAT_FEED_REFRESH = WorkerErrorSpec(
    # refresh_from_feeds returns [] when every feed fails, so only an unexpected error lands here.
    "threat_feed_refresh", "The threat feeds could not be updated",
    "Downloading or saving the feeds hit an unexpected error.",
    "Try again later.",
)
ABUSEIPDB_LOOKUP = WorkerErrorSpec(
    # lookup_abuseipdb turns every request failure into "could not test"; this is anything else.
    "abuseipdb_lookup", "The AbuseIPDB lookup failed", "The lookup hit an unexpected error.", "Try again.",
)
HARDWARE_DETECT = WorkerErrorSpec(
    "hardware_detect", "Hardware auto-detection failed",
    "Probing your router for known hardware hit an unexpected error.",
    "You can still add hardware manually.",
)
COMMUNITY_INDEX = WorkerErrorSpec(
    "community_index", "The community plugin index is unavailable",
    "It could not be downloaded, or the index was not valid.",
    "Check your connection, or try later.",
)
COMMUNITY_DOWNLOAD = WorkerErrorSpec(
    "community_download", "The plugin could not be downloaded",
    "The download failed, or the file did not match its published checksum.",
    "Try again later.",
)
PLUGIN_REGISTRY = WorkerErrorSpec(
    "plugin_registry", "The plugin registry could not be loaded",
    "It could not be downloaded, or the registry was not valid.",
    "Check your connection, then refresh.",
)

# ── Saving files (S6) ────────────────────────────────────────────────────────
#
# Shown by ``export_failed`` (toast) or ``show_error_dialog``. The why/next below is the fallback
# for a cause ``error_text`` cannot name — usually a bug in the code building the file.

#: ``error_text`` kinds that describe a save failing at its location.
FILE_KINDS: FrozenSet[str] = frozenset({"permission_denied", "disk_full", "path_not_found", "invalid_path"})

_WRITE_FAILED = "Writing the file hit an unexpected error."
_TRY_AGAIN = "Try again."

EXPORT_BASELINE_DIFF = WorkerErrorSpec(
    "export_baseline_diff", "The drift report could not be saved", _WRITE_FAILED, _TRY_AGAIN, FILE_KINDS,
)
EXPORT_CVE_CSV = WorkerErrorSpec(
    "export_cve_csv", "The CVE list could not be saved", _WRITE_FAILED, _TRY_AGAIN, FILE_KINDS,
)
EXPORT_DIAGNOSIS_REPORT = WorkerErrorSpec(
    "export_diagnosis_report", "The diagnosis report could not be saved", _WRITE_FAILED, _TRY_AGAIN,
    FILE_KINDS,
)
EXPORT_INVENTORY_EVENTS = WorkerErrorSpec(
    "export_inventory_events", "The inventory changes could not be saved", _WRITE_FAILED, _TRY_AGAIN,
    FILE_KINDS,
)
EXPORT_INVENTORY_COMPARISON = WorkerErrorSpec(
    "export_inventory_comparison", "The comparison could not be saved", _WRITE_FAILED, _TRY_AGAIN,
    FILE_KINDS,
)
EXPORT_INVENTORY_SELECTION = WorkerErrorSpec(
    "export_inventory_selection", "The selected rows could not be saved", _WRITE_FAILED, _TRY_AGAIN,
    FILE_KINDS,
)
EXPORT_MAP_IMAGE = WorkerErrorSpec(
    "export_map_image", "The map image could not be saved", _WRITE_FAILED, _TRY_AGAIN, FILE_KINDS,
)
EXPORT_MAP_SHARE = WorkerErrorSpec(
    "export_map_share", "The shareable map could not be saved",
    "Drawing or writing the image hit an unexpected error.", _TRY_AGAIN, FILE_KINDS,
)
EXPORT_ALERT_HISTORY = WorkerErrorSpec(
    "export_alert_history", "The alert history could not be saved", _WRITE_FAILED, _TRY_AGAIN,
    FILE_KINDS,
)

EXPORT_ALL_DATA = WorkerErrorSpec(
    "export_all_data", "Your data could not be exported",
    "Writing the ZIP archive hit an unexpected error.", _TRY_AGAIN, FILE_KINDS,
)
EXPORT_LOG_VIEW = WorkerErrorSpec(
    "export_log_view", "The filtered log could not be saved", _WRITE_FAILED, _TRY_AGAIN, FILE_KINDS,
)
EXPORT_LOG_RANGE = WorkerErrorSpec(
    "export_log_range", "The log could not be saved", _WRITE_FAILED,
    "Press Export CSV again to choose another file.", FILE_KINDS,
)
EXPORT_PDF_REPORT = WorkerErrorSpec(
    "export_pdf_report", "The PDF report could not be saved",
    "Creating the PDF hit an unexpected error.", _TRY_AGAIN, FILE_KINDS,
)
PDF_NO_ENGINE = WorkerErrorSpec(
    # modules/report_pdf.NoPdfBackendError — raised only once the location check has passed.
    "pdf_no_engine", "The PDF report could not be created",
    "No PDF engine worked. Edge or Chrome failed or is missing.",
    "Try again, or install Google Chrome.",
)
EXPORT_ISP_REPORT = WorkerErrorSpec(
    "export_isp_report", "The network health report could not be saved",
    "Building or writing the report hit an unexpected error.", _TRY_AGAIN, FILE_KINDS,
)
PLUGIN_TEMPLATE = WorkerErrorSpec(
    # The file goes to the fixed plugins folder, so "choose another location" is never offered.
    "plugin_template", "The plugin file could not be created",
    "Writing it to the plugins folder failed.", "Check the plugins folder, then try again.",
    frozenset({"disk_full"}),
)

# ── Copying to the clipboard (S6) ────────────────────────────────────────────
#
# Nothing here touches the file system or the network: the text is built from data already in
# memory, so a failure is a bug and no error_text kind applies.

COPY_NETWORK_SUMMARY = WorkerErrorSpec(
    "copy_network_summary", "The network summary could not be copied",
    "Building the summary hit an unexpected error.", _TRY_AGAIN,
)
COPY_GRADE_CARD = WorkerErrorSpec(
    "copy_grade_card", "The grade card could not be copied",
    "Drawing the card image hit an unexpected error.", _TRY_AGAIN,
)
COPY_ISP_COMPLAINT = WorkerErrorSpec(
    "copy_isp_complaint", "The ISP complaint could not be copied",
    "Building the complaint text hit an unexpected error.", _TRY_AGAIN,
)
COPY_ISP_FORUM_POST = WorkerErrorSpec(
    "copy_isp_forum_post", "The forum post could not be copied",
    "Building the post hit an unexpected error.", _TRY_AGAIN,
)

# ── Labels, status lines and charts (S6b) ────────────────────────────────────
#
# A site that caught the exception passes it, so an entry with ``explains`` can say what the file
# system or database reported. An entry without ``explains`` is one whose ``try`` can only fail by a
# bug (the body reads data already in memory) or whose error_text wording would be wrong there.

_UNEXPECTED = "hit an unexpected error."
_DB_WRITE_KINDS: FrozenSet[str] = frozenset({"database_busy", "disk_full"})
#: The file goes to a folder NetSentinel chose, so "choose another location" would be wrong.
_FIXED_FOLDER_KINDS: FrozenSet[str] = frozenset({"disk_full"})

AUTO_REPORT = WorkerErrorSpec(
    "auto_report", "The report could not be created", f"Building or saving it {_UNEXPECTED}",
    "Run the scan again.", _FIXED_FOLDER_KINDS,
)
EXPORT_REPORT = WorkerErrorSpec(
    "export_report", "The report could not be saved", _WRITE_FAILED, _TRY_AGAIN, FILE_KINDS,
)
SCAN_STARTUP = WorkerErrorSpec(
    "scan_startup", "The scan could not start", f"Preparing the scan {_UNEXPECTED}", "Start the scan again.",
)
TOPOLOGY_RENDER = WorkerErrorSpec(
    "topology_render", "The network map could not be updated",
    f"Drawing it from the scan results {_UNEXPECTED}", "Run the scan again.",
)
DEVICE_FILTER = WorkerErrorSpec(
    "device_filter", "The search could not be applied", f"Filtering the device list {_UNEXPECTED}",
    "Clear the search and try again.",
)
BASELINE_CHECK = WorkerErrorSpec(
    "baseline_check", "New devices could not be checked",
    f"Comparing this scan with the saved device list {_UNEXPECTED}", "Run the scan again.",
)
LOG_CHART = WorkerErrorSpec(
    "log_chart", "The chart could not be opened", f"Drawing the loaded log {_UNEXPECTED}",
    "Load the log again, then retry.",
)
LOG_ANALYSIS = WorkerErrorSpec(
    "log_analysis", "The log could not be analysed", f"Analysing the loaded entries {_UNEXPECTED}",
    "Load the log again to retry.",
)
ROOT_CAUSE = WorkerErrorSpec(
    "root_cause", "The correlation could not run", f"Analysing the scan results {_UNEXPECTED}",
    "Run the scans again, then retry.",
)
# Both IoT sites only start a background thread; what fails inside it is the *_RUN entries below.
IOT_LEARN = WorkerErrorSpec(
    "iot_learn", "Baseline learning could not start", f"Starting it {_UNEXPECTED}", _TRY_AGAIN,
)
IOT_MONITOR = WorkerErrorSpec(
    "iot_monitor", "The anomaly monitor could not start", f"Starting it {_UNEXPECTED}", _TRY_AGAIN,
)
# Inside the IoT threads, reported by signal (RULE-WIN27). Measured 2026-09-18: with no capture
# driver scapy raises RuntimeError from the first sniff, before anything is saved; a read-only
# baseline file raises PermissionError errno 13. The baseline lives in a fixed folder, so only
# disk_full is explained (the S6b fixed-folder precedent).
IOT_LEARN_RUN = WorkerErrorSpec(
    "iot_learn_run", "Baseline learning did not finish",
    "It needs Npcap, and a Documents folder it can save the baseline to.",
    "Check both, then click Learn again.", explains=frozenset({"disk_full"}),
)
IOT_MONITOR_RUN = WorkerErrorSpec(
    "iot_monitor_run", "The anomaly monitor did not start",
    "It needs Npcap and a saved baseline for the devices it watches.",
    "Check both, then start it again.",
)
NETWORK_GRADE = WorkerErrorSpec(
    "network_grade", "The network could not be graded",
    f"Calculating the grade from the scan results {_UNEXPECTED}", "Run the scans again, then retry.",
)
RISK_SCORE = WorkerErrorSpec(
    "risk_score", "Devices could not be scored", f"Scoring the scan results {_UNEXPECTED}",
    "Run the scans again, then retry.",
)
UPDATE_CHECK = WorkerErrorSpec(
    # No explains: measured (S6b) — every network kind's advice is wrong here ("check the host
    # name", and GitHub's anonymous rate-limit 403 reads as "check the API key").
    "update_check", "The update check failed",
    "You may be offline, or GitHub is unreachable or limiting requests.", "Try again later.",
)

HA_LOAD = WorkerErrorSpec(
    # A read: measured (S6b), a WAL read succeeds under a write lock, so no database kind applies.
    "ha_load", "Devices could not be loaded", f"Reading them from the database {_UNEXPECTED}",
    "Reopen this page to try again.",
)
HA_SAVE = WorkerErrorSpec(
    "ha_save", "The device was not saved", f"Writing it to the database {_UNEXPECTED}", _TRY_AGAIN,
    _DB_WRITE_KINDS,
)
HA_ADD = WorkerErrorSpec(
    "ha_add", "The device was not added", f"Writing it to the database {_UNEXPECTED}", _TRY_AGAIN,
    _DB_WRITE_KINDS,
)

PLUGIN_CATALOGUE_INSTALL = WorkerErrorSpec(
    "plugin_catalogue_install", "The plugin could not be installed",
    "Copying it to the plugins folder failed.", "Check the plugins folder, then try again.",
    _FIXED_FOLDER_KINDS,
)
PLUGIN_REGISTER = WorkerErrorSpec(
    "plugin_register", "The plugin could not be added",
    "Copying it to the plugins folder failed.", "Check the plugins folder, then try again.",
    _FIXED_FOLDER_KINDS,
)
PLUGIN_BUNDLE_IMPORT = WorkerErrorSpec(
    # modules/nspkg.unpack_nspkg's own ValueError names the exact rule — it goes in the detail.
    "plugin_bundle_import", "The plugin bundle could not be imported",
    "It must be a .nspkg (ZIP) file with plugin.py and a valid manifest.json.", "Choose another file.",
    _FIXED_FOLDER_KINDS,
)
PLUGIN_ERROR = WorkerErrorSpec(
    # Only the text hub_helpers.plugin_error_text cannot classify; protocol messages show as written.
    "plugin_error", "The plugin reported an error",
    "It is not one NetSentinel can explain.", "Open the plugin log for details, then refresh.",
)
PLUGIN_CONNECTION_TEST = WorkerErrorSpec(
    "plugin_connection_test", "The connection test failed",
    "The plugin reported an error NetSentinel cannot explain.", "Check the IP address and password, then retry.",
)

HEATMAP_FLOOR_PLAN = WorkerErrorSpec(
    "heatmap_floor_plan", "The floor plan could not be loaded",
    "The file may not be a PNG, JPEG, BMP or GIF image, or it is damaged.", "Choose another image.",
    frozenset({"permission_denied"}),
)
HEATMAP_SURVEY_LOAD = WorkerErrorSpec(
    "heatmap_survey_load", "The survey could not be loaded",
    "The file is damaged or is not a NetSentinel survey.", "Choose another survey file.",
    frozenset({"permission_denied"}),
)
HEATMAP_SURVEY_SAVE = WorkerErrorSpec(
    "heatmap_survey_save", "The survey could not be saved", "Writing it to the surveys folder failed.",
    _TRY_AGAIN, _FIXED_FOLDER_KINDS,
)
EXPORT_HEATMAP_IMAGE = WorkerErrorSpec(
    "export_heatmap_image", "The heatmap image could not be saved", _WRITE_FAILED, _TRY_AGAIN, FILE_KINDS,
)
TOPOLOGY_SNAPSHOT = WorkerErrorSpec(
    "topology_snapshot", "The topology snapshot could not be made",
    f"Drawing or saving the map image {_UNEXPECTED}", "The document is generated without it.",
    _FIXED_FOLDER_KINDS,
)

LIVE_BANDWIDTH = WorkerErrorSpec(
    # psutil missing (a broken install) or net_io_counters() failing; the poller retries every second.
    "live_bandwidth", "Interface counters could not be read",
    "Windows did not return the network adapter statistics.", "It retries automatically.",
)
APP_TRAFFIC = WorkerErrorSpec(
    # S9.4: AppTrafficClassifier.run() has exactly two error paths and both are capability
    # gaps -- Scapy missing, or AppTrafficSniffer.start() refusing without Npcap and
    # administrator rights. It never reads interface counters, and "start it again" cannot
    # install a driver, so the old text misdescribed the failure and misdirected the fix.
    "app_traffic", "App traffic monitoring could not run", _PACKET_CAPTURE,
    "Check both, then start it again.",
)
SPEED_SERVER_LIST = WorkerErrorSpec(
    "speed_server_list", "The server list could not be fetched",
    "Speedtest servers could not be reached. You may be offline.", "A test still picks the best server.",
)
ABUSEIPDB_NOT_TESTABLE = WorkerErrorSpec(
    # AbuseIpDbUnreachableError wraps every request failure: no answer, an HTTP error (401 for a
    # bad key, 429 for the rate limit) or an unreadable reply.
    "abuseipdb_not_testable", "AbuseIPDB could not test this IP",
    "It did not answer, refused the API key, or limited requests.", "Check the key, or try again later.",
)

#: Every entry by its attribute name — what sites reference as ``WE.<NAME>``.
ALL: Dict[str, WorkerErrorSpec] = {
    name: value for name, value in dict(globals()).items() if isinstance(value, WorkerErrorSpec)
}
