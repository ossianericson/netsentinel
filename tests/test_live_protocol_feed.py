"""Tests for modules/live_protocol_feed.py (Phase A5 — Protocol Visualizer Live Mode).

Pattern-matches tests/test_arp_monitor.py (dataclass/import/graceful-degrade
checks) and tests/test_wifi_monitor_worker.py (real scapy packets via
pytest.importorskip for handler behaviour, rather than hand-rolled stubs).
"""
import time

import pytest

from modules.live_protocol_feed import (
    SCAPY_AVAILABLE,
    LiveFrameEvent,
    LiveProtocolFeed,
)


def test_import():
    from modules import live_protocol_feed as m
    assert hasattr(m, "SCAPY_AVAILABLE")
    assert hasattr(m, "LiveFrameEvent")
    assert hasattr(m, "LiveProtocolFeed")


def test_scapy_available_is_bool():
    assert isinstance(SCAPY_AVAILABLE, bool)


def test_live_frame_event_fields():
    evt = LiveFrameEvent(
        protocol="ARP",
        src_ip="192.168.1.50",
        src_mac="aa:bb:cc:dd:ee:ff",
        dst_ip="192.168.1.1",
        summary="192.168.1.50 is at aa:bb:cc:dd:ee:ff",
        is_reply=True,
        is_broadcast=False,
        ts=1234.5,
    )
    assert evt.protocol == "ARP"
    assert evt.src_ip == "192.168.1.50"
    assert evt.is_reply is True
    assert evt.is_broadcast is False


def test_unsupported_protocol_raises():
    with pytest.raises(ValueError):
        LiveProtocolFeed(protocol="TCP", on_event=lambda e: None, on_error=lambda m: None)


def test_stop_without_start_is_safe():
    feed = LiveProtocolFeed(protocol="ARP", on_event=lambda e: None, on_error=lambda m: None)
    feed.stop()  # must not raise — no sniffer was ever created


def test_start_without_scapy_calls_on_error(monkeypatch):
    monkeypatch.setattr("modules.live_protocol_feed.SCAPY_AVAILABLE", False)
    errors = []
    feed = LiveProtocolFeed(protocol="ARP", on_event=lambda e: None, on_error=errors.append)
    feed.start()
    assert len(errors) == 1
    assert "scapy" in errors[0].lower()


def test_rate_limit_drops_excess_events_in_same_window():
    feed = LiveProtocolFeed(protocol="ARP", on_event=lambda e: None, on_error=lambda m: None)
    results = [feed._rate_limited() for _ in range(6)]
    assert results == [False, False, False, False, True, True]
    assert feed.overflow_count == 2


def test_rate_limit_resets_after_window_elapses():
    feed = LiveProtocolFeed(protocol="ARP", on_event=lambda e: None, on_error=lambda m: None)
    for _ in range(4):
        assert feed._rate_limited() is False
    assert feed._rate_limited() is True
    feed._window_start = time.monotonic() - 1.1  # simulate the 1s window elapsing
    assert feed._rate_limited() is False


def test_arp_handler_emits_normalized_reply_event():
    pytest.importorskip("scapy.all")
    from scapy.all import ARP, Ether

    feed = LiveProtocolFeed(protocol="ARP", on_event=lambda e: events.append(e), on_error=lambda m: None)
    events: list = []
    feed.on_event = events.append
    pkt = Ether(src="aa:bb:cc:dd:ee:ff") / ARP(
        op=2, psrc="192.168.1.50", hwsrc="aa:bb:cc:dd:ee:ff", pdst="192.168.1.1",
    )
    feed._handle_arp(pkt)
    assert len(events) == 1
    evt = events[0]
    assert evt.protocol == "ARP"
    assert evt.src_ip == "192.168.1.50"
    assert evt.src_mac == "aa:bb:cc:dd:ee:ff"
    assert evt.is_reply is True
    assert evt.is_broadcast is False
    assert feed.event_count == 1


def test_arp_handler_flags_gratuitous_as_broadcast():
    pytest.importorskip("scapy.all")
    from scapy.all import ARP, Ether

    events: list = []
    feed = LiveProtocolFeed(protocol="ARP", on_event=events.append, on_error=lambda m: None)
    pkt = Ether(src="11:22:33:44:55:66") / ARP(
        op=1, psrc="192.168.1.77", hwsrc="11:22:33:44:55:66", pdst="192.168.1.1",
    )
    feed._handle_arp(pkt)
    assert len(events) == 1
    assert events[0].is_broadcast is True
    assert events[0].is_reply is False


def test_arp_handler_ignores_non_arp_packet():
    pytest.importorskip("scapy.all")
    from scapy.all import Ether, IP

    events: list = []
    feed = LiveProtocolFeed(protocol="ARP", on_event=events.append, on_error=lambda m: None)
    pkt = Ether() / IP(src="1.2.3.4", dst="5.6.7.8")
    feed._handle_arp(pkt)
    assert events == []


def test_dns_handler_emits_normalized_query_event():
    pytest.importorskip("scapy.all")
    from scapy.all import DNS, DNSQR, IP, UDP, Ether

    events: list = []
    feed = LiveProtocolFeed(protocol="DNS", on_event=events.append, on_error=lambda m: None)
    pkt = (
        Ether(src="aa:bb:cc:dd:ee:ff")
        / IP(src="192.168.1.50", dst="8.8.8.8")
        / UDP(sport=5353, dport=53)
        / DNS(qr=0, qdcount=1, qd=DNSQR(qname="example.com"))
    )
    feed._handle_dns(pkt)
    assert len(events) == 1
    evt = events[0]
    assert evt.protocol == "DNS"
    assert evt.src_ip == "192.168.1.50"
    assert evt.dst_ip == "8.8.8.8"
    assert evt.is_reply is False
    assert evt.summary == "Query for example.com"


def test_dns_handler_emits_normalized_reply_event():
    pytest.importorskip("scapy.all")
    from scapy.all import DNS, DNSQR, IP, UDP, Ether

    events: list = []
    feed = LiveProtocolFeed(protocol="DNS", on_event=events.append, on_error=lambda m: None)
    pkt = (
        Ether()
        / IP(src="8.8.8.8", dst="192.168.1.50")
        / UDP(sport=53, dport=5353)
        / DNS(qr=1, qdcount=1, qd=DNSQR(qname="example.com"))
    )
    feed._handle_dns(pkt)
    assert len(events) == 1
    assert events[0].is_reply is True


def test_dns_handler_ignores_non_dns_packet():
    pytest.importorskip("scapy.all")
    from scapy.all import IP, TCP, Ether

    events: list = []
    feed = LiveProtocolFeed(protocol="DNS", on_event=events.append, on_error=lambda m: None)
    pkt = Ether() / IP(src="1.2.3.4", dst="5.6.7.8") / TCP(sport=1234, dport=443)
    feed._handle_dns(pkt)
    assert events == []
