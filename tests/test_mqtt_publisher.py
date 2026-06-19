"""
Tests for modules/mqtt_publisher.py
"""
from unittest.mock import MagicMock, patch

from modules.mqtt_publisher import (
    MqttPublisher, get_publisher, _safe,
)


# ── _safe helper ──────────────────────────────────────────────────────────────

def test_safe_colons():
    assert _safe("AA:BB:CC:DD:EE:FF") == "AA_BB_CC_DD_EE_FF"


def test_safe_dots():
    assert _safe("192.168.1.1") == "192_168_1_1"


def test_safe_slashes():
    assert _safe("topic/sub") == "topic_sub"


def test_safe_mqtt_wildcards():
    result = _safe("a+b#c")
    assert "+" not in result
    assert "#" not in result


def test_safe_clean_string():
    assert _safe("netsentinel") == "netsentinel"


# ── MqttPublisher: configure ──────────────────────────────────────────────────

def test_configure_stores_values():
    pub = MqttPublisher()
    pub.configure(host="10.0.0.1", port=1884, username="user",
                  password="pass", base_topic="ns", ha_discovery=False)
    assert pub._host == "10.0.0.1"
    assert pub._port == 1884
    assert pub._username == "user"
    assert pub._base_topic == "ns"
    assert pub._ha_discovery is False


def test_configure_strips_trailing_slash():
    pub = MqttPublisher()
    pub.configure(base_topic="netsentinel/")
    assert pub._base_topic == "netsentinel"


# ── MqttPublisher: is_connected ───────────────────────────────────────────────

def test_not_connected_by_default():
    pub = MqttPublisher()
    assert pub.is_connected() is False


# ── MqttPublisher: publish methods when disconnected ─────────────────────────

def test_publish_device_event_when_disconnected():
    """Should not raise even when disconnected (no client)."""
    pub = MqttPublisher()
    pub.publish_device_event("joined", {"mac": "AA:BB", "ip": "10.0.0.1"})  # no exception


def test_publish_alert_when_disconnected():
    pub = MqttPublisher()
    pub.publish_alert("HIGH", "Test alert")


def test_publish_uptime_state_when_disconnected():
    pub = MqttPublisher()
    pub.publish_uptime_state("10.0.0.1", "up", 5.0)


# ── MqttPublisher: _publish_raw routing ──────────────────────────────────────

def test_publish_raw_when_connected():
    pub = MqttPublisher()
    pub._connected = True
    mock_client = MagicMock()
    pub._client = mock_client

    pub._publish_raw("netsentinel/test", {"k": "v"})
    mock_client.publish.assert_called_once()
    topic_arg = mock_client.publish.call_args[0][0]
    assert topic_arg == "netsentinel/test"


def test_publish_raw_json_serialises_dict():
    pub = MqttPublisher()
    pub._connected = True
    mock_client = MagicMock()
    pub._client = mock_client
    pub._publish_raw("t", {"mac": "AA"})
    payload = mock_client.publish.call_args[1]["payload"]
    import json
    obj = json.loads(payload)
    assert obj["mac"] == "AA"


def test_publish_raw_string_payload():
    pub = MqttPublisher()
    pub._connected = True
    mock_client = MagicMock()
    pub._client = mock_client
    pub._publish_raw("t", "online", retain=True)
    payload = mock_client.publish.call_args[1]["payload"]
    assert payload == "online"


# ── Device event topic structure ──────────────────────────────────────────────

def test_device_joined_topic():
    pub = MqttPublisher()
    pub._connected = True
    pub._base_topic = "netsentinel"
    pub._ha_discovery = False
    mock_client = MagicMock()
    pub._client = mock_client

    pub.publish_device_event("joined", {"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.0.0.1"})
    topic = mock_client.publish.call_args[0][0]
    assert topic == "netsentinel/devices/AA_BB_CC_DD_EE_FF/joined"


def test_device_left_topic():
    pub = MqttPublisher()
    pub._connected = True
    pub._base_topic = "ns"
    pub._ha_discovery = False
    mock_client = MagicMock()
    pub._client = mock_client

    pub.publish_device_event("left", {"mac": "11:22:33:44:55:66"})
    topic = mock_client.publish.call_args[0][0]
    assert topic == "ns/devices/11_22_33_44_55_66/left"


# ── Alert topic structure ─────────────────────────────────────────────────────

def test_alert_topic():
    pub = MqttPublisher()
    pub._connected = True
    pub._base_topic = "netsentinel"
    mock_client = MagicMock()
    pub._client = mock_client

    pub.publish_alert("HIGH", "Rogue device detected", "192.168.1.5")
    topic = mock_client.publish.call_args[0][0]
    assert topic == "netsentinel/alerts/high"


# ── HA discovery payloads ─────────────────────────────────────────────────────

def test_ha_device_discovery_topic():
    pub = MqttPublisher()
    pub._connected = True
    pub._base_topic = "netsentinel"
    pub._ha_discovery = True
    mock_client = MagicMock()
    pub._client = mock_client

    device = {"mac": "AA:BB:CC:DD:EE:FF", "hostname": "router", "vendor": "Cisco"}
    pub._publish_ha_device_discovery(device)
    topics = [c[0][0] for c in mock_client.publish.call_args_list]
    assert any("homeassistant/binary_sensor/netsentinel_AA_BB_CC_DD_EE_FF/config" in t for t in topics)


def test_ha_device_discovery_payload():
    import json
    pub = MqttPublisher()
    pub._connected = True
    pub._base_topic = "netsentinel"
    pub._ha_discovery = True
    mock_client = MagicMock()
    pub._client = mock_client

    device = {"mac": "AA:BB:CC:DD:EE:FF", "hostname": "router"}
    pub._publish_ha_device_discovery(device)
    payload_str = mock_client.publish.call_args[1]["payload"]
    payload = json.loads(payload_str)
    assert payload["device_class"] == "connectivity"
    assert "unique_id" in payload
    assert payload["payload_on"] == "ON"


def test_ha_rtt_discovery_topic():
    pub = MqttPublisher()
    pub._connected = True
    pub._base_topic = "netsentinel"
    mock_client = MagicMock()
    pub._client = mock_client

    pub._publish_ha_rtt_discovery("192.168.1.1")
    topic = mock_client.publish.call_args[0][0]
    assert "homeassistant/sensor/netsentinel_rtt_192_168_1_1/config" in topic


# ── notify callback ───────────────────────────────────────────────────────────

def test_notify_callback_connected():
    pub = MqttPublisher()
    received = []
    pub._on_status = lambda ok, msg: received.append((ok, msg))
    pub._notify(True, "Connected!")
    assert received == [(True, "Connected!")]


def test_notify_callback_disconnected():
    pub = MqttPublisher()
    received = []
    pub._on_status = lambda ok, msg: received.append((ok, msg))
    pub._notify(False, "Lost connection")
    assert received == [(False, "Lost connection")]


def test_notify_no_callback_does_not_raise():
    pub = MqttPublisher()
    pub._on_status = None
    pub._notify(False, "No one listening")  # should not raise


# ── Singleton ─────────────────────────────────────────────────────────────────

def test_get_publisher_returns_same_instance():
    p1 = get_publisher()
    p2 = get_publisher()
    assert p1 is p2


# ── paho unavailable path ─────────────────────────────────────────────────────

def test_connect_without_paho():
    pub = MqttPublisher()
    messages = []
    pub._on_status = lambda ok, msg: messages.append((ok, msg))
    with patch("modules.mqtt_publisher._PAHO_AVAILABLE", False):
        pub._connect_bg()
    assert any("paho-mqtt" in m[1].lower() for m in messages)
