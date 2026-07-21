"""
tests/test_scan_scaling.py — Part 2/L9 standing scaling guard.

A 1,000-device fixture used as a benchmark across the hot paths named in the
large/corporate/VPN network plan: rogue_device.scan() (skeleton + resolution
phases), the M1 device table population (streaming upsert), topology build
(collapse_to_segments/build_cytoscape_elements), name_resolver.resolve_batch
orchestration overhead, and network_benchmark.grade().

Run with: pytest -m benchmark tests/test_scan_scaling.py -v

RULE-PERF1 (ResizeToContents trap): NOT re-tested here — tests/test_table_resize_mode.py
already does a blanket ui/-wide scan that covers the M1/device tables, so a
second targeted check here would be redundant.
"""
from __future__ import annotations

import json
import statistics
import time

import pytest

try:
    from PyQt6.QtWidgets import QTableWidget
    _HAS_QT = True
except ImportError:
    _HAS_QT = False


def _median_s(fn, repeats: int = 5) -> float:
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return statistics.median(times)


def _assert_scales(t_small: float, t_large: float, factor: int = 10, threshold: float = 15.0):
    if t_small < 1e-7:
        pytest.skip("below measurement threshold")
    ratio = t_large / t_small
    assert ratio < threshold, (
        f"Scaling ratio {ratio:.1f}x for {factor}x input suggests O(n^2) regression "
        f"(t_small={t_small:.6f}s, t_large={t_large:.6f}s)"
    )


# ── rogue_device.scan() — Phase 1 skeleton + Phase 2 resolution ──────────────

def _synthetic_arp_entries(n: int):
    return [(f"192.168.{i // 254}.{i % 254 + 1}", f"aa:bb:{i:04x}"[:17].ljust(17, "0"))
            for i in range(n)]


@pytest.mark.benchmark
def test_rogue_device_scan_scaling(tmp_path, monkeypatch):
    """rogue_device.scan()'s ARP-table pass must scale ~linearly with device
    count -- both the Part 2/L7 skeleton phase and the resolution phase."""
    from modules.rogue_device import scan

    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))

    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: "192.168.0.1")
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)
    monkeypatch.setattr("modules.rogue_device._resolve_name", lambda ip: None)
    monkeypatch.setattr("modules.name_resolver.resolve_batch", lambda entries, **kw: {})

    def _run(n):
        entries = _synthetic_arp_entries(n)
        monkeypatch.setattr("modules.rogue_device._get_arp_table", lambda e=entries: e)
        scan(offenders_path=offenders)

    t_small = _median_s(lambda: _run(100), repeats=3)
    t_large = _median_s(lambda: _run(1000), repeats=3)

    _assert_scales(t_small, t_large)


# ── M1 device table streaming upsert (ui/scan_wiring.py) ─────────────────────

@pytest.mark.benchmark
@pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")
def test_m1_stream_device_row_scaling():
    """_m1_stream_device_row() upserts by IP into a dict (Part 2/L7) -- must
    stay O(1) per call, not degrade into an O(n) table scan per device as the
    device count grows."""
    from ui.scan_wiring import ScanResultMixin

    class _Stub:
        pass

    def _run(n):
        stub = _Stub()
        stub._m1_table = QTableWidget(0, 9)
        stub._m1_stream_rows = {}
        for i in range(n):
            ScanResultMixin._m1_stream_device_row(stub, {
                "ip": f"192.168.{i // 254}.{i % 254 + 1}",
                "name": "", "mac": f"aa:bb:{i:04x}",
                "vendor": "Unknown", "risk_level": "CLEAN",
                "type": "", "verdict": "Scanning…",
            })

    t_small = _median_s(lambda: _run(100), repeats=3)
    t_large = _median_s(lambda: _run(1000), repeats=3)

    _assert_scales(t_small, t_large)


# ── Topology build (modules/topology_cytoscape.py) ───────────────────────────

def _topo_device(ip: str, mac: str) -> dict:
    return {"ip": ip, "mac": mac, "risk_level": "CLEAN", "hostname": "", "vendor": ""}


