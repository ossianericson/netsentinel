"""
Phase 2.3 -- ARP monitor routed through the alert engine.

_on_arp_event() (ui/tabs_monitors.py) used to fire a raw tray balloon per ARP
event, independent of the "ARP Spoof Detected" rule -- no opt-in gate, no
cooldown, no maintenance-window suppression, no Alert History row. Routing
the single event through AlertEngine.evaluate_arp_watch_checks() (the same
evaluator the background watcher already uses, wrapped in a one-event
SimpleNamespace(events=[event]) shim) gains all of that for free.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from ui.tabs_monitors import _MonitorTabsMixin  # noqa: E402


class _FakeTray:
    def __init__(self) -> None:
        self.balloons: list = []

    def is_available(self) -> bool:
        return True

    def show_notification(self, *a, **kw) -> None:
        self.balloons.append((a, kw))

    def increment_badge(self) -> None:
        pass


class _FakeArpTable:
    def rowCount(self) -> int:
        return 0

    def insertRow(self, row) -> None:
        pass

    def setItem(self, row, col, item) -> None:
        pass


class _FakeStack:
    def setCurrentIndex(self, idx) -> None:
        pass


def _arp_event():
    from types import SimpleNamespace
    return SimpleNamespace(
        event_type="GATEWAY_HIJACK", attacker_mac="aa:bb:cc:dd:ee:ff",
        attacker_ip="10.0.0.99", victim_ip="10.0.0.1",
        original_mac="11:22:33:44:55:66", verdict="Gateway MAC changed unexpectedly",
    )


class _Stub(_MonitorTabsMixin):
    def __init__(self, engine) -> None:
        self._tray_manager = _FakeTray()
        self._arp_stack = _FakeStack()
        self._arp_table = _FakeArpTable()
        self._alert_engine = engine
        self._home_page = MagicMock()
        self._store = MagicMock()


class _FakeAlertEngine:
    def __init__(self, alerts) -> None:
        self._alerts = alerts
        self.received_events = None

    def evaluate_arp_watch_checks(self, report):
        self.received_events = list(report.events)
        return self._alerts


def test_no_raw_balloon_and_engine_is_called(monkeypatch):
    from modules.alert_types import AlertFired

    alert = AlertFired(
        rule_name="ARP Spoof Detected", rule_type="ARP_SPOOF", host="10.0.0.1",
        message="Gateway MAC changed unexpectedly", severity="CRITICAL", ts=1000,
    )
    engine = _FakeAlertEngine([alert])
    stub = _Stub(engine)

    calls = []
    monkeypatch.setattr(stub, "_surface_alert_in_app", lambda a: calls.append(a), raising=False)
    monkeypatch.setattr("modules.scan_persistence.persist_alert", lambda store, a: 1)

    stub._on_arp_event(_arp_event())

    assert stub._tray_manager.balloons == []
    assert calls == [alert]
    assert engine.received_events[0].event_type == "GATEWAY_HIJACK"
    stub._home_page.on_alert.assert_called_once_with(alert)


def test_no_alert_when_rule_disabled_or_engine_returns_nothing():
    engine = _FakeAlertEngine([])
    stub = _Stub(engine)
    stub._surface_alert_in_app = MagicMock()

    stub._on_arp_event(_arp_event())

    assert stub._tray_manager.balloons == []
    stub._surface_alert_in_app.assert_not_called()
    stub._home_page.on_alert.assert_not_called()


def test_persist_failure_does_not_break_the_handler():
    from modules.alert_types import AlertFired

    alert = AlertFired(
        rule_name="ARP Spoof Detected", rule_type="ARP_SPOOF", host="10.0.0.1",
        message="x", severity="CRITICAL", ts=1000,
    )
    engine = _FakeAlertEngine([alert])
    stub = _Stub(engine)
    stub._surface_alert_in_app = MagicMock()
    stub._store = None  # forces persist_alert to fail internally

    stub._on_arp_event(_arp_event())  # must not raise

    stub._surface_alert_in_app.assert_called_once_with(alert)
