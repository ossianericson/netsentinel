"""
Tests for modules/maintenance_window.py

Covers:
  - MaintenanceWindow: is_currently_active, duration_minutes, to_dict / from_dict
  - MaintenanceWindowManager: add / remove / update / get
  - is_suppressed: active window matches host, all-host window, expired window
  - suppression log: record, get, clear
  - to_json / load_from_json: round-trip serialisation
  - purge_expired
  - AlertEngine integration: set_maintenance_checker suppresses _fire_if_cooled
  - Recurring daily windows (Sprint 5): daily_start_hour/daily_end_hour, overnight
    wraparound, same-day windows, backward-compat JSON load
"""
from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from modules.maintenance_window import MaintenanceWindow, MaintenanceWindowManager


def _future_window(hosts=None, minutes_from_now=5, duration_minutes=60, active=True):
    start = int(time.time()) + minutes_from_now * 60
    return MaintenanceWindow(
        label="Test Window",
        hosts=hosts or [],
        start_ts=start,
        end_ts=start + duration_minutes * 60,
        active=active,
    )


def _active_window(hosts=None, duration_minutes=60):
    now = int(time.time())
    return MaintenanceWindow(
        label="Active Window",
        hosts=hosts or [],
        start_ts=now - 60,
        end_ts=now + duration_minutes * 60,
    )


def _expired_window(hosts=None):
    now = int(time.time())
    return MaintenanceWindow(
        label="Expired",
        hosts=hosts or [],
        start_ts=now - 7200,
        end_ts=now - 3600,
    )


class TestMaintenanceWindow(unittest.TestCase):
    def test_is_currently_active_true(self):
        w = _active_window()
        self.assertTrue(w.is_currently_active)

    def test_is_currently_active_false_future(self):
        w = _future_window(minutes_from_now=30)
        self.assertFalse(w.is_currently_active)

    def test_is_currently_active_false_expired(self):
        w = _expired_window()
        self.assertFalse(w.is_currently_active)

    def test_is_currently_active_false_when_disabled(self):
        w = _active_window()
        w.active = False
        self.assertFalse(w.is_currently_active)

    def test_duration_minutes(self):
        w = _active_window(duration_minutes=90)
        self.assertAlmostEqual(w.duration_minutes, 90, delta=1)

    def test_to_dict_from_dict_roundtrip(self):
        w = _active_window(hosts=["10.0.0.1", "10.0.0.2"])
        d = w.to_dict()
        w2 = MaintenanceWindow.from_dict(d)
        self.assertEqual(w2.label, w.label)
        self.assertEqual(w2.hosts, w.hosts)
        self.assertEqual(w2.start_ts, w.start_ts)
        self.assertEqual(w2.end_ts, w.end_ts)
        self.assertEqual(w2.active, w.active)
        self.assertEqual(w2.id, w.id)


def _mk_localtime(hour):
    """Build a fake time.struct_time-like object with only tm_hour meaningful."""
    return time.struct_time((2026, 7, 1, hour, 0, 0, 2, 182, 0))


