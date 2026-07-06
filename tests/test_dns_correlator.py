"""Tests for modules/dns_correlator.py — DNS failure / micro-outage correlator."""
from modules.dns_correlator import (
    PingPoint, DnsPoint, CorrelatorResult, _find_outages, PING_TARGETS, DNS_DOMAINS,
)


def test_import():
    from modules import dns_correlator as m
    assert hasattr(m, "scan")
    assert hasattr(m, "PingPoint")
    assert hasattr(m, "CorrelatorResult")


def test_ping_targets_is_list():
    assert isinstance(PING_TARGETS, list)
    assert len(PING_TARGETS) >= 2


def test_dns_domains_is_list():
    assert isinstance(DNS_DOMAINS, list)
    assert len(DNS_DOMAINS) >= 3


def test_ping_point_fields():
    pt = PingPoint(timestamp=1000.0, target="1.1.1.1", rtt_ms=12.5)
    assert pt.target == "1.1.1.1"
    assert pt.rtt_ms == 12.5
    assert pt.is_timeout is False


def test_ping_point_timeout():
    pt = PingPoint(timestamp=1000.0, target="1.1.1.1", rtt_ms=0.0, is_timeout=True)
    assert pt.is_timeout is True


def test_dns_point_fields():
    pt = DnsPoint(timestamp=2000.0, domain="google.com", rtt_ms=5.0, resolved=True)
    assert pt.domain == "google.com"
    assert pt.resolved is True


def test_correlator_result_defaults():
    r = CorrelatorResult()
    assert r.ping_series == []
    assert r.dns_series == []
    assert r.micro_outages == []
    assert r.plain_verdict == ""


def test_find_outages_empty():
    outages, stp_candidates = _find_outages([])
    assert outages == []
    assert stp_candidates == []


def test_find_outages_no_outage():
    series = [PingPoint(timestamp=float(i), target="1.1.1.1", rtt_ms=5.0) for i in range(10)]
    outages, _ = _find_outages(series)
    assert outages == []


def test_find_outages_detects_gap():
    series = []
    for i in range(5):
        series.append(PingPoint(timestamp=float(i), target="1.1.1.1", rtt_ms=5.0))
    for i in range(5, 10):
        series.append(PingPoint(timestamp=float(i), target="1.1.1.1", rtt_ms=0.0, is_timeout=True))
    for i in range(10, 12):
        series.append(PingPoint(timestamp=float(i), target="1.1.1.1", rtt_ms=5.0))
    outages, _ = _find_outages(series)
    assert len(outages) >= 1
