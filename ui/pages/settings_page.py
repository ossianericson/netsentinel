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

from PyQt6.QtCore import Qt, QSettings, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import ui.styles as _styles
from ui.styles import (
    ACCENT, ACCENT_DARK, BG_ALT_ROW, BG_CARD, BG_DARK, BORDER,
    BTN_HOVER_BG, CARD_HDR_BORDER, CARD_RADIUS, GREEN, NAV_BAR, RED, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)


# ── Background workers for plugin marketplace ─────────────────────────────────

class _FetchRegistryWorker(QThread):
    """Fetch the community plugin registry off the main thread."""
    ready = pyqtSignal(list)   # List[RegistryEntry]
    error = pyqtSignal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self) -> None:
        try:
            from modules.plugin_registry import fetch_registry
            entries = fetch_registry(self._url)
            self.ready.emit(entries)
        except Exception as exc:
            self.error.emit(str(exc))


class _InstallWorker(QThread):
    """Download and install one plugin off the main thread."""
    done  = pyqtSignal(str)         # plugin name
    error = pyqtSignal(str, str)    # plugin name, error message

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self._entry = entry

    def run(self) -> None:
        try:
            from modules.plugin_registry import install_plugin
            install_plugin(self._entry)
            self.done.emit(self._entry.name)
        except Exception as exc:
            self.error.emit(self._entry.name, str(exc))


class _UninstallWorker(QThread):
    """Remove a plugin file off the main thread."""
    done  = pyqtSignal(str)       # plugin name
    error = pyqtSignal(str, str)  # plugin name, error message

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self._entry = entry

    def run(self) -> None:
        try:
            from modules.plugin_registry import uninstall_plugin
            uninstall_plugin(self._entry)
            self.done.emit(self._entry.name)
        except Exception as exc:
            self.error.emit(self._entry.name, str(exc))


def _page_header(title: str, subtitle: str = "") -> QFrame:
    container = QFrame()
    container.setObjectName("pageHeader")
    container.setStyleSheet(
        f"QFrame#pageHeader {{ background: transparent; border: none;"
        f" border-bottom: 1px solid {BORDER}; }}"
    )
    vbox = QVBoxLayout(container)
    vbox.setContentsMargins(20, 16, 20, 12)
    vbox.setSpacing(2)
    t = QLabel(title)
    t.setStyleSheet(
        f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold;"
        "padding:0; background:transparent; border:none;"
    )
    vbox.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px;"
            "padding:0; background:transparent; border:none;"
        )
        vbox.addWidget(s)
    return container


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    """Return (card QFrame, body QVBoxLayout) styled per design system."""
    card = QFrame()
    card.setObjectName("card")
    card.setStyleSheet(
        f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
        f"border-radius:{CARD_RADIUS};}}"
    )
    cl = QVBoxLayout(card)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(0)

    tb = QFrame()
    tb.setFixedHeight(32)
    tb.setStyleSheet(
        f"background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};"
    )
    tbl = QHBoxLayout(tb)
    tbl.setContentsMargins(12, 0, 12, 0)
    lbl = QLabel(title)
    lbl.setStyleSheet(
        f"color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;"
    )
    tbl.addWidget(lbl)
    tbl.addStretch()
    cl.addWidget(tb)

    body = QWidget()
    body.setStyleSheet(f"background:{BG_CARD};")
    bl = QVBoxLayout(body)
    bl.setContentsMargins(16, 12, 16, 14)
    bl.setSpacing(10)
    cl.addWidget(body)
    return card, bl


def _integr_cert_count(qs: QSettings) -> tuple[bool, str]:
    try:
        import json as _json
        targets = _json.loads(qs.value("cert/targets", "[]"))
        n = len(targets) if isinstance(targets, list) else 0
    except Exception:
        n = 0
    return (n > 0, f"{n} target{'s' if n != 1 else ''} configured")


def _integr_svc_count(qs: QSettings) -> tuple[bool, str]:
    try:
        import json as _json
        targets = _json.loads(qs.value("service_monitor/targets", "[]"))
        n = len(targets) if isinstance(targets, list) else 0
    except Exception:
        n = 0
    return (n > 0, f"{n} target{'s' if n != 1 else ''} configured")


