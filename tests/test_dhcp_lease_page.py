"""Tests for ui/pages/dhcp_lease_page.py"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


@pytest.fixture
def page():
    from ui.pages.dhcp_lease_page import DhcpLeasePage
    p = DhcpLeasePage()
    yield p
    # __init__ fires a real DhcpLeaseWorker QThread (RULE-WIN4): it must finish
    # before the page is torn down, or Qt aborts the whole process with
    # "QThread: Destroyed while thread '' is still running".
    if p._worker is not None:
        p._worker.wait(5000)
    try:
        p.deleteLater()
    except RuntimeError:
        pass  # already deleted
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_import():
    from ui.pages.dhcp_lease_page import DhcpLeasePage  # noqa: F401


def test_instantiation(page):
    assert page is not None


def test_has_scan_requested_signal(page):
    assert hasattr(page, "scan_requested")


def test_on_leases_result_does_not_crash(page):
    """Injecting lease results should not crash."""
    leases = [
        {"ip": "192.168.1.10", "mac": "aa:bb:cc:dd:ee:ff", "hostname": "mypc",
         "server": "192.168.1.1", "lease_time": 86400}
    ]
    slot = getattr(page, "on_leases_result", None) or getattr(page, "on_result", None)
    if slot:
        slot(leases)
    assert page is not None
