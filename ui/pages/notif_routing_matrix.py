"""
notif_routing_matrix.py — _NotifRoutingMatrixMixin: per-rule x per-channel
advanced routing matrix.

Collapsed-by-default "Advanced" card, same expander shape as
_build_escalation_card (notif_extra_channels.py). Additive and self-gating:
absent notif/rule_routing -> {} -> every channel's rule_types stays []
("all rules", the value _matches_channel() already understands) -> byte-
identical behaviour to before this card existed.

State is self-loaded from QSettings during _build_routing_matrix_card() —
same self-contained pattern as _build_weekly_digest_card() /
_build_morning_briefing_card() — so it is already populated by the time
NotificationsPage._restore() calls _apply_to_router() at the end of __init__.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui import styles as _s
from ui.pages.notif_channel_panels import _ALERT_RULE_DEFS, _card
from modules.notification_router import routing_matrix_from_json, routing_matrix_to_json

# channel_key -> combo display label, in the order shown in the combo.
_ROUTE_CHANNEL_LABELS = (
    ("toast",    "Desktop toast"),
    ("webhook",  "Webhook"),
    ("email",    "Email"),
    ("pushover", "Pushover"),
    ("ntfy",     "ntfy"),
    ("telegram", "Telegram"),
)

_ROUTE_GRID_COLUMNS = 3


class _NotifRoutingMatrixMixin:
    """Pure-Python mixin. NotificationsPage inherits this alongside QWidget."""

    def _build_routing_matrix_card(self) -> QWidget:
        card, bl = _card("Advanced Routing")
        self._routing_expand_btn = QPushButton("▶  Advanced: Route rules to channels")
        self._routing_expand_btn.setFlat(True)
        self._routing_expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._routing_expand_btn, "QPushButton {{ color:{ACCENT}; font-size:11px; font-weight:bold;"
            " background:transparent; border:none; padding:2px 0; text-align:left; }}"
            "QPushButton:hover {{ color:{ACCENT_DARK}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
        bl.addWidget(self._routing_expand_btn)

        self._routing_body = QWidget()
        self._routing_body.setVisible(False)
        body_lay = QVBoxLayout(self._routing_body)
        body_lay.setContentsMargins(0, 6, 0, 0)
        body_lay.setSpacing(8)

        explainer = QLabel(
            "By default every channel receives every alert rule. Pick a channel "
            "below to route only specific rules to it."
        )
        explainer.setWordWrap(True)
        _s.themed_ss(explainer, "font-size:11px; color:{TEXT_SECONDARY}; border:none;")
        body_lay.addWidget(explainer)

        chan_row = QHBoxLayout()
        chan_row.setSpacing(8)
        chan_lbl = QLabel("Channel:")
        _s.themed_ss(chan_lbl, "font-size:11px; color:{TEXT_PRIMARY}; border:none;")
        self._route_channel_combo = QComboBox()
        for key, label in _ROUTE_CHANNEL_LABELS:
            self._route_channel_combo.addItem(label, key)
        self._route_channel_combo.setFixedWidth(160)
        _s.themed_ss(self._route_channel_combo, "font-size:11px; color:{TEXT_PRIMARY};"
            " border:1px solid {BORDER}; padding:2px 4px;")
        chan_row.addWidget(chan_lbl)
        chan_row.addWidget(self._route_channel_combo)
        chan_row.addStretch()
        body_lay.addLayout(chan_row)

        self._chk_route_all = QCheckBox("All rules")
        _s.themed_ss(self._chk_route_all, "QCheckBox{{color:{TEXT_PRIMARY};font-size:11px;font-weight:bold;}}")
        self._chk_route_all.clicked.connect(self._on_route_all_clicked)
        body_lay.addWidget(self._chk_route_all)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        self._route_rule_checks: dict = {}
        for i, (name, rule_type, _desc) in enumerate(_ALERT_RULE_DEFS):
            chk = QCheckBox(name)
            _s.themed_ss(chk, "QCheckBox{{color:{TEXT_PRIMARY};font-size:11px;}}")
            chk.toggled.connect(self._on_route_rule_toggled)
            grid.addWidget(chk, i // _ROUTE_GRID_COLUMNS, i % _ROUTE_GRID_COLUMNS)
            self._route_rule_checks[rule_type] = chk
        body_lay.addLayout(grid)

        self._route_empty_warning = QLabel("⚠ No rules selected — this channel will receive nothing.")
        _s.themed_ss(self._route_empty_warning, "font-size:11px; color:{AMBER}; border:none; padding-top:4px;")
        self._route_empty_warning.setVisible(False)
        body_lay.addWidget(self._route_empty_warning)

        bl.addWidget(self._routing_body)
        self._routing_expand_btn.clicked.connect(self._toggle_routing_body)

        qs = QSettings("NetSentinel", "NetSentinel")
        self._route_matrix: dict = routing_matrix_from_json(qs.value("notif/rule_routing", ""))
        self._route_empty: set = set()
        self._route_active_channel = self._route_channel_combo.currentData()
        self._load_route_column(self._route_active_channel)
        self._route_channel_combo.currentIndexChanged.connect(self._on_route_channel_changed)

        return card

    def _toggle_routing_body(self) -> None:
        expanded = self._routing_body.isVisible()
        self._routing_body.setVisible(not expanded)
        arrow = "▼" if not expanded else "▶"
        self._routing_expand_btn.setText(f"{arrow}  Advanced: Route rules to channels")

    # ── Column flush/load — only the active channel's checkboxes are shown,
    #    so switching channels means saving the outgoing column's state and
    #    loading the incoming one. ─────────────────────────────────────────

    def _flush_route_column(self, channel_key: str) -> None:
        selected = [rt for rt, chk in self._route_rule_checks.items() if chk.isChecked()]
        self._route_matrix[channel_key] = selected
        if selected:
            self._route_empty.discard(channel_key)
        else:
            self._route_empty.add(channel_key)

    def _load_route_column(self, channel_key: str) -> None:
        if channel_key in self._route_empty:
            selected = set()
        else:
            stored = self._route_matrix.get(channel_key, [])
            # [] (or never configured) means "all rules" — matches
            # _matches_channel()'s rule_types=[] convention.
            selected = set(stored) if stored else set(self._route_rule_checks)
        for rt, chk in self._route_rule_checks.items():
            chk.blockSignals(True)
            chk.setChecked(rt in selected)
            chk.blockSignals(False)
        self._chk_route_all.blockSignals(True)
        self._chk_route_all.setChecked(len(selected) == len(self._route_rule_checks))
        self._chk_route_all.blockSignals(False)
        self._route_empty_warning.setVisible(channel_key in self._route_empty)

    def _on_route_channel_changed(self, _index: int) -> None:
        prev = self._route_active_channel
        if prev is not None:
            self._flush_route_column(prev)
        new_key = self._route_channel_combo.currentData()
        self._route_active_channel = new_key
        self._load_route_column(new_key)
        self._save()

    def _on_route_rule_toggled(self, _checked: bool) -> None:
        active = self._route_active_channel
        if active is None:
            return
        self._flush_route_column(active)
        self._route_empty_warning.setVisible(active in self._route_empty)
        all_checked = all(chk.isChecked() for chk in self._route_rule_checks.values())
        self._chk_route_all.blockSignals(True)
        self._chk_route_all.setChecked(all_checked)
        self._chk_route_all.blockSignals(False)
        self._save()

    def _on_route_all_clicked(self, checked: bool) -> None:
        for chk in self._route_rule_checks.values():
            chk.blockSignals(True)
            chk.setChecked(checked)
            chk.blockSignals(False)
        active = self._route_active_channel
        if active is not None:
            self._flush_route_column(active)
            self._route_empty_warning.setVisible(active in self._route_empty)
        self._save()

    # ── Persistence + apply-to-router helpers ─────────────────────────────

    def _save_routing_matrix(self) -> None:
        active = getattr(self, "_route_active_channel", None)
        if active is not None:
            self._flush_route_column(active)
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("notif/rule_routing", routing_matrix_to_json(self._route_matrix))

    def _route_types_for(self, channel_key: str) -> list:
        """rule_types= value for a channel — [] means 'all', matching
        _matches_channel()'s convention. A stored list covering every rule
        type collapses to [] too (same rule routing_matrix_to_json() applies
        at the persistence layer) so a freshly-flushed 'everything checked'
        column is byte-identical to a never-touched one, not just functionally
        equivalent."""
        stored = self._route_matrix.get(channel_key, [])
        if stored and set(stored) >= set(self._route_rule_checks):
            return []
        return list(stored)

    def _route_channel_disabled(self, channel_key: str) -> bool:
        """True when the user has explicitly deselected every rule for this
        channel — _apply_to_router() folds this into that channel's enabled=."""
        return channel_key in self._route_empty
