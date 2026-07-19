"""Tests for modules/protocol_animator_extra.py — five additional scene builders."""


_NET_INFO = {
    "gateway": "192.168.1.1",
    "local_ips": [{"ip": "192.168.1.100"}],
    "gateway_mac": "aa:bb:cc:dd:ee:ff",
    "dns_servers": ["8.8.8.8"],
}


def test_protocol_animator_extra_import():
    from modules import protocol_animator_extra
    assert protocol_animator_extra is not None


def test_build_ospf_scene_returns_valid_structure():
    from modules.protocol_animator_extra import build_ospf_scene
    from modules.protocol_animator import ProtocolSceneData
    scene = build_ospf_scene(_NET_INFO)
    assert isinstance(scene, ProtocolSceneData)
    assert scene.protocol == "OSPF"
    assert len(scene.nodes) >= 2
    assert len(scene.steps) >= 2


def test_build_ospf_scene_fallback_with_empty_net_info():
    from modules.protocol_animator_extra import build_ospf_scene
    from modules.protocol_animator import ProtocolSceneData
    scene = build_ospf_scene({})
    assert isinstance(scene, ProtocolSceneData)
    assert len(scene.nodes) == 3
    assert len(scene.steps) == 4


def test_build_nat_scene_returns_valid_structure():
    from modules.protocol_animator_extra import build_nat_scene
    from modules.protocol_animator import ProtocolSceneData
    scene = build_nat_scene(_NET_INFO)
    assert isinstance(scene, ProtocolSceneData)
    assert scene.protocol == "NAT"
    assert len(scene.nodes) == 3
    assert len(scene.steps) == 4


def test_build_nat_scene_step_labels():
    from modules.protocol_animator_extra import build_nat_scene
    scene = build_nat_scene(_NET_INFO)
    labels = [s.packet_label for s in scene.steps]
    assert "TCP SYN" in labels[0]
    assert "translated" in labels[1]
    assert "SYN-ACK" in labels[2]


def test_build_scene_for_key_matches_individual_builders_for_all_ten_keys():
    """Shared dispatch must return byte-identical scenes to calling each builder
    directly — this is the regression guard for the ProtocolVizPage._build_scene
    refactor onto the shared helper (Lab Mode Upgrade Phase L1)."""
    from modules.protocol_animator import (
        build_arp_scene, build_dhcp_scene, build_dns_scene, build_stp_scene, build_tcp_scene,
    )
    from modules.protocol_animator_extra import (
        build_icmp_scene, build_nat_scene, build_ospf_scene, build_scene_for_key,
        build_tls_scene, build_vlan_scene,
    )

    net_info = _NET_INFO
    devices = [{"ip": "192.168.1.100", "mac": "11:22:33:44:55:66", "hostname": "test-host"}]
    diag_result = None
    m2_result = None

    expected = {
        "ARP":  build_arp_scene(net_info, devices),
        "DNS":  build_dns_scene(net_info, diag_result),
        "TCP":  build_tcp_scene(net_info, devices),
        "DHCP": build_dhcp_scene(net_info),
        "STP":  build_stp_scene(m2_result),
        "OSPF": build_ospf_scene(net_info),
        "NAT":  build_nat_scene(net_info),
        "VLAN": build_vlan_scene(net_info),
        "TLS":  build_tls_scene(net_info, devices),
        "ICMP": build_icmp_scene(net_info),
    }
    for key, exp_scene in expected.items():
        got = build_scene_for_key(key, net_info, devices, diag_result, m2_result)
        assert got == exp_scene, f"scene mismatch for key={key}"


def test_build_scene_for_key_unknown_key_falls_back_to_arp():
    from modules.protocol_animator import build_arp_scene
    from modules.protocol_animator_extra import build_scene_for_key
    devices = []
    got = build_scene_for_key("NOPE", _NET_INFO, devices)
    assert got == build_arp_scene(_NET_INFO, devices)


def test_build_vlan_scene_returns_valid_structure():
    from modules.protocol_animator_extra import build_vlan_scene
    from modules.protocol_animator import ProtocolSceneData
    scene = build_vlan_scene({})
    assert isinstance(scene, ProtocolSceneData)
    assert scene.protocol == "VLAN"
    assert len(scene.nodes) == 4
    assert len(scene.steps) == 4


