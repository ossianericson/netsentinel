"""Tests for modules/protocol_animator.py — AnimNode/AnimStep scene builders."""
import pytest


def test_protocol_animator_import():
    from modules import protocol_animator
    assert protocol_animator is not None


def test_anim_node_dataclass():
    from modules.protocol_animator import AnimNode
    node = AnimNode(id="gw", label="Gateway", role="gateway", x=0.5, y=0.5)
    assert node.id == "gw"
    assert node.label == "Gateway"
    assert node.role == "gateway"


def test_anim_step_dataclass():
    from modules.protocol_animator import AnimStep
    step = AnimStep(
        from_node="host", to_node="gw",
        packet_label="ARP Request",
        frame_detail="Who has 192.168.1.1?",
        explanation="ARP resolution step",
    )
    assert step.from_node == "host"
    assert step.to_node == "gw"
    assert step.packet_label == "ARP Request"


def test_protocol_scene_data_dataclass():
    from modules.protocol_animator import ProtocolSceneData, AnimNode, AnimStep
    scene = ProtocolSceneData(
        protocol="ARP",
        title="ARP Resolution",
        subtitle="",
        nodes=[AnimNode(id="a", label="A", role="client", x=0, y=0)],
        steps=[],
    )
    assert scene.title == "ARP Resolution"
    assert len(scene.nodes) == 1


def test_build_arp_scene_no_data_returns_empty():
    """Without scan data build_arp_scene returns empty nodes."""
    from modules.protocol_animator import build_arp_scene, ProtocolSceneData
    scene = build_arp_scene({}, [])
    assert isinstance(scene, ProtocolSceneData)
    assert scene.missing_data_msg != ""


def test_build_arp_scene_with_data():
    from modules.protocol_animator import build_arp_scene, ProtocolSceneData
    net_info = {
        "gateway": "192.168.1.1",
        "local_ips": [{"ip": "192.168.1.100"}],
        "gateway_mac": "aa:bb:cc:dd:ee:ff",
    }
    scene = build_arp_scene(net_info, [])
    assert isinstance(scene, ProtocolSceneData)
    assert len(scene.nodes) >= 2
    assert len(scene.steps) >= 1


def test_build_dns_scene_returns_valid_structure():
    from modules.protocol_animator import build_dns_scene, ProtocolSceneData
    net_info = {"local_ips": [{"ip": "192.168.1.100"}], "dns_servers": ["8.8.8.8"]}
    scene = build_dns_scene(net_info, diag_result=None)
    assert isinstance(scene, ProtocolSceneData)


def test_build_dhcp_scene_returns_valid_structure():
    from modules.protocol_animator import build_dhcp_scene, ProtocolSceneData
    scene = build_dhcp_scene({})
    assert isinstance(scene, ProtocolSceneData)


def test_build_stp_scene_with_no_result():
    from modules.protocol_animator import build_stp_scene, ProtocolSceneData
    scene = build_stp_scene(None)
    assert isinstance(scene, ProtocolSceneData)


def test_build_tcp_scene_returns_valid_structure():
    from modules.protocol_animator import build_tcp_scene, ProtocolSceneData
    scene = build_tcp_scene({}, devices=[])
    assert isinstance(scene, ProtocolSceneData)
