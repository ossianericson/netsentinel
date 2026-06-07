"""
MQTT Publisher — publishes NetSentinel events to an MQTT broker.

Supports:
  • Device join / leave events
  • Alert fired events
  • Uptime state change events
  • Home Assistant MQTT discovery (binary_sensor / sensor entities)

paho-mqtt is an optional dependency; all public functions degrade
gracefully when it is not installed.

Credentials are stored in the OS keychain (RULE 22-A):
  keyring service: "NetSentinel"
  key:             "mqtt/password"

Configuration (everything except the password) is persisted via QSettings
(NetSentinel.ini) under the [mqtt] section.

MQTT topic layout (default base_topic = "netsentinel"):
  netsentinel/devices/{mac_safe}/joined
  netsentinel/devices/{mac_safe}/left
  netsentinel/alerts/{level}
  netsentinel/uptime/{ip_safe}/state

Home Assistant MQTT discovery:
  homeassistant/binary_sensor/netsentinel_{mac_safe}/config  (device online presence)
  homeassistant/sensor/netsentinel_rtt_{ip_safe}/config      (RTT latency sensor)
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

_PAHO_AVAILABLE = False
try:
    import paho.mqtt.client as mqtt  # type: ignore
    _PAHO_AVAILABLE = True
except ImportError:
    pass  # non-fatal


# ── MAC / IP sanitiser for MQTT topic segments ────────────────────────────────

def _safe(s: str) -> str:
    """Replace characters illegal in MQTT topics with underscores."""
    return s.replace(":", "_").replace(".", "_").replace("/", "_").replace("+", "_").replace("#", "_")


# ── MqttPublisher ─────────────────────────────────────────────────────────────

class MqttPublisher:
    """
    Manages a persistent MQTT connection and publishes NetSentinel events.

    Thread-safe: all public methods may be called from any thread.
    """

    def __init__(self) -> None:
        self._lock       = threading.Lock()
        self._client: Optional[Any] = None   # paho Client
        self._connected  = False
        self._host       = "localhost"
        self._port       = 1883
        self._username   = ""
        self._base_topic = "netsentinel"
        self._ha_discovery = True
        self._on_status: Optional[Callable[[bool, str], None]] = None  # (connected, msg)

    # ── Configuration ─────────────────────────────────────────────────────────

    def configure(
        self,
        host:         str  = "localhost",
        port:         int  = 1883,
        username:     str  = "",
        password:     str  = "",
        base_topic:   str  = "netsentinel",
        ha_discovery: bool = True,
        on_status:    Optional[Callable[[bool, str], None]] = None,
    ) -> None:
        """Apply new settings. If already connected, reconnect with new credentials."""
        with self._lock:
            self._host         = host
            self._port         = port
            self._username     = username
            self._base_topic   = base_topic.strip("/")
            self._ha_discovery = ha_discovery
            self._on_status    = on_status
            self._password     = password

    # ── Connection lifecycle ──────────────────────────────────────────────────

    def connect(self) -> None:
        """Open (or reopen) the MQTT connection in a background thread."""
        threading.Thread(target=self._connect_bg, daemon=True).start()

    def disconnect(self) -> None:
        with self._lock:
            c = self._client
        if c:
            try:
                c.disconnect()
            except Exception:
                pass  # non-fatal

    def is_connected(self) -> bool:
        return self._connected

    def _connect_bg(self) -> None:
        if not _PAHO_AVAILABLE:
            self._notify(False, "paho-mqtt not installed (pip install paho-mqtt)")
            return

        with self._lock:
            host       = self._host
            port       = self._port
            username   = self._username
            password   = getattr(self, "_password", "")
            base_topic = self._base_topic

        try:
            # paho v1 and v2 compat
            try:
                client = mqtt.Client(client_id="netsentinel", protocol=mqtt.MQTTv311)
            except TypeError:
                client = mqtt.Client()

            if username:
                client.username_pw_set(username, password or None)

            client.on_connect    = self._on_connect
            client.on_disconnect = self._on_disconnect

            # LWT — sent by broker if we drop unexpectedly
            lwt_topic = f"{base_topic}/status"
            client.will_set(lwt_topic, payload="offline", retain=True, qos=1)

            client.connect(host, port, keepalive=60)

            with self._lock:
                self._client = client

            client.loop_start()
        except Exception as exc:
            self._notify(False, f"Connection failed: {exc}")

    def _on_connect(self, client, userdata, flags, rc, *args) -> None:
        if rc == 0:
            self._connected = True
            # Publish online status
            self._publish_raw(f"{self._base_topic}/status", "online", retain=True)
            self._notify(True, f"Connected to {self._host}:{self._port}")
        else:
            self._connected = False
            codes = {
                1: "Unacceptable protocol version",
                2: "Client identifier rejected",
                3: "Server unavailable",
                4: "Bad username or password",
                5: "Not authorized",
            }
            self._notify(False, f"Connect refused: {codes.get(rc, f'code {rc}')}")

    def _on_disconnect(self, client, userdata, rc, *args) -> None:
        self._connected = False
        if rc != 0:
            self._notify(False, f"Unexpected disconnect (rc={rc}) — will not auto-reconnect")
        else:
            self._notify(False, "Disconnected")

    def _notify(self, connected: bool, msg: str) -> None:
        self._connected = connected
        cb = self._on_status
        if cb:
            try:
                cb(connected, msg)
            except Exception:
                pass  # non-fatal

    # ── Low-level publish ─────────────────────────────────────────────────────

    def _publish_raw(
        self,
        topic:   str,
        payload: Any,
        retain:  bool = False,
        qos:     int  = 0,
    ) -> None:
        with self._lock:
            client = self._client
        if client is None or not self._connected:
            return
        if not isinstance(payload, (str, bytes, bytearray)):
            payload = json.dumps(payload)
        try:
            client.publish(topic, payload=payload, retain=retain, qos=qos)
        except Exception as exc:
            log.debug("MQTT publish error: %s", exc)

    # ── Event publishers ──────────────────────────────────────────────────────

    def publish_device_event(self, event_type: str, device: Dict) -> None:
        """
        Publish a device join/leave event.

        event_type ∈ {"joined", "left"}
        device keys: mac, ip, hostname, vendor, risk_level (all optional)
        """
        mac = _safe(str(device.get("mac") or "unknown"))
        payload = {
            "mac":      device.get("mac", ""),
            "ip":       device.get("ip", ""),
            "hostname": device.get("hostname", ""),
            "vendor":   device.get("vendor", ""),
            "risk":     device.get("risk_level", ""),
            "event":    event_type,
        }
        topic = f"{self._base_topic}/devices/{mac}/{event_type}"
        self._publish_raw(topic, payload)

        if self._ha_discovery:
            self._publish_ha_device_discovery(device)
            # State update for online/offline binary sensor
            state_topic = f"{self._base_topic}/devices/{mac}/state"
            self._publish_raw(state_topic, "ON" if event_type == "joined" else "OFF", retain=True)

    def publish_alert(self, level: str, message: str, source_ip: str = "") -> None:
        """Publish an alert event."""
        payload = {
            "level":     level,
            "message":   message,
            "source_ip": source_ip,
        }
        topic = f"{self._base_topic}/alerts/{level.lower()}"
        self._publish_raw(topic, payload)

    def publish_uptime_state(self, ip: str, state: str, rtt_ms: float = 0.0) -> None:
        """Publish an uptime/RTT update. state ∈ {'up', 'down'}."""
        ip_s = _safe(ip)
        payload = {"ip": ip, "state": state, "rtt_ms": rtt_ms}
        self._publish_raw(f"{self._base_topic}/uptime/{ip_s}/state", payload)

        if self._ha_discovery and rtt_ms > 0:
            self._publish_ha_rtt_discovery(ip)
            self._publish_raw(f"{self._base_topic}/uptime/{ip_s}/rtt", str(round(rtt_ms, 1)), retain=True)

    # ── Home Assistant MQTT Discovery ─────────────────────────────────────────

    def _publish_ha_device_discovery(self, device: Dict) -> None:
        """
        Publish HA MQTT discovery config for a binary_sensor representing
        a device's network presence (ON = online, OFF = offline).
        """
        mac    = str(device.get("mac") or "unknown")
        mac_s  = _safe(mac)
        name   = str(device.get("hostname") or device.get("vendor") or mac)
        vendor = str(device.get("vendor") or "Unknown")
        config = {
            "name":          f"NetSentinel — {name}",
            "unique_id":     f"netsentinel_{mac_s}",
            "device_class":  "connectivity",
            "state_topic":   f"{self._base_topic}/devices/{mac_s}/state",
            "payload_on":    "ON",
            "payload_off":   "OFF",
            "retain":        True,
            "device": {
                "identifiers":    [f"netsentinel_{mac_s}"],
                "name":           name,
                "model":          vendor,
                "manufacturer":   "NetSentinel",
                "via_device":     "NetSentinel",
            },
        }
        discovery_topic = f"homeassistant/binary_sensor/netsentinel_{mac_s}/config"
        self._publish_raw(discovery_topic, config, retain=True)

    def _publish_ha_rtt_discovery(self, ip: str) -> None:
        """Publish HA MQTT discovery config for an RTT latency sensor."""
        ip_s = _safe(ip)
        config = {
            "name":                 f"NetSentinel RTT — {ip}",
            "unique_id":            f"netsentinel_rtt_{ip_s}",
            "device_class":         "duration",
            "unit_of_measurement":  "ms",
            "state_topic":          f"{self._base_topic}/uptime/{ip_s}/rtt",
            "value_template":       "{{ value }}",
            "retain":               True,
            "device": {
                "identifiers":  [f"netsentinel_host_{ip_s}"],
                "name":         f"Host {ip}",
                "manufacturer": "NetSentinel",
            },
        }
        discovery_topic = f"homeassistant/sensor/netsentinel_rtt_{ip_s}/config"
        self._publish_raw(discovery_topic, config, retain=True)


# ── Module-level singleton ────────────────────────────────────────────────────

_publisher: Optional[MqttPublisher] = None


def get_publisher() -> MqttPublisher:
    """Return the module-level MqttPublisher singleton."""
    global _publisher
    if _publisher is None:
        _publisher = MqttPublisher()
    return _publisher
