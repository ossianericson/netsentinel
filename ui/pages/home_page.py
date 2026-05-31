"""
HomePage â€” introductory landing page shown in Home mode.

Hero card (network grade), three mini metric cards (speed / stability / devices),
and a recent-alerts strip.

Architecture rules observed:
  Ã¢â‚¬Â¢ All colours from ui.styles â€” no hardcoded hex values.
  Ã¢â‚¬Â¢ No blocking I/O. Pure display widget; all data arrives via public slots.
  Ã¢â‚¬Â¢ Outer scroll area so the content is never clipped on small windows.
"""
from __future__ import annotations

import datetime

import json

from PyQt6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRect, QRectF, Qt, QSettings, QUrl, QVariantAnimation, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QDesktopServices, QFont, QPainter, QPainterPath, QPen
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
    ACCENT_DARK,
    ACCENT_LITE,
    AMBER,
    BG_CARD,
    BG_DARK,
    BG_HOVER,
    BORDER,
    CARD_RADIUS,
    GREEN,
    NAV_BAR,
    PRO_WARN_BG,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    UPDATE_BAR_BG,
    UPDATE_BAR_BORDER,
    UPDATE_BAR_FG,
    WHITE,
)
import ui.styles as _styles

try:
    from ui.pages.discover_page import _FEATURES as _GUIDE_FEATURES
except ImportError:
    _GUIDE_FEATURES: list = []

from ui.widgets.home_widgets import (
    _GradeRing, _MiniCard, _AlertRow, _MiniSparkline, _GradeSparkline, _EventsTicker,
    _GRADE_HISTORY_KEY, _GRADE_HISTORY_MAX,
    _append_grade_history, _load_grade_history, _bundled_plugin_path,
    FreshnessStrip, GettingStartedCard,
    _GradeBreakdownDialog, StandardWelcomePage, ProWelcomePage,
)
from ui.pages.home_suggestions import _HomeSuggestionsMixin
from ui.pages.home_data_mixin import _HomeDataMixin


