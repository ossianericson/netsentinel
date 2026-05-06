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

from ui.styles import (
    ACCENT, AMBER, BG_CARD, BORDER, BTN_HOVER_BG,
    CARD_HDR_BORDER, CARD_RADIUS, GREEN, RED, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY,
)


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
    lbl.setStyleSheet(f"color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;")
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


def _btn(label: str, color: str = ACCENT) -> QPushButton:
    b = QPushButton(label)
    b.setFixedHeight(26)
    b.setStyleSheet(
        f"QPushButton{{background:{BG_CARD};color:{color};"
        f"border:1px solid {color};border-radius:2px;"
        f"padding:0 10px;font-size:11px;}}"
        f"QPushButton:hover{{background:{BTN_HOVER_BG};}}"
    )
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
        desc.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY}; border:none;")
        bl.addWidget(desc)

        qs = QSettings("NetSentinel", "NetSentinel")

        self._chk_enabled = QCheckBox("Enable REST API  (disabled by default)")
        self._chk_enabled.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY};")
        self._chk_enabled.setChecked(qs.value("rest_api/enabled", False, type=bool))
        self._chk_enabled.stateChanged.connect(self._on_enable_changed)
        bl.addWidget(self._chk_enabled)

        port_row = QHBoxLayout()
        port_row.setSpacing(8)
        port_lbl = QLabel("Port:")
        port_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY}; border:none;")
        self._spin_port = QSpinBox()
        self._spin_port.setRange(1024, 65535)
        self._spin_port.setValue(int(qs.value("rest_api/port", 8765)))
        self._spin_port.setFixedWidth(90)
        self._spin_port.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; padding:2px 4px;"
        )
        self._spin_port.valueChanged.connect(self._on_port_changed)
        port_row.addWidget(port_lbl)
        port_row.addWidget(self._spin_port)
        port_row.addStretch()
        bl.addLayout(port_row)

        self._chk_external = QCheckBox(
            "Allow external access (bind 0.0.0.0 — exposes API to your network)"
        )
        self._chk_external.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY};")
        self._chk_external.setChecked(qs.value("rest_api/external", False, type=bool))
        self._chk_external.stateChanged.connect(self._on_external_changed)
        bl.addWidget(self._chk_external)

        self._lbl_warning = QLabel(
            "WARNING: Enabling external access exposes the API to all devices on your network. "
            "Keep your API key secret and ensure your firewall is configured appropriately."
        )
        self._lbl_warning.setWordWrap(True)
        self._lbl_warning.setStyleSheet(
            f"font-size:11px; color:{AMBER}; background:#FFF8E7;"
            f" border:1px solid {AMBER}; padding:6px 8px;"
        )
        self._lbl_warning.setVisible(self._chk_external.isChecked())
        bl.addWidget(self._lbl_warning)

        port_val = int(qs.value("rest_api/port", 8765))
        self._lbl_other_devices = QLabel(
            f"To access from another device on your network:\n"
            f"1. Enable external access above.\n"
            f"2. Find this machine's IP (run  ipconfig  in a terminal).\n"
            f"3. Open:  http://[this-machine-IP]:{port_val}/dashboard"
        )
        self._lbl_other_devices.setWordWrap(True)
        self._lbl_other_devices.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        self._lbl_other_devices.setVisible(self._chk_external.isChecked())
        bl.addWidget(self._lbl_other_devices)

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
        self._btn_show_key = _btn("Show Key")
        self._btn_show_key.clicked.connect(self._show_api_key)
        self._btn_regen_key = _btn("Regenerate", RED)
        self._btn_regen_key.setStyleSheet(
            f"QPushButton{{background:{BG_CARD};color:{RED};"
            f"border:1px solid {RED};border-radius:2px;"
            f"padding:0 10px;font-size:11px;}}"
            f"QPushButton:hover{{background:#FFF0F0;}}"
        )
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
        self._lbl_dot.setStyleSheet(f"font-size:16px; color:{TEXT_MUTED}; border:none;")
        self._lbl_status = QLabel("Checking…")
        self._lbl_status.setOpenExternalLinks(True)
        self._lbl_status.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY}; border:none;")

        self._btn_refresh = _btn("↻ Refresh")
        self._btn_refresh.clicked.connect(self._probe_status)

        self._btn_action = QPushButton("Start API")
        self._btn_action.setFixedHeight(26)
        self._btn_action.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:#FFFFFF;"
            f"border:1px solid {ACCENT};border-radius:2px;"
            f"padding:0 12px;font-size:11px;font-weight:bold;}}"
            f"QPushButton:hover{{background:#005A9E;}}"
        )
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
        self._endpoint_ref.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; font-family:Consolas,monospace;"
            f" border:none; padding:4px 0 0 0;"
        )
        self._endpoint_ref.setVisible(False)
        bl.addWidget(self._endpoint_ref)

        QTimer.singleShot(200, self._probe_status)
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

        self._lbl_dot.setStyleSheet(f"font-size:16px; color:{TEXT_MUTED}; border:none;")
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
            self._lbl_dot.setStyleSheet(f"font-size:16px; color:{GREEN}; border:none;")
            self._lbl_status.setText(
                f'Running on port {port} — '
                f'<a href="{base}/dashboard" style="color:{ACCENT};">open dashboard ↗</a>'
            )
            self._btn_action.setVisible(False)
        else:
            self._lbl_dot.setStyleSheet(f"font-size:16px; color:{AMBER}; border:none;")
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
        self._lbl_dot.setStyleSheet(f"font-size:16px; color:{TEXT_MUTED}; border:none;")
        self._lbl_status.setText("Disabled — enable above to activate")
        self._btn_action.setVisible(False)
        self._endpoint_ref.setVisible(False)

    def _update_endpoint_ref(self, base: str) -> None:
        _ENDPOINTS = [
            ("/health",        "Health check"),
            ("/dashboard",     "Browser dashboard"),
            ("/devices",       "Discovered devices"),
            ("/alerts",        "Recent alerts"),
            ("/uptime/<ip>",   "Uptime % for a device"),
            ("/speed-history", "Speed test history"),
            ("/grade",         "Network grade and score"),
        ]
        rows = []
        for path, desc in _ENDPOINTS:
            if "<" not in path:
                full = f"{base}{path}"
                link = (
                    f'<a href="{full}" style="color:{ACCENT}; font-family:Consolas;">'
                    f"GET {path}</a>"
                )
            else:
                link = f'<span style="font-family:Consolas;">GET {path}</span>'
            rows.append(f'{link}  <span style="color:{TEXT_MUTED};">— {desc}</span>')
        auth_line = (
            f'<span style="color:{TEXT_MUTED};">Auth: '
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
        self._worker.started_ok.connect(lambda _: QTimer.singleShot(600, self._probe_status))
        self._worker.start()

        self._lbl_dot.setStyleSheet(f"font-size:16px; color:{TEXT_MUTED}; border:none;")
        self._lbl_status.setText("Starting…")
        self._btn_action.setVisible(False)
