"""Live verification matrix for the error-surfacing audit (S0.2).

`docs/internal/error-surfacing-audit-2026-09-15.md` derived its F1/F2/F4/F6 findings
from reading code. This script drives the REAL code path behind each row -- the real
`app.py` wiring functions, real QThread workers, real widgets, real delivery code --
with a genuine fault injected, and prints what actually happens. Re-run it after S1,
S2 and S4: a row whose verdict flips from REPRODUCED to NOT REPRODUCED is the proof
those sprints did what they claimed.

    PYTHONIOENCODING=utf-8 python docs/spikes/error-surfacing-matrix.py

Safety -- it touches nothing of the developer's:
  * no Dashboard is constructed, so nothing reaches `scan_registry/state` or the
    other registry-backed QSettings that cannot be sandboxed on Windows
    (tests/conftest.py); `app.py` wiring runs against a recording stand-in window
  * LOCALAPPDATA is redirected to a temp dir before any project import
  * network faults use loopback only (a closed port, a port this script occupies)
  * the failing keyring backend is installed in-process and restored afterwards

Method labels in the output:
  real-path  -- production function/worker/widget, genuine fault, observed effect
  construct  -- the API cannot express the state at all (checked by introspection)

READ THE LAST LINE, NOT THE EXIT CODE. This script ends in `os._exit(0)` to skip
Qt/QThread interpreter teardown, and on Windows the process still frequently
reports 0xC0000409 (STATUS_STACK_BUFFER_OVERRUN) anyway -- a live Qt thread
losing a race with the exit. It is not an app fault: `netsentinel_crash.log` is
byte-identical across a run, so faulthandler never saw it, and every row is
already printed by then. S1.6 stopped the REST worker and released the pages,
which did not change it. The `MATRIX COMPLETE` line is therefore the completion
signal (RULE-GATE1): if you cannot see it, the run truncated -- if you can, the
rows above it are complete regardless of what the shell reports.
"""
from __future__ import annotations

import inspect
import io
import logging
import os
import re
import socket
import sys
import tempfile
import time
from contextlib import contextmanager, redirect_stderr
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="ns-matrix-")

from PyQt6.QtCore import QObject, QTimer, pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QApplication, QStatusBar, QWidget  # noqa: E402

APP = QApplication(["ns-matrix", "-platform", "offscreen"])
ROWS: list[tuple[str, str, str, str, str]] = []   # id, finding, method, observed, verdict


def row(rid: str, finding: str, method: str, observed: str, reproduced: bool | None) -> None:
    verdict = {True: "REPRODUCED", False: "NOT REPRODUCED", None: "INCONCLUSIVE"}[reproduced]
    ROWS.append((rid, finding, method, observed, verdict))


