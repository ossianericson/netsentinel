"""
tests/test_alert_dep_card.py — O1: alert dependency tree configuration card.

Covers:
  - _load_deps / _save_deps QSettings roundtrip
  - _NotifDepMixin exposes expected methods
  - _AddDepDialog.get_values() returns correct parent + children
  - _dep_push_to_engine() calls set_dependency_map on the injected engine
"""
from __future__ import annotations


# ── Import smoke test ─────────────────────────────────────────────────────────

def test_import():
    from ui.pages.notif_dep_card import (  # noqa: F401
        _load_deps, _save_deps, _AddDepDialog, _NotifDepMixin,
    )


# ── Data-layer roundtrip ──────────────────────────────────────────────────────

def test_save_and_load_roundtrip():
    from ui.pages.notif_dep_card import _load_deps, _save_deps

    original = _load_deps()
    test_data = [
        {"parent": "192.168.1.1", "children": ["192.168.1.10", "192.168.1.11"],
         "added_ts": 1700000000},
    ]
    _save_deps(test_data)
    loaded = _load_deps()
    assert loaded == test_data

    _save_deps(original)


def test_load_deps_returns_list_on_empty():
    from ui.pages.notif_dep_card import _load_deps, _save_deps

    original = _load_deps()
    _save_deps([])
    loaded = _load_deps()
    assert loaded == []

    _save_deps(original)


def test_save_multiple_deps():
    from ui.pages.notif_dep_card import _load_deps, _save_deps

    original = _load_deps()
    deps = [
        {"parent": "10.0.0.1", "children": ["10.0.0.2"], "added_ts": 1000},
        {"parent": "10.0.0.10", "children": ["10.0.0.11", "10.0.0.12"], "added_ts": 2000},
    ]
    _save_deps(deps)
    loaded = _load_deps()
    assert len(loaded) == 2
    parents = {d["parent"] for d in loaded}
    assert parents == {"10.0.0.1", "10.0.0.10"}

    _save_deps(original)


def test_load_deps_tolerates_corrupt_value(monkeypatch):
    from ui.pages import notif_dep_card

    class _FakeQS:
        def value(self, key, default="[]"):
            return "NOT VALID JSON {{{"

        def setValue(self, key, val):
            pass

    monkeypatch.setattr(notif_dep_card, "QSettings", lambda *a: _FakeQS())
    result = notif_dep_card._load_deps()
    assert result == []


# ── Mixin method surface ──────────────────────────────────────────────────────

def test_mixin_has_required_methods():
    from ui.pages.notif_dep_card import _NotifDepMixin

    for method_name in ("_build_dep_card", "_dep_add", "_dep_remove_selected",
                        "_dep_refresh_table", "_dep_context_menu", "_dep_push_to_engine"):
        assert hasattr(_NotifDepMixin, method_name), (
            f"_NotifDepMixin missing expected method: {method_name}"
        )


# ── _AddDepDialog ─────────────────────────────────────────────────────────────

def test_add_dep_dialog_get_values(qt_app):
    from ui.pages.notif_dep_card import _AddDepDialog
    from PyQt6.QtWidgets import QApplication

    dlg = _AddDepDialog(known_ips=["192.168.1.1", "192.168.1.2"])
    try:
        dlg._parent_edit.setText("192.168.1.1")
        dlg._children_edit.setText("192.168.1.10, 192.168.1.11")
        parent, children = dlg.get_values()
        assert parent == "192.168.1.1"
        assert "192.168.1.10" in children
        assert "192.168.1.11" in children
        assert len(children) == 2
    finally:
        try:
            dlg.deleteLater()
        except RuntimeError:
            pass  # widget already destroyed by Qt — safe to ignore
        app = QApplication.instance()
        if app:
            for _ in range(3):
                app.processEvents()


def test_add_dep_dialog_strips_whitespace(qt_app):
    from ui.pages.notif_dep_card import _AddDepDialog
    from PyQt6.QtWidgets import QApplication

    dlg = _AddDepDialog(known_ips=[])
    try:
        dlg._parent_edit.setText("  10.0.0.1  ")
        dlg._children_edit.setText(" 10.0.0.2 , 10.0.0.3 ")
        parent, children = dlg.get_values()
        assert parent == "10.0.0.1"
        assert children == ["10.0.0.2", "10.0.0.3"]
    finally:
        try:
            dlg.deleteLater()
        except RuntimeError:
            pass  # widget already destroyed by Qt — safe to ignore
        app = QApplication.instance()
        if app:
            for _ in range(3):
                app.processEvents()


# ── Engine wiring ─────────────────────────────────────────────────────────────

def test_dep_push_to_engine_calls_engine(qt_app, monkeypatch):
    """_dep_push_to_engine forwards to AlertEngine.set_dependency_map."""
    from ui.pages.notif_dep_card import _NotifDepMixin, _load_deps, _save_deps
    from PyQt6.QtCore import pyqtSignal
    from PyQt6.QtWidgets import QWidget, QApplication

    class _MockEngine:
        def __init__(self):
            self.calls: list[tuple] = []

        def set_dependency_map(self, parent, children):
            self.calls.append((parent, children))

    class _ConcreteWidget(_NotifDepMixin, QWidget):
        notify_dep_changed = pyqtSignal(str, list)

        def __init__(self):
            super().__init__()
            self._store = None
            self._alert_engine = _MockEngine()
            self._build_dep_card()

    original = _load_deps()
    _save_deps([])

    w = _ConcreteWidget()
    try:
        w._dep_push_to_engine("192.168.1.1", ["192.168.1.10"])
        assert w._alert_engine.calls == [("192.168.1.1", ["192.168.1.10"])]
    finally:
        _save_deps(original)
        try:
            w.deleteLater()
        except RuntimeError:
            pass  # widget already destroyed by Qt — safe to ignore
        app = QApplication.instance()
        if app:
            for _ in range(3):
                app.processEvents()
