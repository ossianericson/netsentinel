"""
LabPickerPanel — Lab Mode's scenario picker grid with completion tracking
(Lab Mode Upgrade Phase L2).

Extracted from lab_mode_page.py to keep that file under the 1000-line UI
budget (RULE-AH1) once the picker gained per-card completion badges and an
overall progress strip. Pure UI — progress state (modules/lab_progress.py
shape) is owned by the page and pushed in via refresh_progress(); this
widget never touches QSettings directly.

Usage::

    panel = LabPickerPanel(SCENARIOS)
    panel.start_requested.connect(on_start)              # LabScenario
    panel.explore_protocol_requested.connect(on_explore)  # protocol key str
    panel.refresh_progress(progress_state)                # after load / mark_complete
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from modules.lab_progress import best_verdict, is_complete, summary
from modules.lab_scenarios import LabScenario
from ui import styles as _s

_EFFORT_COLOR_NAME = {"S": "GREEN", "M": "AMBER", "L": "RED"}


def _effort_color(effort: str) -> str:
    return getattr(_s, _EFFORT_COLOR_NAME.get(effort, "AMBER"))


class LabPickerPanel(QWidget):
    """Scenario picker grid: cards + an overall 'N of total complete' strip."""

    start_requested             = pyqtSignal(object)  # LabScenario
    explore_protocol_requested  = pyqtSignal(str)

    def __init__(self, scenarios: List[LabScenario], parent=None):
        super().__init__(parent)
        self._scenarios = scenarios
        self._cards:  Dict[str, QFrame] = {}
        self._badges: Dict[str, QLabel] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 24)
        outer.setSpacing(6)

        from ui.widgets.page_header import PageHeaderBar
        hdr = PageHeaderBar(
            "Lab Mode",
            subtitle="Guided exercises to learn real networking concepts using your live network.",
        )
        hdr.show_first_visit_banner(
            "lab_mode",
            "Each exercise walks you through a real networking concept using your actual "
            "devices, not a simulation. Hints are available if you get stuck, and you can "
            "reveal the full solution at any point.",
        )
        outer.addWidget(hdr)
        outer.addSpacing(6)

        self._progress_strip = QLabel()
        _s.themed_ss(self._progress_strip, "font-size:11px; color:{TEXT_SECONDARY}; background:transparent;")
        outer.addWidget(self._progress_strip)
        outer.addSpacing(6)

        grid = QGridLayout()
        grid.setSpacing(12)
        for idx, scenario in enumerate(scenarios):
            card, badge = self._build_card(scenario)
            self._cards[scenario.id]  = card
            self._badges[scenario.id] = badge
            grid.addWidget(card, idx // 2, idx % 2)
        outer.addLayout(grid)
        outer.addStretch()

        self.refresh_progress({})

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh_progress(self, progress: dict) -> None:
        """Update the completion strip and every card's badge from persisted state."""
        done, total = summary(progress, len(self._scenarios))
        self._progress_strip.setText(f"{done} of {total} complete")
        for scenario in self._scenarios:
            completed = is_complete(progress, scenario.id)
            badge = self._badges[scenario.id]
            if completed:
                date = progress[scenario.id].get("completed_at", "")[:10]
                verdict = best_verdict(progress, scenario.id) or ""
                badge.setText(f"✓  Completed · {date}" if date else "✓  Completed")
                badge.setToolTip(f"Best result: {verdict}" if verdict else "")
            badge.setVisible(completed)
            _s.themed_ss(self._cards[scenario.id], lambda done=completed: (
                f"QFrame#labCard {{ background:{_s.BG_ALT_ROW if done else _s.BG_CARD};"
                f" border:1px solid {_s.BORDER}; border-radius:8px; }}"
            ))

    # ── Card construction ────────────────────────────────────────────────────

    def _build_card(self, scenario: LabScenario) -> Tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("labCard")
        _s.themed_ss(card, "QFrame#labCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:8px; }}")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)

        header = QHBoxLayout()
        t = QLabel(scenario.title)
        _s.themed_ss(t, "font-size:13px; font-weight:bold; color:{TEXT_PRIMARY}; background:transparent;")
        e = QLabel(f"Effort: {scenario.effort}")
        _s.themed_ss(e, lambda eff=scenario.effort: (
            f"font-size:10px; color:{_effort_color(eff)}; background:transparent;"
        ))
        header.addWidget(t)
        header.addStretch()
        header.addWidget(e)
        lay.addLayout(header)

        badge = QLabel("")
        _s.themed_ss(badge, "font-size:10px; font-weight:bold; color:{GREEN}; background:transparent;")
        badge.setVisible(False)
        lay.addWidget(badge)

        g = QLabel(scenario.goal)
        g.setWordWrap(True)
        _s.themed_ss(g, "font-size:11px; color:{TEXT_SECONDARY}; background:transparent;")
        lay.addWidget(g)

        steps_lbl = QLabel(f"{len(scenario.steps)} steps")
        _s.themed_ss(steps_lbl, "font-size:10px; color:{TEXT_SECONDARY}; background:transparent;")
        lay.addWidget(steps_lbl)

        # Curriculum alignment badges
        try:
            from ui.widgets.objective_badge import ObjectiveBadge
            badge_row = QHBoxLayout()
            badge_row.setSpacing(4)
            for ob in ObjectiveBadge.for_scenario(scenario.title):
                badge_row.addWidget(ob)
            badge_row.addStretch()
            lay.addLayout(badge_row)
        except Exception:
            pass  # non-fatal — badge widget optional

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        start_btn = QPushButton("Start Exercise")
        start_btn.setFixedHeight(28)
        _s.themed_ss(start_btn, "QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            " border-radius:4px; font-size:11px; }}"
            "QPushButton:hover {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
            "QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}")
        start_btn.clicked.connect(lambda _, s=scenario: self.start_requested.emit(s))
        btn_row.addWidget(start_btn)

        if scenario.protocol:
            viz_btn = QPushButton(f"See how {scenario.protocol} works →")
            viz_btn.setFixedHeight(28)
            _s.themed_ss(viz_btn, "QPushButton {{ background:transparent; color:{ACCENT};"
                " border:1px solid {ACCENT}; border-radius:4px; font-size:11px; }}"
                "QPushButton:hover {{ background:{BG_HOVER}; color:{ACCENT}; }}"
                "QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}")
            _proto = scenario.protocol
            viz_btn.clicked.connect(lambda _, p=_proto: self.explore_protocol_requested.emit(p))
            btn_row.addWidget(viz_btn)

        btn_row.addStretch()
        lay.addLayout(btn_row)
        return card, badge
