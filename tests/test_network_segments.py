"""Tests for modules/network_segments.py — Sprint 4 (Network Segment / Zone Grouping)."""
from __future__ import annotations

from dataclasses import dataclass

import pytest


# ── Import test ───────────────────────────────────────────────────────────────

def test_import():
    import modules.network_segments as ns
    assert hasattr(ns, "NetworkSegment")
    assert hasattr(ns, "auto_detect_segments")
    assert hasattr(ns, "classify_device_segment")
    assert hasattr(ns, "merge_segments")
    assert hasattr(ns, "SEGMENT_PALETTE")


# ── NetworkSegment dataclass ──────────────────────────────────────────────────

def test_network_segment_defaults():
    from modules.network_segments import NetworkSegment
    seg = NetworkSegment(id=0, name="Test", cidr="192.168.1.0/24", color="#0078D4")
    assert seg.description == ""
    assert seg.auto_created == 0


# ── auto_detect_segments ──────────────────────────────────────────────────────

@dataclass
class _FakeDevice:
    ip: str
    mac: str = "aa:bb:cc:dd:ee:ff"
    hostname: str = ""
    vendor: str = ""
    device_type: str = ""
    risk_level: str = "LOW"


def test_auto_detect_single_subnet():
    from modules.network_segments import auto_detect_segments
    devices = [_FakeDevice("192.168.1.10"), _FakeDevice("192.168.1.20")]
    segs = auto_detect_segments(devices)
    assert len(segs) == 1
    assert segs[0].cidr == "192.168.1.0/24"
    assert segs[0].auto_created == 1
    assert segs[0].id == 0


def test_auto_detect_two_subnets():
    from modules.network_segments import auto_detect_segments
    devices = [
        _FakeDevice("192.168.1.10"),
        _FakeDevice("192.168.1.20"),
        _FakeDevice("10.0.1.5"),
        _FakeDevice("10.0.1.6"),
    ]
    segs = auto_detect_segments(devices)
    cidrs = {s.cidr for s in segs}
    assert "192.168.1.0/24" in cidrs
    assert "10.0.1.0/24" in cidrs


def test_auto_detect_gateway_labels_main():
    from modules.network_segments import auto_detect_segments
    devices = [_FakeDevice("192.168.1.10"), _FakeDevice("192.168.1.1")]
    segs = auto_detect_segments(devices, gateway_ip="192.168.1.1")
    assert len(segs) == 1
    assert "Main Network" in segs[0].name


def test_auto_detect_ignores_invalid_ips():
    from modules.network_segments import auto_detect_segments
    devices = [
        _FakeDevice("192.168.1.10"),
        _FakeDevice("?"),
        _FakeDevice(""),
        _FakeDevice("0.0.0.0"),
    ]
    segs = auto_detect_segments(devices)
    assert len(segs) == 1


def test_auto_detect_palette_cycles():
    from modules.network_segments import auto_detect_segments, SEGMENT_PALETTE
    # Build 9 different /24 subnets to exceed palette length
    devices = [_FakeDevice(f"10.0.{i}.1") for i in range(9)]
    segs = auto_detect_segments(devices)
    assert len(segs) == 9
    colors = [s.color for s in segs]
    # First 8 should match palette; 9th wraps around
    assert colors[0] == SEGMENT_PALETTE[0]
    assert colors[8] == SEGMENT_PALETTE[8 % len(SEGMENT_PALETTE)]


def test_auto_detect_dict_devices():
    from modules.network_segments import auto_detect_segments
    devices = [{"ip": "192.168.2.5"}, {"ip": "192.168.2.6"}]
    segs = auto_detect_segments(devices)
    assert len(segs) == 1
    assert segs[0].cidr == "192.168.2.0/24"


# ── classify_device_segment ───────────────────────────────────────────────────

def test_classify_returns_matching_segment():
    from modules.network_segments import NetworkSegment, classify_device_segment
    segs = [
        NetworkSegment(id=1, name="Main", cidr="192.168.1.0/24", color="#0078D4"),
        NetworkSegment(id=2, name="Guest", cidr="10.0.0.0/24", color="#2E7D32"),
    ]
    result = classify_device_segment("192.168.1.50", segs)
    assert result is not None
    assert result.id == 1


