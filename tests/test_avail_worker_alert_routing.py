"""Phase 4 C3 — the LAN AvailabilityWorker must reach the alert engine.

There are two AvailabilityWorkers. The one built in `app.py` is never given
targets, so it monitors DEFAULT_TARGETS (8.8.8.8 / 1.1.1.1) and IS wired to the
engine via the `_on_cycle` closure. The one built per-scan in
`ui/scan_wiring.py::_m1_restart_availability_worker` monitors every scanned LAN
device — including the gateway — and was wired only to
`Dashboard._on_avail_cycle_done` (HistoryPage / Home Assistant / MQTT). So a
gateway or infrastructure device going down produced history and MQTT state but
never an alert.

The fix routes the LAN worker into the *existing* `_on_cycle` rather than adding
a second engine hookup, so both workers share one engine instance and one set of
HOST_DOWN edge/dedup state.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock

import pytest

try:
    from PyQt6.QtCore import QObject, pyqtSignal
    from ui.scan_wiring import ScanResultMixin
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

_REPO_ROOT = Path(__file__).resolve().parent.parent


class _FakeAvailWorker(QObject):
    """Stands in for AvailabilityWorker — no thread, no ICMP, real signal."""

    cycle_done = pyqtSignal(dict)

    def __init__(self, **kwargs):
        super().__init__()
        self.kwargs = kwargs
        self.started = False

    def isRunning(self) -> bool:
        return False

    def start(self) -> None:
        self.started = True


class _Stub(ScanResultMixin):
    pass


def _make_stub(monkeypatch, with_handler=True):
    monkeypatch.setattr(
        "workers.availability_worker.AvailabilityWorker", _FakeAvailWorker,
    )
    stub = _Stub()
    stub._store = MagicMock()
    stub._device_baselines = None
    stub._history_cycles = []
    stub._on_avail_cycle_done = stub._history_cycles.append
    stub._engine_cycles = []
    if with_handler:
        stub._alert_cycle_handler = stub._engine_cycles.append
    return stub


_SCAN = {"devices": [
    {"ip": "192.168.68.1",  "mac": "aa:bb:cc:00:00:01", "hostname": "gateway"},
    {"ip": "192.168.68.54", "mac": "aa:bb:cc:00:00:02", "hostname": "printer"},
]}

_CYCLE = {"ts": 1, "states": {"192.168.68.1": "DOWN"}, "rtts": {"192.168.68.1": -1.0}}


def test_lan_worker_cycle_reaches_the_alert_engine(monkeypatch):
    """Fails before fix: cycle_done is only wired to _on_avail_cycle_done."""
    stub = _make_stub(monkeypatch)

    stub._m1_restart_availability_worker(_SCAN)
    assert getattr(stub, "_avail_worker", None) is not None, (
        "the LAN AvailabilityWorker was not created — check the fake patched in"
    )
    stub._avail_worker.cycle_done.emit(_CYCLE)

    assert stub._engine_cycles == [_CYCLE], (
        "the LAN worker's cycle must reach app.py's _on_cycle so gateway and "
        "infrastructure outages can fire HOST_DOWN; got no engine call"
    )


def test_lan_worker_still_feeds_history_and_mqtt(monkeypatch):
    """The pre-existing consumer must keep its cycles — this is additive."""
    stub = _make_stub(monkeypatch)

    stub._m1_restart_availability_worker(_SCAN)
    stub._avail_worker.cycle_done.emit(_CYCLE)

    assert stub._history_cycles == [_CYCLE]


def test_lan_worker_wiring_is_optional(monkeypatch):
    """No published handler (headless / cli.py) must not break the worker."""
    stub = _make_stub(monkeypatch, with_handler=False)

    stub._m1_restart_availability_worker(_SCAN)
    stub._avail_worker.cycle_done.emit(_CYCLE)

    assert stub._history_cycles == [_CYCLE]
    assert stub._engine_cycles == []


def test_retarget_of_a_running_worker_does_not_double_connect(monkeypatch):
    """A rescan calls set_targets() on the live worker — no second connect."""
    stub = _make_stub(monkeypatch)
    stub._m1_restart_availability_worker(_SCAN)

    worker = stub._avail_worker
    monkeypatch.setattr(worker, "isRunning", lambda: True)
    worker.set_targets = MagicMock()

    stub._m1_restart_availability_worker(_SCAN)

    assert stub._avail_worker is worker, "a running worker must be retargeted, not replaced"
    worker.set_targets.assert_called_once()
    worker.cycle_done.emit(_CYCLE)
    assert stub._engine_cycles == [_CYCLE], (
        "one connect only — a duplicated connection would deliver the cycle twice "
        "and double-count every alert"
    )


def test_app_publishes_the_alert_cycle_handler_on_the_window():
    """app.py must expose _on_cycle so scan_wiring can reuse it (RULE-DW2).

    Asserted structurally rather than by constructing the app: the wiring lives
    in a closure inside main()'s helper, which cannot be reached without a full
    Dashboard (RULE-TP4-DASH).
    """
    tree = ast.parse((_REPO_ROOT / "app.py").read_text(encoding="utf-8"))

    published = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(t, ast.Attribute)
            and t.attr == "_alert_cycle_handler"
            and isinstance(t.value, ast.Name)
            and t.value.id == "window"
            for t in node.targets
        )
        and isinstance(node.value, ast.Name)
        and node.value.id == "_on_cycle"
    ]

    assert len(published) == 1, (
        "app.py must assign `window._alert_cycle_handler = _on_cycle` exactly once "
        "so ui/scan_wiring.py can route the LAN AvailabilityWorker into the same "
        f"engine hookup; found {len(published)} such assignments"
    )