def wait_for(pred, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        APP.processEvents()
        if pred():
            return True
        time.sleep(0.02)
    APP.processEvents()
    return pred()


class Recorder:
    """Stand-in window: every attribute chain is recordable and callable."""

    def __init__(self, log: list, path: str = "window") -> None:
        self._log, self._path = log, path

    def __getattr__(self, name: str) -> "Recorder":
        if name.startswith("__"):
            raise AttributeError(name)
        return Recorder(self._log, f"{self._path}.{name}")

    def __call__(self, *args, **kwargs) -> "Recorder":
        self._log.append((self._path, args, kwargs))
        return Recorder(self._log, f"{self._path}()")


def effects_since(log: list, start: int) -> list[str]:
    """UI-effecting calls recorded after *start*, ignoring signal wiring."""
    return [
        f"{path.removeprefix('window.')}{args!r}"
        for path, args, _kw in log[start:]
        if ".connect" not in path
    ]


@contextmanager
def captured_records():
    """Records that reach ANY handler, filtered by effective level exactly as in production."""
    records: list[logging.LogRecord] = []

    class _Grab(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Grab(level=logging.DEBUG)
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield records
    finally:
        root.removeHandler(handler)


def drawn_rows(health) -> list[tuple[str, str]] | None:
    """S4: the (key, CTA) rows the real Home app-health strip draws for *health*.

    None before S4 (no strip to draw with). The strip is built directly rather than
    through HomePage, because its flag is a registry-backed QSettings this script must
    not touch — the flag only decides whether the strip exists, not what it draws.
    """
    try:
        from ui.widgets.app_health_strip import AppHealthStrip
    except ImportError:
        return None
    strip = AppHealthStrip()
    strip.set_conditions(health.active())
    rows = [] if strip.isHidden() else [(r.condition.key, r.condition.cta_label) for r in strip.rows()]
    strip.deleteLater()
    return rows


def run_probe_wiring(wire_name: str, rid: str, finding: str, expect) -> None:
    import app
    from workers.proactive_probe_worker import ProactiveProbeWorker

    def _probe():
        raise OSError("Npcap is not installed")  # the fault a real ARP/DHCP cycle hits

    log: list = []
    window = Recorder(log)
    worker = ProactiveProbeWorker(probe=_probe, interval_s=3600)
    getattr(app, wire_name)(window, worker, Recorder(log, "alerts"), Recorder(log, "store"))
    errors: list[str] = []
    worker.error.connect(errors.append)
    start = len(log)
    worker.start()
    got = wait_for(lambda: bool(errors))
    APP.processEvents()
    worker.stop()
    worker.wait(3000)
    effects = effects_since(log, start)
    row(rid, finding, "real-path", f"error={errors[:1]} -> UI effects: {effects or 'none'}",
        expect(effects) if got else None)


# ── F4: what a log.warning becomes -- run FIRST, before any handler is attached ─────

#: A record with the four fields F4 is about:
#: 2026-09-16 18:05:09,123 WARNING netsentinel.monitors: Availability monitor error: boom
_SHAPED = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} [A-Z]+ [\w.]+: ")


def f4_log_record_shape() -> None:
    import ui.dashboard  # noqa: F401  -- pull in the same library set the GUI loads
    from modules import app_logging
    from modules import deco_client  # noqa: F401  -- RULE-LINT5: not `import modules.deco_client`,
    #                                   which collides with the `from modules.deco_client import ...`
    #                                   in f1d_deco_partial (CodeQL py/import-and-import-from)

    # Configure exactly as an entry point does (LOCALAPPDATA is already redirected to a
    # temp dir at the top of this file, so this writes nowhere the developer will find).
    # Deliberately AFTER the GUI imports above: a library that grabs root at import time
    # would be part of the real condition, and this run should see it.
    path = app_logging.configure(app_version="matrix")

    buf = io.StringIO()
    with redirect_stderr(buf):
        logging.getLogger("netsentinel.monitors").warning("%s monitor error: %s", "Availability", "boom")
        logging.getLogger("modules.notification_channels").debug("webhook delivery failed: %s", "refused")
    written = buf.getvalue()

    lines = Path(path).read_text(encoding="utf-8").splitlines() if path else []
    shaped = [ln for ln in lines if _SHAPED.match(ln) and "boom" in ln]
    header = [ln for ln in lines if "session start" in ln]
    row("F4", "log.warning reaches stderr.log with no time/level/logger; debug is dropped",
        "real-path",
        f"app.log={shaped[:1]}; header={bool(header)}; stderr got {written!r}",
        not shaped)


# ── F1a: ARP / DHCP watch errors ─────────────────────────────────────────────────

def f1a_arp_dhcp() -> None:
    def clears_dot(label):
        return lambda effects: any(
            e.startswith("_set_flyout_dot(") and repr(label) in e and "''" in e for e in effects
        ) and not any(e.startswith("_nav_set_scan_state(") for e in effects)

    run_probe_wiring("_wire_arp_watch", "F1a-ARP",
                     "ARP Spoof Watch error clears the flyout dot (reads as never-run)",
                     clears_dot("ARP Spoof Watch"))
    run_probe_wiring("_wire_dhcp_watch", "F1a-DHCP",
                     "DHCP Rogue Monitor error clears the flyout dot (reads as never-run)",
                     clears_dot("DHCP Rogue Monitor"))


# ── F1b: freshness pills ─────────────────────────────────────────────────────────

def f1b_pills() -> None:
    from ui.widgets.home_session_widgets import FreshnessStrip

    params = list(inspect.signature(FreshnessStrip.update_freshness).parameters)[1:]
    strip = FreshnessStrip()
    # S4.2 added `failing`; before it the API could not express the state at all.
    kwargs = {"failing": {"ARP": "Npcap is not installed"}} if "failing" in params else {}
    strip.update_freshness(arp=True, **kwargs)
    text = strip._fs_pill_arp.text()
    row("F1b", "Home pills are ON/OFF only -- a running-but-failing monitor shows green",
        "construct", f"update_freshness{tuple(params)}; arp=True with ARP failing renders {text!r}",
        text.startswith("●"))
    strip.deleteLater()


# ── F1c: Service Diagnostics error -> scan_complete -> "fresh"; Speed Test hidden ──

def f1c_service_diagnostics() -> None:
    try:
        from ui.pages.service_diagnostics_page import ServiceDiagnosticsPage
        page = ServiceDiagnosticsPage()
    except Exception as exc:
        row("F1c-SVC", "Service Diagnostics error emits scan_complete (app.py maps it to fresh)",
            "real-path", f"page could not be constructed: {exc!r}", None)
        return
    fired: list[str] = []
    page.scan_complete.connect(lambda: fired.append("scan_complete"))
    page._on_error("DNS resolution failed for example.invalid")
    APP.processEvents()
    wiring = (REPO / "app.py").read_text(encoding="utf-8")
    maps_to_fresh = 'scan_complete.connect(\n        lambda: window._nav_set_scan_state("Service Diagnostics", "fresh")' in wiring
    row("F1c-SVC", "Service Diagnostics error emits scan_complete (app.py maps it to fresh)",
        "real-path", f"_on_error -> {fired or 'nothing'}; app.py scan_complete->fresh wiring present={maps_to_fresh}",
        fired == ["scan_complete"] and maps_to_fresh)
    page.deleteLater()


def f1c_speed_test_hidden() -> None:
    try:
        from ui.pages.speed_test_page import SpeedTestPage
        page = SpeedTestPage()
    except Exception as exc:
        row("F1c-SPD", "Speed Test error while page hidden shows nothing, adds no history row",
            "real-path", f"page could not be constructed: {exc!r}", None)
        return
    calls: list[str] = []
    page._set_status = lambda *a, **k: calls.append("_set_status")
    page._add_history_row = lambda *a, **k: calls.append("_add_history_row")
    page._on_test_error("Ookla CLI exited with code 2")
    page.deleteLater()
    row("F1c-SPD", "Speed Test error while page hidden shows nothing, adds no history row",
        "real-path", f"isVisible={page.isVisible()} -> {calls or 'no status, no history row'}",
        calls == [])
    page.deleteLater()


# ── F1d: Deco partial client list ────────────────────────────────────────────────

def f1d_deco_partial() -> None:
    from modules.deco_client import DecoMeshClient, MeshApiError, MeshUnit

    client = DecoMeshClient("192.0.2.1", "unused")
    units = [
        MeshUnit(name="Kitchen", mac="aa:bb:cc:00:00:01", ip="", role="master", online=True),
        MeshUnit(name="Kontor", mac="aa:bb:cc:00:00:02", ip="", role="slave", online=True),
    ]

    def _request(path, payload):
        if payload["params"]["device_mac"].endswith("02"):
            raise MeshApiError("Response ended prematurely")
        return {"client_list": [{"mac": "11-22-33-44-55-66", "online": True, "name": "cGhvbmU=",
                                 "ip": "192.168.68.10", "connection_type": "band5",
                                 "up_speed": 0, "down_speed": 0}]}

    client._request = _request
    with captured_records() as records:
        try:
            result = client.get_all_clients(units=units)
        except Exception as exc:
            row("F1d", "Deco partial fetch returns a list shaped like a complete one",
                "real-path", f"get_all_clients raised {exc!r}", None)
            return
    markers = [a for a in ("partial", "failed_units", "failed_nodes") if hasattr(result, a)]
    row("F1d", "Deco partial fetch returns a list shaped like a complete one", "real-path",
        f"1 of 2 nodes failed -> {type(result).__name__} of {len(result)}, partial markers={markers}, "
        f"log={[r.getMessage()[:60] for r in records]}",
        type(result) is list and not markers)


# ── F2: background failures ──────────────────────────────────────────────────────

def f2_scheduled_speedtest() -> None:
    import app

    finding = "Scheduled speed test failure reaches no surface"
    if not hasattr(app, "_report_worker_health"):  # before S3: the page wiring was the only path
        run_probe_wiring("_wire_speedtest_scheduling", "F2-SPD", finding, lambda effects: effects == [])
        return

    from modules.app_health_catalogue import SCHEDULED_SPEED_TEST
    from workers.proactive_probe_worker import ProactiveProbeWorker

    def _probe():
        raise OSError("Ookla CLI exited with code 2")

    health = app._create_app_health()
    worker = ProactiveProbeWorker(probe=_probe, interval_s=3600)
    app._report_worker_health(health, SCHEDULED_SPEED_TEST, worker, "probe_done")  # as main() does
    errors: list[str] = []
    worker.error.connect(errors.append)
    # NOT inside redirect_stderr: this pump runs F1c-SPD's deferred SpeedTestPage deletion,
    # and doing that while sys.stderr is a StringIO invalidated this process's stdout
    # handle (WinError 6) — every later row, and MATRIX COMPLETE, then vanished. Seen only
    # in this harness (S4, 2026-09-17); mechanism not isolated.
    worker.start()
    got = wait_for(lambda: bool(errors))
    worker.stop()
    worker.wait(3000)
    raised = drawn_rows(health)
    worker.probe_done.emit(object())  # the next scheduled test succeeds
    after = drawn_rows(health)
    worker.deleteLater()
    row("F2-SPD", finding, "real-path",
        f"error={errors[:1]} -> strip rows={raised}; after the next success={after}",
        (raised is None or ("speedtest:scheduled", "Speed Test") not in raised or after != [])
        if got else None)


def f2_g6_note_and_clobber() -> None:
    import app
    from ui.monitor_state import _MonitorStateMixin

    class _Emitter(QObject):
        error = pyqtSignal(str)
        cycle_done = pyqtSignal(dict)

    finding = "Monitor error: one status note per session, overwritten by the next status write"
    if "note" not in inspect.signature(app._wire_monitor_error_surface).parameters:
        # S10.2 — the note is gone and the strip is the only surface. Same fault, same
        # progress write, as the legacy row below; the row passes when the note is absent
        # AND the strip holds the condition across the progress write.
        #
        # Keyed on the *absence* of `note` deliberately. Keyed on its presence (as this
        # was between S4.3 and S10.2, while the flag decided which path ran), deleting the
        # parameter would drop this row into the legacy branch, where it asserts a note
        # that can no longer be written — reporting REPRODUCED for the opposite reason.
        from modules.app_health_catalogue import MONITORS

        log: list = []
        emitter = _Emitter()
        health = app._create_app_health()
        app._report_worker_health(health, MONITORS["Availability"], emitter, "cycle_done")
        app._wire_monitor_error_surface(Recorder(log), {"Availability": emitter})
        with redirect_stderr(io.StringIO()):
            emitter.error.emit("database is locked")
            emitter.error.emit("database is locked")
            notes = [a[0] for p, a, _k in log if p.endswith("_set_status")]
            host = QWidget()
            host._status_bar = QStatusBar(host)
            _MonitorStateMixin._set_status(host, "Scanning 12/254 hosts…")
            shown = host._status_bar.currentMessage().strip()
            rows = drawn_rows(health)
            emitter.cycle_done.emit({})
            after = drawn_rows(health)
        row("F2-G6", finding, "real-path",
            f"2 errors -> status notes={notes}; bar after a progress write={shown!r}; "
            f"strip rows={rows}; after the next cycle={after}",
            bool(notes) or ("monitor:availability", "Availability History") not in (rows or [])
            or after != [])
        host.deleteLater()
        return

    log = []
    emitter = _Emitter()
    app._wire_monitor_error_surface(Recorder(log), {"Availability": emitter})
    with redirect_stderr(io.StringIO()):
        emitter.error.emit("database is locked")
        emitter.error.emit("database is locked")
    notes = [a[0] for p, a, _k in log if p.endswith("_set_status")]

    host = QWidget()
    host._status_bar = QStatusBar(host)
    _MonitorStateMixin._set_status(host, notes[0] if notes else "note")
    _MonitorStateMixin._set_status(host, "Scanning 12/254 hosts…")
    shown = host._status_bar.currentMessage().strip()
    row("F2-G6", finding,
        "real-path", f"2 errors -> notes={notes}; after one progress update the bar shows {shown!r}",
        len(notes) == 1 and "see log" in notes[0] and shown.startswith("Scanning"))
    host.deleteLater()


def f2_rest_api_bind() -> None:
    from workers.rest_api_worker import RestApiWorker

    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        blocker.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    port = blocker.getsockname()[1]
    import importlib.util
    import threading

    waitress = importlib.util.find_spec("waitress") is not None
    escaped: list[str] = []
    previous_hook = threading.excepthook
    threading.excepthook = lambda args: escaped.append(args.exc_type.__name__)
    worker = RestApiWorker(store=None)
    worker.set_bind("127.0.0.1", port)
    health = None
    if hasattr(worker, "report_to"):  # S3.3 — the worker raises rest_api:serve itself
        from modules.app_health import AppHealth
        health = AppHealth()
        worker.report_to(health)
    errors: list[str] = []
    worker.error.connect(errors.append)
    try:
        with redirect_stderr(io.StringIO()):
            worker.start()
            got = wait_for(lambda: bool(errors) or bool(escaped), timeout=15)
    finally:
        threading.excepthook = previous_hook
        # The QThread is still in its msleep loop. Leaving it running meant the
        # process raced os._exit(0) against a live Qt thread and exited
        # 0xC0000409 (STATUS_STACK_BUFFER_OVERRUN) instead of 0 — RULE-WIN4.
        worker.stop()
        worker.wait(3000)
        worker.deleteLater()
    server = "waitress" if waitress else "Flask dev server (waitress absent)"
    cond = health.get("rest_api:serve") if health is not None else None
    if errors:
        # S1 checked for app.py's print() handler by string match; that is gone, so the
        # row now asks the real question: did the failure become durable state? The
        # condition is not drawn until S4 — say so rather than let the flip overclaim.
        rows = drawn_rows(health) if health is not None else None
        observed = (f"{server}: error={errors[0][:70]!r} -> app-health condition="
                    f"{(cond.key, cond.why) if cond else None}; strip rows={rows}")
        # S4: raised AND drawn with a button to the REST API page (before S4 the strip
        # did not exist, so a raised condition was the most this row could ask for).
        reproduced = cond is None or (rows is not None and ("rest_api:serve", "REST API") not in rows)
    elif escaped:
        # werkzeug calls sys.exit(1) on a failed bind; SystemExit is not an Exception, so
        # _serve's handlers miss it and crash_net's thread hook deliberately ignores it.
        observed = f"{server}: NO error signal; {escaped[0]} escaped the rest-api-server thread"
        reproduced = True
    else:
        observed = f"{server}: nothing within 15 s"
        reproduced = None
    row("F2-REST", "REST API bind failure reaches no surface", "real-path",
        f"port {port} occupied -> {observed}", reproduced if got else None)
    blocker.close()


def f2_webhook_failure() -> None:
    from modules.alert_types import AlertFired
    from modules.notification_router import NotificationRouter, WebhookChannel

    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    closed = probe.getsockname()[1]
    probe.close()
    channel = WebhookChannel(enabled=True, url=f"http://127.0.0.1:{closed}/hook", min_severity="INFO")
    alert = AlertFired(rule_name="Gateway down", rule_type="HOST_DOWN", host="192.168.1.1",
                       message="Gateway stopped answering", severity="CRITICAL", ts=int(time.time()))
    try:
        router = NotificationRouter()
    except Exception as exc:
        row("F2-HOOK", "Webhook delivery failure is visible only in the in-memory delivery log",
            "real-path", f"router could not be constructed: {exc!r}", None)
        return
    health = None
    deliveries = 1
    if hasattr(router, "set_app_health"):  # S3.3: a condition after N consecutive failures
        from modules.app_health import AppHealth
        from modules.notification_router import _CONDITION_AFTER_FAILURES

        health = AppHealth()
        router.set_app_health(health)
        deliveries = _CONDITION_AFTER_FAILURES
    hook_key = f"notify:{channel.name}"
    with captured_records() as records:
        for _ in range(deliveries):
            router._deliver(channel, alert)
        # Wait for what the verdict reads, not only the FAILED status: _mark_failed sets the
        # status under its lock and only then, outside it, raises the condition and logs.
        # Stopping at the third FAILED raced the delivery thread (S5: one spurious REPRODUCED).
        # A genuine regression still ends here — as a timeout, then REPRODUCED.
        wait_for(lambda: sum(e.get("status") == "FAILED" for e in router.get_delivery_log()) >= deliveries
                 and bool(records) and (health is None or health.get(hook_key) is not None),
                 timeout=10 * deliveries)
    log_entries = [(e.get("channel") or e.get("name"), e.get("status")) for e in router.get_delivery_log()]
    rows = drawn_rows(health) if health is not None else None
    hook_row = (hook_key, "Notifications")
    row("F2-HOOK", "Webhook delivery failure is visible only in the in-memory delivery log",
        "real-path", f"delivery log={log_entries}; records reaching any handler="
                     f"{[r.getMessage()[:60] for r in records][:2]}; strip rows={rows}",
        (any(s == "FAILED" for _c, s in log_entries) and not records)
        or (rows is not None and hook_row not in rows))


def f2_keyring_write() -> None:
    import keyring
    from keyring.backends.fail import Keyring as FailKeyring

    import ui.pages.mqtt_page as mqtt_page

    original = keyring.get_keyring()
    keyring.set_keyring(FailKeyring())
    try:
        with captured_records() as records:
            raised = None
            try:
                mqtt_page._set_secret("hunter2")
            except Exception as exc:
                raised = exc
            read_back = mqtt_page._get_secret()
    finally:
        keyring.set_keyring(original)
    row("F2-KEY", "MQTT password save fails silently when the keyring backend fails", "real-path",
        f"_set_secret raised={raised!r}; _get_secret()={read_back!r}; records={len(records)}",
        raised is None and read_back == "" and not records)


# ── F6: toasts ───────────────────────────────────────────────────────────────────

def f6_toasts() -> None:
    from ui import styles as _s
    from ui.widgets.toast import ToastManager

    ToastManager._inst = None
    ToastManager.show("Save failed", "error")
    dropped = len(ToastManager.instance()._toasts) == 0

    parent = QWidget()
    parent.resize(900, 700)
    mgr = ToastManager.instance()
    mgr.attach(parent)
    ToastManager.show("Scan complete — Grade dropped from B to C", "warning")
    toast = mgr._toasts[-1]
    sheet = toast.styleSheet()
    timers = [t for t in toast.findChildren(QTimer) if t.isActive() and t.isSingleShot()]
    renders_as_info = f"border-left:3px solid {_s.ACCENT}" in sheet and _s.AMBER not in sheet
    row("F6-WARN", "Toast kind 'warning' renders as a sticky info toast", "real-path",
        f"accent border={renders_as_info}; auto-dismiss timers={len(timers)}",
        renders_as_info and not timers)

    for t in list(mgr._toasts):
        mgr._remove_toast(t)
    ToastManager.show("Export failed — disk full", "error")
    error_toast = mgr._toasts[-1]
    for i in range(3):
        ToastManager.show(f"Saved {i}", "success")
    evicted = error_toast not in mgr._toasts
    row("F6-EVICT", "A 4th toast silently evicts a sticky error toast; toasts before attach() vanish",
        "real-path", f"error evicted={evicted}; pre-attach toast dropped={dropped}",
        evicted and dropped)
    parent.deleteLater()


# ── F5: raw worker text as the message (S5) ─────────────────────────────────────

def f5_raw_worker_error_text() -> None:
    """The real SNMP trap and DNS zone error slots, handed a Swedish OS error.

    Before S5 both put the worker string into the label ("⚠ {msg}" / "failed — {msg}. …").
    After S5 the label carries fixed what/why/next text and the raw string is detail only.
    """
    finding = "A worker error string is shown to the user as the message itself (RULE-A2)"
    raw = "[WinError 10048] Endast en användning av varje socketadress är normalt tillåten"
    try:
        from ui.pages.dns_zone_page import DnsZonePage
        from ui.pages.snmp_trap_page import SnmpTrapPage
        pages = [("SNMP trap", SnmpTrapPage()), ("DNS zone", DnsZonePage())]
    except Exception as exc:
        row("F5", finding, "real-path", f"pages could not be constructed: {exc!r}", None)
        return
    pages[0][1].on_error(raw)
    pages[1][1]._on_error(raw)
    APP.processEvents()
    shown = {name: page._status_lbl.text() for name, page in pages}
    leaked = [name for name, text in shown.items() if "socketadress" in text]
    row("F5", finding, "real-path",
        f"raw text in label: {leaked or 'none'}; labels={shown}", bool(leaked))
    for _name, page in pages:
        page.deleteLater()


# ── F6-EXPORT / F6-SUCCESS: saves and copies (S6) ────────────────────────────────

@contextmanager
def _patched(owner, name, value):
    original = getattr(owner, name)
    setattr(owner, name, value)
    try:
        yield
    finally:
        setattr(owner, name, original)


def f6_export_and_success() -> None:
    """The real CVE export into a folder that does not exist, and a real successful copy.

    Before S6 the export toast was ``Export failed: [Errno 2] …`` with no next step, and the copy's
    confirmation called ``ToastManager.instance().show_toast`` — which never existed — inside its
    ``try``, so a successful copy showed a "Copy Failed" dialog.
    """
    from PyQt6.QtWidgets import QFileDialog, QMessageBox
    from ui.pages.cve_page import CvePage
    from ui.pages.reports_page import ReportsPage
    from ui.widgets.toast import ToastManager
    import modules.report_scheduler as report_scheduler

    shown: list = []

    def _record(cls, message, kind="info", *args, **kwargs):
        shown.append((message, kind, kwargs.get("action_label", "")))

    target = Path(tempfile.mkdtemp(prefix="ns-matrix-export-")) / "gone" / "cve.csv"
    host = QWidget()
    host._rows = [{"cve_id": "CVE-2026-0001"}]
    host._export_csv = lambda: None
    with _patched(ToastManager, "show", classmethod(_record)), \
            _patched(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), ""))):
        CvePage._export_csv(host)
    message, kind, action = shown[-1] if shown else ("", "", "")
    raw_in_message = "Errno" in message or "cve.csv" in message
    row("F6-EXPORT", "A failed save shows the raw exception with no next step (RULE-A2)", "real-path",
        f"toast={message!r}; kind={kind}; action={action!r}", raw_in_message or not action)

    modals: list = []
    host2 = QWidget()
    host2._store = object()
    shown.clear()
    with _patched(ToastManager, "show", classmethod(_record)), \
            _patched(QMessageBox, "warning", staticmethod(lambda *a, **k: modals.append(a[1:]))), \
            _patched(report_scheduler, "generate_status_report", lambda store: "summary"):
        ReportsPage._copy_summary(host2)
    row("F6-SUCCESS", "A successful copy is reported as failed (RULE-SURF1 inverse)", "real-path",
        f"failure dialogs={modals}; toasts={[k for _m, k, _a in shown]}", bool(modals))
    host.deleteLater()
    host2.deleteLater()


