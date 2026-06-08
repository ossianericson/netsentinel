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
from ui.styles import (
    ACCENT, ACCENT_DARK, BG_HOVER, BTN_DISABLED_BORDER, INFO_BOX_BG,
    INFO_BOX_BORDER, INFO_BOX_FG, RED, TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)

# Self-contained colours (no ui.styles import needed — banner is standalone)
_BLUE_BG   = INFO_BOX_BG
_BLUE_BDR  = INFO_BOX_BORDER
_BLUE_TEXT = INFO_BOX_FG
_LINK_CLR  = ACCENT
_BTN_BG    = ACCENT
_BTN_TEXT  = WHITE
_BTN_HOVER = ACCENT_DARK
_DIM_TEXT  = TEXT_SECONDARY


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
        self.setStyleSheet(
            f"QFrame#ooklaBanner {{"
            f"  background:{_BLUE_BG};"
            f"  border:1px solid {_BLUE_BDR};"
            f"  border-radius:3px;"
            f"}}"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(8)

        # Info icon + message
        icon = QLabel("\u2139")   # ℹ
        icon.setStyleSheet(f"color:{_LINK_CLR}; font-size:14px; background:transparent; border:none;")
        icon.setFixedWidth(16)

        self._msg = QLabel(
            "Install the <b>Ookla Speedtest CLI</b> to unlock 1 Gbps+ multi-connection tests."
        )
        self._msg.setStyleSheet(
            f"color:{_BLUE_TEXT}; font-size:11px; background:transparent; border:none;"
        )
        self._msg.setTextFormat(Qt.TextFormat.RichText)

        # "Install via winget" button
        self._btn_install = QPushButton("Install via winget")
        self._btn_install.setStyleSheet(
            f"QPushButton {{"
            f"  background:{_BTN_BG}; color:{_BTN_TEXT};"
            f"  border:none; border-radius:3px; padding:4px 12px; font-size:11px;"
            f"}}"
            f"QPushButton:hover {{ background:{_BTN_HOVER}; }}"
            f"QPushButton:disabled {{ background:{BTN_DISABLED_BORDER}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        self._btn_install.setFixedHeight(28)
        self._btn_install.clicked.connect(self._on_install_clicked)

        # "Manual install" link
        self._btn_manual = QLabel(
            '<a href="https://www.speedtest.net/apps/cli" style="color:ACCENT;">Manual install</a>'
        )
        self._btn_manual.setStyleSheet("background:transparent; border:none; font-size:11px;")
        self._btn_manual.setOpenExternalLinks(True)
        self._btn_manual.setTextFormat(Qt.TextFormat.RichText)

        # Dismiss button
        self._btn_dismiss = QPushButton("\u00d7")   # ×
        self._btn_dismiss.setStyleSheet(
            f"QPushButton {{"
            f"  background:transparent; color:{_DIM_TEXT};"
            f"  border:none; font-size:16px; padding:0 4px;"
            f"}}"
            f"QPushButton:hover {{ color:{_BLUE_TEXT}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{_DIM_TEXT}; }}"
        )
        self._btn_dismiss.setFixedSize(24, 24)
        self._btn_dismiss.setToolTip("Dismiss")
        self._btn_dismiss.clicked.connect(self.hide)

        lay.addWidget(icon)
        lay.addWidget(self._msg, stretch=1)
        lay.addWidget(self._btn_install)
        lay.addWidget(self._btn_manual)
        lay.addWidget(self._btn_dismiss)

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
            QTimer.singleShot(6000, self.hide)
        else:
            self._msg.setText(
                f"<span style='color:{RED};'>\u26a0 Installation failed:</span> {message}"
            )
            self._btn_install.setEnabled(True)
            self._btn_install.setText("Retry")
