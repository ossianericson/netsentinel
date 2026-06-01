"""
Main Dashboard — NetSentinel network security scanner and monitor.
"""

import datetime
import html
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QByteArray, QEasingCurve, QObject, QPoint, QPropertyAnimation, QRect, QSettings, QSize, QTimer, QVariantAnimation, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.command_palette import CommandPalette
from ui.help import _PAGE_HELP
from ui.live_graph import LiveGraphWidget
from ui.npcap_banner import NpcapMissingBanner
from ui.styles import (
    ACCENT, ACCENT_DARK, ACCENT_LITE, ADMIN_WARN_FG,
    ADMIN_WARN_HOVER, AMBER, AMBER_BG, AUDIT_RED,
    BG_ALT_ROW, BG_CARD, BG_DARK, BG_HOVER,
    BLUE, BORDER, BORDER_MED, BTN_HOVER_BG,
    CARD_HDR_BORDER, CARD_RADIUS, CHART_PURPLE, CRITICAL,
    GRADE_A_BG, GRADE_B_BG, GRADE_B_FG, GRADE_C_BG,
    GRADE_D_BG, GRADE_F_BG, GRADE_F_FG, GREEN,
    GREEN_BG, MAIN_STYLE, NAV_BAR, NAV_DIVIDER,
    PRO_BANNER_BORDER, PRO_WARN_BG, RED, RED_BG,
    RISK_BG, RISK_COLORS, SIDEBAR_BG, SIDEBAR_HOVER,
    SIDEBAR_ITEM_FG, SIDEBAR_SECTION_BG, SIDEBAR_SECTION_FG, SIDEBAR_SEL_BG,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, UPDATE_BAR_BG,
    UPDATE_BAR_BORDER, UPDATE_BAR_FG, WHITE,
)
from modules.utils import get_offenders_path, is_admin


def _color_for_level(level: str) -> str:
    return RISK_COLORS.get(level.upper(), TEXT_SECONDARY)


def _bg_for_level(level: str) -> str:
    return RISK_BG.get(level.upper(), BG_CARD)


