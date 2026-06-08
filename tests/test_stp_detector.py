"""Tests for modules/stp_detector.py — STP/BPDU rogue bridge detector."""
from modules.stp_detector import SCAPY_AVAILABLE, BPDUInfo, _parse_bpdu


def test_import():
    import modules.stp_detector as m
    assert hasattr(m, "SCAPY_AVAILABLE")
    assert hasattr(m, "BPDUInfo")
    assert hasattr(m, "STPSniffer")
    assert hasattr(m, "scan")


def test_scapy_flag_is_bool():
    assert isinstance(SCAPY_AVAILABLE, bool)


def test_bpdu_info_fields():
    b = BPDUInfo(
        src_mac="01:80:c2:00:00:00",
        interface="eth0",
        bpdu_type="Config",
        root_priority=32768,
        bridge_priority=32768,
    )
    assert b.src_mac == "01:80:c2:00:00:00"
    assert b.interface == "eth0"
    assert b.root_priority == 32768
    assert b.bpdu_type == "Config"


def test_parse_bpdu_too_short():
    # Payload shorter than minimum BPDU should return None
    result = _parse_bpdu(b"\x00\x00\x00", "aa:bb:cc:dd:ee:ff", "eth0")
    assert result is None


def test_parse_bpdu_config_bpdu():
    # 35-byte zero payload — minimal 802.1D Config BPDU shape
    payload = bytes(35)
    result = _parse_bpdu(payload, "00:11:22:33:44:55", "eth0")
    assert result is None or isinstance(result, BPDUInfo)


def test_scan_no_scapy_calls_error(monkeypatch):
    monkeypatch.setattr("modules.stp_detector.SCAPY_AVAILABLE", False)
    import modules.stp_detector as m
    errors = []
    result = m.scan(gateway_mac=None, on_bpdu=lambda b: None, on_error=errors.append, duration=0)
    assert isinstance(result, dict)
    assert len(errors) == 1
    assert "Scapy" in errors[0] or "scapy" in errors[0].lower()
