"""
REST API page — configure and monitor the local read-only HTTP API.

Lives in the left toolbar under Tools. Replaces the settings card.
"""
from __future__ import annotations

import sys
from typing import Optional

from PyQt6.QtCore import Qt, QSettings, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from ui import styles as _s


# ── HTTP probe worker ─────────────────────────────────────────────────────────

class _ProbeWorker(QThread):
    """Check whether the REST API server is accepting connections."""
    result = pyqtSignal(bool)

    def __init__(self, host: str, port: int, parent=None):
        super().__init__(parent)
        self._host = "127.0.0.1" if host == "0.0.0.0" else host
        self._port = port

    def run(self) -> None:
        import socket
        try:
            with socket.create_connection((self._host, self._port), timeout=1.5):
                self.result.emit(True)
        except OSError:
            self.result.emit(False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _page_header(title: str, subtitle: str = "") -> QFrame:
    container = QFrame()
    container.setObjectName("pageHeader")
    _s.themed_ss(container, "QFrame#pageHeader {{ background: transparent; border: none;"
        " border-bottom: 1px solid {BORDER}; }}")
    vbox = QVBoxLayout(container)
    vbox.setContentsMargins(20, 16, 20, 12)
    vbox.setSpacing(2)
    t = QLabel(title)
    _s.themed_ss(t, "color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold;"
        "padding:0; background:transparent; border:none;")
    vbox.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        _s.themed_ss(s, "color:{TEXT_SECONDARY}; font-size:11px;"
            "padding:0; background:transparent; border:none;")
        vbox.addWidget(s)
    return container


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("card")
    _s.themed_ss(card, "QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
        "border-radius:{CARD_RADIUS};}}")
    cl = QVBoxLayout(card)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(0)

    tb = QFrame()
    tb.setFixedHeight(32)
    _s.themed_ss(tb, "background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};")
    tbl = QHBoxLayout(tb)
    tbl.setContentsMargins(12, 0, 12, 0)
    lbl = QLabel(title)
    _s.themed_ss(lbl, "color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;")
    tbl.addWidget(lbl)
    tbl.addStretch()
    cl.addWidget(tb)

    body = QWidget()
    _s.themed_ss(body, "background:{BG_CARD};")
    bl = QVBoxLayout(body)
    bl.setContentsMargins(16, 12, 16, 14)
    bl.setSpacing(10)
    cl.addWidget(body)
    return card, bl


def _btn(label: str, color_name: str = "ACCENT") -> QPushButton:
    b = QPushButton(label)
    b.setFixedHeight(26)
    _s.themed_ss(b, lambda cn=color_name: (
        f"QPushButton{{background:{_s.BG_CARD};color:{getattr(_s, cn)};"
        f"border:1px solid {getattr(_s, cn)};border-radius:2px;"
        f"padding:0 10px;font-size:11px;}}"
        f"QPushButton:hover{{background:{_s.BTN_HOVER_BG};}}"
        f"QPushButton:pressed {{ color:{_s.TEXT_PRIMARY}; }}"
    ))
    return b


# ── Page ──────────────────────────────────────────────────────────────────────

class RestApiPage(QWidget):
    """Standalone page for configuring and monitoring the local REST API."""

    def __init__(self, store=None, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._store = store
        self._probe: Optional[_ProbeWorker] = None
        self._worker = None  # RestApiWorker managed by this page (hot-start path)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(_page_header(
            "Local REST API",
            "Read-only HTTP API for Grafana, Home Assistant, and scripts",
        ))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;")

        body = QWidget()
        body.setObjectName("contentArea")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 16, 20, 20)
        bl.setSpacing(12)

        bl.addWidget(self._build_config_card())
        bl.addWidget(self._build_status_card())
        bl.addStretch()

        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

    # ── Config card ───────────────────────────────────────────────────────────

    def _build_config_card(self) -> QFrame:
        card, bl = _card("Configuration")

        desc = QLabel(
            "Expose a read-only HTTP API on localhost so external tools "
            "(Grafana, Home Assistant, scripts) can query NetSentinel data. "
            "Changes take effect after restarting the app."
        )
        desc.setWordWrap(True)
        _s.themed_ss(desc, "font-size:11px; color:{TEXT_SECONDARY}; border:none;")
        bl.addWidget(desc)

        qs = QSettings("NetSentinel", "NetSentinel")

        self._chk_enabled = QCheckBox("Enable REST API  (disabled by default)")
        _s.themed_ss(self._chk_enabled, "font-size:11px; color:{TEXT_PRIMARY};")
        self._chk_enabled.setChecked(qs.value("rest_api/enabled", False, type=bool))
        self._chk_enabled.stateChanged.connect(self._on_enable_changed)
        bl.addWidget(self._chk_enabled)

        port_row = QHBoxLayout()
        port_row.setSpacing(8)
        port_lbl = QLabel("Port:")
        _s.themed_ss(port_lbl, "font-size:11px; color:{TEXT_PRIMARY}; border:none;")
        self._spin_port = QSpinBox()
        self._spin_port.setRange(1024, 65535)
        self._spin_port.setValue(int(qs.value("rest_api/port", 8765)))
        self._spin_port.setFixedWidth(_s.SPINBOX_WIDTH_WIDE_PLAIN)
        # background-color/color/font-size ONLY -- border/padding make the
        # +/- buttons unclickable under windows11 (see style_spinbox() docstring).
        _s.themed_ss(self._spin_port, "font-size:11px; color:{TEXT_PRIMARY}; background:{BG_DARK};")
        _s.style_spinbox(self._spin_port)
        self._spin_port.valueChanged.connect(self._on_port_changed)
        port_row.addWidget(port_lbl)
        port_row.addWidget(self._spin_port)
        port_row.addStretch()
        bl.addLayout(port_row)

        self._chk_external = QCheckBox(
            "Allow external access (bind 0.0.0.0 — exposes API to your network)"
        )
        _s.themed_ss(self._chk_external, "font-size:11px; color:{TEXT_PRIMARY};")
        self._chk_external.setChecked(qs.value("rest_api/external", False, type=bool))
        self._chk_external.stateChanged.connect(self._on_external_changed)
        bl.addWidget(self._chk_external)

        self._lbl_warning = QLabel(
            "WARNING: Enabling external access exposes the API to all devices on your network. "
            "Keep your API key secret and ensure your firewall is configured appropriately."
        )
        self._lbl_warning.setWordWrap(True)
        _s.themed_ss(self._lbl_warning, "font-size:11px; color:{AMBER}; background:{AMBER_BG};"
            " border:1px solid {AMBER}; padding:6px 8px;")
        bl.addWidget(self._lbl_warning)
        self._lbl_warning.setVisible(self._chk_external.isChecked())

        port_val = int(qs.value("rest_api/port", 8765))
        self._lbl_other_devices = QLabel(
            f"To access from another device on your network:\n"
            f"1. Enable external access above.\n"
            f"2. Find this machine's IP (run  ipconfig  in a terminal).\n"
            f"3. Open:  http://[this-machine-IP]:{port_val}/dashboard"
        )
        self._lbl_other_devices.setWordWrap(True)
        _s.themed_ss(self._lbl_other_devices, "font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;")
        bl.addWidget(self._lbl_other_devices)
        self._lbl_other_devices.setVisible(self._chk_external.isChecked())

        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        key_lbl = QLabel("API Key:")
        _s.themed_ss(key_lbl, "font-size:11px; color:{TEXT_PRIMARY}; border:none;")
        self._txt_api_key = QLineEdit()
        self._txt_api_key.setReadOnly(True)
        self._txt_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._txt_api_key.setPlaceholderText("Click 'Show Key' to view or generate")
        _s.themed_ss(self._txt_api_key, "font-size:11px; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; padding:2px 6px;")
        self._btn_show_key = _btn("Show Key")
        self._btn_show_key.clicked.connect(self._show_api_key)
        self._btn_regen_key = _btn("Regenerate", "RED")
        _s.themed_ss(self._btn_regen_key, "QPushButton{{background:{BG_CARD};color:{RED};"
            "border:1px solid {RED};border-radius:2px;"
            "padding:0 10px;font-size:11px;}}"
            "QPushButton:hover{{background:{PRO_WARN_BG};}}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}")
        self._btn_regen_key.clicked.connect(self._regen_api_key)
        key_row.addWidget(key_lbl)
        key_row.addWidget(self._txt_api_key, 1)
        key_row.addWidget(self._btn_show_key)
        key_row.addWidget(self._btn_regen_key)
        bl.addLayout(key_row)

        return card

    # ── Status card ───────────────────────────────────────────────────────────

    def _build_status_card(self) -> QFrame:
        card, bl = _card("Status & Endpoints")

        status_row = QHBoxLayout()
        status_row.setSpacing(8)

        self._lbl_dot = QLabel("●")
        _s.themed_ss(self._lbl_dot, "font-size:16px; color:{TEXT_MUTED}; border:none;")
        self._lbl_status = QLabel("Checking…")
        self._lbl_status.setOpenExternalLinks(True)
        _s.themed_ss(self._lbl_status, "font-size:11px; color:{TEXT_SECONDARY}; border:none;")

        self._btn_refresh = _btn("↻ Refresh")
        self._btn_refresh.clicked.connect(self._probe_status)

        self._btn_action = QPushButton("Start API")
        self._btn_action.setFixedHeight(26)
        _s.themed_ss(self._btn_action, "QPushButton{{background:{ACCENT};color:{WHITE};"
            "border:1px solid {ACCENT};border-radius:2px;"
            "padding:0 12px;font-size:11px;font-weight:bold;}}"
            "QPushButton:hover{{background:{ACCENT_DARK};}}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}")
        self._btn_action.clicked.connect(self._on_action)
        self._btn_action.setVisible(False)

        status_row.addWidget(self._lbl_dot)
        status_row.addWidget(self._lbl_status, 1)
        status_row.addWidget(self._btn_refresh)
        status_row.addWidget(self._btn_action)
        bl.addLayout(status_row)

        self._endpoint_ref = QLabel()
        self._endpoint_ref.setOpenExternalLinks(True)
        self._endpoint_ref.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        self._endpoint_ref.setWordWrap(True)
        _s.themed_ss(self._endpoint_ref, "font-size:10px; color:{TEXT_SECONDARY}; font-family:Consolas,monospace;"
            " border:none; padding:4px 0 0 0;")
        self._endpoint_ref.setVisible(False)
        bl.addWidget(self._endpoint_ref)

        _t = QTimer(self)
        _t.setSingleShot(True)
        _t.timeout.connect(self._probe_status)
        _t.start(200)
        return card

    # ── Handlers ─────────────────────────────────────────────────────────────

    def _on_enable_changed(self, state: int) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("rest_api/enabled", bool(state))
        self._probe_status()

    def _on_port_changed(self, value: int) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue("rest_api/port", value)

    def _on_external_changed(self, state: int) -> None:
        enabled = bool(state)
        QSettings("NetSentinel", "NetSentinel").setValue("rest_api/external", enabled)
        self._lbl_warning.setVisible(enabled)
        self._lbl_other_devices.setVisible(enabled)

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

    def _probe_status(self) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        enabled  = qs.value("rest_api/enabled", False, type=bool)
        port     = int(qs.value("rest_api/port", 8765))
        external = qs.value("rest_api/external", False, type=bool)

        if not enabled:
            self._set_disabled()
            return

        _s.themed_ss(self._lbl_dot, "font-size:16px; color:{TEXT_MUTED}; border:none;")
        self._lbl_status.setText("Checking…")
        self._btn_action.setVisible(False)

        if self._probe and self._probe.isRunning():
            return

        host = "0.0.0.0" if external else "127.0.0.1"
        self._probe = _ProbeWorker(host, port, parent=self)
        self._probe.result.connect(lambda ok: self._on_probe_result(ok, port))
        self._probe.start()

    def _on_probe_result(self, running: bool, port: int) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        if not qs.value("rest_api/enabled", False, type=bool):
            self._set_disabled()
            return

        base = f"http://localhost:{port}"
        if running:
            _s.themed_ss(self._lbl_dot, "font-size:16px; color:{GREEN}; border:none;")
            self._lbl_status.setText(
                f'Running on port {port} — '
                f'<a href="{base}/dashboard" style="color:{_s.ACCENT};">open dashboard ↗</a>'
            )
            self._btn_action.setVisible(False)
        else:
            _s.themed_ss(self._lbl_dot, "font-size:16px; color:{AMBER}; border:none;")
            label = "Start API" if self._store is not None else "Restart App"
            self._lbl_status.setText(
                "Not running — click to start" if self._store is not None
                else "Not running — restart the app to apply your settings"
            )
            self._btn_action.setText(label)
            self._btn_action.setVisible(True)

        self._update_endpoint_ref(base)
        self._endpoint_ref.setVisible(True)

    def _set_disabled(self) -> None:
        _s.themed_ss(self._lbl_dot, "font-size:16px; color:{TEXT_MUTED}; border:none;")
        self._lbl_status.setText("Disabled — enable above to activate")
        self._btn_action.setVisible(False)
        self._endpoint_ref.setVisible(False)

    def _update_endpoint_ref(self, base: str) -> None:
        _ENDPOINTS = [
            ("/health",                             "Health check"),
            ("/dashboard",                          "Browser dashboard"),
            ("/devices",                            "Discovered devices"),
            ("/alerts",                             "Recent alerts"),
            ("/uptime/<ip>",                        "Uptime % for a device"),
            ("/speed-history",                      "Speed test history"),
            ("/grade",                              "Network grade and score"),
            ("/service-catalog",                    "List diagnosable services"),
            ("/service-diagnostics/<service_id>",   "Run connectivity diagnostics for a service"),
        ]
        rows = []
        for path, desc in _ENDPOINTS:
            if "<" not in path:
                full = f"{base}{path}"
                link = (
                    f'<a href="{full}" style="color:{_s.ACCENT}; font-family:Consolas;">'
                    f"GET {path}</a>"
                )
            else:
                link = f'<span style="font-family:Consolas;">GET {path}</span>'
            rows.append(f'{link}  <span style="color:{_s.TEXT_MUTED};">— {desc}</span>')
        auth_line = (
            f'<span style="color:{_s.TEXT_MUTED};">Auth: '
            f"X-API-Key: &lt;key&gt;  or  ?api_key=&lt;key&gt;</span>"
        )
        self._endpoint_ref.setText("<br>".join(rows) + "<br>" + auth_line)

    def _on_action(self) -> None:
        if self._store is not None:
            self._hot_start()
        else:
            from PyQt6.QtCore import QProcess, QCoreApplication
            QProcess.startDetached(sys.executable, sys.argv)
            QCoreApplication.quit()

    def _hot_start(self) -> None:
        from workers.rest_api_worker import RestApiWorker
        from modules.rest_api import get_or_create_api_key

        qs       = QSettings("NetSentinel", "NetSentinel")
        port     = int(qs.value("rest_api/port", 8765))
        external = qs.value("rest_api/external", False, type=bool)
        host     = "0.0.0.0" if external else "127.0.0.1"

        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(3000)

        get_or_create_api_key()

        self._worker = RestApiWorker(store=self._store, parent=self)
        self._worker.set_bind(host, port)
        self._worker.error.connect(lambda msg: print(f"[REST API] {msg}", flush=True))
        def _on_started_ok(_: object) -> None:
            _t = QTimer(self)
            _t.setSingleShot(True)
            _t.timeout.connect(self._probe_status)
            _t.start(600)
        self._worker.started_ok.connect(_on_started_ok)
        self._worker.start()

        _s.themed_ss(self._lbl_dot, "font-size:16px; color:{TEXT_MUTED}; border:none;")
        self._lbl_status.setText("Starting…")
        self._btn_action.setVisible(False)
