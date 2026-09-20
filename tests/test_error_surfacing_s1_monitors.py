"""S1.1 — a background monitor whose probe fails must not read as never-run.

``app.py::_wire_arp_watch`` / ``_wire_dhcp_watch`` answered a probe error with
``_set_flyout_dot(label, "")``, and ``""`` is the *never-run* colour: an
erroring monitor was pixel-identical to one that had never started.

The second half of the defect is an ownership conflict.
``ui/monitor_state.py::_push_monitor_pills`` repainted those same two dots
``GREEN if worker.isRunning() else ""``. A ``ProactiveProbeWorker`` keeps
running after a probe raises, so every later pill push turned the error dot
back to green — fixing only the error slot would not have held. The dots now
belong to the scan registry, the same ownership transfer F-57 already made for
Network Logger three lines above them in that file.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

import app as app_module  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


class _StubSignal:
    """Captures the slot a wiring function connects, so it can be fired."""

    def __init__(self) -> None:
        self.slots: list = []

    def connect(self, slot, *_a, **_k) -> None:
        self.slots.append(slot)

    def emit(self, *args) -> None:
        for slot in self.slots:
            slot(*args)


class _StubWorker:
    def __init__(self) -> None:
        self.probe_done = _StubSignal()
        self.error = _StubSignal()


class _StubWindow:
    """Records every dot / scan-state write the wiring performs."""

    def __init__(self) -> None:
        self.dots: list[tuple[str, str]] = []
        self.states: list[tuple[str, str, str | None]] = []

    def _set_flyout_dot(self, label: str, color: str) -> None:
        self.dots.append((label, color))

    def _nav_set_scan_state(self, label, state, ts=None, error=None, verdict=None) -> None:
        self.states.append((str(label), state, error))


@pytest.mark.parametrize(
    "wire_name, label",
    [
        ("_wire_arp_watch", "ARP Spoof Watch"),
        ("_wire_dhcp_watch", "DHCP Rogue Monitor"),
    ],
)
def test_background_watch_error_records_an_error_state(wire_name, label):
    """The probe failed. That is a state of its own, not an empty dot."""
    window, worker = _StubWindow(), _StubWorker()
    getattr(app_module, wire_name)(window, worker, alerts=None, store=None)

    worker.error.emit("Npcap is not installed")

    assert ("", ) not in [(c,) for _, c in window.dots], (
        f"{wire_name} cleared the {label} dot — that is the never-run colour"
    )
    assert (label, "error", "Npcap is not installed") in window.states, (
        f"{wire_name} recorded no error state for {label}; states={window.states}"
    )


def _push_monitor_pills_source() -> str:
    src = (REPO_ROOT / "ui" / "monitor_state.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_push_monitor_pills":
            return ast.get_source_segment(src, node) or ""
    raise AssertionError("_push_monitor_pills not found in ui/monitor_state.py")


@pytest.mark.parametrize("label", ["ARP Spoof Watch", "DHCP Rogue Monitor"])
def test_push_monitor_pills_no_longer_owns_the_watch_dots(label):
    """Guard the ownership transfer against reintroduction.

    A ``_set_flyout_dot(label, GREEN if running else "")`` line here overwrites
    whatever the registry last recorded, including an error — and the worker
    keeps running after a failed probe, so ``isRunning()`` stays True.
    """
    body = _push_monitor_pills_source()
    assert f'_set_flyout_dot("{label}"' not in body, (
        f"_push_monitor_pills writes the {label} dot again. That dot belongs to "
        "the scan registry (_nav_set_scan_state); a raw write here stomps the "
        "error state a failed probe just recorded."
    )