# ── F6b-DB / F6b-UPD: labels and the update check (S6b) ─────────────────────────

def f6b_database_lock() -> None:
    """The real Home Automation save, through a real MetricStore, while another connection holds a
    real exclusive lock on the same database.

    Before S6b the label read ``⚠  Save failed: database is locked``. After it, the label names the
    busy database and what to do, and the raw text is detail. Slow by design: the store's own
    ``busy_timeout`` (5 s) runs out before the write raises.
    """
    import sqlite3

    import ui.pages.home_automation_page as ha
    from modules.metric_store import MetricStore
    from PyQt6.QtWidgets import QDialog

    finding = "A database failure is shown as the raw sqlite text (RULE-A2)"
    folder = Path(tempfile.mkdtemp(prefix="ns-matrix-db-"))
    store = MetricStore(db_path=folder / "ha.db")
    page = ha.HomeAutomationPage(store=store)

    class _Dialog:
        def __init__(self, *_a, **_k):
            pass

        def values(self):
            return {"room": "Kitchen"}

    holder = sqlite3.connect(str(folder / "ha.db"))
    holder.execute("BEGIN EXCLUSIVE")
    try:
        with _patched(ha, "_DeviceEditDialog", _Dialog), \
                _patched(ha, "run_dialog", lambda dlg: QDialog.DialogCode.Accepted):
            page._open_edit_dialog({"mac": "aa:bb:cc:dd:ee:ff"})
    finally:
        holder.rollback()
        holder.close()
    text = page._status_lbl.text()
    row("F6b-DB", finding, "real-path", f"label={text!r}", "locked" in text)
    page.deleteLater()
    store.close()


