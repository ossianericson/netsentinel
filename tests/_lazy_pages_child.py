"""Subprocess child that runs the Dashboard-constructing lazy_pages tests.

NOT collected by pytest (leading-underscore filename keeps it out of test_*
discovery). Invoked by `tests/test_lazy_pages.py` via `subprocess.run([sys.executable,
this_file, <test_name>])`.

Why a subprocess: a fully-constructed Dashboard cannot be created-and-destroyed
in-process on Windows without a Qt/QThread teardown crash, which is why
`Dashboard.closeEvent()` uses `os._exit(0)`. Under pytest, the autouse
`_flush_qt_events` fixture closes the Dashboard, that os._exit(0) fires, and the
whole pytest session silently terminates (the "os._exit test-suite mask"). Running
each Dashboard test in its own child process isolates that: the child owns its exit
code explicitly and never runs Qt/interpreter teardown, so os._exit can neither mask
a failure nor crash on shutdown.

Contract: `main(name)` runs the named test body and calls `os._exit(0)` on success or
`os._exit(1)` (after printing the traceback) on any failure. The parent asserts on the
child's return code. See project_test_suite_osexit_mask memory.
"""
from __future__ import annotations

import os
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path

# Allow `from ui.dashboard import Dashboard` when run as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QWidget

# Redirect settings_path() to an isolated temp file BEFORE any Dashboard is
# constructed. Every dash.close() below runs the real closeEvent(), which
# unconditionally calls save_settings() -- on the real repo-root NetSentinel.ini
# if this were not redirected, silently overwriting the developer's actual
# window geometry with whatever a never-shown, offscreen-constructed Dashboard
# reports (its degenerate normalGeometry(), often small and off-screen-ish).
# Confirmed live: running just this file flips a real maximized/1500x900
# saved state to normal_x=-320/normal_y=-50/900x800 -- the exact "window keeps
# coming back small, not by me" symptom, reproducing on every test-suite run.
import tempfile as _tempfile
from ui import app_settings as _app_settings
_TEST_SETTINGS_PATH = Path(_tempfile.mkdtemp()) / "NetSentinel_test.ini"
_app_settings.settings_path = lambda: _TEST_SETTINGS_PATH

from ui.nav.lazy_page import _LazyPageHost


# The conservative Phase-2 deferred set: (nav label, dashboard attr).
_DEFERRED = [
    ("IP Calculator", "_ip_calc_page"),
    ("WiFi Heatmap", "_wifi_heatmap_page"),
    ("802.11 Monitor", "_wifi_monitor_page"),
    ("Troubleshoot", "_troubleshoot_page"),
    ("DNS Zone Map", "_dns_zone_page"),
    ("DHCP Leases", "_dhcp_lease_page"),
    ("Config Snapshots", "_baseline_page"),
    ("REST API", "_rest_api_page"),
    ("Feature Guide", "_discover_page"),
    ("Help & Reference", "_help_tab_widget"),
    ("Protocol Visualizer", "_protocol_viz_page"),  # Phase A4
    ("App Traffic", "_app_traffic_page"),           # startup-perf coverage expansion
    ("Active Connections", "_connections_page"),    # startup-perf coverage expansion
]


# Module-level ref keeps the QApplication alive. Without it, the Python wrapper is
# GC'd when _ensure_app() returns, which tears down the C++ QApplication under the
# Dashboard mid-construction and fastfails (STATUS_STACK_BUFFER_OVERRUN). conftest.py's
# session fixture holds the same kind of long-lived reference.
_APP: QApplication | None = None


def _ensure_app() -> QApplication:
    """Session QApplication, offscreen — mirrors tests/conftest.py qt_app fixture."""
    global _APP
    if _APP is None:
        _APP = QApplication.instance() or QApplication(["netsentinel-test", "-platform", "offscreen"])
    return _APP


