"""
tabs_scan.py — _ScanTabsMixin: scan result tab content builders (M1–M5).

Extracted from ui/tabs.py (Sprint 8). Contains the five main scan-result
tab builders plus their event handlers and filter helpers.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSettings, pyqtSlot
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.live_graph import LiveGraphWidget
from ui.npcap_banner import NpcapMissingBanner
from ui.styles import (
    ACCENT, ACCENT_DARK, BG_CARD, BG_DARK,
    BG_HOVER, BORDER, CHART_PURPLE,
    GREEN, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    WHITE,
)
from ui.tabs_helpers import _make_card, _page_header, _table


class _ScanTabsMixin:
    """Mixin providing scan result tab builders (M1–M5) for Dashboard/TabBuilderMixin.

    Extracted from ui/tabs.py (Sprint 8).
    """

    def _build_m1_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # ── KPI summary tiles ─────────────────────────────────────────────────
        lay.addWidget(self._build_kpi_bar())

        self._m1_status = QLabel("Not yet scanned.")
        self._m1_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:2px 0;")

        self._m1_group_btn = QPushButton("▼▼  Collapse All")
        self._m1_group_btn.setFixedHeight(22)
        self._m1_group_btn.setStyleSheet(
            f"QPushButton{{background:{BG_DARK};color:{TEXT_MUTED};border:1px solid {BORDER};"
            f"border-radius:3px;padding:0 8px;font-size:10px;}}"
            f"QPushButton:hover{{background:{BG_HOVER};color:{TEXT_PRIMARY};}}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        self._m1_group_btn.setVisible(False)
        self._m1_group_btn.clicked.connect(self._m1_toggle_all_groups)

        _node_grp_on = QSettings("NetSentinel", "NetSentinel").value(
            "devices/group_by_node", False, type=bool
        )
        self._m1_group_by_node: bool = _node_grp_on

        # Segmented view control — always enabled, no plugin gate
        self._m1_seg_active_ss = (
            f"QPushButton{{background:{ACCENT_DARK};color:{WHITE};border:none;"
            f"border-radius:3px;padding:0 10px;font-size:10px;}}"
            f"QPushButton:hover{{background:{ACCENT};}}"
        )
        self._m1_seg_inactive_ss = (
            f"QPushButton{{background:transparent;color:{TEXT_MUTED};border:none;"
            f"border-radius:3px;padding:0 10px;font-size:10px;}}"
            f"QPushButton:hover{{background:{BG_HOVER};color:{TEXT_PRIMARY};}}"
        )
        _seg_frame = QFrame()
        _seg_frame.setFixedHeight(24)
        _seg_frame.setStyleSheet(
            f"QFrame{{background:{BG_DARK};border:1px solid {BORDER};border-radius:4px;}}"
        )
        _seg_lay = QHBoxLayout(_seg_frame)
        _seg_lay.setContentsMargins(1, 1, 1, 1)
        _seg_lay.setSpacing(0)

        self._m1_seg_list = QPushButton("≡  List")
        self._m1_seg_list.setFixedHeight(22)
        self._m1_seg_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self._m1_seg_list.setToolTip("Flat device list")
        self._m1_seg_list.setStyleSheet(
            self._m1_seg_inactive_ss if _node_grp_on else self._m1_seg_active_ss
        )
        self._m1_seg_node = QPushButton("⊞  By Node")
        self._m1_seg_node.setFixedHeight(22)
        self._m1_seg_node.setCursor(Qt.CursorShape.PointingHandCursor)
        self._m1_seg_node.setToolTip("Group devices by mesh node / AP")
        self._m1_seg_node.setStyleSheet(
            self._m1_seg_active_ss if _node_grp_on else self._m1_seg_inactive_ss
        )
        _seg_lay.addWidget(self._m1_seg_list)
        _seg_lay.addWidget(self._m1_seg_node)

        self._m1_seg_list.clicked.connect(lambda: self._on_node_group_toggled(False))
        self._m1_seg_node.clicked.connect(lambda: self._on_node_group_toggled(True))

        _status_row = QHBoxLayout()
        _status_row.setContentsMargins(0, 0, 0, 0)
        _status_row.addWidget(self._m1_status, 1)
        _status_row.addWidget(_seg_frame)
        _status_row.addSpacing(4)
        _status_row.addWidget(self._m1_group_btn)

        # Integration discovery banner — hidden until scan finds a device matching
        # a bundled plugin's default gateway IP
        self._m1_int_banner = QFrame()
        self._m1_int_banner.setVisible(False)
        _ib_lay = QHBoxLayout(self._m1_int_banner)
        _ib_lay.setContentsMargins(10, 5, 10, 5)
        _ib_lay.setSpacing(8)
        self._m1_int_banner.setStyleSheet(
            f"QFrame {{ background:{ACCENT}18; border:1px solid {ACCENT}55;"
            " border-radius:4px; }"
        )
        self._m1_int_lbl = QLabel()
        self._m1_int_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:11px; background:transparent; border:none;"
        )
        _ib_lay.addWidget(self._m1_int_lbl, 1)
        _int_cfg_btn = QPushButton("Configure  →")
        _int_cfg_btn.setFixedHeight(22)
        _int_cfg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _int_cfg_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            " border-radius:3px; font-size:10px; padding:0 10px; }"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        _int_cfg_btn.clicked.connect(
            lambda: self._nav_rail_go_to("Hardware")
        )
        _ib_lay.addWidget(_int_cfg_btn)

        self._m1_node_hint = QLabel()   # hidden stub — hint lives in By Node group header
        self._m1_node_hint.setVisible(False)

        self._m1_table = _table([
            "IP Address", "Hostname", "MAC Address", "Vendor", "Risk", "Device Type",
            "Node", "Band", "Verdict",
        ])
        self._m1_table.setColumnWidth(0, 120)
        self._m1_table.setColumnWidth(1, 160)
        self._m1_table.setColumnWidth(2, 145)
        self._m1_table.setColumnWidth(3, 180)
        self._m1_table.setColumnWidth(4, 70)
        self._m1_table.setColumnWidth(5, 130)
        self._m1_table.setColumnWidth(6, 155)
        self._m1_table.setColumnWidth(7, 55)
        # Node (6) and Band (7) are hidden until a Deco scan populates them
        self._m1_table.setColumnHidden(6, True)
        self._m1_table.setColumnHidden(7, True)
        self._m1_table.setStyleSheet(
            f"QTableWidget::item:hover {{ background-color: {BG_HOVER}; }}"
        )

        # Column sorting (click header to sort ascending/descending)
        self._m1_table.setSortingEnabled(True)
        self._m1_table.horizontalHeader().setSortIndicatorShown(True)
        self._m1_table.horizontalHeader().sortIndicatorChanged.connect(
            self._m1_sort_changed
        )

        # Right-click context menu
        self._m1_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._m1_table.customContextMenuRequested.connect(self._m1_context_menu)

        # Double-click → pre-fill Port Scan (TCP) and navigate there
        self._m1_table.doubleClicked.connect(self._m1_row_double_clicked)

        # Empty-state placeholder shown when table has no rows
        self._m1_empty = QLabel("Run a scan to discover devices on this network.")
        self._m1_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._m1_empty.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:13px; padding:40px;"
            "background:transparent; border:none;"
        )

        # ── Card wrapping table + empty state ─────────────────────────────────
        m1_card, m1_body = _make_card("Discovered Devices")

        # Search bar + filter chips (FILTER-1)
        _frow_w = QWidget()
        _frow_w.setStyleSheet("background:transparent;")
        _frow = QHBoxLayout(_frow_w)
        _frow.setContentsMargins(8, 5, 8, 4)
        _frow.setSpacing(6)

        self._m1_search = QLineEdit()
        self._m1_search.setPlaceholderText("Search IP, hostname, MAC, vendor…")
        self._m1_search.setFixedHeight(26)
        self._m1_search.setClearButtonEnabled(True)
        self._m1_search.setStyleSheet(
            f"QLineEdit {{ background:{BG_DARK}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:0 6px; font-size:11px; }}"
            f"QLineEdit:focus {{ border-color:{ACCENT}; }}"
        )
        self._m1_search.textChanged.connect(self._m1_apply_filter)
        _frow.addWidget(self._m1_search, 1)

        self._m1_chip_active_ss = (
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:3px; padding:0 8px; font-size:10px; }}"
        )
        self._m1_chip_inactive_ss = (
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:0 8px; font-size:10px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; border-color:{TEXT_MUTED}; }}"
        )
        self._m1_chip = "all"
        self._m1_chip_btns: dict = {}
        for _ckey, _clabel in (
            ("all", "All"), ("online", "Online"),
            ("offline", "Offline"), ("unknown", "Unknown vendor"),
        ):
            _cbtn = QPushButton(_clabel)
            _cbtn.setFixedHeight(22)
            _cbtn.setCursor(Qt.CursorShape.PointingHandCursor)
            _cbtn.setStyleSheet(
                self._m1_chip_active_ss if _ckey == "all" else self._m1_chip_inactive_ss
            )
            _cbtn.clicked.connect(lambda _=False, k=_ckey: self._m1_set_chip(k))
            self._m1_chip_btns[_ckey] = _cbtn
            _frow.addWidget(_cbtn)

        from ui.widgets.density_toggle import DensityToggle
        _frow.addSpacing(4)
        _frow.addWidget(DensityToggle("m1_devices", self._m1_table))

        m1_body.addWidget(_frow_w)

        # Stack: table on top, empty label behind — we toggle visibility
        from PyQt6.QtWidgets import QStackedWidget as _SW
        self._m1_stack = _SW()
        self._m1_stack.addWidget(self._m1_empty)   # index 0 — empty state
        self._m1_stack.addWidget(self._m1_table)   # index 1 — live data
        self._m1_stack.setCurrentIndex(0)
        m1_body.addWidget(self._m1_stack)

        lay.addLayout(_status_row)
        lay.addWidget(self._m1_int_banner)
        lay.addWidget(m1_card, 1)

        from ui.widgets.explainer_panel import ExplainerPanel
        self._m1_explainer = ExplainerPanel("rogue_device")
        self._m1_explainer.navigate_to.connect(self._nav_rail_go_to)
        lay.addWidget(self._m1_explainer)
        return w

    @pyqtSlot('QModelIndex')
    def _m1_row_double_clicked(self, index) -> None:
        """Double-click a device row → pre-fill SYN scanner IP and navigate."""
        ip_item = self._m1_table.item(index.row(), 0)
        if ip_item:
            ip = ip_item.text().strip()
            if ip and hasattr(self, "_syn_host"):
                self._syn_host.setText(ip)
                self._nav_rail_go_to("Port Scan (TCP)")

    def _m1_set_chip(self, key: str) -> None:
        self._m1_chip = key
        for k, btn in self._m1_chip_btns.items():
            btn.setStyleSheet(
                self._m1_chip_active_ss if k == key else self._m1_chip_inactive_ss
            )
        self._m1_apply_filter()

    def _m1_apply_filter(self) -> None:
        text = self._m1_search.text().lower().strip()
        chip = self._m1_chip
        for row in range(self._m1_table.rowCount()):
            text_match = not text or any(
                text in (self._m1_table.item(row, col) or QTableWidgetItem()).text().lower()
                for col in (0, 1, 2, 3)
            )
            risk_item = self._m1_table.item(row, 4)
            risk = (risk_item.text() if risk_item else "").upper()
            vendor_item = self._m1_table.item(row, 3)
            vendor = (vendor_item.text() if vendor_item else "").lower().strip()
            if chip == "all":
                chip_match = True
            elif chip == "online":
                chip_match = risk != "UNKNOWN"
            elif chip == "offline":
                chip_match = risk == "UNKNOWN"
            else:
                chip_match = vendor in ("unknown", "—", "")
            self._m1_table.setRowHidden(row, not (text_match and chip_match))

    def _m1_sort_changed(self, col: int, order) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("home/m1_sort_col", col)
        qs.setValue("home/m1_sort_order", order.value)

    def _m1_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        row = self._m1_table.rowAtIndex(pos) if hasattr(self._m1_table, 'rowAtIndex') \
              else self._m1_table.rowAt(pos.y())
        if row < 0:
            return
        first = self._m1_table.item(row, 0)
        if first and first.data(Qt.ItemDataRole.UserRole) == "__sat_header__":
            return
        ip  = (first or QTableWidgetItem()).text()
        mac = (self._m1_table.item(row, 2) or QTableWidgetItem()).text()
        menu = QMenu(self)
        menu.setStyleSheet(f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};")
        act_scan     = menu.addAction(f"🔍  Port Scan  {ip}")
        act_geo      = menu.addAction(f"🗺  Show on Geolocation Map →")
        act_abuseipdb = menu.addAction(f"🛡  Check IP (AbuseIPDB) →")
        act_wol      = menu.addAction(f"⚡  Wake-on-LAN  →  {mac}")
        # Show CVE Tracker link only when this IP has tracked CVE entries
        _has_cves = False
        try:
            if self._store:
                _has_cves = any(c.get("host") == ip for c in self._store.list_cve_lifecycles())
        except Exception:
            pass  # non-fatal
        act_cve = menu.addAction(f"🔎  View in CVE Tracker →") if _has_cves else None
        menu.addSeparator()
        act_fix      = menu.addAction("🔧  How to Fix")
        menu.addSeparator()
        act_copy_ip  = menu.addAction("📋  Copy IP")
        act_copy_mac = menu.addAction("📋  Copy MAC")
        act_copy_row = menu.addAction("📋  Copy full row")
        chosen = menu.exec(self._m1_table.viewport().mapToGlobal(pos))
        if chosen == act_scan:
            self._run_port_scan(ip)
        elif chosen == act_geo:
            self._show_ip_on_geo_map(ip)
        elif chosen == act_abuseipdb:
            self._threat_intel_page.check_ip(ip)
            self._nav_rail_go_to("Threat Intel")
        elif act_cve and chosen == act_cve:
            self._nav_rail_go_to("CVE Tracker")
        elif chosen == act_wol:
            self._send_wol(mac)
        elif chosen == act_fix:
            rem = ""
            if self._m1_result:
                for d in self._m1_result.get("devices", []):
                    d_ip = d.get("ip", "") if isinstance(d, dict) else getattr(d, "ip", "")
                    if d_ip == ip:
                        rem = d.get("remediation", "") if isinstance(d, dict) else getattr(d, "remediation", "")
                        break
            self._show_how_to_fix(ip, rem or "No specific remediation available for this device.")
        elif chosen == act_copy_ip:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(ip)
        elif chosen == act_copy_mac:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(mac)
        elif chosen == act_copy_row:
            from PyQt6.QtWidgets import QApplication
            parts = []
            for col in range(self._m1_table.columnCount()):
                item = self._m1_table.item(row, col)
                parts.append(item.text() if item else "")
            QApplication.clipboard().setText("\t".join(parts))

    # ── Module 2 ──────────────────────────────────────────────────────────────

    def _build_m2_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QStackedWidget

        # ── Page 0: empty state ───────────────────────────────────────────────
        empty = QWidget()
        evl = QVBoxLayout(empty)
        evl.addWidget(NpcapMissingBanner(parent=empty))
        evl.addStretch()
        em_desc = QLabel(
            "STP/BPDU frame capture identifies unauthorised Spanning Tree root bridges\n"
            "that cause intermittent network drops and DNS failures."
        )
        em_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        em_desc.setWordWrap(True)
        em_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        em_btn = QPushButton("Start STP Capture")
        em_btn.setObjectName("btnScan")
        em_btn.setFixedWidth(200)
        em_btn.clicked.connect(self._start_full_scan)
        evl.addWidget(em_desc, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addSpacing(12)
        evl.addWidget(em_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addStretch()

        # ── Page 1: content ───────────────────────────────────────────────────
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(_page_header(
            "Rogue Bridge Detection",
            "Identifies devices claiming to be network switches via Spanning Tree Protocol"
            " — a sign of misconfiguration or an unauthorized device."
        ))
        self._m2_status = QLabel("Not yet scanned.")
        self._m2_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:2px 0;")
        lay.addWidget(self._m2_status)
        card, card_body = _make_card("STP Frames Detected")
        self._m2_table = _table([
            "Source MAC", "BPDU Type", "Root MAC", "Bridge Priority",
            "Hello (s)", "MaxAge (s)", "FwdDelay (s)", "Rogue?"
        ])
        self._m2_table.setColumnWidth(0, 150)
        self._m2_table.setColumnWidth(1, 80)
        self._m2_table.setColumnWidth(2, 150)
        self._m2_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._m2_table.customContextMenuRequested.connect(self._m2_context_menu)
        card_body.addWidget(self._m2_table)
        lay.addWidget(card, 1)
        from ui.widgets.explainer_panel import ExplainerPanel
        self._m2_explainer = ExplainerPanel("stp_rogue")
        self._m2_explainer.navigate_to.connect(self._nav_rail_go_to)
        lay.addWidget(self._m2_explainer)

        self._m2_stack = QStackedWidget()
        self._m2_stack.addWidget(empty)
        self._m2_stack.addWidget(content)
        return self._m2_stack

    def _m2_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        row = self._m2_table.rowAt(pos.y())
        if row < 0:
            return
        src_mac = (self._m2_table.item(row, 0) or QTableWidgetItem()).text()
        is_rogue = (self._m2_table.item(row, 7) or QTableWidgetItem()).text().strip().upper() in ("YES", "TRUE", "ROGUE")
        menu = QMenu(self)
        menu.setStyleSheet(f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};")
        act_fix  = menu.addAction("🔧  How to Fix")
        menu.addSeparator()
        act_copy = menu.addAction("📋  Copy MAC")
        chosen = menu.exec(self._m2_table.viewport().mapToGlobal(pos))
        if chosen == act_fix:
            if is_rogue:
                rem = (
                    f"A rogue STP Root Bridge was detected from {src_mac}. "
                    "Disconnect the Ethernet cable from this device immediately. "
                    "If it is a mesh satellite (e.g. Google Nest, TP-Link Deco), it must use "
                    "Wi-Fi backhaul only — do not connect it via Ethernet. "
                    "After disconnecting, wait 60 seconds for the real router to reclaim the Root Bridge role, "
                    "then re-run this scan to confirm the network is stable."
                )
            else:
                rem = (
                    f"Device {src_mac} is sending STP BPDUs but is not currently rated as rogue. "
                    "This is expected for your main router or managed switch. "
                    "If you see repeated outages, verify this MAC belongs to your router."
                )
            self._show_how_to_fix(src_mac, rem)
        elif chosen == act_copy:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(src_mac)

    # ── Module 3 ──────────────────────────────────────────────────────────────

    def _build_m3_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QStackedWidget

        # ── Page 0: empty state ───────────────────────────────────────────────
        empty = QWidget()
        evl = QVBoxLayout(empty)
        evl.addWidget(NpcapMissingBanner(parent=empty))
        evl.addStretch()
        em_desc = QLabel(
            "Live packet capture measures broadcast and multicast rates\n"
            "and identifies the device causing a broadcast storm."
        )
        em_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        em_desc.setWordWrap(True)
        em_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        em_btn = QPushButton("Start Broadcast Capture")
        em_btn.setObjectName("btnScan")
        em_btn.setFixedWidth(220)
        em_btn.clicked.connect(self._start_full_scan)
        evl.addWidget(em_desc, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addSpacing(12)
        evl.addWidget(em_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addStretch()

        # ── Page 1: content ───────────────────────────────────────────────────
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(_page_header(
            "Broadcast Storm Analysis",
            "Detects packet floods that can slow or crash your network"
            " — usually a faulty switch or routing loop."
        ))
        self._m3_status = QLabel("Not yet scanned.")
        self._m3_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:2px 0;")
        lay.addWidget(self._m3_status)
        stats = QHBoxLayout()
        self._m3_bcast_lbl = self._stat_label("Broadcast/s", "—")
        self._m3_mcast_lbl = self._stat_label("Multicast/s", "—")
        self._m3_ratio_lbl = self._stat_label("Bcast ratio", "—")
        self._m3_level_lbl = self._stat_label("Storm level", "—")
        for w2 in (self._m3_bcast_lbl, self._m3_mcast_lbl,
                   self._m3_ratio_lbl, self._m3_level_lbl):
            stats.addWidget(w2)
        stats.addStretch()
        lay.addLayout(stats)
        card, card_body = _make_card("Broadcast Sources")
        self._m3_table = _table(["Source MAC", "Broadcast Packets", "Rogue Match?"])
        self._m3_table.setColumnWidth(0, 160)
        self._m3_table.setColumnWidth(1, 160)
        self._m3_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._m3_table.customContextMenuRequested.connect(self._m3_context_menu)
        card_body.addWidget(self._m3_table)
        lay.addWidget(card, 1)
        from ui.widgets.explainer_panel import ExplainerPanel
        self._m3_explainer = ExplainerPanel("broadcast_storm")
        self._m3_explainer.navigate_to.connect(self._nav_rail_go_to)
        lay.addWidget(self._m3_explainer)

        self._m3_stack = QStackedWidget()
        self._m3_stack.addWidget(empty)
        self._m3_stack.addWidget(content)
        return self._m3_stack

    def _m3_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        row = self._m3_table.rowAt(pos.y())
        if row < 0:
            return
        src_mac = (self._m3_table.item(row, 0) or QTableWidgetItem()).text()
        bcast   = (self._m3_table.item(row, 1) or QTableWidgetItem()).text()
        menu = QMenu(self)
        menu.setStyleSheet(f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};")
        act_fix  = menu.addAction("🔧  How to Fix")
        act_copy = menu.addAction("📋  Copy MAC")
        chosen = menu.exec(self._m3_table.viewport().mapToGlobal(pos))
        if chosen == act_fix:
            rem = (
                f"Device {src_mac} sent {bcast} broadcast packets. "
                "To resolve a broadcast storm: "
                "1. Identify the physical device using the MAC address "
                "(check your router's DHCP table). "
                "2. Restart or reboot that device. "
                "3. Check for firmware updates — faulty firmware is a common cause. "
                "4. If the storm continues, disconnect the device from the network "
                "and move it to a separate VLAN or guest network. "
                "5. High broadcast rates from IoT devices (cameras, smart plugs) often indicate "
                "a failing device that needs replacement."
            )
            self._show_how_to_fix(src_mac, rem)
        elif chosen == act_copy:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(src_mac)

    # ── Module 4 ──────────────────────────────────────────────────────────────

    def _build_m4_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QStackedWidget

        # ── Page 0: empty state ───────────────────────────────────────────────
        empty = QWidget()
        evl = QVBoxLayout(empty)
        evl.addStretch()
        em_desc = QLabel(
            "No WiFi scan has been run yet.\n"
            "NetSentinel will enumerate nearby networks, detect rogue SSIDs,\n"
            "and flag co-channel interference."
        )
        em_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        em_desc.setWordWrap(True)
        em_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        em_btn = QPushButton("Scan for WiFi Networks")
        em_btn.setObjectName("btnScan")
        em_btn.setFixedWidth(220)
        em_btn.clicked.connect(self._start_full_scan)
        evl.addWidget(em_desc, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addSpacing(12)
        evl.addWidget(em_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addStretch()

        # ── Page 1: content ───────────────────────────────────────────────────
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(_page_header(
            "WiFi Networks",
            "Wireless scan — SSID enumeration, rogue AP detection, co-channel interference"
        ))
        self._m4_status = QLabel("Not yet scanned.")
        self._m4_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:2px 0;")
        lay.addWidget(self._m4_status)

        # Deco band-usage KPI chips — hidden until mesh data arrives
        self._m4_deco_bar = self._build_m4_deco_bar()
        self._m4_deco_bar.setVisible(False)
        lay.addWidget(self._m4_deco_bar)

        card, card_body = _make_card("Detected Networks")
        self._m4_table = _table([
            "SSID", "BSSID", "Nodes", "Channel", "Band", "Signal (dBm)",
            "Rogue SSID?", "Co-Channel?", "Connected?",
        ])
        self._m4_table.setColumnWidth(0, 180)
        self._m4_table.setColumnWidth(1, 150)
        self._m4_table.setColumnWidth(2, 55)   # Nodes
        self._m4_table.setColumnWidth(5, 105)  # Signal range
        self._m4_table.setColumnWidth(8, 95)   # Connected
        card_body.addWidget(self._m4_table)
        lay.addWidget(card, 1)

        self._m4_stack = QStackedWidget()
        self._m4_stack.addWidget(empty)
        self._m4_stack.addWidget(content)
        return self._m4_stack

    def _build_m4_deco_bar(self) -> QWidget:
        """KPI chips showing Deco band usage — revealed when mesh data is present."""
        bar = QWidget()
        bar.setFixedHeight(62)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 2, 0, 4)
        row.setSpacing(8)

        def _chip(dot_color: str, label: str):
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
            dot.setStyleSheet(f"color:{dot_color};font-size:9px;background:transparent;border:none;")
            lbl = QLabel(label.upper())
            lbl.setStyleSheet(
                f"color:{TEXT_MUTED};font-size:9px;font-weight:bold;"
                "letter-spacing:0.5px;background:transparent;border:none;"
            )
            hdr.addWidget(dot); hdr.addWidget(lbl); hdr.addStretch()
            vl.addLayout(hdr)
            val = QLabel("—")
            val.setStyleSheet(f"color:{TEXT_MUTED};font-size:18px;font-weight:bold;"
                              "background:transparent;border:none;")
            vl.addWidget(val)
            return tile, val

        header = QLabel("Deco band usage")
        header.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;padding:0;background:transparent;")
        row.addWidget(header)

        t1, self._m4_chip_24   = _chip(GREEN,        "2.4 GHz clients")
        t2, self._m4_chip_5    = _chip(ACCENT,        "5 GHz clients")
        t3, self._m4_chip_6    = _chip(CHART_PURPLE,  "6 GHz clients")
        t4, self._m4_chip_wired = _chip(TEXT_SECONDARY, "Wired clients")
        for t in (t1, t2, t3, t4):
            row.addWidget(t, 1)
        row.addStretch()
        return bar

    def _update_m4_deco_chips(self) -> None:
        """Refresh Deco band-usage chips from current mesh enrichment data."""
        if not getattr(self, "_mesh_enrichment", None):
            return
        counts: dict = {"2.4G": 0, "5G": 0, "6G": 0, "Wired": 0}
        for mc in self._mesh_enrichment.values():
            band = getattr(mc, "band", "")
            if band in counts:
                counts[band] += 1
        self._m4_chip_24.setText(str(counts["2.4G"]))
        self._m4_chip_5.setText(str(counts["5G"]))
        self._m4_chip_6.setText(str(counts["6G"]))
        self._m4_chip_wired.setText(str(counts["Wired"]))
        self._m4_deco_bar.setVisible(True)

    # ── Module 5 ──────────────────────────────────────────────────────────────

    def _build_m5_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QStackedWidget

        # ── Page 0: empty state ───────────────────────────────────────────────
        empty = QWidget()
        evl = QVBoxLayout(empty)
        evl.addStretch()
        em_desc = QLabel(
            "Continuous RTT and DNS monitoring hasn't started yet.\n"
            "Run a scan to begin measuring latency and detecting outages."
        )
        em_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        em_desc.setWordWrap(True)
        em_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        em_btn = QPushButton("Start Monitoring")
        em_btn.setObjectName("btnScan")
        em_btn.setFixedWidth(180)
        em_btn.clicked.connect(self._start_full_scan)
        evl.addWidget(em_desc, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addSpacing(12)
        evl.addWidget(em_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addStretch()

        # ── Page 1: content ───────────────────────────────────────────────────
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(_page_header(
            "DNS & Outage Monitor",
            "Continuous RTT/DNS monitoring — latency graph, outage detection, STP correlation"
        ))
        self._m5_status = QLabel("Not yet scanned.")
        self._m5_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:2px 0;")
        lay.addWidget(self._m5_status)
        self._graph = LiveGraphWidget()
        self._graph.setMinimumHeight(80)
        lay.addWidget(self._graph, 2)
        card, card_body = _make_card("Detected Outages")
        self._m5_outage_table = _table([
            "Target", "Duration (s)", "Consecutive Drops", "STP Signature?", "Severity"
        ])
        card_body.addWidget(self._m5_outage_table)
        lay.addWidget(card, 1)
        from ui.widgets.explainer_panel import ExplainerPanel
        self._m5_explainer = ExplainerPanel("dns_stability")
        self._m5_explainer.navigate_to.connect(self._nav_rail_go_to)
        lay.addWidget(self._m5_explainer)

        self._m5_stack = QStackedWidget()
        self._m5_stack.addWidget(empty)
        self._m5_stack.addWidget(content)
        return self._m5_stack
