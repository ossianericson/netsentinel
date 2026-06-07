"""
ui/pages/connections_page.py — Active Connections (Process-to-Socket Map)
==========================================================================
Shows every active TCP/UDP connection on the local machine, enriched with:
  - Owning process name + PID
  - Remote IP geo-location (country, flag)
  - Colour-coded risk (external vs local vs listen)
  - "Block Process" action (creates Windows Firewall outbound-deny rule)

Layout
------
  Title + subtitle
  KPI row: Total / Established / External / Blocked Processes
  Filter/action bar: search | proto filter | Show LISTEN | Refresh | Auto-refresh toggle
  Status label
  Connections table (10 columns)
  Blocked rules panel (collapsible list of active NS-Block-* rules)
"""

from __future__ import annotations

import subprocess
import sys
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.empty_state_card import EmptyStateCard

from ui.expanding_table import ExpandingTable

from ui.styles import (
    ACCENT, AMBER, BG_ALT_ROW, BG_CARD,
    BG_DARK, BG_HOVER, BORDER, CARD_HDR_BORDER,
    GREEN, RED, TABLE_ROW_BORDER, TABLE_SEL,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, TH_BG,
    TH_BORDER, TH_TEXT,
)
from ui.table_utils import kpi_tile as _shared_kpi_tile, restore_column_widths, save_column_widths


_TABLE_HEADERS = [
    "Process", "PID", "Proto", "Local", "Remote IP",
    "Port", "Status", "Country", "Path", "Action",
]

_STATUS_COLOR = {
    "ESTABLISHED": GREEN,
    "LISTEN":      ACCENT,
    "TIME_WAIT":   AMBER,
    "CLOSE_WAIT":  AMBER,
    "SYN_SENT":    AMBER,
    "FIN_WAIT1":   TEXT_MUTED,
    "FIN_WAIT2":   TEXT_MUTED,
}


# ── Firewall helpers ──────────────────────────────────────────────────────────

def _rule_name(exe_name: str) -> str:
    return f"NS-Block-{exe_name}"


def _block_process(exe_path: str, exe_name: str) -> tuple[bool, str]:
    """Create an outbound-deny firewall rule. Returns (success, message)."""
    if sys.platform != "win32":
        return False, "Firewall control is only available on Windows"
    if not exe_path:
        return False, f"Cannot block '{exe_name}' — executable path unknown"
    rule = _rule_name(exe_name)
    cmd = [
        "netsh", "advfirewall", "firewall", "add", "rule",
        f"name={rule}",
        "dir=out",
        "action=block",
        f"program={exe_path}",
        "enable=yes",
        "profile=any",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return True, f"Blocked: {exe_name}"
        return False, result.stderr.strip() or result.stdout.strip()
    except Exception as exc:
        return False, str(exc)


def _unblock_process(exe_name: str) -> tuple[bool, str]:
    """Remove the NS-Block-* firewall rule for exe_name."""
    if sys.platform != "win32":
        return False, "Windows only"
    rule = _rule_name(exe_name)
    cmd = [
        "netsh", "advfirewall", "firewall", "delete", "rule",
        f"name={rule}",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return True, f"Unblocked: {exe_name}"
        return False, result.stderr.strip() or "Rule not found"
    except Exception as exc:
        return False, str(exc)


def _get_blocked_rules() -> list[str]:
    """Return list of exe names currently blocked by NS-Block-* rules."""
    if sys.platform != "win32":
        return []
    try:
        result = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule",
             "name=all", "dir=out", "verbose"],
            capture_output=True, text=True, timeout=15
        )
        rules = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("Rule Name:") and "NS-Block-" in line:
                name = line.split("NS-Block-", 1)[1].strip()
                rules.append(name)
        return rules
    except Exception:
        return []


# ── Main page ─────────────────────────────────────────────────────────────────