class TestRecurringDailyWindow(unittest.TestCase):
    """Sprint 5: daily_start_hour/daily_end_hour recurring quiet-hours windows."""

    def _recurring_window(self, daily_start_hour, daily_end_hour, hosts=None):
        # start_ts/end_ts are irrelevant in recurring mode but must still be
        # valid ints (dataclass requires them) — use an arbitrary past window.
        return MaintenanceWindow(
            label="Nightly Quiet Hours",
            hosts=hosts or [],
            start_ts=0,
            end_ts=0,
            daily_start_hour=daily_start_hour,
            daily_end_hour=daily_end_hour,
        )

    def test_non_recurring_fields_default_to_none(self):
        w = _active_window()
        self.assertIsNone(w.daily_start_hour)
        self.assertIsNone(w.daily_end_hour)

    def test_overnight_wraparound_covers_late_night_hour(self):
        w = self._recurring_window(23, 7)
        with patch("modules.maintenance_window.time.localtime", return_value=_mk_localtime(23)):
            self.assertTrue(w.is_currently_active)

    def test_overnight_wraparound_covers_early_morning_hour(self):
        w = self._recurring_window(23, 7)
        with patch("modules.maintenance_window.time.localtime", return_value=_mk_localtime(6)):
            self.assertTrue(w.is_currently_active)

    def test_overnight_wraparound_covers_midnight(self):
        w = self._recurring_window(23, 7)
        with patch("modules.maintenance_window.time.localtime", return_value=_mk_localtime(0)):
            self.assertTrue(w.is_currently_active)

    def test_overnight_wraparound_excludes_midday(self):
        w = self._recurring_window(23, 7)
        with patch("modules.maintenance_window.time.localtime", return_value=_mk_localtime(12)):
            self.assertFalse(w.is_currently_active)

    def test_overnight_wraparound_excludes_end_hour_boundary(self):
        # end hour is exclusive: [start, end) with wraparound
        w = self._recurring_window(23, 7)
        with patch("modules.maintenance_window.time.localtime", return_value=_mk_localtime(7)):
            self.assertFalse(w.is_currently_active)

    def test_same_day_recurring_window_covers_hour(self):
        w = self._recurring_window(9, 17)
        with patch("modules.maintenance_window.time.localtime", return_value=_mk_localtime(12)):
            self.assertTrue(w.is_currently_active)

    def test_same_day_recurring_window_excludes_hour(self):
        w = self._recurring_window(9, 17)
        with patch("modules.maintenance_window.time.localtime", return_value=_mk_localtime(20)):
            self.assertFalse(w.is_currently_active)

    def test_recurring_window_ignores_absolute_start_end(self):
        """Even if start_ts/end_ts would say 'expired', recurring mode ignores them."""
        now = int(time.time())
        w = MaintenanceWindow(
            label="Nightly",
            start_ts=now - 999999,
            end_ts=now - 999998,   # long expired, if absolute logic were used
            daily_start_hour=23,
            daily_end_hour=7,
        )
        with patch("modules.maintenance_window.time.localtime", return_value=_mk_localtime(23)):
            self.assertTrue(w.is_currently_active)

    def test_recurring_window_respects_active_flag(self):
        w = self._recurring_window(23, 7)
        w.active = False
        with patch("modules.maintenance_window.time.localtime", return_value=_mk_localtime(23)):
            self.assertFalse(w.is_currently_active)

    def test_non_recurring_window_unaffected_by_new_fields(self):
        """A plain absolute window with daily_* left at None must behave exactly
        as before — no regression from adding the new fields."""
        w = _active_window()
        self.assertTrue(w.is_currently_active)
        expired = _expired_window()
        self.assertFalse(expired.is_currently_active)

    def test_json_roundtrip_preserves_daily_fields(self):
        w = self._recurring_window(23, 7)
        d = w.to_dict()
        w2 = MaintenanceWindow.from_dict(d)
        self.assertEqual(w2.daily_start_hour, 23)
        self.assertEqual(w2.daily_end_hour, 7)

    def test_backward_compat_load_missing_daily_fields_defaults_none(self):
        """Old JSON blobs saved before Sprint 5 have no daily_* keys at all."""
        old_blob = {
            "label": "Old Window",
            "start_ts": int(time.time()) - 60,
            "end_ts": int(time.time()) + 3600,
            "hosts": [],
            "active": True,
        }
        w = MaintenanceWindow.from_dict(old_blob)
        self.assertIsNone(w.daily_start_hour)
        self.assertIsNone(w.daily_end_hour)
        self.assertTrue(w.is_currently_active)


