"""
Main Dashboard — NetSentinel network security scanner and monitor.
"""

import datetime
import html
from pathlib import Path

from PyQt6.QtCore import Qt, QPropertyAnimation, QSettings, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QMainWindow,
    QScrollArea,
    QStatusBar,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ui.perf_audit import profile_page_init
from ui import styles as _s
from ui.widgets.device_detail_pane import _wire_close_icon
from modules.utils import get_offenders_path, is_admin
from modules.scan_persistence import persist_alert, record_modem_signal


# ─── Module Tab Helpers (defined in ui/tabs.py, re-exported here) ────────────
from ui.tabs import _add_row
from ui.tabs_helpers import _page_header  # noqa: F401 — re-exported; used via lazy `from ui.dashboard import _page_header`

__all__ = ["Dashboard", "_page_header", "_color_for_level"]


# --- Activity-Rail Navigation widgets (extracted to ui/nav/rail.py) -----------
from ui.nav.labels import NavLabel as L
from ui.nav.rail import (
    _ClickLabel, _SmoothProgressBar,
)
from ui.dialog_utils import run_dialog


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
from ui.nav.lazy_page import _LazyPageMixin
from ui.monitor_state import (
    _color_for_level,  # re-exported via __all__; used by ui.scan_enrichment lazy import
    _MonitorStateMixin,
)
from ui.plugin_page_mixin import _PluginPageMixin
from ui.export_mixin import _ExportMixin



def _register_external_worker(workers: list, worker) -> None:
    """Append *worker* to *workers* if it is real and not already present.

    Free function (not a Dashboard method) so it is unit-testable without
    constructing a Dashboard (RULE-TP4-DASH). ``worker`` may be None —
    rest_api_worker is None unless the REST API is enabled.
    """
    if worker is not None and worker not in workers:
        workers.append(worker)


