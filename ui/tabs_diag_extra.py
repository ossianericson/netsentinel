"""
tabs_diag_extra.py — _DiagExtraTabsMixin: MTR tab, advanced tools, and related handlers.

Extracted from ui/tabs_diag.py (Sprint 13). _DiagTabsMixin inherits from this mixin.
Logger handlers were subsequently extracted to ui/tabs_logger.py (Sprint 15).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    AMBER, BG_CARD, BORDER, CARD_RADIUS,
    GREEN, RED,
    TEXT_PRIMARY, TEXT_SECONDARY,
)
from ui.tabs_helpers import _table


class _DiagExtraTabsMixin:
    """Mixin providing the MTR tab, advanced tools tab, and their handlers.

    Extracted from ui/tabs_diag.py (Sprint 13).
    _DiagTabsMixin inherits from this mixin.
    """

    # ── MTR tab (Advanced) ────────────────────────────────────────────────────

    def _build_mtr_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        top = QHBoxLayout()
        title = QLabel("🔁  Continuous Traceroute  (MTR)")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        top.addWidget(title)
        top.addStretch()
        tgt_lbl = QLabel("Target:")
        tgt_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        self._mtr_target = QLineEdit("8.8.8.8")
        self._mtr_target.setFixedWidth(130)
        self._btn_mtr = QPushButton("▶  Start MTR")
        self._btn_mtr.setObjectName("btnDiag")
        self._btn_mtr.setFixedHeight(30)
        self._btn_mtr.clicked.connect(self._toggle_mtr)
        top.addWidget(tgt_lbl)
        top.addWidget(self._mtr_target)
        top.addWidget(self._btn_mtr)
        lay.addLayout(top)

        self._mtr_status = QLabel("Click Start MTR to run a continuous hop-by-hop trace.")
        self._mtr_status.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(self._mtr_status)

        self._mtr_table = _table(["Hop", "IP Address", "Sent", "Loss %", "Avg RTT (ms)", "Last RTT"])
        self._mtr_table.setColumnWidth(0, 45)
        self._mtr_table.setColumnWidth(1, 160)
        self._mtr_table.setColumnWidth(2, 60)
        self._mtr_table.setColumnWidth(3, 70)
        self._mtr_table.setColumnWidth(4, 110)
        lay.addWidget(self._mtr_table, 1)
        self._mtr_worker = None
        # {hop: {ip, sent, lost, total_rtt}}
        self._mtr_stats: dict = {}
        self._mtr_cycle = 0
        return w

    # ── Advanced Tools tab ────────────────────────────────────────────────────

    def _build_advanced_tools_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        title = QLabel("🔧  Advanced Tools")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        lay.addWidget(title)

        # Port Scanner card
        ps_frame = QFrame()
        ps_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
        )
        ps_l = QVBoxLayout(ps_frame)
        ps_l.setContentsMargins(16, 12, 16, 12)
        ps_l.setSpacing(6)
        ps_title = QLabel("🔍  Port Scanner")
        ps_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        ps_title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        ps_l.addWidget(ps_title)
        ps_desc = QLabel(
            "TCP connect-scan of common ports on any host.  "
            "No admin required.  Right-click a device in Device Fingerprinter → Port Scan."
        )
        ps_desc.setWordWrap(True)
        ps_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        ps_l.addWidget(ps_desc)
        ps_row = QHBoxLayout()
        self._ps_host = QLineEdit()
        self._ps_host.setPlaceholderText("IP or hostname…")
        self._ps_host.setFixedWidth(180)
        self._ps_mode = QComboBox()
        self._ps_mode.addItems(["Normal", "Fast", "Low Impact"])
        self._ps_mode.setFixedWidth(90)
        self._ps_mode.setToolTip(
            "Fast: 100 threads, 0.35s timeout\n"
            "Normal: 50 threads, 0.60s timeout\n"
            "Low Impact: 8 threads, 1.20s timeout, 50ms delay"
        )
        self._btn_ps = QPushButton("Scan Ports")
        self._btn_ps.setObjectName("btnDiag")
        self._btn_ps.setFixedHeight(30)
        self._btn_ps.clicked.connect(
            lambda: self._run_port_scan(self._ps_host.text().strip())
        )
        self._ps_status = QLabel("")
        self._ps_status.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        ps_row.addWidget(self._ps_host)
        ps_row.addWidget(self._ps_mode)
        ps_row.addWidget(self._btn_ps)
        ps_row.addWidget(self._ps_status, 1)
        ps_l.addLayout(ps_row)
        self._ps_table = _table(["Port", "Service", "Version", "Banner", "Risk"])
        self._ps_table.setColumnWidth(0, 60)
        self._ps_table.setColumnWidth(1, 170)
        self._ps_table.setColumnWidth(2, 180)
        self._ps_table.setColumnWidth(3, 200)
        self._ps_table.setMaximumHeight(220)
        ps_l.addWidget(self._ps_table)
        lay.addWidget(ps_frame)

        # Wake-on-LAN card
        wol_frame = QFrame()
        wol_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
        )
        wol_l = QVBoxLayout(wol_frame)
        wol_l.setContentsMargins(16, 12, 16, 12)
        wol_l.setSpacing(6)
        wol_title = QLabel("⚡  Wake-on-LAN")
        wol_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        wol_title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        wol_l.addWidget(wol_title)
        wol_row = QHBoxLayout()
        self._wol_mac = QLineEdit()
        self._wol_mac.setPlaceholderText("MAC address  aa:bb:cc:dd:ee:ff")
        self._wol_mac.setFixedWidth(220)
        self._btn_wol = QPushButton("Send WoL Packet")
        self._btn_wol.setObjectName("btnNetRefresh")
        self._btn_wol.setFixedHeight(30)
        self._btn_wol.clicked.connect(
            lambda: self._send_wol(self._wol_mac.text().strip())
        )
        self._wol_status = QLabel("")
        self._wol_status.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        wol_row.addWidget(QLabel("MAC:"))
        wol_row.addWidget(self._wol_mac)
        wol_row.addWidget(self._btn_wol)
        wol_row.addWidget(self._wol_status, 1)
        wol_l.addLayout(wol_row)
        lay.addWidget(wol_frame)

        # Device Baseline card
        bl_frame = QFrame()
        bl_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
        )
        bl_l = QVBoxLayout(bl_frame)
        bl_l.setContentsMargins(16, 12, 16, 12)
        bl_l.setSpacing(6)
        bl_title = QLabel("📋  New Device Alerts  (baseline diff)")
        bl_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        bl_title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        bl_l.addWidget(bl_title)
        bl_desc = QLabel(
            "After each scan, devices not seen before are highlighted here.  "
            "Baseline is saved to ~/Documents/NetSentinel/device_baseline.json."
        )
        bl_desc.setWordWrap(True)
        bl_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        bl_l.addWidget(bl_desc)
        self._bl_new_lbl = QLabel("No scan run yet.")
        self._bl_new_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        bl_l.addWidget(self._bl_new_lbl)
        self._bl_table = _table(["IP", "Hostname", "MAC", "Vendor", "First Seen"])
        self._bl_table.setMaximumHeight(160)
        bl_l.addWidget(self._bl_table)
        lay.addWidget(bl_frame)

        lay.addStretch()
        return w

    # ── MTR handlers ──────────────────────────────────────────────────────────

    @pyqtSlot()
    def _toggle_mtr(self):
        if self._mtr_worker and self._mtr_worker.isRunning():
            self._mtr_worker.stop()
            self._btn_mtr.setText("▶  Start MTR")
            self._mtr_status.setText("MTR stopped.")
            self._mtr_worker = None
        else:
            target = self._mtr_target.text().strip() or "8.8.8.8"
            self._record_recent_action(
                action_id=f"mtr:{target}",
                label=f"Hop-by-hop trace · {target}",
                page="Hop-by-Hop Trace",
                params={"target": target},
            )
            from workers.scan_worker import MTRWorker
            self._mtr_stats = {}
            self._mtr_table.setRowCount(0)
            self._mtr_cycle = 0
            self._mtr_worker = MTRWorker(target=target)
            self._mtr_worker.hop_result.connect(self._on_mtr_hop)
            self._mtr_worker.cycle_done.connect(self._on_mtr_cycle)
            self._mtr_worker.status.connect(self._mtr_status.setText)
            self._mtr_worker.error.connect(self._mtr_status.setText)
            self._mtr_worker.start()
            self._btn_mtr.setText("⏹  Stop MTR")

    @pyqtSlot(int, str, float)
    def _on_mtr_hop(self, hop_n: int, ip: str, rtt: float):
        if hop_n not in self._mtr_stats:
            self._mtr_stats[hop_n] = {"ip": ip, "sent": 0, "lost": 0, "total": 0.0}
        s = self._mtr_stats[hop_n]
        s["sent"] += 1
        if rtt < 0:
            s["lost"] += 1
        else:
            s["total"] += rtt
        s["last"] = rtt

    @pyqtSlot(int)
    def _on_mtr_cycle(self, cycle: int):
        from PyQt6.QtGui import QColor
        self._mtr_cycle = cycle
        self._mtr_table.setRowCount(0)
        for hop_n in sorted(self._mtr_stats):
            s = self._mtr_stats[hop_n]
            sent = s["sent"]
            lost = s["lost"]
            ok = sent - lost
            loss_pct = (lost / sent * 100) if sent else 0
            avg_rtt = (s["total"] / ok) if ok else -1
            last = s.get("last", -1)
            loss_color = RED if loss_pct > 10 else (AMBER if loss_pct > 0 else GREEN)
            row = self._mtr_table.rowCount()
            self._mtr_table.insertRow(row)
            vals = [
                str(hop_n), s["ip"], str(sent),
                f"{loss_pct:.0f}%",
                f"{avg_rtt:.0f} ms" if avg_rtt >= 0 else "—",
                f"{last:.0f} ms" if last >= 0 else "—",
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(loss_color if col == 3 else TEXT_PRIMARY))
                self._mtr_table.setItem(row, col, item)

    # ── Port scan handlers ────────────────────────────────────────────────────

    def _run_port_scan(self, host: str):
        if not host:
            return
        self._record_recent_action(
            action_id=f"ps:{host}",
            label=f"Port scan · {host}",
            page="Tools & Wake-on-LAN",
            params={"host": host},
        )
        from workers.scan_worker import PortScanWorker
        if hasattr(self, "_ps_host"):
            self._ps_host.setText(host)
        self._nav_rail_go_to("Tools & Wake-on-LAN")
        self._ps_table.setRowCount(0)
        mode = self._ps_mode.currentText().lower() if hasattr(self, "_ps_mode") else "normal"
        if hasattr(self, "_ps_status"):
            self._ps_status.setText(f"Scanning {host} ({mode} mode)…")
        self._ps_worker = PortScanWorker(host=host, mode=mode)
        self._ps_worker.result.connect(self._on_port_scan_result)
        self._ps_worker.status.connect(lambda m: self._ps_status.setText(m) if hasattr(self, "_ps_status") else None, Qt.ConnectionType.QueuedConnection)
        self._ps_worker.error.connect(lambda e: self._ps_status.setText(f"Error: {e}") if hasattr(self, "_ps_status") else None, Qt.ConnectionType.QueuedConnection)
        self._ps_worker.start()

    # ── WoL handler ───────────────────────────────────────────────────────────

    def _send_wol(self, mac: str):
        from modules.utils import send_wol
        ok = send_wol(mac)
        msg = f"WoL magic packet sent to {mac}" if ok else f"Invalid MAC address: {mac}"
        color = GREEN if ok else RED
        if hasattr(self, "_wol_status"):
            self._wol_status.setStyleSheet(f"color:{color}; font-size:11px;")
            self._wol_status.setText(msg)
        else:
            self._set_status(msg)

    # ── Alert routing handler ─────────────────────────────────────────────────

    @pyqtSlot(object)
    def _on_alert_view_requested(self, alert) -> None:
        """Navigate to the most relevant page for the alert that was clicked."""
        # Dict alerts come from the Home action-needed card rows — open the drawer directly
        if isinstance(alert, dict):
            self._nav_rail_go_to("Notifications")
            try:
                if hasattr(self, "_notifications_page"):
                    self._notifications_page._alert_drawer.open(alert)
            except Exception:
                pass
            return
        rule_type = getattr(alert, "rule_type", "") or ""
        host = getattr(alert, "host", "") or ""
        if rule_type == "PORT_SCAN" and host:
            if hasattr(self, "_syn_host"):
                self._syn_host.setText(host)
            self._nav_rail_go_to("Port Scan (TCP)")
        elif rule_type in ("THREAT_INTEL", "CVE") and host:
            if hasattr(self, "_threat_intel_page"):
                self._threat_intel_page.check_ip(host)
            self._nav_rail_go_to("Threat Intelligence")
        elif rule_type == "RATE_SPIKE" and host:
            if hasattr(self, "_live_bandwidth_page"):
                self._live_bandwidth_page.annotate_event("Rate spike", RED)
            self._nav_rail_go_to("Live Bandwidth")
        elif host:
            self._on_inventory_device_selected(host)
        else:
            self._nav_rail_go_to("Notifications")
