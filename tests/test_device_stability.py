"""
Tests for modules/device_stability.py — stability scoring and role inference.
"""
from unittest.mock import MagicMock

from modules.device_stability import (
    RoleEvidence,
    compute_ip_stability,
    infer_role,
    is_static_candidate,
    purge_non_devices,
    recompute_roles,
    update_stability_for_device,
)

# An OUI-backed (globally administered) MAC. Test fixtures must not use the
# habitual "aa:bb:cc:..." here — 0xaa has the U/L bit set, so device_identity
# reads it as a privacy MAC and, with no hostname or vendor to go on, correctly
# refuses to promote it (see test_anonymous_mac_is_never_promoted below).
_OUI_MAC = "3c:64:cf:e0:27:02"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_store(ip_history_rows):
    """Return a minimal mock MetricStore with a given device_ip_history dataset."""
    store = MagicMock()
    store.get_ip_history_stats.return_value = ip_history_rows
    store.get_total_seen_count.return_value = sum(int(r[1] or 0) for r in ip_history_rows)
    store.update_device_stability.return_value = None
    store.get_known_devices.return_value = {}
    return store


# ── compute_ip_stability ──────────────────────────────────────────────────────

def test_stability_unknown_mac_returns_zero():
    store = _make_store([])
    assert compute_ip_stability("aa:bb:cc:dd:ee:ff", store) == 0.0


def test_stability_single_ip_returns_one():
    store = _make_store([("192.168.1.1", 10)])
    assert compute_ip_stability("aa:bb:cc:dd:ee:ff", store) == 1.0


def test_stability_two_ips_dominant():
    # 8 at .1, 2 at .50 → stability = 8/10 = 0.8
    store = _make_store([("192.168.1.1", 8), ("192.168.1.50", 2)])
    result = compute_ip_stability("aa:bb:cc:dd:ee:ff", store)
    assert abs(result - 0.8) < 1e-9


def test_stability_equal_ips():
    store = _make_store([("10.0.0.1", 5), ("10.0.0.2", 5)])
    result = compute_ip_stability("aa:bb:cc:dd:ee:ff", store)
    assert abs(result - 0.5) < 1e-9


def test_stability_zero_seen_count():
    store = _make_store([("192.168.1.1", 0)])
    assert compute_ip_stability("aa:bb:cc:dd:ee:ff", store) == 0.0


# ── infer_role ────────────────────────────────────────────────────────────────

def test_role_gateway_last_octet_1():
    assert infer_role("192.168.1.1", "Unknown", None, 1, 0.5) == "gateway"


def test_role_gateway_last_octet_254():
    assert infer_role("10.0.0.254", "router", None, 1, 0.5) == "gateway"


def test_device_type_alone_no_longer_promotes_to_infrastructure():
    """REGRESSION (Signal Quality Phase 2). device_type is a heuristic guess —
    it called an iPad a "Domain Controller" and a Google Nest Wifi router a
    "Video Doorbell" on the reference network. Promotion to infrastructure is
    the alert-eligibility gate, so a guess alone must not open it."""
    assert infer_role("192.168.1.5", "router", None, 1, 0.3) is None
    assert infer_role("192.168.1.6", "Access Point", None, 1, 0.3) is None
    assert infer_role("192.168.1.7", "switch", None, 1, 0.3) is None


def test_device_type_plus_vendor_evidence_promotes_to_infrastructure():
    """An OUI-registered networking vendor is the corroboration device_type
    could not supply on its own."""
    assert infer_role(
        "192.168.1.5", "Access Point", None, 1, 0.3,
        mac=_OUI_MAC, vendor="Ubiquiti Networks",
    ) == "infrastructure"


def test_role_server_requires_threshold():
    # Below threshold — should not infer server
    assert infer_role("192.168.1.10", "server", None, 3, 0.8) != "server"
    # At threshold
    assert infer_role("192.168.1.10", "server", None, 5, 0.9) == "server"


def test_always_on_unknown_device_is_no_longer_infrastructure():
    """REGRESSION (Signal Quality Phase 2). This catch-all — "10+ scans and a
    stable IP" — was the single biggest defect in the alert gate: it promoted
    a PS4, a Chromecast, a Lexmark printer, an Xbox, three unidentifiable
    privacy MACs and the SSDP multicast group to infrastructure, which opted
    all of them in to every device-scoped alert rule. "Always on" describes
    every appliance on a home network; it is a statement about uptime, not
    about function."""
    assert infer_role("192.168.1.20", "Unknown Device", None, 10, 0.92) is None
    assert infer_role("192.168.1.20", "Unknown Device", None, 900, 1.0) is None


