"""
kpi_bar.py — _KpiBarMixin: four-tile KPI bar for the Devices page.

Extracted from ui/dashboard.py (Sprint 13) to keep that file within budget.
Dashboard inherits _KpiBarMixin.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from ui.styles import (
    ACCENT, AMBER, BG_CARD, BORDER,
    GREEN, RED, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    WHITE,
)


class _KpiBarMixin:
    """Mixin providing the four KPI tiles for the Devices page top bar.

    Extracted from ui/dashboard.py (Sprint 13).
    """

    def _build_kpi_bar(self) -> QWidget:
        """
        Four KPI tiles: Total Nodes | Critical Risks | Unauthorized | Scan Status.
        Sits at the top of the Devices page. Values are updated by _update_kpi_tiles().
        """
        bar = QWidget()
        bar.setFixedHeight(56)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 6)
        row.setSpacing(8)

        def _tile(dot_color: str, label: str, start_val: str, start_color: str):
            """Return (tile QFrame, dot QLabel, value QLabel)."""
            tile = QFrame()
            tile.setObjectName("card")
            tile.setStyleSheet(
                f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
                f"border-left:3px solid {dot_color};border-radius:0px;}}"
            )
            vl = QVBoxLayout(tile)
            vl.setContentsMargins(8, 4, 8, 4)
            vl.setSpacing(1)

            hdr = QHBoxLayout()
            hdr.setSpacing(4)
            dot = QLabel("●")
            dot.setStyleSheet(
                f"color:{dot_color}; font-size:9px; background:transparent; border:none;"
            )
            lbl = QLabel(label.upper())
            lbl.setStyleSheet(
                f"color:{TEXT_MUTED}; font-size:9px; font-weight:bold;"
                "letter-spacing:0.5px; background:transparent; border:none;"
            )
            hdr.addWidget(dot)
            hdr.addWidget(lbl)
            hdr.addStretch()
            vl.addLayout(hdr)

            val = QLabel(start_val)
            val.setStyleSheet(
                f"color:{start_color}; font-size:18px; font-weight:bold;"
                "background:transparent; border:none;"
            )
            vl.addWidget(val)
            return tile, dot, val

        t1, self._kpi_nodes_dot,  self._kpi_nodes_val  = _tile(ACCENT,          "Total Nodes",    "—", TEXT_MUTED)
        t2, self._kpi_risk_dot,   self._kpi_risk_val   = _tile(TEXT_MUTED,      "Critical Risks", "—", TEXT_MUTED)
        t3, self._kpi_unauth_dot, self._kpi_unauth_val = _tile(TEXT_MUTED,      "Unauthorized",   "—", TEXT_MUTED)
        t4, self._kpi_scan_dot,   self._kpi_scan_val   = _tile(TEXT_SECONDARY,  "Scan Status",    "Ready", TEXT_SECONDARY)

        # Keep references to the tiles themselves so we can update border colours
        self._kpi_risk_tile  = t2
        self._kpi_unauth_tile = t3

        for t in (t1, t2, t3, t4):
            row.addWidget(t, 1)
        return bar

    def _update_kpi_tiles(self, data: dict) -> None:
        """Refresh KPI tile values from a completed scan result dict."""
        devices    = data.get("devices", [])
        total      = len(devices)
        high_risk  = sum(
            1 for d in devices
            if (d.risk_level if not isinstance(d, dict) else d.get("risk_level", "")) in ("HIGH", "CRITICAL")
        )
        unauth     = data.get("high_risk_count", high_risk)

        # Nodes tile — always blue
        self._kpi_nodes_val.setText(str(total))
        self._kpi_nodes_val.setStyleSheet(
            f"color:{ACCENT}; font-size:18px; font-weight:bold;"
            "background:transparent; border:none;"
        )

        # Critical risks tile — green if 0, amber if 1-2, red if 3+
        risk_color = GREEN if high_risk == 0 else (AMBER if high_risk <= 2 else RED)
        self._kpi_risk_val.setText(str(high_risk))
        self._kpi_risk_val.setStyleSheet(
            f"color:{risk_color}; font-size:18px; font-weight:bold;"
            "background:transparent; border:none;"
        )
        self._kpi_risk_dot.setStyleSheet(
            f"color:{risk_color}; font-size:9px; background:transparent; border:none;"
        )
        self._kpi_risk_tile.setStyleSheet(
            f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
            f"border-left:3px solid {risk_color};border-radius:0px;}}"
        )

        # Unauthorized tile — green if 0, red if >0
        unauth_color = GREEN if unauth == 0 else RED
        self._kpi_unauth_val.setText(str(unauth))
        self._kpi_unauth_val.setStyleSheet(
            f"color:{unauth_color}; font-size:18px; font-weight:bold;"
            "background:transparent; border:none;"
        )
        self._kpi_unauth_dot.setStyleSheet(
            f"color:{unauth_color}; font-size:9px; background:transparent; border:none;"
        )
        self._kpi_unauth_tile.setStyleSheet(
            f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
            f"border-left:3px solid {unauth_color};border-radius:0px;}}"
        )

        # Scan status tile — green "Complete"
        self._kpi_scan_val.setText("Complete")
        self._kpi_scan_dot.setStyleSheet(
            f"color:{GREEN}; font-size:9px; background:transparent; border:none;"
        )
        self._kpi_scan_val.setStyleSheet(
            f"color:{GREEN}; font-size:18px; font-weight:bold;"
            "background:transparent; border:none;"
        )
