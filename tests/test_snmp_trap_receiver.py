"""
Tests for SNMP trap receiver module (T2#10).

Covers:
  • BER decoder helpers (OID, length, value types)
  • decode_trap_packet (v1 + v2c + malformed)
  • SnmpTrapReceiver (open / receive / close lifecycle)
  • SnmpTrap dataclass defaults
"""

from __future__ import annotations

import socket
import struct
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from modules.snmp_trap_receiver import (
    SnmpTrap,
    SnmpTrapReceiver,
    _decode_oid,
    _decode_value,
    _encode_oid,
    decode_trap_packet,
    SNMP_TRAP_PORT,
    FALLBACK_PORT,
)


# ── BER helpers ───────────────────────────────────────────────────────────────

class TestEncodeDecodeOid:
    def test_roundtrip_simple(self):
        oid = "1.3.6.1.2.1.1.1.0"
        assert _decode_oid(_encode_oid(oid)) == oid

    def test_roundtrip_enterprise(self):
        oid = "1.3.6.1.4.1.9.9.46.2.6.1.1.14"
        assert _decode_oid(_encode_oid(oid)) == oid

    def test_single_component_zero(self):
        raw = bytes([0])        # encodes 0.0
        decoded = _decode_oid(raw)
        assert decoded == "0.0"

    def test_empty_bytes(self):
        assert _decode_oid(b"") == "0.0"


class TestDecodeValue:
    def test_integer(self):
        raw = bytes([0, 0, 0, 42])
        assert _decode_value(0x02, raw) == "42"

    def test_negative_integer(self):
        raw = struct.pack(">i", -1)
        assert _decode_value(0x02, raw) == "-1"

    def test_octet_string_utf8(self):
        assert _decode_value(0x04, b"hello") == "hello"

    def test_octet_string_binary_fallback(self):
        result = _decode_value(0x04, bytes([0xFF, 0xFE]))
        # Should be a hex string or replacement-char string, not crash
        assert isinstance(result, str)

    def test_ip_address(self):
        assert _decode_value(0x40, bytes([192, 168, 1, 1])) == "192.168.1.1"

    def test_timeticks(self):
        # 100 hundredths = 1 second
        raw = struct.pack(">I", 100)
        result = _decode_value(0x43, raw)
        assert "1s" in result

    def test_null(self):
        assert _decode_value(0x05, b"") == ""

    def test_unknown_tag_returns_hex(self):
        result = _decode_value(0xFF, bytes([0xDE, 0xAD]))
        assert isinstance(result, str)


# ── SNMPv2c trap packet ───────────────────────────────────────────────────────

def _build_v2c_trap_packet(
    community: str = "public",
    trap_oid: str = "1.3.6.1.6.3.1.1.5.1",
) -> bytes:
    """Build a minimal valid SNMPv2c Trap-PDU (0xA7) packet."""
    def ber_tlv(tag, value):
        n = len(value)
        if n < 0x80:
            return bytes([tag, n]) + value
        return bytes([tag, 0x81, n]) + value

    def ber_oid(oid_str):
        return ber_tlv(0x06, _encode_oid(oid_str))

    def ber_int(val):
        return ber_tlv(0x02, bytes([val]))

    def ber_seq(content):
        return ber_tlv(0x30, content)

    # sysUpTime.0 varbind
    sysuptime_oid = ber_oid("1.3.6.1.2.1.1.3.0")
    timeticks     = ber_tlv(0x43, struct.pack(">I", 12345))
    vb1           = ber_seq(sysuptime_oid + timeticks)

    # snmpTrapOID.0 varbind
    trapoid_oid   = ber_oid("1.3.6.1.6.3.1.1.4.1.0")
    trapoid_val   = ber_oid(trap_oid)
    vb2           = ber_seq(trapoid_oid + trapoid_val)

    varbind_list  = ber_seq(vb1 + vb2)
    req_id        = ber_int(1)
    err_status    = ber_int(0)
    err_idx       = ber_int(0)

    pdu           = ber_tlv(0xA7, req_id + err_status + err_idx + varbind_list)
    version       = ber_int(1)              # SNMPv2c = 1
    comm          = ber_tlv(0x04, community.encode())
    return ber_seq(version + comm + pdu)


def _build_v1_trap_packet(
    community: str = "public",
    enterprise: str = "1.3.6.1.4.1.9",
    generic: int = 3,   # linkUp
) -> bytes:
    """Build a minimal valid SNMPv1 Trap-PDU (0xA4) packet."""
    def ber_tlv(tag, value):
        n = len(value)
        if n < 0x80:
            return bytes([tag, n]) + value
        return bytes([tag, 0x81, n]) + value

    def ber_int(val):
        return ber_tlv(0x02, bytes([val]))

    def ber_seq(content):
        return ber_tlv(0x30, content)

    ent_oid      = ber_tlv(0x06, _encode_oid(enterprise))
    agent_addr   = ber_tlv(0x40, bytes([10, 0, 0, 1]))
    gen_trap     = ber_int(generic)
    spec_trap    = ber_int(0)
    time_stamp   = ber_tlv(0x43, struct.pack(">I", 100))
    varbind_list = ber_seq(b"")                          # empty varbinds

    pdu          = ber_tlv(0xA4, ent_oid + agent_addr + gen_trap + spec_trap + time_stamp + varbind_list)
    version      = ber_int(0)              # SNMPv1 = 0
    comm         = ber_tlv(0x04, community.encode())
    return ber_seq(version + comm + pdu)


# ── decode_trap_packet ────────────────────────────────────────────────────────

