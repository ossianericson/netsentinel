"""test_live_graph_redraw.py — silence the two matplotlib stderr floods from the
live latency graph (``ui/live_graph.py``).

Two log spammers surfaced in the 2026-07 Store chaos run, both non-functional but
together ~82% of the entire stderr log:

* ``No artists with labels found for legend`` (467x) — ``redraw()`` called
  ``ax.legend()`` unconditionally, so an early redraw with no plotted series (nothing
  labelled yet) warned every time.
* ``Tight layout not applied. The … margins cannot be made large enough …`` (6018x)
  — the small 8x3 figure could not satisfy ``set_tight_layout`` with its title +
  axis labels + legend, and matplotlib re-evaluates (and re-warns) that constraint on
  **every** ``draw_idle()``. Fixed by using explicit ``subplots_adjust`` margins
  instead — the same pattern ``ui/topology_widget.py`` already uses for this reason.

These are behavioural/structural regression guards (RULE-T3): both fail against the
pre-fix code and pass after.
"""
from __future__ import annotations

import warnings

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 not available", allow_module_level=True)

matplotlib = pytest.importorskip("matplotlib")


def _teardown(w) -> None:
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # non-fatal — C++ object already gone
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_redraw_empty_series_emits_no_legend_warning():
    """An early redraw with no plotted data must not warn about an empty legend."""
    from ui.live_graph import LiveGraphWidget

    w = None
    try:
        w = LiveGraphWidget()
        assert not w._series  # no data added yet
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            w.redraw()
        legend_warnings = [
            str(x.message) for x in caught
            if "No artists with labels" in str(x.message)
        ]
        assert not legend_warnings, (
            "redraw() with no series still calls ax.legend() with no labelled "
            f"artists: {legend_warnings}"
        )
    finally:
        if w is not None:
            _teardown(w)


def test_figure_does_not_use_tight_layout_engine():
    """The figure must not carry a tight-layout engine — that engine re-warns
    ('Tight layout not applied') on every draw for this small figure. Explicit
    subplots_adjust margins are used instead."""
    from matplotlib.layout_engine import TightLayoutEngine

    from ui.live_graph import LiveGraphWidget

    w = None
    try:
        w = LiveGraphWidget()
        assert not isinstance(w._fig.get_layout_engine(), TightLayoutEngine), (
            "live_graph figure uses a tight-layout engine; it cannot satisfy the "
            "constraint at this size and re-warns on every redraw. Use "
            "self._fig.subplots_adjust(...) instead (see ui/topology_widget.py)."
        )
    finally:
        if w is not None:
            _teardown(w)


def test_redraw_with_data_emits_no_tight_layout_warning():
    """A real draw with data must not emit the tight-layout or legend warnings."""
    from ui.live_graph import LiveGraphWidget

    w = None
    try:
        w = LiveGraphWidget()
        w.add_ping_point(0.0, "1.1.1.1", 12.0)
        w.add_ping_point(1.0, "1.1.1.1", 15.0)
        w.add_ping_point(2.0, "gateway", None)  # a timeout marker too
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            w.redraw()
            w._fig.canvas.draw()  # force a real render so the layout engine evaluates
        noisy = [
            str(x.message) for x in caught
            if "Tight layout not applied" in str(x.message)
            or "No artists with labels" in str(x.message)
        ]
        assert not noisy, f"redraw()+draw() still emits matplotlib spam: {noisy}"
    finally:
        if w is not None:
            _teardown(w)
