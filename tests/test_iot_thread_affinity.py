"""RULE-WIN27 — IoT Behaviour's Learn and Monitor paths, driven through real threads.

The page's widgets, the Dashboard-style signals and the ``threading.Thread`` hand-off are real;
only the ``modules/iot_baseline`` calls are replaced, so each case controls what the background
thread sees (a baseline, the measured no-Npcap ``RuntimeError``, a pass that blocks until
released). A spy on the status label and the baseline table records the thread of every write
and forwards only GUI-thread writes to Qt — the test observes the defect without committing it.
"""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QThread, pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

# The error scapy 2.7.0 raises from the first sniff when no capture driver is installed
# (measured 2026-09-18 with scapy.arch.windows._NotAvailableSocket as conf.L2listen).
NO_NPCAP = ("Sniffing and sending packets is not available at layer 2: winpcap is not installed. "
            "You may use conf.L3socket or conf.L3socket6 to access layer 3")
MAC = "aa:bb:cc:dd:ee:01"

_widgets: list = []


def _on_gui_thread() -> bool:
    return QThread.currentThread() == QApplication.instance().thread()


def _pump_until(predicate, timeout: float = 5.0) -> bool:
    app = QApplication.instance()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    app.processEvents()
    return predicate()


def _host_class():
    from ui.tabs_analysis import _AnalysisTabsMixin

    class _Host(_AnalysisTabsMixin, QWidget):
        # The same three signals Dashboard declares (pinned by the last test below).
        _iot_progress = pyqtSignal(int, str)
        _iot_ready = pyqtSignal(int, object)
        _iot_failed = pyqtSignal(int, object)

    return _Host


class _Spy:
    """Record (on_gui_thread, value) per write; forward to Qt only from the GUI thread."""

    def __init__(self, widget, method: str):
        self.calls: list = []
        real = getattr(widget, method)

        def _spy(*args):
            gui = _on_gui_thread()
            self.calls.append((gui, args))
            if gui:
                return real(*args)
            return None

        setattr(widget, method, _spy)

    def off_thread(self):
        return [args for gui, args in self.calls if not gui]

    def texts(self):
        return [str(args[0]) for _, args in self.calls]


class _FakeMonitor:
    instances: list = []

    def __init__(self, baselines, on_alert, on_error=None, **_kw):
        self.baselines = baselines
        self.on_alert = on_alert
        self.on_error = on_error
        self.built_on_gui_thread = _on_gui_thread()
        self.started = False
        self.stopped = False
        self.start_error = None
        _FakeMonitor.instances.append(self)

    def start(self):
        self.started = True
        if self.start_error is not None and self.on_error is not None:
            self.on_error(self.start_error)

    def stop(self):
        self.stopped = True


def _baselines():
    import modules.iot_baseline as ib

    return {MAC: ib.DeviceBaseline(mac=MAC, ip="192.168.1.20", device_type="Smart TV", vendor="LG", model="")}


@pytest.fixture
def page(monkeypatch):
    import modules.iot_baseline as ib

    _FakeMonitor.instances = []
    monkeypatch.setattr(ib, "IoTMonitor", _FakeMonitor)
    host = _host_class()()
    _widgets.append(host)
    for name, value in {
        "_m1_result": {"devices": [{"ip": "192.168.1.20", "mac": MAC, "device_type": "Smart TV"}]},
        "_alert_engine": None, "_store": None, "_home_page": MagicMock(),
        "_monitor_overview_page": MagicMock(), "_nav_rail_go_to": MagicMock(),
        "_surface_alert_in_app": MagicMock(),
    }.items():
        setattr(host, name, value)
    tab = host._build_iot_baseline_tab()
    _widgets.append(tab)
    host._iot_learn_duration.setValue(30)
    status = _Spy(host._iot_status, "setText")
    table = {m: _Spy(host._iot_baseline_table, m) for m in ("setRowCount", "insertRow", "setItem")}
    yield host, status, table
    timer = getattr(host, "_iot_drain_timer", None)
    if timer is not None:
        timer.stop()
    for w in _widgets:
        try:
            w.deleteLater()
        except RuntimeError:
            pass  # C++ object already destroyed
    _widgets.clear()
    for _ in range(3):
        QApplication.instance().processEvents()


def _off_thread_writes(status, table):
    found = [("status.setText", a) for a in status.off_thread()]
    for name, spy in table.items():
        found += [(f"table.{name}", a) for a in spy.off_thread()]
    return found


# ── Learn ─────────────────────────────────────────────────────────────────────

