"""
SecurityOverviewPage — full-aggregation Security Audit dashboard.

Layout
──────
  Subtitle
  Scan Status card  (per-tool last-run state)
  Security Scan KPI row  (high-risk ports | CVE devices | TLS issues | login failures)
  Threat Intel KPI row   (indicators | malicious IPs | blocked domains | last updated)
  Quick-nav pills   (Port Scan → CVE Tracker → TLS & Exposure → Login Test → Threat Intel)
  Findings tabs
    ├─ Security Findings  (port scan HIGH-risk + open CVEs + TLS issues)
    └─ Threat Intel       (top-15 by confidence from ThreatIntelDB)
"""

from __future__ import annotations

import time
from typing import List, Optional

from PyQt6.QtCore import Qt, QSettings, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QScrollArea, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ui.nav.labels import NavLabel as L
from ui.tabs_helpers import _table as _make_table

try:
    from modules.threat_intel import load_from_cache
    _THREAT_OK = True
except Exception:
    _THREAT_OK = False  # non-fatal — threat intel module may not be available

from modules.alert_types import SECURITY_RELEVANT_RULE_TYPES
from ui.widgets.context_menu import install_copy_menu
from ui import styles as _s


# ── UI helpers ─────────────────────────────────────────────────────────────────

def _card(title: str = "") -> tuple[QWidget, QVBoxLayout]:
    frame = QFrame()
    _s.themed_ss(frame, "QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
        " border-radius:{CARD_RADIUS}; }}")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(12, 10, 12, 12)
    lay.setSpacing(6)
    if title:
        hdr = QLabel(title)
        hdr.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        _s.themed_ss(hdr, "color:{TEXT_SECONDARY}; text-transform:uppercase; letter-spacing:1px;"
            " border-bottom:1px solid {CARD_HDR_BORDER}; padding-bottom:4px;")
        lay.addWidget(hdr)
    return frame, lay


def _kpi_tile(label: str, value: str, color: str) -> QWidget:
    # `color` is a theme-token NAME (e.g. "RED"), resolved live via themed_ss.
    frame = QFrame()
    _s.themed_ss(frame, "QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
        " border-radius:{CARD_RADIUS}; }}")
    frame.setMinimumHeight(80)
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(14, 10, 14, 10)
    lay.setSpacing(2)
    val_lbl = QLabel(value)
    val_lbl.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
    _s.themed_ss(val_lbl, lambda tk=color: f"color:{getattr(_s, tk)};")
    lbl_lbl = QLabel(label)
    _s.themed_ss(lbl_lbl, "color:{TEXT_MUTED}; font-size:10px;")
    hint_btn = QPushButton("")
    hint_btn.setFlat(True)
    hint_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    _s.themed_ss(hint_btn, "QPushButton {{ color:{ACCENT}; font-size:9px; background:transparent;"
        " border:none; padding:0; text-align:left; }}"
        "QPushButton:hover {{ color:{ACCENT_LITE}; }}"
        "QPushButton:pressed {{ color:{ACCENT_DARK}; }}")
    hint_btn.setVisible(False)
    lay.addStretch()
    lay.addWidget(val_lbl)
    lay.addWidget(lbl_lbl)
    lay.addWidget(hint_btn)
    lay.addStretch()
    frame._val_lbl = val_lbl  # type: ignore[attr-defined]
    frame._hint_btn = hint_btn  # type: ignore[attr-defined]
    return frame


def _severity_color(sev: str) -> str:
    s = sev.lower()
    if s == "critical":
        return _s.RED
    if s in ("high", "warning"):
        return _s.AMBER
    return _s.TEXT_MUTED


def _confidence_color(conf: int) -> str:
    if conf >= 80:
        return _s.RED
    if conf >= 50:
        return _s.AMBER
    return _s.TEXT_SECONDARY


# C-3: Scan types shown in the Scan Status overview card
_AUDIT_SCAN_LABELS: tuple[str, ...] = (
    L.PORT_SCAN_TCP,
    L.PORT_SCAN_UDP,
    L.CVE_LOOKUP,
    L.THREAT_INTEL,
    L.TLS_EXPOSURE,
    L.LOGIN_TEST,
    L.OS_DETECTION,
    L.EXPOSED_TO_INTERNET,
    L.FULL_DEVICE_DISCOVERY,
)

