"""
HardwareIntegrationPage — Hardware Hub

Primary view: live status cards for every imported hardware plugin.
Each card auto-refreshes on a configurable interval, shows key metrics,
and expands to a full signal/topology detail panel (v2.1).

Secondary view: collapsible "How to write a plugin" guide (steps 1-4).

Plugin interface contract
─────────────────────────
  Required at module level:
    HARDWARE_NAME: str
    HARDWARE_TYPE: str   ("router" | "modem" | "ap" | "switch" | "other")
    get_info()  -> dict
    get_status() -> dict

  Optional:
    get_clients() -> list[dict]

Scripts are stored as file paths in QSettings("NetSentinel","NetSentinel")
under the key  hardware/custom_scripts.
"""

from __future__ import annotations

import ast
import hashlib
import json
import time
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QSettings, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QCursor, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import QProcess

from workers.plugin_polling_worker import PluginPollingWorker
from ui.styles import (
    ACCENT,
    ACCENT_DARK,
    ACCENT_LITE,
    AMBER,
    BG_ALT_ROW,
    BG_CARD,
    BG_DARK,
    BG_HOVER,
    BORDER,
    CARD_HDR_BORDER,
    CARD_RADIUS,
    GREEN,
    RED,
    TABLE_ROW_BORDER,
    TABLE_SEL,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TH_BG,
    TH_BORDER,
    TH_TEXT,
)

_SETTINGS_KEY    = "hardware/custom_scripts"
_SETTINGS_RESULT = "hardware/last_result/{}"  # .format(path_hash)


def _find_python_exe() -> str:
    """Return a usable Python interpreter path.

    In development sys.executable is already python.exe.  In a frozen
    (PyInstaller onefile) bundle sys.executable is the .exe itself, so we
    search PATH for python3 / python.
    """
    import sys as _sys
    if not getattr(_sys, "frozen", False):
        return _sys.executable
    import shutil
    for candidate in ("python3", "python", "py"):
        found = shutil.which(candidate)
        if found:
            return found
    return "python"

_TEMPLATE = '''\
"""
NetSentinel Hardware Integration Script
Hardware: <YOUR HARDWARE NAME>
Author:   <YOUR NAME>

Test this script standalone first:
    python this_file.py

Once the output looks correct, import it via the
Hardware Integration page in NetSentinel.

Tip: search "<your model> local API" or "<your model> REST API"
     to find community docs for your specific hardware.
"""

import json
import sys

# ── Metadata (required) ───────────────────────────────────────────────────────
HARDWARE_NAME = "My Router XYZ"     # displayed in the app
HARDWARE_TYPE = "router"            # router | modem | ap | switch | other
HARDWARE_IP   = "192.168.1.1"       # your device\'s LAN address
USERNAME      = "admin"


# ── Credentials (read from OS keychain — never hard-code passwords) ───────────

def _load_password() -> str:
    """Return the saved admin password from the OS keychain.

    Save the password once using the Hardware Integration page in NetSentinel
    (the password field shown below each imported script).
    """
    try:
        import keyring
        pw = keyring.get_password("NetSentinel/hardware", HARDWARE_IP)
        if pw:
            return pw
    except Exception:
        pass
    raise RuntimeError(
        f"No password saved for {HARDWARE_IP}. "
        "Enter and save the password in the Hardware Integration page."
    )


# ── Required interface ────────────────────────────────────────────────────────

def get_info() -> dict:
    """Static metadata — called once when the script is first imported."""
    return {
        "name":         HARDWARE_NAME,
        "type":         HARDWARE_TYPE,
        "ip":           HARDWARE_IP,
        "manufacturer": "Brand Name",
        "model":        "XYZ-1000",
        "firmware":     "v1.0.0",       # fetch from device API or hardcode
    }


def get_status() -> dict:
    """Live status — called periodically when the page is visible."""
    return {
        "wan_ip":            None,
        "uptime_sec":        None,
        "download_mbps":     None,
        "upload_mbps":       None,
        "signal_dbm":        None,
        "connected_clients": [],
        "extra":             {},
    }


# ── Optional interface ────────────────────────────────────────────────────────

def get_clients() -> list:
    return []


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__" and "--netsentinel" not in sys.argv:
    print("=== Hardware Info ===")
    print(json.dumps(get_info(), indent=2, default=str))
    print("\\n=== Live Status ===")
    print(json.dumps(get_status(), indent=2, default=str))
    print("\\n=== Clients ===")
    print(json.dumps(get_clients(), indent=2, default=str))

# ── NetSentinel plugin shim (do not remove) ───────────────────────────────────
import sys as _sys
if "--netsentinel" in _sys.argv:
    import json as _json
    try:
        _clients = get_clients()
    except NameError:
        _clients = []
    _sys.stdout.write(_json.dumps({
        "info":    get_info(),
        "status":  get_status(),
        "clients": _clients,
    }, default=str) + "\\n")
    _sys.exit(0)
'''


# ── Helpers ───────────────────────────────────────────────────────────────────

def _btn(label: str, accent: bool = False) -> QPushButton:
    b = QPushButton(label)
    b.setFixedHeight(26)
    b.setFont(QFont("Segoe UI", 9))
    if accent:
        b.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#fff; border:none;"
            f" border-radius:3px; padding:0 12px; }}"
            f"QPushButton:hover {{ background:{ACCENT_LITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; }}"
        )
    else:
        b.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:0 10px; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; }}"
        )
    return b


def _path_hash(path: str) -> str:
    return hashlib.md5(path.encode()).hexdigest()[:12]


def _validate_script(path: str) -> tuple[bool, str, dict]:
    try:
        source = Path(path).read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return False, f"Syntax error: {exc}", {}
    except Exception as exc:
        return False, str(exc), {}

    top_names: dict[str, object] = {}
    func_names: set[str] = set()

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                    top_names[target.id] = node.value.value
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_names.add(node.name)

    missing = ({"HARDWARE_NAME", "HARDWARE_TYPE", "get_info", "get_status"}
               - (set(top_names) | func_names))
    if missing:
        return False, f"Missing: {', '.join(sorted(missing))}", {}

    return True, "OK", {
        "name":             str(top_names.get("HARDWARE_NAME", Path(path).stem)),
        "type":             str(top_names.get("HARDWARE_TYPE", "unknown")),
        "ip":               str(top_names.get("HARDWARE_IP", "")),
        "description":      str(top_names.get("DESCRIPTION", "")),
        "credential_label": str(top_names.get("CREDENTIAL_LABEL", "Password")),
    }


def _load_paths() -> list[str]:
    s = QSettings("NetSentinel", "NetSentinel")
    raw = s.value(_SETTINGS_KEY, [])
    if isinstance(raw, str):
        raw = [raw]
    return [p for p in (raw or []) if p]


def _save_paths(paths: list[str]) -> None:
    QSettings("NetSentinel", "NetSentinel").setValue(_SETTINGS_KEY, paths)


