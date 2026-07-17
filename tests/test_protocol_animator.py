"""Tests for modules/protocol_animator.py — AnimNode/AnimStep scene builders."""


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
    from modules.protocol_animator import ProtocolSceneData, AnimNode
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


# ── Phase A2: FrameLayer / AnimStep.layers data contract ───────────────────────

def test_frame_layer_dataclass():
    from modules.protocol_animator import FrameLayer
    layer = FrameLayer(name="Ethernet II", fields=[("Src MAC", "AA:BB:CC:DD:EE:FF")])
    assert layer.name == "Ethernet II"
    assert layer.fields == [("Src MAC", "AA:BB:CC:DD:EE:FF")]


def test_anim_step_layers_defaults_to_empty_list():
    from modules.protocol_animator import AnimStep
    step = AnimStep(
        from_node="host", to_node="gw",
        packet_label="ARP Request",
        frame_detail="Who has 192.168.1.1?",
        explanation="ARP resolution step",
    )
    assert step.layers == []


def test_anim_step_layers_independent_across_instances():
    """default_factory=list must not share a mutable default between instances."""
    from modules.protocol_animator import AnimStep, FrameLayer
    a = AnimStep("h", "g", "A", "d", "e")
    b = AnimStep("h", "g", "B", "d", "e")
    a.layers.append(FrameLayer("X", [("f", "v")]))
    assert b.layers == []


# ── Phase A2: every step must carry a real layered frame breakdown ─────────────

def _assert_scene_steps_have_layers(scene) -> None:
    for step in scene.steps:
        assert len(step.layers) >= 2, (
            f"{scene.protocol} step '{step.packet_label}' has only "
            f"{len(step.layers)} layer(s), expected >= 2"
        )
        for layer in step.layers:
            assert layer.fields, (
                f"{scene.protocol} step '{step.packet_label}' layer '{layer.name}' "
                f"has no fields"
            )
            for name, value in layer.fields:
                assert name.strip(), f"{scene.protocol} layer '{layer.name}' has a blank field name"
                assert str(value).strip(), (
                    f"{scene.protocol} layer '{layer.name}' field '{name}' has a blank value"
                )


_ARP_NET_INFO = {
    "gateway": "192.168.1.1",
    "local_ips": [{"ip": "192.168.1.100"}],
    "gateway_mac": "aa:bb:cc:dd:ee:ff",
    "dns_servers": ["8.8.8.8"],
}


def test_build_arp_scene_steps_have_frame_layers():
    from modules.protocol_animator import build_arp_scene
    scene = build_arp_scene(_ARP_NET_INFO, [])
    _assert_scene_steps_have_layers(scene)


def test_build_dns_scene_steps_have_frame_layers():
    from modules.protocol_animator import build_dns_scene
    scene = build_dns_scene(_ARP_NET_INFO, diag_result=None)
    _assert_scene_steps_have_layers(scene)


def test_build_tcp_scene_steps_have_frame_layers():
    from modules.protocol_animator import build_tcp_scene
    scene = build_tcp_scene(_ARP_NET_INFO, devices=[])
    _assert_scene_steps_have_layers(scene)


def test_build_dhcp_scene_steps_have_frame_layers():
    from modules.protocol_animator import build_dhcp_scene
    scene = build_dhcp_scene(_ARP_NET_INFO)
    _assert_scene_steps_have_layers(scene)


def test_build_stp_scene_steps_have_frame_layers():
    from modules.protocol_animator import build_stp_scene
    scene = build_stp_scene(None)
    _assert_scene_steps_have_layers(scene)


def test_build_stp_scene_steps_have_frame_layers_with_real_bpdus():
    from modules.protocol_animator import build_stp_scene
    m2_result = {
        "bpdus": [
            {"root_mac": "00:11:22:33:44:00", "root_priority": 4096, "src_mac": "00:11:22:33:44:01"},
            {"root_mac": "00:11:22:33:44:00", "root_priority": 4096, "src_mac": "00:11:22:33:44:02"},
        ]
    }
    scene = build_stp_scene(m2_result)
    _assert_scene_steps_have_layers(scene)