def test_role_workstation():
    assert infer_role("192.168.1.50", "laptop", None, 2, 0.5) == "workstation"
    assert infer_role("192.168.1.51", "Phone", None, 2, 0.5) == "workstation"


def test_role_iot():
    assert infer_role("192.168.1.100", "IoT", None, 2, 0.5) == "iot"
    assert infer_role("192.168.1.101", "IP Camera", None, 2, 0.5) == "iot"


def test_role_custom_name_suppresses_inference():
    # Even .1 IP should not get gateway role when user has set a custom name
    assert infer_role("192.168.1.1", "router", "My Router", 20, 1.0) is None


def test_role_none_for_unknown():
    assert infer_role("192.168.1.200", "Unknown Device", None, 1, 0.5) is None


# ── RoleEvidence.from_network ────────────────────────────────────────────────

class _Unit:
    def __init__(self, mac=None, ip=None):
        self.mac = mac
        self.ip = ip


def test_from_network_reads_the_gateway_and_dhcp_server():
    ev = RoleEvidence.from_network(
        {"gateway": " 192.168.68.1 ", "dhcp_server": "192.168.68.1"}
    )
    assert ev.gateway_ip == "192.168.68.1"
    assert ev.dhcp_server_ip == "192.168.68.1"


def test_from_network_reads_the_dhcp_server_from_the_real_worker_shape():
    """The live producer nests it. NetworkInfoWorker builds the dict as
    `info = get_network_info(); info["dhcp"] = get_dhcp_info()`
    ([scan_worker.py:510](workers/scan_worker.py#L510)), and that exact dict
    becomes `self._net_info` and is what `ui/scan_wiring.py` hands to this
    method — so reading only the top level found the key nowhere and
    `dhcp_server_ip` was never fed despite being accepted and used by
    `_has_infrastructure_evidence()`.
    """
    ev = RoleEvidence.from_network(
        {"gateway": "192.168.68.1", "dhcp": {"dhcp_enabled": True,
                                             "dhcp_server": "192.168.68.1"}}
    )
    assert ev.dhcp_server_ip == "192.168.68.1"


def test_from_network_prefers_a_top_level_dhcp_server_over_the_nested_one():
    ev = RoleEvidence.from_network(
        {"dhcp_server": "10.0.0.1", "dhcp": {"dhcp_server": "192.168.68.1"}}
    )
    assert ev.dhcp_server_ip == "10.0.0.1"


def test_from_network_tolerates_a_non_dict_dhcp_value():
    """Defensive for the same reason RULE-NET1 exists — the sub-dict is absent
    entirely until NetworkInfoWorker has run at least once."""
    for bad in (None, "", "192.168.68.1", []):
        assert RoleEvidence.from_network({"dhcp": bad}).dhcp_server_ip is None


def test_from_network_tolerates_an_unresolved_gateway():
    """RULE-NET1: get_network_info() initialises both keys to None and only
    overwrites them on a successful resolution — a normal runtime state on VPN
    or a just-flushed ARP cache, not corruption."""
    ev = RoleEvidence.from_network({"gateway": None, "gateway_mac": None})
    assert ev.gateway_ip is None
    assert ev.dhcp_server_ip is None


def test_from_network_accepts_no_arguments_at_all():
    assert RoleEvidence.from_network() == RoleEvidence()
    assert RoleEvidence.from_network(None, None) == RoleEvidence()


def test_from_network_collects_mesh_node_identifiers():
    ev = RoleEvidence.from_network(
        {"gateway": "192.168.68.1"},
        [_Unit(mac="F4:F5:D8:AA:BB:CC", ip="192.168.68.2"), _Unit(mac=None, ip=None)],
    )
    assert ev.mesh_node_macs == frozenset({"f4:f5:d8:aa:bb:cc"})
    assert ev.mesh_node_ips == frozenset({"192.168.68.2"})


def test_from_network_accepts_mesh_units_as_dicts():
    ev = RoleEvidence.from_network(None, [{"mac": "aa:bb:cc:00:11:22"}])
    assert ev.mesh_node_macs == frozenset({"aa:bb:cc:00:11:22"})


def test_from_network_never_raises_on_a_malformed_unit():
    ev = RoleEvidence.from_network({"gateway": "10.0.0.1"}, [object(), None, 42])
    assert ev.gateway_ip == "10.0.0.1"
    assert ev.mesh_node_macs == frozenset()


# ── infer_role: corroborating evidence (Signal Quality Phase 2) ──────────────