class ConnectionsPage(QWidget):
    """Active Connections — process-to-socket map with firewall control."""

    scan_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._popover = None
        self._connections: list = []
        self._displayed_conns: list = []
        self._blocked_rules: list[str] = []
        self._worker = None
        self._poller = None
        self._group_by_proc: bool = False

        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(5000)
        self._auto_timer.timeout.connect(self._refresh)

        self._undo_exe: str = ""
        self._undo_timer = QTimer(self)
        self._undo_timer.setSingleShot(True)
        self._undo_timer.timeout.connect(self._hide_undo_bar)

        self._setup_ui()
        self._refresh()  # load immediately on open
        self._load_blocked_rules()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Header
        from ui.widgets.page_header import PageHeaderBar
        root.addWidget(PageHeaderBar("Active Connections"))

        # KPI row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        _kt, self._lbl_total    = _shared_kpi_tile("Total",       "—", ACCENT)
        _ke, self._lbl_estab    = _shared_kpi_tile("Established", "—", GREEN)
        _kx, self._lbl_external = _shared_kpi_tile("External",    "—", AMBER)
        _kb, self._lbl_blocked  = _shared_kpi_tile("FW Blocked",  "—", RED)
        for t in (_kt, _ke, _kx, _kb):
            kpi_row.addWidget(t, 1)
        root.addLayout(kpi_row)

        # Filter bar
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        _inp = (
            f"QLineEdit {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:4px 8px;"
            f" font-size:11px; }}"
            f"QLineEdit:focus {{ border-color:{ACCENT}; }}"
        )
        _cbo = (
            f"QComboBox {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:3px 8px;"
            f" font-size:11px; min-height:26px; }}"
        )

        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter by process, IP, port…")
        self._search.setClearButtonEnabled(True)
        self._search.setStyleSheet(_inp)
        self._search.textChanged.connect(self._apply_filters)

        self._proto_filter = QComboBox()
        self._proto_filter.setStyleSheet(_cbo)
        self._proto_filter.addItems(["All Protocols", "TCP", "UDP"])
        self._proto_filter.currentIndexChanged.connect(self._apply_filters)

        self._chk_listen = QCheckBox("Show LISTEN")
        self._chk_listen.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;"
        )
        self._chk_listen.toggled.connect(self._refresh)

        self._chk_local = QCheckBox("Show local")
        self._chk_local.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;"
        )
        self._chk_local.setChecked(True)
        self._chk_local.toggled.connect(self._apply_filters)

        btn_refresh = QPushButton("⟳  Refresh")
        btn_refresh.setObjectName("btnNetRefresh")
        btn_refresh.setFixedHeight(28)
        btn_refresh.clicked.connect(self._refresh)

        self._chk_auto = QCheckBox("Auto (5s)")
        self._chk_auto.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;"
        )
        self._chk_auto.toggled.connect(self._on_auto_toggled)

        self._btn_group = QPushButton("⊞ Group by Process")
        self._btn_group.setCheckable(True)
        self._btn_group.setFixedHeight(28)
        self._btn_group.setStyleSheet(
            f"QPushButton {{ font-size:11px; color:{TEXT_SECONDARY}; background:{BG_CARD};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:0 8px; }}"
            f"QPushButton:checked {{ color:{ACCENT}; border-color:{ACCENT}; background:{BG_HOVER}; }}"
            f"QPushButton:hover {{ border-color:{ACCENT}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_SECONDARY}; }}"
        )
        self._btn_group.toggled.connect(self._on_group_toggled)

        filter_row.addWidget(self._search, 2)
        filter_row.addWidget(self._proto_filter)
        filter_row.addWidget(self._chk_listen)
        filter_row.addWidget(self._chk_local)
        filter_row.addWidget(btn_refresh)
        filter_row.addWidget(self._chk_auto)
        filter_row.addWidget(self._btn_group)
        root.addLayout(filter_row)

        # Status label
        self._status_lbl = QLabel("Loading…")
        self._status_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px;"
            f" background:transparent; border:none;"
        )
        root.addWidget(self._status_lbl)

        # Undo bar — appears for 10 s after a successful block action
        self._undo_bar = QFrame()
        self._undo_bar.setFixedHeight(32)
        self._undo_bar.setStyleSheet(
            f"background:{BG_CARD}; border:none;"
            f" border-left:3px solid {GREEN}; border-radius:0;"
        )
        _ub_lay = QHBoxLayout(self._undo_bar)
        _ub_lay.setContentsMargins(10, 0, 8, 0)
        _ub_lay.setSpacing(8)
        self._undo_lbl = QLabel()
        self._undo_lbl.setStyleSheet(
            f"color:{GREEN}; font-size:11px; font-weight:bold;"
            f" background:transparent; border:none;"
        )
        _ub_lay.addWidget(self._undo_lbl)
        _ub_lay.addStretch()
        self._undo_btn = QPushButton("Undo")
        self._undo_btn.setFixedSize(52, 22)
        self._undo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._undo_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_SECONDARY};"
            f" border:1px solid {BORDER}; border-radius:3px; font-size:10px; }}"
            f"QPushButton:hover {{ border-color:{ACCENT}; color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_SECONDARY}; }}"
        )
        self._undo_btn.clicked.connect(self._do_undo_block)
        _ub_lay.addWidget(self._undo_btn)
        self._undo_bar.setVisible(False)
        root.addWidget(self._undo_bar)

        # Connections table
        self._tbl = ExpandingTable(
            0, len(_TABLE_HEADERS),
            detail_builder=lambda r: self._build_connection_detail(r),
            detail_height=110,
        )
        self._tbl.setHorizontalHeaderLabels(_TABLE_HEADERS)
        self._tbl.horizontalHeader().setStretchLastSection(False)
        self._tbl.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._tbl.horizontalHeader().setSectionResizeMode(
            8, QHeaderView.ResizeMode.Stretch
        )
        self._tbl.setAlternatingRowColors(True)
        self._tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.verticalHeader().setDefaultSectionSize(24)
        self._tbl.setColumnWidth(1, 55)   # PID
        self._tbl.setColumnWidth(2, 45)   # Proto
        self._tbl.setColumnWidth(3, 145)  # Local
        self._tbl.setColumnWidth(4, 130)  # Remote IP
        self._tbl.setColumnWidth(5, 50)   # Port
        self._tbl.setColumnWidth(6, 90)   # Status
        self._tbl.setColumnWidth(7, 130)  # Country
        self._tbl.setColumnWidth(9, 70)   # Action
        self._tbl.setStyleSheet(
            f"QTableWidget {{ border:none; font-size:11px; color:{TEXT_PRIMARY}; }}"
            f"QHeaderView::section {{"
            f"  background:{TH_BG}; color:{TH_TEXT}; font-size:11px;"
            f"  font-weight:bold; padding:4px 5px; border:none;"
            f"  border-right:1px solid {TH_BORDER};"
            f"}}"
            f"QTableWidget::item:selected {{ background:{TABLE_SEL}; color:{TEXT_PRIMARY}; }}"
            f"QTableWidget::item:alternate {{ background:{BG_ALT_ROW}; }}"
            f"QTableWidget::item {{ border-bottom:1px solid {TABLE_ROW_BORDER}; }}"
        )
        self._tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tbl.customContextMenuRequested.connect(self._context_menu)

        # Content stack: index 0 = empty state, index 1 = table + blocked panel
        self._content_stack = QStackedWidget()

        empty_card = EmptyStateCard(
            icon="◆",
            title="Active Connections",
            what_it_shows=(
                "Every TCP/UDP connection on this machine — process name, remote IP, "
                "country, and connection status — updated live."
            ),
            why_it_matters=(
                "Unexpected outbound connections can reveal malware, data exfiltration, "
                "or shadow IT. Knowing what's connecting matters."
            ),
            btn_label="Start Monitoring",
        )
        empty_card.clicked.connect(self._refresh)
        self._content_stack.addWidget(empty_card)

        # Index 1: table + blocked rules panel
        content_w = QWidget()
        content_lay = QVBoxLayout(content_w)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(4)

        from ui.widgets.density_toggle import DensityToggle
        _dt_row = QHBoxLayout()
        _dt_row.setContentsMargins(0, 2, 0, 2)
        _dt_row.addStretch()
        _dt_row.addWidget(DensityToggle("connections", self._tbl))
        content_lay.addLayout(_dt_row)

        content_lay.addWidget(self._tbl, 3)
        self._tbl.horizontalHeader().sectionResized.connect(
            lambda _l, _o, _n: save_column_widths(self._tbl, "connections")
        )

        # Blocked rules panel
        blocked_frame = QFrame()
        blocked_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:0;"
        )
        blocked_lay = QVBoxLayout(blocked_frame)
        blocked_lay.setContentsMargins(12, 8, 12, 8)
        blocked_lay.setSpacing(6)

        hdr = QHBoxLayout()
        hdr_lbl = QLabel("FIREWALL BLOCKS (NS-Block-* rules)")
        hdr_lbl.setStyleSheet(
            f"font-size:11px; font-weight:bold; color:{RED};"
            f" background:transparent; border:none;"
        )
        btn_reload_rules = QPushButton("Reload")
        btn_reload_rules.setObjectName("btnNetRefresh")
        btn_reload_rules.setFixedHeight(22)
        btn_reload_rules.setFixedWidth(60)
        btn_reload_rules.clicked.connect(self._load_blocked_rules)
        hdr.addWidget(hdr_lbl)
        hdr.addStretch()
        hdr.addWidget(btn_reload_rules)
        blocked_lay.addLayout(hdr)

        self._blocked_lbl = QLabel("No active blocks")
        self._blocked_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY};"
            f" background:transparent; border:none;"
        )
        self._blocked_lbl.setWordWrap(True)
        blocked_lay.addWidget(self._blocked_lbl)

        content_lay.addWidget(blocked_frame)
        self._content_stack.addWidget(content_w)

        root.addWidget(self._content_stack, 1)

    # ── Refresh ───────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _refresh(self) -> None:
        from workers.process_worker import ConnectionSnapshotWorker
        if self._worker and self._worker.isRunning():
            return
        self._status_lbl.setText("Scanning connections…")
        include_listen = self._chk_listen.isChecked()
        self._worker = ConnectionSnapshotWorker(
            include_listen=include_listen, parent=self
        )
        self._worker.snapshot_ready.connect(self._on_snapshot)
        self._worker.error.connect(
            lambda e: self._status_lbl.setText(f"⚠  {e}")
        )
        self._worker.start()

    @pyqtSlot(list)
    def _on_snapshot(self, conns: list) -> None:
        self._connections = conns
        self._content_stack.setCurrentIndex(1)
        self._apply_filters()
        self._update_kpis()

    def _update_kpis(self) -> None:
        total    = len(self._connections)
        estab    = sum(1 for c in self._connections if c.status == "ESTABLISHED")
        external = sum(1 for c in self._connections
                       if c.remote_ip and not c.is_local)
        blocked  = len(self._blocked_rules)
        self._lbl_total.set_value(total)
        self._lbl_estab.set_value(estab)
        self._lbl_external.set_value(external)
        self._lbl_blocked.set_value(blocked)
        self._status_lbl.setText(
            f"{total} connection(s)  |  {estab} established  |  {external} external"
        )

    # ── Filtering + table population ──────────────────────────────────────────

    @pyqtSlot()
    def _apply_filters(self) -> None:
        text        = self._search.text().strip().lower()
        proto_sel   = self._proto_filter.currentText()
        show_local  = self._chk_local.isChecked()

        visible = []
        for c in self._connections:
            if proto_sel != "All Protocols" and c.proto != proto_sel:
                continue
            if not show_local and c.is_local:
                continue
            if text:
                haystack = " ".join([
                    c.exe_name, str(c.pid), c.remote_ip,
                    str(c.remote_port), c.status, c.country, c.exe_path,
                ]).lower()
                if text not in haystack:
                    continue
            visible.append(c)

        if self._group_by_proc:
            self._populate_grouped_table(visible)
        else:
            self._populate_table(visible)

    def _on_group_toggled(self, checked: bool) -> None:
        self._group_by_proc = checked
        self._apply_filters()

    def _populate_grouped_table(self, conns: list) -> None:
        from collections import defaultdict
        self._tbl.clear_detail()
        self._tbl.setRowCount(0)

        groups: dict[str, list] = defaultdict(list)
        for c in conns:
            groups[c.exe_name].append(c)

        _STATUS_RANK = {"ESTABLISHED": 3, "LISTEN": 2, "TIME_WAIT": 1}
        groups_sorted = sorted(
            groups.items(),
            key=lambda kv: (
                -max(_STATUS_RANK.get(c.status, 0) for c in kv[1]),
                -sum(1 for c in kv[1] if c.remote_ip and not c.is_local),
            ),
        )

        self._displayed_conns = []
        for exe_name, grp_conns in groups_sorted:
            external = sum(1 for c in grp_conns if c.remote_ip and not c.is_local)
            worst = max(grp_conns, key=lambda c: _STATUS_RANK.get(c.status, 0))
            is_blocked = exe_name in self._blocked_rules
            self._displayed_conns.append(("group", exe_name, grp_conns))

            row = self._tbl.rowCount()
            self._tbl.insertRow(row)

            row_color = TEXT_PRIMARY if external else TEXT_SECONDARY
            status_color = _STATUS_COLOR.get(worst.status, TEXT_MUTED)

            cells = [
                (exe_name,            row_color),
                (str(len(grp_conns)), TEXT_MUTED),
                ("—",                 TEXT_MUTED),
                ("—",                 TEXT_MUTED),
                (f"{external} ext",   AMBER if external else TEXT_MUTED),
                ("—",                 TEXT_MUTED),
                (worst.status,        status_color),
                ("—",                 TEXT_MUTED),
                (worst.exe_path or "—", TEXT_MUTED),
                ("🔓 Unblock" if is_blocked else "🔒 Block",
                 RED if not is_blocked else AMBER),
            ]
            for col, (text, color) in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setForeground(QColor(color))
                if col == 0:
                    item.setToolTip(
                        f"{exe_name}\n{len(grp_conns)} connection(s) · {external} external"
                    )
                self._tbl.setItem(row, col, item)

    def _populate_table(self, conns: list) -> None:
        self._tbl.clear_detail()
        self._displayed_conns = conns
        self._tbl.setRowCount(0)

        # Precompute per-process stats for ACT-1 tooltips
        _proc_total: dict[str, int] = {}
        _proc_external: dict[str, int] = {}
        for _c in self._connections:
            _proc_total[_c.exe_name] = _proc_total.get(_c.exe_name, 0) + 1
            if _c.remote_ip and not _c.is_local:
                _proc_external[_c.exe_name] = _proc_external.get(_c.exe_name, 0) + 1

        for c in conns:
            row = self._tbl.rowCount()
            self._tbl.insertRow(row)

            # Colour scheme: red for external established, amber for listen,
            # grey for local/system
            if c.status == "ESTABLISHED" and not c.is_local:
                row_color = TEXT_PRIMARY
            elif c.status in ("LISTEN", "NONE"):
                row_color = TEXT_MUTED
            else:
                row_color = TEXT_SECONDARY

            status_color = _STATUS_COLOR.get(c.status, TEXT_MUTED)

            # Country cell: flag code + country name
            country_str = ""
            if c.flag:
                country_str = f"{c.flag}  {c.country}"
            elif c.country:
                country_str = c.country
            elif c.remote_ip and not c.is_local:
                country_str = "…"  # pending lookup

            # Action column: Block / Unblocked
            is_blocked = c.exe_name in self._blocked_rules
            action_str = "🔓 Unblock" if is_blocked else "🔒 Block"
            action_color = RED if not is_blocked else AMBER

            cells = [
                (c.exe_name,              row_color),
                (str(c.pid) if c.pid else "—", TEXT_MUTED),
                (c.proto,                 ACCENT),
                (c.local_addr,            TEXT_MUTED),
                (c.remote_ip or "—",      TEXT_PRIMARY if c.remote_ip else TEXT_MUTED),
                (str(c.remote_port) if c.remote_port else "—", TEXT_MUTED),
                (c.status,                status_color),
                (country_str,             TEXT_SECONDARY),
                (c.exe_path or "—",       TEXT_MUTED),
                (action_str,              action_color),
            ]

            for col, (text, color) in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setForeground(QColor(color))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, conns.index(c))
                    # ACT-1: rich process tooltip
                    _total_conn = _proc_total.get(c.exe_name, 1)
                    _ext_conn   = _proc_external.get(c.exe_name, 0)
                    _tip = (
                        f"{c.exe_name}\n"
                        f"{c.exe_path or 'path unknown'}\n"
                        f"PID {c.pid or '—'} · {_total_conn} connection(s) · {_ext_conn} external"
                    )
                    item.setToolTip(_tip)
                self._tbl.setItem(row, col, item)

    # ── Inline detail panel ───────────────────────────────────────────────────

    def _build_group_detail(self, exe_name: str, grp_conns: list) -> QWidget:
        """Compact table of individual connections within a process group."""
        outer = QWidget()
        outer.setStyleSheet(
            f"QWidget {{ background:{BG_HOVER}; border:none; border-left:3px solid {ACCENT}; }}"
        )
        lay = QVBoxLayout(outer)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(4)

        hdr_lbl = QLabel(f"{exe_name}  —  {len(grp_conns)} connection(s)")
        hdr_lbl.setStyleSheet(
            f"font-size:11px; font-weight:bold; color:{TEXT_PRIMARY};"
            f" background:transparent; border:none;"
        )
        lay.addWidget(hdr_lbl)

        sub_tbl = QTableWidget(0, 5)
        sub_tbl.setHorizontalHeaderLabels(["Local", "Remote IP", "Port", "Status", "Country"])
        sub_tbl.verticalHeader().setVisible(False)
        sub_tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        sub_tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        sub_tbl.verticalHeader().setDefaultSectionSize(24)
        sub_tbl.setFixedHeight(min(24 * len(grp_conns) + 26, 120))
        sub_tbl.setStyleSheet(
            f"QTableWidget {{ border:none; font-size:10px; color:{TEXT_PRIMARY}; background:{BG_CARD}; }}"
            f"QHeaderView::section {{ background:{TH_BG}; color:{TH_TEXT}; font-size:10px;"
            f" font-weight:bold; padding:2px 4px; border:none; }}"
            f"QTableWidget::item:selected {{ background:{TABLE_SEL}; color:{TEXT_PRIMARY}; }}"
        )
        sub_tbl.horizontalHeader().setStretchLastSection(True)
        for c in grp_conns:
            r = sub_tbl.rowCount()
            sub_tbl.insertRow(r)
            country_str = f"{c.flag}  {c.country}" if c.flag else (c.country or "")
            for col, (val, color) in enumerate([
                (c.local_addr, TEXT_MUTED),
                (c.remote_ip or "—", TEXT_PRIMARY),
                (str(c.remote_port) if c.remote_port else "—", TEXT_MUTED),
                (c.status, _STATUS_COLOR.get(c.status, TEXT_MUTED)),
                (country_str, TEXT_SECONDARY),
            ]):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(color))
                sub_tbl.setItem(r, col, item)
        lay.addWidget(sub_tbl)
        return outer

    def _build_connection_detail(self, logical_row: int) -> QWidget:
        if logical_row >= len(self._displayed_conns):
            return QWidget()
        entry = self._displayed_conns[logical_row]
        if isinstance(entry, tuple) and entry[0] == "group":
            return self._build_group_detail(entry[1], entry[2])
        c = entry

        status_color = _STATUS_COLOR.get(c.status, TEXT_MUTED)
        is_blocked = c.exe_name in self._blocked_rules

        outer = QWidget()
        outer.setStyleSheet(
            f"QWidget {{ background:{BG_HOVER}; border:none;"
            f" border-left:3px solid {ACCENT}; }}"
        )
        lay = QHBoxLayout(outer)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(24)

        def _lbl(text: str, color: str = TEXT_PRIMARY) -> QLabel:
            l = QLabel(str(text))
            l.setStyleSheet(
                f"font-size:11px; color:{color}; background:transparent; border:none;"
            )
            return l

        def _hdr(text: str) -> QLabel:
            l = QLabel(text)
            l.setStyleSheet(
                f"font-size:10px; font-weight:bold; color:{TEXT_MUTED};"
                " background:transparent; border:none;"
            )
            return l

        # Process column
        proc = QWidget()
        proc.setStyleSheet("QWidget { background:transparent; border:none; }")
        pg = QFormLayout(proc)
        pg.setContentsMargins(0, 0, 0, 0)
        pg.setSpacing(3)
        pg.setHorizontalSpacing(12)
        pg.addRow(_hdr("Process"),  _lbl(f"{c.exe_name}  (PID {c.pid or '—'})"))
        pg.addRow(_hdr("Protocol"), _lbl(c.proto, ACCENT))
        pg.addRow(_hdr("Status"),   _lbl(c.status, status_color))
        country_str = f"{c.flag}  {c.country}" if c.flag else (c.country or "—")
        pg.addRow(_hdr("Country"),  _lbl(country_str))
        lay.addWidget(proc)

        # Address column
        addr = QWidget()
        addr.setStyleSheet("QWidget { background:transparent; border:none; }")
        ag = QFormLayout(addr)
        ag.setContentsMargins(0, 0, 0, 0)
        ag.setSpacing(3)
        ag.setHorizontalSpacing(12)
        ag.addRow(_hdr("Local"),  _lbl(c.local_addr or "—", TEXT_MUTED))
        remote = f"{c.remote_ip}:{c.remote_port}" if c.remote_ip else "—"
        ag.addRow(_hdr("Remote"), _lbl(remote))
        path_lbl = QLabel(c.exe_path or "—")
        path_lbl.setWordWrap(True)
        path_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )
        ag.addRow(_hdr("EXE Path"), path_lbl)
        lay.addLayout(ag, 1)

        # Actions column
        if is_blocked:
            btn_fw = QPushButton(f"Unblock {c.exe_name}")
            btn_fw.setStyleSheet(
                f"font-size:11px; font-weight:bold; color:white; background:{AMBER};"
                f" border:none; padding:0 12px; border-radius:4px;"
            )
            btn_fw.clicked.connect(lambda: self._toggle_block(c, True))
        else:
            btn_fw = QPushButton(f"Block {c.exe_name}")
            btn_fw.setStyleSheet(
                f"font-size:11px; font-weight:bold; color:white; background:{RED};"
                f" border:none; padding:0 12px; border-radius:4px;"
            )
            btn_fw.clicked.connect(lambda: self._toggle_block(c, False))
        btn_fw.setFixedHeight(28)

        actions = QVBoxLayout()
        actions.setSpacing(6)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addWidget(btn_fw)
        actions.addStretch()
        lay.addLayout(actions)

        return outer

    def showEvent(self, event) -> None:
        restore_column_widths(self._tbl, "connections")
        super().showEvent(event)

    def set_popover(self, popover) -> None:
        self._popover = popover

    # ── Context menu ──────────────────────────────────────────────────────────

    def _context_menu(self, pos) -> None:
        row = self._tbl.rowAt(pos.y())
        if row < 0:
            return
        item = self._tbl.item(row, 0)
        if not item:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None or idx >= len(self._displayed_conns):
            return
        c = self._displayed_conns[idx]

        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; font-size:11px; padding:4px; }}"
            f"QMenu::item {{ padding:5px 20px; }}"
            f"QMenu::item:selected {{ background:{BG_HOVER}; }}"
        )

        is_blocked = c.exe_name in self._blocked_rules
        if is_blocked:
            act_fw = menu.addAction(f"🔓  Unblock {c.exe_name}")
        else:
            act_fw = menu.addAction(f"🔒  Block {c.exe_name} (add firewall rule)")

        act_device = None
        if c.remote_ip and self._popover:
            menu.addSeparator()
            act_device = menu.addAction(f"Device Info — {c.remote_ip}")

        menu.addSeparator()
        act_copy_ip  = menu.addAction("Copy Remote IP")
        act_copy_exe = menu.addAction("Copy Process Name")
        act_copy_path = menu.addAction("Copy EXE Path")

        action = menu.exec(self._tbl.viewport().mapToGlobal(pos))
        if action == act_fw:
            self._toggle_block(c, is_blocked)
        elif act_device and action == act_device:
            from PyQt6.QtGui import QCursor
            self._popover.show_for(c.remote_ip, QCursor.pos())
        elif action == act_copy_ip:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(c.remote_ip or "")
        elif action == act_copy_exe:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(c.exe_name)
        elif action == act_copy_path:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(c.exe_path or "")

    def _get_visible_conns(self) -> list:
        """Return the filtered connection list currently shown in the table."""
        text        = self._search.text().strip().lower()
        proto_sel   = self._proto_filter.currentText()
        show_local  = self._chk_local.isChecked()
        visible = []
        for c in self._connections:
            if proto_sel != "All Protocols" and c.proto != proto_sel:
                continue
            if not show_local and c.is_local:
                continue
            if text:
                haystack = " ".join([
                    c.exe_name, str(c.pid), c.remote_ip,
                    str(c.remote_port), c.status, c.country, c.exe_path,
                ]).lower()
                if text not in haystack:
                    continue
            visible.append(c)
        return visible

    # ── Block / Unblock ───────────────────────────────────────────────────────

    def _toggle_block(self, conn, currently_blocked: bool) -> None:
        if currently_blocked:
            ok, msg = _unblock_process(conn.exe_name)
            self._status_lbl.setText(f"{'✓' if ok else '⚠'}  {msg}")
            self._load_blocked_rules()
            self._apply_filters()
            return

        # Block path — confirmation dialog
        dlg = QDialog(self)
        dlg.setWindowTitle("Confirm Firewall Block")
        dlg.setMinimumWidth(420)
        dlg.setStyleSheet(f"background:{BG_DARK}; color:{TEXT_PRIMARY};")
        lay = QVBoxLayout(dlg)
        lay.setSpacing(12)
        lay.setContentsMargins(16, 16, 16, 12)

        msg_lbl = QLabel(
            f"Add an outbound-deny Windows Firewall rule for:\n\n"
            f"  Process:  {conn.exe_name}\n"
            f"  Path:     {conn.exe_path or 'unknown'}\n\n"
            f"This will block ALL outbound traffic from this process.\n"
            f"You can remove the rule at any time via the Unblock action."
        )
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent;"
        )
        lay.addWidget(msg_lbl)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Block Process")
        btns.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(
            f"background:{RED}; color:white; border:none;"
            f" border-radius:3px; padding:5px 14px; font-size:11px; font-weight:bold;"
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        ok, msg = _block_process(conn.exe_path, conn.exe_name)
        if ok:
            self._undo_exe = conn.exe_name
            self._undo_lbl.setText(f"✓  Blocked {conn.exe_name}")
            self._undo_bar.setVisible(True)
            self._undo_timer.start(10_000)
        else:
            self._status_lbl.setText(f"⚠  {msg}")
        self._load_blocked_rules()
        self._apply_filters()

    def _do_undo_block(self) -> None:
        """Undo the most recent block action within the 10-second window."""
        if not self._undo_exe:
            return
        exe = self._undo_exe
        ok, msg = _unblock_process(exe)
        self._hide_undo_bar()
        self._status_lbl.setText(f"{'✓' if ok else '⚠'}  Undo: {msg}")
        self._load_blocked_rules()
        self._apply_filters()

    def _hide_undo_bar(self) -> None:
        self._undo_timer.stop()
        self._undo_bar.setVisible(False)
        self._undo_exe = ""

    # ── Blocked rules panel ───────────────────────────────────────────────────

    def _load_blocked_rules(self) -> None:
        self._blocked_rules = _get_blocked_rules()
        count = len(self._blocked_rules)
        if count:
            self._blocked_lbl.setText(
                "  |  ".join(f"🔒 {r}" for r in self._blocked_rules)
            )
        else:
            self._blocked_lbl.setText("No active blocks")
        self._lbl_blocked.set_value(count)
        # Repaint action column
        self._apply_filters()

    # ── Auto-refresh toggle ───────────────────────────────────────────────────

    @pyqtSlot(bool)
    def _on_auto_toggled(self, checked: bool) -> None:
        if checked:
            self._auto_timer.start()
        else:
            self._auto_timer.stop()
