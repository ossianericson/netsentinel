"""Tests for modules/smb_enumerator.py — SMB/Windows Share enumerator."""
import struct

from modules.smb_enumerator import (
    SMBShare, SMBUser, SMBSession, NetBIOSInfo, SMBEnumResult, enumerate_smb,
    _netbios_name_query,
)


def test_import():
    from modules import smb_enumerator as m
    assert hasattr(m, "enumerate_smb")
    assert hasattr(m, "SMBEnumResult")
    assert hasattr(m, "NetBIOSInfo")


def test_smb_share_fields():
    s = SMBShare(name="SHARE$")
    assert s.name == "SHARE$"
    assert s.share_type == ""
    assert s.permissions == ""


def test_smb_user_fields():
    u = SMBUser(username="admin")
    assert u.username == "admin"
    assert u.full_name == ""


def test_smb_session_fields():
    s = SMBSession(client_ip="10.0.0.5", username="user")
    assert s.username == "user"
    assert s.client_ip == "10.0.0.5"


def test_netbios_info_defaults():
    n = NetBIOSInfo()
    assert n.machine_name == ""
    assert n.workgroup == ""
    assert n.mac == ""
    assert n.is_domain_controller is False


def test_smb_enum_result_defaults():
    r = SMBEnumResult(host="192.168.1.100", netbios=NetBIOSInfo())
    assert r.host == "192.168.1.100"
    assert r.shares == []
    assert r.users == []
    assert r.tier == 1


def test_enumerate_smb_unreachable():
    result = enumerate_smb("240.0.0.1", timeout=0.2)
    assert isinstance(result, SMBEnumResult)
    assert result.host == "240.0.0.1"


def _build_nbstat_response(entries):
    """Build a fake NBSTAT (UDP 137) reply body matching _netbios_name_query's parser:
    56-byte pad up to the name table, a name-count byte, then 18-byte name records
    (15-byte padded name + 1-byte type + 2-byte flags), followed by a 6-byte MAC."""
    body = bytes([len(entries)])
    for name, ntype, flags in entries:
        body += name.encode("ascii").ljust(15, b" ")[:15]
        body += bytes([ntype])
        body += struct.pack(">H", flags)
    body += b"\x00" * 6  # MAC
    return b"\x00" * 56 + body


class _FakeNbstatSocket:
    def __init__(self, reply: bytes):
        self._reply = reply

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def settimeout(self, timeout):
        pass

    def sendto(self, data, addr):
        pass

    def recvfrom(self, bufsize):
        return self._reply, ("10.0.0.1", 137)


def test_netbios_name_query_sets_domain_controller_flag(monkeypatch):
    # F-56 (partial): a 0x1C (domain controller list) NBSTAT record must set
    # is_domain_controller, not just get folded into .workgroup.
    reply = _build_nbstat_response([
        ("WORKSTATION", 0x00, 0x0000),
        ("MYDOMAIN", 0x1C, 0x0000),
    ])
    monkeypatch.setattr(
        "modules.smb_enumerator.socket.socket",
        lambda *a, **k: _FakeNbstatSocket(reply),
    )
    info = _netbios_name_query("10.0.0.1")
    assert info.is_domain_controller is True
    assert info.workgroup == "MYDOMAIN"


def test_netbios_name_query_non_dc_leaves_flag_false(monkeypatch):
    reply = _build_nbstat_response([
        ("WORKSTATION", 0x00, 0x0000),
        ("WORKGROUP", 0x00, 0x8000),
    ])
    monkeypatch.setattr(
        "modules.smb_enumerator.socket.socket",
        lambda *a, **k: _FakeNbstatSocket(reply),
    )
    info = _netbios_name_query("10.0.0.1")
    assert info.is_domain_controller is False


def test_enumerate_smb_tier1_propagates_domain_controller_flag(monkeypatch):
    monkeypatch.setattr(
        "modules.smb_enumerator._netbios_name_query",
        lambda host, timeout=3.0: NetBIOSInfo(machine_name="DC01", is_domain_controller=True),
    )
    monkeypatch.setattr(
        "modules.smb_enumerator._smb_anonymous_banner",
        lambda host, timeout=5.0: ("", False),
    )
    result = enumerate_smb("10.0.0.1", timeout=0.2)
    assert result.is_domain_controller is True
    assert "Domain Controller" in " ".join(result.risk_flags)
