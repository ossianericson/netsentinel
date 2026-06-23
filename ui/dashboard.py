"""
Main Dashboard — NetSentinel network security scanner and monitor.
"""

import datetime
import html
import webbrowser
from pathlib import Path

from PyQt6.QtCore import Qt, QPropertyAnimation, QSettings, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.npcap_banner import NpcapMissingBanner
from ui.perf_audit import profile_page_init
from ui.styles import (
    ACCENT, ACCENT_LITE, BG_CARD, BG_DARK, BORDER, CHART_BG, CHART_GRID,
    CHART_PLOT_BG, GREEN, MAIN_STYLE, NAV_DIVIDER,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)
from modules.utils import get_offenders_path, is_admin


# ─── Module Tab Helpers (defined in ui/tabs.py, re-exported here) ────────────
from ui.tabs import (
    _table, _add_row,
    _empty_state_widget,
)
from ui.tabs_helpers import _page_header  # noqa: F401 — re-exported; used via lazy `from ui.dashboard import _page_header`

__all__ = ["Dashboard", "_page_header"]


# --- Activity-Rail Navigation widgets (extracted to ui/nav/rail.py) -----------
from ui.nav.rail import (
    _ClickLabel, _SmoothProgressBar,
)


# _PAGE_HELP is defined in ui/help.py and imported at the top of this file.



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
from ui.nav.builder import _NavBuilderMixin
from ui.monitor_state import (
    _color_for_level,  # noqa: F401 — re-exported; used via lazy `from ui.dashboard import _color_for_level`
    _MonitorStateMixin,
)
from ui.plugin_page_mixin import _PluginPageMixin



