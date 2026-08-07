"""
claim_ranking — the ui/ side of modules/relevance.py.

Signal Quality Phase 5. Every surface that shows a list of claims needs the same
two lookups before it can rank one (the importance-tier map and the user's
dismissal history), and both are per-render MetricStore reads that would
otherwise be copy-pasted into six pages. This is that boilerplate, once.

The ranking policy itself lives in `modules/relevance.py` (ARCH RULE 1 — pure
Python, no PyQt). Nothing here decides ordering; it fetches inputs, calls
relevance, and hands back rows in the caller's own shape.

Two distinct uses, deliberately kept separate:

  * `rank_alert_rows()` / `rank_device_events()` — reorder a list. For surfaces
    that are a *priority queue* (the Home "Action needed" card, the Overview
    activity tile, a per-host drawer).
  * `top_by_relevance()` — choose WHICH rows survive a cap, without reordering
    them. For surfaces that are a *chronological record* (Timeline, Alert
    History). A timeline reordered by importance stops being a timeline, but its
    row cap is still a relevance decision — and it was being made by accident,
    as "whichever N happen to be newest".
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional, Sequence

from modules.relevance import (
    claim_from_alert_row,
    claim_from_device_event,
    score,
)

__all__ = [
    "ranking_context",
    "rank_alert_rows",
    "rank_device_events",
    "top_by_relevance",
]


def ranking_context(store: Any) -> tuple:
    """Return `(tiers, dismissals)` for a render pass.

    Both are best-effort: a store that cannot answer (missing table on an old
    schema, closed connection) yields empty maps, and relevance treats an empty
    map as "unknown", which is neutral rather than suppressive. Ranking must
    never be the reason a page fails to draw.
    """
    tiers: dict = {}
    dismissals: dict = {}
    if store is None:
        return tiers, dismissals
    try:
        tiers = store.get_importance_tiers() or {}
    except Exception:
        pass  # non-fatal — unknown tiers rank neutrally, never low
    try:
        dismissals = store.get_dismissal_counts() or {}
    except Exception:
        pass  # non-fatal — no dismissal history just means no penalty
    return tiers, dismissals


def _rank_rows(
    rows: Sequence[Any],
    adapter: Callable[..., Any],
    store: Any,
    limit: Optional[int],
) -> List[Any]:
    if not rows:
        return []
    tiers, dismissals = ranking_context(store)
    try:
        scored = [
            (score(adapter(row, tiers=tiers), dismissals=dismissals), i, row)
            for i, row in enumerate(rows)
        ]
    except Exception:
        # Ranking is an improvement on the caller's existing order, never a
        # precondition for showing anything. A malformed row must not blank the
        # page — fall back to the order we were given.
        return list(rows)[:limit] if limit else list(rows)
    # `i` breaks ties so the producer's own order survives, making the sort
    # stable and the surface stable across refreshes.
    scored.sort(key=lambda t: (-t[0], t[1]))
    ordered = [row for _, _, row in scored]
    return ordered[:limit] if limit else ordered


def rank_alert_rows(
    rows: Sequence[Any], store: Any = None, limit: Optional[int] = None
) -> List[Any]:
    """Most-relevant-first ordering for `alert_fired` rows."""
    return _rank_rows(rows, claim_from_alert_row, store, limit)


def rank_device_events(
    rows: Sequence[Any], store: Any = None, limit: Optional[int] = None
) -> List[Any]:
    """Most-relevant-first ordering for `device_event` rows."""
    return _rank_rows(rows, claim_from_device_event, store, limit)


def top_by_relevance(
    rows: Sequence[Any],
    adapter: Callable[..., Any],
    store: Any = None,
    limit: int = 200,
    key: Optional[Callable[[Any], Any]] = None,
) -> List[Any]:
    """Keep the `limit` most relevant rows, then restore the caller's order.

    For a chronological surface with a row cap. The cap decides what the user
    can see at all, so it should be answered by relevance — but the *display*
    order stays whatever `key` says (typically newest-first), because a record
    that is not in time order is not a record.
    """
    rows = list(rows)
    if len(rows) <= limit:
        return sorted(rows, key=key, reverse=True) if key else rows
    kept = _rank_rows(rows, adapter, store, limit)
    return sorted(kept, key=key, reverse=True) if key else kept
