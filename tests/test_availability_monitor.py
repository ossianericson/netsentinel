"""
Tests for modules/availability_monitor.py — pure-Python monitoring logic.

All tests use an in-memory MetricStore and a patched _ping function so no
real network calls are made.
"""

from unittest.mock import patch

import pytest

from modules.metric_store import MetricStore
from modules.availability_monitor import (
    AvailabilityMonitor,
    CycleResult,
    TargetConfig,
    DEFAULT_DEGRADED_THRESHOLD,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def store():
    s = MetricStore(db_path=":memory:")
    yield s
    s.close()


@pytest.fixture
def monitor(store):
    targets = [
        TargetConfig("10.0.0.1", label="Gateway"),
        TargetConfig("8.8.8.8",  label="DNS"),
    ]
    return AvailabilityMonitor(store=store, targets=targets)


# ── TargetConfig ──────────────────────────────────────────────────────────────

class TestTargetConfig:
    def test_display_name_uses_label(self):
        cfg = TargetConfig("10.0.0.1", label="Router")
        assert cfg.display_name == "Router"

    def test_display_name_falls_back_to_host(self):
        cfg = TargetConfig("10.0.0.1")
        assert cfg.display_name == "10.0.0.1"

    def test_default_threshold(self):
        cfg = TargetConfig("10.0.0.1")
        assert cfg.degraded_threshold_ms == DEFAULT_DEGRADED_THRESHOLD


# ── State classification ───────────────────────────────────────────────────────

class TestClassify:
    def test_negative_rtt_is_down(self):
        assert AvailabilityMonitor._classify(-1.0, 150.0) == "DOWN"

    def test_fast_rtt_is_up(self):
        assert AvailabilityMonitor._classify(20.0, 150.0) == "UP"

    def test_rtt_at_threshold_is_up(self):
        assert AvailabilityMonitor._classify(150.0, 150.0) == "UP"

    def test_rtt_just_above_threshold_is_degraded(self):
        assert AvailabilityMonitor._classify(150.1, 150.0) == "DEGRADED"

    def test_very_high_rtt_is_degraded(self):
        assert AvailabilityMonitor._classify(999.0, 150.0) == "DEGRADED"


# ── Event type transitions ─────────────────────────────────────────────────────

class TestEventForTransition:
    def test_up_to_down(self):
        assert AvailabilityMonitor._event_for_transition("UP", "DOWN") == "DOWN"

    def test_degraded_to_down(self):
        assert AvailabilityMonitor._event_for_transition("DEGRADED", "DOWN") == "DOWN"

    def test_down_to_up_is_recovered(self):
        assert AvailabilityMonitor._event_for_transition("DOWN", "UP") == "RECOVERED"

    def test_down_to_degraded_is_recovered(self):
        assert AvailabilityMonitor._event_for_transition("DOWN", "DEGRADED") == "RECOVERED"

    def test_up_to_degraded_is_degraded(self):
        assert AvailabilityMonitor._event_for_transition("UP", "DEGRADED") == "DEGRADED"

    def test_degraded_to_up_is_recovered(self):
        assert AvailabilityMonitor._event_for_transition("DEGRADED", "UP") == "RECOVERED"


# ── run_cycle — happy path ─────────────────────────────────────────────────────

class TestRunCycle:
    def test_returns_cycle_result(self, monitor):
        with patch("modules.availability_monitor._ping", return_value=10.0):
            result = monitor.run_cycle()
        assert isinstance(result, CycleResult)
        assert "10.0.0.1" in result.states
        assert "8.8.8.8" in result.states

    def test_both_hosts_up(self, monitor):
        with patch("modules.availability_monitor._ping", return_value=10.0):
            result = monitor.run_cycle()
        assert result.states["10.0.0.1"] == "UP"
        assert result.states["8.8.8.8"]  == "UP"

    def test_unreachable_host_is_down(self, monitor):
        with patch("modules.availability_monitor._ping", return_value=-1.0):
            result = monitor.run_cycle()
        assert result.states["10.0.0.1"] == "DOWN"

    def test_slow_host_is_degraded(self, monitor):
        with patch("modules.availability_monitor._ping", return_value=9999.0):
            result = monitor.run_cycle()
        assert result.states["10.0.0.1"] == "DEGRADED"

    def test_rtt_stored_in_result(self, monitor):
        with patch("modules.availability_monitor._ping", return_value=42.0):
            result = monitor.run_cycle()
        assert result.rtts["8.8.8.8"] == pytest.approx(42.0)

    def test_first_cycle_no_changes(self, monitor):
        with patch("modules.availability_monitor._ping", return_value=10.0):
            result = monitor.run_cycle()
        assert result.changes == []

    def test_second_cycle_no_changes_if_same_state(self, monitor):
        with patch("modules.availability_monitor._ping", return_value=10.0):
            monitor.run_cycle()
            result = monitor.run_cycle()
        assert result.changes == []

    def test_transition_up_to_down_emits_change(self, monitor):
        with patch("modules.availability_monitor._ping", return_value=10.0):
            monitor.run_cycle()
        with patch("modules.availability_monitor._ping", return_value=-1.0):
            result = monitor.run_cycle()
        assert len(result.changes) == 2  # both hosts went down
        hosts = {c.host for c in result.changes}
        assert "10.0.0.1" in hosts

    def test_change_contains_correct_fields(self, monitor):
        with patch("modules.availability_monitor._ping", return_value=10.0):
            monitor.run_cycle()
        with patch("modules.availability_monitor._ping", return_value=-1.0):
            result = monitor.run_cycle()
        change = next(c for c in result.changes if c.host == "10.0.0.1")
        assert change.previous == "UP"
        assert change.current == "DOWN"
        assert change.event_type == "DOWN"

    def test_recovery_emits_recovered(self, monitor):
        with patch("modules.availability_monitor._ping", return_value=10.0):
            monitor.run_cycle()
        with patch("modules.availability_monitor._ping", return_value=-1.0):
            monitor.run_cycle()
        with patch("modules.availability_monitor._ping", return_value=5.0):
            result = monitor.run_cycle()
        change = next(c for c in result.changes if c.host == "10.0.0.1")
        assert change.event_type == "RECOVERED"


# ── MetricStore integration ───────────────────────────────────────────────────

class TestStoreIntegration:
    def test_rtt_sample_written(self, store, monitor):
        with patch("modules.availability_monitor._ping", return_value=15.0):
            monitor.run_cycle()
        pts = store.query_rtt_history("10.0.0.1", hours=1)
        assert len(pts) == 1
        assert pts[0].rtt_ms == pytest.approx(15.0)

    def test_device_state_written(self, store, monitor):
        with patch("modules.availability_monitor._ping", return_value=10.0):
            monitor.run_cycle()
        hist = store.query_device_state_history("10.0.0.1", hours=1)
        assert len(hist) == 1
        assert hist[0].state == "UP"

    def test_down_event_written_on_transition(self, store, monitor):
        with patch("modules.availability_monitor._ping", return_value=10.0):
            monitor.run_cycle()
        with patch("modules.availability_monitor._ping", return_value=-1.0):
            monitor.run_cycle()
        events = store.query_device_events(hours=1, ip="10.0.0.1")
        assert any(e.event_type == "DOWN" for e in events)

    def test_no_event_on_first_cycle(self, store, monitor):
        with patch("modules.availability_monitor._ping", return_value=10.0):
            monitor.run_cycle()
        events = store.query_device_events(hours=1, ip="10.0.0.1")
        assert events == []


# ── get_current_states ────────────────────────────────────────────────────────

class TestGetCurrentStates:
    def test_empty_before_first_cycle(self, monitor):
        assert monitor.get_current_states() == {}

    def test_populated_after_cycle(self, monitor):
        with patch("modules.availability_monitor._ping", return_value=10.0):
            monitor.run_cycle()
        states = monitor.get_current_states()
        assert states["10.0.0.1"] == "UP"
        assert states["8.8.8.8"]  == "UP"


# ── on_cycle callback ─────────────────────────────────────────────────────────

class TestOnCycleCallback:
    def test_callback_invoked(self, store):
        received = []
        mon = AvailabilityMonitor(
            store=store,
            targets=[TargetConfig("1.1.1.1")],
            on_cycle=received.append,
        )
        with patch("modules.availability_monitor._ping", return_value=10.0):
            mon.run_cycle()
        assert len(received) == 1
        assert isinstance(received[0], CycleResult)

    def test_callback_not_set(self, store):
        # No exception when on_cycle is None (default)
        mon = AvailabilityMonitor(store=store, targets=[TargetConfig("1.1.1.1")])
        with patch("modules.availability_monitor._ping", return_value=10.0):
            mon.run_cycle()   # should not raise


# ── set_targets ───────────────────────────────────────────────────────────────

class TestSetTargets:
    def test_new_targets_used_next_cycle(self, store):
        mon = AvailabilityMonitor(store=store, targets=[TargetConfig("1.1.1.1")])
        with patch("modules.availability_monitor._ping", return_value=10.0):
            mon.run_cycle()

        mon.set_targets([TargetConfig("192.168.1.1")])
        with patch("modules.availability_monitor._ping", return_value=5.0):
            result = mon.run_cycle()

        assert "192.168.1.1" in result.states
        assert "1.1.1.1" not in result.states
