"""RULE-WIN18 — a page must not run background timers before it is ever shown.

Mechanism (found live 2026-07-30, see docs/spikes/idle-rss-leak-lazy-page-timers.md):
`ui/nav/lazy_page.py`'s background chunk-builder constructs EVERY lazy page a
few seconds after startup, whether or not the user ever opens it. Any QTimer
started from `__init__` therefore runs for the entire app session on a page
nobody has looked at. Both offenders rebuilt a QTableWidget on every tick, and
QTableWidgetItem is a C++ object — so the growth was native and completely
invisible to tracemalloc, which is why several earlier rounds of
tracemalloc/UMDH/VMMap diagnostics on this leak found nothing.

Measured on a real Dashboard idling on Home with a real MetricStore:
main-process RSS +556 MB/hr before, dead flat (-19.6 MB/hr) after.

RULE-WIN15 covers the other end of the lifecycle (stop on hide). It is NOT
sufficient on its own: a widget that is constructed but never made visible
never receives a hideEvent, so `hideEvent()` alone cannot stop a timer that
`__init__` already started. Both halves are required.

These are runtime tests rather than an AST guard on purpose — the
ConnectionsPage offender started its timer *indirectly*, via
`self._chk_auto.setChecked(True)` firing the `toggled` signal into a handler
that called `start()`. No realistic static check follows that path; asking the
live widget "do you have any active timers?" catches every route.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 not installed")

from PyQt6.QtCore import QThread, QTimer
from PyQt6.QtWidgets import QApplication, QStackedWidget, QWidget


def _flush(n: int = 5) -> None:
    app = QApplication.instance()
    if app:
        for _ in range(n):
            app.processEvents()


def _teardown(page) -> None:
    """Stop every worker QThread before deleting the page.

    ConnectionsPage.__init__ kicks off a ConnectionSnapshotWorker (psutil socket
    enumeration) via its initial _refresh(). Deleting a parent widget while a
    child QThread is still running tears down the C++ QThread mid-run and
    fastfails the whole pytest process with no summary line — the RULE-GATE1
    truncation mode, which reads as a pass by exit code alone (RULE-WIN4).
    """
    for t in page.findChildren(QTimer):
        t.stop()
    for w in page.findChildren(QThread):
        try:
            if w.isRunning():
                if hasattr(w, "stop"):
                    w.stop()
                w.quit()
                w.wait(2000)
        except RuntimeError:
            pass  # C++ object already gone
    _flush()
    page.deleteLater()
    _flush()


def _active_timers(widget) -> list:
    """Every running QTimer owned by this widget or any descendant."""
    return [t for t in widget.findChildren(QTimer) if t.isActive()]


def _make_connections_page():
    from ui.pages.connections_page import ConnectionsPage
    return ConnectionsPage()


def _make_timeline_page():
    from unittest.mock import MagicMock
    from ui.pages.timeline_page import TimelinePage
    store = MagicMock()
    store.recent_events.return_value = []
    return TimelinePage(store=store)


def _make_security_overview_page():
    """SecurityOverviewPage with its data load stubbed out.

    The page keeps a deliberate one-shot _load_data() in __init__ (it seeds the
    initial hidden/shown state of the finding tables); only the repeating timer
    is deferred to showEvent. Overriding _load_data on a subclass — rather than
    monkeypatching the class, which breaks @pyqtSlot resolution for every later
    instance in the same process — keeps this test off the real MetricStore and
    the on-disk threat-intel cache while still exercising the real timer wiring.
    """
    from ui.pages.security_overview_page import SecurityOverviewPage

    class _StubbedSecurityOverviewPage(SecurityOverviewPage):
        def _load_data(self) -> None:
            pass  # no store queries / cache file read — timer lifecycle is what's under test

    return _StubbedSecurityOverviewPage(store=None)


def _make_dhcp_lease_page():
    """DhcpLeasePage with its scan stubbed out.

    The real _run_scan() starts a DhcpLeaseWorker QThread that shells out to
    `arp -a` / `ipconfig /all`; the timer wiring is identical either way.
    """
    from ui.pages.dhcp_lease_page import DhcpLeasePage

    class _StubbedDhcpLeasePage(DhcpLeasePage):
        def _run_scan(self) -> None:
            pass  # no worker QThread / subprocess — timer lifecycle is what's under test

    return _StubbedDhcpLeasePage()


def _stubbed(cls, **stubs):
    """Subclass `cls` overriding data-load methods with no-ops.

    Overriding on a subclass rather than monkeypatching the class keeps
    @pyqtSlot resolution intact for every later instance in the same process
    (see _make_security_overview_page for the full reasoning).
    """
    return type(f"_Stubbed{cls.__name__}", (cls,), dict(stubs))


def _make_cert_page():
    from ui.pages.cert_page import CertPage
    return _stubbed(CertPage, _refresh=lambda self: None)(store=None)


def _make_uptime_page():
    from ui.pages.uptime_page import UptimePage
    return _stubbed(UptimePage, _refresh=lambda self: None)(store=None)


def _make_service_page():
    from ui.pages.service_page import ServicePage
    return _stubbed(ServicePage, _refresh=lambda self: None)(store=None)


def _make_maintenance_page():
    from ui.pages.maintenance_page import MaintenancePage
    return _stubbed(MaintenancePage, _refresh_table=lambda self: None)()


def _make_hardware_integration_page():
    """HardwareIntegrationPage with plugin registry reads and poll workers stubbed.

    Its __init__ reads the real registered-plugin list out of QSettings and starts
    a poll worker per instance — RULE-WIN6's own worked example of a page whose
    every persistent-storage reader must be patched, or the developer's real
    plugins spawn threads that outlive teardown. None of it affects timer wiring.
    """
    from unittest.mock import patch
    from ui.pages.hardware_integration_page import HardwareIntegrationPage

    cls = _stubbed(HardwareIntegrationPage, _start_all_poll_workers=lambda self: None)
    with patch("ui.pages.hardware_integration_page._load_instances", return_value=[]), \
         patch("ui.pages.hardware_integration_page._load_paths", return_value=[]):
        return cls(parent=None)


# (module stem under ui/pages/, factory). Do NOT hand-curate this list and hope:
# test_every_page_with_a_repeating_timer_is_covered() below fails when a page
# module wires a repeating QTimer without appearing here.
_PAGE_FACTORIES = [
    ("connections_page", _make_connections_page),
    ("timeline_page", _make_timeline_page),
    ("security_overview_page", _make_security_overview_page),
    ("dhcp_lease_page", _make_dhcp_lease_page),
    ("cert_page", _make_cert_page),
    ("uptime_page", _make_uptime_page),
    ("service_page", _make_service_page),
    ("maintenance_page", _make_maintenance_page),
    ("hardware_integration_page", _make_hardware_integration_page),
]


@pytest.mark.parametrize("name,factory", _PAGE_FACTORIES, ids=[p[0] for p in _PAGE_FACTORIES])
def test_never_shown_page_runs_no_timers(qt_app, name, factory):
    """A page constructed but never shown must have zero active timers.

    This is the case the lazy background page-builder creates for every page
    the user never opens — and the one `hideEvent()` structurally cannot cover.
    """
    page = factory()
    _flush()

    running = _active_timers(page)
    assert not running, (
        f"{name} page started {len(running)} timer(s) at construction "
        f"(intervals: {[t.interval() for t in running]} ms). A lazy page is "
        f"constructed at startup even if never opened, so this runs for the "
        f"whole app session on a page nobody sees (RULE-WIN18). Start the "
        f"timer in showEvent() instead, and stop it in hideEvent()."
    )

    _teardown(page)


@pytest.mark.parametrize("name,factory", _PAGE_FACTORIES, ids=[p[0] for p in _PAGE_FACTORIES])
def test_timer_starts_on_show_and_stops_on_hide(qt_app, name, factory):
    """The timer must follow real visibility, driven by a real page switch.

    Uses QStackedWidget.setCurrentWidget (not bare .hide()/.show()) so this
    exercises the same event path the Dashboard nav actually produces.
    """
    other = QWidget()
    stack = QStackedWidget()
    page = factory()
    stack.addWidget(other)
    stack.addWidget(page)
    stack.show()

    stack.setCurrentWidget(page)
    _flush()
    assert _active_timers(page), (
        f"{name} page must start its auto-refresh timer once actually visible"
    )

    stack.setCurrentWidget(other)   # real hideEvent
    _flush()
    still = _active_timers(page)
    assert not still, (
        f"{name} page left {len(still)} timer(s) running after navigating away "
        f"(intervals: {[t.interval() for t in still]} ms) — RULE-WIN15."
    )

    stack.setCurrentWidget(page)    # real showEvent again
    _flush()
    assert _active_timers(page), (
        f"{name} page must resume its timer when revisited"
    )

    stack.setCurrentWidget(other)
    _flush()
    _teardown(page)
    other.deleteLater()
    stack.deleteLater()
    _flush()


def _repeating_timer_owners(src: str) -> set[str]:
    """Expressions in `src` that own a QTimer wired to fire more than once.

    A timer counts as repeating when something connects to its `timeout` and
    nothing calls `setSingleShot(True)` on the same expression. Single-shot
    timers (status-message resets, search debounces) are not what RULE-WIN18
    is about — they cannot run for the life of the session.
    """
    tree = ast.parse(src)
    connected: set[str] = set()
    single_shot: set[str] = set()

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        func = node.func
        if (func.attr == "connect"
                and isinstance(func.value, ast.Attribute)
                and func.value.attr == "timeout"):
            connected.add(ast.unparse(func.value.value))
        if func.attr == "setSingleShot" and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and arg.value is True:
                single_shot.add(ast.unparse(func.value))

    return connected - single_shot


_PAGES_DIR = Path(__file__).resolve().parents[1] / "ui" / "pages"

# Pages that wire a repeating timer but have no lifecycle factory yet. This is a
# RATCHET: it may only shrink. Add a factory to _PAGE_FACTORIES and delete the
# entry here — never add a new one. Nothing in this set has been *cleared*; it
# is known-unverified debt, not a clean bill of health.
_UNCOVERED_BASELINE = {
    "history_page",
    "home_automation_page",
    "inventory_page",
    "live_bandwidth_page",
    "monitor_overview_page",
    "overview_page",
    "speed_test_page",
    "trigger_builder_page",
}


def test_every_page_with_a_repeating_timer_is_covered():
    """A new page with a background timer must not slip past RULE-WIN18.

    _PAGE_FACTORIES used to be purely hand-maintained, so the rule was only
    enforced on pages someone remembered to add — and four pages
    (cert/uptime/service/maintenance) sat in the tree starting repeating
    timers straight from __init__ with nothing to catch them. This closes the
    loop: the file list is the source of truth, not anyone's memory.
    """
    flagged = set()
    for path in sorted(_PAGES_DIR.glob("*.py")):
        try:
            src = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if _repeating_timer_owners(src):
            flagged.add(path.stem)

    covered = {module for module, _ in _PAGE_FACTORIES}
    uncovered = flagged - covered

    unexpected = uncovered - _UNCOVERED_BASELINE
    assert not unexpected, (
        f"{sorted(unexpected)} wire a repeating QTimer but have no entry in "
        f"_PAGE_FACTORIES, so RULE-WIN18 is not enforced on them. A lazy page "
        f"is constructed at startup even if never opened, so a timer started "
        f"in __init__ runs for the whole session on a page nobody sees. Add a "
        f"factory (stub out data loads, see _stubbed) — do not add the page to "
        f"_UNCOVERED_BASELINE."
    )

    fixed = _UNCOVERED_BASELINE - uncovered
    assert not fixed, (
        f"{sorted(fixed)} are now covered (or no longer have a repeating "
        f"timer) — remove them from _UNCOVERED_BASELINE. The ratchet only "
        f"moves one way."
    )


def test_connections_auto_checkbox_stays_checked_by_default(qt_app):
    """The visible UI state must be unchanged by the fix.

    The bug was fixed by blocking the checkbox's signal during construction,
    which is exactly the kind of change that could silently flip the user-facing
    default. Pin it: still checked, just not running yet.
    """
    page = _make_connections_page()
    _flush()
    assert page._chk_auto.isChecked(), (
        "Auto (5s) must still be checked by default — the fix only defers "
        "STARTING the timer, it must not change the visible default"
    )
    assert not page._auto_timer.isActive(), (
        "...but the timer must not be running before the page is ever shown"
    )
    _teardown(page)