def f6b_update_check_blocks() -> None:
    """The real Help-tab update check with a request that takes 1.5 s.

    Before S6b ``urlopen`` ran on the GUI thread, so the click returned only when the request did.
    """
    import threading
    import urllib.error
    import urllib.request

    import modules.utils
    from PyQt6.QtWidgets import QLabel
    from ui.tabs_help import _HelpTabsMixin

    finding = "The update check freezes the window for as long as the request takes (RULE 4)"
    release = threading.Event()

    def _slow(*_a, **_k):
        release.wait(1.5)
        raise urllib.error.URLError("matrix: no network")

    class _Host(QWidget, _HelpTabsMixin):
        def _on_update_available(self, latest):
            pass

    host = _Host()
    host._update_lbl = QLabel("", host)
    with _patched(modules.utils, "is_store_app", lambda: False), _patched(urllib.request, "urlopen", _slow):
        t0 = time.monotonic()
        host._check_for_updates()
        blocked_s = time.monotonic() - t0
        release.set()
        worker = getattr(host, "_update_check_worker", None)
        if worker is not None:
            worker.wait(5000)
            APP.processEvents()
    row("F6b-UPD", finding, "real-path",
        f"click returned after {blocked_s:.2f}s; label={host._update_lbl.text()!r}", blocked_s >= 1.0)
    host.deleteLater()


# ── IOT-THREAD: IoT Behaviour's background thread (RULE-WIN27) ──────────────────

def iot_learn_thread() -> None:
    """The real IoT Learn path with no capture driver: scapy's own ``_NotAvailableSocket`` as
    ``conf.L2listen``, which is what scapy installs when Npcap is missing (measured 2026-09-18).

    Before the fix the ``threading.Thread`` wrote the status label itself, and the RuntimeError
    escaped it, so the page read "Learning for 30 s…" for good. A spy records each write's thread
    and forwards only GUI-thread writes, so the row observes a cross-thread write without making it.
    The baseline path is a temp file; the failing sniff raises before anything is saved anyway.
    """
    import modules.iot_baseline as ib
    from PyQt6.QtCore import QThread
    from scapy.arch.windows import _NotAvailableSocket
    from scapy.config import conf
    from ui.tabs_analysis import _AnalysisTabsMixin

    finding = "IoT Learn writes widgets from a threading.Thread; a failed learn reads as still learning"

    class _Host(_AnalysisTabsMixin, QWidget):
        _iot_progress = pyqtSignal(int, str)
        _iot_ready = pyqtSignal(int, object)
        _iot_failed = pyqtSignal(int, object)

    host = _Host()
    host._m1_result = {"devices": [{"ip": "192.0.2.10", "mac": "aa:bb:cc:dd:ee:10", "device_type": "Smart TV"}]}
    tab = host._build_iot_baseline_tab()
    host._iot_learn_duration.setValue(30)
    label = host._iot_status
    real_set = label.setText
    off_thread: list = []

    def _spy(text):
        if QThread.currentThread() == APP.thread():
            real_set(text)
        else:
            off_thread.append(text)

    label.setText = _spy
    baseline = Path(tempfile.mkdtemp(prefix="ns-matrix-iot-")) / "iot_baseline.json"
    # Wait for a final state, not the first change: the progress line ("Learning baselines for…")
    # lands before the failure does, and stopping there read a still-learning label as fixed.
    with _patched(conf, "L2listen", _NotAvailableSocket), _patched(ib, "_DEFAULT_BASELINE_PATH", baseline):
        host._run_iot_learn()
        wait_for(lambda: not label.text().startswith("Learning"), timeout=3.0)
    text = label.text()
    row("IOT-THREAD", finding, "real-path", f"off-thread writes={len(off_thread)}; label={text!r}",
        bool(off_thread) or text.startswith("Learning"))
    tab.deleteLater()
    host.deleteLater()


# ── S7: detection modules that report a probe that never ran as a clean result ──

def _dns_name(name: str) -> bytes:
    return b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00"


def _axfr_zone_message(domain: str) -> bytes:
    """One length-prefixed AXFR response: SOA, A, SOA — a complete two-record zone."""
    import struct

    owner = _dns_name(domain)
    soa = _dns_name(f"ns1.{domain}") + _dns_name(f"admin.{domain}") + struct.pack(">IIIII", 1, 3600, 600, 86400, 300)

    def rr(rtype: int, rdata: bytes) -> bytes:
        return owner + struct.pack(">HHIH", rtype, 1, 300, len(rdata)) + rdata

    body = (struct.pack(">HHHHHH", 1, 0x8400, 1, 3, 0, 0) + owner + struct.pack(">HH", 252, 1)
            + rr(6, soa) + rr(1, socket.inet_aton("192.0.2.10")) + rr(6, soa))
    return struct.pack(">H", len(body)) + body


@contextmanager
def fake_axfr_server(host: str, domain: str):
    """A TCP DNS server on *host*:53 that answers any query with a complete zone and then
    keeps the connection open, as RFC 7766 lets a server do. `axfr_transfer` hard-codes
    port 53, so the fake needs a loopback address of its own."""
    import threading

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind((host, 53))
    srv.listen(1)
    srv.settimeout(0.2)
    stop = threading.Event()

    def _serve() -> None:
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with conn:
                conn.recv(4096)
                conn.sendall(_axfr_zone_message(domain))
                stop.wait()   # hold the connection until the row is done

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(2.0)
        srv.close()


