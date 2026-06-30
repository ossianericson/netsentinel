"""scan_status_md.py — render the Security-Audit scan registry as Markdown.

Pure Python (no PyQt, no DB writes) so it is unit-testable headless. The Security
Overview "Copy as Markdown" button passes the live ``_scan_registry`` dict plus the
ordered ``_AUDIT_SCAN_LABELS`` tuple to :func:`render_scan_status_md`, then copies
the returned string to the clipboard for pasting into a ticket, email, or report.

Registry entry shape (set by ``_nav_set_scan_state`` in ``ui/nav/builder.py``)::

    registry[label] = {"state": str, "ts": float, "error": str|None, "verdict": str|None}

``state`` is one of ``never | running | fresh | stale | error``.
"""

from __future__ import annotations

import time
from typing import Mapping, Sequence

# state key → human-readable label (mirrors _STATE_LABELS in security_overview_page.py)
_STATE_LABELS = {
    "fresh": "Fresh",
    "stale": "Stale",
    "running": "Running",
    "error": "Error",
    "never": "Never run",
}


def _format_age(ts: float, now: float) -> str:
    """Return a coarse human age like ``"just now"``, ``"5m ago"``, ``"3h ago"``.

    ``ts`` of 0 (or falsy) means the scan never ran → ``"Never"``.
    """
    if not ts:
        return "Never"
    delta = max(0.0, now - ts)
    if delta < 45:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    return f"{int(delta // 86400)}d ago"


def _escape_cell(text: str) -> str:
    """Escape characters that would break a Markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def render_scan_status_md(
    registry: Mapping[str, Mapping[str, object]],
    labels: Sequence[str],
    *,
    now: float | None = None,
    title: str = "NetSentinel Scan Status",
) -> str:
    """Render the scan registry as a GitHub-flavoured Markdown table.

    Parameters
    ----------
    registry: mapping of nav label → scan-state entry (see module docstring).
    labels:   ordered nav labels to render, one row each (e.g. ``_AUDIT_SCAN_LABELS``).
    now:      reference epoch for age formatting; defaults to ``time.time()``.
    title:    H2 heading placed above the table.
    """
    now = time.time() if now is None else now

    lines = [f"## {title}", "", "| Tool | State | Last run | Finding |",
             "| --- | --- | --- | --- |"]

    for label in labels:
        entry = registry.get(label, {}) or {}
        state = str(entry.get("state") or "never")
        ts_raw = entry.get("ts") or 0.0
        ts = float(ts_raw) if isinstance(ts_raw, (int, float, str)) else 0.0
        verdict = entry.get("verdict")
        error = entry.get("error")

        state_label = _STATE_LABELS.get(state, _STATE_LABELS["never"])
        age = _format_age(ts, now)
        finding = verdict or error or "—"

        lines.append(
            f"| {_escape_cell(label)} | {state_label} | {age} | {_escape_cell(str(finding))} |"
        )

    return "\n".join(lines)
