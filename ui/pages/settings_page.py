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

from pathlib import Path

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
    BG_HOVER,
)

from ui.pages.settings_cards import (
    _SettingsCardsMixin,
    _NotifTestWorker,
    _card, _page_header, _integr_cert_count, _integr_svc_count,
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

    def _on_compact_toggled(self, checked: bool) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue("display/compact_rows", checked)
        self._mark_dirty()

    def _on_tooltip_toggled(self, checked: bool) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue("display/tooltips_enabled", checked)
        self._mark_dirty()