def test_learn_writes_every_widget_on_the_gui_thread(page, monkeypatch):
    import modules.iot_baseline as ib

    host, status, table = page

    def _learn(devices, duration_s, progress_cb=None, **_kw):
        progress_cb("Learning baselines for 1 device(s) over 30 s…")
        return _baselines()

    monkeypatch.setattr(ib, "learn", _learn)
    host._run_iot_learn()

    assert _pump_until(lambda: any("Baseline learned" in t for t in status.texts())), status.texts()
    assert _off_thread_writes(status, table) == []
    assert host._iot_baseline_table.rowCount() == 1
    assert host._iot_status.text().startswith("Baseline learned for 1 IoT device(s)")


def test_a_learn_failure_is_shown_not_left_as_learning(page, monkeypatch, caplog):
    import logging

    import modules.iot_baseline as ib
    from ui import worker_error_catalogue as WE
    from ui.error_display import worker_error_text

    host, status, table = page

    def _learn(*_a, **_k):
        raise RuntimeError(NO_NPCAP)

    monkeypatch.setattr(ib, "learn", _learn)
    with caplog.at_level(logging.WARNING):
        host._run_iot_learn()
        _pump_until(lambda: "Learning for" not in host._iot_status.text(), timeout=3.0)

    assert "Learning for" not in host._iot_status.text(), "a failed learn still reads as running"
    assert host._iot_status.text() == worker_error_text(WE.IOT_LEARN_RUN)
    assert "winpcap" not in host._iot_status.text()
    records = [r for r in caplog.records if r.name == f"netsentinel.worker_error.{WE.IOT_LEARN_RUN.key}"]
    assert records and records[0].exc_info, "the traceback did not reach the app log"


# ── Monitor ───────────────────────────────────────────────────────────────────

def test_monitor_is_built_and_started_on_the_gui_thread(page, monkeypatch):
    import modules.iot_baseline as ib

    host, status, table = page

    def _load(devices, progress_cb=None, **_kw):
        progress_cb("1 device(s) have no baseline — starting 60s learning pass…")
        return _baselines()

    monkeypatch.setattr(ib, "load_or_create", _load)
    host._run_iot_monitor()

    assert _pump_until(lambda: any(m.started for m in _FakeMonitor.instances))
    _pump_until(lambda: host._iot_status.text().startswith("Monitoring"))
    (monitor,) = _FakeMonitor.instances
    assert monitor.built_on_gui_thread, "IoTMonitor was built on the background thread"
    assert _off_thread_writes(status, table) == []
    assert host._iot_status.text() == "Monitoring 1 IoT device(s) — watching for anomalies…"
    assert host._iot_monitor_obj is monitor


def test_a_monitor_start_error_shows_the_fixed_text_not_the_raw(page, monkeypatch):
    import modules.iot_baseline as ib
    from ui import worker_error_catalogue as WE
    from ui.error_display import worker_error_text

    host, status, table = page
    raw = f"Failed to start IoT monitor: {NO_NPCAP}"
    real_start = _FakeMonitor.start

    def _start_failing(self):
        self.start_error = raw
        real_start(self)

    monkeypatch.setattr(_FakeMonitor, "start", _start_failing)
    monkeypatch.setattr(ib, "load_or_create", lambda devices, progress_cb=None, **_k: _baselines())
    host._run_iot_monitor()

    assert _pump_until(lambda: any(m.started for m in _FakeMonitor.instances))
    _pump_until(lambda: False, timeout=0.3)  # let any queued write land
    assert not any("winpcap" in t for t in status.texts()), status.texts()
    assert host._iot_status.text() == worker_error_text(WE.IOT_MONITOR_RUN)
    assert host._iot_monitor_obj is None and _FakeMonitor.instances[0].stopped
    assert getattr(host, "_iot_drain_timer", None) is None


def test_stop_during_the_learning_pass_starts_no_monitor(page, monkeypatch):
    import modules.iot_baseline as ib

    host, status, table = page
    entered, release = threading.Event(), threading.Event()

    def _load(devices, progress_cb=None, **_kw):
        entered.set()
        release.wait(5.0)
        progress_cb("  Baseline for 192.168.1.20: 3 IPs, 2 ports, 0.4 pps")
        return _baselines()

    monkeypatch.setattr(ib, "load_or_create", _load)
    host._run_iot_monitor()
    assert entered.wait(5.0)

    host._stop_iot_monitor()
    release.set()
    _pump_until(lambda: False, timeout=0.5)

    assert not any(m.started for m in _FakeMonitor.instances), "Stop did not stop the monitor"
    assert host._iot_monitor_obj is None
    assert host._iot_status.text() == "Anomaly monitor stopped."