@pytest.mark.benchmark
def test_build_cytoscape_elements_scaling_to_1000():
    """Extends the existing 20-vs-200 precedent to 1000 devices -- the scale a
    real corporate ARP table can reach."""
    from modules.topology_cytoscape import build_cytoscape_elements

    def _devices(n):
        return [_topo_device(f"192.168.{i // 254}.{i % 254 + 1}", f"aa{i:06x}") for i in range(n)]

    small = _devices(100)
    large = _devices(1000)

    t_small = _median_s(lambda: build_cytoscape_elements(devices=small, gateway_ip="192.168.0.1"), repeats=3)
    t_large = _median_s(lambda: build_cytoscape_elements(devices=large, gateway_ip="192.168.0.1"), repeats=3)

    _assert_scales(t_small, t_large)


@pytest.mark.benchmark
def test_collapse_to_segments_scaling_to_1000():
    """collapse_to_segments() (Part 1/D) is what keeps a 1000-device network
    map readable -- must stay cheap even at that scale, not just correct.
    Both sizes must sit ABOVE _COLLAPSE_THRESHOLD_DEFAULT (150): comparing a
    below-threshold (near-instant early return) size against an above-threshold
    one would measure the threshold branch, not this function's scaling.

    Segment count is held FIXED (4) across both sizes -- classify_device_segment()
    is O(segments) per device, so letting segment count grow along with device
    count (as a naive "one /24 per 254 devices" IP scheme would) confounds two
    different variables and produces a misleadingly steep ratio that has
    nothing to do with device-count scaling. A real corporate network's VLAN/
    segment count doesn't scale with host count either."""
    from modules.topology_cytoscape import collapse_to_segments

    _NUM_SEGMENTS = 4

    def _devices(n):
        return [
            _topo_device(f"192.168.{i % _NUM_SEGMENTS}.{(i // _NUM_SEGMENTS) % 254 + 1}", f"aa{i:06x}")
            for i in range(n)
        ]

    small = _devices(200)
    large = _devices(2000)

    t_small = _median_s(lambda: collapse_to_segments(small, gateway_ip="192.168.0.1"), repeats=3)
    t_large = _median_s(lambda: collapse_to_segments(large, gateway_ip="192.168.0.1"), repeats=3)

    _assert_scales(t_small, t_large)


# ── name_resolver.resolve_batch orchestration overhead ───────────────────────

@pytest.mark.benchmark
def test_resolve_batch_orchestration_scaling(monkeypatch):
    """Isolates resolve_batch()'s own dispatch/bookkeeping overhead (dict
    building, lock, parallel_map dispatch) from real probe network variance by
    mocking resolve() to return instantly -- the shared probe pool (Part 2/L2b)
    is a fixed-size 32 regardless of batch size, so orchestration cost must
    scale with device count only, not blow up with it."""
    from modules.name_resolver import resolve_batch, ResolvedName

    monkeypatch.setattr(
        "modules.name_resolver.resolve",
        lambda ip, mac="", **kw: ResolvedName(ip=ip, hostname=""),
    )

    def _devices(n):
        return [{"ip": f"192.168.{i // 254}.{i % 254 + 1}", "mac": f"aa:bb:{i:04x}"} for i in range(n)]

    small = _devices(100)
    large = _devices(1000)

    t_small = _median_s(lambda: resolve_batch(small), repeats=3)
    t_large = _median_s(lambda: resolve_batch(large), repeats=3)

    _assert_scales(t_small, t_large)


# ── network_benchmark.grade() ─────────────────────────────────────────────────

@pytest.mark.benchmark
def test_grade_scaling_with_large_m1_result():
    """grade() only reads m1_result['high_risk_count'] -- it must never start
    iterating the full device list, so cost should be flat (not just linear)
    regardless of device count. Locks in the current O(1) behaviour as a
    regression guard."""
    from modules.network_benchmark import grade

    def _m1_result(n):
        return {
            "devices": [_topo_device(f"192.168.{i // 254}.{i % 254 + 1}", f"aa{i:06x}") for i in range(n)],
            "high_risk_count": 3,
            "total_count": n,
        }

    small = _m1_result(100)
    large = _m1_result(1000)

    t_small = _median_s(lambda: grade(m1_result=small), repeats=5)
    t_large = _median_s(lambda: grade(m1_result=large), repeats=5)

    _assert_scales(t_small, t_large, threshold=5.0)
