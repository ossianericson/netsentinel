"""
Regression tests for the Signal Quality Phase 1 fixes in modules/device_tracker.py.

Three defects, all measured against a real 25-day database
(docs/spikes/signal-quality-baseline.md):

  1. LEFT re-fires hourly. 569 LEFT events across 30 MACs; the top eight emitted
     34-37 each; the gateway "left the network" 7 times. The suppression check
     only looked back `gone_threshold_s`, so an absent device re-announced its
     absence every hour forever.

  2. Multicast addresses are tracked as devices. `01:00:5e:7f:ff:fa` /
     `239.255.255.250` (SSDP) held a known_device row promoted to
     inferred_role=infrastructure — the alert-eligibility gate.

  3. `known_device.mac_randomized` is read by the query layer and written by
     nobody, so it is 0 for every row on every install.

Written before the fix (RULE-T3); each asserts the corrected contract.
"""
from __future__ import annotations

import pytest

from modules.device_tracker import DeviceTracker
from modules.metric_store import MetricStore


@pytest.fixture
def store(tmp_path):
    s = MetricStore(db_path=tmp_path / "tracker.db")
    yield s
    s.close()


@pytest.fixture
def tracker(store):
    return DeviceTracker(store=store, gone_threshold_s=3600)


def _dev(mac="aa:bb:cc:11:22:33", ip="192.168.1.10", host="mypc", vendor="Apple"):
    return {
        "mac": mac, "ip": ip, "hostname": host,
        "vendor": vendor, "device_type": "Laptop",
    }


def _left_events(store, mac):
    return [
        e for e in store.query_device_events(hours=24 * 365, event_types=["LEFT"])
        if e.mac == mac
    ]


@pytest.fixture
def clock(monkeypatch):
    """A controllable clock.

    The re-fire defect only appears across scans separated by more than
    `gone_threshold_s`; scans run back-to-back in real time all fall inside the
    old suppression window and look correct. Tests that do not advance time
    cannot see the bug at all.

    Note the patch target resolves to the stdlib `time` module itself, so this
    moves the clock for MetricStore's queries too. That is deliberate and
    required: `query_device_events()` filters on wall-clock time, so a clock that
    advanced only inside device_tracker would leave the tracker writing events at
    simulated timestamps the store then treats as months old. monkeypatch
    restores it after each test.
    """
    class _Clock:
        def __init__(self):
            self.now = 1_780_000_000.0

        def advance(self, seconds):
            self.now += seconds

    c = _Clock()
    monkeypatch.setattr("modules.device_tracker.time.time", lambda: c.now)
    return c


# ── Defect 1: LEFT must fire once per absence episode ────────────────────────

class TestLeftIsEdgeTriggered:
    def test_absent_device_emits_exactly_one_left_over_eight_hours(
        self, tracker, store, clock
    ):
        """The core defect: a device that stays away must not re-announce itself.

        Eight hourly scans with the device absent — the exact shape that produced
        34-37 LEFT events per MAC on the reference network. The old suppression
        check looked back only `gone_threshold_s`, so the previous LEFT had always
        just aged out by the time the next scan ran.
        """
        mac = "aa:bb:cc:11:22:33"
        tracker.process_scan([_dev(mac=mac)])

        for _ in range(8):
            clock.advance(3600)
            tracker.process_scan([])

        assert len(_left_events(store, mac)) == 1

    def test_only_the_first_absent_scan_reports_it_as_gone(self, tracker, clock):
        mac = "aa:bb:cc:11:22:33"
        tracker.process_scan([_dev(mac=mac)])

        clock.advance(3600)
        first = tracker.process_scan([])
        clock.advance(3600)
        second = tracker.process_scan([])

        assert [d.mac for d in first.gone_devices] == [mac]
        assert second.gone_devices == []

    def test_returning_then_leaving_again_emits_a_second_left(
        self, tracker, store, clock
    ):
        """Edge-triggering must not become fire-once-ever: a genuinely new
        absence episode is new information and has to be reported."""
        mac = "aa:bb:cc:11:22:33"

        tracker.process_scan([_dev(mac=mac)])
        clock.advance(3600)
        tracker.process_scan([])
        assert len(_left_events(store, mac)) == 1

        # Device comes back...
        clock.advance(600)
        tracker.process_scan([_dev(mac=mac)])
        # ...then goes away again, a full threshold later.
        clock.advance(3600)
        tracker.process_scan([])

        assert len(_left_events(store, mac)) == 2

    def test_device_seen_within_the_threshold_is_never_reported_gone(
        self, tracker, store, clock
    ):
        mac = "aa:bb:cc:11:22:33"
        tracker.process_scan([_dev(mac=mac)])
        clock.advance(60)
        result = tracker.process_scan([])
        assert result.gone_devices == []
        assert _left_events(store, mac) == []


# ── Defect 2: multicast/broadcast addresses are not devices ──────────────────

class TestNonDevicesAreNotTracked:
    @pytest.mark.parametrize("mac,ip", [
        ("01:00:5e:7f:ff:fa", "239.255.255.250"),   # SSDP — the live-database row
        ("01:00:5e:00:00:fb", "224.0.0.251"),       # mDNS
        ("33:33:00:00:00:01", "ff02::1"),           # IPv6 all-nodes
        ("ff:ff:ff:ff:ff:ff", "255.255.255.255"),   # broadcast
    ])
    def test_multicast_addresses_never_enter_the_inventory(self, tracker, store, mac, ip):
        tracker.process_scan([_dev(mac=mac, ip=ip, host="", vendor="")])
        assert mac not in store.get_known_devices()

    def test_multicast_addresses_are_not_reported_as_new_devices(self, tracker):
        result = tracker.process_scan([
            _dev(mac="01:00:5e:7f:ff:fa", ip="239.255.255.250", host="", vendor=""),
        ])
        assert result.new_devices == []

    def test_real_devices_alongside_a_multicast_row_are_still_tracked(self, tracker, store):
        """The filter must drop only the non-device, not the whole scan."""
        result = tracker.process_scan([
            _dev(mac="01:00:5e:7f:ff:fa", ip="239.255.255.250", host="", vendor=""),
            _dev(mac="f4:f5:d8:aa:bb:cc", ip="192.168.1.20"),
        ])
        known = store.get_known_devices()
        assert "f4:f5:d8:aa:bb:cc" in known
        assert "01:00:5e:7f:ff:fa" not in known
        assert [d.mac for d in result.new_devices] == ["f4:f5:d8:aa:bb:cc"]


# ── Defect 3: mac_randomized must actually be written ───────────────────────

class TestMacRandomizedIsPersisted:
    def test_privacy_mac_is_flagged(self, tracker, store):
        tracker.process_scan([_dev(mac="02:a8:f1:3b:93:40", host="", vendor="")])
        assert store.get_known_devices()["02:a8:f1:3b:93:40"].mac_randomized is True

    def test_ordinary_mac_is_not_flagged(self, tracker, store):
        tracker.process_scan([_dev(mac="f4:f5:d8:aa:bb:cc")])
        assert store.get_known_devices()["f4:f5:d8:aa:bb:cc"].mac_randomized is False

    def test_randomised_but_named_device_is_still_flagged(self, tracker, store):
        """The flag records the MAC's nature, not whether we could name the
        device — 'Ossians-iPhone-2022' is randomised AND identifiable."""
        tracker.process_scan([
            _dev(mac="92:ac:4a:bf:8d:10", host="Ossians-iPhone-2022", vendor=""),
        ])
        kd = store.get_known_devices()["92:ac:4a:bf:8d:10"]
        assert kd.mac_randomized is True