def _run_dns_zone_axfr(server: str, domain: str) -> tuple[list, str, str, object]:
    """The real DNS Zone Map page's AXFR button. Returns (signals, label, AXFR KPI, page)."""
    from PyQt6.QtWidgets import QLabel
    from ui.pages.dns_zone_page import DnsZonePage

    page = DnsZonePage()
    fired: list = []
    page.scan_complete.connect(lambda v: fired.append(("scan_complete", v)))
    page.scan_failed.connect(lambda v: fired.append(("scan_failed", v)))
    not_testable = getattr(page, "scan_not_testable", None)   # S7
    if not_testable is not None:
        not_testable.connect(lambda v: fired.append(("scan_not_testable", v)))
    page._server_field.setText(server)
    page._domain_field.setText(domain)
    page._run_axfr()
    wait_for(lambda: bool(fired), timeout=25.0)   # a final state, not the first progress line
    if page._worker is not None:
        page._worker.wait(5000)
    APP.processEvents()
    records = page._kpi_records.findChild(QLabel, "kpi_value").text()
    return fired, page._status_lbl.text(), records, page


def dns_axfr_unreachable() -> None:
    """The real AXFR button against 127.0.0.3, where nothing listens on 53.

    Before S7 `axfr_transfer` swallowed the refused connection and returned [], and the page
    said "No DNS zone data found. Try providing a DNS server for AXFR." — the server the user
    just provided — and emitted scan_complete, which the registry maps to "fresh".
    """
    finding = "An unreachable AXFR server reads as 'no zone data — try providing a server'"
    fired, text, _records, page = _run_dns_zone_axfr("127.0.0.3", "matrix.test")
    kinds = [k for k, _v in fired]
    row("B1-UNREACH", finding, "real-path", f"signals={kinds}; label={text!r}",
        "scan_complete" in kinds or "Could not reach" not in text)
    page.deleteLater()


def dns_axfr_held_open() -> None:
    """The real AXFR button against a fake server that sends a complete zone (SOA, A, SOA)
    and keeps the TCP connection open.

    Before S7 the recv loop read to EOF, the page's 10 s timeout raised before the parse, and
    the complete zone was discarded: 0 records — an open zone transfer read as no data.
    """
    finding = "A complete zone from a server that holds the connection open is discarded"
    with fake_axfr_server("127.0.0.2", "matrix.test"):
        fired, text, records, page = _run_dns_zone_axfr("127.0.0.2", "matrix.test")
    row("B1-HOLD", finding, "real-path", f"records={records}; signals={[k for k, _v in fired]}; label={text!r}",
        records != "2")
    page.deleteLater()


def discovery_methods_failed() -> None:
    """The real Full Device Discovery with scapy's own no-Npcap sockets: `_NotAvailableSocket`
    at layer 2 and the native `L3WinSocket` at layer 3 (what scapy installs when Npcap is
    missing — measured 2026-09-19), which raises without elevation. 127.0.0.0/30 keeps every
    active probe on loopback; the ARP cache read is the real one.

    Before S7 both failures were swallowed: "Found N device(s) … using: arp-cache, icmp-ping"
    and the registry went "fresh", with nothing saying the two most complete methods never ran.
    """
    import ctypes

    import modules.combined_discovery as cd
    from scapy.arch.windows import _NotAvailableSocket
    from scapy.arch.windows.native import L3WinSocket
    from scapy.config import conf

    finding = "ARP sweep / TCP SYN that cannot run (no Npcap) vanish from a 'Found N device(s)' verdict"
    if ctypes.windll.shell32.IsUserAnAdmin():
        row("B3", finding, "real-path", "elevated shell: L3WinSocket would work, so no fault to inject", None)
        return
    with _patched(conf, "L2socket", _NotAvailableSocket), _patched(conf, "L3socket", L3WinSocket):
        res = cd.discover(cidr="127.0.0.0/30", resolve_hostnames=False, timeout=1.0)
    failed = getattr(res, "methods_failed", None)
    verdict = res.plain_verdict
    row("B3", finding, "real-path",
        f"devices={res.count}; used={res.methods_used}; failed={failed}; verdict={verdict!r}",
        res.count > 0 and not failed)


_NET_VIEW_TABLE = (
    "Shared resources at \\\\127.0.0.2\n\n\n\n"
    "Share name  Type  Used as  Comment\n\n"
    "-------------------------------------------------------------------------------\n"
    "Public      Disk\n"
    "The command completed successfully.\n\n"
)


def smb_login_failed() -> None:
    """The real credentialed SMB enumeration, whose `net use` login fails. Faked through
    `subprocess` — no login is attempted: `net use` exits 2 (net.exe's error exit, e.g.
    System error 1326), `net view` / `net localgroup` answer as the scanner's own account.

    Before S7 `_run` swallowed the failed login and every later `net` command ran as the
    scanner's own Windows account, so the result was tier 2, no error, not_testable False.
    """
    import subprocess

    import modules.smb_enumerator as smb

    finding = "A failed SMB login is swallowed; the scanner's own view is reported as the target's"

    def _net(cmd, **_kw):
        if cmd[:2] == ["net", "view"]:
            return _NET_VIEW_TABLE
        if cmd[:2] == ["net", "localgroup"]:
            return "-----\n*Administrators\n*Users\nThe command completed successfully.\n"
        raise subprocess.CalledProcessError(2, cmd[:2])   # the login, and the /delete after it

    with _patched(smb.subprocess, "check_output", _net):
        res = smb.enumerate_smb("127.0.0.2", username="matrix", password="not-a-password", timeout=1.0)
    row("B4", finding, "real-path",
        f"tier={res.tier}; not_testable={res.not_testable}; error={res.error!r}; "
        f"shares={[s.name for s in res.shares]}; groups={res.local_groups}",
        not res.not_testable)


def smb_not_testable_green() -> None:
    """The real Tier-1 SMB enumeration of 127.0.0.2 with `net view` exiting 2 (what an
    unreachable host does, measured), then the real `_on_smb_result`.

    Before S7 the result was not_testable, but `plain_verdict` ignored it and the handler
    painted the "Machine: … · 0 share(s)" line GREEN because there were no risk flags.
    """
    import subprocess

    import modules.smb_enumerator as smb
    from PyQt6.QtWidgets import QLabel, QTableWidget
    from ui import styles as _s
    from ui.scan_enrichment import ScanEnrichmentMixin

    finding = "An SMB host that could not be tested is painted as a green, clean result"

    def _net(cmd, **_kw):
        raise subprocess.CalledProcessError(2, cmd[:2])

    with _patched(smb.subprocess, "check_output", _net):
        res = smb.enumerate_smb("127.0.0.2", timeout=1.0)

    class _Host(ScanEnrichmentMixin, QWidget):
        pass

    host = _Host()
    host._smb_verdict = QLabel(host)
    host._smb_status = QLabel(host)
    host._recon_smb_shares_table = QTableWidget(0, 4, host)
    host._recon_smb_users_table = QTableWidget(0, 4, host)
    states: list = []
    host._nav_set_scan_state = lambda label, state, **_kw: states.append(state)
    host._on_smb_result(res)
    text = host._smb_verdict.text()
    green = f"color:{_s.GREEN}" in host._smb_verdict.styleSheet()
    row("B4a", finding, "real-path",
        f"not_testable={res.not_testable}; registry={states}; green={green}; verdict={text!r}",
        green or "could not test" not in text.lower())
    host.deleteLater()


# ── S8: UI refresh paths and grading inputs ──────────────────────────────────

@contextmanager
def _toasts():
    """Collect the toasts a real code path raises.

    The toast is the surface these rows are about, so they must observe it rather than a
    log record: `captured_records()` filters at production level, and a `log.debug`
    companion to a toast is dropped there — which would read as silence even after the
    surface exists.
    """
    from ui.widgets.toast import ToastManager

    shown: list = []

    def _record(_cls, message, kind="info", *_a, **_kw):
        shown.append((message, kind))

    with _patched(ToastManager, "show", classmethod(_record)):
        yield shown

def _s8_store():
    """A real MetricStore holding exactly the rows S8's readers claim to read.

    192.168.1.10 is DOWN for half of the last 24 h (uptime 50 %). 192.168.1.20 was last
    seen 10 days ago, so it exists in the 720 h window and is None in the 24 h / 168 h
    ones — the shape that decides B11. One grade and one JOINED event are recorded.
    """
    import tempfile as _tf
    from pathlib import Path as _P

    from modules.metric_store import MetricStore

    st = MetricStore(db_path=_P(_tf.mkdtemp(prefix="ns-s8-")) / "m.db", prune_on_init=False)
    now = int(time.time())
    for i in range(20):
        st.record_device_state("192.168.1.10", "aa:bb:cc:00:00:10", "nas",
                               "UP" if i % 2 else "DOWN", 5.0, ts=now - i * 300)
    st.record_device_state("192.168.1.20", None, "old-tv", "UP", 4.0, ts=now - 10 * 86400)
    for i in range(10):
        st.record_rtt("192.168.1.1", 12.0, ts=now - i * 60)
    st.record_device_event("192.168.1.50", "JOINED", mac="aa:bb:cc:00:00:50", ts=now - 3600)
    st.record_grade("B", 82.0, "measured")
    return st