class Dashboard(ScanResultMixin, AppHeaderMixin, TabBuilderMixin,
               _NavBuilderMixin, _LazyPageMixin, _MonitorStateMixin, _PluginPageMixin,
               _ExportMixin, QMainWindow):
    _update_available         = pyqtSignal(str)
    global_time_range_changed = pyqtSignal(float)  # hours: float
    _wan_ip_ready             = pyqtSignal(str)        # WAN IP fetched → geo map set_home_ip (thread-safe)
    _wan_ip_nav_req           = pyqtSignal(str, str)   # WAN IP + label → set_home_ip + navigate_to_ip

    def __init__(self, store=None, alert_engine=None, notif_router=None, maint_manager=None,
                 start_minimised: bool = False):
        super().__init__()
        self._store        = store          # MetricStore | None
        self._alert_engine = alert_engine   # AlertEngine | None
        self._notif_router = notif_router   # NotificationRouter | None
        self._maint_manager = maint_manager # MaintenanceWindowManager | None
        self._global_hours = 24.0
        # Tray-only startup (Phase 5.5). Set before _restore_settings() runs
        # (below) so app_settings.restore_settings() can see it. _pending_*
        # record intent recorded during construction for AppHeaderMixin.
        # show_main_window() to honour on first real reveal — see RULE-WIN12
        # for why the SetWindowPlacement-family fixup must be replayed there
        # in the same order restore_settings() would have applied it.
        self._start_minimised = start_minimised
        self._pending_show_maximized = False
        self._pending_maximize_restore_rect = None
        self.setWindowTitle("NetSentinel  —  Network Security Scanner & Monitor")
        self.setMinimumSize(900, 600)
        # ── Window chrome (RULE-WIN9) ─────────────────────────────────────────
        # On Windows the window keeps its REAL Win32 style (caption, sysmenu, thick
        # frame, min/max box) and ui/native_chrome.py merely stops Windows painting
        # the frame via WM_NCCALCSIZE — which is what makes Aero Snap, Snap Layouts,
        # shake and native resize work at all. FramelessWindowHint produces a bare
        # WS_POPUP that Windows does not consider maximizable or snappable
        # (docs/spikes/window-snap-subclass.md).
        #
        # This shipped behind experimental/native_chrome (RULE-EXP1) and was promoted
        # to the default in v2.1.30 after a clean chaos soak with the flag on. The
        # flag is GONE rather than merely defaulted True: it was never written by the
        # app, but dev machines and the Phase-3 probe scripts did write an explicit
        # `false`, and a stale stored value would have silently kept those users on
        # the old window forever.
        #
        # Non-Windows keeps the frameless path — it is the only implementation there
        # (WM_NCCALCSIZE is a Win32 message), and it still owns the _Grip resize
        # widgets and _DragHeader's manual drag in ui/header.py.
        import sys as _sys_plat
        self._native_chrome = _sys_plat.platform == "win32"
        if self._native_chrome:
            self.setWindowFlags(Qt.WindowType.Window)
        else:
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        # Page styling goes on the APPLICATION, never on the Dashboard widget.
        # Qt resolves a widget's own stylesheet ahead of the application one for
        # that widget and all its descendants, so a widget-level MAIN_STYLE here
        # would outrank — and permanently strand — the app-level sheet that
        # _on_theme_changed() writes on every theme switch: the app would come up
        # half-switched, with only the themed_ss widgets repainted.
        from PyQt6.QtWidgets import QApplication as _QApp_init
        _app_init = _QApp_init.instance()
        if _app_init is not None:
            # RULE-STARTUP2: an app-level setStyleSheet() re-polishes every
            # top-level widget, including the QSplashScreen that may still be
            # showing at this point in construction — _suspend_repaints()
            # prevents the queued repaint from flushing as a startup flash.
            with _s._suspend_repaints():
                _app_init.setStyleSheet(_s.MAIN_STYLE + _s.get_app_qss())
        else:
            self.setStyleSheet(_s.MAIN_STYLE)  # no QApplication — headless test path
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

        # ── Deferred page construction (RULE-EXP1 — graduated to permanent) ───
        # A conservative set of self-contained "leaf" pages are registered as
        # _LazyPageHost placeholders and built on first navigation (or by a
        # background chunk-builder), instead of eagerly in _build_tabs(). See
        # project_com_reentrancy_startup_crash memory / docs/spikes/startup-com-reentrancy.md.
        self._lazy_hosts: list = []          # _LazyPageHost objects awaiting materialization
        self._lazy_build_timer = None        # background chunk-builder QTimer(self)
        # Buffered kwargs for ProtocolVizPage.set_context() while that page is
        # still a _LazyPageHost — scan handlers feed it on every scan regardless
        # of nav state, unlike every other lazy page (see _feed_protocol_viz_context).
        self._protocol_viz_pending_context: "dict | None" = None
        # Same pattern for AppTrafficPage.set_label_map() — see
        # _feed_app_traffic_label_map.
        self._app_traffic_pending_label_map: "dict | None" = None

        # ── Deferred theme refresh (RULE-EXP1) ────────────────────────────────
        # experimental/theme_switch_deferred: when True, _on_theme_changed()
        # calls refresh_theme() immediately only for the currently-visible stack
        # page; every other page (incl. matplotlib re-renders — topology, both
        # history charts, geo map, network map, wifi heatmap, timeline, live
        # bandwidth, app traffic, speed test) is queued in _theme_dirty_widgets
        # and flushed lazily the next time the user navigates to it
        # (_nav_rail_go_to in ui/nav/builder.py). Default False ⇒ the
        # previously-verified eager fan-out stays byte-for-byte intact.
        self._theme_switch_deferred = QSettings("NetSentinel", "NetSentinel").value(
            "experimental/theme_switch_deferred", False, type=bool
        )
        self._theme_dirty_widgets: set = set()

        # Scan results cache
        self._m1_result   = None
        self._m2_result   = None
        self._m3_result   = None
        self._m4_result   = None
        self._m5_result   = None
        self._lldp_result = None  # list[LldpNeighbor] from Sprint 5 LLDP worker

        # Device Identity Program Phase 3: per-MAC classification-claim
        # accumulator shared by scan_wiring.py (seeds the scan-time claim) and
        # scan_enrichment.py (adds passive/DHCP/mesh-hostname claims as they
        # arrive) — both are mixed into this same Dashboard instance. Reset in
        # _m1_update_scan_registries() whenever a new scan result replaces the
        # device list.
        from modules.device_classification import ClaimTracker
        from ui.scan_settings import identity_stable_arbitration_enabled
        self._classification_claims = ClaimTracker(
            stable=identity_stable_arbitration_enabled()
        )

        # Security audit coordinator state
        self._pending_security_tools: list = []

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
        self._is_scanning = False
        self._prescan_worker = None
        self._diag_worker = None
        self._logger_worker = None
        # Always-on background workers created in app.py (availability, cert,
        # syslog/SNMP-trap receivers, passive observer, posture probes, …).
        # Registered here so closeEvent() drains them before os._exit(0); see
        # register_external_worker() / _drain_external_workers().
        self._external_workers: list = []

        # Scan watchdog (G5): guards against a hung pre-scan/module worker
        # leaving the UI stuck on "Scanning…" forever. Parented QTimer per
        # RULE-WIN5 — never QTimer.singleShot bound to self.
        self._scan_watchdog = QTimer(self)
        self._scan_watchdog.setSingleShot(True)
        self._scan_watchdog.timeout.connect(self._on_scan_watchdog_timeout)
        self._scan_started_at: float = 0.0

        # Cached results
        self._net_info: dict = {}
        self._wan_ip:   str  = ""   # public WAN IP, fetched once per session after scan
        self._diag_result = None
        self._last_scan_devices: list = []    # for NetworkDocPage port_data accumulation
        self._port_data_cache:   dict = {}    # {ip: [port_dict, ...]} across scan types
        self._cred_access_hosts: set  = set()  # hosts where Login Test confirmed working creds (F-46)
        self._port_scan_not_testable_hosts: set = set()  # hosts a blocked SYN scan could not reach (L3)
        self._os_detect_not_testable_hosts: set = set()  # hosts OS fingerprinting got no signal from (L3)
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
        _loghub_sc.activated.connect(lambda: self._nav_rail_go_to(L.NETWORK_LOGGER))

        # Ctrl+Shift+H — Quick Check floating window (S8-2)
        self._quick_check_window = None
        _quickcheck_sc = QShortcut(QKeySequence("Ctrl+Shift+H"), self)
        _quickcheck_sc.activated.connect(self._show_quick_check_window)

        # Alt+1–5 — quick jump to five most-used pages
        for _i, _lbl in enumerate(["Overview", "Devices", "Speed Test", "What's Wrong?", "Network Logger"], 1):
            _sc = QShortcut(QKeySequence(f"Alt+{_i}"), self)
            _sc.activated.connect(lambda _l=_lbl: self._nav_rail_go_to(_l))

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

        # Monitor resume bar — hidden; shown when monitors are auto-resumed at startup
        self._monitor_resume_bar = self._build_monitor_resume_bar()
        self._monitor_resume_bar.setVisible(False)

        # Main area: sidebar+content fills window
        _main = profile_page_init(self._build_tabs)
        # Insert notification bars inside content_wrapper so they never bleed over the rail
        self._content_area_layout.insertWidget(0, self._update_bar)
        self._content_area_layout.insertWidget(1, self._monitor_resume_bar)
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
            "QLabel {{ padding: 0 8px; font-size: 11px; background: transparent;"
            " border: none; color: {TEXT_MUTED}; }}"
            "QLabel:hover {{ color: {WHITE}; }}"
        )
        _pulse_sep = QFrame()
        _pulse_sep.setFrameShape(QFrame.Shape.VLine)
        _pulse_sep.setFixedWidth(1)
        _s.themed_ss(_pulse_sep, "background: {NAV_DIVIDER}; border: none;")

        self._pulse_online_lbl  = _ClickLabel("○  —")
        self._pulse_devices_lbl = _ClickLabel("■  —")
        self._pulse_scan_lbl    = _ClickLabel("Last scan: —")
        self._pulse_logger_lbl  = _ClickLabel("○  Logger off")
        self._pulse_alerts_lbl  = _ClickLabel("⚠ 0")
        for _l in (self._pulse_online_lbl, self._pulse_devices_lbl,
                   self._pulse_scan_lbl, self._pulse_logger_lbl, self._pulse_alerts_lbl):
            _s.themed_ss(_l, _pulse_base)
            _l.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pulse_alerts_lbl.setHidden(True)
        self._pulse_online_lbl.setToolTip(_s.safe_tooltip(
            "Connection status (last logger result)\nClick to open Connectivity Tests"
        ))
        self._pulse_devices_lbl.setToolTip(_s.safe_tooltip(
            "Number of devices seen in the last scan\nClick to open Overview"
        ))
        self._pulse_scan_lbl.setToolTip(_s.safe_tooltip(
            "Time since the last network scan completed\nClick to open Overview"
        ))
        self._pulse_logger_lbl.setToolTip(_s.safe_tooltip(
            "Network logger state — starts automatically on first launch\nClick to open Logs"
        ))
        self._pulse_alerts_lbl.setToolTip(_s.safe_tooltip(
            "Unacknowledged alerts\nClick to open Alert History"
        ))

        self._pulse_online_lbl.clicked.connect(
            lambda: self._nav_rail_go_to(L.WHATS_WRONG))
        self._pulse_devices_lbl.clicked.connect(
            lambda: self._nav_rail_go_to(L.DASHBOARD))
        self._pulse_scan_lbl.clicked.connect(
            lambda: self._nav_rail_go_to(L.DASHBOARD))
        self._pulse_logger_lbl.clicked.connect(
            lambda: self._nav_rail_go_to(L.NETWORK_LOGGER))
        self._pulse_alerts_lbl.clicked.connect(self._on_pulse_alerts_clicked)

        self._status_bar.addPermanentWidget(_pulse_sep)
        self._status_bar.addPermanentWidget(self._pulse_online_lbl)
        self._status_bar.addPermanentWidget(self._pulse_devices_lbl)
        self._status_bar.addPermanentWidget(self._pulse_scan_lbl)
        self._status_bar.addPermanentWidget(self._pulse_logger_lbl)
        self._status_bar.addPermanentWidget(self._pulse_alerts_lbl)

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
        # Restore full settings (mode, scan hosts, etc.) after UI is built.
        # NOTE: do NOT install the window chrome before this. Doing so forces the
        # HWND to exist early (winId()), and Qt then re-pushes its stale
        # creation-time geometry over the restored one — the window snaps back to
        # its minimum size. The chrome installs in showEvent instead, and re-applies
        # the saved rect itself once the frame is real (see _install_window_chrome).
        self._restore_settings()
        # Install resize grips for all 8 edges/corners (frameless window only —
        # native chrome keeps the real WS_THICKFRAME, so Windows resizes for us).
        if not self._native_chrome:
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

        def __init__(self, admin_rows: set, parent=None):
            super().__init__(parent)
            self._admin_rows    = admin_rows
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
            painter.setPen(QColor(_s.WHITE))
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
                right_offset += self._paint_pill(painter, option, self._BADGE, _s.RED, right_offset)
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
        dlg.setStyleSheet(f"background:{_s.BG_DARK}; color:{_s.TEXT_PRIMARY};")
        lay = QVBoxLayout(dlg)

        heading = QLabel(f"<b>Remediation steps for: {title}</b>")
        heading.setStyleSheet(f"color:{_s.ACCENT_LITE}; font-size:13px; padding-bottom:4px;")
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
        txt.setStyleSheet(f"color:{_s.TEXT_PRIMARY}; font-size:12px; padding:4px;")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.addWidget(txt)
        inner_lay.addStretch()
        scroll.setWidget(inner)
        scroll.setStyleSheet(f"background:{_s.BG_CARD}; border:1px solid {_s.BORDER}; border-radius:0px;")
        scroll.setMinimumHeight(160)

        lay.addWidget(scroll, 1)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(dlg.accept)
        lay.addWidget(btns)
        run_dialog(dlg)

    # ── Window lifecycle ──────────────────────────────────────────────────────

    def register_external_worker(self, worker) -> None:
        """Register an always-on background worker (created in app.py) so that
        closeEvent() stops it before os._exit(0). Tolerates None and duplicates.
        """
        _register_external_worker(self._external_workers, worker)

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
        # Instrumented and bounded — see ui/shutdown.py for the full mechanism.
        # Previously this loop was serial and per-worker (23 dashboard workers x
        # (800 + 2000) ms, then 17 external x 1500 ms, no global deadline ⇒ ~90 s
        # worst case), it terminate()d raw-socket/Npcap workers, and seven live
        # workers plus the Overview-tile pollers were in no stop list at all.
        import time as _time
        from ui.shutdown import (
            collect_dashboard_workers, collect_hardware_pollers, collect_page_pollers,
            drain_workers, hard_exit, shutdown_log,
        )
        _t_start = _time.monotonic()
        shutdown_log("=== closeEvent: real shutdown path ===")

        self._save_window_state()

        # One list, one deadline. Draining the dashboard workers, the always-on
        # app.py workers and the Overview-tile pollers together is what makes the
        # deadline global: split into separate calls, each would get its own
        # budget and the waits would add up again.
        _workers = (collect_dashboard_workers(self)
                    + list(self._external_workers)
                    + collect_page_pollers(self)
                    + collect_hardware_pollers(self))
        _still = drain_workers(_workers, deadline_s=3.0, label="shutdown")
        if _still:
            # These are the threads the exit below is about to kill mid-syscall —
            # the single most useful line in the log when diagnosing a WER report.
            shutdown_log(
                "  STILL RUNNING at exit: %s",
                ", ".join(sorted(type(w).__name__ for w in _still)),
            )

        # The hardware poll workers were drained above; just drop the references.
        # Calling HardwareIntegrationPage.closedown() here instead would re-run its
        # own serial stop()/wait(2000)-per-worker loop OUTSIDE the deadline — a
        # measured flat 2.0 s of the close before this was folded into the drain.
        _hw = getattr(self, "_hardware_integration_page", None)
        if _hw is not None:
            try:
                _hw._poll_workers.clear()
            except Exception as _exc:
                shutdown_log("  hardware poll-worker clear raised: %s", _exc)

        super().closeEvent(event)

        # WAL flush. The hard exit below bypasses Python's connection-close and
        # atexit path entirely, so nothing else would checkpoint the WAL.
        #
        # PASSIVE, not the default TRUNCATE: TRUNCATE must wait for every reader
        # and writer to clear and honours busy_timeout=5000, so it could block the
        # UI thread up to 5 s at the very end of shutdown — with prune_worker
        # potentially inside an uninterruptible VACUUM. PASSIVE flushes whatever
        # it can without ever blocking. Skipping TRUNCATE costs nothing but WAL
        # file size: the data is already durable in the WAL and SQLite replays it
        # on the next open.
        if self._store is not None:
            _t_ckpt = _time.monotonic()
            try:
                self._store.checkpoint(passive=True)
            except Exception as _exc:
                shutdown_log("  checkpoint raised: %s", _exc)
            shutdown_log("  checkpoint(passive): %.0fms", (_time.monotonic() - _t_ckpt) * 1000)

        import sys as _sys
        # PyInstaller onefile extracts to a _MEI* temp dir and registers an atexit
        # handler to clean it up. The hard exit bypasses atexit, leaving the dir
        # behind and causing a "Failed to remove temporary directory" warning on
        # the next launch. Delete it explicitly — nothing uses it after this point.
        if getattr(_sys, "frozen", False) and hasattr(_sys, "_MEIPASS"):
            try:
                import shutil as _shutil
                _shutil.rmtree(_sys._MEIPASS, ignore_errors=True)
            except Exception:
                pass  # non-fatal
        shutdown_log("=== closeEvent complete: %.0fms total ===",
                     (_time.monotonic() - _t_start) * 1000)
        # TerminateProcess, not os._exit/ExitProcess: it skips DLL_PROCESS_DETACH,
        # so a thread still inside Npcap/WinSock cannot fault the teardown. See
        # ui/shutdown.hard_exit().
        hard_exit(0)


    def _surface_alert_in_app(self, alert) -> None:
        """In-app surfaces for a fired alert -- always on, never gated.

        Status bar + tray badge only. It deliberately shows NO desktop
        notification balloon: that is NotificationRouter's ToastChannel job and
        is strictly opt-in (notif/toast_enabled, default False). Every
        evaluate_*() consumer calls this directly, so these surfaces work
        regardless of notification settings.
        """
        severity = getattr(alert, "severity", "INFO")
        message  = getattr(alert, "message",  str(alert))
        if severity == "CRITICAL":
            prefix = "🔴"
        elif severity == "HEALTHY":
            prefix = "🟢"
        else:
            prefix = "🟡"
        self._set_status(f"{prefix} {message}")
        # A resolution closes an alert; it must not add to the unacked badge.
        if self._tray_manager.is_available() and not getattr(alert, "is_resolution", False):
            self._tray_manager.increment_badge()
        self._maybe_prompt_toast_optin()

    def _maybe_prompt_toast_optin(self) -> None:
        """One-time in-app nudge after an alert fires while desktop balloons are
        off. In-app toast only -- it does not itself show an OS balloon, so strict
        opt-in is preserved."""
        from PyQt6.QtCore import QSettings as _QS
        qs = _QS("NetSentinel", "NetSentinel")
        if qs.value("notif/toast_enabled", False, type=bool):
            return
        if qs.value("notif/toast_optin_prompted", False, type=bool):
            return
        qs.setValue("notif/toast_optin_prompted", True)
        try:
            from ui.widgets.toast import ToastManager
            ToastManager.show(
                "Desktop notifications are off — alerts appear here and in Alert History.",
                "action", action_label="Turn on",
                action_callback=lambda: self._nav_rail_go_to(L.NOTIFICATIONS),
            )
        except Exception:
            pass  # non-fatal — the nudge is cosmetic, must never break alert delivery

    def _show_alert_toast(self, alert) -> None:
        """Desktop notification balloon -- ROUTER-ONLY entry point.

        Wired once, as NotificationRouter.set_toast_callback() in app.py. The
        router has already applied snooze + ToastChannel.enabled + min_severity
        + rule_types before calling this, so there is deliberately NO settings
        read here and no other call site may exist (enforced by
        tests/test_toast_gate.py::test_show_alert_toast_has_exactly_one_call_site).
        In-app surfaces live in _surface_alert_in_app().
        """
        severity = getattr(alert, "severity", "INFO")
        message  = getattr(alert, "message",  str(alert))
        if self._tray_manager.is_available():
            self._tray_manager.show_notification("NetSentinel Alert", message, severity)
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
        self._nav_rail_go_to(L.INVENTORY_CHANGES)
        if hasattr(self, "_inventory_page"):
            self._inventory_page.select_device(ip_or_mac)

    def _on_popover_open_threat_intel(self, ip: str) -> None:
        self._nav_rail_go_to(L.THREAT_INTEL)
        if hasattr(self, "_threat_intel_page") and ip:
            self._threat_intel_page.check_ip(ip)

    # ── TIME-2: View in Network Logger from alert drawer ──────────────────────

    def _on_view_alert_in_log_hub(self, alert_ts: float, source_key: str) -> None:
        self._nav_rail_go_to(L.NETWORK_LOGGER)
        if hasattr(self, "_log_hub_page"):
            self._log_hub_page.jump_to_alert_time(alert_ts, source_key)

    @pyqtSlot(str, str)
    def _on_automation_rule_requested(self, rule_name: str, match_value: str) -> None:
        self._nav_rail_go_to(L.AUTOMATION_HOOKS)
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
        container = _W()
        container.setObjectName("monitorResumeBar")
        container.setFixedHeight(28)
        # Neutral surface + crisp green left accent + green text (no saturated fill)
        _s.themed_ss(
            container,
            "QWidget#monitorResumeBar {{ background:{BANNER_BG};"
            " border-left: 3px solid {GREEN};"
            " border-bottom: 1px solid {BORDER}; }}",
        )
        row = _HL(container)
        row.setContentsMargins(12, 0, 8, 0)
        row.setSpacing(6)
        icon = _L("●")
        _s.themed_ss(icon, "color:{GREEN}; font-size:8px; background:transparent; border:none;")
        row.addWidget(icon)
        self._monitor_resume_lbl = _L("")
        _s.themed_ss(
            self._monitor_resume_lbl,
            "color:{GREEN}; font-size:11px; font-weight:bold; background:transparent; border:none;",
        )
        row.addWidget(self._monitor_resume_lbl, 1)
        btn_stop = _B("Stop all")
        btn_stop.setFixedHeight(20)
        _s.themed_ss(
            btn_stop,
            "QPushButton {{ background:transparent; color:{TEXT_SECONDARY};"
            " border:1px solid {BORDER}; border-radius:3px; font-size:10px; padding:0 8px; }}"
            "QPushButton:hover {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}",
        )
        btn_stop.clicked.connect(self._stop_all_resumed_monitors)
        row.addWidget(btn_stop)
        btn_dismiss = _B("")
        btn_dismiss.setFixedSize(24, 24)
        btn_dismiss.setCursor(_Qt.CursorShape.PointingHandCursor)
        _wire_close_icon(btn_dismiss, "TEXT_SECONDARY")
        _s.themed_ss(
            btn_dismiss,
            "QPushButton {{ background:transparent; border:none; }}"
            "QPushButton:hover {{ background:transparent; }}"
            "QPushButton:pressed {{ background:transparent; }}",
        )
        btn_dismiss.clicked.connect(lambda: container.hide())
        row.addWidget(btn_dismiss)
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
        # Mark done as soon as we decide to show it — not on interaction. The
        # Step-1 card's position can lose its anchor if Home-page mode state
        # (recurring vs first-run) flips right after creation, which used to
        # leave the card stranded and unclicked forever, so the interaction-only
        # flag never got set and the tour kept reappearing on every launch.
        mark_onboarding_done()
        self._nav_rail_go_to(L.HOME)
        from ui.widgets.coach_mark import CoachMarkChain

        def _step1_done() -> None:
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
            pass  # nothing further to do; onboarding already marked done above

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
                # Card anchors to the header button specifically (not the Home-page
                # button _pick_home_scan_btn resolves) — the header button is a
                # permanent top-bar element, never hidden by recurring/first-run
                # mode toggles, so the card can never lose its anchor and fall
                # back to the disconnected bottom-right corner of the window.
                "card_target":   lambda: getattr(self, "_header_scan_btn", None),
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
            self._nav_rail_go_to(L.DASHBOARD)

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
                        self._nav_rail_go_to(L.NETWORK_LOGGER),
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
                        self._nav_rail_go_to(L.NETWORK_LOGGER),
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
                    "on_show":      lambda: self._nav_rail_go_to(L.DEVICES),
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
                    "on_show":      lambda: self._nav_rail_go_to(L.HARDWARE),
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
        self._is_scanning = scanning
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
                f"color:{_s.ACCENT}; font-size:9px; background:transparent; border:none;"
            )
            self._kpi_scan_val.setStyleSheet(
                f"color:{_s.ACCENT}; font-size:18px; font-weight:bold;"
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
        self._nav_rail_go_to(L.HOME)
        if hasattr(self, "_home_page"):
            self._home_page._recurring_mode = False
            self._home_page._set_first_run_mode(True)
            self._home_page.refresh_checklist()
        # Re-trigger the welcome overlay (key is now False)
        _t = QTimer(self)
        _t.setSingleShot(True)
        _t.timeout.connect(self._show_welcome_overlay)
        _t.start(400)

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
            _s.themed_ss(dlg, "QDialog{{background:{BG_DARK};}}")
            lay = QVBoxLayout(dlg)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(self._settings_page)
            self._settings_dlg = dlg
        self._settings_dlg.show()
        self._settings_dlg.raise_()
        self._settings_dlg.activateWindow()

    def _open_help_dialog(self):
        """Navigate to Help & Reference in the Education sidebar section."""
        self._nav_rail_go_to(L.HELP_REFERENCE)

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
        self._advance_security_audit()

    def _advance_security_audit(self) -> None:
        """Fire the next pending security scan worker silently — never navigate away from Security Overview."""
        if not self._pending_security_tools:
            self._set_status("Security audit complete — see Security Overview for findings.")
            return
        label = self._pending_security_tools.pop(0)
        if label == L.PORT_SCAN_TCP:
            gw = self._net_info.get("gateway", "") if self._net_info else ""
            if not gw:
                # No gateway known yet — skip and advance to next tool
                self._advance_security_audit()
                return
            self._syn_host.setText(gw)
            self._start_syn_scan()
        elif label == L.EXPOSED_TO_INTERNET:
            self._start_exposure_check()
        elif label == L.THREAT_INTEL:
            self._nav_set_scan_state(L.THREAT_INTEL, "running")
            self._awaiting_threat_intel = True
            self._threat_intel_page._run_refresh()
        elif label == L.DEVICE_RISK_SCORE:
            # Synchronous — scores off the already-populated device scan result,
            # no async worker to wait on, so advance the queue immediately.
            self._run_risk_scorer()
            self._advance_security_audit()
        elif label == L.CVE_LOOKUP:
            # _start_cve_lookup() advances the queue itself, on both the
            # no-versions-found path and via _on_cve_finished() (F-02).
            self._start_cve_lookup()
        elif label == L.TLS_EXPOSURE:
            if not getattr(self, "_cert_worker", None):
                self._advance_security_audit()
                return
            self._nav_set_scan_state(L.TLS_EXPOSURE, "running")
            self._awaiting_tls_check = True
            self._cert_worker.run_now()
        else:
            # Unrecognised label — skip silently
            self._advance_security_audit()

    def _on_tls_check_done(self, results: list) -> None:
        """Update the TLS & Exposure scan-registry row (F-02: this label previously
        had zero producers anywhere, so the Scan Status card always showed
        "Never run" regardless of the hourly background CertWorker checks).
        Also advances the security-audit queue if a dispatch is pending."""
        import time as _time
        expired  = sum(1 for r in results if r.get("is_expired"))
        expiring = sum(
            1 for r in results
            if not r.get("is_expired") and (r.get("days_remaining") if r.get("days_remaining") is not None else 999) < 30
        )
        # Sprint 5b (C): every monitored host being unreachable must not read
        # as "no hosts monitored" (idle) or a clean cert-OK verdict -- both
        # currently look identical to a genuinely empty/healthy config.
        if results and all(r.get("not_testable") for r in results):
            _reason = next((r.get("not_testable_reason") for r in results if r.get("not_testable_reason")), "")
            self._nav_set_scan_state(L.TLS_EXPOSURE, "not_testable", ts=_time.time(), error=_reason)
        else:
            if not results:
                verdict = "no hosts monitored"
            elif expired or expiring:
                verdict = f"{expired} expired, {expiring} expiring soon"
            else:
                verdict = f"{len(results)} cert(s) OK"
            self._nav_set_scan_state(L.TLS_EXPOSURE, "fresh", ts=_time.time(), verdict=verdict)
        if getattr(self, "_awaiting_tls_check", False):
            self._awaiting_tls_check = False
            self._advance_security_audit()

    def _on_threat_intel_scan_complete(self) -> None:
        """Update the Threat Intel scan-registry row (S1: this label previously
        had zero producers anywhere, so the Scan Status card always showed
        "Never run" regardless of how many feed refreshes ran). Also advances
        the security-audit queue if a dispatch is pending -- mirrors
        _on_tls_check_done()'s _awaiting_* pattern above."""
        import time as _time
        n = len(getattr(self._threat_intel_page, "_threat_entries", []) or [])
        self._nav_set_scan_state(L.THREAT_INTEL, "fresh", ts=_time.time(), verdict=f"{n} indicator(s)")
        if getattr(self, "_awaiting_threat_intel", False):
            self._awaiting_threat_intel = False
            self._advance_security_audit()

    def _on_threat_intel_scan_error(self, msg: str) -> None:
        self._nav_set_scan_state(L.THREAT_INTEL, "error", error=msg)
        if getattr(self, "_awaiting_threat_intel", False):
            self._awaiting_threat_intel = False
            self._advance_security_audit()

    def _on_threat_intel_scan_not_testable(self, reason: str) -> None:
        import time as _time
        self._nav_set_scan_state(L.THREAT_INTEL, "not_testable", ts=_time.time(), error=reason)
        if getattr(self, "_awaiting_threat_intel", False):
            self._awaiting_threat_intel = False
            self._advance_security_audit()

    def _maybe_confirm_scan_environment(self) -> bool:
        """
        One-time pre-scan notice on a non-home network (VPN/corporate/large subnet).
        Returns False if the user cancels — the caller must not start the scan.
        """
        from modules.network_environment import NetworkEnvironment
        env = getattr(self, "_net_env", None)
        if not isinstance(env, NetworkEnvironment) or env.kind == "home":
            return True
        qs = QSettings("NetSentinel", "NetSentinel")
        ack_key = f"scan/env_ack/{env.fingerprint()}"
        if qs.value(ack_key, False, type=bool):
            return True
        from PyQt6.QtWidgets import QMessageBox
        lines = [env.title, ""] + [f"• {r}" for r in env.reasons] + [""] + \
            [f"• {e}" for e in env.effects]
        box = QMessageBox(self)
        box.setWindowTitle("Different network detected")
        box.setText("\n".join(lines))
        box.setIcon(QMessageBox.Icon.Warning)
        box.addButton("Scan Anyway", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        run_dialog(box)
        clicked = box.clickedButton()
        proceed = clicked is not None and clicked.text() == "Scan Anyway"
        if proceed:
            qs.setValue(ack_key, True)
        return proceed

    @pyqtSlot()
    def _start_full_scan(self):
        if self._is_scanning:
            return
        if not self._maybe_confirm_scan_environment():
            return
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
        from ui.scan_settings import effective_flush_caches
        _will_flush = effective_flush_caches()
        _prescan_msg = (
            "Pre-scan in progress (flushing caches & sweeping subnet)…" if _will_flush
            else "Pre-scan in progress (sweeping subnet)…"
        )
        self._verdict.update(_prescan_msg, "UNKNOWN")
        self._set_scanning(True)
        self._active_count = 0

        # Run pre-scan first (flush + ping sweep), then kick off modules
        from workers.scan_worker import PreScanWorker
        self._prescan_worker = PreScanWorker(flush_caches=_will_flush)
        self._prescan_worker.status.connect(self._on_prescan_status)
        self._prescan_worker.done.connect(self._launch_modules)
        self._prescan_worker.error.connect(self._on_prescan_error)
        self._prescan_worker.start()

        # (Re)start the watchdog for this scan attempt — base 120s + a per-device
        # allowance (scaled to the last known device count), covers pre-scan +
        # module launch; _on_worker_done cancels it once modules complete.
        # _on_scan_watchdog_timeout() extends it further, honestly, while
        # workers are still actually running (Part 1/C3).
        import time as _time
        self._scan_started_at = _time.time()
        self._scan_watchdog.start(self._scan_watchdog_budget_ms())

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

        self._nav_rail_go_to(L.GEOLOCATION_MAP)

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
        import time as _t
        qs = QSettings("NetSentinel", "NetSentinel")
        if not qs.value("sched_scan/enabled", False, bool):
            return
        try:
            next_ts = float(qs.value("sched_scan/next_ts", 0))
        except (TypeError, ValueError):
            next_ts = 0.0  # unparseable INI value — treat as "not scheduled"
        if next_ts <= 0 or _t.time() < next_ts:
            return
        # Compute next run. Shared with settings_cards._save_sched_scan() so the
        # writer and this consumer can never disagree, and so a zero/negative
        # interval cannot spin forever on the GUI thread.
        from modules.scheduler import next_scheduled_run
        qs.setValue("sched_scan/next_ts", next_scheduled_run(
            now=_t.time(),
            hour=qs.value("sched_scan/hour", 2),
            minute=qs.value("sched_scan/minute", 0),
            interval_hours=qs.value("sched_scan/interval_hours", 24),
        ))
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
        # The digest has its own explicit opt-in key (notif/weekly_digest_enabled)
        # and is not a rule alert, so it is delivered directly -- same pattern as
        # the morning briefing -- rather than through NotificationRouter.dispatch().
        if hasattr(self, "_notifications_page"):
            summary_text = self._notifications_page._generate_weekly_summary()
        else:
            summary_text = "NetSentinel weekly digest"
        if self._tray_manager.is_available():
            try:
                self._tray_manager.show_notification(
                    "NetSentinel Weekly Digest", summary_text, "INFO",
                    on_click=lambda: self._nav_rail_go_to(L.NOTIFICATIONS),
                )
                # Only advance last_ts on a successful send -- writing this
                # before dispatch made a failed digest self-suppressing for
                # 6 days (the previous bug).
                qs.setValue("notif/weekly_digest_last_ts", now.timestamp())
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
        self._nav_set_scan_state(L.SPEED_TEST, "fresh", ts=_time.time(), verdict=_speed_verdict)

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
        # V6 Sprint 1 — MODEM_SIGNAL_DROP.  Evaluated on every poll (~30 s), and
        # deliberately ahead of the Monitor logging block below rather than inside
        # it: the rule compares the current sample against a *prior* baseline, and
        # with logging off nothing ever wrote modem_signal_log, so there was no
        # baseline and the rule could never fire.  An unrelated opt-in toggle was
        # silently disabling the alert, not just the log.
        _cur_type = data.get("network_type")
        _cur_sinr = (
            data.get("nr5g_sinr_db") if _cur_type and "5G" in _cur_type
            else data.get("lte_snr_db")
        )
        if self._alert_engine is not None:
            _prior_type, _prior_sinr = self._modem_signal_history()
            for a in self._alert_engine.evaluate_modem_checks(
                _cur_type, _cur_sinr, _prior_sinr, _prior_type,
            ):
                self._surface_alert_in_app(a)
                self._home_page.on_alert(a)
                try:
                    persist_alert(self._store, a)
                except Exception:
                    pass  # non-fatal — persistence failure must not block modem UI updates
        # Fold this sample in only after evaluating, so the baseline stays "prior".
        self._modem_sinr_series.append(_cur_sinr)
        self._modem_prev_network_type = _cur_type

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
                        record_modem_signal(
                            self._store,
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
                        # A new row exists — drop the cached copy so the next poll
                        # re-reads it (see _modem_signal_history).
                        self._modem_hist_cache = None
                    except Exception:
                        pass  # log_modem_entry is best-effort; DB write failure is non-fatal

    @pyqtSlot(str, bool, str, str)
    def _on_plugin_reachability(
        self, instance_id: str, unreachable: bool, label: str, reason: str,
    ) -> None:
        """INFRA_UNREACHABLE — one hardware-plugin poll outcome (Phase 4 C4).

        Called for successful polls too: the healthy observation is what ends
        the EvidenceGate episode and lets a recovery be reported.
        """
        if self._alert_engine is None:
            return
        for a in self._alert_engine.evaluate_infra_unreachable_checks(
            instance_id, unreachable, label=label, reason=reason,
        ):
            self._surface_alert_in_app(a)
            self._home_page.on_alert(a)
            try:
                persist_alert(self._store, a)
            except Exception:
                pass  # non-fatal — persistence failure must not block plugin polling

    @pyqtSlot(float)
    def _on_dns_sample(self, dns_ms: float) -> None:
        """DNS_LATENCY — one DNS latency measurement from the logger (Phase 4 C5).

        Arrives every cycle whether or not the user enabled DNS *logging*, and
        for failed probes too (-1.0), which the engine needs in order to ignore
        them without ending an open episode.
        """
        if self._alert_engine is None:
            return
        for a in self._alert_engine.evaluate_dns_latency_checks(
            dns_ms, outage_hosts=self._dns_outage_hosts(),
        ):
            self._surface_alert_in_app(a)
            self._home_page.on_alert(a)
            try:
                persist_alert(self._store, a)
            except Exception:
                pass  # non-fatal — persistence failure must not block the logger

    def _dns_outage_hosts(self) -> tuple:
        """Hosts whose being down makes slow DNS a symptom, not a finding.

        The gateway plus the availability monitor's internet probes — not the
        whole of `_host_down_since`, which has held every scanned LAN device
        since C3 routed the LAN availability worker into the engine. One dead
        printer must not mute DNS alerting.
        """
        from modules.availability_monitor import DEFAULT_TARGETS
        # RULE-NET1: "gateway" is Optional[str] and is present-but-None on a
        # VPN or a just-flushed ARP cache, so .get(k, "") is not enough.
        gw = (self._net_info.get("gateway") or "") if self._net_info else ""
        return tuple([h for h in (gw,) if h] + list(DEFAULT_TARGETS))

    def _modem_signal_history(self):
        """Return ``(prior_network_type, prior_sinr_series)`` for MODEM_SIGNAL_DROP.

        Prefers the persisted 7-day `modem_signal_log` — it is the richer
        baseline and keeps the Monitor-logging-on path behaving exactly as it
        did — but falls back to an in-memory rolling window so the rule still
        works with logging off, which is the default and was previously a state
        in which it could never fire at all.  Whichever series has more samples
        wins, so a stale single logged row cannot starve the rule of the history
        it needs to reach `rule.min_samples`.

        The logged copy is cached because `_on_modem_signal` is the only writer
        of that table: between writes a fresh query returns identical rows, so
        re-running it on every 30 s poll would buy nothing.
        """
        db_type = None
        db_sinr: list = []
        if self._store is not None:
            if self._modem_hist_cache is None:
                try:
                    self._modem_hist_cache = self._store.query_modem_signal_log(
                        hours=168.0, limit=500,
                    )
                except Exception:
                    self._modem_hist_cache = []  # DB unavailable — use memory only
            if self._modem_hist_cache:
                db_type = self._modem_hist_cache[0].network_type
                db_sinr = [
                    v for v in (
                        (p.nr5g_sinr if p.network_type and "5G" in p.network_type else p.lte_snr)
                        for p in self._modem_hist_cache
                    ) if v is not None
                ]

        mem_sinr = self._modem_sinr_series.values()
        prior_type = db_type if db_type is not None else self._modem_prev_network_type
        return prior_type, (db_sinr if len(db_sinr) >= len(mem_sinr) else mem_sinr)

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
            self._scan_watchdog.stop()
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
            lbl.setStyleSheet(f"color:{_s.TEXT_SECONDARY}; font-size:11px; padding:0 10px;")
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
        import time as _time
        from ui import styles as _s
        from PyQt6.QtWidgets import QApplication
        _t0 = _time.perf_counter()
        # Single app-level setStyleSheet() instead of one on Dashboard (MAIN_STYLE)
        # plus a second on QApplication (get_app_qss(), QMenu/QToolTip only): each
        # setStyleSheet() call forces Qt to recursively re-polish EVERY widget in
        # the application, regardless of the new sheet's size — so two calls back
        # to back means two full-tree re-polishes. Since Dashboard is a descendant
        # of QApplication, the app-level sheet already cascades down to it and
        # every page underneath; combining the two payloads into one app-level
        # call keeps identical coverage (full page styling + QMenu/QToolTip) at
        # half the re-polish cost. Measured: this was ~60-80% of the total
        # theme-switch stall (up to 2.7s of it), dwarfing the ~2,000-widget
        # _reapply_themed() pass (styles.py) and the 77-page refresh_theme()
        # fan-out below.
        _app = QApplication.instance()
        if _app:
            # RULE-STARTUP2. This is already called from inside apply_theme()'s
            # own _suspend_repaints() block (theme_changed is emitted there, and
            # a same-thread connection dispatches synchronously) — wrapping again
            # here makes that lexically true instead of relying on emit-time
            # ordering, which a future change to the connection type could break.
            with _s._suspend_repaints():
                _app.setStyleSheet(_s.MAIN_STYLE + _s.get_app_qss())
        else:
            self.setStyleSheet(_s.MAIN_STYLE)  # no QApplication — headless test path
        _t_stage3 = _time.perf_counter()
        # experimental/theme_switch_deferred (RULE-EXP1): only the page the user
        # is actually looking at needs to be correct right now — every other
        # stack page (incl. any matplotlib re-render its refresh_theme() does)
        # is queued and flushed on first navigation to it (_nav_rail_go_to,
        # ui/nav/builder.py) instead of paying for all ~76 up front. Default
        # False keeps the previously-verified eager fan-out byte-for-byte intact.
        _current_widget = self._stack.currentWidget() if self._theme_switch_deferred else None
        for i in range(self._stack.count()):
            w = self._stack.widget(i)
            if not w or not hasattr(w, "refresh_theme"):
                continue
            if self._theme_switch_deferred and w is not _current_widget:
                self._theme_dirty_widgets.add(w)
            else:
                w.refresh_theme()
        # The DNS/ping LiveGraphWidget is embedded inside a QStackedWidget page
        # that has no refresh_theme, so the fan-out above cannot reach it —
        # forward the live theme switch to it explicitly.
        _graph = getattr(self, "_graph", None)
        if _graph is not None and hasattr(_graph, "refresh_theme"):
            _graph.refresh_theme()
        # The SNMP interface-errors chart lives on the Dashboard (tabs_monitors
        # mixin), not on a stack page, so the fan-out cannot reach it either.
        if hasattr(self, "refresh_snmp_if_theme"):
            self.refresh_snmp_if_theme()
        for btn in getattr(self, "_nav_rail_buttons", {}).values():
            if hasattr(btn, "refresh_theme"):
                btn.refresh_theme()
        flyout = getattr(self, "_nav_flyout", None)
        if flyout and hasattr(flyout, "refresh_theme"):
            flyout.refresh_theme()
        _t_stage4 = _time.perf_counter()
        # Uses ui.styles' dedicated theme_switch instrumentation logger — a
        # bare log.info() here would be silently dropped (no logging.basicConfig()
        # anywhere in the app, so root level is the default WARNING).
        _s._ensure_theme_switch_log_handler()
        _s._theme_switch_log.info(
            "_on_theme_changed(%s): stage3 app setStyleSheet (merged)=%.1fms "
            "stage4 refresh_theme fan-out (%d pages)=%.1fms total=%.1fms",
            _name, (_t_stage3 - _t0) * 1000, self._stack.count(),
            (_t_stage4 - _t_stage3) * 1000, (_t_stage4 - _t0) * 1000,
        )





