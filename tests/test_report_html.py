"""Tests for modules/report_html.py — HTML generation helpers."""

from modules.report_html import (
    generate_html, _badge, _module1_html, _module2_html,
    _network_info_html, _CSS,
)


def test_css_is_nonempty_string():
    assert isinstance(_CSS, str)
    assert len(_CSS) > 100


def test_badge_returns_span():
    b = _badge("HIGH")
    assert '<span class="badge HIGH">' in b


def test_badge_normalises_case():
    b = _badge("high")
    assert "HIGH" in b


def test_badge_unknown_default():
    b = _badge("")
    assert "UNKNOWN" in b


def test_generate_html_returns_html():
    result = generate_html()
    assert "<!DOCTYPE html>" in result
    assert "<html" in result
    assert "NetSentinel" in result


def test_generate_html_embeds_verdict():
    result = generate_html(overall_verdict="All good", overall_level="CLEAN")
    assert "All good" in result


def test_generate_html_verdict_levels():
    for level, css_class in [("HIGH", "red"), ("MEDIUM", "amber"), ("CLEAN", "green")]:
        result = generate_html(overall_level=level)
        assert css_class in result


def test_module1_html_no_data():
    out = _module1_html(None)
    assert "not run" in out.lower()


def test_module1_html_empty_devices():
    out = _module1_html({"devices": []})
    assert "No devices" in out


def test_module1_html_with_device():
    out = _module1_html({"devices": [
        {"ip": "192.168.1.1", "mac": "aa:bb:cc", "vendor": "Cisco",
         "risk_level": "LOW", "verdict": "OK", "remediation": ""},
    ]})
    assert "192.168.1.1" in out
    assert "Cisco" in out


def test_module2_html_no_bpdus():
    out = _module2_html({"bpdus": []})
    assert "No BPDU" in out


def test_network_info_html_no_data():
    out = _network_info_html(None)
    assert "not collected" in out.lower()


def test_network_info_html_with_data():
    out = _network_info_html({
        "local_ips": [{"ip": "192.168.1.10", "adapter": "eth0"}],
        "gateway": "192.168.1.1",
        "dns_servers": ["8.8.8.8"],
        "adapters": [],
    })
    assert "192.168.1.10" in out
    assert "8.8.8.8" in out


def test_generate_html_importable_from_report_exporter():
    from modules.report_exporter import generate_html as ghtml
    assert ghtml is generate_html
