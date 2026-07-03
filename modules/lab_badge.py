"""
Lab Mode completion badge — local-only PNG export.

Vector-style hexagon/shield motif per RULE-I2's icon language, rendered on
the standalone dark export palette (modules/colours.py) so it never touches
the live Qt widget tree. Wording stays factual (title + completion date
only) — this is a personal keepsake, not a formal credential.
"""

from __future__ import annotations

import math
from pathlib import Path

from modules.colours import (
    ACCENT,
    ACCENT_DARK,
    BADGE_CLEAN_BG,
    BADGE_CLEAN_FG,
    EXPORT_BG,
    EXPORT_TEXT,
)

_FOOTER = "Completed locally in NetSentinel Lab Mode"


def _hexagon_points(cx: float, cy: float, r: float) -> list:
    """Pointy-top hexagon vertices per RULE-I2."""
    return [
        (cx + r * math.sin(math.radians(60 * i)), cy + r * math.cos(math.radians(60 * i)))
        for i in range(6)
    ]


def render_lab_badge_png(scenario_title: str, completed_at: str, output_path: Path) -> Path:
    """Render a Lab Mode completion badge and save it to output_path."""
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    from matplotlib.patches import FancyBboxPatch, Polygon

    fig = Figure(figsize=(6, 4), dpi=150, facecolor=EXPORT_BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(EXPORT_BG)
    ax.set_xlim(-1.4, 1.4)
    ax.set_ylim(-1.35, 1.05)
    ax.axis("off")

    ax.add_patch(Polygon(
        _hexagon_points(0.0, 0.42, 0.55), closed=True,
        facecolor=ACCENT, edgecolor=ACCENT_DARK, linewidth=2.5, zorder=2,
    ))
    # Shield silhouette inside the hexagon
    ax.add_patch(Polygon(
        [(-0.18, 0.68), (0.18, 0.68), (0.2, 0.4), (0.0, 0.14), (-0.2, 0.4)],
        closed=True, facecolor=EXPORT_TEXT, edgecolor="none", zorder=3,
    ))

    ax.add_patch(FancyBboxPatch(
        (-1.15, -1.2), 2.3, 0.85,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        facecolor=BADGE_CLEAN_BG, edgecolor="none", zorder=1,
    ))
    ax.text(0, -0.55, "NETSENTINEL LAB", ha="center", fontsize=11, fontweight="bold",
            color=BADGE_CLEAN_FG, zorder=3)
    ax.text(0, -0.8, scenario_title, ha="center", fontsize=13, fontweight="bold",
            color=EXPORT_TEXT, zorder=3)
    ax.text(0, -1.02, f"Completed {completed_at}", ha="center", fontsize=9,
            color=EXPORT_TEXT, zorder=3)
    ax.text(0, -1.22, _FOOTER, ha="center", fontsize=7.5,
            color=BADGE_CLEAN_FG, zorder=3)

    out = Path(output_path)
    fig.savefig(out, facecolor=EXPORT_BG)
    return out