class TestManagerCrud(unittest.TestCase):
    def test_add_and_get(self):
        mgr = MaintenanceWindowManager()
        w = _active_window()
        mgr.add_window(w)
        self.assertEqual(len(mgr.get_windows()), 1)

    def test_remove(self):
        mgr = MaintenanceWindowManager()
        w = _active_window()
        mgr.add_window(w)
        result = mgr.remove_window(w.id)
        self.assertTrue(result)
        self.assertEqual(len(mgr.get_windows()), 0)

    def test_remove_nonexistent_returns_false(self):
        mgr = MaintenanceWindowManager()
        self.assertFalse(mgr.remove_window("nonexistent-id"))

    def test_update(self):
        mgr = MaintenanceWindowManager()
        w = _active_window()
        mgr.add_window(w)
        updated = MaintenanceWindow(
            id=w.id, label="Updated", hosts=["1.2.3.4"],
            start_ts=w.start_ts, end_ts=w.end_ts,
        )
        mgr.update_window(updated)
        self.assertEqual(mgr.get_windows()[0].label, "Updated")

    def test_get_active_windows(self):
        mgr = MaintenanceWindowManager()
        mgr.add_window(_active_window())
        mgr.add_window(_expired_window())
        mgr.add_window(_future_window())
        active = mgr.get_active_windows()
        self.assertEqual(len(active), 1)


class TestIsSupressed(unittest.TestCase):
    def test_suppressed_when_host_matches(self):
        mgr = MaintenanceWindowManager()
        mgr.add_window(_active_window(hosts=["10.0.0.1"]))
        result = mgr.is_suppressed("10.0.0.1")
        self.assertIsNotNone(result)
        self.assertIn("Active Window", result)

    def test_not_suppressed_for_other_host(self):
        mgr = MaintenanceWindowManager()
        mgr.add_window(_active_window(hosts=["10.0.0.1"]))
        self.assertIsNone(mgr.is_suppressed("10.0.0.2"))

    def test_suppressed_all_hosts_when_hosts_empty(self):
        mgr = MaintenanceWindowManager()
        mgr.add_window(_active_window(hosts=[]))  # empty = all hosts
        self.assertIsNotNone(mgr.is_suppressed("any.host.whatsoever"))

    def test_not_suppressed_when_window_expired(self):
        mgr = MaintenanceWindowManager()
        mgr.add_window(_expired_window(hosts=["10.0.0.1"]))
        self.assertIsNone(mgr.is_suppressed("10.0.0.1"))

    def test_not_suppressed_when_window_future(self):
        mgr = MaintenanceWindowManager()
        mgr.add_window(_future_window(hosts=["10.0.0.1"]))
        self.assertIsNone(mgr.is_suppressed("10.0.0.1"))

    def test_not_suppressed_when_disabled(self):
        mgr = MaintenanceWindowManager()
        w = _active_window(hosts=["10.0.0.1"])
        w.active = False
        mgr.add_window(w)
        self.assertIsNone(mgr.is_suppressed("10.0.0.1"))


class TestSuppressionLog(unittest.TestCase):
    def test_record_and_get(self):
        mgr = MaintenanceWindowManager()
        mgr.record_suppression("wid", "Test", "10.0.0.1", "rule", "WARNING", "msg")
        log = mgr.get_suppression_log()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0].host, "10.0.0.1")

    def test_clear(self):
        mgr = MaintenanceWindowManager()
        mgr.record_suppression("wid", "Test", "10.0.0.1", "rule", "WARNING", "msg")
        mgr.clear_suppression_log()
        self.assertEqual(mgr.get_suppression_log(), [])

    def test_log_capped(self):
        mgr = MaintenanceWindowManager()
        mgr._LOG_MAX = 5
        for i in range(10):
            mgr.record_suppression("w", "T", f"10.0.0.{i}", "r", "INFO", "m")
        self.assertEqual(len(mgr.get_suppression_log()), 5)