def test_gateway_evidence_beats_the_last_octet_heuristic():
    """A real gateway address supersedes the .1/.254 guess in both directions."""
    ev = RoleEvidence(gateway_ip="10.0.5.9")
    assert infer_role("10.0.5.9", None, None, 1, 0.5, mac=_OUI_MAC, evidence=ev) == "gateway"
    # .1 is NOT the gateway on this network, and we know that for a fact.
    assert infer_role("10.0.5.1", None, None, 1, 0.5, mac=_OUI_MAC, evidence=ev) != "gateway"


def test_last_octet_heuristic_still_applies_when_no_gateway_is_known():
    assert infer_role("192.168.1.1", None, None, 1, 0.5, mac=_OUI_MAC) == "gateway"


def test_dhcp_server_identity_promotes_to_infrastructure():
    """A host that hands out leases is infrastructure by definition."""
    ev = RoleEvidence(dhcp_server_ip="192.168.1.5")
    assert infer_role(
        "192.168.1.5", "Unknown Device", None, 1, 0.1, mac=_OUI_MAC, evidence=ev
    ) == "infrastructure"


def test_mesh_node_membership_promotes_to_infrastructure():
    """The mesh plugin's own reported node list — the AP saying so itself."""
    ev = RoleEvidence(mesh_node_macs=frozenset({_OUI_MAC}))
    assert infer_role(
        "192.168.1.30", "Video Doorbell", None, 1, 0.1, mac=_OUI_MAC, evidence=ev
    ) == "infrastructure"


def test_mesh_node_membership_matches_on_ip_too():
    ev = RoleEvidence(mesh_node_ips=frozenset({"192.168.1.31"}))
    assert infer_role(
        "192.168.1.31", None, None, 1, 0.1, mac=_OUI_MAC, evidence=ev
    ) == "infrastructure"


def test_open_dns_or_dhcp_ports_promote_to_infrastructure():
    assert infer_role(
        "192.168.1.40", "Unknown Device", None, 1, 0.1, [53, 80], mac=_OUI_MAC
    ) == "infrastructure"
    assert infer_role(
        "192.168.1.41", "Unknown Device", None, 1, 0.1, [67], mac=_OUI_MAC
    ) == "infrastructure"


def test_google_nest_wifi_router_is_promoted_from_its_vendor():
    """The real mesh AP on the reference network. device_type said "Video
    Doorbell" and it therefore carried no role at all, while a PS4 and a
    printer held infrastructure."""
    assert infer_role(
        "192.168.68.64", "Video Doorbell", None, 6, 0.67,
        mac="f0:72:ea:51:d3:b8",
        vendor="Google Nest / Nest Wifi / Google Wifi Router",
    ) == "infrastructure"


# ── infer_role: the identity gate (acceptance criterion 1) ───────────────────

def test_anonymous_mac_is_never_promoted_to_infrastructure():
    """A randomised MAC with no hostname and no vendor is unidentifiable.
    Three such devices held infrastructure on the reference network."""
    for ports in (None, [53, 67]):
        assert infer_role(
            "192.168.68.56", "Unknown Device", None, 592, 0.78,
            ports, mac="6a:34:64:72:f8:f0", vendor="Unknown",
        ) is None


def test_anonymous_mac_at_the_gateway_address_is_not_a_gateway():
    assert infer_role(
        "192.168.1.1", None, None, 500, 1.0, mac="6a:34:64:72:f8:f0",
    ) is None


def test_randomised_mac_with_a_hostname_is_still_promotable():
    """iOS/Android randomise per-SSID and then keep the address, so a privacy
    MAC is not by itself grounds to refuse identification."""
    assert infer_role(
        "192.168.1.1", None, None, 10, 1.0,
        mac="92:ac:4a:bf:8d:10", hostname="Ossians-iPhone-2022",
    ) == "gateway"


def test_multicast_address_gets_no_role_at_all():
    """01:00:5e:7f:ff:fa / 239.255.255.250 held infrastructure in the live DB."""
    assert infer_role(
        "239.255.255.250", "Unknown Device", None, 654, 1.0,
        mac="01:00:5e:7f:ff:fa",
    ) is None


