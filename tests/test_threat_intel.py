"""Tests for modules/threat_intel.py — threat intelligence feed."""
import json
import pytest
from modules.threat_intel import (
    ThreatEntry, ThreatIntelDB, _is_public_ip,
    _parse_feodo_json, _parse_urlhaus_text, _parse_plain_ip_list,
)


def test_import():
    import modules.threat_intel as m
    assert hasattr(m, "ThreatEntry")
    assert hasattr(m, "ThreatIntelDB")
    assert hasattr(m, "_is_public_ip")
    assert hasattr(m, "refresh_from_feeds")


def test_threat_entry_fields():
    e = ThreatEntry(
        indicator="198.51.100.1",
        itype="ip",
        categories=["botnet"],
        source="feodo",
        confidence=85,
        last_seen="2024-01-01",
    )
    assert e.indicator == "198.51.100.1"
    assert e.source == "feodo"
    assert "botnet" in e.categories
    assert e.confidence == 85


def test_is_public_ip_rfc1918():
    assert _is_public_ip("192.168.1.1") is False
    assert _is_public_ip("10.0.0.1") is False
    assert _is_public_ip("172.16.0.1") is False


def test_is_public_ip_loopback():
    assert _is_public_ip("127.0.0.1") is False


def test_is_public_ip_public():
    assert _is_public_ip("1.1.1.1") is True
    assert _is_public_ip("8.8.4.4") is True


def test_parse_feodo_json_valid():
    # Feodo feed is a flat JSON array (not nested under "blocklist")
    data = json.dumps([
        {"ip_address": "1.2.3.4", "malware": "Emotet", "last_online": "2024-01-01", "status": "online"}
    ]).encode()
    entries = _parse_feodo_json(data)
    assert len(entries) >= 1
    assert any(e.indicator == "1.2.3.4" for e in entries)


def test_parse_feodo_json_invalid():
    entries = _parse_feodo_json(b"not json")
    assert entries == []


def test_parse_urlhaus_text_returns_list():
    data = b"# comment\n2024-01-01,http://1.2.3.4/malware,online,phishing,\n"
    entries = _parse_urlhaus_text(data)
    assert isinstance(entries, list)


def test_parse_plain_ip_list():
    data = b"# comment\n1.2.3.4\n5.6.7.8\n"
    entries = _parse_plain_ip_list(data, "test_source", ["malware"], 75)
    assert len(entries) == 2
    indicators = {e.indicator for e in entries}
    assert "1.2.3.4" in indicators
    assert "5.6.7.8" in indicators


def test_plain_ip_list_parses_ips():
    # _parse_plain_ip_list parses all IPs; RFC1918 filtering happens at query time
    data = b"1.2.3.4\n5.6.7.8\n"
    entries = _parse_plain_ip_list(data, "test", [], 50)
    indicators = {e.indicator for e in entries}
    assert "1.2.3.4" in indicators
    assert "5.6.7.8" in indicators


def test_threat_intel_db_empty():
    db = ThreatIntelDB()
    assert db.check_ip("1.2.3.4") is None


def test_threat_intel_db_from_entries():
    entry = ThreatEntry(
        indicator="1.2.3.4", itype="ip", categories=["botnet"],
        source="feodo", confidence=90, last_seen="2024",
    )
    db = ThreatIntelDB.from_entries([entry])
    result = db.check_ip("1.2.3.4")
    assert result is not None
    assert result.indicator == "1.2.3.4"


def test_threat_intel_db_miss():
    entry = ThreatEntry(
        indicator="1.2.3.4", itype="ip", categories=[],
        source="feodo", confidence=50, last_seen="",
    )
    db = ThreatIntelDB.from_entries([entry])
    assert db.check_ip("5.5.5.5") is None


def test_threat_intel_db_size():
    entries = [
        ThreatEntry(indicator=f"1.2.3.{i}", itype="ip", categories=[], source="test", confidence=50, last_seen="")
        for i in range(10)
    ]
    db = ThreatIntelDB.from_entries(entries)
    assert len(db) == 10
