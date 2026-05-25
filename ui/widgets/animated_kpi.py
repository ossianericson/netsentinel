"""ui/widgets/animated_kpi.py — count-up animated KPI label (ANIM-6)."""
from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QVariantAnimation
from PyQt6.QtWidgets import QLabel

from ui.theme import _reduce_motion


class AnimatedKpi(QLabel):
    """QLabel that count-up animates when its integer value changes (400 ms InOutQuad)."""

    def __init__(self, text: str = "—", fmt: str = "{}", parent=None) -> None:
        super().__init__(text, parent)
        self._fmt = fmt
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(400)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.valueChanged.connect(lambda v: self.setText(self._fmt.format(int(v))))

    def set_value(self, value: int) -> None:
        if _reduce_motion():
            self.setText(self._fmt.format(value))
            return
        try:
            current = int(self.text().replace(",", "").replace("—", "0"))
        except ValueError:
            current = 0
        self._anim.stop()
        self._anim.setStartValue(float(current))
        self._anim.setEndValue(float(value))
        self._anim.start()