class SettingsPage(QWidget):
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
            f"font-size:10px; color:#F59E0B; background:transparent; border:none;"
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

        for builder, title in [
            (self._build_config_completeness_card, "Configuration Status"),
            (self._build_integrations_card,        "Active Integrations"),
            (self._build_appearance_card,          "Appearance — Colour Theme"),
            (self._build_display_card,             "Display"),
            (self._build_scanning_card,            "Network Scanning"),
            (self._build_sched_scan_card,          "Scheduled Full Scan"),
            (self._build_tray_card,                "Notifications & Tray"),
            (self._build_plugin_marketplace_card,  "Plugin Marketplace"),
            (self._build_shortcuts_card,           "Keyboard Shortcuts"),
            (self._build_health_card,              "App Health"),
            (self._build_maintenance_card,         "Maintenance"),
        ]:
            card = builder()
            self._all_cards.append((card, title))
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
            for card, title in self._all_cards:
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
        for card, title in self._all_cards:
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
            for card, _ in self._all_cards:
                card.setVisible(True)
        else:
            for card, title in self._all_cards:
                card.setVisible(q in title.lower())

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

    # ── Active Integrations ───────────────────────────────────────────────────

    def _build_integrations_card(self) -> QFrame:
        card, bl = _card("Active Integrations")

        qs = QSettings("NetSentinel", "NetSentinel")

        def _row(label: str, status_fn, nav_target: str) -> None:
            row = QHBoxLayout()
            row.setSpacing(8)
            lbl = QLabel(label)
            lbl.setFixedWidth(190)
            lbl.setStyleSheet(f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;")
            status_val = status_fn()
            ok = status_val[0]
            status_txt = status_val[1]
            s_lbl = QLabel(status_txt)
            s_color = GREEN if ok else TEXT_MUTED
            s_lbl.setStyleSheet(
                f"font-size:11px;color:{s_color};background:transparent;"
            )
            cfg_btn = QPushButton("Configure →")
            cfg_btn.setFlat(True)
            cfg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            cfg_btn.setStyleSheet(
                f"QPushButton{{color:{ACCENT};font-size:11px;background:transparent;"
                f"border:none;padding:0;}}"
                f"QPushButton:hover{{color:{ACCENT_DARK};}}"
            )
            cfg_btn.clicked.connect(lambda _=False, t=nav_target: self.navigate_to.emit(t))
            row.addWidget(lbl)
            row.addWidget(s_lbl, 1)
            row.addWidget(cfg_btn)
            bl.addLayout(row)

        _row("Email notifications",
             lambda: (bool(qs.value("notifications/email_address", "")),
                      ("✓ " + str(qs.value("notifications/email_address", ""))[:30])
                      if qs.value("notifications/email_address", "") else "✗ Not configured"),
             "Notifications")

        _row("Webhook",
             lambda: (bool(qs.value("notifications/webhook_url", "")),
                      ("✓ Configured" if qs.value("notifications/webhook_url", "") else "✗ Not set")),
             "Notifications")

        _row("Pushover",
             lambda: (bool(qs.value("notifications/pushover_user_key", "")),
                      ("✓ Configured" if qs.value("notifications/pushover_user_key", "") else "✗ Not set")),
             "Notifications")

        _row("5G Modem logging",
             lambda: (qs.value("logging/modem_enabled", False, type=bool),
                      (f"● Logging · every {qs.value('logging/modem_interval_min', 5, type=int)} min"
                       if qs.value("logging/modem_enabled", False, type=bool) else "● Not enabled")),
             "Logs")

        _row("Mesh Router logging",
             lambda: (qs.value("logging/mesh_enabled", False, type=bool),
                      (f"● Logging · every {qs.value('logging/mesh_interval_min', 5, type=int)} min"
                       if qs.value("logging/mesh_enabled", False, type=bool) else "● Not enabled")),
             "Logs")

        _row("Syslog receiver",
             lambda: (qs.value("logging/syslog_enabled", True, type=bool),
                      ("● Listening" if qs.value("logging/syslog_enabled", True, type=bool) else "● Disabled")),
             "Logs")

        _row("SNMP traps",
             lambda: (qs.value("logging/snmp_enabled", True, type=bool),
                      ("● Listening" if qs.value("logging/snmp_enabled", True, type=bool) else "● Disabled")),
             "Logs")

        _row("TLS cert targets",
             lambda: _integr_cert_count(qs),
             "TLS & Exposure")

        _row("Service monitor targets",
             lambda: _integr_svc_count(qs),
             "Service Monitor")

        return card

    # ── Appearance ────────────────────────────────────────────────────────────

    def _build_appearance_card(self) -> QFrame:
        card, bl = _card("Appearance — Colour Theme")

        desc = QLabel(
            "Choose a colour theme for the entire application. "
            "The change takes effect after restarting NetSentinel."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"font-size:11px;color:{TEXT_SECONDARY};background:transparent;"
        )
        bl.addWidget(desc)

        self._theme_status_lbl = QLabel("")
        self._theme_status_lbl.setStyleSheet(
            f"font-size:11px;color:{ACCENT};background:transparent;"
        )

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._theme_btns: dict[str, QPushButton] = {}

        for name in _styles.THEMES:
            btn = QPushButton(name)
            self._theme_btns[name] = btn
            btn_row.addWidget(btn)
            btn.clicked.connect(lambda checked=False, n=name: self._on_theme(n))

        btn_row.addStretch()
        bl.addLayout(btn_row)
        bl.addWidget(self._theme_status_lbl)

        self._refresh_theme_buttons()
        return card

    def _refresh_theme_buttons(self):
        active = _styles.get_active_theme_name()
        for name, btn in self._theme_btns.items():
            if name == active:
                btn.setStyleSheet(
                    f"QPushButton{{background:{ACCENT};color:{NAV_BAR};"
                    f"border:1px solid {ACCENT};border-radius:4px;"
                    f"padding:5px 14px;font-size:11px;font-weight:bold;}}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton{{background:{BG_CARD};color:{ACCENT};"
                    f"border:1px solid {ACCENT};border-radius:4px;"
                    f"padding:5px 14px;font-size:11px;}}"
                    f"QPushButton:hover{{background:{BTN_HOVER_BG};}}"
                )

    def _on_theme(self, name: str):
        _styles.set_active_theme_name(name)
        self._refresh_theme_buttons()
        self._theme_status_lbl.setText(
            f"Theme '{name}' saved — restart NetSentinel to apply."
        )

    # ── Display preferences ───────────────────────────────────────────────────

    def _build_display_card(self) -> QFrame:
        card, bl = _card("Display Preferences")

        qs = QSettings("NetSentinel", "NetSentinel")

        self._chk_compact = QCheckBox("Compact table rows (24 px — more devices visible)")
        self._chk_compact.setStyleSheet(
            f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;"
        )
        self._chk_compact.setChecked(
            qs.value("display/compact_rows", True, type=bool)
        )
        self._chk_compact.toggled.connect(self._on_compact_toggled)
        bl.addWidget(self._chk_compact)

        self._chk_tooltips = QCheckBox("Show extended tooltips on hover (400 ms delay)")
        self._chk_tooltips.setStyleSheet(
            f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;"
        )
        self._chk_tooltips.setChecked(
            qs.value("display/tooltips_enabled", True, type=bool)
        )
        self._chk_tooltips.toggled.connect(self._on_tooltip_toggled)
        bl.addWidget(self._chk_tooltips)

        note = QLabel(
            "Row height and tooltip settings take effect the next time a table is populated."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            f"font-size:10px;color:{TEXT_SECONDARY};background:transparent;"
        )
        bl.addWidget(note)
        return card

    def _on_compact_toggled(self, checked: bool):
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("display/compact_rows", checked)
        self._mark_dirty()

    def _on_tooltip_toggled(self, checked: bool):
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("display/tooltips_enabled", checked)
        self._mark_dirty()

    # ── Network Scanning ──────────────────────────────────────────────────────

    def _build_scanning_card(self) -> QFrame:
        card, bl = _card("Network Scanning")

        qs = QSettings("NetSentinel", "NetSentinel")

        self._chk_auto_snap = QCheckBox(
            "Auto-snapshot after every scan (keeps last 10) — Config Snapshots"
        )
        self._chk_auto_snap.setStyleSheet(
            f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;"
        )
        self._chk_auto_snap.setChecked(
            qs.value("baseline/auto_snapshot", False, type=bool)
        )
        self._chk_auto_snap.toggled.connect(self._on_auto_snap_toggled)
        bl.addWidget(self._chk_auto_snap)

        note = QLabel(
            "When enabled, a Config Snapshot is silently saved after each device scan. "
            "If any change is detected versus the previous snapshot, a toast and a rail "
            "badge appear on Config Snapshots."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            f"font-size:10px;color:{TEXT_SECONDARY};background:transparent;"
        )
        bl.addWidget(note)
        return card

    def _on_auto_snap_toggled(self, checked: bool):
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("baseline/auto_snapshot", checked)
        self._mark_dirty()

    # ── Scheduled Full Scan (SCHED-1) ─────────────────────────────────────────

    def _build_sched_scan_card(self) -> QFrame:
        card, bl = _card("Scheduled Full Scan")
        qs = QSettings("NetSentinel", "NetSentinel")

        self._chk_sched_scan = QCheckBox("Enable scheduled full network scan")
        self._chk_sched_scan.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent;"
        )
        self._chk_sched_scan.setChecked(qs.value("sched_scan/enabled", False, bool))
        bl.addWidget(self._chk_sched_scan)

        # Recurrence row
        rec_row = QHBoxLayout()
        rec_row.setSpacing(8)
        rec_lbl = QLabel("Run every")
        rec_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent;")
        self._sched_scan_combo = QComboBox()
        self._sched_scan_combo.addItems(["24 hours (daily)", "12 hours", "6 hours", "1 hour"])
        _interval_map = {"24 hours (daily)": 24, "12 hours": 12, "6 hours": 6, "1 hour": 1}
        _saved_hours = qs.value("sched_scan/interval_hours", 24, int)
        _rev = {v: k for k, v in _interval_map.items()}
        self._sched_scan_combo.setCurrentText(_rev.get(_saved_hours, "24 hours (daily)"))
        self._sched_scan_combo.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; padding:2px 4px;"
        )
        rec_row.addWidget(rec_lbl)
        rec_row.addWidget(self._sched_scan_combo)
        rec_row.addStretch()
        bl.addLayout(rec_row)

        # Next-run time
        time_row = QHBoxLayout()
        time_row.setSpacing(8)
        time_lbl = QLabel("Start time (today)")
        time_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent;")
        self._sched_hour_spin = QSpinBox()
        self._sched_hour_spin.setRange(0, 23)
        self._sched_hour_spin.setValue(qs.value("sched_scan/hour", 2, int))
        self._sched_hour_spin.setFixedWidth(55)
        self._sched_hour_spin.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; padding:2px 4px;"
        )
        colon = QLabel(":")
        colon.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent;")
        self._sched_min_spin = QSpinBox()
        self._sched_min_spin.setRange(0, 59)
        self._sched_min_spin.setValue(qs.value("sched_scan/minute", 0, int))
        self._sched_min_spin.setFixedWidth(55)
        self._sched_min_spin.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; padding:2px 4px;"
        )
        time_row.addWidget(time_lbl)
        time_row.addWidget(self._sched_hour_spin)
        time_row.addWidget(colon)
        time_row.addWidget(self._sched_min_spin)
        time_row.addStretch()
        bl.addLayout(time_row)

        save_btn = QPushButton("Save Schedule")
        save_btn.setFixedHeight(28)
        save_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:white; border:none;"
            f" font-size:11px; border-radius:4px; padding:0 14px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; }}"
        )
        save_btn.clicked.connect(self._save_sched_scan)
        bl.addWidget(save_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self._sched_scan_next_lbl = QLabel("")
        self._sched_scan_next_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_MUTED}; background:transparent;"
        )
        bl.addWidget(self._sched_scan_next_lbl)
        self._refresh_sched_scan_label()
        return card

    def _save_sched_scan(self) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("sched_scan/enabled", self._chk_sched_scan.isChecked())
        _interval_map = {"24 hours (daily)": 24, "12 hours": 12, "6 hours": 6, "1 hour": 1}
        hours = _interval_map.get(self._sched_scan_combo.currentText(), 24)
        qs.setValue("sched_scan/interval_hours", hours)
        qs.setValue("sched_scan/hour",   self._sched_hour_spin.value())
        qs.setValue("sched_scan/minute", self._sched_min_spin.value())
        import time as _t, datetime as _dt
        now = _dt.datetime.now()
        next_run = now.replace(
            hour=self._sched_hour_spin.value(),
            minute=self._sched_min_spin.value(),
            second=0, microsecond=0
        )
        if next_run <= now:
            next_run += _dt.timedelta(hours=hours)
        qs.setValue("sched_scan/next_ts", next_run.timestamp())
        self._refresh_sched_scan_label()
        self._mark_dirty()

    def _refresh_sched_scan_label(self) -> None:
        if not hasattr(self, "_sched_scan_next_lbl"):
            return
        qs = QSettings("NetSentinel", "NetSentinel")
        if not qs.value("sched_scan/enabled", False, bool):
            self._sched_scan_next_lbl.setText("Scheduled scan is disabled.")
            return
        import time as _t
        next_ts = float(qs.value("sched_scan/next_ts", 0))
        if next_ts > _t.time():
            import datetime as _dt
            nxt = _dt.datetime.fromtimestamp(next_ts)
            self._sched_scan_next_lbl.setText(
                f"Next scan: {nxt.strftime('%a %d %b at %H:%M')}"
            )
        else:
            self._sched_scan_next_lbl.setText("Next scan: not yet scheduled — click Save.")

    # ── System Tray & Startup ─────────────────────────────────────────────────

    def _build_tray_card(self) -> QFrame:
        import sys
        from ui.system_tray import get_run_on_startup, set_run_on_startup

        card, bl = _card("System Tray & Startup")

        qs = QSettings("NetSentinel", "NetSentinel")

        # Minimize to tray
        self._chk_tray = QCheckBox(
            "Minimize to system tray on close  "
            "(app keeps running in the background)"
        )
        self._chk_tray.setStyleSheet(
            f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;"
        )
        self._chk_tray.setChecked(qs.value("tray/minimize_to_tray", True, type=bool))
        self._chk_tray.toggled.connect(self._on_tray_toggled)
        bl.addWidget(self._chk_tray)

        # Minimize button → tray (opt-in)
        self._chk_minimize_tray = QCheckBox(
            "Minimize button also hides to tray  "
            "(default is minimize to taskbar)"
        )
        self._chk_minimize_tray.setStyleSheet(
            f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;"
        )
        self._chk_minimize_tray.setChecked(
            qs.value("tray/minimize_window_to_tray", False, type=bool)
        )
        self._chk_minimize_tray.toggled.connect(self._on_minimize_tray_toggled)
        bl.addWidget(self._chk_minimize_tray)

        # Run on startup (Windows only)
        self._chk_startup = QCheckBox(
            "Start NetSentinel automatically when Windows starts  "
            "(launches minimised to tray)"
        )
        self._chk_startup.setStyleSheet(
            f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;"
        )
        if sys.platform != "win32":
            self._chk_startup.setEnabled(False)
            self._chk_startup.setToolTip("Startup registration is only available on Windows")
        else:
            self._chk_startup.setChecked(get_run_on_startup())
        self._chk_startup.toggled.connect(self._on_startup_toggled)
        bl.addWidget(self._chk_startup)

        # ── Notification opt-ins ───────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{BORDER}; background:{BORDER}; max-height:1px; border:none;")
        bl.addWidget(sep)

        notif_lbl = QLabel("Notifications  (all off by default)")
        notif_lbl.setStyleSheet(
            f"font-size:11px; font-weight:600; color:{TEXT_PRIMARY}; background:transparent;"
        )
        bl.addWidget(notif_lbl)

        self._chk_notify_new_device = QCheckBox(
            "Notify when a new device joins the network"
        )
        self._chk_notify_new_device.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent;"
        )
        self._chk_notify_new_device.setChecked(
            qs.value("tray/notify_new_device", False, type=bool)
        )
        self._chk_notify_new_device.toggled.connect(
            lambda v: (
                QSettings("NetSentinel", "NetSentinel").setValue("tray/notify_new_device", v),
                self._mark_dirty(),
            )
        )
        bl.addWidget(self._chk_notify_new_device)

        self._chk_notify_gone = QCheckBox(
            "Notify when a known device leaves the network"
        )
        self._chk_notify_gone.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent;"
        )
        self._chk_notify_gone.setChecked(
            qs.value("tray/notify_device_gone", False, type=bool)
        )
        self._chk_notify_gone.toggled.connect(
            lambda v: (
                QSettings("NetSentinel", "NetSentinel").setValue("tray/notify_device_gone", v),
                self._mark_dirty(),
            )
        )
        bl.addWidget(self._chk_notify_gone)

        note = QLabel(
            "Alert-rule notifications (ARP attacks, HIGH-risk devices, custom rules) "
            "are configured per-rule in the Alerts tab."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
        )
        bl.addWidget(note)
        return card

    def _on_tray_toggled(self, checked: bool) -> None:
        self._mark_dirty()
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("tray/minimize_to_tray", checked)
        # Also update the live tray manager if reachable
        try:
            from PyQt6.QtWidgets import QApplication
            win = QApplication.instance().activeWindow()
            if win is None:
                # Try main window via topLevelWidgets
                for w in QApplication.instance().topLevelWidgets():
                    if hasattr(w, "_tray_manager"):
                        win = w
                        break
            if win and hasattr(win, "_tray_manager"):
                win._tray_manager.set_minimize_to_tray(checked)
        except Exception:
            pass

    def _on_minimize_tray_toggled(self, checked: bool) -> None:
        self._mark_dirty()
        QSettings("NetSentinel", "NetSentinel").setValue("tray/minimize_window_to_tray", checked)

    def _on_startup_toggled(self, checked: bool) -> None:
        self._mark_dirty()
        from ui.system_tray import set_run_on_startup
        set_run_on_startup(checked)

    # ── Plugin Marketplace ────────────────────────────────────────────────────

    def _build_plugin_marketplace_card(self) -> QFrame:
        from modules.plugin_registry import REGISTRY_URL
        card, bl = _card("Community Plugins — Browse & Install")

        desc = QLabel(
            "Browse community plugins hosted on GitHub. "
            "Click Install to download a plugin to your local plugins folder."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size:11px;color:{TEXT_SECONDARY};background:transparent;")
        bl.addWidget(desc)

        # Registry URL row
        url_row = QHBoxLayout()
        url_row.setSpacing(6)
        url_lbl = QLabel("Registry URL:")
        url_lbl.setStyleSheet(f"font-size:11px;color:{TEXT_PRIMARY};")
        url_lbl.setFixedWidth(90)
        self._pm_url = QLineEdit(REGISTRY_URL)
        self._pm_url.setStyleSheet(
            f"font-size:11px;color:{TEXT_PRIMARY};border:1px solid {BORDER};padding:2px 6px;"
        )
        url_row.addWidget(url_lbl)
        url_row.addWidget(self._pm_url, 1)
        bl.addLayout(url_row)

        # Toolbar
        tb_row = QHBoxLayout()
        tb_row.setSpacing(6)

        _btn_qss = (
            f"QPushButton{{background:{BG_CARD};color:{ACCENT};"
            f"border:1px solid {ACCENT};border-radius:2px;"
            f"padding:0 12px;font-size:11px;height:26px;}}"
            f"QPushButton:hover{{background:{BTN_HOVER_BG};}}"
            f"QPushButton:disabled{{color:{TEXT_MUTED};border-color:{BORDER};}}"
        )
        self._pm_btn_refresh = QPushButton("↻  Refresh")
        self._pm_btn_refresh.setStyleSheet(_btn_qss)
        self._pm_btn_refresh.clicked.connect(self._pm_refresh)

        self._pm_btn_install = QPushButton("▼  Install")
        self._pm_btn_install.setStyleSheet(_btn_qss)
        self._pm_btn_install.setEnabled(False)
        self._pm_btn_install.clicked.connect(self._pm_install_selected)

        self._pm_btn_uninstall = QPushButton("✕  Uninstall")
        self._pm_btn_uninstall.setStyleSheet(
            f"QPushButton{{background:{BG_CARD};color:{RED};"
            f"border:1px solid {RED};border-radius:2px;"
            f"padding:0 12px;font-size:11px;height:26px;}}"
            f"QPushButton:hover{{background:#FFF0F0;}}"
            f"QPushButton:disabled{{color:{TEXT_MUTED};border-color:{BORDER};}}"
        )
        self._pm_btn_uninstall.setEnabled(False)
        self._pm_btn_uninstall.clicked.connect(self._pm_uninstall_selected)

        self._pm_btn_folder = QPushButton("📁  Open Plugins Folder")
        self._pm_btn_folder.setStyleSheet(_btn_qss)
        self._pm_btn_folder.clicked.connect(self._pm_open_folder)

        tb_row.addWidget(self._pm_btn_refresh)
        tb_row.addWidget(self._pm_btn_install)
        tb_row.addWidget(self._pm_btn_uninstall)
        tb_row.addStretch()
        tb_row.addWidget(self._pm_btn_folder)
        bl.addLayout(tb_row)

        # Table
        self._pm_table = QTableWidget(0, 5)
        self._pm_table.setHorizontalHeaderLabels(["Name", "Author", "Tags", "Version", "Status"])
        self._pm_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._pm_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._pm_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._pm_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._pm_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._pm_table.verticalHeader().setDefaultSectionSize(24)
        self._pm_table.verticalHeader().setVisible(False)
        self._pm_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._pm_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._pm_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._pm_table.setAlternatingRowColors(True)
        self._pm_table.setMinimumHeight(160)
        self._pm_table.setStyleSheet(
            f"QTableWidget{{font-size:11px;background:{BG_CARD};border:1px solid {BORDER};}}"
            f"QHeaderView::section{{background:{BG_CARD};color:{TEXT_PRIMARY};"
            f"font-size:11px;font-weight:bold;border:none;"
            f"border-bottom:1px solid {BORDER};padding:3px 6px;}}"
            f"QTableWidget::item:selected{{background:{ACCENT};color:white;}}"
        )
        self._pm_table.itemSelectionChanged.connect(self._pm_on_selection)
        bl.addWidget(self._pm_table)

        # Status label
        self._pm_status = QLabel("Click ↻ Refresh to load the community plugin registry.")
        self._pm_status.setStyleSheet(
            f"font-size:10px;color:{TEXT_SECONDARY};background:transparent;"
        )
        bl.addWidget(self._pm_status)

        self._pm_entries: list = []
        self._pm_workers: list = []   # keep references so GC doesn't kill them
        return card

    # ── Plugin marketplace slots ──────────────────────────────────────────────

    def _pm_refresh(self) -> None:
        self._pm_btn_refresh.setEnabled(False)
        self._pm_status.setText("Fetching registry…")
        url = self._pm_url.text().strip()
        worker = _FetchRegistryWorker(url, parent=self)
        worker.ready.connect(self._pm_on_registry_ready)
        worker.error.connect(self._pm_on_registry_error)
        worker.finished.connect(lambda: self._pm_btn_refresh.setEnabled(True))
        self._pm_workers.append(worker)
        worker.start()

    def _pm_on_registry_ready(self, entries: list) -> None:
        from modules.plugin_registry import is_installed
        self._pm_entries = entries
        self._pm_table.setRowCount(0)
        for e in entries:
            row = self._pm_table.rowCount()
            self._pm_table.insertRow(row)

            installed = is_installed(e)
            dot_color = GREEN if installed else TEXT_MUTED
            dot_text  = "● Installed" if installed else "○ Available"

            for col, text in enumerate([
                e.name, e.author, e.tag_str, e.version,
            ]):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._pm_table.setItem(row, col, item)

            status_item = QTableWidgetItem(dot_text)
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            from PyQt6.QtGui import QColor
            status_item.setForeground(QColor(dot_color))
            self._pm_table.setItem(row, 4, status_item)

        self._pm_status.setText(
            f"Loaded {len(entries)} plugin{'s' if len(entries) != 1 else ''} from registry."
        )

    def _pm_on_registry_error(self, msg: str) -> None:
        self._pm_status.setText(f"Error: {msg}")

    def _pm_on_selection(self) -> None:
        rows = self._pm_table.selectedItems()
        has_sel = bool(rows)
        self._pm_btn_install.setEnabled(has_sel)
        self._pm_btn_uninstall.setEnabled(has_sel)

    def _pm_install_selected(self) -> None:
        row = self._pm_table.currentRow()
        if row < 0 or row >= len(self._pm_entries):
            return
        entry = self._pm_entries[row]
        self._pm_btn_install.setEnabled(False)
        self._pm_status.setText(f"Installing {entry.name}…")
        worker = _InstallWorker(entry, parent=self)
        worker.done.connect(self._pm_on_install_done)
        worker.error.connect(self._pm_on_install_error)
        self._pm_workers.append(worker)
        worker.start()

    def _pm_on_install_done(self, name: str) -> None:
        self._pm_status.setText(f"✓ {name} installed successfully.")
        self._pm_on_registry_ready(self._pm_entries)   # refresh status dots

    def _pm_on_install_error(self, name: str, msg: str) -> None:
        self._pm_status.setText(f"Error installing {name}: {msg}")
        self._pm_btn_install.setEnabled(True)

    def _pm_uninstall_selected(self) -> None:
        row = self._pm_table.currentRow()
        if row < 0 or row >= len(self._pm_entries):
            return
        entry = self._pm_entries[row]
        self._pm_btn_uninstall.setEnabled(False)
        self._pm_status.setText(f"Removing {entry.name}…")
        worker = _UninstallWorker(entry, parent=self)
        worker.done.connect(self._pm_on_uninstall_done)
        worker.error.connect(self._pm_on_uninstall_error)
        self._pm_workers.append(worker)
        worker.start()

    def _pm_on_uninstall_done(self, name: str) -> None:
        self._pm_status.setText(f"✓ {name} uninstalled.")
        self._pm_on_registry_ready(self._pm_entries)

    def _pm_on_uninstall_error(self, name: str, msg: str) -> None:
        self._pm_status.setText(f"Error removing {name}: {msg}")
        self._pm_btn_uninstall.setEnabled(True)

    def _pm_open_folder(self) -> None:
        import subprocess, sys
        from modules.plugin_system import plugins_dir
        path = plugins_dir()
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    # ── Shortcuts reference ───────────────────────────────────────────────────

    def _build_shortcuts_card(self) -> QFrame:
        card, bl = _card("Keyboard Shortcuts")

        shortcuts = [
            ("Ctrl + R",           "Run full scan"),
            ("Ctrl + E",           "Export last scan results"),
            ("Ctrl + Q",           "Quit application"),
            ("F5",                 "Refresh current page"),
            ("Right-click",        "Context menu on any table row"),
            ("Ctrl + Shift + M",   "Visual Diagnostic Overlay (Matrix mode)"),
        ]

        for i, (key, desc) in enumerate(shortcuts):
            row_w = QWidget()
            row_w.setStyleSheet(
                f"background:{BG_ALT_ROW if i % 2 else BG_CARD};"
            )
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 3, 0, 3)
            row_l.setSpacing(12)

            k = QLabel(key)
            k.setFixedWidth(150)
            k.setStyleSheet(
                f"font-family:Consolas;font-size:10px;color:{ACCENT_DARK};"
                f"background:transparent;"
            )
            d = QLabel(desc)
            d.setStyleSheet(
                f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;"
            )
            row_l.addWidget(k)
            row_l.addWidget(d, 1)
            bl.addWidget(row_w)

        return card

    # ── Maintenance ───────────────────────────────────────────────────────────

    def _build_maintenance_card(self) -> QFrame:
        card, bl = _card("Maintenance")

        desc = QLabel(
            "Reload the OUI vendor database without restarting the application. "
            "Use this after updating offenders.json or installing a new vendor list."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;")
        bl.addWidget(desc)

        btn = QPushButton("Reload OUI Database")
        btn.setFixedWidth(180)
        btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{ACCENT};"
            f" border:1px solid {ACCENT}; padding:4px 14px;"
            f" font-size:11px; border-radius:4px; }}"
            f"QPushButton:hover {{ background:{BTN_HOVER_BG}; }}"
        )
        btn.clicked.connect(self.reload_oui_requested.emit)
        bl.addWidget(btn, alignment=Qt.AlignmentFlag.AlignLeft)

        reset_btn = QPushButton("Reset all dismissed notices")
        reset_btn.setFixedWidth(220)
        reset_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_SECONDARY};"
            f" border:1px solid {BORDER}; padding:4px 14px;"
            f" font-size:11px; border-radius:4px; }}"
            f"QPushButton:hover {{ background:{BTN_HOVER_BG}; color:{TEXT_PRIMARY}; }}"
        )
        reset_btn.clicked.connect(self.reset_dismissed_requested.emit)
        bl.addWidget(reset_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        export_btn = QPushButton("Export All Data (ZIP)")
        export_btn.setFixedWidth(220)
        export_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_SECONDARY};"
            f" border:1px solid {BORDER}; padding:4px 14px;"
            f" font-size:11px; border-radius:4px; }}"
            f"QPushButton:hover {{ background:{BTN_HOVER_BG}; color:{TEXT_PRIMARY}; }}"
        )
        export_btn.clicked.connect(self.export_all_requested.emit)
        bl.addWidget(export_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        setup_btn = QPushButton("Run first-time setup")
        setup_btn.setFixedWidth(220)
        setup_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_SECONDARY};"
            f" border:1px solid {BORDER}; padding:4px 14px;"
            f" font-size:11px; border-radius:4px; }}"
            f"QPushButton:hover {{ background:{BTN_HOVER_BG}; color:{TEXT_PRIMARY}; }}"
        )
        setup_btn.clicked.connect(self.run_setup_requested.emit)
        bl.addWidget(setup_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        return card

    # ── Config completeness (HEALTH-4) ────────────────────────────────────────

    def _build_config_completeness_card(self) -> QFrame:
        card, bl = _card("Configuration Status")

        intro = QLabel(
            "Features that need attention are highlighted. "
            "Click a chip to jump to the relevant settings."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;")
        bl.addWidget(intro)

        from PyQt6.QtWidgets import QHBoxLayout as _HBox
        chips_row = _HBox()
        chips_row.setSpacing(8)

        self._cfg_chips: dict[str, QLabel] = {}
        for key, label in [
            ("notifications",   "Notifications"),
            ("sched_scan",      "Scheduled Scan"),
            ("monitor_resume",  "Monitor Resume"),
            ("digest",          "Weekly Digest"),
            ("cve_tracking",    "CVE Tracking"),
            ("automation",      "Automation"),
        ]:
            chip = QLabel(label)
            chip.setFixedHeight(24)
            chip.setStyleSheet(self._chip_style("grey"))
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setContentsMargins(10, 0, 10, 0)
            chips_row.addWidget(chip)
            self._cfg_chips[key] = chip

        chips_row.addStretch()
        bl.addLayout(chips_row)
        self.refresh_config_completeness()
        return card

    def _chip_style(self, state: str) -> str:
        if state == "green":
            return (
                f"font-size:10px; font-weight:bold; color:#065F46;"
                f" background:#D1FAE5; border:1px solid #10B981; border-radius:10px;"
                f" padding:0 10px;"
            )
        if state == "amber":
            return (
                f"font-size:10px; font-weight:bold; color:#92400E;"
                f" background:#FEF3C7; border:1px solid #F59E0B; border-radius:10px;"
                f" padding:0 10px;"
            )
        return (
            f"font-size:10px; font-weight:bold; color:#6B7280;"
            f" background:#F3F4F6; border:1px solid #D1D5DB; border-radius:10px;"
            f" padding:0 10px;"
        )

    def refresh_config_completeness(self, cve_count: int = 0, rule_count: int = 0) -> None:
        if not hasattr(self, "_cfg_chips"):
            return
        s = QSettings("NetSentinel", "NetSentinel")

        def _set(key: str, state: str) -> None:
            self._cfg_chips[key].setStyleSheet(self._chip_style(state))

        # Notifications — tray alerts on
        _set("notifications", "green" if s.value("tray/alerts_enabled", True, bool) else "grey")
        # Scheduled scan
        _set("sched_scan", "green" if s.value("sched_scan/enabled", False, bool) else "grey")
        # Monitor auto-resume — any monitor was persisted
        any_monitor = (
            s.value("monitor_persist/arp_running", False, bool)
            or s.value("monitor_persist/bandwidth_running", False, bool)
        )
        _set("monitor_resume", "green" if any_monitor else "grey")
        # Weekly digest
        email = s.value("digest/email", "", str)
        digest_on = s.value("digest/enabled", False, bool)
        if digest_on and email:
            _set("digest", "green")
        elif digest_on or email:
            _set("digest", "amber")
        else:
            _set("digest", "grey")
        # CVE tracking
        _set("cve_tracking", "green" if cve_count > 0 else "grey")
        # Automation rules
        _set("automation", "green" if rule_count > 0 else "grey")

    # ── App Health (HEALTH-1) ─────────────────────────────────────────────────

    def _build_health_card(self) -> QFrame:
        card, bl = _card("App Health")

        tbl = QTableWidget(6, 2)
        tbl.setHorizontalHeaderLabels(["Component", "Status"])
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.horizontalHeader().setStyleSheet(
            f"QHeaderView::section {{ background:{NAV_BAR}; color:white;"
            f" font-size:10px; font-weight:bold; padding:4px 8px; border:none; }}"
        )
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        tbl.setAlternatingRowColors(True)
        tbl.setStyleSheet(
            f"QTableWidget {{ font-size:11px; color:{TEXT_PRIMARY}; border:none;"
            f" background:{BG_CARD}; alternate-background-color:{BG_ALT_ROW}; gridline-color:{BORDER}; }}"
            f"QTableWidget::item {{ padding:4px 8px; }}"
        )
        tbl.setFixedHeight(168)

        _components = [
            "Scheduler",
            "ARP Monitor",
            "Bandwidth Monitor",
            "Report Scheduler",
            "Database",
            "Logger",
        ]
        for row, name in enumerate(_components):
            tbl.setItem(row, 0, QTableWidgetItem(name))
            tbl.setItem(row, 1, QTableWidgetItem("—"))
            tbl.setRowHeight(row, 24)

        bl.addWidget(tbl)
        self._health_table = tbl
        return card

    def refresh_health_status(self, statuses: dict) -> None:
        """Update the App Health table. statuses maps component name → (status_str, color_hint)."""
        if not hasattr(self, "_health_table"):
            return
        tbl = self._health_table
        for row in range(tbl.rowCount()):
            name_item = tbl.item(row, 0)
            if name_item is None:
                continue
            name = name_item.text()
            if name in statuses:
                status_str, ok = statuses[name]
                item = QTableWidgetItem(status_str)
                from PyQt6.QtGui import QColor
                item.setForeground(QColor(GREEN if ok else RED))
                tbl.setItem(row, 1, item)
