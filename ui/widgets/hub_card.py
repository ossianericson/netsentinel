"""
hub_card.py — HubCard widget, panel classes, and helper functions.

Extracted from ui/pages/hardware_integration_page.py (Sprint 4, S3-1).
HardwareIntegrationPage is defined in hardware_integration_page.py and imports from here.
"""
from __future__ import annotations

import collections
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import QProcess

from ui import styles as _s
from ui.styles import (
    alpha,
    BLACK, CARD_RADIUS,
)

from ui.widgets.hub_helpers import (
    _CIRCUIT_BREAK_THRESHOLD, _DEGRADED_HOURS,
    _find_python_exe, _path_hash, _load_health, _reset_health,
    _load_instance_config, _save_instance_config,
    _safe_set_text, _age_str, _rsrp_color, _sinr_color,
    _classify_error,
    # Backwards-compatible re-exports — consumed by hardware_integration_page.py,
    # hardware_browse_mixin.py, plugin_guide.py, plugin_wizard_mixin.py, credential_dialog.py
    _TEMPLATE,  # noqa: F401
    _instance_id, _validate_script,  # noqa: F401
    _load_paths, _save_paths,  # noqa: F401
    _load_instances, _save_instances,  # noqa: F401
    _is_consented, _record_consent,  # noqa: F401
    _migrate_stale_paths,  # noqa: F401
    _load_last_result, _save_last_result,  # noqa: F401
    _record_success, _record_error,  # noqa: F401
    _save_health,  # noqa: F401
)

# Explicit re-export list so CodeQL recognises these as intentional re-exports.
__all__ = [
    "HubCard", "PipInstallDialog",
    "_TEMPLATE", "_instance_id", "_validate_script",
    "_load_paths", "_save_paths",
    "_load_instances", "_save_instances",
    "_is_consented", "_record_consent",
    "_migrate_stale_paths",
    "_load_last_result", "_save_last_result",
    "_record_success", "_record_error",
    "_save_health",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _btn(label: str, accent: bool = False) -> QPushButton:
    b = QPushButton(label)
    b.setFixedHeight(26)
    b.setFont(QFont("Segoe UI", 9))
    if accent:
        _s.themed_ss(b, "QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            " border-radius:3px; padding:0 12px; }}"
            "QPushButton:hover {{ background:{ACCENT_LITE}; }}"
            "QPushButton:pressed {{ background:{ACCENT_DARK}; }}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}")
    else:
        _s.themed_ss(b, "QPushButton {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            " border:1px solid {BORDER}; border-radius:3px; padding:0 10px; }}"
            "QPushButton:hover {{ background:{BG_HOVER}; }}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}")
    return b


# ── P3-4 Community index background threads ───────────────────────────────────

class _CommunityIndexThread(QThread):
    """Fetch community plugin index JSON in a background thread."""

    done  = pyqtSignal(list)   # list of plugin dicts
    error = pyqtSignal(str)

    def __init__(self, url: str, parent=None) -> None:
        super().__init__(parent)
        self._url = url

    def run(self) -> None:
        try:
            import urllib.request
            with urllib.request.urlopen(self._url, timeout=15) as resp:  # noqa: S310
                data = resp.read().decode("utf-8", errors="replace")
            import json as _json
            entries = _json.loads(data)
            if not isinstance(entries, list):
                self.error.emit("Index is not a JSON array")
                return
            self.done.emit(entries)
        except Exception as exc:
            self.error.emit(str(exc))


class _CommunityDownloadThread(QThread):
    """Download a community plugin file, verify SHA-256, save to AppData/plugins/."""

    done  = pyqtSignal(str)    # path to saved .py file
    error = pyqtSignal(str)

    def __init__(self, url: str, expected_sha256: str, plugin_name: str, parent=None) -> None:
        super().__init__(parent)
        self._url      = url
        self._expected = expected_sha256
        self._name     = plugin_name

    def run(self) -> None:
        try:
            import urllib.request
            import hashlib as _hl
            import re
            from modules.utils import get_app_data_dir

            with urllib.request.urlopen(self._url, timeout=30) as resp:  # noqa: S310
                data = resp.read()

            if self._expected:
                actual = _hl.sha256(data).hexdigest()
                if actual != self._expected:
                    self.error.emit(
                        f"SHA-256 mismatch for '{self._name}' — "
                        f"expected {self._expected[:16]}… got {actual[:16]}…"
                    )
                    return

            safe = re.sub(r"[^a-zA-Z0-9_]", "_", self._name.lower()).strip("_") or "plugin"
            dest_dir = get_app_data_dir() / "plugins"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f"{safe}.py"
            dest.write_bytes(data)
            self.done.emit(str(dest))
        except Exception as exc:
            self.error.emit(str(exc))


# ── Signal detail panel (modem) ───────────────────────────────────────────────

