"""Tests for device_classifier module."""
from modules.device_classifier import classify


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
