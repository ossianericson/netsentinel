"""
HomePage — introductory landing page shown in Home mode.

Hero card (network grade), three mini metric cards (speed / stability / devices),
and a recent-alerts strip.

Architecture rules observed:
  • All colours from ui.styles — no hardcoded hex values.
  • No blocking I/O. Pure display widget; all data arrives via public slots.
  • Outer scroll area so the content is never clipped on small windows.
"""
from __future__ import annotations

import datetime

from PyQt6.QtCore import Qt, QSettings, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT,
    AMBER,
    BG_CARD,
    BG_DARK,
    BG_HOVER,
    BORDER,
    CARD_RADIUS,
    GREEN,
    PRO_WARN_BG,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    UPDATE_BAR_BG,
    UPDATE_BAR_BORDER,
    UPDATE_BAR_FG,
)
import ui.styles as _styles

try:
    from ui.pages.discover_page import _FEATURES as _GUIDE_FEATURES
except ImportError:
    _GUIDE_FEATURES: list = []


class HomePage(QWidget):
    """Simple landing page for new / Home-mode users."""

    #: Emitted when a mini-card is clicked; carries the target page label string.
    navigate_to = pyqtSignal(str)
    #: Emitted when the user clicks "Start Monitoring" on the stability card.
    start_monitoring_requested = pyqtSignal()
    #: Emitted when the user clicks "Investigate →" on a live challenge suggestion.
    investigate_live_requested = pyqtSignal()
    #: Emitted when the user clicks an alert row; carries the raw alert object.
    alert_view_requested = pyqtSignal(object)

    # ── _MiniCard ─────────────────────────────────────────────────────────────

    class _MiniCard(QFrame):
        """One of the three top-line metric summary cards."""

        #: Emitted when the card is clicked.
        clicked = pyqtSignal()

        def mousePressEvent(self, event) -> None:  # type: ignore[override]
            self.clicked.emit()
            super().mousePressEvent(event)

        def __init__(self, icon: str, title: str, val: str, sub: str,
                     parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setMinimumHeight(100)
            self.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setStyleSheet(
                f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
                f" border-radius:{CARD_RADIUS}; }}"
            )
            lay = QVBoxLayout(self)
            lay.setContentsMargins(12, 8, 12, 8)
            lay.setSpacing(2)

            self._icon_lbl = QLabel(icon)
            self._icon_lbl.setStyleSheet(
                f"font-size:13px; color:{TEXT_PRIMARY};"
                " background:transparent; border:none;"
            )
            self._title_lbl = QLabel(title)
            self._title_lbl.setStyleSheet(
                f"font-size:11px; font-weight:bold; color:{TEXT_PRIMARY};"
                " background:transparent; border:none;"
            )
            self._val_lbl = QLabel(val)
            self._val_lbl.setStyleSheet(
                f"font-size:20px; font-weight:bold; color:{TEXT_PRIMARY};"
                " background:transparent; border:none;"
            )
            self._sub_lbl = QLabel(sub)
            self._sub_lbl.setStyleSheet(
                f"font-size:10px; color:{TEXT_SECONDARY};"
                " background:transparent; border:none;"
            )

            self._dot_lbl = QLabel("\u25cf")
            self._dot_lbl.setStyleSheet(
                f"font-size:8px; color:{GREEN}; background:transparent; border:none;"
            )
            self._dot_lbl.setFixedWidth(12)
            self._status_lbl = QLabel("")
            self._status_lbl.setStyleSheet(
                f"font-size:10px; color:{TEXT_SECONDARY};"
                " background:transparent; border:none;"
            )
            status_row = QHBoxLayout()
            status_row.setContentsMargins(0, 0, 0, 0)
            status_row.setSpacing(3)
            status_row.addWidget(self._dot_lbl)
            status_row.addWidget(self._status_lbl)
            status_row.addStretch()

            lay.addWidget(self._icon_lbl)
            lay.addWidget(self._title_lbl)
            lay.addWidget(self._val_lbl)
            lay.addWidget(self._sub_lbl)
            lay.addLayout(status_row)

        def set_value(self, val: str, sub: str, status: str, colour: str) -> None:
            """Update the card's main value, subtitle, status dot and label."""
            self._val_lbl.setText(val)
            self._val_lbl.setStyleSheet(
                f"font-size:20px; font-weight:bold; color:{colour};"
                " background:transparent; border:none;"
            )
            self._sub_lbl.setText(sub)
            self._dot_lbl.setStyleSheet(
                f"font-size:8px; color:{colour};"
                " background:transparent; border:none;"
            )
            self._status_lbl.setText(status)

    # ── _AlertRow ─────────────────────────────────────────────────────────────

    class _AlertRow(QFrame):
        """Single row in the recent-alerts strip."""

        clicked = pyqtSignal(object)  # carries the raw alert object

        def __init__(self, colour: str, msg: str, time_str: str,
                     alert: object = None,
                     parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self._alert = alert
            self.setFixedHeight(28)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setStyleSheet("QFrame { background:transparent; border:none; }")
            lay = QHBoxLayout(self)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(6)

            dot = QLabel("\u25cf")
            dot.setFixedWidth(12)
            dot.setStyleSheet(
                f"font-size:8px; color:{colour};"
                " background:transparent; border:none;"
            )
            msg_lbl = QLabel(msg)
            msg_lbl.setStyleSheet(
                f"font-size:11px; color:{TEXT_PRIMARY};"
                " background:transparent; border:none;"
            )
            msg_lbl.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            time_lbl = QLabel(time_str)
            time_lbl.setStyleSheet(
                f"font-size:10px; color:{TEXT_SECONDARY};"
                " background:transparent; border:none;"
            )
            time_lbl.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            lay.addWidget(dot)
            lay.addWidget(msg_lbl, 1)
            lay.addWidget(time_lbl)

        def mousePressEvent(self, event) -> None:  # type: ignore[override]
            self.clicked.emit(self._alert)
            super().mousePressEvent(event)

    # ── Constructor ───────────────────────────────────────────────────────────

    def __init__(self, store=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._alert_count = 0
        self._device_count: int = 0
        self._signals_connected: bool = False
        self._first_run_mode: bool = False
        self._recurring_mode: bool = False
        self._current_grade: str = ""
        self._last_scan_ts: "datetime.datetime | None" = None
        self._sheet_action_target: str = "Notifications"
        self._dashboard_url = "http://localhost:8765/dashboard"
        self._setup_ui()
        if self._store is not None:
            from PyQt6.QtCore import QTimer
            # Use a parented QTimer so it is automatically destroyed with this
            # widget.  QTimer.singleShot(0, slot) creates an un-parented timer
            # that can fire after the widget's C++ object has been deleted,
            # corrupting the heap on Linux (SIGABRT ~30 tests later).
            _t = QTimer(self)
            _t.setSingleShot(True)
            _t.timeout.connect(self._preload_from_store)
            _t.start(0)

    # ── Theme nudge banner ────────────────────────────────────────────────────

    def _build_theme_banner(self) -> "QFrame | None":
        qs = QSettings("NetSentinel", "NetSentinel")
        if qs.value("ui/theme_nudge_dismissed", False, type=bool):
            return None

        active = _styles.get_active_theme_name()

        banner = QFrame()
        banner.setStyleSheet(
            f"QFrame {{ background:{UPDATE_BAR_BG}; border-bottom:1px solid {UPDATE_BAR_BORDER}; }}"
        )
        row = QHBoxLayout(banner)
        row.setContentsMargins(14, 6, 10, 6)
        row.setSpacing(8)

        lbl = QLabel("Choose a theme:")
        lbl.setStyleSheet(
            f"font-size:11px; color:{UPDATE_BAR_FG}; background:transparent; border:none;"
        )
        row.addWidget(lbl)

        _THEMES = [
            ("Arctic Clean",  "☀  Light"),
            ("Midnight Pro",  "🌙  Dark"),
            ("Obsidian Neon", "✦  Neon"),
        ]

        def _dismiss(save_theme: str | None = None) -> None:
            if save_theme:
                _styles.set_active_theme_name(save_theme)
                lbl.setText(f"Theme '{save_theme}' saved — restart NetSentinel to apply.")
                for b in _btn_refs:
                    b.setEnabled(False)
                close_btn.setVisible(False)
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(2500, banner.hide)
            else:
                banner.hide()
            QSettings("NetSentinel", "NetSentinel").setValue("ui/theme_nudge_dismissed", True)

        _btn_refs: list[QPushButton] = []
        for theme_name, theme_label in _THEMES:
            btn = QPushButton(theme_label)
            btn.setFixedHeight(24)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if theme_name == active:
                btn.setStyleSheet(
                    f"QPushButton {{ background:{ACCENT}; color:#ffffff;"
                    f" border:none; border-radius:3px; font-size:11px; padding:0 10px; }}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background:transparent; color:{UPDATE_BAR_FG};"
                    f" border:1px solid {UPDATE_BAR_BORDER}; border-radius:3px;"
                    f" font-size:11px; padding:0 10px; }}"
                    f"QPushButton:hover {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
                )
                _name = theme_name
                btn.clicked.connect(lambda _checked, n=_name: _dismiss(n))
            _btn_refs.append(btn)
            row.addWidget(btn)

        row.addStretch()

        close_btn = QPushButton("×")
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Dismiss")
        close_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none;"
            f" font-size:15px; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
        )
        close_btn.clicked.connect(lambda: _dismiss(None))
        row.addWidget(close_btn)

        return banner

    # ── UI build ──────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setObjectName("homePageRoot")
        self.setStyleSheet(f"QWidget#homePageRoot {{ background:{BG_DARK}; }}")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Theme nudge banner (one-time, dismissed via QSettings) ───────────
        _banner = self._build_theme_banner()
        if _banner is not None:
            outer.addWidget(_banner)
        # ─────────────────────────────────────────────────────────────────────

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border:none; background:transparent; }")

        inner = QWidget()
        inner.setObjectName("homepageInner")
        inner.setStyleSheet(f"QWidget#homepageInner {{ background:{BG_DARK}; }}")
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        lay = QVBoxLayout(inner)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        # ── Browser dashboard strip (visible when API enabled + not dismissed) ─
        self._dashboard_strip = QFrame()
        self._dashboard_strip.setStyleSheet(
            f"QFrame {{ background:{UPDATE_BAR_BG}; border:1px solid {UPDATE_BAR_BORDER};"
            f" border-radius:4px; }}"
        )
        self._dashboard_strip.setVisible(False)
        _ds_lay = QHBoxLayout(self._dashboard_strip)
        _ds_lay.setContentsMargins(12, 5, 8, 5)
        _ds_lay.setSpacing(8)
        _ds_icon = QLabel("🌐")
        _ds_icon.setFixedWidth(18)
        _ds_icon.setStyleSheet(
            f"font-size:12px; color:{UPDATE_BAR_FG}; background:transparent; border:none;"
        )
        self._ds_text = QLabel("")
        self._ds_text.setStyleSheet(
            f"font-size:11px; color:{UPDATE_BAR_FG}; background:transparent; border:none;"
        )
        _ds_open = QPushButton("Open ↗")
        _ds_open.setFixedHeight(24)
        _ds_open.setCursor(Qt.CursorShape.PointingHandCursor)
        _ds_open.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#ffffff; border:none;"
            f" border-radius:3px; font-size:11px; padding:0 8px; }}"
            f"QPushButton:hover {{ background:#1a6fc4; }}"
        )
        _ds_open.clicked.connect(self._open_dashboard)
        _ds_dismiss = QPushButton("×")
        _ds_dismiss.setFixedSize(20, 20)
        _ds_dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        _ds_dismiss.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{UPDATE_BAR_FG}; border:none;"
            f" font-size:14px; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
        )
        _ds_dismiss.clicked.connect(self._dismiss_dashboard_strip)
        _ds_lay.addWidget(_ds_icon)
        _ds_lay.addWidget(self._ds_text, 1)
        _ds_lay.addWidget(_ds_open)
        _ds_lay.addWidget(_ds_dismiss)
        lay.addWidget(self._dashboard_strip)

        # ── Since you were last here (hidden until data loaded) ───────────────
        self._last_visit_card = QFrame()
        self._last_visit_card.setStyleSheet(
            f"QFrame {{ background:{PRO_WARN_BG}; border:1px solid {UPDATE_BAR_BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        self._last_visit_card.setVisible(False)
        lv_lay = QHBoxLayout(self._last_visit_card)
        lv_lay.setContentsMargins(12, 8, 12, 8)
        lv_lay.setSpacing(10)
        _lv_icon = QLabel("◷")
        _lv_icon.setFixedWidth(18)
        _lv_icon.setStyleSheet(
            f"font-size:13px; color:{UPDATE_BAR_FG}; background:transparent; border:none;"
        )
        self._lv_text = QLabel("")
        self._lv_text.setWordWrap(True)
        self._lv_text.setStyleSheet(
            f"font-size:11px; color:{UPDATE_BAR_FG}; background:transparent; border:none;"
        )
        lv_lay.addWidget(_lv_icon)
        lv_lay.addWidget(self._lv_text, 1)
        lay.addWidget(self._last_visit_card)

        # ── Recurring-user top section (hidden until conditions met) ──────────
        self._recurring_section = QFrame()
        self._recurring_section.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        self._recurring_section.setVisible(False)
        _rec_outer = QVBoxLayout(self._recurring_section)
        _rec_outer.setContentsMargins(14, 10, 14, 12)
        _rec_outer.setSpacing(8)

        _rec_mon_hdr = QLabel("MONITORING STATUS")
        _rec_mon_hdr.setStyleSheet(
            f"font-size:10px; font-weight:700; color:{TEXT_SECONDARY};"
            " background:transparent; border:none; letter-spacing:1.5px;"
        )
        _rec_outer.addWidget(_rec_mon_hdr)

        # Pill row — separate instances synced by set_monitor_pills()
        _rec_pills_row = QHBoxLayout()
        _rec_pills_row.setSpacing(6)
        _rec_pills_row.setContentsMargins(0, 0, 0, 0)

        def _rec_pill(label: str, target: str) -> QPushButton:
            b = QPushButton(f"○  {label}")
            b.setFixedHeight(22)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton {{ background:{BG_HOVER}; color:{TEXT_MUTED}; font-size:10px;"
                f" border:1px solid {BORDER}; border-radius:11px; padding:1px 10px; }}"
                f"QPushButton:hover {{ border-color:{ACCENT}; }}"
            )
            b.clicked.connect(lambda _=False, t=target: self.navigate_to.emit(t))
            return b

        self._rec_pill_arp    = _rec_pill("ARP Watch",       "ARP Spoof Watch")
        self._rec_pill_dhcp   = _rec_pill("DHCP Watch",      "DHCP Rogue Monitor")
        self._rec_pill_storm  = _rec_pill("Broadcast Storm", "Broadcast Storm")
        self._rec_pill_logger = _rec_pill("Network Logger",  "Logs")
        for _rp in (self._rec_pill_arp, self._rec_pill_dhcp,
                    self._rec_pill_storm, self._rec_pill_logger):
            _rec_pills_row.addWidget(_rp)
        _rec_pills_row.addStretch()
        _rec_outer.addLayout(_rec_pills_row)

        # Grade + last scan + rescan row
        _rec_status_row = QHBoxLayout()
        _rec_status_row.setSpacing(12)
        _rec_status_row.setContentsMargins(0, 0, 0, 0)
        self._rec_grade_lbl = QLabel("Network Grade: –")
        self._rec_grade_lbl.setStyleSheet(
            f"font-size:11px; font-weight:600; color:{TEXT_SECONDARY};"
            " background:transparent; border:none;"
        )
        self._rec_scan_time_lbl = QLabel("Last scan: –")
        self._rec_scan_time_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )
        self._btn_rescan_compact = QPushButton("▶  Rescan")
        self._btn_rescan_compact.setFixedHeight(26)
        self._btn_rescan_compact.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_rescan_compact.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{ACCENT}; border:1px solid {ACCENT}44;"
            f" border-radius:4px; font-size:11px; font-weight:600; padding:0 10px; }}"
            f"QPushButton:hover {{ background:{ACCENT}22; border-color:{ACCENT}; }}"
        )
        _rec_status_row.addWidget(self._rec_grade_lbl)
        _rec_status_row.addWidget(self._rec_scan_time_lbl)
        _rec_status_row.addStretch()
        _rec_status_row.addWidget(self._btn_rescan_compact)
        _rec_outer.addLayout(_rec_status_row)

        lay.addWidget(self._recurring_section)

        # ── Hero card ─────────────────────────────────────────────────────────
        hero = QFrame()
        hero.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        hero_lay = QHBoxLayout(hero)
        hero_lay.setContentsMargins(16, 16, 16, 16)
        hero_lay.setSpacing(16)

        self._grade_circle = QLabel("\u2013")
        self._grade_circle.setFixedSize(68, 68)
        self._grade_circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._grade_circle.setStyleSheet(
            f"font-size:28px; font-weight:bold; color:{TEXT_SECONDARY};"
            f" border:3px solid {BORDER}; border-radius:34px;"
            f" background:{BG_CARD};"
        )
        hero_lay.addWidget(self._grade_circle)

        right = QVBoxLayout()
        right.setSpacing(4)

        self._hero_title = QLabel("What's on your network?")
        self._hero_title.setStyleSheet(
            f"font-size:14px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        self._hero_sub = QLabel(
            "Discover devices · check stability · detect threats"
        )
        self._hero_sub.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY};"
            " background:transparent; border:none;"
        )
        self._hero_sub.setWordWrap(True)

        # Primary + secondary action row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._btn_scan = QPushButton("\u25b6  Scan Network")
        self._btn_scan.setObjectName("btnScanHero")
        self._btn_diagnose = QPushButton("\u25c6  What\u2019s Wrong?")
        self._btn_diagnose.setToolTip(
            "Pick a symptom \u2014 slow, dropping, or no connection \u2014 and get a plain-English diagnosis"
        )
        self._btn_diagnose.setStyleSheet(
            f"QPushButton {{ min-height: 34px; font-size: 12px; font-weight: 600;"
            f" background: {ACCENT}; color: #ffffff;"
            f" border: none; border-radius: 4px; padding: 0 14px; }}"
            f"QPushButton:hover {{ background: #005A9E; }}"
        )
        btn_row.addWidget(self._btn_scan)
        btn_row.addWidget(self._btn_diagnose)
        btn_row.addStretch()

        # Tertiary follow-up action \u2014 visually separated, link-style
        isp_row = QHBoxLayout()
        isp_row.setSpacing(0)
        self._btn_isp = QPushButton("\ud83d\udcca  Network Health Report")
        self._btn_isp.setToolTip("Generate a Network Health Report \u2014 great for ISP support tickets")
        self._btn_isp.setStyleSheet(
            f"QPushButton {{ min-height: 22px; font-size: 11px; font-weight: 500;"
            f" background: transparent; color: {TEXT_MUTED};"
            f" border: none; padding: 0; text-decoration: underline; }}"
            f"QPushButton:hover {{ color: {ACCENT}; }}"
        )
        isp_row.addWidget(self._btn_isp)
        isp_row.addStretch()

        right.addWidget(self._hero_title)
        right.addWidget(self._hero_sub)
        right.addSpacing(4)
        right.addLayout(btn_row)
        right.addLayout(isp_row)
        hero_lay.addLayout(right, 1)
        lay.addWidget(hero)

        # ── Feature search bar ────────────────────────────────────────────────
        search_card = QFrame()
        search_card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        search_outer = QVBoxLayout(search_card)
        search_outer.setContentsMargins(10, 8, 10, 8)
        search_outer.setSpacing(6)

        self._home_search = QLineEdit()
        self._home_search.setPlaceholderText(
            "Search features — try 'wifi', 'arp', 'heatmap', 'dns'…"
        )
        self._home_search.setFixedHeight(30)
        self._home_search.setStyleSheet(
            f"QLineEdit {{ background:{BG_DARK}; border:1px solid {BORDER};"
            f" border-radius:4px; color:{TEXT_PRIMARY}; font-size:11px; padding:0 8px; }}"
            f"QLineEdit:focus {{ border-color:{ACCENT}; }}"
        )
        self._home_search.textChanged.connect(self._apply_home_search)
        search_outer.addWidget(self._home_search)

        self._search_results = QFrame()
        self._search_results.setStyleSheet("QFrame { background:transparent; border:none; }")
        self._search_results.setVisible(False)
        self._search_results_inner = QVBoxLayout(self._search_results)
        self._search_results_inner.setContentsMargins(0, 2, 0, 0)
        self._search_results_inner.setSpacing(3)
        search_outer.addWidget(self._search_results)

        lay.addWidget(search_card)

        # ── Post-scan summary sheet (NUX-2, one-time) ─────────────────────────
        self._post_scan_sheet = QFrame()
        self._post_scan_sheet.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {ACCENT}44;"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        self._post_scan_sheet.setVisible(False)
        _sheet_lay = QVBoxLayout(self._post_scan_sheet)
        _sheet_lay.setContentsMargins(14, 10, 14, 10)
        _sheet_lay.setSpacing(6)

        _sheet_hdr = QHBoxLayout()
        _sheet_hdr.setSpacing(0)
        _sheet_title_lbl = QLabel("Your network at a glance")
        _sheet_title_lbl.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        _sheet_hdr.addWidget(_sheet_title_lbl)
        _sheet_hdr.addStretch()
        _sheet_x = QPushButton("×")
        _sheet_x.setFixedSize(20, 20)
        _sheet_x.setCursor(Qt.CursorShape.PointingHandCursor)
        _sheet_x.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none;"
            f" font-size:14px; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
        )
        _sheet_x.clicked.connect(self._dismiss_post_scan_sheet)
        _sheet_hdr.addWidget(_sheet_x)
        _sheet_lay.addLayout(_sheet_hdr)

        self._sheet_stats_lbl = QLabel("")
        self._sheet_stats_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        _sheet_lay.addWidget(self._sheet_stats_lbl)

        _sheet_cta = QHBoxLayout()
        _sheet_cta.setSpacing(16)
        self._sheet_grade_btn = QPushButton("Run a Network Grade →")
        self._sheet_grade_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sheet_grade_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{ACCENT}; border:none;"
            f" font-size:11px; padding:0; }}"
            f"QPushButton:hover {{ color:#1a6fc4; text-decoration:underline; }}"
        )
        self._sheet_grade_btn.clicked.connect(
            lambda: self.navigate_to.emit("Network Grade")
        )
        _sheet_cta.addWidget(self._sheet_grade_btn)
        self._sheet_action_btn = QPushButton("Set up notifications →")
        self._sheet_action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sheet_action_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{ACCENT}; border:none;"
            f" font-size:11px; padding:0; }}"
            f"QPushButton:hover {{ color:#1a6fc4; text-decoration:underline; }}"
        )
        self._sheet_action_btn.clicked.connect(
            lambda: self.navigate_to.emit(self._sheet_action_target)
        )
        _sheet_cta.addWidget(self._sheet_action_btn)
        _sheet_cta.addStretch()
        _sheet_lay.addLayout(_sheet_cta)
        lay.addWidget(self._post_scan_sheet)

        # ── "Three things" section label ──────────────────────────────────────
        self._sec1_lbl = QLabel("THE THREE THINGS THAT MATTER")
        self._sec1_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
            " border:none; padding-top:4px; letter-spacing:1px;"
        )
        lay.addWidget(self._sec1_lbl)

        # ── Mini-card row — three equal-width columns ────────────────────────
        self._mini_cards_widget = QWidget()
        self._mini_cards_widget.setStyleSheet("background:transparent;")
        card_row = QHBoxLayout(self._mini_cards_widget)
        card_row.setContentsMargins(0, 0, 0, 0)
        card_row.setSpacing(8)
        self._speed_card     = HomePage._MiniCard("\u26a1", "Speed",     "\u2013", "\u2013")
        self._stability_card = HomePage._MiniCard("\u25ce", "Stability", "\u2013", "\u2013")
        self._devices_card   = HomePage._MiniCard("\u2295", "Devices",   "\u2013", "\u2013")
        for _card in (self._speed_card, self._stability_card, self._devices_card):
            card_row.addWidget(_card, 1)  # stretch=1 → equal width
        self._speed_card.clicked.connect(
            lambda: self.navigate_to.emit("Speed Test"))
        self._stability_card.clicked.connect(
            lambda: self.navigate_to.emit("DNS & Stability"))
        self._devices_card.clicked.connect(
            lambda: self.navigate_to.emit("Devices"))
        lay.addWidget(self._mini_cards_widget)

        # ── Monitoring status pills (NUX-3) ───────────────────────────────────
        self._monitoring_pills_row = QWidget()
        self._monitoring_pills_row.setStyleSheet("background:transparent;")
        _pills_lay = QHBoxLayout(self._monitoring_pills_row)
        _pills_lay.setContentsMargins(0, 4, 0, 0)
        _pills_lay.setSpacing(6)

        _pills_hdr = QLabel("MONITORING")
        _pills_hdr.setStyleSheet(
            f"font-size:9px; color:{TEXT_SECONDARY}; background:transparent;"
            " border:none; letter-spacing:1px;"
        )
        _pills_lay.addWidget(_pills_hdr)
        _pills_lay.addSpacing(4)

        def _pill(label: str, target: str) -> QPushButton:
            b = QPushButton(f"○  {label}")
            b.setFixedHeight(22)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton {{ background:{BG_CARD}; color:{TEXT_MUTED}; font-size:10px;"
                f" border:1px solid {BORDER}; border-radius:11px; padding:1px 10px; }}"
                f"QPushButton:hover {{ background:{BG_HOVER}; }}"
            )
            b.clicked.connect(lambda _=False, t=target: self.navigate_to.emit(t))
            return b

        self._pill_arp    = _pill("ARP Watch",       "ARP Spoof Watch")
        self._pill_dhcp   = _pill("DHCP Watch",      "DHCP Rogue Monitor")
        self._pill_storm  = _pill("Broadcast Storm", "Broadcast Storm")
        self._pill_logger = _pill("Network Logger",  "Logs")
        for _p in (self._pill_arp, self._pill_dhcp, self._pill_storm, self._pill_logger):
            _pills_lay.addWidget(_p)
        _pills_lay.addStretch()
        lay.addWidget(self._monitoring_pills_row)

        self._monitoring_nudge = QLabel(
            "Monitoring is off — turn it on in 10 seconds →"
        )
        self._monitoring_nudge.setVisible(False)
        self._monitoring_nudge.setCursor(Qt.CursorShape.PointingHandCursor)
        self._monitoring_nudge.setStyleSheet(
            f"font-size:11px; color:{AMBER}; background:transparent;"
            " border:none; padding-top:2px;"
        )
        self._monitoring_nudge.mousePressEvent = (  # type: ignore[method-assign]
            lambda _e: self._scroll_to_setup_card()
        )
        lay.addWidget(self._monitoring_nudge)

        # ── Stability monitoring card ─────────────────────────────────────────
        self._sec_mon_lbl = QLabel("STABILITY MONITORING")
        self._sec_mon_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
            " border:none; padding-top:4px; letter-spacing:1px;"
        )
        lay.addWidget(self._sec_mon_lbl)

        self._mon_card = QFrame()
        self._mon_card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        mon_lay = QHBoxLayout(self._mon_card)
        mon_lay.setContentsMargins(14, 10, 14, 10)
        mon_lay.setSpacing(10)

        self._mon_dot = QLabel("●")
        self._mon_dot.setFixedWidth(12)
        self._mon_dot.setStyleSheet(
            f"font-size:9px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        self._mon_status_lbl = QLabel(
            "Not running — start to log connection stability over time."
        )
        self._mon_status_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        self._mon_status_lbl.setWordWrap(True)

        self._btn_mon_start = QPushButton("Start Monitoring")
        self._btn_mon_start.setFixedHeight(28)
        self._btn_mon_start.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#ffffff; border:none;"
            f" border-radius:4px; font-size:11px; font-weight:600; padding:0 12px; }}"
            f"QPushButton:hover {{ background:#1a6fc4; }}"
        )
        self._btn_mon_start.clicked.connect(self.start_monitoring_requested)

        self._btn_mon_view = QPushButton("View Log →")
        self._btn_mon_view.setFlat(True)
        self._btn_mon_view.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_mon_view.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px;"
            f" background:transparent; border:none; padding:0; }}"
            f"QPushButton:hover {{ color:#005A9E; }}"
        )
        self._btn_mon_view.clicked.connect(lambda: self.navigate_to.emit("Logs"))

        mon_lay.addWidget(self._mon_dot)
        mon_lay.addWidget(self._mon_status_lbl, 1)
        mon_lay.addWidget(self._btn_mon_start)
        mon_lay.addWidget(self._btn_mon_view)
        lay.addWidget(self._mon_card)

        # ── Post-scan results strip (hidden until first scan completes) ────────
        self._results_strip = QFrame()
        self._results_strip.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER}; }}"
        )
        self._results_strip.setVisible(False)
        _strip_lay = QVBoxLayout(self._results_strip)
        _strip_lay.setContentsMargins(12, 8, 12, 8)
        _strip_lay.setSpacing(6)

        _strip_hdr = QLabel("EXPLORE YOUR RESULTS")
        _strip_hdr.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
            " border:none; letter-spacing:1px;"
        )
        _strip_lay.addWidget(_strip_hdr)

        def _result_row(default_text: str, btn_label: str, target: str):
            rw = QWidget()
            rw.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(rw)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(8)
            dot = QLabel("●")
            dot.setFixedWidth(12)
            dot.setStyleSheet(
                f"font-size:8px; color:{TEXT_SECONDARY};"
                " background:transparent; border:none;"
            )
            lbl = QLabel(default_text)
            lbl.setStyleSheet(
                f"font-size:11px; color:{TEXT_PRIMARY};"
                " background:transparent; border:none;"
            )
            btn = QPushButton(btn_label)
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ color:{ACCENT}; font-size:11px;"
                f" background:transparent; border:none; padding:0; }}"
                f"QPushButton:hover {{ color:#005A9E; }}"
            )
            btn.clicked.connect(lambda: self.navigate_to.emit(target))
            rl.addWidget(dot)
            rl.addWidget(lbl, 1)
            rl.addWidget(btn)
            return rw, lbl, dot

        _dev_row, self._res_devices_lbl, self._res_devices_dot = \
            _result_row("–", "View Devices →", "Devices")
        _conn_row, self._res_conn_lbl, self._res_conn_dot = \
            _result_row("–", "View Connection →", "DNS & Stability")
        _sec_row, self._res_security_lbl, self._res_security_dot = \
            _result_row("–", "View Overview →", "Overview")

        _strip_lay.addWidget(_dev_row)
        _strip_lay.addWidget(_conn_row)
        _strip_lay.addWidget(_sec_row)
        lay.addWidget(self._results_strip)

        # ── Suggested next steps (hidden until computed) ──────────────────────
        self._suggestions_sec = QLabel("WHAT TO DO NEXT")
        self._suggestions_sec.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
            " border:none; padding-top:4px; letter-spacing:1px;"
        )
        self._suggestions_sec.setVisible(False)
        lay.addWidget(self._suggestions_sec)

        self._suggestions_card = QFrame()
        self._suggestions_card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        self._suggestions_card.setVisible(False)
        self._suggestions_inner = QVBoxLayout(self._suggestions_card)
        self._suggestions_inner.setContentsMargins(12, 8, 12, 8)
        self._suggestions_inner.setSpacing(4)
        lay.addWidget(self._suggestions_card)

        # ── Recent alerts section label (+ "View all →" in recurring mode) ────
        self._alerts_hdr_row = QWidget()
        self._alerts_hdr_row.setStyleSheet("background:transparent;")
        _ahr_lay = QHBoxLayout(self._alerts_hdr_row)
        _ahr_lay.setContentsMargins(0, 4, 0, 0)
        _ahr_lay.setSpacing(0)
        self._sec2_lbl = QLabel("RECENT ALERTS")
        self._sec2_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
            " border:none; letter-spacing:1px;"
        )
        self._btn_view_all_alerts = QPushButton("View all →")
        self._btn_view_all_alerts.setFlat(True)
        self._btn_view_all_alerts.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_view_all_alerts.setVisible(False)
        self._btn_view_all_alerts.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:10px; background:transparent;"
            f" border:none; padding:0; }}"
            f"QPushButton:hover {{ color:#1a6fc4; }}"
        )
        self._btn_view_all_alerts.clicked.connect(
            lambda: self.navigate_to.emit("Notifications")
        )
        _ahr_lay.addWidget(self._sec2_lbl)
        _ahr_lay.addStretch()
        _ahr_lay.addWidget(self._btn_view_all_alerts)
        lay.addWidget(self._alerts_hdr_row)

        # ── Alert card ────────────────────────────────────────────────────────
        self._alert_card = QFrame()
        self._alert_card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        self._alert_inner = QVBoxLayout(self._alert_card)
        self._alert_inner.setContentsMargins(12, 8, 12, 8)
        self._alert_inner.setSpacing(2)

        self._no_alerts_lbl = QLabel("No alerts \u2014 configure alerts in Settings to get notified")
        self._no_alerts_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY};"
            " background:transparent; border:none;"
        )
        self._alert_inner.addWidget(self._no_alerts_lbl)
        # Permanent footer — always visible; text changes to "No other alerts" once rows appear
        self._no_other_alerts_lbl = QLabel()
        self._no_other_alerts_lbl.setVisible(False)
        self._no_other_alerts_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY};"
            " background:transparent; border:none;"
        )
        self._alert_inner.addWidget(self._no_other_alerts_lbl)
        lay.addWidget(self._alert_card)

        # ── Setup checklist card (NUX-4) ──────────────────────────────────────
        self._setup_card = QFrame()
        self._setup_card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        _sc_outer = QVBoxLayout(self._setup_card)
        _sc_outer.setContentsMargins(12, 8, 12, 10)
        _sc_outer.setSpacing(0)

        # Header row — shows "Setup" or "✓ Setup complete" chip; clickable to collapse
        self._setup_collapsed = False
        _sc_hdr_row = QHBoxLayout()
        _sc_hdr_row.setSpacing(8)
        self._setup_hdr_lbl = QLabel("SETUP CHECKLIST")
        self._setup_hdr_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
            " border:none; letter-spacing:1px;"
        )
        self._setup_progress_lbl = QLabel("0/5 done")
        self._setup_progress_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )
        _sc_collapse_btn = QPushButton("▼")
        _sc_collapse_btn.setFixedSize(18, 18)
        _sc_collapse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _sc_collapse_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none;"
            f" font-size:10px; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
        )
        self._setup_collapse_btn = _sc_collapse_btn
        _sc_collapse_btn.clicked.connect(self._setup_toggle_collapse)
        _sc_hdr_row.addWidget(self._setup_hdr_lbl)
        _sc_hdr_row.addWidget(self._setup_progress_lbl)
        _sc_hdr_row.addStretch()
        _sc_hdr_row.addWidget(_sc_collapse_btn)
        _sc_outer.addLayout(_sc_hdr_row)

        # Body — checklist rows
        self._setup_body = QWidget()
        self._setup_body.setStyleSheet("background:transparent;")
        _sc_body_lay = QVBoxLayout(self._setup_body)
        _sc_body_lay.setContentsMargins(0, 6, 0, 0)
        _sc_body_lay.setSpacing(5)

        _setup_steps = [
            ("Run your first scan",        "Devices"),
            ("Turn on ARP Spoof Watch",    "ARP Spoof Watch"),
            ("Add a notification channel", "Notifications"),
            ("Enable at least one alert rule", "Notifications"),
            ("Run a Network Grade",        "Network Grade"),
        ]
        self._setup_check_lbls: list[QLabel] = []
        for title, target in _setup_steps:
            _row = QWidget()
            _row.setStyleSheet("background:transparent;")
            _rl = QHBoxLayout(_row)
            _rl.setContentsMargins(0, 0, 0, 0)
            _rl.setSpacing(8)
            _chk = QLabel("○")
            _chk.setFixedWidth(14)
            _chk.setStyleSheet(
                f"font-size:12px; color:{TEXT_MUTED}; background:transparent; border:none;"
            )
            self._setup_check_lbls.append(_chk)
            _step_lbl = QLabel(title)
            _step_lbl.setStyleSheet(
                f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
            )
            _nav_btn = QPushButton("→")
            _nav_btn.setFlat(True)
            _nav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            _nav_btn.setStyleSheet(
                f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
                f" border:none; padding:0; }}"
                f"QPushButton:hover {{ color:#1a6fc4; }}"
            )
            _nav_btn.clicked.connect(lambda _=False, t=target: self.navigate_to.emit(t))
            _rl.addWidget(_chk)
            _rl.addWidget(_step_lbl, 1)
            _rl.addWidget(_nav_btn)
            _sc_body_lay.addWidget(_row)

        _sc_outer.addWidget(self._setup_body)
        lay.addWidget(self._setup_card)

        # ── Quick tips card (dismissible; hidden once user dismisses) ──────────
        self._tips_card = QFrame()
        self._tips_card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        self._tips_card.setVisible(False)
        _tips_lay = QVBoxLayout(self._tips_card)
        _tips_lay.setContentsMargins(12, 8, 12, 8)
        _tips_lay.setSpacing(3)

        _tips_hdr_row = QHBoxLayout()
        _tips_hdr_row.setContentsMargins(0, 0, 0, 0)
        _tips_hdr_row.setSpacing(0)
        _tips_hdr = QLabel("QUICK TIPS")
        _tips_hdr.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
            " border:none; letter-spacing:1px;"
        )
        _tips_x = QPushButton("×")
        _tips_x.setFixedSize(18, 18)
        _tips_x.setCursor(Qt.CursorShape.PointingHandCursor)
        _tips_x.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_SECONDARY}; border:none;"
            f" font-size:13px; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
        )
        _tips_x.clicked.connect(self._dismiss_tips)
        _tips_hdr_row.addWidget(_tips_hdr)
        _tips_hdr_row.addStretch()
        _tips_hdr_row.addWidget(_tips_x)
        _tips_lay.addLayout(_tips_hdr_row)

        def _tip_row(icon: str, text: str) -> QWidget:
            w = QWidget()
            w.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(w)
            rl.setContentsMargins(0, 2, 0, 2)
            rl.setSpacing(8)
            ic = QLabel(icon)
            ic.setFixedWidth(16)
            ic.setStyleSheet("font-size:12px; background:transparent; border:none;")
            lb = QLabel(text)
            lb.setStyleSheet(
                f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
            )
            lb.setWordWrap(True)
            rl.addWidget(ic)
            rl.addWidget(lb, 1)
            return w

        _tips_lay.addWidget(_tip_row("⌨", "Press  Ctrl+K  to open the command palette — search any page instantly."))
        _tips_lay.addWidget(_tip_row("📌", "Right-click any nav item to pin it to the sidebar for quick access."))
        _tips_lay.addWidget(_tip_row("⚙", "Right-click a device row for quick actions: block, How to Fix, history."))
        self._tip_row_rest_api = _tip_row("🌐", "Enable the REST API in  Settings → REST API  for a live browser dashboard at localhost:8765/dashboard.")
        _tips_lay.addWidget(self._tip_row_rest_api)

        lay.addWidget(self._tips_card)
        lay.addStretch()

    # ── Feature search ────────────────────────────────────────────────────────

    def _apply_home_search(self, text: str) -> None:
        while self._search_results_inner.count():
            item = self._search_results_inner.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        q = text.strip().lower()
        if not q:
            self._search_results.setVisible(False)
            return

        filtered = [
            f for f in _GUIDE_FEATURES
            if q in f["name"].lower()
            or q in f["desc"].lower()
            or q in f.get("group", "").lower()
            or q in (f.get("page") or "").lower()
            or any(q in t.lower() for t in f.get("tags", []))
        ][:6]

        if not filtered:
            lbl = QLabel(f'No features matching "{text}"')
            lbl.setStyleSheet(
                f"font-size:11px; color:{TEXT_SECONDARY};"
                " background:transparent; border:none;"
            )
            self._search_results_inner.addWidget(lbl)
        else:
            for feat in filtered:
                self._search_results_inner.addWidget(
                    self._make_search_result_row(feat)
                )
        self._search_results.setVisible(True)

    def _make_search_result_row(self, feat: dict) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background:transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(2, 3, 2, 3)
        rl.setSpacing(8)

        name_lbl = QLabel(feat["name"])
        name_lbl.setStyleSheet(
            f"font-size:11px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none; min-width:130px;"
        )
        desc_lbl = QLabel(feat["desc"])
        desc_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY};"
            " background:transparent; border:none;"
        )
        desc_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        btn = QPushButton("Open →")
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px;"
            f" background:transparent; border:none; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
        )
        target = feat.get("page") or "Feature Guide"
        btn.clicked.connect(lambda _=False, t=target: self.navigate_to.emit(t))

        rl.addWidget(name_lbl)
        rl.addWidget(desc_lbl, 1)
        rl.addWidget(btn)
        return row

    # ── Discoverability strips ────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        qs = QSettings("NetSentinel", "NetSentinel")
        api_enabled = qs.value("rest_api/enabled", False, type=bool)
        strip_dismissed = qs.value("home/dashboard_strip_dismissed", False, type=bool)
        if api_enabled and not strip_dismissed:
            port = int(qs.value("rest_api/port", 8765))
            self._dashboard_url = f"http://localhost:{port}/dashboard"
            self._ds_text.setText(
                f"REST API running at localhost:{port} — browser dashboard + 7 endpoints "
                f"(devices, alerts, uptime, grade…). Open Settings to see the full list."
            )
            self._dashboard_strip.setVisible(True)
        else:
            self._dashboard_strip.setVisible(False)
        tips_dismissed = qs.value("home/tips_dismissed", False, type=bool)
        if not tips_dismissed:
            self._tip_row_rest_api.setVisible(not api_enabled)
            self._tips_card.setVisible(True)
        else:
            self._tips_card.setVisible(False)
        self.refresh_checklist()
        self._check_recurring_mode()
        if self._recurring_mode:
            self._update_recurring_scan_time()

    def _open_dashboard(self) -> None:
        QDesktopServices.openUrl(QUrl(self._dashboard_url))

    def _dismiss_dashboard_strip(self) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue(
            "home/dashboard_strip_dismissed", True
        )
        self._dashboard_strip.setVisible(False)

    def _dismiss_tips(self) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue("home/tips_dismissed", True)
        self._tips_card.setVisible(False)

    def _dismiss_post_scan_sheet(self) -> None:
        self._post_scan_sheet.setVisible(False)
        QSettings("NetSentinel", "NetSentinel").setValue(
            "home/post_scan_sheet_dismissed", True
        )
        # Show nudge if all monitoring pills are still off
        if not any(p.text().startswith("●") for p in (
            self._pill_arp, self._pill_dhcp, self._pill_storm, self._pill_logger
        )):
            self._monitoring_nudge.setVisible(True)

    def _maybe_show_post_scan_sheet(
        self, n_total: int, n_new: int, n_at_risk: int
    ) -> None:
        if QSettings("NetSentinel", "NetSentinel").value(
            "home/post_scan_sheet_dismissed", False, type=bool
        ):
            return
        n_recognized = n_total - n_new
        parts = [f"{n_total} device{'s' if n_total != 1 else ''} found"]
        if n_new:
            parts.append(f"{n_new} new")
        if n_recognized and n_new:
            parts.append(f"{n_recognized} recognized")
        self._sheet_stats_lbl.setText("  ·  ".join(parts))
        if self._current_grade:
            self._sheet_grade_btn.setText(
                f"Network Grade: {self._current_grade}  →"
            )
        else:
            self._sheet_grade_btn.setText("Run a Network Grade →")
        if n_at_risk > 0:
            self._sheet_action_btn.setText("Check unknown devices →")
            self._sheet_action_target = "Devices"
        else:
            self._sheet_action_btn.setText("Set up notifications →")
            self._sheet_action_target = "Notifications"
        self._post_scan_sheet.setVisible(True)

    def _set_first_run_mode(self, on: bool) -> None:
        """Show/hide secondary sections based on whether any devices have been scanned."""
        self._first_run_mode = on
        for w in (
            self._sec1_lbl, self._mini_cards_widget,
            self._monitoring_pills_row, self._monitoring_nudge,
            self._sec_mon_lbl, self._mon_card,
            self._alerts_hdr_row, self._alert_card,
        ):
            w.setVisible(not on)
        if on:
            self._hero_title.setText("Discover your network")
            self._hero_sub.setText(
                "See every device, check your security score, and start monitoring"
                " — takes about 30 seconds."
                "   ·   Try Ctrl+K to find any feature instantly."
            )
            self._suggestions_sec.setVisible(False)
            self._suggestions_card.setVisible(False)
            self._tips_card.setVisible(False)

    # ── Recurring-user layout ─────────────────────────────────────────────────

    def _check_recurring_mode(self) -> None:
        """Activate recurring layout if setup is complete and ≥5 scans recorded."""
        if self._first_run_mode or self._recurring_mode:
            return
        qs = QSettings("NetSentinel", "NetSentinel")
        scan_count = int(qs.value("home/scan_count", 0))
        if scan_count >= 5 and all(self._checklist_states()):
            self._apply_recurring_layout(True)

    def _apply_recurring_layout(self, on: bool) -> None:
        """Toggle between new-user and recurring-user Home layout."""
        if self._recurring_mode == on:
            return
        self._recurring_mode = on
        # Recurring top section: prominent monitoring status + grade/rescan
        self._recurring_section.setVisible(on)
        # Big scan button → compact rescan link
        self._btn_scan.setVisible(not on)
        self._btn_rescan_compact.setVisible(on)
        # Existing monitoring pills row is duplicated in recurring section
        self._monitoring_pills_row.setVisible(not on)
        self._monitoring_nudge.setVisible(False)
        # "View all →" next to Recent Alerts
        self._btn_view_all_alerts.setVisible(on)
        if on:
            # Refresh recurring section display
            self._update_recurring_grade_display()
            self._update_recurring_scan_time()

    def _update_recurring_grade_display(self) -> None:
        if not hasattr(self, "_rec_grade_lbl"):
            return
        if self._current_grade:
            from ui.styles import GREEN as _G, AMBER as _A, RED as _R
            color = _G if self._current_grade in ("A", "B") else (
                _A if self._current_grade == "C" else _R
            )
            self._rec_grade_lbl.setText(f"Network Grade: {self._current_grade}")
            self._rec_grade_lbl.setStyleSheet(
                f"font-size:11px; font-weight:600; color:{color};"
                " background:transparent; border:none;"
            )
        else:
            self._rec_grade_lbl.setText("Network Grade: –")

    def _update_recurring_scan_time(self) -> None:
        if not hasattr(self, "_rec_scan_time_lbl"):
            return
        if self._last_scan_ts is None:
            self._rec_scan_time_lbl.setText("Last scan: –")
            return
        delta = datetime.datetime.now() - self._last_scan_ts
        mins = int(delta.total_seconds() / 60)
        if mins < 1:
            self._rec_scan_time_lbl.setText("Last scan: just now")
        elif mins < 60:
            self._rec_scan_time_lbl.setText(f"Last scan: {mins} min ago")
        else:
            hrs = mins // 60
            self._rec_scan_time_lbl.setText(f"Last scan: {hrs}h ago")

    def _update_scan_button_label(self) -> None:
        label = "▶  Scan Network" if self._device_count == 0 else "▶  Rescan"
        self._btn_scan.setText(label)

    def set_monitor_pills(
        self, arp: bool, dhcp: bool, storm: bool, logger: bool
    ) -> None:
        """Update monitoring pill badges. Called by dashboard on worker state changes."""
        _pill_map = [
            (self._pill_arp,    arp,    "ARP Watch"),
            (self._pill_dhcp,   dhcp,   "DHCP Watch"),
            (self._pill_storm,  storm,  "Broadcast Storm"),
            (self._pill_logger, logger, "Network Logger"),
        ]
        for btn, active, label in _pill_map:
            if active:
                btn.setText(f"●  {label}")
                btn.setStyleSheet(
                    f"QPushButton {{ background:{GREEN}22; color:{GREEN}; font-size:10px;"
                    f" font-weight:bold; border:1px solid {GREEN}; border-radius:11px;"
                    f" padding:1px 10px; }}"
                    f"QPushButton:hover {{ background:{GREEN}44; }}"
                )
            else:
                btn.setText(f"○  {label}")
                btn.setStyleSheet(
                    f"QPushButton {{ background:{BG_CARD}; color:{TEXT_MUTED}; font-size:10px;"
                    f" border:1px solid {BORDER}; border-radius:11px; padding:1px 10px; }}"
                    f"QPushButton:hover {{ background:{BG_HOVER}; }}"
                )
        if any([arp, dhcp, storm, logger]):
            self._monitoring_nudge.setVisible(False)
        # Sync recurring section pills
        _rec_map = [
            (self._rec_pill_arp,    arp,    "ARP Watch"),
            (self._rec_pill_dhcp,   dhcp,   "DHCP Watch"),
            (self._rec_pill_storm,  storm,  "Broadcast Storm"),
            (self._rec_pill_logger, logger, "Network Logger"),
        ]
        for rbtn, active, rlabel in _rec_map:
            if active:
                rbtn.setText(f"●  {rlabel}")
                rbtn.setStyleSheet(
                    f"QPushButton {{ background:{GREEN}22; color:{GREEN}; font-size:10px;"
                    f" font-weight:bold; border:1px solid {GREEN}; border-radius:11px;"
                    f" padding:1px 10px; }}"
                    f"QPushButton:hover {{ background:{GREEN}44; }}"
                )
            else:
                rbtn.setText(f"○  {rlabel}")
                rbtn.setStyleSheet(
                    f"QPushButton {{ background:{BG_HOVER}; color:{TEXT_MUTED}; font-size:10px;"
                    f" border:1px solid {BORDER}; border-radius:11px; padding:1px 10px; }}"
                    f"QPushButton:hover {{ border-color:{ACCENT}; }}"
                )

    def _scroll_to_setup_card(self) -> None:
        """Scroll to / expand the setup checklist card (NUX-4)."""
        if not hasattr(self, "_setup_card"):
            return
        self._setup_card.setVisible(True)
        if self._setup_collapsed:
            self._setup_toggle_collapse()

    # ── NUX-4 setup checklist ─────────────────────────────────────────────────

    def _setup_toggle_collapse(self) -> None:
        self._setup_collapsed = not self._setup_collapsed
        self._setup_body.setVisible(not self._setup_collapsed)
        self._setup_collapse_btn.setText("▶" if self._setup_collapsed else "▼")

    def _checklist_states(self) -> list[bool]:
        qs = QSettings("NetSentinel", "NetSentinel")
        scan_done  = self._device_count > 0
        arp_done   = qs.value("home/setup/arp_started", False, type=bool)
        channel_done = any(
            qs.value(k, False, type=bool)
            for k in qs.allKeys()
            if k.startswith("notif/") and k.endswith("_enabled")
        )
        rule_done  = qs.value("notif/any_rule_enabled", False, type=bool)
        grade_done = qs.value("grade/last_run", False, type=bool)
        return [scan_done, arp_done, channel_done, rule_done, grade_done]

    def refresh_checklist(self) -> None:
        """Re-read step states and update checklist UI. Call from showEvent and cycle_done."""
        if not hasattr(self, "_setup_check_lbls"):
            return
        states = self._checklist_states()
        done_count = sum(states)
        for chk, done in zip(self._setup_check_lbls, states):
            if done:
                chk.setText("✓")
                chk.setStyleSheet(
                    f"font-size:12px; color:{GREEN}; background:transparent; border:none;"
                )
            else:
                chk.setText("○")
                chk.setStyleSheet(
                    f"font-size:12px; color:{TEXT_MUTED}; background:transparent; border:none;"
                )
        self._setup_progress_lbl.setText(f"{done_count}/5 done")
        all_done = done_count == 5
        if all_done:
            self._setup_hdr_lbl.setText("✓ SETUP COMPLETE")
            self._setup_hdr_lbl.setStyleSheet(
                f"font-size:10px; color:{GREEN}; background:transparent;"
                " border:none; letter-spacing:1px;"
            )
            if not self._setup_collapsed:
                self._setup_toggle_collapse()
        else:
            self._setup_hdr_lbl.setText("SETUP CHECKLIST")
            self._setup_hdr_lbl.setStyleSheet(
                f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
                " border:none; letter-spacing:1px;"
            )

    def set_scanning(self, running: bool) -> None:
        self._btn_scan.setEnabled(not running)
        if running:
            self._btn_scan.setText("Scanning…")
            self._hero_sub.setText(
                "Scan in progress — tiles will update as each module completes."
            )
        else:
            self._update_scan_button_label()
            self._hero_sub.setText("Discover devices · check stability · detect threats")

    # ── Startup preload ───────────────────────────────────────────────────────

    def _preload_from_store(self) -> None:
        """Populate cards with the most-recent persisted data on first show."""
        if self._store is None:
            return
        try:
            # Guard against the widget being deleted before the timer fires.
            self.objectName()
        except RuntimeError:
            return
        try:
            # Speed card — last recorded test result
            speed_rows = self._store.query_speed_test_history(hours=168, limit=1)
            if speed_rows:
                row = speed_rows[0]
                dl = row.download_mbps or 0.0
                ul = row.upload_mbps or 0.0
                colour = GREEN if dl > 25 else (AMBER if dl > 5 else RED)
                self._speed_card.set_value(
                    f"{dl:.0f} Mbps",
                    f"/ up {ul:.0f} Mbps",
                    "(last scan)",
                    colour,
                )
        except Exception:
            pass
        try:
            # Devices card — count of known devices
            devices = self._store.get_known_devices()
            n = len(devices)
            self._device_count = n
            self._update_scan_button_label()
            if n > 0:
                self._devices_card.set_value(
                    str(n),
                    "on network",
                    "(last scan)",
                    GREEN,
                )
        except Exception:
            pass
        if self._device_count == 0:
            self._set_first_run_mode(True)

    # ── Public slots ──────────────────────────────────────────────────────────

    @pyqtSlot(dict)
    def on_cycle_done(self, result: dict) -> None:
        """Refresh devices and stability cards from an availability cycle result."""
        devices = result.get("devices", [])
        rtts = result.get("rtts", {})
        n_total = len(devices)
        was_first_run = self._first_run_mode
        if n_total > 0 and self._first_run_mode:
            self._set_first_run_mode(False)

        # Devices card
        n_at_risk = sum(
            1 for d in devices
            if d.get("risk_level", "UNKNOWN") in ("HIGH", "UNKNOWN")
        )
        dev_colour = GREEN if n_at_risk == 0 else AMBER
        n_new = sum(1 for d in devices if d.get("is_new", False))
        dev_sub = f"on network" + (f" \u00b7 {n_new} new" if n_new else "")
        dev_status = (
            f"{n_at_risk} at risk" if n_at_risk
            else ("All healthy" if n_total > 0 else "Run a scan to discover devices")
        )
        self._device_count = n_total
        self._update_scan_button_label()
        self._devices_card.set_value(str(n_total), dev_sub, dev_status, dev_colour)

        # Stability card \u2014 average RTT across all hosts
        avg_rtt: float | None = None
        if rtts:
            all_vals: list[float] = []
            for v in rtts.values():
                if isinstance(v, (int, float)):
                    all_vals.append(float(v))
                elif isinstance(v, list):
                    all_vals.extend(float(x) for x in v if x is not None)
            if all_vals:
                avg_rtt = sum(all_vals) / len(all_vals)
                if avg_rtt < 50:
                    stab_colour, stab_status = GREEN, "Stable connection"
                elif avg_rtt < 150:
                    stab_colour, stab_status = AMBER, "Moderate latency"
                else:
                    stab_colour, stab_status = RED, "High latency"
                self._stability_card.set_value(
                    f"{avg_rtt:.0f} ms", "avg latency", stab_status, stab_colour
                )

        # Hero title + inline stats subtitle
        if n_total > 0:
            rtt_part = f" \u00b7 {avg_rtt:.0f} ms avg latency" if avg_rtt is not None else ""
            risk_part = (
                f" \u00b7 {n_at_risk} device{'s' if n_at_risk != 1 else ''} at risk"
                if n_at_risk else " \u00b7 No alerts"
            )
            self._hero_title.setText(
                "Your network is in great shape"
                if n_at_risk == 0 else
                f"{n_at_risk} device{'s' if n_at_risk != 1 else ''} need attention"
            )
            self._hero_sub.setText(
                f"{n_total} device{'s' if n_total != 1 else ''} online"
                f"{rtt_part}{risk_part}"
            )

        # \u2500\u2500 Results strip \u2014 show after first scan, update on every cycle \u2500\u2500\u2500\u2500\u2500\u2500
        if n_total > 0:
            # Devices row
            _s = "s" if n_total != 1 else ""
            _new = f"  \u00b7  {n_new} new" if n_new else ""
            self._res_devices_lbl.setText(
                f"{n_total} device{_s} found{_new}"
            )
            _dev_colour = GREEN if n_at_risk == 0 else AMBER
            self._res_devices_dot.setStyleSheet(
                f"font-size:8px; color:{_dev_colour};"
                " background:transparent; border:none;"
            )

            # Connection row
            if avg_rtt is not None:
                _conn_colour = GREEN if avg_rtt < 50 else (AMBER if avg_rtt < 150 else RED)
                self._res_conn_lbl.setText(f"{avg_rtt:.0f} ms avg latency")
            else:
                _conn_colour = GREEN
                self._res_conn_lbl.setText("Connection monitoring active")
            self._res_conn_dot.setStyleSheet(
                f"font-size:8px; color:{_conn_colour};"
                " background:transparent; border:none;"
            )

            # Security row
            if n_at_risk == 0:
                _sec_colour = GREEN
                self._res_security_lbl.setText("No security issues detected")
            else:
                _sec_colour = RED
                _i = "s" if n_at_risk != 1 else ""
                self._res_security_lbl.setText(
                    f"{n_at_risk} device{_i} need attention"
                )
            self._res_security_dot.setStyleSheet(
                f"font-size:8px; color:{_sec_colour};"
                " background:transparent; border:none;"
            )

            self._results_strip.setVisible(True)

        if was_first_run and n_total > 0:
            self._maybe_show_post_scan_sheet(n_total, n_new, n_at_risk)
        self.refresh_checklist()
        if n_total > 0:
            self._last_scan_ts = datetime.datetime.now()
            qs = QSettings("NetSentinel", "NetSentinel")
            qs.setValue("home/scan_count", int(qs.value("home/scan_count", 0)) + 1)
            if self._recurring_mode:
                self._update_recurring_scan_time()
            else:
                self._check_recurring_mode()

    @pyqtSlot(object)
    def on_speed_result(self, result) -> None:
        """Refresh the speed mini-card from a SpeedTestResult."""
        dl = getattr(result, "download_mbps", 0.0) or 0.0
        ul = getattr(result, "upload_mbps", 0.0) or 0.0
        colour = GREEN if dl > 25 else (AMBER if dl > 5 else RED)
        self._speed_card.set_value(
            f"{dl:.0f} Mbps",
            f"/ up {ul:.0f} Mbps",
            "last result",
            colour,
        )

    @pyqtSlot(object)
    def on_alert(self, alert) -> None:
        """Prepend an alert row; keep at most 3 rows."""
        if self._alert_count == 0:
            # Switch from the initial label to the "no other alerts" footer
            self._no_alerts_lbl.setVisible(False)
            self._no_other_alerts_lbl.setText("No other alerts in the last 24 hours")
            self._no_other_alerts_lbl.setVisible(True)

        # Remove oldest if already at limit (insert position 0 = first widget slot)
        if self._alert_count >= 3:
            # The bottom 2 items are the two footer labels; remove item at count()-3
            item = self._alert_inner.takeAt(self._alert_inner.count() - 3)
            if item and item.widget():
                item.widget().deleteLater()
            self._alert_count -= 1

        severity = getattr(alert, "severity", "WARNING")
        msg = str(getattr(alert, "message", alert))
        colour = RED if any(k in severity.upper() for k in ("HIGH", "CRITICAL")) else AMBER
        time_str = datetime.datetime.now().strftime("%H:%M")
        row = HomePage._AlertRow(colour, msg[:80], time_str, alert=alert)
        row.clicked.connect(self.alert_view_requested.emit)
        # Insert before the footer labels (at index 0 — top of list)
        self._alert_inner.insertWidget(0, row)
        self._alert_count += 1

    @pyqtSlot(str, float)
    def set_monitoring_status(self, running: bool, elapsed_str: str = "",
                              outage_count: int = 0) -> None:
        """Update the stability monitoring card on the home page."""
        if running:
            dot_color = GREEN
            outage_txt = f" · {outage_count} outage{'s' if outage_count != 1 else ''}" if outage_count else " · no outages"
            elapsed_txt = f"  {elapsed_str}" if elapsed_str else ""
            self._mon_status_lbl.setText(
                f"Running{elapsed_txt}{outage_txt} — leave the app open to keep logging."
            )
            self._mon_status_lbl.setStyleSheet(
                f"font-size:11px; color:{GREEN}; background:transparent; border:none;"
            )
            self._mon_dot.setStyleSheet(
                f"font-size:9px; color:{GREEN}; background:transparent; border:none;"
            )
            self._btn_mon_start.setText("Stop")
            self._btn_mon_start.setStyleSheet(
                f"QPushButton {{ background:transparent; color:{TEXT_SECONDARY}; border:1px solid {BORDER};"
                f" border-radius:4px; font-size:11px; padding:0 12px; }}"
                f"QPushButton:hover {{ background:{BORDER}; }}"
            )
        else:
            self._mon_status_lbl.setText(
                "Not running — start to log connection stability over time."
            )
            self._mon_status_lbl.setStyleSheet(
                f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
            )
            self._mon_dot.setStyleSheet(
                f"font-size:9px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
            )
            self._btn_mon_start.setText("Start Monitoring")
            self._btn_mon_start.setStyleSheet(
                f"QPushButton {{ background:{ACCENT}; color:#ffffff; border:none;"
                f" border-radius:4px; font-size:11px; font-weight:600; padding:0 12px; }}"
                f"QPushButton:hover {{ background:#1a6fc4; }}"
            )

    def set_last_visit_summary(
        self,
        joined_count: int,
        outage_count: int,
        last_visit_str: str,
    ) -> None:
        """Show or hide the 'Since you were last here' banner."""
        parts = []
        if joined_count > 0:
            s = "s" if joined_count != 1 else ""
            parts.append(f"{joined_count} new device{s} joined")
        if outage_count > 0:
            s = "s" if outage_count != 1 else ""
            parts.append(f"{outage_count} outage{s} recorded")
        if not parts:
            self._last_visit_card.setVisible(False)
            return
        self._lv_text.setText(f"Since {last_visit_str}: {'  ·  '.join(parts)}.")
        self._last_visit_card.setVisible(True)

    def set_suggestions(self, suggestions: list) -> None:
        """Populate and show the 'What to do next' strip."""
        while self._suggestions_inner.count():
            item = self._suggestions_inner.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        if not suggestions:
            self._suggestions_sec.setVisible(False)
            self._suggestions_card.setVisible(False)
            return

        for sug in suggestions[:4]:
            text     = sug.get("text", "")
            action   = sug.get("action_label", "Fix →")
            target   = sug.get("target")       # None = emit start_monitoring_requested
            priority = sug.get("priority", "medium")
            colour   = RED if priority == "high" else (AMBER if priority == "medium" else ACCENT)

            row = QWidget()
            row.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            rl.setSpacing(8)

            dot = QLabel("●")
            dot.setFixedWidth(12)
            dot.setStyleSheet(
                f"font-size:8px; color:{colour}; background:transparent; border:none;"
            )
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent; border:none;"
            )
            btn = QPushButton(action)
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ color:{ACCENT}; font-size:11px;"
                f" background:transparent; border:none; padding:0; }}"
                f"QPushButton:hover {{ color:#005A9E; }}"
            )
            if target == "__live__":
                btn.clicked.connect(self.investigate_live_requested)
            elif target is not None:
                btn.clicked.connect(lambda _c=False, t=target: self.navigate_to.emit(t))
            else:
                btn.clicked.connect(self.start_monitoring_requested)

            rl.addWidget(dot)
            rl.addWidget(lbl, 1)
            rl.addWidget(btn)
            self._suggestions_inner.addWidget(row)

        self._suggestions_sec.setVisible(True)
        self._suggestions_card.setVisible(True)

    def on_grade(self, grade: str, score: float) -> None:  # noqa: ARG002
        """Update the hero grade circle text and colour."""
        self._current_grade = grade
        if grade in ("A", "B"):
            colour = GREEN
        elif grade == "C":
            colour = AMBER
        else:
            colour = RED
        self._grade_circle.setText(grade)
        self._grade_circle.setStyleSheet(
            f"font-size:28px; font-weight:bold; color:{colour};"
            f" border:3px solid {colour}; border-radius:34px;"
            f" background:{BG_CARD};"
        )
        if self._recurring_mode:
            self._update_recurring_grade_display()


