"""
Regression test for a claims-audit doc-vs-code mismatch (F-26): ui/help.py
for Wi-Fi Heatmap claims "Red = strong, blue = weak", but the page used
cmap="RdYlGn" with vmin=weak/vmax=strong -- weak rendered red and strong
rendered green, with no blue anywhere in the colormap.

This test extracts the actual cmap name used in
ui/pages/wifi_heatmap_page.py._draw_heatmap_layer() and checks its real
colour output at the weak (vmin) and strong (vmax) ends against matplotlib
directly, rather than asserting a specific cmap string -- any colormap
choice that satisfies "weak reads as blue-ish, strong reads as red-ish"
should pass.
"""
from __future__ import annotations

import re
from pathlib import Path

import matplotlib

ROOT = Path(__file__).parent.parent
SOURCE = (ROOT / "ui" / "pages" / "wifi_heatmap_page.py").read_text(encoding="utf-8")


def _heatmap_cmap_name() -> str:
    m = re.search(r'_draw_heatmap_layer.*?cmap="([^"]+)"', SOURCE, re.DOTALL)
    assert m, "could not find cmap= in _draw_heatmap_layer()"
    return m.group(1)


def test_no_longer_uses_backwards_red_yellow_green():
    assert _heatmap_cmap_name() != "RdYlGn"


def test_weak_end_reads_bluer_than_red_and_strong_end_reads_redder_than_blue():
    cmap = matplotlib.colormaps[_heatmap_cmap_name()]
    weak_rgba = cmap(0.0)     # vmin = HEATMAP_VMIN = weak signal
    strong_rgba = cmap(1.0)   # vmax = HEATMAP_VMAX = strong signal

    weak_r, _, weak_b, _ = weak_rgba
    strong_r, _, strong_b, _ = strong_rgba

    assert weak_b > weak_r, "weak (vmin) end should read blue-ish, not red-ish"
    assert strong_r > strong_b, "strong (vmax) end should read red-ish, not blue-ish"
