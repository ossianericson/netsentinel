"""Tests for modules/snmp_poller.py — raw SNMP GET poller."""
from unittest.mock import patch

from modules.snmp_poller import (
    _encode_oid, _ber_length, _ber_tlv, _build_snmp_get,
    SNMPResult, poll,
)


def test_import():
    from modules import snmp_poller as m
    assert hasattr(m, "poll")
    assert hasattr(m, "SNMPResult")
    assert hasattr(m, "_encode_oid")
    assert hasattr(m, "_build_snmp_get")


def test_encode_oid_sysDescr():
    encoded = _encode_oid("1.3.6.1.2.1.1.1.0")
    assert isinstance(encoded, bytes)
    assert len(encoded) > 0


def test_encode_oid_simple():
    encoded = _encode_oid("1.3")
    assert isinstance(encoded, bytes)


def test_ber_length_short():
    data = b"\x01\x02\x03"
    result = _ber_length(data)
    assert result == bytes([3])


def test_ber_length_long():
    data = bytes(200)
    result = _ber_length(data)
    # Long form: 0x81 + length byte
    assert result[0] == 0x81
    assert result[1] == 200


def test_ber_tlv_builds_bytes():
    result = _ber_tlv(0x04, b"hello")
    assert result[0] == 0x04
    assert b"hello" in result


def test_build_snmp_get_valid():
    pkt = _build_snmp_get("1.3.6.1.2.1.1.1.0", community="public", request_id=42)
    assert isinstance(pkt, bytes)
    assert b"public" in pkt


def test_snmp_result_defaults():
    r = SNMPResult(host="192.168.1.1")
    assert r.host == "192.168.1.1"
    assert r.sys_descr == ""
    assert r.sys_name == ""
    assert r.reachable is False


def test_poll_unreachable_returns_result():
    result = poll("240.0.0.1", timeout=0.2)
    assert isinstance(result, SNMPResult)
    assert result.reachable is False


def test_snmp_result_cpu_load_default_empty():
    r = SNMPResult(host="192.168.1.1")
    assert r.cpu_load == ""


def test_poll_cpu_load_primary_oid_hit():
    from modules.snmp_poller import _poll_cpu_load

    def fake_get(host, oid, community, timeout):
        if oid == "1.3.6.1.2.1.25.3.3.1.2.1":
            return "17"
        return "<error: not found>"

    with patch("modules.snmp_poller._snmp_get_single", side_effect=fake_get):
        assert _poll_cpu_load("192.168.1.1", "public", 2.0) == "17%"


def test_poll_cpu_load_falls_back_to_vendor_oid_when_primary_misses():
    from modules.snmp_poller import _poll_cpu_load

    def fake_get(host, oid, community, timeout):
        if oid == "1.3.6.1.2.1.25.3.3.1.2.1":
            return "<error: not found>"
        if oid == "1.3.6.1.4.1.9.9.109.1.1.1.1.8.1":
            return "42"
        return "<error: not found>"

    with patch("modules.snmp_poller._snmp_get_single", side_effect=fake_get):
        assert _poll_cpu_load("192.168.1.1", "public", 2.0) == "42%"


def test_poll_cpu_load_both_miss_returns_empty_string():
    from modules.snmp_poller import _poll_cpu_load

    def fake_get(host, oid, community, timeout):
        return "<error: not found>"

    with patch("modules.snmp_poller._snmp_get_single", side_effect=fake_get):
        assert _poll_cpu_load("192.168.1.1", "public", 2.0) == ""


def test_poll_populates_cpu_load_field():
    responses = {
        "1.3.6.1.2.1.1.1.0": "Linux router",
        "1.3.6.1.2.1.1.3.0": "12345",
        "1.3.6.1.2.1.1.5.0": "router1",
        "1.3.6.1.2.1.1.4.0": "admin",
        "1.3.6.1.2.1.2.1.0": "4",
        "1.3.6.1.2.1.25.3.3.1.2.1": "9",
    }

    def fake_get(host, oid, community, timeout):
        return responses.get(oid, "<error: not found>")

    with patch("modules.snmp_poller._snmp_get_single", side_effect=fake_get):
        result = poll("192.168.1.1")

    assert result.cpu_load == "9%"
    assert result.reachable is True
