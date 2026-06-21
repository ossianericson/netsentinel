"""
HomePage � introductory landing page shown in Home mode.

Hero card (network grade), three mini metric cards (speed / stability / devices),
and a recent-alerts strip.

Architecture rules observed:
  � All colours from ui.styles � no hardcoded hex values.
  � No blocking I/O. Pure display widget; all data arrives via public slots.
  � Outer scroll area so the content is never clipped on small windows.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSettings, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
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
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    UPDATE_BAR_BG,
    UPDATE_BAR_BORDER,
    UPDATE_BAR_FG,
    WHITE,
)

from ui.widgets.home_widgets import (
    _GradeRing, _MiniCard, _GradeSparkline, _EventsTicker,
)
from ui.widgets.home_session_widgets import (
    FreshnessStrip, GettingStartedCard,
    StandardWelcomePage, ProWelcomePage,  # noqa: F401 — re-exported for test imports
)
from ui.widgets.health_status_card import HealthStatusCard
from ui.widgets.bandwidth_hog_card import BandwidthHogCard
from ui.widgets.usage_insights_card import UsageInsightsCard
from ui.widgets.weekly_report_card import WeeklyReportCard
from ui.widgets.scan_radar_widget import ScanRadarWidget

__all__ = ["HomePage", "StandardWelcomePage", "ProWelcomePage"]
from ui.pages.home_suggestions import _HomeSuggestionsMixin
from ui.pages.home_data_mixin import _HomeDataMixin


class HomePage(_HomeDataMixin, _HomeSuggestionsMixin, QWidget):
    """Simple landing page for new / Home-mode users."""

    #: Emitted when a mini-card is clicked; carries the target page label string.
    navigate_to = pyqtSignal(str)
    #: Emitted when the user clicks "Start Monitoring" on the stability card.
    start_monitoring_requested = pyqtSignal()
    #: Emitted from GettingStartedCard step 4 — start ARP Watch immediately.
    start_arp_requested = pyqtSignal()
    #: Emitted from GettingStartedCard step 5 — start Network Logger immediately.
    start_logger_requested = pyqtSignal()
    #: Emitted when the user clicks the refresh icon on the freshness strip.
    rescan_requested = pyqtSignal()
    #: Emitted when the user clicks "Investigate →" on a live challenge suggestion.
    investigate_live_requested = pyqtSignal()
    #: Emitted when the user clicks an alert row; carries the raw alert object.
    alert_view_requested = pyqtSignal(object)
    #: Emitted when user clicks "Add" on a hardware checklist step; carries plugin path.
    add_plugin_requested = pyqtSignal(str)
    #: Emitted when the user clicks "Email me this report →" on the weekly report card (S8-3).
    email_weekly_report_requested = pyqtSignal()

    # ── Public slot for ambient health (S2-2) ─────────────────────────────────

    def on_health_update(self, snapshot) -> None:
        """Delegate HealthWorker results to the ambient health card."""
        if hasattr(self, "_health_card"):
            self._health_card.on_health_update(snapshot)

    # ── Public slot for bandwidth hog card (S5-4) ─────────────────────────────

    def on_bandwidth_update(self, payload: dict) -> None:
        """Delegate AppTrafficPage.top_host_changed results to the bandwidth card."""
        if hasattr(self, "_bandwidth_card"):
            self._bandwidth_card.on_bandwidth_update(payload)

    # ── Constructor ───────────────────────────────────────────────────────────

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

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_hw_nudge()
        if hasattr(self, "_usage_card"):
            self._usage_card.refresh()

    # ── Hardware nudge ────────────────────────────────────────────────────────

    def _build_hw_nudge_bar(self) -> "QFrame":
        from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton
        from PyQt6.QtCore import Qt
        bar = QFrame()
        bar.setObjectName("hwNudgeBar")
        bar.setStyleSheet(
            f"QFrame#hwNudgeBar {{ background:{BG_HOVER}; border-bottom:1px solid {BORDER}; }}"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 6, 10, 6)
        lay.setSpacing(10)
        _icon = QLabel("⬡")
        _icon.setFixedWidth(18)
        _icon.setStyleSheet(
            f"font-size:12px; color:{ACCENT}; background:transparent; border:none;"
        )
        _text = QLabel(
            "Optional: connect your router or modem to see real device names and signal data — works without it."
        )
        _text.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent; border:none;"
        )
        _btn = QPushButton("Set up Hardware →")
        _btn.setFixedHeight(24)
        _btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; font-size:11px;"
            f" border:none; border-radius:3px; padding:0 10px; }}"
            f"QPushButton:hover   {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
        )
        _btn.clicked.connect(lambda: self.navigate_to.emit("Hardware"))
        _dismiss = QPushButton("✕")
        _dismiss.setFixedSize(20, 20)
        _dismiss.setFlat(True)
        _dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        _dismiss.setStyleSheet(
            f"QPushButton {{ color:{TEXT_SECONDARY}; background:transparent; border:none; font-size:10px; }}"
            f"QPushButton:hover   {{ color:{TEXT_PRIMARY}; background:transparent; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; background:transparent; }}"
        )
        _dismiss.setToolTip("Dismiss")
        _dismiss.clicked.connect(self._dismiss_hw_nudge)
        lay.addWidget(_icon)
        lay.addWidget(_text, 1)
        lay.addWidget(_btn)
        lay.addWidget(_dismiss)
        bar.setVisible(False)
        return bar

    def _refresh_hw_nudge(self) -> None:
        import json as _json
        bar = getattr(self, "_hw_nudge_bar", None)
        if bar is None:
            return
        qs = QSettings("NetSentinel", "NetSentinel")
        if not qs.value("ui/onboarding_v2_done", False, type=bool):
            bar.setVisible(False)
            return
        if qs.value("ui/hw_nudge_dismissed", False, type=bool):
            bar.setVisible(False)
            return
        configured = False
        try:
            raw = qs.value("hardware/custom_scripts", "[]") or "[]"
            configured = len(_json.loads(raw)) > 0
        except Exception:
            pass  # non-fatal — check the instances key below
        if not configured:
            try:
                raw2 = qs.value("hardware/instances", None)
                configured = bool(raw2 and _json.loads(raw2))
            except Exception:
                pass  # non-fatal — malformed QSettings value
        bar.setVisible(not configured)

    def _dismiss_hw_nudge(self) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue("ui/hw_nudge_dismissed", True)
        bar = getattr(self, "_hw_nudge_bar", None)
        if bar:
            bar.setVisible(False)

    def _build_tip_card(
        self, icon: str, name: str, desc_first: str, page: "str | None", dismissed_key: str
    ) -> "QWidget":
        bar = QFrame()
        bar.setObjectName("tipCard")
        bar.setStyleSheet(
            f"QFrame#tipCard {{ background:{BG_HOVER}; border:1px solid {BORDER};"
            f" border-radius:4px; }}"
        )
        _lay = QHBoxLayout(bar)
        _lay.setContentsMargins(10, 4, 8, 4)
        _lay.setSpacing(8)
        _icon_lbl = QLabel(icon)
        _icon_lbl.setFixedWidth(16)
        _icon_lbl.setStyleSheet(
            f"font-size:11px; color:{ACCENT}; background:transparent; border:none;"
        )
        _hdr = QLabel("Did you know?")
        _hdr.setStyleSheet(
            f"font-size:10px; font-weight:bold; color:{TEXT_SECONDARY};"
            " background:transparent; border:none;"
        )
        _txt = QLabel(f"{name} — {desc_first}")
        _txt.setStyleSheet(
            f"font-size:10px; color:{TEXT_PRIMARY}; background:transparent; border:none;"
        )
        _lay.addWidget(_icon_lbl)
        _lay.addWidget(_hdr)
        _lay.addSpacing(2)
        _lay.addWidget(_txt, 1)
        if page:
            _go = QPushButton("Open →")
            _go.setFixedHeight(20)
            _go.setCursor(Qt.CursorShape.PointingHandCursor)
            _go.setStyleSheet(
                f"QPushButton {{ background:transparent; color:{ACCENT}; font-size:9px;"
                f" border:1px solid {ACCENT}; border-radius:3px; padding:0 6px; }}"
                f"QPushButton:hover {{ background:{BG_HOVER}; color:{ACCENT}; }}"
                f"QPushButton:pressed {{ background:{BORDER}; color:{TEXT_PRIMARY}; }}"
            )
            _go.clicked.connect(lambda _=False, p=page: self.navigate_to.emit(p))
            _lay.addWidget(_go)
        _dismiss = QPushButton("✕")
        _dismiss.setFixedSize(18, 18)
        _dismiss.setFlat(True)
        _dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        _dismiss.setStyleSheet(
            f"QPushButton {{ color:{TEXT_SECONDARY}; background:transparent; border:none; font-size:9px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; background:transparent; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; background:transparent; }}"
        )

        def _on_dismiss(_bar=bar) -> None:
            from datetime import datetime
            QSettings("NetSentinel", "NetSentinel").setValue(
                dismissed_key, datetime.now().isoformat()
            )
            self._tip_card_dismissed = True
            _bar.setVisible(False)

        _dismiss.clicked.connect(_on_dismiss)
        _lay.addWidget(_dismiss)
        return bar

    def _setup_ui(self) -> None:
        self.setObjectName("homePageRoot")
        self.setStyleSheet(f"QWidget#homePageRoot {{ background:{BG_DARK}; }}")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Hardware nudge (post-onboarding, until first plugin configured) ──
        self._hw_nudge_bar = self._build_hw_nudge_bar()
        outer.addWidget(self._hw_nudge_bar)
        # ─────────────────────────────────────────────────────────────────────

        # ── Freshness strip � always visible above scroll area ────────────────
        self._freshness_strip = FreshnessStrip()
        self._freshness_strip.rescan_requested.connect(self.rescan_requested)
        self._freshness_strip.navigate_to.connect(self.navigate_to)
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

        # ── S2-2: Ambient health status card (always visible, updates every 60s) ──
        self._health_card = HealthStatusCard()
        self._health_card.navigate_to.connect(self.navigate_to)
        lay.addWidget(self._health_card)

        # ── S5-4: "Who's hogging bandwidth?" card ──────────────────────────────
        self._bandwidth_card = BandwidthHogCard()
        self._bandwidth_card.navigate_to.connect(self.navigate_to)
        lay.addWidget(self._bandwidth_card)

        # ── S6-3: "Usage insights" card — household traffic narrative ─────────
        self._usage_card = UsageInsightsCard(store=self._store)
        self._usage_card.navigate_to.connect(self.navigate_to)
        lay.addWidget(self._usage_card)

        # ── S8-3: "Your Network Last Week" card — shown once per calendar week ─
        self._weekly_report_card = WeeklyReportCard(store=self._store)
        self._weekly_report_card.navigate_to.connect(self.navigate_to)
        self._weekly_report_card.email_requested.connect(self.email_weekly_report_requested)
        lay.addWidget(self._weekly_report_card)

        # ── Browser dashboard strip (visible when API enabled + not dismissed) ─
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
        _ds_icon = QLabel("�")
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
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:3px; font-size:11px; padding:0 8px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        _ds_open.clicked.connect(self._open_dashboard)
        _ds_dismiss = QPushButton("�")
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

        # ── GETTING STARTED checklist (replaces separate hw strip) ──────────────
        _already_done = QSettings("NetSentinel", "NetSentinel").value(
            "setup/all_done", False, type=bool
        )
        self._setup_card_top = GettingStartedCard()
        self._setup_card_top.add_plugin_requested.connect(self.add_plugin_requested)
        self._setup_card_top.navigate_to.connect(self.navigate_to)
        self._setup_card_top.completion_done.connect(self._on_setup_complete)
        self._setup_card_top.start_arp_requested.connect(self.start_arp_requested)
        self._setup_card_top.start_logger_requested.connect(self.start_logger_requested)
        # Skip the checklist immediately on subsequent launches once setup is done
        if _already_done:
            self._setup_card_top.setVisible(False)
        lay.addWidget(self._setup_card_top)

        # ── Setup completion celebration card (shown when all steps done) ──────
        self._setup_complete_card = QFrame()
        self._setup_complete_card.setObjectName("setupCompleteCard")
        self._setup_complete_card.setStyleSheet(
            f"QFrame#setupCompleteCard {{ background:{BG_CARD};"
            f" border:1px solid {GREEN}44; border-left:3px solid {GREEN};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        self._setup_complete_card.setVisible(_already_done)
        _sc_lay = QVBoxLayout(self._setup_complete_card)
        _sc_lay.setContentsMargins(14, 12, 14, 12)
        _sc_lay.setSpacing(6)
        _sc_title = QLabel("✓  Setup complete — you're ready to go")
        _sc_title.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{GREEN};"
            " background:transparent; border:none;"
        )
        _sc_sub = QLabel(
            "NetSentinel has 60+ tools — the Feature Guide is the quickest way "
            "to find what to explore next."
        )
        _sc_sub.setWordWrap(True)
        _sc_sub.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        _sc_btn_row = QHBoxLayout()
        _sc_btn_row.setSpacing(16)
        _sc_explore = QPushButton("Explore features →")
        _sc_explore.setFlat(True)
        _sc_explore.setCursor(Qt.CursorShape.PointingHandCursor)
        _sc_explore.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; padding:0; }}"
            f"QPushButton:hover {{ color:{ACCENT_DARK}; background:transparent; }}"
            f"QPushButton:pressed {{ color:{ACCENT_DARK}; background:transparent; }}"
        )
        _sc_explore.clicked.connect(lambda: self.navigate_to.emit("Feature Guide"))
        _sc_summary = QPushButton("View this week’s summary →")
        _sc_summary.setFlat(True)
        _sc_summary.setCursor(Qt.CursorShape.PointingHandCursor)
        _sc_summary.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; padding:0; }}"
            f"QPushButton:hover {{ color:{ACCENT_DARK}; background:transparent; }}"
            f"QPushButton:pressed {{ color:{ACCENT_DARK}; background:transparent; }}"
        )
        _sc_summary.clicked.connect(lambda: self.navigate_to.emit("Dashboard"))
        _sc_advanced = QPushButton("Advanced settings →")
        _sc_advanced.setFlat(True)
        _sc_advanced.setCursor(Qt.CursorShape.PointingHandCursor)
        _sc_advanced.setToolTip(
            "SMTP, SNMP, API keys and other technical configuration live here — "
            "optional, and never required to use NetSentinel."
        )
        _sc_advanced.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; padding:0; }}"
            f"QPushButton:hover {{ color:{ACCENT_DARK}; background:transparent; }}"
            f"QPushButton:pressed {{ color:{ACCENT_DARK}; background:transparent; }}"
        )
        _sc_advanced.clicked.connect(lambda: self.navigate_to.emit("Settings"))
        _sc_btn_row.addWidget(_sc_explore)
        _sc_btn_row.addWidget(_sc_summary)
        _sc_btn_row.addWidget(_sc_advanced)
        _sc_btn_row.addStretch()
        _sc_lay.addWidget(_sc_title)
        _sc_lay.addWidget(_sc_sub)
        _sc_lay.addLayout(_sc_btn_row)
        lay.addWidget(self._setup_complete_card)

        # ── Since you were last here (hidden until data loaded) ───────────────
        # S9-6: reused for both the routine "since last visit" note and the
        # more prominent 7+ day "welcome back" recovery card — style/icon/title
        # are swapped at runtime by _apply_last_visit_style() rather than
        # building a second widget.
        self._last_visit_card = QFrame()
        self._last_visit_card.setObjectName("lastVisitCard")
        self._last_visit_card.setVisible(False)
        lv_lay = QHBoxLayout(self._last_visit_card)
        lv_lay.setContentsMargins(12, 8, 12, 8)
        lv_lay.setSpacing(10)
        self._lv_icon = QLabel("◷")
        self._lv_icon.setFixedWidth(20)
        lv_text_col = QVBoxLayout()
        lv_text_col.setSpacing(1)
        self._lv_title = QLabel("")
        self._lv_title.setVisible(False)
        self._lv_text = QLabel("")
        self._lv_text.setWordWrap(True)
        lv_text_col.addWidget(self._lv_title)
        lv_text_col.addWidget(self._lv_text)
        lv_lay.addWidget(self._lv_icon)
        lv_lay.addLayout(lv_text_col, 1)
        self._apply_last_visit_style(prominent=False)
        lay.addWidget(self._last_visit_card)

        # ── First-scan guidance (one-time, after very first scan) ─────────────
        self._first_scan_banner = QFrame()
        self._first_scan_banner.setObjectName("firstScanBanner")
        self._first_scan_banner.setStyleSheet(
            f"QFrame#firstScanBanner {{ background:{BG_CARD};"
            f" border:1px solid {GREEN}44; border-left:3px solid {GREEN};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        self._first_scan_banner.setVisible(False)
        _fsb_outer = QVBoxLayout(self._first_scan_banner)
        _fsb_outer.setContentsMargins(14, 10, 14, 10)
        _fsb_outer.setSpacing(6)
        _fsb_top = QHBoxLayout()
        _fsb_top.setSpacing(0)
        self._first_scan_lbl = QLabel("First scan complete — here's where to look:")
        self._first_scan_lbl.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        _fsb_dismiss = QPushButton("✕")
        _fsb_dismiss.setFixedSize(20, 20)
        _fsb_dismiss.setFlat(True)
        _fsb_dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        _fsb_dismiss.setStyleSheet(
            f"QPushButton {{ color:{TEXT_MUTED}; background:transparent; border:none;"
            f" font-size:10px; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; background:transparent; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; background:transparent; }}"
        )
        _fsb_dismiss.clicked.connect(self._dismiss_first_scan_banner)
        _fsb_top.addWidget(self._first_scan_lbl, 1)
        _fsb_top.addWidget(_fsb_dismiss)
        _fsb_outer.addLayout(_fsb_top)
        _fsb_btns = QHBoxLayout()
        _fsb_btns.setSpacing(8)
        for _flbl, _fpg in (
            ("◎  Dashboard", "Dashboard"),
            ("◎  Devices", "Devices"),
            ("◎  What's Wrong?", "What's Wrong?"),
        ):
            _fb = QPushButton(_flbl)
            _fb.setFixedHeight(26)
            _fb.setCursor(Qt.CursorShape.PointingHandCursor)
            _fb.setStyleSheet(
                f"QPushButton {{ background:{ACCENT}; color:{WHITE}; font-size:11px;"
                f" border:none; border-radius:3px; padding:0 10px; }}"
                f"QPushButton:hover {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
                f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
            )
            _fb.clicked.connect(lambda _=False, p=_fpg: self.navigate_to.emit(p))
            _fsb_btns.addWidget(_fb)
        _fsb_btns.addStretch()
        _fsb_outer.addLayout(_fsb_btns)
        lay.addWidget(self._first_scan_banner)

        # ── DASH-1: "Action needed" card ─────────────────────────────────────
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
        _ac_hdr_lbl = QLabel("⚠  Action needed")
        _ac_hdr_lbl.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{RED};"
            " background:transparent; border:none;"
        )
        _ac_hdr_row.addWidget(_ac_hdr_lbl)
        _ac_hdr_row.addStretch()
        _ac_outer.addLayout(_ac_hdr_row)

        # ── ALERT-3: per-alert rows with inline ack ───────────────────────────
        self._ac_alert_rows_widget = QWidget()
        self._ac_alert_rows_widget.setStyleSheet("background:transparent;")
        self._ac_alert_rows_lay = QVBoxLayout(self._ac_alert_rows_widget)
        self._ac_alert_rows_lay.setContentsMargins(0, 0, 0, 0)
        self._ac_alert_rows_lay.setSpacing(2)
        self._ac_alert_rows_widget.setVisible(False)
        _ac_outer.addWidget(self._ac_alert_rows_widget)

        self._ac_view_all_btn = QPushButton("View all alerts →")
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

        # ── Offline devices row (separate concern, unchanged) ─────────────────
        _ac_devices_row = QHBoxLayout()
        _ac_devices_row.setSpacing(8)
        self._ac_devices_lbl = QLabel("")
        self._ac_devices_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        _ac_devices_btn = QPushButton("View Devices →")
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

        # ── Post-scan delta banner (hidden until 2nd+ scan) ───────────────────
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
        _db_dismiss = QPushButton("�")
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

        # ── Milestone banner (hidden until a milestone is reached) ────────────
        self._milestone_banner = QFrame()
        self._milestone_banner.setObjectName("milestoneBanner")
        self._milestone_banner.setStyleSheet(
            f"QFrame#milestoneBanner {{ background:{BG_CARD};"
            f" border:1px solid {BORDER}; border-left:3px solid {ACCENT};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        self._milestone_banner.setVisible(False)
        _mb_lay = QHBoxLayout(self._milestone_banner)
        _mb_lay.setContentsMargins(12, 8, 8, 8)
        _mb_lay.setSpacing(10)
        self._milestone_lbl = QLabel("")
        self._milestone_lbl.setWordWrap(True)
        self._milestone_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent; border:none;"
        )
        _mb_dismiss = QPushButton("×")
        _mb_dismiss.setFixedSize(20, 20)
        _mb_dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        _mb_dismiss.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none;"
            f" font-size:14px; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_MUTED}; }}"
        )
        _mb_dismiss.clicked.connect(lambda: self._milestone_banner.setVisible(False))
        _mb_lay.addWidget(self._milestone_lbl, 1)
        _mb_lay.addWidget(_mb_dismiss)
        lay.addWidget(self._milestone_banner)

        # ── Recurring-user top section (hidden until conditions met) ──────────
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

        # Pill row � separate instances synced by set_monitor_pills()
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
                f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
            )
            b.clicked.connect(lambda _=False, t=target: self.navigate_to.emit(t))
            return b

        self._rec_pill_arp    = _rec_pill("ARP Watch",       "ARP Spoof Watch")
        self._rec_pill_dhcp   = _rec_pill("DHCP Watch",      "DHCP Rogue Monitor")
        self._rec_pill_storm  = _rec_pill("Broadcast Storm", "Broadcast Storm")
        self._rec_pill_logger = _rec_pill("Network Logger",  "Network Logger")
        self._rec_pill_arp.setToolTip(
            "ARP Watch monitors for MAC address impersonation (ARP spoofing).\n"
            "Attackers use this to intercept traffic on your network.\n"
            "Click to open ARP Spoof Watch and enable monitoring."
        )
        self._rec_pill_dhcp.setToolTip(
            "DHCP Watch detects rogue DHCP servers that could redirect your traffic.\n"
            "A rogue server assigns itself as your DNS, intercepting all lookups.\n"
            "Click to open DHCP Rogue Monitor."
        )
        self._rec_pill_storm.setToolTip(
            "Broadcast Storm monitor listens for flood-level broadcast traffic\n"
            "that can slow or freeze your entire network.\n"
            "Requires Npcap and administrator rights. Click to open."
        )
        self._rec_pill_logger.setToolTip(
            "Network Logger records your connection stability (RTT, jitter, packet loss)\n"
            "continuously in the background. Start it once to build a history timeline.\n"
            "Click to open Network Logger and start recording."
        )
        for _rp in (self._rec_pill_arp, self._rec_pill_dhcp,
                    self._rec_pill_storm, self._rec_pill_logger):
            _rec_pills_row.addWidget(_rp)
        _rec_pills_row.addStretch()
        _rec_outer.addLayout(_rec_pills_row)

        # Grade + last scan + rescan row
        _rec_status_row = QHBoxLayout()
        _rec_status_row.setSpacing(12)
        _rec_status_row.setContentsMargins(0, 0, 0, 0)
        self._rec_grade_lbl = QLabel("Network Grade: �")
        self._rec_grade_lbl.setStyleSheet(
            f"font-size:11px; font-weight:600; color:{TEXT_SECONDARY};"
            " background:transparent; border:none;"
        )
        self._grade_sparkline = _GradeSparkline()
        self._rec_scan_time_lbl = QLabel("Last scan: �")
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
        _diag_open = QPushButton("What's Wrong? →")
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

        # ── This Week card (DASH-2) ───────────────────────────────────────────
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
            val_lbl = QLabel("�")
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

        # ── Recurring mode intro card (one-time, shown when layout first activates) ──
        self._recurring_intro_card = QFrame()
        self._recurring_intro_card.setObjectName("recurringIntroCard")
        self._recurring_intro_card.setStyleSheet(
            f"QFrame#recurringIntroCard {{ background:{BG_CARD};"
            f" border:1px solid {BORDER}; border-left:3px solid {ACCENT};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        self._recurring_intro_card.setVisible(False)
        _ri_outer = QHBoxLayout(self._recurring_intro_card)
        _ri_outer.setContentsMargins(12, 10, 8, 10)
        _ri_outer.setSpacing(10)
        _ri_icon = QLabel("⬡")
        _ri_icon.setFixedWidth(20)
        _ri_icon.setStyleSheet(
            f"font-size:14px; color:{ACCENT}; background:transparent; border:none;"
        )
        _ri_text_col = QVBoxLayout()
        _ri_text_col.setSpacing(2)
        _ri_title = QLabel("Home page upgraded")
        _ri_title.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        _ri_body = QLabel(
            "You've run 5 scans — great work. The home page now shows your monitoring "
            "status and this week's activity summary. Your devices and grade history are "
            "still in the Discover and Reports sections. Press Ctrl+K to find any page instantly."
        )
        _ri_body.setWordWrap(True)
        _ri_body.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        _ri_text_col.addWidget(_ri_title)
        _ri_text_col.addWidget(_ri_body)
        _ri_x = QPushButton("×")
        _ri_x.setFixedSize(20, 20)
        _ri_x.setCursor(Qt.CursorShape.PointingHandCursor)
        _ri_x.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none;"
            f" font-size:14px; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; background:transparent; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; background:transparent; }}"
        )
        _ri_x.clicked.connect(self._dismiss_recurring_intro)
        _ri_outer.addWidget(_ri_icon)
        _ri_outer.addLayout(_ri_text_col, 1)
        _ri_outer.addWidget(_ri_x)
        lay.addWidget(self._recurring_intro_card)

        # Grade + This Week side-by-side (POLISH-1)
        _stats_hbox = QHBoxLayout()
        _stats_hbox.setSpacing(10)
        _stats_hbox.addWidget(self._recurring_section, 3)
        _stats_hbox.addWidget(self._this_week_card, 2)
        lay.addLayout(_stats_hbox)

        # ── Live challenge banner (hidden until Network Logger detects an anomaly) ───
        self._live_challenge_banner = QFrame()
        self._live_challenge_banner.setObjectName("liveChallengeBar")
        self._live_challenge_banner.setStyleSheet(
            f"QFrame#liveChallengeBar {{ background:{AMBER}22; border:1px solid {AMBER}88;"
            f" border-left:3px solid {AMBER}; border-radius:{CARD_RADIUS}; }}"
        )
        self._live_challenge_banner.setVisible(False)
        _lc_lay = QHBoxLayout(self._live_challenge_banner)
        _lc_lay.setContentsMargins(12, 8, 8, 8)
        _lc_lay.setSpacing(8)
        _lc_icon = QLabel("▲")
        _lc_icon.setFixedWidth(16)
        _lc_icon.setStyleSheet(
            f"font-size:11px; color:{AMBER}; background:transparent; border:none;"
        )
        self._lc_text = QLabel("")
        self._lc_text.setWordWrap(True)
        self._lc_text.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent; border:none;"
        )
        _lc_diagnose = QPushButton("Diagnose now →")
        _lc_diagnose.setFixedHeight(24)
        _lc_diagnose.setCursor(Qt.CursorShape.PointingHandCursor)
        _lc_diagnose.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{AMBER}; font-size:11px;"
            f" border:1px solid {AMBER}88; border-radius:3px; padding:0 8px; }}"
            f"QPushButton:hover {{ background:{AMBER}22; color:{AMBER}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{AMBER}; }}"
        )
        _lc_dismiss = QPushButton("×")
        _lc_dismiss.setFixedSize(20, 20)
        _lc_dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        _lc_dismiss.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none;"
            f" font-size:14px; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_MUTED}; }}"
        )
        _lc_diagnose.clicked.connect(lambda: self.navigate_to.emit("What's Wrong?"))
        _lc_dismiss.clicked.connect(lambda: self._live_challenge_banner.setVisible(False))
        _lc_lay.addWidget(_lc_icon)
        _lc_lay.addWidget(self._lc_text, 1)
        _lc_lay.addWidget(_lc_diagnose)
        _lc_lay.addWidget(_lc_dismiss)
        lay.addWidget(self._live_challenge_banner)

        # ── Hero card ─────────────────────────────────────────────────────────
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
            "Discover devices � check stability � detect threats"
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
        # Inline radar + progress label — shown only while scanning
        self._radar = ScanRadarWidget()
        self._radar.setFixedSize(54, 54)
        self._radar.setVisible(False)

        self._scan_progress_lbl = QLabel("")
        self._scan_progress_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY};"
            " background:transparent; border:none;"
        )
        self._scan_progress_lbl.setVisible(False)

        btn_row.addWidget(self._btn_scan)
        btn_row.addWidget(self._btn_diagnose)
        btn_row.addSpacing(8)
        btn_row.addWidget(self._radar)
        btn_row.addSpacing(4)
        btn_row.addWidget(self._scan_progress_lbl)
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

        # Insert hero card at position 3 (after _dashboard_strip / _setup_card_top /
        # _setup_complete_card) so the grade ring and CTA buttons are always
        # visible near the top of the page before any contextual banners.
        lay.insertWidget(3, hero)

        # ── Feature search bar ────────────────────────────────────────────────
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
            "Search features � try 'wifi', 'arp', 'heatmap', 'dns'�"
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

        # ── Post-scan summary sheet (NUX-2, one-time) ─────────────────────────
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
        _sheet_x = QPushButton("�")
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
        self._sheet_grade_btn = QPushButton("Run a Network Grade →")
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
        self._sheet_action_btn = QPushButton("Set up notifications →")
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

        # ── "Three things" section label ──────────────────────────────────────
        self._sec1_lbl = QLabel("THE THREE THINGS THAT MATTER")
        self._sec1_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
            " border:none; padding-top:4px; letter-spacing:1px;"
        )
        lay.addWidget(self._sec1_lbl)

        # ── Mini-card row � three equal-width columns ────────────────────────
        self._mini_cards_widget = QWidget()
        self._mini_cards_widget.setStyleSheet("background:transparent;")
        card_row = QHBoxLayout(self._mini_cards_widget)
        card_row.setContentsMargins(0, 0, 0, 0)
        card_row.setSpacing(8)
        self._speed_card     = _MiniCard("\u26a1", "Speed",     "\u2013", "\u2013")
        self._stability_card = _MiniCard("\u25ce", "Stability", "\u2013", "\u2013")
        self._devices_card   = _MiniCard("\u2295", "Devices",   "\u2013", "\u2013")
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
                f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
            )
            b.clicked.connect(lambda _=False, t=target: self.navigate_to.emit(t))
            return b

        self._pill_arp    = _pill("ARP Watch",       "ARP Spoof Watch")
        self._pill_dhcp   = _pill("DHCP Watch",      "DHCP Rogue Monitor")
        self._pill_storm  = _pill("Broadcast Storm", "Broadcast Storm")
        self._pill_logger = _pill("Network Logger",  "Network Logger")
        self._pill_arp.setToolTip(
            "ARP Watch monitors for MAC address impersonation (ARP spoofing).\n"
            "Attackers use this to intercept traffic on your network.\n"
            "Click to open ARP Spoof Watch and enable monitoring."
        )
        self._pill_dhcp.setToolTip(
            "DHCP Watch detects rogue DHCP servers that could redirect your traffic.\n"
            "A rogue server assigns itself as your DNS, intercepting all lookups.\n"
            "Click to open DHCP Rogue Monitor."
        )
        self._pill_storm.setToolTip(
            "Broadcast Storm monitor listens for flood-level broadcast traffic\n"
            "that can slow or freeze your entire network.\n"
            "Requires Npcap and administrator rights. Click to open."
        )
        self._pill_logger.setToolTip(
            "Network Logger records your connection stability (RTT, jitter, packet loss)\n"
            "continuously in the background. Start it once to build a history timeline.\n"
            "Click to open Network Logger and start recording."
        )
        for _p in (self._pill_arp, self._pill_dhcp, self._pill_storm, self._pill_logger):
            _pills_lay.addWidget(_p)
        _pills_lay.addStretch()
        lay.addWidget(self._monitoring_pills_row)

        # Persistent hint label below pills (always visible with the pills row)
        self._monitoring_pills_hint = QLabel(
            "Continuous monitors — click any pill to configure"
        )
        self._monitoring_pills_hint.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        lay.addWidget(self._monitoring_pills_hint)

        # ── "Did you know?" rotating tip card ────────────────────────────────
        try:
            from ui.pages.discover_data import _FEATURES as _feat_data
            _tips = [f for f in _feat_data if f.get("group") == "Hidden features"]
        except Exception:
            _tips = []

        if _tips:
            _qs = QSettings("NetSentinel", "NetSentinel")
            _tip_idx = int(_qs.value("home/tip_session_index", 0))
            _tip = _tips[_tip_idx % len(_tips)]
            _dismissed_key = f"home/tip_{_tip_idx}_dismissed"
            _qs.setValue("home/tip_session_index", (_tip_idx + 1) % len(_tips))
            _tip_ts = _qs.value(_dismissed_key, None)
            if _tip_ts is None:
                self._tip_card_dismissed = False
            else:
                try:
                    from datetime import datetime
                    _dismissed_at = datetime.fromisoformat(str(_tip_ts))
                    self._tip_card_dismissed = (datetime.now() - _dismissed_at).days < 7
                except Exception:
                    self._tip_card_dismissed = True  # legacy bool True — treat as dismissed
            self._tip_card = self._build_tip_card(
                _tip.get("icon", "⬡"),
                _tip["name"],
                _tip["desc"].split(".")[0],
                _tip.get("page"),
                _dismissed_key,
            )
        else:
            self._tip_card_dismissed = True
            self._tip_card = QWidget()

        self._tip_card.setVisible(False)  # _set_first_run_mode shows it when data exists
        lay.addWidget(self._tip_card)

        _nudge_row = QHBoxLayout()
        _nudge_row.setContentsMargins(0, 2, 0, 0)
        _nudge_row.setSpacing(8)
        self._monitoring_nudge = QLabel("Monitoring is off.")
        self._monitoring_nudge.setVisible(False)
        self._monitoring_nudge.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;"
            " border:none;"
        )
        _nudge_row.addWidget(self._monitoring_nudge)
        self._btn_start_logger = QPushButton("▶  Start Network Logger")
        self._btn_start_logger.setFixedHeight(22)
        self._btn_start_logger.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_start_logger.setVisible(False)
        self._btn_start_logger.setToolTip(
            "Start the Network Logger to record connection stability in the background.\n"
            "It logs RTT, jitter, and packet loss continuously so you can spot patterns."
        )
        self._btn_start_logger.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{ACCENT}; font-size:10px;"
            f" border:1px solid {ACCENT}; border-radius:11px; padding:1px 10px; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        self._btn_start_logger.clicked.connect(self.start_monitoring_requested)
        _nudge_row.addWidget(self._btn_start_logger)
        _nudge_row.addStretch()
        lay.addLayout(_nudge_row)

        # ── Stability monitoring card ─────────────────────────────────────────
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

        self._mon_dot = QLabel("●")
        self._mon_dot.setFixedWidth(12)
        self._mon_dot.setStyleSheet(
            f"font-size:9px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        self._mon_status_lbl = QLabel(
            "Not running � start to log connection stability over time."
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

        self._btn_mon_view = QPushButton("View Log →")
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

        # ── Post-scan results strip (hidden until first scan completes) ────────
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
                f"QPushButton:hover {{ color:{ACCENT_DARK}; background:transparent; }}"
                f"QPushButton:pressed {{ color:{ACCENT_DARK}; background:transparent; }}"
            )
            btn.clicked.connect(lambda: self.navigate_to.emit(target))
            rl.addWidget(dot)
            rl.addWidget(lbl, 1)
            rl.addWidget(btn)
            return rw, lbl, dot

        _dev_row, self._res_devices_lbl, self._res_devices_dot = \
            _result_row("�", "View Devices →", "Devices")
        _conn_row, self._res_conn_lbl, self._res_conn_dot = \
            _result_row("�", "View Connection →", "DNS & Stability")
        _sec_row, self._res_security_lbl, self._res_security_dot = \
            _result_row("�", "View Dashboard →", "Dashboard")

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

        # ── Alert card ────────────────────────────────────────────────────────
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
        # Permanent footer � always visible; text changes to "No other alerts" once rows appear
        self._no_other_alerts_lbl = QLabel()
        self._no_other_alerts_lbl.setVisible(False)
        self._no_other_alerts_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY};"
            " background:transparent; border:none;"
        )
        self._alert_inner.addWidget(self._no_other_alerts_lbl)
        lay.addWidget(self._alert_card)

        lay.addStretch()