# Values are theme-token NAMES resolved live via _state_color (below) so the
# Scan Status pills restyle on a theme switch, not only on the next refresh.
_STATE_COLORS: dict[str, str] = {
    "fresh":   "GREEN",
    "stale":   "AMBER",
    "running": "ACCENT",
    "error":   "RED",
    "never":   "TEXT_MUTED",
}
_STATE_LABELS: dict[str, str] = {
    "fresh":   "Fresh",
    "stale":   "Stale",
    "running": "Running",
    "error":   "Error",
    "never":   "Never run",
}


def _state_color(state: str) -> str:
    """Live theme hex for a scan-registry state (falls back to TEXT_MUTED)."""
    return getattr(_s, _STATE_COLORS.get(state, "TEXT_MUTED"))


# ── Main page ──────────────────────────────────────────────────────────────────

class SecurityOverviewPage(QWidget):
    """Full-aggregation dashboard for the Security Audit section."""

    navigate_to             = pyqtSignal(str)
    scan_requested          = pyqtSignal()
    # V6 Sprint 3/4 — (posture_key, enabled); posture_key is one of
    # "port_sweep" | "cve_recheck" | "exposure_check" | "arp_watch" | "dhcp_watch"
    posture_scheduling_changed = pyqtSignal(str, bool)
    # Emitted after an inline Acknowledge — lets app.py refresh the rail badge
    # immediately instead of waiting for the 30s fallback timer.
    alert_acknowledged = pyqtSignal()

    def __init__(self, store=None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._store = store

        # Threat Intel data
        self._entries: List = []
        self._last_loaded: Optional[float] = None

        # Accumulated scan data (per-host, replaced on each scan)
        self._port_findings:  List[dict] = []
        self._cred_flags:     List[str]  = []
        _qs = QSettings("NetSentinel", "NetSentinel")
        self._port_scan_done: bool = _qs.value("security/port_scan_done", False, type=bool)
        self._cred_scan_done: bool = _qs.value("security/cred_scan_done", False, type=bool)

        # MetricStore-derived data (refreshed by _load_metricstore_data)
        self._cve_entries: List[dict] = []
        self._tls_issues:  List       = []

        # C-3: Scan Status card state (populated by _build_scan_status_card)
        self._scan_registry_data: dict = {}
        self._scan_status_table: Optional[QTableWidget] = None

        # Unresolved Security Alerts card state
        self._unacked_alerts: List[dict] = []
        self._unacked_alerts_table: Optional[QTableWidget] = None

        self._build_ui()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(5_000)
        self._refresh_timer.timeout.connect(self._load_data)
        self._refresh_timer.start()
        self._load_data()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border:none; background:transparent; }")

        inner = QWidget()
        _s.themed_ss(inner, "background:{BG_DARK};")
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        root = QVBoxLayout(inner)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        subtitle = QLabel(
            "Aggregate findings from all active security scans — run Port Scan, "
            "CVE Tracker, TLS audit, or Login Test to populate each section."
        )
        subtitle.setWordWrap(True)
        _s.themed_ss(subtitle, "font-size:10px; color:{TEXT_SECONDARY}; background:transparent;")
        root.addWidget(subtitle)

        # Admin/Npcap requirement banner — auto-hides if Npcap is installed
        try:
            from ui.npcap_banner import NpcapMissingBanner
            _npcap_banner = NpcapMissingBanner(self)
            root.addWidget(_npcap_banner)
        except Exception:
            pass  # non-fatal — banner may not be available in all build configs

        # C-3: Scan Status card at top — one row per audit scan type
        root.addWidget(self._build_scan_status_card())

        # Unresolved Security Alerts — the same filtered query that drives the
        # Security Audit rail badge, with an inline Acknowledge per row so the
        # badge is explainable and actionable from this page.
        root.addWidget(self._build_unacked_alerts_card())

        # V6 Sprint 3: opt-in scheduled posture scans (nightly port sweep,
        # CVE re-check, weekly exposure check) — off by default.
        root.addWidget(self._build_posture_scans_card())

        scan_hdr = QLabel("Security Scan Findings")
        scan_hdr.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        _s.themed_ss(scan_hdr, "color:{TEXT_SECONDARY}; text-transform:uppercase; letter-spacing:1px;"
            " background:transparent;")
        root.addWidget(scan_hdr)
        root.addLayout(self._build_scan_kpi_row())

        threat_hdr = QLabel("Threat Intelligence")
        threat_hdr.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        _s.themed_ss(threat_hdr, "color:{TEXT_SECONDARY}; text-transform:uppercase; letter-spacing:1px;"
            " background:transparent;")
        root.addWidget(threat_hdr)
        root.addLayout(self._build_threat_kpi_row())

        root.addLayout(self._build_nav_pills())
        root.addWidget(self._build_findings_tabs(), 1)

    # ── C-3: Scan Status card ─────────────────────────────────────────────────

    def _build_scan_status_card(self) -> QWidget:
        """Build a compact card showing last-run state for each security scan type."""
        card, lay = _card("Scan Status")
        t = _make_table(["Scan", "Status", "Last Run", "Finding"])
        t.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Status column holds a QSS-padded pill widget — ResizeToContents under-measures
        # it (padding isn't reflected in sizeHint() before the widget is polished/shown),
        # so pin a fixed width wide enough for the longest label ("Never run").
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        t.setColumnWidth(1, 90)
        self._scan_status_table = t
        lay.addWidget(t)

        # Copy-as-Markdown action row — shareable status snapshot for tickets/email
        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        self._copy_md_btn = QPushButton("⧉  Copy as Markdown")
        self._copy_md_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._copy_md_btn, "QPushButton {{ color:{ACCENT}; font-size:9px; background:transparent;"
            " border:none; padding:2px 0; text-align:left; }}"
            "QPushButton:hover {{ color:{ACCENT_LITE}; }}"
            "QPushButton:pressed {{ color:{ACCENT_DARK}; }}")
        self._copy_md_btn.clicked.connect(self._copy_scan_status_md)
        action_row.addWidget(self._copy_md_btn)
        action_row.addStretch()
        self._copy_md_status = QLabel("")
        _s.themed_ss(self._copy_md_status, "color:{TEXT_SECONDARY}; font-size:9px; background:transparent;")
        action_row.addWidget(self._copy_md_status)
        lay.addLayout(action_row)

        self._rebuild_scan_status_table()
        return card

    # ── Unresolved Security Alerts ────────────────────────────────────────────

    def _build_unacked_alerts_card(self) -> QWidget:
        """Build the card showing unacknowledged security-relevant alerts.

        Runs the identical filtered query that drives the Security Audit rail
        badge (SECURITY_RELEVANT_RULE_TYPES), so the count on this page always
        matches the badge — this is what makes the badge explainable.
        """
        card, lay = _card("Unresolved Security Alerts")
        t = _make_table(["Rule", "Host", "Severity", "Time", ""])
        t.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        t.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        t.setColumnWidth(4, 110)
        self._unacked_alerts_table = t
        lay.addWidget(t)

        self._unacked_alerts_empty_lbl = QLabel("No unresolved security alerts.")
        _s.themed_ss(self._unacked_alerts_empty_lbl, "color:{TEXT_SECONDARY}; font-size:10px; padding:4px 0;")
        lay.addWidget(self._unacked_alerts_empty_lbl)

        self._rebuild_unacked_alerts_table()
        return card

    def _load_unacked_alerts(self) -> None:
        if self._store is None:
            self._unacked_alerts = []
            return
        try:
            self._unacked_alerts = self._store.get_unacked_alerts(
                rule_types=SECURITY_RELEVANT_RULE_TYPES
            )
        except Exception:
            self._unacked_alerts = []

    def _rebuild_unacked_alerts_table(self) -> None:
        t = self._unacked_alerts_table
        if t is None:
            return
        t.setRowCount(0)
        for row in self._unacked_alerts:
            r = t.rowCount()
            t.insertRow(r)
            t.setItem(r, 0, QTableWidgetItem(row.get("rule_name", "")))
            t.setItem(r, 1, QTableWidgetItem(row.get("host", "")))
            sev = row.get("severity", "")
            sev_item = QTableWidgetItem(sev)
            sev_item.setForeground(QColor(_severity_color(sev)))
            t.setItem(r, 2, sev_item)
            ts = row.get("ts") or 0
            from ui.tabs_helpers import _scan_age_str
            t.setItem(r, 3, QTableWidgetItem(_scan_age_str(ts) if ts else "—"))

            ack_btn = QPushButton("✓ Acknowledge")
            ack_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            _s.themed_ss(ack_btn, "QPushButton {{ color:{ACCENT}; font-size:10px; background:transparent;"
                " border:1px solid {BORDER}; border-radius:3px; padding:2px 6px; }}"
                "QPushButton:hover {{ background:{BG_ALT_ROW}; color:{ACCENT_LITE}; }}"
                "QPushButton:pressed {{ background:{BG_ALT_ROW}; color:{ACCENT_DARK}; }}")
            alert_id = row.get("id")
            ack_btn.clicked.connect(lambda _c=False, aid=alert_id: self._on_ack_unacked_alert(aid))
            t.setCellWidget(r, 4, ack_btn)
            t.setRowHeight(r, 24)

        has_rows = t.rowCount() > 0
        t.setVisible(has_rows)
        self._unacked_alerts_empty_lbl.setVisible(not has_rows)
        if has_rows:
            t.setFixedHeight(t.horizontalHeader().height() + t.verticalHeader().length() + 2)

    def _on_ack_unacked_alert(self, alert_id: Optional[int]) -> None:
        if alert_id is None or self._store is None:
            return
        try:
            self._store.acknowledge_alert(int(alert_id))
        except Exception:
            return  # non-fatal — leave the row in place if the write failed
        self._unacked_alerts = [a for a in self._unacked_alerts if a.get("id") != alert_id]
        self._rebuild_unacked_alerts_table()
        self.alert_acknowledged.emit()

    # ── V6 Sprint 3: scheduled posture scans ─────────────────────────────────

    def _build_posture_scans_card(self) -> QWidget:
        """Opt-in toggles for scheduled posture scans (3.1/3.2/3.4) and passive
        always-on guards (4.1/4.2).

        Each toggle persists to QSettings and emits posture_scheduling_changed
        so app.py can start/stop the matching ProactiveProbeWorker — same
        shape as SpeedTestPage.auto_speedtest_changed.
        """
        card, body = _card("Scheduled Posture Scans")
        body.setContentsMargins(8, 8, 8, 8)
        body.setSpacing(4)

        note = QLabel(
            "Off by default. When enabled, these run automatically in the "
            "background and alert you only on what changed or was detected "
            "since the last run — not just while their own page is open."
        )
        note.setWordWrap(True)
        _s.themed_ss(note, "color:{TEXT_SECONDARY}; font-size:10px;")
        body.addWidget(note)

        self._posture_checks: dict[str, QCheckBox] = {}
        _toggles = (
            ("port_sweep", "Nightly port-scan sweep of known devices — alerts on newly opened ports"),
            ("cve_recheck", "Twice-daily CVE re-check for already-tracked services"),
            ("exposure_check", "Weekly internet-exposure check — alerts on newly exposed ports"),
            ("arp_watch", "Background ARP spoof watch — alerts on gateway hijack, IP takeover, or MAC clone"),
            ("dhcp_watch", "Background rogue DHCP watch — alerts on offers from an unexpected server"),
        )
        for key, label in _toggles:
            chk = QCheckBox(label)
            _s.themed_ss(chk, "QCheckBox{{color:{TEXT_PRIMARY};font-size:11px;}}")
            chk.setChecked(QSettings("NetSentinel", "NetSentinel").value(
                f"posture/{key}_enabled", False, type=bool
            ))
            chk.stateChanged.connect(lambda _state, k=key: self._on_posture_toggle_changed(k))
            self._posture_checks[key] = chk
            body.addWidget(chk)

        return card

    def _on_posture_toggle_changed(self, key: str) -> None:
        chk = self._posture_checks[key]
        enabled = chk.isChecked()
        QSettings("NetSentinel", "NetSentinel").setValue(f"posture/{key}_enabled", enabled)
        self.posture_scheduling_changed.emit(key, enabled)

    def _copy_scan_status_md(self) -> None:
        """Copy the current scan registry as a Markdown table to the clipboard."""
        from modules.scan_status_md import render_scan_status_md

        registry = getattr(self, "_scan_registry_data", {}) or {}
        md = render_scan_status_md(registry, _AUDIT_SCAN_LABELS)
        clip = QApplication.clipboard()
        if clip is not None:
            clip.setText(md)
        self._copy_md_status.setText("Copied to clipboard")
        # parented one-shot so it is auto-destroyed with the widget (RULE-WIN5)
        _t = QTimer(self)
        _t.setSingleShot(True)
        _t.timeout.connect(lambda: self._copy_md_status.setText(""))
        _t.start(2500)

    def update_scan_registry(self, registry: dict) -> None:
        """Receive live scan registry updates from _nav_set_scan_state (C-3)."""
        self._scan_registry_data = registry
        if self._scan_status_table is not None:
            self._rebuild_scan_status_table()

    def _rebuild_scan_status_table(self) -> None:
        """Repopulate the Scan Status table from current registry data."""
        from ui.tabs_helpers import _scan_age_str
        registry = getattr(self, "_scan_registry_data", {})
        t = self._scan_status_table
        if t is None:
            return
        t.setRowCount(0)
        for label in _AUDIT_SCAN_LABELS:
            entry = registry.get(label, {})
            state = entry.get("state", "never")
            ts = entry.get("ts") or 0.0
            verdict = entry.get("verdict") or ""
            r = t.rowCount()
            t.insertRow(r)
            t.setItem(r, 0, QTableWidgetItem(label))
            pill = QLabel(_STATE_LABELS.get(state, "Never run"))
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            _s.themed_ss(pill, lambda st=state: (
                "background:" + _state_color(st) + ";"
                " color:" + _s.WHITE + ";"
                " border-radius:8px; padding:1px 8px;"
                " font-size:10px; font-weight:bold; margin:2px;"
            ))
            t.setCellWidget(r, 1, pill)
            t.setItem(r, 2, QTableWidgetItem(_scan_age_str(ts) if ts else "Never"))
            t.setItem(r, 3, QTableWidgetItem(verdict or "—"))
        # Exact-fit height — no internal scrollbar, all rows always visible.
        t.setFixedHeight(t.horizontalHeader().height() + t.verticalHeader().length() + 2)

    # ── Security Scan KPI row ──────────────────────────────────────────────────

    def _build_scan_kpi_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        self._tile_ports = _kpi_tile("High-Risk Ports", "—", "RED")
        self._tile_cves  = _kpi_tile("Devices w/ CVEs", "—", "AMBER")
        self._tile_tls   = _kpi_tile("TLS Issues",      "—", "AMBER")
        self._tile_cred  = _kpi_tile("Login Failures",  "—", "RED")
        self._tile_ports._hint_btn.setText("→ Run Port Scan")
        self._tile_ports._hint_btn.clicked.connect(
            lambda: self.navigate_to.emit("Port Scan (TCP)")
        )
        self._tile_cred._hint_btn.setText("→ Run Login Test")
        self._tile_cred._hint_btn.clicked.connect(
            lambda: self.navigate_to.emit("Login Test")
        )
        for tile in (self._tile_ports, self._tile_cves, self._tile_tls, self._tile_cred):
            row.addWidget(tile, 1)
        return row

    # ── Threat Intel KPI row ───────────────────────────────────────────────────

    def _build_threat_kpi_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        self._tile_total   = _kpi_tile("Threat Indicators", "—", "ACCENT")
        self._tile_ips     = _kpi_tile("Malicious IPs",     "—", "RED")
        self._tile_domains = _kpi_tile("Blocked Domains",   "—", "AMBER")
        self._tile_updated = _kpi_tile("Last Updated",      "—", "TEXT_SECONDARY")
        self._tile_total._hint_btn.setText("→ Refresh Threat Intel")
        self._tile_total._hint_btn.clicked.connect(
            lambda: self.navigate_to.emit("Threat Intel")
        )
        for tile in (self._tile_total, self._tile_ips, self._tile_domains, self._tile_updated):
            row.addWidget(tile, 1)
        return row

    # ── Quick-nav pills ────────────────────────────────────────────────────────

    def _build_nav_pills(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        _pills = [
            ("Port Scan →",      "Port Scan (TCP)"),
            ("CVE Tracker →",    "CVE Lookup"),
            ("TLS & Exposure →", "TLS & Exposure"),
            ("Login Test →",     "Login Test"),
            ("Threat Intel →",   "Threat Intel"),
            ("Geo Map →",        "Geolocation Map"),
        ]
        for label, target in _pills:
            btn = QPushButton(label)
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            _s.themed_ss(btn, "QPushButton {{ color:{ACCENT}; font-size:10px; background:transparent;"
                " border:1px solid {BORDER}; border-radius:3px; padding:2px 8px; }}"
                "QPushButton:hover {{ background:{BG_ALT_ROW}; color:{ACCENT_LITE}; }}"
                "QPushButton:pressed {{ background:{BG_ALT_ROW}; color:{ACCENT_DARK}; }}")
            btn.clicked.connect(lambda _c, t=target: self.navigate_to.emit(t))
            row.addWidget(btn)
        row.addStretch()
        return row

    # ── Findings tab widget ────────────────────────────────────────────────────

    def _build_findings_tabs(self) -> QWidget:
        self._findings_tabs = QTabWidget()
        _s.themed_ss(self._findings_tabs, "QTabWidget::pane {{ background:{BG_CARD}; border:1px solid {BORDER}; }}"
            "QTabBar::tab {{ background:{BG_CARD}; color:{TEXT_SECONDARY};"
            " padding:4px 14px; border:1px solid {BORDER}; border-bottom:none;"
            " font-size:10px; }}"
            "QTabBar::tab:selected {{ color:{TEXT_PRIMARY}; font-weight:600;"
            " border-top:2px solid {ACCENT}; }}")

        # ── Tab 1: Security Findings ──────────────────────────────────────────
        sec_tab = QWidget()
        sec_lay = QVBoxLayout(sec_tab)
        sec_lay.setContentsMargins(8, 8, 8, 8)
        self._scan_table = _make_table(["Type", "Severity", "Host", "Finding"])

        def _scan_copy():
            r = self._scan_table.currentRow()
            it = self._scan_table.item(r, 3)
            if r >= 0 and it:
                from PyQt6.QtWidgets import QApplication as _A
                _A.clipboard().setText(it.text())

        def _scan_view_details():
            r = self._scan_table.currentRow()
            if r < 0:
                return
            from PyQt6.QtWidgets import QMessageBox
            type_it  = self._scan_table.item(r, 0)
            sev_it   = self._scan_table.item(r, 1)
            host_it  = self._scan_table.item(r, 2)
            find_it  = self._scan_table.item(r, 3)
            typ     = type_it.text()  if type_it  else ""
            sev     = sev_it.text()   if sev_it   else ""
            host    = host_it.text()  if host_it  else ""
            finding = find_it.text()  if find_it  else ""
            QMessageBox.information(self, "Finding Details",
                f"<b>Type:</b> {typ}<br>"
                f"<b>Severity:</b> {sev}<br>"
                f"<b>Host:</b> {host}<br><br>"
                f"<b>Finding:</b><br>{finding}")

        install_copy_menu(self._scan_table, [
            ("separator",    None),
            ("Copy finding", _scan_copy),
            ("separator",    None),
            ("View details", _scan_view_details),
        ])

        self._scan_empty = QLabel(
            "No security findings yet.\n\n"
            "Run Port Scan (TCP) to detect high-risk open ports.\n"
            "Run CVE Tracker to surface open vulnerabilities.\n"
            "Run TLS & Exposure to check certificate health.\n"
            "Run Login Test to detect credential weaknesses."
        )
        self._scan_empty.setWordWrap(True)
        self._scan_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _s.themed_ss(self._scan_empty, "color:{TEXT_MUTED}; font-size:11px; padding:24px; background:transparent;")
        sec_lay.addWidget(self._scan_table)
        sec_lay.addWidget(self._scan_empty)
        self._findings_tabs.addTab(sec_tab, "Security Findings")

        # ── Tab 2: Threat Intel ───────────────────────────────────────────────
        threat_tab = QWidget()
        threat_lay = QVBoxLayout(threat_tab)
        threat_lay.setContentsMargins(8, 8, 8, 8)
        self._findings_table = _make_table(
            ["Indicator", "Type", "Categories", "Confidence", "Source"]
        )

        def _copy_indicator():
            r = self._findings_table.currentRow()
            it = self._findings_table.item(r, 0)
            if r >= 0 and it:
                from PyQt6.QtWidgets import QApplication as _A2
                _A2.clipboard().setText(it.text())

        def _how_to_fix():
            r = self._findings_table.currentRow()
            if r < 0:
                return
            from PyQt6.QtWidgets import QMessageBox
            ind_it  = self._findings_table.item(r, 0)
            type_it = self._findings_table.item(r, 1)
            cat_it  = self._findings_table.item(r, 2)
            ind  = ind_it.text()  if ind_it  else "this indicator"
            typ  = type_it.text() if type_it else "unknown type"
            cats = cat_it.text()  if cat_it  else "unknown categories"
            QMessageBox.information(self, "How to Fix",
                f"<b>{ind}</b> ({typ}) — {cats}<br><br>"
                "<b>Recommended steps:</b><br>"
                "1. Identify which device contacted this indicator.<br>"
                "2. Block the indicator at your firewall or DNS level.<br>"
                "3. Run a full port scan and CVE check on the affected device.<br>"
                "4. If the device is a workstation, run an antimalware scan immediately.<br>"
                "5. Check AbuseIPDB and VirusTotal for additional context.")

        install_copy_menu(self._findings_table, [
            ("separator",      None),
            ("Copy indicator", _copy_indicator),
            ("separator",      None),
            ("How to Fix",     _how_to_fix),
        ])

        self._empty_widget = QLabel(
            "No threat intelligence data.\n\n"
            "Navigate to Threat Intel and run an intelligence update."
        )
        self._empty_widget.setWordWrap(True)
        self._empty_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _s.themed_ss(self._empty_widget, "color:{TEXT_MUTED}; font-size:11px; padding:24px; background:transparent;")
        threat_lay.addWidget(self._findings_table)
        threat_lay.addWidget(self._empty_widget)
        self._findings_tabs.addTab(threat_tab, "Threat Intel")

        return self._findings_tabs

    # ── Data loading ───────────────────────────────────────────────────────────

    def _load_data(self) -> None:
        if _THREAT_OK:
            try:
                self._entries = load_from_cache()
            except Exception:
                self._entries = []
            self._last_loaded = time.time()

        self._load_metricstore_data()
        self._load_unacked_alerts()
        self._update_scan_kpis()
        self._update_threat_kpis()
        self._update_scan_table()
        self._update_threat_table()
        self._rebuild_unacked_alerts_table()

    def _load_metricstore_data(self) -> None:
        if self._store is None:
            return
        try:
            self._cve_entries = self._store.list_cve_lifecycles(state_filter="Open")
        except Exception:
            self._cve_entries = []
        try:
            certs = self._store.query_cert_status(hours=720)
            self._tls_issues = [
                c for c in certs
                if c.is_expired or c.is_self_signed
                or (c.days_remaining is not None and c.days_remaining < 30)
            ]
        except Exception:
            self._tls_issues = []

    def _update_scan_kpis(self) -> None:
        port_n = len(self._port_findings)
        cve_n  = len(set(e.get("host", "") for e in self._cve_entries if e.get("host")))
        tls_n  = len(self._tls_issues)
        cred_n = len(self._cred_flags)

        def _val(done: bool, n: int) -> str:
            return str(n) if done else "—"

        def _col(done: bool, n: int, alarm: str) -> str:
            if not done:
                return _s.TEXT_MUTED
            return alarm if n > 0 else _s.GREEN

        self._tile_ports._val_lbl.setText(_val(self._port_scan_done, port_n))
        _s.themed_ss(self._tile_ports._val_lbl, lambda d=self._port_scan_done, n=port_n: (
            f"color:{_col(d, n, _s.RED)};"
            f" font-size:24px; font-weight:bold;"
        ))
        store_done = self._store is not None
        self._tile_cves._val_lbl.setText(_val(store_done, cve_n))
        _s.themed_ss(self._tile_cves._val_lbl, lambda d=store_done, n=cve_n: (
            f"color:{_col(d, n, _s.AMBER)}; font-size:24px; font-weight:bold;"
        ))
        self._tile_tls._val_lbl.setText(_val(store_done, tls_n))
        _s.themed_ss(self._tile_tls._val_lbl, lambda d=store_done, n=tls_n: (
            f"color:{_col(d, n, _s.AMBER)}; font-size:24px; font-weight:bold;"
        ))
        self._tile_cred._val_lbl.setText(_val(self._cred_scan_done, cred_n))
        _s.themed_ss(self._tile_cred._val_lbl, lambda d=self._cred_scan_done, n=cred_n: (
            f"color:{_col(d, n, _s.RED)};"
            f" font-size:24px; font-weight:bold;"
        ))
        self._tile_ports._hint_btn.setVisible(not self._port_scan_done)
        self._tile_cred._hint_btn.setVisible(not self._cred_scan_done)

    def _update_threat_kpis(self) -> None:
        entries = self._entries
        total   = len(entries)
        ips     = sum(1 for e in entries if getattr(e, "itype", "") == "ip")
        domains = sum(1 for e in entries if getattr(e, "itype", "") == "domain")

        self._tile_total._val_lbl.setText(str(total))
        self._tile_ips._val_lbl.setText(str(ips))
        self._tile_domains._val_lbl.setText(str(domains))

        if total == 0:
            self._tile_updated._val_lbl.setText("—")
        else:
            dates = [s for e in entries if (s := getattr(e, "last_seen", "") or "")]
            last = max(dates) if dates else ""
            self._tile_updated._val_lbl.setText(last[:10] if last else "cached")
        self._tile_total._hint_btn.setVisible(total == 0)

    def _update_scan_table(self) -> None:
        t = self._scan_table
        t.setRowCount(0)

        def _row(type_: str, severity: str, host: str, finding: str) -> None:
            r = t.rowCount()
            t.insertRow(r)
            color = _severity_color(severity)
            for col, val in enumerate([type_, severity, host, finding]):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(color if col == 1 else _s.TEXT_PRIMARY))
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                )
                t.setItem(r, col, item)

        for pf in self._port_findings:
            _row("Port", "High", pf.get("host", ""),
                 f"Port {pf['port']} ({pf.get('service', '')})")

        for cve in self._cve_entries:
            sev  = cve.get("severity", "Warning") or "Warning"
            cvss = cve.get("cvss_score", 0.0) or 0.0
            _row("CVE", sev, cve.get("host", ""),
                 f"{cve.get('cve_id', '')} — CVSS {cvss:.1f}")

        for c in self._tls_issues:
            if c.is_expired:
                desc, sev = "Certificate expired", "Critical"
            elif c.is_self_signed:
                desc, sev = "Self-signed certificate", "High"
            else:
                rem = c.days_remaining or 0
                desc = f"Expires in {rem} day{'s' if rem != 1 else ''}"
                sev  = "High" if rem < 7 else "Warning"
            _row("TLS", sev, f"{c.host}:{c.port}", desc)

        has = t.rowCount() > 0
        t.setVisible(has)
        self._scan_empty.setVisible(not has)

    def _update_threat_table(self) -> None:
        entries = self._entries
        if not entries:
            self._findings_table.setVisible(False)
            self._empty_widget.setVisible(True)
            return

        self._empty_widget.setVisible(False)
        self._findings_table.setVisible(True)
        sorted_entries = sorted(
            entries, key=lambda e: getattr(e, "confidence", 0), reverse=True,
        )[:15]

        self._findings_table.setRowCount(0)
        for entry in sorted_entries:
            row = self._findings_table.rowCount()
            self._findings_table.insertRow(row)
            conf = getattr(entry, "confidence", 0)
            cats = getattr(entry, "categories", "") or ""
            if isinstance(cats, (list, tuple)):
                cats = ", ".join(cats)
            items = [
                QTableWidgetItem(getattr(entry, "indicator", "—")),
                QTableWidgetItem(getattr(entry, "itype", "—")),
                QTableWidgetItem(cats),
                QTableWidgetItem(f"{conf}%"),
                QTableWidgetItem(getattr(entry, "source", "—")),
            ]
            items[3].setForeground(QColor(_confidence_color(conf)))
            for col, item in enumerate(items):
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                )
                self._findings_table.setItem(row, col, item)

    # ── Public API ─────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Called by dashboard when the page becomes visible."""
        self._load_data()

    def notify_scan_complete(self) -> None:
        """Called by dashboard after a network device scan finishes."""
        self._load_metricstore_data()
        self._update_scan_kpis()
        self._update_scan_table()

    def on_scan_result(self, result: dict) -> None:
        """Called by dashboard after M1 device discovery."""
        devices = result.get("devices", [])
        n = len(devices)
        if n > 0:
            self._m1_device_count = n

    def on_port_scan_result(self, result) -> None:
        """Accumulates HIGH-risk open port findings from any port scan result."""
        host = getattr(result, "host", "") or getattr(result, "ip", "") or "unknown"
        # Replace prior findings for this host
        self._port_findings = [pf for pf in self._port_findings if pf.get("host") != host]
        try:
            from modules.port_scanner import HIGH_RISK_PORTS as _HRP
        except Exception:
            _HRP = set()
        for p in getattr(result, "open_ports", []):
            # PortResult has .risk; SYNPortResult does not — fall back to port-number check
            risk = getattr(p, "risk", None)
            if risk is None:
                risk = "HIGH" if p.port in _HRP else "LOW"
            if risk == "HIGH":
                svc = getattr(p, "name", getattr(p, "service", "")) or ""
                self._port_findings.append({"host": host, "port": p.port, "service": svc})
        self._port_scan_done = True
        _qs = QSettings("NetSentinel", "NetSentinel")
        _qs.setValue("security/any_scan_done", True)
        _qs.setValue("security/port_scan_done", True)
        self._update_scan_kpis()
        self._update_scan_table()

    def on_cred_result(self, result) -> None:
        """Records risk flags from a credentialed (login test) scan result."""
        self._cred_flags    = list(getattr(result, "risk_flags", []) or [])
        self._cred_scan_done = True
        _qs = QSettings("NetSentinel", "NetSentinel")
        _qs.setValue("security/any_scan_done", True)
        _qs.setValue("security/cred_scan_done", True)
        self._update_scan_kpis()
