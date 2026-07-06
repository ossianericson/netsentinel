"""Tests for modules/stp_detector.py — STP/BPDU rogue bridge detector."""
from modules.stp_detector import SCAPY_AVAILABLE, BPDUInfo, _parse_bpdu


def test_import():
    from modules import stp_detector as m
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
    from modules import stp_detector as m
    errors = []
    result = m.scan(gateway_mac=None, on_bpdu=lambda b: None, on_error=errors.append, duration=0)
    assert isinstance(result, dict)
    assert len(errors) == 1
    assert "Scapy" in errors[0] or "scapy" in errors[0].lower()


# ── _parse_bpdu analysis-logic tests ─────────────────────────────────────────

def test_parse_bpdu_invalid_dsap_ssap():
    payload = bytes([0x00, 0x00, 0x03]) + bytes(35)
    assert _parse_bpdu(payload, "aa:bb:cc:dd:ee:ff", "eth0") is None


def test_parse_bpdu_bpdu_too_short_after_llc():
    # Valid LLC but only 3 bytes of BPDU data — need ≥4 to read type
    payload = bytes([0x42, 0x42, 0x03, 0x00, 0x00, 0x00])
    assert _parse_bpdu(payload, "aa:bb:cc:dd:ee:ff", "eth0") is None


def test_parse_bpdu_tcn_type():
    """TCN BPDU (type=0x80) — short payload returns BPDUInfo with type set."""
    llc = bytes([0x42, 0x42, 0x03])
    bpdu = bytes([0x00, 0x00, 0x00, 0x80])   # proto=0, ver=0, type=0x80=TCN
    result = _parse_bpdu(llc + bpdu, "00:11:22:33:44:55", "eth0")
    assert result is not None
    assert result.bpdu_type == "TCN"
    assert result.src_mac == "00:11:22:33:44:55"
    assert result.interface == "eth0"


def test_parse_bpdu_config_full_fields():
    """Config BPDU with crafted data — verify all fields are parsed correctly."""
    import struct

    llc = bytes([0x42, 0x42, 0x03])
    bpdu = bytearray(35)
    # offset 0-3: protocol ID (0x0000), version (0x00), type (0x00=Config)
    bpdu[0:4] = b"\x00\x00\x00\x00"
    # offset 5-6: root priority = 32768
    struct.pack_into(">H", bpdu, 5, 32768)
    # offset 7-12: root MAC = 00:11:22:33:44:55
    bpdu[7:13] = bytes([0x00, 0x11, 0x22, 0x33, 0x44, 0x55])
    # offset 13-16: root path cost = 0
    struct.pack_into(">I", bpdu, 13, 0)
    # offset 17-18: bridge priority = 32768
    struct.pack_into(">H", bpdu, 17, 32768)
    # offset 19-24: bridge MAC = aa:bb:cc:dd:ee:ff
    bpdu[19:25] = bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF])
    # offset 29-30: max_age = 0x1400 → 5120 / 256 = 20.0 seconds
    struct.pack_into(">H", bpdu, 29, 0x1400)
    # offset 31-32: hello_time = 0x0200 → 512 / 256 = 2.0 seconds
    struct.pack_into(">H", bpdu, 31, 0x0200)
    # offset 33-34: forward_delay = 0x0F00 → 3840 / 256 = 15.0 seconds
    struct.pack_into(">H", bpdu, 33, 0x0F00)

    result = _parse_bpdu(llc + bytes(bpdu), "de:ad:be:ef:00:01", "eth1")

    assert result is not None
    assert isinstance(result, BPDUInfo)
    assert result.bpdu_type == "Config"
    assert result.root_priority == 32768
    assert result.root_mac == "00:11:22:33:44:55"
    assert result.bridge_priority == 32768
    assert result.bridge_mac == "aa:bb:cc:dd:ee:ff"
    assert abs(result.max_age - 20.0) < 0.01
    assert abs(result.hello_time - 2.0) < 0.01
    assert abs(result.forward_delay - 15.0) < 0.01
    assert result.src_mac == "de:ad:be:ef:00:01"
    assert result.interface == "eth1"


def test_parse_bpdu_unknown_type():
    """Unrecognised BPDU type code produces a descriptive type string."""
    llc = bytes([0x42, 0x42, 0x03])
    bpdu = bytes([0x00, 0x00, 0x00, 0xFF])   # type 0xFF — unknown
    result = _parse_bpdu(llc + bpdu, "aa:bb:cc:00:00:01", "eth0")
    assert result is not None
    assert "Unknown" in result.bpdu_type or "0xff" in result.bpdu_type


def test_parse_bpdu_config_not_rogue_by_default():
    """is_rogue must default to False; rogue detection happens in STPSniffer."""
    import struct
    llc = bytes([0x42, 0x42, 0x03])
    bpdu = bytearray(35)
    bpdu[3] = 0x00
    struct.pack_into(">H", bpdu, 5, 4096)
    bpdu[7:13] = bytes([0x00, 0x11, 0x22, 0x33, 0x44, 0x55])
    result = _parse_bpdu(llc + bytes(bpdu), "aa:bb:cc:dd:ee:ff", "eth0")
    assert result is not None
    assert result.is_rogue is False
