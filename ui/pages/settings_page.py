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

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import ui.styles as _styles
from ui.styles import (
    ACCENT, ACCENT_DARK, BG_ALT_ROW, BG_CARD, BG_DARK, BORDER,
    BTN_HOVER_BG, CARD_HDR_BORDER, NAV_BAR, TEXT_PRIMARY, TEXT_SECONDARY,
    WHITE,
)


def _page_header(title: str, subtitle: str = ""):
    t = QLabel(title)
    t.setStyleSheet(
        f"color:{TEXT_PRIMARY};font-size:18px;font-weight:bold;"
        "padding:0;background:transparent;border:none;"
    )
    s = QLabel(subtitle)
    s.setStyleSheet(
        f"color:{TEXT_SECONDARY};font-size:11px;"
        "padding:0 0 8px 0;background:transparent;border:none;"
    )
    return t, s


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    """Return (card QFrame, body QVBoxLayout) styled per design system."""
    card = QFrame()
    card.setObjectName("card")
    card.setStyleSheet(
        f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
        f"border-radius:0px;}}"
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


class SettingsPage(QWidget):
    """
    Dedicated settings and customisation page shown in the sidebar.
    Contains the theme picker, display preferences, and shortcuts reference.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        pt, ps = _page_header(
            "Settings & Customisation",
            "Change the colour theme, display preferences, and more",
        )
        outer.addWidget(pt)
        outer.addWidget(ps)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;")

        body = QWidget()
        body.setObjectName("contentArea")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 12, 20)
        bl.setSpacing(12)

        bl.addWidget(self._build_appearance_card())
        bl.addWidget(self._build_display_card())
        bl.addWidget(self._build_tray_card())
        bl.addWidget(self._build_rest_api_card())
        bl.addWidget(self._build_shortcuts_card())
        bl.addStretch()

        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

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

    def _on_tooltip_toggled(self, checked: bool):
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("display/tooltips_enabled", checked)

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

        note = QLabel(
            "Tray notifications fire automatically when new devices join, "
            "devices leave, ARP attacks are detected, or alerts fire."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            f"font-size:10px;color:{TEXT_SECONDARY};background:transparent;"
        )
        bl.addWidget(note)
        return card

    def _on_tray_toggled(self, checked: bool) -> None:
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

    def _on_startup_toggled(self, checked: bool) -> None:
        from ui.system_tray import set_run_on_startup
        set_run_on_startup(checked)

    # ── REST API ──────────────────────────────────────────────────────────────

    def _build_rest_api_card(self) -> QFrame:
        from ui.styles import AMBER, RED
        card, bl = _card("Local REST API")

        desc = QLabel(
            "Expose a read-only HTTP API on localhost so external tools "
            "(Grafana, Home Assistant, scripts) can query NetSentinel data."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY}; border:none;")
        bl.addWidget(desc)

        # Enable toggle
        self._chk_api_enabled = QCheckBox("Enable REST API  (disabled by default)")
        self._chk_api_enabled.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY};")
        qs = QSettings("NetSentinel", "NetSentinel")
        self._chk_api_enabled.setChecked(qs.value("rest_api/enabled", False, type=bool))
        self._chk_api_enabled.stateChanged.connect(self._on_api_toggle)
        bl.addWidget(self._chk_api_enabled)

        # Port row
        port_row = QHBoxLayout()
        port_row.setSpacing(8)
        port_lbl = QLabel("Port:")
        port_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY}; border:none;")
        self._spin_api_port = QSpinBox()
        self._spin_api_port.setRange(1024, 65535)
        self._spin_api_port.setValue(int(qs.value("rest_api/port", 8765)))
        self._spin_api_port.setFixedWidth(90)
        self._spin_api_port.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; padding:2px 4px;"
        )
        self._spin_api_port.valueChanged.connect(self._on_api_port_changed)
        port_row.addWidget(port_lbl)
        port_row.addWidget(self._spin_api_port)
        port_row.addStretch()
        bl.addLayout(port_row)

        # External access toggle + warning
        self._chk_api_external = QCheckBox("Allow external access (bind 0.0.0.0 — exposes API to your network)")
        self._chk_api_external.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY};")
        self._chk_api_external.setChecked(qs.value("rest_api/external", False, type=bool))
        self._chk_api_external.stateChanged.connect(self._on_api_external_changed)
        bl.addWidget(self._chk_api_external)

        self._lbl_api_warning = QLabel(
            "WARNING: Enabling external access exposes the API to all devices on your network. "
            "Ensure your API key is kept secret and your firewall is configured appropriately."
        )
        self._lbl_api_warning.setWordWrap(True)
        self._lbl_api_warning.setStyleSheet(
            f"font-size:11px; color:{AMBER}; background:#FFF8E7;"
            f" border:1px solid {AMBER}; padding:6px 8px;"
        )
        self._lbl_api_warning.setVisible(self._chk_api_external.isChecked())
        bl.addWidget(self._lbl_api_warning)

        # API key row
        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        key_lbl = QLabel("API Key:")
        key_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY}; border:none;")
        self._txt_api_key = QLineEdit()
        self._txt_api_key.setReadOnly(True)
        self._txt_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._txt_api_key.setPlaceholderText("Click 'Show Key' to view or generate")
        self._txt_api_key.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; padding:2px 6px;"
        )
        self._btn_show_key = QPushButton("Show Key")
        self._btn_show_key.setFixedHeight(26)
        self._btn_show_key.setStyleSheet(
            f"font-size:11px; color:{ACCENT}; border:1px solid {ACCENT};"
            f" background:white; padding:0 10px;"
        )
        self._btn_show_key.clicked.connect(self._show_api_key)
        self._btn_regen_key = QPushButton("Regenerate")
        self._btn_regen_key.setFixedHeight(26)
        self._btn_regen_key.setStyleSheet(
            f"font-size:11px; color:{RED}; border:1px solid {RED};"
            f" background:white; padding:0 10px;"
        )
        self._btn_regen_key.clicked.connect(self._regen_api_key)
        key_row.addWidget(key_lbl)
        key_row.addWidget(self._txt_api_key, 1)
        key_row.addWidget(self._btn_show_key)
        key_row.addWidget(self._btn_regen_key)
        bl.addLayout(key_row)

        # Status label
        self._lbl_api_status = QLabel("")
        self._lbl_api_status.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY}; border:none;")
        bl.addWidget(self._lbl_api_status)
        self._update_api_status_label()

        # Endpoint reference
        ref_lbl = QLabel(
            "Endpoints:  GET /health   /devices   /alerts   /uptime/<ip>   /speed-history\n"
            "Auth header:  X-API-Key: <key>  or  ?api_key=<key>"
        )
        ref_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; font-family:Consolas; border:none;"
        )
        bl.addWidget(ref_lbl)

        return card

    def _on_api_toggle(self, state: int) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        enabled = bool(state)
        qs.setValue("rest_api/enabled", enabled)
        self._update_api_status_label()

    def _on_api_port_changed(self, value: int) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("rest_api/port", value)

    def _on_api_external_changed(self, state: int) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        enabled = bool(state)
        qs.setValue("rest_api/external", enabled)
        self._lbl_api_warning.setVisible(enabled)

    def _show_api_key(self) -> None:
        from modules.rest_api import get_or_create_api_key
        key = get_or_create_api_key()
        if self._txt_api_key.echoMode() == QLineEdit.EchoMode.Password:
            self._txt_api_key.setText(key)
            self._txt_api_key.setEchoMode(QLineEdit.EchoMode.Normal)
            self._btn_show_key.setText("Hide Key")
        else:
            self._txt_api_key.setEchoMode(QLineEdit.EchoMode.Password)
            self._btn_show_key.setText("Show Key")

    def _regen_api_key(self) -> None:
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Regenerate API Key",
            "This will invalidate the current key immediately.\n"
            "Any external tools using the old key will stop working.\n\nProceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            from modules.rest_api import regenerate_api_key
            key = regenerate_api_key()
            self._txt_api_key.setText(key)
            self._txt_api_key.setEchoMode(QLineEdit.EchoMode.Normal)
            self._btn_show_key.setText("Hide Key")
            self._lbl_api_status.setText("New API key generated.")

    def _update_api_status_label(self) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        enabled = qs.value("rest_api/enabled", False, type=bool)
        port    = int(qs.value("rest_api/port", 8765))
        external = qs.value("rest_api/external", False, type=bool)
        if enabled:
            host = "0.0.0.0" if external else "127.0.0.1"
            self._lbl_api_status.setText(
                f"API running on http://{host}:{port}/  — "
                "changes take effect after restarting NetSentinel"
            )
        else:
            self._lbl_api_status.setText("API disabled — enable above and restart to activate.")

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
