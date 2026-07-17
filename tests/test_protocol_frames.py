"""Tests for modules/protocol_frames.py — shared FrameLayer constructor helpers (Phase A2)."""


def test_protocol_frames_import():
    from modules import protocol_frames
    assert protocol_frames is not None


def test_ethernet_layer_basic_fields():
    from modules.protocol_frames import ethernet_layer
    layer = ethernet_layer("aa:bb:cc:dd:ee:ff", "11:22:33:44:55:66", "0x0800", "IPv4")
    assert layer.name == "Ethernet II"
    field_names = [f[0] for f in layer.fields]
    assert "Src MAC" in field_names
    assert "Dst MAC" in field_names
    assert "EtherType" in field_names
    values = dict(layer.fields)
    assert values["Src MAC"] == "AA:BB:CC:DD:EE:FF"
    assert "0x0800" in values["EtherType"]
    assert "IPv4" in values["EtherType"]


def test_ethernet_layer_handles_missing_mac():
    from modules.protocol_frames import ethernet_layer
    layer = ethernet_layer("", "", "0x0806")
    values = dict(layer.fields)
    assert values["Src MAC"] != ""
    assert values["Dst MAC"] != ""


def test_ipv4_layer_basic_fields():
    from modules.protocol_frames import ipv4_layer
    layer = ipv4_layer("192.168.1.100", "192.168.1.1", ttl=64, proto="17 (UDP)")
    assert layer.name == "IPv4"
    values = dict(layer.fields)
    assert values["Src IP"] == "192.168.1.100"
    assert values["Dst IP"] == "192.168.1.1"
    assert values["TTL"] == "64"
    assert values["Protocol"] == "17 (UDP)"


def test_ipv4_layer_omits_optional_fields_when_not_given():
    from modules.protocol_frames import ipv4_layer
    layer = ipv4_layer("10.0.0.1", "10.0.0.2")
    field_names = [f[0] for f in layer.fields]
    assert "Protocol" not in field_names
    assert "Flags" not in field_names


def test_udp_layer_basic_fields():
    from modules.protocol_frames import udp_layer
    layer = udp_layer(68, 67, length=300)
    assert layer.name == "UDP"
    values = dict(layer.fields)
    assert values["Src Port"] == "68"
    assert values["Dst Port"] == "67"
    assert values["Length"] == "300"


def test_udp_layer_omits_length_when_not_given():
    from modules.protocol_frames import udp_layer
    layer = udp_layer(53, 51820)
    field_names = [f[0] for f in layer.fields]
    assert "Length" not in field_names


def test_tcp_layer_basic_fields():
    from modules.protocol_frames import tcp_layer
    layer = tcp_layer(49152, 443, "SYN", seq=0)
    assert layer.name == "TCP"
    values = dict(layer.fields)
    assert values["Flags"] == "SYN"
    assert values["Seq"] == "0"
    assert "Ack" not in values


def test_tcp_layer_includes_ack_when_given():
    from modules.protocol_frames import tcp_layer
    layer = tcp_layer(443, 49152, "SYN,ACK", seq=0, ack=1)
    values = dict(layer.fields)
    assert values["Ack"] == "1"


def test_find_mac_for_ip_matches_dict_device():
    from modules.protocol_frames import find_mac_for_ip
    devices = [{"ip": "192.168.1.50", "mac": "aa:bb:cc:dd:ee:ff"}]
    assert find_mac_for_ip(devices, "192.168.1.50") == "aa:bb:cc:dd:ee:ff"


def test_find_mac_for_ip_matches_attr_device():
    from modules.protocol_frames import find_mac_for_ip
    from modules.rogue_device import DeviceInfo
    devices = [DeviceInfo(ip="192.168.1.51", mac="11:22:33:44:55:66")]
    assert find_mac_for_ip(devices, "192.168.1.51") == "11:22:33:44:55:66"


def test_find_mac_for_ip_no_match_returns_empty():
    from modules.protocol_frames import find_mac_for_ip
    devices = [{"ip": "192.168.1.50", "mac": "aa:bb:cc:dd:ee:ff"}]
    assert find_mac_for_ip(devices, "10.0.0.9") == ""
    assert find_mac_for_ip([], "10.0.0.9") == ""
    assert find_mac_for_ip(devices, "") == ""
