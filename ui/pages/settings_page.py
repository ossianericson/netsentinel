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

from ui import styles as _s

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

    # category → set of card titles
    _CATEGORY_MAP: dict[str, set[str]] = {
        "Appearance":   {"Appearance — Colour Theme", "Display"},
        "Monitoring":   {"Network Scanning", "Scheduled Full Scan", "Internet Plan"},
        "Alerts":       {"Notifications & Tray"},
        "Integrations": {"Active Integrations", "Plugin Marketplace"},
        "Advanced":     {"App Health", "Maintenance", "Keyboard Shortcuts",
                         "Configuration Status"},
    }

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._dirty = False
        self._all_cards: list[tuple[QFrame, str, str, str]] = []  # (card, title, kw, category)
        self._notif_test_workers: list[_NotifTestWorker] = []  # prevent GC
        self._active_category: str = "All"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header with dirty indicator
        hdr_container = QFrame()
        _s.themed_ss(hdr_container, "QFrame {{ background:transparent; border-bottom:1px solid {BORDER}; }}")
        hdr_lay = QHBoxLayout(hdr_container)
        hdr_lay.setContentsMargins(20, 16, 20, 12)
        hdr_lay.setSpacing(8)
        hdr_title = QLabel("Settings & Customisation")
        _s.themed_ss(hdr_title, "color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold;"
            " padding:0; background:transparent; border:none;")
        self._dirty_dot = QLabel("● Unsaved changes")
        _s.themed_ss(self._dirty_dot, "font-size:10px; color:{AMBER}; background:transparent; border:none;")
        self._dirty_dot.setVisible(False)
        hdr_lay.addWidget(hdr_title)
        hdr_lay.addSpacing(8)
        hdr_lay.addWidget(self._dirty_dot)
        hdr_lay.addStretch()
        outer.addWidget(hdr_container)

        # SETTINGS-1: search bar
        search_row = QFrame()
        _s.themed_ss(search_row, "QFrame {{ background:{BG_DARK}; border-bottom:1px solid {BORDER}; }}")
        search_lay = QHBoxLayout(search_row)
        search_lay.setContentsMargins(16, 6, 16, 6)
        search_lay.setSpacing(8)
        search_icon = QLabel("🔍")
        _s.themed_ss(search_icon, "font-size:12px; background:transparent; border:none; color:{TEXT_MUTED};")
        self._settings_search = QLineEdit()
        self._settings_search.setPlaceholderText("Search settings…")
        _s.themed_ss(self._settings_search, "QLineEdit {{ background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};"
            " border-radius:4px; padding:4px 8px; font-size:11px; }}"
            "QLineEdit:focus {{ border-color:{ACCENT}; }}")
        self._settings_search.textChanged.connect(self._on_search_changed)
        search_lay.addWidget(search_icon)
        search_lay.addWidget(self._settings_search, 1)
        outer.addWidget(search_row)

        # SETTINGS-CAT: category chip bar
        cat_row = QFrame()
        _s.themed_ss(cat_row, "QFrame {{ background:{BG_DARK}; border-bottom:1px solid {BORDER}; }}")
        cat_lay = QHBoxLayout(cat_row)
        cat_lay.setContentsMargins(16, 6, 16, 6)
        cat_lay.setSpacing(6)
        self._cat_btns: dict[str, QPushButton] = {}
        qs_cat = QSettings("NetSentinel", "NetSentinel")
        saved_cat = qs_cat.value("settings/last_category", "All", type=str)
        for chip_label in ["All", "Appearance", "Monitoring", "Alerts", "Integrations", "Advanced"]:
            btn = QPushButton(chip_label)
            btn.setCheckable(False)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(24)
            btn.setStyleSheet(self._chip_qss(chip_label == saved_cat))
            btn.clicked.connect(
                lambda _, lbl=chip_label: self._on_category_changed(lbl)
            )
            cat_lay.addWidget(btn)
            self._cat_btns[chip_label] = btn
        cat_lay.addStretch()
        outer.addWidget(cat_row)
        self._active_category = saved_cat

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
            # resolve category
            cat = "Advanced"  # default
            for _cat, _titles in self._CATEGORY_MAP.items():
                if title in _titles:
                    cat = _cat
                    break
            self._all_cards.append((card, title, keywords, cat))
            bl.addWidget(card)
        bl.addStretch()

        self._settings_scroll.setWidget(body)

        outer.addWidget(self._settings_scroll, 1)

    # ── Search + dirty guard ─────────────────────────────────────────────────

    def _chip_qss(self, active: bool) -> str:
        """Category-chip QSS from live theme tokens (shape I — re-applied on refresh_theme,
        never registered with themed_ss because the applied state depends on selection)."""
        if active:
            return (
                f"QPushButton {{ font-size:11px; padding:3px 12px;"
                f" border:1px solid {_s.ACCENT}; border-radius:10px;"
                f" background:{_s.ACCENT}; color:{_s.WHITE}; }}"
                f"QPushButton:hover {{ background:{_s.ACCENT_LITE}; color:{_s.WHITE}; border-color:{_s.ACCENT_LITE}; }}"
                f"QPushButton:pressed {{ background:{_s.ACCENT_DARK}; color:{_s.WHITE}; border-color:{_s.ACCENT_DARK}; }}"
            )
        return (
            f"QPushButton {{ font-size:11px; padding:3px 12px;"
            f" border:1px solid {_s.BORDER}; border-radius:10px;"
            f" background:{_s.BG_CARD}; color:{_s.TEXT_MUTED}; }}"
            f"QPushButton:hover {{ border-color:{_s.ACCENT}; color:{_s.TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{_s.ACCENT}; color:{_s.WHITE}; border-color:{_s.ACCENT}; }}"
        )

    def _on_category_changed(self, label: str) -> None:
        self._active_category = label
        QSettings("NetSentinel", "NetSentinel").setValue("settings/last_category", label)
        for lbl, btn in self._cat_btns.items():
            btn.setStyleSheet(self._chip_qss(lbl == label))
        self._apply_visibility()

    def _apply_visibility(self) -> None:
        q = self._settings_search.text().strip().lower()
        for card, title, keywords, cat in self._all_cards:
            cat_ok = self._active_category == "All" or cat == self._active_category
            search_ok = len(q) < 3 or (q in title.lower() or q in keywords.lower())
            card.setVisible(cat_ok and search_ok)

    def _on_search_changed(self, text: str) -> None:
        self._apply_visibility()

    def refresh_theme(self) -> None:
        self._refresh_theme_swatches()
        for lbl, btn in self._cat_btns.items():
            btn.setStyleSheet(self._chip_qss(lbl == self._active_category))

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
        _s.themed_ss(desc, "font-size:10px; color:{TEXT_MUTED}; background:transparent;")
        bl.addWidget(desc)

        row = QHBoxLayout()
        lbl = QLabel("Monthly data cap:")
        _s.themed_ss(lbl, "font-size:11px; color:{TEXT_PRIMARY}; background:transparent;")
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
        _s.themed_ss(speed_lbl, "font-size:11px; color:{TEXT_PRIMARY}; background:transparent;")
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

