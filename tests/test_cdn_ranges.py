"""
tests/test_cdn_ranges.py — Unit tests for modules/cdn_ranges.py (S6-2).
"""

from modules.cdn_ranges import cdn_breakdown_label, classify_cdn_ip


def test_import():
    assert classify_cdn_ip is not None


def test_classify_netflix_ip():
    assert classify_cdn_ip("23.246.0.5") == "Netflix"


def test_classify_youtube_ip():
    assert classify_cdn_ip("142.250.1.1") == "YouTube"


def test_classify_unrecognised_ip_returns_none():
    assert classify_cdn_ip("8.8.8.8") is None


def test_classify_none_input():
    assert classify_cdn_ip(None) is None
    assert classify_cdn_ip("") is None


def test_classify_invalid_ip_does_not_raise():
    assert classify_cdn_ip("not-an-ip") is None


def test_classify_ipv6_does_not_raise():
    assert classify_cdn_ip("2001:db8::1") is None


def test_cdn_breakdown_label_formats_percentages():
    label = cdn_breakdown_label({"Netflix": 620, "YouTube": 380})
    assert "Netflix" in label
    assert "YouTube" in label
    assert "62%" in label
    assert "38%" in label


def test_cdn_breakdown_label_empty():
    assert cdn_breakdown_label({}) == ""
