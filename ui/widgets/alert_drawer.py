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

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QSize, QThread, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.device_detail_pane import _wire_close_icon

from ui import styles as _s
from ui.styles import (
    alpha,
)
from ui.widgets.jargon_tooltip import LearnMoreLink, find_known_term
from modules.alert_remediation import remediation_for

# ── Constants ─────────────────────────────────────────────────────────────────

_SEV_COLOR = {"INFO": "ACCENT", "WARNING": "AMBER", "CRITICAL": "RED", "HEALTHY": "GREEN"}

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
            pass  # non-fatal
        self.done.emit(result)


# ── Wrapping button row ──────────────────────────────────────────────────────

class _FlowLayout(QLayout):
    """Lays out child widgets left-to-right, wrapping to a new line when the next
    widget would not fit the available width.

    Used for the drawer's action-button row: the set of visible buttons (and their
    text) varies per alert, so a fixed single-row QHBoxLayout clips button text
    whenever the combined width exceeds the 320px drawer. Wrapping instead of
    clipping keeps every label fully readable regardless of which buttons are
    visible or how long their text is.
    """

    def __init__(self, parent=None, margin: int = 0, hspacing: int = 6, vspacing: int = 6):
        super().__init__(parent)
        self._hspacing = hspacing
        self._vspacing = vspacing
        self._items: list = []
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0

        for item in self._items:
            widget = item.widget()
            if widget is not None and not widget.isVisible():
                continue
            item_size = item.sizeHint()
            next_x = x + item_size.width() + self._hspacing
            if next_x - self._hspacing > effective.right() + 1 and line_height > 0:
                x = effective.x()
                y = y + line_height + self._vspacing
                next_x = x + item_size.width() + self._hspacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(x, y, item_size.width(), item_size.height()))
            x = next_x
            line_height = max(line_height, item_size.height())

        return y + line_height - rect.y() + margins.bottom()


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
        _s.themed_ss(self, "AlertDrawer {{ background:{BG_CARD}; border-left:1px solid {BORDER}; }}")

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
        self._anim.finished.connect(self._restore_focus)
        self._anim.start()

    def _restore_focus(self) -> None:
        try:
            self._anim.finished.disconnect(self._restore_focus)
        except RuntimeError:
            pass  # non-fatal — already disconnected after a prior close
        w = self.window()
        if w:
            w.activateWindow()

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
        _s.themed_ss(hdr, "background:{BG_DARK}; border-bottom:1px solid {BORDER};")
        hlay = QHBoxLayout(hdr)
        hlay.setContentsMargins(12, 0, 8, 0)
        hlay.setSpacing(8)

        self._sev_badge = QLabel("INFO")
        self._sev_badge.setFixedSize(62, 18)
        self._sev_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _s.themed_ss(self._sev_badge, "color:{WHITE}; font-size:9px; font-weight:bold;"
            " background:{ACCENT}; border-radius:3px; border:none;")

        self._rule_lbl = QLabel("Alert Detail")
        _s.themed_ss(self._rule_lbl, "color:{TEXT_PRIMARY}; font-size:11px; font-weight:bold;"
            " background:transparent; border:none;")
        self._rule_lbl.setMinimumWidth(0)

        close_btn = QPushButton()
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _wire_close_icon(close_btn)
        _s.themed_ss(close_btn, "QPushButton {{ background:transparent; border:none; }}"
            "QPushButton:hover {{ background:transparent; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; }}")
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
        _s.themed_ss(body, "background:{BG_CARD};")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(12, 12, 12, 12)
        bl.setSpacing(8)

        self._meta_lbl = QLabel()
        _s.themed_ss(self._meta_lbl, "color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;")
        bl.addWidget(self._meta_lbl)

        self._sublabel_lbl = QLabel()
        _s.themed_ss(self._sublabel_lbl, "color:{ACCENT}; font-size:11px; font-weight:bold;"
            " background:transparent; border:none;")
        self._sublabel_lbl.setVisible(False)
        bl.addWidget(self._sublabel_lbl)

        self._msg_lbl = QLabel()
        self._msg_lbl.setWordWrap(True)
        _s.themed_ss(self._msg_lbl, "color:{TEXT_SECONDARY}; font-size:11px;"
            " background:transparent; border:none;")
        bl.addWidget(self._msg_lbl)

        # Contextual "learn more" link (S7-3) — populated per-alert in _populate()
        self._learn_more_row = QHBoxLayout()
        self._learn_more_row.setContentsMargins(0, 0, 0, 0)
        self._learn_more_link: "LearnMoreLink | None" = None
        bl.addLayout(self._learn_more_row)

        fix_sep = QFrame()
        fix_sep.setFixedHeight(1)
        _s.themed_ss(fix_sep, "background:{BORDER}; border:none;")
        bl.addWidget(fix_sep)

        fix_hdr = QLabel("WHAT TO DO")
        _s.themed_ss(fix_hdr, "color:{TEXT_MUTED}; font-size:9px; font-weight:bold;"
            " letter-spacing:1px; background:transparent; border:none;")
        bl.addWidget(fix_hdr)

        self._fix_lbl = QLabel()
        self._fix_lbl.setWordWrap(True)
        self._fix_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        _s.themed_ss(self._fix_lbl, "color:{TEXT_SECONDARY}; font-size:10px; line-height:140%;"
            " background:transparent; border:none;")
        self._fix_lbl.setVisible(False)
        bl.addWidget(self._fix_lbl)

        self._no_fix_lbl = QLabel("No specific remediation available for this alert type.")
        self._no_fix_lbl.setWordWrap(True)
        _s.themed_ss(self._no_fix_lbl, "color:{TEXT_MUTED}; font-size:10px; font-style:italic;"
            " background:transparent; border:none;")
        self._no_fix_lbl.setVisible(False)
        bl.addWidget(self._no_fix_lbl)

        sep = QFrame()
        sep.setFixedHeight(1)
        _s.themed_ss(sep, "background:{BORDER}; border:none;")
        bl.addWidget(sep)

        dev_hdr = QLabel("DEVICE CONTEXT")
        _s.themed_ss(dev_hdr, "color:{TEXT_MUTED}; font-size:9px; font-weight:bold;"
            " letter-spacing:1px; background:transparent; border:none;")
        bl.addWidget(dev_hdr)

        self._dev_lbl = QLabel("—")
        self._dev_lbl.setWordWrap(True)
        self._dev_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        _s.themed_ss(self._dev_lbl, "color:{TEXT_SECONDARY}; font-size:11px;"
            " background:transparent; border:none;")
        bl.addWidget(self._dev_lbl)

        ev_sep = QFrame()
        ev_sep.setFixedHeight(1)
        _s.themed_ss(ev_sep, "background:{BORDER}; border:none;")
        bl.addWidget(ev_sep)

        ev_hdr = QLabel("EVIDENCE")
        _s.themed_ss(ev_hdr, "color:{TEXT_MUTED}; font-size:9px; font-weight:bold;"
            " letter-spacing:1px; background:transparent; border:none;")
        bl.addWidget(ev_hdr)

        self._ev_events_lbl = QLabel("…")
        self._ev_alerts_lbl = QLabel("…")
        self._ev_cve_lbl    = QLabel("…")
        for lbl in (self._ev_events_lbl, self._ev_alerts_lbl, self._ev_cve_lbl):
            _s.themed_ss(lbl, "color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;")
            bl.addWidget(lbl)

        # ── Ack info (shown when already acknowledged) ────────────────────────
        ack_sep = QFrame()
        ack_sep.setFixedHeight(1)
        _s.themed_ss(ack_sep, "background:{BORDER}; border:none;")
        bl.addWidget(ack_sep)

        self._ack_info_lbl = QLabel()
        self._ack_info_lbl.setWordWrap(True)
        _s.themed_ss(self._ack_info_lbl, "color:{GREEN}; font-size:10px; background:transparent; border:none;")
        self._ack_info_lbl.setVisible(False)
        bl.addWidget(self._ack_info_lbl)

        self._ack_comment_lbl = QLabel()
        self._ack_comment_lbl.setWordWrap(True)
        _s.themed_ss(self._ack_comment_lbl, "color:{TEXT_SECONDARY}; font-size:10px; font-style:italic;"
            " background:transparent; border:none;")
        self._ack_comment_lbl.setVisible(False)
        bl.addWidget(self._ack_comment_lbl)

        # ── Inline ack form (shown when user clicks Acknowledge) ──────────────
        self._ack_form = QFrame()
        self._ack_form.setVisible(False)
        _s.themed_ss(self._ack_form, "QFrame {{ background:{BG_DARK}; border:1px solid {BORDER}; border-radius:3px; }}")
        ack_form_lay = QVBoxLayout(self._ack_form)
        ack_form_lay.setContentsMargins(8, 8, 8, 8)
        ack_form_lay.setSpacing(6)

        ack_form_hdr = QLabel("Acknowledge alert")
        _s.themed_ss(ack_form_hdr, "color:{TEXT_PRIMARY}; font-size:11px; font-weight:bold;"
            " background:transparent; border:none;")
        ack_form_lay.addWidget(ack_form_hdr)

        self._ack_name_edit = QLineEdit()
        self._ack_name_edit.setPlaceholderText("Your name (optional)")
        self._ack_name_edit.setFixedHeight(24)
        _ack_edit_ss = (
            "QLineEdit {{ font-size:10px; color:{TEXT_PRIMARY}; background:{BG_CARD};"
            " border:1px solid {BORDER}; border-radius:2px; padding:0 4px; }}"
        )
        _s.themed_ss(self._ack_name_edit, _ack_edit_ss)
        ack_form_lay.addWidget(self._ack_name_edit)

        self._ack_comment_edit = QLineEdit()
        self._ack_comment_edit.setPlaceholderText("Comment, e.g. tracking JIRA-123 (optional)")
        self._ack_comment_edit.setFixedHeight(24)
        _s.themed_ss(self._ack_comment_edit, _ack_edit_ss)
        ack_form_lay.addWidget(self._ack_comment_edit)

        ack_btn_row = QHBoxLayout()
        self._ack_confirm_btn = QPushButton("✓ Confirm")
        self._ack_confirm_btn.setFixedHeight(24)
        _s.themed_ss(self._ack_confirm_btn, "QPushButton {{ background:{GREEN}; color:{WHITE}; border:none;"
            " border-radius:3px; font-size:10px; font-weight:bold; padding:0 8px; }}"
            "QPushButton:hover {{ opacity:0.9; }}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}")
        self._ack_confirm_btn.clicked.connect(self._on_ack_confirm)

        _ack_cancel_btn = QPushButton("Cancel")
        _ack_cancel_btn.setFixedHeight(24)
        _s.themed_ss(_ack_cancel_btn, "QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none;"
            " font-size:10px; }}"
            "QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_MUTED}; }}")
        _ack_cancel_btn.clicked.connect(lambda: self._ack_form.setVisible(False))
        ack_btn_row.addWidget(self._ack_confirm_btn)
        ack_btn_row.addWidget(_ack_cancel_btn)
        ack_btn_row.addStretch()
        ack_form_lay.addLayout(ack_btn_row)
        bl.addWidget(self._ack_form)

        bl.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ── Actions row ───────────────────────────────────────────────────────
        # Wraps to multiple lines instead of a fixed-height single row: the set of
        # visible buttons (and their text) varies per alert, and a plain QHBoxLayout
        # clips button text whenever the combined width exceeds the 320px drawer.
        acts = QFrame()
        _s.themed_ss(acts, "background:{BG_DARK}; border-top:1px solid {BORDER};")
        alay = _FlowLayout(acts, margin=8, hspacing=6, vspacing=4)

        self._ack_btn = QPushButton("✓ Acknowledge")
        self._ack_btn.setFixedHeight(26)
        self._ack_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._ack_btn, "QPushButton {{ background:{GREEN}; color:{WHITE}; border:none;"
            " border-radius:3px; font-size:10px; font-weight:bold; padding:0 8px; }}"
            "QPushButton:hover {{ opacity:0.9; }}"
            "QPushButton:disabled {{ background:{BG_DARK}; color:{TEXT_MUTED};"
            " border:1px solid {BORDER}; }}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}")
        self._ack_btn.clicked.connect(self._on_ack)

        self._snooze_btn = QPushButton("Snooze 1h")
        self._snooze_btn.setFixedHeight(26)
        self._snooze_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._snooze_btn, lambda: (
            f"QPushButton {{ background:transparent; color:{_s.AMBER};"
            f" border:1px solid {_s.AMBER}; border-radius:3px;"
            f" font-size:10px; padding:0 8px; }}"
            f"QPushButton:hover {{ background:{alpha(_s.AMBER, 0x22)}; }}"
            f"QPushButton:pressed {{ background:{_s.BG_HOVER}; color:{_s.AMBER}; }}"
        ))
        self._snooze_btn.clicked.connect(self._on_snooze)

        self._log_btn = QPushButton("Network Logger →")
        self._log_btn.setFixedHeight(26)
        self._log_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._log_btn.setToolTip(_s.safe_tooltip("Open Network Logger at ±30 min around this alert"))
        _s.themed_ss(self._log_btn, lambda: (
            f"QPushButton {{ background:transparent; color:{_s.ACCENT};"
            f" border:1px solid {_s.ACCENT}; border-radius:3px;"
            f" font-size:10px; padding:0 8px; }}"
            f"QPushButton:hover {{ background:{alpha(_s.ACCENT, 0x22)}; }}"
            f"QPushButton:pressed {{ background:{_s.BG_HOVER}; color:{_s.ACCENT}; }}"
        ))
        self._log_btn.clicked.connect(self._on_view_log_hub)

        self._fix_btn = QPushButton("Fix this →")
        self._fix_btn.setFixedHeight(26)
        self._fix_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._fix_btn, "QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            " border-radius:3px; font-size:10px; font-weight:bold; padding:0 8px; }}"
            "QPushButton:hover {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
            "QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}")
        self._fix_btn.clicked.connect(self._on_go)
        self._fix_btn.setVisible(False)

        self._go_btn = QPushButton("Go to page →")
        self._go_btn.setFixedHeight(26)
        self._go_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._go_btn, "QPushButton {{ background:transparent; color:{ACCENT};"
            " border:1px solid {BORDER}; border-radius:3px;"
            " font-size:10px; padding:0 8px; }}"
            "QPushButton:hover {{ border-color:{ACCENT}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
        self._go_btn.clicked.connect(self._on_go)
        self._go_btn.setVisible(False)

        self._troubleshoot_btn = QPushButton("Troubleshoot →")
        self._troubleshoot_btn.setFixedHeight(26)
        self._troubleshoot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._troubleshoot_btn.setToolTip(_s.safe_tooltip("Open the Troubleshoot hub to find the right fix"))
        _s.themed_ss(self._troubleshoot_btn, "QPushButton {{ background:transparent; color:{ACCENT};"
            " border:1px solid {BORDER}; border-radius:3px;"
            " font-size:10px; padding:0 8px; }}"
            "QPushButton:hover {{ border-color:{ACCENT}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
        self._troubleshoot_btn.clicked.connect(
            lambda: self.navigate_to.emit("Troubleshoot")
        )

        alay.addWidget(self._ack_btn)
        alay.addWidget(self._snooze_btn)
        alay.addWidget(self._log_btn)
        alay.addWidget(self._fix_btn)
        alay.addWidget(self._go_btn)
        alay.addWidget(self._troubleshoot_btn)
        root.addWidget(acts)

    # ── Content population ────────────────────────────────────────────────────

    def _populate(self, alert: dict) -> None:
        sev  = alert.get("severity", "INFO")
        rule = alert.get("rule_name", "—")
        rule_type = alert.get("rule_type", "")
        host = alert.get("host", "—")
        ts   = alert.get("ts", 0)
        msg  = alert.get("message", "")

        sev_colour_name = _SEV_COLOR.get(sev, "ACCENT")
        self._sev_badge.setText(sev)
        _s.themed_ss(self._sev_badge, lambda cn=sev_colour_name: (
            f"color:{_s.WHITE}; font-size:9px; font-weight:bold;"
            f" background:{getattr(_s, cn)}; border-radius:3px; border:none;"
        ))

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

        while self._learn_more_row.count():
            item = self._learn_more_row.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._learn_more_link = None
        term = find_known_term(f"{rule} {msg}")
        if term:
            self._learn_more_link = LearnMoreLink(term)
            self._learn_more_row.addWidget(self._learn_more_link)
            self._learn_more_row.addStretch()

        already_acked = bool(alert.get("acked_ts"))
        self._ack_btn.setEnabled(not already_acked)
        self._ack_btn.setText("✓ Acknowledged" if already_acked else "✓ Acknowledge")
        self._ack_form.setVisible(False)

        if already_acked:
            acked_by = alert.get("acked_by") or "user"
            acked_ts = alert.get("acked_ts")
            acked_date = time.strftime("%Y-%m-%d %H:%M", time.localtime(acked_ts)) if acked_ts else "—"
            self._ack_info_lbl.setText(f"✓ Acknowledged by {acked_by} on {acked_date}")
            self._ack_info_lbl.setVisible(True)
            comment = alert.get("acked_comment") or ""
            if comment:
                self._ack_comment_lbl.setText(f'"{comment}"')
                self._ack_comment_lbl.setVisible(True)
            else:
                self._ack_comment_lbl.setVisible(False)
        else:
            self._ack_info_lbl.setVisible(False)
            self._ack_comment_lbl.setVisible(False)

        self._dev_lbl.setText(self._build_device_context(host))

        # A live per-alert override (e.g. IOT_BEHAVIOR's signal-specific text)
        # takes priority when present -- not persisted, so history rows loaded
        # from the DB never carry this key and fall back to the table.
        fix_text = alert.get("remediation") or remediation_for(rule_type, rule_name=rule)
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
        """Show the inline ack form; actual write happens in _on_ack_confirm."""
        alert = self._current_alert
        if not alert or not self._store:
            return
        if alert.get("acked_ts"):
            return
        self._ack_name_edit.clear()
        self._ack_comment_edit.clear()
        self._ack_form.setVisible(True)

    def _on_ack_confirm(self) -> None:
        alert = self._current_alert
        if not alert or not self._store:
            return
        alert_id = alert.get("id")
        if alert_id is None:
            return
        name    = self._ack_name_edit.text().strip() or "user"
        comment = self._ack_comment_edit.text().strip()
        try:
            self._store.acknowledge_alert(int(alert_id), acked_by=name, comment=comment)
        except Exception:
            return
        self._ack_form.setVisible(False)
        self._ack_btn.setEnabled(False)
        self._ack_btn.setText("✓ Acknowledged")
        self._ack_info_lbl.setText(
            f"✓ Acknowledged by {name} on "
            f"{time.strftime('%Y-%m-%d %H:%M', time.localtime())}"
        )
        self._ack_info_lbl.setVisible(True)
        if comment:
            self._ack_comment_lbl.setText(f'"{comment}"')
            self._ack_comment_lbl.setVisible(True)
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
            _s.themed_ss(lbl, "color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;")
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
            _s.themed_ss(lbl, "color:{TEXT_SECONDARY}; font-size:10px;"
                " background:transparent; border:none;")
