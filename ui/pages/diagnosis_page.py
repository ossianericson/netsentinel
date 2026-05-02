"""
One-click 'What's Wrong?' diagnosis page.

Three internal states managed via a QStackedWidget:
  0 — idle:    single 'Run Diagnosis' button
  1 — running: progress bar + step label + Cancel button
  2 — done:    verdict card + up to 5 finding cards + Run Again button
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from modules.metric_store import MetricStore
from ui.styles import (
    ACCENT, AMBER, BG_CARD, BG_DARK, BORDER, GREEN, RED,
    TEXT_PRIMARY, TEXT_SECONDARY,
)

_SEV_COLOR = {
    "CRITICAL": RED,
    "HIGH":     RED,
    "MEDIUM":   AMBER,
    "LOW":      GREEN,
    "INFO":     ACCENT,
}

_IDLE    = 0
_RUNNING = 1
_DONE    = 2


class DiagnosisPage(QWidget):

    navigate_to = pyqtSignal(str)  # emits "Overview" when back link is clicked

    def __init__(self, store: Optional[MetricStore] = None, parent=None):
        super().__init__(parent)
        self._store        = store
        self._worker       = None
        self._gateway_ip   = None
        self._gateway_mac  = None
        self._setup_ui()

    def set_network_info(
        self,
        gateway_ip: Optional[str],
        gateway_mac: Optional[str],
    ) -> None:
        self._gateway_ip  = gateway_ip
        self._gateway_mac = gateway_mac

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"QWidget {{ background:{BG_DARK}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # Back link
        back_btn = QPushButton("← Overview")
        back_btn.setFlat(True)
        back_btn.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; padding:0; text-align:left; }}"
            f"QPushButton:hover {{ color:#005A9E; }}"
        )
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(lambda: self.navigate_to.emit("Overview"))
        root.addWidget(back_btn)

        title = QLabel("What's Wrong?")
        title.setStyleSheet(
            f"font-size:18px; font-weight:bold; color:{TEXT_PRIMARY}; background:transparent;"
        )
        sub = QLabel(
            "Runs all detection modules and produces a plain-English diagnosis of your network."
        )
        sub.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;"
        )
        root.addWidget(title)
        root.addWidget(sub)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_idle())    # 0
        self._stack.addWidget(self._build_running()) # 1
        self._stack.addWidget(self._build_done())    # 2
        root.addWidget(self._stack, 1)

    def _build_idle(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(10)

        self._run_btn = QPushButton("Run Diagnosis")
        self._run_btn.setFixedWidth(220)
        self._run_btn.setFixedHeight(52)
        self._run_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#fff; border:none;"
            f" font-size:15px; font-weight:bold; border-radius:6px; }}"
            f"QPushButton:hover {{ background:#005A9E; }}"
        )
        self._run_btn.clicked.connect(self._start)
        lay.addWidget(self._run_btn)

        hint = QLabel("Takes about 30 seconds.")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;"
        )
        lay.addWidget(hint)
        return w

    def _build_running(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(14)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFixedWidth(420)
        self._progress_bar.setFixedHeight(10)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setStyleSheet(
            f"QProgressBar {{ background:#E0E8EF; border-radius:5px; border:none; }}"
            f"QProgressBar::chunk {{ background:{ACCENT}; border-radius:5px; }}"
        )

        self._step_lbl = QLabel("Starting…")
        self._step_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._step_lbl.setStyleSheet(
            f"font-size:13px; color:{TEXT_SECONDARY}; background:transparent;"
        )

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedWidth(100)
        self._cancel_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_SECONDARY};"
            f" border:1px solid {BORDER}; padding:4px 14px; font-size:11px;"
            f" border-radius:4px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
        )
        self._cancel_btn.clicked.connect(self._cancel)

        lay.addWidget(self._progress_bar, alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._step_lbl)
        lay.addWidget(self._cancel_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        return w

    def _build_done(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        # Verdict card
        self._verdict_card = QFrame()
        self._verdict_card.setObjectName("verdictCard")
        self._verdict_card.setStyleSheet(
            f"QFrame#verdictCard {{ background:{BG_CARD};"
            f" border-left:4px solid {ACCENT}; border-top:1px solid {BORDER};"
            f" border-right:1px solid {BORDER}; border-bottom:1px solid {BORDER}; }}"
        )
        vc_lay = QVBoxLayout(self._verdict_card)
        vc_lay.setContentsMargins(14, 10, 14, 10)
        vc_lay.setSpacing(4)

        self._verdict_title = QLabel("Diagnosis Result")
        self._verdict_title.setStyleSheet(
            f"font-size:13px; font-weight:bold; color:{TEXT_PRIMARY};"
            f" border:none; background:transparent;"
        )
        self._verdict_text = QLabel("–")
        self._verdict_text.setWordWrap(True)
        self._verdict_text.setStyleSheet(
            f"font-size:12px; color:{TEXT_PRIMARY}; border:none; background:transparent;"
        )
        vc_lay.addWidget(self._verdict_title)
        vc_lay.addWidget(self._verdict_text)
        outer.addWidget(self._verdict_card)

        # Findings list in a scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea {{ background:{BG_DARK}; border:none; }}")

        self._findings_container = QWidget()
        self._findings_container.setStyleSheet(f"background:{BG_DARK};")
        self._findings_layout = QVBoxLayout(self._findings_container)
        self._findings_layout.setContentsMargins(0, 0, 0, 0)
        self._findings_layout.setSpacing(6)
        self._findings_layout.addStretch()

        scroll.setWidget(self._findings_container)
        outer.addWidget(scroll, 1)

        # Run Again button
        btn_row = QHBoxLayout()
        self._again_btn = QPushButton("Run Again")
        self._again_btn.setFixedWidth(120)
        self._again_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{ACCENT};"
            f" border:1px solid {ACCENT}; padding:4px 14px; font-size:11px;"
            f" border-radius:4px; }}"
            f"QPushButton:hover {{ background:{ACCENT}; color:#fff; }}"
        )
        self._again_btn.clicked.connect(self._reset)
        btn_row.addWidget(self._again_btn)
        btn_row.addStretch()
        outer.addLayout(btn_row)

        return w

    # ── Finding card ──────────────────────────────────────────────────────────

    def _make_finding_card(self, finding) -> QFrame:
        sev      = getattr(finding, "severity",    "INFO")
        headline = getattr(finding, "headline",    "")
        remedy   = getattr(finding, "remediation", "")
        color    = _SEV_COLOR.get(sev, ACCENT)

        card = QFrame()
        card.setObjectName("findingCard")
        card.setStyleSheet(
            f"QFrame#findingCard {{ background:{BG_CARD};"
            f" border-left:3px solid {color}; border-top:1px solid {BORDER};"
            f" border-right:1px solid {BORDER}; border-bottom:1px solid {BORDER}; }}"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(4)

        hdr = QHBoxLayout()
        badge = QLabel(sev)
        badge.setFixedWidth(68)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"font-size:9px; font-weight:bold; color:{color};"
            f" border:1px solid {color}; border-radius:3px; padding:1px 0;"
            f" background:transparent;"
        )
        hl = QLabel(headline)
        hl.setWordWrap(True)
        hl.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            f" border:none; background:transparent;"
        )
        hdr.addWidget(badge)
        hdr.addWidget(hl, 1)
        lay.addLayout(hdr)

        if remedy:
            rem = QLabel(remedy)
            rem.setWordWrap(True)
            rem.setStyleSheet(
                f"font-size:11px; color:{TEXT_SECONDARY}; border:none; background:transparent;"
            )
            lay.addWidget(rem)

        return card

    # ── State machine ─────────────────────────────────────────────────────────

    def _start(self) -> None:
        from workers.diagnosis_worker import DiagnosisWorker
        self._stack.setCurrentIndex(_RUNNING)
        self._progress_bar.setValue(0)
        self._step_lbl.setText("Starting…")
        self._worker = DiagnosisWorker(
            gateway_ip=self._gateway_ip,
            gateway_mac=self._gateway_mac,
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _cancel(self) -> None:
        if self._worker:
            self._worker.stop()
        self._reset()

    def _reset(self) -> None:
        if self._worker:
            self._worker.stop()
            self._worker.quit()
            self._worker.wait(3000)
            self._worker = None
        self._stack.setCurrentIndex(_IDLE)

    def _on_progress(self, pct: int, msg: str) -> None:
        self._progress_bar.setValue(pct)
        self._step_lbl.setText(msg)

    def _on_finished(self, result) -> None:
        if result is None:
            self._reset()
            return
        self._show_result(result)

    def _show_result(self, result) -> None:
        sev      = getattr(result, "global_severity", "INFO")
        summary  = getattr(result, "plain_summary",   "") or "No issues detected."
        findings = getattr(result, "findings",        [])

        color = _SEV_COLOR.get(sev, ACCENT)
        self._verdict_card.setStyleSheet(
            f"QFrame#verdictCard {{ background:{BG_CARD};"
            f" border-left:4px solid {color}; border-top:1px solid {BORDER};"
            f" border-right:1px solid {BORDER}; border-bottom:1px solid {BORDER}; }}"
        )
        self._verdict_title.setText(f"Diagnosis — {sev}")
        self._verdict_title.setStyleSheet(
            f"font-size:13px; font-weight:bold; color:{color};"
            f" border:none; background:transparent;"
        )
        self._verdict_text.setText(summary)

        # Clear old finding cards (preserve trailing stretch)
        while self._findings_layout.count() > 1:
            item = self._findings_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        for finding in findings[:5]:
            card = self._make_finding_card(finding)
            self._findings_layout.insertWidget(
                self._findings_layout.count() - 1, card
            )

        self._stack.setCurrentIndex(_DONE)
