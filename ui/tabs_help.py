"""
tabs_help.py — _HelpTabsMixin: Help & Shortcuts tab builder + About dialog +
manual update check.

Extracted from ui/dashboard.py (P7 — dashboard.py diet).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from ui import styles as _s
from ui.dialog_utils import run_dialog


class _HelpTabsMixin:
    """Mixin providing the Help tab builder, About dialog, and update check.

    Extracted from ui/dashboard.py (P7 — dashboard.py diet).
    """

    # ── Help page ────────────────────────────────────────────────────────────

    def _build_help_tab(self) -> QWidget:
        """Static Help & Shortcuts reference page (body delegated to ui.help)."""
        from ui.help_tab import build_help_tab
        return build_help_tab(self)

    def _check_for_updates(self):
        """Manual update check from the Help tab button."""
        from modules.utils import is_store_app  # noqa: PLC0415
        if is_store_app():
            self._update_lbl.setText(
                "Updates are managed by the Microsoft Store and install automatically."
            )
            return

        import urllib.request, json as _json
        from PyQt6.QtWidgets import QApplication
        current = QApplication.applicationVersion()
        self._update_lbl.setText("Checking…")
        QApplication.processEvents()
        try:
            url = "https://api.github.com/repos/ossianericson/netsentinel/releases/latest"
            req = urllib.request.Request(url, headers={"User-Agent": "NetSentinel"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = _json.loads(resp.read())
            latest = data.get("tag_name", "").lstrip("v")
            def _ver(s):
                try:
                    return tuple(int(x) for x in s.split("."))
                except ValueError:
                    return (0,)
            if latest and _ver(latest) > _ver(current):
                self._update_lbl.setText(
                    f"Update available: v{latest} (you have v{current}) — "
                    '<a href="https://github.com/ossianericson/netsentinel/releases/latest" '
                    f'style="color:{_s.ACCENT};">Download</a>'
                    ' &nbsp;·&nbsp; or: <code>winget upgrade NetSentinel.NetSentinel</code>'
                )
                self._update_lbl.setOpenExternalLinks(True)
                self._update_lbl.setTextFormat(Qt.TextFormat.RichText)
                self._on_update_available(latest)  # also show the notification bar
            else:
                self._update_lbl.setText(f"You're up to date (v{current})")
        except Exception as exc:
            self._update_lbl.setText(f"Update check failed: {exc}")

    def _show_about(self):
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QLabel, QPushButton, QApplication, QFrame,
        )
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont
        dlg = QDialog(self)
        dlg.setWindowTitle("About NetSentinel")
        dlg.setMinimumWidth(460)
        dlg.setStyleSheet(self.styleSheet())
        lay = QVBoxLayout(dlg)
        lay.setSpacing(0)
        lay.setContentsMargins(32, 28, 32, 24)

        # Title + version + subtitle
        title = QLabel("NetSentinel")
        title.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        _s.themed_ss(title, "color:{ACCENT};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ver_lbl = QLabel(f"v{QApplication.applicationVersion()}")
        _s.themed_ss(ver_lbl, "color:{TEXT_SECONDARY}; font-size:12px;")
        ver_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Network Security Scanner & Connectivity Monitor")
        _s.themed_ss(subtitle, "color:{TEXT_PRIMARY}; font-size:13px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)

        lay.addWidget(title)
        lay.addSpacing(2)
        lay.addWidget(ver_lbl)
        lay.addSpacing(6)
        lay.addWidget(subtitle)
        lay.addSpacing(18)

        # Divider
        _div = QFrame()
        _div.setFrameShape(QFrame.Shape.HLine)
        _s.themed_ss(_div, "color:{BORDER};")
        lay.addWidget(_div)
        lay.addSpacing(14)

        # Body — open source statement + supporter links
        body = QLabel(
            "NetSentinel will always remain free and open source.<br><br>"
            "If you find this tool valuable, please consider supporting:<br>"
            f'&nbsp;&nbsp;&#8226;&nbsp;<a href="https://donate.wikimedia.org/"'
            f' style="color:{_s.ACCENT};">Wikipedia</a>'
            " — free knowledge for everyone<br>"
            f'&nbsp;&nbsp;&#8226;&nbsp;<a href="https://eff.org/donate"'
            f' style="color:{_s.ACCENT};">Electronic Frontier Foundation</a>'
            " — protecting digital rights<br><br>"
            "Thank you for using NetSentinel."
        )
        body.setOpenExternalLinks(True)
        body.setWordWrap(True)
        _s.themed_ss(body, "color:{TEXT_PRIMARY}; font-size:12px;")
        lay.addWidget(body)
        lay.addSpacing(16)

        # Divider
        _div2 = QFrame()
        _div2.setFrameShape(QFrame.Shape.HLine)
        _s.themed_ss(_div2, "color:{BORDER};")
        lay.addWidget(_div2)
        lay.addSpacing(10)

        # Disclaimer
        disclaimer = QLabel(
            "For use on networks you own or have explicit authorization to test."
        )
        disclaimer.setWordWrap(True)
        _s.themed_ss(disclaimer, "color:{TEXT_SECONDARY}; font-size:10px;")
        disclaimer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(disclaimer)
        lay.addSpacing(12)

        # Author + links
        author_lbl = QLabel(
            "Built by <b>Ossian Ericson</b>"
            f'&nbsp;&nbsp;&middot;&nbsp;&nbsp;<a href="https://github.com/ossianericson/netsentinel"'
            f' style="color:{_s.ACCENT};">GitHub</a>'
            f'&nbsp;&nbsp;&middot;&nbsp;&nbsp;<a href="https://www.linkedin.com/in/ossian-ericson/"'
            f' style="color:{_s.ACCENT};">LinkedIn</a>'
        )
        author_lbl.setOpenExternalLinks(True)
        author_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _s.themed_ss(author_lbl, "color:{TEXT_PRIMARY}; font-size:12px;")
        lay.addWidget(author_lbl)
        lay.addSpacing(18)

        # Close button
        btn_close = QPushButton("Close")
        btn_close.setObjectName("btnNetRefresh")
        btn_close.setFixedWidth(100)
        btn_close.clicked.connect(dlg.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        run_dialog(dlg)
