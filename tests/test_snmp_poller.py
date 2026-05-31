"""Tests for modules/snmp_poller.py — raw SNMP GET poller."""
import pytest
from modules.snmp_poller import (
    _encode_oid, _ber_length, _ber_tlv, _build_snmp_get,
    SNMPResult, poll,
)


def test_import():
    import modules.snmp_poller as m
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
