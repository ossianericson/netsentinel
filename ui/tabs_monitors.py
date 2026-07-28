"""
tabs_monitors.py — _MonitorTabsMixin: Topology/ARP/DHCP/Bandwidth/Scheduler/SNMP
tab builders + event handlers.

Extracted from ui/dashboard.py (P7 — dashboard.py diet).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSettings, pyqtSlot
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.npcap_banner import NpcapMissingBanner
from ui import styles as _s
from ui.tabs_helpers import _empty_state_widget, _table
from ui.monitor_state import _color_for_level


class _MonitorTabsMixin:
    """Mixin providing Topology/ARP/DHCP/Bandwidth/Scheduler/SNMP tab builders.

    Extracted from ui/dashboard.py (P7 — dashboard.py diet).
    """

    # ── Topology tab (Sprint 6 — NetworkMapPage) ─────────────────────────────

    def _build_topology_tab(self) -> QWidget:
        from ui.pages.network_map_page import NetworkMapPage
        from ui.widgets.device_detail_pane import _DeviceDrawer

        page = NetworkMapPage(store=self._store)
        self._network_map_page = page

        # self._topology_widget → classic (matplotlib) widget kept for
        # backward-compat with network_doc_page which accesses ._fig
        self._topology_widget = page.classic_widget

        # Expose the diff toolbar controls from the page so that
        # scan_wiring.py's getattr(self, "_btn_topo_diff") / "_topo_diff_lbl"
        # references continue to work without modification.
        self._btn_topo_diff = page.btn_diff
        self._topo_diff_lbl = page.diff_label

        # Diff state — still managed by Dashboard for cross-scan persistence
        self._topo_diff      = None   # TopologyDiff | None — set by scan_wiring
        self._topo_diff_mode = False

        page.node_clicked.connect(self._on_topology_node_clicked)
        page.scan_requested.connect(self._start_full_scan)
        page.btn_diff.toggled.connect(self._on_topo_diff_toggled)

        self._topology_drawer = _DeviceDrawer(page)
        return page

    @pyqtSlot(bool)
    def _on_topo_diff_toggled(self, checked: bool) -> None:
        """Re-render topology with or without the change-detection overlay."""
        self._topo_diff_mode = checked
        if not hasattr(self, "_network_map_page"):
            return
        kw = dict(self._network_map_page._last_render_kwargs)
        if not kw:
            return
        kw["diff"] = self._topo_diff if checked else None
        try:
            self._network_map_page.render(**kw)
        except Exception:
            pass  # non-fatal — diff overlay is best-effort

    @pyqtSlot(str)
    def _on_topology_node_clicked(self, ip: str) -> None:
        """Open _DeviceDrawer for the topology node the user clicked."""
        if not getattr(self, "_m1_result", None) or not hasattr(self, "_topology_drawer"):
            return
        devices = self._m1_result.get("devices", [])
        mac = ""
        for d in devices:
            d_ip = d.get("ip", "") if isinstance(d, dict) else getattr(d, "ip", "")
            if d_ip == ip:
                mac = d.get("mac", "") if isinstance(d, dict) else getattr(d, "mac", "")
                break
        if not mac:
            return
        self._topology_drawer.load(mac, self._store)
        if not self._topology_drawer.isVisible():
            self._topology_drawer.open_drawer()

    # ── ARP monitor tab ───────────────────────────────────────────────────────

    def _build_arp_monitor_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(NpcapMissingBanner(parent=w))
        self._arp_status = QLabel("ARP spoof monitor not running.")
        _s.themed_ss(self._arp_status, "color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        btn_row = QHBoxLayout()
        btn_start = QPushButton("▶  Start ARP Monitor (30s)")
        btn_start.setObjectName("btnNetRefresh")
        btn_start.clicked.connect(self._start_arp_monitor)
        btn_row.addWidget(btn_start)
        btn_row.addStretch()
        self._arp_table = _table(["Type", "Attacker MAC", "Attacker IP", "Victim IP", "Original MAC", "Verdict"])
        self._arp_table.setColumnWidth(0, 110)
        self._arp_table.setColumnWidth(1, 145)
        self._arp_table.setColumnWidth(2, 120)
        self._arp_table.setColumnWidth(5, 400)
        # Empty state shown when monitor hasn't started / no events yet
        from PyQt6.QtWidgets import QStackedWidget as _SW
        self._arp_stack = _SW()
        self._arp_stack.addWidget(_empty_state_widget(
            "⊙", "ARP Watch not running",
            "Real-time detection of devices impersonating your router.",
            "Start ARP Watch", self._start_arp_monitor,
        ))
        self._arp_stack.addWidget(self._arp_table)
        lay.addWidget(self._arp_status)
        lay.addLayout(btn_row)
        lay.addWidget(self._arp_stack, 1)

        from ui.widgets.explainer_panel import ExplainerPanel
        self._arp_explainer = ExplainerPanel("rogue_device")
        self._arp_explainer.navigate_to.connect(self._nav_rail_go_to)
        lay.addWidget(self._arp_explainer)
        return w

    @pyqtSlot()
    def _start_arp_monitor(self):
        from workers.scan_worker import ARPMonitorWorker
        if self._arp_worker and self._arp_worker.isRunning():
            return
        self._arp_table.setRowCount(0)
        gateway_ip = self._net_info.get("gateway") if self._net_info else None
        self._arp_worker = ARPMonitorWorker(gateway_ip=gateway_ip, duration=30)
        self._arp_worker.event_found.connect(self._on_arp_event)
        self._arp_worker.result.connect(lambda r: self._arp_status.setText(r.plain_verdict), Qt.ConnectionType.QueuedConnection)
        self._arp_worker.status.connect(self._arp_status.setText)
        self._arp_worker.error.connect(lambda e: self._arp_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._arp_worker.finished.connect(self._push_monitor_pills)
        self._arp_worker.start()
        self._arp_status.setText("ARP monitor started…")
        QSettings("NetSentinel", "NetSentinel").setValue("home/setup/arp_started", True)
        self._save_monitor_state("arp", True)
        self._push_monitor_pills()
        self._set_flyout_dot("ARP Spoof Watch", _s.GREEN)

    @pyqtSlot(object)
    def _on_arp_event(self, event):
        self._arp_stack.setCurrentIndex(1)   # switch from empty state to table
        row = self._arp_table.rowCount()
        self._arp_table.insertRow(row)
        level = "HIGH" if event.event_type in ("GATEWAY_HIJACK",) else "MEDIUM"
        for col, val in enumerate([
            event.event_type, event.attacker_mac, event.attacker_ip,
            event.victim_ip, event.original_mac, event.verdict
        ]):
            item = QTableWidgetItem(str(val))
            item.setForeground(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(
                _color_for_level(level)
            ))
            self._arp_table.setItem(row, col, item)
        # Route through the same evaluator the background ARP watcher uses
        # (evaluate_arp_watch_checks() reads only report.events) so this event
        # gains the "ARP Spoof Detected" rule's opt-in gate, cooldown,
        # maintenance-window suppression, and Alert History persistence,
        # instead of an ungated raw tray balloon.
        if self._alert_engine is not None:
            from types import SimpleNamespace
            from modules.scan_persistence import persist_alert

            for a in self._alert_engine.evaluate_arp_watch_checks(
                SimpleNamespace(events=[event])
            ):
                self._surface_alert_in_app(a)
                self._home_page.on_alert(a)
                try:
                    persist_alert(self._store, a)
                except Exception:
                    pass  # non-fatal — persistence failure must not break the ARP monitor

    # ── DHCP monitor tab ──────────────────────────────────────────────────────

    def _build_dhcp_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(NpcapMissingBanner(parent=w))
        self._dhcp_status = QLabel("DHCP rogue server monitor not running.")
        _s.themed_ss(self._dhcp_status, "color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        btn_row = QHBoxLayout()
        btn_start = QPushButton("▶  Send DHCP Discover")
        btn_start.setObjectName("btnNetRefresh")
        btn_start.clicked.connect(self._start_dhcp_scan)
        btn_row.addWidget(btn_start)
        btn_row.addStretch()
        self._dhcp_table = _table(["Server IP", "Server MAC", "Offered IP", "Gateway", "DNS", "Lease", "Rogue?", "Verdict"])
        self._dhcp_table.setColumnWidth(7, 400)
        lay.addWidget(self._dhcp_status)
        lay.addLayout(btn_row)
        lay.addWidget(self._dhcp_table, 1)
        return w

    @pyqtSlot()
    def _start_dhcp_scan(self):
        from workers.scan_worker import DHCPDetectorWorker
        if self._dhcp_worker and self._dhcp_worker.isRunning():
            return
        self._dhcp_table.setRowCount(0)
        self._dhcp_worker = DHCPDetectorWorker(duration=10)
        self._dhcp_worker.offer_found.connect(self._on_dhcp_offer)
        self._dhcp_worker.result.connect(lambda r: self._dhcp_status.setText(r.plain_verdict), Qt.ConnectionType.QueuedConnection)
        self._dhcp_worker.result.connect(self._on_dhcp_scan_result, Qt.ConnectionType.QueuedConnection)
        self._dhcp_worker.status.connect(self._dhcp_status.setText)
        self._dhcp_worker.error.connect(lambda e: self._dhcp_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._dhcp_worker.finished.connect(self._push_monitor_pills)
        self._dhcp_worker.start()
        self._dhcp_status.setText("DHCP discover sent — listening for offers…")
        self._push_monitor_pills()
        self._set_flyout_dot("DHCP Rogue Monitor", _s.GREEN)

    @pyqtSlot(object)
    def _on_dhcp_offer(self, offer):
        row = self._dhcp_table.rowCount()
        self._dhcp_table.insertRow(row)
        level = "HIGH" if offer.is_rogue else "CLEAN"
        for col, val in enumerate([
            offer.server_ip, offer.server_mac, offer.offered_ip,
            offer.gateway, ", ".join(offer.dns_servers),
            f"{offer.lease_time}s", "YES ⚠" if offer.is_rogue else "No",
            offer.verdict,
        ]):
            item = QTableWidgetItem(str(val))
            item.setForeground(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(
                _color_for_level(level)
            ))
            self._dhcp_table.setItem(row, col, item)

    # ── Bandwidth tab ─────────────────────────────────────────────────────────

    def _build_bandwidth_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(NpcapMissingBanner(parent=w))
        self._bw_status = QLabel("Bandwidth monitor not running. Requires admin + Npcap.")
        _s.themed_ss(self._bw_status, "color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        btn_row = QHBoxLayout()
        btn_start = QPushButton("▶  Start Bandwidth Monitor")
        btn_start.setObjectName("btnNetRefresh")
        btn_start.clicked.connect(self._start_bandwidth_monitor)
        btn_stop = QPushButton("■  Stop")
        btn_stop.setObjectName("btnNetRefresh")
        btn_stop.clicked.connect(self._stop_bandwidth_monitor)
        btn_row.addWidget(btn_start)
        btn_row.addWidget(btn_stop)
        btn_row.addStretch()
        self._bw_table = _table(["MAC / Label", "TX (kbps)", "RX (kbps)", "Total (kbps)", "Total (Mbps)"])
        from PyQt6.QtWidgets import QStackedWidget as _SW2
        self._bw_stack = _SW2()
        self._bw_stack.addWidget(_empty_state_widget(
            "▲", "No traffic captured yet",
            "Live traffic by device, updated every second.",
            "Start Monitor", self._start_bandwidth_monitor,
        ))
        self._bw_stack.addWidget(self._bw_table)
        lay.addWidget(self._bw_status)
        lay.addLayout(btn_row)
        lay.addWidget(self._bw_stack, 1)
        return w

    def _device_label_resolver(self):
        """Shared MAC → display-name resolver for the live monitor views.

        Built lazily so the mixin does not depend on Dashboard.__init__ ordering.
        """
        resolver = getattr(self, "_dev_label_resolver", None)
        if resolver is None:
            from ui.device_labels import DeviceLabelResolver
            resolver = DeviceLabelResolver(store=getattr(self, "_store", None))
            self._dev_label_resolver = resolver
        return resolver

    @pyqtSlot()
    def _start_bandwidth_monitor(self):
        from workers.scan_worker import BandwidthWorker
        if self._bw_worker and self._bw_worker.isRunning():
            return
        # Build label map from M1 results if available
        label_map: dict = {}
        if self._m1_result:
            for d in self._m1_result.get("devices", []):
                mac = d.get("mac", "") if isinstance(d, dict) else (getattr(d, "mac", "") or "")
                host = d.get("hostname", "") if isinstance(d, dict) else (getattr(d, "hostname", "") or "")
                vendor = d.get("vendor", "") if isinstance(d, dict) else (getattr(d, "vendor", "") or "")
                if mac:
                    label_map[mac.lower()] = host or vendor or mac
        from modules.utils_net import get_local_mac_label_map
        label_map.update(get_local_mac_label_map())
        self._device_label_resolver().set_label_map(label_map)
        self._bw_worker = BandwidthWorker(interval_s=5.0, label_map=label_map)
        self._bw_worker.snapshot.connect(self._on_bw_snapshot)
        self._bw_worker.status.connect(self._bw_status.setText)
        self._bw_worker.error.connect(lambda e: self._bw_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._bw_worker.start()
        self._save_monitor_state("bandwidth", True)

    @pyqtSlot()
    def _stop_bandwidth_monitor(self):
        if self._bw_worker:
            self._bw_worker.stop()
            self._bw_status.setText("Bandwidth monitor stopped.")
            self._save_monitor_state("bandwidth", False)

    @pyqtSlot(object)
    def _on_bw_snapshot(self, snap):
        self._bw_stack.setCurrentIndex(1)   # switch from empty state to table
        self._bw_table.setRowCount(0)
        resolver = self._device_label_resolver()
        for entry in snap.entries:
            row = self._bw_table.rowCount()
            self._bw_table.insertRow(row)
            total_kbps = entry.total_bps / 1000
            level = "HIGH" if total_kbps > 5000 else ("MEDIUM" if total_kbps > 500 else "CLEAN")
            for col, val in enumerate([
                resolver.label_for_entry(entry.mac, entry.label or ""),
                f"{entry.tx_bps/1000:.1f}",
                f"{entry.rx_bps/1000:.1f}",
                f"{total_kbps:.1f}",
                f"{entry.total_mbps:.3f}",
            ]):
                item = QTableWidgetItem(str(val))
                item.setForeground(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(
                    _color_for_level(level)
                ))
                self._bw_table.setItem(row, col, item)
        self._bw_status.setText(
            f"Bandwidth snapshot ({snap.window_s:.0f}s window) — "
            f"{len(snap.entries)} device(s)"
        )

    # ── Scheduler tab ─────────────────────────────────────────────────────────

    def _build_scheduler_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        self._sched_status = QLabel("Scheduled scanner not running.")
        _s.themed_ss(self._sched_status, "color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        ctrl_row = QHBoxLayout()
        self._sched_interval = QSpinBox()
        self._sched_interval.setRange(1, 1440)
        self._sched_interval.setValue(15)
        self._sched_interval.setSuffix(" min")
        self._sched_interval.setFixedWidth(_s.SPINBOX_WIDTH_WITH_SUFFIX)
        # background-color/color/font-size ONLY -- the global MAIN_STYLE QSpinBox
        # rule has border/padding, which makes the +/- buttons unclickable under
        # windows11 (see style_spinbox() docstring) -- override it here.
        _s.themed_ss(self._sched_interval, "QSpinBox {{ background:{BG_DARK}; font-size:11px; color:{TEXT_PRIMARY}; }}")
        _s.style_spinbox(self._sched_interval)
        btn_start = QPushButton("▶  Start Scheduler")
        btn_start.setObjectName("btnNetRefresh")
        btn_start.clicked.connect(self._start_scheduler)
        btn_stop = QPushButton("■  Stop")
        btn_stop.setObjectName("btnNetRefresh")
        btn_stop.clicked.connect(self._stop_scheduler)
        ctrl_row.addWidget(QLabel("Interval:"))
        ctrl_row.addWidget(self._sched_interval)
        ctrl_row.addWidget(btn_start)
        ctrl_row.addWidget(btn_stop)
        ctrl_row.addStretch()
        self._sched_log = QTextEdit()
        self._sched_log.setReadOnly(True)
        _s.themed_ss(self._sched_log, "background:{BG_CARD};color:{TEXT_PRIMARY};font-size:11px;")
        lay.addWidget(self._sched_status)
        lay.addLayout(ctrl_row)
        lay.addWidget(self._sched_log, 1)
        return w

    @pyqtSlot()
    def _start_scheduler(self):
        from workers.scan_worker import SchedulerWorker
        if self._sched_worker and self._sched_worker.isRunning():
            return
        from PyQt6.QtCore import QSettings as _QS
        from ui.scan_settings import effective_flush_caches
        _qs = _QS("NetSentinel", "NetSentinel")
        self._sched_worker = SchedulerWorker(
            interval_minutes=self._sched_interval.value(),
            offenders_path=self._offenders_path,
            notify_desktop=_qs.value("tray/notify_new_device", False, type=bool),
            flush_caches=effective_flush_caches(),
        )
        self._sched_worker.status.connect(self._on_sched_status)
        self._sched_worker.alert.connect(lambda t, m: self._sched_log.append(f"🔔 {t}: {m}"), Qt.ConnectionType.QueuedConnection)
        self._sched_worker.error.connect(lambda e: self._sched_log.append(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._sched_worker.scan_result.connect(self._on_sched_scan_result, Qt.ConnectionType.QueuedConnection)
        self._sched_worker.start()
        self._save_monitor_state("scheduler", True)

    @pyqtSlot()
    def _stop_scheduler(self):
        if self._sched_worker:
            self._sched_worker.stop()
            self._sched_status.setText("Scheduler stopped.")
            self._save_monitor_state("scheduler", False)

    @pyqtSlot(str)
    def _on_sched_status(self, msg: str):
        self._sched_status.setText(msg)
        self._sched_log.append(msg)

    @pyqtSlot(object)
    def _on_sched_scan_result(self, result) -> None:
        # Feeds the same auto-baseline path as Full Device Discovery (ui/scan_wiring.py),
        # so "combine with Config Snapshots" (ui/help.py) is true for scheduled scans too.
        scan_data = getattr(result, "scan_data", None)
        if scan_data:
            self._m1_auto_snapshot_baseline(scan_data)

    # ── SNMP tab ──────────────────────────────────────────────────────────────

    def _build_snmp_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # ── Device poll section ───────────────────────────────────────────────
        self._snmp_status = QLabel("SNMP poller not running.")
        _s.themed_ss(self._snmp_status, "color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        ctrl_row = QHBoxLayout()
        self._snmp_community = QLineEdit()
        self._snmp_community.setFixedWidth(120)
        self._snmp_community.setPlaceholderText("community string")
        self._snmp_community.setEchoMode(QLineEdit.EchoMode.Password)  # RULE 22-D
        # RULE 22-A: load community string from OS keychain
        try:
            import keyring as _kr
            _stored = _kr.get_password("NetSentinel", "snmp/community")
            self._snmp_community.setText(_stored or "public")
        except Exception:
            self._snmp_community.setText("public")
        self._snmp_community.editingFinished.connect(self._save_snmp_community)
        btn_poll = QPushButton("▶  Poll All Devices")
        btn_poll.setObjectName("btnNetRefresh")
        btn_poll.clicked.connect(self._start_snmp_poll)
        ctrl_row.addWidget(QLabel("Community:"))
        ctrl_row.addWidget(self._snmp_community)
        ctrl_row.addWidget(btn_poll)
        ctrl_row.addStretch()
        self._snmp_table = _table(["Host", "Name", "Description", "Uptime", "Interfaces", "CPU Load", "Contact"])
        self._snmp_table.setColumnWidth(0, 120)
        self._snmp_table.setColumnWidth(2, 350)
        self._snmp_table.itemSelectionChanged.connect(self._on_snmp_table_selection)
        lay.addWidget(self._snmp_status)
        lay.addLayout(ctrl_row)
        lay.addWidget(self._snmp_table, 1)

        # ── Interface error metrics card ──────────────────────────────────────
        if_card = QWidget()
        _s.themed_ss(if_card, "QWidget{{background:{BG_CARD};border:1px solid {BORDER};}}")
        if_lay = QVBoxLayout(if_card)
        if_lay.setContentsMargins(8, 6, 8, 6)
        if_lay.setSpacing(4)

        title_row = QHBoxLayout()
        lbl_if = QLabel("◆ Interface Error & Discard Counters")
        _s.themed_ss(lbl_if, "font-weight:600;color:{TEXT_PRIMARY};font-size:12px;border:none;")
        self._snmp_if_status = QLabel("Select a device above and click Poll.")
        _s.themed_ss(self._snmp_if_status, "color:{TEXT_SECONDARY};font-size:11px;border:none;")
        self._snmp_if_host = QLineEdit()
        self._snmp_if_host.setFixedWidth(130)
        self._snmp_if_host.setPlaceholderText("host IP")
        btn_if = QPushButton("▶  Poll Interface Errors")
        btn_if.setObjectName("btnNetRefresh")
        btn_if.clicked.connect(self._start_snmp_if_poll)
        title_row.addWidget(lbl_if)
        title_row.addStretch()
        title_row.addWidget(self._snmp_if_status)
        title_row.addWidget(QLabel("Host:"))
        title_row.addWidget(self._snmp_if_host)
        title_row.addWidget(btn_if)
        if_lay.addLayout(title_row)

        content_split = QSplitter(Qt.Orientation.Horizontal)
        self._snmp_if_table = _table(
            ["Interface", "In Errors", "Out Errors", "In Discards", "Out Discards"]
        )
        self._snmp_if_table.setColumnWidth(0, 140)
        for _c in range(1, 5):
            self._snmp_if_table.setColumnWidth(_c, 90)
        content_split.addWidget(self._snmp_if_table)

        # Matplotlib error bar chart (RULE 10 — theme constants)
        self._snmp_if_fig    = None
        self._snmp_if_ax     = None
        self._snmp_if_canvas = None
        try:
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            self._snmp_if_fig = Figure(facecolor=_s.CHART_BG, figsize=(4, 2.5))
            self._snmp_if_fig.subplots_adjust(left=0.12, right=0.98, top=0.88, bottom=0.22)
            self._snmp_if_ax  = self._snmp_if_fig.add_subplot(111)
            self._snmp_if_ax.set_facecolor(_s.CHART_PLOT_BG)
            self._snmp_if_ax.tick_params(colors=_s.TEXT_SECONDARY, labelsize=8)
            self._snmp_if_ax.grid(True, color=_s.CHART_GRID, linewidth=0.8)
            for sp in ("top", "right"):
                self._snmp_if_ax.spines[sp].set_visible(False)
            for sp in ("bottom", "left"):
                self._snmp_if_ax.spines[sp].set_color(_s.CHART_SPINE)
            self._snmp_if_ax.set_title(
                "Error distribution per interface", fontsize=9,
                color=_s.TEXT_PRIMARY, pad=4,
            )
            self._snmp_if_canvas = FigureCanvasQTAgg(self._snmp_if_fig)
            _s.themed_ss(self._snmp_if_canvas, "background:{CHART_BG}; border:none;")
            content_split.addWidget(self._snmp_if_canvas)
        except Exception:
            pass  # matplotlib not available — chart omitted gracefully

        content_split.setStretchFactor(0, 3)
        content_split.setStretchFactor(1, 2)
        if_lay.addWidget(content_split, 1)
        lay.addWidget(if_card, 1)
        return w

    def refresh_snmp_if_theme(self) -> None:
        """Live theme switch: recolour the SNMP interface-errors bar chart.

        The chart lives on the Dashboard (this mixin), not on a stack page, so
        the dashboard's theme fan-out forwards here explicitly. When data has
        been plotted it re-invokes the (now theme-live) result handler with the
        cached entries; otherwise it just re-reads the empty-axes colours.
        """
        fig    = getattr(self, "_snmp_if_fig", None)
        ax     = getattr(self, "_snmp_if_ax", None)
        canvas = getattr(self, "_snmp_if_canvas", None)
        if fig is None or ax is None or canvas is None:
            return
        fig.set_facecolor(_s.CHART_BG)
        entries = getattr(self, "_snmp_if_last_entries", None)
        if entries:
            self._on_snmp_if_result(entries)   # full recolour with cached data
            return
        ax.set_facecolor(_s.CHART_PLOT_BG)
        ax.tick_params(colors=_s.TEXT_SECONDARY, labelsize=8)
        ax.grid(True, color=_s.CHART_GRID, linewidth=0.8)
        for sp in ("bottom", "left"):
            ax.spines[sp].set_color(_s.CHART_SPINE)
        ax.set_title(
            "Error distribution per interface", fontsize=9,
            color=_s.TEXT_PRIMARY, pad=4,
        )
        try:
            canvas.draw_idle()
        except Exception:
            pass  # non-fatal if canvas is detached

    @pyqtSlot()
    def _on_snmp_table_selection(self) -> None:
        """Auto-fill the interface-errors host field when a row is selected."""
        rows = self._snmp_table.selectedItems()
        if rows:
            host_item = self._snmp_table.item(rows[0].row(), 0)
            if host_item:
                self._snmp_if_host.setText(host_item.text())

    @pyqtSlot()
    def _start_snmp_poll(self):
        from workers.scan_worker import SNMPWorker
        if self._snmp_worker and self._snmp_worker.isRunning():
            return
        # Collect IPs from last M1 scan + gateway
        hosts: list = []
        if self._m1_result:
            for d in self._m1_result.get("devices", []):
                ip = getattr(d, "ip", None) if not isinstance(d, dict) else d.get("ip")
                if ip:
                    hosts.append(ip)
        gw = self._net_info.get("gateway") if self._net_info else None
        if gw and gw not in hosts:
            hosts.insert(0, gw)
        if not hosts:
            self._snmp_status.setText("No devices found — run a Device Fingerprint scan first.")
            return
        self._snmp_table.setRowCount(0)
        community = self._snmp_community.text().strip() or "public"
        self._snmp_worker = SNMPWorker(hosts=hosts, community=community)
        self._snmp_worker.host_result.connect(self._on_snmp_result)
        self._snmp_worker.status.connect(self._snmp_status.setText)
        self._snmp_worker.error.connect(
            lambda e: self._snmp_status.setText(f"⚠ {e}"),
            Qt.ConnectionType.QueuedConnection,
        )
        self._snmp_worker.start()

    @pyqtSlot()
    def _start_snmp_if_poll(self) -> None:
        from workers.scan_worker import SNMPIfErrorWorker
        if self._snmp_if_worker and self._snmp_if_worker.isRunning():
            return
        host = self._snmp_if_host.text().strip()
        if not host:
            self._snmp_if_status.setText("Enter a host IP first.")
            return
        community = self._snmp_community.text().strip() or "public"
        self._snmp_if_table.setRowCount(0)
        self._snmp_if_status.setText(f"Polling {host}…")
        self._snmp_if_worker = SNMPIfErrorWorker(host=host, community=community)
        self._snmp_if_worker.result_ready.connect(self._on_snmp_if_result)
        self._snmp_if_worker.status.connect(self._snmp_if_status.setText)
        self._snmp_if_worker.error.connect(
            lambda e: self._snmp_if_status.setText(f"⚠ {e}"),
            Qt.ConnectionType.QueuedConnection,
        )
        self._snmp_if_worker.start()

    @pyqtSlot()
    def _save_snmp_community(self) -> None:
        """Persist SNMP community string to OS keychain (RULE 22-A)."""
        value = self._snmp_community.text().strip()
        try:
            import keyring as _kr
            if value:
                _kr.set_password("NetSentinel", "snmp/community", value)
            else:
                try:
                    _kr.delete_password("NetSentinel", "snmp/community")
                except Exception:
                    pass  # non-fatal
        except Exception:
            pass  # non-fatal
