"""
Regression test for ui/widgets/skeleton.py's timer-registry leak.

Bug: _timers is a module-level dict keyed by id(table) -- a CPython address
that gets reused after garbage collection. insert_skeleton_rows() stores a
QTimer there but nothing ever removes the entry if the table is destroyed
before clear_skeleton_rows() runs (e.g. a scan that never completes). The
leaked entry keeps the table alive via the _pulse closure, and a later table
reusing that id() can trigger _stop_timer() calling .stop() on an
already-Qt-deleted QTimer -- RuntimeError: wrapped C++ object has been deleted.
"""
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QTableWidget

from ui.widgets import skeleton


def test_timer_registry_entry_removed_when_table_destroyed_without_clear(qt_app):
    """A table destroyed while skeleton rows are still present (scan never
    finished, clear_skeleton_rows() never called) must not leave a stale
    entry in the module-level _timers registry.

    insert_skeleton_rows()'s _pulse closure holds a live Python reference to
    the table, so plain refcounting can never drop it -- only an explicit Qt
    C++-side deletion can. deleteLater() alone doesn't flush within ordinary
    processEvents() calls here, so the DeferredDelete event is sent directly.
    """
    table = QTableWidget(0, 3)
    skeleton.insert_skeleton_rows(table, count=3)
    key = id(table)
    assert key in skeleton._timers

    table.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    qt_app.processEvents()

    assert key not in skeleton._timers, (
        "stale QTimer entry survived table destruction -- leaks the table "
        "via the _pulse closure and risks RuntimeError on a later id() reuse"
    )
