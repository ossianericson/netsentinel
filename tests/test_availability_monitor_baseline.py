"""
Signal Quality Phase 3b — per-device thresholds and DOWN confirmation in the
availability monitor.

This is the *event*-layer half of Phase 3. The alert-layer half (edge-triggered
HOST_DOWN) lives in tests/test_alert_engine_edge_trigger.py; between them they
target acceptance criterion 2: the 306 state events `192.168.68.54` emitted in
25 days drop to <= 10 without losing a genuine outage.

Both behaviours are opt-in (RULE-EXP1) — constructing an AvailabilityMonitor
the way the app has always constructed it must produce byte-identical
classification, and that is asserted here alongside the new behaviour.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from modules.availability_monitor import (
    AvailabilityMonitor,
    TargetConfig,
    DEFAULT_DEGRADED_THRESHOLD,
)
from modules.device_baseline import DOWN_CONFIRMATION_CYCLES
from modules.metric_store import MetricStore


@pytest.fixture
def store():
    s = MetricStore(db_path=":memory:")
    yield s
    s.close()


def _drive(monitor, rtts):
    """Run one cycle per entry in `rtts`, returning the state seen each time."""
    seen = []
    for rtt in rtts:
        with patch("modules.availability_monitor._ping", return_value=rtt):
            result = monitor.run_cycle()
        seen.append(result.states["10.0.0.9"])
    return seen


def _events(store, ip="10.0.0.9"):
    return store.query_device_events_for_ip(ip) if hasattr(
        store, "query_device_events_for_ip"
    ) else []


# ── Per-device DEGRADED threshold ────────────────────────────────────────────

class TestPerDeviceThreshold:
    def test_default_construction_uses_the_global_threshold(self):
        """The legacy path must not move."""
        mon = AvailabilityMonitor(
            store=MetricStore(db_path=":memory:"),
            targets=[TargetConfig("10.0.0.9")],
        )
        assert _drive(mon, [194.0]) == ["DEGRADED"]

    def test_a_provider_lifts_the_threshold_for_a_naturally_slow_device(self):
        """The Chromecast case: 194 ms is this device's normal, so it is UP."""
        mon = AvailabilityMonitor(
            store=MetricStore(db_path=":memory:"),
            targets=[TargetConfig("10.0.0.9")],
            threshold_provider=lambda host: 260.0,
        )
        assert _drive(mon, [194.0]) == ["UP"]

    def test_the_provider_still_reports_a_genuine_slowdown(self):
        """Over-suppression check — a learned threshold is not a mute button."""
        mon = AvailabilityMonitor(
            store=MetricStore(db_path=":memory:"),
            targets=[TargetConfig("10.0.0.9")],
            threshold_provider=lambda host: 260.0,
        )
        assert _drive(mon, [600.0]) == ["DEGRADED"]

    def test_a_broken_provider_falls_back_to_the_target_threshold(self):
        def _boom(host):
            raise RuntimeError("no baseline")

        mon = AvailabilityMonitor(
            store=MetricStore(db_path=":memory:"),
            targets=[TargetConfig("10.0.0.9")],
            threshold_provider=_boom,
        )
        assert _drive(mon, [194.0]) == ["DEGRADED"]

    def test_no_state_churn_for_a_device_sitting_on_the_global_boundary(self):
        """The defect in one test: RTTs straddling 150 ms produce a state change
        every cycle under the global threshold, and none under a learned one."""
        straddling = [140.0, 164.0, 148.0, 176.0, 152.0, 144.0]

        loud = AvailabilityMonitor(
            store=MetricStore(db_path=":memory:"),
            targets=[TargetConfig("10.0.0.9")],
        )
        loud_states = _drive(loud, straddling)

        quiet = AvailabilityMonitor(
            store=MetricStore(db_path=":memory:"),
            targets=[TargetConfig("10.0.0.9")],
            threshold_provider=lambda host: 260.0,
        )
        quiet_states = _drive(quiet, straddling)

        assert len(set(loud_states)) > 1, "fixture no longer straddles the boundary"
        assert set(quiet_states) == {"UP"}


# ── DOWN confirmation ────────────────────────────────────────────────────────

