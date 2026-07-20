"""
header.py — AppHeaderMixin: header construction and frameless-window behaviour.

Extracted from ui/dashboard.py (Sprint 6, S13-3).
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QPoint, QEvent
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)
from PyQt6.QtCore import pyqtSlot

from ui import styles as _s
from ui.nav.rail import _ClickLabel
from ui.widgets.device_detail_pane import _make_close_icon, _wire_close_icon


class AppHeaderMixin:
    """
    Mixin providing the top application bar and frameless-window behaviour
    for Dashboard.

    Must appear before QMainWindow in the MRO:
        class Dashboard(ScanResultMixin, AppHeaderMixin, QMainWindow): ...

    Attributes set on ``self`` by this mixin
    ----------------------------------------
    _maximize_btn           QPushButton  — created by _build_header()
    _pre_maximize_geo       QRect|None   — saved before showMaximized()
    _verdict_badge          QLabel       — network-status badge in header
    _btn_scan               QPushButton  — logical scan trigger (hidden)
    _btn_export             QPushButton  — logical export trigger (hidden)
    _time_range_combo       QComboBox    — global time-range picker
    _header_scan_btn        QToolButton  — "▶  Scan" button in header
    _update_bar_lbl         QLabel       — update-available message
    _app_header             QWidget      — the header bar itself (native hit-test)
    _header_nc_client_widgets list       — header widgets that stay HTCLIENT
    _edge_grips             dict         — 8 _Grip widgets (frameless path only)
    _snap_subclass_installed bool        — guards one-time chrome installation

    Window chrome comes in two flavours, selected by Dashboard._native_chrome and
    installed by _install_window_chrome(); the Win32 hooks themselves live in
    ui/native_chrome.py. Under native chrome the header is the caption and the 8
    resize grips are not installed — Windows does both natively.
    """

    # ── Frameless window — drag support on header ────────────────────────────

    class _DragHeader(QWidget):
        """Header bar that lets the user drag the frameless window."""

        def __init__(self, window: "Dashboard", parent=None):  # type: ignore[name-defined]
            super().__init__(parent)
            self._win = window
            self._drag_pos: QPoint | None = None
            self.setAttribute(
                __import__("PyQt6.QtCore", fromlist=["Qt"]).Qt.WidgetAttribute.WA_StyledBackground,
                False,
            )

        def paintEvent(self, _e):
            from PyQt6.QtGui import QPainter, QColor
            p = QPainter(self)
            p.fillRect(self.rect(), QColor(_s.NAV_BAR))
            p.setPen(QColor(_s.NAV_DIVIDER))
            p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
            p.end()

        def mousePressEvent(self, e):
            if e.button() == Qt.MouseButton.LeftButton:
                self._drag_pos = (
                    e.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
                )
            super().mousePressEvent(e)

        def mouseMoveEvent(self, e):
            if self._drag_pos and e.buttons() == Qt.MouseButton.LeftButton:
                if self._win.isMaximized():
                    # restore first, then re-anchor drag so window follows cursor
                    self._win.showNormal()
                    self._drag_pos = QPoint(
                        self._win.width() // 2,
                        e.globalPosition().toPoint().y() - self._win.frameGeometry().top(),
                    )
                self._win.move(e.globalPosition().toPoint() - self._drag_pos)
            super().mouseMoveEvent(e)

        def mouseReleaseEvent(self, e):
            self._drag_pos = None
            super().mouseReleaseEvent(e)

        def mouseDoubleClickEvent(self, e):
            if e.button() == Qt.MouseButton.LeftButton:
                self._win._toggle_maximize()
            super().mouseDoubleClickEvent(e)

    def _build_header(self) -> QWidget:
        """Slim top bar: brand | stretch | verdict | actions."""
        from PyQt6.QtWidgets import QMenu, QToolButton

        w = self._DragHeader(self)
        w.setObjectName("appBar")
        w.setFixedHeight(42)
        # Background is painted by _DragHeader.paintEvent — no CSS needed for colour.
        # Stylesheet here only scopes child widget colours (labels transparent, etc.)
        _s.themed_ss(
            w, "QLabel {{ background:transparent; color:{WHITE}; border:none; }}"
        )
        lay = QHBoxLayout(w)
        lay.setContentsMargins(14, 0, 0, 0)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # ── Brand (left, fixed) ───────────────────────────────────────────────
        import sys as _sys
        _base = Path(_sys._MEIPASS) if getattr(_sys, "frozen", False) else Path(__file__).parent.parent
        _pix = QPixmap(str(_base / "assets" / "icons" / "netsentinel.png"))
        _icon = QLabel()
        _icon.setFixedSize(24, 24)
        _icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _s.themed_ss(_icon, "background:{NAV_BAR};")
        if not _pix.isNull():
            _icon.setPixmap(
                _pix.scaled(24, 24,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
            )
            _icon.repaint()
        else:
            _icon.setText("N")
            _s.themed_ss(
                _icon,
                "background:{ACCENT}; color:{WHITE}; border-radius:5px;"
                " font-size:13px; font-weight:bold;",
            )
        lay.addWidget(_icon)
        lay.addSpacing(6)

        brand_lbl = QLabel("NetSentinel")
        brand_lbl.setObjectName("lblTitle")
        _s.themed_ss(
            brand_lbl,
            "color:{WHITE}; background:transparent;"
            " font-size:13px; font-weight:bold; letter-spacing:0.5px;",
        )
        lay.addWidget(brand_lbl)

        # ── Stretch — pushes everything else to the right ─────────────────────
        lay.addStretch(1)

        # ── Network status (centre) — hidden until a scan produces real data ────
        self._verdict_badge = _ClickLabel()
        # Shape J: restyled live by monitor_state / tabs_network — _s.* read, not themed_ss.
        self._verdict_badge.setStyleSheet(
            f"color:{_s.TEXT_MUTED}; font-size:11px; font-weight:600;"
            f" background:transparent; border:none; padding:0 12px;"
        )
        self._verdict_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self._verdict_badge.setToolTip("Overall network status — click for details")
        self._verdict_badge.setVisible(False)
        self._verdict_badge.clicked.connect(self._on_verdict_badge_clicked)
        lay.addWidget(self._verdict_badge)

        lay.addStretch(1)

        # Hidden logical widgets — keep as attributes so _set_scanning can enable/disable
        self._btn_scan = QPushButton()
        self._btn_scan.clicked.connect(self._start_full_scan)
        self._btn_export = QPushButton()
        self._btn_export.setEnabled(False)
        self._btn_export.clicked.connect(self._export_report)

        # ── Settings dropdown (⚙) ─────────────────────────────────────────────
        _menu_s = QMenu()
        _s.themed_ss(
            _menu_s,
            "QMenu {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            " border:1px solid {BORDER}; padding:4px; font-size:11px; }}"
            "QMenu::item:selected {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}",
        )

        _act_about = _menu_s.addAction("About NetSentinel")
        _act_about.triggered.connect(self._show_about)
        _menu_s.addSeparator()
        _act_app_settings = _menu_s.addAction("⚙  App Settings…")
        _act_app_settings.triggered.connect(self._open_settings_dialog)
        _menu_s.addSeparator()
        _act_quit = _menu_s.addAction("Quit NetSentinel")
        _act_quit.setIcon(_make_close_icon(_s.TEXT_MUTED))
        _act_quit.triggered.connect(self._quit_app)

        # Transparent at rest — header dark bg shows through; border+accent on hover.
        # The border is a faint WHITE-alpha hairline so it blends on the dark header
        # bar in BOTH themes. (A plain-hex token like SIDEBAR_SECTION_BG is a light
        # near-white value in Arctic → it drew a harsh white box on the dark bar.)
        def _icon_btn_qss():
            return (
                f"QToolButton {{ background:transparent; color:{_s.TEXT_MUTED};"
                f" border:1px solid {_s.alpha(_s.WHITE, 0x22)}; border-radius:5px;"
                f" font-family:'Segoe UI Symbol','Segoe UI',sans-serif;"
                f" font-size:12px; padding:0 8px;"
                f" min-height:26px; max-height:26px; }}"
                f"QToolButton:hover {{ background:{_s.ACCENT}; color:{_s.WHITE}; border-color:{_s.ACCENT_DARK}; }}"
                "QToolButton::menu-indicator { image: none; }"
            )
        _btn_settings = QToolButton()
        _btn_settings.setText("⚙︎")
        _btn_settings.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        _btn_settings.setMenu(_menu_s)
        _btn_settings.setToolTip("Scan Settings — module toggles, durations, and app preferences  (Ctrl+,)")
        _s.themed_ss(_btn_settings, _icon_btn_qss)
        lay.addSpacing(4)
        lay.addWidget(_btn_settings)

        # ── Global time range picker (TIME-1) ────────────────────────────────
        def _time_combo_qss():
            return (
                f"QComboBox {{ background:transparent; color:{_s.TEXT_MUTED};"
                f" border:1px solid {_s.alpha(_s.WHITE, 0x22)}; border-radius:5px;"
                f" font-size:11px; padding:0 6px;"
                f" min-height:26px; max-height:26px; min-width:52px; }}"
                f"QComboBox:hover {{ border-color:{_s.ACCENT}; color:{_s.WHITE}; }}"
                f"QComboBox::drop-down {{ border:none; width:16px; }}"
                f"QComboBox QAbstractItemView {{ background:{_s.BG_CARD}; color:{_s.TEXT_PRIMARY};"
                f" border:1px solid {_s.BORDER}; selection-background-color:{_s.ACCENT}; }}"
            )
        self._time_range_combo = QComboBox()
        self._time_range_combo.addItems(["1h", "6h", "24h", "7d", "30d"])
        self._time_range_combo.setCurrentText("24h")
        self._time_range_combo.setToolTip("Global time window — applies to all data pages")
        _s.themed_ss(self._time_range_combo, _time_combo_qss)
        self._time_range_combo.currentTextChanged.connect(self._on_global_time_changed)
        lay.addSpacing(4)
        lay.addWidget(self._time_range_combo)

        # ── Scan button — persistent PRIMARY action visible from every page ──
        # At rest it matches the ghost chrome buttons beside it (⚙ / time range):
        # transparent bg + faint WHITE-alpha hairline on the dark header, accent
        # fill on hover. (A previous session made it solid accent at rest — its
        # hover look — to work around an unrelated colour bug; that made it stop
        # matching its neighbours. This restores the shared at-rest style.)
        def _scan_btn_qss():
            return (
                f"QToolButton {{ background:transparent; color:{_s.TEXT_MUTED};"
                f" border:1px solid {_s.alpha(_s.WHITE, 0x22)}; border-radius:5px; font-weight:bold;"
                f" font-family:'Segoe UI Symbol','Segoe UI',sans-serif;"
                f" font-size:12px; padding:0 14px;"
                f" min-height:26px; max-height:26px; }}"
                f"QToolButton:hover {{ background:{_s.ACCENT}; color:{_s.WHITE}; border-color:{_s.ACCENT_DARK}; }}"
                f"QToolButton:pressed {{ background:{_s.ACCENT_DARK}; color:{_s.WHITE}; border-color:{_s.ACCENT_DARK}; }}"
            )
        self._header_scan_btn = QToolButton()
        self._header_scan_btn.setText("▶  Scan")
        self._header_scan_btn.setToolTip(
            "Run full network scan (ARP + WiFi + DNS + port discovery)\n"
            "Tip: Ctrl+K to search pages · Ctrl+F to filter sidebar · Ctrl+, for Settings"
        )
        _s.themed_ss(self._header_scan_btn, _scan_btn_qss)
        self._header_scan_btn.clicked.connect(self._start_full_scan)
        lay.addWidget(self._header_scan_btn)

        # ── Window controls ───────────────────────────────────────────────────
        # Segoe MDL2 Assets: the exact font Windows uses for its own title bar
        # buttons — looks native on Win10/11; degrades to readable symbols elsewhere.
        _sep = QFrame()
        _sep.setFrameShape(QFrame.Shape.VLine)
        _sep.setFixedWidth(1)
        _sep.setFixedHeight(26)
        _s.themed_ss(_sep, "background:{NAV_DIVIDER}; border:none;")
        lay.addSpacing(8)
        lay.addWidget(_sep)
        lay.addSpacing(2)

        # _ChromeButton strips Qt's focus-rect drawing so no ring ever bleeds
        # outside the button bounds — matches VS Code / native title bar behaviour.
        from PyQt6.QtWidgets import QStyle

        class _ChromeButton(QPushButton):
            def initStyleOption(self, option):
                super().initStyleOption(option)
                option.state = option.state & ~QStyle.StateFlag.State_HasFocus

        def _wc_base():
            return (
                f"QPushButton {{ background:transparent; color:{_s.TEXT_MUTED};"
                f" border:none; border-radius:0px; outline:none; padding:0;"
                f" font-family:'Segoe MDL2 Assets','Segoe UI Symbol','Segoe UI';"
                f" font-size:10px;"
                f" min-width:46px; max-width:46px;"
                f" min-height:42px; max-height:42px; }}"
                f"QPushButton:focus, QPushButton:focus-visible {{ outline:none; border:none; }}"
                f"QPushButton:pressed {{ outline:none; border:none; }}"
            )
        # NoSubpixelAntialias eliminates ClearType fringing on Segoe MDL2 glyphs
        _wc_font = QFont("Segoe MDL2 Assets", 10)
        _wc_font.setStyleStrategy(QFont.StyleStrategy.NoSubpixelAntialias)

        _btn_min = _ChromeButton("\uE921")     # ChromeMinimize
        _btn_min.setToolTip("Minimise")
        _btn_min.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        _btn_min.setFont(_wc_font)
        _s.themed_ss(
            _btn_min,
            lambda: _wc_base()
            + f"QPushButton:hover {{ background:{_s.SIDEBAR_HOVER}; color:{_s.WHITE}; }}"
            + f"QPushButton:pressed {{ background:{_s.SIDEBAR_HOVER}; color:{_s.WHITE}; }}",
        )
        _btn_min.clicked.connect(self.showMinimized)
        lay.addWidget(_btn_min)

        self._maximize_btn = _ChromeButton("\uE922")   # ChromeMaximize
        self._maximize_btn.setToolTip("Maximize")
        self._maximize_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._maximize_btn.setFont(_wc_font)
        # [ncHover="true"] mirrors :hover for the native-chrome path. There, this
        # button is the one HTMAXBUTTON — it lives in the NON-CLIENT area (which is
        # exactly what makes the Snap Layouts flyout legitimate), so Qt never sees a
        # mouse event for it and :hover can never fire. native_chrome.py posts the
        # hover across and drives this rule instead. Inert on the frameless path.
        _s.themed_ss(
            self._maximize_btn,
            lambda: _wc_base()
            + f"QPushButton:hover {{ background:{_s.SIDEBAR_HOVER}; color:{_s.WHITE}; }}"
            + f'QPushButton[ncHover="true"] {{ background:{_s.SIDEBAR_HOVER}; color:{_s.WHITE}; }}'
            + f"QPushButton:pressed {{ background:{_s.SIDEBAR_HOVER}; color:{_s.WHITE}; }}",
        )
        self._maximize_btn.clicked.connect(self._toggle_maximize)
        lay.addWidget(self._maximize_btn)

        _btn_close = _ChromeButton("\uE8BB")   # ChromeClose
        _btn_close.setToolTip("Close")
        _btn_close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        _btn_close.setFont(_wc_font)
        _s.themed_ss(
            _btn_close,
            lambda: _wc_base()
            + f"QPushButton:hover {{ background:{_s.RED}; color:{_s.WHITE}; }}"
            + f"QPushButton:pressed {{ background:{_s.RED}; color:{_s.WHITE}; }}",
        )
        _btn_close.clicked.connect(self._quit_app)
        lay.addWidget(_btn_close)

        # Read by ui/native_chrome.py's hit-test (via _refresh_chrome_rects).
        # _header_nc_client_widgets are the strips that must stay HTCLIENT so Qt
        # keeps handling their clicks — everything else in the header becomes
        # HTCAPTION and is draggable. Omitting a widget here makes it unclickable
        # under native chrome; the maximize button is deliberately absent (it is
        # the one HTMAXBUTTON).
        self._app_header = w
        self._header_nc_client_widgets = [
            _btn_settings, self._time_range_combo, self._header_scan_btn,
            _btn_min, _btn_close, self._verdict_badge,
        ]
        return w

    # ── Frameless window — helpers ───────────────────────────────────────────

    @pyqtSlot()
    def _toggle_maximize(self):
        """Maximize (dock to the work area) — never full-screen: showFullScreen()
        covers the taskbar and leaves isMaximized() False, silently breaking
        save_settings(), _place_edge_grips() and _DragHeader, which all gate on it."""
        from PyQt6.QtCore import Qt
        if self.windowState() & Qt.WindowState.WindowMaximized:
            self.showNormal()   # Qt restores normalGeometry() itself
        else:
            self._pre_maximize_geo = self.geometry()  # read by save_settings()
            self.showMaximized()

    def changeEvent(self, event):
        super().changeEvent(event)
        if getattr(self, "_maximize_btn", None) is not None:
            from PyQt6.QtCore import QEvent, Qt
            if event.type() == QEvent.Type.WindowStateChange:
                # WindowMaximized also covers native maximize: double-click, Win+Up, Aero Snap.
                is_max = bool(self.windowState() & Qt.WindowState.WindowMaximized)
                # \uE923 = ChromeRestore, \uE922 = ChromeMaximize (Segoe MDL2 Assets)
                self._maximize_btn.setText("\uE923" if is_max else "\uE922")
                self._maximize_btn.setToolTip("Restore Down" if is_max else "Maximize")
                if is_max:
                    # Windows can maximize us without going through _toggle_maximize()
                    # once the window is real (double-click the caption, Win+Up, Aero
                    # Snap, Snap Layouts). Seed the restore size from Qt's own
                    # normalGeometry() so save_settings() still records one.
                    if self._pre_maximize_geo is None:
                        self._pre_maximize_geo = self.normalGeometry()
                else:
                    self._pre_maximize_geo = None
                if hasattr(self, "_edge_grips"):
                    self._place_edge_grips()
                self._refresh_chrome_rects()
        # Minimize-to-tray opt-in — uses cached _minimize_to_tray to avoid QSettings I/O
        from PyQt6.QtCore import QEvent, Qt
        if (event.type() == QEvent.Type.WindowStateChange
                and bool(self.windowState() & Qt.WindowState.WindowMinimized)
                and getattr(self, "_tray_manager", None) is not None
                and self._tray_manager.is_available()
                and getattr(self, "_minimize_to_tray", False)):
            from PyQt6.QtCore import QTimer
            _t = QTimer(self); _t.setSingleShot(True); _t.timeout.connect(self._tray_manager._hide_window); _t.start(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_edge_grips"):
            self._place_edge_grips()
        self._refresh_chrome_rects()

    # ── Windows Snap Layouts ─────────────────────────────────────────────────

    def show_main_window(self) -> None:
        """
        Canonical "make the main window visible" entry point — routed from
        SystemTrayManager._show_window() and app.py's second-instance handler.
        Honours a pending maximize intent recorded by
        app_settings.restore_settings() for a tray-only launch whose last
        session was maximized: replays showMaximized() then the restore-rect
        fixup, in that order (RULE-WIN12 — the SetWindowPlacement-family call
        must land AFTER showMaximized() creates the HWND, never before),
        exactly as restore_settings() would have applied it had the window
        been shown immediately at startup instead of deferred to first reveal.
        """
        if getattr(self, "_pending_show_maximized", False):
            self._pending_show_maximized = False
            self.showMaximized()
            rect = getattr(self, "_pending_maximize_restore_rect", None)
            if rect is not None:
                from ui.app_settings import fix_maximized_restore_rect
                fix_maximized_restore_rect(self, *rect)
        elif self.isMinimized():
            self.showNormal()
        else:
            self.show()

    def showEvent(self, event):
        super().showEvent(event)
        # The ONLY install site for the window chrome. It cannot run earlier: the
        # window needs a realised HWND. Because that puts it *after*
        # _restore_settings() has applied the saved geometry, the install has to
        # re-apply that geometry itself — see _install_window_chrome().
        self._install_window_chrome()
        # Attach toast manager once window is visible
        from ui.widgets.toast import ToastManager
        ToastManager.instance().attach(self)
        # SCHED-3: restore monitors that were running before last close
        if not getattr(self, "_monitors_restored", False):
            self._monitors_restored = True
            from PyQt6.QtCore import QTimer as _QT3
            _QT3.singleShot(3000, self._restore_running_monitors)
        # Welcome overlay — shown once on first ever launch
        if not getattr(self, "_welcome_shown", False):
            self._welcome_shown = True
            from PyQt6.QtCore import QTimer as _QT4
            _QT4.singleShot(600, self._show_welcome_overlay)
        # Tray icon .show() — deferred here (not SystemTrayManager.setup(),
        # called from Dashboard.__init__) because showEvent() only fires
        # after the real window.show() runs in main(), well past every
        # _splash_msg processEvents() pump. See
        # SystemTrayManager.show_tray_icon() (ui/system_tray.py) for the full
        # COM-reentrancy mechanism (docs/spikes/startup-com-reentrancy.md).
        if not getattr(self, "_tray_icon_shown", False):
            self._tray_icon_shown = True
            if getattr(self, "_tray_manager", None) is not None:
                self._tray_manager.show_tray_icon()
        # Deferred page construction: now that the window is up and the event
        # loop is running, drain the placeholder queue in the background so
        # pages are ready before the user reaches them. Short delay lets the
        # first frame paint first.
        if not getattr(self, "_lazy_builder_started", False):
            self._lazy_builder_started = True
            from PyQt6.QtCore import QTimer as _QTlazy
            _QTlazy.singleShot(400, self._start_lazy_page_builder)

    def event(self, e):
        # WinIdChange = Qt recreated our native HWND (to host Network Map's
        # QWebEngineView), which drops the WM_NCCALCSIZE subclass and brings the real
        # title bar back. Re-establish it. docs/spikes/webengine-hwnd-recreation.md.
        if e.type() == QEvent.Type.WinIdChange:
            from ui.native_chrome import reinstall_after_winid_change
            reinstall_after_winid_change(self)
        return super().event(e)

    def _install_window_chrome(self):
        """Install whichever window chrome the experimental flags select. Idempotent.

        Both paths live in ui/native_chrome.py — the Win32 message hooks are kept
        out of this file so the callback that Windows invokes reentrantly can be
        held to "touches zero Qt objects" (RULE-WIN9) and guarded by a test.

        native_chrome  — the real fix: keep a real Windows window (caption, thick
                         frame, max box) and stop Windows *painting* the frame.
                         Aero Snap, Snap Layouts, shake, Alt+Space and native
                         resize all work because the window genuinely has them.
        snap_layout_hover — LEGACY. Returns HTMAXBUTTON on the captionless WS_POPUP
                         that FramelessWindowHint produces, which is the RULE-WIN9
                         fault itself (0x8001010d). Off by default; superseded.

        Ordering vs. geometry: this runs from showEvent() — the earliest point at
        which the window has a realised HWND — which is necessarily *after*
        _restore_settings() has already applied the saved geometry. Qt derives its
        frame margins from the window STYLE, so at restore time it still believes in
        the caption that WM_NCCALCSIZE is about to take away, and places the window a
        caption-height (~32px) out. install_native_chrome() therefore calls
        reapply_geometry_after_chrome() immediately afterwards to put the window back
        on the rect the user actually left it on.
        """
        from PyQt6.QtCore import QSettings as _QSettings

        if getattr(self, "_snap_subclass_installed", False):
            return
        self._snap_subclass_installed = True

        if getattr(self, "_native_chrome", False):
            from ui.native_chrome import install_native_chrome
            if install_native_chrome(self):
                # Remember the HWND that now carries the WM_NCCALCSIZE subclass. If Qt
                # later recreates the window to host a native child (Network Map's
                # QWebEngineView), the WinIdChange hook in event() compares against
                # this to recognise the recreation and re-establish the chrome on the
                # new handle. See docs/spikes/webengine-hwnd-recreation.md.
                self._last_native_hwnd = int(self.winId())
                # The frame just changed shape under Qt: _restore_settings() placed
                # this window against a caption that WM_NCCALCSIZE has now deleted,
                # so it is sitting a caption-height (~32px) out. Put it back on the
                # rect the user actually left it on.
                from ui.app_settings import reapply_geometry_after_chrome
                reapply_geometry_after_chrome(self)
                return
            # Install failed — fall through to the legacy window, which is still
            # frameless-shaped and usable. Better a missing Snap flyout than a
            # window with no chrome behaviour at all.
        if _QSettings("NetSentinel", "NetSentinel").value(
            "experimental/snap_layout_hover", False, type=bool
        ):
            from ui.native_chrome import install_snap_subclass
            install_snap_subclass(self)

    def _refresh_chrome_rects(self):
        """Recache the header/maximize-button rects the native hit-test reads.

        No-op unless native chrome is live. Must run whenever the header's geometry
        within the window changes — a stale cache makes Windows hit-test the wrong
        strip, e.g. treating the Scan button as caption (unclickable).
        """
        if getattr(self, "_native_chrome", False):
            from ui.native_chrome import refresh_chrome_rects
            refresh_chrome_rects(self)

    def _install_edge_grips(self):
        """Create 8 transparent resize-grip strips around the window border."""
        from PyQt6.QtCore import Qt, QRect
        from PyQt6.QtWidgets import QWidget
        _CURSORS = {
            "nw": Qt.CursorShape.SizeFDiagCursor,
            "n":  Qt.CursorShape.SizeVerCursor,
            "ne": Qt.CursorShape.SizeBDiagCursor,
            "w":  Qt.CursorShape.SizeHorCursor,
            "e":  Qt.CursorShape.SizeHorCursor,
            "sw": Qt.CursorShape.SizeBDiagCursor,
            "s":  Qt.CursorShape.SizeVerCursor,
            "se": Qt.CursorShape.SizeFDiagCursor,
        }
        win = self

        class _Grip(QWidget):
            def __init__(self, edge, parent):
                super().__init__(parent)
                self._edge = edge
                self._drag_start = None
                self._start_geo  = None
                self.setCursor(_CURSORS[edge])
                self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
                self.setStyleSheet("background: transparent;")

            def mousePressEvent(self, e):
                if e.button() == Qt.MouseButton.LeftButton:
                    self._drag_start = e.globalPosition().toPoint()
                    self._start_geo  = win.geometry()

            def mouseMoveEvent(self, e):
                if self._drag_start is None:
                    return
                if not (e.buttons() & Qt.MouseButton.LeftButton):
                    return
                d   = e.globalPosition().toPoint() - self._drag_start
                geo = QRect(self._start_geo)
                if "n" in self._edge: geo.setTop(geo.top()    + d.y())
                if "s" in self._edge: geo.setBottom(geo.bottom() + d.y())
                if "w" in self._edge: geo.setLeft(geo.left()   + d.x())
                if "e" in self._edge: geo.setRight(geo.right()  + d.x())
                if geo.width() >= win.minimumWidth() and geo.height() >= win.minimumHeight():
                    win.setGeometry(geo)

            def mouseReleaseEvent(self, e):
                self._drag_start = None

        self._edge_grips = {k: _Grip(k, self) for k in _CURSORS}
        self._place_edge_grips()

    def _place_edge_grips(self):
        from PyQt6.QtCore import Qt
        m = 6
        w, h = self.width(), self.height()
        is_max = bool(self.windowState() & Qt.WindowState.WindowMaximized)
        rects = {
            "nw": (0,     0,     m,     m),
            "n":  (m,     0,     w-2*m, m),
            "ne": (w-m,   0,     m,     m),
            "w":  (0,     m,     m,     h-2*m),
            "e":  (w-m,   m,     m,     h-2*m),
            "sw": (0,     h-m,   m,     m),
            "s":  (m,     h-m,   w-2*m, m),
            "se": (w-m,   h-m,   m,     m),
        }
        for name, grip in self._edge_grips.items():
            x, y, gw, gh = rects[name]
            grip.setGeometry(x, y, gw, gh)
            grip.setVisible(not is_max)
            grip.raise_()

    def _build_update_bar(self) -> QWidget:
        """Thin update-available bar — hidden until a newer release is detected."""
        container = QWidget()
        container.setObjectName("updateNotifBar")
        container.setFixedHeight(36)
        row = QHBoxLayout(container)
        row.setContentsMargins(12, 4, 8, 4)
        row.setSpacing(6)
        _s.themed_ss(
            container,
            "QWidget#updateNotifBar {{ background:{UPDATE_BAR_BG}; "
            "border-bottom: 1px solid {UPDATE_BAR_BORDER}; }}",
        )
        icon = QLabel("↑")
        _s.themed_ss(icon, "color:{ACCENT}; font-size:12px; background:transparent; border:none;")
        row.addWidget(icon)
        self._update_bar_lbl = QLabel("A new version is available.")
        _s.themed_ss(
            self._update_bar_lbl,
            "color:{UPDATE_BAR_FG}; font-size:11px; background:transparent; border:none;",
        )
        self._update_bar_lbl.setOpenExternalLinks(True)
        self._update_bar_lbl.setTextFormat(Qt.TextFormat.RichText)
        row.addWidget(self._update_bar_lbl, 1)
        btn_dismiss = QPushButton()
        btn_dismiss.setFixedSize(20, 20)
        _wire_close_icon(btn_dismiss, "ACCENT")
        _s.themed_ss(
            btn_dismiss,
            "QPushButton {{ background:transparent; border:none; }}"
            "QPushButton:hover {{ background:transparent; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; }}",
        )
        def _dismiss_update_bar() -> None:
            container.hide()
            self.activateWindow()

        btn_dismiss.clicked.connect(_dismiss_update_bar)
        row.addWidget(btn_dismiss)
        return container

    def _start_update_check(self):
        """Kick off a background thread to check the GitHub releases API.

        Runs in Store builds too — both publish the same version numbers, so only
        the remedy _on_update_available() offers differs.
        """
        import threading

        def _check():
            try:
                import urllib.request, json as _json
                from PyQt6.QtWidgets import QApplication
                current = QApplication.applicationVersion()
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
                    self._show_update_bar(latest)
            except Exception:
                pass  # silent — no network or rate-limited; user can check manually

        threading.Thread(target=_check, daemon=True).start()

    def _show_update_bar(self, latest: str):
        """Called from the background thread — must dispatch to the UI thread."""
        self._update_available.emit(latest)

    @pyqtSlot(str)
    def _on_update_available(self, latest: str):
        """Runs on the UI thread — safe to touch widgets."""
        from modules.utils import is_store_app, store_update_url  # noqa: PLC0415
        from PyQt6.QtWidgets import QApplication
        current = QApplication.applicationVersion()
        head = f"NetSentinel v{latest} is available (you have v{current}) — "
        if is_store_app():
            # Only the Store can replace a Store package; routing around it via
            # GitHub/winget is disallowed there. Deep-link the product page.
            link = (f'<a href="{store_update_url()}" '
                    f'style="color:{_s.ACCENT};">Open in Microsoft Store</a>')
        else:
            link = (
                f'<a href="https://github.com/ossianericson/netsentinel/releases/latest" '
                f'style="color:{_s.ACCENT};">Download</a>'
                f' &nbsp;·&nbsp; or run: <code>winget upgrade NetSentinel.NetSentinel</code>'
            )
        self._update_bar_lbl.setText(head + link)
        self._update_bar.setVisible(True)
