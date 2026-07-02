"""Tests for modules/topology_snapshot.py — topology change detection."""

import sqlite3
import threading
from datetime import datetime


# ── Import test ───────────────────────────────────────────────────────────────

def test_module_imports():
    from modules.topology_snapshot import (
        TopologySnapshot, TopologyDiff, build_snapshot,
        save_snapshot, load_last_snapshot, diff_snapshots,
    )
    assert TopologySnapshot is not None
    assert TopologyDiff is not None
    assert build_snapshot is not None
    assert save_snapshot is not None
    assert load_last_snapshot is not None
    assert diff_snapshots is not None


# ── TopologySnapshot dataclass ────────────────────────────────────────────────

def test_snapshot_construction():
    from modules.topology_snapshot import TopologySnapshot
    snap = TopologySnapshot(
        timestamp=datetime.now(),
        device_ips=frozenset(["192.168.1.10", "192.168.1.20"]),
        device_macs=frozenset(["aa:bb:cc:dd:ee:ff"]),
        edges=[("192.168.1.1", "192.168.1.10")],
    )
    assert "192.168.1.10" in snap.device_ips
    assert len(snap.edges) == 1


def test_snapshot_empty():
    from modules.topology_snapshot import TopologySnapshot
    snap = TopologySnapshot(
        timestamp=datetime.now(),
        device_ips=frozenset(),
        device_macs=frozenset(),
        edges=[],
    )
    assert snap.device_ips == frozenset()


# ── TopologyDiff dataclass ────────────────────────────────────────────────────

def test_diff_is_empty_when_no_changes():
    from modules.topology_snapshot import TopologyDiff
    d = TopologyDiff()
    assert d.is_empty is True


def test_diff_is_not_empty_with_added():
    from modules.topology_snapshot import TopologyDiff
    d = TopologyDiff(added_ips=["192.168.1.99"])
    assert d.is_empty is False


def test_diff_summary_added():
    from modules.topology_snapshot import TopologyDiff
    d = TopologyDiff(added_ips=["192.168.1.99", "192.168.1.100"])
    assert "2 new" in d.summary


def test_diff_summary_removed():
    from modules.topology_snapshot import TopologyDiff
    d = TopologyDiff(removed_ips=["10.0.0.5"])
    assert "1 gone" in d.summary


def test_diff_summary_both():
    from modules.topology_snapshot import TopologyDiff
    d = TopologyDiff(added_ips=["192.168.1.5"], removed_ips=["192.168.1.99"])
    s = d.summary
    assert "1 new" in s
    assert "1 gone" in s


def test_diff_summary_empty_string_when_no_changes():
    from modules.topology_snapshot import TopologyDiff
    d = TopologyDiff()
    assert d.summary == ""


# ── build_snapshot ────────────────────────────────────────────────────────────

def test_build_snapshot_from_dicts():
    from modules.topology_snapshot import build_snapshot
    devices = [
        {"ip": "192.168.1.10", "mac": "AA:BB:CC:DD:EE:01"},
        {"ip": "192.168.1.20", "mac": "AA:BB:CC:DD:EE:02"},
    ]
    snap = build_snapshot(devices, gateway_ip="192.168.1.1")
    assert "192.168.1.10" in snap.device_ips
    assert "192.168.1.20" in snap.device_ips
    assert ("192.168.1.1", "192.168.1.10") in snap.edges
    assert ("192.168.1.1", "192.168.1.20") in snap.edges


def test_build_snapshot_from_objects():
    from modules.topology_snapshot import build_snapshot

    class _Dev:
        def __init__(self, ip, mac):
            self.ip = ip
            self.mac = mac

    devices = [_Dev("10.0.0.2", "aa:bb:cc:00:00:01")]
    snap = build_snapshot(devices, gateway_ip="10.0.0.1")
    assert "10.0.0.2" in snap.device_ips
    assert ("10.0.0.1", "10.0.0.2") in snap.edges


