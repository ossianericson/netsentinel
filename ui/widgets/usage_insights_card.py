"""
ui/widgets/usage_insights_card.py — "Usage insights" home page card (S6-3/S6-4/S6-5).

Reads already-persisted App Traffic history from MetricStore (written by
ui/tabs.py._on_app_traffic_sample, fed from AppTrafficPage.traffic_sample_ready)
and turns it into a household usage narrative:

    "Your household used 187 GB this week. Most was streaming (68%), mainly
     between 7pm and 11pm. Gaming traffic increased 40% vs last week."

Optionally appends an ISP plan utilization line (S6-4, only if a monthly data
cap is configured in Settings → Internet Plan) and a one-time-dismissible QoS
overlap suggestion (S6-5).

Shows an empty-state CTA until App Traffic monitoring has collected at least
one window of history — this card never starts packet capture itself
(RULE 4: capture only runs in a worker the user explicitly started).
"""

from __future__ import annotations

import hashlib
from typing import Optional

from PyQt6.QtCore import Qt, QSettings, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from modules.metric_store import MetricStore
from modules.traffic_insights import (
    build_qos_recommendation,
    build_usage_insights,
    compute_plan_utilization,
    format_insight_summary,
)
from ui.styles import (
    ACCENT, ACCENT_DARK, ACCENT_LITE, BG_CARD, BORDER,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)

_QOS_CATEGORY_PAIR = ("Gaming", "VoIP")


