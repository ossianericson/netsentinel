"""
Tests for modules/net_doc_generator.py
"""
import datetime


from modules.net_doc_generator import (
    generate_network_doc,
    _e, _badge, _section,
    _inventory_section, _ports_section, _certs_section,
)


# ── Helper functions ──────────────────────────────────────────────────────────

def test_e_escapes_html():
    assert "&amp;" in _e("a&b")
    assert "&lt;" in _e("<tag>")
    assert _e(None) == ""


def test_badge_known_levels():
    for level in ("HIGH", "MEDIUM", "LOW", "CLEAN", "UNKNOWN"):
        html = _badge(level)
        assert level in html
        assert 'class="badge' in html


def test_badge_lowercases_normalised():
    html = _badge("high")
    assert "HIGH" in html


def test_section_structure():
    body = "<p>hello</p>"
    html = _section("My Title", body)
    assert "MY TITLE" in html or "My Title" in html
    assert body in html
    assert 'class="section' in html


# ── Section generators ────────────────────────────────────────────────────────

def test_inventory_section_empty():
    html = _inventory_section([])
    assert "No devices" in html


def test_inventory_section_with_data():
    devices = [
        {"ip": "10.0.0.1", "mac": "AA:BB:CC:DD:EE:FF", "hostname": "router",
         "vendor": "Cisco", "os": "IOS", "role": "gateway", "risk_level": "CLEAN"},
        {"ip": "10.0.0.2", "mac": "11:22:33:44:55:66", "hostname": "pc",
         "vendor": "Dell", "os": "Windows 11", "role": "workstation", "risk_level": "LOW"},
    ]
    html = _inventory_section(devices)
    assert "10.0.0.1" in html
    assert "AA:BB:CC:DD:EE:FF" in html
    assert "router" in html
    assert "CLEAN" in html
    assert "2 devices" in html


def test_ports_section_empty():
    html = _ports_section({})
    assert "No port scan data" in html


def test_ports_section_with_data():
    port_data = {
        "10.0.0.1": [
            {"port": 80, "protocol": "tcp", "service": "http", "state": "open"},
            {"port": 443, "protocol": "tcp", "service": "https", "state": "open"},
        ],
        "10.0.0.2": [
            {"port": 22, "protocol": "tcp", "service": "ssh", "state": "open"},
        ],
    }
    html = _ports_section(port_data)
    assert "10.0.0.1" in html
    assert "443" in html
    assert "3 open port" in html
    assert "2 hosts" in html


def test_certs_section_empty():
    html = _certs_section([])
    assert "No certificate data" in html


def test_certs_section_valid():
    future = (datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(days=90)).isoformat()
    certs = [
        {"host": "10.0.0.1", "cn": "example.com",
         "issuer": "Let's Encrypt", "expiry": future},
    ]
    html = _certs_section(certs)
    assert "example.com" in html
    assert "10.0.0.1" in html
    assert "Valid" in html or "left" in html


def test_certs_section_expired():
    past = (datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=5)).isoformat()
    certs = [{"host": "1.2.3.4", "cn": "old.cert", "issuer": "CA", "expiry": past}]
    html = _certs_section(certs)
    assert "Expired" in html


def test_certs_section_expiring_soon():
    soon = (datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(days=10)).isoformat()
    certs = [{"host": "1.2.3.4", "cn": "soon.cert", "issuer": "CA", "expiry": soon}]
    html = _certs_section(certs)
    assert "Expires" in html or "warn" in html


# ── generate_network_doc ──────────────────────────────────────────────────────

def test_generate_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.net_doc_generator.get_app_data_dir", lambda: tmp_path)
    out = generate_network_doc(devices=[], port_data={}, cert_data=[])
    assert out.exists()
    assert out.suffix == ".html"


def test_generate_html_structure(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.net_doc_generator.get_app_data_dir", lambda: tmp_path)
    devices = [{"ip": "192.168.1.1", "mac": "AA:BB:CC:DD:EE:FF",
                "hostname": "gw", "vendor": "Vendor", "risk_level": "CLEAN"}]
    out = generate_network_doc(devices=devices)
    content = out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "Network Documentation" in content
    assert "192.168.1.1" in content
    assert "AA:BB:CC:DD:EE:FF" in content


def test_generate_with_ports(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.net_doc_generator.get_app_data_dir", lambda: tmp_path)
    port_data = {"192.168.1.1": [{"port": 80, "protocol": "tcp", "service": "http", "state": "open"}]}
    out = generate_network_doc(devices=[], port_data=port_data)
    content = out.read_text(encoding="utf-8")
    assert "80" in content
    assert "http" in content


def test_generate_with_certs(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.net_doc_generator.get_app_data_dir", lambda: tmp_path)
    future = (datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(days=180)).isoformat()
    certs = [{"host": "10.0.0.1", "cn": "test.local", "issuer": "CA", "expiry": future}]
    out = generate_network_doc(devices=[], cert_data=certs)
    content = out.read_text(encoding="utf-8")
    assert "test.local" in content


def test_generate_custom_title(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.net_doc_generator.get_app_data_dir", lambda: tmp_path)
    out = generate_network_doc(title="My Custom Title")
    assert "My Custom Title" in out.read_text(encoding="utf-8")


def test_generate_missing_topology_png_graceful(tmp_path, monkeypatch):
    """topology_png pointing at a nonexistent file should not raise."""
    monkeypatch.setattr("modules.net_doc_generator.get_app_data_dir", lambda: tmp_path)
    bogus = tmp_path / "does_not_exist.png"
    out = generate_network_doc(topology_png=bogus)
    assert out.exists()


def test_generate_returns_path_in_reports_subdir(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.net_doc_generator.get_app_data_dir", lambda: tmp_path)
    out = generate_network_doc()
    assert out.parent.name == "reports"


def test_generate_dataclass_devices(tmp_path, monkeypatch):
    """Accepts dataclass-style objects as well as plain dicts."""
    monkeypatch.setattr("modules.net_doc_generator.get_app_data_dir", lambda: tmp_path)
    from dataclasses import dataclass
    @dataclass
    class D:
        ip: str = "1.2.3.4"
        mac: str = "AA:BB:CC:DD:EE:FF"
        hostname: str = "dc"
        vendor: str = "HP"
        os: str = ""
        role: str = ""
        risk_level: str = "LOW"

    out = generate_network_doc(devices=[D()])
    assert "1.2.3.4" in out.read_text(encoding="utf-8")
