"""
ProtocolCanvas — animated protocol diagram widget.

Renders a ProtocolSceneData as a live animation using QPainter.
Nodes are drawn as labelled rounded rectangles with a small role glyph;
each AnimStep shows a coloured dot travelling along a curved path between
nodes, leaving a fading motion trail and an arrival pulse on delivery.
Broadcast steps additionally radiate concentric rings from the source node.

Auto-plays at one step per ~2.3 s (scaled by `set_speed()`). Supports
play/pause/reset and manual step-forward / step-back.

Live Mode (Phase A5): enter_live()/pulse()/exit_live() switch the canvas
from the fixed step state machine to transient one-shot packet animations
driven by real captured events — see the "Live mode" section below.

Signals:
    step_changed(int, int)   — current step index, total steps
    finished()               — all steps played
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
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
    CANVAS_FG, CANVAS_GRAY, CANVAS_GREEN, CANVAS_GRID, CANVAS_NODE_FILL,
    CANVAS_PULSE, CANVAS_TRAIL,
)
from ui.widgets.protocol_canvas_glyphs import ROLE_GLYPHS

# ── Timing ─────────────────────────────────────────────────────────────────────
_FPS      = 30
_ANIM_MS  = 900    # ms for the dot to travel from src to dst
_HOLD_MS  = 1400   # ms to pause after arrival before advancing
_ARRIVAL_MS = 300  # ms window (into the hold phase) the arrival pulse plays for

# ── Visual constants ──────────────────────────────────────────────────────────
_BG          = QColor(CANVAS_BG)
_NODE_W      = 110
_NODE_H      = 58
_GLYPH_SIZE  = 16
_GRID_SPACING = 28
_PROGRESS_H  = 4
_BROADCAST_RING_COUNT = 3
_BROADCAST_RING_STAGGER_MS = 220
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

# ── Live Mode (Phase A5) ────────────────────────────────────────────────────
# A live pulse reuses the same travel + arrival-pulse timing as a step, but is
# a transient one-shot: it is discarded once its arrival decay finishes,
# rather than holding for _HOLD_MS while waiting for the next step in a fixed
# sequence. Several can be in flight at once (real traffic doesn't take turns).
_LIVE_PULSE_LIFE_MS = _ANIM_MS + _ARRIVAL_MS


@dataclass
class _LivePulse:
    src_id:       str
    dst_id:       str
    label:        str
    is_reply:     bool
    is_broadcast: bool
    elapsed_ms:   float = 0.0
    trail:        deque = field(default_factory=lambda: deque(maxlen=6))


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
        self._speed:   float = 1.0
        self._trail: deque = deque(maxlen=6)   # eased t-values of the current packet's path

        # Live Mode (Phase A5) — parallel state, only used while _live_mode is True.
        self._live_mode:   bool = False
        self._live_nodes:  list = []          # list[AnimNode] — managed by the page
        self._live_pulses: list = []          # list[_LivePulse] — transient, may overlap

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
        self._trail.clear()
        self.update()
        if data.steps:
            self.step_changed.emit(0, len(data.steps))

    def set_speed(self, multiplier: float) -> None:
        """Scale animation pacing. 2.0 = twice as fast, 0.5 = half speed."""
        self._speed = multiplier if multiplier and multiplier > 0 else 1.0

    def play(self) -> None:
        if not self._scene or not self._scene.steps:
            return
        if self._phase == "done":
            self._step     = 0
            self._phase    = "anim"
            self._phase_ms = 0.0
            self._trail.clear()
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
        self._trail.clear()
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
            self._trail.clear()
            self.update()
            self.step_changed.emit(self._step, len(self._scene.steps))

    def step_back(self) -> None:
        if not self._scene:
            return
        if self._step > 0:
            self._step    -= 1
            self._phase    = "hold"
            self._phase_ms = 0.0
            self._trail.clear()
            self.update()
            self.step_changed.emit(self._step, len(self._scene.steps))

    def is_playing(self) -> bool:
        return self._playing

    def current_step(self) -> int:
        return self._step

    def go_to_step(self, idx: int) -> None:
        """Jump directly to an absolute step index (manual control — pauses playback)."""
        if not self._scene or not self._scene.steps:
            return
        idx = max(0, min(idx, len(self._scene.steps) - 1))
        self._timer.stop()
        self._playing  = False
        self._step     = idx
        self._phase    = "hold"
        self._phase_ms = 0.0
        self._trail.clear()
        self.update()
        self.step_changed.emit(idx, len(self._scene.steps))

    # ── Live Mode API (Phase A5) ─────────────────────────────────────────────

    def enter_live(self, nodes: list[AnimNode]) -> None:
        """Switch from the step state machine to transient live-pulse rendering.

        `nodes` is the initial node set — typically your device + gateway.
        The page grows/evicts this set as talkers appear via
        `set_live_nodes()`; the canvas itself only draws whatever it is
        given."""
        self._timer.stop()
        self._playing = False
        self._live_mode = True
        self._live_nodes = list(nodes)
        self._live_pulses = []
        self._timer.start()
        self.update()

    def set_live_nodes(self, nodes: list[AnimNode]) -> None:
        """Replace the live node set in place (no-op outside live mode)."""
        if not self._live_mode:
            return
        self._live_nodes = list(nodes)
        self.update()

    def pulse(self, src_id: str, dst_id: str, label: str,
              is_reply: bool, is_broadcast: bool) -> None:
        """Animate one real captured packet as a transient src->dst pulse.

        No-op outside live mode (defensive — a stray event after exit_live()
        must not resurrect step-mode drawing state)."""
        if not self._live_mode:
            return
        self._live_pulses.append(_LivePulse(
            src_id=src_id, dst_id=dst_id, label=label,
            is_reply=is_reply, is_broadcast=is_broadcast,
        ))

    def exit_live(self) -> None:
        """Leave live mode. The caller (page) is responsible for restoring
        step-mode content afterward (e.g. re-selecting the current protocol)."""
        self._timer.stop()
        self._live_mode = False
        self._live_nodes = []
        self._live_pulses = []
        self.update()

    def is_live(self) -> bool:
        return self._live_mode

    # ── Visibility lifecycle ───────────────────────────────────────────────────

    def hideEvent(self, event) -> None:
        """RULE-WIN17: this canvas is a reusable widget embedded in two places
        (Protocol Visualizer directly, Lab Mode via LabCanvasCard) and has no
        page of its own to rely on for a hideEvent -- a QStackedWidget page
        switch propagates a real hideEvent down to a nested child like this
        one, but nothing stops the timer that started it. Left unguarded,
        _timer ticks at 30fps forever once play()/enter_live() starts it,
        repainting a widget nobody can see for the rest of the app session."""
        self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event) -> None:
        """Resume ticking only if step-mode or live-mode is still the active
        intent (self._playing / self._live_mode) -- these flags, not a
        separate "was it ticking" snapshot, are what pause()/exit_live()
        already use to mean "stopped on purpose", so a show() right after a
        deliberate pause can't accidentally resurrect playback."""
        super().showEvent(event)
        if (self._playing or self._live_mode) and not self._timer.isActive():
            self._timer.start()

    # ── Timer tick ─────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        if self._live_mode:
            self._tick_live()
            return
        if not self._scene:
            return
        dt = (1000.0 / _FPS) * self._speed
        self._phase_ms += dt

        if self._phase == "anim":
            if self._phase_ms >= _ANIM_MS:
                self._phase    = "hold"
                self._phase_ms = 0.0
                self._trail.clear()
                self.step_changed.emit(self._step, len(self._scene.steps))
            else:
                t = min(self._phase_ms / _ANIM_MS, 1.0)
                self._trail.append(1 - (1 - t) ** 3)
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
                    self._trail.clear()

        self.update()

    def _tick_live(self) -> None:
        """Age every in-flight live pulse; drop ones whose decay has finished.

        Always real-time (ignores set_speed() — these are real packets, not a
        scripted sequence) — matches the 30 fps tick rate used everywhere else."""
        dt = 1000.0 / _FPS
        alive: list = []
        for pulse in self._live_pulses:
            pulse.elapsed_ms += dt
            if pulse.elapsed_ms < _ANIM_MS:
                t = min(pulse.elapsed_ms / _ANIM_MS, 1.0)
                pulse.trail.append(1 - (1 - t) ** 3)
            if pulse.elapsed_ms < _LIVE_PULSE_LIFE_MS:
                alive.append(pulse)
        self._live_pulses = alive
        self.update()

    # ── Coordinate helpers ─────────────────────────────────────────────────────

    def _node_center(self, node_id: str) -> QPointF:
        nodes = self._live_nodes if self._live_mode else (self._scene.nodes if self._scene else [])
        if not nodes:
            return QPointF(self.width() / 2, self.height() / 2)
        node = next((n for n in nodes if n.id == node_id), None)
        if not node:
            return QPointF(self.width() / 2, self.height() / 2)
        mx = _NODE_W / 2 + 8
        my = _NODE_H / 2 + 8
        x  = mx + node.x * (self.width()  - 2 * mx)
        y  = my + node.y * (self.height() - 2 * my)
        return QPointF(x, y)

    @staticmethod
    def _bezier_control(src: QPointF, dst: QPointF, is_reply: bool) -> QPointF:
        """Control point for the src->dst quadratic curve, offset perpendicular
        to the line so request/reply arcs on the same node pair don't overlap."""
        dx = dst.x() - src.x()
        dy = dst.y() - src.y()
        length = math.hypot(dx, dy) or 1
        nx, ny = -dy / length, dx / length
        sign = -1.0 if is_reply else 1.0
        offset = length * 0.12 * sign
        mx = (src.x() + dst.x()) / 2 + nx * offset
        my = (src.y() + dst.y()) / 2 + ny * offset
        return QPointF(mx, my)

    @staticmethod
    def _bezier_point(p0: QPointF, ctrl: QPointF, p1: QPointF, t: float) -> QPointF:
        mt = 1 - t
        x = mt * mt * p0.x() + 2 * mt * t * ctrl.x() + t * t * p1.x()
        y = mt * mt * p0.y() + 2 * mt * t * ctrl.y() + t * t * p1.y()
        return QPointF(x, y)

    # ── Drawing ────────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        p.fillRect(self.rect(), _BG)
        self._draw_backdrop(p)

        if self._live_mode:
            self._paint_live(p)
            p.end()
            return

        if not self._scene or not self._scene.nodes:
            p.setPen(QPen(QColor(CANVAS_DIM)))
            p.setFont(QFont("Segoe UI", 11))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No data — run a scan first")
            p.end()
            return

        self._draw_broadcast_rings(p)
        self._draw_arrows(p)
        self._draw_trail(p)
        self._draw_packet(p)
        self._draw_nodes(p)
        self._draw_arrival_pulse(p)
        self._draw_labels(p)   # always on top of nodes/pulse
        self._draw_progress_strip(p)
        p.end()

    def _paint_live(self, p: QPainter) -> None:
        """Live Mode paint path — transient pulses instead of the step sequence."""
        if not self._live_nodes:
            p.setPen(QPen(QColor(CANVAS_DIM)))
            p.setFont(QFont("Segoe UI", 11))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Live — waiting for the first packet…")
            return

        active_ids = {pid for pulse in self._live_pulses for pid in (pulse.src_id, pulse.dst_id)}
        for pulse in self._live_pulses:
            if not pulse.is_broadcast or pulse.elapsed_ms >= _ANIM_MS:
                continue
            src = self._node_center(pulse.src_id)
            self._draw_broadcast_rings_for(p, src, "anim", pulse.elapsed_ms)
        for pulse in self._live_pulses:
            src = self._node_center(pulse.src_id)
            dst = self._node_center(pulse.dst_id)
            src_s, dst_s = self._clip_to_node(src, dst)
            phase = "anim" if pulse.elapsed_ms < _ANIM_MS else "hold"
            self._draw_trail_for(p, src_s, dst_s, pulse.is_reply, phase, pulse.trail)
            self._draw_packet_for(p, src_s, dst_s, pulse.is_reply, phase, pulse.elapsed_ms)
        self._draw_nodes_for(p, self._live_nodes, active_ids)
        for pulse in self._live_pulses:
            dst = self._node_center(pulse.dst_id)
            phase = "anim" if pulse.elapsed_ms < _ANIM_MS else "hold"
            hold_ms = pulse.elapsed_ms - _ANIM_MS if phase == "hold" else 0.0
            self._draw_arrival_pulse_for(p, dst, phase, hold_ms)

    def _draw_backdrop(self, p: QPainter) -> None:
        pen = QPen(QColor(CANVAS_GRID))
        pen.setWidth(1)
        p.setPen(pen)
        w, h = self.width(), self.height()
        y = _GRID_SPACING
        while y < h:
            x = _GRID_SPACING
            while x < w:
                p.drawPoint(QPointF(float(x), float(y)))
                x += _GRID_SPACING
            y += _GRID_SPACING

    def _draw_broadcast_rings(self, p: QPainter) -> None:
        if self._phase != "anim" or not self._scene.steps:
            return
        step = self._scene.steps[self._step]
        if not step.is_broadcast:
            return
        src = self._node_center(step.from_node)
        self._draw_broadcast_rings_for(p, src, self._phase, self._phase_ms)

    def _draw_broadcast_rings_for(self, p: QPainter, src: QPointF,
                                  phase: str, phase_ms: float) -> None:
        """Parameterized so Live Mode pulses (Phase A5) can reuse the same rings
        without a scene/step lookup — see _paint_live()."""
        if phase != "anim":
            return
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(_BROADCAST_RING_COUNT):
            local_ms = phase_ms - i * _BROADCAST_RING_STAGGER_MS
            if local_ms <= 0:
                continue
            t = min(local_ms / _ANIM_MS, 1.0)
            alpha = int(150 * (1 - t))
            if alpha <= 0:
                continue
            radius = 14 + t * 70
            c = QColor(CANVAS_DIM)
            c.setAlpha(alpha)
            pen = QPen(c, 1.5)
            pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawEllipse(src, radius, radius)

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
            p.setBrush(Qt.BrushStyle.NoBrush)

            # Shorten line so it doesn't overlap the node rectangles
            src_s, dst_s = self._clip_to_node(src, dst)
            ctrl = self._bezier_control(src_s, dst_s, step.is_reply)
            path = QPainterPath()
            path.moveTo(src_s)
            path.quadTo(ctrl, dst_s)
            p.drawPath(path)

            if is_current:
                # tangent at t=1 points from ctrl -> dst_s
                self._draw_arrowhead(p, ctrl, dst_s, c)

    def _draw_trail(self, p: QPainter) -> None:
        if self._phase != "anim" or not self._scene.steps or not self._trail:
            return
        step = self._scene.steps[self._step]
        src = self._node_center(step.from_node)
        dst = self._node_center(step.to_node)
        src_s, dst_s = self._clip_to_node(src, dst)
        self._draw_trail_for(p, src_s, dst_s, step.is_reply, self._phase, self._trail)

    def _draw_trail_for(self, p: QPainter, src_s: QPointF, dst_s: QPointF,
                        is_reply: bool, phase: str, trail) -> None:
        """Parameterized so Live Mode pulses (Phase A5) can reuse the same trail
        painter with their own per-pulse deque — see _paint_live()."""
        if phase != "anim" or not trail:
            return
        ctrl = self._bezier_control(src_s, dst_s, is_reply)
        n = len(trail)
        p.setPen(Qt.PenStyle.NoPen)
        for i, te in enumerate(trail):
            pt = self._bezier_point(src_s, ctrl, dst_s, te)
            age_frac = (i + 1) / n   # oldest -> smallest/faintest, newest -> largest
            c = QColor(CANVAS_TRAIL)
            c.setAlpha(int(130 * age_frac))
            radius = 1.5 + 3.0 * age_frac
            p.setBrush(QBrush(c))
            p.drawEllipse(pt, radius, radius)

    def _draw_packet(self, p: QPainter) -> None:
        if self._phase != "anim" or not self._scene.steps:
            return
        step = self._scene.steps[self._step]
        src = self._node_center(step.from_node)
        dst = self._node_center(step.to_node)
        src_s, dst_s = self._clip_to_node(src, dst)
        self._draw_packet_for(p, src_s, dst_s, step.is_reply, self._phase, self._phase_ms)

    def _draw_packet_for(self, p: QPainter, src_s: QPointF, dst_s: QPointF,
                         is_reply: bool, phase: str, phase_ms: float) -> None:
        """Parameterized so Live Mode pulses (Phase A5) can reuse the same
        travelling-dot painter — see _paint_live()."""
        if phase != "anim":
            return
        t = min(phase_ms / _ANIM_MS, 1.0)
        t = 1 - (1 - t) ** 3   # ease-out cubic

        ctrl = self._bezier_control(src_s, dst_s, is_reply)
        pt = self._bezier_point(src_s, ctrl, dst_s, t)

        dot_color = _REPLY_COLOR if is_reply else _REQUEST_COLOR

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
        self._draw_nodes_for(p, self._scene.nodes, active_ids)

    def _draw_nodes_for(self, p: QPainter, nodes, active_ids: set) -> None:
        """Parameterized so Live Mode (Phase A5) can draw its own dynamic node
        set — see _paint_live()."""
        for node in nodes:
            cx, cy = self._node_center(node.id).x(), self._node_center(node.id).y()
            rx = cx - _NODE_W / 2
            ry = cy - _NODE_H / 2
            rect = QRectF(rx, ry, _NODE_W, _NODE_H)

            border_hex = _ROLE_COLOR.get(node.role, CANVAS_DIM)
            border = QColor(border_hex)
            is_active = node.id in active_ids

            path = QPainterPath()
            path.addRoundedRect(rect, 8, 8)

            # Solid base fill so the card reads as a frosted panel, not a flat tint
            p.fillPath(path, QBrush(QColor(CANVAS_NODE_FILL)))

            # Role-tinted overlay
            bg = QColor(border)
            bg.setAlpha(30 if not is_active else 55)
            p.fillPath(path, QBrush(bg))

            # Border
            pen = QPen(border, 2.0 if is_active else 1.0)
            pen.setStyle(Qt.PenStyle.DashLine if node.role == "broadcast" else Qt.PenStyle.SolidLine)
            p.setPen(pen)
            p.drawPath(path)

            # Role glyph
            glyph_builder = ROLE_GLYPHS.get(node.role)
            if glyph_builder:
                glyph_rect = QRectF(cx - _GLYPH_SIZE / 2, ry + 4, _GLYPH_SIZE, _GLYPH_SIZE)
                glyph_path = glyph_builder(glyph_rect)
                p.setPen(QPen(QColor(CANVAS_FG), 1.4))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(glyph_path)

            # Label text — below the glyph
            label_rect = QRectF(rect.left(), ry + _NODE_H * 0.42, _NODE_W, _NODE_H * 0.55)
            p.setPen(QPen(QColor(CANVAS_FG)))
            p.setFont(_FONT_NODE)
            p.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, node.label)

    def _draw_arrival_pulse(self, p: QPainter) -> None:
        """Expanding ring + brightened border for the first _ARRIVAL_MS of the hold phase."""
        if self._phase != "hold" or self._phase_ms >= _ARRIVAL_MS:
            return
        if not self._scene.steps:
            return
        step = self._scene.steps[self._step]
        dst = self._node_center(step.to_node)
        self._draw_arrival_pulse_for(p, dst, self._phase, self._phase_ms)

    def _draw_arrival_pulse_for(self, p: QPainter, dst: QPointF,
                                phase: str, phase_ms: float) -> None:
        """Parameterized so Live Mode pulses (Phase A5) can reuse the same
        arrival ring — see _paint_live()."""
        if phase != "hold" or phase_ms >= _ARRIVAL_MS:
            return
        t = min(phase_ms / _ARRIVAL_MS, 1.0)
        te = 1 - (1 - t) ** 2   # ease-out quad
        radius = 10 + te * 22
        alpha  = int(180 * (1 - te))
        if alpha <= 0:
            return
        c = QColor(CANVAS_PULSE)
        c.setAlpha(alpha)
        pen = QPen(c, 2.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(dst, radius, radius)

    def _draw_progress_strip(self, p: QPainter) -> None:
        if not self._scene or not self._scene.steps:
            return
        n = len(self._scene.steps)
        w, h = self.width(), self.height()
        seg_w = w / n
        top = h - _PROGRESS_H
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(n):
            rect = QRectF(i * seg_w + 1, top, max(seg_w - 2, 1), _PROGRESS_H - 1)
            if i == self._step:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(CANVAS_ACCENT)))
                p.drawRect(rect)
                p.setBrush(Qt.BrushStyle.NoBrush)
            elif i < self._step:
                played = QColor(CANVAS_GRAY)
                played.setAlpha(140)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(played))
                p.drawRect(rect)
                p.setBrush(Qt.BrushStyle.NoBrush)
            else:
                p.setPen(QPen(QColor(CANVAS_DIM), 1.0))
                p.drawRect(rect)

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
