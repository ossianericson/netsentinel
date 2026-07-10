"""Tests for the experimental/lazy_pages deferred page-construction path.

Phase 2 of the startup-slow-construction fix. Covers:
  * _LazyPageHost placeholder + materialize idempotency (in-process unit tests)
  * navigating to every deferred label materializes the real widget
  * the eager (flag-off) path constructs real pages directly (no hosts)

The three Dashboard-constructing cases run in a **subprocess** (tests/_lazy_pages_child.py):
a fully-constructed Dashboard cannot be created-and-destroyed in-process on Windows without
a Qt/QThread teardown crash, so `Dashboard.closeEvent()` uses `os._exit(0)`. In-process,
the autouse `_flush_qt_events` fixture would close the Dashboard, fire that os._exit(0), and
silently terminate the whole pytest session (the "os._exit test-suite mask"). Isolating each
Dashboard test in its own process keeps the suite honest. Guarded by
tests/test_suite_completes.py and RULE-TP4-DASH.

See project_com_reentrancy_startup_crash / project_test_suite_osexit_mask memory and
docs/spikes/startup-com-reentrancy.md.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QLabel

from ui.nav.lazy_page import _LazyPageHost


# ── _LazyPageHost unit behaviour (safe in-process — no Dashboard) ─────────────

def test_lazy_host_holds_placeholder(qt_app):
    built = []

    def factory():
        built.append(1)
        return QLabel("real")

    host = _LazyPageHost(factory, "Some Page")
    assert not host._materialized
    assert host._real is None
    assert built == []          # factory not run until materialized
    host.deleteLater()


def test_lazy_host_factory_runs_once_via_materialize(qt_app):
    """_materialize_host must be idempotent — factory runs at most once."""
    from ui.nav.lazy_page import _LazyPageMixin

    calls = []

    class _Stub(_LazyPageMixin):
        def __init__(self):
            from PyQt6.QtWidgets import QStackedWidget
            self._stack = QStackedWidget()
            self._nav_label_to_widget = {}
            self._nav_sections = []
            self._lazy_hosts = []

    def factory():
        w = QLabel("real")
        calls.append(w)
        return w

    stub = _Stub()
    host = _LazyPageHost(factory, "Some Page")
    stub._stack.addWidget(host)
    stub._nav_label_to_widget["Some Page"] = host
    stub._lazy_hosts.append(host)

    real1 = stub._materialize_host(host)
    real2 = stub._materialize_host(host)   # second call is a no-op

    assert len(calls) == 1
    assert real1 is real2
    assert real1 is calls[0]
    assert stub._nav_label_to_widget["Some Page"] is real1
    assert host not in stub._lazy_hosts
    assert stub._stack.indexOf(real1) >= 0
    stub._stack.deleteLater()


# ── Dashboard integration (out-of-process — see module docstring) ─────────────

_CHILD = Path(__file__).resolve().parent / "_lazy_pages_child.py"
_REPO_ROOT = Path(__file__).resolve().parent.parent
_CHILD_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def _run_child(name: str) -> None:
    """Run one Dashboard test body in a child process; assert it exits clean."""
    r = subprocess.run(
        [sys.executable, str(_CHILD), name],
        capture_output=True,
        text=True,
        env=_CHILD_ENV,          # inherits conftest's hermetic AppData redirect
        cwd=str(_REPO_ROOT),
        timeout=120,
    )
    assert r.returncode == 0, (
        f"lazy_pages child {name!r} failed (rc={r.returncode}):\n"
        f"--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}"
    )


def test_deferred_pages_are_hosts_until_navigated():
    _run_child("test_deferred_pages_are_hosts_until_navigated")


def test_materialize_all_drains_queue():
    _run_child("test_materialize_all_drains_queue")


def test_eager_path_builds_real_pages():
    _run_child("test_eager_path_builds_real_pages")