class TestSerialization(unittest.TestCase):
    def test_to_json_load_from_json(self):
        mgr = MaintenanceWindowManager()
        mgr.add_window(_active_window(hosts=["1.2.3.4"]))
        mgr.add_window(_future_window(hosts=["5.6.7.8"]))
        raw = mgr.to_json()

        mgr2 = MaintenanceWindowManager()
        mgr2.load_from_json(raw)
        self.assertEqual(len(mgr2.get_windows()), 2)
        hosts = {w.hosts[0] for w in mgr2.get_windows() if w.hosts}
        self.assertIn("1.2.3.4", hosts)

    def test_load_invalid_json_is_safe(self):
        mgr = MaintenanceWindowManager()
        mgr.load_from_json("not json at all {{{")
        self.assertEqual(mgr.get_windows(), [])

    def test_load_empty_string(self):
        mgr = MaintenanceWindowManager()
        mgr.load_from_json("")
        self.assertEqual(mgr.get_windows(), [])


class TestPurgeExpired(unittest.TestCase):
    def test_purges_old_expired(self):
        mgr = MaintenanceWindowManager()
        # Window that ended 10 days ago
        old = MaintenanceWindow(
            label="Old",
            start_ts=int(time.time()) - 10 * 86400 - 3600,
            end_ts=int(time.time()) - 10 * 86400,
        )
        recent = _active_window()
        mgr.add_window(old)
        mgr.add_window(recent)
        removed = mgr.purge_expired(older_than_days=7)
        self.assertEqual(removed, 1)
        self.assertEqual(len(mgr.get_windows()), 1)

    def test_recurring_window_survives_purge_despite_stale_dummy_end_ts(self):
        """Regression (F-40 claims-audit): a recurring window's start_ts/end_ts
        are dummy placeholders set at creation time (is_currently_active()
        ignores them entirely for recurring windows). purge_expired() must not
        delete a still-recurring window just because its old dummy end_ts has
        aged past the cutoff -- that would silently delete a user's nightly
        quiet-hours window after a week."""
        mgr = MaintenanceWindowManager()
        recurring = MaintenanceWindow(
            label="Nightly quiet hours",
            start_ts=int(time.time()) - 10 * 86400 - 3600,
            end_ts=int(time.time()) - 10 * 86400,
            daily_start_hour=22, daily_end_hour=6,
        )
        mgr.add_window(recurring)
        removed = mgr.purge_expired(older_than_days=7)
        self.assertEqual(removed, 0)
        self.assertEqual(len(mgr.get_windows()), 1)


class TestAlertEngineIntegration(unittest.TestCase):
    def test_maintenance_checker_suppresses_alert(self):
        from modules.alert_engine import AlertEngine, AlertRule
        from unittest.mock import MagicMock

        engine = AlertEngine(store=None)
        engine.set_rules([AlertRule(name="rtt", rule_type="RTT_THRESHOLD",
                                    host="10.0.0.1", threshold_ms=50.0, cooldown_s=0)])

        cb = MagicMock()
        engine.set_on_alert(cb)

        # No maintenance → alert fires
        engine.evaluate_cycle({
            "ts": int(time.time()),
            "states": {"10.0.0.1": "UP"},
            "rtts": {"10.0.0.1": 150.0},
            "loss": {},
        })
        # May or may not fire depending on current state; reset cooldown
        engine._last_fired.clear()

        # With maintenance → alert suppressed
        engine.set_maintenance_checker(lambda host: "Planned Maintenance" if host == "10.0.0.1" else None)
        fired = engine.evaluate_cycle({
            "ts": int(time.time()),
            "states": {"10.0.0.1": "UP"},
            "rtts": {"10.0.0.1": 150.0},
            "loss": {},
        })
        suppressed_alerts = [a for a in fired if a.host == "10.0.0.1"
                              and a.rule_type == "RTT_THRESHOLD"]
        self.assertEqual(len(suppressed_alerts), 0)


if __name__ == "__main__":
    unittest.main()
