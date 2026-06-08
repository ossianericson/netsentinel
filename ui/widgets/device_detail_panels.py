"""
device_detail_panels.py — _ModemDetailPanel and _RouterDetailPanel widget classes.

Extracted from ui/widgets/hub_card.py (Sprint 13) to keep that file within budget.
hub_card.py imports both classes from here.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from ui.styles import (
    ACCENT, AMBER,
    BG_ALT_ROW, BG_DARK,
    BLACK, BORDER,
    GREEN, TABLE_ROW_BORDER, TABLE_SEL,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    TH_BG, TH_BORDER, TH_TEXT,
)
from ui.widgets.hub_helpers import _rsrp_color, _sinr_color

class _ModemDetailPanel(QFrame):
    """Two-column signal grid: 5G NR | LTE Primary."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("modemDetailPanel")
        self.setStyleSheet(
            f"QFrame#modemDetailPanel {{ background:{BG_DARK}; border:none;"
            f" border-top:1px solid {BORDER}; }}"
        )
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._nr_col  = self._make_col("5G NR",       ACCENT, border_right=True)
        self._lte_col = self._make_col("LTE Primary",  AMBER,  border_right=False)
        root.addWidget(self._nr_col[0], 1)
        root.addWidget(self._lte_col[0], 1)

        _ls = f"color:{TEXT_SECONDARY}; font-size:10px; border:none; background:transparent;"
        _vs = f"color:{TEXT_PRIMARY}; font-size:10px; font-weight:bold; border:none; background:transparent;"

        def _row(col_lay, label, attr):
            h = QHBoxLayout()
            h.setContentsMargins(0, 1, 0, 1)
            h.setSpacing(6)
            l = QLabel(f"{label}:")
            l.setFixedWidth(52)
            l.setStyleSheet(_ls)
            v = QLabel("—")
            v.setStyleSheet(_vs)
            setattr(self, attr, v)
            h.addWidget(l)
            h.addWidget(v, 1)
            col_lay.addLayout(h)

        _row(self._nr_col[1],  "Band",  "_nr_band")
        _row(self._nr_col[1],  "RSRP",  "_nr_rsrp")
        _row(self._nr_col[1],  "SINR",  "_nr_sinr")
        _row(self._nr_col[1],  "RSRQ",  "_nr_rsrq")
        _row(self._nr_col[1],  "PCI",   "_nr_pci")
        _row(self._nr_col[1],  "ARFCN", "_nr_arfcn")
        self._nr_col[1].addStretch()

        _row(self._lte_col[1], "Band",   "_lte_band")
        _row(self._lte_col[1], "RSRP",   "_lte_rsrp")
        _row(self._lte_col[1], "SNR",    "_lte_snr")
        _row(self._lte_col[1], "RSRQ",   "_lte_rsrq")
        _row(self._lte_col[1], "PCI",    "_lte_pci")
        _row(self._lte_col[1], "EARFCN", "_lte_earfcn")
        self._lte_col[1].addStretch()

        # Connection strip
        conn = QFrame()
        conn.setStyleSheet(
            f"background:{BG_DARK}; border:none; border-bottom:1px solid {BORDER};"
        )
        cl = QHBoxLayout(conn)
        cl.setContentsMargins(12, 4, 12, 4)
        cl.setSpacing(0)

        def _cpair(label, attr):
            ll = QLabel(f"{label}: ")
            ll.setStyleSheet(_ls)
            vl = QLabel("—")
            vl.setStyleSheet(_vs)
            setattr(self, attr, vl)
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.VLine)
            sep.setStyleSheet(f"border:none; border-left:1px solid {BORDER}; margin:0 12px;")
            cl.addWidget(ll); cl.addWidget(vl); cl.addWidget(sep)

        _cpair("Operator", "_conn_op")
        _cpair("Cell ID",  "_conn_cell")
        _cpair("WAN IP",   "_conn_ip")
        cl.addStretch()

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(conn)

        body = QFrame()
        body.setStyleSheet(f"background:{BG_DARK}; border:none;")
        body.setLayout(root)
        outer.addWidget(body)

        self.setLayout(outer)

    def _make_col(self, title: str, color: str, border_right: bool):
        col = QFrame()
        border = f"border-right:1px solid {BORDER};" if border_right else ""
        col.setStyleSheet(f"background:{BG_DARK}; border:none; {border}")
        lay = QVBoxLayout(col)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet(
            f"color:{color}; font-size:10px; font-weight:bold; border:none;"
            f" border-bottom:1px solid {BORDER}; background:transparent;"
            f" padding-bottom:3px; margin-bottom:2px;"
        )
        lay.addWidget(t)
        return col, lay

    def update(self, extra: dict, status: dict | None = None) -> None:
        # wan_ip lives at status top-level in most plugins, not inside extra
        merged = {**(status or {}), **extra}
        def _s(v): return str(v) if v is not None else "—"
        def _dbm(v): return f"{float(v):.1f} dBm" if v is not None else "—"
        def _db(v):  return f"{float(v):.1f} dB"  if v is not None else "—"

        self._nr_band.setText(_s(merged.get("nr5g_band")))
        nr_rsrp = merged.get("nr5g_rsrp_dbm")
        self._nr_rsrp.setText(_dbm(nr_rsrp))
        self._nr_rsrp.setStyleSheet(
            f"color:{_rsrp_color(nr_rsrp)}; font-size:10px; font-weight:bold;"
            f" border:none; background:transparent;"
        )
        nr_sinr = merged.get("nr5g_sinr_db")
        self._nr_sinr.setText(_db(nr_sinr))
        self._nr_sinr.setStyleSheet(
            f"color:{_sinr_color(nr_sinr)}; font-size:10px; font-weight:bold;"
            f" border:none; background:transparent;"
        )
        self._nr_rsrq.setText(_db(merged.get("nr5g_rsrq_db")))
        self._nr_pci.setText(_s(merged.get("nr5g_pci")))
        self._nr_arfcn.setText(_s(merged.get("nr5g_arfcn")))

        lte_rsrp = merged.get("lte_rsrp_dbm")
        self._lte_band.setText(_s(merged.get("lte_band")))
        self._lte_rsrp.setText(_dbm(lte_rsrp))
        self._lte_rsrp.setStyleSheet(
            f"color:{_rsrp_color(lte_rsrp)}; font-size:10px; font-weight:bold;"
            f" border:none; background:transparent;"
        )
        lte_snr = merged.get("lte_snr_db")
        self._lte_snr.setText(_db(lte_snr))
        self._lte_snr.setStyleSheet(
            f"color:{_sinr_color(lte_snr)}; font-size:10px; font-weight:bold;"
            f" border:none; background:transparent;"
        )
        self._lte_rsrq.setText(_db(merged.get("lte_rsrq_db")))
        self._lte_pci.setText(_s(merged.get("lte_pci")))
        self._lte_earfcn.setText(_s(merged.get("lte_earfcn")))

        mcc, mnc = merged.get("mcc"), merged.get("mnc")
        self._conn_op.setText(f"{mcc}-{mnc}" if mcc and mnc else "—")
        cell = merged.get("cell_id")
        enb  = merged.get("enb_id")
        self._conn_cell.setText(
            f"{cell} (eNB: {enb})" if cell and enb else _s(cell)
        )
        self._conn_ip.setText(_s(merged.get("wan_ip")))


