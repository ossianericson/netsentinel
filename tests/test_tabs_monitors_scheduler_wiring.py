"""F-38 regression: SchedulerWorker.scan_result must be wired to the same
auto-baseline path Full Device Discovery uses, so scheduled scans genuinely
"combine with Config Snapshots" as ui/help.py claims.
"""
from types import SimpleNamespace

from PyQt6.QtCore import QObject, pyqtSignal

from ui.tabs_monitors import _MonitorTabsMixin


class _FakeSchedulerWorker(QObject):
    status = pyqtSignal(str)
    alert = pyqtSignal(str, str)
    error = pyqtSignal(str)
    scan_result = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.started = False

    def isRunning(self) -> bool:
        return False

    def start(self) -> None:
        self.started = True


class _SchedulerHost(_MonitorTabsMixin, QObject):
    """Minimal Dashboard stand-in exposing only what _start_scheduler touches."""

    def __init__(self):
        super().__init__()
        self._sched_worker = None
        self._sched_interval = SimpleNamespace(value=lambda: 15)
        self._offenders_path = None
        self._sched_status = SimpleNamespace(setText=lambda *_a: None)
        self._sched_log = SimpleNamespace(append=lambda *_a: None)
        self.snapshot_calls: list = []

    def _save_monitor_state(self, *_a, **_k) -> None:
        pass

    def _m1_auto_snapshot_baseline(self, data) -> None:
        # In the real Dashboard this lives on ScanResultMixin (ui/scan_wiring.py);
        # here we just record the call to prove the wiring reaches it.
        self.snapshot_calls.append(data)


def test_start_scheduler_connects_scan_result_to_auto_snapshot(monkeypatch, qt_app):
    host = _SchedulerHost()
    fake_worker = _FakeSchedulerWorker()
    monkeypatch.setattr("workers.scan_worker.SchedulerWorker", lambda **_kw: fake_worker)

    host._start_scheduler()
    assert fake_worker.started is True

    fake_result = SimpleNamespace(scan_data={"devices": [{"mac": "aa:bb:cc:dd:ee:ff"}]})
    fake_worker.scan_result.emit(fake_result)
    qt_app.processEvents()  # scan_result is a QueuedConnection — drain it

    assert host.snapshot_calls == [{"devices": [{"mac": "aa:bb:cc:dd:ee:ff"}]}]


def test_on_sched_scan_result_ignores_empty_scan_data(qt_app):
    host = _SchedulerHost()
    host._on_sched_scan_result(SimpleNamespace(scan_data={}))
    host._on_sched_scan_result(SimpleNamespace(scan_data=None))
    assert host.snapshot_calls == []
