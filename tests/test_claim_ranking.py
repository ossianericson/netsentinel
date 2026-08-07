"""
ui/claim_ranking.py — the ui/ side of relevance, plus the surfaces it routes.

Signal Quality Phase 5. The ranking POLICY is pinned in tests/test_relevance.py;
this file pins the wiring: that the surfaces call it, that a store which cannot
answer degrades to neutral instead of blanking a page, and that the new-device
announcement speaks about the most relevant device rather than the first one the
scanner happened to return.
"""
from __future__ import annotations

import time

import pytest

from modules.relevance import claim_from_alert_row, claim_from_device_event
from ui.claim_ranking import (
    rank_alert_rows,
    rank_device_events,
    ranking_context,
    top_by_relevance,
)

NOW = int(time.time())


class _Store:
    """Minimal store double exposing only what claim_ranking reads."""

    def __init__(self, tiers=None, dismissals=None, raises=False):
        self._tiers = tiers or {}
        self._dismissals = dismissals or {}
        self._raises = raises

    def get_importance_tiers(self):
        if self._raises:
            raise RuntimeError("no such column: importance_tier")
        return self._tiers

    def get_dismissal_counts(self, days=30.0):
        if self._raises:
            raise RuntimeError("db is closed")
        return self._dismissals


# ── ranking_context ──────────────────────────────────────────────────────────

class TestRankingContext:
    def test_reads_both_maps(self):
        store = _Store({"10.0.0.1": "critical"}, {"NEW_DEVICE": 3})
        tiers, dismissals = ranking_context(store)
        assert tiers == {"10.0.0.1": "critical"}
        assert dismissals == {"NEW_DEVICE": 3}

    def test_a_none_store_yields_empty_maps(self):
        assert ranking_context(None) == ({}, {})

    def test_a_raising_store_degrades_to_neutral(self):
        """An old schema or a closed connection must not break rendering —
        and empty maps are neutral in relevance, never suppressive."""
        assert ranking_context(_Store(raises=True)) == ({}, {})


# ── rank_alert_rows ──────────────────────────────────────────────────────────

class TestRankAlertRows:
    def test_gateway_critical_beats_older_transient_warning(self):
        store = _Store({"192.168.68.1": "critical", "10.0.0.4": "transient"})
        rows = [
            {"ts": NOW - 5, "host": "10.0.0.4", "severity": "WARNING",
             "rule_type": "HOST_DEGRADED", "message": "chromecast slow"},
            {"ts": NOW - 600, "host": "192.168.68.1", "severity": "CRITICAL",
             "rule_type": "HOST_DOWN", "message": "gateway offline"},
        ]
        assert rank_alert_rows(rows, store)[0]["message"] == "gateway offline"

    def test_limit_truncates_after_ranking_not_before(self):
        store = _Store({"192.168.68.1": "critical"})
        rows = [
            {"ts": NOW - i, "host": "10.0.0.9", "severity": "INFO",
             "rule_type": "HOST_DOWN", "message": f"noise {i}"}
            for i in range(10)
        ] + [
            {"ts": NOW - 999, "host": "192.168.68.1", "severity": "CRITICAL",
             "rule_type": "HOST_DOWN", "message": "gateway offline"},
        ]
        top = rank_alert_rows(rows, store, limit=1)
        assert len(top) == 1
        assert top[0]["message"] == "gateway offline", (
            "truncating before ranking is exactly the Home-card defect: the "
            "gateway outage was last in the list and got cut"
        )

    def test_empty_input(self):
        assert rank_alert_rows([], _Store()) == []

    def test_a_malformed_row_does_not_blank_the_surface(self):
        """Ranking improves an order the caller already had; it must never be
        the reason nothing renders."""
        rows = [{"ts": NOW, "host": "h", "severity": "WARNING", "rule_type": "X"}, None]
        assert len(rank_alert_rows(rows, _Store())) == 2

    def test_ordering_is_stable_for_equal_rows(self):
        rows = [
            {"ts": NOW, "host": "h", "severity": "WARNING",
             "rule_type": "HOST_DOWN", "message": str(i)}
            for i in range(6)
        ]
        assert [r["message"] for r in rank_alert_rows(rows, _Store())] == [
            "0", "1", "2", "3", "4", "5"
        ]

    def test_dismissed_class_sinks_below_an_undismissed_peer(self):
        store = _Store({}, {"NEW_DEVICE": 40})
        rows = [
            {"ts": NOW, "host": "a", "severity": "WARNING",
             "rule_type": "NEW_DEVICE", "message": "dismissed a lot"},
            {"ts": NOW, "host": "b", "severity": "WARNING",
             "rule_type": "HOST_DEGRADED", "message": "never dismissed"},
        ]
        assert rank_alert_rows(rows, store)[0]["message"] == "never dismissed"


# ── rank_device_events ───────────────────────────────────────────────────────

def test_rank_device_events_uses_the_tier_map():
    store = _Store({"192.168.68.1": "critical", "10.0.0.4": "transient"})
    rows = [
        {"ts": NOW, "ip": "10.0.0.4", "event_type": "LEFT"},
        {"ts": NOW, "ip": "192.168.68.1", "event_type": "LEFT"},
    ]
    assert rank_device_events(rows, store)[0]["ip"] == "192.168.68.1"


# ── top_by_relevance ─────────────────────────────────────────────────────────