class _ModemDetailPanel(QFrame):
    """Two-column signal grid: 5G NR | LTE Primary."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("modemDetailPanel")
        _s.themed_ss(self, "QFrame#modemDetailPanel {{ background:{BG_DARK}; border:none;"
            " border-top:1px solid {BORDER}; }}")
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._nr_col  = self._make_col("5G NR",       _s.ACCENT, border_right=True)
        self._lte_col = self._make_col("LTE Primary",  _s.AMBER,  border_right=False)
        root.addWidget(self._nr_col[0], 1)
        root.addWidget(self._lte_col[0], 1)

        _ls = f"color:{_s.TEXT_SECONDARY}; font-size:10px; border:none; background:transparent;"
        _vs = f"color:{_s.TEXT_PRIMARY}; font-size:10px; font-weight:bold; border:none; background:transparent;"

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
        _s.themed_ss(conn, "background:{BG_DARK}; border:none; border-bottom:1px solid {BORDER};")
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
            _s.themed_ss(sep, "border:none; border-left:1px solid {BORDER}; margin:0 12px;")
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
        _s.themed_ss(body, "background:{BG_DARK}; border:none;")
        body.setLayout(root)
        outer.addWidget(body)

        self.setLayout(outer)

    def _make_col(self, title: str, color: str, border_right: bool):
        col = QFrame()
        border = f"border-right:1px solid {_s.BORDER};" if border_right else ""
        _s.themed_ss(col, lambda border=border: f"background:{_s.BG_DARK}; border:none; {border}")
        lay = QVBoxLayout(col)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)
        t = QLabel(title)
        _s.themed_ss(t, lambda color=color: f"color:{color}; font-size:10px; font-weight:bold; border:none;"
            f" border-bottom:1px solid {_s.BORDER}; background:transparent;"
            f" padding-bottom:3px; margin-bottom:2px;")
        lay.addWidget(t)
        return col, lay

    def update(self, extra: dict, status: dict | None = None) -> None:
        # wan_ip lives at status top-level in most plugins, not inside extra
        merged = {**(status or {}), **extra}
        def _txt(v): return str(v) if v is not None else "—"
        def _dbm(v): return f"{float(v):.1f} dBm" if v is not None else "—"
        def _db(v):  return f"{float(v):.1f} dB"  if v is not None else "—"

        self._nr_band.setText(_txt(merged.get("nr5g_band")))
        nr_rsrp = merged.get("nr5g_rsrp_dbm")
        self._nr_rsrp.setText(_dbm(nr_rsrp))
        _s.themed_ss(self._nr_rsrp, lambda _rsrp_color=_rsrp_color, nr_rsrp=nr_rsrp: f"color:{_rsrp_color(nr_rsrp)}; font-size:10px; font-weight:bold;"
            f" border:none; background:transparent;")
        nr_sinr = merged.get("nr5g_sinr_db")
        self._nr_sinr.setText(_db(nr_sinr))
        _s.themed_ss(self._nr_sinr, lambda _sinr_color=_sinr_color, nr_sinr=nr_sinr: f"color:{_sinr_color(nr_sinr)}; font-size:10px; font-weight:bold;"
            f" border:none; background:transparent;")
        self._nr_rsrq.setText(_db(merged.get("nr5g_rsrq_db")))
        self._nr_pci.setText(_txt(merged.get("nr5g_pci")))
        self._nr_arfcn.setText(_txt(merged.get("nr5g_arfcn")))

        lte_rsrp = merged.get("lte_rsrp_dbm")
        self._lte_band.setText(_txt(merged.get("lte_band")))
        self._lte_rsrp.setText(_dbm(lte_rsrp))
        _s.themed_ss(self._lte_rsrp, lambda _rsrp_color=_rsrp_color, lte_rsrp=lte_rsrp: f"color:{_rsrp_color(lte_rsrp)}; font-size:10px; font-weight:bold;"
            f" border:none; background:transparent;")
        lte_snr = merged.get("lte_snr_db")
        self._lte_snr.setText(_db(lte_snr))
        _s.themed_ss(self._lte_snr, lambda _sinr_color=_sinr_color, lte_snr=lte_snr: f"color:{_sinr_color(lte_snr)}; font-size:10px; font-weight:bold;"
            f" border:none; background:transparent;")
        self._lte_rsrq.setText(_db(merged.get("lte_rsrq_db")))
        self._lte_pci.setText(_txt(merged.get("lte_pci")))
        self._lte_earfcn.setText(_txt(merged.get("lte_earfcn")))

        mcc, mnc = merged.get("mcc"), merged.get("mnc")
        self._conn_op.setText(f"{mcc}-{mnc}" if mcc and mnc else "—")
        cell = merged.get("cell_id")
        enb  = merged.get("enb_id")
        self._conn_cell.setText(
            f"{cell} (eNB: {enb})" if cell and enb else _txt(cell)
        )
        self._conn_ip.setText(_txt(merged.get("wan_ip")))


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

    # themed_ss templates — {TOKEN} placeholders resolved live (drop-'f' shape C1)
    _TABLE_SS = (
        "QTableWidget {{ border:none; font-size:10px; color:{TEXT_PRIMARY}; }}"
        "QHeaderView::section {{"
        "  background:{TH_BG}; color:{TH_TEXT}; font-size:10px;"
        "  font-weight:bold; padding:3px 5px; border:none;"
        "  border-right:1px solid {TH_BORDER};"
        "}}"
        "QTableWidget::item:selected {{ background:{TABLE_SEL}; color:{TEXT_PRIMARY}; }}"
        "QTableWidget::item:alternate {{ background:{BG_ALT_ROW}; }}"
        "QTableWidget::item {{ border-bottom:1px solid {TABLE_ROW_BORDER}; }}"
    )
    _TREE_SS = (
        "QTreeWidget {{ border:none; font-size:10px; color:{TEXT_PRIMARY};"
        "  background:{BG_DARK}; alternate-background-color:{BG_ALT_ROW}; }}"
        "QTreeWidget::item {{ border-bottom:1px solid {TABLE_ROW_BORDER};"
        "  padding:2px 0; }}"
        "QTreeWidget::item:selected {{ background:{TABLE_SEL}; color:{TEXT_PRIMARY}; }}"
        "QHeaderView::section {{"
        "  background:{TH_BG}; color:{TH_TEXT}; font-size:10px;"
        "  font-weight:bold; padding:3px 5px; border:none;"
        "  border-right:1px solid {TH_BORDER};"
        "}}"
        "QTreeWidget::branch:has-children:!has-siblings:closed,"
        "QTreeWidget::branch:closed:has-children:has-siblings {{"
        "  image: none; border-image: none; }}"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._view_mode = "flat"
        self._last_clients: list = []
        self._last_nodes: list = []

        self.setObjectName("routerDetailPanel")
        _s.themed_ss(self, "QFrame#routerDetailPanel {{ background:{BG_DARK}; border:none;"
            " border-top:1px solid {BORDER}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 10)
        lay.setSpacing(8)

        # ── Mesh nodes ────────────────────────────────────────────────────────
        nodes_hdr = QLabel("MESH NODES")
        _s.themed_ss(nodes_hdr, "color:{ACCENT}; font-size:9px; font-weight:bold; border:none;"
            " background:transparent; letter-spacing:0.5px;")
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
        _s.themed_ss(self._node_table, self._TABLE_SS)
        lay.addWidget(self._node_table)

        # ── Connected clients header ──────────────────────────────────────────
        cli_hdr_row = QHBoxLayout()
        cli_hdr_row.setContentsMargins(0, 4, 0, 0)
        clients_hdr = QLabel("CONNECTED CLIENTS")
        _s.themed_ss(clients_hdr, "color:{AMBER}; font-size:9px; font-weight:bold; border:none;"
            " background:transparent; letter-spacing:0.5px;")
        self._client_count_lbl = QLabel("")
        _s.themed_ss(self._client_count_lbl, "color:{TEXT_MUTED}; font-size:9px; border:none; background:transparent;")
        self._toggle_btn = QPushButton("Group by node")
        self._toggle_btn.setFixedHeight(20)
        _s.themed_ss(self._toggle_btn, lambda BLACK=BLACK: f"QPushButton {{ background:{_s.BG_DARK}; color:{_s.TEXT_MUTED}; border:1px solid {_s.BORDER};"
            f"  border-radius:3px; font-size:9px; padding:0 6px; }}"
            f"QPushButton:hover {{ color:{_s.TEXT_PRIMARY}; border-color:{_s.ACCENT}; }}"
            f"QPushButton:checked {{ background:{_s.ACCENT}; color:{BLACK}; border-color:{_s.ACCENT}; }}"
            f"QPushButton:pressed {{ color:{_s.TEXT_PRIMARY}; }}")
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
        _s.themed_ss(self._client_table, self._TABLE_SS)
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
        _s.themed_ss(self._tree_widget, self._TREE_SS)
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
                role_item.setForeground(QColor(_s.GREEN))
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
                band_item.setForeground(QColor(_s.ACCENT))
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
            header.setForeground(0, QColor(_s.ACCENT if role == "master" else _s.TEXT_MUTED))
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
                    child.setForeground(2, QColor(_s.ACCENT))
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


# ── Plugin connection tester (live-test before registration) ─────────────────

class _PluginConnectionTester(QThread):
    """Runs get_info() + get_status() in a background thread with temporary credentials.

    Emits success(dict) if both calls return without error, or failure(str) with
    a human-readable message.  The caller is responsible for persisting the
    credential to keyring ONLY on success.
    """

    success = pyqtSignal(dict)  # {"info": ..., "status": ...}
    failure = pyqtSignal(str)   # plain-English error message

    def __init__(self, path: str, ip: str, pw: str, parent=None) -> None:
        super().__init__(parent)
        self._path = path
        self._ip   = ip
        self._pw   = pw

    def run(self) -> None:
        import importlib.util
        import os as _os

        # Temporarily save credential so the plugin can read it via keyring.
        try:
            import keyring as _kr
            _kr.set_password("NetSentinel/hardware", self._ip, self._pw)
        except Exception:
            pass  # keyring unavailable — plugin reads from its own field

        # Legacy env-var shim: set NETSENTINEL_PLUGIN_IP so older plugins that
        # haven't adopted _NETSENTINEL_INSTANCE_IP still work.  We save/restore
        # so concurrent testers don't pollute each other's IP (RULE-PL1).
        _prev_ip = _os.environ.get("NETSENTINEL_PLUGIN_IP")
        _os.environ["NETSENTINEL_PLUGIN_IP"] = self._ip

        try:
            if not Path(self._path).exists():
                self.failure.emit(f"Plugin file not found: {self._path}")
                return

            # Ensure NetSentinel modules are importable
            _ns_root = next(
                (p for p in __import__("sys").path
                 if p and Path(p, "modules", "utils.py").exists()),
                str(Path(__file__).parent.parent.parent),
            )
            import sys as _sys
            if _ns_root not in _sys.path:
                _sys.path.insert(0, _ns_root)

            spec = importlib.util.spec_from_file_location(
                f"_ns_test_{Path(self._path).stem}", self._path
            )
            if spec is None or spec.loader is None:
                self.failure.emit("Cannot load plugin file.")
                return

            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]

            # Inject IP directly into the module namespace (RULE-PL1).
            # This takes precedence over the env-var shim above.
            mod._NETSENTINEL_INSTANCE_IP = self._ip
            mod._NETSENTINEL_INSTANCE_ID = ""  # no stable ID yet at test time

            get_info   = getattr(mod, "get_info",   None)
            get_status = getattr(mod, "get_status", None)

            if not callable(get_info) or not callable(get_status):
                self.failure.emit("Plugin is missing get_info() or get_status().")
                return

            info   = get_info()
            status = get_status()

            # Treat an error inside extra as a failure so the user can fix it now
            err = (status.get("extra") or {}).get("error", "")
            if err:
                self.failure.emit(_classify_error(str(err)))
                return

            self.success.emit({"info": info, "status": status})

        except SystemExit:
            self.failure.emit("Plugin called sys.exit() unexpectedly.")
        except Exception as exc:
            self.failure.emit(_classify_error(str(exc)))
        finally:
            # Always restore the env var to its pre-test value (RULE-PL1).
            if _prev_ip is None:
                _os.environ.pop("NETSENTINEL_PLUGIN_IP", None)
            else:
                _os.environ["NETSENTINEL_PLUGIN_IP"] = _prev_ip


# ── Pip install dialog ────────────────────────────────────────────────────────

class PipInstallDialog(QDialog):
    """Runs `pip install <package>` in a QProcess and streams output to a log.

    Usage:
        dlg = PipInstallDialog("fritzconnection", parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # library is now installed
    """

    def __init__(self, package: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._package = package
        self._success = False
        self.setWindowTitle(f"Install {package}")
        self.setMinimumWidth(520)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        hdr = QLabel(f"Installing <b>{package}</b> via pip…")
        _s.themed_ss(hdr, "color:{TEXT_PRIMARY}; font-size:14px;")
        lay.addWidget(hdr)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(200)
        _s.themed_ss(self._log, "background:{BG_DARK}; color:{TEXT_SECONDARY}; "
            "font-family:monospace; font-size:12px; border:none;")
        lay.addWidget(self._log)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)  # indeterminate
        self._bar.setTextVisible(False)
        lay.addWidget(self._bar)

        btn_row = QHBoxLayout()
        self._btn_close = QPushButton("Cancel")
        self._btn_close.setFixedHeight(32)
        self._btn_close.clicked.connect(self._on_cancel)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_close)
        lay.addLayout(btn_row)

        self._proc = QProcess(self)
        self._proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._proc.readyReadStandardOutput.connect(self._on_output)
        self._proc.finished.connect(self._on_finished)

        python = _find_python_exe()
        self._proc.start(python, ["-m", "pip", "install", "--upgrade", package])

    def _on_output(self) -> None:
        from PyQt6.QtGui import QTextCursor
        data = bytes(self._proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._log.moveCursor(QTextCursor.MoveOperation.End)
        self._log.insertPlainText(data)
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_finished(self, exit_code: int, _status) -> None:
        self._bar.setRange(0, 1)
        self._bar.setValue(1)
        if exit_code == 0:
            self._success = True
            self._log.append(f"\n✓  {self._package} installed successfully.")
            self._btn_close.setText("Done")
            self._btn_close.clicked.disconnect()
            self._btn_close.clicked.connect(self.accept)
        else:
            self._log.append(f"\n✗  pip exited with code {exit_code}.")
            self._btn_close.setText("Close")

    def _on_cancel(self) -> None:
        if self._proc.state() != QProcess.ProcessState.NotRunning:
            self._proc.kill()
        self.reject()


# ── Hub card ──────────────────────────────────────────────────────────────────

class HubCard(QFrame):
    """Live status card for one imported hardware plugin."""

    refresh_clicked         = pyqtSignal(str)   # path
    remove_clicked          = pyqtSignal(str)   # path
    stop_clicked            = pyqtSignal(str)   # path — stop polling worker
    reenable_clicked        = pyqtSignal(str)   # path — re-enable after circuit break
    install_completed       = pyqtSignal(str)   # path — pip install succeeded, reload worker
    add_another             = pyqtSignal(str)   # path — add a second instance of this plugin
    update_credentials_clicked = pyqtSignal(str)  # instance_id — open credential dialog
    reimport_clicked        = pyqtSignal(str)   # path — plugin file not found, browse for new
    rename_requested        = pyqtSignal(str, str, str)  # (instance_id, old_name, new_name)

    def __init__(self, path: str, meta: dict, last_result: Optional[dict],
                 instance_id: str = "", display_name: str = "",
                 instance_ip: str = "", parent=None):
        super().__init__(parent)
        self._path          = path
        self._meta          = meta
        self._instance_id   = instance_id or _path_hash(path)[:12]
        self._instance_ip   = instance_ip or meta.get("ip", "")
        self._pending_pkg   = ""   # pypi package to install when dep error shown
        self._last_ts    = last_result.get("_ts", 0.0) if isinstance(last_result, dict) else 0.0
        self._hw_type    = meta.get("type", "unknown")
        self._detail_visible = False
        # Use custom display name if provided (for multi-instance)
        if display_name:
            meta = dict(meta)
            meta["name"] = display_name

        self.setObjectName("hubCard")
        _s.themed_ss(self, lambda CARD_RADIUS=CARD_RADIUS: f"QFrame#hubCard {{ background:{_s.BG_CARD}; border:1px solid {_s.BORDER};"
            f" border-radius:{CARD_RADIUS}; }}")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header row ────────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setObjectName("hubCardHdr")
        _s.themed_ss(hdr, lambda CARD_RADIUS=CARD_RADIUS: f"QFrame#hubCardHdr {{ background:{_s.BG_CARD}; border:none;"
            f" border-radius:{CARD_RADIUS}; }}")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(12, 8, 10, 8)
        hdr_lay.setSpacing(8)

        # Status dot — clickable to expand/collapse detail
        self._dot = QLabel("●")
        _s.themed_ss(self._dot, "color:{TEXT_MUTED}; font-size:13px; border:none;")
        self._dot.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dot.setToolTip("Click to expand / collapse detail")
        self._dot.mousePressEvent = lambda _: self._toggle_detail()
        hdr_lay.addWidget(self._dot)

        # Plugin icon (P2-3) — 24×24 QPixmap if icon.png found alongside script
        icon_path = meta.get("icon_path", "")
        if icon_path:
            try:
                px = QPixmap(icon_path).scaled(
                    24, 24,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                if not px.isNull():
                    icon_lbl = QLabel()
                    icon_lbl.setPixmap(px)
                    icon_lbl.setFixedSize(26, 26)
                    icon_lbl.setStyleSheet("border:none; background:transparent;")
                    hdr_lay.addWidget(icon_lbl)
            except Exception:
                pass  # icon load failure is non-critical

        # Name + type badge
        name_col = QVBoxLayout()
        name_col.setSpacing(1)
        name_col.setContentsMargins(0, 0, 0, 0)
        self._name_lbl = QLabel(f"<b>{meta.get('name', Path(path).stem)}</b>")
        self._name_lbl.setTextFormat(Qt.TextFormat.RichText)
        _s.themed_ss(self._name_lbl, "color:{TEXT_PRIMARY}; font-size:12px; border:none; background:transparent;")
        hw_type = meta.get("type", "")
        hw_ip   = self._instance_ip or meta.get("ip", "")
        sub_txt = "  ·  ".join(filter(None, [hw_type, hw_ip]))
        self._sub_lbl = QLabel(sub_txt)
        _s.themed_ss(self._sub_lbl, "color:{TEXT_MUTED}; font-size:9px; border:none; background:transparent;")
        name_col.addWidget(self._name_lbl)
        name_col.addWidget(self._sub_lbl)
        hdr_lay.addLayout(name_col)

        # Metrics summary (centre)
        self._metrics_lbl = QLabel("Never run")
        _s.themed_ss(self._metrics_lbl, "color:{TEXT_MUTED}; font-size:10px; border:none; background:transparent;")
        hdr_lay.addWidget(self._metrics_lbl, 1)

        # Timestamp
        self._ts_lbl = QLabel("")
        _s.themed_ss(self._ts_lbl, "color:{TEXT_MUTED}; font-size:9px; border:none; background:transparent;")
        hdr_lay.addWidget(self._ts_lbl)

        # Health counter — "42/45 ✓" shown in small muted text
        self._health_lbl = QLabel("")
        _s.themed_ss(self._health_lbl, "color:{TEXT_MUTED}; font-size:9px; border:none; background:transparent;")
        self._health_lbl.setVisible(False)
        hdr_lay.addWidget(self._health_lbl)

        # Install dependency button — hidden until a dep error is detected
        self._btn_install = _btn("⬇ Install dependency", accent=True)
        self._btn_install.setFixedHeight(26)
        self._btn_install.setToolTip("Install the missing Python library via pip")
        self._btn_install.setVisible(False)
        self._btn_install.clicked.connect(self._on_install_dep)
        hdr_lay.addWidget(self._btn_install)

        # Re-enable button — shown after circuit breaker fires
        self._btn_reenable = _btn("↺ Re-enable")
        self._btn_reenable.setFixedHeight(26)
        self._btn_reenable.setToolTip("Reset error counter and resume polling")
        self._btn_reenable.setVisible(False)
        self._btn_reenable.clicked.connect(self._on_reenable)
        hdr_lay.addWidget(self._btn_reenable)

        # Update credentials button — shown when an AUTH: error is detected (P4-1)
        self._btn_update_cred = _btn("🔑 Re-enter Password")
        self._btn_update_cred.setFixedHeight(26)
        self._btn_update_cred.setToolTip(
            "Authentication failed — click to update the saved password"
        )
        self._btn_update_cred.setVisible(False)
        self._btn_update_cred.clicked.connect(
            lambda: self.update_credentials_clicked.emit(self._instance_id)
        )
        hdr_lay.addWidget(self._btn_update_cred)

        # Re-import button — shown when FILE: error indicates plugin file is gone (P6-2)
        self._btn_reimport = _btn("⤵ Re-import")
        self._btn_reimport.setFixedHeight(26)
        self._btn_reimport.setToolTip(
            "Plugin file was moved or deleted — browse to locate it again"
        )
        self._btn_reimport.setVisible(False)
        self._btn_reimport.clicked.connect(
            lambda: self.reimport_clicked.emit(self._path)
        )
        hdr_lay.addWidget(self._btn_reimport)

        # Refresh button
        self._btn_refresh = _btn("↻")
        self._btn_refresh.setFixedWidth(28)
        self._btn_refresh.setToolTip("Refresh now")
        self._btn_refresh.clicked.connect(lambda: self.refresh_clicked.emit(self._path))
        hdr_lay.addWidget(self._btn_refresh)

        # Stop polling button
        self._btn_stop = _btn("■")
        self._btn_stop.setFixedWidth(28)
        self._btn_stop.setToolTip("Stop polling (disconnect)")
        self._btn_stop.clicked.connect(lambda: self.stop_clicked.emit(self._path))
        hdr_lay.addWidget(self._btn_stop)

        # Add Another Instance button
        btn_add_another = _btn("＋")
        btn_add_another.setFixedWidth(28)
        btn_add_another.setToolTip("Add another instance of this plugin (different device / IP)")
        btn_add_another.clicked.connect(lambda: self.add_another.emit(self._path))
        hdr_lay.addWidget(btn_add_another)

        # Log console toggle button (P3-3)
        self._btn_logs = QPushButton("≡")
        self._btn_logs.setFixedSize(28, 26)
        self._btn_logs.setCheckable(True)
        self._btn_logs.setToolTip("Show / hide plugin log")
        self._btn_logs.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._btn_logs, lambda alpha=alpha: f"QPushButton {{ background:{_s.BG_CARD}; color:{_s.TEXT_PRIMARY};"
            f" border:1px solid {_s.BORDER}; border-radius:3px; }}"
            f"QPushButton:hover {{ background:{_s.BG_HOVER}; color:{_s.TEXT_PRIMARY}; }}"
            f"QPushButton:checked {{ background:{alpha(_s.ACCENT, 0x22)}; border-color:{_s.ACCENT}; color:{_s.TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{_s.BG_HOVER}; color:{_s.TEXT_PRIMARY}; }}")
        self._btn_logs.toggled.connect(self._toggle_logs)
        hdr_lay.addWidget(self._btn_logs)

        # Configure button (P2-2) — only shown when plugin declares CONFIG_SCHEMA
        self._config_schema: dict = meta.get("config_schema", {}) or {}
        self._btn_configure = QPushButton("⚙")
        self._btn_configure.setFixedSize(28, 26)
        self._btn_configure.setCheckable(True)
        self._btn_configure.setToolTip("Configure plugin settings")
        self._btn_configure.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._btn_configure, lambda alpha=alpha: f"QPushButton {{ background:{_s.BG_CARD}; color:{_s.TEXT_PRIMARY};"
            f" border:1px solid {_s.BORDER}; border-radius:3px; }}"
            f"QPushButton:hover {{ background:{_s.BG_HOVER}; color:{_s.TEXT_PRIMARY}; }}"
            f"QPushButton:checked {{ background:{alpha(_s.ACCENT, 0x22)}; border-color:{_s.ACCENT}; color:{_s.TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{_s.BG_HOVER}; color:{_s.TEXT_PRIMARY}; }}")
        self._btn_configure.toggled.connect(self._toggle_config_panel)
        hdr_lay.addWidget(self._btn_configure)
        self._btn_configure.setVisible(bool(self._config_schema))

        # Rename button — inline display-name edit (P3-4)
        btn_rename = _btn("✎")
        btn_rename.setFixedWidth(28)
        btn_rename.setToolTip("Rename this plugin instance")
        btn_rename.clicked.connect(self._on_rename_btn)
        hdr_lay.addWidget(btn_rename)

        # Remove button
        btn_remove = _btn("✕")
        btn_remove.setFixedWidth(28)
        btn_remove.setToolTip("Remove this instance")
        btn_remove.clicked.connect(lambda: self.remove_clicked.emit(self._path))
        hdr_lay.addWidget(btn_remove)

        outer.addWidget(hdr)

        # ── Password row ──────────────────────────────────────────────────────
        pw_row = QFrame()
        pw_row.setObjectName("hubCardPwRow")
        _s.themed_ss(pw_row, "QFrame#hubCardPwRow {{ background:{BG_CARD}; border:none;"
            " border-top:1px solid {BORDER}; border-radius:0px; }}")
        pw_lay = QHBoxLayout(pw_row)
        pw_lay.setContentsMargins(40, 4, 10, 4)
        pw_lay.setSpacing(6)

        hw_ip_for_pw = meta.get("ip", "")
        pw_lbl = QLabel(f"Password ({hw_ip_for_pw or 'IP unknown'}):")
        _s.themed_ss(pw_lbl, "color:{TEXT_MUTED}; font-size:9px; border:none;")
        pw_lay.addWidget(pw_lbl)

        self._pw_edit = QLineEdit()
        self._pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_edit.setPlaceholderText("enter password…")
        self._pw_edit.setFixedHeight(20)
        self._pw_edit.setFont(QFont("Segoe UI", 9))
        _s.themed_ss(self._pw_edit, "QLineEdit {{ background:{BG_DARK}; color:{TEXT_PRIMARY};"
            " border:1px solid {BORDER}; border-radius:3px; padding:0 6px; }}")
        pw_lay.addWidget(self._pw_edit, 1)

        self._pw_status = QLabel("")
        _s.themed_ss(self._pw_status, "color:{GREEN}; font-size:9px; border:none;")
        self._pw_status.setFixedWidth(60)
        pw_lay.addWidget(self._pw_status)

        btn_pw_save = _btn("Save")
        btn_pw_save.setToolTip("Save password in OS keychain")
        btn_pw_save.clicked.connect(
            lambda: self._save_password(hw_ip_for_pw, self._pw_edit, self._pw_status)
        )
        pw_lay.addWidget(btn_pw_save)

        btn_pw_forget = _btn("Forget")
        btn_pw_forget.setToolTip("Remove saved password from OS keychain")
        btn_pw_forget.clicked.connect(
            lambda: self._forget_password(hw_ip_for_pw, self._pw_status)
        )
        pw_lay.addWidget(btn_pw_forget)
        outer.addWidget(pw_row)

        # Security note — reassure user password is not stored in plain text
        _sec_lbl = QLabel("🔒  Saved securely in the OS keychain — never written to disk or this file")
        _s.themed_ss(_sec_lbl, "color:{TEXT_MUTED}; font-size:9px; background:transparent; border:none;"
            " padding:0 0 2px 40px;")
        outer.addWidget(_sec_lbl)

        # ── Detail panel (v2.1) ───────────────────────────────────────────────
        if self._hw_type == "modem":
            self._detail = _ModemDetailPanel()
        else:
            self._detail = _RouterDetailPanel()
        self._detail.setVisible(False)
        outer.addWidget(self._detail)

        # Log console panel (P3-3) — collapsible, hidden by default
        self._log_lines: collections.deque = collections.deque(maxlen=100)
        self._log_panel = QTextEdit()
        self._log_panel.setReadOnly(True)
        self._log_panel.setMaximumHeight(130)
        self._log_panel.setFont(QFont("Consolas", 8))
        _s.themed_ss(self._log_panel, "QTextEdit {{ background:{BG_DARK}; color:{TEXT_SECONDARY}; border:none;"
            " border-top:1px solid {BORDER}; font-family:Consolas,monospace; }}")
        self._log_panel.setVisible(False)
        outer.addWidget(self._log_panel)

        # Config panel (P2-2) — auto-generated from CONFIG_SCHEMA, hidden by default
        self._config_panel: Optional[QFrame] = None
        self._config_fields: dict = {}   # key → widget
        if self._config_schema:
            self._config_panel = self._build_config_panel(self._config_schema)
            self._config_panel.setVisible(False)
            outer.addWidget(self._config_panel)

        # Apply persisted result immediately if available
        if isinstance(last_result, dict):
            self._apply_result(last_result)

        # Apply persisted health state (circuit-breaker may already be tripped)
        self.refresh_health_ui()

    # ── Public interface ──────────────────────────────────────────────────────

    def update_result(self, data: dict, ts: float) -> None:
        self._last_ts = ts
        self._apply_result(data)

    def set_error(self, msg: str) -> None:
        import re as _re
        _s.themed_ss(self._dot, "color:{RED}; font-size:13px; border:none;")
        m = _re.search(r"pip install\s+(\S+)", msg)
        if m:
            self._pending_pkg = m.group(1)
            self._metrics_lbl.setText(f"Missing library: {self._pending_pkg}")
            self._btn_install.setText(f"⬇ Install {self._pending_pkg}")
            self._btn_install.setVisible(True)
            self._btn_update_cred.setVisible(False)
            self._btn_reimport.setVisible(False)
        elif msg.startswith("Authentication failed"):
            # P4-1: auth err — credential update button shown; update creds and retry
            self._pending_pkg = ""
            self._metrics_lbl.setText("Authentication failed — update credentials and retry")
            self._btn_update_cred.setVisible(True)
            self._btn_reimport.setVisible(False)
        elif msg.startswith("Plugin file was moved or deleted"):
            # P6-2: file gone — show re-import button
            self._pending_pkg = ""
            self._metrics_lbl.setText("Plugin file not found — re-import required")
            self._btn_reimport.setVisible(True)
            self._btn_update_cred.setVisible(False)
            self._btn_install.setVisible(False)
        else:
            self._pending_pkg = ""
            short = msg[:80] if msg else "Unknown error"
            self._metrics_lbl.setText(
                f"Plugin error — {short}. Check the plugin log for details."
            )
            self._btn_update_cred.setVisible(False)
            self._btn_install.setVisible(False)
            self._btn_reimport.setVisible(False)
        _s.themed_ss(self._metrics_lbl, "color:{AMBER}; font-size:10px; border:none; background:transparent;")
        self._btn_refresh.setEnabled(True)
        self._btn_refresh.setText("↻")

    def _on_install_dep(self) -> None:
        if not self._pending_pkg:
            return
        dlg = PipInstallDialog(self._pending_pkg, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._btn_install.setVisible(False)
            self._pending_pkg = ""
            self._metrics_lbl.setText("Library installed — reloading plugin…")
            _s.themed_ss(self._metrics_lbl, "color:{GREEN}; font-size:10px; border:none; background:transparent;")
            # P1-6: signal the page to invalidate module cache and restart worker
            self.install_completed.emit(self._path)

    def set_refreshing(self, active: bool) -> None:
        self._btn_refresh.setEnabled(not active)
        self._btn_refresh.setText("…" if active else "↻")

    def tick_timestamp(self) -> None:
        if self._last_ts > 0:
            self._ts_lbl.setText(_age_str(self._last_ts))

    def refresh_health_ui(self) -> None:
        """Read persisted health state and update the dot colour + counter label."""
        import time as _t
        h = _load_health(self._path)
        total = h["success"] + h["errors"]

        if h.get("disabled"):
            self.mark_disabled()
            return

        # Circuit-breaker: degraded (amber) if no success in _DEGRADED_HOURS
        if h["success"] > 0 and h["last_ok"] > 0:
            hours_since = (_t.time() - h["last_ok"]) / 3600
            if hours_since > _DEGRADED_HOURS:
                _s.themed_ss(self._dot, "color:{AMBER}; font-size:13px; border:none;")
                self._dot.setToolTip(
                    f"Degraded — no successful poll in {int(hours_since)} h"
                )

        # Health counter label: "42/45" only after at least 3 polls
        if total >= 3:
            pct = int(100 * h["success"] / total) if total else 0
            colour = _s.GREEN if pct >= 90 else _s.AMBER if pct >= 60 else _s.RED
            self._health_lbl.setText(f"{h['success']}/{total}")
            _s.themed_ss(self._health_lbl, lambda colour=colour: f"color:{colour}; font-size:9px; border:none; background:transparent;")
            self._health_lbl.setVisible(True)
        else:
            self._health_lbl.setVisible(False)

    def mark_disabled(self) -> None:
        """Show the circuit-breaker 'Auto-disabled' state with a Re-enable button."""
        h = _load_health(self._path)
        _s.themed_ss(self._dot, "color:{RED}; font-size:13px; border:none;")
        self._metrics_lbl.setText(
            f"Auto-disabled after {h.get('consecutive', _CIRCUIT_BREAK_THRESHOLD)} errors"
        )
        _s.themed_ss(self._metrics_lbl, "color:{RED}; font-size:10px; border:none; background:transparent;")
        self._btn_refresh.setEnabled(False)
        self._btn_reenable.setVisible(True)
        self._btn_install.setVisible(False)

    def _on_reenable(self) -> None:
        _reset_health(self._path)
        self._btn_reenable.setVisible(False)
        self._btn_refresh.setEnabled(True)
        _s.themed_ss(self._dot, "color:{TEXT_MUTED}; font-size:13px; border:none;")
        self._metrics_lbl.setText("Re-enabled — waiting for next poll…")
        _s.themed_ss(self._metrics_lbl, "color:{TEXT_MUTED}; font-size:10px; border:none; background:transparent;")
        self.reenable_clicked.emit(self._path)

    # ── Private ───────────────────────────────────────────────────────────────

    def _apply_result(self, data: dict) -> None:
        if not isinstance(data, dict):
            return
        info    = data.get("info", {}) or {}
        status  = data.get("status", {}) or {}
        # Guard: QSettings round-trip can corrupt list-of-dicts to list-of-strings
        clients = [c for c in (data.get("clients") or []) if isinstance(c, dict)]
        extra   = status.get("extra", {}) or {}
        hw_type = info.get("type", self._hw_type)

        # If the plugin returned an error inside extra (e.g. missing pip package),
        # route it through set_error so the pip-install button appears if applicable.
        err_msg = extra.get("error", "")
        if err_msg:
            self.set_error(str(err_msg))
            return

        _s.themed_ss(self._dot, "color:{GREEN}; font-size:13px; border:none;")
        self._ts_lbl.setText(_age_str(self._last_ts))

        # Build metrics summary
        if hw_type == "modem":
            parts = []
            nt = extra.get("network_type")
            if nt:
                parts.append(nt)
            band = extra.get("nr5g_band") or extra.get("lte_band")
            if band:
                parts.append(band)
            rsrp = extra.get("nr5g_rsrp_dbm") or extra.get("lte_rsrp_dbm")
            if rsrp is not None:
                try:
                    parts.append(f"RSRP {float(rsrp):.0f} dBm")
                except (TypeError, ValueError):
                    pass  # non-fatal
            sinr = extra.get("nr5g_sinr_db") or extra.get("lte_snr_db")
            if sinr is not None:
                try:
                    parts.append(f"SINR {float(sinr):.1f} dB")
                except (TypeError, ValueError):
                    pass  # non-fatal
            summary = "  ·  ".join(parts) if parts else "Online"
            self._metrics_lbl.setText(summary)
            _s.themed_ss(self._metrics_lbl, "color:{TEXT_PRIMARY}; font-size:10px; border:none; background:transparent;")
            if isinstance(self._detail, _ModemDetailPanel):
                self._detail.update(extra, status)
        else:
            n_nodes  = status.get("mesh_nodes") or 0
            n_cli    = status.get("connected_clients") or len(clients)
            parts = []
            if n_nodes:
                parts.append(f"{n_nodes} node{'s' if n_nodes != 1 else ''}")
            if n_cli is not None:
                parts.append(f"{n_cli} client{'s' if n_cli != 1 else ''}")
            summary = "  ·  ".join(parts) if parts else "Online"
            self._metrics_lbl.setText(summary)
            _s.themed_ss(self._metrics_lbl, "color:{TEXT_PRIMARY}; font-size:10px; border:none; background:transparent;")
            if isinstance(self._detail, _RouterDetailPanel):
                self._detail.update(status, clients)

        self._btn_refresh.setEnabled(True)
        self._btn_refresh.setText("↻")
        self._btn_update_cred.setVisible(False)

        # Auto-expand detail on first successful result
        if not self._detail_visible:
            self._toggle_detail()

    def _toggle_detail(self) -> None:
        self._detail_visible = not self._detail_visible
        self._detail.setVisible(self._detail_visible)
        self._dot.setToolTip(
            "Click to collapse detail" if self._detail_visible else "Click to expand detail"
        )

    # ── Log console (P3-3) ────────────────────────────────────────────────────

    def append_log(self, line: str) -> None:
        """Append a structured log entry from the polling worker."""
        self._log_lines.append(line)
        try:
            self._log_panel.setPlainText("\n".join(self._log_lines))
            sb = self._log_panel.verticalScrollBar()
            sb.setValue(sb.maximum())
        except RuntimeError:
            pass  # QTextEdit deleted before the worker callback fired — safe to ignore

    def _toggle_logs(self, checked: bool) -> None:
        self._log_panel.setVisible(checked)

    # ── Config panel (P2-2) ───────────────────────────────────────────────────

    def _build_config_panel(self, schema: dict) -> QFrame:
        """Auto-generate a config form from a CONFIG_SCHEMA dict."""
        from PyQt6.QtWidgets import QFormLayout, QCheckBox, QSpinBox
        panel = QFrame()
        _s.themed_ss(panel, "QFrame {{ background:{BG_DARK}; border:none;"
            " border-top:1px solid {BORDER}; }}")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(4)

        hdr = QLabel("Plugin Configuration")
        _s.themed_ss(hdr, "color:{TEXT_SECONDARY}; font-size:9px; font-weight:bold;"
            " border:none; background:transparent;")
        lay.addWidget(hdr)

        form = QFormLayout()
        form.setSpacing(4)
        form.setContentsMargins(0, 2, 0, 2)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        saved = _load_instance_config(self._instance_id)

        _fss = (
            f"background:{_s.BG_CARD}; color:{_s.TEXT_PRIMARY}; border:1px solid {_s.BORDER};"
            " border-radius:3px; padding:2px 5px; font-size:11px;"
        )

        for key, spec in schema.items():
            if not isinstance(spec, dict):
                continue
            label = spec.get("label", key)
            typ   = spec.get("type", "str")
            default = saved.get(key, spec.get("default", ""))

            if typ == "bool":
                w = QCheckBox()
                w.setChecked(bool(default))
                w.setStyleSheet("border:none; background:transparent;")
            elif typ == "int":
                w = QSpinBox()
                w.setRange(int(spec.get("min", 0)), int(spec.get("max", 99999)))
                try:
                    w.setValue(int(default))
                except (TypeError, ValueError):
                    w.setValue(int(spec.get("default", 0)))
                w.setStyleSheet(_fss)
                w.setFixedHeight(24)
            else:
                w = QLineEdit(str(default))
                w.setStyleSheet(_fss)
                w.setFixedHeight(24)

            self._config_fields[key] = w
            form.addRow(label, w)

        lay.addLayout(form)

        btn_save = _btn("Save", accent=True)
        btn_save.setFixedHeight(24)
        btn_save.clicked.connect(self._apply_config)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_save)
        lay.addLayout(btn_row)
        return panel

    def _toggle_config_panel(self, checked: bool) -> None:
        if self._config_panel is not None:
            self._config_panel.setVisible(checked)

    def _apply_config(self) -> None:
        """Read config field values and persist them."""
        from PyQt6.QtWidgets import QCheckBox, QSpinBox
        cfg: dict = {}
        for key, w in self._config_fields.items():
            if isinstance(w, QCheckBox):
                cfg[key] = w.isChecked()
            elif isinstance(w, QSpinBox):
                cfg[key] = w.value()
            else:
                cfg[key] = w.text()
        _save_instance_config(self._instance_id, cfg)
        self._btn_configure.setChecked(False)

    def _save_password(self, hw_ip: str, pw_edit: QLineEdit, status: QLabel) -> None:
        pw = pw_edit.text().strip()
        if not pw:
            status.setText("Empty!")
            _s.themed_ss(status, "color:{AMBER}; font-size:9px;")
            return
        if not hw_ip:
            status.setText("No IP")
            _s.themed_ss(status, "color:{AMBER}; font-size:9px;")
            return
        try:
            import keyring
            keyring.set_password("NetSentinel/hardware", hw_ip, pw)
            pw_edit.clear()
            status.setText("✓ Saved")
            _s.themed_ss(status, "color:{GREEN}; font-size:9px;")
            _t = QTimer(status)
            _t.setSingleShot(True)
            _t.timeout.connect(lambda s=status: _safe_set_text(s, ""))
            _t.start(3000)
        except Exception as exc:
            status.setText("Error")
            _s.themed_ss(status, "color:{RED}; font-size:9px;")
            status.setToolTip(str(exc))

    def _forget_password(self, hw_ip: str, status: QLabel) -> None:
        if not hw_ip:
            return
        try:
            import keyring
            # Clear all services that a plugin might read credentials from
            for service in ("NetSentinel/hardware", "NetSentinel/modem", "NetSentinel/mesh"):
                try:
                    keyring.delete_password(service, hw_ip)
                except Exception:
                    pass  # non-fatal
            status.setText("Forgotten")
            _s.themed_ss(status, "color:{TEXT_MUTED}; font-size:9px;")
        except Exception:
            status.setText("Not saved")
            _s.themed_ss(status, "color:{TEXT_MUTED}; font-size:9px;")
        _t = QTimer(status)
        _t.setSingleShot(True)
        _t.timeout.connect(lambda s=status: _safe_set_text(s, ""))
        _t.start(3000)

    def _on_rename_btn(self) -> None:
        """P3-4: Inline rename — prompt for a new display name, update card and emit signal."""
        from PyQt6.QtWidgets import QInputDialog
        current_name = self._meta.get("name", Path(self._path).stem)
        new_name, ok = QInputDialog.getText(
            self, "Rename Plugin",
            "Display name:", text=current_name,
        )
        new_name = new_name.strip()
        if not ok or not new_name or new_name == current_name:
            return
        self._meta = dict(self._meta)
        self._meta["name"] = new_name
        self._name_lbl.setText(f"<b>{new_name}</b>")
        self.rename_requested.emit(self._instance_id, current_name, new_name)


# ── Step-guide helper widgets (guide section) ─────────────────────────────────

def _step_card(number: int, title: str) -> tuple[QWidget, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("hubStepCard")
    _s.themed_ss(frame, lambda CARD_RADIUS=CARD_RADIUS: f"QFrame#hubStepCard {{ background:{_s.BG_CARD}; border:1px solid {_s.BORDER};"
        f" border-radius:{CARD_RADIUS}; }}")
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    hdr = QWidget()
    _s.themed_ss(hdr, "background:{BG_CARD}; border-bottom:1px solid {CARD_HDR_BORDER};")
    hdr_lay = QHBoxLayout(hdr)
    hdr_lay.setContentsMargins(12, 8, 12, 8)
    hdr_lay.setSpacing(10)

    badge = QLabel(str(number))
    badge.setFixedSize(22, 22)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
    _s.themed_ss(badge, "background:{ACCENT}; color:{WHITE}; border-radius:11px; border:none;")
    title_lbl = QLabel(title)
    title_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
    _s.themed_ss(title_lbl, "color:{TEXT_PRIMARY}; border:none; background:transparent;")
    hdr_lay.addWidget(badge)
    hdr_lay.addWidget(title_lbl)
    hdr_lay.addStretch()
    outer.addWidget(hdr)

    body = QWidget()
    _s.themed_ss(body, "background:{BG_CARD};")
    body_lay = QVBoxLayout(body)
    body_lay.setContentsMargins(14, 10, 14, 12)
    body_lay.setSpacing(8)
    outer.addWidget(body)

    return frame, body_lay


def _para(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    _s.themed_ss(lbl, "color:{TEXT_SECONDARY}; font-size:10px;")
    return lbl


def _sub_header(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
    _s.themed_ss(lbl, "color:{TEXT_PRIMARY}; border:none;"
        " border-bottom:1px solid {BORDER}; padding-bottom:3px; margin-top:2px;")
    return lbl


def _copy_text(btn: QPushButton, text: str) -> None:
    QApplication.clipboard().setText(text)
    orig = btn.text()
    btn.setText("✓  Copied!")
    _t = QTimer(btn)
    _t.setSingleShot(True)
    _t.timeout.connect(lambda: btn.setText(orig))
    _t.start(2000)


def _code_chip(code: str) -> QWidget:
    frame = QFrame()
    _s.themed_ss(frame, "background:{BG_DARK}; border:1px solid {BORDER}; border-radius:3px;")
    row = QHBoxLayout(frame)
    row.setContentsMargins(8, 4, 6, 4)
    row.setSpacing(8)
    lbl = QLabel(code)
    lbl.setFont(QFont("Consolas", 8))
    _s.themed_ss(lbl, "color:{ACCENT}; border:none; background:transparent;")
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    copy_btn = _btn("⎘")
    copy_btn.setFixedSize(24, 20)
    copy_btn.setToolTip("Copy to clipboard")
    copy_btn.clicked.connect(lambda: _copy_text(copy_btn, code))
    row.addWidget(lbl, 1)
    row.addWidget(copy_btn)
    return frame


def _prompt_block(label: str, text: str) -> QWidget:
    frame = QFrame()
    _s.themed_ss(frame, "background:{BG_DARK}; border:1px solid {BORDER}; border-radius:4px;")
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(10, 6, 10, 8)
    outer.setSpacing(4)
    hdr = QHBoxLayout()
    hdr.setContentsMargins(0, 0, 0, 0)
    lbl_w = QLabel(label)
    lbl_w.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
    _s.themed_ss(lbl_w, "color:{AMBER}; border:none; background:transparent;")
    copy_btn = _btn("⎘  Copy prompt")
    copy_btn.setFixedHeight(20)
    copy_btn.clicked.connect(lambda: _copy_text(copy_btn, text))
    hdr.addWidget(lbl_w)
    hdr.addStretch()
    hdr.addWidget(copy_btn)
    outer.addLayout(hdr)
    body = QLabel(text)
    body.setFont(QFont("Consolas", 8))
    body.setWordWrap(True)
    _s.themed_ss(body, "color:{TEXT_SECONDARY}; font-size:9px; border:none; background:transparent;")
    body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    outer.addWidget(body)
    return frame


# ── Main page ─────────────────────────────────────────────────────────────────
