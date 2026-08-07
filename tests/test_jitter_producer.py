"""JITTER_HIGH had no data source — nothing ever produced a jitter sample.

`jitter_ms` was `-1.0` on all 112,497 `rtt_sample` rows in the live database
(a single distinct value across the whole table), because
`AvailabilityMonitor.run_cycle()` pings with `_ping_once()` and
`MetricStore.record_rtt()` defaults `jitter_ms` to `-1.0`. `app.py::_on_cycle`
then filters `jitter_ms >= 0` before calling `evaluate_jitter_checks()`, so
every sample was discarded and the rule could not fire. The producer was
missing, not the filter.

Measuring it everywhere is not free, and that is why this is bounded rather
than global: `icmp_ping()` shells out to `ping.exe` once per sample and
`run_cycle()` walks its targets **sequentially** with a 2 s timeout each. At
~28 LAN targets, three samples apiece is up to 168 s of worst-case cycle time
against a 60 s interval — the cycle would overrun itself whenever several
hosts were down. Jitter is an uplink-quality signal anyway, so it is collected
for the gateway and the internet reachability targets only.
"""
from __future__ import annotations

import pytest

from modules import availability_monitor as am
from modules.availability_monitor import AvailabilityMonitor, TargetConfig


class _FakeStore:
    def __init__(self):
        self.rtt_rows = []
        self.state_rows = []

    def record_availability_cycle(self, rtt_rows, state_rows):
        self.rtt_rows.extend(rtt_rows)
        self.state_rows.extend(state_rows)

    def record_device_event(self, **kw):
        pass  # not under test — event recording is unchanged by this fix


@pytest.fixture()
def store():
    return _FakeStore()


def _targets(*hosts):
    return [TargetConfig(host=h) for h in hosts]


def test_jitter_is_measured_for_nominated_hosts(store, monkeypatch):
    calls = {"once": [], "jitter": []}
    monkeypatch.setattr(am, "_ping", lambda h: (calls["once"].append(h), 12.0)[1])
    monkeypatch.setattr(am, "_ping_jitter",
                        lambda h, count=3: (calls["jitter"].append(h), (12.0, 3.5))[1])

    mon = AvailabilityMonitor(
        store=store,
        targets=_targets("192.168.68.1", "192.168.68.50", "8.8.8.8"),
        jitter_hosts=["192.168.68.1", "8.8.8.8"],
    )
    mon.run_cycle()

    assert sorted(calls["jitter"]) == ["192.168.68.1", "8.8.8.8"]
    assert calls["once"] == ["192.168.68.50"]

    by_host = {r["host"]: r for r in store.rtt_rows}
    assert by_host["192.168.68.1"]["jitter_ms"] == pytest.approx(3.5)
    assert by_host["8.8.8.8"]["jitter_ms"] == pytest.approx(3.5)
    # Every other host must stay at the sentinel — a fabricated 0.0 would read
    # as "perfectly stable" and is a claim we have no evidence for.
    assert by_host["192.168.68.50"]["jitter_ms"] == -1.0


def test_default_is_unchanged_no_jitter_anywhere(store, monkeypatch):
    """RULE-EXP1: the previously-shipped path stays bit-for-bit intact."""
    monkeypatch.setattr(am, "_ping", lambda h: 12.0)
    monkeypatch.setattr(am, "_ping_jitter",
                        lambda h, count=3: pytest.fail("must not sample jitter by default"))

    mon = AvailabilityMonitor(store=store, targets=_targets("10.0.0.1", "10.0.0.2"))
    mon.run_cycle()
    assert all(r["jitter_ms"] == -1.0 for r in store.rtt_rows)


def test_a_failed_ping_reports_no_jitter_rather_than_zero(store, monkeypatch):
    """_ping_jitter returns (-1, -1) when every probe fails.

    -1 must survive to the row: `_on_cycle` filters `jitter_ms >= 0`, so a 0.0
    here would feed a fake perfect-stability sample into the rule's history
    for a host that is actually down.
    """
    monkeypatch.setattr(am, "_ping", lambda h: -1.0)
    monkeypatch.setattr(am, "_ping_jitter", lambda h, count=3: (-1.0, -1.0))

    mon = AvailabilityMonitor(store=store, targets=_targets("10.0.0.1"),
                              jitter_hosts=["10.0.0.1"])
    result = mon.run_cycle()

    assert store.rtt_rows[0]["jitter_ms"] == -1.0
    assert store.rtt_rows[0]["rtt_ms"] == -1.0
    assert result.states["10.0.0.1"] == "DOWN"


def test_jitter_host_membership_does_not_change_state_classification(store, monkeypatch):
    """The rtt returned by the 3-sample path drives state exactly as before."""
    monkeypatch.setattr(am, "_ping", lambda h: 12.0)
    monkeypatch.setattr(am, "_ping_jitter", lambda h, count=3: (900.0, 4.0))

    mon = AvailabilityMonitor(store=store, targets=_targets("10.0.0.1"),
                              jitter_hosts=["10.0.0.1"])
    result = mon.run_cycle()
    # 900 ms is above the 150 ms global DEGRADED threshold.
    assert result.states["10.0.0.1"] == "DEGRADED"
    assert result.rtts["10.0.0.1"] == pytest.approx(900.0)


def test_unknown_jitter_host_is_harmless(store, monkeypatch):
    """Nominating a host that is not a target must not raise or add rows."""
    monkeypatch.setattr(am, "_ping", lambda h: 12.0)
    monkeypatch.setattr(am, "_ping_jitter", lambda h, count=3: (12.0, 1.0))

    mon = AvailabilityMonitor(store=store, targets=_targets("10.0.0.1"),
                              jitter_hosts=["203.0.113.9"])
    mon.run_cycle()
    assert len(store.rtt_rows) == 1
    assert store.rtt_rows[0]["jitter_ms"] == -1.0
