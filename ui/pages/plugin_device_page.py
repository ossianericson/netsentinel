"""
PluginDevicePage — live status page for a hardware integration plugin.

Renders differently based on plugin type:
  "modem"  → signal panel (NR5G / LTE bands, RSRP, SINR, cell info)
  "router" → mesh node cards + connected-client table
  other    → generic key/value status panel

Receives data via update(result) where result has the shape:
  {"info": {...}, "status": {...}, "clients": [...], "_path": "..."}

The page is marked disabled/greyed when the plugin file no longer exists.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from PyQt6.QtCore    import Qt
from PyQt6.QtGui     import QColor, QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from ui.styles import (
    ACCENT, AMBER, BORDER, BG_CARD, BG_DARK, BG_ALT_ROW,
    GREEN, RED, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)


# ── helpers ────────────────────────────────────────────────────────────────────

def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("pluginCard")
    card.setStyleSheet(
        f"QFrame#pluginCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
        " border-radius:4px; }}"
    )
    outer = QVBoxLayout(card)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    hdr = QFrame()
    hdr.setStyleSheet(
        f"QFrame {{ background:{BG_CARD}; border:none;"
        f" border-bottom:1px solid {BORDER}; border-radius:4px 4px 0 0; }}"
    )
    hdr_lay = QHBoxLayout(hdr)
    hdr_lay.setContentsMargins(12, 6, 12, 6)
    lbl = QLabel(title.upper())
    lbl.setStyleSheet(
        f"color:{TEXT_PRIMARY}; font-weight:bold; font-size:11px;"
        " letter-spacing:0.5px; background:transparent; border:none;"
    )
    hdr_lay.addWidget(lbl)
    hdr_lay.addStretch()
    outer.addWidget(hdr)

    body = QVBoxLayout()
    body.setContentsMargins(12, 10, 12, 10)
    body.setSpacing(6)
    outer.addLayout(body, 1)
    return card, body


def _row(label: str, layout: QVBoxLayout) -> QLabel:
    h = QHBoxLayout()
    h.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(label)
    lbl.setFixedWidth(160)
    lbl.setStyleSheet(
        f"color:{TEXT_SECONDARY}; font-size:12px; background:transparent; border:none;"
    )
    val = QLabel("—")
    val.setStyleSheet(
        f"color:{TEXT_PRIMARY}; font-size:12px; font-weight:bold;"
        " background:transparent; border:none;"
    )
    val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    h.addWidget(lbl)
    h.addWidget(val, 1)
    layout.addLayout(h)
    return val


def _quality_color(rsrp: Optional[float]) -> str:
    if rsrp is None:
        return TEXT_SECONDARY
    if rsrp >= -80:
        return GREEN
    if rsrp >= -90:
        return "#FFA726"
    if rsrp >= -100:
        return AMBER
    return RED


def _fmt(v, suffix: str = "") -> str:
    if v is None:
        return "—"
    return f"{v}{suffix}"


# ── page ───────────────────────────────────────────────────────────────────────

class PluginDevicePage(QWidget):
    """Live status page for one hardware plugin."""

    def __init__(self, plugin_path: str, label: str, hw_type: str,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._path   = plugin_path
        self._label  = label
        self._type   = hw_type
        self._build_ui()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border:none; }")
        outer.addWidget(scroll)

        inner = QWidget()
        inner.setStyleSheet(f"QWidget {{ background:{BG_DARK}; }}")
        scroll.setWidget(inner)

        self._root = QVBoxLayout(inner)
        self._root.setContentsMargins(16, 16, 16, 16)
        self._root.setSpacing(12)

        # Error / info banner
        self._banner = QLabel()
        self._banner.setWordWrap(True)
        self._banner.setContentsMargins(10, 6, 10, 6)
        self._banner.setStyleSheet(
            f"background:{RED}22; color:{RED}; border:1px solid {RED}44;"
            " border-radius:4px; font-size:12px;"
        )
        self._banner.setVisible(False)
        self._root.addWidget(self._banner)

        # Timestamp row
        self._ts_lbl = QLabel("No data yet — run a Test from the Hardware page.")
        self._ts_lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px;")
        self._root.addWidget(self._ts_lbl)

        if self._type == "modem":
            self._build_modem_ui()
        elif self._type in ("router", "ap", "switch"):
            self._build_router_ui()
        else:
            self._build_generic_ui()

        self._root.addStretch(1)

    def _build_modem_ui(self) -> None:
        # Status
        card, body = _card("Status")
        self._m_wan_ip      = _row("WAN IP",         body)
        self._m_wan_status  = _row("WAN Status",     body)
        self._m_net_type    = _row("Network Type",   body)
        self._m_bars        = _row("Signal Bars",    body)
        self._m_firmware    = _row("Firmware",       body)
        self._root.addWidget(card)

        # NR5G
        card2, body2 = _card("5G NR")
        self._m_nr_band  = _row("Band",    body2)
        self._m_nr_rsrp  = _row("RSRP",   body2)
        self._m_nr_sinr  = _row("SINR",   body2)
        self._m_nr_rsrq  = _row("RSRQ",   body2)
        self._m_nr_pci   = _row("PCI",    body2)
        self._m_nr_arfcn = _row("ARFCN",  body2)
        self._root.addWidget(card2)

        # LTE
        card3, body3 = _card("LTE")
        self._m_lte_band   = _row("Band",   body3)
        self._m_lte_rsrp   = _row("RSRP",  body3)
        self._m_lte_snr    = _row("SNR",   body3)
        self._m_lte_rsrq   = _row("RSRQ",  body3)
        self._m_lte_pci    = _row("PCI",   body3)
        self._m_lte_earfcn = _row("EARFCN", body3)
        self._root.addWidget(card3)

        # Cell identity
        card4, body4 = _card("Cell Identity")
        self._m_cell_id = _row("Cell ID", body4)
        self._m_enb_id  = _row("eNB ID",  body4)
        self._m_mcc     = _row("MCC",     body4)
        self._m_mnc     = _row("MNC",     body4)
        self._root.addWidget(card4)

    def _build_router_ui(self) -> None:
        self._r_group_by_node: bool = False
        self._r_last_nodes:   list  = []
        self._r_last_clients: list  = []

        # Summary
        card, body = _card("Status")
        self._r_clients = _row("Connected clients", body)
        self._r_nodes   = _row("Mesh nodes",        body)
        self._r_wan_ip  = _row("WAN IP",            body)
        self._root.addWidget(card)

        # Nodes table
        card2, body2 = _card("Mesh Nodes")
        self._r_node_tbl = QTableWidget(0, 3)
        self._r_node_tbl.setHorizontalHeaderLabels(["Name", "MAC", "Role"])
        self._r_node_tbl.horizontalHeader().setStretchLastSection(True)
        self._r_node_tbl.verticalHeader().setVisible(False)
        self._r_node_tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._r_node_tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._r_node_tbl.setAlternatingRowColors(True)
        self._r_node_tbl.setStyleSheet(
            f"QTableWidget {{ border:none; background:{BG_CARD}; alternate-background-color:{BG_ALT_ROW}; }}"
            f"QHeaderView::section {{ background:{BG_CARD}; color:{TEXT_SECONDARY}; border:none;"
            f" border-bottom:1px solid {BORDER}; padding:4px 8px; font-size:11px; }}"
        )
        self._r_node_tbl.setMaximumHeight(150)
        body2.addWidget(self._r_node_tbl)
        self._root.addWidget(card2)

        # Clients card — header row contains the flat/grouped toggle
        _tbl_ss = (
            f"QTableWidget {{ border:none; background:{BG_CARD};"
            f" alternate-background-color:{BG_ALT_ROW}; }}"
            f"QHeaderView::section {{ background:{BG_CARD}; color:{TEXT_SECONDARY}; border:none;"
            f" border-bottom:1px solid {BORDER}; padding:4px 8px; font-size:11px; }}"
        )
        _tree_ss = (
            f"QTreeWidget {{ border:none; background:{BG_CARD}; outline:none; }}"
            f"QTreeWidget::item {{ padding:3px 4px; color:{TEXT_PRIMARY}; }}"
            f"QTreeWidget::item:selected {{ background:{ACCENT}22; color:{TEXT_PRIMARY}; }}"
            f"QHeaderView::section {{ background:{BG_CARD}; color:{TEXT_SECONDARY}; border:none;"
            f" border-bottom:1px solid {BORDER}; padding:4px 8px; font-size:11px; }}"
            f"QTreeWidget::branch:has-children:!has-siblings:closed,"
            f"QTreeWidget::branch:closed:has-children:has-siblings {{"
            f" border-image:none; image:url(none); }}"
        )

        # Build the clients card manually so we can inject the toggle into the header
        card3 = QFrame()
        card3.setObjectName("pluginCard")
        card3.setStyleSheet(
            f"QFrame#pluginCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:4px; }}"
        )
        card3_outer = QVBoxLayout(card3)
        card3_outer.setContentsMargins(0, 0, 0, 0)
        card3_outer.setSpacing(0)

        hdr3 = QFrame()
        hdr3.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:none;"
            f" border-bottom:1px solid {BORDER}; border-radius:4px 4px 0 0; }}"
        )
        hdr3_lay = QHBoxLayout(hdr3)
        hdr3_lay.setContentsMargins(12, 4, 8, 4)
        hdr3_lbl = QLabel("CONNECTED CLIENTS")
        hdr3_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-weight:bold; font-size:11px;"
            " letter-spacing:0.5px; background:transparent; border:none;"
        )
        hdr3_lay.addWidget(hdr3_lbl)
        hdr3_lay.addStretch()

        self._r_group_btn = QPushButton("≡  Group by node")
        self._r_group_btn.setFixedHeight(22)
        self._r_group_btn.setCheckable(True)
        self._r_group_btn.setToolTip("Show clients grouped under their mesh node (expand/collapse each node)")
        self._r_group_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:1px solid {BORDER};"
            f" border-radius:3px; padding:0 8px; font-size:10px; }}"
            f"QPushButton:hover {{ background:{BG_ALT_ROW}; color:{TEXT_PRIMARY}; }}"
            f"QPushButton:checked {{ background:{ACCENT}22; color:{ACCENT}; border-color:{ACCENT}; }}"
        )
        self._r_group_btn.toggled.connect(self._on_group_toggled)
        hdr3_lay.addWidget(self._r_group_btn)
        card3_outer.addWidget(hdr3)

        body3 = QVBoxLayout()
        body3.setContentsMargins(0, 0, 0, 0)
        body3.setSpacing(0)

        # Flat table (default view)
        self._r_client_tbl = QTableWidget(0, 5)
        self._r_client_tbl.setHorizontalHeaderLabels(["IP", "Hostname", "MAC", "Band", "Node"])
        self._r_client_tbl.horizontalHeader().setStretchLastSection(True)
        self._r_client_tbl.verticalHeader().setVisible(False)
        self._r_client_tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._r_client_tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._r_client_tbl.setAlternatingRowColors(True)
        self._r_client_tbl.setStyleSheet(_tbl_ss)
        body3.addWidget(self._r_client_tbl)

        # Grouped tree (hidden by default)
        self._r_tree = QTreeWidget()
        self._r_tree.setColumnCount(4)
        self._r_tree.setHeaderLabels(["Device", "IP", "MAC", "Band"])
        self._r_tree.header().setStretchLastSection(True)
        self._r_tree.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        self._r_tree.setSelectionBehavior(QTreeWidget.SelectionBehavior.SelectRows)
        self._r_tree.setRootIsDecorated(True)
        self._r_tree.setStyleSheet(_tree_ss)
        self._r_tree.setVisible(False)
        body3.addWidget(self._r_tree)

        card3_outer.addLayout(body3, 1)
        self._root.addWidget(card3)

    def _build_generic_ui(self) -> None:
        card, body = _card("Status")
        self._g_rows: dict[str, QLabel] = {}
        for key in ("wan_ip", "uptime_sec", "download_mbps", "upload_mbps",
                    "signal_dbm", "connected_clients"):
            self._g_rows[key] = _row(key.replace("_", " ").title(), body)
        self._root.addWidget(card)

    # ── data ──────────────────────────────────────────────────────────────────

    def update(self, result: dict) -> None:
        """Refresh the page from a plugin result dict."""
        info    = result.get("info", {})
        status  = result.get("status", {})
        clients = result.get("clients", [])
        extra   = status.get("extra", {})
        err     = extra.get("error")

        # File-missing warning
        file_ok = os.path.isfile(self._path)
        if not file_ok:
            self._show_banner(f"Plugin file not found: {self._path}", RED)
        elif err:
            self._show_banner(str(err), RED)
        else:
            self._banner.setVisible(False)

        self._ts_lbl.setText(
            f"Last updated: {datetime.now().strftime('%H:%M:%S')}  ·  {info.get('ip', '')}"
        )

        if self._type == "modem":
            self._fill_modem(status, extra)
        elif self._type in ("router", "ap", "switch"):
            self._fill_router(status, extra, clients)
        else:
            self._fill_generic(status)

    def _show_banner(self, text: str, color: str) -> None:
        self._banner.setText(text)
        self._banner.setStyleSheet(
            f"background:{color}22; color:{color}; border:1px solid {color}44;"
            " border-radius:4px; font-size:12px; padding:6px 10px;"
        )
        self._banner.setVisible(True)

    def _fill_modem(self, status: dict, extra: dict) -> None:
        self._m_wan_ip.setText(_fmt(status.get("wan_ip")))
        self._m_wan_status.setText(_fmt(status.get("wan_status")))
        self._m_net_type.setText(_fmt(extra.get("network_type")))
        bars = extra.get("signal_bars")
        self._m_bars.setText(_fmt(bars))
        self._m_firmware.setText(_fmt(extra.get("firmware")))

        nr_rsrp = extra.get("nr5g_rsrp_dbm")
        self._m_nr_band.setText(_fmt(extra.get("nr5g_band")))
        self._m_nr_rsrp.setText(_fmt(nr_rsrp, " dBm"))
        self._m_nr_rsrp.setStyleSheet(
            f"color:{_quality_color(nr_rsrp)}; font-size:12px; font-weight:bold;"
            " background:transparent; border:none;"
        )
        self._m_nr_sinr.setText(_fmt(extra.get("nr5g_sinr_db"), " dB"))
        self._m_nr_rsrq.setText(_fmt(extra.get("nr5g_rsrq_db"), " dB"))
        self._m_nr_pci.setText(_fmt(extra.get("nr5g_pci")))
        self._m_nr_arfcn.setText(_fmt(extra.get("nr5g_arfcn")))

        lte_rsrp = extra.get("lte_rsrp_dbm")
        self._m_lte_band.setText(_fmt(extra.get("lte_band")))
        self._m_lte_rsrp.setText(_fmt(lte_rsrp, " dBm"))
        self._m_lte_rsrp.setStyleSheet(
            f"color:{_quality_color(lte_rsrp)}; font-size:12px; font-weight:bold;"
            " background:transparent; border:none;"
        )
        self._m_lte_snr.setText(_fmt(extra.get("lte_snr_db"), " dB"))
        self._m_lte_rsrq.setText(_fmt(extra.get("lte_rsrq_db"), " dB"))
        self._m_lte_pci.setText(_fmt(extra.get("lte_pci")))
        self._m_lte_earfcn.setText(_fmt(extra.get("lte_earfcn")))

        self._m_cell_id.setText(_fmt(extra.get("cell_id")))
        self._m_enb_id.setText(_fmt(extra.get("enb_id")))
        self._m_mcc.setText(_fmt(extra.get("mcc")))
        self._m_mnc.setText(_fmt(extra.get("mnc")))

    def _fill_router(self, status: dict, extra: dict, clients: list) -> None:
        nodes = extra.get("nodes", [])
        self._r_clients.setText(str(status.get("connected_clients") or len(clients)))
        self._r_nodes.setText(str(status.get("mesh_nodes") or len(nodes)))
        self._r_wan_ip.setText(_fmt(status.get("wan_ip")))

        # Nodes table
        self._r_node_tbl.setRowCount(0)
        for node in nodes:
            r = self._r_node_tbl.rowCount()
            self._r_node_tbl.insertRow(r)
            self._r_node_tbl.setItem(r, 0, QTableWidgetItem(node.get("name", "")))
            self._r_node_tbl.setItem(r, 1, QTableWidgetItem(node.get("mac", "")))
            role_item = QTableWidgetItem(node.get("role", ""))
            role_item.setForeground(
                __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(
                    ACCENT if node.get("role") == "master" else TEXT_SECONDARY
                )
            )
            self._r_node_tbl.setItem(r, 2, role_item)
        self._r_node_tbl.resizeColumnsToContents()

        # Store for re-use when toggle switches
        self._r_last_nodes   = nodes
        self._r_last_clients = clients

        # Flat clients table
        self._r_client_tbl.setRowCount(0)
        for c in clients:
            r = self._r_client_tbl.rowCount()
            self._r_client_tbl.insertRow(r)
            self._r_client_tbl.setItem(r, 0, QTableWidgetItem(c.get("ip", "") or ""))
            self._r_client_tbl.setItem(r, 1, QTableWidgetItem(c.get("hostname", "") or ""))
            self._r_client_tbl.setItem(r, 2, QTableWidgetItem(c.get("mac", "") or ""))
            self._r_client_tbl.setItem(r, 3, QTableWidgetItem(c.get("band", "") or ""))
            self._r_client_tbl.setItem(r, 4, QTableWidgetItem(c.get("unit", "") or ""))
        self._r_client_tbl.resizeColumnsToContents()

        if self._r_group_by_node:
            self._rebuild_tree(nodes, clients)

    # ── grouping ──────────────────────────────────────────────────────────────

    def _on_group_toggled(self, checked: bool) -> None:
        self._r_group_by_node = checked
        self._r_client_tbl.setVisible(not checked)
        self._r_tree.setVisible(checked)
        if checked:
            self._rebuild_tree(self._r_last_nodes, self._r_last_clients)

    def _rebuild_tree(self, nodes: list, clients: list) -> None:
        self._r_tree.clear()

        # Build node-name → client list map using client["unit"]
        node_names = [n.get("name", "") for n in nodes]
        buckets: dict[str, list] = {n: [] for n in node_names}
        unassigned: list = []
        for c in clients:
            unit = c.get("unit", "") or ""
            if unit in buckets:
                buckets[unit].append(c)
            else:
                unassigned.append(c)

        bold = QFont()
        bold.setBold(True)

        def _make_client_item(c: dict) -> QTreeWidgetItem:
            name = c.get("hostname") or c.get("mac") or "Unknown"
            it = QTreeWidgetItem([name, c.get("ip", "") or "", c.get("mac", "") or "", c.get("band", "") or ""])
            it.setForeground(0, QColor(TEXT_PRIMARY))
            return it

        for node in nodes:
            node_name = node.get("name", "")
            role      = node.get("role", "")
            node_clients = buckets.get(node_name, [])
            count = len(node_clients)

            role_chip = f"  [{role}]" if role else ""
            header = QTreeWidgetItem([f"{node_name}{role_chip}  ({count} device{'s' if count != 1 else ''})", "", "", ""])
            header.setFont(0, bold)
            header.setForeground(0, QColor(ACCENT if role == "master" else TEXT_PRIMARY))
            header.setExpanded(True)

            for c in node_clients:
                header.addChild(_make_client_item(c))

            self._r_tree.addTopLevelItem(header)

        if unassigned:
            ua = QTreeWidgetItem([f"Unassigned  ({len(unassigned)})", "", "", ""])
            ua.setFont(0, bold)
            ua.setForeground(0, QColor(TEXT_MUTED))
            ua.setExpanded(True)
            for c in unassigned:
                ua.addChild(_make_client_item(c))
            self._r_tree.addTopLevelItem(ua)

        self._r_tree.resizeColumnToContents(0)
        self._r_tree.resizeColumnToContents(1)
        self._r_tree.resizeColumnToContents(2)

    def _fill_generic(self, status: dict) -> None:
        for key, lbl in self._g_rows.items():
            lbl.setText(_fmt(status.get(key)))

    def mark_unavailable(self) -> None:
        """Grey the page out when the plugin file is missing."""
        self._show_banner(
            f"Plugin file not found — re-import it from the Hardware page:\n{self._path}",
            AMBER,
        )
