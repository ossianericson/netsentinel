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

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, pyqtSignal
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
    AMBER,
    BG_CARD,
    BG_DARK,
    BORDER,
    GREEN,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
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
        )
        self._log_btn.clicked.connect(self._on_view_log_hub)

        self._go_btn = QPushButton("Go to page →")
        self._go_btn.setFixedHeight(26)
        self._go_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._go_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{ACCENT};"
            f" border:1px solid {BORDER}; border-radius:3px;"
            f" font-size:10px; padding:0 8px; }}"
            f"QPushButton:hover {{ border-color:{ACCENT}; }}"
        )
        self._go_btn.clicked.connect(self._on_go)
        self._go_btn.setVisible(False)

        alay.addWidget(self._ack_btn)
        alay.addWidget(self._snooze_btn)
        alay.addWidget(self._log_btn)
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

        page = _rule_to_page(rule)
        self._go_btn.setVisible(bool(page))
        if page:
            self._go_btn.setProperty("_target_page", page)

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