def test_classify_returns_none_for_no_match():
    from modules.network_segments import NetworkSegment, classify_device_segment
    segs = [NetworkSegment(id=1, name="Main", cidr="192.168.1.0/24", color="#0078D4")]
    result = classify_device_segment("10.0.0.5", segs)
    assert result is None


def test_classify_tightest_match():
    from modules.network_segments import NetworkSegment, classify_device_segment
    # /24 is tighter than /16
    segs = [
        NetworkSegment(id=1, name="Wide", cidr="192.168.0.0/16", color="#0078D4"),
        NetworkSegment(id=2, name="Narrow", cidr="192.168.1.0/24", color="#2E7D32"),
    ]
    result = classify_device_segment("192.168.1.5", segs)
    assert result is not None
    assert result.id == 2


def test_classify_empty_ip():
    from modules.network_segments import NetworkSegment, classify_device_segment
    segs = [NetworkSegment(id=1, name="Main", cidr="192.168.1.0/24", color="#0078D4")]
    assert classify_device_segment("", segs) is None
    assert classify_device_segment("invalid", segs) is None


def test_classify_empty_segments():
    from modules.network_segments import classify_device_segment
    assert classify_device_segment("192.168.1.1", []) is None


# ── merge_segments ────────────────────────────────────────────────────────────

def test_merge_prefers_stored_user_defined():
    from modules.network_segments import NetworkSegment, merge_segments
    stored = [NetworkSegment(id=5, name="My LAN", cidr="192.168.1.0/24",
                              color="#FF0000", auto_created=0)]
    detected = [NetworkSegment(id=0, name="Local Network (192.168.1.x)",
                                cidr="192.168.1.0/24", color="#0078D4", auto_created=1)]
    result = merge_segments(detected, stored)
    # stored record wins — no duplicate, user name retained
    cidrs = [s.cidr for s in result]
    assert cidrs.count("192.168.1.0/24") == 1
    names = [s.name for s in result]
    assert "My LAN" in names


def test_merge_appends_new_subnet():
    from modules.network_segments import NetworkSegment, merge_segments
    stored = [NetworkSegment(id=1, name="Main", cidr="192.168.1.0/24",
                              color="#0078D4", auto_created=1)]
    detected = [
        NetworkSegment(id=0, name="Local Network (192.168.1.x)",
                       cidr="192.168.1.0/24", color="#0078D4", auto_created=1),
        NetworkSegment(id=0, name="Internal Network (10.0.1.x)",
                       cidr="10.0.1.0/24", color="#2E7D32", auto_created=1),
    ]
    result = merge_segments(detected, stored)
    cidrs = {s.cidr for s in result}
    assert "192.168.1.0/24" in cidrs
    assert "10.0.1.0/24" in cidrs


# ── Scaling guard ─────────────────────────────────────────────────────────────

import statistics, time as _time


def _median_time(fn, repeats=5):
    times = []
    for _ in range(repeats):
        t0 = _time.perf_counter()
        fn()
        times.append(_time.perf_counter() - t0)
    return statistics.median(times)


@pytest.mark.benchmark
def test_classify_scaling():
    from modules.network_segments import NetworkSegment, classify_device_segment

    def _build(n):
        return [NetworkSegment(id=i, name=f"S{i}", cidr=f"10.{i//256}.{i%256}.0/24",
                               color="#0078D4") for i in range(n)]

    small = _build(10)
    large = _build(100)
    t_s = _median_time(lambda: [classify_device_segment("10.0.5.1", small)])
    t_l = _median_time(lambda: [classify_device_segment("10.0.5.1", large)])
    if t_s < 1e-7:
        pytest.skip("below measurement threshold")
    ratio = t_l / t_s
    assert ratio < 15, f"Scaling ratio {ratio:.1f}x suggests O(n²) regression"