class TestDecodeV2cTrap:
    def test_version_is_v2c(self):
        pkt = _build_v2c_trap_packet()
        trap = decode_trap_packet(pkt, "10.0.0.1", 12345)
        assert trap.version == "v2c"

    def test_community_extracted(self):
        pkt = _build_v2c_trap_packet(community="private")
        trap = decode_trap_packet(pkt, "10.0.0.1", 0)
        assert trap.community == "private"

    def test_trap_oid_extracted(self):
        pkt = _build_v2c_trap_packet(trap_oid="1.3.6.1.6.3.1.1.5.3")
        trap = decode_trap_packet(pkt, "10.0.0.1", 0)
        assert "1.3.6.1.6.3.1.1.5.3" in trap.trap_oid

    def test_source_ip_preserved(self):
        pkt = _build_v2c_trap_packet()
        trap = decode_trap_packet(pkt, "192.168.99.1", 162)
        assert trap.src_ip == "192.168.99.1"

    def test_has_varbinds(self):
        pkt = _build_v2c_trap_packet()
        trap = decode_trap_packet(pkt, "10.0.0.1", 0)
        assert len(trap.varbinds) >= 2

    def test_timestamp_set(self):
        before = int(time.time())
        pkt = _build_v2c_trap_packet()
        trap = decode_trap_packet(pkt, "10.0.0.1", 0)
        assert trap.ts >= before


class TestDecodeV1Trap:
    def test_version_is_v1(self):
        pkt = _build_v1_trap_packet()
        trap = decode_trap_packet(pkt, "10.0.0.2", 162)
        assert trap.version == "v1"

    def test_trap_type_name(self):
        pkt = _build_v1_trap_packet(generic=3)
        trap = decode_trap_packet(pkt, "10.0.0.2", 162)
        assert trap.trap_type == "linkUp"

    def test_community_extracted(self):
        pkt = _build_v1_trap_packet(community="secret")
        trap = decode_trap_packet(pkt, "10.0.0.2", 162)
        assert trap.community == "secret"

    def test_cold_start_type(self):
        pkt = _build_v1_trap_packet(generic=0)
        trap = decode_trap_packet(pkt, "10.0.0.2", 162)
        assert trap.trap_type == "coldStart"

    def test_link_down_type(self):
        pkt = _build_v1_trap_packet(generic=2)
        trap = decode_trap_packet(pkt, "10.0.0.2", 162)
        assert trap.trap_type == "linkDown"


class TestMalformedPacket:
    def test_empty_bytes(self):
        trap = decode_trap_packet(b"", "1.2.3.4", 162)
        assert trap.raw_error != ""

    def test_garbage_bytes(self):
        trap = decode_trap_packet(b"\xFF\xFF\xFF\xFF", "1.2.3.4", 0)
        assert trap.raw_error != ""

    def test_truncated_packet(self):
        pkt = _build_v2c_trap_packet()
        trap = decode_trap_packet(pkt[:10], "1.2.3.4", 0)
        assert trap.raw_error != ""

    def test_fields_still_set_on_error(self):
        trap = decode_trap_packet(b"\x00", "9.9.9.9", 999)
        assert trap.src_ip == "9.9.9.9"
        assert trap.src_port == 999


# ── SnmpTrapReceiver lifecycle ────────────────────────────────────────────────

class TestSnmpTrapReceiver:
    def test_open_and_close(self):
        r = SnmpTrapReceiver(port=0)   # OS-assigned port
        port = r.open()
        assert port > 0
        r.close()

    def test_listen_port_set_after_open(self):
        r = SnmpTrapReceiver(port=0)
        r.open()
        assert r.listen_port > 0
        r.close()

    def test_receive_one_returns_trap(self):
        """Send a UDP packet to the receiver and verify it's decoded."""
        r = SnmpTrapReceiver(port=0)
        r.open()
        port = r.listen_port

        pkt = _build_v2c_trap_packet()

        def _send():
            time.sleep(0.05)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(pkt, ("127.0.0.1", port))
            s.close()

        threading.Thread(target=_send, daemon=True).start()
        trap = r.receive_one()
        r.close()
        assert trap is not None
        assert trap.version == "v2c"

    def test_receive_one_returns_none_on_timeout(self):
        r = SnmpTrapReceiver(port=0)
        r.open()
        result = r.receive_one()   # no sender → times out in 1 s
        r.close()
        assert result is None

    def test_on_trap_callback_called(self):
        cb = MagicMock()
        r = SnmpTrapReceiver(port=0, on_trap=cb)
        r.open()
        port = r.listen_port

        pkt = _build_v2c_trap_packet()

        def _send():
            time.sleep(0.05)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(pkt, ("127.0.0.1", port))
            s.close()

        threading.Thread(target=_send, daemon=True).start()
        r.receive_one()
        r.close()
        cb.assert_called_once()

    def test_close_twice_no_error(self):
        r = SnmpTrapReceiver(port=0)
        r.open()
        r.close()
        r.close()   # should not raise


# ── SnmpTrap dataclass ────────────────────────────────────────────────────────

class TestSnmpTrapDataclass:
    def test_varbinds_defaults_empty(self):
        t = SnmpTrap(ts=0, src_ip="", src_port=0, version="v2c",
                     community="", trap_oid="", trap_type="")
        assert t.varbinds == []

    def test_raw_error_defaults_empty(self):
        t = SnmpTrap(ts=0, src_ip="", src_port=0, version="v2c",
                     community="", trap_oid="", trap_type="")
        assert t.raw_error == ""
