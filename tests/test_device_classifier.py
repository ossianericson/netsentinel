"""Tests for device_classifier module."""
from modules.device_classifier import (
    ClassificationResult,
    classify,
    classify_with_evidence,
    is_randomized_mac,
)


def test_classify_ip_camera_by_vendor():
    assert classify(vendor="Hikvision Digital Technology", hostname="", open_ports=set()) == "IP Camera"


def test_classify_ip_camera_by_hostname():
    assert classify(vendor="", hostname="ipcam-01", open_ports=set()) == "IP Camera"


def test_classify_nas_by_vendor():
    result = classify(vendor="Synology Incorporated", hostname="", open_ports=set())
    assert "NAS" in result or "File" in result


def test_classify_nas_by_ports():
    result = classify(vendor="Unknown", hostname="", open_ports={445, 548})
    assert "NAS" in result or "File" in result


def test_classify_domain_controller_by_ports():
    result = classify(vendor="Microsoft", hostname="dc01", open_ports={389, 445, 88})
    assert "Domain Controller" in result


def test_classify_printer():
    result = classify(vendor="HP", hostname="printer", open_ports={631, 9100})
    assert "Print" in result


def test_classify_smart_tv_by_hostname():
    result = classify(vendor="Samsung Electronics", hostname="samsung-tv", open_ports=set())
    assert "TV" in result or "Smart" in result


def test_classify_router_by_vendor():
    result = classify(vendor="Cisco Systems", hostname="", open_ports=set())
    assert "Router" in result or "Firewall" in result or "Switch" in result


def test_classify_unknown_returns_string():
    result = classify(vendor="", hostname="", open_ports=set())
    assert isinstance(result, str)
    assert len(result) > 0


def test_classify_accepts_list_ports():
    # open_ports can be a list or set
    result = classify(vendor="Hikvision Digital Technology", hostname="", open_ports=[])
    assert isinstance(result, str)


# ── is_randomized_mac ────────────────────────────────────────────────────────

def test_randomized_mac_detected():
    # U/L bit (0x02) set in first octet → locally administered
    assert is_randomized_mac("02:00:00:00:00:01") is True


def test_randomized_mac_dash_format():
    assert is_randomized_mac("02-00-00-00-00-01") is True


def test_unicast_mac_not_randomized():
    # Real Google OUI — U/L bit clear
    assert is_randomized_mac("f4:f5:d8:aa:bb:cc") is False


def test_randomized_mac_empty_string():
    assert is_randomized_mac("") is False


def test_randomized_mac_condensed_format():
    # 020000000001 — no separators
    assert is_randomized_mac("020000000001") is True


# ── New hostname rules ───────────────────────────────────────────────────────

def test_samsung_galaxy_phone_hostname():
    # SM-G = Galaxy S series phone; no vendor info (unknown OUI)
    result = classify(vendor="", hostname="SM-G991B", open_ports=set())
    assert result == "Android Device"


def test_samsung_galaxy_phone_lowercase():
    result = classify(vendor="", hostname="sm-a525f", open_ports=set())
    assert result == "Android Device"


def test_samsung_galaxy_tab_hostname():
    # SM-T = Galaxy Tab; should be Tablet, not Android Device
    result = classify(vendor="", hostname="SM-T510", open_ports=set())
    assert result == "Tablet"


def test_lg_webos_hostname():
    result = classify(vendor="", hostname="lgwebos-12345", open_ports=set())
    assert result == "Smart TV"


def test_bravia_hostname():
    result = classify(vendor="", hostname="BRAVIA-KD-55X9000", open_ports=set())
    assert result == "Smart TV"


def test_raspberry_pi_hostname():
    result = classify(vendor="", hostname="raspberrypi", open_ports=set())
    assert result == "Single Board Computer"


def test_libreelec_hostname():
    result = classify(vendor="", hostname="LibreELEC-12", open_ports=set())
    assert result == "Single Board Computer"


def test_raspberry_pi_vendor():
    result = classify(vendor="Raspberry Pi Foundation", hostname="", open_ports=set())
    assert result == "Single Board Computer"


def test_ps5_standalone_hostname():
    # Without trailing separator — previously fell through to Unknown Device
    result = classify(vendor="", hostname="PS5", open_ports=set())
    assert result == "Games Console"


def test_google_tv_hostname():
    result = classify(vendor="", hostname="google-tv-living-room", open_ports=set())
    assert result == "Smart TV"


# ── ClassificationResult and classify_with_evidence ─────────────────────────

def test_classification_result_is_dataclass():
    result = classify_with_evidence(vendor="Synology", hostname="diskstation")
    assert isinstance(result, ClassificationResult)


def test_classification_result_has_required_fields():
    result = classify_with_evidence()
    assert hasattr(result, "device_type")
    assert hasattr(result, "vendor")
    assert hasattr(result, "confidence")
    assert hasattr(result, "evidence")
    assert hasattr(result, "mac_randomized")


def test_classification_result_vendor_boosts_confidence():
    # Known vendor match alone should push confidence above 0
    result = classify_with_evidence(vendor="Hikvision Digital Technology")
    assert result.confidence > 0.0
    assert result.device_type == "IP Camera"


def test_classification_result_hostname_evidence_populated():
    result = classify_with_evidence(hostname="raspberrypi")
    assert result.device_type == "Single Board Computer"
    assert any("hostname" in e for e in result.evidence)


def test_classification_result_randomized_mac_flag():
    result = classify_with_evidence(
        vendor="Some Vendor",
        hostname="some-device",
        mac="02:00:00:00:00:01",
    )
    assert result.mac_randomized is True
    assert any("randomized-mac" in e for e in result.evidence)


def test_classification_result_randomized_mac_reduces_confidence():
    normal = classify_with_evidence(vendor="Cisco Systems", hostname="")
    penalised = classify_with_evidence(
        vendor="Cisco Systems", hostname="", mac="02:00:00:00:00:01"
    )
    assert penalised.confidence < normal.confidence


def test_classification_result_unknown_device_zero_confidence():
    result = classify_with_evidence(vendor="", hostname="", open_ports=set())
    assert result.device_type == "Unknown Device"
    assert result.confidence == 0.0


def test_classify_with_evidence_matches_classify():
    # classify_with_evidence must always agree with classify() on device_type
    cases = [
        {"vendor": "Hikvision Digital Technology", "hostname": "", "open_ports": set()},
        {"vendor": "", "hostname": "raspberrypi", "open_ports": set()},
        {"vendor": "Synology Incorporated", "hostname": "", "open_ports": set()},
        {"vendor": "", "hostname": "SM-T510", "open_ports": set()},
    ]
    for kwargs in cases:
        plain = classify(**kwargs)
        rich = classify_with_evidence(**kwargs)
        assert rich.device_type == plain, f"Mismatch for {kwargs}: {rich.device_type!r} != {plain!r}"