class TestTopByRelevance:
    def test_under_the_cap_nothing_is_dropped(self):
        rows = [{"ts": NOW - i, "host": "h", "severity": "INFO",
                 "rule_type": "X"} for i in range(5)]
        assert len(top_by_relevance(rows, claim_from_alert_row,
                                    _Store(), limit=200)) == 5

    def test_the_cap_keeps_the_important_row_and_display_stays_chronological(self):
        """The Timeline contract: relevance decides WHO survives the cap, the
        surface still renders newest-first."""
        store = _Store({"192.168.68.1": "critical"})
        rows = [
            {"ts": NOW - 10_000, "host": "192.168.68.1", "severity": "CRITICAL",
             "rule_type": "HOST_DOWN", "message": "gateway offline"},
        ] + [
            {"ts": NOW - i, "host": "10.0.0.9", "severity": "INFO",
             "rule_type": "HOST_DOWN", "message": f"noise {i}"}
            for i in range(1, 30)
        ]
        kept = top_by_relevance(rows, claim_from_alert_row, store, limit=3,
                                key=lambda r: r["ts"])
        assert len(kept) == 3
        assert any(r["message"] == "gateway offline" for r in kept), (
            "an old but critical claim must survive a cap that a pure "
            "newest-first slice would have dropped"
        )
        assert [r["ts"] for r in kept] == sorted(
            (r["ts"] for r in kept), reverse=True
        ), "display order must stay newest-first"

    def test_under_cap_with_a_key_still_sorts(self):
        rows = [{"ts": NOW - 5, "host": "h", "severity": "INFO", "rule_type": "X"},
                {"ts": NOW, "host": "h", "severity": "INFO", "rule_type": "X"}]
        out = top_by_relevance(rows, claim_from_alert_row, _Store(), limit=10,
                               key=lambda r: r["ts"])
        assert out[0]["ts"] == NOW


# ── The four consolidated new-device surfaces ────────────────────────────────

pytest.importorskip("PyQt6.QtWidgets")


class _Dev:
    def __init__(self, mac, ip, vendor="Unknown", hostname="", device_type=""):
        self.mac, self.ip, self.vendor = mac, ip, vendor
        self.hostname, self.device_type = hostname, device_type


class _TrayStub:
    def __init__(self):
        self.notifications: list = []

    def is_available(self):
        return False

    def show_notification(self, *a):
        self.notifications.append(a)

    def increment_badge(self):
        pass  # no badge state needed for these assertions


class _BandwidthStub:
    def __init__(self):
        self.annotations: list = []

    def annotate_event(self, text, colour):
        self.annotations.append(text)


def _make_stub(tiers=None):
    """A bare object carrying only what _surface_new_devices() touches."""
    from ui.scan_wiring import ScanResultMixin

    class _Stub(ScanResultMixin):
        def __init__(self):
            self._store = _Store(tiers or {})
            self._tray_manager = _TrayStub()
            self._live_bandwidth_page = _BandwidthStub()
            self.status_messages: list = []

        def _set_status(self, msg):
            self.status_messages.append(msg)

    return _Stub()


class TestNewDeviceConsolidation:
    def test_one_status_line_and_one_annotation_per_scan(self):
        stub = _make_stub()
        stub._surface_new_devices([
            _Dev("aa:bb:cc:00:00:01", "10.0.0.1"),
            _Dev("aa:bb:cc:00:00:02", "10.0.0.2"),
        ])
        assert len(stub.status_messages) == 1
        assert len(stub._live_bandwidth_page.annotations) == 1
        assert "2 new device(s)" in stub.status_messages[0]

    def test_the_status_line_leads_with_the_most_relevant_device(self):
        """Scan order used to decide. A new router discovered third should not
        be announced behind two IoT bulbs."""
        stub = _make_stub(tiers={"10.0.0.9": "critical"})
        stub._surface_new_devices([
            _Dev("aa:bb:cc:00:00:01", "10.0.0.1", vendor="Bulb Co"),
            _Dev("aa:bb:cc:00:00:02", "10.0.0.2", vendor="Bulb Co"),
            _Dev("aa:bb:cc:00:00:09", "10.0.0.9", vendor="Deco"),
        ])
        assert stub.status_messages[0].index("10.0.0.9") < stub.status_messages[0].index(
            "10.0.0.1"
        )

    def test_ranking_failure_still_announces_every_device(self):
        stub = _make_stub()
        stub._store = _Store(raises=True)
        stub._surface_new_devices([_Dev("aa:bb:cc:00:00:01", "10.0.0.1")])
        assert len(stub.status_messages) == 1

    def test_no_tray_notification_when_the_tray_is_unavailable(self):
        stub = _make_stub()
        stub._surface_new_devices([_Dev("aa:bb:cc:00:00:01", "10.0.0.1")])
        assert stub._tray_manager.notifications == []


def test_device_event_adapter_reads_the_scan_wiring_row_shape():
    """_surface_new_devices() synthesises rows for the shared adapter; if that
    shape drifts, ranking silently degrades to unranked."""
    row = {"ts": NOW, "ip": "10.0.0.9", "mac": "aa:bb", "event_type": "JOINED"}
    claim = claim_from_device_event(row, tiers={"10.0.0.9": "critical"})
    assert claim.tier == "critical"
    assert claim.host == "10.0.0.9"