def test_build_snapshot_filters_noise_ips():
    from modules.topology_snapshot import build_snapshot
    devices = [
        {"ip": "0.0.0.0",         "mac": ""},
        {"ip": "255.255.255.255", "mac": ""},
        {"ip": "?",               "mac": ""},
        {"ip": "192.168.1.5",     "mac": "aa:bb:cc:dd:ee:ff"},
    ]
    snap = build_snapshot(devices)
    assert "192.168.1.5" in snap.device_ips
    assert "0.0.0.0" not in snap.device_ips
    assert "255.255.255.255" not in snap.device_ips
    assert len(snap.device_ips) == 1


def test_build_snapshot_no_gateway():
    from modules.topology_snapshot import build_snapshot
    devices = [{"ip": "192.168.1.10", "mac": ""}]
    snap = build_snapshot(devices, gateway_ip=None)
    assert snap.edges == []


def test_build_snapshot_macs_normalised_lowercase():
    from modules.topology_snapshot import build_snapshot
    devices = [{"ip": "192.168.1.2", "mac": "AA:BB:CC:DD:EE:FF"}]
    snap = build_snapshot(devices)
    assert "aa:bb:cc:dd:ee:ff" in snap.device_macs


# ── diff_snapshots ────────────────────────────────────────────────────────────

def _make_snap(ips, gateway="192.168.1.1"):
    from modules.topology_snapshot import TopologySnapshot
    return TopologySnapshot(
        timestamp=datetime.now(),
        device_ips=frozenset(ips),
        device_macs=frozenset(),
        edges=[(gateway, ip) for ip in ips if ip != gateway],
    )


def test_diff_no_changes():
    from modules.topology_snapshot import diff_snapshots
    s1 = _make_snap(["192.168.1.10", "192.168.1.20"])
    d = diff_snapshots(s1, s1)
    assert d.is_empty


def test_diff_added_device():
    from modules.topology_snapshot import diff_snapshots
    prev = _make_snap(["192.168.1.10"])
    curr = _make_snap(["192.168.1.10", "192.168.1.20"])
    d = diff_snapshots(curr, prev)
    assert "192.168.1.20" in d.added_ips
    assert d.removed_ips == []


def test_diff_removed_device():
    from modules.topology_snapshot import diff_snapshots
    prev = _make_snap(["192.168.1.10", "192.168.1.20"])
    curr = _make_snap(["192.168.1.10"])
    d = diff_snapshots(curr, prev)
    assert "192.168.1.20" in d.removed_ips
    assert d.added_ips == []


def test_diff_added_and_removed():
    from modules.topology_snapshot import diff_snapshots
    prev = _make_snap(["192.168.1.10", "192.168.1.20"])
    curr = _make_snap(["192.168.1.10", "192.168.1.30"])
    d = diff_snapshots(curr, prev)
    assert "192.168.1.30" in d.added_ips
    assert "192.168.1.20" in d.removed_ips


def test_diff_added_edges():
    from modules.topology_snapshot import diff_snapshots
    prev = _make_snap(["192.168.1.10"])
    curr = _make_snap(["192.168.1.10", "192.168.1.11"])
    d = diff_snapshots(curr, prev)
    assert ("192.168.1.1", "192.168.1.11") in d.added_edges


def test_diff_removed_edges():
    from modules.topology_snapshot import diff_snapshots
    prev = _make_snap(["192.168.1.10", "192.168.1.11"])
    curr = _make_snap(["192.168.1.10"])
    d = diff_snapshots(curr, prev)
    assert ("192.168.1.1", "192.168.1.11") in d.removed_edges


# ── save_snapshot / load_last_snapshot (in-memory MetricStore stub) ───────────