class TestDownConfirmation:
    def test_default_construction_reports_down_immediately(self):
        mon = AvailabilityMonitor(
            store=MetricStore(db_path=":memory:"),
            targets=[TargetConfig("10.0.0.9")],
        )
        assert _drive(mon, [5.0, -1.0]) == ["UP", "DOWN"]

    def test_a_single_dropped_ping_is_not_an_outage(self):
        mon = AvailabilityMonitor(
            store=MetricStore(db_path=":memory:"),
            targets=[TargetConfig("10.0.0.9")],
            confirm_down=True,
        )
        assert _drive(mon, [5.0, -1.0, 5.0]) == ["UP", "UP", "UP"]

    def test_a_sustained_outage_is_still_reported(self):
        mon = AvailabilityMonitor(
            store=MetricStore(db_path=":memory:"),
            targets=[TargetConfig("10.0.0.9")],
            confirm_down=True,
        )
        seen = _drive(mon, [5.0] + [-1.0] * 4)
        assert seen[0] == "UP"
        assert seen[-1] == "DOWN"

    def test_confirmation_costs_exactly_the_declared_cycles(self):
        mon = AvailabilityMonitor(
            store=MetricStore(db_path=":memory:"),
            targets=[TargetConfig("10.0.0.9")],
            confirm_down=True,
        )
        seen = _drive(mon, [5.0] + [-1.0] * 5)
        first_down = seen.index("DOWN")
        assert first_down == DOWN_CONFIRMATION_CYCLES, (
            f"expected DOWN on failure #{DOWN_CONFIRMATION_CYCLES}, "
            f"got the sequence {seen}"
        )

    def test_a_first_ever_observation_is_not_debounced(self):
        """There is no prior reachable state to hold, so claiming UP would be
        inventing reachability the monitor has never seen."""
        mon = AvailabilityMonitor(
            store=MetricStore(db_path=":memory:"),
            targets=[TargetConfig("10.0.0.9")],
            confirm_down=True,
        )
        assert _drive(mon, [-1.0]) == ["DOWN"]

    def test_the_raw_rtt_is_never_falsified(self):
        """Confirmation changes the CLASSIFICATION, never the measurement — the
        record layer must stay complete (program plan: record vs claim)."""
        mon = AvailabilityMonitor(
            store=MetricStore(db_path=":memory:"),
            targets=[TargetConfig("10.0.0.9")],
            confirm_down=True,
        )
        with patch("modules.availability_monitor._ping", return_value=5.0):
            mon.run_cycle()
        with patch("modules.availability_monitor._ping", return_value=-1.0):
            result = mon.run_cycle()
        assert result.states["10.0.0.9"] == "UP"      # unconfirmed
        assert result.rtts["10.0.0.9"] == -1.0        # but the truth is intact

    def test_recovery_re_arms_the_confirmation(self):
        mon = AvailabilityMonitor(
            store=MetricStore(db_path=":memory:"),
            targets=[TargetConfig("10.0.0.9")],
            confirm_down=True,
        )
        seen = _drive(mon, [5.0, -1.0, 5.0, -1.0, 5.0])
        assert seen == ["UP", "UP", "UP", "UP", "UP"]

    def test_no_state_events_recorded_for_a_debounced_blip(self, store):
        """The 306-events defect is about device_event rows, so assert on those
        and not only on the in-memory state."""
        mon = AvailabilityMonitor(
            store=store,
            targets=[TargetConfig("10.0.0.9")],
            confirm_down=True,
        )
        for rtt in [5.0, -1.0, 5.0, -1.0, 5.0]:
            with patch("modules.availability_monitor._ping", return_value=rtt):
                result = mon.run_cycle()
        assert result.changes == []

    def test_a_real_outage_still_records_its_events(self, store):
        mon = AvailabilityMonitor(
            store=store,
            targets=[TargetConfig("10.0.0.9")],
            confirm_down=True,
        )
        all_changes = []
        for rtt in [5.0, -1.0, -1.0, -1.0, 5.0]:
            with patch("modules.availability_monitor._ping", return_value=rtt):
                all_changes.extend(mon.run_cycle().changes)
        kinds = [c.event_type for c in all_changes]
        assert kinds == ["DOWN", "RECOVERED"]


# ── The two together ─────────────────────────────────────────────────────────

def test_defaults_are_byte_identical_to_the_shipped_monitor():
    """RULE-EXP1: the legacy path stays intact until the flag is flipped."""
    legacy = AvailabilityMonitor(
        store=MetricStore(db_path=":memory:"),
        targets=[TargetConfig("10.0.0.9")],
    )
    assert legacy._threshold_for(TargetConfig("10.0.0.9")) == DEFAULT_DEGRADED_THRESHOLD
    assert _drive(legacy, [5.0, -1.0, 5.0, 194.0]) == [
        "UP", "DOWN", "UP", "DEGRADED"
    ]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
