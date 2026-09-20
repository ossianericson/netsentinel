"""S3.3 — every always-on producer in ``app.py`` raises its app-health condition on its real
error signal and resolves it on its real success signal (RULE-T7).

Before S3 each of these failures had one of three fates, all reproduced by the S0 matrix:
the six G6 monitors got a single status-bar line the next progress update overwrote
(F2-G6); the scheduled speed test's error slot was ``pass`` (F2-SPD); the syslog/SNMP
receivers and the report scheduler reported only on their own pages, which a user who is
not looking at them never sees.

Two halves, because either alone is blind:

* **Behaviour** — the real worker classes, constructed but never started, with their real
  signals emitted by hand (RULE-DBG5). A stub with an invented ``cycle_done`` would stay
  green after someone renamed the real signal, and the condition would then never
  resolve: a permanent false warning, the RULE-SURF1 defect inverted.
* **Placement** — found while wiring: the first version connected these after the
  Dashboard was built, seconds after the workers had started. A cross-thread signal
  emitted with nothing connected is dropped, and the listeners fail exactly once, within
  milliseconds of ``start()`` (a UDP bind). The behavioural test passed; the app would
  never have raised the condition. ``main()`` is checked for connect-before-start.
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6")

import app as app_module  # noqa: E402
from modules import app_health_catalogue as cat  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]
_made: list = []


@pytest.fixture(autouse=True)
def _release_qobjects(qt_app):
    """RULE-WIN4 / RULE-WIN6: QThreads are invisible to the widget flush — release them."""
    yield
    for obj in _made:
        try:
            obj.deleteLater()
        except RuntimeError:
            pass  # already destroyed with its parent
    _made.clear()
    for _ in range(3):
        qt_app.processEvents()


def _keep(obj):
    _made.append(obj)
    return obj


def _make(kind: str):
    from workers.availability_worker import AvailabilityWorker
    from workers.cert_worker import CertWorker
    from workers.health_worker import HealthWorker
    from workers.passive_observer_worker import PassiveObserverWorker
    from workers.proactive_probe_worker import ProactiveProbeWorker
    from workers.report_scheduler_worker import ReportSchedulerWorker
    from workers.service_worker import ServiceWorker
    from workers.snmp_trap_worker import SnmpTrapWorker
    from workers.syslog_worker import SyslogWorker

    store = MagicMock()
    factories = {
        "avail_worker": lambda: AvailabilityWorker(store=store, interval_s=60),
        "cert_worker": lambda: CertWorker(store=store, interval_s=3600),
        "svc_worker": lambda: ServiceWorker(store=store, interval_s=60),
        "health_worker": lambda: HealthWorker(store=store),
        "passive_observer_worker": lambda: PassiveObserverWorker(),
        "trend_worker": lambda: ProactiveProbeWorker(probe=lambda: None, interval_s=3600),
        "scheduled_speedtest_worker": lambda: ProactiveProbeWorker(probe=lambda: None, interval_s=3600),
        "syslog_worker": lambda: SyslogWorker(),
        "snmp_trap_worker": lambda: SnmpTrapWorker(),
        "report_worker": lambda: ReportSchedulerWorker(store=store),
    }
    return _keep(factories[kind]())


# main()'s variable → (condition, success signal, a payload of the signal's declared type)
_PRODUCERS = {
    "avail_worker": (cat.MONITORS["Availability"], "cycle_done", ({},)),
    "cert_worker": (cat.MONITORS["Certificate"], "check_done", ([],)),
    "svc_worker": (cat.MONITORS["Service"], "check_done", ([],)),
    "health_worker": (cat.MONITORS["Health"], "result_ready", (object(),)),
    "passive_observer_worker": (cat.MONITORS["Passive Observer"], "observation_ready", (object(),)),
    "trend_worker": (cat.MONITORS["Trend Forecast"], "probe_done", (object(),)),
    "scheduled_speedtest_worker": (cat.SCHEDULED_SPEED_TEST, "probe_done", (object(),)),
    "syslog_worker": (cat.SYSLOG_RECEIVER, "status", ("Listening on UDP :514",)),
    "snmp_trap_worker": (cat.SNMP_TRAP_RECEIVER, "status", ("Listening on UDP :162",)),
    "report_worker": (cat.REPORT_SCHEDULER, "report_saved", ("C:/reports/r.pdf",)),
}


@pytest.mark.parametrize("var", sorted(_PRODUCERS))
def test_each_producer_raises_on_its_error_and_resolves_on_its_success(var):
    spec, ok_signal, payload = _PRODUCERS[var]
    health = app_module._create_app_health()
    worker = _make(var)
    app_module._report_worker_health(health, spec, worker, ok_signal)

    worker.error.emit("Tidsgränsen nåddes")
    cond = health.get(spec.key)
    assert cond is not None and cond.resolved_at is None, f"{var}: error raised no condition"
    assert cond.detail == "Tidsgränsen nåddes"

    getattr(worker, ok_signal).emit(*payload)
    assert health.get(spec.key).resolved_at is not None, f"{var}: {ok_signal} did not resolve it"


def _main_calls():
    tree = ast.parse((_REPO_ROOT / "app.py").read_text(encoding="utf-8"))
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    reports, starts = {}, {}
    for node in ast.walk(main):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "_report_worker_health":
            worker, signal = node.args[2], node.args[3]
            if isinstance(worker, ast.Name) and isinstance(signal, ast.Constant):
                reports[worker.id] = (node.lineno, signal.value)
        elif (isinstance(func, ast.Attribute) and func.attr == "start"
              and isinstance(func.value, ast.Name)):
            starts.setdefault(func.value.id, []).append(node.lineno)
    return reports, starts


@pytest.mark.parametrize("var", sorted(_PRODUCERS))
def test_main_connects_each_producer_before_starting_it(var):
    reports, starts = _main_calls()

    assert var in reports, f"main() never reports {var} to the app-health registry"
    line, signal = reports[var]
    assert signal == _PRODUCERS[var][1], (
        f"main() resolves {var} on {signal!r}; the real success signal is {_PRODUCERS[var][1]!r}"
    )
    early = [s for s in starts.get(var, []) if s < line]
    assert not early, (
        f"{var}.start() on line {early[0]} runs before its health wiring on line {line}: "
        "a failure emitted in between is dropped"
    )


def test_repeated_errors_stay_one_condition():
    spec, ok_signal, _ = _PRODUCERS["avail_worker"]
    health = app_module._create_app_health()
    worker = _make("avail_worker")
    app_module._report_worker_health(health, spec, worker, ok_signal)

    for _ in range(5):
        worker.error.emit("boom")

    assert [(c.key, c.count) for c in health.active()] == [(spec.key, 5)]


def test_transitions_are_recorded_in_the_app_log(caplog):
    """D4's log is where a condition that came and went before anyone looked is still visible."""
    spec, ok_signal, _ = _PRODUCERS["svc_worker"]
    health = app_module._create_app_health()
    worker = _make("svc_worker")
    app_module._report_worker_health(health, spec, worker, ok_signal)

    with caplog.at_level(logging.INFO, logger="netsentinel.app_health"):
        worker.error.emit("boom")
        worker.error.emit("boom")
        worker.check_done.emit([])

    records = [r for r in caplog.records if r.name == "netsentinel.app_health"]
    assert [r.levelno for r in records] == [logging.WARNING, logging.INFO]
    assert "monitor:service" in records[0].getMessage()
    assert "boom" in records[0].getMessage()


