"""
header.py — AppHeaderMixin: header construction and frameless-window behaviour.

Extracted from ui/dashboard.py (Sprint 6, S13-3).
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QPoint
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

from ui.styles import (
    NAV_DIVIDER,
)


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
    _edge_grips             dict         — 8 _Grip widgets around the window
    _snap_subclass_proc     ctypes cb    — Win32 subclass procedure (optional)
    _snap_subclass_installed bool        — guards one-time subclassing
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
            from ui.styles import NAV_BAR, NAV_DIVIDER
            p = QPainter(self)
            p.fillRect(self.rect(), QColor(NAV_BAR))
            p.setPen(QColor(NAV_DIVIDER))
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
        from ui.styles import ACCENT, ACCENT_DARK, BG_CARD, BG_HOVER, BORDER, NAV_BAR, RED
        from ui.styles import SIDEBAR_SECTION_BG, SIDEBAR_HOVER, TEXT_MUTED, TEXT_PRIMARY
        from ui.styles import WHITE

        w = self._DragHeader(self)
        w.setObjectName("appBar")
        w.setFixedHeight(42)
        # Background is painted by _DragHeader.paintEvent — no CSS needed for colour.
        # Stylesheet here only scopes child widget colours (labels transparent, etc.)
        w.setStyleSheet(
            f"QLabel {{ background:transparent; color:{WHITE}; border:none; }}"
        )
        lay = QHBoxLayout(w)
        lay.setContentsMargins(14, 0, 0, 0)
        lay.setSpacing(6)

        # ── Brand (left, fixed) ───────────────────────────────────────────────
        import sys as _sys
        _base = Path(_sys._MEIPASS) if getattr(_sys, "frozen", False) else Path(__file__).parent.parent
        _pix = QPixmap(str(_base / "assets" / "icons" / "netsentinel.png"))
        _icon = QLabel()
        _icon.setFixedSize(24, 24)
        _icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _icon.setStyleSheet(f"background:{NAV_BAR};")
        if not _pix.isNull():
            _icon.setPixmap(
                _pix.scaled(24, 24,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
            )
            _icon.repaint()
        else:
            _icon.setText("N")
            _icon.setStyleSheet(
                f"background:{ACCENT}; color:{WHITE}; border-radius:5px;"
                " font-size:13px; font-weight:bold;"
            )
        lay.addWidget(_icon)
        lay.addSpacing(6)

        brand_lbl = QLabel("NetSentinel")
        brand_lbl.setObjectName("lblTitle")
        brand_lbl.setStyleSheet(
            f"color:{WHITE}; background:transparent;"
            " font-size:13px; font-weight:bold; letter-spacing:0.5px;"
        )
        lay.addWidget(brand_lbl)

        # ── Stretch — pushes everything else to the right ─────────────────────
        lay.addStretch(1)

        # ── Network status (centre) — hidden until a scan produces real data ────
        self._verdict_badge = QLabel()
        self._verdict_badge.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:11px; font-weight:600;"
            f" background:transparent; border:none; padding:0 12px;"
        )
        self._verdict_badge.setToolTip("Overall network status")
        self._verdict_badge.setVisible(False)
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
        _menu_s.setStyleSheet(
            f"QMenu {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; padding:4px; font-size:11px; }}"
            f"QMenu::item:selected {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
        )

        _act_about = _menu_s.addAction("About NetSentinel")
        _act_about.triggered.connect(self._show_about)
        _menu_s.addSeparator()
        _act_app_settings = _menu_s.addAction("⚙  App Settings…")
        _act_app_settings.triggered.connect(self._open_settings_dialog)
        _menu_s.addSeparator()
        _act_quit = _menu_s.addAction("✕  Quit NetSentinel")
        _act_quit.triggered.connect(self._quit_app)

        # Transparent at rest — header dark bg shows through; border+accent on hover
        _icon_btn_qss = (
            f"QToolButton {{ background:transparent; color:{TEXT_MUTED};"
            f" border:1px solid {SIDEBAR_SECTION_BG}; border-radius:5px;"
            f" font-family:'Segoe UI Symbol','Segoe UI',sans-serif;"
            f" font-size:12px; padding:0 8px;"
            f" min-height:26px; max-height:26px; }}"
            f"QToolButton:hover {{ background:{ACCENT}; color:{WHITE}; border-color:{ACCENT_DARK}; }}"
            "QToolButton::menu-indicator { image: none; }"
        )
        _btn_settings = QToolButton()
        _btn_settings.setText("⚙︎")
        _btn_settings.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        _btn_settings.setMenu(_menu_s)
        _btn_settings.setToolTip("Scan Settings — module toggles, durations, and app preferences  (Ctrl+,)")
        _btn_settings.setStyleSheet(_icon_btn_qss)
        lay.addSpacing(4)
        lay.addWidget(_btn_settings)

        # ── Global time range picker (TIME-1) ────────────────────────────────
        _time_combo_qss = (
            f"QComboBox {{ background:transparent; color:{TEXT_MUTED};"
            f" border:1px solid {SIDEBAR_SECTION_BG}; border-radius:5px;"
            f" font-size:11px; padding:0 6px;"
            f" min-height:26px; max-height:26px; min-width:52px; }}"
            f"QComboBox:hover {{ border-color:{ACCENT}; color:{WHITE}; }}"
            f"QComboBox::drop-down {{ border:none; width:16px; }}"
            f"QComboBox QAbstractItemView {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; selection-background-color:{ACCENT}; }}"
        )
        self._time_range_combo = QComboBox()
        self._time_range_combo.addItems(["1h", "6h", "24h", "7d", "30d"])
        self._time_range_combo.setCurrentText("24h")
        self._time_range_combo.setToolTip("Global time window — applies to all data pages")
        self._time_range_combo.setStyleSheet(_time_combo_qss)
        self._time_range_combo.currentTextChanged.connect(self._on_global_time_changed)
        lay.addSpacing(4)
        lay.addWidget(self._time_range_combo)

        # ── Scan button — persistent trigger visible from every page ─────────
        self._header_scan_btn = QToolButton()
        self._header_scan_btn.setText("▶  Scan")
        self._header_scan_btn.setToolTip(
            "Run full network scan (ARP + WiFi + DNS + port discovery)\n"
            "Tip: Ctrl+K to search pages · Ctrl+F to filter sidebar · Ctrl+, for Settings"
        )
        self._header_scan_btn.setStyleSheet(_icon_btn_qss)
        self._header_scan_btn.clicked.connect(self._start_full_scan)
        lay.addWidget(self._header_scan_btn)

        # ── Window controls ───────────────────────────────────────────────────
        # Segoe MDL2 Assets: the exact font Windows uses for its own title bar
        # buttons — looks native on Win10/11; degrades to readable symbols elsewhere.
        _sep = QFrame()
        _sep.setFrameShape(QFrame.Shape.VLine)
        _sep.setFixedWidth(1)
        _sep.setFixedHeight(26)
        _sep.setStyleSheet(f"background:{NAV_DIVIDER}; border:none;")
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

        _wc_base = (
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED};"
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
        _btn_min.setStyleSheet(
            _wc_base +
            f"QPushButton:hover {{ background:{SIDEBAR_HOVER}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{SIDEBAR_HOVER}; color:{WHITE}; }}"
        )
        _btn_min.clicked.connect(self.showMinimized)
        lay.addWidget(_btn_min)

        self._maximize_btn = _ChromeButton("\uE922")   # ChromeMaximize
        self._maximize_btn.setToolTip("Maximise")
        self._maximize_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._maximize_btn.setFont(_wc_font)
        self._maximize_btn.setStyleSheet(
            _wc_base +
            f"QPushButton:hover {{ background:{SIDEBAR_HOVER}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{SIDEBAR_HOVER}; color:{WHITE}; }}"
        )
        self._maximize_btn.clicked.connect(self._toggle_maximize)
        lay.addWidget(self._maximize_btn)

        _btn_close = _ChromeButton("\uE8BB")   # ChromeClose
        _btn_close.setToolTip("Close")
        _btn_close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        _btn_close.setFont(_wc_font)
        _btn_close.setStyleSheet(
            _wc_base +
            f"QPushButton:hover {{ background:{RED}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{RED}; color:{WHITE}; }}"
        )
        _btn_close.clicked.connect(self._quit_app)
        lay.addWidget(_btn_close)

        return w

    # ── Frameless window — helpers ───────────────────────────────────────────

    def _toggle_maximize(self):
        from PyQt6.QtCore import Qt
        if self.windowState() & Qt.WindowState.WindowMaximized:
            # Capture and clear _pre_maximize_geo BEFORE showNormal() so the
            # changeEvent handler (which also clears it) cannot race us.
            pre_geo = self._pre_maximize_geo
            self._pre_maximize_geo = None
            self.showNormal()
            if pre_geo is not None:
                self.setGeometry(pre_geo)
        else:
            self._pre_maximize_geo = self.geometry()
            self.showMaximized()

    def changeEvent(self, event):
        super().changeEvent(event)
        if getattr(self, "_maximize_btn", None) is not None:
            from PyQt6.QtCore import QEvent, Qt
            if event.type() == QEvent.Type.WindowStateChange:
                is_max = bool(self.windowState() & Qt.WindowState.WindowMaximized)
                self._maximize_btn.setText("\uE923" if is_max else "\uE922")
                self._maximize_btn.setToolTip("Restore" if is_max else "Maximise")
                if not is_max:
                    self._pre_maximize_geo = None
                if hasattr(self, "_edge_grips"):
                    self._place_edge_grips()
        # Minimize-to-tray opt-in — uses cached _minimize_to_tray to avoid QSettings I/O
        from PyQt6.QtCore import QEvent, Qt
        if (event.type() == QEvent.Type.WindowStateChange
                and bool(self.windowState() & Qt.WindowState.WindowMinimized)
                and getattr(self, "_tray_manager", None) is not None
                and self._tray_manager.is_available()
                and getattr(self, "_minimize_to_tray", False)):
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self._tray_manager._hide_window)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_edge_grips"):
            self._place_edge_grips()

    # ── Windows Snap Layouts ─────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_snap_subclass_installed", False):
            self._install_snap_subclass()
            self._snap_subclass_installed = True
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

    def _install_snap_subclass(self):
        """Subclass the Win32 HWND so WM_NCHITTEST returns HTMAXBUTTON over our
        maximize button.  This is safer than nativeEvent because the message ID
        arrives as a plain C argument — no MSG struct pointer parsing needed."""
        try:
            import ctypes, ctypes.wintypes as wt

            WM_NCHITTEST = 0x0084
            HTMAXBUTTON  = 9

            _DefSubclassProc = ctypes.windll.comctl32.DefSubclassProc
            _DefSubclassProc.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
            _DefSubclassProc.restype  = ctypes.c_ssize_t

            SUBCLASSPROC = ctypes.WINFUNCTYPE(
                ctypes.c_ssize_t,
                wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM,
                ctypes.c_size_t,   # UINT_PTR  uIdSubclass
                ctypes.c_size_t,   # DWORD_PTR dwRefData
            )

            WM_NCLBUTTONDOWN = 0x00A1
            WM_NCLBUTTONUP   = 0x00A2

            win = self

            def _over_maximize_btn():
                btn = win._maximize_btn
                if btn is None:
                    return False
                from PyQt6.QtGui import QCursor
                p  = QCursor.pos()
                tl = btn.mapToGlobal(btn.rect().topLeft())
                return (tl.x() <= p.x() < tl.x() + btn.width() and
                        tl.y() <= p.y() < tl.y() + btn.height())

            def _proc(hwnd, msg, wparam, lparam, uid, ref):
                if msg == WM_NCHITTEST and _over_maximize_btn():
                    return HTMAXBUTTON
                # Intercept non-client clicks on the maximize button so we drive
                # the toggle ourselves instead of letting DefWindowProc do it.
                if wparam == HTMAXBUTTON:
                    if msg == WM_NCLBUTTONDOWN:
                        return 0  # swallow — we act on release
                    if msg == WM_NCLBUTTONUP:
                        win._toggle_maximize()
                        return 0
                return _DefSubclassProc(hwnd, msg, wparam, lparam)

            self._snap_subclass_proc = SUBCLASSPROC(_proc)
            hwnd = int(self.winId())

            # WS_THICKFRAME + WS_MAXIMIZEBOX are required for Windows to show the
            # Snap Layout flyout — without them it ignores HTMAXBUTTON entirely.
            GWL_STYLE      = -16
            WS_THICKFRAME  = 0x00040000
            WS_MAXIMIZEBOX = 0x00010000
            _GetWindowLong = ctypes.windll.user32.GetWindowLongW
            _SetWindowLong = ctypes.windll.user32.SetWindowLongW
            _GetWindowLong.argtypes = [wt.HWND, ctypes.c_int]
            _GetWindowLong.restype  = ctypes.c_long
            _SetWindowLong.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_long]
            _SetWindowLong.restype  = ctypes.c_long
            style = _GetWindowLong(hwnd, GWL_STYLE)
            _SetWindowLong(hwnd, GWL_STYLE, style | WS_THICKFRAME | WS_MAXIMIZEBOX)
            # Tell DWM to recalculate the non-client area after the style change.
            SWP_FLAGS = 0x0027  # SWP_NOMOVE|SWP_NOSIZE|SWP_NOZORDER|SWP_FRAMECHANGED
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FLAGS)

            _SetWindowSubclass = ctypes.windll.comctl32.SetWindowSubclass
            _SetWindowSubclass.argtypes = [wt.HWND, SUBCLASSPROC, ctypes.c_size_t, ctypes.c_size_t]
            _SetWindowSubclass.restype  = wt.BOOL
            _SetWindowSubclass(hwnd, self._snap_subclass_proc, 1, 0)
        except Exception:
            pass  # non-fatal

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
        from ui.styles import ACCENT, UPDATE_BAR_BG, UPDATE_BAR_BORDER, UPDATE_BAR_FG
        from ui.styles import BG_HOVER

        container = QWidget()
        container.setObjectName("updateNotifBar")
        container.setFixedHeight(28)
        row = QHBoxLayout(container)
        row.setContentsMargins(12, 0, 8, 0)
        row.setSpacing(6)
        container.setStyleSheet(
            f"QWidget#updateNotifBar {{ background:{UPDATE_BAR_BG}; "
            f"border-bottom: 1px solid {UPDATE_BAR_BORDER}; }}"
        )
        icon = QLabel("↑")
        icon.setStyleSheet(f"color:{ACCENT}; font-size:12px; background:transparent; border:none;")
        row.addWidget(icon)
        self._update_bar_lbl = QLabel("A new version is available.")
        self._update_bar_lbl.setStyleSheet(
            f"color:{UPDATE_BAR_FG}; font-size:11px; background:transparent; border:none;"
        )
        self._update_bar_lbl.setOpenExternalLinks(True)
        self._update_bar_lbl.setTextFormat(Qt.TextFormat.RichText)
        row.addWidget(self._update_bar_lbl, 1)
        btn_dismiss = QPushButton("✕")
        btn_dismiss.setFixedSize(20, 20)
        btn_dismiss.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{ACCENT}; border:none; font-size:12px; }}"
            f"QPushButton:hover {{ color:{UPDATE_BAR_FG}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        btn_dismiss.clicked.connect(container.hide)
        row.addWidget(btn_dismiss)
        return container

    def _start_update_check(self):
        """Kick off a background thread to check the GitHub releases API."""
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
        from PyQt6.QtWidgets import QApplication
        from ui.styles import ACCENT
        current = QApplication.applicationVersion()
        msg = (
            f"NetSentinel v{latest} is available (you have v{current}) — "
            f'<a href="https://github.com/ossianericson/netsentinel/releases/latest" '
            f'style="color:{ACCENT};">Download</a>'
            f' &nbsp;·&nbsp; or run: <code>winget upgrade NetSentinel.NetSentinel</code>'
        )
        self._update_bar_lbl.setText(msg)
        self._update_bar.setVisible(True)