def s8_health_availability() -> None:
    """The real HealthScoreCalculator over a real store where one device was down half the day.

    Before S8 `_availability_score` read `row["24h"]` while `query_uptime_table` emits
    `str(24.0)`, so the heaviest input (weight 0.45) was never read and always took its
    optimistic 80.0 default — and the red-state "some devices are unreachable" headline,
    guarded by `avail_score is not None`, could never be reached.
    """
    from modules.health_score import HealthScoreCalculator

    st = _s8_store()
    calc = HealthScoreCalculator()
    table = calc and st.query_uptime_table(hours_list=[24.0])
    avail = calc._availability_score(st)
    snap = calc.compute(st)
    st.close()
    row("B8", "availability never reaches the health score; a half-down device still reads green",
        "real-path",
        f"table={table}; availability={avail}; score={snap.score} state={snap.state!r}; "
        f"headline={snap.headline!r}",
        avail is None and bool(table))


def s8_digest_grade() -> None:
    """The real weekly-digest Grade tile against a store that has a recorded grade.

    Before S8 `_grade_kpi` called `store.get_grade_result()` — a method that has never
    existed on MetricStore (`query_last_grade()` is the accessor) — and the AttributeError
    was swallowed, so the tile was permanently "—".
    """
    from modules import digest_builder as _db

    st = _s8_store()
    tile = _db._grade_kpi(st)
    stored = st.query_last_grade()
    st.close()
    row("B9", "weekly digest Grade tile is permanently '—' (reader calls a method that never existed)",
        "real-path", f"stored={stored}; tile={tile!r}",
        stored is not None and "—" in tile)


def s8_digest_new_devices() -> None:
    """The real digest new-device tile and table against recorded JOINED events.

    Before S8 both filtered `event_type in ("join", "new")`; `record_device_event` only
    accepts the vocabulary `JOINED / LEFT / UP / DOWN / DEGRADED / RECOVERED`, so the
    digest reported 0 new devices every week.
    """
    from modules import digest_builder as _db

    st = _s8_store()
    kpi = _db._new_device_kpi(st)
    tbl = _db._new_devices_table(st)
    events = [e.event_type for e in st.query_device_events(hours=168)]
    st.close()
    row("B10", "weekly digest always reports 0 new devices (filters 'join'/'new'; vocabulary is 'JOINED')",
        "real-path", f"events={events}; kpi={kpi!r}; table={tbl[:64]!r}",
        bool(events) and ">0<" in kpi)


def s8_digest_uptime_table() -> None:
    """The real digest uptime table with one device last seen 10 days ago.

    Before S8 `r.get("168.0", r.get("24.0", 100.0))` returned None for that device — `.get`
    falls back on a *missing* key, not a present None — and `None >= 99` raised TypeError,
    collapsing the whole table into "Uptime data unavailable."
    """
    from modules import digest_builder as _db

    st = _s8_store()
    rows_ = st.query_uptime_table()
    tbl = _db._uptime_table(st)
    st.close()
    row("B11", "one device outside the 7-day window collapses the entire digest uptime table",
        "real-path", f"rows={rows_}; table={tbl[:72]!r}",
        bool(rows_) and "unavailable" in tbl)


class _AckHost(QWidget):
    """Minimal concrete host for the real _HomeDataMixin acknowledgement methods."""

    alerts_acknowledged = pyqtSignal()

    def __init__(self, store) -> None:
        from PyQt6.QtWidgets import QVBoxLayout

        super().__init__()
        self._store = store
        self._ac_alert_rows_lay = QVBoxLayout(self)
        for name in ("_ac_alert_rows_widget", "_ac_view_all_btn", "_ac_count_lbl",
                     "_ac_ack_all_btn", "_action_card"):
            setattr(self, name, QWidget(self))

    def set_pending_alert_rows(self, alerts: list) -> None:
        self.pending_set_to = alerts


