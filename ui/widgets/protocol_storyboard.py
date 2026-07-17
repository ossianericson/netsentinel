"""
protocol_storyboard — renders a ProtocolSceneData's full step sequence into a single
vertical filmstrip PNG (Phase A3 — Shareability).

build_storyboard_pixmap() captures the live canvas at each step offscreen via
QWidget.render(), then composes a title header, one framed panel per step (the
captured frame plus its packet label and word-wrapped explanation), and a footer
into one QPixmap with a single QPainter pass. The canvas's step_changed signal is
blocked during the capture loop so the intermediate go_to_step() calls don't reach
connected UI (e.g. the page's step list), and the canvas is restored to its original
step — and resumed if it was playing — before returning.

All chrome reuses the canvas's own CANVAS_* dark "cinema" tokens (ui/styles.py) so the
export reads as one continuous strip rather than seaming into the app's light theme.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap

from ui.styles import CANVAS_BG, CANVAS_DIM, CANVAS_FG, CANVAS_GRAY, CANVAS_GRID

if TYPE_CHECKING:
    from modules.protocol_animator import AnimStep, ProtocolSceneData
    from ui.widgets.protocol_canvas import ProtocolCanvas

_MARGIN      = 24
_HEADER_H    = 60
_FOOTER_H    = 34
_PANEL_GAP   = 18
_TEXT_GAP    = 10
_LABEL_GAP   = 4

_FONT_TITLE  = QFont("Segoe UI", 16, QFont.Weight.Bold)
_FONT_SUB    = QFont("Segoe UI", 10)
_FONT_STEP   = QFont("Segoe UI", 12, QFont.Weight.Bold)
_FONT_EXPL   = QFont("Segoe UI", 10)
_FONT_FOOTER = QFont("Segoe UI", 8)

_WRAP = Qt.TextFlag.TextWordWrap | int(Qt.AlignmentFlag.AlignLeft)


def build_storyboard_pixmap(canvas: "ProtocolCanvas", scene: "ProtocolSceneData") -> QPixmap:
    """Render every step of *scene* offscreen and compose a vertical filmstrip PNG.

    Leaves *canvas* on its original step (and playing state) when done.
    """
    orig_step    = canvas.current_step()
    orig_playing = canvas.is_playing()
    frame_w      = max(canvas.width(), 1)
    frame_h      = max(canvas.height(), 1)

    canvas.blockSignals(True)
    try:
        frames: List[QPixmap] = []
        for i in range(len(scene.steps)):
            canvas.go_to_step(i)
            canvas.repaint()
            pixmap = QPixmap(canvas.size())
            canvas.render(pixmap)
            frames.append(pixmap)
    finally:
        canvas.blockSignals(False)
        canvas.go_to_step(orig_step)
        if orig_playing:
            canvas.play()

    return _compose(scene, frames, frame_w, frame_h)


def _wrapped_text_height(text: str, font: QFont, width: int) -> int:
    fm = QFontMetrics(font)
    return fm.boundingRect(0, 0, max(width, 1), 0, Qt.TextFlag.TextWordWrap, text).height()


def _compose(scene: "ProtocolSceneData", frames: List[QPixmap], frame_w: int, frame_h: int) -> QPixmap:
    text_w = max(frame_w, 1)
    step_label_h = QFontMetrics(_FONT_STEP).height()

    panel_heights = []
    for step in scene.steps:
        expl_h = _wrapped_text_height(step.explanation, _FONT_EXPL, text_w)
        panel_heights.append(frame_h + _TEXT_GAP + step_label_h + _LABEL_GAP + expl_h)

    total_w = frame_w + _MARGIN * 2
    total_h = (
        _MARGIN + _HEADER_H
        + sum(panel_heights) + _PANEL_GAP * max(len(frames) - 1, 0)
        + _FOOTER_H + _MARGIN
    )

    pixmap = QPixmap(total_w, max(total_h, 1))
    pixmap.fill(QColor(CANVAS_BG))

    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    y = _draw_header(p, scene, frame_w)

    for step, frame, panel_h in zip(scene.steps, frames, panel_heights):
        y = _draw_panel(p, step, frame, panel_h, frame_w, frame_h, y)
        y += _PANEL_GAP

    _draw_footer(p, frame_w, total_h)
    p.end()

    return pixmap


def _draw_header(p: QPainter, scene: "ProtocolSceneData", frame_w: int) -> int:
    y = _MARGIN
    p.setPen(QColor(CANVAS_FG))
    p.setFont(_FONT_TITLE)
    p.drawText(QRectF(_MARGIN, y, frame_w, 26), Qt.AlignmentFlag.AlignLeft,
               f"{scene.title} — NetSentinel")
    y += 28

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    p.setPen(QColor(CANVAS_GRAY))
    p.setFont(_FONT_SUB)
    p.drawText(QRectF(_MARGIN, y, frame_w, 18), Qt.AlignmentFlag.AlignLeft,
               f"{scene.subtitle}  ·  generated {stamp}")
    y += 22

    p.setPen(QColor(CANVAS_GRID))
    p.drawLine(_MARGIN, y, _MARGIN + frame_w, y)
    return _MARGIN + _HEADER_H


def _draw_panel(p: QPainter, step: "AnimStep", frame: QPixmap, panel_h: int,
                 frame_w: int, frame_h: int, y: int) -> int:
    p.drawPixmap(_MARGIN, y, frame)
    ty = y + frame_h + _TEXT_GAP

    step_label_h = QFontMetrics(_FONT_STEP).height()
    p.setPen(QColor(CANVAS_FG))
    p.setFont(_FONT_STEP)
    p.drawText(QRectF(_MARGIN, ty, frame_w, step_label_h), Qt.AlignmentFlag.AlignLeft,
               step.packet_label)
    ty += step_label_h + _LABEL_GAP

    p.setPen(QColor(CANVAS_GRAY))
    p.setFont(_FONT_EXPL)
    expl_h = panel_h - (frame_h + _TEXT_GAP + step_label_h + _LABEL_GAP)
    p.drawText(QRectF(_MARGIN, ty, frame_w, expl_h), _WRAP, step.explanation)

    return y + panel_h


def _draw_footer(p: QPainter, frame_w: int, total_h: int) -> None:
    p.setPen(QColor(CANVAS_DIM))
    p.setFont(_FONT_FOOTER)
    p.drawText(QRectF(_MARGIN, total_h - _FOOTER_H, frame_w, 20), Qt.AlignmentFlag.AlignLeft,
               "Generated by NetSentinel — Protocol Visualizer")
