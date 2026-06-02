"""
ui/widgets/alert_drawer.py — Alert detail side drawer (ALERT-1)

A 320px QFrame that slides in from the right of its parent container,
showing full context for a single fired alert: severity, rule, host,
device context from MetricStore, live metric sub-label, and action buttons.

Used by: NotificationsPage (wired to alert history table single-click).
"""
from __future__ import annotations

import re
import time

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QThread, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT,
    ACCENT_DARK,
    AMBER,
    BG_CARD,
    BG_DARK,
    BORDER,
    GREEN,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    BG_HOVER,
    WHITE,
)

# ── Constants ─────────────────────────────────────────────────────────────────

_SEV_COLOR = {"INFO": ACCENT, "WARNING": AMBER, "CRITICAL": RED}

_RULE_PAGE: dict[str, str] = {
    "PORT_SCAN":   "Port Scan (TCP)",
    "THREAT_INTEL": "Threat Intel",
    "CVE":         "CVE Lookup",
    "CERT":        "TLS & Exposure",
    "RATE_SPIKE":  "Live Bandwidth",
    "BANDWIDTH":   "Live Bandwidth",
    "ARP":         "ARP Spoof Watch",
    "DHCP":        "DHCP Rogue Monitor",
    "SERVICE_DOWN": "Service Heartbeat",
}

# Per-alert-type fix text following Design Principles 1–4:
# - No CLI commands
# - Fix at the router, not the device
# - Use app-measured data
# - Close the loop with a rescan
_RULE_FIX: dict[str, str] = {
    "PORT_SCAN": (
        "An unexpected port is open on this device. Open Port Scan to see the full results.\n"
        "To close it: log in to your router's admin page and disable any services you do not "
        "recognise. On the device itself, disable the service from its settings.\n"
        "After making changes, run a new Port Scan in NetSentinel to confirm the port is closed."
    ),
    "ARP": (
        "NetSentinel detected possible MAC address impersonation — a device may be "
        "intercepting traffic on your network.\n"
        "Open ARP Spoof Watch to see the full ARP table and identify the suspicious device.\n"
        "Once identified, block the unknown device from your router's client list, then "
        "click Rescan in NetSentinel to confirm the alert clears."
    ),
    "DHCP": (
        "A device is responding to DHCP requests from an IP that is not your router. "
        "This rogue DHCP server could redirect your traffic.\n"
        "Open DHCP Rogue Monitor to identify it. Then locate and disconnect the device from "
        "your network, or block it in your router's client list.\n"
        "Run a new scan in NetSentinel to confirm the rogue server is gone."
    ),
    "DEVICE": (
        "An unknown device joined your network. Open the Devices page to identify it.\n"
        "If you do not recognise it: block it in your router's wireless client list. "
        "Look for a setting called 'Block' or 'Deny' next to the device's MAC address.\n"
        "After blocking, run a new scan in NetSentinel to verify it no longer appears."
    ),
    "HOST_DOWN": (
        "NetSentinel cannot reach this device. Check the Availability page for the full "
        "outage timeline and when it went offline.\n"
        "Try restarting the device or checking its network cable. For Wi-Fi devices, "
        "check whether the device is still connected to your router's client list.\n"
        "NetSentinel will automatically detect when the device comes back online."
    ),
    "SERVICE_DOWN": (
        "A monitored service is not responding. Open Service Heartbeat to see its history.\n"
        "Restart the device or service. If the service requires a specific port, verify "
        "the port has not been blocked by your router's firewall settings.\n"
        "NetSentinel will automatically show the service as recovered when it responds."
    ),
    "RTT_THRESHOLD": (
        "NetSentinel measured high latency to this device. Open the Log Hub to see "
        "the full latency timeline and when the problem started.\n"
        "High latency for all devices usually means the router or ISP link is congested. "
        "Try changing the DNS server on your router to 1.1.1.1 to rule out DNS delays.\n"
        "After making changes, run a new DNS test in NetSentinel to confirm improvement."
    ),
    "THREAT_INTEL": (
        "This IP address has been reported for malicious activity in threat intelligence feeds.\n"
        "Open Threat Intel to see the full report and abuse score.\n"
        "Block traffic to/from this IP on your router's firewall, then run a new Threat "
        "Intel scan in NetSentinel to confirm the device is no longer contacting it."
    ),
    "CVE": (
        "A known vulnerability was found on this device. Open CVE Lookup to see full details "
        "and the CVSS severity score.\n"
        "Apply the latest firmware or software update for the affected device. Check the "
        "manufacturer's website for a security advisory.\n"
        "After updating, run a new scan in NetSentinel to verify the CVE is resolved."
    ),
    "CERT": (
        "A TLS certificate on this host is expired or about to expire. Open TLS & Exposure "
        "to see the certificate details.\n"
        "Renew the certificate through the hosting provider or certificate authority. "
        "If the service is hosted on your network, update the certificate on the server.\n"
        "After renewal, run a new TLS scan in NetSentinel to confirm the certificate is valid."
    ),
    "BANDWIDTH": (
        "Unusually high bandwidth was detected on this interface. Open Live Bandwidth to "
        "see a real-time chart of which device is consuming the most traffic.\n"
        "If a single device is using excessive bandwidth, check for software updates running "
        "in the background, video streaming, or potential malware.\n"
        "After investigating, monitor the Live Bandwidth page to confirm usage returns to normal."
    ),
}