@contextmanager
def _reset_nav_restore_state():
    """Save/clear/restore NetSentinel.ini's [nav] last_section/last_page.

    ui/nav/builder.py's startup restore (builder.py:426-437) auto-navigates to
    whatever page was open when the app last closed — reading real NetSentinel.ini
    on disk (ui.app_settings.settings_path(), NOT the hermetic-redirected
    LOCALAPPDATA the QSettings("NetSentinel","NetSentinel") registry calls use).
    On a dev machine where that was ever "Protocol Visualizer" (e.g. an earlier
    RULE-T6 live walk), that auto-nav silently materializes the page during
    Dashboard.__init__ before any test assertion runs, making "should still be a
    host before nav" fail non-deterministically depending on local history —
    not a product bug. Tests that assert pre-nav placeholder state must not
    depend on whatever page a developer happened to have open last.
    """
    from ui.app_settings import settings_path
    qs = QSettings(str(settings_path()), QSettings.Format.IniFormat)
    saved_section = qs.value("nav/last_section", "")
    saved_page = qs.value("nav/last_page", "")
    qs.setValue("nav/last_section", "")
    qs.setValue("nav/last_page", "")
    qs.sync()
    try:
        yield
    finally:
        qs.setValue("nav/last_section", saved_section)
        qs.setValue("nav/last_page", saved_page)
        qs.sync()


# ── Dashboard integration test bodies (verbatim assertions from test_lazy_pages) ──
# On success each body ends with `dash.close()`: closeEvent() drains the background
# worker QThreads (dashboard.py) and then calls os._exit(0), exiting the CHILD process
# cleanly with code 0 (the success signal the parent reads). A bare os._exit(0) here
# would race the still-live worker threads and fastfail with STATUS_STACK_BUFFER_OVERRUN
# — the exact teardown crash closeEvent's worker-drain exists to prevent (RULE-WIN4).
# A failed assertion raises BEFORE close(), so main() reports it as exit 1 (no masking).

def test_deferred_pages_are_hosts_until_navigated() -> None:
    """Deferred attrs are _LazyPageHost until first nav (permanent behavior)."""
    _ensure_app()
    from ui.dashboard import Dashboard

    with _reset_nav_restore_state():
        dash = Dashboard(store=None)

    assert dash._lazy_hosts, "expected a non-empty deferred-page queue"

    for label, attr in _DEFERRED:
        host = getattr(dash, attr)
        assert isinstance(host, _LazyPageHost), f"{attr} should be a host before nav"
        assert dash._nav_label_to_widget.get(label) is host

    # Navigating materializes the real widget and re-points the map.
    for label, attr in _DEFERRED:
        dash._nav_rail_go_to(label)
        real = getattr(dash, attr)
        assert not isinstance(real, _LazyPageHost), f"{attr} should be real after nav"
        assert isinstance(real, QWidget)
        assert dash._nav_label_to_widget.get(label) is real
        assert dash._stack.indexOf(real) >= 0

    dash.close()   # drain workers + os._exit(0) — clean child success exit


def test_materialize_all_drains_queue() -> None:
    _ensure_app()
    from ui.dashboard import Dashboard

    with _reset_nav_restore_state():
        dash = Dashboard(store=None)

    assert dash._lazy_hosts
    dash._materialize_all_pages()
    assert dash._lazy_hosts == []
    for _label, attr in _DEFERRED:
        assert not isinstance(getattr(dash, attr), _LazyPageHost)

    dash.close()   # drain workers + os._exit(0) — clean child success exit


def test_protocol_viz_pending_context_replayed_on_materialize() -> None:
    """Scan-fed context buffered while the page is a placeholder must survive
    to the real page on first navigation — Protocol Visualizer is fed by scan
    handlers (tabs_network.py, scan_enrichment.py) regardless of nav state,
    unlike every other lazy page, so it has no "navigate first" guard to rely on."""
    _ensure_app()
    from ui.dashboard import Dashboard
    from ui.nav.lazy_page import _LazyPageHost

    with _reset_nav_restore_state():
        dash = Dashboard(store=None)

    assert isinstance(dash._protocol_viz_page, _LazyPageHost)
    assert dash._protocol_viz_pending_context is None

    # Simulate a scan result arriving before the user ever opens the page.
    fed_net_info = {"gateway": "10.0.0.1"}
    dash._feed_protocol_viz_context(
        net_info=fed_net_info, devices=[], diag_result=None, m2_result=None,
    )
    assert isinstance(dash._protocol_viz_page, _LazyPageHost), "still a placeholder"
    assert dash._protocol_viz_pending_context == {
        "net_info": fed_net_info, "devices": [], "diag_result": None, "m2_result": None,
    }

    dash._nav_rail_go_to("Protocol Visualizer")
    real = dash._protocol_viz_page
    assert not isinstance(real, _LazyPageHost)
    assert dash._protocol_viz_pending_context is None, "buffer must clear after replay"
    assert real._net_info == fed_net_info, "buffered context must reach the real page"

    dash.close()   # drain workers + os._exit(0) — clean child success exit


