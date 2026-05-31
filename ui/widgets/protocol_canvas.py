"""
ProtocolCanvas — animated protocol diagram widget.

Renders a ProtocolSceneData as a live animation using QPainter.
Nodes are drawn as labelled rounded rectangles; each AnimStep shows a
coloured dot travelling between nodes with a label on the arrow.

Auto-plays at one step per ~2.3 s.  Supports play/pause/reset and
manual step-forward / step-back.

Signals:
    step_changed(int, int)   — current step index, total steps
    finished()               — all steps played
"""
from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import (
    QPointF, QRectF, Qt, QTimer, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen,
)
from PyQt6.QtWidgets import QWidget

from modules.protocol_animator import AnimNode, AnimStep, ProtocolSceneData
from ui.styles import (
    CANVAS_ACCENT, CANVAS_AMBER, CANVAS_BG, CANVAS_DIM,
    CANVAS_FG, CANVAS_GRAY, CANVAS_GREEN,
)

# ── Timing ─────────────────────────────────────────────────────────────────────
_FPS      = 30
_ANIM_MS  = 900    # ms for the dot to travel from src to dst
_HOLD_MS  = 1400   # ms to pause after arrival before advancing

# ── Visual constants ──────────────────────────────────────────────────────────
_BG          = QColor(CANVAS_BG)
_NODE_W      = 110
_NODE_H      = 58
_FONT_NODE   = QFont("Segoe UI", 8)
_FONT_PKT    = QFont("Segoe UI", 8, QFont.Weight.Bold)
_FONT_DETAIL = QFont("Segoe UI", 7)

_ROLE_COLOR: dict[str, str] = {
    "client":    CANVAS_ACCENT,
    "gateway":   CANVAS_GREEN,
    "dns":       CANVAS_AMBER,
    "server":    CANVAS_GRAY,
    "broadcast": CANVAS_DIM,
    "switch":    CANVAS_GRAY,
    "root":      CANVAS_GREEN,
}
_REPLY_COLOR  = QColor(CANVAS_GREEN)
_REQUEST_COLOR = QColor(CANVAS_ACCENT)


