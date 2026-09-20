"""S4.4a — app-health transitions reach Qt surfaces on the GUI thread, never on the reporter's.

``AppHealth`` calls its subscribers on whatever thread reported: a notification delivery
thread, the REST API server thread, a worker's QThread. A widget touched from any of those
is undefined behaviour in Qt — not an exception, a native fault some time later. The bridge
is the single place the registry meets Qt, and it defers every transition through a queued
signal, so nothing downstream of it can be reached off the GUI thread.
"""
from __future__ import annotations

import ast
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from modules.app_health import AppHealth  # noqa: E402
from modules.app_health_catalogue import MONITORS, SYSLOG_RECEIVER  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _pump(qt_app, until, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qt_app.processEvents()
        if until():
            return True
        time.sleep(0.01)
    return until()


@pytest.fixture
def bridge(qt_app):
    from ui.app_health_bridge import AppHealthBridge

    health = AppHealth()
    b = AppHealthBridge(health)
    yield b, health
    b.deleteLater()
    for _ in range(3):
        qt_app.processEvents()


def test_a_transition_reported_off_the_gui_thread_is_delivered_on_it(qt_app, bridge):
    from PyQt6.QtCore import QThread

    b, health = bridge
    delivered_on: list = []
    b.changed.connect(lambda: delivered_on.append(QThread.currentThread() is qt_app.thread()))

    reporter = threading.Thread(
        target=lambda: health.report_failure(MONITORS["Availability"], detail="boom"),
        name="notification-delivery",
    )
    reporter.start()
    reporter.join(5)

    assert _pump(qt_app, lambda: bool(delivered_on)), "the transition never reached the GUI thread"
    assert delivered_on == [True]


def test_a_transition_reported_on_the_gui_thread_is_still_deferred(qt_app, bridge):
    """A subscriber runs inside ``report_failure()``'s caller. Repainting from there would
    re-enter whatever widget code reported the failure — so even the GUI thread waits a turn."""
    b, health = bridge
    seen: list = []
    b.changed.connect(lambda: seen.append(True))

    health.report_failure(SYSLOG_RECEIVER)
    assert seen == []

    assert _pump(qt_app, lambda: bool(seen))


def test_repeats_do_not_repaint(qt_app, bridge):
    b, health = bridge
    seen: list = []
    b.changed.connect(lambda: seen.append(True))

    for _ in range(5):
        health.report_failure(MONITORS["Service"])
    _pump(qt_app, lambda: False, timeout=0.2)

    assert seen == [True]


def test_conditions_is_the_registrys_active_list(bridge):
    b, health = bridge
    health.report_failure(SYSLOG_RECEIVER)
    health.report_failure(MONITORS["Service"])

    assert [c.key for c in b.conditions()] == ["monitor:service", "listener:syslog"]


def test_the_bridge_is_the_only_ui_subscriber():
    """Any other ``subscribe()`` in ui/ would be a callback that can run off the GUI thread."""
    offenders = []
    for path in sorted((_REPO_ROOT / "ui").rglob("*.py")):
        if path.name == "app_health_bridge.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "subscribe"):
                offenders.append(f"{path.relative_to(_REPO_ROOT)}:{node.lineno}")
    assert not offenders, f"subscribe() outside ui/app_health_bridge.py: {offenders}"


def test_the_experimental_flag_is_fully_retired():
    """S10.2 — RULE-EXP1's gate came off once the owner accepted the surface live (S4.5).

    A half-removed flag is the failure this guards: a stray ``app_health_ui_enabled()``
    left in one page would keep that one surface dark while the rest drew, which is
    harder to notice than the whole surface being off.
    """
    from ui import app_health_bridge

    assert not hasattr(app_health_bridge, "FLAG_KEY")
    assert not hasattr(app_health_bridge, "app_health_ui_enabled")

    offenders = []
    for path in sorted((_REPO_ROOT / "ui").rglob("*.py")) + [_REPO_ROOT / "app.py"]:
        text = path.read_text(encoding="utf-8")
        # A module docstring cannot read a setting, and app_health_bridge's records why
        # the flag went away — scan the code, not the history note above it.
        doc = ast.get_docstring(ast.parse(text))
        if doc:
            text = text.replace(doc, "")
        if "experimental/app_health_v1" in text or "app_health_ui_enabled" in text:
            offenders.append(path.relative_to(_REPO_ROOT).as_posix())
    assert not offenders, (
        "the retired experimental/app_health_v1 flag is still read in: "
        f"{offenders} — the app-health surface ships unconditionally since S10.2"
    )
