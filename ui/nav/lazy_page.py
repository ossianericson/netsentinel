"""
ui.nav.lazy_page — deferred page-construction placeholder.

Part of the startup-slow-construction fix (RULE-EXP1 graduated to permanent —
deferred construction is no longer flag-gated; see docs/spikes/startup-com-reentrancy.md
and the ``project_com_reentrancy_startup_crash`` memory for the full rationale: all
~60 page widgets were being constructed eagerly inside ``Dashboard.__init__`` and the
whole tree polished in one shot when attached to the styled window, which is what
Windows' ``IsHungAppWindow`` flagged as a startup "hang".

A ``_LazyPageHost`` is a lightweight QWidget registered in the ``QStackedWidget``
and ``_nav_label_to_widget`` map *in place of* a real page.  It holds a zero-arg
``factory`` callable that builds (and self-assigns) the real page on demand.  The
dashboard swaps the real widget in via ``_NavBuilderMixin._materialize_host`` on
first navigation or when the background chunk-builder reaches it — whichever
happens first.
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ui.styles import themed_ss


class _LazyPageHost(QWidget):
    """Placeholder standing in for a not-yet-constructed page.

    Parameters
    ----------
    factory:
        Zero-arg callable that constructs the real page, assigns it to the owning
        Dashboard attribute (e.g. ``self._ip_calc_page = IpCalculatorPage(...)``)
        and returns it.  Run at most once, by ``_materialize_host``.
    nav_label:
        The canonical nav label the page registers under.  Stored for debugging
        and the placeholder text; materialization re-points the map by identity,
        so this is not load-bearing for lookup.
    """

    def __init__(self, factory: Callable[[], QWidget], nav_label: str,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._factory = factory
        self._nav_label = nav_label
        self._materialized = False
        self._real: Optional[QWidget] = None
        themed_ss(self, "QWidget {{ background:{BG_DARK}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._placeholder = QLabel("Loading…")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        themed_ss(
            self._placeholder,
            "color:{TEXT_SECONDARY}; font-size:13px; background:transparent; border:none;",
        )
        lay.addWidget(self._placeholder)


class _LazyPageMixin:
    """Deferred page-construction runtime, mixed into Dashboard.

    Split out of ``ui/nav/builder.py`` (RULE-AH1) — the placeholder swap logic
    and background chunk-builder. State (``_lazy_hosts``, ``_lazy_build_timer``)
    is created in ``Dashboard.__init__``. The on-first-nav trigger itself lives
    in ``_NavBuilderMixin._nav_rail_go_to``.
    """

    def _lazy_or_build(self, attr: str, nav_label: str,
                       factory: Callable[[], QWidget]) -> None:
        """Register a _LazyPageHost placeholder; the real page is built later.

        ``factory`` is a zero-arg callable that builds the real page, assigns it to
        ``self.<attr>`` and returns it. A placeholder is stored at ``self.<attr>``
        immediately and the factory is deferred to ``_materialize_host`` (first-nav
        hook or background chunk-builder).
        """
        host = _LazyPageHost(factory, nav_label)
        setattr(self, attr, host)
        self._lazy_hosts.append(host)

    def _materialize_host(self, host: "_LazyPageHost") -> QWidget:
        """Build a placeholder's real page and swap it into the stack + nav map.

        Idempotent — a second call returns the already-built widget. Safe to call
        for a host that is no longer registered (returns the built widget anyway).
        """
        if host._materialized:
            return host._real
        host._materialized = True
        real = host._factory()          # builds + re-assigns self.<attr> = real
        host._real = real

        # Re-point every label that currently maps to this host (normally one).
        labels = [lbl for lbl, w in self._nav_label_to_widget.items() if w is host]
        for lbl in labels:
            self._nav_label_to_widget[lbl] = real
        for sec in self._nav_sections:
            for e in sec["entries"]:
                if e.page is host:
                    e.page = real

        idx = self._stack.indexOf(host)
        self._stack.addWidget(real)
        if idx >= 0:
            self._stack.removeWidget(host)
        if host in self._lazy_hosts:
            self._lazy_hosts.remove(host)

        # Wire the ? help button now that the real header exists (the startup
        # _proactive_wire_page_help_btns pass skipped the placeholder).
        from ui.help import _PAGE_HELP
        for lbl in labels:
            info = _PAGE_HELP.get(lbl, {})
            if info.get("what"):
                self._wire_page_help_btn(lbl, info, page=real)

        host.deleteLater()
        return real

    def _start_lazy_page_builder(self) -> None:
        """Start the background chunk-builder that drains _lazy_hosts after show.

        Parented QTimer (RULE-WIN5). Idempotent — a no-op if the queue is empty
        or the builder is already running.
        """
        if getattr(self, "_lazy_build_timer", None) is not None:
            return
        if not self._lazy_hosts:
            return
        from PyQt6.QtCore import QTimer as _QTimer
        t = _QTimer(self)
        t.setInterval(150)                # gentle cadence; ~2 pages / 150 ms
        t.timeout.connect(self._lazy_build_tick)
        t.start()
        self._lazy_build_timer = t

    def _lazy_build_tick(self) -> None:
        """Materialize up to 2 queued hosts per tick; stop the timer when drained."""
        built = 0
        while self._lazy_hosts and built < 2:
            self._materialize_host(self._lazy_hosts[0])   # removes itself from queue
            built += 1
        if not self._lazy_hosts and getattr(self, "_lazy_build_timer", None) is not None:
            self._lazy_build_timer.stop()
            self._lazy_build_timer = None

    def _materialize_all_pages(self) -> None:
        """Force-build every remaining placeholder (for code that iterates all pages)."""
        for host in list(getattr(self, "_lazy_hosts", [])):
            self._materialize_host(host)

    def _feed_protocol_viz_context(self, **kwargs) -> None:
        """Route a ProtocolVizPage.set_context() call around lazy construction.

        Unlike every other lazy page, Protocol Visualizer is fed by scan-result
        handlers (tabs_network.py, scan_enrichment.py) that fire on every scan
        regardless of nav state — there is no "navigate first" guard to rely on
        for materialization. While the page is still a _LazyPageHost, buffer the
        kwargs instead of calling set_context() on the placeholder (AttributeError);
        the factory in tabs.py replays them once the real page is built, so the
        first-ever visit still shows current data instead of an empty state.
        """
        page = self._protocol_viz_page
        if isinstance(page, _LazyPageHost):
            self._protocol_viz_pending_context = kwargs
        else:
            page.set_context(**kwargs)

    def _feed_app_traffic_label_map(self, label_map: dict) -> None:
        """Route an AppTrafficPage.set_label_map() call around lazy construction.

        scan_enrichment.py recomputes the MAC->hostname label map on every scan,
        independent of nav state (same shape of problem as
        _feed_protocol_viz_context above). AppTrafficPage starts with an empty
        _label_map and has no independent way to re-derive it at construction
        time, so a call dropped while the page is still a placeholder would
        leave real traffic rows showing raw MACs until the *next* scan. Buffer
        it instead; the factory in tabs.py replays it once the real page is built.
        """
        page = self._app_traffic_page
        if isinstance(page, _LazyPageHost):
            self._app_traffic_pending_label_map = dict(label_map)
        else:
            page.set_label_map(label_map)

    def _ensure_page(self, attr: str):
        """Return the real widget at self.<attr>, force-materializing it first if needed.

        For lazy pages that are also the *target* of a cross-page signal fired by
        an eager page (e.g. inventory_page.show_connections_for reaching into
        connections_page before the user has ever navigated there) — unlike
        _feed_*_context above, these call sites need to act on the real widget
        immediately (focus/select a row), not buffer-and-replay, so materializing
        on demand is the correct behavior rather than a degradation to paper over.
        """
        page = getattr(self, attr)
        if isinstance(page, _LazyPageHost):
            return self._materialize_host(page)
        return page
