"""Tests for modules/dns_zone_scanner.py — DNS zone enumeration (AXFR + mDNS)."""
from modules.dns_zone_scanner import (
    DnsRecord, MdnsService, DnsZoneResult, _decode_name, _parse_rdata,
)


class _FakeSocket:
    """Mimics socket.socket just enough to drive axfr_transfer's cleanup path."""

    def __init__(self, fail_on):
        self._fail_on = fail_on  # which method should raise
        self.closed = False

    def settimeout(self, _t):
        pass

    def connect(self, _addr):
        if self._fail_on == "connect":
            raise ConnectionRefusedError("refused")

    def sendall(self, _msg):
        if self._fail_on == "sendall":
            raise OSError("broken pipe")

    def recv(self, _n):
        if self._fail_on == "recv":
            raise TimeoutError("recv timed out")
        return b""

    def close(self):
        self.closed = True


def test_axfr_transfer_closes_socket_on_connection_failure(monkeypatch):
    """A refused/failed AXFR connection must still close the socket, not leak it."""
    from modules import dns_zone_scanner as m

    fake = _FakeSocket(fail_on="connect")
    monkeypatch.setattr(m.socket, "socket", lambda *a, **kw: fake)

    result = m.axfr_transfer("10.0.0.1", "example.com", timeout=1.0)

    assert result == []
    assert fake.closed is True


def test_import():
    from modules import dns_zone_scanner as m
    assert hasattr(m, "DnsZoneResult")
    assert hasattr(m, "_parse_dns_response")


def test_dns_record_fields():
    r = DnsRecord(name="example.com", rtype="A", value="1.2.3.4", ttl=300)
    assert r.name == "example.com"
    assert r.rtype == "A"
    assert r.value == "1.2.3.4"
    assert r.ttl == 300


def test_mdns_service_fields():
    s = MdnsService(
        service_type="_http._tcp.local",
        instance="MyHost",
        host="myhost.local",
        ip="192.168.1.10",
        port=80,
    )
    assert s.service_type == "_http._tcp.local"
    assert s.port == 80


def test_dns_zone_result_defaults():
    r = DnsZoneResult()
    assert r.records == []
    assert r.services == []
    assert r.verdict == ""
    assert r.level in ("CLEAN", "LOW", "HIGH", "UNKNOWN", "")


def test_decode_name_simple():
    # Encode "example.com" as DNS wire format
    data = b"\x07example\x03com\x00"
    name, offset = _decode_name(data, 0)
    assert name.lower() == "example.com"
    assert offset > 0


def test_decode_name_pointer(monkeypatch):
    # DNS compression pointer — 0xC0 + offset
    # "example.com" at offset 0, pointer at offset 13 pointing back to 0
    data = b"\x07example\x03com\x00" + b"\xc0\x00"
    name, offset = _decode_name(data, 13)
    assert name.lower() == "example.com"


def test_parse_rdata_a_record():
    data = b"\x01\x02\x03\x04"
    result = _parse_rdata(1, data, 0, 4)  # type A = 1
    assert "1.2.3.4" in result
