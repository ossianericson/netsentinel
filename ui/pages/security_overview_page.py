"""
SecurityOverviewPage — Security Audit dashboard (first item in Security Audit section).

Layout
──────
  Hero CTA card  (ACCENT border — primary scan actions + status)
  KPI row        (Threat Indicators / Malicious IPs / Blocked Domains / Last Updated)
  Quick nav row  (horizontal pills — Threat Intel / Geo Map / Port Scan / CVEs)
  Recent high-risk findings table (top 15 by confidence)

This page reads from the local ThreatIntelDB cache only — no network calls.
All navigation is via the navigate_to signal wired in dashboard.py.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import List, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT, ACCENT_DARK, ACCENT_LITE, AMBER,
    BG_ALT_ROW, BG_CARD, BORDER, CARD_HDR_BORDER,
    CARD_RADIUS, GREEN, RED, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, TH_BG, TH_TEXT,
    WHITE,
)

try:
    from modules.threat_intel import ThreatEntry, load_from_cache
    _THREAT_OK = True
except Exception:
    _THREAT_OK = False

try:
    from ui.pages.overview_page import _SecurityScanPanel
    _PANEL_OK = True
except Exception:
    _PANEL_OK = False


# ── UI helpers ────────────────────────────────────────────────────────────────

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
    lay.addStretch()
    lay.addWidget(val_lbl)
    lay.addWidget(lbl_lbl)
    lay.addStretch()
    frame._val_lbl = val_lbl  # type: ignore[attr-defined]
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


def _confidence_color(conf: int) -> str:
    if conf >= 80:
        return RED
    if conf >= 50:
        return AMBER
    return TEXT_SECONDARY


# ── Main page ─────────────────────────────────────────────────────────────────

class SecurityOverviewPage(QWidget):
    """Dashboard-style overview for the Security Audit section."""

    navigate_to             = pyqtSignal(str)   # emit label to navigate to a page
    scan_requested          = pyqtSignal()       # trigger full network device scan
    security_scan_requested = pyqtSignal(list)  # open security tool pages

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._entries: List = []
        self._last_loaded: Optional[float] = None

        self._build_ui()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(60_000)
        self._refresh_timer.timeout.connect(self._load_data)
        self._refresh_timer.start()
        self._load_data()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        root.addWidget(self._build_hero_card())
        root.addLayout(self._build_kpi_row())

        if _PANEL_OK:
            self._sec_panel = _SecurityScanPanel(self)
            self._sec_panel.run_clicked.connect(self.security_scan_requested.emit)
            root.addWidget(self._sec_panel)

        root.addWidget(self._build_findings_card(), 1)

    # ── Hero CTA card ─────────────────────────────────────────────────────────

    def _build_hero_card(self) -> QWidget:
        """Full-width card with ACCENT border — describes the network scan action."""
        hero = QFrame()
        hero.setObjectName("heroCard")
        hero.setStyleSheet(
            f"QFrame#heroCard {{ background:{BG_CARD}; border:1px solid {ACCENT};"
            f" border-radius:6px; }}"
        )
        outer = QHBoxLayout(hero)
        outer.setContentsMargins(18, 14, 14, 14)
        outer.setSpacing(20)

        # ── Left: title + description + status dots ───────────────────────────
        left = QVBoxLayout()
        left.setSpacing(4)

        title = QLabel("Network Scan")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY}; border:none; background:transparent;")

        body = QLabel(
            "Discovers every device on your network — IPs, MACs, hostnames, vendor, "
            "and risk level. Results populate the threat findings below and the Devices table."
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

        # ── Right: primary scan button ────────────────────────────────────────
        self._scan_btn = QPushButton("▶  Scan Network")
        self._scan_btn.setFixedHeight(44)
        self._scan_btn.setMinimumWidth(165)
        self._scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scan_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" font-size:13px; font-weight:bold; padding:0 22px; border-radius:5px; }}"
            f"QPushButton:hover {{ background:{ACCENT_LITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        self._scan_btn.clicked.connect(self.scan_requested.emit)

        outer.addLayout(left, 1)
        outer.addWidget(self._scan_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        return hero

    # ── KPI row ───────────────────────────────────────────────────────────────

    def _build_kpi_row(self) -> QHBoxLayout:
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self._tile_total   = _kpi_tile("Threat Indicators", "—", ACCENT)
        self._tile_ips     = _kpi_tile("Malicious IPs",     "—", RED)
        self._tile_domains = _kpi_tile("Blocked Domains",   "—", AMBER)
        self._tile_updated = _kpi_tile("Last Updated",      "—", TEXT_SECONDARY)
        for tile in (self._tile_total, self._tile_ips, self._tile_domains, self._tile_updated):
            kpi_row.addWidget(tile, 1)
        return kpi_row

    # ── Findings card ─────────────────────────────────────────────────────────

    def _build_findings_card(self) -> QWidget:
        findings_card, findings_lay = _card("Recent High-Risk Findings")
        self._findings_table = _make_table(
            ["Indicator", "Type", "Categories", "Confidence", "Source"]
        )
        self._findings_table.setFixedHeight(260)

        # Informative empty state for the findings section
        self._empty_widget = QWidget()
        ew_lay = QVBoxLayout(self._empty_widget)
        ew_lay.setContentsMargins(20, 20, 20, 20)
        ew_lay.setSpacing(6)
        ew_lay.addStretch()
        _show_hdr = QLabel("What this section shows")
        _show_hdr.setStyleSheet(
            f"font-size:10px; font-weight:600; color:{TEXT_SECONDARY};"
            f" text-transform:uppercase; letter-spacing:0.5px; background:transparent;"
        )
        _show_body = QLabel(
            "High-risk IP addresses and domains found on your network, cross-referenced against "
            "threat intelligence feeds — malware, botnets, spam sources, and known attackers."
        )
        _show_body.setWordWrap(True)
        _show_body.setStyleSheet(f"font-size:12px; color:{TEXT_PRIMARY}; background:transparent;")
        _why_hdr = QLabel("Why it matters")
        _why_hdr.setStyleSheet(
            f"font-size:10px; font-weight:600; color:{TEXT_SECONDARY};"
            f" text-transform:uppercase; letter-spacing:0.5px; background:transparent;"
        )
        _why_body = QLabel(
            "Knowing which device contacted a known C2 server turns an abstract alert into an "
            "immediate incident response action."
        )
        _why_body.setWordWrap(True)
        _why_body.setStyleSheet(f"font-size:12px; color:{TEXT_PRIMARY}; background:transparent;")
        _nav_btn = QPushButton("Go to Threat Intelligence →")
        _nav_btn.setFlat(True)
        _nav_btn.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; text-align:left; }}"
            f"QPushButton:hover {{ color:{ACCENT_LITE}; }}"
            f"QPushButton:pressed {{ color:{ACCENT_DARK}; }}"
        )
        _nav_btn.clicked.connect(lambda: self.navigate_to.emit("Threat Intel"))
        for _w in (_show_hdr, _show_body, _why_hdr, _why_body, _nav_btn):
            ew_lay.addWidget(_w)
        ew_lay.addStretch()

        findings_lay.addWidget(self._findings_table)
        findings_lay.addWidget(self._empty_widget)
        return findings_card

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_data(self) -> None:
        if not _THREAT_OK:
            self._show_empty("Threat intelligence module not available.")
            return
        try:
            entries = load_from_cache()
        except Exception:
            entries = []

        self._entries = entries
        self._last_loaded = time.time()
        self._update_kpis()
        self._update_table()
        self._update_status_lbl()

    def _update_kpis(self) -> None:
        entries = self._entries
        total   = len(entries)
        ips     = sum(1 for e in entries if getattr(e, "itype", "") == "ip")
        domains = sum(1 for e in entries if getattr(e, "itype", "") == "domain")

        self._tile_total._val_lbl.setText(str(total))
        self._tile_ips._val_lbl.setText(str(ips))
        self._tile_domains._val_lbl.setText(str(domains))

        if total == 0:
            self._tile_updated._val_lbl.setText("—")
            self._tile_updated._val_lbl.setStyleSheet(f"color:{TEXT_MUTED};")
        else:
            dates = [s for e in entries if (s := getattr(e, "last_seen", "") or "")]
            last = max(dates) if dates else ""
            display = last[:10] if last else "cached"
            self._tile_updated._val_lbl.setText(display)
            self._tile_updated._val_lbl.setStyleSheet(f"color:{TEXT_SECONDARY};")

    def _update_table(self) -> None:
        entries = self._entries
        if not entries:
            self._findings_table.setVisible(False)
            self._empty_widget.setVisible(True)
            return

        self._empty_widget.setVisible(False)
        self._findings_table.setVisible(True)

        sorted_entries = sorted(
            entries,
            key=lambda e: getattr(e, "confidence", 0),
            reverse=True,
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
            color = _confidence_color(conf)
            items[3].setForeground(QColor(color))

            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self._findings_table.setItem(row, col, item)

    def _update_status_lbl(self) -> None:
        if self._last_loaded is None:
            self._last_scan_lbl.setText("● Threat cache: not loaded")
            return
        dt = datetime.fromtimestamp(self._last_loaded)
        has_data = bool(self._entries)
        color = TEXT_SECONDARY if has_data else TEXT_MUTED
        self._last_scan_lbl.setText(f"● Threat cache: {dt.strftime('%H:%M:%S')}")
        self._last_scan_lbl.setStyleSheet(
            f"color:{color}; font-size:9px; border:none; background:transparent;"
        )

    def _show_empty(self, msg: str) -> None:
        self._findings_table.setVisible(False)
        self._empty_widget.setVisible(True)

    # ── Public API ────────────────────────────────────────────────────────────

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