# ── Router/AP detail panel ────────────────────────────────────────────────────

class _RouterDetailPanel(QFrame):
    """Mesh nodes table + connected clients table for router/AP plugins.

    The client list supports two view modes toggled by a button in the header:
      flat    — QTableWidget sorted by hostname (default)
      grouped — QTreeWidget with each mesh node as a collapsible group header

    Both modes work for all plugins: Deco (many nodes), FritzBox/Netgear (single
    router group), UniFi, MikroTik, etc. Clients with no unit field go to a
    "Router" fallback group.

    Right-click context menus mirror mesh_router_page:
      Nodes:   Geolocation Map | Copy IP | Copy MAC
      Clients: Port Scan | Geolocation Map | AbuseIPDB | Copy IP | Copy MAC
    """

    # Emitted on context-menu actions — parent page connects to its own signals
    geo_map_ip     = pyqtSignal(str)
    port_scan_ip   = pyqtSignal(str)
    check_abuse_ip = pyqtSignal(str)

    _TABLE_SS = (
        f"QTableWidget {{ border:none; font-size:10px; color:{TEXT_PRIMARY}; }}"
        f"QHeaderView::section {{"
        f"  background:{TH_BG}; color:{TH_TEXT}; font-size:10px;"
        f"  font-weight:bold; padding:3px 5px; border:none;"
        f"  border-right:1px solid {TH_BORDER};"
        f"}}"
        f"QTableWidget::item:selected {{ background:{TABLE_SEL}; color:{TEXT_PRIMARY}; }}"
        f"QTableWidget::item:alternate {{ background:{BG_ALT_ROW}; }}"
        f"QTableWidget::item {{ border-bottom:1px solid {TABLE_ROW_BORDER}; }}"
    )
    _TREE_SS = (
        f"QTreeWidget {{ border:none; font-size:10px; color:{TEXT_PRIMARY};"
        f"  background:{BG_DARK}; alternate-background-color:{BG_ALT_ROW}; }}"
        f"QTreeWidget::item {{ border-bottom:1px solid {TABLE_ROW_BORDER};"
        f"  padding:2px 0; }}"
        f"QTreeWidget::item:selected {{ background:{TABLE_SEL}; color:{TEXT_PRIMARY}; }}"
        f"QHeaderView::section {{"
        f"  background:{TH_BG}; color:{TH_TEXT}; font-size:10px;"
        f"  font-weight:bold; padding:3px 5px; border:none;"
        f"  border-right:1px solid {TH_BORDER};"
        f"}}"
        f"QTreeWidget::branch:has-children:!has-siblings:closed,"
        f"QTreeWidget::branch:closed:has-children:has-siblings {{"
        f"  image: none; border-image: none; }}"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._view_mode = "flat"
        self._last_clients: list = []
        self._last_nodes: list = []

        self.setObjectName("routerDetailPanel")
        self.setStyleSheet(
            f"QFrame#routerDetailPanel {{ background:{BG_DARK}; border:none;"
            f" border-top:1px solid {BORDER}; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 10)
        lay.setSpacing(8)

        # ── Mesh nodes ────────────────────────────────────────────────────────
        nodes_hdr = QLabel("MESH NODES")
        nodes_hdr.setStyleSheet(
            f"color:{ACCENT}; font-size:9px; font-weight:bold; border:none;"
            f" background:transparent; letter-spacing:0.5px;"
        )
        lay.addWidget(nodes_hdr)

        self._node_table = QTableWidget(0, 3)
        self._node_table.setHorizontalHeaderLabels(["Node", "Role", "MAC"])
        self._node_table.horizontalHeader().setStretchLastSection(True)
        self._node_table.setAlternatingRowColors(True)
        self._node_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._node_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._node_table.verticalHeader().setVisible(False)
        self._node_table.setShowGrid(True)
        self._node_table.verticalHeader().setDefaultSectionSize(24)
        self._node_table.setMaximumHeight(180)
        self._node_table.setStyleSheet(self._TABLE_SS)
        lay.addWidget(self._node_table)

        # ── Connected clients header ──────────────────────────────────────────
        cli_hdr_row = QHBoxLayout()
        cli_hdr_row.setContentsMargins(0, 4, 0, 0)
        clients_hdr = QLabel("CONNECTED CLIENTS")
        clients_hdr.setStyleSheet(
            f"color:{AMBER}; font-size:9px; font-weight:bold; border:none;"
            f" background:transparent; letter-spacing:0.5px;"
        )
        self._client_count_lbl = QLabel("")
        self._client_count_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:9px; border:none; background:transparent;"
        )
        self._toggle_btn = QPushButton("Group by node")
        self._toggle_btn.setFixedHeight(20)
        self._toggle_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_DARK}; color:{TEXT_MUTED}; border:1px solid {BORDER};"
            f"  border-radius:3px; font-size:9px; padding:0 6px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; border-color:{ACCENT}; }}"
            f"QPushButton:checked {{ background:{ACCENT}; color:{BLACK}; border-color:{ACCENT}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.toggled.connect(self._on_toggle)
        cli_hdr_row.addWidget(clients_hdr)
        cli_hdr_row.addWidget(self._client_count_lbl)
        cli_hdr_row.addStretch()
        cli_hdr_row.addWidget(self._toggle_btn)
        lay.addLayout(cli_hdr_row)

        # ── Client stack (flat table / grouped tree) ──────────────────────────
        self._client_stack = QStackedWidget()

        # Page 0: flat QTableWidget — cols: Hostname, IP, Band, Node, ↑ KB/s, ↓ KB/s
        self._client_table = QTableWidget(0, 6)
        self._client_table.setHorizontalHeaderLabels(
            ["Hostname", "IP", "Band", "Node", "↑ KB/s", "↓ KB/s"]
        )
        hdr = self._client_table.horizontalHeader()
        hdr.setSectionResizeMode(0, hdr.ResizeMode.Stretch)
        self._client_table.setColumnWidth(1, 115)
        self._client_table.setColumnWidth(2, 68)
        self._client_table.setColumnWidth(3, 95)
        self._client_table.setColumnWidth(4, 62)
        self._client_table.setColumnWidth(5, 62)
        self._client_table.setAlternatingRowColors(True)
        self._client_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._client_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._client_table.verticalHeader().setVisible(False)
        self._client_table.setShowGrid(True)
        self._client_table.verticalHeader().setDefaultSectionSize(24)
        self._client_table.setMaximumHeight(220)
        self._client_table.setStyleSheet(self._TABLE_SS)
        self._client_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._client_table.customContextMenuRequested.connect(self._client_context_menu)
        self._client_stack.addWidget(self._client_table)  # index 0

        # Page 1: grouped QTreeWidget — cols: Node/Hostname, IP, Band, ↑ KB/s, ↓ KB/s
        self._tree_widget = QTreeWidget()
        self._tree_widget.setHeaderLabels(["Node / Hostname", "IP", "Band", "↑ KB/s", "↓ KB/s"])
        thdr = self._tree_widget.header()
        thdr.setSectionResizeMode(0, thdr.ResizeMode.Stretch)
        self._tree_widget.setColumnWidth(1, 115)
        self._tree_widget.setColumnWidth(2, 68)
        self._tree_widget.setColumnWidth(3, 62)
        self._tree_widget.setColumnWidth(4, 62)
        self._tree_widget.setAlternatingRowColors(True)
        self._tree_widget.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        self._tree_widget.setSelectionBehavior(QTreeWidget.SelectionBehavior.SelectRows)
        self._tree_widget.setMaximumHeight(220)
        self._tree_widget.setStyleSheet(self._TREE_SS)
        self._tree_widget.setRootIsDecorated(True)
        self._tree_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree_widget.customContextMenuRequested.connect(self._tree_context_menu)
        self._client_stack.addWidget(self._tree_widget)   # index 1

        # Node table context menu
        self._node_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._node_table.customContextMenuRequested.connect(self._node_context_menu)

        lay.addWidget(self._client_stack)

    # ── Toggle ────────────────────────────────────────────────────────────────

    def _on_toggle(self, checked: bool) -> None:
        self._view_mode = "grouped" if checked else "flat"
        self._toggle_btn.setText("Show flat list" if checked else "Group by node")
        self._client_stack.setCurrentIndex(1 if checked else 0)
        if checked:
            self._rebuild_tree(self._last_clients, self._last_nodes)

    # ── Data population ───────────────────────────────────────────────────────

    @staticmethod
    def _display_name(c: dict) -> str:
        import re as _re
        _mac_re = _re.compile(r"^([0-9a-f]{2}[:\-]){5}[0-9a-f]{2}$", _re.I)
        hostname = c.get("hostname", "") or ""
        return hostname if hostname and not _mac_re.match(hostname) else c.get("ip", "—")

    @staticmethod
    def _bw_str(val) -> str:
        try:
            v = float(val)
            return f"{v:.0f}" if v else ""
        except (TypeError, ValueError):
            return ""

    def update(self, status: dict, clients: list) -> None:
        if not isinstance(status, dict):
            status = {}
        nodes   = [n for n in (status.get("extra", {}).get("nodes") or []) if isinstance(n, dict)]
        clients = [c for c in (clients or []) if isinstance(c, dict)]
        n_cli = status.get("connected_clients") or len(clients)

        self._last_clients = clients
        self._last_nodes   = nodes

        # Node table — store IP in col 2, MAC col 3 (IP hidden by default but accessible for menu)
        self._node_table.setRowCount(0)
        for node in nodes:
            r = self._node_table.rowCount()
            self._node_table.insertRow(r)
            self._node_table.setItem(r, 0, QTableWidgetItem(node.get("name", "—")))
            role_item = QTableWidgetItem(node.get("role", "—"))
            if node.get("role") == "master":
                role_item.setForeground(QColor(GREEN))
            self._node_table.setItem(r, 1, role_item)
            # MAC in col 2 — store IP as UserRole for context menu
            mac_item = QTableWidgetItem(node.get("mac", "—"))
            mac_item.setData(Qt.ItemDataRole.UserRole, node.get("ip", ""))
            self._node_table.setItem(r, 2, mac_item)

        self._client_count_lbl.setText(
            f"({n_cli} device{'s' if n_cli != 1 else ''})" if n_cli is not None else ""
        )

        # Flat table
        self._client_table.setRowCount(0)
        for c in clients:
            r = self._client_table.rowCount()
            self._client_table.insertRow(r)
            hn_item = QTableWidgetItem(self._display_name(c))
            hn_item.setData(Qt.ItemDataRole.UserRole, {"ip": c.get("ip", ""), "mac": c.get("mac", "")})
            self._client_table.setItem(r, 0, hn_item)
            self._client_table.setItem(r, 1, QTableWidgetItem(c.get("ip", "—")))
            band = c.get("band", "") or ""
            band_item = QTableWidgetItem(band if band else "—")
            if "5" in band:
                band_item.setForeground(QColor(ACCENT))
            self._client_table.setItem(r, 2, band_item)
            self._client_table.setItem(r, 3, QTableWidgetItem(c.get("unit", "") or "—"))
            ul = QTableWidgetItem(self._bw_str(c.get("upload_kbps")))
            ul.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            dl = QTableWidgetItem(self._bw_str(c.get("download_kbps")))
            dl.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._client_table.setItem(r, 4, ul)
            self._client_table.setItem(r, 5, dl)

        if self._view_mode == "grouped":
            self._rebuild_tree(clients, nodes)

    def _rebuild_tree(self, clients: list, nodes: list) -> None:
        self._tree_widget.clear()

        node_names = [n.get("name", "") for n in nodes if n.get("name")]
        groups: dict[str, list] = {name: [] for name in node_names}
        ungrouped: list = []

        for c in clients:
            unit = (c.get("unit") or "").strip()
            if unit in groups:
                groups[unit].append(c)
            elif unit:
                groups.setdefault(unit, []).append(c)
            else:
                ungrouped.append(c)

        if ungrouped:
            groups["Router"] = ungrouped

        for group_name, group_clients in groups.items():
            node_meta = next((n for n in nodes if n.get("name") == group_name), {})
            role = node_meta.get("role", "")
            role_suffix = " (main)" if role == "master" else (" (satellite)" if role == "slave" else "")
            n = len(group_clients)
            header = QTreeWidgetItem([
                f"{group_name}{role_suffix}  ·  {n} device{'s' if n != 1 else ''}",
                "", "", "", "",
            ])
            header.setForeground(0, QColor(ACCENT if role == "master" else TEXT_MUTED))
            self._tree_widget.addTopLevelItem(header)

            for c in group_clients:
                band = c.get("band", "") or ""
                child = QTreeWidgetItem([
                    self._display_name(c),
                    c.get("ip", "—"),
                    band if band else "—",
                    self._bw_str(c.get("upload_kbps")),
                    self._bw_str(c.get("download_kbps")),
                ])
                child.setData(0, Qt.ItemDataRole.UserRole,
                              {"ip": c.get("ip", ""), "mac": c.get("mac", "")})
                if "5" in band:
                    child.setForeground(2, QColor(ACCENT))
                for col in (3, 4):
                    child.setTextAlignment(col, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                header.addChild(child)

            header.setExpanded(True)

    # ── Context menus ─────────────────────────────────────────────────────────

    def _node_context_menu(self, pos) -> None:
        row = self._node_table.rowAt(pos.y())
        if row < 0:
            return
        mac_item = self._node_table.item(row, 2)
        ip  = (mac_item.data(Qt.ItemDataRole.UserRole) or "") if mac_item else ""
        mac = self._node_table.item(row, 2).text() if self._node_table.item(row, 2) else ""
        menu = QMenu(self)
        if ip:
            menu.addAction("Show on Geolocation Map", lambda: self.geo_map_ip.emit(ip))
            menu.addSeparator()
            menu.addAction(f"Copy IP  {ip}", lambda: QApplication.clipboard().setText(ip))
        if mac and mac != "—":
            menu.addAction(f"Copy MAC  {mac}", lambda: QApplication.clipboard().setText(mac))
        if not menu.isEmpty():
            menu.exec(QCursor.pos())

    def _client_context_menu(self, pos) -> None:
        row = self._client_table.rowAt(pos.y())
        if row < 0:
            return
        data = self._client_table.item(row, 0)
        info = data.data(Qt.ItemDataRole.UserRole) if data else {}
        ip  = info.get("ip", "") if info else ""
        mac = info.get("mac", "") if info else ""
        self._show_client_menu(ip, mac)

    def _tree_context_menu(self, pos) -> None:
        item = self._tree_widget.itemAt(pos)
        if not item or item.parent() is None:
            return  # top-level node header — no client menu
        info = item.data(0, Qt.ItemDataRole.UserRole) or {}
        self._show_client_menu(info.get("ip", ""), info.get("mac", ""))

    def _show_client_menu(self, ip: str, mac: str) -> None:
        menu = QMenu(self)
        if ip:
            menu.addAction("Port Scan", lambda: self.port_scan_ip.emit(ip))
            menu.addAction("Show on Geolocation Map", lambda: self.geo_map_ip.emit(ip))
            menu.addAction("Check IP (AbuseIPDB)", lambda: self.check_abuse_ip.emit(ip))
            menu.addSeparator()
            menu.addAction(f"Copy IP  {ip}", lambda: QApplication.clipboard().setText(ip))
        if mac and mac != "—":
            menu.addAction(f"Copy MAC  {mac}", lambda: QApplication.clipboard().setText(mac))
        if not menu.isEmpty():
            menu.exec(QCursor.pos())
