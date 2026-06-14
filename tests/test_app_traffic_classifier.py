"""
tests/test_app_traffic_classifier.py — Unit tests for app_traffic_classifier.

Covers:
  - Module import
  - classify_port() well-known port heuristics
  - classify_port() fallback for unknown ports
  - AppFlowEntry / AppHostSnapshot / AppTrafficSnapshot dataclasses
  - AppHostSnapshot.category_totals()
  - AppTrafficSniffer.snapshot() with synthetic flow data
  - CATEGORY_ORDER completeness (every key in APP_CATEGORY_COLORS is listed)
"""

import pytest

from modules.app_traffic_classifier import (
    AppFlowEntry,
    AppHostSnapshot,
    AppTrafficSnapshot,
    AppTrafficSniffer,
    CATEGORY_ORDER,
    classify_port,
)
from modules.colours import APP_CATEGORY_COLORS  # type: ignore[attr-defined]


# ── Import smoke ──────────────────────────────────────────────────────────────

def test_import():
    assert classify_port is not None


# ── classify_port ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("proto,port,expected_cat,expected_app", [
    ("tcp", 80,    "Web",       "HTTP"),
    ("tcp", 443,   "Web",       "HTTPS"),
    ("udp", 53,    "DNS",       "DNS"),
    ("tcp", 22,    "SSH/Admin", "SSH"),
    ("tcp", 3389,  "SSH/Admin", "RDP"),
    ("tcp", 1935,  "Streaming", "RTMP"),
    ("tcp", 32400, "Streaming", "Plex"),
    ("udp", 1194,  "VPN",       "OpenVPN"),
    ("udp", 51820, "VPN",       "WireGuard"),
    ("tcp", 6881,  "P2P",       "BitTorrent"),
    ("tcp", 445,   "File Share", "SMB"),
    ("tcp", 3306,  "Database",  "MySQL"),
    ("tcp", 1883,  "IoT",       "MQTT"),
    ("udp", 123,   "System",    "NTP"),
    ("udp", 5353,  "Discovery", "mDNS"),
    ("udp", 5060,  "VoIP",      "SIP"),
    ("udp", 3074,  "Gaming",    "Xbox"),
    ("udp", 27015, "Gaming",    "Steam"),
    ("tcp", 25,    "Email",     "SMTP"),
    ("tcp", 993,   "Email",     "IMAPS"),
])
def test_classify_port_known(proto, port, expected_cat, expected_app):
    cat, app = classify_port(proto, port)
    assert cat == expected_cat
    assert app == expected_app


def test_classify_port_unknown():
    cat, app = classify_port("tcp", 12345)
    assert cat == "Other"
    assert "12345" in app


def test_classify_port_case_insensitive():
    cat, _ = classify_port("TCP", 80)
    assert cat == "Web"
    cat, _ = classify_port("UDP", 53)
    assert cat == "DNS"


# ── CATEGORY_ORDER completeness ───────────────────────────────────────────────

def test_category_order_covers_all_colors():
    for cat in APP_CATEGORY_COLORS:
        assert cat in CATEGORY_ORDER, f"Category '{cat}' missing from CATEGORY_ORDER"


def test_category_order_no_duplicates():
    assert len(CATEGORY_ORDER) == len(set(CATEGORY_ORDER))


# ── Data classes ──────────────────────────────────────────────────────────────

def test_app_flow_entry_defaults():
    f = AppFlowEntry(mac="aa:bb:cc:dd:ee:ff", category="Web", app="HTTPS")
    assert f.bytes_total == 0
    assert f.label == ""


def test_app_host_snapshot_category_totals():
    flows = [
        AppFlowEntry(mac="m1", category="Web",  app="HTTPS", bytes_total=1000),
        AppFlowEntry(mac="m1", category="Web",  app="HTTP",  bytes_total=500),
        AppFlowEntry(mac="m1", category="DNS",  app="DNS",   bytes_total=200),
    ]
    host = AppHostSnapshot(mac="m1", label="Laptop", flows=flows, total_bytes=1700)
    totals = host.category_totals()
    assert totals["Web"] == 1500
    assert totals["DNS"] == 200
    assert "Other" not in totals


