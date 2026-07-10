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
from pathlib import Path

# Allow `from ui.dashboard import Dashboard` when run as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QWidget

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


# ── Dashboard integration test bodies (verbatim assertions from test_lazy_pages) ──
# On success each body ends with `dash.close()`: closeEvent() drains the background
# worker QThreads (dashboard.py) and then calls os._exit(0), exiting the CHILD process
# cleanly with code 0 (the success signal the parent reads). A bare os._exit(0) here
# would race the still-live worker threads and fastfail with STATUS_STACK_BUFFER_OVERRUN
# — the exact teardown crash closeEvent's worker-drain exists to prevent (RULE-WIN4).
# A failed assertion raises BEFORE close(), so main() reports it as exit 1 (no masking).

def test_deferred_pages_are_hosts_until_navigated() -> None:
    """With the flag on, deferred attrs are _LazyPageHost until first nav."""
    _ensure_app()
    from ui.dashboard import Dashboard

    QSettings("NetSentinel", "NetSentinel").setValue("experimental/lazy_pages", True)
    try:
        dash = Dashboard(store=None)
    finally:
        QSettings("NetSentinel", "NetSentinel").setValue("experimental/lazy_pages", False)

    assert dash._lazy_pages is True
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

    QSettings("NetSentinel", "NetSentinel").setValue("experimental/lazy_pages", True)
    try:
        dash = Dashboard(store=None)
    finally:
        QSettings("NetSentinel", "NetSentinel").setValue("experimental/lazy_pages", False)

    assert dash._lazy_hosts
    dash._materialize_all_pages()
    assert dash._lazy_hosts == []
    for _label, attr in _DEFERRED:
        assert not isinstance(getattr(dash, attr), _LazyPageHost)

    dash.close()   # drain workers + os._exit(0) — clean child success exit


def test_eager_path_builds_real_pages() -> None:
    """With the flag off (default), no hosts are created."""
    _ensure_app()
    from ui.dashboard import Dashboard

    QSettings("NetSentinel", "NetSentinel").setValue("experimental/lazy_pages", False)
    dash = Dashboard(store=None)
    assert dash._lazy_pages is False
    assert dash._lazy_hosts == []
    for _label, attr in _DEFERRED:
        assert not isinstance(getattr(dash, attr), _LazyPageHost)

    dash.close()   # drain workers + os._exit(0) — clean child success exit


_TESTS = {
    "test_deferred_pages_are_hosts_until_navigated": test_deferred_pages_are_hosts_until_navigated,
    "test_materialize_all_drains_queue": test_materialize_all_drains_queue,
    "test_eager_path_builds_real_pages": test_eager_path_builds_real_pages,
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