class ProtocolCanvas(QWidget):
    step_changed = pyqtSignal(int, int)   # (current_idx, total)
    finished     = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene:   Optional[ProtocolSceneData] = None
        self._step:    int   = 0
        self._phase:   str   = "done"   # "anim" | "hold" | "done"
        self._phase_ms: float = 0.0
        self._playing: bool  = False

        self._timer = QTimer(self)
        self._timer.setInterval(1000 // _FPS)
        self._timer.timeout.connect(self._tick)

        self.setMinimumHeight(240)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_scene(self, data: ProtocolSceneData) -> None:
        self._timer.stop()
        self._scene    = data
        self._step     = 0
        self._phase    = "hold"
        self._phase_ms = 0.0
        self._playing  = False
        self.update()
        if data.steps:
            self.step_changed.emit(0, len(data.steps))

    def play(self) -> None:
        if not self._scene or not self._scene.steps:
            return
        if self._phase == "done":
            self._step     = 0
            self._phase    = "anim"
            self._phase_ms = 0.0
        self._playing = True
        self._timer.start()

    def pause(self) -> None:
        self._playing = False
        self._timer.stop()
        self.update()

    def reset(self) -> None:
        self._timer.stop()
        self._playing  = False
        self._step     = 0
        self._phase    = "hold"
        self._phase_ms = 0.0
        self.update()
        if self._scene:
            self.step_changed.emit(0, len(self._scene.steps))

    def step_forward(self) -> None:
        if not self._scene:
            return
        if self._step < len(self._scene.steps) - 1:
            self._step    += 1
            self._phase    = "hold"
            self._phase_ms = 0.0
            self.update()
            self.step_changed.emit(self._step, len(self._scene.steps))

    def step_back(self) -> None:
        if not self._scene:
            return
        if self._step > 0:
            self._step    -= 1
            self._phase    = "hold"
            self._phase_ms = 0.0
            self.update()
            self.step_changed.emit(self._step, len(self._scene.steps))

    def is_playing(self) -> bool:
        return self._playing

    # ── Timer tick ─────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        if not self._scene:
            return
        dt = 1000.0 / _FPS
        self._phase_ms += dt

        if self._phase == "anim":
            if self._phase_ms >= _ANIM_MS:
                self._phase    = "hold"
                self._phase_ms = 0.0
                self.step_changed.emit(self._step, len(self._scene.steps))
        elif self._phase == "hold":
            if self._phase_ms >= _HOLD_MS:
                nxt = self._step + 1
                if nxt >= len(self._scene.steps):
                    self._phase   = "done"
                    self._playing = False
                    self._timer.stop()
                    self.finished.emit()
                else:
                    self._step     = nxt
                    self._phase    = "anim"
                    self._phase_ms = 0.0

        self.update()

    # ── Coordinate helpers ─────────────────────────────────────────────────────

    def _node_center(self, node_id: str) -> QPointF:
        if not self._scene:
            return QPointF(self.width() / 2, self.height() / 2)
        node = next((n for n in self._scene.nodes if n.id == node_id), None)
        if not node:
            return QPointF(self.width() / 2, self.height() / 2)
        mx = _NODE_W / 2 + 8
        my = _NODE_H / 2 + 8
        x  = mx + node.x * (self.width()  - 2 * mx)
        y  = my + node.y * (self.height() - 2 * my)
        return QPointF(x, y)

    # ── Drawing ────────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        p.fillRect(self.rect(), _BG)

        if not self._scene or not self._scene.nodes:
            p.setPen(QPen(QColor(CANVAS_DIM)))
            p.setFont(QFont("Segoe UI", 11))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No data — run a scan first")
            p.end()
            return

        self._draw_arrows(p)
        self._draw_packet(p)
        self._draw_nodes(p)
        self._draw_labels(p)   # always on top — drawn after nodes
        p.end()

    def _draw_arrows(self, p: QPainter) -> None:
        for i, step in enumerate(self._scene.steps):
            if i > self._step:
                break
            src = self._node_center(step.from_node)
            dst = self._node_center(step.to_node)
            is_current = (i == self._step)

            color = _REPLY_COLOR if step.is_reply else _REQUEST_COLOR
            alpha = 200 if is_current else 55
            c = QColor(color)
            c.setAlpha(alpha)
            width = 2.0 if is_current else 1.0

            pen = QPen(c, width)
            if step.is_broadcast:
                pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)

            # Shorten line so it doesn't overlap the node rectangles
            src_s, dst_s = self._clip_to_node(src, dst)
            p.drawLine(src_s, dst_s)

            if is_current:
                self._draw_arrowhead(p, src_s, dst_s, c)

    def _draw_packet(self, p: QPainter) -> None:
        if self._phase != "anim" or not self._scene.steps:
            return
        step = self._scene.steps[self._step]
        t = min(self._phase_ms / _ANIM_MS, 1.0)
        t = 1 - (1 - t) ** 3   # ease-out cubic

        src = self._node_center(step.from_node)
        dst = self._node_center(step.to_node)
        px  = src.x() + t * (dst.x() - src.x())
        py  = src.y() + t * (dst.y() - src.y())
        pt  = QPointF(px, py)

        dot_color = _REPLY_COLOR if step.is_reply else _REQUEST_COLOR

        # glow
        glow = QColor(dot_color)
        glow.setAlpha(50)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(pt, 12, 12)

        # dot
        p.setBrush(QBrush(dot_color))
        p.drawEllipse(pt, 6, 6)

    def _draw_nodes(self, p: QPainter) -> None:
        active_ids = set()
        if self._scene.steps and self._step < len(self._scene.steps):
            s = self._scene.steps[self._step]
            active_ids = {s.from_node, s.to_node}

        for node in self._scene.nodes:
            cx, cy = self._node_center(node.id).x(), self._node_center(node.id).y()
            rx = cx - _NODE_W / 2
            ry = cy - _NODE_H / 2
            rect = QRectF(rx, ry, _NODE_W, _NODE_H)

            border_hex = _ROLE_COLOR.get(node.role, CANVAS_DIM)
            border = QColor(border_hex)
            is_active = node.id in active_ids

            # Card background
            bg = QColor(border)
            bg.setAlpha(30 if not is_active else 55)
            path = QPainterPath()
            path.addRoundedRect(rect, 8, 8)
            p.fillPath(path, QBrush(bg))

            # Border
            pen = QPen(border, 2.0 if is_active else 1.0)
            pen.setStyle(Qt.PenStyle.DashLine if node.role == "broadcast" else Qt.PenStyle.SolidLine)
            p.setPen(pen)
            p.drawPath(path)

            # Label text
            p.setPen(QPen(QColor(CANVAS_FG)))
            p.setFont(_FONT_NODE)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, node.label)

    # ── Sub-drawing helpers ────────────────────────────────────────────────────

    def _draw_arrowhead(self, p: QPainter, src: QPointF, dst: QPointF, color: QColor) -> None:
        dx = dst.x() - src.x()
        dy = dst.y() - src.y()
        length = math.hypot(dx, dy)
        if length < 1:
            return
        ux, uy  = dx / length, dy / length
        tip      = dst
        base_len = 10
        base_w   = 5
        b1 = QPointF(tip.x() - ux * base_len - uy * base_w,
                     tip.y() - uy * base_len + ux * base_w)
        b2 = QPointF(tip.x() - ux * base_len + uy * base_w,
                     tip.y() - uy * base_len - ux * base_w)
        path = QPainterPath()
        path.moveTo(tip)
        path.lineTo(b1)
        path.lineTo(b2)
        path.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(color))
        p.drawPath(path)

    def _draw_labels(self, p: QPainter) -> None:
        """Draw the packet label for the current step — called last so it's always on top."""
        if not self._scene or not self._scene.steps:
            return
        if self._step >= len(self._scene.steps):
            return
        step = self._scene.steps[self._step]
        src  = self._node_center(step.from_node)
        dst  = self._node_center(step.to_node)
        self._draw_packet_label(p, src, dst, step)

    def _draw_packet_label(self, p: QPainter, src: QPointF, dst: QPointF,
                           step: AnimStep) -> None:
        mx = (src.x() + dst.x()) / 2
        my = (src.y() + dst.y()) / 2
        # Offset above the line
        dx = dst.x() - src.x()
        dy = dst.y() - src.y()
        length = math.hypot(dx, dy) or 1
        # Perpendicular unit vector (pointing upward if line goes right)
        px_n, py_n = -dy / length, dx / length
        if py_n > 0:   # flip so offset is always above
            px_n, py_n = -px_n, -py_n
        ox = mx + px_n * 52
        oy = my + py_n * 52

        # Measure actual text so the pill fits snugly rather than using a fixed width
        w1 = QFontMetrics(_FONT_PKT).horizontalAdvance(step.packet_label)
        w2 = QFontMetrics(_FONT_DETAIL).horizontalAdvance(step.frame_detail)
        pad = 14   # horizontal padding each side
        hw  = max(w1, w2) / 2 + pad   # half-width of pill

        lbl_rect = QRectF(ox - hw, oy - 12, hw * 2, 14)
        det_rect = QRectF(ox - hw, oy + 3,  hw * 2, 13)

        # Single pill covering both rows — arrow line cannot cut between them
        bg = QColor(CANVAS_BG)
        bg.setAlpha(210)
        pill = QRectF(ox - hw, oy - 15, hw * 2, 34)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(pill, 5, 5)

        p.setPen(QPen(QColor(CANVAS_FG)))
        p.setFont(_FONT_PKT)
        p.drawText(lbl_rect, Qt.AlignmentFlag.AlignCenter, step.packet_label)

        p.setPen(QPen(QColor(CANVAS_GRAY)))
        p.setFont(_FONT_DETAIL)
        p.drawText(det_rect, Qt.AlignmentFlag.AlignCenter, step.frame_detail)

    def _clip_to_node(self, src: QPointF, dst: QPointF) -> tuple[QPointF, QPointF]:
        """Shorten src and dst so lines start/end at node border, not centre."""
        dx = dst.x() - src.x()
        dy = dst.y() - src.y()
        length = math.hypot(dx, dy) or 1
        ux, uy  = dx / length, dy / length
        hw, hh  = _NODE_W / 2, _NODE_H / 2
        # Approximate clip distance using bounding box
        if abs(ux) > 0:
            tx = hw / abs(ux)
        else:
            tx = float("inf")
        if abs(uy) > 0:
            ty = hh / abs(uy)
        else:
            ty = float("inf")
        clip = min(tx, ty) + 2
        s = QPointF(src.x() + ux * clip, src.y() + uy * clip)
        d = QPointF(dst.x() - ux * clip, dst.y() - uy * clip)
        return s, d
