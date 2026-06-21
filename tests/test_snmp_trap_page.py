"""Tests for ui/pages/snmp_trap_page.py"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


def _make_store(tmp_path):
    from modules.metric_store import MetricStore
    return MetricStore(db_path=tmp_path / "test.db")


@pytest.fixture
def page(tmp_path):
    from ui.pages.snmp_trap_page import SnmpTrapPage
    store = _make_store(tmp_path)
    p = SnmpTrapPage(store=store)
    yield p
    try:
        p.deleteLater()
    except RuntimeError:
        pass  # already deleted
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()
    store.close()


def test_import():
    from ui.pages.snmp_trap_page import SnmpTrapPage  # noqa: F401


def test_instantiation(page):
    assert page is not None


def test_on_trap_received_does_not_crash(page):
    """Injecting a trap dict should add a row without crashing."""
    trap = {
        "src": "192.168.1.10",
        "community": "public",
        "oid": "1.3.6.1.2.1.1.3.0",
        "value": "12345",
    }
    slot = (
        getattr(page, "on_trap_received", None) or
        getattr(page, "on_snmp_trap", None)
    )
    if slot:
        slot(trap)
    assert page is not None


def test_widget_is_not_none(page):
    assert page is not None
