"""
tabs_diag.py — _DiagTabsMixin: diagnostics tab builder + event handlers.

Extracted from ui/tabs.py (Sprint 8). Logger tab + retention helpers were extracted
to ui/tabs_logger.py (Sprint 15). MTR tab + advanced tools were extracted to
ui/tabs_diag_extra.py (Sprint 13); inheritance wired in Sprint 16.
"""
from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui import styles as _s
from ui.tabs_helpers import _table
from ui.tabs_diag_extra import _DiagExtraTabsMixin
from ui.tabs_logger import _LoggerTabMixin


class _DiagTabsMixin(_DiagExtraTabsMixin, _LoggerTabMixin):
    """Mixin providing diagnostics/logger/tools tab builders + event handlers.

    Extracted from ui/tabs.py (Sprint 8).
    MTR/tools extracted to ui/tabs_diag_extra.py (Sprint 13); wired Sprint 16.
    Logger tab extracted to ui/tabs_logger.py (Sprint 15).
    """

    # ── Diagnostics tab ───────────────────────────────────────────────────────

    def _build_diagnostics_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        # Top bar
        top = QHBoxLayout()
        title = QLabel("⚡  Network Health & Diagnostics")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        _s.themed_ss(title, "color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        top.addWidget(title)
        top.addStretch()
        self._btn_diag = QPushButton("⚡  Run Diagnostics")
        self._btn_diag.setObjectName("btnDiag")
        self._btn_diag.setFixedHeight(34)
        self._btn_diag.clicked.connect(self._start_diagnostics)
        top.addWidget(self._btn_diag)
        lay.addLayout(top)

        self._diag_status_lbl = QLabel("Click 'Run Diagnostics' to test connectivity and performance.")
        _s.themed_ss(self._diag_status_lbl, "color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(self._diag_status_lbl)

        # Summary row
        summary_row = QHBoxLayout()
        self._diag_speed_lbl  = self._stat_label("Download", "—")
        self._diag_public_lbl = self._stat_label("Public IP", "—")
        self._diag_dns_lbl    = self._stat_label("System DNS", "—")
        self._diag_gw_lbl     = self._stat_label("Gateway RTT", "—")
        for w2 in (self._diag_gw_lbl, self._diag_speed_lbl,
                   self._diag_dns_lbl, self._diag_public_lbl):
            summary_row.addWidget(w2)
        summary_row.addStretch()
        lay.addLayout(summary_row)

        # Two-column detail: Ping | DNS
        cols = QHBoxLayout()
        cols.setSpacing(10)

        left = QVBoxLayout()
        left.addWidget(QLabel("  Ping Tests"))
        self._diag_ping_table = _table(["Host", "IP", "RTT (ms)", "Status"])
        self._diag_ping_table.setColumnWidth(0, 120)
        self._diag_ping_table.setColumnWidth(1, 120)
        self._diag_ping_table.setColumnWidth(2, 70)
        left.addWidget(self._diag_ping_table)

        right = QVBoxLayout()
        right.addWidget(QLabel("  DNS Speed"))
        self._diag_dns_table = _table(["DNS Server", "Latency (ms)", "Resolved IP", "Status"])
        self._diag_dns_table.setColumnWidth(0, 110)
        self._diag_dns_table.setColumnWidth(1, 100)
        self._diag_dns_table.setColumnWidth(2, 110)
        right.addWidget(self._diag_dns_table)

        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        lay.addLayout(cols)

        # HTTP connectivity
        http_row = QHBoxLayout()
        http_lbl = QLabel("  Internet Connectivity:")
        _s.themed_ss(http_lbl, "color:{TEXT_SECONDARY}; font-size:11px;")
        http_row.addWidget(http_lbl)
        self._diag_http_labels: list = []
        for name, _ in [("Google 204", ""), ("Cloudflare", ""), ("Apple captive", "")]:
            lbl = QLabel(f"● {name}: —")
            _s.themed_ss(lbl, "color:{TEXT_SECONDARY}; font-size:11px; padding:0 10px;")
            self._diag_http_labels.append(lbl)
            http_row.addWidget(lbl)
        http_row.addStretch()
        lay.addLayout(http_row)

        # DNS Leak
        leak_row = QHBoxLayout()
        leak_lbl_hdr = QLabel("  DNS Leak Test:")
        _s.themed_ss(leak_lbl_hdr, "color:{TEXT_SECONDARY}; font-size:11px;")
        leak_row.addWidget(leak_lbl_hdr)
        self._diag_leak_lbl = QLabel("—")
        _s.themed_ss(self._diag_leak_lbl, "color:{TEXT_SECONDARY}; font-size:11px; padding-left:10px;")
        self._diag_leak_lbl.setWordWrap(True)
        leak_row.addWidget(self._diag_leak_lbl, 1)
        lay.addLayout(leak_row)
        self._diag_leak_table = _table(["Resolver IP", "Country", "ASN / Org"])
        self._diag_leak_table.setColumnWidth(0, 130)
        self._diag_leak_table.setColumnWidth(1, 120)
        self._diag_leak_table.setMaximumHeight(110)
        lay.addWidget(self._diag_leak_table)

        # Traceroute
        trace_lbl = QLabel("  Traceroute to 8.8.8.8:")
        _s.themed_ss(trace_lbl, "color:{TEXT_SECONDARY}; font-size:11px; padding-top:4px;")
        lay.addWidget(trace_lbl)
        self._diag_trace_table = _table(["Hop", "IP Address", "RTT (ms)"])
        self._diag_trace_table.setColumnWidth(0, 50)
        self._diag_trace_table.setColumnWidth(1, 160)
        lay.addWidget(self._diag_trace_table, 1)
        return w