def test_the_dashboard_receives_the_registry_and_the_mqtt_password_is_watched(
    qt_app, monkeypatch, tmp_path,
):
    from keyring.errors import PasswordSetError

    from ui.pages.mqtt_page import MqttPage

    monkeypatch.setattr(MqttPage, "_settings_path", lambda self: tmp_path / "NetSentinel.ini")
    monkeypatch.setattr("ui.pages.mqtt_page.keyring.get_password", lambda *_a: None)

    def _refuse(*_a):
        raise PasswordSetError("Credential Manager sa nej")

    page = _keep(MqttPage(parent=None))
    # A real QObject, not a SimpleNamespace: since S10.2 _wire_app_health always attaches
    # the surface, and AppHealthBridge is parented to the window.
    from PyQt6.QtCore import QObject

    window = _keep(QObject())
    health = app_module._create_app_health()
    app_module._wire_app_health(window, health, page)
    assert window._app_health is health  # read by ui/tabs.py::_watch_rest_api_worker
    assert window._app_health_bridge is not None, "the surface attaches unconditionally"

    monkeypatch.setattr("ui.pages.mqtt_page.keyring.set_password", _refuse)
    page._password.setText("hunter2")
    page._save_settings()
    assert health.get(cat.MQTT_PASSWORD.key).resolved_at is None

    monkeypatch.setattr("ui.pages.mqtt_page.keyring.set_password", lambda *_a: None)
    page._save_settings()
    assert health.get(cat.MQTT_PASSWORD.key).resolved_at is not None