def test_app_traffic_pending_label_map_replayed_on_materialize() -> None:
    """Label map fed by scan_enrichment.py before the user ever opens App Traffic
    must survive to the real page on first navigation — same shape of problem as
    Protocol Visualizer above (fed by scan results regardless of nav state), but
    for AppTrafficPage._label_map."""
    _ensure_app()
    from ui.dashboard import Dashboard
    from ui.nav.lazy_page import _LazyPageHost

    with _reset_nav_restore_state():
        dash = Dashboard(store=None)

    assert isinstance(dash._app_traffic_page, _LazyPageHost)
    assert dash._app_traffic_pending_label_map is None

    # Simulate scan_enrichment.py feeding a label map before the user ever
    # opens App Traffic.
    fed_map = {"aa:bb:cc:dd:ee:ff": "kitchen-cam"}
    dash._feed_app_traffic_label_map(fed_map)
    assert isinstance(dash._app_traffic_page, _LazyPageHost), "still a placeholder"
    assert dash._app_traffic_pending_label_map == fed_map

    dash._nav_rail_go_to("App Traffic")
    real = dash._app_traffic_page
    assert not isinstance(real, _LazyPageHost)
    assert dash._app_traffic_pending_label_map is None, "buffer must clear after replay"
    assert real._label_map == fed_map, "buffered label map must reach the real page"

    dash.close()   # drain workers + os._exit(0) — clean child success exit


def test_connections_page_materializes_via_cross_page_signal() -> None:
    """inventory_page.show_connections_for fires before Active Connections has
    ever been navigated to (e.g. right-click 'Show Connections' from a fresh
    Inventory view). Unlike the buffered pages above, this handler needs the
    real widget immediately (to call focus_on_ip), so it force-materializes via
    _ensure_page rather than deferring — assert that materialization actually
    happens and the target IP is applied."""
    _ensure_app()
    from ui.dashboard import Dashboard
    from ui.nav.lazy_page import _LazyPageHost

    with _reset_nav_restore_state():
        dash = Dashboard(store=None)

    assert isinstance(dash._connections_page, _LazyPageHost)

    dash._inventory_page.show_connections_for.emit("192.168.1.50")

    real = dash._connections_page
    assert not isinstance(real, _LazyPageHost), "signal must force materialization"
    assert dash._nav_label_to_widget.get("Active Connections") is real
    assert real._search.text() == "192.168.1.50", "focus_on_ip must reach the real page"

    dash.close()   # drain workers + os._exit(0) — clean child success exit


_TESTS = {
    "test_deferred_pages_are_hosts_until_navigated": test_deferred_pages_are_hosts_until_navigated,
    "test_materialize_all_drains_queue": test_materialize_all_drains_queue,
    "test_protocol_viz_pending_context_replayed_on_materialize": test_protocol_viz_pending_context_replayed_on_materialize,
    "test_app_traffic_pending_label_map_replayed_on_materialize": test_app_traffic_pending_label_map_replayed_on_materialize,
    "test_connections_page_materializes_via_cross_page_signal": test_connections_page_materializes_via_cross_page_signal,
}


def main(name: str) -> None:
    fn = _TESTS.get(name)
    if fn is None:
        sys.stderr.write(f"unknown test: {name!r}; valid: {sorted(_TESTS)}\n")
        os._exit(2)
    try:
        fn()
    except (Exception, KeyboardInterrupt, SystemExit):  # noqa: BLE001 — report ANY failure via exit code
        traceback.print_exc()
        sys.stderr.flush()
        os._exit(1)
    # Success: exit hard, skipping Qt/interpreter teardown (the whole point).
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write("usage: _lazy_pages_child.py <test_name>\n")
        os._exit(2)
    main(sys.argv[1])