def _load_last_result(path: str) -> Optional[dict]:
    s = QSettings("NetSentinel", "NetSentinel")
    raw = s.value(_SETTINGS_RESULT.format(_path_hash(path)), None)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _save_last_result(path: str, data: dict) -> None:
    s = QSettings("NetSentinel", "NetSentinel")
    try:
        s.setValue(_SETTINGS_RESULT.format(_path_hash(path)), json.dumps(data, default=str))
    except Exception:
        pass


def _age_str(ts: float) -> str:
    if ts <= 0:
        return "never"
    age = int(time.time() - ts)
    if age < 60:
        return "just now"
    if age < 3600:
        return f"{age // 60} min ago"
    if age < 86400:
        return f"{age // 3600} h ago"
    return f"{age // 86400} d ago"


def _rsrp_color(v) -> str:
    if v is None:
        return TEXT_MUTED
    try:
        f = float(v)
    except (TypeError, ValueError):
        return TEXT_MUTED
    if f >= -80:
        return GREEN
    if f >= -100:
        return AMBER
    return RED


def _sinr_color(v) -> str:
    if v is None:
        return TEXT_MUTED
    try:
        f = float(v)
    except (TypeError, ValueError):
        return TEXT_MUTED
    if f >= 13:
        return GREEN
    if f >= 5:
        return AMBER
    return RED


# ── Signal detail panel (modem) ───────────────────────────────────────────────

