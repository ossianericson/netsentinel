"""
LabScoreboardPanel — Lab Mode's badge collection + curriculum coverage view
(Lab Mode Badge Scoreboard).

Structurally a sibling of ui/widgets/lab_picker.py::LabPickerPanel — same
push-model contract: progress state (modules/lab_progress.py shape) is owned
by the page and pushed in via refresh(); this widget never touches QSettings
directly.

Usage::

    panel = LabScoreboardPanel(SCENARIOS)
    panel.back_requested.connect(on_back)
    panel.start_requested.connect(on_start)     # LabScenario, clicked from a locked card
    panel.refresh(progress_state)                # after load / mark_complete
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from modules.lab_achievements import badge_states, curriculum_coverage, earned_count
from modules.lab_scenarios import LabScenario
from ui import styles as _s
from ui.nav.rail import _SmoothProgressBar
from ui.widgets.badge_medallion import BadgeMedallion
from ui.widgets.page_header import PageHeaderBar


class LabScoreboardPanel(QWidget):
    """Badge grid (earned in colour, locked greyed out) + per-cert coverage bars."""

    back_requested  = pyqtSignal()
    start_requested = pyqtSignal(object)   # LabScenario — clicking a locked card starts it

    def __init__(self, scenarios: List[LabScenario], parent=None) -> None:
        super().__init__(parent)
        self._scenarios = scenarios
        self._cards:        Dict[str, QFrame]         = {}
        self._medallions:   Dict[str, BadgeMedallion]  = {}
        self._status_lbls:  Dict[str, QLabel]          = {}
        self._badge_rows:   Dict[str, QHBoxLayout]     = {}
        self._start_btns:   Dict[str, QPushButton]     = {}
        self._coverage_bars: Dict[str, QProgressBar]   = {}
        self._coverage_lbls: Dict[str, QLabel]         = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 24)
        outer.setSpacing(6)

        hdr = PageHeaderBar(
            "Achievements",
            subtitle="Badges you have earned by completing Lab Mode exercises.",
        )
        outer.addWidget(hdr)
        outer.addSpacing(6)

        back_btn = QPushButton("← Back to Exercises")
        back_btn.setFlat(True)
        _s.themed_ss(back_btn, "QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            " border:none; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
        back_btn.clicked.connect(self.back_requested.emit)
        outer.addWidget(back_btn)
        outer.addSpacing(6)

        # Overall progress row
        prog_row = QHBoxLayout()
        self._progress_bar = _SmoothProgressBar()
        self._progress_bar.setRange(0, len(scenarios))
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setTextVisible(False)
        _s.themed_ss(self._progress_bar, "QProgressBar {{ background:{BG_CARD}; border:none;"
            " border-radius:3px; }}"
            "QProgressBar::chunk {{ background:{ACCENT}; border-radius:3px; }}")
        self._progress_lbl = QLabel()
        _s.themed_ss(self._progress_lbl, "font-size:11px; color:{TEXT_SECONDARY}; background:transparent;")
        prog_row.addWidget(self._progress_bar, 1)
        prog_row.addSpacing(8)
        prog_row.addWidget(self._progress_lbl)
        outer.addLayout(prog_row)
        outer.addSpacing(10)

        # Curriculum coverage block — one row per cert with a non-zero denominator.
        # The set of certs is fixed by the curriculum data, not by progress, so
        # rows are built once here and only their bar/label are updated in refresh().
        coverage_box = QVBoxLayout()
        coverage_box.setSpacing(4)
        for cert in curriculum_coverage({}, scenarios):
            row = QHBoxLayout()
            cert_lbl = QLabel(cert)
            cert_lbl.setFixedWidth(160)
            _s.themed_ss(cert_lbl, "font-size:11px; color:{TEXT_PRIMARY}; background:transparent;")
            bar = QProgressBar()
            bar.setFixedHeight(6)
            bar.setTextVisible(False)
            _s.themed_ss(bar, "QProgressBar {{ background:{BG_CARD}; border:none; border-radius:3px; }}"
                "QProgressBar::chunk {{ background:{ACCENT}; border-radius:3px; }}")
            count_lbl = QLabel()
            count_lbl.setFixedWidth(140)
            _s.themed_ss(count_lbl, "font-size:11px; color:{TEXT_SECONDARY}; background:transparent;")
            row.addWidget(cert_lbl)
            row.addWidget(bar, 1)
            row.addWidget(count_lbl)
            coverage_box.addLayout(row)
            self._coverage_bars[cert] = bar
            self._coverage_lbls[cert] = count_lbl
        outer.addLayout(coverage_box)
        outer.addSpacing(12)

        # Badge grid — 4 columns, inside a scroll area.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;")
        body = QWidget()
        body.setStyleSheet("background:transparent;")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        grid = QGridLayout()
        grid.setSpacing(12)
        for idx, scenario in enumerate(scenarios):
            card, widgets = self._build_card(scenario)
            self._cards[scenario.id]       = card
            self._medallions[scenario.id]  = widgets["medallion"]
            self._status_lbls[scenario.id] = widgets["status_lbl"]
            self._badge_rows[scenario.id]  = widgets["badge_row"]
            self._start_btns[scenario.id]  = widgets["start_btn"]
            grid.addWidget(card, idx // 4, idx % 4)
        body_lay.addLayout(grid)
        body_lay.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self.refresh({})

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self, progress: dict) -> None:
        """Rebuild every card's state from persisted progress. Same push-model contract as
        LabPickerPanel.refresh_progress() — this widget never touches QSettings."""
        done, total = earned_count(progress, self._scenarios)
        self._progress_bar.set_smooth_value(done)
        self._progress_lbl.setText(f"{done} of {total} earned")

        coverage = curriculum_coverage(progress, self._scenarios)
        for cert, (earned_n, total_n) in coverage.items():
            bar = self._coverage_bars.get(cert)
            lbl = self._coverage_lbls.get(cert)
            if bar is None or lbl is None:
                continue
            bar.setRange(0, total_n)
            bar.setValue(earned_n)
            lbl.setText(f"{earned_n} / {total_n} objectives")

        for state in badge_states(progress, self._scenarios):
            sid = state.scenario_id
            self._medallions[sid].set_earned(state.earned)
            self._status_lbls[sid].setText(
                f"Earned {state.earned_at}" if state.earned else "Locked"
            )
            _s.themed_ss(self._status_lbls[sid], lambda done=state.earned: _s.qss_chip(
                _s.BADGE_OK_FG if done else _s.BADGE_OFF_FG,
                _s.BADGE_OK_BG if done else _s.BADGE_OFF_BG,
                _s.BADGE_OK_BORDER if done else _s.BADGE_OFF_BORDER,
            ))
            _s.themed_ss(self._cards[sid], lambda done=state.earned: _s.qss_frame(
                "scoreboardCard",
                bg=(_s.BG_ALT_ROW if done else _s.BG_CARD),
                hover_border=_s.ACCENT,
            ))
            self._start_btns[sid].setVisible(not state.earned)

            row = self._badge_rows[sid]
            while row.count():
                item = row.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            try:
                from ui.widgets.objective_badge import ObjectiveBadge
                for ob in ObjectiveBadge.for_scenario(state.title):
                    row.addWidget(ob)
                row.addStretch()
            except Exception:
                pass  # non-fatal — badge widget optional

    # ── Card construction ────────────────────────────────────────────────────

    def _build_card(self, scenario: LabScenario) -> Tuple[QFrame, dict]:
        card = QFrame()
        card.setObjectName("scoreboardCard")
        _s.themed_ss(card, lambda: _s.qss_frame("scoreboardCard", hover_border=_s.ACCENT))
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(6)

        medallion = BadgeMedallion(size=64)
        med_row = QHBoxLayout()
        med_row.addStretch()
        med_row.addWidget(medallion)
        med_row.addStretch()
        lay.addLayout(med_row)

        title_lbl = QLabel(scenario.title)
        title_lbl.setWordWrap(True)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _s.themed_ss(title_lbl, "font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent;")
        lay.addWidget(title_lbl)

        status_lbl = QLabel("Locked")
        status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(status_lbl)

        badge_row = QHBoxLayout()
        badge_row.setSpacing(4)
        lay.addLayout(badge_row)

        start_btn = QPushButton("Start →")
        start_btn.setFixedHeight(24)
        _s.themed_ss(start_btn, "QPushButton {{ background:transparent; color:{ACCENT};"
            " border:1px solid {ACCENT}; border-radius:4px; font-size:10px; }}"
            "QPushButton:hover {{ background:{BG_HOVER}; color:{ACCENT}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}")
        start_btn.clicked.connect(lambda _, s=scenario: self.start_requested.emit(s))
        lay.addWidget(start_btn)

        return card, {
            "medallion":  medallion,
            "status_lbl": status_lbl,
            "badge_row":  badge_row,
            "start_btn":  start_btn,
        }
