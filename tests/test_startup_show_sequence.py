"""
tests/test_startup_show_sequence.py — Phase 5.5 tray-only startup.

The Dashboard-constructing cases run out-of-process (tests/_startup_minimised_child.py)
per RULE-TP4-DASH — see that file's docstring, or tests/_lazy_pages_child.py's for
the full mechanism (a real Dashboard cannot be created-and-destroyed in-process
on Windows without a Qt/QThread teardown crash).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_CHILD = Path(__file__).resolve().parent / "_startup_minimised_child.py"
_REPO_ROOT = Path(__file__).resolve().parent.parent
_CHILD_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def _run_child(name: str) -> None:
    r = subprocess.run(
        [sys.executable, str(_CHILD), name],
        capture_output=True,
        text=True,
        env=_CHILD_ENV,          # inherits conftest's hermetic AppData redirect
        cwd=str(_REPO_ROOT),
        timeout=120,
    )
    assert r.returncode == 0, (
        f"startup_minimised child {name!r} failed (rc={r.returncode}):\n"
        f"--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}"
    )


def test_start_minimised_true_not_visible_pending_maximized():
    _run_child("test_start_minimised_true_not_visible_pending_maximized")


def test_start_minimised_false_still_maximized_and_visible():
    _run_child("test_start_minimised_false_still_maximized_and_visible")


def test_offscreen_normal_rect_gets_clamped_onto_current_screen():
    _run_child("test_offscreen_normal_rect_gets_clamped_onto_current_screen")