# ── Standard mode welcome page ────────────────────────────────────────────────

class StandardWelcomePage(QWidget):
    """
    Landing page shown when 'Home' is selected in Standard mode.
    Displays a 2-column feature card grid: 'WHAT EACH SECTION GIVES YOU'.
    """

    _FEATURES = [
        ("\u26a1", "Speed test",      AMBER,        ["Download / upload speed",
                                                      "Ookla or fallback backends",
                                                      "Historical trend chart"]),
        ("\u25ce", "DNS & Stability", ACCENT,        ["Live ping + DNS latency graph",
                                                      "Outage detection & log",
                                                      "STP reconvergence signature"]),
        ("\u2295", "Devices",         TEXT_PRIMARY,  ["IP, MAC, vendor, model",
                                                      "Right-click How to Fix",
                                                      "Availability history per device"]),
        ("\u25b2", "Live Bandwidth",  TEXT_PRIMARY,  ["Per-device rx/tx Mbps",
                                                      "60-second rolling area chart",
                                                      "Session totals table"]),
        ("\u25fc", "Network Grade",   TEXT_PRIMARY,  ["A\u2013F across 8 dimensions",
                                                      "Colour-coded verdict per metric",
                                                      "Actionable fix tip per grade"]),
        ("\u2197", "Network Health Report", TEXT_PRIMARY, ["Self-contained HTML export",
                                                           "MTR hop table + outage log",
                                                           "Great for ISP support tickets"]),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border:none; background:transparent; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        inner = QWidget()
        inner.setObjectName("homepageInner")
        inner.setStyleSheet(f"QWidget#homepageInner {{ background:{BG_DARK}; }}")
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        lay = QVBoxLayout(inner)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(12)

        hdr = QLabel("WHAT EACH SECTION GIVES YOU")
        hdr.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
            " letter-spacing:1px; padding-bottom:2px;"
        )
        lay.addWidget(hdr)

        # 2-column grid of feature cards
        from PyQt6.QtWidgets import QGridLayout
        grid_w = QWidget()
        grid_w.setStyleSheet(f"background:{BG_DARK};")
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)

        for i, (icon, title, icon_colour, bullets) in enumerate(self._FEATURES):
            card = self._make_card(icon, title, icon_colour, bullets)
            grid.addWidget(card, i // 2, i % 2)

        lay.addWidget(grid_w)
        lay.addStretch()

    @staticmethod
    def _make_card(icon: str, title: str, icon_colour: str,
                   bullets: list[str]) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER}; }}"
        )
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(12, 10, 12, 10)
        card_lay.setSpacing(6)

        # Icon + title row
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(
            f"font-size:14px; color:{icon_colour}; background:transparent; border:none;"
        )
        icon_lbl.setFixedWidth(18)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        title_row.addWidget(icon_lbl)
        title_row.addWidget(title_lbl, 1)
        card_lay.addLayout(title_row)

        for bullet in bullets:
            b = QLabel(f"\u2022 {bullet}")
            b.setStyleSheet(
                f"font-size:11px; color:{TEXT_SECONDARY};"
                " background:transparent; border:none; padding-left:4px;"
            )
            card_lay.addWidget(b)

        return card


