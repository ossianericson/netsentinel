"""Tests for modules/alert_engine_checks4.py — _AlertChecksMixin4
(V6 Sprint 4 — ARP_SPOOF / ROGUE_DHCP / CONFIG_DRIFT)."""
from __future__ import annotations

from modules.alert_engine import AlertEngine, AlertRule
from modules.arp_monitor import SpoofEvent
from modules.arp_watch import ArpWatchReport
from modules.config_baseline import build_snapshot_from_scan, diff_snapshots
from modules.dhcp_detector import DHCPOffer
from modules.dhcp_watch import DhcpWatchReport


def test_import_mixin():
    from modules.alert_engine_checks4 import _AlertChecksMixin4
    assert _AlertChecksMixin4 is not None


def test_mixin_methods_present():
    from modules.alert_engine_checks4 import _AlertChecksMixin4
    assert hasattr(_AlertChecksMixin4, "evaluate_arp_watch_checks")
    assert hasattr(_AlertChecksMixin4, "evaluate_dhcp_watch_checks")
    assert hasattr(_AlertChecksMixin4, "evaluate_config_drift_checks")


def test_evaluate_arp_watch_checks_no_events():
    engine = AlertEngine(rules=[AlertRule(name="arp", rule_type="ARP_SPOOF", cooldown_s=0)])
    fired = engine.evaluate_arp_watch_checks(ArpWatchReport(events=[]))
    assert fired == []


def test_evaluate_arp_watch_checks_gateway_hijack_is_critical():
    engine = AlertEngine(rules=[AlertRule(name="arp", rule_type="ARP_SPOOF", cooldown_s=0)])
    evt = SpoofEvent(
        event_type="GATEWAY_HIJACK", attacker_mac="11:22:33:44:55:66",
        attacker_ip="192.168.1.50", victim_ip="192.168.1.1",
        original_mac="aa:bb:cc:dd:ee:ff", verdict="GATEWAY HIJACK: ...",
    )
    fired = engine.evaluate_arp_watch_checks(ArpWatchReport(events=[evt]))
    assert len(fired) == 1
    assert fired[0].rule_type == "ARP_SPOOF"
    assert fired[0].severity == "CRITICAL"
    assert fired[0].host == "192.168.1.1"


def test_evaluate_dhcp_watch_checks_ignores_legitimate_offers():
    engine = AlertEngine(rules=[AlertRule(name="dhcp", rule_type="ROGUE_DHCP", cooldown_s=0)])
    legit = DHCPOffer(server_ip="192.168.1.1", server_mac="aa:bb:cc:dd:ee:ff",
                       offered_ip="192.168.1.100", gateway="192.168.1.1", is_rogue=False)
    fired = engine.evaluate_dhcp_watch_checks(DhcpWatchReport(offers=[legit], rogue_offers=[]))
    assert fired == []


def test_evaluate_dhcp_watch_checks_fires_for_rogue_offer():
    engine = AlertEngine(rules=[AlertRule(name="dhcp", rule_type="ROGUE_DHCP", cooldown_s=0)])
    rogue = DHCPOffer(server_ip="192.168.1.99", server_mac="11:22:33:44:55:66",
                       offered_ip="192.168.1.101", gateway="192.168.1.99", is_rogue=True,
                       verdict="ROGUE DHCP SERVER: ...")
    fired = engine.evaluate_dhcp_watch_checks(DhcpWatchReport(offers=[rogue], rogue_offers=[rogue]))
    assert len(fired) == 1
    assert fired[0].rule_type == "ROGUE_DHCP"
    assert fired[0].severity == "CRITICAL"
    assert fired[0].host == "192.168.1.99"


def test_evaluate_config_drift_checks_no_drift():
    engine = AlertEngine(rules=[AlertRule(name="drift", rule_type="CONFIG_DRIFT", cooldown_s=0)])
    old = build_snapshot_from_scan([{"ip": "192.168.1.10", "device_type": "router"}])
    old.id = 1
    new = build_snapshot_from_scan([{"ip": "192.168.1.10", "device_type": "router"}])
    new.id = 2
    diff = diff_snapshots(old, new)
    fired = engine.evaluate_config_drift_checks(diff)
    assert fired == []


def test_evaluate_config_drift_checks_added_removed_and_role_change():
    engine = AlertEngine(rules=[AlertRule(name="drift", rule_type="CONFIG_DRIFT", cooldown_s=0)])
    old = build_snapshot_from_scan([
        {"ip": "192.168.1.10", "device_type": "router"},
        {"ip": "192.168.1.20", "device_type": "iot"},
    ])
    old.id = 1
    new = build_snapshot_from_scan([
        {"ip": "192.168.1.10", "device_type": "server"},   # role changed
        {"ip": "192.168.1.30", "device_type": "iot"},       # added
    ])
    new.id = 2
    diff = diff_snapshots(old, new)

    fired = engine.evaluate_config_drift_checks(diff)
    hosts = {a.host for a in fired}
    assert hosts == {"192.168.1.10", "192.168.1.20", "192.168.1.30"}
    assert all(a.rule_type == "CONFIG_DRIFT" for a in fired)
