"""
OoklaCliBanner — thin info strip shown when the Ookla CLI is not installed.

Displayed at the top of the Speed Test page.  Offers a one-click winget install
and a link to the Ookla website.  Auto-hides if the CLI is already installed.

Security note: no credentials involved; winget is invoked with --silent and
--accept-package-agreements only.  The subprocess call uses CREATE_NO_WINDOW and
does not accept any user-supplied input.
"""

from __future__ import annotations

import platform
import subprocess

from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)
from ui import styles as _s
from ui.widgets.device_detail_pane import _wire_close_icon


class _OoklaInstallWorker(QThread):
    """Run `winget install Ookla.Speedtest.CLI` in a background thread."""

    finished = pyqtSignal(bool, str)   # (success, message)

    def run(self) -> None:
        try:
            flags = 0
            if platform.system() == "Windows":
                flags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
            result = subprocess.run(
                [
                    "winget", "install",
                    "--id", "Ookla.Speedtest.CLI",
                    "--source", "winget",
                    "--silent",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                ],
                capture_output=True,
                text=True,
                # winget writes UTF-8 (progress bars, box-drawing glyphs, localized
                # strings) rather than the OEM console codepage, so name the codec
                # explicitly and never let a glyph abort the install.
                encoding="utf-8",
                errors="replace",
                timeout=120,
                creationflags=flags,
            )
            if result.returncode == 0:
                self.finished.emit(True, "Ookla CLI installed successfully.")
            else:
                # winget exit code 0x8A150011 (-1978335215) means "already installed"
                if result.returncode in (-1978335215, 0x8A150011):
                    self.finished.emit(True, "Ookla CLI is already installed.")
                else:
                    stderr = (result.stderr or "").strip()[-300:]
                    self.finished.emit(False, f"winget exit {result.returncode}: {stderr}")
        except FileNotFoundError:
            self.finished.emit(False, "winget not found. Install it from the Microsoft Store.")
        except subprocess.TimeoutExpired:
            self.finished.emit(False, "Installation timed out after 120 seconds.")
        except Exception as exc:  # pragma: no cover
            self.finished.emit(False, str(exc))


class OoklaCliBanner(QFrame):
    """
    A 40px-tall informational strip shown when the Ookla CLI binary is absent.

    Signals
    -------
    installed()
        Emitted after a successful background install.  The speed-test page
        connects this to refresh its backend cascade.
    """

    installed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ooklaBanner")
        self._worker: _OoklaInstallWorker | None = None
        self._build_ui()
        self._check_visible()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.setFixedHeight(40)
        _s.themed_ss(self,
            "QFrame#ooklaBanner {{"
            "  background:{INFO_BOX_BG};"
            "  border:1px solid {INFO_BOX_BORDER};"
            "  border-radius:3px;"
            "}}"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(8)

        # Info icon + message
        icon = QLabel("\u2139")   # ℹ
        _s.themed_ss(icon, "color:{ACCENT}; font-size:14px; background:transparent; border:none;")
        icon.setFixedWidth(16)

        self._msg = QLabel(
            "Install the <b>Ookla Speedtest CLI</b> to unlock 1 Gbps+ multi-connection tests."
        )
        _s.themed_ss(self._msg,
            "color:{INFO_BOX_FG}; font-size:11px; background:transparent; border:none;"
        )
        self._msg.setTextFormat(Qt.TextFormat.RichText)

        # "Install via winget" button
        self._btn_install = QPushButton("Install via winget")
        _s.themed_ss(self._btn_install,
            "QPushButton {{"
            "  background:{ACCENT}; color:{WHITE};"
            "  border:none; border-radius:3px; padding:4px 12px; font-size:11px;"
            "}}"
            "QPushButton:hover {{ background:{ACCENT_DARK}; }}"
            "QPushButton:disabled {{ background:{BTN_DISABLED_BORDER}; color:{WHITE}; }}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        self._btn_install.setFixedHeight(28)
        self._btn_install.clicked.connect(self._on_install_clicked)

        # "Manual install" link
        self._btn_manual = QLabel()
        self._set_manual_link_text()
        _s.themed_ss(self._btn_manual, "background:transparent; border:none; font-size:11px;")
        self._btn_manual.setOpenExternalLinks(True)
        self._btn_manual.setTextFormat(Qt.TextFormat.RichText)

        # Dismiss button
        self._btn_dismiss = QPushButton()
        _wire_close_icon(self._btn_dismiss, "TEXT_SECONDARY")
        _s.themed_ss(self._btn_dismiss,
            "QPushButton {{"
            "  background:transparent;"
            "  border:none; padding:0 4px;"
            "}}"
            "QPushButton:hover {{ background:transparent; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; }}"
        )
        self._btn_dismiss.setFixedSize(24, 24)
        self._btn_dismiss.setToolTip(_s.safe_tooltip("Dismiss"))
        self._btn_dismiss.clicked.connect(self.hide)

        lay.addWidget(icon)
        lay.addWidget(self._msg, stretch=1)
        lay.addWidget(self._btn_install)
        lay.addWidget(self._btn_manual)
        lay.addWidget(self._btn_dismiss)

    def _set_manual_link_text(self) -> None:
        self._btn_manual.setText(
            f'<a href="https://www.speedtest.net/apps/cli" style="color:{_s.ACCENT};">'
            "Manual install</a>"
        )

    def refresh_theme(self) -> None:
        """Live theme switch: the manual-install link colour is baked into HTML
        text, outside the themed_ss registry, so it needs an explicit rebuild."""
        self._set_manual_link_text()

    # ── Visibility logic ──────────────────────────────────────────────────────

    def _check_visible(self) -> None:
        """Hide the banner immediately if the Ookla CLI is already installed."""
        try:
            from modules.speed_tester import _find_ookla_cli
            if _find_ookla_cli() is not None:
                self.hide()
                return
        except Exception:
            pass  # non-fatal
        # Only show on Windows (winget is Windows-only)
        if platform.system() != "Windows":
            self.hide()

    # ── Install flow ──────────────────────────────────────────────────────────

    @pyqtSlot()
    def _on_install_clicked(self) -> None:
        self._btn_install.setEnabled(False)
        self._btn_install.setText("Installing…")
        self._msg.setText("Installing Ookla Speedtest CLI via winget, please wait…")

        self._worker = _OoklaInstallWorker()
        self._worker.finished.connect(self._on_install_finished)
        self._worker.start()

    @pyqtSlot(bool, str)
    def _on_install_finished(self, success: bool, message: str) -> None:
        if success:
            self._msg.setText(
                "\u2713  Ookla CLI installed. <b>Rerun the test</b> for 1 Gbps+ speeds."
            )
            self._btn_install.hide()
            self._btn_manual.hide()
            self.installed.emit()
            # Auto-hide after 6 seconds
            from PyQt6.QtCore import QTimer
            _t = QTimer(self)
            _t.setSingleShot(True)
            _t.timeout.connect(self.hide)
            _t.start(6000)
        else:
            self._msg.setText(
                f"<span style='color:{_s.RED};'>\u26a0 Installation failed:</span> {message}"
            )
            self._btn_install.setEnabled(True)
            self._btn_install.setText("Retry")