class _AckRow(QWidget):
    """Records whether the UI hid and destroyed it, whatever the store did."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.hidden_by_ui = False
        self.deleted_by_ui = False

    def setVisible(self, visible: bool) -> None:  # noqa: N802
        if not visible:
            self.hidden_by_ui = True
        super().setVisible(visible)

    def deleteLater(self) -> None:  # noqa: N802
        self.deleted_by_ui = True
        super().deleteLater()


def s8_ack_row_asserts_success() -> None:
    """The real `_ack_alert_row` whose store refuses the write.

    Before S8 the row was hidden and deleteLater()'d unconditionally, so a failed
    acknowledgement looked exactly like a successful one — and the row reappeared at the
    next 30 s refresh with no explanation.
    """
    from ui.pages.home_data_mixin import _HomeDataMixin

    class _Store:
        def acknowledge_alert(self, _id):
            raise RuntimeError("database is locked")

    class _Host(_AckHost, _HomeDataMixin):
        pass

    host = _Host(_Store())
    rw = _AckRow(host)
    host._ac_alert_rows_lay.addWidget(rw)
    with _toasts() as shown:
        host._ack_alert_row(7, rw)
    row("B12-ROW", "a failed acknowledgement hides and destroys the row exactly like a successful one",
        "real-path",
        f"hidden={rw.hidden_by_ui}; deleted={rw.deleted_by_ui}; toasts={shown}",
        rw.hidden_by_ui and rw.deleted_by_ui and not shown)


def s8_undo_ack_silent() -> None:
    """The real `_undo_ack_all` whose store refuses the write.

    Before S8 it returned silently, so the Undo affordance on the acknowledgement toast
    reported success it had not delivered: the alerts stayed acknowledged.
    """
    from ui.pages.home_data_mixin import _HomeDataMixin

    class _Store:
        def unacknowledge_alerts(self, _ids):
            raise RuntimeError("database is locked")

    class _Host(_AckHost, _HomeDataMixin):
        pass

    host = _Host(_Store())
    fired = []
    host.alerts_acknowledged.connect(lambda: fired.append(1))
    with _toasts() as shown:
        host._undo_ack_all([1, 2, 3])
    row("B12-UNDO", "Undo on the acknowledgement toast silently does nothing when the write fails",
        "real-path",
        f"signal_emitted={bool(fired)}; pending_rows_repopulated={hasattr(host, 'pending_set_to')}; "
        f"toasts={shown}",
        not fired and not shown)


def s8_annotation_save_silent() -> None:
    """The real device-drawer annotation save whose write raises.

    Before S8 the exception was swallowed, so a user's label / location / owner / asset tag /
    notes were discarded with the drawer behaving exactly as if they had been stored.
    """
    import modules.device_tracker as dt
    from ui.pages.inventory_page import _DeviceDrawer

    def _boom(*_a, **_kw):
        raise RuntimeError("database is locked")

    host = QWidget()
    drawer = _DeviceDrawer(host)
    drawer._current_mac = "aa:bb:cc:00:00:10"
    drawer._current_store = object()
    drawer._ann_label.setText("Living Room TV")
    drawer._ann_notes.setPlainText("bought 2024")
    with _patched(dt, "save_annotations", _boom), _toasts() as shown:
        drawer._save_annotations()
    row("B13-ANN", "a device annotation that failed to save is discarded with no indication",
        "real-path", f"label={drawer._ann_label.text()!r}; toasts={shown}",
        not shown)


def s8_scheduled_scan_silent() -> None:
    """The real `_check_scheduled_scan` whose `_start_scan()` raises.

    QSettings is faked in-process: the production call is `QSettings("NetSentinel",
    "NetSentinel")`, which reads the developer's own registry, and this row writes
    `sched_scan/next_ts`.

    Before S8 next_ts was advanced *before* the scan was attempted and the failure was
    swallowed, so a scheduled scan that never ran rolled silently forward to its next window.
    """
    import ui.dashboard as dash

    store: dict = {"sched_scan/enabled": True, "sched_scan/next_ts": time.time() - 60,
                   "sched_scan/hour": 2, "sched_scan/minute": 0,
                   "sched_scan/interval_hours": 24}

    class _FakeQSettings:
        def __init__(self, *_a, **_kw) -> None:
            pass

        def value(self, key, default=None, *_a, **_kw):
            return store.get(key, default)

        def setValue(self, key, value) -> None:  # noqa: N802
            store[key] = value

    class _Self:
        def _start_scan(self):
            raise RuntimeError("scan worker could not start")

    before = store["sched_scan/next_ts"]
    with _patched(dash, "QSettings", _FakeQSettings), captured_records() as records:
        dash.Dashboard._check_scheduled_scan(_Self())
    surfaced = [r.getMessage() for r in records]
    advanced = store["sched_scan/next_ts"] != before
    row("B14", "a scheduled scan that failed to start rolls silently forward to the next window",
        "real-path", f"next_ts_advanced={advanced}; records={surfaced}",
        advanced and not surfaced)


# ── S9 / S10: consistency, and the surfaces a headless run leaves behind ────────

#: Unrecognised plugin failure text, localized by Windows exactly as a user would get it
#: (sv-SE WinError 10060). ``plugin_error_text`` returns None for it, so the dialog falls
#: through to ``show_worker_error`` -- the other of the two branches S9-GLYPH compares.
_UNCLASSIFIED_PLUGIN_ERROR = (
    "[WinError 10060] Ett anslutningsforsok misslyckades eftersom den anslutna parten "
    "inte svarade korrekt efter en viss tidsperiod"
)


@contextmanager
def _modals():
    """Collect the modal dialogs a real code path raises.

    Companion to ``_toasts()``: S9.2 is about which of the two channels a site uses, so a
    row has to watch both at once or it cannot tell a converted site from a silent one.
    """
    from PyQt6.QtWidgets import QMessageBox

    raised: list = []

    def _record(kind):
        def _fn(*args, **_kw):
            raised.append((kind, args[1] if len(args) > 1 else ""))
            return QMessageBox.StandardButton.Ok
        return staticmethod(_fn)

    with _patched(QMessageBox, "information", _record("information")), \
            _patched(QMessageBox, "warning", _record("warning")):
        yield raised


def s9_storm_tile_vocabulary() -> None:
    """The real Monitor Overview storm tile at each of the three levels.

    The Broadcast Storm page writes ``risk_to_label(level)`` ("Needs attention"); this tile
    writes the internal risk vocabulary straight at the user -- F8 flagged "Warn", and
    "Storm"/"Clean" are the same class. The architecture reference is explicit that the
    internal levels never reach a user as a label.
    """
    from ui.pages.monitor_overview_page import MonitorOverviewPage

    internal = {"STORM", "WARN", "WARNING", "CLEAN"}
    page = MonitorOverviewPage()
    drawn: dict = {}
    for level in ("STORM", "WARNING", "CLEAN"):
        page.set_storm_status(level)
        drawn[level] = (page._tile_storm._value_lbl.text(), page._tile_storm._sub_lbl.text())
    leaked = sorted({v.upper() for v, _sub in drawn.values()} & internal)
    row("S9-STORM", "the Monitor Overview storm tile shows the internal risk vocabulary",
        "real-path", f"drawn={drawn}; internal tokens={leaked}", bool(leaked))
    page.deleteLater()


def s9_credential_dialog_glyph() -> None:
    """The real credential dialog failing twice: once with text it recognises, once without.

    Both are the same failure of the same button. The recognised branch writes its own
    string, the unrecognised one goes through ``show_worker_error`` -- and the two disagree
    about which glyph a failure carries.
    """
    import keyring
    from PyQt6.QtWidgets import QDialog, QLabel, QLineEdit, QPushButton
    import ui.widgets.credential_dialog as cd

    class _FakeTester(QObject):
        success = pyqtSignal(dict)
        failure = pyqtSignal(str)
        message = ""

        def __init__(self, *_a, **_kw) -> None:
            super().__init__()

        def start(self) -> None:
            self.failure.emit(type(self).message)

        def isRunning(self) -> bool:  # noqa: N802 - QThread's name, read by the dialog
            return False

        def wait(self, *_a) -> bool:
            return True

    seen: list = []

    def _drive(dlg):
        ip_edit, pw_edit = dlg.findChildren(QLineEdit)[:2]
        ip_edit.setText("192.168.1.1")
        pw_edit.setText("secret")
        next(b for b in dlg.findChildren(QPushButton) if b.text() == "Test & Add").click()
        for _ in range(6):
            APP.processEvents()
        seen.extend(
            lbl.text().strip() for lbl in dlg.findChildren(QLabel)
            if lbl.wordWrap() and lbl.text().strip() and not lbl.text().strip()[0].isalnum()
        )
        dlg.deleteLater()
        return QDialog.DialogCode.Rejected

    parent = QWidget()
    with _patched(cd, "_PluginConnectionTester", _FakeTester), \
            _patched(cd, "run_dialog", _drive), \
            _patched(keyring, "delete_password", lambda *_a: None):
        for message in ("AUTH: bad password", _UNCLASSIFIED_PLUGIN_ERROR):
            _FakeTester.message = message
            cd.show_credential_dialog(parent, "Modem", "192.168.1.1", "Password")

    glyphs = sorted({t[0] for t in seen})
    row("S9-GLYPH", "one dialog gives the same connection failure two different glyphs",
        "real-path", f"status texts={seen}; leading glyphs={glyphs}", len(glyphs) > 1)
    parent.deleteLater()


def s9_pdf_export_success_modal() -> None:
    """The real ``ReportsPage._export_pdf`` on a PDF that saves.

    Its own neighbour ``_copy_summary`` confirms with a success toast (S6.0), and so does
    every other export in the app. This one stops the user with a modal for a non-decision.
    """
    from PyQt6.QtWidgets import QFileDialog, QListWidget, QPushButton
    import modules.report_exporter as report_exporter
    from ui.pages.reports_page import ReportsPage

    target = Path(tempfile.mkdtemp(prefix="ns-matrix-pdf-")) / "report.pdf"
    host = QWidget()
    host._btn_pdf = QPushButton("Export PDF", host)
    host._report_list = QListWidget(host)
    host._sync_list_visibility = lambda: None
    host._export_pdf = lambda: None

    with _toasts() as shown, _modals() as raised, \
            _patched(report_exporter, "save_pdf_report",
                     lambda p: Path(p).write_bytes(b"%PDF-1.4")), \
            _patched(QFileDialog, "getSaveFileName",
                     staticmethod(lambda *a, **k: (str(target), ""))):
        ReportsPage._export_pdf(host)

    row("S9-PDF", "a successful PDF export stops the user with a modal, unlike every other export",
        "real-path", f"saved={target.exists()}; modals={raised}; toasts={shown}",
        bool(raised) and not shown)
    host.deleteLater()


def s9_log_export_loudness() -> None:
    """The real ``LogSourcePanel._export_visible`` twice: nothing to export, then a real write.

    The two ends are the wrong way round on the loudness ladder (RULE-SURF2): the non-event
    is the loudest thing in the method, and the write that actually happened says nothing.
    """
    from PyQt6.QtWidgets import QFileDialog, QLineEdit, QTableWidget
    from ui.pages.log_source_panel import _LogSourcePanelMixin

    target = Path(tempfile.mkdtemp(prefix="ns-matrix-logexp-")) / "filtered.csv"
    host = QWidget()
    host._search_box = QLineEdit(host)
    host._is_source_enabled = lambda _k: True
    host._entry_matches = lambda _e, _f: True
    host._table = QTableWidget(0, 3, host)
    host._table.setHorizontalHeaderLabels(["Time", "Source", "Event"])
    host._export_visible = lambda: None

    host._entries = []
    with _toasts() as empty_toasts, _modals() as empty_modals:
        _LogSourcePanelMixin._export_visible(host)

    host._entries = [{"source_key": "rtt", "row": ("12:00", "RTT", "ok")}]
    with _toasts() as ok_toasts, _modals() as ok_modals, \
            _patched(QFileDialog, "getSaveFileName",
                     staticmethod(lambda *a, **k: (str(target), ""))):
        _LogSourcePanelMixin._export_visible(host)

    wrote = target.exists()
    row("S9-LOGEXP", "an empty export is a modal while a successful one says nothing at all",
        "real-path",
        f"empty: modals={empty_modals} toasts={empty_toasts}; "
        f"wrote={wrote}: modals={ok_modals} toasts={ok_toasts}",
        bool(empty_modals) or (wrote and not ok_toasts))
    host.deleteLater()


def s9_map_export_refusal_modal() -> None:
    """The real ``NetworkMapPage._on_export`` refusing on the non-interactive tab.

    Both of that page's success paths already toast; only the refusal is modal.
    """
    from PyQt6.QtWidgets import QTabWidget
    from ui.pages.network_map_page import NetworkMapPage

    host = QWidget()
    host._web_available = True
    host._inner_tab = QTabWidget(host)
    host._inner_tab.addTab(QWidget(host), "Interactive")
    host._inner_tab.addTab(QWidget(host), "Static")
    host._inner_tab.setCurrentIndex(1)
    host._run_js = lambda _js: None

    with _toasts() as shown, _modals() as raised:
        NetworkMapPage._on_export(host)

    row("S9-MAPEXP", "the map-export refusal is a modal while the same page's successes toast",
        "real-path", f"modals={raised}; toasts={shown}", bool(raised) and not shown)
    host.deleteLater()


def s9_app_traffic_capability_text() -> None:
    """The real ``AppTrafficPage._on_error`` fed the real producer's capability message.

    ``AppTrafficClassifier.run()`` has exactly two error paths and both are capability gaps
    -- Scapy missing, or the capture refusing to start without Npcap and administrator. The
    catalogue entry describes a different failure and ends in advice that cannot work.
    """
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    from PyQt6.QtWidgets import QLabel
    from ui.pages.app_traffic_page import AppTrafficPage

    producer = ("Failed to start packet capture. "
                "Run as Administrator/root with Npcap installed.")
    figure = Figure()
    host = QWidget()
    host._ax = figure.add_subplot(111)
    host._canvas = FigureCanvasQTAgg(figure)
    host._stop_worker = lambda: None
    host._status_lbl = QLabel(host)

    AppTrafficPage._on_error(host, producer)

    message = host._ax.texts[-1].get_text() if host._ax.texts else ""
    lowered = message.lower()
    names_capability = "npcap" in lowered or "administrator" in lowered
    row("S9-APPTRAF", "App Traffic answers a missing capture driver with 'start monitoring again'",
        "real-path", f"drawn={message!r}; names Npcap/administrator={names_capability}",
        not names_capability)
    host.deleteLater()


def s10_event_log_raw_exception() -> None:
    """The real ``SvcDoRun`` when the logger it runs raises.

    Nobody is watching a service. The Event Log entry is the whole account of what went
    wrong, and it is handed the exception's own text -- localized by Windows, with no why
    and nothing to do next.
    """
    os.environ["PROGRAMDATA"] = tempfile.mkdtemp(prefix="ns-matrix-svc-")
    import threading as _threading

    import win32event

    import svc
    from modules.error_text import explain

    boom = PermissionError(13, "Access is denied")
    written: list = []

    class _EventLog:
        EVENTLOG_INFORMATION_TYPE = 4
        EVENTLOG_WARNING_TYPE = 2
        PYS_SERVICE_STARTED = 1
        PYS_SERVICE_STOPPED = 2

        def LogMsg(self, *args) -> None:  # noqa: N802 - servicemanager's own name
            written.append(("LogMsg", args))

        def LogErrorMsg(self, text) -> None:  # noqa: N802
            written.append(("LogErrorMsg", text))

        def LogWarningMsg(self, text) -> None:  # noqa: N802
            written.append(("LogWarningMsg", text))

    service = object.__new__(svc._NetSentinelLoggerService)
    service._win32_stop = win32event.CreateEvent(None, 0, 0, None)
    service._thread_stop = _threading.Event()

    def _raise(stop_event):
        raise boom

    with _patched(svc, "servicemanager", _EventLog()), _patched(svc, "_run_logger", _raise):
        service.SvcDoRun()
    win32event.SetEvent(service._win32_stop)

    errors = [text for kind, text in written if kind == "LogErrorMsg"]
    message = errors[0] if errors else ""
    raw_shown = "Access is denied" in message
    next_step = explain(boom).next_step
    row("S10-EVTLOG", "a failed service writes the raw exception to the Event Log and no next step",
        "real-path",
        f"LogErrorMsg={message!r}; raw shown={raw_shown}; next step present={next_step in message}",
        raw_shown or next_step not in message)


def s10_stderr_surfaces_raw_exception() -> None:
    """The three real stderr surfaces of a headless run, each given a genuine fault.

    ``cli._resolve_output`` cannot create its parent, ``svc --status`` cannot query the
    service, and ``app --report`` cannot find a local address. All three are the only thing
    their user sees, and all three hand over the exception.
    """
    import win32serviceutil

    import app as app_mod
    import cli
    import modules.utils as _utils
    import svc
    from modules.error_text import explain

    observed: dict = {}

    blocker = Path(tempfile.mkdtemp(prefix="ns-matrix-cli-")) / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    # Ask the OS what it really raises rather than guessing: Windows answers
    # FileExistsError(WinError 183) and POSIX NotADirectoryError, and the two classify
    # differently. Deriving it keeps the expectation honest on either platform.
    try:
        (blocker / "sub").mkdir(parents=True, exist_ok=True)
        cli_next_step = ""
        cli_raw_marker = "WinError"
    except OSError as mkdir_exc:
        cli_next_step = explain(mkdir_exc).next_step
        cli_raw_marker = str(mkdir_exc)
    buf = io.StringIO()
    try:
        with redirect_stderr(buf):
            cli._resolve_output(str(blocker / "sub" / "out.json"))
    except SystemExit:
        pass  # expected: each of these three surfaces ends in sys.exit; stderr is the subject
    observed["cli"] = buf.getvalue().strip()

    def _refuse(_name):
        raise OSError(1060, "The specified service does not exist as an installed service.")

    buf = io.StringIO()
    try:
        with _patched(win32serviceutil, "QueryServiceStatus", staticmethod(_refuse)), \
                redirect_stderr(buf):
            svc._cmd_status()
    except SystemExit:
        pass  # expected: each of these three surfaces ends in sys.exit; stderr is the subject
    observed["svc-status"] = buf.getvalue().strip()

    def _no_adapter():
        raise RuntimeError("no usable network adapter")

    argv = sys.argv
    buf = io.StringIO()
    try:
        sys.argv = ["app.py", "--report", "--no-flush-caches",
                    "--output", str(Path(tempfile.mkdtemp(prefix="ns-matrix-rep-")) / "r.html")]
        with _patched(_utils, "get_local_ip", _no_adapter), redirect_stderr(buf):
            app_mod._headless()
    except SystemExit:
        pass  # expected: each of these three surfaces ends in sys.exit; stderr is the subject
    finally:
        sys.argv = argv
    lines = [ln for ln in buf.getvalue().strip().splitlines() if ln.strip()]
    observed["app-report"] = lines[0] if lines else ""

    # Each surface: the exact raw text that must NOT survive into it, and the next step
    # that must. svc --status carries a domain next step (install the service); explain()'s
    # generic "try again" cannot help with a service that was never installed.
    reproduced = False
    for key, raw_marker, next_step in (
        ("cli", cli_raw_marker, cli_next_step),
        ("svc-status", "does not exist as an installed service", "netsentinel-svc install"),
        ("app-report", "no usable network adapter",
         explain(RuntimeError("x")).next_step),
    ):
        text = observed[key]
        if raw_marker in text or next_step not in text:
            reproduced = True

    row("S10-STDERR",
        "the CLI, the service status command and the headless report print the raw exception",
        "real-path", "; ".join(f"{k}={v!r}" for k, v in observed.items()), reproduced)


def main() -> None:
    steps = [f4_log_record_shape, f1a_arp_dhcp, f1b_pills, f1c_service_diagnostics,
             f1c_speed_test_hidden, f1d_deco_partial, f2_scheduled_speedtest,
             f2_g6_note_and_clobber, f2_rest_api_bind, f2_webhook_failure, f2_keyring_write,
             f6_toasts, f5_raw_worker_error_text, f6_export_and_success,
             f6b_database_lock, f6b_update_check_blocks, iot_learn_thread,
             dns_axfr_unreachable, dns_axfr_held_open, discovery_methods_failed,
             smb_login_failed, smb_not_testable_green,
             s8_health_availability, s8_digest_grade, s8_digest_new_devices,
             s8_digest_uptime_table, s8_ack_row_asserts_success, s8_undo_ack_silent,
             s8_annotation_save_silent, s8_scheduled_scan_silent,
             s9_storm_tile_vocabulary, s9_credential_dialog_glyph,
             s9_pdf_export_success_modal, s9_log_export_loudness,
             s9_map_export_refusal_modal, s9_app_traffic_capability_text,
             s10_event_log_raw_exception, s10_stderr_surfaces_raw_exception]
    for step in steps:
        try:
            step()
        except Exception as exc:  # a broken row must not hide the others
            row(step.__name__, "(row crashed)", "-", f"{type(exc).__name__}: {exc}", None)
    print("\n" + "=" * 100)
    for rid, finding, method, observed, verdict in ROWS:
        print(f"[{verdict}] {rid} ({method}) {finding}\n    observed: {observed}")

    # RULE-GATE1: os._exit() below means the exit code cannot prove the run
    # finished, so print a positive completion signal. A reader that does not
    # see this line is looking at a truncated run, whatever the exit code says.
    repro = sum(1 for *_, v in ROWS if v == "REPRODUCED")
    fixed = sum(1 for *_, v in ROWS if v == "NOT REPRODUCED")
    unknown = sum(1 for *_, v in ROWS if v == "INCONCLUSIVE")
    print("=" * 100)
    print(f"MATRIX COMPLETE — {len(ROWS)} rows: {repro} REPRODUCED, "
          f"{fixed} NOT REPRODUCED, {unknown} inconclusive")
    sys.stdout.flush()
    os._exit(0)  # skip Qt/QThread interpreter teardown (see tests/_lazy_pages_child.py)


if __name__ == "__main__":
    main()
