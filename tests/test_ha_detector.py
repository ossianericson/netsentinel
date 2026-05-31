"""Tests for modules/ha_detector.py — Home Automation device detector."""
import pytest
from modules.ha_detector import HaMatch, ha_category, scan


def test_import():
    import modules.ha_detector as m
    assert hasattr(m, "scan")
    assert hasattr(m, "HaMatch")
    assert hasattr(m, "ha_category")


def test_ha_match_fields():
    m = HaMatch(
        ip="192.168.1.50",
        mac="aa:bb:cc:dd:ee:ff",
        ha_type="home_assistant",
        confidence="high",
        detail="port 8123 open",
        label="Home Assistant",
    )
    assert m.ip == "192.168.1.50"
    assert m.ha_type == "home_assistant"
    assert m.confidence == "high"


def test_ha_category_known_types():
    assert ha_category("home_assistant") != ""
    assert ha_category("hue_bridge") != ""
    assert ha_category("mqtt_broker") != ""
    assert ha_category("sonos") != ""


def test_ha_category_unknown_returns_string():
    result = ha_category("nonexistent_type_xyz")
    assert isinstance(result, str)


def test_scan_empty_list():
    result = scan([])
    assert result == []


def test_scan_returns_list():
    result = scan([])
    assert isinstance(result, list)
