"""
SecurityOverviewPage — full-aggregation Security Audit dashboard.

Layout
──────
  Subtitle
  Hero CTA card     (scan button + status indicators)
  Security Scan KPI row  (high-risk ports | CVE devices | TLS issues | login failures)
  Threat Intel KPI row   (indicators | malicious IPs | blocked domains | last updated)
  Quick-nav pills   (Port Scan → CVE Tracker → TLS & Exposure → Login Test → Threat Intel)
  Findings tabs
    ├─ Security Findings  (port scan HIGH-risk + open CVEs + TLS issues)
    └─ Threat Intel       (top-15 by confidence from ThreatIntelDB)
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import List, Optional

from PyQt6.QtCore import Qt, QSettings, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ui.styles import (
    ACCENT, ACCENT_DARK, ACCENT_LITE, AMBER,
    BG_ALT_ROW, BG_CARD, BORDER, CARD_HDR_BORDER,
    CARD_RADIUS, GREEN, RED, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, TH_BG, TH_TEXT,
    WHITE,
)

try:
    from modules.threat_intel import load_from_cache
    _THREAT_OK = True
except Exception:
    _THREAT_OK = False  # non-fatal — threat intel module may not be available

from ui.widgets.context_menu import install_copy_menu


# ── UI helpers ─────────────────────────────────────────────────────────────────

def _card(title: str = "") -> tuple[QWidget, QVBoxLayout]:
    frame = QFrame()
    frame.setStyleSheet(
        f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
        f" border-radius:{CARD_RADIUS}; }}"
    )
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(12, 10, 12, 12)
    lay.setSpacing(6)
    if title:
        hdr = QLabel(title)
        hdr.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        hdr.setStyleSheet(
            f"color:{TEXT_SECONDARY}; text-transform:uppercase; letter-spacing:1px;"
            f" border-bottom:1px solid {CARD_HDR_BORDER}; padding-bottom:4px;"
        )
        lay.addWidget(hdr)
    return frame, lay


def _kpi_tile(label: str, value: str, color: str) -> QWidget:
    frame = QFrame()
    frame.setStyleSheet(
        f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
        f" border-radius:{CARD_RADIUS}; }}"
    )
    frame.setMinimumHeight(80)
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(14, 10, 14, 10)
    lay.setSpacing(2)
    val_lbl = QLabel(value)
    val_lbl.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
    val_lbl.setStyleSheet(f"color:{color};")
    lbl_lbl = QLabel(label)
    lbl_lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:10px;")
    hint_btn = QPushButton("")
    hint_btn.setFlat(True)
    hint_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    hint_btn.setStyleSheet(
        f"QPushButton {{ color:{ACCENT}; font-size:9px; background:transparent;"
        f" border:none; padding:0; text-align:left; }}"
        f"QPushButton:hover {{ color:{ACCENT_LITE}; }}"
        f"QPushButton:pressed {{ color:{ACCENT_DARK}; }}"
    )
    hint_btn.setVisible(False)
    lay.addStretch()
    lay.addWidget(val_lbl)
    lay.addWidget(lbl_lbl)
    lay.addWidget(hint_btn)
    lay.addStretch()
    frame._val_lbl = val_lbl  # type: ignore[attr-defined]
    frame._hint_btn = hint_btn  # type: ignore[attr-defined]
    return frame


def _make_table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setStretchLastSection(True)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(24)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    t.setStyleSheet(
        f"QTableWidget {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
        f" border:none; font-size:11px; }}"
        f"QHeaderView::section {{ background:{TH_BG}; color:{TH_TEXT};"
        f" font-size:10px; font-weight:600; border:none; padding:3px 6px; }}"
        f"QTableWidget::item:alternate {{ background:{BG_ALT_ROW}; }}"
        f"QTableWidget::item:selected {{ background:{ACCENT}; color:{WHITE}; }}"
    )
    return t


def _severity_color(sev: str) -> str:
    s = sev.lower()
    if s == "critical":
        return RED
    if s in ("high", "warning"):
        return AMBER
    return TEXT_MUTED


def _confidence_color(conf: int) -> str:
    if conf >= 80:
        return RED
    if conf >= 50:
        return AMBER
    return TEXT_SECONDARY


# C-3: Scan types shown in the Scan Status overview card
_AUDIT_SCAN_LABELS: tuple[str, ...] = (
    "Port Scan (TCP)",
    "Port Scan (UDP)",
    "CVE Lookup",
    "Threat Intel",
    "TLS & Exposure",
    "Login Test",
    "OS Detection",
    "Exposed to Internet",
    "Full Device Discovery",
)

# Ordered sequence for the coordinated "Run Security Audit" button.
# Only tools that can fire silently (no host input required, or auto-detected)
# belong here — the audit runs entirely in the background from Security Overview.
_AUDIT_SEQUENCE: tuple[str, ...] = (
    "Port Scan (TCP)",        # auto-uses gateway IP
    "Exposed to Internet",    # no target needed — WAN IP / UPnP check
)

_STATE_COLORS: dict[str, str] = {
    "fresh":   GREEN,
    "stale":   AMBER,
    "running": ACCENT,
    "error":   RED,
    "never":   TEXT_MUTED,
}
_STATE_LABELS: dict[str, str] = {
    "fresh":   "Fresh",
    "stale":   "Stale",
    "running": "Running",
    "error":   "Error",
    "never":   "Never run",
}


# ── Main page ──────────────────────────────────────────────────────────────────

class SecurityOverviewPage(QWidget):
    """Full-aggregation dashboard for the Security Audit section."""

    navigate_to             = pyqtSignal(str)
    scan_requested          = pyqtSignal()
    security_scan_requested = pyqtSignal(list)

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

        # Per-tool audit progress rows (shown only during active audit)
        self._audit_tool_rows: dict = {}  # label → {"dot": QLabel, "state": QLabel, "finding": QLabel}
        self._audit_rows_widget: Optional[QWidget] = None

        self._build_ui()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(5_000)
        self._refresh_timer.timeout.connect(self._load_data)
        self._refresh_timer.start()
        self._load_data()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        subtitle = QLabel(
            "Aggregate findings from all active security scans — run Port Scan, "
            "CVE Tracker, TLS audit, or Login Test to populate each section."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
        )
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

        root.addWidget(self._build_hero_card())

        # Audit progress strip — shown only during a coordinated audit run
        self._audit_progress_bar = QFrame()
        self._audit_progress_bar.setStyleSheet(
            f"QFrame {{ background:{ACCENT}; border-radius:3px; }}"
        )
        self._audit_progress_bar.setFixedHeight(2)
        self._audit_progress_bar.setVisible(False)

        self._audit_progress_lbl = QLabel("")
        self._audit_progress_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
        )
        self._audit_progress_lbl.setVisible(False)

        root.addWidget(self._audit_progress_bar)
        root.addWidget(self._audit_progress_lbl)

        self._audit_rows_widget = self._build_audit_rows_widget()
        self._audit_rows_widget.setVisible(False)
        root.addWidget(self._audit_rows_widget)

        scan_hdr = QLabel("Security Scan Findings")
        scan_hdr.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        scan_hdr.setStyleSheet(
            f"color:{TEXT_SECONDARY}; text-transform:uppercase; letter-spacing:1px;"
            f" background:transparent;"
        )
        root.addWidget(scan_hdr)
        root.addLayout(self._build_scan_kpi_row())

        threat_hdr = QLabel("Threat Intelligence")
        threat_hdr.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        threat_hdr.setStyleSheet(
            f"color:{TEXT_SECONDARY}; text-transform:uppercase; letter-spacing:1px;"
            f" background:transparent;"
        )
        root.addWidget(threat_hdr)
        root.addLayout(self._build_threat_kpi_row())

        root.addLayout(self._build_nav_pills())
        root.addWidget(self._build_findings_tabs(), 1)

    # ── C-3: Scan Status card ─────────────────────────────────────────────────

    def _build_scan_status_card(self) -> QWidget:
        """Build a compact card showing last-run state for each security scan type."""
        card, lay = _card("Scan Status")
        t = _make_table(["Scan", "Status", "Last Run", "Finding"])
        t.setMaximumHeight(len(_AUDIT_SCAN_LABELS) * 24 + 28)
        self._scan_status_table = t
        lay.addWidget(t)

        # Copy-as-Markdown action row — shareable status snapshot for tickets/email
        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        self._copy_md_btn = QPushButton("⧉  Copy as Markdown")
        self._copy_md_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_md_btn.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:9px; background:transparent;"
            f" border:none; padding:2px 0; text-align:left; }}"
            f"QPushButton:hover {{ color:{ACCENT_LITE}; }}"
            f"QPushButton:pressed {{ color:{ACCENT_DARK}; }}"
        )
        self._copy_md_btn.clicked.connect(self._copy_scan_status_md)
        action_row.addWidget(self._copy_md_btn)
        action_row.addStretch()
        self._copy_md_status = QLabel("")
        self._copy_md_status.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:9px; background:transparent;"
        )
        action_row.addWidget(self._copy_md_status)
        lay.addLayout(action_row)

        self._rebuild_scan_status_table()
        return card

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
            pill.setStyleSheet(
                "background:" + _STATE_COLORS.get(state, TEXT_MUTED) + ";"
                " color:" + WHITE + ";"
                " border-radius:8px; padding:1px 8px;"
                " font-size:10px; font-weight:bold; margin:2px;"
            )
            t.setCellWidget(r, 1, pill)
            t.setItem(r, 2, QTableWidgetItem(_scan_age_str(ts) if ts else "Never"))
            t.setItem(r, 3, QTableWidgetItem(verdict or "—"))

    # ── Hero CTA card ──────────────────────────────────────────────────────────

    def _build_hero_card(self) -> QWidget:
        hero = QFrame()
        hero.setObjectName("heroCard")
        hero.setStyleSheet(
            f"QFrame#heroCard {{ background:{BG_CARD}; border:1px solid {ACCENT};"
            f" border-radius:6px; }}"
        )
        outer = QHBoxLayout(hero)
        outer.setContentsMargins(18, 14, 14, 14)
        outer.setSpacing(20)

        left = QVBoxLayout()
        left.setSpacing(4)

        title = QLabel("Security Audit")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY}; border:none; background:transparent;")

        body = QLabel(
            "Run the full security audit to check for open ports, known CVEs, TLS certificate "
            "issues, and threat intelligence indicators across all discovered devices."
        )
        body.setWordWrap(True)
        body.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:10px; border:none; background:transparent;"
        )

        left.addWidget(title)
        left.addWidget(body)
        left.addStretch()

        status_row = QHBoxLayout()
        status_row.setSpacing(16)
        self._last_net_scan_lbl = QLabel("● Network scan: not run")
        self._last_net_scan_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:9px; border:none; background:transparent;"
        )
        self._last_scan_lbl = QLabel("● Threat cache: not loaded")
        self._last_scan_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:9px; border:none; background:transparent;"
        )
        status_row.addWidget(self._last_net_scan_lbl)
        status_row.addWidget(self._last_scan_lbl)
        status_row.addStretch()
        left.addLayout(status_row)

        self._hero_status_lbl = QLabel("")
        self._hero_status_lbl.setStyleSheet(
            f"color:{GREEN}; font-size:9px; border:none; background:transparent;"
        )
        self._hero_status_lbl.setVisible(False)
        left.addWidget(self._hero_status_lbl)

        # Right side: primary audit button + secondary scan button + grade link
        right = QVBoxLayout()
        right.setSpacing(6)

        self._audit_btn = QPushButton("▶  Run Security Audit")
        self._audit_btn.setFixedHeight(40)
        self._audit_btn.setMinimumWidth(185)
        self._audit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._audit_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" font-size:12px; font-weight:bold; padding:0 18px; border-radius:5px; }}"
            f"QPushButton:hover {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
        )
        self._audit_btn.clicked.connect(
            lambda: self.security_scan_requested.emit(list(_AUDIT_SEQUENCE))
        )

        self._scan_btn = QPushButton("Scan Network")
        self._scan_btn.setFixedHeight(28)
        self._scan_btn.setMinimumWidth(185)
        self._scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scan_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{ACCENT}; border:1px solid {BORDER};"
            f" font-size:10px; padding:0 14px; border-radius:4px; }}"
            f"QPushButton:hover {{ background:{BG_ALT_ROW}; color:{ACCENT_LITE}; }}"
            f"QPushButton:pressed {{ background:{BG_ALT_ROW}; color:{ACCENT_DARK}; }}"
        )
        self._scan_btn.clicked.connect(self.scan_requested.emit)

        grade_link = QPushButton("See Network Grade →")
        grade_link.setFlat(True)
        grade_link.setCursor(Qt.CursorShape.PointingHandCursor)
        grade_link.setStyleSheet(
            f"QPushButton {{ color:{TEXT_SECONDARY}; font-size:10px; background:transparent;"
            f" border:none; padding:2px 0; text-align:left; }}"
            f"QPushButton:hover {{ color:{ACCENT}; }}"
            f"QPushButton:pressed {{ color:{ACCENT_DARK}; }}"
        )
        grade_link.clicked.connect(lambda: self.navigate_to.emit("Network Grade"))

        right.addWidget(self._audit_btn)

        # Pre-flight scope toggle
        self._scope_toggle_btn = QPushButton("▼  Show audit scope")
        self._scope_toggle_btn.setFlat(True)
        self._scope_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scope_toggle_btn.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:9px; background:transparent;"
            f" border:none; padding:2px 0; text-align:left; }}"
            f"QPushButton:hover {{ color:{ACCENT_LITE}; }}"
            f"QPushButton:pressed {{ color:{ACCENT_DARK}; }}"
        )

        self._scope_panel = QFrame()
        self._scope_panel.setStyleSheet(
            f"QFrame {{ background:{BG_ALT_ROW}; border:1px solid {BORDER};"
            f" border-radius:3px; padding:4px; }}"
        )
        _scope_lay = QVBoxLayout(self._scope_panel)
        _scope_lay.setContentsMargins(8, 4, 8, 4)
        _scope_lay.setSpacing(2)
        for i, tool in enumerate(_AUDIT_SEQUENCE, 1):
            lbl = QLabel(f"{i}. {tool}")
            lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:9px; border:none;")
            _scope_lay.addWidget(lbl)
        self._scope_panel.setVisible(False)

        self._scope_toggle_btn.clicked.connect(self._toggle_scope_panel)

        right.addWidget(self._scope_toggle_btn)
        right.addWidget(self._scope_panel)

        right.addWidget(self._scan_btn)
        right.addWidget(grade_link)

        outer.addLayout(left, 1)
        _right_w = QWidget()
        _right_w.setLayout(right)
        _right_w.setStyleSheet("background:transparent;")
        outer.addWidget(_right_w, 0, Qt.AlignmentFlag.AlignVCenter)
        return hero

    def _build_audit_rows_widget(self) -> QWidget:
        """Build the per-tool progress widget shown during a coordinated audit."""
        container = QWidget()
        container.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:3px;"
        )
        lay = QVBoxLayout(container)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(3)
        hdr = QLabel("Audit in progress")
        hdr.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        hdr.setStyleSheet(
            f"color:{TEXT_SECONDARY}; border:none; background:transparent;"
        )
        lay.addWidget(hdr)
        for tool in _AUDIT_SEQUENCE:
            row_w = QWidget()
            row_w.setStyleSheet("background:transparent; border:none;")
            row_lay = QHBoxLayout(row_w)
            row_lay.setContentsMargins(0, 1, 0, 1)
            row_lay.setSpacing(6)
            dot = QLabel("●")
            dot.setFixedWidth(14)
            dot.setStyleSheet(
                f"color:{TEXT_MUTED}; font-size:9px; border:none; background:transparent;"
            )
            name_lbl = QLabel(tool)
            name_lbl.setStyleSheet(
                f"color:{TEXT_PRIMARY}; font-size:10px; border:none; background:transparent;"
            )
            name_lbl.setMinimumWidth(140)
            state_lbl = QLabel("Waiting")
            state_lbl.setStyleSheet(
                f"color:{TEXT_MUTED}; font-size:9px; border:none; background:transparent;"
            )
            state_lbl.setMinimumWidth(60)
            finding_lbl = QLabel("")
            finding_lbl.setStyleSheet(
                f"color:{TEXT_SECONDARY}; font-size:9px; border:none; background:transparent;"
            )
            row_lay.addWidget(dot)
            row_lay.addWidget(name_lbl)
            row_lay.addWidget(state_lbl)
            row_lay.addWidget(finding_lbl)
            row_lay.addStretch()
            lay.addWidget(row_w)
            self._audit_tool_rows[tool] = {
                "dot": dot, "state": state_lbl, "finding": finding_lbl,
            }
        return container

    def _set_tool_row_state(self, tool: str, state: str, finding: str = "") -> None:
        """Update one per-tool progress row. state: 'waiting'|'running'|'done'|'error'."""
        row = self._audit_tool_rows.get(tool)
        if not row:
            return
        _dot_color = {
            "waiting": TEXT_MUTED,
            "running": ACCENT,
            "done":    GREEN,
            "error":   RED,
        }.get(state, TEXT_MUTED)
        _state_text = {
            "waiting": "Waiting",
            "running": "Running…",
            "done":    "Done",
            "error":   "Error",
        }.get(state, state)
        row["dot"].setStyleSheet(
            f"color:{_dot_color}; font-size:9px; border:none; background:transparent;"
        )
        row["state"].setText(_state_text)
        row["state"].setStyleSheet(
            f"color:{_dot_color}; font-size:9px; border:none; background:transparent;"
        )
        if finding:
            row["finding"].setText(finding)

    def _toggle_scope_panel(self) -> None:
        currently_shown = not self._scope_panel.isHidden()
        self._scope_panel.setVisible(not currently_shown)
        self._scope_toggle_btn.setText(
            "▲  Hide audit scope" if not currently_shown else "▼  Show audit scope"
        )

    # ── Security Scan KPI row ──────────────────────────────────────────────────

    def _build_scan_kpi_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        self._tile_ports = _kpi_tile("High-Risk Ports", "—", RED)
        self._tile_cves  = _kpi_tile("Devices w/ CVEs", "—", AMBER)
        self._tile_tls   = _kpi_tile("TLS Issues",      "—", AMBER)
        self._tile_cred  = _kpi_tile("Login Failures",  "—", RED)
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
        self._tile_total   = _kpi_tile("Threat Indicators", "—", ACCENT)
        self._tile_ips     = _kpi_tile("Malicious IPs",     "—", RED)
        self._tile_domains = _kpi_tile("Blocked Domains",   "—", AMBER)
        self._tile_updated = _kpi_tile("Last Updated",      "—", TEXT_SECONDARY)
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
            btn.setStyleSheet(
                f"QPushButton {{ color:{ACCENT}; font-size:10px; background:transparent;"
                f" border:1px solid {BORDER}; border-radius:3px; padding:2px 8px; }}"
                f"QPushButton:hover {{ background:{BG_ALT_ROW}; color:{ACCENT_LITE}; }}"
                f"QPushButton:pressed {{ background:{BG_ALT_ROW}; color:{ACCENT_DARK}; }}"
            )
            btn.clicked.connect(lambda _c, t=target: self.navigate_to.emit(t))
            row.addWidget(btn)
        row.addStretch()
        return row

    # ── Findings tab widget ────────────────────────────────────────────────────

    def _build_findings_tabs(self) -> QWidget:
        self._findings_tabs = QTabWidget()
        self._findings_tabs.setStyleSheet(
            f"QTabWidget::pane {{ background:{BG_CARD}; border:1px solid {BORDER}; }}"
            f"QTabBar::tab {{ background:{BG_CARD}; color:{TEXT_SECONDARY};"
            f" padding:4px 14px; border:1px solid {BORDER}; border-bottom:none;"
            f" font-size:10px; }}"
            f"QTabBar::tab:selected {{ color:{TEXT_PRIMARY}; font-weight:600;"
            f" border-top:2px solid {ACCENT}; }}"
        )

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
        self._scan_empty.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:11px; padding:24px; background:transparent;"
        )
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
        self._empty_widget.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:11px; padding:24px; background:transparent;"
        )
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
        self._update_scan_kpis()
        self._update_threat_kpis()
        self._update_scan_table()
        self._update_threat_table()
        self._update_status_lbl()

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
                return TEXT_MUTED
            return alarm if n > 0 else GREEN

        self._tile_ports._val_lbl.setText(_val(self._port_scan_done, port_n))
        self._tile_ports._val_lbl.setStyleSheet(
            f"color:{_col(self._port_scan_done, port_n, RED)};"
            f" font-size:24px; font-weight:bold;"
        )
        store_done = self._store is not None
        self._tile_cves._val_lbl.setText(_val(store_done, cve_n))
        self._tile_cves._val_lbl.setStyleSheet(
            f"color:{_col(store_done, cve_n, AMBER)}; font-size:24px; font-weight:bold;"
        )
        self._tile_tls._val_lbl.setText(_val(store_done, tls_n))
        self._tile_tls._val_lbl.setStyleSheet(
            f"color:{_col(store_done, tls_n, AMBER)}; font-size:24px; font-weight:bold;"
        )
        self._tile_cred._val_lbl.setText(_val(self._cred_scan_done, cred_n))
        self._tile_cred._val_lbl.setStyleSheet(
            f"color:{_col(self._cred_scan_done, cred_n, RED)};"
            f" font-size:24px; font-weight:bold;"
        )
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
                item.setForeground(QColor(color if col == 1 else TEXT_PRIMARY))
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

    def _update_status_lbl(self) -> None:
        if self._last_loaded is None:
            self._last_scan_lbl.setText("● Threat cache: not loaded")
            return
        dt    = datetime.fromtimestamp(self._last_loaded)
        color = TEXT_SECONDARY if self._entries else TEXT_MUTED
        self._last_scan_lbl.setText(f"● Threat cache: {dt.strftime('%H:%M:%S')}")
        self._last_scan_lbl.setStyleSheet(
            f"color:{color}; font-size:9px; border:none; background:transparent;"
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Called by dashboard when the page becomes visible."""
        self._load_data()

    def notify_scan_complete(self) -> None:
        """Called by dashboard after a network device scan finishes."""
        dt = datetime.now()
        self._last_net_scan_lbl.setText(f"● Network scan: {dt.strftime('%H:%M:%S')}")
        self._last_net_scan_lbl.setStyleSheet(
            f"color:{GREEN}; font-size:9px; border:none; background:transparent;"
        )
        self._load_metricstore_data()
        self._update_scan_kpis()
        self._update_scan_table()

    def on_scan_result(self, result: dict) -> None:
        """Called by dashboard after M1 device discovery — shows device count in hero."""
        devices = result.get("devices", [])
        n = len(devices)
        if n > 0:
            self._m1_device_count = n
            label = "device" if n == 1 else "devices"
            self._hero_status_lbl.setText(
                f"● {n} {label} discovered — run security scans to check for vulnerabilities"
            )
            self._hero_status_lbl.setVisible(True)

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
        _n = len(self._port_findings)
        _s = "s" if _n != 1 else ""
        self._set_tool_row_state(
            "Port Scan (TCP)", "done",
            finding=f"{_n} high-risk port{_s}" if _n else "No high-risk ports",
        )

    def on_cred_result(self, result) -> None:
        """Records risk flags from a credentialed (login test) scan result."""
        self._cred_flags    = list(getattr(result, "risk_flags", []) or [])
        self._cred_scan_done = True
        _qs = QSettings("NetSentinel", "NetSentinel")
        _qs.setValue("security/any_scan_done", True)
        _qs.setValue("security/cred_scan_done", True)
        self._update_scan_kpis()
        _n = len(self._cred_flags)
        _s = "s" if _n != 1 else ""
        self._set_tool_row_state(
            "Login Test", "done",
            finding=f"{_n} risk flag{_s}" if _n else "No risk flags",
        )

    # ── Audit coordinator public API ──────────────────────────────────────────

    def set_audit_progress(self, current_step: str, step_n: int, total_steps: int) -> None:
        """Called by dashboard coordinator to show per-tool audit progress."""
        # Show the rows widget on first step
        if self._audit_rows_widget is not None:
            self._audit_rows_widget.setVisible(True)
        # Reset all to waiting on first step
        if step_n == 1:
            for tool in _AUDIT_SEQUENCE:
                self._set_tool_row_state(tool, "waiting")
        # Mark previous step done
        if step_n > 1:
            prev_idx = step_n - 2
            if 0 <= prev_idx < len(_AUDIT_SEQUENCE):
                self._set_tool_row_state(_AUDIT_SEQUENCE[prev_idx], "done")
        # Mark current step running
        if current_step in self._audit_tool_rows:
            self._set_tool_row_state(current_step, "running")
        # Keep legacy label in sync for any callers that read it
        self._audit_progress_lbl.setText(
            f"Step {step_n}/{total_steps}: {current_step}…"
        )
        self._audit_btn.setText("⏳  Audit in progress…")
        self._audit_btn.setEnabled(False)

    def clear_audit_progress(self) -> None:
        """Called by dashboard coordinator when all scans complete."""
        # Mark last running row as done
        for tool, row in self._audit_tool_rows.items():
            if row["state"].text() == "Running…":
                self._set_tool_row_state(tool, "done")
        # Hide rows widget after a short delay (parented timer — RULE-WIN5)
        _t = QTimer(self)
        _t.setSingleShot(True)
        _t.timeout.connect(lambda: (
            self._audit_rows_widget.setVisible(False)
            if self._audit_rows_widget else None
        ))
        _t.start(3000)
        self._audit_progress_lbl.setText("")
        self._audit_btn.setText("▶  Run Security Audit")
        self._audit_btn.setEnabled(True)