def test_reference_network_consumer_devices_get_no_infrastructure_role():
    """Every one of these held inferred_role=infrastructure before Phase 2."""
    cases = [
        ("192.168.68.69", "Games Console", "5c:93:a2:5c:47:19", "PS4-C8208A",
         "Liteon Technology Corporation", 588, 0.99),
        ("192.168.68.57", "Unknown Device", "00:21:b7:a3:09:1a", "ET0021B7A3091A",
         "Lexmark International, Inc.", 662, 0.87),
        ("192.168.68.52", "Streaming Stick", "88:3d:24:21:77:66", None,
         "Google", 654, 0.90),
        ("192.168.68.67", "Games Console", "d8:3a:dd:de:11:a7", "PINAS",
         "Microsoft", 662, 1.0),
        ("192.168.68.54", "Streaming Stick", "54:60:09:ee:10:2a", None,
         "Google Chromecast / Google Home / Cast Audio", 654, 0.71),
    ]
    for ip, dt, mac, hn, vendor, scans, stability in cases:
        role = infer_role(ip, dt, None, scans, stability,
                          mac=mac, hostname=hn, vendor=vendor)
        assert role not in ("gateway", "infrastructure"), f"{mac} -> {role}"


# ── recompute_roles (migration) ──────────────────────────────────────────────

class _Row:
    """Minimal known_device stand-in."""

    def __init__(self, **kw):
        self.mac = kw.get("mac", "")
        self.ip = kw.get("ip")
        self.hostname = kw.get("hostname")
        self.vendor = kw.get("vendor")
        self.device_type = kw.get("device_type")
        self.custom_name = kw.get("custom_name")
        self.scan_count = kw.get("scan_count", 0)
        self.ip_stability = kw.get("ip_stability", 0.0)
        self.inferred_role = kw.get("inferred_role")


def _recompute_store(rows):
    store = MagicMock()
    store.get_known_devices.return_value = {r.mac: r for r in rows}
    return store


def test_recompute_clears_a_stale_infrastructure_role():
    """The migration must recompute rather than trust stored values — the
    reference database has 9 wrong assignments, and update_device_stability()
    deliberately never clears a role, so a stale one would survive forever."""
    row = _Row(mac="5c:93:a2:5c:47:19", ip="192.168.68.69", hostname="PS4-C8208A",
               vendor="Liteon Technology Corporation", device_type="Games Console",
               scan_count=588, ip_stability=0.99, inferred_role="infrastructure")
    store = _recompute_store([row])

    changed = recompute_roles(store)

    assert changed == {"5c:93:a2:5c:47:19": None}
    store.clear_inferred_role.assert_called_once_with("5c:93:a2:5c:47:19")
    store.update_device_stability.assert_not_called()


def test_recompute_writes_a_newly_justified_role():
    row = _Row(mac="f0:72:ea:51:d3:b8", ip="192.168.68.64",
               vendor="Google Nest / Nest Wifi / Google Wifi Router",
               device_type="Video Doorbell", scan_count=6, ip_stability=0.67,
               inferred_role=None)
    store = _recompute_store([row])

    changed = recompute_roles(store)

    assert changed == {"f0:72:ea:51:d3:b8": "infrastructure"}
    kwargs = store.update_device_stability.call_args.kwargs
    assert kwargs["inferred_role"] == "infrastructure"
    assert kwargs["scan_count"] == 6


def test_recompute_leaves_a_correct_role_untouched():
    row = _Row(mac="3c:64:cf:e0:27:02", ip="192.168.68.1",
               vendor="TP-Link (Deco mesh / RE series extenders)",
               device_type="Mesh Network Node", scan_count=662,
               ip_stability=1.0, inferred_role="gateway")
    store = _recompute_store([row])

    assert recompute_roles(store) == {}
    store.update_device_stability.assert_not_called()
    store.clear_inferred_role.assert_not_called()


def test_recompute_survives_a_row_that_raises():
    bad = _Row(mac="bad", ip=None, inferred_role="infrastructure")
    good = _Row(mac="5c:93:a2:5c:47:19", ip="192.168.68.69", hostname="PS4",
                vendor="Liteon", scan_count=10, ip_stability=1.0,
                inferred_role="infrastructure")
    store = _recompute_store([bad, good])
    store.clear_inferred_role.side_effect = [RuntimeError("locked"), None]

    changed = recompute_roles(store)

    assert "5c:93:a2:5c:47:19" in changed


# ── purge_non_devices (migration) ────────────────────────────────────────────

def test_purge_deletes_a_multicast_group():
    """Acceptance criterion 3: `239.255.255.250` must be *absent* from
    known_device. Phase 1 only stopped new multicast rows being written and
    Phase 2 only cleared the role — the SSDP group survived both."""
    row = _Row(mac="01:00:5e:7f:ff:fa", ip="239.255.255.250", scan_count=654)
    store = _recompute_store([row])

    purged = purge_non_devices(store)

    assert purged == {"01:00:5e:7f:ff:fa": "01:00:5e:7f:ff:fa is a multicast/broadcast MAC, not a host"}
    store.delete_known_device.assert_called_once_with("01:00:5e:7f:ff:fa")


