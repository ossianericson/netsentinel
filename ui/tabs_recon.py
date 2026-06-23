"""
tabs_recon.py — _ReconTabsMixin: security-audit recon tab builders for Dashboard.

Extracted from ui/dashboard.py (Sprint 18) to keep that file within budget.
TabBuilderMixin inherits _ReconTabsMixin via tabs.py.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QPoint, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton,
    QScrollArea, QSpinBox, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from ui.styles import (
    ACCENT, ACCENT_DARK, AMBER, AMBER_BG,
    BG_CARD, BORDER, CARD_RADIUS, GREEN, GREEN_BG, RED, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)
from ui.tabs_helpers import _table, _empty_state_widget, risk_to_label

if TYPE_CHECKING:
    pass


# ── Community scan plugin registry threads (PB-8) ─────────────────────────────

class _ScanPluginRegistryFetchThread(QThread):
    """Fetches the scan plugin community index in a background thread."""
    done  = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, url: str, parent=None) -> None:
        super().__init__(parent)
        self._url = url

    def run(self) -> None:
        try:
            from modules.plugin_registry import fetch_registry
            self.done.emit(fetch_registry(self._url))
        except Exception as exc:
            self.error.emit(str(exc))


class _ScanPluginInstallThread(QThread):
    """Downloads and installs one scan plugin entry in a background thread."""
    done  = pyqtSignal(str)   # installed file path
    error = pyqtSignal(str)

    def __init__(self, entry, parent=None) -> None:
        super().__init__(parent)
        self._entry = entry

    def run(self) -> None:
        try:
            from modules.plugin_registry import install_plugin
            self.done.emit(str(install_plugin(self._entry)))
        except Exception as exc:
            self.error.emit(str(exc))


class _ReconTabsMixin:
    """Mixin providing recon security-audit tab builders for Dashboard.

    Extracted from ui/dashboard.py (Sprint 18).
    TabBuilderMixin inherits this mixin.
    """

    # ── Recon: SYN / UDP / OS / Risk / CVE / Exposure tabs ──────────────────

    def _build_recon_syn_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        warn = QLabel(
            "⚠  SYN stealth scan requires administrator privileges and Npcap (Windows). "
            "Scans are not logged by the target's application layer. "
            "Use only on networks you own or have authorization to test."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet(f"color:{AMBER};font-size:11px;background:{AMBER_BG};padding:6px;border-radius:4px;")
        self._syn_status = QLabel("SYN scanner idle.")
        self._syn_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        ctrl = QHBoxLayout()
        self._syn_host = QLineEdit()
        self._syn_host.setPlaceholderText("IP or hostname…")
        self._syn_host.setFixedWidth(180)
        self._syn_rate = QSpinBox()
        self._syn_rate.setRange(10, 5000)
        self._syn_rate.setValue(500)
        self._syn_rate.setSuffix(" pps")
        self._syn_rate.setFixedWidth(100)
        from PyQt6.QtWidgets import QComboBox as _CB
        self._syn_ports_combo = _CB()
        self._syn_ports_combo.addItems(["Top 1000 ports", "Common 26 ports", "Full range (slow)"])
        self._syn_ports_combo.setFixedWidth(160)
        btn = QPushButton("⚡  SYN Scan")
        btn.setObjectName("btnNetRefresh")
        btn.clicked.connect(self._start_syn_scan)
        btn_stop = QPushButton("■  Stop")
        btn_stop.setObjectName("btnNetRefresh")
        btn_stop.clicked.connect(self._stop_syn_scan)
        ctrl.addWidget(self._syn_host)
        ctrl.addWidget(QLabel("Rate:"))
        ctrl.addWidget(self._syn_rate)
        ctrl.addWidget(self._syn_ports_combo)
        ctrl.addWidget(btn)
        ctrl.addWidget(btn_stop)
        ctrl.addStretch()
        self._recon_syn_table = _table(["Port", "State", "Protocol", "Service", "CVEs"])
        self._recon_syn_table.verticalHeader().setDefaultSectionSize(24)
        self._recon_syn_table.setColumnWidth(0, 70)
        self._recon_syn_table.setColumnWidth(1, 90)
        self._recon_syn_table.setColumnWidth(2, 70)
        self._recon_syn_table.setColumnWidth(3, 180)
        self._recon_syn_table.setColumnWidth(4, 70)
        self._recon_syn_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._recon_syn_table.customContextMenuRequested.connect(self._syn_table_context_menu)
        self._recon_syn_table.cellClicked.connect(self._on_syn_cell_clicked)
        from PyQt6.QtWidgets import QStackedWidget as _SW3
        self._syn_stack = _SW3()
        self._syn_stack.addWidget(_empty_state_widget(
            "◈", "Port Scan (TCP) — not yet run",
            "Discovers open TCP ports on every device in your network, ranked by risk.\n\n"
            "Requires: Administrator + Npcap\n"
            "Scan time: ~2–5 minutes for 20 devices\n\n"
            "High-risk findings appear automatically in Security Overview.",
            None, None,
        ))
        self._syn_stack.addWidget(self._recon_syn_table)
        lay.addWidget(warn)
        lay.addWidget(self._syn_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._syn_stack, 1)
        return w

    @pyqtSlot()
    def _start_syn_scan(self):
        from workers.scan_worker import SYNScanWorker
        host = self._syn_host.text().strip()
        if not host:
            return
        if self._syn_worker and self._syn_worker.isRunning():
            return
        self._record_recent_action(
            action_id=f"syn:{host}",
            label=f"Port Scan (TCP) · {host}",
            page="Port Scan (TCP)",
            params={"host": host},
        )
        self._recon_syn_table.setRowCount(0)
        self._syn_status.setText("⏳  Scanning ports…  this may take up to 30 seconds")
        self._nav_set_scan_state("Port Scan (TCP)", "running")
        mode_text = self._syn_ports_combo.currentText()
        if "Full range" in mode_text:
            ports = list(range(1, 65536))
        elif "Common 26" in mode_text:
            from modules.port_scanner import COMMON_PORTS
            ports = COMMON_PORTS
        else:
            from modules.syn_scanner import TOP_1000_PORTS
            ports = TOP_1000_PORTS
        rate = self._syn_rate.value()
        self._syn_worker = SYNScanWorker(host=host, ports=ports, rate_pps=rate)
        self._syn_worker.result.connect(self._on_syn_result)
        self._syn_worker.status.connect(self._syn_status.setText)
        self._syn_worker.error.connect(lambda e: self._syn_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._syn_worker.start()

    @pyqtSlot()
    def _stop_syn_scan(self):
        if self._syn_worker:
            self._syn_worker.stop()

    @pyqtSlot(int, int)
    def _on_syn_cell_clicked(self, row: int, col: int) -> None:
        if col != 4:
            return
        svc_item = self._recon_syn_table.item(row, 3)
        if svc_item and svc_item.text():
            self._nav_rail_go_to("CVE Tracker")

    def _syn_table_context_menu(self, pos) -> None:
        from PyQt6.QtWidgets import QMenu
        row = self._recon_syn_table.rowAt(pos.y())
        host = self._syn_host.text().strip()
        if row < 0 or not host:
            return
        port_item = self._recon_syn_table.item(row, 0)
        svc_item  = self._recon_syn_table.item(row, 3)
        port = (port_item.text() if port_item else "")
        svc  = (svc_item.text()  if svc_item  else "")
        menu = QMenu(self)
        menu.setStyleSheet(f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};")
        act_geo   = menu.addAction(f"🗺  Show {host} on Geolocation Map →")
        act_abuse = menu.addAction(f"🛡  Check {host} (AbuseIPDB) →")
        menu.addSeparator()
        act_copy_host = menu.addAction(f"📋  Copy host  ({host})")
        if port:
            act_copy_port = menu.addAction(f"📋  Copy  {host}:{port}  ({svc})")
        else:
            act_copy_port = None
        chosen = menu.exec(self._recon_syn_table.viewport().mapToGlobal(pos))
        if chosen == act_geo:
            self._show_ip_on_geo_map(host)
        elif chosen == act_abuse:
            self._threat_intel_page.check_ip(host)
            self._nav_rail_go_to("Threat Intel")
        elif chosen == act_copy_host:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(host)
        elif act_copy_port and chosen == act_copy_port:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(f"{host}:{port}")

    def _build_recon_udp_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        warn = QLabel(
            "⚠  UDP scan requires administrator privileges and Npcap (Windows). "
            "No response = open|filtered (firewall or open service — UDP is ambiguous)."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet(f"color:{AMBER};font-size:11px;background:{AMBER_BG};padding:6px;border-radius:4px;")
        self._udp_status = QLabel("UDP scanner idle.")
        self._udp_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        ctrl = QHBoxLayout()
        self._udp_host = QLineEdit()
        self._udp_host.setPlaceholderText("IP or hostname…")
        self._udp_host.setFixedWidth(180)
        btn = QPushButton("📻  UDP Scan")
        btn.setObjectName("btnNetRefresh")
        btn.clicked.connect(self._start_udp_scan)
        ctrl.addWidget(self._udp_host)
        ctrl.addWidget(btn)
        ctrl.addStretch()
        self._recon_udp_table = _table(["Port", "State", "Service"])
        self._recon_udp_table.setColumnWidth(0, 70)
        self._recon_udp_table.setColumnWidth(1, 120)
        self._recon_udp_table.setColumnWidth(2, 220)
        from PyQt6.QtWidgets import QStackedWidget as _SW
        self._udp_stack = _SW()
        self._udp_stack.addWidget(_empty_state_widget(
            "◆", "UDP Scan — not yet run",
            "Probes UDP services on a specific host — DNS, DHCP, SNMP, TFTP, and others.\n\n"
            "Requires: Administrator + Npcap\n"
            "Scan time: ~1–3 minutes per host\n\n"
            "Findings appear automatically in Security Overview.",
            None, None,
        ))
        self._udp_stack.addWidget(self._recon_udp_table)
        lay.addWidget(warn)
        lay.addWidget(self._udp_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._udp_stack, 1)
        return w

    @pyqtSlot()
    def _start_udp_scan(self):
        from workers.scan_worker import UDPScanWorker
        host = self._udp_host.text().strip()
        if not host:
            return
        if self._udp_worker and self._udp_worker.isRunning():
            return
        self._recon_udp_table.setRowCount(0)
        self._udp_status.setText("⏳  Scanning UDP ports…  this may take 1–2 minutes")
        self._nav_set_scan_state("Port Scan (UDP)", "running")
        self._udp_worker = UDPScanWorker(host=host)
        self._udp_worker.result.connect(self._on_udp_result)
        self._udp_worker.status.connect(self._udp_status.setText)
        self._udp_worker.error.connect(lambda e: self._udp_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._udp_worker.start()

    def _build_recon_os_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        self._os_status = QLabel("OS fingerprinter idle. Run Device Fingerprint scan first, or enter IPs manually.")
        self._os_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._os_status.setWordWrap(True)
        ctrl = QHBoxLayout()
        self._os_hosts_input = QLineEdit()
        self._os_hosts_input.setPlaceholderText("Leave blank to use M1 scan results…")
        btn = QPushButton("🖥  Fingerprint")
        btn.setObjectName("btnNetRefresh")
        btn.clicked.connect(self._start_os_fingerprint)
        ctrl.addWidget(self._os_hosts_input, 1)
        ctrl.addWidget(btn)
        self._recon_os_table = _table(["IP", "TTL", "OS Family", "Confidence", "TCP Window", "Banner Hint"])
        self._recon_os_table.setColumnWidth(0, 120)
        self._recon_os_table.setColumnWidth(1, 50)
        self._recon_os_table.setColumnWidth(2, 200)
        self._recon_os_table.setColumnWidth(3, 80)
        self._recon_os_table.setColumnWidth(4, 100)
        from PyQt6.QtWidgets import QStackedWidget as _SW
        self._os_stack = _SW()
        self._os_stack.addWidget(_empty_state_widget(
            "🖥", "No results yet",
            "OS fingerprinting uses TTL, TCP window size, and banner responses. Leave the IP field blank to use M1 scan results.",
            None, None,
        ))
        self._os_stack.addWidget(self._recon_os_table)
        lay.addWidget(self._os_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._os_stack, 1)
        return w

    @pyqtSlot()
    def _start_os_fingerprint(self):
        from workers.scan_worker import OSFingerprintWorker
        manual = self._os_hosts_input.text().strip()
        if manual:
            ips = [x.strip() for x in manual.replace(",", " ").split() if x.strip()]
        else:
            ips = []
            if self._m1_result:
                for d in self._m1_result.get("devices", []):
                    ip = getattr(d, "ip", None) if not isinstance(d, dict) else d.get("ip")
                    if ip:
                        ips.append(ip)
        if not ips:
            self._os_status.setText("No IPs to fingerprint. Run a scan first or enter IPs manually.")
            return
        if self._os_worker and self._os_worker.isRunning():
            return
        self._recon_os_table.setRowCount(0)
        self._nav_set_scan_state("OS Detection", "running")
        self._os_worker = OSFingerprintWorker(ips=ips)
        self._os_worker.result.connect(self._on_os_result)
        self._os_worker.status.connect(self._os_status.setText)
        self._os_worker.error.connect(lambda e: self._os_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._os_worker.start()

    def _build_recon_risk_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        self._risk_status = QLabel(
            "Risk scorer idle — will populate automatically after network scan."
        )
        self._risk_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        ctrl = QHBoxLayout()
        btn = QPushButton("🎯  Score All Devices")
        btn.setObjectName("btnNetRefresh")
        btn.clicked.connect(self._run_risk_scorer)
        ctrl.addWidget(btn)
        ctrl.addStretch()
        self._recon_risk_table = _table(["IP", "Device Type", "Score", "Severity", "Primary Finding", "Remediation"])
        self._recon_risk_table.setColumnWidth(0, 120)
        self._recon_risk_table.setColumnWidth(1, 160)
        self._recon_risk_table.setColumnWidth(2, 55)
        self._recon_risk_table.setColumnWidth(3, 80)
        self._recon_risk_table.setColumnWidth(4, 300)
        lay.addWidget(self._risk_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._recon_risk_table, 1)
        return w

    @pyqtSlot()
    def _run_risk_scorer(self):
        from PyQt6.QtGui import QColor
        if not self._m1_result:
            self._risk_status.setText("No scan data — run Device Fingerprint first.")
            return
        try:
            from modules.risk_scorer import score_devices
            assessments = score_devices(self._m1_result.get("devices", []))
            self._recon_risk_table.setRowCount(0)
            for a in assessments:
                row = self._recon_risk_table.rowCount()
                self._recon_risk_table.insertRow(row)
                color = (RED if a.severity in ("CRITICAL", "HIGH") else
                         AMBER if a.severity == "MEDIUM" else GREEN)
                top_finding = a.findings[0].title if a.findings else "—"
                for col, val in enumerate([
                    a.ip, a.device_type or a.vendor,
                    str(a.total_score), a.severity,
                    top_finding, a.top_remediation,
                ]):
                    item = QTableWidgetItem(str(val))
                    item.setForeground(QColor(color if col in (2, 3) else TEXT_PRIMARY))
                    self._recon_risk_table.setItem(row, col, item)
            critical = sum(1 for a in assessments if a.severity in ("CRITICAL", "HIGH"))
            self._risk_status.setText(
                f"Scored {len(assessments)} device(s) — {critical} HIGH/CRITICAL risk."
            )
        except Exception as exc:
            self._risk_status.setText(f"⚠ Risk scoring failed: {exc}")

    def _build_recon_cve_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        info = QLabel(
            "Queries the NVD (National Vulnerability Database) API v2 for known CVEs "
            "matching service versions detected by the port scanner. "
            "Set NVD_API_KEY environment variable for higher rate limits."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._cve_status = QLabel("CVE lookup idle. Run the port scanner first (Advanced Tools tab).")
        self._cve_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._cve_status.setWordWrap(True)
        ctrl = QHBoxLayout()
        self._cve_target_input = QLineEdit()
        self._cve_target_input.setPlaceholderText("Optional: manually add service versions, e.g.  OpenSSH 8.9p1, Apache/2.4.54")
        btn = QPushButton("🛡  Lookup CVEs")
        btn.setObjectName("btnNetRefresh")
        btn.clicked.connect(self._start_cve_lookup)
        ctrl.addWidget(self._cve_target_input, 1)
        ctrl.addWidget(btn)
        self._recon_cve_table = _table(["CVE ID", "Service", "Score", "Severity", "Published", "Description"])
        self._recon_cve_table.setColumnWidth(0, 130)
        self._recon_cve_table.setColumnWidth(1, 160)
        self._recon_cve_table.setColumnWidth(2, 55)
        self._recon_cve_table.setColumnWidth(3, 80)
        self._recon_cve_table.setColumnWidth(4, 90)
        from PyQt6.QtWidgets import QStackedWidget as _SW
        self._cve_stack = _SW()
        self._cve_stack.addWidget(_empty_state_widget(
            "🛡", "No results yet",
            "CVE lookup reads service versions from the port scanner. Run a port scan first, then click Lookup CVEs.",
            None, None,
        ))
        self._cve_stack.addWidget(self._recon_cve_table)
        lay.addWidget(info)
        lay.addWidget(self._cve_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._cve_stack, 1)
        return w

    @pyqtSlot()
    def _start_cve_lookup(self):
        from workers.scan_worker import CVELookupWorker
        if self._cve_worker and self._cve_worker.isRunning():
            return

        # Collect service versions from last port scan result
        versions: list = []
        manual = self._cve_target_input.text().strip()
        if manual:
            versions = [v.strip() for v in manual.split(",") if v.strip()]
        else:
            # Pull from port scan results table
            ps_table = self._ps_table
            version_col = 2  # Version column index in port scan table
            for row in range(ps_table.rowCount()):
                item = ps_table.item(row, version_col)
                if item and item.text().strip():
                    versions.append(item.text().strip())

        if not versions:
            self._cve_status.setText("No service versions found. Run a port scan first or enter versions manually.")
            return

        self._recon_cve_table.setRowCount(0)
        self._nav_set_scan_state("CVE Lookup", "running")
        self._cve_worker = CVELookupWorker(service_versions=list(set(versions)))
        self._cve_worker.cve_result.connect(self._on_cve_result)
        self._cve_worker.status.connect(self._cve_status.setText)
        self._cve_worker.finished_all.connect(lambda: self._cve_status.setText(
            self._cve_status.text() + "  ✓ Done."
        ), Qt.ConnectionType.QueuedConnection)
        self._cve_worker.finished_all.connect(self._on_cve_finished, Qt.ConnectionType.QueuedConnection)
        self._cve_worker.start()

    @pyqtSlot()
    def _on_cve_finished(self) -> None:
        if getattr(self, "_pending_security_tools", []):
            self._advance_security_audit()

    def _build_recon_exposure_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        info = QLabel(
            "Checks whether LAN devices are reachable from the public internet.\n"
            "Stage 1: fetches your public WAN IP and detects carrier-grade NAT (CGNAT).\n"
            "Stage 2: queries your router's UPnP/IGD (LAN-only SSDP) for port-forwarding rules — "
            "any forwarded port means that service is internet-accessible."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._exposure_status = QLabel("Internet exposure check idle.")
        self._exposure_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._exposure_status.setWordWrap(True)
        self._exposure_verdict = QLabel("")
        self._exposure_verdict.setWordWrap(True)
        self._exposure_verdict.setStyleSheet(
            f"color:{AMBER};font-size:12px;font-weight:bold;padding:6px;"
            f"background:{AMBER_BG};border-radius:4px;"
        )
        self._exposure_verdict.hide()
        ctrl = QHBoxLayout()
        btn = QPushButton("🌐  Check Exposure")
        btn.setObjectName("btnNetRefresh")
        btn.clicked.connect(self._start_exposure_check)
        ctrl.addWidget(btn)
        ctrl.addStretch()
        self._recon_exposure_table = _table(
            ["Device IP", "External Port", "Internal Port", "Protocol", "Description", "Enabled"]
        )
        self._recon_exposure_table.setColumnWidth(0, 130)
        self._recon_exposure_table.setColumnWidth(1, 110)
        self._recon_exposure_table.setColumnWidth(2, 110)
        self._recon_exposure_table.setColumnWidth(3, 70)
        self._recon_exposure_table.setColumnWidth(4, 200)
        lay.addWidget(info)
        lay.addWidget(self._exposure_verdict)
        lay.addWidget(self._exposure_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._recon_exposure_table, 1)
        return w

    @pyqtSlot()
    def _start_exposure_check(self):
        from workers.scan_worker import InternetExposureWorker
        if self._exposure_worker and self._exposure_worker.isRunning():
            return
        self._recon_exposure_table.setRowCount(0)
        self._exposure_verdict.hide()
        self._nav_set_scan_state("Exposed to Internet", "running")
        self._exposure_worker = InternetExposureWorker()
        self._exposure_worker.result.connect(self._on_exposure_result)
        self._exposure_worker.status.connect(self._exposure_status.setText)
        self._exposure_worker.error.connect(lambda e: self._exposure_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._exposure_worker.start()


    # ── Recon: Credentialed / Discovery / SMB / Plugin / Private Endpoint ──


    def _build_recon_cred_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QFormLayout, QComboBox
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        info = QLabel(
            "Connects to a remote host via SSH and collects:\n"
            "installed packages, running services, local users, patch level,\n"
            "listening ports, sudo NOPASSWD entries, and failed login attempts.\n"
            "Requires SSH access (password or private key). "
            "Works on Linux, macOS, and Windows (OpenSSH)."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        form_w = QWidget()
        form = QFormLayout(form_w)
        form.setContentsMargins(0, 0, 0, 0)
        self._cred_host    = QLineEdit(); self._cred_host.setPlaceholderText("192.168.1.1")
        self._cred_port    = QSpinBox(); self._cred_port.setRange(1, 65535); self._cred_port.setValue(22)
        self._cred_user    = QLineEdit(); self._cred_user.setPlaceholderText("root")
        self._cred_pass    = QLineEdit(); self._cred_pass.setPlaceholderText("(leave blank to use key)")
        self._cred_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._cred_key     = QLineEdit(); self._cred_key.setPlaceholderText("/home/user/.ssh/id_rsa")
        self._cred_os      = QComboBox()
        self._cred_os.addItems(["auto", "linux", "macos", "windows"])
        form.addRow("Host:", self._cred_host)
        form.addRow("SSH Port:", self._cred_port)
        form.addRow("Username:", self._cred_user)
        form.addRow("Password:", self._cred_pass)
        form.addRow("Key file:", self._cred_key)
        form.addRow("OS hint:", self._cred_os)

        ctrl = QHBoxLayout()
        self._btn_cred = QPushButton("🔑  Run Credentialed Scan")
        self._btn_cred.setObjectName("btnNetRefresh")
        self._btn_cred.clicked.connect(self._start_cred_scan)
        self._btn_cred_stop = QPushButton("⏹  Stop")
        self._btn_cred_stop.clicked.connect(lambda: self._cred_worker and self._cred_worker.stop())
        ctrl.addWidget(self._btn_cred)
        ctrl.addWidget(self._btn_cred_stop)
        ctrl.addStretch()

        self._cred_status = QLabel("Credentialed scan idle.")
        self._cred_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
        self._cred_status.setWordWrap(True)

        self._cred_verdict = QLabel("")
        self._cred_verdict.setWordWrap(True)
        self._cred_verdict.setStyleSheet(
            f"color:{GREEN};font-size:11px;font-weight:bold;padding:4px;"
            f"background:{BG_CARD};border-radius:4px;"
        )
        self._cred_verdict.hide()

        self._recon_cred_sw_table   = _table(["Package", "Version", "Source"])
        self._recon_cred_svc_table  = _table(["Service", "Status", "PID"])
        self._recon_cred_user_table = _table(["User", "UID / SID", "Home", "Shell"])
        self._recon_cred_sessions_table = _table(["Active Session (logged-in user)"])

        self._recon_cred_info_table = _table(["Field", "Value"])
        self._recon_cred_info_table.horizontalHeader().setSectionResizeMode(
            1, __import__("PyQt6.QtWidgets", fromlist=["QHeaderView"]).QHeaderView.ResizeMode.Stretch
        )

        from PyQt6.QtWidgets import QTabWidget as _TW
        inner_tabs = _TW()
        inner_tabs.addTab(self._recon_cred_info_table,     "▪ Device Info")
        inner_tabs.addTab(self._recon_cred_sw_table,       "📦 Software")
        inner_tabs.addTab(self._recon_cred_svc_table,      "⚙ Services")
        inner_tabs.addTab(self._recon_cred_user_table,     "👤 Users")
        inner_tabs.addTab(self._recon_cred_sessions_table, "● Active Sessions")

        lay.addWidget(info)
        lay.addWidget(form_w)
        lay.addWidget(self._cred_verdict)
        lay.addWidget(self._cred_status)
        lay.addLayout(ctrl)
        lay.addWidget(inner_tabs, 1)
        return w

    @pyqtSlot()
    def _start_cred_scan(self):
        from workers.scan_worker import CredentialedScanWorker
        host = self._cred_host.text().strip()
        if not host:
            self._cred_status.setText("⚠ Enter a host IP or hostname.")
            return
        if self._cred_worker and self._cred_worker.isRunning():
            return
        self._recon_cred_sw_table.setRowCount(0)
        self._recon_cred_svc_table.setRowCount(0)
        self._recon_cred_user_table.setRowCount(0)
        self._recon_cred_sessions_table.setRowCount(0)
        self._recon_cred_info_table.setRowCount(0)
        self._cred_verdict.hide()
        self._cred_worker = CredentialedScanWorker(
            host=host,
            ssh_port=self._cred_port.value(),
            username=self._cred_user.text().strip() or "root",
            password=self._cred_pass.text(),
            key_path=self._cred_key.text().strip(),
            os_hint=self._cred_os.currentText(),
        )
        self._cred_worker.result.connect(self._on_cred_result)
        self._cred_worker.status.connect(self._cred_status.setText)
        self._cred_worker.error.connect(lambda e: self._cred_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._nav_set_scan_state("Login Test", "running")
        self._cred_worker.start()

    def _build_recon_discovery_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        info = QLabel(
            "Runs all discovery methods in parallel and merges results:\n"
            "• ARP cache (passive, instant)\n"
            "• ARP broadcast sweep (Scapy — requires admin)\n"
            "• ICMP ping sweep (64 parallel threads)\n"
            "• TCP SYN probe to ports 80/443/22/8080 (Scapy)\n"
            "• mDNS query (zero-conf devices: printers, Chromecast, Apple TV)\n"
            "Typically completes a /24 in under 3 seconds."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        ctrl = QHBoxLayout()
        self._disc_cidr = QLineEdit()
        self._disc_cidr.setPlaceholderText("192.168.1.0/24  (blank = auto-detect)")
        self._disc_cidr.setMaximumWidth(260)
        self._disc_passive_chk = QCheckBox("Passive only (no active probes)")
        self._btn_disc = QPushButton("🚀  Start Discovery")
        self._btn_disc.setObjectName("btnNetRefresh")
        self._btn_disc.clicked.connect(self._start_discovery)
        self._btn_disc_stop = QPushButton("⏹  Stop")
        self._btn_disc_stop.clicked.connect(lambda: self._discovery_worker and self._discovery_worker.stop())
        ctrl.addWidget(self._disc_cidr)
        ctrl.addWidget(self._disc_passive_chk)
        ctrl.addWidget(self._btn_disc)
        ctrl.addWidget(self._btn_disc_stop)
        ctrl.addStretch()

        self._disc_status = QLabel("Combined discovery idle.")
        self._disc_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
        self._disc_status.setWordWrap(True)

        self._recon_disc_table = _table(["IP", "MAC", "Hostname", "Methods", "Latency (ms)"])
        self._recon_disc_table.setColumnWidth(0, 130)
        self._recon_disc_table.setColumnWidth(1, 140)
        self._recon_disc_table.setColumnWidth(2, 200)
        self._recon_disc_table.setColumnWidth(3, 180)

        lay.addWidget(info)
        lay.addLayout(ctrl)
        lay.addWidget(self._disc_status)
        lay.addWidget(self._recon_disc_table, 1)
        return w

    @pyqtSlot()
    def _start_discovery(self):
        from workers.scan_worker import CombinedDiscoveryWorker
        if self._discovery_worker and self._discovery_worker.isRunning():
            return
        self._recon_disc_table.setRowCount(0)
        self._disc_status.setText("Starting combined discovery…")
        self._discovery_worker = CombinedDiscoveryWorker(
            cidr=self._disc_cidr.text().strip(),
            passive_only=self._disc_passive_chk.isChecked(),
        )
        self._discovery_worker.result.connect(self._on_discovery_result)
        self._discovery_worker.status.connect(self._disc_status.setText)
        self._discovery_worker.error.connect(lambda e: self._disc_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._nav_set_scan_state("Full Device Discovery", "running")
        self._discovery_worker.start()

    def _build_recon_smb_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QFormLayout, QTabWidget as _TW
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        info = QLabel(
            "NetBIOS + SMB enumeration.\n"
            "Tier 1 (no credentials): machine name, workgroup/domain, OS version, "
            "anonymous session check, share list (Windows scanner only).\n"
            "Tier 2 (with credentials): full share list, local users, active sessions, "
            "local groups. Requires impacket or Windows net.exe."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        form_w = QWidget()
        form = QFormLayout(form_w)
        form.setContentsMargins(0, 0, 0, 0)
        self._smb_host   = QLineEdit(); self._smb_host.setPlaceholderText("192.168.1.1")
        self._smb_user   = QLineEdit(); self._smb_user.setPlaceholderText("(blank = Tier 1 only)")
        self._smb_pass   = QLineEdit(); self._smb_pass.setPlaceholderText("")
        self._smb_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._smb_domain = QLineEdit(); self._smb_domain.setPlaceholderText("WORKGROUP")
        form.addRow("Host:", self._smb_host)
        form.addRow("Username:", self._smb_user)
        form.addRow("Password:", self._smb_pass)
        form.addRow("Domain:", self._smb_domain)

        ctrl = QHBoxLayout()
        self._btn_smb = QPushButton("🗂  Enumerate SMB")
        self._btn_smb.setObjectName("btnNetRefresh")
        self._btn_smb.clicked.connect(self._start_smb_enum)
        self._btn_smb_stop = QPushButton("⏹  Stop")
        self._btn_smb_stop.clicked.connect(lambda: self._smb_worker and self._smb_worker.stop())
        ctrl.addWidget(self._btn_smb)
        ctrl.addWidget(self._btn_smb_stop)
        ctrl.addStretch()

        self._smb_status = QLabel("SMB enumeration idle.")
        self._smb_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
        self._smb_status.setWordWrap(True)

        self._smb_verdict = QLabel("")
        self._smb_verdict.setWordWrap(True)
        self._smb_verdict.setStyleSheet(
            f"color:{AMBER};font-size:11px;font-weight:bold;padding:4px;"
            f"background:{BG_CARD};border-radius:4px;"
        )
        self._smb_verdict.hide()

        self._recon_smb_shares_table = _table(["Share", "Type", "Comment", "Risk"])
        self._recon_smb_users_table  = _table(["Username", "SID / UID", "Full Name", "Last Logon"])

        inner_tabs = _TW()
        inner_tabs.addTab(self._recon_smb_shares_table, "📁 Shares")
        inner_tabs.addTab(self._recon_smb_users_table,  "👤 Users")

        lay.addWidget(info)
        lay.addWidget(form_w)
        lay.addWidget(self._smb_verdict)
        lay.addWidget(self._smb_status)
        lay.addLayout(ctrl)
        lay.addWidget(inner_tabs, 1)
        return w

    @pyqtSlot()
    def _start_smb_enum(self):
        from workers.scan_worker import SMBEnumWorker
        host = self._smb_host.text().strip()
        if not host:
            self._smb_status.setText("⚠ Enter a host IP or hostname.")
            return
        if self._smb_worker and self._smb_worker.isRunning():
            return
        self._recon_smb_shares_table.setRowCount(0)
        self._recon_smb_users_table.setRowCount(0)
        self._smb_verdict.hide()
        self._smb_worker = SMBEnumWorker(
            host=host,
            username=self._smb_user.text().strip(),
            password=self._smb_pass.text(),
            domain=self._smb_domain.text().strip(),
        )
        self._smb_worker.result.connect(self._on_smb_result)
        self._smb_worker.status.connect(self._smb_status.setText)
        self._smb_worker.error.connect(lambda e: self._smb_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._smb_worker.start()

    def _build_recon_plugin_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        info = QLabel(
            "Custom plugins extend NetSentinel with your own checks.\n"
            "Each plugin is a .py file in the plugins/ folder (shown below) with a "
            "PLUGIN_META dict and a run(devices) function that returns a PluginResult.\n"
            "Click Reload to re-scan the folder after adding or editing a plugin."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        ctrl = QHBoxLayout()
        self._btn_plugin_reload = QPushButton("↺  Reload Plugins")
        self._btn_plugin_reload.setObjectName("btnNetRefresh")
        self._btn_plugin_reload.clicked.connect(self._reload_plugins)

        self._btn_plugin_open_dir = QPushButton("📂  Open Plugins Folder")
        self._btn_plugin_open_dir.setObjectName("btnNetRefresh")
        self._btn_plugin_open_dir.clicked.connect(self._open_plugins_dir)

        self._btn_plugin_run = QPushButton("▶  Run Selected")
        self._btn_plugin_run.setObjectName("btnNetRefresh")
        self._btn_plugin_run.clicked.connect(self._run_selected_plugin)

        self._btn_plugin_new = QPushButton("⬡  New Scan Plugin")
        self._btn_plugin_new.setObjectName("btnNetRefresh")
        self._btn_plugin_new.clicked.connect(self._new_scan_plugin_wizard)

        self._btn_plugin_community = QPushButton("⬇  Get Plugins")
        self._btn_plugin_community.setObjectName("btnNetRefresh")
        self._btn_plugin_community.setToolTip(
            "Browse and install scan plugins from the community registry"
        )
        self._btn_plugin_community.clicked.connect(self._browse_community_plugins)

        ctrl.addWidget(self._btn_plugin_reload)
        ctrl.addWidget(self._btn_plugin_open_dir)
        ctrl.addWidget(self._btn_plugin_run)
        ctrl.addWidget(self._btn_plugin_new)
        ctrl.addWidget(self._btn_plugin_community)
        ctrl.addStretch()

        self._plugin_dir_lbl = QLabel("")
        self._plugin_dir_lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:10px;")

        self._plugin_list_table = _table(["Plugin", "Version", "Status", "Tags", "Description", "Author"])
        self._plugin_list_table.setColumnWidth(0, 180)
        self._plugin_list_table.setColumnWidth(1, 60)
        self._plugin_list_table.setColumnWidth(2, 55)
        self._plugin_list_table.setColumnWidth(3, 120)
        self._plugin_list_table.setColumnWidth(4, 280)
        self._plugin_list_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._plugin_list_table.customContextMenuRequested.connect(self._on_plugin_table_context)
        self._plugin_list_table.cellClicked.connect(self._on_plugin_status_cell_clicked)

        self._plugin_status = QLabel("Click Reload Plugins to discover .py files in the plugins folder.")
        self._plugin_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
        self._plugin_status.setWordWrap(True)

        self._plugin_result_text = QTextEdit()
        self._plugin_result_text.setReadOnly(True)
        self._plugin_result_text.setMaximumHeight(160)
        self._plugin_result_text.setStyleSheet(
            f"background:{BG_CARD};color:{TEXT_PRIMARY};font-size:11px;"
            f"border:1px solid {BORDER};border-radius:{CARD_RADIUS};padding:6px;"
        )
        self._plugin_result_text.setPlaceholderText("Plugin output will appear here…")

        lay.addWidget(info)
        lay.addLayout(ctrl)
        lay.addWidget(self._plugin_dir_lbl)
        lay.addWidget(self._plugin_list_table, 1)
        lay.addWidget(self._plugin_status)
        lay.addWidget(self._plugin_result_text)

        self._plugins: list = []
        self._plugin_validation: list = []  # List[List[str]] — issues per plugin index
        self._plugin_worker = None
        self._reload_plugins()
        return w

    @pyqtSlot()
    def _reload_plugins(self):
        from modules.plugin_system import load_plugins, plugins_dir, validate_scan_plugin
        self._plugins = load_plugins()
        self._plugin_validation = []
        d = plugins_dir()
        self._plugin_dir_lbl.setText(f"Plugins folder: {d}")
        self._plugin_list_table.setRowCount(0)
        for p in self._plugins:
            if p._run_fn is None:
                issues = ["Plugin failed to load — check file for syntax or import errors."]
            else:
                issues = validate_scan_plugin(p.path)
            self._plugin_validation.append(issues)

            r = self._plugin_list_table.rowCount()
            self._plugin_list_table.insertRow(r)

            for c, v in enumerate([p.name, p.version]):
                self._plugin_list_table.setItem(r, c, QTableWidgetItem(v))

            # Status badge: green = OK, amber = advisory only, red = error
            if not issues:
                dot_color = GREEN
                tooltip = "All validation checks passed."
            else:
                api_only = all("api_version" in i for i in issues)
                dot_color = AMBER if api_only else RED
                tooltip = "\n".join(issues)
            status_item = QTableWidgetItem("●")
            status_item.setForeground(QColor(dot_color))
            status_item.setToolTip(tooltip)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._plugin_list_table.setItem(r, 2, status_item)

            for c, v in enumerate([p.tag_str, p.description, p.author]):
                self._plugin_list_table.setItem(r, 3 + c, QTableWidgetItem(v))

        n = len(self._plugins)
        self._plugin_status.setText(
            f"{n} plugin{'s' if n != 1 else ''} loaded. Select one and click Run Selected."
        )

    @pyqtSlot()
    def _open_plugins_dir(self):
        from modules.plugin_system import plugins_dir
        import subprocess, sys
        d = str(plugins_dir())
        if sys.platform == "win32":
            subprocess.Popen(["explorer", d])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", d])
        else:
            subprocess.Popen(["xdg-open", d])

    def _new_scan_plugin_wizard(self) -> None:
        """Open a wizard to create a new scan plugin template (PB-1)."""
        dlg = QDialog(self._plugin_list_table.window())
        dlg.setWindowTitle("New Scan Plugin")
        dlg.setMinimumWidth(440)
        vlay = QVBoxLayout(dlg)
        vlay.setContentsMargins(16, 16, 16, 8)
        vlay.setSpacing(8)

        form_w = QWidget()
        form = QFormLayout(form_w)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)

        name_edit = QLineEdit()
        name_edit.setPlaceholderText("My Custom Check")
        desc_edit = QLineEdit()
        desc_edit.setPlaceholderText("Describe what this plugin checks")
        tags_edit = QLineEdit()
        tags_edit.setPlaceholderText("ports, risk  (comma-separated, optional)")

        form.addRow("Plugin name *:", name_edit)
        form.addRow("Description:", desc_edit)
        form.addRow("Tags:", tags_edit)
        vlay.addWidget(form_w)

        note = QLabel(
            "A .py template will be created in the plugins folder ready to edit. "
            "It comes with PLUGIN_META + a run(devices) stub that passes validation."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:10px;padding:4px 0;")
        vlay.addWidget(note)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        vlay.addWidget(bb)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        plugin_name = name_edit.text().strip()
        if not plugin_name:
            return

        description = desc_edit.text().strip() or f"Custom scan plugin: {plugin_name}"
        tags_raw = [t.strip() for t in tags_edit.text().split(",") if t.strip()]
        tags_py = ", ".join(f'"{t}"' for t in tags_raw)

        import re
        slug = re.sub(r"[^a-zA-Z0-9_]", "_", plugin_name.lower()).strip("_") or "custom_plugin"

        from modules.plugin_system import plugins_dir
        d = plugins_dir()
        dest = d / f"{slug}.py"
        counter = 1
        while dest.exists():
            dest = d / f"{slug}_{counter}.py"
            counter += 1

        template = (
            f'"""\n{description}\n"""\n\n'
            f"PLUGIN_META = {{\n"
            f'    "name":        "{plugin_name}",\n'
            f'    "version":     "1.0.0",\n'
            f'    "description": "{description}",\n'
            f'    "author":      "Custom",\n'
            f'    "tags":        [{tags_py}],\n'
            f'    "api_version": "1",\n'
            f"}}\n\n\n"
            f"def run(devices, **kwargs):\n"
            f"    from modules.plugin_system import PluginResult\n"
            f"    findings = []\n"
            f"    for device in devices:\n"
            f"        ip = getattr(device, 'ip', None) or "
            f"(device.get('ip') if isinstance(device, dict) else '?')\n"
            f"        # TODO: add your checks here\n"
            f"        pass\n\n"
            f"    risk = 'HIGH' if findings else 'CLEAN'\n"
            f"    return PluginResult(\n"
            f"        plugin_name=PLUGIN_META['name'],\n"
            f"        findings=findings,\n"
            f"        risk_level=risk,\n"
            f"    )\n"
        )

        try:
            dest.write_text(template, encoding="utf-8")
        except OSError as exc:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(
                self._plugin_list_table.window(),
                "Write Error",
                f"Could not write plugin file:\n{exc}",
            )
            return

        self._reload_plugins()
        self._plugin_status.setText(
            f"Created '{dest.name}' — open the plugins folder to edit it."
        )

    def _browse_community_plugins(self) -> None:
        """Browse and install community scan plugins from the registry (PB-8)."""
        from modules.plugin_registry import REGISTRY_URL, is_installed

        dlg = QDialog(self._plugin_list_table.window())
        dlg.setWindowTitle("Community Scan Plugins")
        dlg.setMinimumSize(560, 440)
        vlay = QVBoxLayout(dlg)
        vlay.setContentsMargins(12, 10, 12, 10)
        vlay.setSpacing(6)

        top = QHBoxLayout()
        reg_status = QLabel("Press Refresh to fetch available plugins.")
        reg_status.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;")
        top.addWidget(reg_status, 1)
        btn_refresh = QPushButton("↻  Refresh")
        btn_refresh.setObjectName("btnNetRefresh")
        top.addWidget(btn_refresh)
        vlay.addLayout(top)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        inner = QWidget()
        inner.setStyleSheet(f"background:{BG_CARD};")
        cards_lay = QVBoxLayout(inner)
        cards_lay.setContentsMargins(0, 4, 0, 4)
        cards_lay.setSpacing(4)
        cards_lay.addStretch()
        scroll.setWidget(inner)
        vlay.addWidget(scroll, 1)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        vlay.addWidget(bb)

        _active_threads: list = []

        def _rebuild_cards(entries: list) -> None:
            while cards_lay.count() > 1:
                item = cards_lay.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            reg_status.setText(f"{len(entries)} plugin(s) available.")
            for entry in entries:
                row = QFrame()
                row.setStyleSheet(
                    f"QFrame{{background:{BG_CARD};border:1px solid {BORDER};"
                    f"border-radius:{CARD_RADIUS};}}"
                )
                rlay = QHBoxLayout(row)
                rlay.setContentsMargins(10, 6, 10, 6)
                rlay.setSpacing(8)
                info_col = QVBoxLayout()
                name_lbl = QLabel(
                    f"<b>{entry.name}</b>  "
                    f"<span style='color:{TEXT_MUTED};font-size:9px;'>"
                    f"v{entry.version}  by {entry.author}</span>"
                )
                name_lbl.setTextFormat(Qt.TextFormat.RichText)
                name_lbl.setStyleSheet(f"color:{TEXT_PRIMARY};border:none;")
                info_col.addWidget(name_lbl)
                if entry.description:
                    desc_lbl = QLabel(entry.description)
                    desc_lbl.setStyleSheet(
                        f"color:{TEXT_SECONDARY};font-size:10px;border:none;"
                    )
                    desc_lbl.setWordWrap(True)
                    info_col.addWidget(desc_lbl)
                rlay.addLayout(info_col, 1)
                installed = is_installed(entry)
                btn_inst = QPushButton("✓ Installed" if installed else "⬇ Install")
                btn_inst.setEnabled(not installed)
                btn_inst.setFixedHeight(26)
                _inst_bg = GREEN_BG if installed else ACCENT
                _inst_fg = GREEN if installed else WHITE
                btn_inst.setStyleSheet(
                    f"QPushButton{{background:{_inst_bg};color:{_inst_fg};"
                    f"border:none;border-radius:3px;font-size:11px;padding:0 10px;}}"
                    f"QPushButton:hover{{background:{ACCENT_DARK};color:{WHITE};}}"
                    f"QPushButton:pressed{{background:{ACCENT_DARK};color:{WHITE};}}"
                    f"QPushButton:disabled{{background:{GREEN_BG};color:{GREEN};}}"
                )
                if not installed:
                    def _on_install(_, e=entry, b=btn_inst) -> None:
                        b.setText("Installing…")
                        b.setEnabled(False)
                        t = _ScanPluginInstallThread(e, parent=dlg)
                        t.done.connect(
                            lambda _p, _b=b: (_b.setText("✓ Installed"), self._reload_plugins()),
                            Qt.ConnectionType.QueuedConnection,
                        )
                        t.error.connect(
                            lambda msg, _b=b: _b.setText("Error"),
                            Qt.ConnectionType.QueuedConnection,
                        )
                        _active_threads.append(t)
                        t.start()
                    btn_inst.clicked.connect(_on_install)
                rlay.addWidget(btn_inst)
                cards_lay.insertWidget(cards_lay.count() - 1, row)

        def _fetch() -> None:
            reg_status.setText("Fetching registry…")
            t = _ScanPluginRegistryFetchThread(REGISTRY_URL, parent=dlg)
            t.done.connect(_rebuild_cards, Qt.ConnectionType.QueuedConnection)
            t.error.connect(
                lambda msg: reg_status.setText(f"Error: {msg}"),
                Qt.ConnectionType.QueuedConnection,
            )
            _active_threads.append(t)
            t.start()

        btn_refresh.clicked.connect(_fetch)
        dlg.exec()

    @pyqtSlot()
    def _run_selected_plugin(self):
        from workers.scan_worker import PluginWorker
        row = self._plugin_list_table.currentRow()
        if row < 0 or row >= len(self._plugins):
            self._plugin_status.setText("⚠ Select a plugin from the list first.")
            return
        if self._plugin_worker and self._plugin_worker.isRunning():
            return
        info = self._plugins[row]
        # Use Module 1 scan results as device list if available
        devices = []
        if self._m1_result:
            devices = self._m1_result.get("devices", [])
        self._plugin_status.setText(f"Running '{info.name}'…")
        self._plugin_result_text.clear()
        self._plugin_worker = PluginWorker(info, devices)
        self._plugin_worker.result.connect(self._on_plugin_result)
        self._plugin_worker.status.connect(self._plugin_status.setText)
        self._plugin_worker.error.connect(self._on_plugin_error)
        self._plugin_worker.start()

    @pyqtSlot(str)
    def _on_plugin_error(self, msg: str):
        tb_lines = msg.strip().splitlines()
        if len(tb_lines) > 10:
            tb_lines = ["(… truncated …)"] + tb_lines[-10:]
        lines = [
            "Plugin failed to execute.",
            "",
            "What happened: the plugin raised an unhandled exception or could not start.",
            "Likely cause:  a missing dependency, import error, or syntax problem.",
            "What to try:   right-click the plugin and choose 'Show validation', or",
            "               open the plugins folder to edit the file.",
            "",
            "— Error details —",
        ] + tb_lines
        self._plugin_result_text.setPlainText("\n".join(lines))
        self._plugin_status.setText("Plugin failed — see output below.")
        self._plugin_status.setStyleSheet(f"color:{RED};font-size:11px;")

    def _on_plugin_status_cell_clicked(self, row: int, col: int) -> None:
        """Show validation issues when the Status column cell is clicked (PB-4)."""
        if col != 2:
            return
        if row < 0 or row >= len(self._plugin_validation):
            return
        issues = self._plugin_validation[row]
        if not issues:
            return
        dlg = QDialog(self._plugin_list_table.window())
        dlg.setWindowTitle("Plugin Validation Issues")
        dlg.setMinimumWidth(440)
        vlay = QVBoxLayout(dlg)
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setPlainText("\n".join(f"• {i}" for i in issues))
        txt.setStyleSheet(
            f"background:{BG_CARD};color:{TEXT_PRIMARY};font-size:11px;"
            f"border:1px solid {BORDER};padding:6px;"
        )
        vlay.addWidget(txt)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        vlay.addWidget(bb)
        dlg.exec()

    @pyqtSlot(QPoint)
    def _on_plugin_table_context(self, pos) -> None:
        """Right-click context menu for the plugin list table (PB-5)."""
        row = self._plugin_list_table.rowAt(pos.y())
        if row < 0 or row >= len(self._plugins):
            return
        menu = QMenu(self._plugin_list_table)
        act_test = menu.addAction("▶  Test with last scan")
        menu.addSeparator()
        act_validate = menu.addAction("▣  Show validation")
        menu.addSeparator()
        act_copy = menu.addAction("Copy name")
        action = menu.exec(self._plugin_list_table.viewport().mapToGlobal(pos))
        if action == act_test:
            self._run_plugin_in_dialog(row)
        elif action == act_validate:
            self._on_plugin_status_cell_clicked(row, 2)
        elif action == act_copy:
            info = self._plugins[row]
            QApplication.clipboard().setText(info.name)

    def _run_plugin_in_dialog(self, row: int) -> None:
        """Run a scan plugin against the last scan result; show output in a dialog (PB-5/PB-6)."""
        from workers.scan_worker import PluginWorker as _ScanPluginWorker
        if self._plugin_worker and self._plugin_worker.isRunning():
            self._plugin_status.setText("⚠ A plugin is already running — wait for it to finish.")
            return
        info = self._plugins[row]
        devices = (self._m1_result or {}).get("devices", [])

        dlg = QDialog(self._plugin_list_table.window())
        dlg.setWindowTitle(f"Plugin Result — {info.name}")
        dlg.setMinimumSize(500, 320)
        vlay = QVBoxLayout(dlg)

        output = QTextEdit()
        output.setReadOnly(True)
        output.setPlainText("Running…")
        output.setStyleSheet(
            f"background:{BG_CARD};color:{TEXT_PRIMARY};font-size:11px;"
            f"border:1px solid {BORDER};padding:6px;"
        )
        vlay.addWidget(output, 1)

        # Collapsible error details section (PB-6)
        details_toggle = QPushButton("▼  Show error details")
        details_toggle.setFlat(True)
        details_toggle.setStyleSheet(f"color:{AMBER};font-size:10px;text-align:left;")
        details_toggle.hide()
        vlay.addWidget(details_toggle)

        details_text = QTextEdit()
        details_text.setReadOnly(True)
        details_text.setMaximumHeight(120)
        details_text.setStyleSheet(
            f"background:{BG_CARD};color:{TEXT_MUTED};font-size:10px;"
            f"font-family:'Courier New';border:1px solid {BORDER};padding:4px;"
        )
        details_text.hide()
        vlay.addWidget(details_text)

        def _toggle_details() -> None:
            if details_text.isVisible():
                details_text.hide()
                details_toggle.setText("▼  Show error details")
            else:
                details_text.show()
                details_toggle.setText("▲  Hide error details")

        details_toggle.clicked.connect(_toggle_details)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        vlay.addWidget(bb)

        self._plugin_status.setText(f"Running '{info.name}'…")
        self._plugin_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")

        def _on_result(res) -> None:
            if res.error:
                output.setPlainText(
                    f"Plugin:  {res.plugin_name}\n\n"
                    "The plugin encountered an error while running.\n"
                    "Likely cause: a coding error in the plugin or missing expected data.\n"
                    "What to try:  close this dialog, right-click the plugin row, and\n"
                    "             choose 'Show validation' for a static analysis report."
                )
                tb_lines = res.error.strip().splitlines()
                if len(tb_lines) > 15:
                    tb_lines = ["(… truncated …)"] + tb_lines[-15:]
                details_text.setPlainText("\n".join(tb_lines))
                details_toggle.show()
                self._plugin_status.setText(f"'{res.plugin_name}' failed — error details available.")
                self._plugin_status.setStyleSheet(f"color:{RED};font-size:11px;")
                return
            lines = [f"Plugin:  {res.plugin_name}", f"Risk:    {risk_to_label(res.risk_level)}", ""]
            if res.findings:
                lines += [f"Findings ({len(res.findings)}):"]
                lines += [f"  • {f}" for f in res.findings]
            else:
                lines.append("No findings.")
            output.setPlainText("\n".join(lines))
            color = RED if res.risk_level in ("HIGH", "CRITICAL") else (
                AMBER if res.risk_level == "MEDIUM" else GREEN
            )
            self._plugin_status.setText(
                f"'{res.plugin_name}' complete — {risk_to_label(res.risk_level)} "
                f"({len(res.findings)} finding{'s' if len(res.findings) != 1 else ''})"
            )
            self._plugin_status.setStyleSheet(f"color:{color};font-size:11px;")

        def _on_err(msg: str) -> None:
            output.setPlainText(
                "Plugin failed to execute.\n\n"
                "What happened: the plugin raised an unhandled exception or could not start.\n"
                "Likely cause:  a missing dependency, import error, or syntax problem.\n"
                "What to try:   close this dialog, right-click the plugin row, and\n"
                "               choose 'Show validation' for a static analysis report."
            )
            tb_lines = msg.strip().splitlines()
            if len(tb_lines) > 15:
                tb_lines = ["(… truncated …)"] + tb_lines[-15:]
            details_text.setPlainText("\n".join(tb_lines))
            details_toggle.show()
            self._plugin_status.setText("Plugin failed — error details available.")
            self._plugin_status.setStyleSheet(f"color:{RED};font-size:11px;")

        worker = _ScanPluginWorker(info, devices)
        worker.result.connect(_on_result)
        worker.error.connect(_on_err)
        worker.start()
        self._plugin_worker = worker
        dlg.exec()

    def _build_recon_pe_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        title = QLabel("🔒  Private Endpoint Checker")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        lay.addWidget(title)

        desc = QLabel(
            "Verify that named service endpoints resolve to private (RFC-1918) IPs, "
            "are TCP-reachable, and have valid TLS certificates.  "
            "Works for Azure Private Link, AWS PrivateLink, and any internal hostname:port."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(desc)

        # ── Input area ────────────────────────────────────────────────────────
        input_frame = QFrame()
        input_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
        )
        input_lay = QVBoxLayout(input_frame)
        input_lay.setContentsMargins(14, 10, 14, 10)
        input_lay.setSpacing(6)

        input_lbl = QLabel("Endpoints — one per line, format:  hostname:port  or  IP:port  (port optional, defaults to 443)")
        input_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        input_lay.addWidget(input_lbl)

        self._pe_input = QTextEdit()
        self._pe_input.setPlaceholderText(
            "myblob.privatelink.blob.core.windows.net:443\n"
            "my-rds.cluster-xxxx.us-east-1.rds.amazonaws.com:5432\n"
            "10.0.1.55:22"
        )
        self._pe_input.setFixedHeight(100)
        self._pe_input.setStyleSheet(
            f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};"
            "border-radius:4px; padding:6px; font-size:12px; font-family:'Courier New';"
        )
        input_lay.addWidget(self._pe_input)

        btn_row = QHBoxLayout()
        self._btn_pe_run = QPushButton("▶  Run Checks")
        self._btn_pe_run.setObjectName("btnDiag")
        self._btn_pe_run.setFixedHeight(34)
        self._btn_pe_run.clicked.connect(self._run_pe_checks)
        self._btn_pe_clear = QPushButton("Clear")
        self._btn_pe_clear.setFixedHeight(34)
        self._btn_pe_clear.clicked.connect(lambda: (
            self._pe_table.setRowCount(0),
            self._pe_status.setText("")
        ))
        self._pe_status = QLabel("")
        self._pe_status.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        btn_row.addWidget(self._btn_pe_run)
        btn_row.addWidget(self._btn_pe_clear)
        btn_row.addWidget(self._pe_status, 1)
        input_lay.addLayout(btn_row)
        lay.addWidget(input_frame)

        # ── Results table ─────────────────────────────────────────────────────
        self._pe_table = _table([
            "Status", "Endpoint", "Cloud", "Resolved IP(s)",
            "Private?", "TCP", "TLS Days", "Findings"
        ])
        self._pe_table.setColumnWidth(0, 60)
        self._pe_table.setColumnWidth(1, 220)
        self._pe_table.setColumnWidth(2, 70)
        self._pe_table.setColumnWidth(3, 150)
        self._pe_table.setColumnWidth(4, 65)
        self._pe_table.setColumnWidth(5, 55)
        self._pe_table.setColumnWidth(6, 70)
        lay.addWidget(self._pe_table, 1)

        return w

    @pyqtSlot()
    def _run_pe_checks(self):
        from workers.scan_worker import PrivateEndpointWorker
        from modules.private_endpoint_checker import EndpointSpec

        raw = self._pe_input.toPlainText().strip()
        if not raw:
            self._pe_status.setText("⚠ Enter at least one endpoint above.")
            return
        if self._pe_worker and self._pe_worker.isRunning():
            return

        specs: list = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                # Could be host:port OR IPv6 — detect by counting colons
                parts = line.rsplit(":", 1)
                try:
                    port = int(parts[1])
                    host = parts[0].strip("[]")
                except ValueError:
                    host = line
                    port = 443
            else:
                host = line
                port = 443
            specs.append(EndpointSpec(host=host, port=port))

        if not specs:
            self._pe_status.setText("⚠ No valid endpoints parsed.")
            return

        self._pe_table.setRowCount(0)
        self._pe_status.setText(f"Checking {len(specs)} endpoint(s)…")
        self._btn_pe_run.setEnabled(False)

        self._pe_worker = PrivateEndpointWorker(specs)
        self._pe_worker.result.connect(self._on_pe_result)
        self._pe_worker.status.connect(self._pe_status.setText)
        self._pe_worker.error.connect(lambda e: self._pe_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._pe_worker.finished_all.connect(self._on_pe_done)
        self._pe_worker.start()

    @pyqtSlot()
    def _on_pe_done(self):
        total = self._pe_table.rowCount()
        fails = sum(
            1 for r in range(total)
            if (self._pe_table.item(r, 0) or QTableWidgetItem()).text() == "FAIL"
        )
        self._pe_status.setText(
            f"✓ Done — {total} endpoint(s), {fails} FAIL, {total - fails} OK."
        )
        self._btn_pe_run.setEnabled(True)

    # ── OS Detection helpers ───────────────────────────────────────────────────

    def _update_os_tab_from_m1(self) -> None:
        """Update OS Detection status when M1 data arrives — shows device count as CTA."""
        if not hasattr(self, "_os_status") or not getattr(self, "_m1_result", None):
            return
        devices = self._m1_result.get("devices", [])
        n = len(devices)
        if n > 0:
            s = "s" if n != 1 else ""
            self._os_status.setText(
                f"{n} device{s} discovered — click Fingerprint to detect operating systems "
                f"(requires admin + Npcap)"
            )

    def _prefill_os_from_m1(self) -> None:
        """Infer OS family from M1 device_type/vendor/hostname. Low-confidence — shown until active fingerprint runs."""
        if not hasattr(self, "_os_stack") or not getattr(self, "_m1_result", None):
            return
        devices = self._m1_result.get("devices", [])
        if not devices:
            return

        _OS_HINTS: dict[str, tuple] = {
            "router":         ("Linux / Router OS",    "Medium — inferred from role"),
            "gateway":        ("Linux / Router OS",    "Medium — inferred from role"),
            "switch":         ("Cisco IOS / Linux",    "Low — inferred from role"),
            "access point":   ("Linux (embedded)",     "Low — inferred from role"),
            "printer":        ("Embedded RTOS",        "Low — inferred from role"),
            "apple":          ("macOS / iOS",          "Medium — vendor match"),
            "samsung":        ("Android",              "Medium — vendor match"),
            "android":        ("Android",              "Medium — vendor match"),
            "windows":        ("Windows",              "Medium — hostname hint"),
            "linux":          ("Linux",                "Medium — hostname hint"),
            "raspberry":      ("Linux (Raspberry Pi)", "High — hostname match"),
            "synology":       ("DSM (Linux)",          "High — vendor match"),
            "qnap":           ("QTS (Linux)",          "High — vendor match"),
            "esxi":           ("VMware ESXi",          "High — hostname match"),
            "plex":           ("Linux",                "Medium — service hint"),
        }

        from PyQt6.QtWidgets import QTableWidgetItem as _TI
        from PyQt6.QtGui import QColor as _QC
        t = self._recon_os_table
        t.setRowCount(0)
        for d in devices:
            if isinstance(d, dict):
                ip          = d.get("ip", "")
                device_type = (d.get("device_type") or "").lower()
                vendor      = (d.get("vendor") or "").lower()
                hostname    = (d.get("hostname") or "").lower()
            else:
                ip          = getattr(d, "ip", "")
                device_type = (getattr(d, "device_type", "") or "").lower()
                vendor      = (getattr(d, "vendor", "") or "").lower()
                hostname    = (getattr(d, "hostname", "") or "").lower()

            combined = f"{device_type} {vendor} {hostname}"
            os_family, confidence = "Unknown", "Low — no hint available"
            for key, (fam, conf) in _OS_HINTS.items():
                if key in combined:
                    os_family, confidence = fam, conf
                    break

            row = t.rowCount()
            t.insertRow(row)
            for col, val in enumerate([ip, "—", os_family, confidence, "—", "—"]):
                item = _TI(val)
                item.setForeground(_QC(TEXT_SECONDARY if col in (1, 4, 5) else TEXT_PRIMARY))
                t.setItem(row, col, item)

        if t.rowCount() > 0:
            self._os_stack.setCurrentIndex(1)  # show table, hide empty state
            self._os_status.setText(
                f"Showing {t.rowCount()} inferred OS guesses from device discovery — "
                f"click Fingerprint to get accurate results"
            )

