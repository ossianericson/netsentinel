"""Performance instrumentation helpers (UX Sprint 10, S10-1).

Pure stdlib — no PyQt imports — so these helpers are unit-testable without a
QApplication. Two independent concerns live here:

1. ``warn_if_nav_slow`` — a permanent regression guard called from
   ``ui/nav/builder.py._nav_rail_go_to()`` on every navigation.
2. ``profile_page_init`` — an opt-in (env-var gated) cProfile wrapper around
   page construction, used to find the slowest ``ui/pages/*.py`` constructors
   during startup. Disabled by default so normal runs pay zero overhead.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable, Dict, List, Tuple, TypeVar

_logger = logging.getLogger("netsentinel.perf")

#: RULE-UX1 target — navigations slower than this are logged as a warning.
NAV_SLOW_THRESHOLD_MS = 150.0

T = TypeVar("T")


def warn_if_nav_slow(label: str, elapsed_ms: float) -> None:
    """Log a warning when navigating to ``label`` took longer than the threshold."""
    if elapsed_ms > NAV_SLOW_THRESHOLD_MS:
        _logger.warning(
            "Navigation to %r took %.0fms (exceeds %.0fms threshold)",
            label, elapsed_ms, NAV_SLOW_THRESHOLD_MS,
        )


def _slowest_page_inits(stats: Dict[tuple, tuple], n: int = 10) -> List[Tuple[float, str]]:
    """Extract the n slowest ``__init__`` calls under ui/pages/ from raw cProfile stats.

    ``stats`` is the ``{(file, line, func): (cc, nc, tt, ct, callers)}`` dict
    exposed by ``pstats.Stats.stats``. Pulled out as a pure function so the
    filtering/sorting logic can be tested without running a real profiler.
    """
    rows: List[Tuple[float, str]] = []
    for func, values in stats.items():
        file_path, _line, name = func
        cumulative_time = values[3]
        norm = str(file_path).replace("\\", "/")
        if name == "__init__" and "ui/pages/" in norm:
            rows.append((cumulative_time, f"{Path(file_path).stem}.{name}"))
    rows.sort(key=lambda row: row[0], reverse=True)
    return rows[:n]


def profile_page_init(build_fn: Callable[[], T]) -> T:
    """Run ``build_fn()`` and, if opted in, log the 10 slowest page constructors.

    Opt-in via the ``NETSENTINEL_PROFILE_PAGES=1`` environment variable —
    cProfile overhead is not paid on every normal startup.
    """
    if os.environ.get("NETSENTINEL_PROFILE_PAGES") != "1":
        return build_fn()

    import cProfile
    import pstats

    profiler = cProfile.Profile()
    profiler.enable()
    try:
        return build_fn()
    finally:
        profiler.disable()
        slowest = _slowest_page_inits(pstats.Stats(profiler).stats)
        _logger.info("Page init profiling — 10 slowest ui/pages/*.py constructors:")
        for cumulative_time, label in slowest:
            _logger.info("  %.1fms  %s", cumulative_time * 1000, label)