class HomePage(_HomeDataMixin, _HomeSuggestionsMixin, QWidget):
    """Simple landing page for new / Home-mode users."""

    #: Emitted when a mini-card is clicked; carries the target page label string.
    navigate_to = pyqtSignal(str)
    #: Emitted when the user clicks "Start Monitoring" on the stability card.
    start_monitoring_requested = pyqtSignal()
    #: Emitted when the user clicks the refresh icon on the freshness strip.
    rescan_requested = pyqtSignal()
    #: Emitted when the user clicks "Investigate â†’" on a live challenge suggestion.
    investigate_live_requested = pyqtSignal()
    #: Emitted when the user clicks an alert row; carries the raw alert object.
    alert_view_requested = pyqtSignal(object)
    #: Emitted when user clicks "Add" on a hardware checklist step; carries plugin path.
    add_plugin_requested = pyqtSignal(str)


    # Ã¢â€â‚¬Ã¢â€â‚¬ Constructor Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

    def __init__(self, store=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._alert_count = 0
        self._ac_offline_count = 0
        self._device_count: int = 0
        self._signals_connected: bool = False
        self._first_run_mode: bool = False
        self._recurring_mode: bool = False
        self._current_grade: str = ""
        self._last_scan_ts: "datetime.datetime | None" = None
        self._grade_dimensions: list = []
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

    # Ã¢â€â‚¬Ã¢â€â‚¬ Theme nudge banner Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

    def _build_theme_banner(self) -> "QFrame | None":
        qs = QSettings("NetSentinel", "NetSentinel")
        if qs.value("ui/theme_nudge_dismissed", False, type=bool):
            return None

        active = _styles.get_active_theme_name()

        banner = QFrame()
        banner.setObjectName("themeBanner")
        banner.setStyleSheet(
            f"QFrame#themeBanner {{ background:{UPDATE_BAR_BG}; border-bottom:1px solid {UPDATE_BAR_BORDER}; }}"
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
            ("Arctic Clean",  "â˜€  Light"),
            ("Midnight Pro",  "Ã°Å¸Å’â„¢  Dark"),
            ("Obsidian Neon", "âœ¦  Neon"),
        ]

        def _dismiss(save_theme: str | None = None) -> None:
            if save_theme:
                _styles.set_active_theme_name(save_theme)
                lbl.setText(f"Theme '{save_theme}' saved â€” restart NetSentinel to apply.")
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
                    f"QPushButton {{ background:{ACCENT}; color:{WHITE};"
                    f" border:none; border-radius:3px; font-size:11px; padding:0 10px; }}"
                    f"QPushButton:hover {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
                    f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background:transparent; color:{UPDATE_BAR_FG};"
                    f" border:1px solid {UPDATE_BAR_BORDER}; border-radius:3px;"
                    f" font-size:11px; padding:0 10px; }}"
                    f"QPushButton:hover {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
                    f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
                )
                _name = theme_name
                btn.clicked.connect(lambda _checked, n=_name: _dismiss(n))
            _btn_refs.append(btn)
            row.addWidget(btn)

        row.addStretch()

        close_btn = QPushButton("Ãƒâ€”")
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Dismiss")
        close_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none;"
            f" font-size:15px; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; background:transparent; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; background:transparent; }}"
        )
        close_btn.clicked.connect(lambda: _dismiss(None))
        row.addWidget(close_btn)

        return banner


    def _setup_ui(self) -> None:
        self.setObjectName("homePageRoot")
        self.setStyleSheet(f"QWidget#homePageRoot {{ background:{BG_DARK}; }}")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Ã¢â€â‚¬Ã¢â€â‚¬ Theme nudge banner (one-time, dismissed via QSettings) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        _banner = self._build_theme_banner()
        if _banner is not None:
            outer.addWidget(_banner)
        # Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

        # Ã¢â€â‚¬Ã¢â€â‚¬ Freshness strip â€” always visible above scroll area Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        self._freshness_strip = FreshnessStrip()
        self._freshness_strip.rescan_requested.connect(self.rescan_requested)
        outer.addWidget(self._freshness_strip)

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

        # Ã¢â€â‚¬Ã¢â€â‚¬ Browser dashboard strip (visible when API enabled + not dismissed) Ã¢â€â‚¬
        self._dashboard_strip = QFrame()
        self._dashboard_strip.setObjectName("dashboardStrip")
        self._dashboard_strip.setStyleSheet(
            f"QFrame#dashboardStrip {{ background:{UPDATE_BAR_BG}; border:1px solid {UPDATE_BAR_BORDER};"
            f" border-radius:4px; }}"
        )
        self._dashboard_strip.setVisible(False)
        _ds_lay = QHBoxLayout(self._dashboard_strip)
        _ds_lay.setContentsMargins(12, 5, 8, 5)
        _ds_lay.setSpacing(8)
        _ds_icon = QLabel("Ã°Å¸Å’Â")
        _ds_icon.setFixedWidth(18)
        _ds_icon.setStyleSheet(
            f"font-size:12px; color:{UPDATE_BAR_FG}; background:transparent; border:none;"
        )
        self._ds_text = QLabel("")
        self._ds_text.setStyleSheet(
            f"font-size:11px; color:{UPDATE_BAR_FG}; background:transparent; border:none;"
        )
        _ds_open = QPushButton("Open â†—")
        _ds_open.setFixedHeight(24)
        _ds_open.setCursor(Qt.CursorShape.PointingHandCursor)
        _ds_open.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:3px; font-size:11px; padding:0 8px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        _ds_open.clicked.connect(self._open_dashboard)
        _ds_dismiss = QPushButton("Ãƒâ€”")
        _ds_dismiss.setFixedSize(20, 20)
        _ds_dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        _ds_dismiss.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{UPDATE_BAR_FG}; border:none;"
            f" font-size:14px; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{UPDATE_BAR_FG}; }}"
        )
        _ds_dismiss.clicked.connect(self._dismiss_dashboard_strip)
        _ds_lay.addWidget(_ds_icon)
        _ds_lay.addWidget(self._ds_text, 1)
        _ds_lay.addWidget(_ds_open)
        _ds_lay.addWidget(_ds_dismiss)
        lay.addWidget(self._dashboard_strip)

        # Ã¢â€â‚¬Ã¢â€â‚¬ GETTING STARTED checklist (replaces separate hw strip) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        self._setup_card_top = GettingStartedCard()
        self._setup_card_top.add_plugin_requested.connect(self.add_plugin_requested)
        self._setup_card_top.navigate_to.connect(self.navigate_to)
        lay.addWidget(self._setup_card_top)

        # Ã¢â€â‚¬Ã¢â€â‚¬ Since you were last here (hidden until data loaded) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        self._last_visit_card = QFrame()
        self._last_visit_card.setObjectName("lastVisitCard")
        self._last_visit_card.setStyleSheet(
            f"QFrame#lastVisitCard {{ background:{PRO_WARN_BG}; border:1px solid {UPDATE_BAR_BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        self._last_visit_card.setVisible(False)
        lv_lay = QHBoxLayout(self._last_visit_card)
        lv_lay.setContentsMargins(12, 8, 12, 8)
        lv_lay.setSpacing(10)
        _lv_icon = QLabel("â—·")
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

        # Ã¢â€â‚¬Ã¢â€â‚¬ DASH-1: "Action needed" card Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        self._action_card = QFrame()
        self._action_card.setObjectName("actionCard")
        self._action_card.setStyleSheet(
            f"QFrame#actionCard {{ background:{BG_CARD}; border:1px solid {RED}44;"
            f" border-left:3px solid {RED}; border-radius:{CARD_RADIUS}; }}"
        )
        self._action_card.setVisible(False)
        _ac_outer = QVBoxLayout(self._action_card)
        _ac_outer.setContentsMargins(14, 10, 14, 10)
        _ac_outer.setSpacing(6)
        _ac_hdr_row = QHBoxLayout()
        _ac_hdr_lbl = QLabel("âš   Action needed")
        _ac_hdr_lbl.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{RED};"
            " background:transparent; border:none;"
        )
        _ac_hdr_row.addWidget(_ac_hdr_lbl)
        _ac_hdr_row.addStretch()
        _ac_outer.addLayout(_ac_hdr_row)

        # Ã¢â€â‚¬Ã¢â€â‚¬ ALERT-3: per-alert rows with inline ack Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        self._ac_alert_rows_widget = QWidget()
        self._ac_alert_rows_widget.setStyleSheet("background:transparent;")
        self._ac_alert_rows_lay = QVBoxLayout(self._ac_alert_rows_widget)
        self._ac_alert_rows_lay.setContentsMargins(0, 0, 0, 0)
        self._ac_alert_rows_lay.setSpacing(2)
        self._ac_alert_rows_widget.setVisible(False)
        _ac_outer.addWidget(self._ac_alert_rows_widget)

        self._ac_view_all_btn = QPushButton("View all alerts â†’")
        self._ac_view_all_btn.setFixedHeight(22)
        self._ac_view_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ac_view_all_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{AMBER}; border:none;"
            f" font-size:10px; padding:0; text-align:left; }}"
            f"QPushButton:hover {{ color:{RED}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{AMBER}; }}"
        )
        self._ac_view_all_btn.clicked.connect(lambda: self.navigate_to.emit("Notifications"))
        self._ac_view_all_btn.setVisible(False)
        _ac_outer.addWidget(self._ac_view_all_btn)

        # Ã¢â€â‚¬Ã¢â€â‚¬ Offline devices row (separate concern, unchanged) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        _ac_devices_row = QHBoxLayout()
        _ac_devices_row.setSpacing(8)
        self._ac_devices_lbl = QLabel("")
        self._ac_devices_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        _ac_devices_btn = QPushButton("View Devices â†’")
        _ac_devices_btn.setFixedHeight(24)
        _ac_devices_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _ac_devices_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{RED}; border:1px solid {RED};"
            f" border-radius:3px; font-size:11px; padding:0 8px; }}"
            f"QPushButton:hover {{ background:{RED}22; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{RED}; }}"
        )
        _ac_devices_btn.clicked.connect(lambda: self.navigate_to.emit("Inventory Changes"))
        _ac_devices_row.addWidget(self._ac_devices_lbl)
        _ac_devices_row.addWidget(_ac_devices_btn)
        _ac_devices_row.addStretch()
        _ac_outer.addLayout(_ac_devices_row)

        self._ac_offline_count = 0  # track so ack-all can decide whether to hide card
        lay.addWidget(self._action_card)

        # Ã¢â€â‚¬Ã¢â€â‚¬ Post-scan delta banner (hidden until 2nd+ scan) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        self._delta_banner = QFrame()
        self._delta_banner.setObjectName("deltaBanner")
        self._delta_banner.setStyleSheet(
            f"QFrame#deltaBanner {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        self._delta_banner.setVisible(False)
        _db_lay = QHBoxLayout(self._delta_banner)
        _db_lay.setContentsMargins(12, 6, 8, 6)
        _db_lay.setSpacing(10)
        self._delta_chips_lbl = QLabel("")
        self._delta_chips_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent; border:none;"
        )
        _db_dismiss = QPushButton("Ãƒâ€”")
        _db_dismiss.setFixedSize(20, 20)
        _db_dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        _db_dismiss.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none;"
            f" font-size:14px; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_MUTED}; }}"
        )
        _db_dismiss.clicked.connect(lambda: self._delta_banner.setVisible(False))
        _db_lay.addWidget(self._delta_chips_lbl, 1)
        _db_lay.addWidget(_db_dismiss)
        lay.addWidget(self._delta_banner)

        # Ã¢â€â‚¬Ã¢â€â‚¬ Recurring-user top section (hidden until conditions met) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        self._recurring_section = QFrame()
        self._recurring_section.setObjectName("recurringSection")
        self._recurring_section.setStyleSheet(
            f"QFrame#recurringSection {{ background:{BG_CARD}; border:1px solid {BORDER};"
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

        # Pill row â€” separate instances synced by set_monitor_pills()
        _rec_pills_row = QHBoxLayout()
        _rec_pills_row.setSpacing(6)
        _rec_pills_row.setContentsMargins(0, 0, 0, 0)

        def _rec_pill(label: str, target: str) -> QPushButton:
            b = QPushButton(f"â—‹  {label}")
            b.setFixedHeight(22)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton {{ background:{BG_HOVER}; color:{TEXT_MUTED}; font-size:10px;"
                f" border:1px solid {BORDER}; border-radius:11px; padding:1px 10px; }}"
                f"QPushButton:hover {{ border-color:{ACCENT}; }}"
                f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
            )
            b.clicked.connect(lambda _=False, t=target: self.navigate_to.emit(t))
            return b

        self._rec_pill_arp    = _rec_pill("ARP Watch",       "ARP Spoof Watch")
        self._rec_pill_dhcp   = _rec_pill("DHCP Watch",      "DHCP Rogue Monitor")
        self._rec_pill_storm  = _rec_pill("Broadcast Storm", "Broadcast Storm")
        self._rec_pill_logger = _rec_pill("Network Logger",  "Network Logger")
        for _rp in (self._rec_pill_arp, self._rec_pill_dhcp,
                    self._rec_pill_storm, self._rec_pill_logger):
            _rec_pills_row.addWidget(_rp)
        _rec_pills_row.addStretch()
        _rec_outer.addLayout(_rec_pills_row)

        # Grade + last scan + rescan row
        _rec_status_row = QHBoxLayout()
        _rec_status_row.setSpacing(12)
        _rec_status_row.setContentsMargins(0, 0, 0, 0)
        self._rec_grade_lbl = QLabel("Network Grade: â€”")
        self._rec_grade_lbl.setStyleSheet(
            f"font-size:11px; font-weight:600; color:{TEXT_SECONDARY};"
            " background:transparent; border:none;"
        )
        self._grade_sparkline = _GradeSparkline()
        self._rec_scan_time_lbl = QLabel("Last scan: â€”")
        self._rec_scan_time_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )
        self._btn_rescan_compact = QPushButton("â–¶  Rescan")
        self._btn_rescan_compact.setFixedHeight(26)
        self._btn_rescan_compact.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_rescan_compact.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{ACCENT}; border:1px solid {ACCENT}44;"
            f" border-radius:4px; font-size:11px; font-weight:600; padding:0 10px; }}"
            f"QPushButton:hover {{ background:{ACCENT}22; border-color:{ACCENT}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        _rec_status_row.addWidget(self._rec_grade_lbl)
        _rec_status_row.addWidget(self._grade_sparkline)
        _rec_status_row.addWidget(self._rec_scan_time_lbl)
        _rec_status_row.addStretch()
        _rec_status_row.addWidget(self._btn_rescan_compact)
        _rec_outer.addLayout(_rec_status_row)

        # Last diagnosis summary row
        _diag_row = QHBoxLayout()
        _diag_row.setSpacing(8)
        self._rec_diag_lbl = QLabel("Last diagnosis:  none yet")
        self._rec_diag_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )
        _diag_open = QPushButton("What's Wrong? â†’")
        _diag_open.setFlat(True)
        _diag_open.setCursor(Qt.CursorShape.PointingHandCursor)
        _diag_open.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; padding:0; }}"
            f"QPushButton:hover {{ color:{ACCENT_DARK}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        _diag_open.clicked.connect(lambda: self.navigate_to.emit("What's Wrong?"))
        _diag_row.addWidget(self._rec_diag_lbl)
        _diag_row.addStretch()
        _diag_row.addWidget(_diag_open)
        _rec_outer.addLayout(_diag_row)

        # HOME-3: live events ticker
        self._events_ticker = _EventsTicker(store=None)
        self._events_ticker.navigate_to.connect(self.navigate_to)
        _rec_outer.addWidget(self._events_ticker)

        # Ã¢â€â‚¬Ã¢â€â‚¬ This Week card (DASH-2) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        self._this_week_card = QFrame()
        self._this_week_card.setObjectName("thisWeekCard")
        self._this_week_card.setStyleSheet(
            f"QFrame#thisWeekCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        self._this_week_card.setVisible(False)
        _tw_outer = QVBoxLayout(self._this_week_card)
        _tw_outer.setContentsMargins(14, 10, 14, 10)
        _tw_outer.setSpacing(6)
        _tw_hdr = QLabel("THIS WEEK")
        _tw_hdr.setStyleSheet(
            f"font-size:10px; font-weight:700; color:{TEXT_SECONDARY};"
            " background:transparent; border:none; letter-spacing:1.5px;"
        )
        _tw_outer.addWidget(_tw_hdr)

        _tw_chips_row = QHBoxLayout()
        _tw_chips_row.setSpacing(8)
        _tw_chips_row.setContentsMargins(0, 0, 0, 0)

        def _tw_chip(color: str) -> tuple[QFrame, QLabel, QLabel]:
            chip = QFrame()
            chip.setObjectName("weekChip")
            chip.setStyleSheet(
                f"QFrame#weekChip {{ background:{BG_DARK}; border:1px solid {BORDER};"
                f" border-radius:6px; }}"
            )
            chip_lay = QVBoxLayout(chip)
            chip_lay.setContentsMargins(10, 6, 10, 6)
            chip_lay.setSpacing(2)
            val_lbl = QLabel("â€”")
            val_lbl.setStyleSheet(
                f"font-size:16px; font-weight:bold; color:{color};"
                " background:transparent; border:none;"
            )
            name_lbl = QLabel()
            name_lbl.setStyleSheet(
                f"font-size:9px; color:{TEXT_MUTED}; background:transparent; border:none;"
            )
            chip_lay.addWidget(val_lbl)
            chip_lay.addWidget(name_lbl)
            return chip, val_lbl, name_lbl

        _tw_c1, self._tw_alerts_val, self._tw_alerts_name = _tw_chip(AMBER)
        _tw_c2, self._tw_devices_val, self._tw_devices_name = _tw_chip(ACCENT)
        _tw_c3, self._tw_grade_val, self._tw_grade_name = _tw_chip(GREEN)
        _tw_c4, self._tw_cve_val, self._tw_cve_name = _tw_chip(RED)

        self._tw_alerts_name.setText("Alerts")
        self._tw_devices_name.setText("New Devices")
        self._tw_grade_name.setText("Grade Change")
        self._tw_cve_name.setText("CVEs")

        for _chip in (_tw_c1, _tw_c2, _tw_c3, _tw_c4):
            _tw_chips_row.addWidget(_chip, 1)

        _tw_outer.addLayout(_tw_chips_row)

        # Grade + This Week side-by-side (POLISH-1)
        _stats_hbox = QHBoxLayout()
        _stats_hbox.setSpacing(10)
        _stats_hbox.addWidget(self._recurring_section, 3)
        _stats_hbox.addWidget(self._this_week_card, 2)
        lay.addLayout(_stats_hbox)

        # Ã¢â€â‚¬Ã¢â€â‚¬ Hero card Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        hero = QFrame()
        hero.setObjectName("heroCard")
        hero.setStyleSheet(
            f"QFrame#heroCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        hero_lay = QHBoxLayout(hero)
        hero_lay.setContentsMargins(16, 16, 16, 16)
        hero_lay.setSpacing(16)

        self._grade_circle = _GradeRing()
        self._grade_circle.setToolTip(
            "Network Grade \u2014 A\u2013F score across 8 health dimensions:\n"
            "Uptime, Latency, Jitter, DNS Speed, Download Speed,\n"
            "Device Safety, STP Health, Broadcast Storm Level.\n"
            "Click (?) to see the full breakdown."
        )
        self._grade_details_btn = QPushButton("?")
        self._grade_details_btn.setFixedSize(20, 18)
        self._grade_details_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._grade_details_btn.setToolTip("Show grade breakdown")
        self._grade_details_btn.setVisible(False)
        self._grade_details_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_SECONDARY}; border:none;"
            f" font-size:10px; border-radius:3px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; background:{BORDER}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_SECONDARY}; }}"
        )
        self._grade_details_btn.clicked.connect(self._show_grade_breakdown)
        # HOME-2: week-over-week grade delta chip
        self._grade_delta_lbl = QLabel("")
        self._grade_delta_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._grade_delta_lbl.setVisible(False)
        self._grade_delta_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )

        _grade_col = QVBoxLayout()
        _grade_col.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        _grade_col.setSpacing(2)
        _grade_col.addWidget(self._grade_circle)
        _grade_col.addWidget(self._grade_delta_lbl, 0, Qt.AlignmentFlag.AlignHCenter)
        _grade_col.addWidget(self._grade_details_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        hero_lay.addLayout(_grade_col)

        right = QVBoxLayout()
        right.setSpacing(4)

        self._hero_title = QLabel("What's on your network?")
        self._hero_title.setStyleSheet(
            f"font-size:14px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        self._hero_sub = QLabel(
            "Discover devices Â· check stability Â· detect threats"
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
            f" background: {ACCENT}; color: {WHITE};"
            f" border: none; border-radius: 4px; padding: 0 14px; }}"
            f"QPushButton:hover {{ background: {ACCENT_DARK}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
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
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_MUTED}; }}"
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

        # Ã¢â€â‚¬Ã¢â€â‚¬ Feature search bar Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        search_card = QFrame()
        search_card.setObjectName("searchCard")
        search_card.setStyleSheet(
            f"QFrame#searchCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        search_outer = QVBoxLayout(search_card)
        search_outer.setContentsMargins(10, 8, 10, 8)
        search_outer.setSpacing(6)

        self._home_search = QLineEdit()
        self._home_search.setPlaceholderText(
            "Search features â€” try 'wifi', 'arp', 'heatmap', 'dns'â€¦"
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
        self._search_results.setObjectName("searchResults")
        self._search_results.setStyleSheet("QFrame#searchResults { background:transparent; border:none; }")
        self._search_results.setVisible(False)
        self._search_results_inner = QVBoxLayout(self._search_results)
        self._search_results_inner.setContentsMargins(0, 2, 0, 0)
        self._search_results_inner.setSpacing(3)
        search_outer.addWidget(self._search_results)

        lay.addWidget(search_card)

        # Ã¢â€â‚¬Ã¢â€â‚¬ Post-scan summary sheet (NUX-2, one-time) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        self._post_scan_sheet = QFrame()
        self._post_scan_sheet.setObjectName("postScanSheet")
        self._post_scan_sheet.setStyleSheet(
            f"QFrame#postScanSheet {{ background:{BG_CARD}; border:1px solid {ACCENT}44;"
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
        _sheet_x = QPushButton("Ãƒâ€”")
        _sheet_x.setFixedSize(20, 20)
        _sheet_x.setCursor(Qt.CursorShape.PointingHandCursor)
        _sheet_x.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none;"
            f" font-size:14px; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_MUTED}; }}"
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
        self._sheet_grade_btn = QPushButton("Run a Network Grade â†’")
        self._sheet_grade_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sheet_grade_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{ACCENT}; border:none;"
            f" font-size:11px; padding:0; }}"
            f"QPushButton:hover {{ color:{ACCENT_DARK}; text-decoration:underline; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        self._sheet_grade_btn.clicked.connect(
            lambda: self.navigate_to.emit("Network Grade")
        )
        _sheet_cta.addWidget(self._sheet_grade_btn)
        self._sheet_action_btn = QPushButton("Set up notifications â†’")
        self._sheet_action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sheet_action_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{ACCENT}; border:none;"
            f" font-size:11px; padding:0; }}"
            f"QPushButton:hover {{ color:{ACCENT_DARK}; text-decoration:underline; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        self._sheet_action_btn.clicked.connect(
            lambda: self.navigate_to.emit(self._sheet_action_target)
        )
        _sheet_cta.addWidget(self._sheet_action_btn)
        _sheet_cta.addStretch()
        _sheet_lay.addLayout(_sheet_cta)
        lay.addWidget(self._post_scan_sheet)

        # Ã¢â€â‚¬Ã¢â€â‚¬ "Three things" section label Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        self._sec1_lbl = QLabel("THE THREE THINGS THAT MATTER")
        self._sec1_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
            " border:none; padding-top:4px; letter-spacing:1px;"
        )
        lay.addWidget(self._sec1_lbl)

        # Ã¢â€â‚¬Ã¢â€â‚¬ Mini-card row â€” three equal-width columns Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        self._mini_cards_widget = QWidget()
        self._mini_cards_widget.setStyleSheet("background:transparent;")
        card_row = QHBoxLayout(self._mini_cards_widget)
        card_row.setContentsMargins(0, 0, 0, 0)
        card_row.setSpacing(8)
        self._speed_card     = _MiniCard("\u26a1", "Speed",     "\u2013", "\u2013")
        self._stability_card = _MiniCard("\u25ce", "Stability", "\u2013", "\u2013")
        self._devices_card   = _MiniCard("\u2295", "Devices",   "\u2013", "\u2013")
        for _card in (self._speed_card, self._stability_card, self._devices_card):
            card_row.addWidget(_card, 1)  # stretch=1 â†’ equal width
        self._speed_card.clicked.connect(
            lambda: self.navigate_to.emit("Speed Test"))
        self._stability_card.clicked.connect(
            lambda: self.navigate_to.emit("DNS & Stability"))
        self._devices_card.clicked.connect(
            lambda: self.navigate_to.emit("Devices"))
        lay.addWidget(self._mini_cards_widget)

        # Ã¢â€â‚¬Ã¢â€â‚¬ Monitoring status pills (NUX-3) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
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
            b = QPushButton(f"â—‹  {label}")
            b.setFixedHeight(22)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton {{ background:{BG_CARD}; color:{TEXT_MUTED}; font-size:10px;"
                f" border:1px solid {BORDER}; border-radius:11px; padding:1px 10px; }}"
                f"QPushButton:hover {{ background:{BG_HOVER}; }}"
                f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
            )
            b.clicked.connect(lambda _=False, t=target: self.navigate_to.emit(t))
            return b

        self._pill_arp    = _pill("ARP Watch",       "ARP Spoof Watch")
        self._pill_dhcp   = _pill("DHCP Watch",      "DHCP Rogue Monitor")
        self._pill_storm  = _pill("Broadcast Storm", "Broadcast Storm")
        self._pill_logger = _pill("Network Logger",  "Network Logger")
        for _p in (self._pill_arp, self._pill_dhcp, self._pill_storm, self._pill_logger):
            _pills_lay.addWidget(_p)
        _pills_lay.addStretch()
        lay.addWidget(self._monitoring_pills_row)

        self._monitoring_nudge = QLabel(
            "Monitoring is off â€” turn it on in 10 seconds â†’"
        )
        self._monitoring_nudge.setVisible(False)
        self._monitoring_nudge.setCursor(Qt.CursorShape.PointingHandCursor)
        self._monitoring_nudge.setStyleSheet(
            f"font-size:11px; color:{ACCENT}; background:transparent;"
            " border:none; padding-top:2px;"
        )
        self._monitoring_nudge.mousePressEvent = (  # type: ignore[method-assign]
            lambda _e: self._scroll_to_setup_card()
        )
        lay.addWidget(self._monitoring_nudge)

        # Ã¢â€â‚¬Ã¢â€â‚¬ Stability monitoring card Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        self._sec_mon_lbl = QLabel("STABILITY MONITORING")
        self._sec_mon_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
            " border:none; padding-top:4px; letter-spacing:1px;"
        )
        lay.addWidget(self._sec_mon_lbl)

        self._mon_card = QFrame()
        self._mon_card.setObjectName("monCard")
        self._mon_card.setStyleSheet(
            f"QFrame#monCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        mon_lay = QHBoxLayout(self._mon_card)
        mon_lay.setContentsMargins(14, 10, 14, 10)
        mon_lay.setSpacing(10)

        self._mon_dot = QLabel("â—Â")
        self._mon_dot.setFixedWidth(12)
        self._mon_dot.setStyleSheet(
            f"font-size:9px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        self._mon_status_lbl = QLabel(
            "Not running â€” start to log connection stability over time."
        )
        self._mon_status_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        self._mon_status_lbl.setWordWrap(True)

        self._btn_mon_start = QPushButton("Start Monitoring")
        self._btn_mon_start.setFixedHeight(28)
        self._btn_mon_start.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:4px; font-size:11px; font-weight:600; padding:0 12px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        self._btn_mon_start.clicked.connect(self.start_monitoring_requested)

        self._btn_mon_view = QPushButton("View Log â†’")
        self._btn_mon_view.setFlat(True)
        self._btn_mon_view.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_mon_view.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px;"
            f" background:transparent; border:none; padding:0; }}"
            f"QPushButton:hover {{ color:{ACCENT_DARK}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        self._btn_mon_view.clicked.connect(lambda: self.navigate_to.emit("Network Logger"))

        mon_lay.addWidget(self._mon_dot)
        mon_lay.addWidget(self._mon_status_lbl, 1)
        mon_lay.addWidget(self._btn_mon_start)
        mon_lay.addWidget(self._btn_mon_view)
        lay.addWidget(self._mon_card)

        # Ã¢â€â‚¬Ã¢â€â‚¬ Post-scan results strip (hidden until first scan completes) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        self._results_strip = QFrame()
        self._results_strip.setObjectName("resultsStrip")
        self._results_strip.setStyleSheet(
            f"QFrame#resultsStrip {{ background:{BG_CARD}; border:1px solid {BORDER}; }}"
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
            dot = QLabel("â—Â")
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
                f"QPushButton:hover {{ color:{ACCENT_DARK}; background:transparent; }}"
                f"QPushButton:pressed {{ color:{ACCENT_DARK}; background:transparent; }}"
            )
            btn.clicked.connect(lambda: self.navigate_to.emit(target))
            rl.addWidget(dot)
            rl.addWidget(lbl, 1)
            rl.addWidget(btn)
            return rw, lbl, dot

        _dev_row, self._res_devices_lbl, self._res_devices_dot = \
            _result_row("â€”", "View Devices â†’", "Devices")
        _conn_row, self._res_conn_lbl, self._res_conn_dot = \
            _result_row("â€”", "View Connection â†’", "DNS & Stability")
        _sec_row, self._res_security_lbl, self._res_security_dot = \
            _result_row("â€”", "View Overview â†’", "Overview")

        _strip_lay.addWidget(_dev_row)
        _strip_lay.addWidget(_conn_row)
        _strip_lay.addWidget(_sec_row)
        lay.addWidget(self._results_strip)

        # Ã¢â€â‚¬Ã¢â€â‚¬ Suggested next steps (hidden until computed) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        self._suggestions_sec = QLabel("WHAT TO DO NEXT")
        self._suggestions_sec.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
            " border:none; padding-top:4px; letter-spacing:1px;"
        )
        self._suggestions_sec.setVisible(False)
        lay.addWidget(self._suggestions_sec)

        self._suggestions_card = QFrame()
        self._suggestions_card.setObjectName("suggestionsCard")
        self._suggestions_card.setStyleSheet(
            f"QFrame#suggestionsCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        self._suggestions_card.setVisible(False)
        self._suggestions_inner = QVBoxLayout(self._suggestions_card)
        self._suggestions_inner.setContentsMargins(12, 8, 12, 8)
        self._suggestions_inner.setSpacing(4)
        lay.addWidget(self._suggestions_card)

        # Ã¢â€â‚¬Ã¢â€â‚¬ Recent alerts section label (+ "View all â†’" in recurring mode) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
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
        self._btn_view_all_alerts = QPushButton("View all â†’")
        self._btn_view_all_alerts.setFlat(True)
        self._btn_view_all_alerts.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_view_all_alerts.setVisible(False)
        self._btn_view_all_alerts.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:10px; background:transparent;"
            f" border:none; padding:0; }}"
            f"QPushButton:hover {{ color:{ACCENT_DARK}; background:transparent; }}"
            f"QPushButton:pressed {{ color:{ACCENT_DARK}; background:transparent; }}"
        )
        self._btn_view_all_alerts.clicked.connect(
            lambda: self.navigate_to.emit("Notifications")
        )
        _ahr_lay.addWidget(self._sec2_lbl)
        _ahr_lay.addStretch()
        _ahr_lay.addWidget(self._btn_view_all_alerts)
        lay.addWidget(self._alerts_hdr_row)

        # Ã¢â€â‚¬Ã¢â€â‚¬ Alert card Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        self._alert_card = QFrame()
        self._alert_card.setObjectName("alertCard")
        self._alert_card.setStyleSheet(
            f"QFrame#alertCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
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
        # Permanent footer â€” always visible; text changes to "No other alerts" once rows appear
        self._no_other_alerts_lbl = QLabel()
        self._no_other_alerts_lbl.setVisible(False)
        self._no_other_alerts_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY};"
            " background:transparent; border:none;"
        )
        self._alert_inner.addWidget(self._no_other_alerts_lbl)
        lay.addWidget(self._alert_card)

        # Ã¢â€â‚¬Ã¢â€â‚¬ Quick tips card (dismissible; hidden once user dismisses) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        self._tips_card = QFrame()
        self._tips_card.setObjectName("tipsCard")
        self._tips_card.setStyleSheet(
            f"QFrame#tipsCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
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
        _tips_x = QPushButton("Ãƒâ€”")
        _tips_x.setFixedSize(18, 18)
        _tips_x.setCursor(Qt.CursorShape.PointingHandCursor)
        _tips_x.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_SECONDARY}; border:none;"
            f" font-size:13px; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; background:transparent; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; background:transparent; }}"
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

        _tips_lay.addWidget(_tip_row("Ã¢Å’Â¨", "Press  Ctrl+K  to open the command palette â€” search any page instantly."))
        _tips_lay.addWidget(_tip_row("Ã°Å¸â€œÅ’", "Right-click any nav item to pin it to the sidebar for quick access."))
        _tips_lay.addWidget(_tip_row("Ã¢Å¡â„¢", "Right-click a device row for quick actions: block, How to Fix, history."))
        self._tip_row_rest_api = _tip_row("Ã°Å¸Å’Â", "Enable the REST API in  Settings â†’ REST API  for a live browser dashboard at localhost:8765/dashboard.")
        _tips_lay.addWidget(self._tip_row_rest_api)

        lay.addWidget(self._tips_card)
        lay.addStretch()