class UsageInsightsCard(QWidget):
    """Full-width home page card narrating last week's bandwidth usage."""

    navigate_to = pyqtSignal(str)   # emitted when CTA is clicked

    def __init__(self, store: Optional[MetricStore] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._store = store
        self._has_data = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setObjectName("usageInsightsCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._frame = QFrame()
        self._frame.setObjectName("usageInsightsFrame")
        self._frame.setStyleSheet(
            f"QFrame#usageInsightsFrame {{ background:{BG_CARD};"
            f" border:1px solid {BORDER}; border-radius:6px; }}"
        )
        frame_lay = QVBoxLayout(self._frame)
        frame_lay.setContentsMargins(14, 10, 14, 10)
        frame_lay.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        self._icon_lbl = QLabel("◆")
        self._icon_lbl.setFixedWidth(28)
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_lbl.setStyleSheet(
            f"font-size:18px; font-weight:bold; color:{TEXT_MUTED};"
            " background:transparent; border:none;"
        )

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        self._headline_lbl = QLabel("Usage insights")
        self._headline_lbl.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        self._headline_lbl.setWordWrap(True)

        self._sub_lbl = QLabel(
            "Start App Traffic monitoring to see what your household used your "
            "bandwidth for this week."
        )
        self._sub_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        self._sub_lbl.setWordWrap(True)

        text_col.addWidget(self._headline_lbl)
        text_col.addWidget(self._sub_lbl)

        self._cta_btn = QPushButton("Open App Traffic →")
        self._cta_btn.setFixedHeight(28)
        self._cta_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cta_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._cta_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:4px; font-size:11px; padding:0 12px; }}"
            f"QPushButton:hover {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
        )
        self._cta_btn.clicked.connect(lambda: self.navigate_to.emit("App Traffic"))

        top_row.addWidget(self._icon_lbl)
        top_row.addLayout(text_col, 1)
        top_row.addWidget(self._cta_btn)
        frame_lay.addLayout(top_row)

        # ISP plan utilization line (S6-4) — hidden unless a cap is configured
        self._plan_lbl = QLabel("")
        self._plan_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )
        self._plan_lbl.setVisible(False)
        frame_lay.addWidget(self._plan_lbl)

        # QoS overlap suggestion (S6-5) — dismissible, shown once per pattern
        qos_row = QHBoxLayout()
        self._qos_lbl = QLabel("")
        self._qos_lbl.setWordWrap(True)
        self._qos_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        self._qos_dismiss_btn = QPushButton("✕")
        self._qos_dismiss_btn.setFixedSize(18, 18)
        self._qos_dismiss_btn.setFlat(True)
        self._qos_dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._qos_dismiss_btn.setStyleSheet(
            f"QPushButton {{ color:{TEXT_SECONDARY}; background:transparent; border:none; font-size:9px; }}"
            f"QPushButton:hover   {{ color:{TEXT_PRIMARY}; background:transparent; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; background:transparent; }}"
        )
        self._qos_dismiss_btn.setToolTip("Dismiss this suggestion")
        self._qos_dismiss_btn.clicked.connect(self._dismiss_qos_suggestion)
        qos_row.addWidget(self._qos_lbl, 1)
        qos_row.addWidget(self._qos_dismiss_btn)
        self._qos_row_w = QWidget()
        self._qos_row_w.setLayout(qos_row)
        self._qos_row_w.setVisible(False)
        frame_lay.addWidget(self._qos_row_w)

        outer.addWidget(self._frame)
        self._qos_key = ""

    # ── Data refresh ───────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Re-query MetricStore and rebuild the narrative. Safe to call repeatedly."""
        if self._store is None:
            return
        try:
            this_week = self._store.query_app_traffic_category_totals_range(0, 168)
            last_week = self._store.query_app_traffic_category_totals_range(168, 336)
        except Exception:
            return  # non-fatal — store unavailable

        if not this_week:
            return   # keep showing the empty-state CTA

        dominant_cat = max(this_week.items(), key=lambda kv: kv[1])[0]
        try:
            dominant_hourly = self._store.query_app_traffic_hourly_distribution(
                category=dominant_cat, hours=168.0,
            )
        except Exception:
            dominant_hourly = {}

        insight = build_usage_insights(this_week, dominant_hourly, last_week)
        self._apply_insight(insight)
        self._apply_plan_utilization()
        self._apply_qos_suggestion()

    def _apply_insight(self, insight) -> None:
        if not insight.has_data:
            return
        self._has_data = True
        self._icon_lbl.setStyleSheet(
            f"font-size:18px; font-weight:bold; color:{ACCENT};"
            " background:transparent; border:none;"
        )
        self._headline_lbl.setText("Usage insights")
        self._sub_lbl.setText(format_insight_summary(insight))
        self._cta_btn.setText("View Details →")

    def _apply_plan_utilization(self) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        cap_gb = qs.value("traffic/monthly_cap_gb", 0.0, type=float)
        if not cap_gb:
            self._plan_lbl.setVisible(False)
            return
        try:
            month_totals = self._store.query_app_traffic_category_totals(hours=24.0 * 30)
        except Exception:
            month_totals = {}
        used_bytes = sum(month_totals.values())
        text = compute_plan_utilization(used_bytes, cap_gb)
        if text:
            self._plan_lbl.setText(text)
            self._plan_lbl.setVisible(True)
        else:
            self._plan_lbl.setVisible(False)

    def _apply_qos_suggestion(self) -> None:
        try:
            cat_a, cat_b = _QOS_CATEGORY_PAIR
            hourly_a = self._store.query_app_traffic_hourly_distribution(category=cat_a, hours=168.0)
            hourly_b = self._store.query_app_traffic_hourly_distribution(category=cat_b, hours=168.0)
        except Exception:
            self._qos_row_w.setVisible(False)
            return

        text = build_qos_recommendation(cat_a, hourly_a, cat_b, hourly_b)
        if not text:
            self._qos_row_w.setVisible(False)
            return

        key = hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
        self._qos_key = key
        qs = QSettings("NetSentinel", "NetSentinel")
        if qs.value(f"usage_insights/qos_dismissed/{key}", False, type=bool):
            self._qos_row_w.setVisible(False)
            return
        self._qos_lbl.setText(text)
        self._qos_row_w.setVisible(True)

    def _dismiss_qos_suggestion(self) -> None:
        if self._qos_key:
            QSettings("NetSentinel", "NetSentinel").setValue(
                f"usage_insights/qos_dismissed/{self._qos_key}", True,
            )
        self._qos_row_w.setVisible(False)