def test_a_second_start_stops_the_first_monitor(page, monkeypatch):
    import modules.iot_baseline as ib

    host, status, table = page
    monkeypatch.setattr(ib, "load_or_create", lambda devices, progress_cb=None, **_k: _baselines())

    host._run_iot_monitor()
    assert _pump_until(lambda: len(_FakeMonitor.instances) == 1 and _FakeMonitor.instances[0].started)
    host._run_iot_monitor()
    assert _pump_until(lambda: len(_FakeMonitor.instances) == 2 and _FakeMonitor.instances[1].started)

    first, second = _FakeMonitor.instances
    assert first.stopped, "the first sniffer was orphaned"
    assert not second.stopped and host._iot_monitor_obj is second


# ── RULE-WIN28 — the alert drain returns to the event loop ────────────────────
#
# Live 2026-09-18: a NEW_PORT flood filled the queue faster than a `while True` drain could
# insert rows, so the drain tick never ended and the window went Not Responding (py-spy:
# 9,788 -> 9,910 rows in 5 s, GUI thread pinned in _drain_iot_alerts).

def _started_monitor(host, monkeypatch):
    import modules.iot_baseline as ib

    monkeypatch.setattr(ib, "load_or_create", lambda devices, progress_cb=None, **_k: _baselines())
    host._run_iot_monitor()
    assert _pump_until(lambda: any(m.started for m in _FakeMonitor.instances))
    host._iot_drain_timer.stop()  # the test drives each tick itself
    return _FakeMonitor.instances[-1]


def _port_alert(i: int):
    import modules.iot_baseline as ib

    return ib.IoTAlert(mac=MAC, ip="192.168.1.20", device_label="LG [192.168.1.20]",
                       alert_type="NEW_PORT", severity="MEDIUM",
                       detail=f"Device opened connection to port {50000 + i}", remediation="Verify")


def test_one_drain_tick_takes_a_bounded_batch(page, monkeypatch):
    host, _status, _table = page
    monitor = _started_monitor(host, monkeypatch)
    for i in range(500):
        monitor.on_alert(_port_alert(i))

    host._iot_drain_timer.timeout.emit()

    rows = host._iot_alert_table.rowCount()
    assert 0 < rows <= 100, f"one tick inserted {rows} rows — the event loop waits for all of them"
    assert host._iot_queue.qsize() == 500 - rows, "the rest must wait for the next tick, not be dropped"


def test_the_alert_table_keeps_the_newest_rows_and_reports_the_total(page, monkeypatch):
    host, _status, _table = page
    monitor = _started_monitor(host, monkeypatch)
    total = 800
    for i in range(total):
        monitor.on_alert(_port_alert(i))

    for _ in range(100):
        if host._iot_queue.empty():
            break
        host._iot_drain_timer.timeout.emit()

    assert host._iot_queue.empty()
    rows = host._iot_alert_table.rowCount()
    assert rows < total, "an unbounded table grows a row and a cell widget per alert"
    assert host._iot_alert_table.item(rows - 1, 4).text().endswith(str(50000 + total - 1)), \
        "the newest alert must be the one kept"
    assert f"{total} alerts" in host._iot_status.text(), host._iot_status.text()
    host._monitor_overview_page.set_iot_anomaly_count.assert_called_with(total)


def test_no_ui_queue_drain_loops_until_empty():
    """AST guard: in ui/, `get_nowait()` inside `while True` is an unbounded drain (RULE-WIN28)."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "ui"
    offenders = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.While) and isinstance(node.test, ast.Constant) and node.test.value is True):
                continue
            if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "get_nowait"
                   for n in ast.walk(node)):
                offenders.append(f"{path.relative_to(root.parent).as_posix()}:{node.lineno}")
    assert offenders == [], (
        "GUI-thread queue drains must take a bounded batch per tick (RULE-WIN28): "
        "`for _ in range(N): try: q.get_nowait() except queue.Empty: break`. Offenders: "
        + ", ".join(offenders)
    )


# ── The host's signals are Dashboard's ────────────────────────────────────────

def test_dashboard_declares_the_signals_the_iot_page_emits():
    from ui.dashboard import Dashboard

    host = _host_class()
    for name in ("_iot_progress", "_iot_ready", "_iot_failed"):
        assert hasattr(Dashboard, name), f"Dashboard does not declare {name}"
        assert getattr(Dashboard, name).signatures == getattr(host, name).signatures, name
