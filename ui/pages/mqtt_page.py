"""
MQTT / Home Assistant Integration Page.

Sections:
  • Connection config card (broker, port, username, password via keychain,
    base topic, HA Discovery toggle)
  • Connection status indicator + Connect / Disconnect buttons
  • Event log — last N published events
  • Test Publish button — sends a sample device event to verify the broker
"""

from __future__ import annotations

import datetime
from typing import Optional

import keyring
from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
    QVBoxLayout, QWidget,
)

from ui import styles as _s
from modules.mqtt_publisher import MqttPublisher, get_publisher, _PAHO_AVAILABLE


_KEYCHAIN_SVC = "NetSentinel"
_KEYCHAIN_KEY = "mqtt/password"


def _get_secret() -> str:
    """Read the stored MQTT password, degrading to "" when no keyring backend
    is available (e.g. headless Linux / CI). Without this guard, constructing
    this page raised keyring.errors.NoKeyringError and aborted the whole
    Dashboard build. Mirrors _load_secret in notif_channel_panels/threat_intel."""
    try:
        return keyring.get_password(_KEYCHAIN_SVC, _KEYCHAIN_KEY) or ""
    except Exception:
        return ""  # no keyring backend — treat the secret as unset


def _set_secret(pw: str) -> None:
    try:
        keyring.set_password(_KEYCHAIN_SVC, _KEYCHAIN_KEY, pw)
    except Exception:
        pass  # no keyring backend — silently skip persisting the secret


# ── Connection worker ─────────────────────────────────────────────────────────

class _ConnectWorker(QThread):
    """Runs publisher.connect() off the main thread."""

    status_changed = pyqtSignal(bool, str)   # connected, message

    def __init__(self, publisher: MqttPublisher, parent=None):
        super().__init__(parent)
        self._pub = publisher

    def run(self) -> None:
        self._pub.connect()


# ── Card helper ───────────────────────────────────────────────────────────────