class _StubStore:
    """Minimal MetricStore stand-in backed by an in-memory SQLite DB."""

    def __init__(self):
        self._conn = sqlite3.connect(":memory:")
        self._write_lock = threading.Lock()
        self._conn.execute(
            "CREATE TABLE topology_snapshots "
            "(id INTEGER PRIMARY KEY, ts INTEGER NOT NULL, data_json TEXT NOT NULL)"
        )
        self._conn.execute(
            "CREATE INDEX idx_topo_snap_ts ON topology_snapshots(ts DESC)"
        )
        self._conn.commit()

    def _execute_write(self, sql, params):
        with self._write_lock:
            self._conn.execute(sql, params)
            self._conn.commit()

    def _execute_read(self, sql, params=()):
        return self._conn.execute(sql, params).fetchall()

    def save_topology_snapshot(self, ts, data_json, keep=10):
        self._execute_write(
            "INSERT INTO topology_snapshots (ts, data_json) VALUES (?, ?)",
            (ts, data_json),
        )
        self._execute_write(
            "DELETE FROM topology_snapshots WHERE id NOT IN "
            "(SELECT id FROM topology_snapshots ORDER BY ts DESC LIMIT ?)",
            (keep,),
        )

    def get_last_topology_snapshot(self):
        rows = self._execute_read(
            "SELECT ts, data_json FROM topology_snapshots ORDER BY ts DESC LIMIT 1",
        )
        return tuple(rows[0]) if rows else None


def test_save_and_load_round_trip():
    from modules.topology_snapshot import TopologySnapshot, save_snapshot, load_last_snapshot
    store = _StubStore()
    snap = TopologySnapshot(
        timestamp=datetime(2025, 1, 15, 12, 0, 0),
        device_ips=frozenset(["10.0.0.2", "10.0.0.3"]),
        device_macs=frozenset(["aa:bb:cc:dd:ee:01"]),
        edges=[("10.0.0.1", "10.0.0.2"), ("10.0.0.1", "10.0.0.3")],
    )
    save_snapshot(snap, store)
    loaded = load_last_snapshot(store)
    assert loaded is not None
    assert loaded.device_ips == snap.device_ips
    assert loaded.device_macs == snap.device_macs
    assert set(loaded.edges) == set(snap.edges)


def test_load_returns_none_when_empty():
    from modules.topology_snapshot import load_last_snapshot
    store = _StubStore()
    assert load_last_snapshot(store) is None


def test_save_keeps_only_latest_10():
    from modules.topology_snapshot import TopologySnapshot, save_snapshot
    store = _StubStore()
    for i in range(15):
        snap = TopologySnapshot(
            timestamp=datetime(2025, 1, i + 1, 0, 0, 0),
            device_ips=frozenset([f"10.0.0.{i}"]),
            device_macs=frozenset(),
            edges=[],
        )
        save_snapshot(snap, store)
    rows = store._execute_read("SELECT COUNT(*) FROM topology_snapshots")
    assert rows[0][0] <= 10


def test_load_returns_most_recent():
    from modules.topology_snapshot import TopologySnapshot, save_snapshot, load_last_snapshot
    store = _StubStore()
    for i in range(3):
        snap = TopologySnapshot(
            timestamp=datetime(2025, 1, i + 1, 0, 0, 0),
            device_ips=frozenset([f"10.0.0.{i}"]),
            device_macs=frozenset(),
            edges=[],
        )
        save_snapshot(snap, store)
    latest = load_last_snapshot(store)
    assert latest is not None
    assert f"10.0.0.2" in latest.device_ips


# ── Scaling guard ─────────────────────────────────────────────────────────────

def test_diff_snapshots_scaling():
    import statistics
    import time
    from modules.topology_snapshot import diff_snapshots, TopologySnapshot

    def _make(n):
        ips = [f"10.0.{i // 255}.{i % 255}" for i in range(n)]
        return TopologySnapshot(
            timestamp=datetime.now(),
            device_ips=frozenset(ips),
            device_macs=frozenset(),
            edges=[("10.0.0.1", ip) for ip in ips],
        )

    small, large = _make(50), _make(500)

    def _med(fn, reps=5):
        ts = []
        for _ in range(reps):
            t0 = time.perf_counter()
            fn()
            ts.append(time.perf_counter() - t0)
        return statistics.median(ts)

    t_s = _med(lambda: diff_snapshots(small, small))
    t_l = _med(lambda: diff_snapshots(large, large))
    if t_s < 1e-7:
        import pytest
        pytest.skip("below measurement threshold")
    ratio = t_l / t_s
    assert ratio < 15, (
        f"diff_snapshots scaling ratio {ratio:.1f}x exceeds 15x for 10x input"
    )
