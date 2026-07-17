"""
protocol_canvas_glyphs — small vector role icons for ProtocolCanvas nodes.

One builder per role in `_ROLE_COLOR` (ui/widgets/protocol_canvas.py). Each
builder returns a QPainterPath of simple shapes sized to fit the given square
QRectF — no image assets, no new dependency.
"""
from __future__ import annotations

from typing import Callable, Dict

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QPainterPath


def _laptop(r: QRectF) -> QPainterPath:
    """client — a laptop base + screen."""
    p = QPainterPath()
    w, h = r.width(), r.height()
    screen = QRectF(r.left() + w * 0.14, r.top(), w * 0.72, h * 0.62)
    p.addRoundedRect(screen, w * 0.06, w * 0.06)
    base = QRectF(r.left(), r.top() + h * 0.72, w, h * 0.16)
    p.addRoundedRect(base, w * 0.05, w * 0.05)
    return p


def _router(r: QRectF) -> QPainterPath:
    """gateway — a router box with two antennas."""
    p = QPainterPath()
    w, h = r.width(), r.height()
    box = QRectF(r.left(), r.top() + h * 0.45, w, h * 0.4)
    p.addRoundedRect(box, w * 0.08, w * 0.08)
    for fx in (0.3, 0.7):
        ax = r.left() + w * fx
        p.moveTo(ax, r.top() + h * 0.45)
        p.lineTo(ax, r.top())
    return p


def _globe(r: QRectF) -> QPainterPath:
    """dns — a globe: outer circle + one meridian + one parallel ellipse."""
    p = QPainterPath()
    p.addEllipse(r)
    cx, cy = r.center().x(), r.center().y()
    p.addEllipse(QRectF(cx - r.width() * 0.18, r.top(), r.width() * 0.36, r.height()))
    p.moveTo(r.left(), cy)
    p.lineTo(r.right(), cy)
    return p


def _server(r: QRectF) -> QPainterPath:
    """server — a two-slot server rack."""
    p = QPainterPath()
    w, h = r.width(), r.height()
    slot_h = h * 0.42
    for i in range(2):
        slot = QRectF(r.left(), r.top() + i * (slot_h + h * 0.08), w, slot_h)
        p.addRoundedRect(slot, w * 0.06, w * 0.06)
        dot_y = slot.center().y()
        p.addEllipse(r.right() - w * 0.18, dot_y - h * 0.03, w * 0.08, h * 0.06)
    return p


def _broadcast(r: QRectF) -> QPainterPath:
    """broadcast — a dot with two radiating quarter-arcs."""
    p = QPainterPath()
    w, h = r.width(), r.height()
    cx, cy = r.center().x(), r.center().y()
    dot_r = w * 0.12
    p.addEllipse(cx - dot_r, cy - dot_r, dot_r * 2, dot_r * 2)
    for scale in (0.55, 0.95):
        arc_rect = QRectF(cx - w * scale / 2, cy - h * scale / 2, w * scale, h * scale)
        p.arcMoveTo(arc_rect, 200)
        p.arcTo(arc_rect, 200, 140)
    return p


def _switch(r: QRectF) -> QPainterPath:
    """switch — a box with a row of port ticks."""
    p = QPainterPath()
    w, h = r.width(), r.height()
    box = QRectF(r.left(), r.top() + h * 0.2, w, h * 0.6)
    p.addRoundedRect(box, w * 0.06, w * 0.06)
    port_y0 = box.top() + h * 0.15
    port_y1 = box.bottom() - h * 0.15
    for i in range(4):
        px = box.left() + w * (0.14 + i * 0.24)
        p.moveTo(px, port_y0)
        p.lineTo(px, port_y1)
    return p


def _root(r: QRectF) -> QPainterPath:
    """root — a root-bridge tree: trunk node with two branch nodes below."""
    p = QPainterPath()
    w, h = r.width(), r.height()
    top_r = w * 0.14
    cx = r.center().x()
    top_c = (cx, r.top() + h * 0.15)
    p.addEllipse(top_c[0] - top_r, top_c[1] - top_r, top_r * 2, top_r * 2)
    for fx in (0.22, 0.78):
        leaf_c = (r.left() + w * fx, r.bottom() - h * 0.15)
        leaf_r = w * 0.11
        p.addEllipse(leaf_c[0] - leaf_r, leaf_c[1] - leaf_r, leaf_r * 2, leaf_r * 2)
        p.moveTo(*top_c)
        p.lineTo(*leaf_c)
    return p


ROLE_GLYPHS: Dict[str, Callable[[QRectF], QPainterPath]] = {
    "client":    _laptop,
    "gateway":   _router,
    "dns":       _globe,
    "server":    _server,
    "broadcast": _broadcast,
    "switch":    _switch,
    "root":      _root,
}