def _card(title: str) -> tuple[QFrame, QVBoxLayout, QHBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    _s.themed_ss(frame, "QFrame#card {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS}; }}")
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    hdr = QFrame()
    hdr.setFixedHeight(32)
    _s.themed_ss(hdr, "background:{BG_CARD}; border-bottom:1px solid {CARD_HDR_BORDER}; border-radius:0px;")
    hdr_lay = QHBoxLayout(hdr)
    hdr_lay.setContentsMargins(12, 0, 10, 0)
    t = QLabel(title.upper())
    _s.themed_ss(t, "color:{TEXT_PRIMARY}; font-weight:bold; font-size:11px;"
        " letter-spacing:0.5px; background:transparent; border:none;")
    hdr_lay.addWidget(t)
    hdr_lay.addStretch()
    outer.addWidget(hdr)
    body = QVBoxLayout()
    body.setContentsMargins(12, 10, 12, 10)
    body.setSpacing(8)
    outer.addLayout(body, 1)
    return frame, body, hdr_lay


# ── Main page ─────────────────────────────────────────────────────────────────

class MqttPage(QWidget):
    """
    MQTT / Home Assistant integration configuration page.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._publisher  = get_publisher()
        self._worker: Optional[_ConnectWorker] = None
        self._setup_ui()
        self._load_settings()

        if not _PAHO_AVAILABLE:
            self._log_line("⚠  paho-mqtt is not installed. Run: pip install paho-mqtt")

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border:none; }")
        outer_lay = QVBoxLayout(self)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.addWidget(scroll)

        inner = QWidget()
        scroll.setWidget(inner)
        root = QVBoxLayout(inner)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Page header
        title = QLabel("MQTT / Home Assistant")
        _s.themed_ss(title, "color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold;"
            " background:transparent; border:none;")
        sub = QLabel(
            "Publish device join/leave, alerts, and uptime events to an MQTT broker. "
            "Home Assistant MQTT discovery is supported."
        )
        sub.setWordWrap(True)
        _s.themed_ss(sub, "color:{TEXT_SECONDARY}; font-size:11px;"
            " background:transparent; border:none; padding:0 0 4px 0;")
        root.addWidget(title)
        root.addWidget(sub)

        # ── Config card ───────────────────────────────────────────────────────
        cfg_frame, cfg_body, _ = _card("Broker Configuration")

        _in_qss = (
            "QLineEdit {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:2px; padding:3px 6px; font-size:11px; color:{TEXT_PRIMARY}; }}"
            "QLineEdit:focus {{ border-color:{ACCENT}; }}"
        )

        def _row(label: str, widget: QWidget) -> None:
            row = QHBoxLayout()
            row.setSpacing(8)
            lbl = QLabel(label)
            lbl.setFixedWidth(100)
            _s.themed_ss(lbl, "color:{TEXT_PRIMARY}; font-size:11px;")
            row.addWidget(lbl)
            row.addWidget(widget, 1)
            cfg_body.addLayout(row)

        self._host = QLineEdit()
        self._host.setPlaceholderText("192.168.1.x or hostname")
        _s.themed_ss(self._host, _in_qss)
        _row("Broker host:", self._host)

        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(1883)
        _s.themed_ss(self._port, "QSpinBox {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:2px; padding:3px 6px; font-size:11px; color:{TEXT_PRIMARY}; }}")
        _row("Port:", self._port)

        self._username = QLineEdit()
        self._username.setPlaceholderText("Leave blank for anonymous")
        _s.themed_ss(self._username, _in_qss)
        _row("Username:", self._username)

        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setPlaceholderText("Stored in OS keychain")
        _s.themed_ss(self._password, _in_qss)
        _row("Password:", self._password)

        self._base_topic = QLineEdit()
        self._base_topic.setPlaceholderText("netsentinel")
        _s.themed_ss(self._base_topic, _in_qss)
        _row("Base topic:", self._base_topic)

        _chk_qss = (
            "QCheckBox {{ color:{TEXT_PRIMARY}; font-size:11px; }}"
            "QCheckBox::indicator {{ width:13px; height:13px; border:1px solid {BORDER};"
            " border-radius:2px; background:{BG_CARD}; }}"
            "QCheckBox::indicator:checked {{ background:{ACCENT}; border-color:{ACCENT}; }}"
        )
        self._chk_ha = QCheckBox("Enable Home Assistant MQTT Discovery")
        self._chk_ha.setChecked(True)
        _s.themed_ss(self._chk_ha, _chk_qss)
        cfg_body.addWidget(self._chk_ha)

        self._chk_devices = QCheckBox("Publish device join / leave events")
        self._chk_alerts  = QCheckBox("Publish alert events")
        self._chk_uptime  = QCheckBox("Publish uptime / RTT state changes")
        for c in (self._chk_devices, self._chk_alerts, self._chk_uptime):
            c.setChecked(True)
            _s.themed_ss(c, _chk_qss)
            cfg_body.addWidget(c)

        root.addWidget(cfg_frame)

        # ── Status + action row ───────────────────────────────────────────────
        action_frame, action_body, _ = _card("Connection")
        status_row = QHBoxLayout()
        status_row.setSpacing(10)

        self._status_dot = QLabel("●")
        _s.themed_ss(self._status_dot, "color:{TEXT_MUTED}; font-size:16px; border:none; background:transparent;")
        self._status_lbl = QLabel("Disconnected")
        _s.themed_ss(self._status_lbl, "color:{TEXT_MUTED}; font-size:11px; border:none; background:transparent;")
        status_row.addWidget(self._status_dot)
        status_row.addWidget(self._status_lbl, 1)

        self._btn_connect = QPushButton("Connect")
        self._btn_connect.setFixedHeight(28)
        self._btn_connect.setMinimumWidth(90)
        _s.themed_ss(self._btn_connect, "QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            " border-radius:2px; padding:0 14px; font-size:11px; }}"
            "QPushButton:hover {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
            "QPushButton:disabled {{ background:{TEXT_MUTED}; color:{WHITE}; }}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}")
        self._btn_connect.clicked.connect(self._connect)

        _secondary_btn_ss = (
            "QPushButton {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            " border:1px solid {BORDER}; border-radius:2px; padding:0 12px; font-size:11px; }}"
            "QPushButton:hover {{ background:{RED}; color:{WHITE}; border-color:{RED}; }}"
            "QPushButton:disabled {{ color:{TEXT_MUTED}; }}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )

        self._btn_disconnect = QPushButton("Disconnect")
        self._btn_disconnect.setFixedHeight(28)
        self._btn_disconnect.setEnabled(False)
        _s.themed_ss(self._btn_disconnect, _secondary_btn_ss)
        self._btn_disconnect.clicked.connect(self._disconnect)

        self._btn_test = QPushButton("Test Publish")
        self._btn_test.setFixedHeight(28)
        self._btn_test.setEnabled(False)
        _s.themed_ss(self._btn_test, _secondary_btn_ss)
        self._btn_test.clicked.connect(self._test_publish)

        status_row.addWidget(self._btn_connect)
        status_row.addWidget(self._btn_disconnect)
        status_row.addWidget(self._btn_test)
        action_body.addLayout(status_row)
        root.addWidget(action_frame)

        # ── Event log card ────────────────────────────────────────────────────
        log_frame, log_body, log_hdr_lay = _card("Event Log")
        btn_clear = QPushButton("Clear")
        btn_clear.setFixedHeight(22)
        _s.themed_ss(btn_clear, "QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:1px solid {BORDER};"
            " border-radius:2px; padding:0 8px; font-size:11px; }}"
            "QPushButton:hover {{ background:{BG_CARD}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_MUTED}; }}")
        btn_clear.clicked.connect(self._log.clear if hasattr(self, "_log") else lambda: None)
        log_hdr_lay.addWidget(btn_clear)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        _s.themed_ss(self._log, "QPlainTextEdit {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            " font-size:11px; font-family:Consolas; border:none; padding:4px 8px; }}")
        self._log.setMaximumBlockCount(500)
        # Now wire the clear button properly
        btn_clear.clicked.disconnect()
        btn_clear.clicked.connect(self._log.clear)
        log_body.addWidget(self._log)
        root.addWidget(log_frame, 1)

    # ── Settings persistence ──────────────────────────────────────────────────

    def _settings_path(self):
        from modules.utils import get_app_data_dir
        return get_app_data_dir() / "NetSentinel.ini"

    def _load_settings(self) -> None:
        from PyQt6.QtCore import QSettings
        s = QSettings(str(self._settings_path()), QSettings.Format.IniFormat)
        s.beginGroup("mqtt")
        self._host.setText(s.value("host", "localhost"))
        self._port.setValue(int(s.value("port", 1883)))
        self._username.setText(s.value("username", ""))
        self._base_topic.setText(s.value("base_topic", "netsentinel"))
        self._chk_ha.setChecked(s.value("ha_discovery", "true").lower() == "true")
        self._chk_devices.setChecked(s.value("pub_devices", "true").lower() == "true")
        self._chk_alerts.setChecked(s.value("pub_alerts", "true").lower() == "true")
        self._chk_uptime.setChecked(s.value("pub_uptime", "true").lower() == "true")
        s.endGroup()
        # Password from keychain (don't pre-fill — just leave placeholder)
        pw = _get_secret()
        self._password.setPlaceholderText("●●●●●● (stored)" if pw else "Stored in OS keychain")

    def _save_settings(self) -> None:
        from PyQt6.QtCore import QSettings
        s = QSettings(str(self._settings_path()), QSettings.Format.IniFormat)
        s.beginGroup("mqtt")
        s.setValue("host",         self._host.text().strip())
        s.setValue("port",         self._port.value())
        s.setValue("username",     self._username.text().strip())
        s.setValue("base_topic",   self._base_topic.text().strip() or "netsentinel")
        s.setValue("ha_discovery", str(self._chk_ha.isChecked()).lower())
        s.setValue("pub_devices",  str(self._chk_devices.isChecked()).lower())
        s.setValue("pub_alerts",   str(self._chk_alerts.isChecked()).lower())
        s.setValue("pub_uptime",   str(self._chk_uptime.isChecked()).lower())
        s.endGroup()
        pw = self._password.text()
        if pw:
            _set_secret(pw)

    # ── Connection actions ────────────────────────────────────────────────────

    @pyqtSlot()
    def _connect(self) -> None:
        if not _PAHO_AVAILABLE:
            self._log_line("paho-mqtt not installed — run: pip install paho-mqtt")
            return

        self._save_settings()
        pw = self._password.text() or _get_secret()
        self._publisher.configure(
            host         = self._host.text().strip() or "localhost",
            port         = self._port.value(),
            username     = self._username.text().strip(),
            password     = pw,
            base_topic   = self._base_topic.text().strip() or "netsentinel",
            ha_discovery = self._chk_ha.isChecked(),
            on_status    = self._on_status_changed,
        )
        self._btn_connect.setEnabled(False)
        self._btn_connect.setText("Connecting…")
        self._log_line(f"Connecting to {self._host.text()}:{self._port.value()}…")

        self._worker = _ConnectWorker(self._publisher, parent=self)
        self._worker.start()

    @pyqtSlot()
    def _disconnect(self) -> None:
        self._publisher.disconnect()

    @pyqtSlot()
    def _test_publish(self) -> None:
        dummy = {
            "mac": "AA:BB:CC:00:11:22",
            "ip":  "192.168.1.100",
            "hostname": "test-device",
            "vendor": "NetSentinel",
        }
        self._publisher.publish_device_event("joined", dummy)
        self._log_line("Test publish sent: device joined (AA:BB:CC:00:11:22)")

    # ── Status callback (called from publisher, potentially a bg thread) ──────

    def _on_status_changed(self, connected: bool, msg: str) -> None:
        from PyQt6.QtCore import QMetaObject, Qt
        QMetaObject.invokeMethod(
            self, "_apply_status",
            Qt.ConnectionType.QueuedConnection,
            *[],
        )
        # Store for deferred apply
        self._pending_status = (connected, msg)

    @pyqtSlot()
    def _apply_status(self) -> None:
        connected, msg = getattr(self, "_pending_status", (False, ""))
        if connected:
            _s.themed_ss(self._status_dot, "color:{GREEN}; font-size:16px; border:none; background:transparent;")
            _s.themed_ss(self._status_lbl, "color:{GREEN}; font-size:11px; border:none; background:transparent;")
            self._status_lbl.setText(f"Connected — {msg}")
            self._btn_connect.setEnabled(False)
            self._btn_connect.setText("Connected")
            self._btn_disconnect.setEnabled(True)
            self._btn_test.setEnabled(True)
        else:
            _s.themed_ss(self._status_dot, "color:{RED}; font-size:16px; border:none; background:transparent;")
            _s.themed_ss(self._status_lbl, "color:{RED}; font-size:11px; border:none; background:transparent;")
            self._status_lbl.setText(f"Disconnected — {msg}")
            self._btn_connect.setEnabled(True)
            self._btn_connect.setText("Connect")
            self._btn_disconnect.setEnabled(False)
            self._btn_test.setEnabled(False)
        self._log_line(msg)

    def _log_line(self, text: str) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._log.appendPlainText(f"[{ts}] {text}")

    # ── Public API: called by dashboard to publish events ─────────────────────

    def on_device_event(self, event_type: str, device: dict) -> None:
        """Forward a device join/leave to the publisher if enabled."""
        if self._chk_devices.isChecked() and self._publisher.is_connected():
            self._publisher.publish_device_event(event_type, device)
            self._log_line(
                f"Published device_{event_type}: {device.get('mac', '?')} / {device.get('ip', '?')}"
            )

    def on_alert(self, level: str, message: str, source_ip: str = "") -> None:
        """Forward an alert to the publisher if enabled."""
        if self._chk_alerts.isChecked() and self._publisher.is_connected():
            self._publisher.publish_alert(level, message, source_ip)
            self._log_line(f"Published alert [{level}]: {message[:60]}")

    def on_uptime_state(self, ip: str, state: str, rtt_ms: float = 0.0) -> None:
        """Forward an uptime/RTT update to the publisher if enabled."""
        if self._chk_uptime.isChecked() and self._publisher.is_connected():
            self._publisher.publish_uptime_state(ip, state, rtt_ms)