class RiskBadge(QLabel):
    def __init__(self, level: str, parent=None):
        super().__init__(level.upper(), parent)
        color = _color_for_level(level)
        bg    = _bg_for_level(level)
        self.setStyleSheet(
            f"color:{color}; background:{bg}; border:1px solid {color};"
            "border-radius:3px; padding:1px 8px; font-weight:bold; font-size:10px;"
        )
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class VerdictPanel(QFrame):
    """Traffic-light coloured plain-English verdict box."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("verdictFrame")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._title = QLabel("Overall Verdict")
        self._title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))

        self._text = QLabel("Run a scan to see results.")
        self._text.setObjectName("verdictText")
        self._text.setWordWrap(True)
        self._text.setFont(QFont("Segoe UI", 11))
        self._text.setTextFormat(Qt.TextFormat.PlainText)

        self._layout.addWidget(self._title)
        self._layout.addWidget(self._text)
        self._set_level("UNKNOWN")

    def _set_level(self, level: str):
        color = _color_for_level(level)
        bg    = _bg_for_level(level)
        self.setStyleSheet(
            f"QFrame#verdictFrame {{ background:{bg}; border-left:4px solid {color};"
            f"border-radius:0px; border-top:1px solid {BORDER};"
            f"border-right:1px solid {BORDER}; border-bottom:1px solid {BORDER}; }}"
        )
        self._title.setStyleSheet(f"color:{color}; font-weight:bold; padding:6px 12px 2px 12px;")
        self._text.setStyleSheet(f"color:{TEXT_PRIMARY}; padding:2px 12px 8px 12px; font-size:11px;")

    def update(self, text: str, level: str = "UNKNOWN"):
        self._set_level(level)
        self._text.setText(text)


# ─── Module Tab Helpers (defined in ui/tabs.py, re-exported here) ────────────
from ui.tabs import (
    _make_scroll_area, _table, _add_row, _add_skeleton_rows,
    _empty_state_widget, _error_state_widget, _make_card, _page_header,
)


# --- Activity-Rail Navigation widgets (extracted to ui/nav/rail.py) -----------
from ui.nav.rail import (
    _LUCIDE, _make_nav_icon, _NavEntry,
    _RailButton, _FlyoutItem, _FlyoutPanel,
    _CanvasClickFilter, _ClickLabel, _SmoothProgressBar,
)


# _PAGE_HELP is defined in ui/help.py and imported at the top of this file.


# Pages that auto-expand the tip bar on first visit (they have non-obvious interactions)
_AUTO_HELP_PAGES: frozenset[str] = frozenset({
    "Network Logger", "Lab Mode", "Protocol Visualizer",
    "Automation Hooks", "MQTT / Home Assistant", "TLS & Exposure",
    "Service Heartbeat", "SNMP Trap Receiver", "Syslog Viewer",
    "IoT Behaviour", "Scheduled Scans",
})


def _make_chart_window(fig) -> "QMainWindow":
    from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout
    from PyQt6.QtCore import Qt as _Qt
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

    win = QMainWindow()
    win.setWindowTitle("Network Logger — RTT Chart")
    win.setAttribute(_Qt.WidgetAttribute.WA_DeleteOnClose)
    win.resize(1400, 820)

    container = QWidget()
    lay = QVBoxLayout(container)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)

    canvas = FigureCanvasQTAgg(fig)

    try:
        from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
    except ImportError:
        from matplotlib.backends.backend_qt import NavigationToolbar2QT

    toolbar = NavigationToolbar2QT(canvas, win)
    win.addToolBar(toolbar)
    lay.addWidget(canvas)
    win.setCentralWidget(container)
    canvas.draw()
    return win


# ─── Main Window ─────────────────────────────────────────────────────────────

from ui.scan_wiring import ScanResultMixin
from ui.header import AppHeaderMixin
from ui.tabs import TabBuilderMixin



class Dashboard(ScanResultMixin, AppHeaderMixin, TabBuilderMixin, QMainWindow):
    _update_available         = pyqtSignal(str)
    global_time_range_changed = pyqtSignal(float)  # hours: float

    def __init__(self, store=None, alert_engine=None, notif_router=None, maint_manager=None):
        super().__init__()
        self._store        = store          # MetricStore | None
        self._alert_engine = alert_engine   # AlertEngine | None
        self._notif_router = notif_router   # NotificationRouter | None
        self._maint_manager = maint_manager # MaintenanceWindowManager | None
        self._global_hours = 24.0
        self.setWindowTitle("NetSentinel  —  Network Security Scanner & Monitor")
        self.setMinimumSize(900, 600)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setStyleSheet(MAIN_STYLE)
        self._maximize_btn = None   # set by _build_header; updated in changeEvent
        self._pre_maximize_geo: "QRect | None" = None  # saved before showMaximized()

        # Window icon
        from pathlib import Path as _Path
        from PyQt6.QtGui import QIcon as _QIcon
        import sys as _sys
        _base = _Path(_sys._MEIPASS) if getattr(_sys, "frozen", False) else _Path(__file__).parent.parent
        for _ico in ("assets/icons/NetSentinel.ico", "NetSentinel.ico", "icon.ico"):
            _p = _base / _ico
            if _p.exists():
                self.setWindowIcon(_QIcon(str(_p)))
                break

        self._offenders_path = get_offenders_path()
        self._admin = is_admin()

        # Scan results cache
        self._m1_result = None
        self._m2_result = None
        self._m3_result = None
        self._m4_result = None
        self._m5_result = None

        # Mesh enrichment — populated when MeshRouterPage scan completes
        self._mesh_enrichment: dict = {}   # normalised MAC → MeshClient

        # Plugin enrichment — one entry per plugin path; merged in _apply_mesh_enrichment
        # dict[path, dict[mac, client_dict]] — supports multiple router/AP plugins
        self._plugin_enrichments: dict[str, dict] = {}
        self._plugin_nodes:       dict[str, list] = {}  # path → [{name,mac,role}]
        self._plugin_hardware_name: str = ""  # name of last-run plugin

        # M1 satellite grouping state
        self._m1_sat_expanded: dict = {}   # node_name → bool (default False = collapsed)
        self._m1_grouping_active: bool = False

        # Active workers
        self._workers = []
        self._active_count = 0
        self._prescan_worker = None
        self._diag_worker = None
        self._logger_worker = None

        # Cached results
        self._net_info: dict = {}
        self._wan_ip:   str  = ""   # public WAN IP, fetched once per session after scan
        self._diag_result = None
        self._last_scan_devices: list = []    # for NetworkDocPage port_data accumulation
        self._port_data_cache:   dict = {}    # {ip: [port_dict, ...]} across scan types
        self._auto_report_pending:   bool = False  # True while full-report run is in progress
        self._auto_report_scan_done: bool = False
        self._auto_report_diag_done: bool = False
        self._pending_benchmark:     bool = False  # True when Grade My Network triggered a scan
        self._pending_isp_report:    bool = False  # True when ISP Report triggered diagnostics

        # Network pulse bar state
        self._last_scan_time:   float = 0.0  # epoch set on each m1 result
        self._last_log_status:  str   = ""   # "OK" | "SLOW" | "FAIL" | ""

        # Page transition animation
        self._fade_anim: QPropertyAnimation | None = None

        # Graph update timer
        self._graph_timer = QTimer()
        self._graph_timer.setInterval(500)
        self._graph_timer.timeout.connect(self._refresh_graph)

        # Weekly digest check — fires once per hour to see if a digest should be sent (RECUR-2)
        self._digest_timer = QTimer()
        self._digest_timer.setInterval(3_600_000)  # 1 hour
        self._digest_timer.timeout.connect(self._check_weekly_digest)
        self._digest_timer.start()
        QTimer.singleShot(5000, self._check_weekly_digest)

        # HEALTH-2: offline/no-LAN detection — 3 consecutive failures show amber banner
        self._lan_fail_count: int = 0
        self._lan_check_worker = None
        self._lan_check_timer = QTimer()
        self._lan_check_timer.setInterval(30_000)   # 30 s
        self._lan_check_timer.timeout.connect(self._check_lan_connectivity)
        self._lan_check_timer.start()
        QTimer.singleShot(8000, self._check_lan_connectivity)

        # SCHED-1: scheduled full scan — 60s polling timer checks if next_ts has passed
        self._sched_scan_timer = QTimer()
        self._sched_scan_timer.setInterval(60_000)  # check every minute
        self._sched_scan_timer.timeout.connect(self._check_scheduled_scan)
        self._sched_scan_timer.start()
        QTimer.singleShot(10_000, self._check_scheduled_scan)

        # System tray guardian
        self._tray_quit = False   # set True when quitting via tray menu
        from ui.system_tray import SystemTrayManager
        self._tray_manager = SystemTrayManager(self)
        self._tray_manager.setup()
        # Keep legacy _tray_icon reference so _show_alert_toast still works
        self._tray_icon = self._tray_manager._tray

        # Ctrl+Q always quits immediately regardless of tray setting
        from PyQt6.QtGui import QShortcut, QKeySequence
        _quit_sc = QShortcut(QKeySequence("Ctrl+Q"), self)
        _quit_sc.activated.connect(self._quit_app)

        # Ctrl+F focuses the sidebar search box from anywhere in the app
        _search_sc = QShortcut(QKeySequence("Ctrl+F"), self)
        _search_sc.activated.connect(self._focus_nav_search)

        # Ctrl+K opens the command palette
        _palette_sc = QShortcut(QKeySequence("Ctrl+K"), self)
        _palette_sc.activated.connect(self._open_command_palette)

        # Esc closes the flyout panel in Standard/Pro mode
        _esc_sc = QShortcut(QKeySequence("Escape"), self)
        _esc_sc.activated.connect(self._on_canvas_click)

        # ? — shortcut overlay
        _help_sc = QShortcut(QKeySequence("?"), self)
        _help_sc.activated.connect(self._open_shortcut_overlay)

        # Ctrl+, — Settings
        _settings_sc = QShortcut(QKeySequence("Ctrl+,"), self)
        _settings_sc.activated.connect(self._open_settings_dialog)

        # Ctrl+L — Log Hub
        _loghub_sc = QShortcut(QKeySequence("Ctrl+L"), self)
        _loghub_sc.activated.connect(lambda: self._nav_rail_go_to("Network Logger"))

        # Pinned pages — persisted across sessions
        self._nav_pinned_labels: set = self._load_pinned_labels()
        self._nav_label_to_widget: dict = {}
        self._nav_history: list = []  # NAV-5: back-stack; direct rail clicks clear it

        # ── Rail nav state ────────────────────────────────────────────────────
        self._nav_admin_rows: set = set()   # rows requiring admin — get ·admin badge
        self._nav_audit_rows: set = set()   # Security Audit section rows — rendered in RED
        self._nav_action_rows: dict = {}
        self._nav_sections: list = []        # [{name, icon, entries:[_NavEntry]}]
        self._nav_open_section: str = ""     # name of currently expanded flyout section
        self._nav_rail_buttons: dict = {}    # section_name -> _RailButton
        self._nav_page_to_section: dict = {} # page_label -> section_name
        self._nav_current_page_label: str = ""

        self._build_ui()

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top application bar (dark navy)
        root.addWidget(self._build_header())

        # Update notification bar — hidden until background check finds a newer release
        self._update_bar = self._build_update_bar()
        self._update_bar.setVisible(False)
        self._update_available.connect(self._on_update_available)
        root.addWidget(self._update_bar)

        # Main area: sidebar+content fills window; verdict strip hidden until scan
        _main = self._build_tabs()
        _verdict_area = self._build_verdict_area()
        _verdict_area.setVisible(False)
        # Auto-show verdict strip on first scan result without touching callsites
        _orig_vu = self._verdict.update
        def _vu(text: str, level: str = "UNKNOWN", _ov=_orig_vu):
            _verdict_area.setVisible(True)
            _ov(text, level)
        self._verdict.update = _vu  # type: ignore[method-assign]
        root.addWidget(_main, 1)
        root.addWidget(_verdict_area)

        # Status bar
        self._status_bar = QStatusBar()
        self._progress = _SmoothProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setFixedHeight(4)
        self._progress.setVisible(False)
        self._status_bar.addPermanentWidget(self._progress)

        # ── Network pulse widgets (permanent, right-aligned) ─────────────────
        _pulse_base = (
            "QLabel { padding: 0 8px; font-size: 11px; background: transparent;"
            f" border: none; color: {TEXT_MUTED}; }}"
            f"QLabel:hover {{ color: {WHITE}; }}"
        )
        _pulse_sep = QFrame()
        _pulse_sep.setFrameShape(QFrame.Shape.VLine)
        _pulse_sep.setFixedWidth(1)
        _pulse_sep.setStyleSheet(f"background: {NAV_DIVIDER}; border: none;")

        self._pulse_online_lbl  = _ClickLabel("○  —")
        self._pulse_devices_lbl = _ClickLabel("■  —")
        self._pulse_scan_lbl    = _ClickLabel("Last scan: —")
        self._pulse_logger_lbl  = _ClickLabel("○  Logger off")
        for _l in (self._pulse_online_lbl, self._pulse_devices_lbl,
                   self._pulse_scan_lbl, self._pulse_logger_lbl):
            _l.setStyleSheet(_pulse_base)
            _l.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pulse_online_lbl.setToolTip(
            "Connection status (last logger result)\nClick to open Connectivity Tests"
        )
        self._pulse_devices_lbl.setToolTip(
            "Number of devices seen in the last scan\nClick to open Overview"
        )
        self._pulse_scan_lbl.setToolTip(
            "Time since the last network scan completed\nClick to open Overview"
        )
        self._pulse_logger_lbl.setToolTip(
            "Network logger state — starts automatically on first launch\nClick to open Logs"
        )

        self._pulse_online_lbl.clicked.connect(
            lambda: self._nav_rail_go_to("What's Wrong?"))
        self._pulse_devices_lbl.clicked.connect(
            lambda: self._nav_rail_go_to("Overview"))
        self._pulse_scan_lbl.clicked.connect(
            lambda: self._nav_rail_go_to("Overview"))
        self._pulse_logger_lbl.clicked.connect(
            lambda: self._nav_rail_go_to("Network Logger"))

        self._status_bar.addPermanentWidget(_pulse_sep)
        self._status_bar.addPermanentWidget(self._pulse_online_lbl)
        self._status_bar.addPermanentWidget(self._pulse_devices_lbl)
        self._status_bar.addPermanentWidget(self._pulse_scan_lbl)
        self._status_bar.addPermanentWidget(self._pulse_logger_lbl)

        self.setStatusBar(self._status_bar)
        self._set_status("Ready.")

        # 10-second pulse timer — keeps status-bar indicators current
        self._pulse_timer = QTimer()
        self._pulse_timer.setInterval(10_000)
        self._pulse_timer.timeout.connect(self._refresh_pulse_bar)
        self._pulse_timer.start()
        # Load network info in background on startup
        self._refresh_network_info()
        # Silent background update check
        self._start_update_check()
        # Restore full settings (mode, scan hosts, etc.) after UI is built
        self._restore_settings()
        # Install resize grips for all 8 edges/corners (frameless window)
        self._install_edge_grips()

    def _build_mode_bar(self) -> QWidget:
        """Mode-switcher pill — now built inline inside the sidebar in _build_tabs().
        This method is kept as a no-op for compatibility."""
        from PyQt6.QtWidgets import QWidget as _W
        return _W()  # empty placeholder; never added to the layout

    # ── Admin pill badge delegate ────────────────────────────────────────────

    class _NavAdminDelegate(
        __import__("PyQt6.QtWidgets", fromlist=["QStyledItemDelegate"]).QStyledItemDelegate
    ):
        """Paints a small red 'admin' pill badge on the right of admin nav rows."""

        _BADGE = "admin"
        _H     = 13
        _PAD   = 4
        _GAP   = 6

        def __init__(self, admin_rows: set, color: str, parent=None):
            from PyQt6.QtWidgets import QStyledItemDelegate
            super().__init__(parent)
            self._admin_rows    = admin_rows
            self._color         = color
            self._count_badges: dict = {}  # row → (count_str, bg_color)

        def set_count_badge(self, row: int, count: int, color: str) -> None:
            if count > 0:
                self._count_badges[row] = (str(count), color)
            else:
                self._count_badges.pop(row, None)

        def _paint_pill(self, painter, option, text: str, bg: str, right_offset: int) -> int:
            """Paint a pill badge; returns the width consumed (for stacking badges)."""
            from PyQt6.QtCore import Qt, QRect
            from PyQt6.QtGui import QColor, QFont, QPainter
            f = QFont("Segoe UI", 7)
            f.setBold(True)
            painter.setFont(f)
            fm  = painter.fontMetrics()
            bw  = fm.horizontalAdvance(text) + self._PAD * 2
            bx  = option.rect.right() - right_offset - bw - self._GAP
            by  = option.rect.center().y() - self._H // 2
            rect = QRect(bx, by, bw, self._H)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor(bg))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 3, 3)
            painter.setPen(QColor(WHITE))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
            return bw + self._GAP

        def paint(self, painter, option, index):
            from PyQt6.QtWidgets import QStyle, QStyleOptionViewItem
            from PyQt6.QtGui import QPainter
            opt = QStyleOptionViewItem(option)
            opt.state &= ~QStyle.StateFlag.State_HasFocus
            super().paint(painter, opt, index)
            row = index.row()
            painter.save()
            right_offset = 0
            if row in self._admin_rows:
                right_offset += self._paint_pill(painter, option, self._BADGE, self._color, right_offset)
            if row in self._count_badges:
                text, bg = self._count_badges[row]
                self._paint_pill(painter, option, text, bg, right_offset)
            painter.restore()

    # ── Sidebar navigation helpers ───────────────────────────────────────────
    # Data model (initialised in _build_tabs):
    #   _nav_item_icons[row]    str  — emoji shown in icon-only mode
    #   _nav_item_labels[row]   str  — full label text
    #   _nav_header_rows        set  — rows that are section or sub-group headers
    #   _nav_section_groups[r]  dict — {children:[rows], collapsed:bool, level:0|1}
    #   _nav_current_section    int  — row of last section header added
    #   _nav_current_subgroup   int  — row of last sub-group header (-1 = none)
    #   _nav_collapsed          bool — sidebar in icon-only (narrow) mode

    def _nav_add_section(self, label: str, icon: str = "■",
                         collapsed_by_default: bool = False,
                         fg_color: str = None) -> int:
        """Add a collapsible section header row."""
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QColor, QFont as _QFont, QBrush
        # Insert 8px air-gap + 1px divider before every non-first section
        if self._nav.count() > 0:
            _div = QListWidgetItem()
            _div.setFlags(Qt.ItemFlag.NoItemFlags)
            _div.setSizeHint(QSize(0, 9))
            _div.setBackground(QBrush(QColor(BORDER)))
            self._nav.addItem(_div)
            self._nav_separators.add(self._nav.count() - 1)
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)   # clickable but not selectable
        item.setSizeHint(QSize(0, 28))
        item.setBackground(QBrush(QColor(SIDEBAR_SECTION_BG)))
        f = _QFont("Segoe UI", 9)
        f.setBold(True)
        item.setFont(f)
        self._nav.addItem(item)
        row = self._nav.count() - 1
        self._nav_item_icons[row]    = icon
        self._nav_item_labels[row]   = label
        self._nav_header_rows.add(row)
        self._nav_section_groups[row] = {
            "children": [], "collapsed": collapsed_by_default, "level": 0,
            "fg_color": fg_color,
        }
        self._nav_current_section  = row
        self._nav_current_subgroup = -1
        self._nav_separators.add(row)          # legacy compat
        self._nav_refresh_item_text(row)
        return row

    def _nav_add_subgroup(self, label: str, icon: str = "▸",
                          collapsed_by_default: bool = True) -> int:
        """Add an indented collapsible sub-group header under the current section."""
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QColor, QBrush
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        item.setSizeHint(QSize(0, 26))
        item.setBackground(QBrush(QColor(SIDEBAR_SECTION_BG)))
        self._nav.addItem(item)
        row = self._nav.count() - 1
        self._nav_item_icons[row]    = icon
        self._nav_item_labels[row]   = label
        self._nav_header_rows.add(row)
        self._nav_section_groups[row] = {
            "children": [], "collapsed": collapsed_by_default, "level": 1
        }
        self._nav_section_groups[self._nav_current_section]["children"].append(row)
        self._nav_separators.add(row)          # legacy compat
        self._nav_current_subgroup = row
        self._nav_refresh_item_text(row)
        return row

    def _nav_add_page(self, icon: str, label: str, widget: QWidget) -> int:
        """Add a page entry to the sidebar and the stacked widget. Returns nav row index."""
        from PyQt6.QtCore import QSize
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item.setSizeHint(QSize(0, 30))
        self._nav.addItem(item)
        page_idx = self._stack.addWidget(widget)
        row = self._nav.count() - 1
        self._nav_row_to_page[row] = page_idx
        self._nav_item_icons[row]  = icon
        self._nav_item_labels[row] = label
        self._nav_label_to_widget[label] = widget
        parent = (self._nav_current_subgroup if self._nav_current_subgroup >= 0
                  else self._nav_current_section)
        if parent >= 0:
            self._nav_section_groups[parent]["children"].append(row)
        self._nav_refresh_item_text(row)
        return row

    def _nav_add_alias(self, icon: str, label: str, page_idx: int) -> int:
        """Add a nav entry that points to an already-registered page stack index.

        Use this to expose the same page in multiple sidebar locations (e.g. the
        Pinned quick-access section and its canonical grouped position) without
        adding the widget to QStackedWidget a second time.
        """
        from PyQt6.QtCore import QSize
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item.setSizeHint(QSize(0, 30))
        self._nav.addItem(item)
        row = self._nav.count() - 1
        self._nav_row_to_page[row] = page_idx
        self._nav_item_icons[row]  = icon
        self._nav_item_labels[row] = label
        parent = (self._nav_current_subgroup if self._nav_current_subgroup >= 0
                  else self._nav_current_section)
        if parent >= 0:
            self._nav_section_groups[parent]["children"].append(row)
        self._nav_refresh_item_text(row)
        return row

    def _nav_set_page(self, nav_row: int):
        if nav_row not in self._nav_row_to_page:
            return
        if self._fade_anim is not None and self._fade_anim.state() == QPropertyAnimation.State.Running:
            self._fade_anim.stop()
            w = self._stack.currentWidget()
            if w:
                w.setGraphicsEffect(None)
            self._fade_anim = None
        self._stack.setCurrentIndex(self._nav_row_to_page[nav_row])
        label = self._nav_item_labels.get(nav_row, "")
        if label:
            self.setWindowTitle(f"NetSentinel — {label}")

    def _nav_crossfade_to(self, target_widget) -> None:
        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        from PyQt6.QtCore import QPropertyAnimation, QEasingCurve

        if self._fade_anim is not None and self._fade_anim.state() == QPropertyAnimation.State.Running:
            self._fade_anim.stop()
            cur = self._stack.currentWidget()
            if cur:
                cur.setGraphicsEffect(None)
            self._fade_anim = None

        if self._stack.currentWidget() is target_widget:
            return

        cur = self._stack.currentWidget()
        if cur is None:
            self._stack.setCurrentWidget(target_widget)
            return

        effect = QGraphicsOpacityEffect(cur)
        cur.setGraphicsEffect(effect)

        fade_out = QPropertyAnimation(effect, b"opacity", cur)
        fade_out.setDuration(80)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.Type.InQuad)
        self._fade_anim = fade_out

        def _on_fade_out_done():
            cur.setGraphicsEffect(None)
            self._stack.setCurrentWidget(target_widget)
            in_effect = QGraphicsOpacityEffect(target_widget)
            target_widget.setGraphicsEffect(in_effect)
            fade_in = QPropertyAnimation(in_effect, b"opacity", target_widget)
            fade_in.setDuration(80)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)
            fade_in.setEasingCurve(QEasingCurve.Type.OutQuad)
            fade_in.finished.connect(lambda: target_widget.setGraphicsEffect(None))
            self._fade_anim = fade_in
            fade_in.start()

        fade_out.finished.connect(_on_fade_out_done)
        fade_out.start()

    def _nav_refresh_item_text(self, row: int):
        """Rewrite displayed text for a nav row based on collapsed/expanded mode."""
        item = self._nav.item(row)
        if item is None:
            return
        icon  = self._nav_item_icons.get(row, "")
        label = self._nav_item_labels.get(row, "")
        if self._nav_collapsed:
            item.setText(icon)
            if row not in self._nav_header_rows:
                item.setToolTip(label)
        elif row in self._nav_section_groups:
            grp   = self._nav_section_groups[row]
            arrow = "\u25b6" if grp["collapsed"] else "\u25bc"
            from PyQt6.QtGui import QColor
            if grp["level"] == 0:
                item.setText(f" {arrow}  {label.upper()}")
            else:
                item.setText(f"     {arrow}  {label}")
            _fg = grp.get("fg_color") or SIDEBAR_SECTION_FG
            item.setForeground(QColor(_fg))
            item.setToolTip("")
        else:
            star = " ★" if label in self._nav_pinned_labels else ""
            item.setText(f"  {icon}  {label}{star}")
            item.setToolTip("")
            from PyQt6.QtGui import QColor
            if row in self._nav_audit_rows:
                item.setForeground(QColor(AUDIT_RED))
            else:
                item.setForeground(QColor(SIDEBAR_ITEM_FG))

    def _nav_toggle_section(self, header_row: int):
        """Collapse or expand a section / sub-group header."""
        if header_row not in self._nav_section_groups:
            return
        grp = self._nav_section_groups[header_row]
        grp["collapsed"] = not grp["collapsed"]
        self._nav_refresh_item_text(header_row)
        self._nav_apply_section_visibility(header_row, grp["collapsed"])
        # Persist so the user's preference survives restarts
        from PyQt6.QtCore import QSettings
        _s = QSettings(str(self._settings_path()), QSettings.Format.IniFormat)
        _s.setValue(f"nav/group_{header_row}_collapsed", str(grp["collapsed"]))

    def _nav_apply_section_visibility(self, header_row: int, hide: bool):
        """Show/hide direct children; recurse into sub-group children."""
        for child_row in self._nav_section_groups[header_row]["children"]:
            child_item = self._nav.item(child_row)
            if child_item:
                child_item.setHidden(hide)
            if child_row in self._nav_section_groups:
                child_grp    = self._nav_section_groups[child_row]
                effective_hide = hide or child_grp["collapsed"]
                for sub_row in child_grp["children"]:
                    sub_item = self._nav.item(sub_row)
                    if sub_item:
                        sub_item.setHidden(effective_hide)

    @pyqtSlot()
    def _toggle_sidebar(self):
        """Show/hide the rail sidebar (VSCode-style: toggle entire panel)."""
        visible = not self._nav_rail_panel.isVisible()
        self._nav_rail_panel.setVisible(visible)
        self._sidebar_toggle_btn.setText("▶" if not visible else "◀")

    def _focus_nav_search(self) -> None:
        """Expand sidebar if collapsed, then focus the search box."""
        if self._nav_collapsed:
            self._toggle_sidebar()
        self._nav_search.setFocus()
        self._nav_search.selectAll()

    @pyqtSlot(str)
    def _on_nav_search_changed(self, text: str):
        """Filter sidebar items to those whose label contains text."""
        text = text.strip().lower()
        if not text:
            # Restore visibility: show all then re-hide collapsed sections
            for row in range(self._nav.count()):
                item = self._nav.item(row)
                if item:
                    item.setHidden(False)
            for hrow, grp in self._nav_section_groups.items():
                if grp["collapsed"]:
                    self._nav_apply_section_visibility(hrow, True)
            return
        for row in range(self._nav.count()):
            if row in self._nav_header_rows:
                continue
            label = self._nav_item_labels.get(row, "").lower()
            item  = self._nav.item(row)
            if item:
                item.setHidden(text not in label)

    def _on_nav_item_clicked(self, item):
        """Toggle section/sub-group headers when clicked."""
        row = self._nav.row(item)
        if row in self._nav_section_groups:
            self._nav_toggle_section(row)

    @pyqtSlot(int)
    def _on_nav_row_changed(self, row: int):
        """Navigate to the page for the selected nav row."""
        if row < 0 or row in self._nav_header_rows:
            return
        # Action rows trigger a callable instead of navigating
        if row in self._nav_action_rows:
            self._nav_action_rows[row]()
            return
        self._nav_set_page(row)
        # Reset tray badge when user views any page (they are attending to the app)
        if hasattr(self, "_tray_manager"):
            self._tray_manager.reset_badge()

    def _nav_go_to(self, label: str) -> None:
        """Programmatically navigate to the page with the given rail label."""
        self._nav_rail_go_to(label)

    def _open_isp_from_home(self) -> None:
        self._nav_rail_go_to("Network Health Report")

    def _rebuild_nav_for_mode(self) -> None:
        """Clear all nav state and rebuild the full Pro rail."""
        # ── Reset flat-nav state ───────────────────────────────────────────────
        self._nav.clear()
        self._nav_row_to_page.clear()
        self._nav_item_icons.clear()
        self._nav_item_labels.clear()
        self._nav_header_rows.clear()
        self._nav_section_groups.clear()
        self._nav_separators.clear()
        self._nav_action_rows.clear()
        self._nav_admin_rows.clear()
        self._nav_audit_rows.clear()
        self._nav_current_section  = -1
        self._nav_current_subgroup = -1
        # Reset compat refs so methods that check them don't crash
        self._adv_tab_index_adv = -1
        self._adv_tab_index_mtr = -1

        # ── Reset rail-nav state ───────────────────────────────────────────────
        self._nav_sections.clear()
        self._nav_page_to_section.clear()
        self._nav_open_section = ""
        if hasattr(self, "_nav_flyout") and self._nav_flyout.maximumWidth() > 0:
            self._nav_flyout.close_panel()

        # ── Sidebar panel — rail is permanent, flat panel zeroed out ─────────────
        # setFixedWidth(0) removes the flat panel's contribution to the container's
        # max-width, letting the flyout expand freely to its full 260 px.
        self._nav_flat_panel.setFixedWidth(0)
        self._nav_flat_panel.setVisible(False)
        self._nav_rail_panel.setVisible(True)

        # ── Build nav content — always the full Pro set ───────────────────────
        self._build_pro_nav()

        # ── Inject Pinned section at the top if user has pins ─────────────────
        # _build_pro_nav populates _nav_label_to_widget so widget lookups work here
        # NAV-3: ≤4 pins → individual direct-nav buttons with visible labels on rail
        #        >4 pins → single "Pinned" flyout section (preserves existing behaviour)
        if self._nav_pinned_labels:
            _pinned_entries = []
            for _lbl in sorted(self._nav_pinned_labels):
                _w = self._nav_label_to_widget.get(_lbl)
                if _w is not None:
                    _pinned_entries.append(_NavEntry(
                        label=_lbl, page=_w,
                        admin_required=False, audit_item=False, pinned=True,
                    ))
            if _pinned_entries and len(_pinned_entries) > 4:
                self._nav_sections.insert(0, {
                    "name": "Pinned", "icon": "pin", "entries": _pinned_entries,
                })
            # ≤4 pins: stored separately; _nav_finalize_rail renders them as direct buttons
            self._nav_direct_pins: list = _pinned_entries if len(_pinned_entries) <= 4 else []
        else:
            self._nav_direct_pins = []

        # ── Finalise rail and restore last-used section (VSCode style) ────────
        self._nav_finalize_rail()
        _qs = QSettings(str(self._settings_path()), QSettings.Format.IniFormat)
        _last = _qs.value("nav/last_section", "")
        _open = _last if any(s["name"] == _last for s in self._nav_sections) \
                else (self._nav_sections[0]["name"] if self._nav_sections else "")
        if _open:
            self._nav_rail_toggle(_open)
            _sec = next((s for s in self._nav_sections if s["name"] == _open), None)
            if _sec and _sec["entries"]:
                self._nav_rail_go_to(_sec["entries"][0].label)

        # Final pass: guarantee all audit rows are red regardless of build order
        from PyQt6.QtGui import QColor as _QColor
        for _arow in self._nav_audit_rows:
            _aitem = self._nav.item(_arow)
            if _aitem:
                _aitem.setForeground(_QColor(AUDIT_RED))

    def _nav_ref(self, icon: str, label: str, widget: "QWidget") -> int:
        """Add a nav alias entry for a widget already registered in the stack."""
        idx = self._stack.indexOf(widget)
        if idx < 0:
            idx = self._stack.addWidget(widget)
        self._nav_label_to_widget[label] = widget
        return self._nav_add_alias(icon, label, idx)

    def _nav_flat_item(self, icon: str, label: str, widget: "QWidget",
                       admin_required: bool = False, audit_item: bool = False) -> int:
        """Add a flat-nav item and optionally mark it admin/audit for red styling."""
        row = self._nav_ref(icon, label, widget)
        if admin_required:
            self._nav_admin_rows.add(row)
        if audit_item:
            self._nav_audit_rows.add(row)
        return row

    def _nav_add_action(self, icon: str, label: str, action) -> int:
        """Add a nav item that calls *action* instead of navigating to a page."""
        from PyQt6.QtCore import QSize
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item.setSizeHint(QSize(0, 30))
        self._nav.addItem(item)
        row = self._nav.count() - 1
        self._nav_item_icons[row]  = icon
        self._nav_item_labels[row] = label
        parent = (self._nav_current_subgroup if self._nav_current_subgroup >= 0
                  else self._nav_current_section)
        if parent >= 0:
            self._nav_section_groups[parent]["children"].append(row)
        self._nav_refresh_item_text(row)
        self._nav_action_rows[row] = action
        return row

    def _nav_add_spacer(self) -> None:
        """Add a non-selectable visual spacer row in the nav list."""
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QColor, QBrush
        sep = QListWidgetItem()
        sep.setFlags(Qt.ItemFlag.NoItemFlags)
        sep.setSizeHint(QSize(0, 10))
        sep.setBackground(QBrush(QColor(SIDEBAR_BG)))
        self._nav.addItem(sep)
        self._nav_header_rows.add(self._nav.count() - 1)

    def _nav_add_section_label(self, label: str, fg_color: str = None) -> int:
        """Add a NON-collapsible ALL-CAPS section divider label (not interactive)."""
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QColor, QFont as _QFont
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)   # not selectable, not clickable
        item.setSizeHint(QSize(0, 26))
        f = _QFont("Segoe UI", 9)
        f.setBold(True)
        item.setFont(f)
        item.setText(f"  {label.upper()}")
        _fg = fg_color or SIDEBAR_SECTION_FG
        item.setForeground(QColor(_fg))
        self._nav.addItem(item)
        row = self._nav.count() - 1
        self._nav_item_icons[row]  = ""
        self._nav_item_labels[row] = label
        self._nav_header_rows.add(row)
        # Deliberately NOT in _nav_section_groups — no collapse/expand logic
        return row

    # ── Rail-mode nav helpers ─────────────────────────────────────────────────

    def _nav_begin_section(self, name: str, icon: str) -> None:
        """Start a new section in rail mode. Must be followed by _nav_add_rail_item calls."""
        self._nav_sections.append({"name": name, "icon": icon, "entries": []})

    def _nav_add_rail_item(
        self,
        label: str,
        widget: "QWidget",
        pinned: bool = False,
        admin_required: bool = False,
        audit_item: bool = False,
    ) -> None:
        """Register a page under the current rail section (last in _nav_sections)."""
        if not self._nav_sections:
            return
        # Ensure widget is in the stack
        if self._stack.indexOf(widget) < 0:
            self._stack.addWidget(widget)
        self._nav_label_to_widget[label] = widget
        entry = _NavEntry(
            label=label,
            page=widget,
            admin_required=admin_required,
            audit_item=audit_item,
            pinned=label in self._nav_pinned_labels or pinned,
        )
        self._nav_sections[-1]["entries"].append(entry)
        self._nav_page_to_section[label] = self._nav_sections[-1]["name"]

    def _nav_finalize_rail(self) -> None:
        """Build _RailButton widgets from _nav_sections and wire them up."""
        # Clear old rail buttons (between the mode-btn and settings-btn)
        stretch_idx = None
        for i in range(self._nav_rail_lay.count()):
            item = self._nav_rail_lay.itemAt(i)
            if item and item.spacerItem():
                stretch_idx = i
                break
        # Remove all rail section buttons (inserted between mode btn and stretch)
        while stretch_idx and stretch_idx > 1:
            item = self._nav_rail_lay.takeAt(1)
            if item and item.widget():
                item.widget().deleteLater()
            stretch_idx -= 1

        self._nav_rail_buttons.clear()
        self._nav_rail_pin_buttons: dict = {}  # label -> _RailPinButton

        # NAV-3: Direct-nav Quick Access buttons (≤4 pins) ─────────────────────
        direct_pins = getattr(self, "_nav_direct_pins", [])
        if direct_pins:
            # "QUICK ACCESS" separator label above the pin buttons
            qa_lbl = QLabel("QUICK\nACCESS")
            qa_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
            qa_lbl.setFixedSize(56, 24)
            qa_lbl.setStyleSheet(
                f"color:{TEXT_MUTED}; font-size:7px; font-weight:bold;"
                f" letter-spacing:0.5px; background:transparent;"
            )
            insert_at = self._nav_rail_lay.count() - 2
            self._nav_rail_lay.insertWidget(insert_at, qa_lbl)

            for entry in direct_pins:
                lbl = entry.label
                # short display: first word, max 8 chars
                short = lbl.split()[0][:8]
                pin_btn = _RailButton("star", lbl)
                pin_btn._short_label = short
                pin_btn.setToolTip(lbl)
                pin_btn.clicked.connect(
                    lambda _c, label=lbl: (
                        self._nav_rail_go_to(label),
                        self._nav_flyout.close_panel() if hasattr(self, "_nav_flyout") else None,
                    )
                )
                insert_at = self._nav_rail_lay.count() - 2
                self._nav_rail_lay.insertWidget(insert_at, pin_btn)
                self._nav_rail_pin_buttons[lbl] = pin_btn

        _SECTION_HINTS: dict = {
            "Monitor":        "Monitor  ·  Ctrl+L → Network Logger",
            "Security Audit": (
                "Security Audit\n"
                "Items shown in red require admin rights or run\n"
                "active probes against devices on your network."
            ),
        }
        for sec in self._nav_sections:
            btn = _RailButton(sec["icon"], sec["name"])
            btn.clicked.connect(lambda _c, s=sec["name"]: self._nav_rail_toggle(s))
            if sec["name"] in _SECTION_HINTS:
                btn.setToolTip(_SECTION_HINTS[sec["name"]])
            # Insert before the stretch (index = count - 2: stretch + settings)
            insert_at = self._nav_rail_lay.count() - 2
            self._nav_rail_lay.insertWidget(insert_at, btn)
            self._nav_rail_buttons[sec["name"]] = btn

    def _nav_rail_toggle(self, section_name: str) -> None:
        """Toggle the flyout for the given section; close if already open."""
        if self._nav_open_section == section_name and self._nav_flyout.maximumWidth() > 0:
            # Clicking the active section icon collapses the flyout
            if not self._nav_flyout.is_pinned:
                self._nav_flyout.close_panel()
                self._nav_open_section = ""
                self._nav_rail_buttons[section_name].setChecked(False)
            return
        # Switch to the new section
        self._nav_open_section = section_name
        for name, btn in self._nav_rail_buttons.items():
            btn.setChecked(name == section_name)
        sec = next((s for s in self._nav_sections if s["name"] == section_name), None)
        if sec is None:
            return
        entries = [
            (e.label, e.label in self._nav_pinned_labels, e.admin_required or e.audit_item)
            for e in sec["entries"]
        ]
        self._nav_flyout.load_section(
            title=section_name,
            entries=entries,
            active_label=self._nav_current_page_label,
            on_click=self._nav_rail_go_to,
            on_pin_toggle=self._on_rail_pin_toggle,
        )
        # Re-apply any saved flyout dots after items are rebuilt
        for _lbl, _color in getattr(self, "_flyout_dots", {}).items():
            if _color:
                self._nav_flyout.apply_dot(_lbl, _color)
        self._nav_flyout.open()
        _qs = QSettings(str(self._settings_path()), QSettings.Format.IniFormat)
        _qs.setValue("nav/last_section", section_name)

    def _nav_rail_go_to(self, label: str, _push_history: bool = False) -> None:
        """Navigate to a page by label in rail mode. Flyout stays open."""
        widget = self._nav_label_to_widget.get(label)
        if widget is None:
            return
        if (
            label != "Settings"
            and hasattr(self, "_settings_page")
            and self._settings_page.is_dirty()
            and not self._settings_page.confirm_leave()
        ):
            return
        if _push_history and hasattr(self, "_nav_history"):
            current = getattr(self, "_nav_current_page_label", None)
            if current and current != label:
                self._nav_history.append(current)
        elif hasattr(self, "_nav_history"):
            self._nav_history.clear()
        if hasattr(self, "_back_btn"):
            self._back_btn.setVisible(bool(self._nav_history))
        self._nav_current_page_label = label
        self._nav_crossfade_to(widget)
        self._nav_flyout.set_active(label)
        section = self._nav_page_to_section.get(label, "")
        if hasattr(self, "_breadcrumb_lbl"):
            self._breadcrumb_lbl.setText(f"{section}  ›  {label}" if section else label)
        if hasattr(self, "_help_panel"):
            self._update_help_panel(label)
        if hasattr(self, "_tray_manager"):
            self._tray_manager.reset_badge()
        # Auto-expand tips on first visit to pages with non-obvious interactions
        if label in _AUTO_HELP_PAGES and _PAGE_HELP.get(label) and hasattr(self, "_tip_bar"):
            import json as _json
            _qs2 = QSettings("NetSentinel", "NetSentinel")
            try:
                _visited2 = _json.loads(_qs2.value("discover/visited_pages", "[]"))
            except Exception:
                _visited2 = []
            if label not in _visited2:
                self._tip_bar.setChecked(True)
        self._track_page_visit(label)

    def _nav_deep_link_go_to(self, label: str) -> None:
        """Navigate via a deep link — pushes the current page onto the back stack."""
        self._nav_rail_go_to(label, _push_history=True)

    @pyqtSlot()
    def _nav_go_back(self) -> None:
        if not self._nav_history:
            return
        prev = self._nav_history.pop()
        widget = self._nav_label_to_widget.get(prev)
        if widget is None:
            return
        self._nav_current_page_label = prev
        self._nav_crossfade_to(widget)
        self._nav_flyout.set_active(prev)
        section = self._nav_page_to_section.get(prev, "")
        if hasattr(self, "_breadcrumb_lbl"):
            self._breadcrumb_lbl.setText(f"{section}  ›  {prev}" if section else prev)
        if hasattr(self, "_back_btn"):
            self._back_btn.setVisible(bool(self._nav_history))

    def keyPressEvent(self, event) -> None:
        from PyQt6.QtCore import Qt as _Qt
        if event.key() == _Qt.Key.Key_Escape and self._nav_history:
            self._nav_go_back()
            event.accept()
        else:
            super().keyPressEvent(event)

    @pyqtSlot()
    def _on_modem_tile_clicked(self) -> None:
        label = getattr(self, "_active_modem_plugin_label", "")
        if label:
            self._nav_rail_go_to(label)
        else:
            self._nav_rail_go_to("Hardware")

    @pyqtSlot(str)
    def _on_inventory_device_selected(self, mac: str) -> None:
        """Navigate to Devices and scroll/select the row matching this MAC."""
        self._nav_rail_go_to("Devices")
        self._m1_highlight_mac(mac)

    @pyqtSlot(str)
    def _on_config_drift_detected(self, message: str) -> None:
        """Show a status-bar and tray notification when snapshot comparison finds drift."""
        self._baseline_has_drift = True
        self._refresh_section_badges()
        self._set_status(f"⚠ {message}")
        if self._tray_manager.is_available():
            self._tray_manager.show_notification(
                "Config Drift Detected", message, "WARNING"
            )

    def _wire_page_help_btn(self, label: str, info: dict) -> None:
        """EDU-1: attach ? help button to the current page's PageHeaderBar (once)."""
        from ui.widgets.page_header import PageHeaderBar
        page = self._stack.currentWidget()
        if page is None:
            return
        hdr = page.findChild(PageHeaderBar)
        if hdr is None or hasattr(hdr, "_help_btn"):
            return
        what = info.get("what", "")
        if what:
            hdr.set_help(label, what)

    def _update_help_panel(self, label: str) -> None:
        """Refresh tip bar text and collapse the help panel when the page changes."""
        info = _PAGE_HELP.get(label, {})
        self._tip_bar_has_content = bool(info)

        # Collapse panel silently on page change
        if hasattr(self, "_tip_bar"):
            self._tip_bar.blockSignals(True)
            self._tip_bar.setChecked(False)
            self._tip_bar.blockSignals(False)
        if hasattr(self, "_help_panel"):
            self._help_panel.setVisible(False)

        if not info:
            if hasattr(self, "_tip_bar"):
                self._tip_bar.setText("ⓘ  Keyboard Shortcuts  ▾")
            if hasattr(self, "_help_what_lbl"):
                self._help_what_lbl.setText("")
            if hasattr(self, "_help_hidden_lbl"):
                self._help_hidden_lbl.setVisible(False)
            return

        if hasattr(self, "_tip_bar"):
            self._tip_bar.setText(f"ⓘ  Tips for {label}  ▾")

        what = info.get("what", "")
        bullets = info.get("hidden", [])
        if hasattr(self, "_help_what_lbl"):
            self._help_what_lbl.setText(what)
        if hasattr(self, "_help_hidden_lbl"):
            if bullets:
                hidden_text = "\n".join(f"  •  {b}" for b in bullets)
                self._help_hidden_lbl.setText(f"Hidden interactions:\n{hidden_text}")
                self._help_hidden_lbl.setVisible(True)
            else:
                self._help_hidden_lbl.setVisible(False)

        self._wire_page_help_btn(label, info)

    def _toggle_help_panel(self, checked: bool) -> None:
        # Panel always opens — shortcuts are useful on every page
        if hasattr(self, "_help_panel"):
            self._help_panel.setVisible(checked)

    # ── Visited-feature tracking ───────────────────────────────────────────────

    # Ordered list of high-value pages to surface to unvisited users.
    _DISCOVERY_PAGES = [
        ("Protocol Visualizer", "See animated diagrams of ARP, DNS, TCP and more — using your real devices"),
        ("Lab Mode",            "Try a guided exercise: find a rogue device or diagnose slow DNS on your live network"),
        ("Network Grade",       "Get an A–F score for your network health across 8 dimensions"),
        ("Network Health Report", "Generate a network health report — great for ISP support tickets"),
        ("What's Wrong?",       "Pick a symptom and get a plain-English verdict with a prioritised fix list"),
        ("Feature Guide",       "See everything this app can do — including features most users never find"),
        ("Network Logger",      "Configure log sources and view the live activity log — all in one place"),
    ]

    def _track_page_visit(self, label: str) -> None:
        import json as _json
        qs = QSettings("NetSentinel", "NetSentinel")
        raw = qs.value("discover/visited_pages", "[]")
        try:
            visited: list = _json.loads(raw)
        except Exception:
            visited = []
        if label not in visited:
            visited.append(label)
            qs.setValue("discover/visited_pages", _json.dumps(visited))
            self._refresh_home_suggestions()
            # NAV-3: first-time pin hint after visiting 3 Analysis pages
            if not qs.value("nav/pin_hint_shown", False, type=bool):
                analysis_sec = next(
                    (s for s in self._nav_sections if s["name"] == "Analysis"), None
                )
                if analysis_sec:
                    analysis_labels = {e.label for e in analysis_sec["entries"]}
                    visited_analysis = [p for p in visited if p in analysis_labels]
                    if len(visited_analysis) >= 3:
                        qs.setValue("nav/pin_hint_shown", True)
                        self._set_status(
                            "Tip: right-click any page in the menu to pin it ★ for faster access"
                        )

    def _refresh_home_suggestions(self) -> None:
        if not hasattr(self, "_home_page"):
            return
        # Don't overwrite a live challenge card
        if getattr(self, "_pending_live_scenario", None) is not None:
            return
        import json as _json
        qs = QSettings("NetSentinel", "NetSentinel")
        raw = qs.value("discover/visited_pages", "[]")
        try:
            visited: set = set(_json.loads(raw))
        except Exception:
            visited = set()
        suggestions = []
        for page_label, description in self._DISCOVERY_PAGES:
            if page_label not in visited:
                suggestions.append({
                    "text": description,
                    "action_label": "Try it →",
                    "target": page_label,
                    "priority": "low",
                })
            if len(suggestions) >= 3:
                break
        self._home_page.set_suggestions(suggestions)

    def _on_rail_pin_toggle(self, label: str, is_pinned: bool) -> None:
        """Update pinned set, persist, and rebuild nav so Pinned section appears/disappears."""
        if is_pinned:
            self._nav_pinned_labels.add(label)
        else:
            self._nav_pinned_labels.discard(label)
        self._save_pinned_labels()
        self._rebuild_nav_for_mode()

    def _on_canvas_click(self) -> None:
        """Close flyout on canvas click (only if not pinned)."""
        if hasattr(self, "_nav_flyout") and not self._nav_flyout.is_pinned:
            if self._nav_flyout.maximumWidth() > 0:
                self._nav_flyout.close_panel()
                self._nav_open_section = ""
                for btn in self._nav_rail_buttons.values():
                    btn.setChecked(False)

    def _build_pro_nav(self) -> None:
        """Full nav \u2014 activity rail + flyout. No mode switcher; this is the only nav."""
        self._nav_begin_section("Getting Started", "grid")
        self._nav_add_rail_item("Home",               self._home_page)
        self._nav_add_rail_item("Overview",            self._overview_page)
        self._nav_add_rail_item("Speed Test",          self._speed_test_page)
        self._nav_add_rail_item("DNS & Stability",     self._m5_tab)
        self._nav_add_rail_item("What's Wrong?",       self._diagnosis_page)

        self._nav_begin_section("Discover", "network")
        self._nav_add_rail_item("Devices",             self._m1_tab)
        self._nav_add_rail_item("Network Map",         self._topology_tab_widget)
        self._nav_add_rail_item("WiFi Networks",       self._m4_tab)
        self._nav_add_rail_item("WiFi Heatmap",        self._wifi_heatmap_page)
        self._nav_add_rail_item("DHCP Leases",         self._dhcp_lease_page)
        self._nav_add_rail_item("Home Automation",     self._ha_page)

        self._nav_begin_section("Monitor", "monitor")
        self._nav_add_rail_item("Network Logger",      self._logging_container)
        self._nav_add_rail_item("Live Bandwidth",      self._live_bandwidth_page)
        self._nav_add_rail_item("Active Connections",  self._connections_page)
        self._nav_add_rail_item("Availability History", self._history_page)
        self._nav_add_rail_item("Inventory Changes",   self._inventory_page)
        self._nav_add_rail_item("Bandwidth Usage",     self._bw_tab_widget)
        self._nav_add_rail_item("Service Heartbeat",   self._service_page)
        self._nav_add_rail_item("IPv6 Devices",        self._ipv6_tab_widget)

        self._nav_begin_section("Reports", "bar-chart")
        self._nav_add_rail_item("Network Grade",       self._benchmark_tab_widget)
        self._nav_add_rail_item("Network Health Report", self._reports_page)
        self._nav_add_rail_item("Network Doc",         self._network_doc_page)
        self._nav_add_rail_item("IP Calculator",       self._ip_calc_page)
        self._nav_add_rail_item("Notifications",       self._notifications_page)

        self._nav_begin_section("Analysis", "cpu")
        self._nav_add_rail_item("Broadcast Storm",     self._m3_tab)
        self._nav_add_rail_item("Rogue Bridge (STP)",  self._m2_tab)
        self._nav_add_rail_item("IoT Behaviour",       self._iot_baseline_tab_widget)
        self._nav_add_rail_item("Monitor Overview",    self._monitor_overview_page)
        self._nav_add_rail_item("802.11 Monitor",      self._wifi_monitor_page)
        self._nav_add_rail_item("ARP Spoof Watch",     self._arp_tab_widget)
        self._nav_add_rail_item("Hop-by-Hop Trace",    self._mtr_tab_widget)
        self._nav_add_rail_item("SNMP Device Info",    self._snmp_tab_widget)
        self._nav_add_rail_item("Tools & Wake-on-LAN", self._adv_tab_widget)
        self._nav_add_rail_item("Geolocation Map",     self._geo_map_page)
        self._nav_add_rail_item("Trend Forecasts",     self._trend_page)

        self._nav_begin_section("Automation", "zap")
        self._nav_add_rail_item("Automation Hooks",    self._automation_page)
        self._nav_add_rail_item("Scheduled Scans",     self._sched_tab_widget)
        self._nav_add_rail_item("Custom Triggers",     self._trigger_page)
        self._nav_add_rail_item("MQTT / Home Assistant", self._mqtt_page)
        self._nav_add_rail_item("REST API",            self._rest_api_page)
        self._nav_add_rail_item("Config Snapshots",    self._baseline_page)
        self._nav_add_rail_item("Maintenance Windows", self._maintenance_page)

        self._nav_begin_section("Security Audit", "shield")
        self._nav_add_rail_item("Security Overview",    self._security_overview_page,     audit_item=True)
        self._nav_add_rail_item("Port Scan (TCP)",      self._recon_syn_tab_widget,       admin_required=True, audit_item=True)
        self._nav_add_rail_item("Port Scan (UDP)",      self._recon_udp_tab_widget,       admin_required=True, audit_item=True)
        self._nav_add_rail_item("CVE Lookup",           self._recon_cve_tab_widget,       audit_item=True)
        self._nav_add_rail_item("Threat Intel",         self._threat_intel_page,          audit_item=True)
        self._nav_add_rail_item("TLS & Exposure",       self._cert_page,                  audit_item=True)
        self._nav_add_rail_item("Login Test",           self._recon_cred_tab_widget,      admin_required=True, audit_item=True)
        self._nav_add_rail_item("OS Detection",         self._recon_os_tab_widget,        audit_item=True)
        self._nav_add_rail_item("Device Risk Score",    self._recon_risk_tab_widget,      audit_item=True)
        self._nav_add_rail_item("CVE Tracker",          self._cve_page,                   audit_item=True)
        self._nav_add_rail_item("Exposed to Internet",  self._recon_exposure_tab_widget,  audit_item=True)
        self._nav_add_rail_item("Full Device Discovery", self._recon_discovery_tab_widget, audit_item=True)
        self._nav_add_rail_item("Windows Shares (SMB)", self._recon_smb_tab_widget,       audit_item=True)
        self._nav_add_rail_item("Recon Plugins",         self._recon_plugin_tab_widget,    audit_item=True)
        self._nav_add_rail_item("Private Endpoint Check", self._recon_pe_tab_widget,      audit_item=True)
        self._nav_add_rail_item("Cloud Metadata Probe", self._recon_cloud_tab_widget,     audit_item=True)
        self._nav_add_rail_item("DHCP Rogue Monitor",   self._dhcp_tab_widget,            audit_item=True)

        self._nav_begin_section("Education", "book-open")
        self._nav_add_rail_item("Protocol Visualizer", self._protocol_viz_page)
        self._nav_add_rail_item("Lab Mode",            self._lab_mode_page)
        self._nav_add_rail_item("Feature Guide",       self._discover_page)
        self._nav_add_rail_item("Help & Reference",    self._help_tab_widget)

        self._nav_begin_section("Extend", "plug")
        self._nav_add_rail_item("Hardware",        self._hardware_integration_page)
        for _hw_p, _pg in getattr(self, "_plugin_pages", {}).items():
            self._nav_add_rail_item(_pg._label, _pg)

    #── Favourites / pinnable pages ───────────────────────────────────────────

    def _load_pinned_labels(self) -> set:
        try:
            from PyQt6.QtCore import QSettings
            s = QSettings(str(Dashboard._settings_path()), QSettings.Format.IniFormat)
            raw = s.value("nav/pinned_labels", "")
            return set(filter(None, raw.split("|||"))) if raw else set()
        except Exception:
            return set()

    def _save_pinned_labels(self) -> None:
        try:
            from PyQt6.QtCore import QSettings
            s = QSettings(str(Dashboard._settings_path()), QSettings.Format.IniFormat)
            s.setValue("nav/pinned_labels", "|||".join(sorted(self._nav_pinned_labels)))
        except Exception:
            pass

    def _build_favourites_section(self) -> None:
        """Prepend a Favourites section when the user has pinned at least one page."""
        if not self._nav_pinned_labels:
            return
        self._nav_add_section_label("Favourites")
        for label in sorted(self._nav_pinned_labels):
            widget = self._nav_label_to_widget.get(label)
            if widget is not None:
                self._nav_ref("★", label, widget)

    def _toggle_pin_label(self, label: str) -> None:
        if label in self._nav_pinned_labels:
            self._nav_pinned_labels.discard(label)
        else:
            self._nav_pinned_labels.add(label)
        self._save_pinned_labels()
        self._rebuild_nav_for_mode()

    def _nav_context_menu(self, pos) -> None:
        from PyQt6.QtWidgets import QMenu
        item = self._nav.itemAt(pos)
        if item is None:
            return
        row = self._nav.row(item)
        if row in self._nav_header_rows or row in self._nav_action_rows:
            return
        label = self._nav_item_labels.get(row, "")
        if not label:
            return
        menu = QMenu()
        if label in self._nav_pinned_labels:
            act = menu.addAction("★  Remove from Favourites")
        else:
            act = menu.addAction("☆  Pin to Favourites")
        chosen = menu.exec(self._nav.viewport().mapToGlobal(pos))
        if chosen is act:
            self._toggle_pin_label(label)

    # ── Command palette ───────────────────────────────────────────────────────

    # ── Monitoring state helpers (NAV-2) ──────────────────────────────────────

    _MONITOR_PAGES: dict = {
        "ARP Spoof Watch":     "_arp_worker",
        "DHCP Rogue Monitor":  "_dhcp_worker",
        "Bandwidth Monitor":   "_bw_worker",
    }

    def _is_monitor_running(self, worker_attr: str) -> bool:
        w = getattr(self, worker_attr, None)
        return bool(w and w.isRunning())

    # ── Recent-action recording (RECUR-3) ─────────────────────────────────────

    def _record_recent_action(self, action_id: str, label: str, page: str, params: dict) -> None:
        import json as _json
        qs = QSettings("NetSentinel", "NetSentinel")
        try:
            existing: list = _json.loads(qs.value("recur/recent_actions", "[]"))
        except Exception:
            existing = []
        existing = [a for a in existing if a.get("id") != action_id]
        existing.insert(0, {"id": action_id, "label": label, "page": page, "params": params})
        qs.setValue("recur/recent_actions", _json.dumps(existing[:10]))

    def _build_palette_items(self) -> list:
        import json as _json

        # Recent actions (RECUR-3) — prepend with separator
        recent_items: list = []
        try:
            recent = _json.loads(
                QSettings("NetSentinel", "NetSentinel").value("recur/recent_actions", "[]")
            )
        except Exception:
            recent = []
        if recent:
            recent_items.append({"label": "Recent", "kind": "separator"})
            for a in recent[:5]:
                recent_items.append({
                    "icon": "⟳", "label": a["label"], "kind": "recent",
                    "id": a["id"], "page": a["page"], "params": a.get("params", {}),
                })

        # Pages (NAV-2: add monitoring state to monitor pages)
        _PAGE_SHORTCUTS: dict[str, str] = {
            "Log Hub":  "Ctrl+L",
            "Settings": "Ctrl+,",
        }
        seen: set = set()
        pages = []
        for sec in self._nav_sections:
            for entry in sec["entries"]:
                if entry.label and entry.label not in seen:
                    seen.add(entry.label)
                    worker_attr = self._MONITOR_PAGES.get(entry.label)
                    sc = _PAGE_SHORTCUTS.get(entry.label, "")
                    if worker_attr:
                        running = self._is_monitor_running(worker_attr)
                        state = "● Monitoring" if running else "○ Not running"
                        pages.append({
                            "icon": "◎",
                            "label": f"{entry.label}  {state}",
                            "kind": "page",
                            "real_label": entry.label,
                            "shortcut": sc,
                        })
                        if not running:
                            pages.append({
                                "icon": "▶",
                                "label": f"Start {entry.label}",
                                "kind": "action",
                            })
                    else:
                        pages.append({"icon": "◎", "label": entry.label, "kind": "page", "shortcut": sc})

        if recent_items:
            pages_section = [{"label": "Pages", "kind": "separator"}] + pages
        else:
            pages_section = pages

        actions = [
            {"icon": "⟳", "label": "Run Full Scan",    "kind": "action"},
            {"icon": "⚙", "label": "Open Settings",    "kind": "action"},
            {"icon": "◄", "label": "Toggle Sidebar",   "kind": "action"},
            {"icon": "◈", "label": "Diagnose Network", "kind": "action"},
        ]
        return recent_items + pages_section + actions

    def _open_command_palette(self) -> None:
        items = self._build_palette_items()
        pal = CommandPalette(items, parent=self)
        pal.load_recent_data(self._store)
        pal.page_requested.connect(self._nav_rail_go_to)
        pal.action_requested.connect(self._on_palette_action)
        pal.exec()

    def _open_shortcut_overlay(self) -> None:
        """Show the keyboard shortcut reference overlay (KEYBOARD-1)."""
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox
        from ui.styles import BG_CARD, BORDER, CARD_RADIUS, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED
        dlg = QDialog(self)
        dlg.setWindowTitle("Keyboard Shortcuts")
        dlg.setMinimumWidth(420)
        dlg.setModal(True)
        dlg.setStyleSheet(
            f"QDialog {{ background:{BG_CARD}; }}"
            f"QLabel {{ color:{TEXT_PRIMARY}; background:transparent; }}"
        )
        vlay = QVBoxLayout(dlg)
        vlay.setContentsMargins(20, 16, 20, 16)
        vlay.setSpacing(8)
        hdr = QLabel("Keyboard Shortcuts")
        hdr.setStyleSheet(f"font-size:15px; font-weight:bold; color:{TEXT_PRIMARY};")
        vlay.addWidget(hdr)
        shortcuts = [
            ("?",           "Show this reference"),
            ("Ctrl+K",      "Command palette"),
            ("Ctrl+F",      "Focus nav search"),
            ("Ctrl+R",      "Run full scan"),
            ("Ctrl+,",      "Settings"),
            ("Ctrl+L",      "Log Hub"),
            ("Ctrl+Q",      "Quit"),
            ("J / K",       "Next / previous row in tables"),
            ("Escape",      "Close panel / flyout"),
        ]
        for key, desc in shortcuts:
            row_w = QWidget()
            row_w.setStyleSheet("background:transparent;")
            row_lay = QHBoxLayout(row_w)
            row_lay.setContentsMargins(0, 2, 0, 2)
            key_lbl = QLabel(key)
            key_lbl.setFixedWidth(110)
            key_lbl.setStyleSheet(
                f"font-family:monospace; font-size:11px; font-weight:bold;"
                f" color:{ACCENT}; background:{BORDER}22;"
                f" border:1px solid {BORDER}; border-radius:3px; padding:1px 5px;"
            )
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY};")
            row_lay.addWidget(key_lbl)
            row_lay.addSpacing(12)
            row_lay.addWidget(desc_lbl, 1)
            vlay.addWidget(row_w)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(dlg.accept)
        btns.button(QDialogButtonBox.StandardButton.Close).setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:4px; padding:4px 14px; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        vlay.addSpacing(4)
        vlay.addWidget(btns)
        dlg.exec()

    def _on_palette_action(self, action: str) -> None:
        if action.startswith("__device__"):
            ip_or_mac = action[len("__device__"):]
            self._nav_rail_go_to("Inventory Changes")
            if hasattr(self, "_inventory_page"):
                self._inventory_page.select_device(ip_or_mac)
        elif action.startswith("__alert__"):
            import json as _json
            try:
                alert_dict = _json.loads(action[len("__alert__"):])
                if hasattr(self, "_notifications_page"):
                    self._nav_rail_go_to("Notifications")
                    self._notifications_page._alert_drawer.open(alert_dict)
            except Exception:
                pass
        elif action.startswith("__recent__"):
            self._replay_recent_action(action[len("__recent__"):])
        elif action == "Run Full Scan":
            self._start_full_scan()
        elif action == "Open Settings":
            self._open_settings_dialog()
        elif action == "Toggle Sidebar":
            self._toggle_sidebar()
        elif action == "Diagnose Network":
            self._open_diagnosis()
        elif action == "Start ARP Spoof Watch":
            self._nav_rail_go_to("ARP Spoof Watch")
            self._start_arp_monitor()
        elif action == "Start DHCP Rogue Monitor":
            self._nav_rail_go_to("DHCP Rogue Monitor")
            self._start_dhcp_scan()
        elif action == "Start Bandwidth Monitor":
            self._nav_rail_go_to("Live Bandwidth")
            self._start_bandwidth_monitor()

    def _replay_recent_action(self, action_id: str) -> None:
        import json as _json
        qs = QSettings("NetSentinel", "NetSentinel")
        try:
            recent: list = _json.loads(qs.value("recur/recent_actions", "[]"))
        except Exception:
            return
        action = next((a for a in recent if a.get("id") == action_id), None)
        if action is None:
            return
        page = action.get("page", "")
        params = action.get("params", {})
        self._nav_rail_go_to(page)
        if page == "Port Scan (TCP)" and hasattr(self, "_syn_host"):
            self._syn_host.setText(params.get("host", ""))
        elif page == "Tools & Wake-on-LAN" and hasattr(self, "_ps_host"):
            self._ps_host.setText(params.get("host", ""))
        elif page == "Hop-by-Hop Trace" and hasattr(self, "_mtr_target"):
            self._mtr_target.setText(params.get("target", ""))

    def _on_overview_navigate(self, label: str) -> None:
        if label == "Diagnose Network":
            self._open_diagnosis()
        else:
            self._nav_rail_go_to(label)

    def _open_diagnosis(self) -> None:
        self._nav_rail_go_to("What's Wrong?")

    # ── Alert badge on Security Audit nav section ─────────────────────────────

    def _refresh_alert_badge(self) -> None:
        if not hasattr(self, "_store") or self._store is None:
            return
        # Rail mode: dot + tooltip handled by _refresh_section_badges
        self._refresh_section_badges()

    # ── Module 1 ──────────────────────────────────────────────────────────────

    def _build_kpi_bar(self) -> QWidget:
        """
        Four KPI tiles: Total Nodes | Critical Risks | Unauthorized | Scan Status.
        Sits at the top of the Devices page. Values are updated by _update_kpi_tiles().
        """
        bar = QWidget()
        bar.setFixedHeight(56)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 6)
        row.setSpacing(8)

        def _tile(dot_color: str, label: str, start_val: str, start_color: str):
            """Return (tile QFrame, dot QLabel, value QLabel)."""
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
            dot.setStyleSheet(
                f"color:{dot_color}; font-size:9px; background:transparent; border:none;"
            )
            lbl = QLabel(label.upper())
            lbl.setStyleSheet(
                f"color:{TEXT_MUTED}; font-size:9px; font-weight:bold;"
                "letter-spacing:0.5px; background:transparent; border:none;"
            )
            hdr.addWidget(dot)
            hdr.addWidget(lbl)
            hdr.addStretch()
            vl.addLayout(hdr)

            val = QLabel(start_val)
            val.setStyleSheet(
                f"color:{start_color}; font-size:18px; font-weight:bold;"
                "background:transparent; border:none;"
            )
            vl.addWidget(val)
            return tile, dot, val

        t1, self._kpi_nodes_dot,  self._kpi_nodes_val  = _tile(ACCENT,          "Total Nodes",    "—", TEXT_MUTED)
        t2, self._kpi_risk_dot,   self._kpi_risk_val   = _tile(TEXT_MUTED,      "Critical Risks", "—", TEXT_MUTED)
        t3, self._kpi_unauth_dot, self._kpi_unauth_val = _tile(TEXT_MUTED,      "Unauthorized",   "—", TEXT_MUTED)
        t4, self._kpi_scan_dot,   self._kpi_scan_val   = _tile(TEXT_SECONDARY,  "Scan Status",    "Ready", TEXT_SECONDARY)

        # Keep references to the tiles themselves so we can update border colours
        self._kpi_risk_tile  = t2
        self._kpi_unauth_tile = t3

        for t in (t1, t2, t3, t4):
            row.addWidget(t, 1)
        return bar

    def _update_kpi_tiles(self, data: dict) -> None:
        """Refresh KPI tile values from a completed scan result dict."""
        devices    = data.get("devices", [])
        total      = len(devices)
        high_risk  = sum(
            1 for d in devices
            if (d.risk_level if not isinstance(d, dict) else d.get("risk_level", "")) in ("HIGH", "CRITICAL")
        )
        unauth     = data.get("high_risk_count", high_risk)

        # Nodes tile — always blue
        self._kpi_nodes_val.setText(str(total))
        self._kpi_nodes_val.setStyleSheet(
            f"color:{ACCENT}; font-size:18px; font-weight:bold;"
            "background:transparent; border:none;"
        )

        # Critical risks tile — green if 0, amber if 1-2, red if 3+
        risk_color = GREEN if high_risk == 0 else (AMBER if high_risk <= 2 else RED)
        self._kpi_risk_val.setText(str(high_risk))
        self._kpi_risk_val.setStyleSheet(
            f"color:{risk_color}; font-size:18px; font-weight:bold;"
            "background:transparent; border:none;"
        )
        self._kpi_risk_dot.setStyleSheet(
            f"color:{risk_color}; font-size:9px; background:transparent; border:none;"
        )
        self._kpi_risk_tile.setStyleSheet(
            f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
            f"border-left:3px solid {risk_color};border-radius:0px;}}"
        )

        # Unauthorized tile — green if 0, red if >0
        unauth_color = GREEN if unauth == 0 else RED
        self._kpi_unauth_val.setText(str(unauth))
        self._kpi_unauth_val.setStyleSheet(
            f"color:{unauth_color}; font-size:18px; font-weight:bold;"
            "background:transparent; border:none;"
        )
        self._kpi_unauth_dot.setStyleSheet(
            f"color:{unauth_color}; font-size:9px; background:transparent; border:none;"
        )
        self._kpi_unauth_tile.setStyleSheet(
            f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
            f"border-left:3px solid {unauth_color};border-radius:0px;}}"
        )

        # Scan status tile — green "Complete"
        self._kpi_scan_val.setText("Complete")
        self._kpi_scan_dot.setStyleSheet(
            f"color:{GREEN}; font-size:9px; background:transparent; border:none;"
        )
        self._kpi_scan_val.setStyleSheet(
            f"color:{GREEN}; font-size:18px; font-weight:bold;"
            "background:transparent; border:none;"
        )

    # ── How to Fix dialog (shared by M1 / M2 / M3 context menus) ─────────────

    def _show_how_to_fix(self, title: str, remediation: str):
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QScrollArea as _SA

        dlg = QDialog(self)
        dlg.setWindowTitle(f"How to Fix — {title}")
        dlg.setMinimumWidth(500)
        dlg.setStyleSheet(f"background:{BG_DARK}; color:{TEXT_PRIMARY};")
        lay = QVBoxLayout(dlg)

        heading = QLabel(f"<b>Remediation steps for: {title}</b>")
        heading.setStyleSheet(f"color:{ACCENT_LITE}; font-size:13px; padding-bottom:4px;")
        heading.setWordWrap(True)
        lay.addWidget(heading)

        # Split on ". " or "\\n" for numbered steps
        import re
        raw = remediation.strip() if remediation else "No specific fix information available."
        parts = [p.strip() for p in re.split(r'\. (?=[A-Z0-9])', raw) if p.strip()]
        if len(parts) <= 1 and "\n" in raw:
            parts = [p.strip() for p in raw.split("\n") if p.strip()]

        steps_html = ""
        for i, step in enumerate(parts, 1):
            s = html.escape(step)
            if not s.endswith("."):
                s += "."
            steps_html += f"<li style='margin-bottom:8px'><b>Step {i}:</b> {s}</li>"
        if not steps_html:
            steps_html = f"<li>{html.escape(raw)}</li>"

        txt = QLabel(f"<ol style='padding-left:18px;line-height:1.8'>{steps_html}</ol>")
        txt.setWordWrap(True)
        txt.setTextFormat(Qt.TextFormat.RichText)
        txt.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:12px; padding:4px;")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.addWidget(txt)
        inner_lay.addStretch()
        scroll.setWidget(inner)
        scroll.setStyleSheet(f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:0px;")
        scroll.setMinimumHeight(160)

        lay.addWidget(scroll, 1)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(dlg.accept)
        lay.addWidget(btns)
        dlg.exec()

    # ── Window lifecycle ──────────────────────────────────────────────────────

    def _quit_app(self):
        """Unconditional quit — bypasses minimize-to-tray logic."""
        self._tray_quit = True
        self.close()

    def closeEvent(self, event):
        """X button hides to tray (app keeps monitoring). Quit via ⚙ menu or Ctrl+Q to exit."""
        if (not self._tray_quit
                and self._tray_manager.is_available()
                and self._tray_manager.minimize_to_tray_enabled()):
            event.ignore()
            self._tray_manager._hide_window()
            from PyQt6.QtCore import QSettings as _QS
            _qs = _QS("NetSentinel", "NetSentinel")
            if not _qs.value("tray/hide_hint_shown", False, type=bool):
                self._tray_manager.show_notification(
                    "NetSentinel",
                    "Still monitoring in the system tray — use ⚙ › Quit to exit.",
                    "INFO",
                )
                _qs.setValue("tray/hide_hint_shown", True)
            return

        # ── Real shutdown path ────────────────────────────────────────────────
        self._save_window_state()

        # Collect every worker the dashboard owns into one flat list
        _all_workers = []
        # Transient/one-shot workers
        for attr in ("_net_info_worker", "_diag_worker", "_prescan_worker",
                     "_mtr_worker", "_ps_worker", "_ipv6_worker", "_cloud_worker",
                     "_arp_worker", "_dhcp_worker", "_bw_worker", "_sched_worker",
                     "_snmp_worker", "_syn_worker", "_udp_worker", "_cve_worker",
                     "_exposure_worker", "_os_worker", "_cred_worker",
                     "_discovery_worker", "_smb_worker", "_pe_worker",
                     "_plugin_worker"):
            w = getattr(self, attr, None)
            if w is not None:
                _all_workers.append(w)
        # Workers tracked in self._workers (scan module workers)
        _all_workers.extend(list(self._workers))

        # Signal stop to every running worker first (non-blocking)
        for w in _all_workers:
            if w.isRunning():
                if hasattr(w, "stop"):
                    w.stop()
                elif hasattr(w, "stop_logger"):
                    w.stop_logger()
                else:
                    w.quit()  # ask the event loop to exit

        # Stop the persistent logger worker
        if self._logger_worker and self._logger_worker.isRunning():
            self._logger_worker.stop_logger()
            _all_workers.append(self._logger_worker)

        # Wait briefly for each worker — 800 ms cap so close is responsive
        for w in _all_workers:
            if w.isRunning():
                w.wait(800)
            if w.isRunning():
                w.terminate()
                w.wait(2000)   # wait after terminate before object destruction

        super().closeEvent(event)
        # os._exit(0) bypasses Qt destructor cleanup entirely.
        # This is intentional: calling QApplication.quit() after terminate()
        # can still trigger QThread destructor crashes (STATUS_STACK_BUFFER_OVERRUN)
        # if a thread's OS handle is not yet released. os._exit(0) skips all
        # C++/Qt destructors and exits the process cleanly at the OS level.
        import os as _os, sys as _sys
        # PyInstaller onefile extracts to a _MEI* temp dir and registers an atexit
        # handler to clean it up. os._exit() bypasses atexit, leaving the dir behind
        # and causing a "Failed to remove temporary directory" warning on the next
        # launch. Delete it explicitly before exiting since nothing will use it after
        # this point.
        if getattr(_sys, "frozen", False) and hasattr(_sys, "_MEIPASS"):
            try:
                import shutil as _shutil
                _shutil.rmtree(_sys._MEIPASS, ignore_errors=True)
            except Exception:
                pass
        _os._exit(0)

    # ── Verdict area ─────────────────────────────────────────────────────────

    def _build_verdict_area(self) -> QWidget:
        """Compact verdict strip at bottom — thin, doesn't waste screen space."""
        w = QWidget()
        w.setStyleSheet(
            f"background:{BG_CARD}; border-top:1px solid {BORDER};"
        )
        lay = QHBoxLayout(w)
        lay.setContentsMargins(12, 4, 12, 4)
        lay.setSpacing(0)

        self._verdict = VerdictPanel()
        lay.addWidget(self._verdict, 1)
        return w

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _stat_label(self, title: str, value: str) -> QFrame:
        """KPI card: coloured left border, label above, large number below."""
        frame = QFrame()
        frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER};"
            f"border-left:3px solid {ACCENT}; border-radius:3px;"
        )
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(10, 6, 10, 6)
        fl.setSpacing(1)
        t = QLabel(title.upper())
        t.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:9px; font-weight:bold; letter-spacing:0.5px;"
        )
        v = QLabel(value)
        v.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold;")
        v.setObjectName(f"stat_{title.replace('/','_').replace(' ','_')}")
        fl.addWidget(t)
        fl.addWidget(v)
        return frame

    def _find_stat_value(self, frame: QFrame) -> Optional[QLabel]:
        for child in frame.findChildren(QLabel):
            if child.objectName().startswith("stat_"):
                return child
        return None

    def _update_stat(self, frame: QFrame, value: str, color: str = TEXT_PRIMARY):
        lbl = self._find_stat_value(frame)
        if lbl:
            lbl.setText(value)
            lbl.setStyleSheet(f"color:{color};font-size:18px;font-weight:bold;")

    def _set_status(self, msg: str):
        self._status_bar.showMessage(f"  {msg}")

    def _refresh_pulse_bar(self) -> None:
        """Update the four permanent status-bar indicators (called every 10 s)."""
        import time as _t

        _muted  = f"QLabel {{ padding: 0 8px; font-size: 11px; background: transparent; border: none; color: {TEXT_MUTED}; }} QLabel:hover {{ color: {WHITE}; }}"
        _green  = f"QLabel {{ padding: 0 8px; font-size: 11px; background: transparent; border: none; color: {GREEN}; }} QLabel:hover {{ color: {WHITE}; }}"
        _amber  = f"QLabel {{ padding: 0 8px; font-size: 11px; background: transparent; border: none; color: {AMBER}; }} QLabel:hover {{ color: {WHITE}; }}"
        _red    = f"QLabel {{ padding: 0 8px; font-size: 11px; background: transparent; border: none; color: {RED}; }} QLabel:hover {{ color: {WHITE}; }}"

        # Online / Offline
        status = self._last_log_status
        if status == "OK":
            self._pulse_online_lbl.setText("●  Online")
            self._pulse_online_lbl.setStyleSheet(_green)
        elif status == "SLOW":
            self._pulse_online_lbl.setText("●  Slow")
            self._pulse_online_lbl.setStyleSheet(_amber)
        elif status == "FAIL":
            self._pulse_online_lbl.setText("●  Offline")
            self._pulse_online_lbl.setStyleSheet(_red)
        else:
            self._pulse_online_lbl.setText("○  —")
            self._pulse_online_lbl.setStyleSheet(_muted)

        # Device count
        n = len(self._last_scan_devices)
        if n > 0:
            self._pulse_devices_lbl.setText(f"■  {n} device{'s' if n != 1 else ''}")
        else:
            self._pulse_devices_lbl.setText("■  —")
        self._pulse_devices_lbl.setStyleSheet(_muted)

        # Last scan age
        if self._last_scan_time > 0:
            elapsed = _t.time() - self._last_scan_time
            if elapsed < 60:
                age = "just now"
            elif elapsed < 3600:
                age = f"{int(elapsed // 60)}m ago"
            else:
                age = f"{int(elapsed // 3600)}h ago"
            self._pulse_scan_lbl.setText(f"Last scan: {age}")
        else:
            self._pulse_scan_lbl.setText("Last scan: —")
        self._pulse_scan_lbl.setStyleSheet(_muted)

        # Logger status
        logging_on = bool(self._logger_worker and self._logger_worker.isRunning())
        if logging_on:
            self._pulse_logger_lbl.setText("⏺  Logging")
            self._pulse_logger_lbl.setStyleSheet(_green)
        else:
            self._pulse_logger_lbl.setText("○  Logger off")
            self._pulse_logger_lbl.setStyleSheet(_muted)

    def _show_alert_toast(self, alert) -> None:
        """Show a desktop notification for a fired alert."""
        from ui.styles import RED, AMBER
        severity = getattr(alert, "severity", "INFO")
        message  = getattr(alert, "message",  str(alert))

        # Update status bar regardless
        prefix = "🔴" if severity == "CRITICAL" else "🟡"
        self._set_status(f"{prefix} {message}")

        # Desktop toast via tray manager
        if self._tray_manager.is_available():
            self._tray_manager.show_notification("NetSentinel Alert", message, severity)
            self._tray_manager.increment_badge()
        elif self._tray_icon is not None:
            # Legacy fallback (should never be reached after tray_manager setup)
            from PyQt6.QtWidgets import QSystemTrayIcon
            icon_type = (
                QSystemTrayIcon.MessageIcon.Critical
                if severity == "CRITICAL"
                else QSystemTrayIcon.MessageIcon.Warning
            )
            self._tray_icon.showMessage("NetSentinel Alert", message, icon_type, 5000)



    # ── Global time range (TIME-1) ────────────────────────────────────────────

    def _on_global_time_changed(self, text: str) -> None:
        mapping = {"1h": 1.0, "6h": 6.0, "24h": 24.0, "7d": 168.0, "30d": 720.0}
        hours = mapping.get(text, 24.0)
        self._global_hours = hours
        self.global_time_range_changed.emit(hours)

    def _set_global_time_combo(self, hours: float) -> None:
        """Sync the title bar combo to a given hours value (used by TIME-2 jump)."""
        reverse = {1.0: "1h", 6.0: "6h", 24.0: "24h", 168.0: "7d", 720.0: "30d"}
        text = reverse.get(hours)
        if text and hasattr(self, "_time_range_combo"):
            self._time_range_combo.blockSignals(True)
            self._time_range_combo.setCurrentText(text)
            self._time_range_combo.blockSignals(False)

    # ── DEVICE-1: popover navigation handlers ────────────────────────────────

    def _on_popover_open_inventory(self, ip_or_mac: str) -> None:
        self._nav_rail_go_to("Inventory Changes")
        if hasattr(self, "_inventory_page"):
            self._inventory_page.select_device(ip_or_mac)

    def _on_popover_open_threat_intel(self, ip: str) -> None:
        self._nav_rail_go_to("Threat Intelligence")
        if hasattr(self, "_threat_intel_page") and ip:
            self._threat_intel_page.check_ip(ip)

    # ── TIME-2: View in Log Hub from alert drawer ─────────────────────────────

    def _on_view_alert_in_log_hub(self, alert_ts: float, source_key: str) -> None:
        self._nav_rail_go_to("Network Logger")
        if hasattr(self, "_log_hub_page"):
            self._log_hub_page.jump_to_alert_time(alert_ts, source_key)

    @pyqtSlot(str, str)
    def _on_automation_rule_requested(self, rule_name: str, match_value: str) -> None:
        self._nav_rail_go_to("Automation Hooks")
        if hasattr(self, "_automation_page"):
            self._automation_page.prefill_rule(rule_name, match_value)

    # ── SCHED-3: monitor persistence ──────────────────────────────────────────

    _MONITOR_KEYS = {
        "arp":       "_arp_worker",
        "bandwidth": "_bw_worker",
        "scheduler": "_sched_worker",
    }

    def _save_monitor_state(self, key: str, running: bool) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        saved = set(qs.value("monitors/was_running", "", type=str).split(",")) - {""}
        if running:
            saved.add(key)
        else:
            saved.discard(key)
        qs.setValue("monitors/was_running", ",".join(sorted(saved)))

    def _restore_running_monitors(self) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        keys = set(qs.value("monitors/was_running", "", type=str).split(",")) - {""}
        if "arp" in keys and not (self._arp_worker and self._arp_worker.isRunning()):
            self._start_arp_monitor()
        if "bandwidth" in keys and not (self._bw_worker and self._bw_worker.isRunning()):
            self._start_bandwidth_monitor()
        if "scheduler" in keys and not (self._sched_worker and self._sched_worker.isRunning()):
            self._start_scheduler()

    # ── First-run welcome overlay ──────────────────────────────────────────────

    def _show_welcome_overlay(self) -> None:
        """Show the WelcomeOverlay on first ever launch (ui/first_run_done gate)."""
        from ui.first_run_dialog import WelcomeOverlay, should_show_first_run
        if not should_show_first_run():
            return
        overlay = WelcomeOverlay(self)
        self._welcome_overlay = overlay
        overlay.start_scan_requested.connect(self._on_welcome_scan)
        overlay.dismissed.connect(lambda: setattr(self, "_welcome_overlay", None))
        overlay.show_animated()

    def _on_welcome_scan(self) -> None:
        """User clicked 'Scan my network →' in the welcome overlay."""
        self._welcome_overlay = None
        self._nav_rail_go_to("Home")
        self._start_full_scan()

    def _set_scanning(self, scanning: bool):
        self._btn_scan.setEnabled(not scanning)
        if hasattr(self, "_header_scan_btn"):
            self._header_scan_btn.setEnabled(not scanning)
        if hasattr(self, "_home_page"):
            self._home_page.set_scanning(scanning)
        if hasattr(self, "_overview_page"):
            self._overview_page.set_scanning(scanning)
        self._progress.setVisible(scanning)
        # Update KPI scan-status tile
        if scanning:
            self._kpi_scan_val.setText("Scanning…")
            self._kpi_scan_dot.setStyleSheet(
                f"color:{ACCENT}; font-size:9px; background:transparent; border:none;"
            )
            self._kpi_scan_val.setStyleSheet(
                f"color:{ACCENT}; font-size:18px; font-weight:bold;"
                "background:transparent; border:none;"
            )
        if not scanning:
            _has_results = any(x is not None for x in [
                self._m1_result, self._m2_result, self._m3_result,
                self._m4_result, self._m5_result
            ])
            self._btn_export.setEnabled(_has_results)
            if hasattr(self, "_overview_page"):
                self._overview_page.set_export_enabled(_has_results)
                if not self._auto_report_pending:
                    self._overview_page.set_report_running(False)

    # ── Shared copy-to-clipboard for tables ──────────────────────────────────

    @staticmethod
    def _enable_copy_menu(table: QTableWidget):
        """Wire a right-click 'Copy row' action to any QTableWidget."""
        from PyQt6.QtCore import Qt as _Qt
        table.setContextMenuPolicy(_Qt.ContextMenuPolicy.CustomContextMenu)

        def _show_menu(pos):
            from PyQt6.QtWidgets import QMenu as _QMenu
            from PyQt6.QtGui import QClipboard as _QClipboard
            from PyQt6.QtWidgets import QApplication as _QApp
            rows_selected = sorted({i.row() for i in table.selectedIndexes()})
            if not rows_selected:
                return
            menu = _QMenu(table)
            act_row  = menu.addAction("Copy selected row(s)")
            act_cell = menu.addAction("Copy selected cell")
            chosen = menu.exec(table.viewport().mapToGlobal(pos))
            if chosen == act_row:
                lines = []
                for r in rows_selected:
                    parts = [
                        (table.item(r, c).text() if table.item(r, c) else "")
                        for c in range(table.columnCount())
                    ]
                    lines.append("\t".join(parts))
                _QApp.clipboard().setText("\n".join(lines))
            elif chosen == act_cell:
                item = table.currentItem()
                if item:
                    _QApp.clipboard().setText(item.text())

        table.customContextMenuRequested.connect(_show_menu)

    # ── Window state persistence ──────────────────────────────────────────────

    @staticmethod
    def _settings_path() -> "Path":
        from ui.app_settings import settings_path
        return settings_path()

    def _save_settings(self):
        from ui.app_settings import save_settings
        save_settings(self)

    def _center_on_screen(self, w: int, h: int) -> None:
        from ui.app_settings import center_on_screen
        center_on_screen(self, w, h)

    def _restore_settings(self):
        from ui.app_settings import restore_settings
        restore_settings(self)

    # Keep old names as aliases so any external code still works
    def _save_window_state(self):
        self._save_settings()

    def _restore_window_state(self):
        self._restore_settings()

    # ── OUI database reload ───────────────────────────────────────────────────

    def _reload_oui_db(self):
        """Re-read offenders.json without restarting the app."""
        self._offenders_path = get_offenders_path()
        self._set_status("OUI vendor database reloaded.")

    def _reset_dismissed_notices(self) -> None:
        """Clear all permanently-dismissed banner QSettings keys and re-show banners."""
        qs = QSettings("NetSentinel", "NetSentinel")
        dismissed_keys = [k for k in qs.allKeys() if k.endswith("_dismissed")]
        for k in dismissed_keys:
            qs.remove(k)
        # Trigger re-evaluation of Npcap banner state on next show
        qs.remove("home/npcap_dismissed")
        if hasattr(self, "_home_page"):
            self._home_page.showEvent(None)
        self._set_status("All dismissed notices have been reset.")

    @pyqtSlot()
    def _on_run_first_time_setup(self) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("home/checklist_done", False)
        qs.setValue("home/scan_count", 0)
        # Reset post-scan sheet so it fires again on the next scan
        qs.setValue("home/post_scan_sheet_dismissed", False)
        self._nav_rail_go_to("Home")
        if hasattr(self, "_home_page"):
            self._home_page._recurring_mode = False
            self._home_page._set_first_run_mode(True)
            self._home_page.refresh_checklist()

    @pyqtSlot()
    def _on_export_all(self) -> None:
        from PyQt6.QtWidgets import QFileDialog as _QFD
        import time as _t
        default = f"netsentinel-export-{_t.strftime('%Y%m%d-%H%M%S')}.zip"
        path, _ = _QFD.getSaveFileName(
            self, "Export All Data", default, "ZIP Archives (*.zip)"
        )
        if not path:
            return
        try:
            from modules.exporter import export_all_zip
            from pathlib import Path as _P
            export_all_zip(self._store, _P(path))
            from ui.widgets.toast import ToastManager
            ToastManager.instance().show_toast(f"Export saved to {path}", "info")
        except Exception as exc:
            from PyQt6.QtWidgets import QMessageBox as _MB
            _MB.warning(self, "Export Failed", str(exc))

    # ── Topology tab ──────────────────────────────────────────────────────────

    def _build_topology_tab(self) -> QWidget:
        from ui.topology_widget import TopologyWidget
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lbl = QLabel("Network topology — run a Device Fingerprint scan first.")
        lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._topology_widget = TopologyWidget()
        lay.addWidget(lbl)
        lay.addWidget(self._topology_widget, 1)
        return w

    # ── ARP monitor tab ───────────────────────────────────────────────────────

    def _build_arp_monitor_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(NpcapMissingBanner(parent=w))
        self._arp_status = QLabel("ARP spoof monitor not running.")
        self._arp_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
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
        self._set_flyout_dot("ARP Spoof Watch", GREEN)

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
        # Tray notification for ARP attacks
        if self._tray_manager.is_available():
            self._tray_manager.show_notification(
                f"ARP Attack Detected — {event.event_type.replace('_', ' ').title()}",
                f"{event.attacker_ip} ({event.attacker_mac}) → {event.verdict}",
                "CRITICAL" if level == "HIGH" else "WARNING",
            )
            self._tray_manager.increment_badge()

    # ── DHCP monitor tab ──────────────────────────────────────────────────────

    def _build_dhcp_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(NpcapMissingBanner(parent=w))
        self._dhcp_status = QLabel("DHCP rogue server monitor not running.")
        self._dhcp_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
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
        self._dhcp_worker.status.connect(self._dhcp_status.setText)
        self._dhcp_worker.error.connect(lambda e: self._dhcp_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._dhcp_worker.finished.connect(self._push_monitor_pills)
        self._dhcp_worker.start()
        self._dhcp_status.setText("DHCP discover sent — listening for offers…")
        self._push_monitor_pills()
        self._set_flyout_dot("DHCP Rogue Monitor", GREEN)

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
        self._bw_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
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
        for entry in snap.entries:
            row = self._bw_table.rowCount()
            self._bw_table.insertRow(row)
            total_kbps = entry.total_bps / 1000
            level = "HIGH" if total_kbps > 5000 else ("MEDIUM" if total_kbps > 500 else "CLEAN")
            for col, val in enumerate([
                entry.label or entry.mac,
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
        self._sched_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        ctrl_row = QHBoxLayout()
        self._sched_interval = QSpinBox()
        self._sched_interval.setRange(1, 1440)
        self._sched_interval.setValue(15)
        self._sched_interval.setSuffix(" min")
        self._sched_interval.setFixedWidth(90)
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
        self._sched_log.setStyleSheet(f"background:{BG_CARD};color:{TEXT_PRIMARY};font-size:11px;")
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
        _qs = _QS("NetSentinel", "NetSentinel")
        self._sched_worker = SchedulerWorker(
            interval_minutes=self._sched_interval.value(),
            offenders_path=self._offenders_path,
            notify_desktop=_qs.value("tray/notify_new_device", False, type=bool),
        )
        self._sched_worker.status.connect(self._on_sched_status)
        self._sched_worker.alert.connect(lambda t, m: self._sched_log.append(f"🔔 {t}: {m}"), Qt.ConnectionType.QueuedConnection)
        self._sched_worker.error.connect(lambda e: self._sched_log.append(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
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

    # ── SNMP tab ──────────────────────────────────────────────────────────────

    def _build_snmp_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        self._snmp_status = QLabel("SNMP poller not running.")
        self._snmp_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
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
        self._snmp_table = _table(["Host", "Name", "Description", "Uptime", "Interfaces", "Contact"])
        self._snmp_table.setColumnWidth(0, 120)
        self._snmp_table.setColumnWidth(2, 350)
        lay.addWidget(self._snmp_status)
        lay.addLayout(ctrl_row)
        lay.addWidget(self._snmp_table, 1)
        return w

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
        self._snmp_worker.error.connect(lambda e: self._snmp_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._snmp_worker.start()

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
                    pass
        except Exception:
            pass


    # ── Help page ────────────────────────────────────────────────────────────

    def _build_help_tab(self) -> QWidget:
        """Static Help & Shortcuts reference page (body delegated to ui.help)."""
        from ui.help_tab import build_help_tab
        return build_help_tab(self)

    def _check_for_updates(self):
        """Manual update check from the Help tab button."""
        import urllib.request, json as _json
        from PyQt6.QtWidgets import QApplication
        current = QApplication.applicationVersion()
        self._update_lbl.setText("Checking…")
        QApplication.processEvents()
        try:
            url = "https://api.github.com/repos/ossianericson/netsentinel/releases/latest"
            req = urllib.request.Request(url, headers={"User-Agent": "NetSentinel"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = _json.loads(resp.read())
            latest = data.get("tag_name", "").lstrip("v")
            def _ver(s):
                try:
                    return tuple(int(x) for x in s.split("."))
                except ValueError:
                    return (0,)
            if latest and _ver(latest) > _ver(current):
                self._update_lbl.setText(
                    f"Update available: v{latest} (you have v{current}) — "
                    '<a href="https://github.com/ossianericson/netsentinel/releases/latest" '
                    f'style="color:{ACCENT};">Download</a>'
                    ' &nbsp;·&nbsp; or: <code>winget upgrade NetSentinel.NetSentinel</code>'
                )
                self._update_lbl.setOpenExternalLinks(True)
                self._update_lbl.setTextFormat(Qt.TextFormat.RichText)
                self._on_update_available(latest)  # also show the notification bar
            else:
                self._update_lbl.setText(f"You're up to date (v{current})")
        except Exception as exc:
            self._update_lbl.setText(f"Update check failed: {exc}")

    def _show_about(self):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QApplication
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont
        dlg = QDialog(self)
        dlg.setWindowTitle("About NetSentinel")
        dlg.setMinimumWidth(400)
        dlg.setStyleSheet(self.styleSheet())
        lay = QVBoxLayout(dlg)
        lay.setSpacing(10)
        lay.setContentsMargins(28, 24, 28, 20)

        title = QLabel("NetSentinel")
        title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{ACCENT};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        version = QLabel(f"Version {QApplication.applicationVersion()}")
        version.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc = QLabel("Network Security Scanner & Connectivity Monitor")
        desc.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:13px;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)

        author = QLabel("Built by <b>Ossian Ericson</b>")
        author.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:13px;")
        author.setAlignment(Qt.AlignmentFlag.AlignCenter)

        github = QLabel(
            '<a href="https://github.com/ossianericson/netsentinel" '
            f'style="color:{ACCENT};">github.com/ossianericson/netsentinel</a>'
        )
        github.setOpenExternalLinks(True)
        github.setAlignment(Qt.AlignmentFlag.AlignCenter)
        github.setStyleSheet("font-size:12px;")

        btn_close = QPushButton("Close")
        btn_close.setObjectName("btnNetRefresh")
        btn_close.setFixedWidth(100)
        btn_close.clicked.connect(dlg.accept)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        btn_row.addStretch()

        disclaimer = QLabel(
            "For use on networks you own or have explicit authorization to test."
        )
        disclaimer.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
        disclaimer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        disclaimer.setWordWrap(True)

        for w in (title, version, desc, author, github):
            lay.addWidget(w)
        lay.addSpacing(8)
        lay.addWidget(disclaimer)
        lay.addSpacing(4)
        lay.addLayout(btn_row)

        dlg.exec()

    def _open_settings_dialog(self):
        """Open App Settings (theme, display preferences) as a persistent non-modal dialog."""
        if not hasattr(self, "_settings_dlg") or self._settings_dlg is None:
            from PyQt6.QtWidgets import QDialog, QVBoxLayout
            dlg = QDialog(self)
            dlg.setWindowTitle("App Settings")
            dlg.resize(660, 540)
            dlg.setStyleSheet(f"QDialog{{background:{BG_DARK};}}")
            lay = QVBoxLayout(dlg)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(self._settings_page)
            self._settings_dlg = dlg
        self._settings_dlg.show()
        self._settings_dlg.raise_()
        self._settings_dlg.activateWindow()

    def _open_help_dialog(self):
        """Navigate to Help & Reference in the Education sidebar section."""
        self._nav_rail_go_to("Help & Reference")

    # ── Scan orchestration ───────────────────────────────────────────────────

    @pyqtSlot(list)
    def _run_security_scans(self, tool_labels: list) -> None:
        """Navigate to the first selected security tool page (Phase 1)."""
        if not tool_labels:
            return
        if self._active_count > 0:
            self._set_status("Main scan in progress — please wait before running security tools.")
            return
        self._nav_rail_go_to(tool_labels[0])

    @pyqtSlot()
    def _start_full_scan(self):
        # Track whether this scan was triggered from the home page so we can
        # auto-navigate to Overview once device results arrive.
        self._scan_from_home = (
            hasattr(self, "_home_page")
            and self._stack.currentWidget() is self._home_page
        )
        # Reset UI
        self._m1_result = self._m2_result = self._m3_result = None
        self._m4_result = self._m5_result = None
        self._m1_grouping_active = False
        self._m1_group_btn.setVisible(False)
        self._m1_table.setRowCount(0)
        _add_skeleton_rows(self._m1_table)
        self._m2_table.setRowCount(0)
        self._m3_table.setRowCount(0)
        self._m4_table.setRowCount(0)
        self._m5_outage_table.setRowCount(0)
        self._net_devices_table.setRowCount(0)
        self._graph.reset()
        self._verdict.update("Pre-scan in progress (flushing caches & sweeping subnet)…", "UNKNOWN")
        self._set_scanning(True)
        self._active_count = 0

        # Run pre-scan first (flush + ping sweep), then kick off modules
        from workers.scan_worker import PreScanWorker
        self._prescan_worker = PreScanWorker(flush_caches=True)
        self._prescan_worker.status.connect(self._on_prescan_status)
        self._prescan_worker.done.connect(self._launch_modules)
        self._prescan_worker.start()

    @pyqtSlot(str)
    def _on_prescan_status(self, m: str):
        """Propagate pre-scan progress to the status bar and all module status labels."""
        self._set_status(m)
        for lbl in (self._m1_status, self._m2_status, self._m3_status,
                    self._m4_status, self._m5_status):
            lbl.setText(m)
        if hasattr(self, "_home_page"):
            self._home_page.set_scan_progress(m)

    @pyqtSlot()
    def _launch_modules(self):
        try:
            self._launch_modules_impl()
        except Exception as exc:
            self._set_status(f"Scan startup failed: {exc}")
            self._set_scanning(False)
            self._verdict.update(f"Scan failed to start: {exc}", "HIGH")

    def _launch_modules_impl(self):
        from workers.scan_worker import (
            Module1Worker, Module2Worker, Module3Worker,
            Module4Worker, Module5Worker,
        )

        gateway_ip   = self._net_info.get("gateway") if self._net_info else None
        gateway_mac  = self._net_info.get("gateway_mac") if self._net_info else None
        # Pre-populate rogue MACs from the previous scan (best-effort; M1 and M3 run concurrently)
        rogue_macs: list = []
        if self._m1_result:
            for _d in self._m1_result.get("devices", []):
                _risk = _d.risk_level if not isinstance(_d, dict) else _d.get("risk_level", "")
                _mac  = _d.mac        if not isinstance(_d, dict) else _d.get("mac", "")
                if _risk == "HIGH" and _mac:
                    rogue_macs.append(_mac)

        self._verdict.update("Scan in progress…", "UNKNOWN")
        self._workers.clear()
        self._active_count = 0
        # Refresh network info now that caches have been flushed (Fix #14)
        self._refresh_network_info()

        # Module 1 — always runs
        w1 = Module1Worker(self._offenders_path)
        w1.result.connect(self._on_m1_result)
        w1.status.connect(lambda m: (
            self._set_status(m), self._m1_status.setText(m),
            hasattr(self, "_home_page") and self._home_page.set_scan_progress(m),
        ))
        w1.error.connect(lambda e: self._m1_status.setText(f"Error: {e}"))
        w1.finished.connect(self._on_worker_done)
        self._workers.append(w1)
        self._active_count += 1

        _scan_qs = QSettings("NetSentinel", "NetSentinel")

        # Module 2 — needs admin + Scapy
        if _scan_qs.value("scan/stp_enabled", True, type=bool):
            _stp_dur = _scan_qs.value("scan/stp_duration_s", 10, type=int)
            w2 = Module2Worker(gateway_mac, duration=_stp_dur)
            w2.bpdu_found.connect(self._on_bpdu_found)
            w2.result.connect(self._on_m2_result)
            w2.status.connect(lambda m: (self._set_status(m), self._m2_status.setText(m)))
            w2.error.connect(lambda e: self._m2_status.setText(f"⚠ {e}"))
            w2.finished.connect(self._on_worker_done)
            self._workers.append(w2)
            self._active_count += 1

        # Module 3
        if _scan_qs.value("scan/storm_enabled", True, type=bool):
            _storm_dur = _scan_qs.value("scan/storm_duration_s", 10, type=int)
            w3 = Module3Worker(
                duration=_storm_dur,
                known_rogue_macs=rogue_macs,
            )
            w3.result.connect(self._on_m3_result)
            w3.status.connect(lambda m: (self._set_status(m), self._m3_status.setText(m)))
            w3.error.connect(lambda e: self._m3_status.setText(f"⚠ {e}"))
            w3.finished.connect(self._on_worker_done)
            self._workers.append(w3)
            self._active_count += 1

        # Module 4
        if _scan_qs.value("scan/wifi_enabled", True, type=bool):
            w4 = Module4Worker()
            w4.result.connect(self._on_m4_result)
            w4.status.connect(lambda m: (self._set_status(m), self._m4_status.setText(m)))
            w4.error.connect(lambda e: self._m4_status.setText(f"⚠ {e}"))
            w4.finished.connect(self._on_worker_done)
            self._workers.append(w4)
            self._active_count += 1

        # Module 5
        if _scan_qs.value("scan/dns_enabled", True, type=bool):
            w5 = Module5Worker(gateway_ip=gateway_ip)
            w5.ping_point.connect(self._on_ping_point)
            w5.dns_point.connect(self._on_dns_point)
            w5.result.connect(self._on_m5_result)
            w5.status.connect(lambda m: (self._set_status(m), self._m5_status.setText(m)))
            w5.error.connect(lambda e: self._m5_status.setText(f"⚠ {e}"))
            w5.finished.connect(self._on_worker_done)
            self._workers.append(w5)
            self._active_count += 1
            self._graph_timer.start()

        for w in self._workers:
            w.start()

    # ── Module result handlers ────────────────────────────────────────────────

    @pyqtSlot(dict)

    def _fetch_wan_ip(self) -> None:
        """Fetch the public WAN IP once per session in a background thread."""
        import threading

        def _do():
            try:
                from modules.internet_exposure import _get_wan_ip
                ip, _ = _get_wan_ip()
                if ip:
                    self._wan_ip = ip
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(0, lambda: self._geo_map_page.set_home_ip(ip))
            except Exception:
                pass

        threading.Thread(target=_do, daemon=True).start()

    def _show_ip_on_geo_map(self, ip: str) -> None:
        """Navigate to Geolocation Map and pin the given IP (from right-click).

        For private/LAN addresses the public WAN IP is used instead, since every
        device on the same network shares the same internet-facing location.
        """
        import ipaddress
        try:
            addr = ipaddress.ip_address(ip)
            is_private = addr.is_private or addr.is_loopback or addr.is_link_local
        except ValueError:
            is_private = False

        self._nav_rail_go_to("Geolocation Map")

        if is_private:
            if self._wan_ip:
                self._geo_map_page.navigate_to_ip(
                    self._wan_ip, label=f"Your Network  (local: {ip})"
                )
            else:
                # WAN IP not yet known — show placeholder then fetch and update
                self._geo_map_page._detail_ip.setText(ip)
                self._geo_map_page._detail_body.setText(
                    "Resolving your public WAN IP…\n"
                    "This takes a few seconds on first use."
                )
                self._geo_map_page._detail_links.setText("")
                import threading
                def _do_and_update():
                    try:
                        from modules.internet_exposure import _get_wan_ip
                        wan, _ = _get_wan_ip()
                        if wan:
                            self._wan_ip = wan
                            from PyQt6.QtCore import QTimer
                            QTimer.singleShot(0, lambda: (
                                self._geo_map_page.set_home_ip(wan),
                                self._geo_map_page.navigate_to_ip(
                                    wan, label=f"Your Network  (local: {ip})"
                                ),
                            ))
                    except Exception:
                        pass  # geolocation update is best-effort; WAN IP probe may fail
                threading.Thread(target=_do_and_update, daemon=True).start()
        else:
            try:
                self._geo_map_page.navigate_to_ip(ip, label="Threat Intel")
            except Exception:
                pass  # geo_map_page may not be initialised at this call site

    def _check_hw_autodetect(self) -> None:
        """Run hardware catalogue detection once per gateway IP per session."""
        gw_ip  = (self._net_info or {}).get("gateway", "").strip()
        gw_mac = (self._net_info or {}).get("gateway_mac", "").strip()
        if not gw_ip:
            return
        # Only re-run when the gateway IP changes (avoid redundant HTTP probes)
        if getattr(self, "_hw_detect_last_gw", "") == gw_ip:
            return
        existing = getattr(self, "_hw_detect_worker", None)
        if existing and existing.isRunning():
            return
        self._hw_detect_last_gw = gw_ip
        from workers.hw_detect_worker import HwDetectWorker
        worker = HwDetectWorker(ip=gw_ip, gateway_mac=gw_mac or None, parent=self)
        worker.detected.connect(self._on_hw_detected)
        self._hw_detect_worker = worker
        worker.start()

    @pyqtSlot(list)
    def _on_hw_detected(self, matches: list) -> None:
        if hasattr(self, "_hardware_integration_page"):
            self._hardware_integration_page.on_hardware_detected(matches)

    def _plugin_gateway_map(self) -> dict:
        """Return {ip: plugin_name} for all bundled plugins. Cached per session; cleared by _clear_plugin_gateway_cache."""
        if hasattr(self, "_plugin_gateway_map_cache"):
            return self._plugin_gateway_map_cache
        import ast
        plugins_dir = Path(__file__).parent.parent / "plugins"
        result: dict = {}
        if not plugins_dir.is_dir():
            self._plugin_gateway_map_cache = result
            return result
        for py in plugins_dir.glob("*.py"):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
                ip = name = None
                for node in ast.walk(tree):
                    if isinstance(node, ast.Assign):
                        for t in node.targets:
                            if isinstance(t, ast.Name):
                                if t.id == "HARDWARE_IP" and isinstance(node.value, ast.Constant):
                                    ip = node.value.value
                                elif t.id == "HARDWARE_NAME" and isinstance(node.value, ast.Constant):
                                    name = node.value.value
                if ip and name:
                    result[ip] = name
            except Exception:
                continue
        self._plugin_gateway_map_cache = result
        return result

    def _check_integration_banner(self, devices: list) -> None:
        """Show discovery banner when a scanned device matches an un-imported bundled plugin."""
        if not hasattr(self, "_m1_int_banner"):
            return
        try:
            gateway_map = self._plugin_gateway_map()
            if not gateway_map:
                self._m1_int_banner.setVisible(False)
                return

            # Find which plugin IPs are already imported
            from PyQt6.QtCore import QSettings as _QS
            _imported_paths = set(
                _QS("NetSentinel", "NetSentinel").value("hardware/plugin_paths", [], type=list)
            )
            import ast
            imported_ips: set = set()
            for p in _imported_paths:
                try:
                    tree = ast.parse(Path(p).read_text(encoding="utf-8", errors="replace"))
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Assign):
                            for t in node.targets:
                                if (isinstance(t, ast.Name) and t.id == "HARDWARE_IP"
                                        and isinstance(node.value, ast.Constant)):
                                    imported_ips.add(node.value.value)
                except Exception:
                    continue

            # Collect scanned IPs
            scanned_ips = {
                (d.ip if not isinstance(d, dict) else d.get("ip", ""))
                for d in devices
            }

            # Find matches: gateway IP in scan AND plugin not yet imported
            matches = [
                name for ip, name in gateway_map.items()
                if ip in scanned_ips and ip not in imported_ips
            ]

            if matches:
                names = ", ".join(matches[:3])
                if len(matches) > 3:
                    names += f" +{len(matches) - 3} more"
                self._m1_int_lbl.setText(
                    f"⚡  Hardware detected — {names} available for integration"
                )
                self._m1_int_banner.setVisible(True)
            else:
                self._m1_int_banner.setVisible(False)
        except Exception:
            self._m1_int_banner.setVisible(False)

    @pyqtSlot(dict)

    @pyqtSlot(dict)

    @pyqtSlot(str, str)
    def _on_plugin_page_added(self, path: str, label: str) -> None:
        """Create a nav item under Extend for a newly-installed hardware plugin."""
        from ui.pages.plugin_device_page import PluginDevicePage
        from ui.pages.hardware_integration_page import _validate_script
        from pathlib import Path as _P
        if path in getattr(self, "_plugin_pages", {}):
            return  # already registered
        ok, _, meta = _validate_script(path)
        hw_type  = meta.get("type", "other") if ok else "other"
        hw_ip    = meta.get("ip", "") if ok else ""
        cred_lbl = meta.get("credential_label", "Password") if ok else "Password"
        pg = PluginDevicePage(path, label, hw_type, hw_ip=hw_ip,
                              credential_label=cred_lbl, parent=None)
        pg.test_requested.connect(self._on_plugin_page_test)
        if not ok or not _P(path).is_file():
            pg.mark_unavailable()
        self._plugin_pages[path] = pg
        # Add to the stack and register under "Extend" in _nav_sections
        if self._stack.indexOf(pg) < 0:
            self._stack.addWidget(pg)
        self._nav_label_to_widget[label] = pg
        self._nav_page_to_section[label] = "Extend"
        entry = _NavEntry(
            label=label, page=pg,
            admin_required=False, audit_item=False,
            pinned=label in self._nav_pinned_labels,
        )
        extend_sec = next((s for s in self._nav_sections if s["name"] == "Extend"), None)
        if extend_sec:
            extend_sec["entries"].append(entry)
        self._log_hub_page.update_plugin_sources(
            [p._label for p in self._plugin_pages.values()]
        )
        self._refresh_hardware_badge()
        if hasattr(self, "_home_page"):
            self._home_page.refresh_hw_strip()
        # Immediately refresh the Extend flyout so the new nav item is visible
        # without requiring the user to click away and back (RULE-PL3).
        self._reload_section("Extend", force_open=True)
        # Navigate to the new page immediately so the user sees live status (P3-2).
        self._nav_rail_go_to(label)

    @pyqtSlot(str)
    def _on_plugin_page_removed(self, path: str) -> None:
        """Remove a plugin's nav item when it is deleted from the Hardware page."""
        pg = self._plugin_pages.pop(path, None)
        if pg is None:
            return
        label = pg._label
        # Remove from nav data structures
        self._nav_label_to_widget.pop(label, None)
        self._nav_page_to_section.pop(label, None)
        extend_sec = next((s for s in self._nav_sections if s["name"] == "Extend"), None)
        if extend_sec:
            extend_sec["entries"] = [
                e for e in extend_sec["entries"] if e.label != label
            ]
        # Remove from stack
        idx = self._stack.indexOf(pg)
        if idx >= 0:
            self._stack.removeWidget(pg)
        pg.deleteLater()
        self._log_hub_page.update_plugin_sources(
            [p._label for p in self._plugin_pages.values()]
        )
        self._refresh_hardware_badge()
        # Refresh the Extend flyout so the removed item disappears immediately (RULE-PL3).
        if getattr(self, "_nav_open_section", "") == "Extend":
            self._reload_section("Extend")

    @pyqtSlot(str, str, str)
    def _on_plugin_page_renamed(self, path: str, old_label: str, new_label: str) -> None:
        """P3-4: Propagate a plugin display-name rename to all nav data structures.

        Updates atomically: PluginDevicePage._label, _nav_label_to_widget,
        _nav_page_to_section, _nav_sections entries, pinned set, and breadcrumb.
        """
        pg = getattr(self, "_plugin_pages", {}).get(path)
        if pg is None or old_label == new_label:
            return

        pg._label = new_label

        # Update nav lookup dicts
        self._nav_label_to_widget.pop(old_label, None)
        self._nav_label_to_widget[new_label] = pg
        if hasattr(self, "_nav_page_to_section"):
            self._nav_page_to_section.pop(old_label, None)
            self._nav_page_to_section[new_label] = "Extend"

        # Update the _nav_sections entry in-place
        extend_sec = next((s for s in self._nav_sections if s["name"] == "Extend"), None)
        if extend_sec:
            for entry in extend_sec["entries"]:
                if entry.label == old_label:
                    entry.label = new_label
                    break

        # Update pinned labels if this item was pinned
        if old_label in self._nav_pinned_labels:
            self._nav_pinned_labels.discard(old_label)
            self._nav_pinned_labels.add(new_label)
            self._save_pinned_labels()

        # Reload flyout and update breadcrumb
        self._reload_section("Extend")
        if getattr(self, "_nav_current_page_label", "") == old_label:
            self._nav_current_page_label = new_label
            if hasattr(self, "_breadcrumb_lbl"):
                self._breadcrumb_lbl.setText(f"Extend  ›  {new_label}")

    def _reload_section(self, name: str, force_open: bool = False) -> None:
        """Reload the flyout for the named section and optionally force it open.

        Call this after any mutation to _nav_sections[name]["entries"] so the
        flyout widget immediately reflects the change (RULE-PL3).
        """
        sec = next((s for s in self._nav_sections if s["name"] == name), None)
        if sec is None or not hasattr(self, "_nav_flyout"):
            return
        entries = [
            (e.label, e.label in self._nav_pinned_labels,
             e.admin_required or e.audit_item)
            for e in sec["entries"]
        ]
        try:
            self._nav_flyout.load_section(
                title=name,
                entries=entries,
                active_label=self._nav_current_page_label,
                on_navigate=self._nav_rail_go_to,
                on_pin_toggle=self._on_rail_pin_toggle,
            )
            for _lbl, _clr in getattr(self, "_flyout_dots", {}).items():
                if _clr:
                    self._nav_flyout.apply_dot(_lbl, _clr)
            if force_open:
                self._nav_open_section = name
                if name in getattr(self, "_nav_rail_buttons", {}):
                    self._nav_rail_buttons[name].setChecked(True)
                    for _n, _b in self._nav_rail_buttons.items():
                        if _n != name:
                            _b.setChecked(False)
                self._nav_flyout.open()
        except Exception:
            pass  # flyout not yet built; safe to skip on very early calls

    def _update_monitor_badge(self, _active: bool = False) -> None:
        """Refresh all section badges and Home pills when log source state changes."""
        self._push_monitor_pills()

    def _refresh_section_badges(self, *, arp: bool = None, dhcp: bool = None,
                                 storm: bool = None, logger: bool = None) -> None:
        """Update rail section button dots for Monitor, Analysis, and Security Audit."""
        if not hasattr(self, "_nav_rail_buttons"):
            return
        if arp is None:
            arp = bool(self._arp_worker and self._arp_worker.isRunning())
        if dhcp is None:
            dhcp = bool(self._dhcp_worker and self._dhcp_worker.isRunning())
        if storm is None:
            storm = self._m3_monitoring_active()
        if logger is None:
            qs = QSettings("NetSentinel", "NetSentinel")
            logger = any(
                qs.value(k, False, type=bool)
                for k in qs.allKeys()
                if k.startswith("logging/") and k.endswith("_enabled")
            )
        # Monitor — left dot: green when any log source is active, muted when idle
        mon_btn = self._nav_rail_buttons.get("Monitor")
        if mon_btn:
            mon_btn.set_badge("")   # top-right badge not used for Monitor
            mon_btn.set_left_dot(GREEN if logger else TEXT_MUTED)
        # Analysis — left dot: green when ARP watch or broadcast storm is running
        ana_btn = self._nav_rail_buttons.get("Analysis")
        if ana_btn:
            ana_btn.set_badge("")   # top-right badge not used for Analysis
            ana_btn.set_left_dot(GREEN if (arp or storm) else TEXT_MUTED)
        # Security Audit — numeric red pill when unacked alerts exist, green dot when DHCP running
        sec_btn = self._nav_rail_buttons.get("Security Audit")
        if sec_btn:
            try:
                alert_count = len(self._store.get_unacked_alerts()) if self._store else 0
            except Exception:
                alert_count = 0
            if alert_count > 0:
                sec_btn.set_badge(alert_count)   # numeric red pill
                sec_btn.setToolTip(f"Security Audit — {alert_count} unacknowledged alert(s)")
            elif dhcp:
                sec_btn.set_badge(GREEN)
                sec_btn.setToolTip("Security Audit")
            else:
                sec_btn.set_badge(0)
                sec_btn.setToolTip("Security Audit")

        # POLISH-2: CVE Tracker — count of Open-state CVEs
        cve_btn = self._nav_rail_buttons.get("CVE Tracker")
        if cve_btn and self._store:
            try:
                open_cves = len(self._store.list_cve_lifecycles(state_filter="Open"))
            except Exception:
                open_cves = 0
            cve_btn.set_badge(open_cves if open_cves > 0 else 0)
            if open_cves:
                cve_btn.setToolTip(f"CVE Tracker — {open_cves} open CVE{'s' if open_cves != 1 else ''}")

        # POLISH-2: TLS & Exposure — count of expiring / expired certs
        tls_btn = self._nav_rail_buttons.get("TLS & Exposure")
        if tls_btn and self._store:
            try:
                certs = self._store.query_cert_status(hours=168)
                expired  = sum(1 for c in certs if getattr(c, "is_expired", False))
                expiring = sum(
                    1 for c in certs
                    if not getattr(c, "is_expired", False)
                    and 0 <= (getattr(c, "days_remaining", 999) or 999) <= 30
                )
            except Exception:
                expired = expiring = 0
            cert_total = expired + expiring
            if cert_total > 0:
                tls_btn.set_badge(RED if expired > 0 else AMBER)
                tls_btn.setToolTip(
                    f"TLS & Exposure — {expired} expired, {expiring} expiring soon"
                    if expired else f"TLS & Exposure — {expiring} cert{'s' if expiring != 1 else ''} expiring soon"
                )
            else:
                tls_btn.set_badge(0)

        # POLISH-2: Config Snapshots — drift indicator "≠" when auto-snapshot drifted
        base_btn = self._nav_rail_buttons.get("Config Snapshots")
        if base_btn:
            if getattr(self, "_baseline_has_drift", False):
                base_btn.set_badge(AMBER)
                base_btn.setToolTip("Config Snapshots — baseline drift detected")
            else:
                base_btn.set_badge(0)

    def _check_scheduled_scan(self) -> None:
        """SCHED-1: fire a full scan if enabled and next_ts has passed."""
        import time as _t, datetime as _dt
        qs = QSettings("NetSentinel", "NetSentinel")
        if not qs.value("sched_scan/enabled", False, bool):
            return
        next_ts = float(qs.value("sched_scan/next_ts", 0))
        if next_ts <= 0 or _t.time() < next_ts:
            return
        # Compute next run
        hours = int(qs.value("sched_scan/interval_hours", 24))
        hour  = int(qs.value("sched_scan/hour",   2))
        minute = int(qs.value("sched_scan/minute", 0))
        nxt = _dt.datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
        while nxt.timestamp() <= _t.time():
            nxt += _dt.timedelta(hours=hours)
        qs.setValue("sched_scan/next_ts", nxt.timestamp())
        # Refresh the settings label if page is visible
        if hasattr(self, "_settings_page"):
            try:
                self._settings_page._refresh_sched_scan_label()
            except Exception:
                pass
        # Fire the scan (reuse the existing full-scan trigger)
        try:
            self._start_scan()
        except Exception:
            pass

    def _check_lan_connectivity(self) -> None:
        """HEALTH-2: async socket probe; 3 failures → show amber offline banner."""
        from PyQt6.QtCore import QThread, pyqtSignal as _sig

        class _LanProbe(QThread):
            result = _sig(bool)

            def run(self) -> None:
                import socket
                try:
                    socket.setdefaulttimeout(3)
                    socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(
                        ("1.1.1.1", 53)
                    )
                    self.result.emit(True)
                except OSError:
                    self.result.emit(False)

        if getattr(self, "_lan_check_worker", None) and self._lan_check_worker.isRunning():
            return
        probe = _LanProbe(self)
        self._lan_check_worker = probe

        def _on_result(ok: bool) -> None:
            if ok:
                self._lan_fail_count = 0
                if hasattr(self, "_lan_banner"):
                    self._lan_banner.setVisible(False)
            else:
                self._lan_fail_count = getattr(self, "_lan_fail_count", 0) + 1
                if self._lan_fail_count >= 3 and hasattr(self, "_lan_banner"):
                    self._lan_banner.setVisible(True)

        probe.result.connect(_on_result)
        probe.start()

    def _check_weekly_digest(self) -> None:
        """Fire a weekly digest notification if conditions are met (RECUR-2)."""
        qs = QSettings("NetSentinel", "NetSentinel")
        if not qs.value("notif/weekly_digest_enabled", False, type=bool):
            return
        now = datetime.datetime.now()
        if now.weekday() != 6:  # Sunday only
            return
        time_str = qs.value("notif/weekly_digest_time", "09:00")
        try:
            h, m = (int(x) for x in time_str.split(":"))
        except Exception:
            return
        if now.hour < h or (now.hour == h and now.minute < m):
            return
        last_ts = float(qs.value("notif/weekly_digest_last_ts", 0))
        if now.timestamp() - last_ts < 6 * 86400:
            return
        qs.setValue("notif/weekly_digest_last_ts", now.timestamp())
        # SCHED-4: use digest_builder for full HTML digest
        try:
            from modules.digest_builder import build_digest_html
            body = build_digest_html(self._store) if self._store else "NetSentinel weekly digest"
        except Exception:
            if hasattr(self, "_notifications_page"):
                body = self._notifications_page._generate_weekly_summary()
            else:
                body = "NetSentinel weekly digest"
        if self._notif_router:
            try:
                from modules.notification_router import Alert as _Alert
                alert = _Alert(
                    rule_name="Weekly Digest",
                    rule_type="WEEKLY_DIGEST",
                    severity="INFO",
                    host="NetSentinel",
                    message=body,
                )
                self._notif_router.dispatch(alert)
            except Exception:
                pass

    def _set_flyout_dot(self, label: str, color: str) -> None:
        """Set or clear a status dot on a flyout item by label."""
        if not hasattr(self, "_flyout_dots"):
            self._flyout_dots: dict[str, str] = {}
        self._flyout_dots[label] = color
        if hasattr(self, "_nav_flyout"):
            self._nav_flyout.apply_dot(label, color)

    def _push_monitor_pills(self) -> None:
        """Push current monitoring states to Home pills, flyout dots, and section badges."""
        arp    = bool(self._arp_worker  and self._arp_worker.isRunning())
        dhcp   = bool(self._dhcp_worker and self._dhcp_worker.isRunning())
        storm  = self._m3_monitoring_active()
        qs     = QSettings("NetSentinel", "NetSentinel")
        logger = any(
            qs.value(k, False, type=bool)
            for k in qs.allKeys()
            if k.startswith("logging/") and k.endswith("_enabled")
        )
        if hasattr(self, "_home_page"):
            self._home_page.set_monitor_pills(arp, dhcp, storm, logger)
            if self._store is not None:
                try:
                    unacked = self._store.get_unacked_alerts()
                    offline = sum(
                        1 for d in self._store.get_known_devices().values()
                        if getattr(d, "last_seen", 0) and
                        (__import__("time").time() - d.last_seen) > 1800
                    )
                    self._home_page.set_action_needed(len(unacked), offline)
                    self._home_page.set_pending_alert_rows(unacked)
                except Exception:
                    pass
        # Flyout item dots — always reflect current state
        self._set_flyout_dot("ARP Spoof Watch",    GREEN if arp    else "")
        self._set_flyout_dot("DHCP Rogue Monitor", GREEN if dhcp   else "")
        self._set_flyout_dot("Broadcast Storm",    GREEN if storm  else "")
        self._set_flyout_dot("Network Logger",     GREEN if logger else "")
        # AUTO-1/2: Automation dot and tile — green if any rule fired in last 24h
        try:
            from modules.automation_hooks import get_engine as _get_ae
            _ae = _get_ae()
            _auto_ts = _ae.get_last_triggered()
            _auto_rules = _ae.get_rules()
            import time as _t
            _auto_active = _auto_ts > 0 and (_t.time() - _auto_ts) < 86400
            self._set_flyout_dot("Automation Hooks", GREEN if _auto_active else "")
            if hasattr(self, "_monitor_overview_page"):
                self._monitor_overview_page.set_automation_status(
                    len(_auto_rules), _auto_ts
                )
        except Exception:
            pass
        # HEALTH-1/4: push health + config completeness to Settings page
        if hasattr(self, "_settings_page"):
            try:
                import time as _t2
                bw_running = bool(
                    getattr(self, "_bandwidth_worker", None)
                    and self._bandwidth_worker.isRunning()
                )
                sched_running = bool(
                    getattr(self, "_report_scheduler_worker", None)
                    and self._report_scheduler_worker.isRunning()
                )
                db_ok = self._store is not None
                self._settings_page.refresh_health_status({
                    "Scheduler":           ("Running" if sched_running else "Stopped", sched_running),
                    "ARP Monitor":         ("Running" if arp           else "Stopped", arp),
                    "Bandwidth Monitor":   ("Running" if bw_running     else "Stopped", bw_running),
                    "Report Scheduler":    ("Running" if sched_running  else "Stopped", sched_running),
                    "Database":            ("OK"      if db_ok          else "Error",   db_ok),
                    "Logger":              ("Active"  if logger          else "Inactive", logger),
                })
                cve_count = 0
                rule_count = 0
                try:
                    from modules.automation_hooks import get_engine as _gae
                    rule_count = len(_gae().get_rules())
                except Exception:
                    pass
                try:
                    if self._store:
                        cve_count = len(self._store.list_cve_lifecycles() or [])
                except Exception:
                    pass
                self._settings_page.refresh_config_completeness(cve_count, rule_count)
            except Exception:
                pass
        # Section button badges
        self._refresh_section_badges(arp=arp, dhcp=dhcp, storm=storm, logger=logger)
        # Push to Monitor Overview page
        if hasattr(self, "_monitor_overview_page"):
            self._monitor_overview_page.set_arp_status(arp, alerted=False)
            self._monitor_overview_page.set_dhcp_status(dhcp)
            if self._store is not None:
                try:
                    self._monitor_overview_page.set_monitor_event_times(
                        arp=self._store.get_last_event_time("ARP"),
                        dhcp=self._store.get_last_event_time("DHCP"),
                        storm=self._store.get_last_event_time("Storm"),
                        iot=self._store.get_last_event_time("IoT"),
                        ports=self._store.get_last_event_time("Port"),
                        cve=self._store.get_last_event_time("CVE"),
                    )
                except Exception:
                    pass

    def _m3_monitoring_active(self) -> bool:
        """Return True if any scan worker (including storm) is currently running."""
        return any(
            w.isRunning()
            for w in getattr(self, "_workers", [])
            if hasattr(w, "isRunning")
        )

    def _refresh_hardware_badge(self) -> None:
        """Update the Extend section rail button tooltip to show active plugin count."""
        n = len(getattr(self, "_plugin_pages", {}))
        if n == 0:
            return
        btn = self._nav_rail_buttons.get("Extend")
        if btn:
            btn.setToolTip(f"Extend — {n} plugin{'s' if n != 1 else ''} active")

    @pyqtSlot(str)
    def _on_plugin_page_test(self, path: str) -> None:
        """Run the plugin once immediately when the Test button is clicked.

        Delegates to HardwareIntegrationPage._run_plugin so that:
        - only one PluginPollingWorker exists per plugin (no duplicate logins)
        - all signal connections are QObject→QObject (auto-queued, thread-safe)
        - the result flows through the existing plugin_result→_on_hardware_plugin_result
          path which calls page.update(data) → test_done()
        """
        self._hardware_integration_page._run_plugin(path)

    @pyqtSlot(object)
    def _on_speed_test_modem_forward(self, result) -> None:
        """Forward speed-test modem snapshot to the Hardware Hub."""
        sig = getattr(result, "modem_signal", None)
        if sig:
            self._on_modem_signal(sig)

    @pyqtSlot()
    def _on_modem_disconnect(self) -> None:
        """Stop any active ZTE polling worker and clear cached modem data."""
        worker = getattr(self, "_zte_worker", None)
        if worker:
            worker.stop()
            if not worker.wait(3000):
                worker.terminate()
                worker.wait(500)
            self._zte_worker = None
        self._last_modem_data = None
        from modules.network_infrastructure import hw_state
        hw_state.clear_modem()
        if hasattr(self, "_speed_test_page"):
            self._speed_test_page.clear_modem_credentials()

    @pyqtSlot(dict)
    def _on_modem_signal(self, data: dict) -> None:
        """Cache signal data, route to Overview tile, topology, and Monitor."""
        self._last_modem_data = data
        from modules.network_infrastructure import hw_state
        hw_state.update_modem(data, source="zte", hw_name="ZTE MC889")
        if hasattr(self, "_overview_page"):
            self._overview_page.on_modem_signal(data)
        # Update topology only when the modem's connection details change.
        # Skipping on every poll prevents a costly matplotlib redraw every 30 s.
        _topo_key = (data.get("wan_ip"), data.get("network_type"))
        if (_topo_key != getattr(self, "_last_modem_topo_key", None)
                and getattr(self, "_m1_result", None)
                and hasattr(self, "_topology_widget")):
            self._last_modem_topo_key = _topo_key
            try:
                gw_ip  = self._net_info.get("gateway")     if self._net_info else None
                gw_mac = self._net_info.get("gateway_mac") if self._net_info else None
                self._topology_widget.render(
                    self._m1_result.get("devices", []), gw_ip, gw_mac,
                    mesh_units=getattr(self, "_mesh_units", None),
                    mesh_enrichment=getattr(self, "_mesh_enrichment", None),
                    modem_data=data,
                )
            except Exception:
                pass
        # Monitor logging — live entry + throttled DB write
        if hasattr(self, "_log_hub_page"):
            from PyQt6.QtCore import QSettings
            import time as _time
            s = QSettings()
            if s.value("logging/modem_enabled", False, type=bool):
                self._log_hub_page.add_modem_entry(data)
                interval_s = s.value("logging/modem_interval_min", 5, type=int) * 60
                now = _time.time()
                if self._store and now - self._last_modem_log_ts >= interval_s:
                    try:
                        self._store.record_modem_signal(
                            network_type=data.get("network_type"),
                            signal_bars=data.get("signal_bars"),
                            cell_id=data.get("cell_id"),
                            enb_id=data.get("enb_id"),
                            mcc=data.get("mcc"),
                            mnc=data.get("mnc"),
                            wan_ip=data.get("wan_ip"),
                            nr5g_band=data.get("nr5g_band"),
                            nr5g_rsrp=data.get("nr5g_rsrp_dbm"),
                            nr5g_sinr=data.get("nr5g_sinr_db"),
                            nr5g_rsrq=data.get("nr5g_rsrq_db"),
                            nr5g_pci=data.get("nr5g_pci"),
                            nr5g_arfcn=data.get("nr5g_arfcn"),
                            lte_band=data.get("lte_band"),
                            lte_rsrp=data.get("lte_rsrp_dbm"),
                            lte_snr=data.get("lte_snr_db"),
                            lte_rsrq=data.get("lte_rsrq_db"),
                            lte_pci=data.get("lte_pci"),
                            lte_earfcn=data.get("lte_earfcn"),
                        )
                        self._last_modem_log_ts = now
                    except Exception:
                        pass  # log_modem_entry is best-effort; DB write failure is non-fatal

    @pyqtSlot(dict)
    def _on_avail_cycle_done(self, result: dict) -> None:
        """Route AvailabilityWorker cycle results to HistoryPage, HA page, and MQTT."""
        states = result.get("states", {})
        rtts   = result.get("rtts",   {})
        try:
            self._history_page.on_cycle_done(result)
        except Exception:
            pass
        try:
            self._ha_page.on_availability_update(states)
        except Exception:
            pass
        try:
            for _ip, _state in states.items():
                self._mqtt_page.on_uptime_state(_ip, _state, rtts.get(_ip) or 0.0)
        except Exception:
            pass

    @pyqtSlot(object)
    def _on_bpdu_found(self, bpdu):
        level = "HIGH" if bpdu.is_rogue else "CLEAN"
        _add_row(
            self._m2_table,
            [
                bpdu.src_mac, bpdu.bpdu_type, bpdu.root_mac,
                str(bpdu.bridge_priority),
                f"{bpdu.hello_time:.1f}", f"{bpdu.max_age:.1f}", f"{bpdu.forward_delay:.1f}",
                "\u26a0 YES" if bpdu.is_rogue else "No",
            ],
            level,
        )
        if bpdu.is_rogue:
            self._m2_status.setText(f"\u26a0 ROGUE ROOT BRIDGE: {bpdu.src_mac}")

    @pyqtSlot(dict)

    @pyqtSlot(object)

    @pyqtSlot(object)

    @pyqtSlot(object)
    def _on_ping_point(self, pt):
        if self._m5_stack.currentIndex() == 0:
            self._m5_stack.setCurrentIndex(1)
        self._graph.add_ping_point(pt.timestamp, pt.target, pt.rtt_ms)

    @pyqtSlot(object)
    def _on_dns_point(self, pt):
        self._graph.add_ping_point(pt.timestamp, "DNS", pt.rtt_ms)


    def _refresh_graph(self):
        self._graph.redraw()

    @pyqtSlot()
    def _on_worker_done(self):
        self._active_count -= 1
        if self._active_count <= 0:
            self._active_count = 0
            self._set_scanning(False)
            self._set_status("Scan complete.")
            self._refresh_pulse_bar()
            self._graph_timer.stop()
            self._graph.redraw()
            self._workers.clear()
            self._push_monitor_pills()   # clear Analysis badge + Broadcast Storm dot
            if self._auto_report_pending:
                self._auto_report_scan_done = True
                self._maybe_auto_report()
            if getattr(self, "_pending_benchmark", False):
                self._pending_benchmark = False
                self._run_benchmark()

    # ── Overall verdict ───────────────────────────────────────────────────────

    def _update_overall_verdict(self):
        verdicts = []
        level = "CLEAN"

        if self._m1_result:
            v = self._m1_result.get("plain_verdict", "")
            if v:
                verdicts.append(v)
            if self._m1_result.get("high_risk_count", 0) > 0:
                level = "HIGH"

        if self._m2_result:
            v = self._m2_result.get("plain_verdict", "")
            if v:
                verdicts.append(v)
            if self._m2_result.get("rogue_count", 0) > 0:
                level = "HIGH"

        if self._m3_result:
            storm_level = (
                self._m3_result.storm_level
                if not isinstance(self._m3_result, dict)
                else self._m3_result.get("storm_level", "CLEAN")
            )
            v = (
                self._m3_result.plain_verdict
                if not isinstance(self._m3_result, dict)
                else self._m3_result.get("plain_verdict", "")
            )
            if v:
                verdicts.append(v)
            if storm_level in ("STORM", "WARNING") and level == "CLEAN":
                level = "MEDIUM" if storm_level == "WARNING" else "HIGH"

        if self._m4_result:
            v = (
                self._m4_result.plain_verdict
                if not isinstance(self._m4_result, dict)
                else self._m4_result.get("plain_verdict", "")
            )
            if v:
                verdicts.append(v)
            rogue_c = (
                self._m4_result.rogue_count
                if not isinstance(self._m4_result, dict)
                else self._m4_result.get("rogue_count", 0)
            )
            if rogue_c and level == "CLEAN":
                level = "MEDIUM"

        if self._m5_result:
            v = (
                self._m5_result.plain_verdict
                if not isinstance(self._m5_result, dict)
                else self._m5_result.get("plain_verdict", "")
            )
            if v:
                verdicts.append(v)
            stp_sigs = (
                self._m5_result.stp_signatures
                if not isinstance(self._m5_result, dict)
                else self._m5_result.get("stp_signatures", [])
            )
            if stp_sigs:
                level = "HIGH"

        if self._diag_result:
            v = getattr(self._diag_result, "plain_verdict", "") or ""
            if v:
                verdicts.append(f"Diagnostics: {v}")
            # Failed ping to gateway → escalate
            gw_ping = next(
                (p for p in getattr(self._diag_result, "ping_results", []) if p.host == "Gateway"),
                None,
            )
            if gw_ping and gw_ping.status == "FAIL" and level == "CLEAN":
                level = "HIGH"
            # DNS leak
            leak = getattr(self._diag_result, "dns_leak", None)
            if leak and getattr(leak, "leak_detected", False) and level == "CLEAN":
                level = "MEDIUM"

        combined = "\n\n".join(verdicts) if verdicts else "Scan in progress..."
        self._verdict.update(combined, level)
        # Show the compact status badge once real data is available
        self._verdict_badge.setText(f"\u25cf {level}")
        self._verdict_badge.setStyleSheet(
            f"color:{_color_for_level(level)}; font-size:11px; font-weight:bold; padding:0 8px;"
            "background:transparent; border:none;"
        )
        self._verdict_badge.setVisible(True)

    # ── Export ────────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _run_full_report(self):
        """Run all modules + diagnostics, then auto-open the HTML report. No dialogs."""
        if self._active_count > 0:
            self._set_status("Scan already in progress — please wait.")
            return

        # Arm the auto-report flags
        self._auto_report_pending   = True
        self._auto_report_scan_done = False
        # Diagnostics: start them now; mark done immediately if they were already run
        self._auto_report_diag_done = False
        # Force all scan modules on for the full report run
        _rqs = QSettings("NetSentinel", "NetSentinel")
        for _k in ("stp", "storm", "wifi", "dns"):
            _rqs.setValue(f"scan/{_k}_enabled", True)
        if hasattr(self, "_overview_page"):
            self._overview_page.set_report_running(True)

        # Start diagnostics in the background (runs in parallel with the scan)
        if self._diag_worker and self._diag_worker.isRunning():
            self._auto_report_diag_done = True   # already running; result will arrive
        else:
            self._start_diagnostics()

        # Start the full scan (M1–M5 all checked above)
        self._start_full_scan()

    def _maybe_auto_report(self) -> None:
        """Generate and open the report once both scan and diagnostics are done."""
        if not self._auto_report_pending:
            return
        if not (self._auto_report_scan_done and self._auto_report_diag_done):
            return
        self._auto_report_pending   = False
        self._auto_report_scan_done = False
        self._auto_report_diag_done = False
        if hasattr(self, "_overview_page"):
            self._overview_page.set_report_running(False)
        try:
            import datetime as _dt
            from modules.utils import get_app_data_dir
            from modules.report_exporter import save_report
            _ts  = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            _out = get_app_data_dir() / "reports" / f"netsentinel_report_{_ts}.html"
            _out.parent.mkdir(parents=True, exist_ok=True)
            _level = "CLEAN"
            if self._m1_result and self._m1_result.get("high_risk_count", 0):
                _level = "HIGH"
            if self._m2_result and self._m2_result.get("rogue_count", 0):
                _level = "HIGH"
            _verdict = self._verdict._text.text() if hasattr(self._verdict, "_text") else ""
            save_report(
                _out,
                module1_data=self._m1_result,
                module2_data=self._m2_result,
                module3_data=self._m3_result,
                module4_data=self._m4_result,
                module5_data=self._m5_result,
                diagnostics_data=self._diag_result,
                network_info_data=self._net_info if self._net_info else None,
                overall_verdict=_verdict,
                overall_level=_level,
            )
            webbrowser.open(_out.as_uri())
            self._set_status(f"Report ready — {_out.name}")
        except Exception as _exc:
            self._set_status(f"Auto-report failed: {_exc}")
            if hasattr(self, "_overview_page"):
                self._overview_page.set_report_running(False)

    @pyqtSlot()
    def _export_report(self):
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        default_dir = str(Path.home() / "Desktop")

        path_str, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Report",
            str(Path(default_dir) / f"netsentinel_report_{ts}.html"),
            "HTML Report (*.html);;JSON Export (*.json);;CSV Device List (*.csv);;Nmap XML (*.xml);;All Files (*)",
        )
        if not path_str:
            return

        out = Path(path_str)

        # Determine overall level
        level = "CLEAN"
        if self._m1_result and self._m1_result.get("high_risk_count", 0):
            level = "HIGH"
        if self._m2_result and self._m2_result.get("rogue_count", 0):
            level = "HIGH"
        overall = self._verdict._text.text()

        try:
            suffix = out.suffix.lower()
            if suffix == ".json":
                from modules.report_exporter import save_json_report
                save_json_report(
                    out,
                    module1_data=self._m1_result,
                    module2_data=self._m2_result,
                    module3_data=self._m3_result,
                    module4_data=self._m4_result,
                    module5_data=self._m5_result,
                    diagnostics_data=self._diag_result,
                    network_info_data=self._net_info if self._net_info else None,
                    overall_verdict=overall,
                    overall_level=level,
                )
            elif suffix == ".csv":
                from modules.report_exporter import save_csv_report
                save_csv_report(out, self._m1_result)
            elif suffix == ".xml":
                from modules.report_exporter import save_nmap_xml_report
                ps_result = getattr(self, "_last_portscan_result", None)
                save_nmap_xml_report(out, self._m1_result, ps_result)
            else:
                from modules.report_exporter import save_report
                save_report(
                    out,
                    module1_data=self._m1_result,
                    module2_data=self._m2_result,
                    module3_data=self._m3_result,
                    module4_data=self._m4_result,
                    module5_data=self._m5_result,
                    diagnostics_data=self._diag_result,
                    network_info_data=self._net_info if self._net_info else None,
                    overall_verdict=overall,
                    overall_level=level,
                )
                webbrowser.open(out.as_uri())
            self._set_status(f"Report saved: {out.name}")
        except Exception as exc:
            self._set_status(f"Export failed: {exc}")

    # ── Network Info ──────────────────────────────────────────────────────────

    def _refresh_network_info(self):
        from workers.scan_worker import NetworkInfoWorker
        # Guard: don't start a second worker if one is already running
        if hasattr(self, "_net_info_worker") and self._net_info_worker and self._net_info_worker.isRunning():
            return
        self._net_info_worker = NetworkInfoWorker()
        self._net_info_worker.result.connect(self._update_net_info_ui)
        self._net_info_worker.error.connect(lambda e: self._net_info_label.setText(f"Error: {e}"), Qt.ConnectionType.QueuedConnection)
        self._net_info_worker.start()
        self._net_info_label.setText("Refreshing network information…")

    # ── Diagnostics ───────────────────────────────────────────────────────────

    @pyqtSlot()
    def _start_diagnostics(self):
        from workers.scan_worker import DiagnosticsWorker
        if self._diag_worker and self._diag_worker.isRunning():
            return
        self._diag_ping_table.setRowCount(0)
        self._diag_dns_table.setRowCount(0)
        self._diag_trace_table.setRowCount(0)
        for lbl in self._diag_http_labels:
            lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; padding:0 10px;")
            name = lbl.text().split(":")[0].lstrip("● ")
            lbl.setText(f"● {name}: testing…")
        self._update_stat(self._diag_speed_lbl, "…")
        self._update_stat(self._diag_public_lbl, "…")
        self._update_stat(self._diag_dns_lbl, "…")
        self._update_stat(self._diag_gw_lbl, "…")
        self._btn_diag.setEnabled(False)
        self._diag_status_lbl.setText("Running diagnostics…")

        gw = self._net_info.get("gateway") if self._net_info else None
        self._diag_worker = DiagnosticsWorker(gateway_ip=gw)
        self._diag_worker.status.connect(lambda m: self._diag_status_lbl.setText(m), Qt.ConnectionType.QueuedConnection)
        self._diag_worker.result.connect(self._on_diag_result)
        self._diag_worker.error.connect(
            lambda e: (
                self._diag_status_lbl.setText(f"Error: {e}"),
                self._btn_diag.setEnabled(True),
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        self._diag_worker.finished.connect(self._on_diag_worker_finished)
        self._diag_worker.start()

    @pyqtSlot()
    def _on_diag_worker_finished(self):
        self._btn_diag.setEnabled(True)
        # If a diagnostics error prevented _on_diag_result from firing, we still
        # need to unblock the auto-report so it doesn't wait forever.
        if self._auto_report_pending and not self._auto_report_diag_done:
            self._auto_report_diag_done = True
            self._maybe_auto_report()





