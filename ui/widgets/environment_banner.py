"""
EnvironmentBanner — thin warning bar shown on Home when NetSentinel detects it is
running on a VPN, corporate, or unusually large network (see modules/network_environment.py).

Conforms to the NetSentinel design system, modelled directly on ui/npcap_banner.py:
  • Collapsed row: 28px fixed, ADMIN_WARN_BG background, ⚠ icon + title + ⓘ + dismiss.
  • ⓘ expands an inline details area listing plain-English reasons + effects.
  • Hidden entirely on a "home" environment, or once dismissed for this environment's
    fingerprint (kind + vpn_adapter + domain) — moving to a different network re-arms it.

Usage::

    from ui.widgets.environment_banner import EnvironmentBanner
    banner = EnvironmentBanner()
    lay.addWidget(banner)                 # always add it — starts hidden
    banner.set_environment(net_env)       # call once detection completes
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from modules.network_environment import NetworkEnvironment
from ui.context_banners import mark_banner_seen, should_show_banner
from ui.widgets.device_detail_pane import _wire_close_icon
from ui import styles as _s


class EnvironmentBanner(QFrame):
    """Warning bar for non-home network environments. Starts hidden; call set_environment()."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._env: NetworkEnvironment | None = None
        self.setVisible(False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        row = QWidget()
        row.setFixedHeight(28)
        _s.themed_ss(row, "QWidget {{ background:{ADMIN_WARN_BG};"
            " border:none; border-bottom:1px solid {ADMIN_WARN_BORDER}; }}")
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(10, 0, 10, 0)
        row_lay.setSpacing(8)

        icon = QLabel("⚠")
        _s.themed_ss(icon, "font-size:12px; color:{ADMIN_WARN_FG}; background:transparent; border:none;")
        self._title_lbl = QLabel("")
        _s.themed_ss(self._title_lbl, "font-size:11px; color:{ADMIN_WARN_FG}; background:transparent; border:none;")

        self._info_btn = QPushButton("ⓘ")
        self._info_btn.setFixedSize(20, 20)
        self._info_btn.setFlat(True)
        self._info_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._info_btn, "QPushButton {{ border:none; background:transparent;"
            " font-size:12px; color:{ADMIN_WARN_FG}; }}"
            "QPushButton:hover {{ color:{ADMIN_WARN_HOVER}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ADMIN_WARN_FG}; }}")
        self._info_btn.clicked.connect(self._toggle_details)

        self._dismiss_btn = QPushButton()
        self._dismiss_btn.setFixedSize(18, 18)
        self._dismiss_btn.setFlat(True)
        self._dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _wire_close_icon(self._dismiss_btn)
        _s.themed_ss(self._dismiss_btn, lambda: _s.qss_dismiss_button(9))
        self._dismiss_btn.clicked.connect(self._dismiss)

        row_lay.addWidget(icon)
        row_lay.addWidget(self._title_lbl)
        row_lay.addStretch()
        row_lay.addWidget(self._info_btn)
        row_lay.addWidget(self._dismiss_btn)
        outer.addWidget(row)

        self._details_lbl = QLabel("")
        self._details_lbl.setWordWrap(True)
        self._details_lbl.setVisible(False)
        _s.themed_ss(self._details_lbl, "font-size:10px; color:{ADMIN_WARN_FG}; background:{ADMIN_WARN_BG};"
            " border:none; border-bottom:1px solid {ADMIN_WARN_BORDER}; padding:6px 14px;")
        outer.addWidget(self._details_lbl)

    def _toggle_details(self) -> None:
        self._details_lbl.setVisible(not self._details_lbl.isVisible())

    def _dismiss(self) -> None:
        if self._env is not None:
            mark_banner_seen(self._env.fingerprint())
        self.setVisible(False)

    def set_environment(self, env: NetworkEnvironment | None) -> None:
        """Show (or re-hide) the banner for the given detected environment."""
        self._env = env
        self._details_lbl.setVisible(False)
        if env is None or env.kind == "home" or not should_show_banner(env.fingerprint()):
            self.setVisible(False)
            return
        self._title_lbl.setText(env.title)
        details = "\n".join(f"• {r}" for r in env.reasons) + "\n\n" + \
            "\n".join(f"• {e}" for e in env.effects)
        self._details_lbl.setText(details)
        self.setVisible(True)
