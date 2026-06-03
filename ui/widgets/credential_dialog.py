"""
Credential dialog and unsigned-plugin warning for hardware plugin registration.

Standalone functions — no dependency on HardwareIntegrationPage state.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT,
    ACCENT_DARK,
    ACCENT_LITE,
    AMBER,
    BG_CARD,
    BG_DARK,
    BORDER,
    GREEN,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WHITE,
)
from ui.widgets.hub_card import _PluginConnectionTester, _instance_id


def show_credential_dialog(
    parent: QWidget,
    name: str,
    default_ip: str,
    cred_label: str,
    plugin_path: str = "",
) -> tuple[bool, str]:
    """Credential dialog with live connection test.

    Shows IP + password fields.  The primary button ("Test & Add") runs a
    live connection test in a background thread before accepting.  The dialog
    only closes with Accepted after a successful test, so the plugin is never
    registered when it cannot connect.

    Returns (accepted, confirmed_ip).  confirmed_ip is the IP the user
    actually entered (may differ from default_ip), or "" on cancel.
    """
    # Use the active top-level window so the dialog centers on the screen
    # rather than relative to the page widget (which may be inside a scroll area,
    # causing the dialog to appear partially off-screen).
    from PyQt6.QtWidgets import QApplication as _QApp
    _top = _QApp.activeWindow() or parent
    dlg = QDialog(_top)
    dlg.setWindowTitle(f"Set up {name}")
    dlg.setMinimumWidth(400)

    _field_ss = (
        f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};"
        " border-radius:3px; padding:3px 6px; font-size:12px;"
    )
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(16, 16, 16, 12)
    lay.setSpacing(10)

    note = QLabel(f"Enter the connection details for <b>{name}</b>.")
    note.setTextFormat(Qt.TextFormat.RichText)
    note.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:12px;")
    note.setWordWrap(True)
    lay.addWidget(note)

    form = QFormLayout()
    form.setSpacing(6)

    ip_edit = QLineEdit(default_ip)
    ip_edit.setStyleSheet(_field_ss)
    ip_edit.setPlaceholderText("e.g. 192.168.1.1")
    form.addRow("IP Address", ip_edit)

    pw_edit = QLineEdit()
    pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
    pw_edit.setStyleSheet(_field_ss)
    pw_edit.setPlaceholderText(f"Device {cred_label.lower()}")
    form.addRow(cred_label, pw_edit)
    lay.addLayout(form)

    keyring_note = QLabel("\U0001f512  Password saved to OS keychain — never written to disk")
    keyring_note.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:9px;")
    lay.addWidget(keyring_note)

    status_lbl = QLabel("")
    status_lbl.setWordWrap(True)
    status_lbl.setVisible(False)
    status_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY}; padding:4px 0;")
    lay.addWidget(status_lbl)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(8)
    btn_row.addStretch()

    cancel_btn = QPushButton("Cancel")
    cancel_btn.setStyleSheet(
        f"QPushButton {{ background:transparent; color:{TEXT_SECONDARY}; border:1px solid {BORDER};"
        f" border-radius:3px; padding:5px 14px; font-size:12px; }}"
        f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
        f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
    )
    cancel_btn.clicked.connect(dlg.reject)
    btn_row.addWidget(cancel_btn)

    test_btn = QPushButton("Test & Add")
    test_btn.setDefault(True)
    test_btn.setStyleSheet(
        f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
        f" border-radius:3px; padding:5px 18px; font-size:12px; font-weight:600; }}"
        f"QPushButton:hover {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
        f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
        f"QPushButton:disabled {{ background:{BORDER}; color:{TEXT_MUTED}; }}"
    )
    btn_row.addWidget(test_btn)
    lay.addLayout(btn_row)

    skip_btn = QPushButton("Add Without Testing")
    skip_btn.setVisible(False)
    skip_btn.setToolTip(
        "Device unreachable — save credentials now and add.\n"
        "The card will show an error until the device comes online."
    )
    skip_btn.setStyleSheet(
        f"QPushButton {{ background:transparent; color:{TEXT_SECONDARY}; border:none;"
        f" font-size:10px; padding:2px 0; text-decoration:underline; }}"
        f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
        f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
    )
    lay.addWidget(skip_btn, alignment=Qt.AlignmentFlag.AlignRight)

    _tester: list[_PluginConnectionTester] = []

    def _set_status(msg: str, color: str) -> None:
        status_lbl.setText(msg)
        status_lbl.setStyleSheet(
            f"font-size:11px; color:{color}; padding:4px 0; background:transparent;"
        )
        status_lbl.setVisible(True)

    def _save_and_accept() -> None:
        ip = ip_edit.text().strip()
        pw = pw_edit.text().strip()
        if pw:
            try:
                import keyring as _kr
                iid = _instance_id(plugin_path or ip, ip)
                _kr.set_password("NetSentinel/plugin", iid, pw)
                _kr.set_password("NetSentinel/hardware", ip, pw)
            except Exception:
                pass
        dlg.accept()

    def _run_test() -> None:
        ip = ip_edit.text().strip()
        pw = pw_edit.text().strip()
        if not ip:
            _set_status("Enter the device IP address.", RED)
            return
        if not pw:
            _set_status(f"Enter the device {cred_label.lower()} to continue.", RED)
            pw_edit.setFocus()
            return

        test_btn.setEnabled(False)
        cancel_btn.setEnabled(False)
        ip_edit.setEnabled(False)
        pw_edit.setEnabled(False)
        skip_btn.setVisible(False)
        _set_status("Testing connection…  ⏳", TEXT_SECONDARY)

        tester = _PluginConnectionTester(plugin_path or "", ip, pw, parent=dlg)
        _tester.append(tester)

        def _on_success(result: dict) -> None:
            _set_status("✓  Connected successfully — adding integration.", GREEN)
            try:
                import keyring as _kr
                iid = _instance_id(plugin_path or ip, ip)
                _kr.set_password("NetSentinel/plugin", iid, pw)
                _kr.set_password("NetSentinel/hardware", ip, pw)
            except Exception:
                pass
            QTimer.singleShot(600, dlg.accept)

        def _on_failure(msg: str) -> None:
            try:
                import keyring as _kr
                _kr.delete_password("NetSentinel/hardware", ip)
            except Exception:
                pass
            _set_status(f"✗  {msg}", RED)
            test_btn.setEnabled(True)
            cancel_btn.setEnabled(True)
            ip_edit.setEnabled(True)
            pw_edit.setEnabled(True)
            test_btn.setText("Retry")
            skip_btn.setVisible(True)

        tester.success.connect(_on_success, Qt.ConnectionType.QueuedConnection)
        tester.failure.connect(_on_failure, Qt.ConnectionType.QueuedConnection)
        tester.start()

    skip_btn.clicked.connect(_save_and_accept)
    test_btn.clicked.connect(_run_test)
    pw_edit.returnPressed.connect(_run_test)

    result = dlg.exec()
    confirmed_ip = ip_edit.text().strip()

    for t in _tester:
        if t.isRunning():
            t.wait(500)

    accepted = result == QDialog.DialogCode.Accepted
    return accepted, (confirmed_ip if accepted else "")


def show_unsigned_warning(parent: QWidget, path: str) -> bool:
    """One-time consent dialog shown before adding any non-bundled plugin.

    Returns True when the user clicks 'I understand - Add anyway'.
    """
    try:
        sz = Path(path).stat().st_size
        sz_str = f"{sz:,} bytes"
    except Exception:
        sz_str = "unknown size"

    dlg = QDialog(parent)
    dlg.setWindowTitle("Untrusted Plugin")
    dlg.setMinimumWidth(460)

    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(16, 16, 16, 12)
    lay.setSpacing(10)

    warn_lbl = QLabel(
        "<b>⚠  This plugin runs arbitrary Python code on your machine.</b><br><br>"
        "Only add scripts from sources you trust — for example, scripts you wrote "
        "yourself or obtained from a known community repository.<br><br>"
        "You will <b>not</b> see this warning again for this exact file."
    )
    warn_lbl.setTextFormat(Qt.TextFormat.RichText)
    warn_lbl.setWordWrap(True)
    warn_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:11px;")
    lay.addWidget(warn_lbl)

    path_lbl = QLabel(f"<b>Path:</b> {path}<br><b>Size:</b> {sz_str}")
    path_lbl.setTextFormat(Qt.TextFormat.RichText)
    path_lbl.setWordWrap(True)
    path_lbl.setStyleSheet(
        f"background:{BG_DARK}; color:{TEXT_SECONDARY}; font-size:10px; font-family:Consolas;"
        f" border:1px solid {BORDER}; border-radius:3px; padding:6px;"
    )
    lay.addWidget(path_lbl)

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

    proceed_btn = QPushButton("I understand — Add anyway")
    proceed_btn.setStyleSheet(
        f"QPushButton {{ background:{AMBER}; color:{TEXT_PRIMARY}; border:none;"
        f" border-radius:3px; padding:5px 16px; font-weight:600; }}"
        f"QPushButton:hover {{ background:{AMBER}; color:{TEXT_PRIMARY}; }}"
        f"QPushButton:pressed {{ background:{AMBER}; color:{TEXT_PRIMARY}; }}"
    )
    proceed_btn.clicked.connect(dlg.accept)
    btn_row.addWidget(proceed_btn)
    lay.addLayout(btn_row)

    return dlg.exec() == QDialog.DialogCode.Accepted
