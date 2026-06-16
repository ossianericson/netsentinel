"""
SettingsPage — Application settings and customisation hub.

This is the primary place for all user-facing customisation:
  - Colour theme picker (front-and-centre)
  - Display preferences
  - Keyboard-shortcut reminder

Architecture rules observed:
  • All colours from ui/styles — no hardcoded hex values.
  • No blocking I/O on the main thread.
  • QSettings used for persistence (same org/app as rest of codebase).
"""
from __future__ import annotations


from PyQt6.QtCore import Qt, QSettings, pyqtSignal
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT, AMBER, BG_CARD, BG_DARK, BORDER,
    TEXT_MUTED, TEXT_PRIMARY,
)

from ui.pages.settings_cards import (
    _card,
    _SettingsCardsMixin,
    _NotifTestWorker,
)

class SettingsPage(_SettingsCardsMixin, QWidget):
    """
    Dedicated settings and customisation page shown in the sidebar.
    Contains the theme picker, display preferences, and shortcuts reference.
    """

    #: Emitted when the user clicks "Reload OUI database" in the Maintenance card.
    reload_oui_requested = pyqtSignal()
    #: Emitted when the user clicks "Reset all dismissed notices".
    reset_dismissed_requested = pyqtSignal()
    #: Emitted when "Export All Data" is clicked; dashboard handles the store reference.
    export_all_requested = pyqtSignal()
    #: Emitted when "Run first-time setup" is clicked; dashboard resets state and navigates.
    run_setup_requested = pyqtSignal()
    #: Emitted when "Configure →" is clicked in the integrations card.
    navigate_to = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._dirty = False
        self._all_cards: list[tuple[QFrame, str]] = []
        self._notif_test_workers: list[_NotifTestWorker] = []  # prevent GC

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header with dirty indicator
        hdr_container = QFrame()
        hdr_container.setStyleSheet(
            f"QFrame {{ background:transparent; border-bottom:1px solid {BORDER}; }}"
        )
        hdr_lay = QHBoxLayout(hdr_container)
        hdr_lay.setContentsMargins(20, 16, 20, 12)
        hdr_lay.setSpacing(8)
        hdr_title = QLabel("Settings & Customisation")
        hdr_title.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold;"
            " padding:0; background:transparent; border:none;"
        )
        self._dirty_dot = QLabel("● Unsaved changes")
        self._dirty_dot.setStyleSheet(
            f"font-size:10px; color:{AMBER}; background:transparent; border:none;"
        )
        self._dirty_dot.setVisible(False)
        hdr_lay.addWidget(hdr_title)
        hdr_lay.addSpacing(8)
        hdr_lay.addWidget(self._dirty_dot)
        hdr_lay.addStretch()
        outer.addWidget(hdr_container)

        # SETTINGS-1: search bar
        search_row = QFrame()
        search_row.setStyleSheet(
            f"QFrame {{ background:{BG_DARK}; border-bottom:1px solid {BORDER}; }}"
        )
        search_lay = QHBoxLayout(search_row)
        search_lay.setContentsMargins(16, 6, 16, 6)
        search_lay.setSpacing(8)
        search_icon = QLabel("🔍")
        search_icon.setStyleSheet(
            f"font-size:12px; background:transparent; border:none; color:{TEXT_MUTED};"
        )
        self._settings_search = QLineEdit()
        self._settings_search.setPlaceholderText("Search settings…")
        self._settings_search.setStyleSheet(
            f"QLineEdit {{ background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};"
            f" border-radius:4px; padding:4px 8px; font-size:11px; }}"
            f"QLineEdit:focus {{ border-color:{ACCENT}; }}"
        )
        self._settings_search.textChanged.connect(self._on_search_changed)
        search_lay.addWidget(search_icon)
        search_lay.addWidget(self._settings_search, 1)
        outer.addWidget(search_row)

        self._settings_scroll = QScrollArea()
        self._settings_scroll.setWidgetResizable(True)
        self._settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._settings_scroll.setStyleSheet("background:transparent;")

        body = QWidget()
        body.setObjectName("contentArea")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 12, 20)
        bl.setSpacing(12)

        for builder, title, keywords in [
            (self._build_config_completeness_card, "Configuration Status",
             "setup npcap admin scan status network ready"),
            (self._build_integrations_card,        "Active Integrations",
             "modem mesh mqtt rest api speedtest ookla certificate service monitor"),
            (self._build_appearance_card,          "Appearance — Colour Theme",
             "theme arctic midnight obsidian abyss colour color dark light mode"),
            (self._build_display_card,             "Display",
             "compact rows density tooltips table font size"),
            (self._build_scanning_card,            "Network Scanning",
             "subnet range timeout arp interval ping sweep"),
            (self._build_internet_plan_card,       "Internet Plan",
             "isp data cap monthly usage quota gb plan utilization"),
            (self._build_sched_scan_card,          "Scheduled Full Scan",
             "schedule automatic cron interval repeat timer"),
            (self._build_tray_card,                "Notifications & Tray",
             "email smtp toast webhook pushover ntfy telegram alert notify tray"),
            (self._build_plugin_marketplace_card,  "Plugin Marketplace",
             "plugin extension install hub community"),
            (self._build_shortcuts_card,           "Keyboard Shortcuts",
             "ctrl cmd keyboard hotkey shortcut key binding"),
            (self._build_health_card,              "App Health",
             "version update database log debug about"),
            (self._build_maintenance_card,         "Maintenance",
             "reset export import oui backup restore data"),
        ]:
            card = builder()
            self._all_cards.append((card, title, keywords))
            bl.addWidget(card)
        bl.addStretch()

        self._settings_scroll.setWidget(body)

        # Section anchor sidebar (POLISH-5)
        _ANCHORS = [
            ("Notifications", "Notifications & Tray"),
            ("Schedule",      "Scheduled Full Scan"),
            ("Scanning",      "Network Scanning"),
            ("Appearance",    "Appearance — Colour Theme"),
            ("Maintenance",   "Maintenance"),
            ("About",         "App Health"),
        ]
        sidebar = QFrame()
        sidebar.setFixedWidth(110)
        sidebar.setStyleSheet(
            f"QFrame {{ background:{BG_DARK}; border-right:1px solid {BORDER}; }}"
        )
        _sb_lay = QVBoxLayout(sidebar)
        _sb_lay.setContentsMargins(0, 10, 0, 10)
        _sb_lay.setSpacing(2)
        self._anchor_btns: list[tuple[str, QPushButton]] = []
        _btn_base = (
            f"QPushButton {{ color:{TEXT_MUTED}; font-size:11px; text-align:left;"
            f" padding:4px 12px; background:transparent; border:none; border-left:2px solid transparent; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
        )
        for short, full_title in _ANCHORS:
            btn = QPushButton(short)
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_btn_base)
            for card, title, _kw in self._all_cards:
                if title == full_title:
                    btn.clicked.connect(
                        lambda _, c=card: self._settings_scroll.ensureWidgetVisible(c)
                    )
                    break
            _sb_lay.addWidget(btn)
            self._anchor_btns.append((full_title, btn))
        _sb_lay.addStretch()

        self._settings_scroll.verticalScrollBar().valueChanged.connect(
            self._update_settings_anchor
        )

        content_row = QHBoxLayout()
        content_row.setSpacing(0)
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.addWidget(sidebar)
        content_row.addWidget(self._settings_scroll, 1)
        outer.addLayout(content_row, 1)

    # ── Section anchor sidebar scroll-spy (POLISH-5) ─────────────────────────

    def _update_settings_anchor(self) -> None:
        """Highlight sidebar button for the section currently at the top of the scroll."""
        if not hasattr(self, "_anchor_btns") or not hasattr(self, "_settings_scroll"):
            return
        scroll_y = self._settings_scroll.verticalScrollBar().value()
        body = self._settings_scroll.widget()
        _btn_active = (
            f"QPushButton {{ color:{ACCENT}; font-size:11px; text-align:left;"
            f" padding:4px 12px; background:{ACCENT}15; border:none; border-left:2px solid {ACCENT}; }}"
        )
        _btn_inactive = (
            f"QPushButton {{ color:{TEXT_MUTED}; font-size:11px; text-align:left;"
            f" padding:4px 12px; background:transparent; border:none; border-left:2px solid transparent; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
        )
        active_title = ""
        best_y = -1
        for card, title, _kw in self._all_cards:
            if not card.isVisible():
                continue
            card_y = card.mapTo(body, card.rect().topLeft()).y()
            if card_y <= scroll_y + 10 and card_y >= best_y:
                best_y = card_y
                active_title = title
        for full_title, btn in self._anchor_btns:
            btn.setStyleSheet(_btn_active if full_title == active_title else _btn_inactive)

    # ── Search + dirty guard ─────────────────────────────────────────────────

    def _on_search_changed(self, text: str) -> None:
        q = text.strip().lower()
        if len(q) < 3:
            for card, _t, _kw in self._all_cards:
                card.setVisible(True)
        else:
            for card, title, keywords in self._all_cards:
                card.setVisible(q in title.lower() or q in keywords.lower())

    def refresh_theme(self) -> None:
        self._refresh_theme_buttons()

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._dirty_dot.setVisible(True)

    def is_dirty(self) -> bool:
        return self._dirty

    def clear_dirty(self) -> None:
        self._dirty = False
        self._dirty_dot.setVisible(False)

    def confirm_leave(self) -> bool:
        """Return True if it's OK to navigate away (prompts if dirty)."""
        if not self._dirty:
            return True
        result = QMessageBox.question(
            self,
            "Unsaved changes",
            "You have unsaved settings changes.\nLeave anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            self.clear_dirty()
            return True
        return False

    def _on_compact_toggled(self, checked: bool) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue("display/compact_rows", checked)
        self._mark_dirty()

    def _on_tooltip_toggled(self, checked: bool) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue("display/tooltips_enabled", checked)
        self._mark_dirty()

    # ── Internet Plan (S6-4) ──────────────────────────────────────────────────

    def _build_internet_plan_card(self) -> QFrame:
        """Optional monthly data cap — feeds the home page Usage Insights card (S6-4)."""
        card, bl = _card("Internet Plan")
        desc = QLabel(
            "Set your ISP's monthly data cap to see plan utilization on the home "
            "page Usage Insights card. Leave at 0 GB to hide this comparison."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size:10px; color:{TEXT_MUTED}; background:transparent;")
        bl.addWidget(desc)

        row = QHBoxLayout()
        lbl = QLabel("Monthly data cap:")
        lbl.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent;")
        self._plan_cap_spin = QDoubleSpinBox()
        self._plan_cap_spin.setRange(0, 100_000)
        self._plan_cap_spin.setDecimals(0)
        self._plan_cap_spin.setSuffix(" GB")
        qs = QSettings("NetSentinel", "NetSentinel")
        self._plan_cap_spin.setValue(qs.value("traffic/monthly_cap_gb", 0.0, type=float))
        self._plan_cap_spin.valueChanged.connect(self._on_monthly_cap_changed)
        row.addWidget(lbl)
        row.addWidget(self._plan_cap_spin)
        row.addStretch()
        bl.addLayout(row)

        speed_row = QHBoxLayout()
        speed_lbl = QLabel("Promised download speed:")
        speed_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent;")
        self._plan_speed_spin = QDoubleSpinBox()
        self._plan_speed_spin.setRange(0, 100_000)
        self._plan_speed_spin.setDecimals(0)
        self._plan_speed_spin.setSuffix(" Mbps")
        self._plan_speed_spin.setValue(qs.value("traffic/plan_speed_mbps", 0.0, type=float))
        self._plan_speed_spin.valueChanged.connect(self._on_plan_speed_changed)
        speed_row.addWidget(speed_lbl)
        speed_row.addWidget(self._plan_speed_spin)
        speed_row.addStretch()
        bl.addLayout(speed_row)
        return card

    def _on_monthly_cap_changed(self, value: float) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue("traffic/monthly_cap_gb", value)
        self._mark_dirty()

    def _on_plan_speed_changed(self, value: float) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue("traffic/plan_speed_mbps", value)
        self._mark_dirty()

