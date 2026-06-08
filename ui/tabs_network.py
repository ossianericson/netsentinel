"""
tabs_network.py — _NetworkTabsMixin: network configuration tab builder.

Extracted from ui/tabs.py (Sprint 8). Contains the network info tab builder,
its data-update method, and the network-devices context menu.
"""
from __future__ import annotations

import webbrowser

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    BG_CARD, BORDER, CARD_RADIUS,
    GREEN, RED,
    TEXT_PRIMARY, TEXT_SECONDARY,
)
from ui.tabs_helpers import _table


class _NetworkTabsMixin:
    """Mixin providing the Network Configuration tab builder for Dashboard/TabBuilderMixin.

    Extracted from ui/tabs.py (Sprint 8).
    """

    def _net_devices_context_menu(self, pos) -> None:
        """Context menu for the Network Info tab's device table."""
        from PyQt6.QtWidgets import QMenu
        row = self._net_devices_table.rowAt(pos.y())
        if row < 0:
            return
        ip  = (self._net_devices_table.item(row, 0) or QTableWidgetItem()).text()
        mac = (self._net_devices_table.item(row, 2) or QTableWidgetItem()).text()
        if not ip:
            return
        menu = QMenu(self)
        menu.setStyleSheet(f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};")
        act_scan  = menu.addAction(f"🔍  Port Scan  {ip}")
        act_geo   = menu.addAction(f"🗺  Show on Geo Map →")
        act_abuse = menu.addAction(f"🛡  Check IP (AbuseIPDB) →")
        menu.addSeparator()
        act_copy_ip  = menu.addAction("📋  Copy IP")
        act_copy_mac = menu.addAction("📋  Copy MAC")
        chosen = menu.exec(self._net_devices_table.viewport().mapToGlobal(pos))
        if chosen == act_scan:
            self._run_port_scan(ip)
        elif chosen == act_geo:
            self._show_ip_on_geo_map(ip)
        elif chosen == act_abuse:
            self._threat_intel_page.check_ip(ip)
            self._nav_rail_go_to("Threat Intelligence")
        elif chosen == act_copy_ip:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(ip)
        elif chosen == act_copy_mac:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(mac)

    def _build_network_info_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        # Header row
        hdr = QHBoxLayout()
        hdr_lbl = QLabel("🌐  Network Configuration")
        hdr_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        hdr_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        hdr.addWidget(hdr_lbl)
        hdr.addStretch()
        self._btn_net_refresh = QPushButton("↺  Refresh")
        self._btn_net_refresh.setObjectName("btnNetRefresh")
        self._btn_net_refresh.clicked.connect(self._refresh_network_info)
        hdr.addWidget(self._btn_net_refresh)
        lay.addLayout(hdr)

        # Info card
        self._net_info_card = QFrame()
        self._net_info_card.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
        )
        self._net_card_layout = QVBoxLayout(self._net_info_card)
        self._net_card_layout.setContentsMargins(18, 14, 18, 14)
        self._net_card_layout.setSpacing(8)

        self._net_info_label = QLabel("Loading network information…")
        self._net_info_label.setWordWrap(True)
        self._net_info_label.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        self._net_card_layout.addWidget(self._net_info_label)

        lay.addWidget(self._net_info_card)

        # Router links card
        router_frame = QFrame()
        router_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
        )
        rl = QVBoxLayout(router_frame)
        rl.setContentsMargins(18, 14, 18, 14)
        rl.setSpacing(6)
        rl_title = QLabel("🔗  Router / Modem Admin Panel")
        rl_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        rl_title.setStyleSheet(f"color:{TEXT_PRIMARY};")
        rl.addWidget(rl_title)
        rl_desc = QLabel(
            "Click a link below to open your router's admin page in a browser.\n"
            "Most home routers use http://192.168.x.1 — Huawei 5G modems also "
            "have /html/index.html"
        )
        rl_desc.setWordWrap(True)
        rl_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        rl.addWidget(rl_desc)

        self._router_links_layout = QHBoxLayout()
        self._router_links_layout.setSpacing(10)
        rl.addLayout(self._router_links_layout)
        lay.addWidget(router_frame)

        # ── OS network settings shortcuts ─────────────────────────────────────
        os_frame = QFrame()
        os_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
        )
        os_l = QVBoxLayout(os_frame)
        os_l.setContentsMargins(18, 12, 18, 12)
        os_l.setSpacing(6)
        os_title = QLabel("⚙️  Network Settings Shortcuts")
        os_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        os_title.setStyleSheet(f"color:{TEXT_PRIMARY};")
        os_l.addWidget(os_title)
        os_btn_row = QHBoxLayout()
        os_btn_row.setSpacing(8)
        self._os_setting_btns: list = []
        import platform as _plat
        _sys = _plat.system()
        if _sys == "Windows":
            _shortcuts = [
                ("📶  Wi-Fi Settings",       "ms-settings:network-wifi"),
                ("🔌  Ethernet Settings",    "ms-settings:network-ethernet"),
                ("🌐  Network Status",       "ms-settings:network-status"),
                ("🔒  VPN Settings",         "ms-settings:network-vpn"),
                ("🛡  Firewall & Security",  "ms-settings:windowsdefender"),
            ]
        elif _sys == "Darwin":
            _shortcuts = [
                ("📶  Network Preferences",  "x-apple.systempreferences:com.apple.preference.network"),
                ("📋  Wireless Diagnostics", "open://"),  # fallback — handled below
            ]
        else:
            _shortcuts = []
        for label, uri in _shortcuts:
            btn = QPushButton(label)
            btn.setObjectName("btnNetRefresh")
            btn.setFixedHeight(30)
            btn.setToolTip(f"Open {uri}")
            if uri.startswith("ms-settings:"):
                btn.clicked.connect(lambda _c=False, u=uri: __import__('os').startfile(u))
            elif uri.startswith("x-apple"):
                btn.clicked.connect(
                    lambda _c=False, u=uri: __import__('subprocess').run(
                        ["open", u], capture_output=True
                    )
                )
            os_btn_row.addWidget(btn)
        os_btn_row.addStretch()
        os_l.addLayout(os_btn_row)
        lay.addWidget(os_frame)

        # ── DHCP lease card ───────────────────────────────────────────────────
        dhcp_frame = QFrame()
        dhcp_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
        )
        dhcp_l = QVBoxLayout(dhcp_frame)
        dhcp_l.setContentsMargins(18, 12, 18, 12)
        dhcp_l.setSpacing(4)
        dhcp_title = QLabel("🕐  DHCP Lease  &  Adapter Details")
        dhcp_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        dhcp_title.setStyleSheet(f"color:{TEXT_PRIMARY};")
        dhcp_l.addWidget(dhcp_title)
        self._dhcp_label = QLabel("Loading…")
        self._dhcp_label.setWordWrap(True)
        self._dhcp_label.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        dhcp_l.addWidget(self._dhcp_label)
        lay.addWidget(dhcp_frame)

        # ── Adapters table ────────────────────────────────────────────────────
        adp_lbl = QLabel("  Network Adapters")
        adp_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; padding-top:4px;")
        lay.addWidget(adp_lbl)
        self._adapters_table = _table([
            "Adapter Name", "Type", "IPv4", "MAC Address", "Speed", "WiFi Signal", "SSID", "Status"
        ])
        self._adapters_table.setColumnWidth(0, 180)
        self._adapters_table.setColumnWidth(1, 70)
        self._adapters_table.setColumnWidth(2, 115)
        self._adapters_table.setColumnWidth(3, 140)
        self._adapters_table.setColumnWidth(4, 80)
        self._adapters_table.setColumnWidth(5, 90)
        self._adapters_table.setColumnWidth(6, 140)
        self._adapters_table.setMaximumHeight(130)
        lay.addWidget(self._adapters_table)

        # ── All-devices table (populated after scan) ──────────────────────────
        dev_lbl = QLabel("  All Devices Seen on This Network  (populated after scan)")
        dev_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; padding-top:4px;")
        lay.addWidget(dev_lbl)

        self._net_devices_table = _table([
            "IP Address", "Hostname", "MAC Address", "Vendor", "Risk"
        ])
        self._net_devices_table.setColumnWidth(0, 120)
        self._net_devices_table.setColumnWidth(1, 180)
        self._net_devices_table.setColumnWidth(2, 145)
        self._net_devices_table.setColumnWidth(3, 200)
        self._net_devices_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._net_devices_table.customContextMenuRequested.connect(self._net_devices_context_menu)
        lay.addWidget(self._net_devices_table, 1)
        return w

    def _update_net_info_ui(self, info: dict):
        """Populate the Network Info tab from a get_network_info() dict."""
        self._net_info = info
        self._protocol_viz_page.set_context(
            net_info=self._net_info,
            devices=self._m1_result.get("devices", []) if self._m1_result else [],
            diag_result=self._diag_result,
            m2_result=self._m2_result,
        )
        self._diagnosis_page.set_network_info(
            info.get("gateway"),
            info.get("gateway_mac"),
        )

        lines = []
        for entry in info.get("local_ips", []):
            mask = f" / {entry['mask']}" if entry.get("mask") else ""
            lines.append(
                f"<b>Local IP:</b>  {entry['ip']}{mask}"
                f"  <span style='color:{TEXT_SECONDARY}'>(adapter: {entry['adapter']})</span>"
            )
        gw = info.get("gateway")
        if gw:
            lines.append(f"<b>Default Gateway:</b>  {gw}")
        dns = info.get("dns_servers", [])
        if dns:
            lines.append(f"<b>DNS Servers:</b>  {',  '.join(dns)}")
        domain = info.get("domain", "")
        if domain:
            lines.append(f"<b>Domain:</b>  {domain}")

        self._net_info_label.setTextFormat(Qt.TextFormat.RichText)
        self._net_info_label.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:12px; line-height:1.8;")
        self._net_info_label.setText("<br>".join(lines) if lines else "No network information available.")

        # Show a basic header status once the network is confirmed reachable
        if not self._verdict_badge.isVisible():
            if info.get("gateway") and info.get("local_ips"):
                self._verdict_badge.setText("● Network healthy")
                self._verdict_badge.setStyleSheet(
                    f"color:{GREEN}; font-size:11px; font-weight:600;"
                    " background:transparent; border:none; padding:0 12px;"
                )
                self._verdict_badge.setVisible(True)

        # Rebuild router links
        while self._router_links_layout.count():
            item = self._router_links_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if gw:
            for label, url in [
                (f"http://{gw}/",                    f"http://{gw}/"),
                (f"http://{gw}/html/index.html",     f"http://{gw}/html/index.html"),
                (f"https://{gw}/",                   f"https://{gw}/"),
            ]:
                btn = QPushButton(label)
                btn.setObjectName("btnRouterLink")
                btn.setToolTip(f"Open {url} in your browser")
                btn.clicked.connect(lambda _checked, u=url: webbrowser.open(u))
                self._router_links_layout.addWidget(btn)
        self._router_links_layout.addStretch()

        # ── Populate DHCP lease ──────────────────────────────────────────────
        dhcp = info.get("dhcp", {})
        dhcp_parts = []
        if dhcp.get("dhcp_enabled"):
            if dhcp.get("dhcp_server"):
                dhcp_parts.append(f"<b>DHCP Server:</b>  {dhcp['dhcp_server']}")
            if dhcp.get("lease_obtained"):
                dhcp_parts.append(f"<b>Lease Obtained:</b>  {dhcp['lease_obtained']}")
            if dhcp.get("lease_expires"):
                dhcp_parts.append(f"<b>Lease Expires:</b>  {dhcp['lease_expires']}")
            if dhcp.get("lease_duration_h"):
                dhcp_parts.append(
                    f"<b>Lease Duration:</b>  {dhcp['lease_duration_h']:.0f} h"
                )
        elif dhcp.get("dhcp_enabled") is False:
            dhcp_parts.append("DHCP is disabled on this adapter (static IP)")
        else:
            dhcp_parts.append("DHCP lease information not available.")
        self._dhcp_label.setTextFormat(Qt.TextFormat.RichText)
        self._dhcp_label.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:11px; line-height:1.8;")
        self._dhcp_label.setText("  " + "&nbsp;&nbsp;&nbsp;│&nbsp;&nbsp;&nbsp;".join(dhcp_parts))

        # ── Populate adapters table ──────────────────────────────────────────
        from PyQt6.QtGui import QColor
        self._adapters_table.setRowCount(0)
        for a in info.get("adapters", []):
            row = self._adapters_table.rowCount()
            self._adapters_table.insertRow(row)
            connected = a.get("connected", False)
            row_color = TEXT_PRIMARY if connected else TEXT_SECONDARY
            speed = a.get("speed_mbps", 0)
            speed_str = f"{speed} Mbps" if speed else "—"
            sig = a.get("signal_pct", -1)
            sig_str = f"{sig}%" if sig >= 0 else "—"
            status_str = "Connected" if connected else "Disconnected"
            status_color = GREEN if connected else RED
            vals = [
                a.get("name", ""),
                a.get("type", ""),
                a.get("ipv4", "—"),
                a.get("mac", "—"),
                speed_str,
                sig_str,
                a.get("ssid", ""),
                status_str,
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                c = status_color if col == 7 else row_color
                item.setForeground(QColor(c))
                self._adapters_table.setItem(row, col, item)