def test_purge_leaves_a_real_device_alone():
    row = _Row(mac="3c:64:cf:e0:27:02", ip="192.168.68.1",
               vendor="TP-Link (Deco mesh / RE series extenders)",
               device_type="Mesh Network Node", scan_count=662, ip_stability=1.0)
    store = _recompute_store([row])

    assert purge_non_devices(store) == {}
    store.delete_known_device.assert_not_called()


def test_purge_keeps_an_anonymous_device():
    """ANONYMOUS is a real device the app cannot name — losing it would delete
    a live host from the user's inventory. Only NOT_A_DEVICE is purgeable."""
    row = _Row(mac="02:a8:f1:3b:93:40", ip="192.168.68.72",
               scan_count=483, ip_stability=0.78)
    store = _recompute_store([row])

    assert purge_non_devices(store) == {}
    store.delete_known_device.assert_not_called()


def test_purge_is_idempotent():
    """Runs behind a run-once QSettings key, but a re-run after a restore must
    not double-delete or raise."""
    store = _recompute_store([])

    assert purge_non_devices(store) == {}
    store.delete_known_device.assert_not_called()


def test_purge_survives_a_row_that_raises():
    bad = _Row(mac="01:00:5e:00:00:fb", ip="224.0.0.251")
    good = _Row(mac="01:00:5e:7f:ff:fa", ip="239.255.255.250")
    store = _recompute_store([bad, good])
    store.delete_known_device.side_effect = [RuntimeError("locked"), None]

    purged = purge_non_devices(store)

    assert "01:00:5e:7f:ff:fa" in purged
    assert "01:00:5e:00:00:fb" not in purged


# ── is_static_candidate ───────────────────────────────────────────────────────

def test_static_candidate_pinned_always_true():
    assert is_static_candidate(0.0, 0, None, is_pinned=True) is True


def test_static_candidate_gateway_role():
    assert is_static_candidate(0.5, 1, "gateway") is True


def test_static_candidate_high_stability():
    assert is_static_candidate(0.9, 5, None) is True


def test_static_candidate_low_stability_not_static():
    assert is_static_candidate(0.5, 2, None) is False


def test_static_candidate_enough_scans_but_low_stability():
    assert is_static_candidate(0.6, 10, None) is False


# ── update_stability_for_device ───────────────────────────────────────────────

def test_update_writes_to_store():
    store = MagicMock()
    # ip_history: 8 at .1, 2 at .50 (total 10)
    store.get_ip_history_stats.return_value = [("192.168.1.1", 8), ("192.168.1.50", 2)]
    store.get_total_seen_count.return_value = 10
    store.update_device_stability.return_value = None

    update_stability_for_device(
        mac=_OUI_MAC,
        ip="192.168.1.1",
        device_type="router",
        custom_name=None,
        store=store,
    )

    store.update_device_stability.assert_called_once()
    call_kwargs = store.update_device_stability.call_args.kwargs
    # scan_count = 10, ip_stability = 0.8, role = "gateway" (IP ends in .1)
    assert call_kwargs["scan_count"] == 10
    assert abs(call_kwargs["ip_stability"] - 0.8) < 1e-9
    assert call_kwargs["inferred_role"] == "gateway"


def test_update_preserves_role_when_none_inferred():
    """When role inference returns None, inferred_role must be passed as None
    so MetricStore.update_device_stability does not clear the existing value."""
    store = MagicMock()
    store.get_ip_history_stats.return_value = [("192.168.1.200", 1)]
    store.get_total_seen_count.return_value = 1
    store.update_device_stability.return_value = None

    update_stability_for_device(
        mac=_OUI_MAC,
        ip="192.168.1.200",
        device_type="Unknown Device",
        custom_name=None,
        store=store,
    )

    call_kwargs = store.update_device_stability.call_args.kwargs
    assert call_kwargs["inferred_role"] is None


def test_update_passes_identity_and_evidence_through_to_inference():
    """The identity gate is only as good as what reaches it — a hostname/vendor
    that stops at the DeviceTracker would make every privacy MAC anonymous."""
    store = MagicMock()
    store.get_ip_history_stats.return_value = [("192.168.68.50", 10)]
    store.get_total_seen_count.return_value = 10

    update_stability_for_device(
        mac="92:ac:4a:bf:8d:10",          # randomised MAC ...
        ip="192.168.68.50",
        device_type=None,
        custom_name=None,
        store=store,
        hostname="Ossians-iPhone-2022",   # ... but perfectly identifiable
        evidence=RoleEvidence(gateway_ip="192.168.68.50"),
    )

    assert store.update_device_stability.call_args.kwargs["inferred_role"] == "gateway"