def test_app_traffic_snapshot_top_host():
    h1 = AppHostSnapshot(mac="m1", label="A", total_bytes=100)
    h2 = AppHostSnapshot(mac="m2", label="B", total_bytes=999)
    snap = AppTrafficSnapshot(hosts=[h1, h2])
    assert snap.top_host.label == "B"


def test_app_traffic_snapshot_empty():
    snap = AppTrafficSnapshot(hosts=[])
    assert snap.top_host is None


# ── AppTrafficSniffer (no Scapy required) ────────────────────────────────────

def test_sniffer_snapshot_empty():
    sniffer = AppTrafficSniffer()
    snap = sniffer.snapshot(window_s=10.0, label_map={})
    assert isinstance(snap, AppTrafficSnapshot)
    assert snap.hosts == []


def test_sniffer_snapshot_synthetic():
    """Inject synthetic flow data directly into the sniffer's internal dict."""
    sniffer = AppTrafficSniffer()
    mac = "aa:bb:cc:dd:ee:01"
    # Simulate what _handle() would populate
    sniffer._flows[mac] = {
        ("Web",  "HTTPS"): 10_000,
        ("DNS",  "DNS"):   2_000,
        ("Other", "Port 12345"): 500,
    }

    snap = sniffer.snapshot(window_s=10.0, label_map={mac: "test-device"})
    assert len(snap.hosts) == 1
    host = snap.hosts[0]
    assert host.mac == mac
    assert host.label == "test-device"
    assert host.total_bytes == 12_500
    totals = host.category_totals()
    assert totals["Web"] == 10_000
    assert totals["DNS"] == 2_000

    # After snapshot, internal state must be cleared
    assert sniffer._flows == {}


def test_sniffer_snapshot_label_fallback():
    sniffer = AppTrafficSniffer()
    mac = "bb:bb:bb:bb:bb:bb"
    sniffer._flows[mac] = {("Web", "HTTP"): 1000}
    snap = sniffer.snapshot(window_s=5.0, label_map={})
    assert snap.hosts[0].label == mac   # no label → MAC used as fallback


def test_sniffer_snapshot_zero_bytes_excluded():
    sniffer = AppTrafficSniffer()
    mac = "cc:cc:cc:cc:cc:cc"
    sniffer._flows[mac] = {("Web", "HTTP"): 0}   # zero bytes → host excluded
    snap = sniffer.snapshot(window_s=10.0, label_map={})
    assert snap.hosts == []


def test_sniffer_snapshot_sorted_by_bytes():
    sniffer = AppTrafficSniffer()
    sniffer._flows["aa:aa:aa:aa:aa:01"] = {("Web", "HTTP"): 500}
    sniffer._flows["aa:aa:aa:aa:aa:02"] = {("DNS", "DNS"): 5000}
    snap = sniffer.snapshot(window_s=10.0, label_map={})
    assert snap.hosts[0].total_bytes == 5000
    assert snap.hosts[1].total_bytes == 500


# ── Scaling guard ─────────────────────────────────────────────────────────────

def test_classify_port_scaling():
    """classify_port must run in constant time — O(1) dict lookup."""
    import statistics
    import time

    def run_batch(n: int) -> float:
        t0 = time.perf_counter()
        for i in range(n):
            classify_port("tcp", i % 65535)
        return time.perf_counter() - t0

    t_small = statistics.median(run_batch(500) for _ in range(3))
    t_large = statistics.median(run_batch(5000) for _ in range(3))
    if t_small < 1e-7:
        return   # too fast to measure
    ratio = t_large / t_small
    assert ratio < 15, f"classify_port scaling regression: {ratio:.1f}x for 10x input"
