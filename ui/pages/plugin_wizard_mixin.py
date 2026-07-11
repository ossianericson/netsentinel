"""
_PluginWizardMixin — plugin template wizard for HardwareIntegrationPage.

Extracted from hardware_integration_page.py (S14-2).
"""
from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ui.styles import (
    ACCENT,
    ACCENT_DARK,
    ACCENT_LITE,
    BG_CARD,
    BORDER,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WHITE,
)
from ui.widgets.hub_card import _TEMPLATE

log = logging.getLogger(__name__)


class _PluginWizardMixin:
    """Provides the 'New Plugin' template wizard for HardwareIntegrationPage."""

    def _on_create_plugin(self) -> None:
        """P3-2: Template wizard — generate a new plugin .py from user-supplied fields."""
        from modules.utils import get_app_data_dir as _gad

        _field_ss = (
            f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};"
            " border-radius:3px; padding:3px 6px; font-size:11px;"
        )

        dlg = QDialog(self)
        dlg.setWindowTitle("Create New Plugin")
        dlg.setMinimumWidth(480)

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(10)

        intro = QLabel(
            "Fill in the fields below and NetSentinel will generate a plugin "
            "template ready for you to complete with your hardware's API calls."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
        lay.addWidget(intro)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        name_edit = QLineEdit()
        name_edit.setStyleSheet(_field_ss)
        name_edit.setPlaceholderText("e.g. ASUS RT-AX88U")
        form.addRow("Hardware name *", name_edit)

        type_combo = QComboBox()
        type_combo.addItems(["router", "modem", "ap", "switch", "other"])
        type_combo.setStyleSheet(
            f"QComboBox {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:3px 6px; font-size:11px; }}"
            f"QComboBox:drop-down {{ border:none; }}"
        )
        form.addRow("Hardware type *", type_combo)

        ip_edit = QLineEdit()
        ip_edit.setStyleSheet(_field_ss)
        ip_edit.setPlaceholderText("e.g. 192.168.1.1")
        form.addRow("Default IP *", ip_edit)

        cred_edit = QLineEdit()
        cred_edit.setStyleSheet(_field_ss)
        cred_edit.setText("Password")
        form.addRow("Credential label", cred_edit)

        pypi_edit = QLineEdit()
        pypi_edit.setStyleSheet(_field_ss)
        pypi_edit.setPlaceholderText("e.g. fritzconnection  (leave blank if none)")
        form.addRow("PyPI package", pypi_edit)

        author_edit = QLineEdit()
        author_edit.setStyleSheet(_field_ss)
        author_edit.setPlaceholderText("optional — shown in plugin catalog")
        form.addRow("Author", author_edit)

        lay.addLayout(form)

        try:
            dest_dir = _gad() / "plugins"
        except Exception:
            dest_dir = Path.home() / ".netsentinel" / "plugins"
        path_lbl = QLabel("")
        path_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:9px; font-family:Consolas;"
        )
        path_lbl.setWordWrap(True)
        lay.addWidget(path_lbl)

        def _update_path_preview(*_):
            raw = name_edit.text().strip()
            slug = (
                raw.lower()
                .replace(" ", "_")
                .replace("-", "_")
                .replace("/", "_")
            )
            slug = "".join(c for c in slug if c.isalnum() or c == "_")
            slug = slug or "my_plugin"
            fname = f"{slug}_plugin.py"
            path_lbl.setText(f"Will be created at: {dest_dir / fname}")

        name_edit.textChanged.connect(_update_path_preview)
        _update_path_preview()

        status_lbl = QLabel("")
        status_lbl.setStyleSheet(f"color:{RED}; font-size:10px;")
        status_lbl.setVisible(False)
        lay.addWidget(status_lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_SECONDARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:5px 14px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)

        create_btn = QPushButton("Create Plugin")
        create_btn.setDefault(True)
        create_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:3px; padding:5px 18px; font-size:12px; font-weight:600; }}"
            f"QPushButton:hover {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
            f"QPushButton:disabled {{ background:{BORDER}; color:{TEXT_MUTED}; }}"
        )
        btn_row.addWidget(create_btn)
        lay.addLayout(btn_row)

        _created_path: list[str] = []

        def _on_create() -> None:
            hw_name    = name_edit.text().strip()
            hw_type    = type_combo.currentText()
            hw_ip      = ip_edit.text().strip()
            cred_label = cred_edit.text().strip() or "Password"
            pypi_pkg   = pypi_edit.text().strip()
            author     = author_edit.text().strip()

            if not hw_name:
                status_lbl.setText("Hardware name is required.")
                status_lbl.setVisible(True)
                return
            if not hw_ip:
                status_lbl.setText("Default IP is required.")
                status_lbl.setVisible(True)
                return

            slug = (
                hw_name.lower()
                .replace(" ", "_")
                .replace("-", "_")
                .replace("/", "_")
            )
            slug = "".join(c for c in slug if c.isalnum() or c == "_") or "my_plugin"
            fname = f"{slug}_plugin.py"

            content = _TEMPLATE
            content = content.replace(
                'Hardware: <YOUR HARDWARE NAME>', f'Hardware: {hw_name}'
            )
            content = content.replace(
                'Author:   <YOUR NAME>', f'Author:   {author or "Unknown"}'
            )
            content = content.replace(
                'HARDWARE_NAME = "My Router XYZ"     # displayed in the app',
                f'HARDWARE_NAME = "{hw_name}"',
            )
            content = content.replace(
                'HARDWARE_TYPE = "router"            # router | modem | ap | switch | other',
                f'HARDWARE_TYPE = "{hw_type}"',
            )
            content = content.replace(
                'HARDWARE_IP   = "192.168.1.1"       # your device\'s LAN address',
                f'HARDWARE_IP   = "{hw_ip}"',
            )

            extra_consts = ""
            if pypi_pkg:
                extra_consts += f'\nPYPI_PACKAGE    = "{pypi_pkg}"'
            extra_consts += f'\nCREDENTIAL_LABEL = "{cred_label}"'
            if extra_consts:
                content = content.replace(
                    '\n# ── Credentials',
                    extra_consts + '\n\n# ── Credentials',
                )

            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / fname
                dest.write_text(content, encoding="utf-8")
                _created_path.append(str(dest))
                dlg.accept()
            except Exception as exc:
                log.warning("Plugin template file creation failed: %s", exc)
                status_lbl.setText(
                    "Failed to create file — check that the destination folder is writable and try again."
                )
                status_lbl.setVisible(True)

        create_btn.clicked.connect(_on_create)

        if dlg.exec() != QDialog.DialogCode.Accepted or not _created_path:
            return

        created = _created_path[0]
        self._set_status(
            f"Plugin created: {Path(created).name}  "
            "— click ＋ Add Integration to import it.",
            error=False,
        )

        msg = QMessageBox(self)
        msg.setWindowTitle("Plugin Created")
        msg.setText(
            f"<b>{Path(created).name}</b> has been created.<br><br>"
            f"Path: <code>{created}</code><br><br>"
            "Open the file in your default editor to complete the API code, "
            "then click <b>＋ Add Integration</b> to import it."
        )
        msg.setTextFormat(Qt.TextFormat.RichText)
        open_btn = msg.addButton("Open in editor", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        msg.exec()
        if msg.clickedButton() == open_btn:
            import os as _os
            try:
                _os.startfile(created)  # type: ignore[attr-defined]
            except AttributeError:
                import subprocess
                subprocess.Popen(["xdg-open", created])  # noqa: S603