# ── Module helpers ────────────────────────────────────────────────────────────

def _fmt_elapsed(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    return f"{h}h {m:02d}m" if m else f"{h}h"


def _get_sublabel(alert: dict) -> str:
    """Return a short contextual metric string for the alert, or empty string."""
    rule    = (alert.get("rule_name") or "").upper()
    msg     = alert.get("message") or ""
    elapsed = max(0, int(time.time()) - int(alert.get("ts") or 0))

    if "RTT_THRESHOLD" in rule or "HIGH_RTT" in rule:
        m = re.search(r":\s*([\d.]+)\s*ms", msg)
        return f"RTT: {float(m.group(1)):.0f} ms at alert time" if m else ""
    if "HOST_DOWN" in rule:
        return f"Down for {_fmt_elapsed(elapsed)}"
    if "DEVICE_GONE" in rule:
        return f"Last seen {_fmt_elapsed(elapsed)} ago"
    if "SERVICE_DOWN" in rule:
        m = re.search(r"\((.+):(\d+)\)$", msg)
        prefix = f"Port {m.group(2)} · " if m else ""
        return f"{prefix}down for {_fmt_elapsed(elapsed)}"
    if "CERT_EXPIRY" in rule and "EXPIRED" not in rule:
        m = re.search(r"(\d+)\s+day", msg)
        if m:
            d = int(m.group(1))
            return f"Expires in {d} day{'s' if d != 1 else ''}"
        return ""
    if "CERT_EXPIRED" in rule:
        d = elapsed // 86400
        return f"Expired {max(d, 0)} day{'s' if d != 1 else ''} ago"
    if "THREAT_INTEL" in rule:
        m = re.search(r"score[:\s]+([\d.]+)", msg, re.IGNORECASE)
        return f"Abuse score: {float(m.group(1)):.0f}/100" if m else ""
    return ""


def _rule_to_page(rule: str) -> str:
    rule_upper = rule.upper()
    for key, page in _RULE_PAGE.items():
        if key in rule_upper:
            return page
    return ""


def _rule_to_fix(rule: str) -> str:
    rule_upper = rule.upper()
    for key, fix in _RULE_FIX.items():
        if key in rule_upper:
            return fix
    return ""


# Map rule name prefixes to LogHub source keys
_RULE_LOG_SOURCE: dict[str, str] = {
    "ARP":          "net",
    "DHCP":         "net",
    "RTT":          "net",
    "HOST_DOWN":    "net",
    "DEVICE_GONE":  "net",
    "DEVICE":       "net",
    "RATE_SPIKE":   "net",
    "BANDWIDTH":    "net",
    "PORT_SCAN":    "net",
    "SERVICE_DOWN": "net",
    "CERT":         "net",
    "CVE":          "net",
    "THREAT_INTEL": "net",
    "SYSLOG":       "syslog",
    "SNMP":         "snmp",
}


def _rule_to_log_source(rule: str) -> str:
    rule_upper = rule.upper()
    for key, source in _RULE_LOG_SOURCE.items():
        if key in rule_upper:
            return source
    return "net"


# ── Evidence worker ───────────────────────────────────────────────────────────

class _EvidenceWorker(QThread):
    """Fetch device history, recent alerts, and CVE count for the alert host."""

    done = pyqtSignal(dict)   # {events: int, last_event: str, alerts: int, cve_count: int}

    def __init__(self, store, host: str, rule_name: str, parent=None):
        super().__init__(parent)
        self._store     = store
        self._host      = host
        self._rule_name = rule_name

    def run(self) -> None:
        result: dict = {"events": 0, "last_event": "", "alerts": 0, "cve_count": 0}
        try:
            if self._store is None:
                self.done.emit(result)
                return

            # Device events in last 7 days
            events = self._store.query_device_events(hours=168, ip=self._host)
            result["events"] = len(events)
            if events:
                import time as _time
                result["last_event"] = _time.strftime(
                    "%Y-%m-%d %H:%M", _time.localtime(events[0].ts)
                )

            # Other alerts for same host in last 7 days
            all_alerts = self._store.get_recent_alerts(hours=168, limit=500)
            host_alerts = [
                a for a in all_alerts
                if (a.get("host") == self._host or a.get("ip") == self._host)
            ]
            result["alerts"] = len(host_alerts)

            # CVE count (all CVEs — no per-host filtering needed for context)
            cves = self._store.list_cve_lifecycles() or []
            result["cve_count"] = len(cves)

        except Exception:
            pass
        self.done.emit(result)


# ── Widget ────────────────────────────────────────────────────────────────────

class AlertDrawer(QFrame):
    """320px animated slide-in drawer showing full context for a single alert.

    Signals:
        acknowledged(int)  — emitted after the user acks; carries alert_id
        navigate_to(str)   — emitted when user clicks "Go to page →"
    """

    acknowledged    = pyqtSignal(int)
    navigate_to     = pyqtSignal(str)
    view_in_log_hub = pyqtSignal(float, str)  # (alert_ts, source_key)

    OPEN_WIDTH = 320

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(0)
        self.setMaximumWidth(0)
        self.setStyleSheet(
            f"AlertDrawer {{ background:{BG_CARD}; border-left:1px solid {BORDER}; }}"
        )

        self._store  = None
        self._router = None
        self._current_alert: dict | None = None
        self._evidence_worker: "_EvidenceWorker | None" = None

        self._anim = QPropertyAnimation(self, b"maximumWidth")
        self._anim.setDuration(120)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._build_ui()

    # ── Dependency injection ──────────────────────────────────────────────────

    def set_store(self, store) -> None:
        self._store = store

    def set_router(self, router) -> None:
        self._router = router

    # ── Open / close ──────────────────────────────────────────────────────────

    def open(self, alert: dict) -> None:
        self._current_alert = alert
        self._populate(alert)
        self._start_evidence_fetch(alert)
        self._anim.stop()
        self._anim.setStartValue(self.maximumWidth())
        self._anim.setEndValue(self.OPEN_WIDTH)
        self._anim.start()

    def close_drawer(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(self.maximumWidth())
        self._anim.setEndValue(0)
        self._anim.start()

    def is_open(self) -> bool:
        return self.maximumWidth() > 0

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setFixedHeight(44)
        hdr.setStyleSheet(
            f"background:{BG_DARK}; border-bottom:1px solid {BORDER};"
        )
        hlay = QHBoxLayout(hdr)
        hlay.setContentsMargins(12, 0, 8, 0)
        hlay.setSpacing(8)

        self._sev_badge = QLabel("INFO")
        self._sev_badge.setFixedSize(62, 18)
        self._sev_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sev_badge.setStyleSheet(
            f"color:white; font-size:9px; font-weight:bold;"
            f" background:{ACCENT}; border-radius:3px; border:none;"
        )

        self._rule_lbl = QLabel("Alert Detail")
        self._rule_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:11px; font-weight:bold;"
            f" background:transparent; border:none;"
        )
        self._rule_lbl.setMinimumWidth(0)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none;"
            f" font-size:13px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_MUTED}; }}"
        )
        close_btn.clicked.connect(self.close_drawer)

        hlay.addWidget(self._sev_badge)
        hlay.addWidget(self._rule_lbl, 1)
        hlay.addWidget(close_btn)
        root.addWidget(hdr)

        # ── Scrollable body ───────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;")

        body = QWidget()
        body.setStyleSheet(f"background:{BG_CARD};")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(12, 12, 12, 12)
        bl.setSpacing(8)

        self._meta_lbl = QLabel()
        self._meta_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;"
        )
        bl.addWidget(self._meta_lbl)

        self._sublabel_lbl = QLabel()
        self._sublabel_lbl.setStyleSheet(
            f"color:{ACCENT}; font-size:11px; font-weight:bold;"
            f" background:transparent; border:none;"
        )
        self._sublabel_lbl.setVisible(False)
        bl.addWidget(self._sublabel_lbl)

        self._msg_lbl = QLabel()
        self._msg_lbl.setWordWrap(True)
        self._msg_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px;"
            f" background:transparent; border:none;"
        )
        bl.addWidget(self._msg_lbl)

        fix_sep = QFrame()
        fix_sep.setFixedHeight(1)
        fix_sep.setStyleSheet(f"background:{BORDER}; border:none;")
        bl.addWidget(fix_sep)

        fix_hdr = QLabel("WHAT TO DO")
        fix_hdr.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:9px; font-weight:bold;"
            f" letter-spacing:1px; background:transparent; border:none;"
        )
        bl.addWidget(fix_hdr)

        self._fix_lbl = QLabel()
        self._fix_lbl.setWordWrap(True)
        self._fix_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._fix_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:10px; line-height:140%;"
            f" background:transparent; border:none;"
        )
        self._fix_lbl.setVisible(False)
        bl.addWidget(self._fix_lbl)

        self._no_fix_lbl = QLabel("No specific remediation available for this alert type.")
        self._no_fix_lbl.setWordWrap(True)
        self._no_fix_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:10px; font-style:italic;"
            f" background:transparent; border:none;"
        )
        self._no_fix_lbl.setVisible(False)
        bl.addWidget(self._no_fix_lbl)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{BORDER}; border:none;")
        bl.addWidget(sep)

        dev_hdr = QLabel("DEVICE CONTEXT")
        dev_hdr.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:9px; font-weight:bold;"
            f" letter-spacing:1px; background:transparent; border:none;"
        )
        bl.addWidget(dev_hdr)

        self._dev_lbl = QLabel("—")
        self._dev_lbl.setWordWrap(True)
        self._dev_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._dev_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px;"
            f" background:transparent; border:none;"
        )
        bl.addWidget(self._dev_lbl)

        ev_sep = QFrame()
        ev_sep.setFixedHeight(1)
        ev_sep.setStyleSheet(f"background:{BORDER}; border:none;")
        bl.addWidget(ev_sep)

        ev_hdr = QLabel("EVIDENCE")
        ev_hdr.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:9px; font-weight:bold;"
            f" letter-spacing:1px; background:transparent; border:none;"
        )
        bl.addWidget(ev_hdr)

        self._ev_events_lbl = QLabel("…")
        self._ev_alerts_lbl = QLabel("…")
        self._ev_cve_lbl    = QLabel("…")
        for lbl in (self._ev_events_lbl, self._ev_alerts_lbl, self._ev_cve_lbl):
            lbl.setStyleSheet(
                f"color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;"
            )
            bl.addWidget(lbl)

        bl.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ── Actions row ───────────────────────────────────────────────────────
        acts = QFrame()
        acts.setFixedHeight(48)
        acts.setStyleSheet(
            f"background:{BG_DARK}; border-top:1px solid {BORDER};"
        )
        alay = QHBoxLayout(acts)
        alay.setContentsMargins(8, 0, 8, 0)
        alay.setSpacing(6)

        self._ack_btn = QPushButton("✓ Acknowledge")
        self._ack_btn.setFixedHeight(26)
        self._ack_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ack_btn.setStyleSheet(
            f"QPushButton {{ background:{GREEN}; color:white; border:none;"
            f" border-radius:3px; font-size:10px; font-weight:bold; padding:0 8px; }}"
            f"QPushButton:hover {{ opacity:0.9; }}"
            f"QPushButton:disabled {{ background:{BG_DARK}; color:{TEXT_MUTED};"
            f" border:1px solid {BORDER}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        self._ack_btn.clicked.connect(self._on_ack)

        self._snooze_btn = QPushButton("Snooze 1h")
        self._snooze_btn.setFixedHeight(26)
        self._snooze_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._snooze_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{AMBER};"
            f" border:1px solid {AMBER}; border-radius:3px;"
            f" font-size:10px; padding:0 8px; }}"
            f"QPushButton:hover {{ background:{AMBER}22; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{AMBER}; }}"
        )
        self._snooze_btn.clicked.connect(self._on_snooze)

        self._log_btn = QPushButton("Log Hub →")
        self._log_btn.setFixedHeight(26)
        self._log_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._log_btn.setToolTip("Open Log Hub at ±30 min around this alert")
        self._log_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{ACCENT};"
            f" border:1px solid {ACCENT}; border-radius:3px;"
            f" font-size:10px; padding:0 8px; }}"
            f"QPushButton:hover {{ background:{ACCENT}22; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        self._log_btn.clicked.connect(self._on_view_log_hub)

        self._fix_btn = QPushButton("Fix this →")
        self._fix_btn.setFixedHeight(26)
        self._fix_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fix_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:3px; font-size:10px; font-weight:bold; padding:0 8px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
        )
        self._fix_btn.clicked.connect(self._on_go)
        self._fix_btn.setVisible(False)

        self._go_btn = QPushButton("Go to page →")
        self._go_btn.setFixedHeight(26)
        self._go_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._go_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{ACCENT};"
            f" border:1px solid {BORDER}; border-radius:3px;"
            f" font-size:10px; padding:0 8px; }}"
            f"QPushButton:hover {{ border-color:{ACCENT}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        self._go_btn.clicked.connect(self._on_go)
        self._go_btn.setVisible(False)

        alay.addWidget(self._ack_btn)
        alay.addWidget(self._snooze_btn)
        alay.addWidget(self._log_btn)
        alay.addWidget(self._fix_btn)
        alay.addWidget(self._go_btn)
        root.addWidget(acts)

    # ── Content population ────────────────────────────────────────────────────

    def _populate(self, alert: dict) -> None:
        sev  = alert.get("severity", "INFO")
        rule = alert.get("rule_name", "—")
        host = alert.get("host", "—")
        ts   = alert.get("ts", 0)
        msg  = alert.get("message", "")

        col = _SEV_COLOR.get(sev, ACCENT)
        self._sev_badge.setText(sev)
        self._sev_badge.setStyleSheet(
            f"color:white; font-size:9px; font-weight:bold;"
            f" background:{col}; border-radius:3px; border:none;"
        )

        self._rule_lbl.setText(rule)

        ts_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "—"
        self._meta_lbl.setText(f"{ts_str}  ·  {host}")

        sub = _get_sublabel(alert)
        if sub:
            self._sublabel_lbl.setText(sub)
            self._sublabel_lbl.setVisible(True)
        else:
            self._sublabel_lbl.setVisible(False)

        self._msg_lbl.setText(msg or "—")

        already_acked = bool(alert.get("acked_ts"))
        self._ack_btn.setEnabled(not already_acked)
        self._ack_btn.setText("✓ Acknowledged" if already_acked else "✓ Acknowledge")

        self._dev_lbl.setText(self._build_device_context(host))

        fix_text = _rule_to_fix(rule)
        if fix_text:
            self._fix_lbl.setText(fix_text)
            self._fix_lbl.setVisible(True)
            self._no_fix_lbl.setVisible(False)
        else:
            self._fix_lbl.setVisible(False)
            self._no_fix_lbl.setVisible(True)

        page = _rule_to_page(rule)
        has_page = bool(page)
        if has_page:
            self._go_btn.setProperty("_target_page", page)
            self._fix_btn.setProperty("_target_page", page)
        if fix_text and has_page:
            self._fix_btn.setVisible(True)
            self._go_btn.setVisible(False)
        elif has_page:
            self._fix_btn.setVisible(False)
            self._go_btn.setVisible(True)
        else:
            self._fix_btn.setVisible(False)
            self._go_btn.setVisible(False)

    def _build_device_context(self, host: str) -> str:
        if not self._store:
            return "—"
        try:
            devices = self._store.get_known_devices()
        except Exception:
            return "—"

        dev = devices.get(host)
        if dev is None:
            for d in devices.values():
                if getattr(d, "ip", None) == host:
                    dev = d
                    break

        if dev is None:
            return "Unknown — not seen in scans"

        lines = []
        name = getattr(dev, "custom_name", None) or getattr(dev, "hostname", None)
        if name:
            lines.append(f"Name: {name}")
        vendor = getattr(dev, "vendor", None)
        if vendor:
            lines.append(f"Vendor: {vendor}")
        if getattr(dev, "mac", None):
            lines.append(f"MAC: {dev.mac}")
        if getattr(dev, "ip", None) and dev.ip != host:
            lines.append(f"IP: {dev.ip}")
        if getattr(dev, "first_seen", None):
            lines.append(f"First seen: {time.strftime('%Y-%m-%d', time.localtime(dev.first_seen))}")
        if getattr(dev, "last_seen", None):
            lines.append(f"Last seen: {time.strftime('%Y-%m-%d %H:%M', time.localtime(dev.last_seen))}")
        tags = getattr(dev, "tags", None)
        if tags:
            lines.append(f"Tags: {tags}")

        return "\n".join(lines) if lines else "Device found — no details available"

    # ── Action handlers ───────────────────────────────────────────────────────

    def _on_ack(self) -> None:
        alert = self._current_alert
        if not alert or not self._store:
            return
        alert_id = alert.get("id")
        if alert_id is None:
            return
        try:
            self._store.acknowledge_alert(int(alert_id))
        except Exception:
            return
        self._ack_btn.setEnabled(False)
        self._ack_btn.setText("✓ Acknowledged")
        self.acknowledged.emit(int(alert_id))

    def _on_snooze(self) -> None:
        alert = self._current_alert
        if not alert or not self._router:
            return
        rule_name = alert.get("rule_name", "")
        if rule_name:
            self._router.set_snooze(rule_name, time.time() + 3600)
        self.close_drawer()

    def _on_go(self) -> None:
        page = self._go_btn.property("_target_page")
        if page:
            self.navigate_to.emit(str(page))

    def _on_view_log_hub(self) -> None:
        alert = self._current_alert
        if not alert:
            return
        ts = float(alert.get("ts") or 0)
        source_key = _rule_to_log_source(alert.get("rule_name") or "")
        self.view_in_log_hub.emit(ts, source_key)

    def _start_evidence_fetch(self, alert: dict) -> None:
        if self._evidence_worker and self._evidence_worker.isRunning():
            self._evidence_worker.done.disconnect()
            self._evidence_worker.quit()
        for lbl in (self._ev_events_lbl, self._ev_alerts_lbl, self._ev_cve_lbl):
            lbl.setText("…")
            lbl.setStyleSheet(
                f"color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;"
            )
        if not self._store:
            for lbl in (self._ev_events_lbl, self._ev_alerts_lbl, self._ev_cve_lbl):
                lbl.setText("—")
            return
        host = alert.get("host") or alert.get("ip") or ""
        rule  = alert.get("rule_name") or ""
        self._evidence_worker = _EvidenceWorker(self._store, host, rule, parent=self)
        self._evidence_worker.done.connect(self._on_evidence_done)
        self._evidence_worker.start()

    @pyqtSlot(dict)
    def _on_evidence_done(self, data: dict) -> None:
        ev_count   = data.get("events", 0)
        last_event = data.get("last_event", "")
        al_count   = data.get("alerts", 0)
        cve_count  = data.get("cve_count", 0)

        if ev_count:
            self._ev_events_lbl.setText(
                f"● {ev_count} device event{'s' if ev_count != 1 else ''} (last: {last_event})"
            )
        else:
            self._ev_events_lbl.setText("● No device events in last 7 days")

        if al_count:
            self._ev_alerts_lbl.setText(
                f"● {al_count} other alert{'s' if al_count != 1 else ''} for this host (7d)"
            )
        else:
            self._ev_alerts_lbl.setText("● No other alerts for this host (7d)")

        if cve_count:
            self._ev_cve_lbl.setText(f"● {cve_count} CVE{'s' if cve_count != 1 else ''} tracked")
        else:
            self._ev_cve_lbl.setText("● No CVEs tracked")

        for lbl in (self._ev_events_lbl, self._ev_alerts_lbl, self._ev_cve_lbl):
            lbl.setStyleSheet(
                f"color:{TEXT_SECONDARY}; font-size:10px;"
                f" background:transparent; border:none;"
            )
