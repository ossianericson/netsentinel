"""Tests for modules/smb_enumerator.py — SMB/Windows Share enumerator."""
from modules.smb_enumerator import (
    SMBShare, SMBUser, SMBSession, NetBIOSInfo, SMBEnumResult, enumerate_smb,
)


def test_import():
    import modules.smb_enumerator as m
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
