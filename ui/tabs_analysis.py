"""
tabs_analysis.py — _AnalysisTabsMixin: IPv6, Cloud Metadata, Correlator, IoT Baseline, Benchmark tab builders.

Extracted from ui/dashboard.py (Sprint 13) to keep that file within budget.
Dashboard inherits _AnalysisTabsMixin.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSettings, pyqtSlot
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from ui.npcap_banner import NpcapMissingBanner
from ui.styles import (
    ACCENT, ACCENT_DARK, ACCENT_LITE, AMBER,
    BG_CARD, BG_HOVER, BORDER, BORDER_MED,
    CARD_RADIUS, BLUE,
    GRADE_A_BG, GRADE_B_BG, GRADE_B_FG, GRADE_C_BG,
    GRADE_D_BG, GRADE_F_BG, GRADE_F_FG, GREEN,
    RED, TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)
from ui.tabs_helpers import _page_header, _table


class _AnalysisTabsMixin:
    """Mixin providing analysis tab builders for Dashboard.

    Extracted from ui/dashboard.py (Sprint 13).
    Requires self._m1_result, self._m2_result, self._m3_result,
    self._diag_result, self._logger_worker, self._net_info, self._store,
    self._overview_page, self._home_page, self._monitor_overview_page,
    and self._nav_rail_go_to() to be provided by the host Dashboard class.
    """

    def _build_ipv6_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        top = QHBoxLayout()
        title = QLabel("🔷  IPv6 Devices")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        top.addWidget(title)
        top.addStretch()
        self._btn_ipv6_scan = QPushButton("▶  Scan IPv6")
        self._btn_ipv6_scan.setObjectName("btnDiag")
        self._btn_ipv6_scan.setFixedHeight(34)
        self._btn_ipv6_scan.clicked.connect(self._start_ipv6_scan)
        top.addWidget(self._btn_ipv6_scan)
        lay.addLayout(top)

        self._ipv6_status = QLabel(
            "Reads the OS IPv6 neighbour cache, then actively pings fe80::/8 on each interface."
        )
        self._ipv6_status.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(self._ipv6_status)

        self._ipv6_table = _table(["IPv6 Address", "MAC Address", "State", "Source"])
        self._ipv6_table.setColumnWidth(0, 340)
        self._ipv6_table.setColumnWidth(1, 150)
        self._ipv6_table.setColumnWidth(2, 110)
        self._ipv6_table.setColumnWidth(3, 80)
        lay.addWidget(self._ipv6_table, 1)
        return w

    @pyqtSlot()
    def _start_ipv6_scan(self):
        if self._ipv6_worker and self._ipv6_worker.isRunning():
            return
        from workers.scan_worker import IPv6Worker
        self._ipv6_table.setRowCount(0)
        self._btn_ipv6_scan.setEnabled(False)
        self._ipv6_worker = IPv6Worker()
        self._ipv6_worker.result.connect(self._on_ipv6_result)
        self._ipv6_worker.status.connect(self._ipv6_status.setText)
        self._ipv6_worker.error.connect(
            lambda e: self._ipv6_status.setText(f"⚠ {e}"),
            Qt.ConnectionType.QueuedConnection,
        )
        self._ipv6_worker.finished.connect(
            lambda: self._btn_ipv6_scan.setEnabled(True),
            Qt.ConnectionType.QueuedConnection,
        )
        self._ipv6_worker.start()


    # ── Cloud Metadata tab (Recon) ────────────────────────────────────────────

    def _build_recon_cloud_metadata_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        top = QHBoxLayout()
        title = QLabel("☁  Cloud Metadata Detection")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        top.addWidget(title)
        top.addStretch()
        self._btn_cloud_scan = QPushButton("▶  Run Check")
        self._btn_cloud_scan.setObjectName("btnDiag")
        self._btn_cloud_scan.setFixedHeight(34)
        self._btn_cloud_scan.clicked.connect(self._start_cloud_metadata)
        top.addWidget(self._btn_cloud_scan)
        lay.addLayout(top)

        self._cloud_status = QLabel(
            "Probes 169.254.169.254 (AWS/Azure/GCP) to detect if this machine is inside a cloud VM. "
            "Also checks network devices for SSRF metadata-proxy exposure."
        )
        self._cloud_status.setWordWrap(True)
        self._cloud_status.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(self._cloud_status)

        # Local IMDS result card
        self._cloud_local_box = QTextEdit()
        self._cloud_local_box.setReadOnly(True)
        self._cloud_local_box.setMaximumHeight(180)
        self._cloud_local_box.setStyleSheet(
            f"background:{BG_CARD}; color:{TEXT_PRIMARY}; font-size:11px;"
            f"border:1px solid {BORDER}; border-radius:{CARD_RADIUS}; padding:6px;"
        )
        self._cloud_local_box.setPlaceholderText(
            "IMDS probe result will appear here — runs in < 1 second per provider."
        )
        lay.addWidget(self._cloud_local_box)

        net_lbl = QLabel("  Network SSRF Exposure  (devices that proxy 169.254.169.254):")
        net_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; padding-top:4px;")
        lay.addWidget(net_lbl)
        self._cloud_network_table = _table(
            ["Device IP", "MAC", "Hostname", "Exposed?", "Risk", "Finding"]
        )
        self._cloud_network_table.setColumnWidth(0, 120)
        self._cloud_network_table.setColumnWidth(1, 140)
        self._cloud_network_table.setColumnWidth(2, 140)
        self._cloud_network_table.setColumnWidth(3, 75)
        self._cloud_network_table.setColumnWidth(4, 70)
        lay.addWidget(self._cloud_network_table, 1)
        return w

    @pyqtSlot()
    def _start_cloud_metadata(self):
        if self._cloud_worker and self._cloud_worker.isRunning():
            return
        from workers.scan_worker import CloudMetadataWorker
        self._cloud_local_box.clear()
        self._cloud_network_table.setRowCount(0)
        self._btn_cloud_scan.setEnabled(False)
        self._cloud_status.setText("Probing IMDS endpoints…")
        # Pass in last known devices if available
        devices = getattr(self, "_last_scan_devices", [])
        self._cloud_worker = CloudMetadataWorker(devices=devices)
        self._cloud_worker.local_result.connect(self._on_cloud_local_result)
        self._cloud_worker.network_result.connect(self._on_cloud_network_result)
        self._cloud_worker.status.connect(self._cloud_status.setText)
        self._cloud_worker.error.connect(
            lambda e: self._cloud_status.setText(f"⚠ {e}"),
            Qt.ConnectionType.QueuedConnection,
        )
        self._cloud_worker.finished.connect(
            lambda: self._btn_cloud_scan.setEnabled(True),
            Qt.ConnectionType.QueuedConnection,
        )
        self._cloud_worker.start()

    @pyqtSlot(object)


    # ── Log chart handler ─────────────────────────────────────────────────────

    @pyqtSlot()
    def _view_log_chart(self):
        if not self._log_chart_summary:
            return
        try:
            if getattr(self, "_chart_window", None) and self._chart_window.isVisible():
                self._chart_window.raise_()
                self._chart_window.activateWindow()
                return
        except RuntimeError:
            pass  # non-fatal
        try:
            from modules.log_chart import build_figure
            from ui.dashboard import _make_chart_window
            self._btn_log_chart.setEnabled(False)
            self._log_status_lbl.setText("Rendering chart…")
            fig = build_figure(self._log_chart_summary)
            self._chart_window = _make_chart_window(fig)
            self._chart_window.show()
            self._chart_window.raise_()
            self._chart_window.activateWindow()
            self._log_status_lbl.setText("Chart opened.")
        except Exception as exc:
            self._log_status_lbl.setText(f"Chart error: {exc}")
        finally:
            self._btn_log_chart.setEnabled(True)

    # ── Root Cause Analysis (Correlator) tab ─────────────────────────────────

    def _build_correlator_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        info = QLabel(
            "Automatically links findings from all scans — STP, Storm, Diagnostics, and the "
            "Stability Log — to identify the single root cause of your network problems. "
            "Distinguishes between a fault in your home network versus a problem at your ISP. "
            "Run at least one scan first, then click Analyse."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        self._corr_status = QLabel("No analysis yet — run scans first, then click Analyse.")
        self._corr_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._corr_status.setWordWrap(True)

        # Verdict banner
        self._corr_verdict = QLabel("Run a scan to see the root cause summary.")
        self._corr_verdict.setWordWrap(True)
        self._corr_verdict.setStyleSheet(
            f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:2px solid {BORDER}; "
            "border-radius:4px; padding:10px 14px; font-size:13px; font-weight:bold;"
        )

        ctrl = QHBoxLayout()
        btn_analyse = QPushButton("🧩  Analyse Root Cause Now")
        btn_analyse.setObjectName("btnScan")
        btn_analyse.setToolTip("Correlate all scan results and produce a prioritised root-cause list.")
        btn_analyse.clicked.connect(self._run_correlator)
        ctrl.addWidget(btn_analyse)
        ctrl.addStretch()

        # Findings table
        self._corr_table = _table([
            "Severity", "Category", "Source", "What's Wrong", "How to Fix It"
        ])
        self._corr_table.setColumnWidth(0, 80)
        self._corr_table.setColumnWidth(1, 200)
        self._corr_table.setColumnWidth(2, 160)
        self._corr_table.setColumnWidth(3, 300)

        lay.addWidget(info)
        lay.addWidget(self._corr_verdict)
        lay.addWidget(self._corr_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._corr_table, 1)
        return w

    @pyqtSlot()
    def _run_correlator(self):
        from PyQt6.QtGui import QColor
        try:
            from modules.root_cause_correlator import correlate

            # Gather available results — everything is optional
            diag   = self._diag_result
            m3_res = self._m3_result   # StormResult
            m1_dev = self._m1_result.get("devices", []) if self._m1_result else []
            gw_mac = self._net_info.get("gateway_mac", None) if self._net_info else None

            # Collect BPDU list from m2 result if present
            bpdus = []
            if self._m2_result and "bpdus" in self._m2_result:
                bpdus = self._m2_result["bpdus"]

            # Log summary from logger worker
            log_summary = None
            if self._logger_worker:
                try:
                    log_summary = self._logger_worker.get_summary()
                except Exception:
                    pass  # non-fatal — logger worker may be unavailable

            result = correlate(
                diag_result=diag,
                storm_result=m3_res,
                stp_bpdus=bpdus,
                fingerprint_devices=m1_dev,
                log_summary=log_summary,
                gateway_mac=gw_mac,
            )

            # Update verdict banner colour
            sev_colors = {
                "CRITICAL": RED, "HIGH": RED, "MEDIUM": AMBER,
                "LOW": GREEN, "INFO": TEXT_SECONDARY,
            }
            banner_color = sev_colors.get(result.global_severity, TEXT_SECONDARY)
            self._corr_verdict.setStyleSheet(
                f"background:{BG_CARD}; color:{banner_color}; "
                f"border:2px solid {banner_color}; border-radius:4px; "
                "padding:10px 14px; font-size:13px; font-weight:bold;"
            )
            self._corr_verdict.setText(result.plain_summary)

            # Populate findings table
            self._corr_table.setRowCount(0)
            for f in result.findings:
                row = self._corr_table.rowCount()
                self._corr_table.insertRow(row)
                color = sev_colors.get(f.severity, TEXT_SECONDARY)
                for col, val in enumerate([
                    f.severity, f.category, f.source, f.headline, f.remediation
                ]):
                    item = QTableWidgetItem(str(val))
                    if col in (0, 1):
                        item.setForeground(QColor(color))
                    self._corr_table.setItem(row, col, item)

            isp_tag = " [ISP issue — local alerts suppressed]" if result.suppress_local_alerts else ""
            self._corr_status.setText(
                f"Analysis complete — {result.finding_count} finding(s), "
                f"global severity: {result.global_severity}{isp_tag}"
            )

        except Exception as exc:
            self._corr_status.setText(f"⚠ Correlation failed: {exc}")

    # ── IoT Behavioural Baseline tab ─────────────────────────────────────────

    def _build_iot_baseline_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(_page_header(
            "IoT Behaviour",
            "Compares current traffic for any device against its normal pattern"
            " — deviations often indicate compromise, malfunction, or unusual activity.",
        ))
        lay.addWidget(NpcapMissingBanner(parent=w))

        info = QLabel(
            "NetSentinel learns what traffic is normal for every device on your network "
            "— IoT gadgets, laptops, phones, anything with an IP — and alerts you if one "
            "behaves differently, e.g. suddenly port-scanning, contacting an unusual server, "
            "flooding traffic, or a normally-quiet device becoming active. "
            "Run a Devices scan first, then click Learn to capture a baseline."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        self._iot_status = QLabel("No baseline loaded. Run 'Devices on Network' scan first.")
        self._iot_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._iot_status.setWordWrap(True)

        ctrl = QHBoxLayout()
        btn_learn = QPushButton("📖  Learn Normal Behaviour (60 s)")
        btn_learn.setObjectName("btnNetRefresh")
        btn_learn.setToolTip(
            "Sniffs traffic for 60 seconds to record which servers and ports each IoT device normally uses."
        )
        btn_learn.clicked.connect(self._run_iot_learn)

        btn_monitor = QPushButton("👁  Start Anomaly Monitor")
        btn_monitor.setObjectName("btnScan")
        btn_monitor.setToolTip("Continuously watches IoT device traffic and alerts on deviations from the baseline.")
        btn_monitor.clicked.connect(self._run_iot_monitor)

        btn_stop = QPushButton("⏹  Stop Monitor")
        btn_stop.setObjectName("btnNetRefresh")
        btn_stop.clicked.connect(self._stop_iot_monitor)

        self._iot_learn_duration = QSpinBox()
        self._iot_learn_duration.setRange(30, 600)
        self._iot_learn_duration.setValue(60)
        self._iot_learn_duration.setSuffix(" s")
        self._iot_learn_duration.setToolTip("How many seconds to observe traffic during the learning phase")
        self._iot_learn_duration.setFixedWidth(80)

        ctrl.addWidget(btn_learn)
        ctrl.addWidget(self._iot_learn_duration)
        ctrl.addSpacing(12)
        ctrl.addWidget(btn_monitor)
        ctrl.addWidget(btn_stop)
        ctrl.addStretch()

        # Baseline summary table
        self._iot_baseline_table = _table([
            "Device", "IP", "MAC", "Type", "Known IPs", "Known Ports", "Avg pps", "Learned"
        ])
        self._iot_baseline_table.setColumnWidth(0, 200)
        self._iot_baseline_table.setColumnWidth(1, 110)
        self._iot_baseline_table.setColumnWidth(2, 145)
        self._iot_baseline_table.setColumnWidth(3, 150)
        self._iot_baseline_table.setColumnWidth(4, 60)
        self._iot_baseline_table.setColumnWidth(5, 70)
        self._iot_baseline_table.setColumnWidth(6, 65)

        # Live alert table
        alerts_lbl = QLabel("Live Anomaly Alerts")
        alerts_lbl.setStyleSheet(f"color:{ACCENT_LITE};font-size:12px;font-weight:bold;padding:6px 0 2px 0;")
        self._iot_alert_table = _table([
            "Time", "Device", "Alert Type", "Severity", "Detail", "Remediation", "Action"
        ])
        self._iot_alert_table.setColumnWidth(0, 75)
        self._iot_alert_table.setColumnWidth(1, 170)
        self._iot_alert_table.setColumnWidth(2, 130)
        self._iot_alert_table.setColumnWidth(3, 75)
        self._iot_alert_table.setColumnWidth(4, 300)
        self._iot_alert_table.setColumnWidth(5, 180)
        self._iot_alert_table.setColumnWidth(6, 110)

        lay.addWidget(info)
        lay.addWidget(self._iot_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._iot_baseline_table)
        lay.addWidget(alerts_lbl)
        lay.addWidget(self._iot_alert_table, 1)

        self._iot_monitor_obj = None
        return w

    def _populate_iot_baseline_table(self, baselines: dict) -> None:
        self._iot_baseline_table.setRowCount(0)
        for mac, b in baselines.items():
            row = self._iot_baseline_table.rowCount()
            self._iot_baseline_table.insertRow(row)
            label = b.model or b.vendor or mac
            for col, val in enumerate([
                label, b.ip, mac, b.device_type,
                str(len(b.known_ips)), str(len(b.known_ports)),
                f"{b.avg_pps:.1f}", b.learned_at[:10] if b.learned_at else "—",
            ]):
                self._iot_baseline_table.setItem(row, col, QTableWidgetItem(str(val)))

    @pyqtSlot()
    def _run_iot_learn(self):
        if not self._m1_result:
            self._iot_status.setText("⚠ Run 'Devices on Network' scan first.")
            return
        devices = self._m1_result.get("devices", [])
        duration = self._iot_learn_duration.value()
        self._iot_status.setText(f"Learning for {duration} s — keep devices active…")
        try:
            from modules.iot_baseline import learn
            def _do_learn():
                baselines = learn(
                    devices=devices, duration_s=duration,
                    progress_cb=lambda m: self._iot_status.setText(m),
                )
                self._populate_iot_baseline_table(baselines)
                self._iot_status.setText(
                    f"Baseline learned for {len(baselines)} IoT device(s). "
                    "Click 'Start Anomaly Monitor' to watch for deviations."
                )
            import threading
            threading.Thread(target=_do_learn, daemon=True).start()
        except Exception as exc:
            self._iot_status.setText(f"⚠ Learn failed: {exc}")

    @pyqtSlot()
    def _run_iot_monitor(self):
        try:
            from modules.iot_baseline import load_or_create, IoTMonitor
            from PyQt6.QtGui import QColor

            if not self._m1_result:
                self._iot_status.setText("⚠ Run 'Devices on Network' scan first.")
                return

            devices = self._m1_result.get("devices", [])

            import threading
            import queue as _q
            from PyQt6.QtCore import QTimer as _QTimer

            _IOT_INVESTIGATE_TARGET = {
                "SYN_SCAN":       "Port Scan (TCP)",
                "NEW_PORT":       "Port Scan (TCP)",
                "NEW_DEST":       "Threat Intel",
                "METADATA_PROBE": "Cloud Metadata Probe",
                "RATE_SPIKE":     "Live Bandwidth",
            }

            # Stop any previous drain timer before (re)starting the monitor.
            if hasattr(self, "_iot_drain_timer") and self._iot_drain_timer is not None:
                self._iot_drain_timer.stop()
                self._iot_drain_timer = None

            # IoT alerts arrive from Scapy's AsyncSniffer thread; calling Qt widget
            # methods from that thread causes access violations (P1 crash). Use a
            # thread-safe queue and a main-thread QTimer to drain it safely.
            self._iot_queue = _q.Queue()

            def _drain_iot_alerts():
                try:
                    while True:
                        alert = self._iot_queue.get_nowait()
                        row = self._iot_alert_table.rowCount()
                        self._iot_alert_table.insertRow(row)
                        sev_color = RED if alert.severity == "CRITICAL" else (AMBER if alert.severity == "HIGH" else BLUE)
                        for col, val in enumerate([
                            alert.timestamp[11:19], alert.device_label,
                            alert.alert_type.replace("_", " ").title(),
                            alert.severity, alert.detail, alert.remediation,
                        ]):
                            item = QTableWidgetItem(str(val))
                            if col in (2, 3):
                                item.setForeground(QColor(sev_color))
                            self._iot_alert_table.setItem(row, col, item)
                        target = _IOT_INVESTIGATE_TARGET.get(alert.alert_type, "Devices")
                        inv_btn = QPushButton("Investigate →")
                        inv_btn.setFlat(True)
                        inv_btn.setStyleSheet(f"color:{ACCENT_LITE};font-size:11px;text-align:left;padding:2px 4px;")
                        inv_btn.clicked.connect(lambda _checked, t=target: self._nav_rail_go_to(t))
                        self._iot_alert_table.setCellWidget(row, 6, inv_btn)
                        self._iot_alert_table.scrollToBottom()
                        self._iot_status.setText(
                            f"⚠ Alert: {alert.alert_type} on {alert.device_label}"
                        )
                        if hasattr(self, "_monitor_overview_page"):
                            self._monitor_overview_page.set_iot_anomaly_count(
                                self._iot_alert_table.rowCount()
                            )
                        # V6 Sprint 2 — IOT_BEHAVIOR: route the same signal through
                        # AlertEngine so it becomes a real toast/digest alert instead
                        # of a page-only table row.
                        if self._alert_engine is not None:
                            for a in self._alert_engine.evaluate_iot_behavior_checks([alert]):
                                self._show_alert_toast(a)
                                self._home_page.on_alert(a)
                                if self._store is not None:
                                    try:
                                        self._store.record_alert_fired(
                                            a.rule_name, a.host, a.severity, a.message, ts=a.ts,
                                        )
                                    except Exception:
                                        pass  # non-fatal — persistence failure must not block the drain loop
                except _q.Empty:
                    pass  # queue exhausted — all pending alerts processed this tick

            self._iot_drain_timer = _QTimer(self)
            self._iot_drain_timer.setInterval(100)
            self._iot_drain_timer.timeout.connect(_drain_iot_alerts)
            self._iot_drain_timer.start()

            def _start():
                baselines = load_or_create(
                    devices=devices,
                    progress_cb=lambda m: self._iot_status.setText(m),
                )
                if not baselines:
                    self._iot_status.setText("⚠ No IoT baselines — run Learn first.")
                    return
                self._populate_iot_baseline_table(baselines)

                def _on_alert(alert):
                    # Called from Scapy's background thread — enqueue for main-thread drain
                    self._iot_queue.put(alert)

                self._iot_monitor_obj = IoTMonitor(
                    baselines=baselines,
                    on_alert=_on_alert,
                    on_error=lambda m: self._iot_status.setText(f"⚠ {m}"),
                )
                self._iot_monitor_obj.start()
                self._iot_status.setText(
                    f"Monitoring {len(baselines)} IoT device(s) — watching for anomalies…"
                )

            threading.Thread(target=_start, daemon=True).start()

        except Exception as exc:
            self._iot_status.setText(f"⚠ Monitor failed: {exc}")

    @pyqtSlot()
    def _stop_iot_monitor(self):
        if self._iot_monitor_obj:
            self._iot_monitor_obj.stop()
            self._iot_monitor_obj = None
        if hasattr(self, "_iot_drain_timer") and self._iot_drain_timer is not None:
            self._iot_drain_timer.stop()
            self._iot_drain_timer = None
        self._iot_status.setText("Anomaly monitor stopped.")

    # ── Network Grade (Benchmark) tab ─────────────────────────────────────────

    def _build_benchmark_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QStackedWidget as _SW
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        # Content stack: page 0 = empty state, page 1 = grade content
        self._bm_stack = _SW()

        # ── Page 0: empty state ────────────────────────────────────────────────
        _empty_w = QWidget()
        _el = QVBoxLayout(_empty_w)
        _el.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _el.setSpacing(10)
        _el.setContentsMargins(40, 60, 40, 60)

        _icon_lbl = QLabel("◎")
        _icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _icon_lbl.setStyleSheet(
            f"font-size:48px; color:{BORDER_MED}; background:transparent; border:none;"
        )
        _desc_lbl = QLabel(
            "Grade your network across 8 health dimensions — Uptime, Latency, Jitter, "
            "DNS Speed, Download Speed, Device Safety, STP Health, and Broadcast Storm Level — "
            "compared against a perfect home network baseline."
        )
        _desc_lbl.setWordWrap(True)
        _desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _desc_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px; background:transparent; border:none; max-width:520px;"
        )
        _btn_scan_grade = QPushButton("◎  Scan & Grade")
        _btn_scan_grade.setObjectName("btnScan")
        _btn_scan_grade.setFixedHeight(36)
        _btn_scan_grade.clicked.connect(self._scan_and_grade)
        _el.addWidget(_icon_lbl)
        _el.addSpacing(4)
        _el.addWidget(_desc_lbl)
        _el.addSpacing(12)
        _el.addWidget(_btn_scan_grade, alignment=Qt.AlignmentFlag.AlignCenter)
        self._bm_stack.addWidget(_empty_w)

        # ── Page 1: grade content ──────────────────────────────────────────────
        _content_w = QWidget()
        _cl = QVBoxLayout(_content_w)
        _cl.setContentsMargins(0, 0, 0, 0)
        _cl.setSpacing(6)

        info = QLabel(
            "Compares your network against a 'Perfect Home Network' baseline and gives "
            "an A–F letter grade across Uptime, Latency, Jitter, DNS Speed, Download Speed, "
            "Device Safety, STP Health, and Broadcast Storm Level."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        # Grade display
        grade_row = QHBoxLayout()
        self._bm_grade_label = QLabel("—")
        self._bm_grade_label.setFixedSize(90, 90)
        self._bm_grade_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bm_grade_label.setStyleSheet(
            "font-size:40px; font-weight:bold; border-radius:45px; "
            f"background:{BG_CARD}; border:3px solid {BORDER}; color:{TEXT_PRIMARY};"
        )
        self._bm_score_label = QLabel("Score: —")
        self._bm_score_label.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:16px; font-weight:bold;"
        )
        self._bm_verdict_label = QLabel("Click Grade My Network to score your connection.")
        self._bm_verdict_label.setWordWrap(True)
        self._bm_verdict_label.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px; max-width:500px;"
        )
        grade_text = QVBoxLayout()
        grade_text.addWidget(self._bm_score_label)
        grade_text.addWidget(self._bm_verdict_label)
        grade_row.addWidget(self._bm_grade_label)
        grade_row.addSpacing(16)
        grade_row.addLayout(grade_text)
        grade_row.addStretch()

        ctrl = QHBoxLayout()
        btn_grade = QPushButton("◎  Grade My Network")
        btn_grade.setObjectName("btnScan")
        btn_grade.setToolTip("Score your network health across all available dimensions.")
        btn_grade.clicked.connect(self._run_benchmark)
        btn_isp = QPushButton("⊟  Network Health Report")
        btn_isp.setObjectName("btnNetRefresh")
        btn_isp.setToolTip(
            "Export a Network Health Report — hop table, outages, grade — "
            "as HTML you can print to PDF and attach to an ISP support ticket."
        )
        btn_isp.clicked.connect(self._export_isp_report)
        btn_isp_copy = QPushButton("◇  Copy ISP Complaint")
        btn_isp_copy.setObjectName("btnNetRefresh")
        btn_isp_copy.setToolTip(
            "Copy a ready-to-email complaint script to your clipboard. "
            "Uses NetSentinel's own measurements — no manual steps required."
        )
        btn_isp_copy.clicked.connect(self._copy_isp_complaint)
        btn_isp_reddit = QPushButton("◇  Copy as Reddit post")
        btn_isp_reddit.setObjectName("btnNetRefresh")
        btn_isp_reddit.setToolTip(
            "Copy a sanitized, forum-ready Markdown post for r/HomeNetworking. "
            "Public IP omitted, private IPs masked — safe to paste publicly."
        )
        btn_isp_reddit.clicked.connect(self._copy_isp_reddit_post)
        ctrl.addWidget(btn_grade)
        ctrl.addWidget(btn_isp)
        ctrl.addWidget(btn_isp_copy)
        ctrl.addWidget(btn_isp_reddit)
        ctrl.addStretch()

        # Quiet "your grade improved — share it" strip (Feature 3b), hidden until
        # a genuine improvement between the last two grade runs is detected.
        self._grade_share_card = self._build_grade_share_card()

        # Dimension breakdown table
        self._bm_table = _table(["Dimension", "Grade", "Your Value", "Ideal", "Verdict", "Fix Tip"])

        _cl.addWidget(info)
        _cl.addLayout(grade_row)
        _cl.addSpacing(6)
        _cl.addLayout(ctrl)
        _cl.addWidget(self._grade_share_card)
        _cl.addWidget(self._bm_table, 1)
        self._bm_stack.addWidget(_content_w)

        lay.addWidget(self._bm_stack, 1)
        return w

    def _build_grade_share_card(self) -> QWidget:
        """Quiet inline 'Share this result' strip for the benchmark tab.
        Hidden by default; shown by _show_grade_share_card() only when the
        network grade improves versus the previous run (Feature 3b)."""
        card = QFrame()
        card.setObjectName("gradeShareCard")
        card.setStyleSheet(
            f"QFrame#gradeShareCard {{ background:{BG_HOVER}; border:1px solid {ACCENT};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 6, 12, 6)
        row.setSpacing(10)

        self._grade_share_lbl = QLabel("Your grade improved — share it")
        self._grade_share_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:12px; font-weight:600; border:none;"
            f" background:transparent;"
        )
        row.addWidget(self._grade_share_lbl)
        row.addStretch()

        _btn_qss = (
            f"QPushButton {{ background:{BG_CARD}; color:{ACCENT};"
            f" border:1px solid {ACCENT}; padding:4px 12px; font-size:11px;"
            f" border-radius:4px; }}"
            f"QPushButton:hover {{ background:{ACCENT}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
        )
        self._grade_share_img_btn = QPushButton("Copy as image")
        self._grade_share_img_btn.setStyleSheet(_btn_qss)
        self._grade_share_img_btn.clicked.connect(self._copy_grade_image)
        row.addWidget(self._grade_share_img_btn)

        self._grade_share_md_btn = QPushButton("Copy as Markdown")
        self._grade_share_md_btn.setStyleSheet(_btn_qss)
        self._grade_share_md_btn.clicked.connect(self._copy_isp_reddit_post)
        row.addWidget(self._grade_share_md_btn)

        card.hide()
        return card

    def _show_grade_share_card(self, prev_grade: str, new_grade: str) -> None:
        self._grade_share_lbl.setText(
            f"Your grade improved {prev_grade} → {new_grade} — share it"
        )
        self._grade_share_card.show()

    @pyqtSlot()
    def _copy_grade_image(self):
        """Copy the diagnostic grade card as an image to the clipboard."""
        try:
            from modules.diagnostic_card import build_card_data
            from ui.widgets.diagnostic_card_widget import render_card_widget
            from PyQt6.QtWidgets import QApplication
            card_data = build_card_data(
                self._last_benchmark_result, self._diag_result, self._store
            )
            widget = render_card_widget(card_data)
            widget.show()          # must be visible for grab() to paint correctly
            widget.hide()
            QApplication.clipboard().setPixmap(widget.grab())
            widget.deleteLater()
            from ui.widgets.toast import ToastManager
            ToastManager.show("Grade card copied as image", "success")
        except Exception as exc:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Copy Failed", str(exc))

    @pyqtSlot()
    def _scan_and_grade(self):
        """Empty-state CTA: start a full scan then auto-grade when done."""
        self._bm_stack.setCurrentIndex(1)
        self._bm_verdict_label.setText("Scanning your network…")
        self._pending_benchmark = True
        self._start_full_scan()

    @pyqtSlot()
    def _run_benchmark(self):
        self._bm_stack.setCurrentIndex(1)
        from PyQt6.QtGui import QColor
        try:
            from modules.network_benchmark import grade as bm_grade

            log_summary = None
            if self._logger_worker:
                try:
                    log_summary = self._logger_worker.get_summary()
                except Exception:
                    pass  # non-fatal — logger worker may be unavailable

            result = bm_grade(
                log_summary=log_summary,
                diag_result=self._diag_result,
                m1_result=self._m1_result,
                m2_result=self._m2_result,
                m3_result=self._m3_result,
            )
            self._last_benchmark_result = result
            # V6 Sprint 1 — GRADE_REGRESSION: capture the prior grade before overwriting it.
            _prior_grade = None
            _prior_row = None
            try:
                _prior_row = self._store.query_last_grade()
                _prior_grade = _prior_row.get("grade") if _prior_row else None
            except Exception:
                pass  # non-fatal
            try:
                self._store.record_grade(result.overall_grade, result.overall_score, result.overall_verdict)
            except Exception:
                pass  # non-fatal
            if self._alert_engine is not None:
                for a in self._alert_engine.evaluate_grade_check(
                    result.overall_grade, result.overall_score, result.overall_verdict, _prior_grade,
                ):
                    self._show_alert_toast(a)
                    self._home_page.on_alert(a)
                    try:
                        self._store.record_alert_fired(a.rule_name, a.host, a.severity, a.message, ts=a.ts)
                    except Exception:
                        pass  # non-fatal — persistence failure must not block grade display

            # Update grade circle
            grade_styles = {
                "A": (GREEN,       GRADE_A_BG),
                "B": (GRADE_B_FG,  GRADE_B_BG),
                "C": (AMBER,       GRADE_C_BG),
                "D": (RED,         GRADE_D_BG),
                "F": (GRADE_F_FG,  GRADE_F_BG),
                "N/A": (TEXT_SECONDARY, BG_CARD),
            }
            fg, bg = grade_styles.get(result.overall_grade, (TEXT_SECONDARY, BG_CARD))
            self._bm_grade_label.setText(result.overall_grade)
            self._bm_grade_label.setStyleSheet(
                f"font-size:40px; font-weight:bold; border-radius:45px; "
                f"background:{bg}; border:3px solid {fg}; color:{fg};"
            )
            self._bm_score_label.setText(f"Score: {result.overall_score:.0f}/100")
            self._bm_score_label.setStyleSheet(f"color:{fg}; font-size:16px; font-weight:bold;")
            self._bm_verdict_label.setText(result.overall_verdict)
            self._overview_page.on_grade(result.overall_grade, result.overall_score)
            self._home_page.on_grade(result.overall_grade, result.overall_score)
            self._home_page.on_grade_details(result.overall_grade, result.overall_score,
                                             getattr(result, "dimensions", []))
            if hasattr(self._home_page, "_update_this_week"):
                self._home_page._update_this_week()
            if hasattr(self, "_monitor_overview_page"):
                self._monitor_overview_page.set_grade(result.overall_grade, result.overall_score)
                self._monitor_overview_page.set_grade_details(result.overall_grade,
                                                              result.overall_score,
                                                              getattr(result, "dimensions", []))
            QSettings("NetSentinel", "NetSentinel").setValue("grade/last_run", True)
            self._home_page.refresh_checklist()
            from modules.diagnostic_card import build_card_data
            self._overview_page.set_card_data(
                build_card_data(result, self._diag_result, self._store)
            )

            # Feature 3b — surface a quiet "share it" strip only on a genuine
            # score improvement between the last two grade runs. query_previous_grade()
            # runs AFTER record_grade above, so it returns the prior grade.
            try:
                _prev = self._store.query_previous_grade()
                _prev_score = float(_prev.get("score", 0.0) or 0.0) if _prev else None
                if _prev_score is not None and result.overall_score > _prev_score:
                    self._show_grade_share_card(_prev.get("grade", "?"), result.overall_grade)
                else:
                    self._grade_share_card.hide()
            except Exception:
                self._grade_share_card.hide()  # non-fatal — share prompt is optional

            if hasattr(self, "_tray_manager") and self._tray_manager:
                self._tray_manager.set_grade(result.overall_grade)

            _GRADE_FIX_TARGET = {
                "Connection Uptime":          "Availability History",
                "Average Latency":            "DNS & Stability",
                "Jitter (Call Quality)":      "DNS & Stability",
                "DNS Response Speed":         "DNS & Stability",
                "Download Speed":             "Speed Test",
                "Network Device Safety":      "Devices",
                "Spanning Tree (STP) Health": "Rogue Bridge (STP)",
                "Broadcast Storm Level":      "Broadcast Storm",
            }
            # Populate dimension table
            self._bm_table.setRowCount(0)
            for d in result.dimensions:
                row = self._bm_table.rowCount()
                self._bm_table.insertRow(row)
                grade_color = {
                    "A": GREEN, "B": GRADE_B_FG, "C": AMBER, "D": RED, "F": GRADE_F_FG
                }.get(d.grade, TEXT_SECONDARY)
                for col, val in enumerate([
                    d.name, d.grade, d.value_label, d.ideal_label, d.verdict, d.tip
                ]):
                    item = QTableWidgetItem(str(val))
                    if col == 1:
                        item.setForeground(QColor(grade_color))
                    self._bm_table.setItem(row, col, item)
                if d.grade in ("D", "F"):
                    target = _GRADE_FIX_TARGET.get(d.name)
                    if target:
                        fix_btn = QPushButton(f"Fix this →")
                        fix_btn.setFlat(True)
                        fix_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                        fix_btn.setStyleSheet(
                            f"QPushButton{{color:{ACCENT};font-size:10px;background:transparent;"
                            f"border:none;text-align:left;padding:0 4px;}}"
                            f"QPushButton:hover{{color:{ACCENT_DARK};}}"
                            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
                        )
                        fix_btn.clicked.connect(
                            lambda _checked, t=target: self._nav_rail_go_to(t)
                        )
                        self._bm_table.setCellWidget(row, 5, fix_btn)

            self._bm_table.resizeColumnsToContents()

        except Exception as exc:
            self._bm_verdict_label.setText(f"⚠ Grading failed: {exc}")