def test_build_vlan_scene_has_broadcast_step():
    from modules.protocol_animator_extra import build_vlan_scene
    scene = build_vlan_scene({})
    has_broadcast = any(s.is_broadcast for s in scene.steps)
    assert has_broadcast, "VLAN scene should include a broadcast step for isolation explanation"


def test_build_tls_scene_returns_valid_structure():
    from modules.protocol_animator_extra import build_tls_scene
    from modules.protocol_animator import ProtocolSceneData
    scene = build_tls_scene(_NET_INFO, [])
    assert isinstance(scene, ProtocolSceneData)
    assert scene.protocol == "TLS"
    assert len(scene.nodes) == 2
    assert len(scene.steps) == 4


def test_build_tls_scene_has_reply_steps():
    from modules.protocol_animator_extra import build_tls_scene
    scene = build_tls_scene(_NET_INFO, [])
    reply_count = sum(1 for s in scene.steps if s.is_reply)
    assert reply_count >= 2, "TLS scene should have at least two reply steps"


def test_build_icmp_scene_returns_valid_structure():
    from modules.protocol_animator_extra import build_icmp_scene
    from modules.protocol_animator import ProtocolSceneData
    scene = build_icmp_scene(_NET_INFO)
    assert isinstance(scene, ProtocolSceneData)
    assert scene.protocol == "ICMP"
    assert len(scene.nodes) == 4
    assert len(scene.steps) == 4


def test_build_icmp_scene_includes_gateway_as_hop1():
    from modules.protocol_animator_extra import build_icmp_scene
    scene = build_icmp_scene(_NET_INFO)
    hop1_label = next(n.label for n in scene.nodes if n.id == "hop1")
    assert "192.168.1.1" in hop1_label


def test_all_scenes_have_non_empty_explanations():
    from modules.protocol_animator_extra import (
        build_icmp_scene, build_nat_scene, build_ospf_scene,
        build_tls_scene, build_vlan_scene,
    )
    builders = [
        build_ospf_scene(_NET_INFO),
        build_nat_scene(_NET_INFO),
        build_vlan_scene({}),
        build_tls_scene(_NET_INFO, []),
        build_icmp_scene(_NET_INFO),
    ]
    for scene in builders:
        for step in scene.steps:
            assert step.explanation.strip(), (
                f"{scene.protocol} step '{step.packet_label}' has empty explanation"
            )


def test_all_scenes_have_non_empty_subtitles():
    from modules.protocol_animator_extra import (
        build_icmp_scene, build_nat_scene, build_ospf_scene,
        build_tls_scene, build_vlan_scene,
    )
    for fn in [build_ospf_scene, build_nat_scene, build_icmp_scene]:
        scene = fn(_NET_INFO)
        assert scene.subtitle, f"{scene.protocol} subtitle should not be empty"
    for fn in [build_vlan_scene]:
        scene = fn({})
        assert scene.subtitle, f"{scene.protocol} subtitle should not be empty"
    scene = build_tls_scene(_NET_INFO, [])
    assert scene.subtitle, "TLS subtitle should not be empty"


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


def test_build_ospf_scene_steps_have_frame_layers():
    from modules.protocol_animator_extra import build_ospf_scene
    _assert_scene_steps_have_layers(build_ospf_scene(_NET_INFO))


def test_build_nat_scene_steps_have_frame_layers():
    from modules.protocol_animator_extra import build_nat_scene
    _assert_scene_steps_have_layers(build_nat_scene(_NET_INFO))


def test_build_vlan_scene_steps_have_frame_layers():
    from modules.protocol_animator_extra import build_vlan_scene
    _assert_scene_steps_have_layers(build_vlan_scene({}))


def test_build_tls_scene_steps_have_frame_layers():
    from modules.protocol_animator_extra import build_tls_scene
    _assert_scene_steps_have_layers(build_tls_scene(_NET_INFO, []))


def test_build_icmp_scene_steps_have_frame_layers():
    from modules.protocol_animator_extra import build_icmp_scene
    _assert_scene_steps_have_layers(build_icmp_scene(_NET_INFO))