# ── Pro mode welcome page ─────────────────────────────────────────────────────

class ProWelcomePage(QWidget):
    """
    Landing page shown when 'Home' is selected in Pro mode.
    Shows an admin-required warning and security audit capability cards.
    """

    _CAPABILITIES = [
        ("\u25ce", "Port scanning",       ["\u2022 TCP connect + SYN (Scapy)",
                                           "\u2022 UDP scanner (DNS/SNMP/NTP)",
                                           "\u2022 Stealth / normal / fast modes"]),
        ("\u25ce", "CVE tracker",         ["\u2022 NVD API v2 lookup per host",
                                           "\u2022 Lifecycle state machine",
                                           "\u2022 Days-open counter, owner field"]),
        ("\u25ce", "Threat Intelligence", ["\u2022 Feodo Tracker + Emerging Threats",
                                           "\u2022 AbuseIPDB v2 lookup",
                                           "\u2022 Blocklist KPI tiles"]),
        ("\u25fc", "TLS & exposure",      ["\u2022 Per-host cert expiry monitor",
                                           "\u2022 WAN / CGNAT / UPnP exposure",
                                           "\u2022 Cloud metadata probe"]),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border:none; background:transparent; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        inner = QWidget()
        inner.setObjectName("homepageInner")
        inner.setStyleSheet(f"QWidget#homepageInner {{ background:{BG_DARK}; }}")
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        lay = QVBoxLayout(inner)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(12)

        # Red warning box
        warn = QFrame()
        warn.setStyleSheet(
            f"QFrame {{ background:{PRO_WARN_BG}; border:1px solid {RED}; }}"
        )
        warn_lay = QHBoxLayout(warn)
        warn_lay.setContentsMargins(12, 10, 12, 10)
        warn_icon = QLabel("\u26a0")
        warn_icon.setStyleSheet(
            f"font-size:16px; color:{RED}; background:transparent; border:none;"
        )
        warn_icon.setFixedWidth(22)
        warn_text = QLabel(
            "Security Audit tools require administrator privileges and Npcap. "
            "They are intentionally separated from home-user features to avoid confusion."
        )
        warn_text.setWordWrap(True)
        warn_text.setStyleSheet(
            f"font-size:11px; color:{RED}; background:transparent; border:none;"
        )
        warn_lay.addWidget(warn_icon)
        warn_lay.addWidget(warn_text, 1)
        lay.addWidget(warn)

        hdr = QLabel("SECURITY AUDIT CAPABILITIES")
        hdr.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
            " letter-spacing:1px; padding-top:4px; padding-bottom:2px;"
        )
        lay.addWidget(hdr)

        # 2-column grid
        from PyQt6.QtWidgets import QGridLayout
        grid_w = QWidget()
        grid_w.setStyleSheet(f"background:{BG_DARK};")
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)

        for i, (icon, title, bullets) in enumerate(self._CAPABILITIES):
            card = self._make_card(icon, title, bullets)
            grid.addWidget(card, i // 2, i % 2)

        lay.addWidget(grid_w)
        lay.addStretch()

    @staticmethod
    def _make_card(icon: str, title: str, bullets: list[str]) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER}; }}"
        )
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(12, 10, 12, 10)
        card_lay.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(
            f"font-size:14px; color:{TEXT_PRIMARY}; background:transparent; border:none;"
        )
        icon_lbl.setFixedWidth(18)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        title_row.addWidget(icon_lbl)
        title_row.addWidget(title_lbl, 1)
        card_lay.addLayout(title_row)

        for bullet in bullets:
            b = QLabel(bullet)
            b.setStyleSheet(
                f"font-size:11px; color:{TEXT_SECONDARY};"
                " background:transparent; border:none; padding-left:4px;"
            )
            card_lay.addWidget(b)

        return card
