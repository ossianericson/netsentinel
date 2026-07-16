"""Tests for modules/smb_enumerator.py — SMB/Windows Share enumerator."""
import struct

from modules.smb_enumerator import (
    SMBShare, SMBUser, SMBSession, NetBIOSInfo, SMBEnumResult, enumerate_smb,
    _netbios_name_query, _net_view_shares, _net_exe_enum, _impacket_enum,
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


# ── F-88: SMB share risk flag auth-state awareness ─────────────────────────────

def test_smb_share_visible_anonymous_defaults_false():
    s = SMBShare(name="Public")
    assert s.visible_anonymous is False


def test_risk_flags_only_lists_anonymously_visible_disk_shares():
    result = SMBEnumResult(
        host="10.0.0.5",
        shares=[
            SMBShare(name="Public", share_type="DISK", visible_anonymous=True),
            SMBShare(name="Private", share_type="DISK", visible_anonymous=False),
        ],
    )
    flags = result.risk_flags
    disk_flag = next((f for f in flags if "disk share" in f), "")
    assert "Public" in disk_flag
    assert "Private" not in disk_flag


def test_risk_flags_silent_when_no_share_is_anonymously_visible():
    result = SMBEnumResult(
        host="10.0.0.5",
        shares=[SMBShare(name="Private", share_type="DISK", visible_anonymous=False)],
    )
    assert not any("disk share" in f for f in result.risk_flags)


def test_net_view_shares_marks_all_shares_visible_anonymous(monkeypatch):
    from modules import smb_enumerator
    monkeypatch.setattr(smb_enumerator.platform, "system", lambda: "Windows")
    net_view_output = (
        "Share name  Type      Used as  Comment\n"
        "----------------------------------------\n"
        "Public      Disk               \n"
        "Private     Disk               \n"
    )
    monkeypatch.setattr(
        smb_enumerator.subprocess, "check_output",
        lambda *a, **k: net_view_output,
    )
    shares = _net_view_shares("10.0.0.1")
    assert len(shares) == 2
    assert all(s.visible_anonymous is True for s in shares)


def test_net_exe_enum_marks_shares_via_anonymous_reprobe(monkeypatch):
    from modules import smb_enumerator
    monkeypatch.setattr(smb_enumerator.platform, "system", lambda: "Windows")

    net_view_output = (
        "Share name  Type      Used as  Comment\n"
        "----------------------------------------\n"
        "Public      Disk               \n"
        "Private     Disk               \n"
    )

    def fake_check_output(cmd, **kwargs):
        if len(cmd) >= 2 and cmd[0] == "net" and cmd[1] == "view":
            return net_view_output
        return ""

    monkeypatch.setattr(smb_enumerator.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(
        smb_enumerator, "_net_view_shares",
        lambda host: [SMBShare(name="Public", share_type="DISK", visible_anonymous=True)],
    )

    result = _net_exe_enum("10.0.0.1", "admin", "pw", "", progress=None)

    visible = {s.name: s.visible_anonymous for s in result.shares}
    assert visible == {"Public": True, "Private": False}


def _share_dict(name: str, stype: int = 0, remark: str = "") -> dict:
    return {
        "shi1_netname": name + "\x00",
        "shi1_type": stype,
        "shi1_remark": (remark + "\x00") if remark else "",
    }


def _make_fake_smb_connection(authed_shares, anon_shares, anon_login_ok=True):
    class _FakeSMBConnection:
        def __init__(self, remote_name, remote_host, timeout=None):
            self._is_anon = False

        def login(self, username, password, domain=""):
            if username == "" and password == "":
                if not anon_login_ok:
                    raise RuntimeError("anonymous login refused")
                self._is_anon = True

        def getServerOS(self):
            return "Windows Server 2019"

        def getServerDomain(self):
            return "CORP"

        def getServerName(self):
            return "FILESERVER"

        def listShares(self):
            return anon_shares if self._is_anon else authed_shares

        def logoff(self):
            pass

    return _FakeSMBConnection


def test_impacket_enum_marks_shares_visible_when_in_anonymous_set(monkeypatch):
    from modules import smb_enumerator
    fake_conn = _make_fake_smb_connection(
        authed_shares=[_share_dict("Public", 0), _share_dict("Private", 0)],
        anon_shares=[_share_dict("Public", 0)],
    )
    monkeypatch.setattr(smb_enumerator, "SMBConnection", fake_conn, raising=False)

    result = _impacket_enum("10.0.0.1", "admin", "pw", "CORP", 5.0, progress=None)

    visible = {s.name: s.visible_anonymous for s in result.shares}
    assert visible == {"Public": True, "Private": False}
    assert result.anonymous_login is True


def test_impacket_enum_anonymous_login_refused_no_share_visible(monkeypatch):
    from modules import smb_enumerator
    fake_conn = _make_fake_smb_connection(
        authed_shares=[_share_dict("Public", 0)],
        anon_shares=[],
        anon_login_ok=False,
    )
    monkeypatch.setattr(smb_enumerator, "SMBConnection", fake_conn, raising=False)

    result = _impacket_enum("10.0.0.1", "admin", "pw", "CORP", 5.0, progress=None)

    assert result.anonymous_login is False
    assert all(s.visible_anonymous is False for s in result.shares)