def test_switching_scheduled_speed_tests_off_resolves_their_condition(qt_app):
    """S4.4c — a schedule the user switched off is not a schedule that is failing."""
    from PyQt6.QtCore import QObject, pyqtSignal

    class _SpeedTestPage(QObject):
        auto_speedtest_changed = pyqtSignal(bool, int)

    page = _keep(_SpeedTestPage())
    window = SimpleNamespace(_speed_test_page=page)
    health = app_module._create_app_health()
    worker = _make("scheduled_speedtest_worker")
    # Switching the schedule ON really starts the thread, and destroying a running QThread
    # at teardown kills the pytest process (exit 127, no summary line — RULE-GATE1).
    worker.start = lambda *_a: None
    app_module._report_worker_health(health, cat.SCHEDULED_SPEED_TEST, worker, "probe_done")
    app_module._wire_speedtest_scheduling(window, worker, MagicMock(), MagicMock(), health)

    worker.error.emit("Tidsgränsen nåddes")
    page.auto_speedtest_changed.emit(True, 6)
    assert health.get(cat.SCHEDULED_SPEED_TEST.key).resolved_at is None, "an interval change must not clear it"

    page.auto_speedtest_changed.emit(False, 6)
    assert health.get(cat.SCHEDULED_SPEED_TEST.key).resolved_at is not None


def test_main_hands_the_speed_test_schedule_the_registry():
    tree = ast.parse((_REPO_ROOT / "app.py").read_text(encoding="utf-8"))
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    calls = [n for n in ast.walk(main) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "_wire_speedtest_scheduling"]
    assert calls and any(isinstance(a, ast.Name) and a.id == "app_health" for a in calls[0].args), (
        "main() must pass app_health to _wire_speedtest_scheduling or switching it off never resolves"
    )


@pytest.mark.parametrize("port, random", [(514, False), (5140, False), (54321, True)])
def test_a_syslog_receiver_only_raises_when_it_fell_back_to_a_random_port(port, random):
    """S4.4e — 5140 is the designed fallback (and the normal one without root on
    Linux/macOS), so only a port that is neither is worth a condition."""
    health = app_module._create_app_health()
    worker = _make("syslog_worker")
    app_module._report_syslog_port(health, worker)

    worker.bound.emit(port)

    cond = health.get(cat.SYSLOG_RANDOM_PORT.key)
    assert (cond is not None and cond.resolved_at is None) is random
    if random:
        assert "54321" in cond.detail


def test_main_watches_the_syslog_port_before_starting_the_receiver():
    tree = ast.parse((_REPO_ROOT / "app.py").read_text(encoding="utf-8"))
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    watch = [n.lineno for n in ast.walk(main) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "_report_syslog_port"]
    _reports, starts = _main_calls()
    assert watch, "main() never watches which port the syslog receiver bound"
    assert all(s > watch[0] for s in starts["syslog_worker"])