class _ModemDetailPanel(QFrame):
    """Two-column signal grid: 5G NR | LTE Primary."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background:{BG_DARK}; border:none;"
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
            f"QFrame {{ background:{BG_DARK}; border:none; border-bottom:1px solid {BORDER}; }}"
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
        body.setStyleSheet(f"QFrame {{ background:{BG_DARK}; border:none; }}")
        body.setLayout(root)
        outer.addWidget(body)

        self.setLayout(outer)

    def _make_col(self, title: str, color: str, border_right: bool):
        col = QFrame()
        border = f"border-right:1px solid {BORDER};" if border_right else ""
        col.setStyleSheet(f"QFrame {{ background:{BG_DARK}; border:none; {border} }}")
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
      Nodes:   Geo Map | Copy IP | Copy MAC
      Clients: Port Scan | Geo Map | AbuseIPDB | Copy IP | Copy MAC
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

        self.setStyleSheet(
            f"QFrame {{ background:{BG_DARK}; border:none;"
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
        self._node_table.verticalHeader().setDefaultSectionSize(22)
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
            f"QPushButton:checked {{ background:{ACCENT}; color:#000; border-color:{ACCENT}; }}"
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
        self._client_table.verticalHeader().setDefaultSectionSize(20)
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
        nodes = status.get("extra", {}).get("nodes", [])
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
            menu.addAction("Show on Geo Map", lambda: self.geo_map_ip.emit(ip))
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
            menu.addAction("Show on Geo Map", lambda: self.geo_map_ip.emit(ip))
            menu.addAction("Check IP (AbuseIPDB)", lambda: self.check_abuse_ip.emit(ip))
            menu.addSeparator()
            menu.addAction(f"Copy IP  {ip}", lambda: QApplication.clipboard().setText(ip))
        if mac and mac != "—":
            menu.addAction(f"Copy MAC  {mac}", lambda: QApplication.clipboard().setText(mac))
        if not menu.isEmpty():
            menu.exec(QCursor.pos())


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
        hdr.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:14px;")
        lay.addWidget(hdr)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(200)
        self._log.setStyleSheet(
            f"background:{BG_DARK}; color:{TEXT_SECONDARY}; "
            f"font-family:monospace; font-size:12px; border:none;"
        )
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
        data = bytes(self._proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._log.moveCursor(self._log.textCursor().End)
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

    refresh_clicked = pyqtSignal(str)   # path
    remove_clicked  = pyqtSignal(str)   # path
    stop_clicked    = pyqtSignal(str)   # path — stop polling worker

    def __init__(self, path: str, meta: dict, last_result: Optional[dict], parent=None):
        super().__init__(parent)
        self._path       = path
        self._meta       = meta
        self._last_ts    = last_result.get("_ts", 0.0) if last_result else 0.0
        self._hw_type    = meta.get("type", "unknown")
        self._detail_visible = False

        self.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header row ────────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:none;"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(12, 8, 10, 8)
        hdr_lay.setSpacing(8)

        # Status dot — clickable to expand/collapse detail
        self._dot = QLabel("●")
        self._dot.setStyleSheet(f"color:{TEXT_MUTED}; font-size:13px; border:none;")
        self._dot.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dot.setToolTip("Click to expand / collapse detail")
        self._dot.mousePressEvent = lambda _: self._toggle_detail()
        hdr_lay.addWidget(self._dot)

        # Name + type badge
        name_col = QVBoxLayout()
        name_col.setSpacing(1)
        name_col.setContentsMargins(0, 0, 0, 0)
        self._name_lbl = QLabel(f"<b>{meta.get('name', Path(path).stem)}</b>")
        self._name_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._name_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:12px; border:none; background:transparent;"
        )
        hw_type = meta.get("type", "")
        hw_ip   = meta.get("ip", "")
        sub_txt = "  ·  ".join(filter(None, [hw_type, hw_ip]))
        self._sub_lbl = QLabel(sub_txt)
        self._sub_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:9px; border:none; background:transparent;"
        )
        name_col.addWidget(self._name_lbl)
        name_col.addWidget(self._sub_lbl)
        hdr_lay.addLayout(name_col)

        # Metrics summary (centre)
        self._metrics_lbl = QLabel("Never run")
        self._metrics_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:10px; border:none; background:transparent;"
        )
        hdr_lay.addWidget(self._metrics_lbl, 1)

        # Timestamp
        self._ts_lbl = QLabel("")
        self._ts_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:9px; border:none; background:transparent;"
        )
        hdr_lay.addWidget(self._ts_lbl)

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

        # Remove button
        btn_remove = _btn("✕")
        btn_remove.setFixedWidth(28)
        btn_remove.setToolTip("Remove plugin")
        btn_remove.clicked.connect(lambda: self.remove_clicked.emit(self._path))
        hdr_lay.addWidget(btn_remove)

        outer.addWidget(hdr)

        # ── Password row ──────────────────────────────────────────────────────
        pw_row = QFrame()
        pw_row.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:none;"
            f" border-top:1px solid {BORDER}; border-radius:0px; }}"
        )
        pw_lay = QHBoxLayout(pw_row)
        pw_lay.setContentsMargins(40, 4, 10, 4)
        pw_lay.setSpacing(6)

        hw_ip_for_pw = meta.get("ip", "")
        pw_lbl = QLabel(f"Password ({hw_ip_for_pw or 'IP unknown'}):")
        pw_lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:9px; border:none;")
        pw_lay.addWidget(pw_lbl)

        self._pw_edit = QLineEdit()
        self._pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_edit.setPlaceholderText("enter password…")
        self._pw_edit.setFixedHeight(20)
        self._pw_edit.setFont(QFont("Segoe UI", 9))
        self._pw_edit.setStyleSheet(
            f"QLineEdit {{ background:{BG_DARK}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:0 6px; }}"
        )
        pw_lay.addWidget(self._pw_edit, 1)

        self._pw_status = QLabel("")
        self._pw_status.setStyleSheet(f"color:{GREEN}; font-size:9px; border:none;")
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
        _sec_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:9px; background:transparent; border:none;"
            " padding:0 0 2px 40px;"
        )
        outer.addWidget(_sec_lbl)

        # ── Detail panel (v2.1) ───────────────────────────────────────────────
        if self._hw_type == "modem":
            self._detail = _ModemDetailPanel()
        else:
            self._detail = _RouterDetailPanel()
        self._detail.setVisible(False)
        outer.addWidget(self._detail)

        # Apply persisted result immediately if available
        if last_result:
            self._apply_result(last_result)

    # ── Public interface ──────────────────────────────────────────────────────

    def update_result(self, data: dict, ts: float) -> None:
        self._last_ts = ts
        self._apply_result(data)

    def set_error(self, msg: str) -> None:
        self._dot.setStyleSheet(f"color:{RED}; font-size:13px; border:none;")
        self._metrics_lbl.setText(f"Error: {msg[:80]}")
        self._metrics_lbl.setStyleSheet(
            f"color:{AMBER}; font-size:10px; border:none; background:transparent;"
        )
        self._btn_refresh.setEnabled(True)
        self._btn_refresh.setText("↻")

    def set_refreshing(self, active: bool) -> None:
        self._btn_refresh.setEnabled(not active)
        self._btn_refresh.setText("…" if active else "↻")

    def tick_timestamp(self) -> None:
        if self._last_ts > 0:
            self._ts_lbl.setText(_age_str(self._last_ts))

    # ── Private ───────────────────────────────────────────────────────────────

    def _apply_result(self, data: dict) -> None:
        info    = data.get("info", {})
        status  = data.get("status", {})
        clients = data.get("clients", [])
        extra   = status.get("extra", {})
        hw_type = info.get("type", self._hw_type)

        self._dot.setStyleSheet(f"color:{GREEN}; font-size:13px; border:none;")
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
                    pass
            sinr = extra.get("nr5g_sinr_db") or extra.get("lte_snr_db")
            if sinr is not None:
                try:
                    parts.append(f"SINR {float(sinr):.1f} dB")
                except (TypeError, ValueError):
                    pass
            summary = "  ·  ".join(parts) if parts else "Online"
            self._metrics_lbl.setText(summary)
            self._metrics_lbl.setStyleSheet(
                f"color:{TEXT_PRIMARY}; font-size:10px; border:none; background:transparent;"
            )
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
            self._metrics_lbl.setStyleSheet(
                f"color:{TEXT_PRIMARY}; font-size:10px; border:none; background:transparent;"
            )
            self._detail.update(status, clients)

        self._btn_refresh.setEnabled(True)
        self._btn_refresh.setText("↻")

        # Auto-expand detail on first successful result
        if not self._detail_visible:
            self._toggle_detail()

    def _toggle_detail(self) -> None:
        self._detail_visible = not self._detail_visible
        self._detail.setVisible(self._detail_visible)
        self._dot.setToolTip(
            "Click to collapse detail" if self._detail_visible else "Click to expand detail"
        )

    def _save_password(self, hw_ip: str, pw_edit: QLineEdit, status: QLabel) -> None:
        pw = pw_edit.text().strip()
        if not pw:
            status.setText("Empty!")
            status.setStyleSheet(f"color:{AMBER}; font-size:9px;")
            return
        if not hw_ip:
            status.setText("No IP")
            status.setStyleSheet(f"color:{AMBER}; font-size:9px;")
            return
        try:
            import keyring
            keyring.set_password("NetSentinel/hardware", hw_ip, pw)
            pw_edit.clear()
            status.setText("✓ Saved")
            status.setStyleSheet(f"color:{GREEN}; font-size:9px;")
            QTimer.singleShot(3000, lambda: status.setText(""))
        except Exception as exc:
            status.setText("Error")
            status.setStyleSheet(f"color:{RED}; font-size:9px;")
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
                    pass
            status.setText("Forgotten")
            status.setStyleSheet(f"color:{TEXT_MUTED}; font-size:9px;")
        except Exception:
            status.setText("Not saved")
            status.setStyleSheet(f"color:{TEXT_MUTED}; font-size:9px;")
        QTimer.singleShot(3000, lambda: status.setText(""))


# ── Step-guide helper widgets (guide section) ─────────────────────────────────

def _step_card(number: int, title: str) -> tuple[QWidget, QVBoxLayout]:
    frame = QFrame()
    frame.setStyleSheet(
        f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
        f" border-radius:{CARD_RADIUS}; }}"
    )
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    hdr = QWidget()
    hdr.setStyleSheet(f"background:{BG_CARD}; border-bottom:1px solid {CARD_HDR_BORDER};")
    hdr_lay = QHBoxLayout(hdr)
    hdr_lay.setContentsMargins(12, 8, 12, 8)
    hdr_lay.setSpacing(10)

    badge = QLabel(str(number))
    badge.setFixedSize(22, 22)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
    badge.setStyleSheet(
        f"background:{ACCENT}; color:#fff; border-radius:11px; border:none;"
    )
    title_lbl = QLabel(title)
    title_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
    title_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; border:none; background:transparent;")
    hdr_lay.addWidget(badge)
    hdr_lay.addWidget(title_lbl)
    hdr_lay.addStretch()
    outer.addWidget(hdr)

    body = QWidget()
    body.setStyleSheet(f"background:{BG_CARD};")
    body_lay = QVBoxLayout(body)
    body_lay.setContentsMargins(14, 10, 14, 12)
    body_lay.setSpacing(8)
    outer.addWidget(body)

    return frame, body_lay


def _para(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
    return lbl


def _sub_header(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
    lbl.setStyleSheet(
        f"color:{TEXT_PRIMARY}; border:none;"
        f" border-bottom:1px solid {BORDER}; padding-bottom:3px; margin-top:2px;"
    )
    return lbl


def _copy_text(btn: QPushButton, text: str) -> None:
    QApplication.clipboard().setText(text)
    orig = btn.text()
    btn.setText("✓  Copied!")
    QTimer.singleShot(2000, lambda: btn.setText(orig))


def _code_chip(code: str) -> QWidget:
    frame = QFrame()
    frame.setStyleSheet(
        f"QFrame {{ background:{BG_DARK}; border:1px solid {BORDER}; border-radius:3px; }}"
    )
    row = QHBoxLayout(frame)
    row.setContentsMargins(8, 4, 6, 4)
    row.setSpacing(8)
    lbl = QLabel(code)
    lbl.setFont(QFont("Consolas", 8))
    lbl.setStyleSheet(f"color:{ACCENT}; border:none; background:transparent;")
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
    frame.setStyleSheet(
        f"QFrame {{ background:{BG_DARK}; border:1px solid {BORDER}; border-radius:4px; }}"
    )
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(10, 6, 10, 8)
    outer.setSpacing(4)
    hdr = QHBoxLayout()
    hdr.setContentsMargins(0, 0, 0, 0)
    lbl_w = QLabel(label)
    lbl_w.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
    lbl_w.setStyleSheet(f"color:{AMBER}; border:none; background:transparent;")
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
    body.setStyleSheet(
        f"color:{TEXT_SECONDARY}; font-size:9px; border:none; background:transparent;"
    )
    body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    outer.addWidget(body)
    return frame


# ── Main page ─────────────────────────────────────────────────────────────────

class HardwareIntegrationPage(QWidget):
    """Hardware Hub — live status dashboard for all imported hardware plugins."""

    # data dict has "_path" embedded so dashboard knows which plugin
    plugin_result  = pyqtSignal(dict)
    navigate_to    = pyqtSignal(str)   # page label → _nav_rail_go_to
    geo_map_ip     = pyqtSignal(str)   # open geo map for this IP
    port_scan_ip   = pyqtSignal(str)   # pre-fill port scanner with this IP
    check_abuse_ip = pyqtSignal(str)   # check IP on AbuseIPDB

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._poll_workers: Dict[str, PluginPollingWorker] = {}
        self._cards:   Dict[str, HubCard] = {}
        self._native_modem_connected: bool = False
        # Tab indices — set by _build_ui
        self._tabs: Optional[QTabWidget] = None
        self._modem_tab_idx:     int = 1
        self._mesh_tab_idx:      int = 2
        self._suggested_tab_idx: int = 3
        # Panels inside tabs
        self._modem_panel:    Optional[_ModemDetailPanel]  = None
        self._mesh_panel:     Optional[_RouterDetailPanel] = None
        self._suggested_lay:  Optional[QVBoxLayout]        = None

        self._build_ui()

        # Tick timer — updates "X min ago" labels every 30s
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(30_000)
        self._tick_timer.timeout.connect(self._tick_timestamps)
        self._tick_timer.start()

        # Start persistent poll workers for all imported plugins, staggered 3 s apart
        self._start_all_poll_workers()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 8)
        root.setSpacing(8)

        # Page header — outside tabs so it's always visible
        hdr_row = QHBoxLayout()
        title = QLabel("Hardware")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY};")
        hdr_row.addWidget(title)
        hdr_row.addStretch()
        self._btn_add = _btn("＋  Add Integration", accent=True)
        self._btn_add.clicked.connect(self._on_browse)
        hdr_row.addWidget(self._btn_add)
        root.addLayout(hdr_row)

        # Status label (import feedback) — outside tabs
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"font-size:10px; color:{TEXT_MUTED};")
        root.addWidget(self._status_lbl)

        # ── Tab widget ────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            f"QTabWidget::pane {{ border:1px solid {BORDER}; border-radius:4px; }}"
            f"QTabBar::tab {{ background:{BG_CARD}; color:{TEXT_MUTED};"
            f" padding:5px 14px; border:none; border-bottom:2px solid transparent; }}"
            f"QTabBar::tab:selected {{ color:{TEXT_PRIMARY};"
            f" border-bottom:2px solid {ACCENT}; }}"
            f"QTabBar::tab:hover {{ color:{TEXT_PRIMARY}; }}"
        )
        root.addWidget(self._tabs, 1)

        # ── Tab 0: Hardware (HubCards + guide) — always visible ──────────────
        hub_tab = QWidget()
        hub_tab.setStyleSheet(f"background:{BG_DARK};")
        hub_tab_lay = QVBoxLayout(hub_tab)
        hub_tab_lay.setContentsMargins(0, 6, 0, 0)
        hub_tab_lay.setSpacing(6)

        sub = QLabel(
            "Live status for all integrated hardware. "
            "Modem plugins refresh every 60 s · router/AP every 2 min · switch every 5 min. "
            "Click ● to expand the signal / topology detail panel."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px; padding:0 8px;")
        hub_tab_lay.addWidget(sub)

        self._hub_scroll = QScrollArea()
        self._hub_scroll.setWidgetResizable(True)
        self._hub_scroll.setStyleSheet("QScrollArea { border: none; }")
        self._hub_body = QWidget()
        self._hub_body.setStyleSheet(f"background:{BG_DARK};")
        self._hub_lay = QVBoxLayout(self._hub_body)
        self._hub_lay.setContentsMargins(0, 4, 0, 4)
        self._hub_lay.setSpacing(8)
        self._rebuild_hub()
        self._hub_scroll.setWidget(self._hub_body)
        hub_tab_lay.addWidget(self._hub_scroll, 3)

        guide_toggle_row = QHBoxLayout()
        guide_toggle_row.setContentsMargins(8, 0, 8, 0)
        self._guide_toggle = _btn("▶  How to write a plugin script")
        self._guide_toggle.clicked.connect(self._toggle_guide)
        guide_toggle_row.addWidget(self._guide_toggle)
        guide_toggle_row.addStretch()
        hub_tab_lay.addLayout(guide_toggle_row)

        self._guide_area = QScrollArea()
        self._guide_area.setWidgetResizable(True)
        self._guide_area.setStyleSheet("QScrollArea { border: none; }")
        self._guide_area.setVisible(False)
        guide_body = QWidget()
        guide_body.setStyleSheet(f"background:{BG_DARK};")
        guide_lay = QVBoxLayout(guide_body)
        guide_lay.setContentsMargins(0, 4, 0, 8)
        guide_lay.setSpacing(10)
        guide_lay.addWidget(self._build_step1())
        guide_lay.addWidget(self._build_step2())
        guide_lay.addWidget(self._build_step3_guide())
        guide_lay.addWidget(self._build_step4())
        guide_lay.addStretch()
        self._guide_area.setWidget(guide_body)
        hub_tab_lay.addWidget(self._guide_area, 2)

        if not _load_paths():
            self._guide_area.setVisible(True)
            self._guide_toggle.setText("▼  How to write a plugin script")

        self._tabs.addTab(hub_tab, "Hardware")

        # ── Tab 1: Modem — hidden until modem data arrives ────────────────────
        modem_tab = QWidget()
        modem_tab.setStyleSheet(f"background:{BG_DARK};")
        modem_tab_lay = QVBoxLayout(modem_tab)
        modem_tab_lay.setContentsMargins(0, 0, 0, 0)
        modem_tab_lay.setSpacing(0)
        self._modem_panel = _ModemDetailPanel()
        self._modem_panel.setStyleSheet(
            f"QFrame {{ background:{BG_DARK}; border:none; }}"
        )
        modem_tab_lay.addWidget(self._modem_panel)
        modem_tab_lay.addStretch()
        self._modem_tab_idx = self._tabs.addTab(modem_tab, "Modem")
        self._tabs.setTabVisible(self._modem_tab_idx, False)

        # ── Tab 2: Mesh & Router — hidden until router data arrives ───────────
        mesh_tab = QWidget()
        mesh_tab.setStyleSheet(f"background:{BG_DARK};")
        mesh_tab_lay = QVBoxLayout(mesh_tab)
        mesh_tab_lay.setContentsMargins(0, 0, 0, 0)
        mesh_tab_lay.setSpacing(0)
        self._mesh_panel = _RouterDetailPanel()
        self._mesh_panel.setStyleSheet(
            f"QFrame {{ background:{BG_DARK}; border:none; }}"
        )
        self._mesh_panel.geo_map_ip.connect(self.geo_map_ip)
        self._mesh_panel.port_scan_ip.connect(self.port_scan_ip)
        self._mesh_panel.check_abuse_ip.connect(self.check_abuse_ip)
        mesh_tab_lay.addWidget(self._mesh_panel)
        mesh_tab_lay.addStretch()
        self._mesh_tab_idx = self._tabs.addTab(mesh_tab, "Mesh & Router")
        self._tabs.setTabVisible(self._mesh_tab_idx, False)

        # ── Tab 3: Suggested — hidden until hw_detect finds matches ───────────
        suggested_tab = QWidget()
        suggested_tab.setStyleSheet(f"background:{BG_DARK};")
        suggested_outer = QVBoxLayout(suggested_tab)
        suggested_outer.setContentsMargins(0, 0, 0, 0)
        suggested_outer.setSpacing(0)

        sug_hdr = QFrame()
        sug_hdr.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:none;"
            f" border-bottom:1px solid {BORDER}; }}"
        )
        sug_hdr_lay = QHBoxLayout(sug_hdr)
        sug_hdr_lay.setContentsMargins(12, 7, 10, 7)
        sug_title = QLabel("Suggested for your network")
        sug_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        sug_title.setStyleSheet(f"color:{AMBER}; border:none; background:transparent;")
        sug_hdr_lay.addWidget(sug_title)
        sug_hdr_lay.addStretch()
        suggested_outer.addWidget(sug_hdr)

        sug_scroll = QScrollArea()
        sug_scroll.setWidgetResizable(True)
        sug_scroll.setStyleSheet("QScrollArea { border: none; }")
        sug_inner = QWidget()
        sug_inner.setStyleSheet(f"background:{BG_DARK};")
        self._suggested_lay = QVBoxLayout(sug_inner)
        self._suggested_lay.setContentsMargins(0, 2, 0, 6)
        self._suggested_lay.setSpacing(0)
        sug_scroll.setWidget(sug_inner)
        suggested_outer.addWidget(sug_scroll)

        self._suggested_tab_idx = self._tabs.addTab(suggested_tab, "Suggested")
        self._tabs.setTabVisible(self._suggested_tab_idx, False)

    def _toggle_guide(self) -> None:
        visible = not self._guide_area.isVisible()
        self._guide_area.setVisible(visible)
        self._guide_toggle.setText(
            "▼  How to write a plugin script" if visible
            else "▶  How to write a plugin script"
        )

    # ── Hub management ────────────────────────────────────────────────────────

    @staticmethod
    def _bundled_plugins_dir() -> Path:
        return Path(__file__).parent.parent.parent / "plugins"

    def _zte_plugin_imported(self) -> bool:
        bdir = self._bundled_plugins_dir()
        return str(bdir / "zte_plugin.py") in _load_paths()

    def _rebuild_hub(self) -> None:
        # Remove all existing card widgets
        while self._hub_lay.count():
            item = self._hub_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()

        # ── Catalog: bundled plugins not yet imported ─────────────────────────
        self._rebuild_catalog()

        # ── Active integrations ───────────────────────────────────────────────
        paths = _load_paths()
        if not paths:
            empty = QLabel(
                "No hardware imported yet.\n"
                "Use a catalog entry above, or click  ＋ Add Integration  to import a script."
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                f"color:{TEXT_MUTED}; font-size:11px; padding:24px 0;"
            )
            self._hub_lay.addWidget(empty)
        else:
            for path in paths:
                ok, _, meta = _validate_script(path)
                if not ok:
                    meta = {"name": Path(path).stem, "type": "unknown", "ip": ""}
                last_result = _load_last_result(path)
                card = HubCard(path, meta, last_result, parent=self._hub_body)
                card.refresh_clicked.connect(self._run_plugin)
                card.remove_clicked.connect(self._remove_plugin)
                card.stop_clicked.connect(self._stop_poll_worker)
                self._hub_lay.addWidget(card)
                self._cards[path] = card

        self._hub_lay.addStretch()

        # Phase 3: keep native modem tab hidden when ZTE plugin is active
        if self._tabs and self._zte_plugin_imported():
            self._tabs.setTabVisible(self._modem_tab_idx, False)

    def _rebuild_catalog(self) -> None:
        """Inject catalog cards for bundled plugins that are not yet imported."""
        bdir = self._bundled_plugins_dir()
        if not bdir.is_dir():
            return
        imported = set(_load_paths())
        entries: list[tuple[str, dict]] = []
        for pyf in sorted(bdir.glob("*_plugin.py")):
            ps = str(pyf)
            if ps in imported:
                continue
            ok, _, meta = _validate_script(ps)
            if ok:
                entries.append((ps, meta))
        if not entries:
            return

        # Section header
        hdr_lbl = QLabel("AVAILABLE PLUGINS")
        hdr_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:10px; font-weight:bold;"
            " letter-spacing:0.5px; padding:4px 8px 2px 8px;"
        )
        self._hub_lay.addWidget(hdr_lbl)

        for path, meta in entries:
            self._hub_lay.addWidget(self._build_catalog_card(path, meta))

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(
            f"QFrame {{ border:none; border-top:1px solid {BORDER}; background:transparent; }}"
        )
        sep.setFixedHeight(1)
        self._hub_lay.addWidget(sep)

    def _build_catalog_card(self, path: str, meta: dict) -> QFrame:
        _TYPE_ICON = {"modem": "📡", "router": "🔀", "ap": "📶",
                      "switch": "🔗", "other": "🔌"}
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:4px; }}"
        )
        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        icon_lbl = QLabel(_TYPE_ICON.get(meta.get("type", ""), "🔌"))
        icon_lbl.setFixedWidth(22)
        icon_lbl.setStyleSheet("background:transparent; border:none;")
        lay.addWidget(icon_lbl)

        txt = QVBoxLayout()
        txt.setSpacing(1)
        name_lbl = QLabel(meta.get("name", Path(path).stem))
        name_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:12px; font-weight:bold;"
            " background:transparent; border:none;"
        )
        txt.addWidget(name_lbl)
        desc = meta.get("description", "")
        if desc:
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(
                f"color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;"
            )
            desc_lbl.setWordWrap(True)
            txt.addWidget(desc_lbl)
        lay.addLayout(txt, 1)

        ip_lbl = QLabel(meta.get("ip", ""))
        ip_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:10px; background:transparent; border:none;"
        )
        lay.addWidget(ip_lbl)

        add_btn = QPushButton("＋  Add")
        add_btn.setFixedHeight(26)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#fff; border:none;"
            " border-radius:3px; font-size:11px; padding:0 12px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; }}"
        )
        add_btn.clicked.connect(lambda _, p=path: self._import_bundled(p))
        lay.addWidget(add_btn)
        return card

    def _import_bundled(self, path: str) -> None:
        """Add a bundled plugin to the imported list and start polling."""
        paths = _load_paths()
        if path not in paths:
            paths.append(path)
            _save_paths(paths)
        self._set_status(
            f"Imported '{Path(path).stem}' — running first check…", error=False
        )
        self._rebuild_hub()
        self._start_poll_worker(path)

    def _start_all_poll_workers(self) -> None:
        for i, path in enumerate(_load_paths()):
            QTimer.singleShot(i * 3000, lambda p=path: self._start_poll_worker(p))

    def _start_poll_worker(self, path: str) -> None:
        if path in self._poll_workers:
            return
        ok, _, meta = _validate_script(path)
        hw_type = meta.get("type", "other") if ok else "other"
        if hw_type == "modem" and self._native_modem_connected:
            return
        worker = PluginPollingWorker(path=path, hw_type=hw_type, parent=self)
        worker.result.connect(lambda data, p=path: self._on_plugin_result(p, data),
                              Qt.ConnectionType.QueuedConnection)
        worker.error.connect(lambda msg, p=path: self._on_plugin_error(p, msg),
                             Qt.ConnectionType.QueuedConnection)
        worker.start()
        self._poll_workers[path] = worker

    def _stop_poll_worker(self, path: str) -> None:
        worker = self._poll_workers.pop(path, None)
        if worker:
            worker.stop()
            worker.wait(2000)

    @pyqtSlot()
    def _tick_timestamps(self) -> None:
        for card in self._cards.values():
            card.tick_timestamp()

    # ── Plugin execution ──────────────────────────────────────────────────────

    @pyqtSlot(str)
    def _run_plugin(self, path: str) -> None:
        """Trigger an immediate poll — called by Refresh button or import."""
        card = self._cards.get(path)
        if card:
            card.set_refreshing(True)
        worker = self._poll_workers.get(path)
        if worker and worker.isRunning():
            worker.trigger_now()
        else:
            self._start_poll_worker(path)

    def _on_plugin_result(self, path: str, data: dict) -> None:
        ts = time.time()
        data["_ts"] = ts
        data["_path"] = path
        _save_last_result(path, data)
        card = self._cards.get(path)
        if card:
            card.update_result(data, ts)
        self.plugin_result.emit(data)

    def _on_plugin_error(self, path: str, msg: str) -> None:
        card = self._cards.get(path)
        if card:
            card.set_error(msg)

    # ── Import / remove ───────────────────────────────────────────────────────

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select hardware integration script", "",
            "Python files (*.py)",
        )
        if not path:
            return

        ok, msg, meta = _validate_script(path)
        if not ok:
            self._set_status(f"Validation failed: {msg}", error=True)
            return

        paths = _load_paths()
        if path not in paths:
            paths.append(path)
            _save_paths(paths)

        name = meta.get("name", Path(path).stem)
        self._set_status(f"Imported '{name}' — running first check…", error=False)
        self._rebuild_hub()
        self._start_poll_worker(path)

    @pyqtSlot(str)
    def _remove_plugin(self, path: str) -> None:
        self._stop_poll_worker(path)
        paths = [p for p in _load_paths() if p != path]
        _save_paths(paths)
        self._set_status(f"Removed {Path(path).name}.", error=False)
        self._rebuild_hub()

    # ── Status helper ─────────────────────────────────────────────────────────

    def _set_status(self, text: str, error: bool = False) -> None:
        color = AMBER if error else GREEN
        self._status_lbl.setText(text)
        self._status_lbl.setStyleSheet(f"font-size:10px; color:{color};")
        QTimer.singleShot(5000, lambda: self._status_lbl.setText(""))

    # ── Hardware auto-detection ───────────────────────────────────────────────

    def on_hardware_detected(self, matches: list) -> None:
        """Populate the Suggested tab from catalogue matches.

        Called from dashboard after HwDetectWorker finishes.
        Skips devices that are already installed.
        """
        if self._suggested_lay is None or self._tabs is None:
            return

        from modules.hw_detect import already_installed
        visible = [m for m in matches if not already_installed(m["plugin"].get("id", ""))]

        if not visible:
            self._tabs.setTabVisible(self._suggested_tab_idx, False)
            return

        # Clear previous rows
        while self._suggested_lay.count():
            item = self._suggested_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for match in visible:
            plugin     = match["plugin"]
            confidence = match["confidence"]
            signals    = match["signals"]
            # Modem tab visible → ZTE is already active; Mesh tab → Deco is active
            native_active = (
                (plugin.get("id") == "zte_mc889"
                 and self._tabs.isTabVisible(self._modem_tab_idx)) or
                (plugin.get("id") == "deco"
                 and self._tabs.isTabVisible(self._mesh_tab_idx))
            )
            self._suggested_lay.addWidget(
                self._build_detect_row(plugin, confidence, signals, native_active)
            )

        self._suggested_lay.addStretch()
        n = len(visible)
        self._tabs.setTabText(self._suggested_tab_idx, f"Suggested ({n})")
        self._tabs.setTabVisible(self._suggested_tab_idx, True)

    def _build_detect_row(
        self, plugin: dict, confidence: float, signals: list,
        native_active: bool = False,
    ) -> QWidget:
        row = QFrame()
        row.setStyleSheet(
            f"QFrame {{ background:transparent; border:none;"
            f" border-bottom:1px solid {BORDER}; }}"
        )
        lay = QHBoxLayout(row)
        lay.setContentsMargins(12, 8, 10, 8)
        lay.setSpacing(10)

        # Confidence dot
        dot = QLabel("●")
        if confidence >= 0.7:
            dot.setStyleSheet(f"color:{GREEN}; font-size:11px; border:none;")
            dot.setToolTip(f"Strong match ({confidence:.0%})")
        else:
            dot.setStyleSheet(f"color:{AMBER}; font-size:11px; border:none;")
            dot.setToolTip(f"Possible match ({confidence:.0%})")
        lay.addWidget(dot)

        # Device info
        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        info_col.setContentsMargins(0, 0, 0, 0)
        name_lbl = QLabel(f"<b>{plugin.get('name', '?')}</b>  "
                          f"<span style='color:{TEXT_MUTED}; font-size:9px;'>"
                          f"{plugin.get('manufacturer','')}</span>")
        name_lbl.setTextFormat(Qt.TextFormat.RichText)
        name_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:11px; border:none;")
        sig_lbl = QLabel(" · ".join(signals[:3]))
        sig_lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:9px; border:none;")
        sig_lbl.setWordWrap(True)
        info_col.addWidget(name_lbl)
        info_col.addWidget(sig_lbl)
        lay.addLayout(info_col, 1)

        # Action buttons
        native_page = plugin.get("native_page", "")
        has_bundled = bool(plugin.get("file"))
        has_prompt  = bool(plugin.get("ai_prompt"))

        if native_active and native_page:
            # Device is already supplying live data via its native worker.
            # Show "Open page" instead of Install — no script copy needed.
            status_lbl = QLabel("Active")
            status_lbl.setStyleSheet(
                f"color:{GREEN}; font-size:9px; font-weight:bold; border:none;"
            )
            lay.addWidget(status_lbl)
            btn_open = _btn(f"Open {native_page} →", accent=True)
            btn_open.setFixedHeight(24)
            btn_open.setToolTip(f"Navigate to the {native_page} page")
            btn_open.clicked.connect(lambda _=False, pg=native_page: self.navigate_to.emit(pg))
            lay.addWidget(btn_open)
        else:
            if has_bundled:
                btn_install = _btn("⬇  Install", accent=True)
                btn_install.setFixedHeight(24)
                btn_install.setToolTip(
                    "Copy bundled plugin into your NetSentinel data folder and register it"
                )
                btn_install.clicked.connect(lambda _=False, p=plugin: self._install_from_catalogue(p))
                lay.addWidget(btn_install)

            if has_prompt:
                btn_prompt = _btn("⎘  Copy AI prompt")
                btn_prompt.setFixedHeight(24)
                btn_prompt.setToolTip("Copy a pre-written prompt for an AI to generate this plugin")
                btn_prompt.clicked.connect(
                    lambda _=False, p=plugin: self._copy_ai_prompt(p, btn_prompt)
                )
                lay.addWidget(btn_prompt)

        return row

    def _install_from_catalogue(self, plugin: dict) -> None:
        """Copy a bundled plugin to the user data dir and register it.

        If the plugin requires a PyPI library that is not yet installed,
        opens PipInstallDialog first and only proceeds on success.
        """
        # ── 1. Check / install PyPI dependency ────────────────────────────────
        pypi_lib = plugin.get("pypi_library", "")
        if pypi_lib:
            import importlib.util
            # Map dash-separated package names to their importable module name
            module_name = pypi_lib.replace("-", "_")
            if importlib.util.find_spec(module_name) is None:
                dlg = PipInstallDialog(pypi_lib, parent=self)
                if dlg.exec() != QDialog.DialogCode.Accepted:
                    self._set_status("Dependency install cancelled.", error=True)
                    return
                # Verify the library is now importable after pip install
                import importlib
                importlib.invalidate_caches()
                if importlib.util.find_spec(module_name) is None:
                    self._set_status(
                        f"Library '{pypi_lib}' still not importable after install — "
                        "check the pip output for errors.",
                        error=True,
                    )
                    return

        # ── 2. Copy the bundled plugin script to the user data dir ────────────
        from modules.hw_detect import bundled_plugin_path
        file_rel = plugin.get("file", "")
        if not file_rel:
            self._set_status("No bundled plugin file for this entry.", error=True)
            return

        src = bundled_plugin_path(file_rel)
        if src is None:
            self._set_status(f"Bundled file not found: {file_rel}", error=True)
            return

        import shutil
        from pathlib import Path as _Path
        try:
            dest_dir = _Path.home() / ".netsentinel" / "plugins"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / src.name
            if dest != src:
                shutil.copy2(src, dest)
            dest_str = str(dest)
        except Exception as exc:
            self._set_status(f"Copy failed: {exc}", error=True)
            return

        ok, msg, _ = _validate_script(dest_str)
        if not ok:
            self._set_status(f"Plugin validation failed: {msg}", error=True)
            return

        paths = _load_paths()
        if dest_str not in paths:
            paths.append(dest_str)
            _save_paths(paths)

        name = plugin.get("name", src.name)
        self._set_status(f"Installed '{name}' — opening password field…", error=False)
        self._rebuild_hub()
        self._start_poll_worker(dest_str)
        # Hide the Suggested tab since the device is now installed
        if self._tabs is not None:
            self._tabs.setTabVisible(self._suggested_tab_idx, False)

    # ── Modem / mesh tab data ────────────────────────────────────────────────

    def on_modem_card_data(self, raw: dict) -> None:
        """Update the Modem tab with incoming signal data (any modem source).

        Also updates the shared hw_state singleton so speed test and other
        surfaces can read the latest modem snapshot without a dashboard ref.
        """
        if self._tabs is None or self._modem_panel is None:
            return
        extra  = {k: v for k, v in raw.items() if k != "host"}
        status = {"wan_ip": raw.get("wan_ip"), "extra": extra}
        self._modem_panel.update(extra, status)

        nt = raw.get("network_type", "")
        if "NR5G" in nt.upper() or "5G" in nt.upper():
            suffix = " · 5G NR"
        elif "LTE" in nt.upper():
            suffix = " · LTE"
        else:
            suffix = ""
        self._tabs.setTabText(self._modem_tab_idx, f"Modem{suffix}")
        if not self._zte_plugin_imported():
            self._tabs.setTabVisible(self._modem_tab_idx, True)

        from modules.network_infrastructure import hw_state
        hw_state.update_modem(raw, source="hub", hw_name=raw.get("host", "Modem"))

    def on_mesh_card_data(self, units: list, clients: list, provider: str = "Mesh") -> None:
        """Update the Mesh & Router tab with incoming router data (any source).

        Also updates the shared hw_state singleton.
        """
        if self._tabs is None or self._mesh_panel is None:
            return

        nodes_dicts = [
            {"name": getattr(u, "name", ""), "role": getattr(u, "role", "satellite"),
             "mac": str(getattr(u, "mac", ""))}
            for u in units
        ]
        clients_dicts = [
            {"ip": getattr(c, "ip", ""), "mac": str(getattr(c, "mac", "")),
             "hostname": getattr(c, "name", "") or "", "band": getattr(c, "band", ""),
             "unit": getattr(c, "unit_name", ""),
             "upload_kbps": getattr(c, "upload_kbps", 0),
             "download_kbps": getattr(c, "download_kbps", 0)}
            for c in clients
        ]
        status = {
            "mesh_nodes": len(units),
            "connected_clients": len(clients),
            "extra": {"nodes": nodes_dicts},
        }
        self._mesh_panel.update(status, clients_dicts)

        n_cli = len(clients)
        n_nodes = len(units)
        parts = []
        if n_nodes:
            parts.append(f"{n_nodes} node{'s' if n_nodes != 1 else ''}")
        if n_cli:
            parts.append(f"{n_cli} client{'s' if n_cli != 1 else ''}")
        title = "Mesh & Router" + (f"  ·  {', '.join(parts)}" if parts else "")
        self._tabs.setTabText(self._mesh_tab_idx, title)
        self._tabs.setTabVisible(self._mesh_tab_idx, True)

        from modules.network_infrastructure import hw_state
        hw_state.update_router(clients_dicts, nodes_dicts,
                               source="hub", hw_name=provider)

    def _copy_ai_prompt(self, plugin: dict, btn: QPushButton) -> None:
        """Copy the catalogue AI prompt to clipboard, replacing {ip} placeholder."""
        prompt = plugin.get("ai_prompt", "")
        default_ip = (plugin.get("fingerprints", {}).get("default_ips") or ["192.168.1.1"])[0]
        prompt = prompt.replace("{ip}", default_ip)
        QApplication.clipboard().setText(prompt)
        orig = btn.text()
        btn.setText("✓  Copied!")
        QTimer.singleShot(2000, lambda: btn.setText(orig))

    # ── Native modem coordination ─────────────────────────────────────────────

    def set_native_modem_connected(self, connected: bool) -> None:
        """Called by dashboard when ZteWorker connects/disconnects.

        ZTE MC889 supports only one web session.  While the native ZteWorker is
        active, modem plugin workers are stopped and data flows via
        on_native_modem_data instead.  When ZteWorker stops, the plugin worker
        takes over automatically.
        """
        self._native_modem_connected = connected
        modem_paths = [
            p for p in list(self._poll_workers.keys())
            if _validate_script(p)[2].get("type") == "modem"
        ]
        if connected:
            for p in modem_paths:
                self._stop_poll_worker(p)
        else:
            for p in _load_paths():
                if _validate_script(p)[2].get("type") == "modem":
                    self._start_poll_worker(p)

    def on_native_modem_data(self, raw: dict) -> None:
        """Forward ZteWorker signal payload to modem-type plugin cards.

        Converts the flat ZteSignalData dict to the {info, status, clients}
        envelope that HubCard.update_result() expects.  Saves to QSettings so
        the card shows data on next launch without waiting for first poll.
        """
        ts = time.time()
        for path, card in self._cards.items():
            ok, _, meta = _validate_script(path)
            if not ok or meta.get("type") != "modem":
                continue
            extra = {k: v for k, v in raw.items() if k != "host"}
            status = {
                "wan_ip":            raw.get("wan_ip"),
                "uptime_sec":        None,
                "download_mbps":     None,
                "upload_mbps":       None,
                "signal_dbm":        raw.get("nr5g_rsrp_dbm") or raw.get("lte_rsrp_dbm"),
                "connected_clients": None,
                "extra":             extra,
            }
            info = {
                "name": meta.get("name", "Modem"),
                "type": "modem",
                "ip":   raw.get("host", meta.get("ip", "")),
            }
            data = {"info": info, "status": status, "clients": [],
                    "_path": path, "_ts": ts}
            _save_last_result(path, data)
            card.update_result(data, ts)
            self.plugin_result.emit(data)

    # ── Guide content (collapsible) ───────────────────────────────────────────

    def _build_step1(self) -> QWidget:
        frame, lay = _step_card(1, "Find your hardware's local API")
        lay.addWidget(_para(
            "You do not need to be a programmer — an AI can write almost all "
            "the code for you. Your job is to find out HOW your specific hardware "
            "exposes data, then hand that to the AI."
        ))
        lay.addWidget(_sub_header("1a  Search GitHub for an existing implementation"))
        lay.addWidget(_para("Paste one of these search strings into github.com:"))
        for s in ['"Brand Model" python router', '"Brand Model" python api',
                  '"Brand" router python script', '"Brand" modem python library']:
            lay.addWidget(_code_chip(s))

        lay.addWidget(_sub_header("1b  Ask an AI to write the script for you"))
        lay.addWidget(_para(
            "Claude, ChatGPT, and Gemini can write the full Python script "
            "if you give them the right information."
        ))
        lay.addWidget(_prompt_block(
            "PROMPT A — General (start here)",
            "I want to write a Python script that reads live data from my [Brand] [Model] "
            "router/modem. The admin panel is at http://192.168.1.1. "
            "Login: username 'admin', password 'admin'.\n\n"
            "Please:\n"
            "1. Find if this router has a local JSON REST API or requires HTML scraping\n"
            "2. Write a Python script using requests that logs in and returns:\n"
            "   - WAN IP, Uptime, Connected clients (name, IP, MAC)\n"
            "3. Add a main block at the bottom that prints all results as JSON\n"
            "4. Tell me which packages to install with pip",
        ))
        lay.addWidget(_prompt_block(
            "PROMPT B — From a cURL command (best results)",
            "I captured this API call from my router admin panel using browser dev tools "
            "(F12 → Network → right-click request → Copy as cURL). "
            "Convert it to a Python function using requests.\n\n"
            "[Paste your cURL command here]\n\n"
            "Then wrap the result in the NetSentinel plugin format:\n"
            "- HARDWARE_NAME, HARDWARE_TYPE, get_info(), get_status(), get_clients()\n"
            "- if __name__ == '__main__': print all results as JSON",
        ))

        lay.addWidget(_sub_header("1c  Spy on your own router with browser dev tools"))
        lay.addWidget(_para(
            "Open your router admin panel in a browser, press F12, go to the Network tab, "
            "reload the page, look for JSON responses, and right-click → Copy as cURL. "
            "Paste into Prompt B above."
        ))
        return frame

    def _build_step2(self) -> QWidget:
        frame, lay = _step_card(2, "Get the script written (template + AI)")
        lay.addWidget(_para(
            "Either fill in the template yourself or hand it to an AI."
        ))
        lay.addWidget(_sub_header("Template"))

        template_edit = QTextEdit()
        template_edit.setReadOnly(True)
        template_edit.setPlainText(_TEMPLATE)
        template_edit.setFont(QFont("Consolas", 8))
        template_edit.setFixedHeight(240)
        template_edit.setStyleSheet(
            f"QTextEdit {{ background:{BG_DARK}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:4px; }}"
        )
        lay.addWidget(template_edit)

        btn_row = QHBoxLayout()
        btn_copy = _btn("⎘  Copy template")
        btn_save = _btn("💾  Save template as .py…")
        btn_copy.clicked.connect(lambda: _copy_text(btn_copy, _TEMPLATE))
        btn_save.clicked.connect(self._on_save_template)
        btn_row.addWidget(btn_copy)
        btn_row.addWidget(btn_save)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        lay.addWidget(_prompt_block(
            "PROMPT — Ask AI to complete the template",
            "I want to integrate my [Brand] [Model] router/modem into a monitoring app. "
            "I have a Python plugin template. Hardware details:\n"
            "- Admin panel URL: http://192.168.1.1\n"
            "- Username: admin  Password: admin\n\n"
            "Please complete get_info() and get_status() using the real API for my hardware.\n"
            "[Paste the template here]",
        ))
        return frame

    def _build_step3_guide(self) -> QWidget:
        frame, lay = _step_card(3, "Test locally, then import via ＋ Add Integration above")
        lay.addWidget(_para(
            "Once your script prints correct data when run standalone "
            "(python your_file.py), click ＋ Add Integration at the top of this page. "
            "NetSentinel validates the interface, then runs the script and shows the result "
            "in the Hub above."
        ))
        return frame

    def _build_step4(self) -> QWidget:
        frame, lay = _step_card(4, "Share your script with the community")
        lay.addWidget(_para(
            "A script that works for you almost certainly works for everyone with "
            "the same hardware. Open a GitHub Issue at github.com/ossianericson/netsentinel "
            "with title: [Hardware Plugin] Brand Model XYZ. Attach your .py file."
        ))
        return frame

    def _on_save_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save integration template", "netsentinel_hardware.py",
            "Python files (*.py)",
        )
        if not path:
            return
        try:
            Path(path).write_text(_TEMPLATE, encoding="utf-8")
            self._set_status(f"Template saved to {Path(path).name}", error=False)
        except Exception as exc:
            self._set_status(f"Save failed: {exc}", error=True)
