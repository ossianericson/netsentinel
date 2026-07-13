"""
kpi_bar.py — _KpiBarMixin: four-tile KPI bar for the Devices page.

Extracted from ui/dashboard.py (Sprint 13) to keep that file within budget.
Dashboard inherits _KpiBarMixin.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from ui import styles as _s


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

        def _tile(dot_color_name: str, label: str, start_val: str, start_color_name: str):
            """Return (tile QFrame, dot QLabel, value QLabel)."""
            tile = QFrame()
            tile.setObjectName("card")
            _s.themed_ss(tile, lambda dc=dot_color_name: (
                f"QFrame#card{{background:{_s.BG_CARD};border:1px solid {_s.BORDER};"
                f"border-left:3px solid {getattr(_s, dc)};border-radius:0px;}}"
            ))
            vl = QVBoxLayout(tile)
            vl.setContentsMargins(8, 4, 8, 4)
            vl.setSpacing(1)

            hdr = QHBoxLayout()
            hdr.setSpacing(4)
            dot = QLabel("●")
            _s.themed_ss(dot, lambda dc=dot_color_name: (
                f"color:{getattr(_s, dc)}; font-size:9px; background:transparent; border:none;"
            ))
            lbl = QLabel(label.upper())
            _s.themed_ss(lbl, "color:{TEXT_MUTED}; font-size:9px; font-weight:bold;"
                "letter-spacing:0.5px; background:transparent; border:none;")
            hdr.addWidget(dot)
            hdr.addWidget(lbl)
            hdr.addStretch()
            vl.addLayout(hdr)

            val = QLabel(start_val)
            _s.themed_ss(val, lambda sc=start_color_name: (
                f"color:{getattr(_s, sc)}; font-size:18px; font-weight:bold;"
                "background:transparent; border:none;"
            ))
            vl.addWidget(val)
            return tile, dot, val

        t1, self._kpi_nodes_dot,  self._kpi_nodes_val  = _tile("ACCENT",         "Total Nodes",    "—",     "TEXT_MUTED")
        t2, self._kpi_risk_dot,   self._kpi_risk_val   = _tile("TEXT_MUTED",     "Critical Risks", "—",     "TEXT_MUTED")
        t3, self._kpi_unauth_dot, self._kpi_unauth_val = _tile("TEXT_MUTED",     "Unauthorized",   "—",     "TEXT_MUTED")
        t4, self._kpi_scan_dot,   self._kpi_scan_val   = _tile("TEXT_SECONDARY", "Scan Status",    "Ready", "TEXT_SECONDARY")

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
        _s.themed_ss(self._kpi_nodes_val, "color:{ACCENT}; font-size:18px; font-weight:bold;"
            "background:transparent; border:none;")

        # Critical risks tile — green if 0, amber if 1-2, red if 3+
        risk_name = "GREEN" if high_risk == 0 else ("AMBER" if high_risk <= 2 else "RED")
        self._kpi_risk_val.setText(str(high_risk))
        _s.themed_ss(self._kpi_risk_val, lambda rn=risk_name: (
            f"color:{getattr(_s, rn)}; font-size:18px; font-weight:bold;"
            "background:transparent; border:none;"
        ))
        _s.themed_ss(self._kpi_risk_dot, lambda rn=risk_name: (
            f"color:{getattr(_s, rn)}; font-size:9px; background:transparent; border:none;"
        ))
        _s.themed_ss(self._kpi_risk_tile, lambda rn=risk_name: (
            f"QFrame#card{{background:{_s.BG_CARD};border:1px solid {_s.BORDER};"
            f"border-left:3px solid {getattr(_s, rn)};border-radius:0px;}}"
        ))

        # Unauthorized tile — green if 0, red if >0
        unauth_name = "GREEN" if unauth == 0 else "RED"
        self._kpi_unauth_val.setText(str(unauth))
        _s.themed_ss(self._kpi_unauth_val, lambda un=unauth_name: (
            f"color:{getattr(_s, un)}; font-size:18px; font-weight:bold;"
            "background:transparent; border:none;"
        ))
        _s.themed_ss(self._kpi_unauth_dot, lambda un=unauth_name: (
            f"color:{getattr(_s, un)}; font-size:9px; background:transparent; border:none;"
        ))
        _s.themed_ss(self._kpi_unauth_tile, lambda un=unauth_name: (
            f"QFrame#card{{background:{_s.BG_CARD};border:1px solid {_s.BORDER};"
            f"border-left:3px solid {getattr(_s, un)};border-radius:0px;}}"
        ))

        # Scan status tile — green "Complete"
        self._kpi_scan_val.setText("Complete")
        _s.themed_ss(self._kpi_scan_dot, "color:{GREEN}; font-size:9px; background:transparent; border:none;")
        _s.themed_ss(self._kpi_scan_val, "color:{GREEN}; font-size:18px; font-weight:bold;"
            "background:transparent; border:none;")
