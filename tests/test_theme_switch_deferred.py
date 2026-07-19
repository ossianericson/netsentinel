"""Tests for the experimental/theme_switch_deferred flag (theme-switch responsiveness).

Part 1 Step 2 of the theme-switch-responsiveness plan: when the flag is on,
Dashboard._on_theme_changed() (ui/dashboard.py) refreshes only the currently-visible
stack page immediately and queues every other page in `_theme_dirty_widgets`,
flushed lazily on first navigation to it (_nav_rail_go_to, ui/nav/builder.py).
Default False keeps the previously-verified eager fan-out byte-for-byte intact
(RULE-EXP1).

Dashboard-constructing cases run in a subprocess (tests/_theme_switch_deferred_child.py)
per RULE-TP4-DASH — see tests/_lazy_pages_child.py's docstring for the full mechanism
(Dashboard.closeEvent() ends in os._exit(0); in-process construction would silently
terminate the whole pytest session).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

_CHILD = Path(__file__).resolve().parent / "_theme_switch_deferred_child.py"
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
        f"theme_switch_deferred child {name!r} failed (rc={r.returncode}):\n"
        f"--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}"
    )


def test_deferred_flag_queues_offscreen_pages_and_flushes_on_nav():
    _run_child("test_deferred_flag_queues_offscreen_pages_and_flushes_on_nav")


def test_flag_off_refreshes_every_page_eagerly():
    _run_child("test_flag_off_refreshes_every_page_eagerly")


def test_dashboard_owns_no_widget_stylesheet_so_app_sheet_governs():
    """A widget-level sheet on the Dashboard outranks the app-level one (see child)."""
    _run_child("test_dashboard_owns_no_widget_stylesheet_so_app_sheet_governs")
