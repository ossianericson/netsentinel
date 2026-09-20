"""Where app-health conditions meet Qt (error-surfacing S4, D2) — the only ui/ subscriber.

``modules.app_health.AppHealth`` notifies its subscribers on the *reporting* thread: a
notification delivery thread, the REST API server thread, a worker's QThread. A widget
touched from any of those is undefined behaviour in Qt — not an exception, a native fault
some time later. So nothing in ui/ subscribes except ``AppHealthBridge``, whose callback
does one thread-safe thing: it emits a signal wired to its own slot with an explicit
``QueuedConnection``. Every surface hangs off ``changed``, which therefore always fires on
the GUI thread and never inside the reporter's call stack (S4.4a).

Subscribers hear transitions only (raise and resolve), so the surfaces repaint once per
change of state, never per retry.

The surface shipped behind ``experimental/app_health_v1`` (RULE-EXP1) and the flag was
retired in S10.2, once the owner had accepted it live (S4.5) — where the strip found a
failing report scheduler on its own. There is no longer an off path: the strip, the tray
dot and the listener seeding are wired unconditionally in ``app.py::main``.
"""
from __future__ import annotations

from typing import List

from PyQt6.QtCore import QObject, Qt, pyqtSignal, pyqtSlot

from modules.app_health import AppHealth, Condition

__all__ = ["AppHealthBridge", "attach_surface"]


class AppHealthBridge(QObject):
    """Relays registry transitions to the GUI thread. Create it on the GUI thread."""

    #: A condition was raised or resolved. Always emitted on the GUI thread.
    changed = pyqtSignal()
    _transition = pyqtSignal()

    def __init__(self, health: AppHealth, parent=None) -> None:
        super().__init__(parent)
        self._health = health
        # Queued even for a same-thread emit: a repaint must never run inside the
        # report_failure() call that raised the condition.
        self._transition.connect(self._relay, Qt.ConnectionType.QueuedConnection)
        health.subscribe(self._on_transition)

    def conditions(self) -> List[Condition]:
        """The registry's active conditions, most severe first."""
        return self._health.active()

    def _on_transition(self, _condition: Condition) -> None:
        # Reporting thread. Emitting a signal is thread-safe; touching a widget is not.
        self._transition.emit()

    @pyqtSlot()
    def _relay(self) -> None:
        self.changed.emit()


def attach_surface(window, health: AppHealth) -> AppHealthBridge:
    """Draw ``health`` on Home's strip and the tray dot, now and on every transition.

    The first render happens here, not on the first transition: the listeners fail within
    milliseconds of ``start()``, long before the window exists, so a surface that waited
    for a transition would never show a startup failure (plan §3, found in S3).
    """
    bridge = AppHealthBridge(health, parent=window)

    def _render() -> None:
        conditions = bridge.conditions()
        home = getattr(window, "_home_page", None)
        if home is not None:
            home.set_app_health(conditions)
        tray = getattr(window, "_tray_manager", None)
        if tray is not None:
            tray.set_app_health(conditions)

    bridge.changed.connect(_render)
    _render()
    window._app_health_bridge = bridge
    # The pills read the scan registry, not this bridge; attaching is what turns their
    # failing state on (ui/monitor_state.py::_pill_failures), so paint it once now.
    repaint_pills = getattr(window, "_repaint_pill_failures", None)
    if repaint_pills is not None:
        repaint_pills()
    return bridge