class Dashboard(ScanResultMixin, AppHeaderMixin, TabBuilderMixin,
               _NavBuilderMixin, _MonitorStateMixin, _PluginPageMixin, QMainWindow):
    _update_available         = pyqtSignal(str)
    global_time_range_changed = pyqtSignal(float)  # hours: float
    _wan_ip_ready             = pyqtSignal(str)        # WAN IP fetched → geo map set_home_ip (thread-safe)
    _wan_ip_nav_req           = pyqtSignal(str, str)   # WAN IP + label → set_home_ip + navigate_to_ip

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
        from ui.styles import get_theme_manager as _gtm
        _gtm().theme_changed.connect(self._on_theme_changed)
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
        self._m1_result   = None
        self._m2_result   = None
        self._m3_result   = None
        self._m4_result   = None
        self._m5_result   = None
        self._lldp_result = None  # list[LldpNeighbor] from Sprint 5 LLDP worker

        # Security audit coordinator state
        self._pending_security_tools: list = []
        self._security_audit_total: int = 0

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

        # ScanRegistry — per-label state tracking for Sprint A freshness UX
        # Keys: canonical nav label strings (e.g. "Port Scan (TCP)")
        # Values: {"state": "never"|"running"|"fresh"|"stale"|"error", "ts": float, "error": str|None}
        self._scan_registry: dict = {}
        # Flyout dot colours — persisted between flyout open/close by _nav_rail_toggle
        self._flyout_dots: dict = {}

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
        _t = QTimer(self); _t.setSingleShot(True); _t.timeout.connect(self._check_weekly_digest); _t.start(5000)

        # HEALTH-2: offline/no-LAN detection — 3 consecutive failures show amber banner
        self._lan_fail_count: int = 0
        self._lan_check_worker = None
        self._lan_check_timer = QTimer()
        self._lan_check_timer.setInterval(30_000)   # 30 s
        self._lan_check_timer.timeout.connect(self._check_lan_connectivity)
        self._lan_check_timer.start()
        _t = QTimer(self); _t.setSingleShot(True); _t.timeout.connect(self._check_lan_connectivity); _t.start(8000)

        # SCHED-1: scheduled full scan — 60s polling timer checks if next_ts has passed
        self._sched_scan_timer = QTimer()
        self._sched_scan_timer.setInterval(60_000)  # check every minute
        self._sched_scan_timer.timeout.connect(self._check_scheduled_scan)
        self._sched_scan_timer.start()
        _t = QTimer(self); _t.setSingleShot(True); _t.timeout.connect(self._check_scheduled_scan); _t.start(10_000)

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

        # Ctrl+L — Network Logger
        _loghub_sc = QShortcut(QKeySequence("Ctrl+L"), self)
        _loghub_sc.activated.connect(lambda: self._nav_rail_go_to("Network Logger"))

        # Ctrl+Shift+H — Quick Check floating window (S8-2)
        self._quick_check_window = None
        _quickcheck_sc = QShortcut(QKeySequence("Ctrl+Shift+H"), self)
        _quickcheck_sc.activated.connect(self._show_quick_check_window)

        # Pinned pages — persisted across sessions
        self._nav_pinned_labels: list = self._load_pinned_labels()
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

    # ── Quick Check floating window (S8-2) ────────────────────────────────────

    def _show_quick_check_window(self) -> None:
        """Toggle the compact Quick Check floating window (Ctrl+Shift+H)."""
        win = getattr(self, "_quick_check_window", None)
        if win is not None and win.isVisible():
            win.close()
            return
        from ui.widgets.quick_check_window import QuickCheckWindow
        win = QuickCheckWindow(store=self._store, parent=self)
        screen = self.screen() or win.screen()
        if screen is not None:
            geo = screen.availableGeometry()
            win.move(geo.right() - win.width() - 24, geo.bottom() - win.height() - 24)
        win.show()
        self._quick_check_window = win

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

        # Monitor resume bar — hidden; shown when monitors are auto-resumed at startup
        self._monitor_resume_bar = self._build_monitor_resume_bar()
        self._monitor_resume_bar.setVisible(False)
        root.addWidget(self._monitor_resume_bar)

        # Main area: sidebar+content fills window
        _main = profile_page_init(self._build_tabs)
        self._verdict_area = self._build_verdict_area()  # kept alive for exports; not shown
        root.addWidget(_main, 1)

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
            lambda: self._nav_rail_go_to("Dashboard"))
        self._pulse_scan_lbl.clicked.connect(
            lambda: self._nav_rail_go_to("Dashboard"))
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

    # ── How to Fix dialog (shared by M1 / M2 / M3 context menus) ─────────────

    def _show_how_to_fix(self, title: str, remediation: str):
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox

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
                     "_snmp_worker", "_snmp_if_worker", "_syn_worker", "_udp_worker", "_cve_worker",
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
                pass  # non-fatal
        _os._exit(0)


    def _show_alert_toast(self, alert) -> None:
        """Show a desktop notification for a fired alert."""
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
        self._nav_rail_go_to("Threat Intel")
        if hasattr(self, "_threat_intel_page") and ip:
            self._threat_intel_page.check_ip(ip)

    # ── TIME-2: View in Network Logger from alert drawer ──────────────────────

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

    def _build_monitor_resume_bar(self) -> "QWidget":
        from PyQt6.QtWidgets import QWidget as _W, QHBoxLayout as _HL, QLabel as _L, QPushButton as _B
        from PyQt6.QtCore import Qt as _Qt
        from ui.styles import AMBER, TEXT_PRIMARY, BG_HOVER, NAV_BAR
        container = _W()
        container.setObjectName("monitorResumeBar")
        container.setFixedHeight(28)
        container.setStyleSheet(
            f"QWidget#monitorResumeBar {{ background:{AMBER}18;"
            f" border-bottom: 1px solid {AMBER}55; }}"
        )
        row = _HL(container)
        row.setContentsMargins(12, 0, 8, 0)
        row.setSpacing(6)
        icon = _L("▶")
        icon.setStyleSheet(f"color:{AMBER}; font-size:11px; background:transparent; border:none;")
        row.addWidget(icon)
        self._monitor_resume_lbl = _L("")
        self._monitor_resume_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:11px; background:transparent; border:none;"
        )
        row.addWidget(self._monitor_resume_lbl, 1)
        btn_stop = _B("Stop all")
        btn_stop.setFixedHeight(20)
        btn_stop.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{AMBER}; border:1px solid {AMBER};"
            f" border-radius:3px; font-size:10px; padding:0 8px; }}"
            f"QPushButton:hover {{ background:{AMBER}22; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
        )
        btn_stop.clicked.connect(self._stop_all_resumed_monitors)
        row.addWidget(btn_stop)
        lbl_dismiss = _L("×")
        lbl_dismiss.setFixedSize(24, 24)
        lbl_dismiss.setAlignment(_Qt.AlignmentFlag.AlignCenter)
        lbl_dismiss.setCursor(_Qt.CursorShape.PointingHandCursor)
        lbl_dismiss.setStyleSheet(
            f"color:{NAV_BAR}; font-size:16px; font-weight:bold; background:transparent;"
        )
        lbl_dismiss.mousePressEvent = lambda _e: container.hide()
        row.addWidget(lbl_dismiss)
        return container

    def _show_monitor_resume_bar(self, resumed: list[str]) -> None:
        count = len(resumed)
        names = ", ".join(resumed)
        self._monitor_resume_lbl.setText(
            f"{count} monitor{'s' if count != 1 else ''} resumed from last session: {names}"
        )
        self._monitor_resume_bar.setVisible(True)

    def _stop_all_resumed_monitors(self) -> None:
        if self._arp_worker and self._arp_worker.isRunning():
            self._arp_worker.stop()
            self._save_monitor_state("arp", False)
        if self._bw_worker and self._bw_worker.isRunning():
            self._bw_worker.stop()
            self._save_monitor_state("bandwidth", False)
        if self._sched_worker and self._sched_worker.isRunning():
            self._sched_worker.stop()
            self._save_monitor_state("scheduler", False)
        self._monitor_resume_bar.setVisible(False)

    def _restore_running_monitors(self) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        keys = set(qs.value("monitors/was_running", "", type=str).split(",")) - {""}
        resumed: list[str] = []
        if "arp" in keys and not (self._arp_worker and self._arp_worker.isRunning()):
            self._start_arp_monitor()
            resumed.append("ARP Watch")
        if "bandwidth" in keys and not (self._bw_worker and self._bw_worker.isRunning()):
            self._start_bandwidth_monitor()
            resumed.append("Live Bandwidth")
        if "scheduler" in keys and not (self._sched_worker and self._sched_worker.isRunning()):
            self._start_scheduler()
            resumed.append("Scheduled Scans")
        if resumed:
            self._show_monitor_resume_bar(resumed)

    # ── First-run onboarding ──────────────────────────────────────────────────

    def _show_welcome_overlay(self) -> None:
        """Entry point called at startup — shows coach mark on first launch."""
        self._maybe_start_guided_tour()
        self._maybe_start_onboarding()

    def _maybe_start_guided_tour(self) -> None:
        """Fire the 5-step v2 guided tour on first launch (tour/v2_done key)."""
        from ui.guided_tour import GuidedTour
        if not GuidedTour.should_show():
            return
        _t = QTimer(self)
        _t.setSingleShot(True)
        _t.timeout.connect(lambda: GuidedTour(self).start())
        _t.start(600)

    def restart_guided_tour(self) -> None:
        """Public method — called from Settings 'Restart guided tour' button."""
        from ui.guided_tour import GuidedTour
        GuidedTour(self).restart()

    def _maybe_start_onboarding(self) -> None:
        from ui.onboarding import should_show_onboarding, mark_onboarding_done
        if not should_show_onboarding():
            return
        self._nav_rail_go_to("Home")
        from ui.widgets.coach_mark import CoachMarkChain

        def _step1_done() -> None:
            mark_onboarding_done()
            from PyQt6.QtCore import QSettings as _QS
            # Mark tour as done immediately so scan-result handler doesn't also trigger it
            _QS("NetSentinel", "NetSentinel").setValue("tour/post_scan_done", True)
            # Block the scan-result auto-jump while the guided tour is running
            self._onboarding_active = True
            # Start scan in background (no _scan_from_home flag — tour handles navigation)
            _t = QTimer(self)
            _t.setSingleShot(True)
            _t.timeout.connect(self._start_full_scan)
            _t.start(300)
            # Start 8-step tour immediately (doesn't wait for scan to complete)
            _t2 = QTimer(self)
            _t2.setSingleShot(True)
            _t2.timeout.connect(self._start_post_scan_coach_marks)
            _t2.start(800)

        def _step1_skipped() -> None:
            # User pressed × on the initial coach mark — respect the dismissal.
            # tour/post_scan_done is NOT set here so the 9-step tour still fires
            # after the user's first manual scan from the Home page.
            mark_onboarding_done()
            # Don't start scan or tour; stay on current page

        # Store reference on self — prevents Python GC from collecting the chain
        # before the 400 ms delay fires and the signal connections are alive.
        def _pick_home_scan_btn():
            hp = getattr(self, "_home_page", None)
            if hp is None:
                return None
            compact = getattr(hp, "_btn_rescan_compact", None)
            if compact is not None and compact.isVisible():
                return compact
            return getattr(hp, "_btn_scan", None)

        self._onboarding_chain = CoachMarkChain(
            self,
            [{
                "title":         "Step 1 of 9 — Scan your network",
                "body":          "Click either scan button to start — the one here on this page or the one in the header bar (always visible). Your 8-step guided tour follows automatically.",
                "delay_ms":      400,
                "auto_dismiss_ms": 0,   # stays until user explicitly clicks action button
                "target":        _pick_home_scan_btn,
                "extra_targets": [lambda: getattr(self, "_header_scan_btn", None)],
                "prefer_side":   "below",
                "action_text":   "Start Scan →",
            }],
            on_done=_step1_done,
            on_skip=_step1_skipped,
        )
        self._onboarding_chain.start()

    def _start_logger_if_needed(self) -> None:
        """Start the background network logger if it is not already running."""
        if not (getattr(self, "_logger_worker", None) and self._logger_worker.isRunning()):
            self._toggle_logger()

    def _start_post_scan_coach_marks(self) -> None:
        """Show 8 coach marks walking the user through key sections of the app."""
        from ui.widgets.coach_mark import CoachMarkChain
        self._onboarding_active = True  # block scan-result auto-jump for the tour duration

        def _open_section(name: str) -> None:
            if self._nav_open_section == name and self._nav_flyout.maximumWidth() > 0:
                return  # already open — nothing to do
            self._nav_rail_toggle(name)

        def _tour_done() -> None:
            self._onboarding_active = False
            from PyQt6.QtCore import QSettings as _QS
            _QS("NetSentinel", "NetSentinel").setValue("tour/v1_done", True)
            self._nav_rail_go_to("Dashboard")

        def _tour_skipped() -> None:
            self._onboarding_active = False
            from PyQt6.QtCore import QSettings as _QS
            _QS("NetSentinel", "NetSentinel").setValue("tour/v1_done", True)

        def _tab_proxy(container, tab_index: int) -> QWidget:
            """Transparent child QWidget covering one QTabBar tab — used as a ring target."""
            tab_bar = container.tabBar()
            rect = tab_bar.tabRect(tab_index)
            w = QWidget(tab_bar)
            w.setGeometry(rect)
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            w.setStyleSheet("background: transparent; border: none;")
            w.show()
            return w

        self._post_scan_chain = CoachMarkChain(
            self,
            [
                # ── Pair 1: Monitor section — rail button + flyout item ───────
                {
                    # Open the Monitor flyout; delay_ms waits for the 150 ms
                    # slide animation to settle before the ring is positioned.
                    "on_show":      lambda: _open_section("Monitor"),
                    "delay_ms":     300,
                    "target":       lambda: self._nav_rail_buttons.get("Monitor"),
                    "title":        "Step 2 of 9 — Monitor",
                    "body":         "Click the Monitor icon to open the rail menu — it lists live streams like bandwidth, connections, availability, and more.",
                },
                {
                    # Navigate to Network Logger and select Log Sources tab so the
                    # user can see the page content while the flyout item is ringed.
                    # Flyout stays open (nav_rail_go_to does not close it).
                    "on_show":      lambda: (
                        self._nav_rail_go_to("Network Logger"),
                        self._logging_container.setCurrentIndex(0),
                    ),
                    "delay_ms":     200,
                    "target":       lambda: self._nav_flyout._items.get("Network Logger"),
                    "prefer_side":  "right",
                    "title":        "Step 3 of 9 — Network Logger",
                    "body":         "Click 'Network Logger' to open this page. The Log Sources tab lets you enable or disable each monitoring source.",
                },
                # ── Network Logger: Activity Log tab ─────────────────────────
                {
                    # Navigate to Network Logger, close flyout, select Activity Log tab.
                    # delay_ms lets the layout commit so the tab proxy is correctly positioned.
                    "on_show":      lambda: (
                        self._nav_rail_go_to("Network Logger"),
                        self._nav_flyout.close_panel(),
                        self._logging_container.setCurrentIndex(1),
                    ),
                    "delay_ms":     200,
                    "target":       lambda: _tab_proxy(self._logging_container, 1),
                    "prefer_side":  "right",
                    "title":        "Step 4 of 9 — Activity Log",
                    "body":         "The Activity Log tab shows a live timeline of all monitoring events — RTT, jitter, modem signal, and more.",
                },
                # ── Network Logger: source filter chips ──────────────────────
                {
                    # Switch to Activity Log tab so the source chips are visible.
                    # Do NOT auto-click a chip — let the user interact.
                    "on_show":      lambda: self._logging_container.setCurrentIndex(1),
                    "target":       lambda: getattr(self._log_hub_page, "_toggle_btns", {}).get("net"),
                    # card_target anchors the card to the tab bar — same position as step 4
                    "card_target":  lambda: self._logging_container.tabBar(),
                    "prefer_side":  "right",
                    "title":        "Step 5 of 9 — Source filters",
                    "body":         "These chips filter the log by source. Click 'Network RTT' to focus on ping latency data only.",
                },
                # ── Pair 2: Discover → Devices ─────────────────────────────────
                # Devices comes after 3 Monitor steps so the scan (~14 s) has time to populate
                {
                    "on_show":      lambda: _open_section("Discover"),
                    "target":       lambda: self._nav_rail_buttons.get("Discover"),
                    "title":        "Step 6 of 9 — Discover",
                    "body":         "Click the Discover icon to open this menu. It contains your device inventory, network map, WiFi, and more.",
                },
                {
                    # Navigate to Devices so the inventory is visible; flyout stays open
                    # (scan has had ~4 steps worth of time to populate the device list).
                    "on_show":      lambda: self._nav_rail_go_to("Devices"),
                    "target":       lambda: self._nav_flyout._items.get("Devices"),
                    "title":        "Step 7 of 9 — Network Devices",
                    "body":         "This is your device inventory — every device on the network with type, MAC address, and risk level. Right-click any row for actions.",
                },
                # ── Pair 3: Extend → Hardware Hub ──────────────────────────────
                {
                    "on_show":      lambda: _open_section("Extend"),
                    "target":       lambda: self._nav_rail_buttons.get("Extend"),
                    "title":        "Step 8 of 9 — Extend",
                    "body":         "Click the Extend icon to manage hardware integrations — modem, mesh router, or custom USB devices.",
                },
                {
                    # Navigate to Hardware so the hub is visible; flyout stays open.
                    "on_show":      lambda: self._nav_rail_go_to("Hardware"),
                    "target":       lambda: self._nav_flyout._items.get("Hardware"),
                    "title":        "Step 9 of 9 — Hardware Hub",
                    "body":         "Connect your router, modem, or mesh system here for deep signal stats and diagnostics. Click 'Finish ✓' when you're ready.",
                },
            ],
            auto_dismiss_ms=0,
            on_done=_tour_done,
            on_skip=_tour_skipped,
        )
        self._post_scan_chain.start()

    def _on_welcome_scan(self) -> None:
        """Legacy slot — kept so any existing signal connections don't crash."""
        pass  # no-op; _maybe_start_onboarding drives the first-run flow

    def _set_scanning(self, scanning: bool):
        self._btn_scan.setEnabled(not scanning)
        if hasattr(self, "_header_scan_btn"):
            self._header_scan_btn.setEnabled(not scanning)
        if hasattr(self, "_home_page"):
            self._home_page.set_scanning(scanning)
        if hasattr(self, "_overview_page"):
            self._overview_page.set_scanning(scanning)
        self._progress.setVisible(scanning)
        # Sprint 7: show scan status in the persistent bottom status-bar label
        if hasattr(self, "_pulse_scan_lbl") and scanning:
            self._pulse_scan_lbl.setText("⏳  Scanning…")
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
        # Reset all onboarding keys so coach marks fire immediately in this session
        qs.setValue("ui/first_run_done", False)
        qs.setValue("ui/onboarding_v2_done", False)
        qs.setValue("tour/post_scan_done", False)
        self._welcome_shown = False   # allow _show_welcome_overlay to fire again
        self._nav_rail_go_to("Home")
        if hasattr(self, "_home_page"):
            self._home_page._recurring_mode = False
            self._home_page._set_first_run_mode(True)
            self._home_page.refresh_checklist()
        # Re-trigger the welcome overlay (key is now False)
        _t = QTimer(self)
        _t.setSingleShot(True)
        _t.timeout.connect(self._show_welcome_overlay)
        _t.start(400)

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
        self._dhcp_worker.result.connect(self._on_dhcp_scan_result, Qt.ConnectionType.QueuedConnection)
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
        lay.setSpacing(6)

        # ── Device poll section ───────────────────────────────────────────────
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
        self._snmp_table.itemSelectionChanged.connect(self._on_snmp_table_selection)
        lay.addWidget(self._snmp_status)
        lay.addLayout(ctrl_row)
        lay.addWidget(self._snmp_table, 1)

        # ── Interface error metrics card ──────────────────────────────────────
        if_card = QWidget()
        if_card.setStyleSheet(
            f"QWidget{{background:{BG_CARD};border:1px solid {BORDER};}}"
        )
        if_lay = QVBoxLayout(if_card)
        if_lay.setContentsMargins(8, 6, 8, 6)
        if_lay.setSpacing(4)

        title_row = QHBoxLayout()
        lbl_if = QLabel("◆ Interface Error & Discard Counters")
        lbl_if.setStyleSheet(
            f"font-weight:600;color:{TEXT_PRIMARY};font-size:12px;border:none;"
        )
        self._snmp_if_status = QLabel("Select a device above and click Poll.")
        self._snmp_if_status.setStyleSheet(
            f"color:{TEXT_SECONDARY};font-size:11px;border:none;"
        )
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
            self._snmp_if_fig = Figure(facecolor=CHART_BG, figsize=(4, 2.5))
            self._snmp_if_fig.subplots_adjust(left=0.12, right=0.98, top=0.88, bottom=0.22)
            self._snmp_if_ax  = self._snmp_if_fig.add_subplot(111)
            self._snmp_if_ax.set_facecolor(CHART_PLOT_BG)
            self._snmp_if_ax.tick_params(colors=TEXT_SECONDARY, labelsize=8)
            self._snmp_if_ax.grid(True, color=CHART_GRID, linewidth=0.8)
            for sp in ("top", "right"):
                self._snmp_if_ax.spines[sp].set_visible(False)
            for sp in ("bottom", "left"):
                self._snmp_if_ax.spines[sp].set_color(BORDER)
            self._snmp_if_ax.set_title(
                "Error distribution per interface", fontsize=9,
                color=TEXT_PRIMARY, pad=4,
            )
            self._snmp_if_canvas = FigureCanvasQTAgg(self._snmp_if_fig)
            content_split.addWidget(self._snmp_if_canvas)
        except Exception:
            pass  # matplotlib not available — chart omitted gracefully

        content_split.setStretchFactor(0, 3)
        content_split.setStretchFactor(1, 2)
        if_lay.addWidget(content_split, 1)
        lay.addWidget(if_card, 1)
        return w

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
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QLabel, QPushButton, QApplication, QFrame,
        )
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont
        dlg = QDialog(self)
        dlg.setWindowTitle("About NetSentinel")
        dlg.setMinimumWidth(460)
        dlg.setStyleSheet(self.styleSheet())
        lay = QVBoxLayout(dlg)
        lay.setSpacing(0)
        lay.setContentsMargins(32, 28, 32, 24)

        # Title + version + subtitle
        title = QLabel("NetSentinel")
        title.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{ACCENT};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ver_lbl = QLabel(f"v{QApplication.applicationVersion()}")
        ver_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        ver_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Network Security Scanner & Connectivity Monitor")
        subtitle.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:13px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)

        lay.addWidget(title)
        lay.addSpacing(2)
        lay.addWidget(ver_lbl)
        lay.addSpacing(6)
        lay.addWidget(subtitle)
        lay.addSpacing(18)

        # Divider
        _div = QFrame()
        _div.setFrameShape(QFrame.Shape.HLine)
        _div.setStyleSheet(f"color:{BORDER};")
        lay.addWidget(_div)
        lay.addSpacing(14)

        # Body — open source statement + supporter links
        body = QLabel(
            "NetSentinel will always remain free and open source.<br><br>"
            "If you find this tool valuable, please consider supporting:<br>"
            f'&nbsp;&nbsp;&#8226;&nbsp;<a href="https://donate.wikimedia.org/"'
            f' style="color:{ACCENT};">Wikipedia</a>'
            " — free knowledge for everyone<br>"
            f'&nbsp;&nbsp;&#8226;&nbsp;<a href="https://eff.org/donate"'
            f' style="color:{ACCENT};">Electronic Frontier Foundation</a>'
            " — protecting digital rights<br><br>"
            "Thank you for using NetSentinel."
        )
        body.setOpenExternalLinks(True)
        body.setWordWrap(True)
        body.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:12px;")
        lay.addWidget(body)
        lay.addSpacing(16)

        # Divider
        _div2 = QFrame()
        _div2.setFrameShape(QFrame.Shape.HLine)
        _div2.setStyleSheet(f"color:{BORDER};")
        lay.addWidget(_div2)
        lay.addSpacing(10)

        # Disclaimer
        disclaimer = QLabel(
            "For use on networks you own or have explicit authorization to test."
        )
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
        disclaimer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(disclaimer)
        lay.addSpacing(12)

        # Author + links
        author_lbl = QLabel(
            "Built by <b>Ossian Ericson</b>"
            f'&nbsp;&nbsp;&middot;&nbsp;&nbsp;<a href="https://github.com/ossianericson/netsentinel"'
            f' style="color:{ACCENT};">GitHub</a>'
            f'&nbsp;&nbsp;&middot;&nbsp;&nbsp;<a href="https://www.linkedin.com/in/ossian-ericson/"'
            f' style="color:{ACCENT};">LinkedIn</a>'
        )
        author_lbl.setOpenExternalLinks(True)
        author_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        author_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:12px;")
        lay.addWidget(author_lbl)
        lay.addSpacing(18)

        # Close button
        btn_close = QPushButton("Close")
        btn_close.setObjectName("btnNetRefresh")
        btn_close.setFixedWidth(100)
        btn_close.clicked.connect(dlg.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        dlg.exec()

    def _open_settings_dialog(self):
        """Open App Settings (theme, display preferences) as a persistent non-modal dialog."""
        if not hasattr(self, "_settings_dlg") or self._settings_dlg is None:
            from PyQt6.QtWidgets import QDialog, QVBoxLayout
            dlg = QDialog(self)
            dlg.setWindowTitle("App Settings")
            # 110 px anchor sidebar + cards with 190 px labels need at least ~780 px wide.
            # Default 880×680 gives comfortable room; minimum prevents sidebar overlap on resize.
            dlg.setMinimumSize(780, 540)
            dlg.resize(880, 680)
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
        """Launch a coordinated security audit: fire each tool silently, stay on Security Overview."""
        if not tool_labels:
            return
        if self._active_count > 0:
            self._set_status("Main scan in progress — please wait before running security tools.")
            return
        self._pending_security_tools = list(tool_labels)
        self._security_audit_total = len(tool_labels)
        self._advance_security_audit()

    def _advance_security_audit(self) -> None:
        """Fire the next pending security scan worker silently — never navigate away from Security Overview."""
        if not self._pending_security_tools:
            if hasattr(self, "_security_overview_page"):
                self._security_overview_page.clear_audit_progress()
            self._set_status("Security audit complete — see Security Overview for findings.")
            return
        label = self._pending_security_tools.pop(0)
        step_n = self._security_audit_total - len(self._pending_security_tools)
        if hasattr(self, "_security_overview_page"):
            self._security_overview_page.set_audit_progress(
                label, step_n, self._security_audit_total
            )
        if label == "Port Scan (TCP)":
            gw = self._net_info.get("gateway", "") if self._net_info else ""
            if not gw:
                # No gateway known yet — skip and advance to next tool
                self._advance_security_audit()
                return
            self._syn_host.setText(gw)
            self._start_syn_scan()
        elif label == "Exposed to Internet":
            self._start_exposure_check()
        else:
            # Unrecognised label — skip silently
            self._advance_security_audit()

    @pyqtSlot()
    def _start_full_scan(self):
        # Track whether this scan was triggered from the home page so we can
        # auto-navigate to Overview once device results arrive.
        # Do NOT overwrite if already True (pre-set by _on_welcome_scan to survive
        # the 160ms crossfade animation that delays the stack widget switch).
        if not getattr(self, "_scan_from_home", False):
            self._scan_from_home = (
                hasattr(self, "_home_page")
                and self._stack.currentWidget() is self._home_page
            )
        # Store grade before scan so toast can report improvement/drop
        self._pre_scan_grade = getattr(
            getattr(self, "_home_page", None), "_current_grade", ""
        ) or ""
        # Reset UI
        self._m1_result = self._m2_result = self._m3_result = None
        self._m4_result = self._m5_result = None
        self._m1_grouping_active = False
        self._m1_group_btn.setVisible(False)
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
                    self._wan_ip_ready.emit(ip)  # thread-safe signal → main thread set_home_ip
            except Exception:
                pass  # non-fatal

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
                            # thread-safe signal → main thread set_home_ip + navigate_to_ip
                            self._wan_ip_nav_req.emit(wan, f"Your Network  (local: {ip})")
                    except Exception:
                        pass  # geolocation update is best-effort; WAN IP probe may fail
                threading.Thread(target=_do_and_update, daemon=True).start()
        else:
            try:
                self._geo_map_page.navigate_to_ip(ip, label="Threat Intel")
            except Exception:
                pass  # geo_map_page may not be initialised at this call site

    @pyqtSlot(str, str)
    def _on_wan_ip_nav(self, wan: str, label: str) -> None:
        """Slot for _wan_ip_nav_req signal — called on main thread from background WAN IP fetch."""
        try:
            self._geo_map_page.set_home_ip(wan)
            self._geo_map_page.navigate_to_ip(wan, label=label)
        except Exception:
            pass  # geo_map_page may not be initialised at this call site


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
                pass  # non-fatal
        # Fire the scan (reuse the existing full-scan trigger)
        try:
            self._start_scan()
        except Exception:
            pass  # non-fatal

    def _check_lan_connectivity(self) -> None:
        """HEALTH-2: async socket probe; 3 failures → show amber offline banner."""
        from PyQt6.QtCore import QThread, pyqtSignal as _sig

        class _LanProbe(QThread):
            result = _sig(bool)

            def run(self) -> None:
                import socket
                # Try HTTPS (443) to two hosts — far less likely to be blocked
                # than port 53 TCP which routers and firewalls commonly filter.
                for host, port in (("1.1.1.1", 443), ("8.8.8.8", 443)):
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.settimeout(3)
                        s.connect((host, port))
                        s.close()
                        self.result.emit(True)
                        return
                    except OSError:
                        pass  # host unreachable — try next candidate
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
                pass  # non-fatal


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
        import time as _time
        dl = getattr(result, "download_mbps", 0.0) or 0.0
        ul = getattr(result, "upload_mbps",  0.0) or 0.0
        _speed_verdict = f"{dl:.1f} Mbps ↓ / {ul:.1f} Mbps ↑" if dl > 0 else "Speed test complete"
        self._nav_set_scan_state("Speed Test", "fresh", ts=_time.time(), verdict=_speed_verdict)

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
                and hasattr(self, "_network_map_page")):
            self._last_modem_topo_key = _topo_key
            try:
                gw_ip  = self._net_info.get("gateway")     if self._net_info else None
                gw_mac = self._net_info.get("gateway_mac") if self._net_info else None
                _mu, _me = self._effective_mesh_render_params()
                self._network_map_page.render(
                    self._m1_result.get("devices", []), gw_ip, gw_mac,
                    mesh_units=_mu, mesh_enrichment=_me, modem_data=data,
                )
            except Exception:
                pass  # non-fatal
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
            pass  # non-fatal
        try:
            self._ha_page.on_availability_update(states)
        except Exception:
            pass  # non-fatal
        try:
            for _ip, _state in states.items():
                self._mqtt_page.on_uptime_state(_ip, _state, rtts.get(_ip) or 0.0)
        except Exception:
            pass  # non-fatal

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
            self._show_scan_complete_toast()
            if self._auto_report_pending:
                self._auto_report_scan_done = True
                self._maybe_auto_report()
            if getattr(self, "_pending_benchmark", False):
                self._pending_benchmark = False
                self._run_benchmark()

    def _show_scan_complete_toast(self) -> None:
        """Show a toast summarising scan results; note grade change if applicable."""
        try:
            from ui.widgets.toast import ToastManager
            n_dev = len(getattr(self, "_last_scan_devices", []))
            dev_part = f"{n_dev} device{'s' if n_dev != 1 else ''}"
            grade_now = getattr(
                getattr(self, "_home_page", None), "_current_grade", ""
            ) or ""
            pre = getattr(self, "_pre_scan_grade", "")

            if grade_now and grade_now not in ("—", "?") and pre and pre not in ("—", "?") and grade_now != pre:
                _letters = ("A", "B", "C", "D", "F")
                improved = _letters.index(grade_now) < _letters.index(pre)
                if improved:
                    msg = f"Scan complete — {dev_part} · Grade improved from {pre} to {grade_now}"
                    ToastManager.show(msg, "success")
                else:
                    msg = f"Scan complete — {dev_part} · Grade dropped from {pre} to {grade_now}"
                    ToastManager.show(msg, "warning")
            else:
                grade_part = f" · Grade {grade_now}" if grade_now and grade_now not in ("—", "?") else ""
                ToastManager.show(f"Scan complete — {dev_part}{grade_part}", "success")
        except Exception:  # noqa: BLE001 — toast failure must not crash the UI
            import logging as _logging
            _logging.getLogger(__name__).debug("scan toast error", exc_info=True)


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
            options=QFileDialog.Option.DontUseNativeDialog,
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

    def _on_theme_changed(self, _name: str) -> None:
        from ui import styles as _s
        from PyQt6.QtWidgets import QApplication
        self.setStyleSheet(_s.MAIN_STYLE)
        _app = QApplication.instance()
        if _app:
            _app.setStyleSheet(_s.get_app_qss())
        for i in range(self._stack.count()):
            w = self._stack.widget(i)
            if w and hasattr(w, "refresh_theme"):
                w.refresh_theme()
        for btn in getattr(self, "_nav_rail_buttons", {}).values():
            if hasattr(btn, "refresh_theme"):
                btn.refresh_theme()
        flyout = getattr(self, "_nav_flyout", None)
        if flyout and hasattr(flyout, "refresh_theme"):
            flyout.refresh_theme()





