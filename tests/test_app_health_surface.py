"""S4 — the app-health surface: Home strip, tray dot, tri-state pills, G6's note (RULE-T7).

Every test drives real widgets with real ``Condition`` snapshots from a real ``AppHealth``;
none constructs a Dashboard (RULE-TP4-DASH) and none writes the real registry — the flag
is read through ``ui.app_health_bridge.QSettings``, patched where a test needs it on,
because conftest cannot sandbox explicit-argument QSettings on Windows.

Acceptance (plan §6 S4): A1 flag off changes nothing · A2 a fault shows a row with a
working button and moves the tray dot · A3 the next success removes it.
"""
from __future__ import annotations

import ast
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6")

from modules import app_health_catalogue as cat  # noqa: E402
from modules.app_health import AppHealth  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]
_made: list = []


@pytest.fixture(autouse=True)
def _release(qt_app):
    yield
    for obj in _made:
        try:
            obj.deleteLater()
        except RuntimeError:
            pass  # already destroyed with its parent
    _made.clear()
    from PyQt6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    for _ in range(3):
        qt_app.processEvents()


def _keep(obj):
    _made.append(obj)
    return obj


def _pump(qt_app, until, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qt_app.processEvents()
        if until():
            return True
        time.sleep(0.01)
    return until()


# ── 4.1: the strip ────────────────────────────────────────────────────────────────

def _strip():
    from ui.widgets.app_health_strip import AppHealthStrip

    return _keep(AppHealthStrip())


def test_a_condition_becomes_a_row_whose_button_opens_its_page(qt_app):
    health = AppHealth()
    health.report_failure(cat.SCHEDULED_SPEED_TEST, detail="Ookla CLI exited with code 2")
    strip = _strip()
    opened: list = []
    strip.navigate_to.connect(opened.append)

    strip.set_conditions(health.active())

    assert not strip.isHidden()
    (row,) = strip.rows()
    assert row.what_label.text() == cat.SCHEDULED_SPEED_TEST.what
    assert cat.SCHEDULED_SPEED_TEST.next_step in row.body_label.text()
    assert "Ookla CLI exited with code 2" not in row.body_label.text(), "raw text is tooltip-only (RULE-A2)"
    assert "Ookla CLI exited with code 2" in row.toolTip()
    row.cta_button.click()
    assert opened == ["Speed Test"]


def test_a_resolved_condition_disappears_and_the_strip_hides(qt_app):
    health = AppHealth()
    health.report_failure(cat.MONITORS["Availability"])
    strip = _strip()
    strip.set_conditions(health.active())

    health.report_ok(cat.MONITORS["Availability"].key)
    strip.set_conditions(health.active())

    assert strip.isHidden()
    assert strip.rows() == []


def test_info_conditions_never_open_the_strip_on_their_own(qt_app):
    """Owner decision 2026-09-17 — syslog/SNMP bind at every launch, used or not."""
    health = AppHealth()
    health.report_failure(cat.SYSLOG_RECEIVER)
    health.report_failure(cat.SNMP_TRAP_RECEIVER)
    strip = _strip()

    strip.set_conditions(health.active())

    assert strip.isHidden()


def test_info_and_overflow_wait_behind_show_more(qt_app):
    health = AppHealth()
    for name in ("Availability", "Certificate", "Service", "Health"):
        health.report_failure(cat.MONITORS[name])
    health.report_failure(cat.SYSLOG_RECEIVER)
    strip = _strip()

    strip.set_conditions(health.active())
    assert len(strip.rows()) == 3
    assert strip._more_btn.text() == "Show 2 more"

    strip._more_btn.click()
    assert [r.condition.key for r in strip.rows()][-1] == "listener:syslog"
    assert len(strip.rows()) == 5
    assert strip._more_btn.text() == "Show fewer"


def test_a_condition_without_a_page_draws_no_button(qt_app):
    health = AppHealth()
    health.report_failure(cat.MONITORS["Health"])
    strip = _strip()
    strip.set_conditions(health.active())

    (row,) = strip.rows()
    assert row.cta_button is None


# ── 4.1 + 4.4a end to end: registry → bridge → Home + tray ─────────────────────────

def test_a_failure_from_a_worker_thread_reaches_home_and_the_tray_and_clears(qt_app, monkeypatch):
    """A2 + A3 through the real bridge, reported off the GUI thread as the router does."""
    from ui.app_health_bridge import attach_surface

    health = AppHealth()
    health.report_failure(cat.SYSLOG_RECEIVER)  # before the window existed — must still show
    strip = _strip()
    tray = MagicMock()
    home = SimpleNamespace(set_app_health=strip.set_conditions)
    window = _keep(__import__("PyQt6.QtCore", fromlist=["QObject"]).QObject())
    window._home_page = home
    window._tray_manager = tray

    attach_surface(window, health)
    assert [c.key for c in tray.set_app_health.call_args.args[0]] == ["listener:syslog"]

    spec = cat.notification_channel("EMAIL", "Ops mail")
    t = threading.Thread(target=lambda: health.report_failure(spec, detail="535 5.7.8"))
    t.start()
    t.join(5)
    assert _pump(qt_app, lambda: not strip.isHidden())
    assert strip.rows()[0].condition.key == "notify:Ops mail"

    health.report_ok(spec.key)
    assert _pump(qt_app, lambda: strip.isHidden())


def test_the_tray_dot_takes_the_worse_of_network_and_app_health():
    from ui.system_tray import _effective_health_state as eff

    assert eff("green", "Warning") == "amber"
    assert eff("unknown", "High") == "amber", "High is amber: red means the NETWORK is failing"
    assert eff("red", "Warning") == "red"
    assert eff("green", "Critical") == "red"
    assert eff("green", "Info") == "green"
    assert eff("amber", "") == "amber"


def test_the_tray_tooltip_names_the_condition(qt_app, monkeypatch):
    from PyQt6.QtGui import QIcon, QPixmap
    from PyQt6.QtWidgets import QWidget

    from ui import system_tray

    painted: list = []
    monkeypatch.setattr(system_tray, "_overlay_health_dot", lambda icon, state: painted.append(state) or icon)
    mgr = system_tray.SystemTrayManager(_keep(QWidget()))
    mgr._tray = MagicMock()
    mgr._base_icon = QIcon(QPixmap(32, 32))
    mgr._shown = True
    mgr.set_health("green", "All good")

    health = AppHealth()
    health.report_failure(cat.SYSLOG_RECEIVER)
    health.report_failure(cat.MONITORS["Service"])
    health.report_failure(cat.MONITORS["Certificate"])
    mgr.set_app_health(health.active())

    assert painted[-1] == "amber"
    tip = mgr._tray.setToolTip.call_args.args[0]
    # Equal severity → longest-standing first (AppHealth.active()); Info is not counted.
    assert "App: Service monitoring is failing (+1 more)" in tip

    mgr.set_app_health([])
    assert painted[-1] == "green"
    assert "App:" not in mgr._tray.setToolTip.call_args.args[0]


# ── A1: the strip, now unconditional (S10.2) ──────────────────────────────────────

def test_home_places_the_strip_under_the_freshness_row(qt_app):
    from ui.pages.home_page import HomePage

    page = _keep(HomePage(store=None))
    outer = page.layout()
    widgets = [outer.itemAt(i).widget() for i in range(outer.count())]
    assert widgets.index(page._app_health_strip) == widgets.index(page._freshness_strip) + 1

    health = AppHealth()
    health.report_failure(cat.REPORT_SCHEDULER)
    opened: list = []
    page.navigate_to.connect(opened.append)
    page.set_app_health(health.active())
    page._app_health_strip.rows()[0].cta_button.click()
    assert opened == ["Network Health Report"]


# ── 4.2: tri-state pills ──────────────────────────────────────────────────────────

def test_a_running_but_failing_monitor_is_not_green(qt_app):
    """Matrix F1b."""
    from ui import styles as _s
    from ui.widgets.home_session_widgets import FreshnessStrip

    strip = _keep(FreshnessStrip())
    opened: list = []
    strip.navigate_to.connect(opened.append)

    strip.update_freshness(arp=True, logger=True, failing={"ARP": "Npcap is not installed"})

    assert strip._fs_pill_arp.text().startswith(_s.STATUS_ICON_WARN)
    assert _s.AMBER in strip._fs_pill_arp.styleSheet()
    assert "Npcap is not installed" in strip._fs_pill_arp.toolTip()
    strip.update_freshness(dhcp=True, failing={"DHCP": ""})
    assert "DHCP Leases" in strip._fs_pill_dhcp.toolTip(), "the tooltip names the page the click opens"
    strip.update_freshness(arp=True, logger=True, failing={"ARP": "Npcap is not installed"})
    assert strip._fs_pill_log.text().startswith("●"), "a healthy pill stays green"
    strip._fs_pill_arp.click()
    strip._fs_pill_log.click()
    assert opened == ["ARP Spoof Watch"], "a failing pill opens its page; a healthy ON pill does not"

    strip.update_logger_tooltip(since_str="5 min ago")
    strip.update_freshness(arp=True, logger=True, failing={"Logger": ""})
    strip.update_logger_tooltip(since_str="5 min ago")
    assert "last run failed" in strip._fs_pill_log.toolTip(), "the live-data tooltip must not hide the failure"


def test_an_off_monitor_with_a_stale_error_stays_off(qt_app):
    from ui.widgets.home_session_widgets import FreshnessStrip

    strip = _keep(FreshnessStrip())
    strip.update_freshness(arp=False, failing={"ARP": "old"})
    assert strip._fs_pill_arp.text().startswith("○")


def test_pill_failures_come_from_the_registry():
    """S10.2 — no attachment precondition left; only `state == "error"` decides.

    A registry entry with no error text still counts as failing (the pill is painted
    ON-but-failing with an empty detail), and a `fresh` entry never does.
    """
    from ui.monitor_state import _MonitorStateMixin

    host = SimpleNamespace(
        _scan_registry={
            "ARP Spoof Watch": {"state": "error", "error": "Npcap is not installed"},
            "Network Logger": {"state": "fresh", "error": None},
            "DHCP Rogue Monitor": {"state": "error", "error": None},
        },
        _PILL_REGISTRY_LABELS=_MonitorStateMixin._PILL_REGISTRY_LABELS,
    )
    assert _MonitorStateMixin._pill_failures(host) == {"ARP": "Npcap is not installed", "DHCP": ""}

    host._scan_registry = {}
    assert _MonitorStateMixin._pill_failures(host) == {}, "nothing failing is {}, never None"


def test_a_registry_error_repaints_the_pills_at_once(qt_app):
    """A monitor's error slot writes the registry; nothing else would repaint the pill
    until the next worker start or finish."""
    from ui.monitor_state import _MonitorStateMixin
    from ui.nav.builder import _NavBuilderMixin

    painted: list = []

    class _Host(_NavBuilderMixin, _MonitorStateMixin):
        def __init__(self):
            self._scan_registry = {}
            self._flyout_dots = {}
            self._home_page = SimpleNamespace(
                _last_pill_states=(True, False, False, False),
                set_monitor_pills=lambda *a, failing=None: painted.append((a, failing)),
            )

    host = _Host()
    from unittest.mock import patch
    with patch("ui.nav.builder.QSettings"):
        host._nav_set_scan_state("ARP Spoof Watch", "error", error="Npcap is not installed")
    assert painted == [((True, False, False, False), {"ARP": "Npcap is not installed"})]


# ── 4.3: G6's note ────────────────────────────────────────────────────────────────

def _g6():
    import app as app_module
    from PyQt6.QtCore import QObject, pyqtSignal

    class _Emitter(QObject):
        error = pyqtSignal(str)

    notes: list = []
    window = SimpleNamespace(_set_status=notes.append)
    emitter = _keep(_Emitter())
    app_module._wire_monitor_error_surface(window, {"Availability": emitter})
    return emitter, notes


def test_the_status_bar_carries_no_monitor_note_but_the_log_does(caplog):
    """Matrix F2-G6 — the strip replaced a note the next progress update overwrote.

    S10.2 deleted the note outright, so this handler's only job is the log record; the
    six monitors reach the strip through `_report_worker_health`, wired separately.
    """
    import logging

    emitter, notes = _g6()
    with caplog.at_level(logging.WARNING, logger="netsentinel.monitors"):
        emitter.error.emit("database is locked")
        emitter.error.emit("database is locked")
    assert notes == [], "the status bar must not be written at all"
    assert sum("database is locked" in r.getMessage() for r in caplog.records) == 2, (
        "every error is logged, not just the first — the dedup died with the note"
    )


# ── 4.4b: listener pages learn what their dropped startup signals carried ──────────

def test_listener_pages_are_seeded_from_the_registry_and_the_bound_port():
    import app as app_module

    health = AppHealth()
    health.report_failure(cat.SNMP_TRAP_RECEIVER, detail="Cannot bind UDP port 162: [WinError 10048]")
    syslog_page, snmp_page = MagicMock(), MagicMock()
    window = SimpleNamespace(_syslog_page=syslog_page, _snmp_trap_page=snmp_page)

    app_module._seed_listener_pages(
        window, health,
        SimpleNamespace(listen_port=514), SimpleNamespace(listen_port=0),
    )

    syslog_page.on_status.assert_called_once_with("Listening on UDP :514")
    syslog_page.on_error.assert_not_called()
    snmp_page.on_error.assert_called_once_with("Cannot bind UDP port 162: [WinError 10048]")


def _main_source():
    tree = ast.parse((_REPO_ROOT / "app.py").read_text(encoding="utf-8"))
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")


def test_main_wires_the_whole_surface_with_no_gate():
    """S10.2 — the flag is gone, so every part of the surface is unconditional.

    The RULE-EXP1 gate was retired once the owner accepted the surface live (S4.5). What
    replaces the flag assertions is the opposite check: nothing in ``main`` may put the
    strip, the tray dot or the listener seeding behind an ``if``, or a release could ship
    with the surface silently dark again.
    """
    main = _main_source()
    calls = {}
    for node in ast.walk(main):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            calls.setdefault(node.func.id, []).append(node)

    (wire,) = calls["_wire_app_health"]
    assert not any(k.arg == "surface" for k in wire.keywords), "surface= is retired; the surface always attaches"
    (g6,) = calls["_wire_monitor_error_surface"]
    assert not any(k.arg == "note" for k in g6.keywords), "note= is retired with the legacy status-bar note"

    gated = {"_wire_app_health", "_seed_listener_pages", "_wire_monitor_error_surface"}
    for node in ast.walk(main):
        if not isinstance(node, ast.If):
            continue
        inside = {
            c.func.id for c in ast.walk(node)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id in gated
        }
        assert not inside, f"app-health wiring is conditional again: {sorted(inside)} inside an if at line {node.lineno}"

    (seed,) = calls["_seed_listener_pages"]
    (logging_wire,) = calls["_wire_logging"]
    assert seed.lineno > logging_wire.lineno, "seed after the pages are connected, or a signal can fall between"


def test_the_other_two_home_pill_sets_are_not_green_for_a_failing_monitor_either(qt_app):
    """S4 follow-up (owner, 2026-09-17): Home draws the same four monitors three times —
    the freshness strip, the monitoring card and the recommendation row. Leaving two of
    them green for a failing monitor is the RULE-SURF1 defect F1b fixed, one card lower."""
    from ui import styles as _s
    from ui.pages.home_page import HomePage

    page = _keep(HomePage(store=None))
    base_tip = page._pill_arp.toolTip()

    page.set_monitor_pills(True, False, False, True, failing={"ARP": "Npcap is not installed"})

    for pill in (page._pill_arp, page._rec_pill_arp):
        assert pill.text().startswith(_s.STATUS_ICON_WARN), pill.text()
        assert _s.AMBER in pill.styleSheet()
        assert "Npcap is not installed" in pill.toolTip()
    for pill in (page._pill_logger, page._rec_pill_logger):
        assert pill.text().startswith("●"), "a healthy ON monitor stays green"

    page.set_monitor_pills(True, False, False, True, failing=None)  # recovered, or flag off
    assert page._pill_arp.text().startswith("●")
    assert page._pill_arp.toolTip() == base_tip, "the pill's own description comes back"
