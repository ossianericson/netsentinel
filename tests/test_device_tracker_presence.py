"""
Presence episodes on persisted state (schema v22), replacing the event lookback.

Phase 1 edge-triggered LEFT by asking `query_device_events()` whether a LEFT
newer than `last_seen` already existed — correct, but it re-derived per absent
device per scan what a column can just hold, and it made the invariant depend on
event-table retention. `known_device.presence_state` / `gone_notified_ts` hold
the episode directly.

The behaviour under test is unchanged from Phase 1 and is acceptance criterion 1
(569 LEFT events -> one per real absence episode); these tests pin it against the
new mechanism, including the case the new mechanism could newly get wrong — a
stale `gone_notified_ts` surviving a return and muting the NEXT departure.
"""
from __future__ import annotations

import time

import pytest

from modules.device_tracker import DeviceTracker
from modules.metric_store import MetricStore


@pytest.fixture
def store(tmp_path):
    s = MetricStore(db_path=tmp_path / "presence.db")
    yield s
    s.close()


@pytest.fixture
def tracker(store):
    return DeviceTracker(store, gone_threshold_s=3600)


def _dev(mac="aa:bb:cc:11:22:33", ip="10.0.0.4"):
    return {"mac": mac, "ip": ip, "hostname": "thing", "vendor": "Acme",
            "device_type": "Laptop"}


def _left_events(store, mac):
    return [
        e for e in store.query_device_events(hours=24 * 365, event_types=["LEFT"])
        if e.mac == mac
    ]


def _age_out(store, mac, seconds=7200):
    """Backdate last_seen so the device reads as absent past the threshold."""
    store._execute_write(
        "UPDATE known_device SET last_seen = ? WHERE mac = ?",
        (int(time.time()) - seconds, mac),
    )


class TestPresenceEpisodes:
    def test_seen_device_is_marked_present(self, tracker, store):
        tracker.process_scan([_dev()])
        row = store.get_known_devices()["aa:bb:cc:11:22:33"]
        assert row.presence_state == "present"
        assert row.gone_notified_ts is None

    def test_absence_emits_one_left_and_records_the_stamp(self, tracker, store):
        tracker.process_scan([_dev()])
        _age_out(store, "aa:bb:cc:11:22:33")

        result = tracker.process_scan([])
        assert [d.mac for d in result.gone_devices] == ["aa:bb:cc:11:22:33"]
        row = store.get_known_devices()["aa:bb:cc:11:22:33"]
        assert row.presence_state == "absent"
        assert row.gone_notified_ts is not None
        assert len(_left_events(store, "aa:bb:cc:11:22:33")) == 1

    def test_repeated_scans_during_one_absence_emit_exactly_one_left(
        self, tracker, store
    ):
        """Acceptance criterion 1. The pre-Phase-1 heuristic re-announced an
        absent device every hour, forever: 569 LEFT events across 30 MACs."""
        tracker.process_scan([_dev()])
        _age_out(store, "aa:bb:cc:11:22:33")

        for _ in range(5):
            tracker.process_scan([])

        assert len(_left_events(store, "aa:bb:cc:11:22:33")) == 1

    def test_a_second_absence_reports_again(self, tracker, store):
        tracker.process_scan([_dev()])
        _age_out(store, "aa:bb:cc:11:22:33")
        tracker.process_scan([])                      # episode 1 -> LEFT

        tracker.process_scan([_dev()])                # returns
        row = store.get_known_devices()["aa:bb:cc:11:22:33"]
        assert row.presence_state == "present"
        assert row.gone_notified_ts is None, (
            "a stamp left behind by the previous episode would mute the next "
            "departure permanently"
        )

        _age_out(store, "aa:bb:cc:11:22:33")
        result = tracker.process_scan([])             # episode 2 -> LEFT
        assert [d.mac for d in result.gone_devices] == ["aa:bb:cc:11:22:33"]
        assert len(_left_events(store, "aa:bb:cc:11:22:33")) == 2

    def test_absence_inside_the_threshold_reports_nothing(self, tracker, store):
        tracker.process_scan([_dev()])
        _age_out(store, "aa:bb:cc:11:22:33", seconds=60)

        result = tracker.process_scan([])
        assert result.gone_devices == []
        assert _left_events(store, "aa:bb:cc:11:22:33") == []

    def test_disabled_threshold_never_reports(self, store):
        t = DeviceTracker(store, gone_threshold_s=0)
        t.process_scan([_dev()])
        _age_out(store, "aa:bb:cc:11:22:33")
        assert t.process_scan([]).gone_devices == []

    def test_pre_v22_row_with_no_presence_state_still_reports_once(
        self, tracker, store
    ):
        """Every existing install upgrades with presence_state NULL. A NULL must
        read as 'we have not reported this absence', not as 'already reported'."""
        tracker.process_scan([_dev()])
        _age_out(store, "aa:bb:cc:11:22:33")
        store._execute_write(
            "UPDATE known_device SET presence_state = NULL, gone_notified_ts = NULL "
            "WHERE mac = ?",
            ("aa:bb:cc:11:22:33",),
        )
        assert [d.mac for d in tracker.process_scan([]).gone_devices] == [
            "aa:bb:cc:11:22:33"
        ]


class TestImportanceTierRefresh:
    def test_process_scan_refreshes_the_tier_cache(self, tracker, store):
        tracker.process_scan([{
            "mac": "f4:f5:d8:aa:bb:cc", "ip": "192.168.68.64",
            "hostname": "nestwifi",
            "vendor": "Google Nest / Nest Wifi / Google Wifi Router",
            "device_type": "Video Doorbell",
        }])
        tiers = store.get_importance_tiers()
        assert tiers.get("192.168.68.64") == "critical", (
            "the ranking layer reads the cache; a scan that does not refresh it "
            "leaves every new device unranked"
        )

    def test_cache_matches_the_live_gate_after_a_scan(self, tracker, store):
        tracker.process_scan([_dev()])
        cached = store.get_importance_tiers()
        for key in ("aa:bb:cc:11:22:33", "10.0.0.4"):
            assert cached.get(key) == store.get_device_importance_tier(key)
