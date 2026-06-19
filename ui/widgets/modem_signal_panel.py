"""
modem_signal_panel.py — _ModemSignalPanelMixin: modem signal panel builder and updater for SpeedTestPage.

Extracted from ui/pages/speed_test_page.py (Sprint 13) to keep that file within budget.
SpeedTestPage inherits _ModemSignalPanelMixin.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QVBoxLayout,
)

from ui.styles import (
    ACCENT, AMBER, BG_CARD, BORDER,
    GREEN, TEXT_PRIMARY, TEXT_SECONDARY,
)
from ui.widgets.hub_helpers import _rsrp_color


class _ModemSignalPanelMixin:
    """Mixin providing the modem signal panel builder and update methods for SpeedTestPage.

    Extracted from ui/pages/speed_test_page.py (Sprint 13).
    Requires self._signal_panel to be accessible from the host page.
    """

    def _build_signal_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("sigPanel")
        panel.setStyleSheet(
            f"QFrame#sigPanel {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-left:3px solid {ACCENT}; }}"
        )
        root = QVBoxLayout(panel)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        _lbl_style   = f"color:{TEXT_SECONDARY}; font-size:11px; border:none; background:transparent;"
        _val_style   = f"color:{TEXT_PRIMARY}; font-size:11px; font-weight:bold; border:none; background:transparent;"
        _hdr_style   = f"border:none; border-bottom:1px solid {BORDER}; background:{BG_CARD};"

        # ── header strip ─────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setStyleSheet(f"QFrame {{ {_hdr_style} }}")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(12, 6, 12, 6)
        hdr_lay.setSpacing(8)

        title = QLabel("📡  Modem signal at test time")
        title.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:12px; font-weight:bold; border:none; background:transparent;"
        )
        self._sig_ts = QLabel("")
        self._sig_ts.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; border:none; background:transparent;")
        self._sig_network_type = QLabel("")
        self._sig_network_type.setStyleSheet(f"color:{ACCENT}; font-size:11px; font-weight:bold; border:none; background:transparent;")
        self._sig_bars = QLabel("")
        self._sig_bars.setStyleSheet(f"color:{GREEN}; font-size:11px; border:none; background:transparent;")

        hdr_lay.addWidget(title)
        hdr_lay.addWidget(self._sig_ts)
        hdr_lay.addStretch()
        hdr_lay.addWidget(self._sig_network_type)
        hdr_lay.addWidget(self._sig_bars)
        root.addWidget(hdr)

        # ── connection strip (operator / cell / IP) ───────────────────────────
        conn = QFrame()
        conn.setStyleSheet(f"QFrame {{ {_hdr_style} }}")
        conn_lay = QHBoxLayout(conn)
        conn_lay.setContentsMargins(12, 5, 12, 5)
        conn_lay.setSpacing(0)

        def _conn_pair(label: str, attr: str) -> None:
            lbl = QLabel(f"{label}: ")
            lbl.setStyleSheet(_lbl_style)
            val = QLabel("—")
            val.setStyleSheet(_val_style)
            setattr(self, attr, val)
            conn_lay.addWidget(lbl)
            conn_lay.addWidget(val)
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.VLine)
            sep.setStyleSheet(f"border:none; border-left:1px solid {BORDER}; margin:0 16px;")
            conn_lay.addWidget(sep)

        _conn_pair("Operator", "_sig_operator")
        _conn_pair("Cell ID",  "_sig_cell")
        _conn_pair("Public IP","_sig_ip")
        conn_lay.addStretch()
        root.addWidget(conn)

        # ── two-column signal body ─────────────────────────────────────────────
        body = QFrame()
        body.setStyleSheet(f"QFrame {{ background:{BG_CARD}; border:none; }}")
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)

        def _col_row(label: str, attr: str, parent_lay: QVBoxLayout) -> None:
            h = QHBoxLayout()
            h.setSpacing(6)
            h.setContentsMargins(0, 1, 0, 1)
            lbl_w = QLabel(f"{label}:")
            lbl_w.setFixedWidth(58)
            lbl_w.setStyleSheet(_lbl_style)
            val_w = QLabel("—")
            val_w.setStyleSheet(_val_style)
            setattr(self, attr, val_w)
            h.addWidget(lbl_w)
            h.addWidget(val_w, 1)
            parent_lay.addLayout(h)

        def _signal_col(title: str, title_color: str, border_right: bool) -> QVBoxLayout:
            col = QFrame()
            border = f"border-right:1px solid {BORDER};" if border_right else ""
            col.setStyleSheet(f"QFrame {{ background:{BG_CARD}; border:none; {border} }}")
            lay = QVBoxLayout(col)
            lay.setContentsMargins(12, 8, 12, 8)
            lay.setSpacing(2)
            t = QLabel(title)
            t.setStyleSheet(
                f"color:{title_color}; font-size:11px; font-weight:bold;"
                f" border:none; border-bottom:1px solid {BORDER}; background:transparent;"
                f" padding-bottom:4px; margin-bottom:2px;"
            )
            lay.addWidget(t)
            body_lay.addWidget(col, 1)
            return lay

        nr_lay  = _signal_col("5G NR",        ACCENT, border_right=True)
        lte_lay = _signal_col("LTE Primary",   AMBER,  border_right=False)

        _col_row("Band",  "_sig_5g_band",  nr_lay)
        _col_row("RSRP",  "_sig_5g_rsrp",  nr_lay)
        _col_row("SINR",  "_sig_5g_sinr",  nr_lay)
        _col_row("RSRQ",  "_sig_5g_rsrq",  nr_lay)
        _col_row("PCI",   "_sig_5g_pci",   nr_lay)
        _col_row("ARFCN", "_sig_5g_arfcn", nr_lay)
        nr_lay.addStretch()

        _col_row("Band",   "_sig_lte_band",   lte_lay)
        _col_row("RSRP",   "_sig_lte_rsrp",   lte_lay)
        _col_row("SNR",    "_sig_lte_snr",    lte_lay)
        _col_row("RSRQ",   "_sig_lte_rsrq",   lte_lay)
        _col_row("PCI",    "_sig_lte_pci",    lte_lay)
        _col_row("EARFCN", "_sig_lte_earfcn", lte_lay)
        lte_lay.addStretch()

        root.addWidget(body)
        return panel

    def _update_signal_panel(self, sig: dict) -> None:
        import datetime as _dt

        def _s(v) -> str:
            return str(v) if v is not None else "—"

        def _fmt_dbm(v) -> str:
            return f"{float(v):.1f} dBm" if v is not None else "—"

        def _fmt_db(v) -> str:
            return f"{float(v):.1f} dB" if v is not None else "—"

        def _quality(rsrp) -> str:
            if rsrp is None:
                return ""
            v = float(rsrp)
            if v >= -80:  return "  — Excellent"
            if v >= -90:  return "  — Good"
            if v >= -100: return "  — Fair"
            return "  — Poor"

        # Header
        ts = sig.get("ts")
        if ts:
            self._sig_ts.setText(f"  ·  {_dt.datetime.fromtimestamp(ts).strftime('%H:%M:%S')}")
        nt   = sig.get("network_type")
        bars = sig.get("signal_bars")
        self._sig_network_type.setText(f"  {nt}" if nt else "")
        if bars is not None:
            self._sig_bars.setText(f"  {'●' * bars}{'○' * (5 - bars)}  {bars}/5")
        else:
            self._sig_bars.setText("")

        # Connection strip
        mcc, mnc = sig.get("mcc"), sig.get("mnc")
        self._sig_operator.setText(f"{mcc}-{mnc}" if mcc and mnc else "—")
        cell = sig.get("cell_id")
        enb  = sig.get("enb_id")
        self._sig_cell.setText(
            f"{cell}  (eNB: {enb})" if cell and enb else _s(cell)
        )
        self._sig_ip.setText(_s(sig.get("wan_ip")))

        # 5G NR
        nr_rsrp = sig.get("nr5g_rsrp_dbm")
        self._sig_5g_band.setText(_s(sig.get("nr5g_band")))
        self._sig_5g_rsrp.setText(_fmt_dbm(nr_rsrp) + _quality(nr_rsrp))
        self._sig_5g_rsrp.setStyleSheet(
            f"color:{_rsrp_color(nr_rsrp)}; font-size:11px; font-weight:bold;"
            f" border:none; background:transparent;"
        )
        self._sig_5g_sinr.setText(_fmt_db(sig.get("nr5g_sinr_db")))
        self._sig_5g_rsrq.setText(_fmt_db(sig.get("nr5g_rsrq_db")))
        self._sig_5g_pci.setText(_s(sig.get("nr5g_pci")))
        self._sig_5g_arfcn.setText(_s(sig.get("nr5g_arfcn")))

        # LTE Primary
        lte_rsrp = sig.get("lte_rsrp_dbm")
        self._sig_lte_band.setText(_s(sig.get("lte_band")))
        self._sig_lte_rsrp.setText(_fmt_dbm(lte_rsrp) + _quality(lte_rsrp))
        self._sig_lte_rsrp.setStyleSheet(
            f"color:{_rsrp_color(lte_rsrp)}; font-size:11px; font-weight:bold;"
            f" border:none; background:transparent;"
        )
        self._sig_lte_snr.setText(_fmt_db(sig.get("lte_snr_db")))
        self._sig_lte_rsrq.setText(_fmt_db(sig.get("lte_rsrq_db")))
        self._sig_lte_pci.setText(_s(sig.get("lte_pci")))
        self._sig_lte_earfcn.setText(_s(sig.get("lte_earfcn")))

        self._signal_panel.setVisible(True)
