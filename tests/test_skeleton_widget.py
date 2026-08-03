"""
Regression test for ui/widgets/skeleton.py's timer-registry leak.

Bug: _pulses is a module-level dict keyed by id(table) -- a CPython address
that gets reused after garbage collection. insert_skeleton_rows() stores a
pulse controller there but nothing ever removed the entry if the table is destroyed
before clear_skeleton_rows() runs (e.g. a scan that never completes). The
leaked entry keeps the table alive via the _pulse closure, and a later table
reusing that id() can trigger _stop_timer() calling .stop() on an
already-Qt-deleted QTimer -- RuntimeError: wrapped C++ object has been deleted.
"""
from PyQt6.QtCore import QCoreApplication, QEvent, QTimer
from PyQt6.QtWidgets import QStackedWidget, QTableWidget, QWidget

from ui.widgets import skeleton


def _active_timers(widget):
    return [t for t in widget.findChildren(QTimer) if t.isActive()]


def test_timer_registry_entry_removed_when_table_destroyed_without_clear(qt_app):
    """A table destroyed while skeleton rows are still present (scan never
    finished, clear_skeleton_rows() never called) must not leave a stale
    entry in the module-level _pulses registry.

    insert_skeleton_rows()'s _pulse closure holds a live Python reference to
    the table, so plain refcounting can never drop it -- only an explicit Qt
    C++-side deletion can. deleteLater() alone doesn't flush within ordinary
    processEvents() calls here, so the DeferredDelete event is sent directly.
    """
    table = QTableWidget(0, 3)
    skeleton.insert_skeleton_rows(table, count=3)
    key = id(table)
    assert key in skeleton._pulses

    table.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    qt_app.processEvents()

    assert key not in skeleton._pulses, (
        "stale QTimer entry survived table destruction -- leaks the table "
        "via the _pulse closure and risks RuntimeError on a later id() reuse"
    )


def test_pulse_does_not_run_while_table_is_hidden(qt_app):
    """RULE-WIN18: the pulse must follow real visibility.

    ServicePage.__init__ inserts skeleton rows then calls _refresh(), which
    returns early on `not self.isVisible()` -- so clear_skeleton_rows() is
    never reached on a page the user never opens. A self-starting timer here
    therefore pulsed for the whole app session, allocating a QBrush + QColor
    per skeleton cell every 650 ms on a table nobody could see.
    """
    other = QWidget()
    stack = QStackedWidget()
    table = QTableWidget(0, 3)
    stack.addWidget(other)
    stack.addWidget(table)

    skeleton.insert_skeleton_rows(table, count=3)
    qt_app.processEvents()
    assert not _active_timers(table), (
        "pulse timer started on a table that has never been shown"
    )

    stack.show()
    stack.setCurrentWidget(table)
    qt_app.processEvents()
    assert _active_timers(table), "pulse must run once the table is visible"

    stack.setCurrentWidget(other)      # real hideEvent
    qt_app.processEvents()
    assert not _active_timers(table), "pulse must stop when the table is hidden"

    skeleton.clear_skeleton_rows(table)
    stack.deleteLater()
    other.deleteLater()
    qt_app.processEvents()


def test_no_pulse_after_clear_even_if_the_table_is_shown_again(qt_app):
    """Once the real rows have landed, nothing may pulse again.

    Scope note: this pins the observable behaviour, NOT the mechanism. It does
    not discriminate on dispose()'s removeEventFilter() call — dropping the
    registry reference also drops the Python wrapper PyQt needs to dispatch
    eventFilter back into Python, so the timer stays stopped either way. Do not
    read a pass here as proof the filter was detached.
    """
    stack = QStackedWidget()
    table = QTableWidget(0, 3)
    stack.addWidget(table)
    stack.show()
    qt_app.processEvents()

    skeleton.insert_skeleton_rows(table, count=3)
    qt_app.processEvents()
    assert _active_timers(table)

    skeleton.clear_skeleton_rows(table)
    table.hide()
    table.show()                        # would restart a still-installed filter
    qt_app.processEvents()

    assert not _active_timers(table), (
        "something restarted the pulse after the real rows replaced the "
        "skeleton — the table would keep repainting placeholder shading"
    )

    stack.deleteLater()
    qt_app.processEvents()
