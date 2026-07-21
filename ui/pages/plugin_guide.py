"""
PluginGuide — collapsible "How to write a plugin script" guide widget.

Extracted from hardware_integration_page.py (S14-2) to keep that file
within the 780-line architecture budget.

Used by:
    HardwareIntegrationPage._guide_area  (instantiate once, toggle via .toggle())
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QScrollArea, QTextEdit, QVBoxLayout, QWidget
from PyQt6.QtGui import QFont

from ui.widgets.hub_card import (
    _TEMPLATE,
    _step_card,
    _para,
    _sub_header,
    _copy_text,
    _code_chip,
    _prompt_block,
    _btn,
)
from ui import styles as _s


class PluginGuide(QScrollArea):
    """Scrollable 4-step guide for writing hardware plugin scripts.

    Embed in a layout that is hidden by default; call :meth:`toggle` to
    show/hide.  The parent page controls the toggle button and its label.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea { border: none; }")

        body = QWidget()
        _s.themed_ss(body, "background:{BG_DARK};")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 4, 0, 8)
        lay.setSpacing(10)
        lay.addWidget(self._build_step1())
        lay.addWidget(self._build_step2())
        lay.addWidget(self._build_step3())
        lay.addWidget(self._build_step4())
        lay.addStretch()
        self.setWidget(body)

    # ── Step builders ─────────────────────────────────────────────────────────

    def _build_step1(self) -> QWidget:
        frame, lay = _step_card(1, "Find your hardware's local API")
        lay.addWidget(_para(
            "You do not need to be a programmer — an AI can write almost all "
            "the code for you. Your job is to find out HOW your specific hardware "
            "exposes data, then hand that to the AI."
        ))
        lay.addWidget(_sub_header("1a  Search GitHub for an existing implementation"))
        lay.addWidget(_para("Paste one of these search strings into github.com:"))
        for s in ['"Brand Model" python router', '"Brand Model" python api',
                  '"Brand" router python script', '"Brand" modem python library']:
            lay.addWidget(_code_chip(s))

        lay.addWidget(_sub_header("1b  Ask an AI to write the script for you"))
        lay.addWidget(_para(
            "Claude, ChatGPT, and Gemini can write the full Python script "
            "if you give them the right information."
        ))
        lay.addWidget(_prompt_block(
            "PROMPT A — General (start here)",
            "I want to write a NetSentinel hardware plugin that reads live data from my "
            "[Brand] [Model] router/modem. The admin panel is at http://192.168.1.1. "
            "Login: username 'admin', password 'admin'.\n\n"
            "Please:\n"
            "1. Find if this router has a local JSON REST API or requires HTML scraping\n"
            "2. Write a Python script using requests (with timeout=10 on every call) that "
            "logs in and returns WAN IP, Uptime, Connected clients (name, IP, MAC)\n"
            "3. Wrap it in the NetSentinel plugin format:\n"
            "   - Constants: HARDWARE_NAME (str), HARDWARE_TYPE (must be exactly one of: "
            "router, modem, ap, switch, other)\n"
            "   - Functions: get_info(), get_status(), and optionally get_clients() — none "
            "may take required positional arguments\n"
            "   - Read the password from the OS keychain via the `keyring` package "
            "(NetSentinel/hardware/<ip>), never hard-code it\n"
            "   - Catch every exception inside get_status()/get_clients() and return it as "
            "{\"extra\": {\"error\": \"PREFIX: message\"}} where PREFIX is AUTH: (wrong "
            "credentials), NET: (unreachable/timeout), DEPS: (missing pip package), or ERR: "
            "(anything else) — never let an exception propagate out of these functions\n"
            "4. Add a main block at the bottom that prints get_info()/get_status()/"
            "get_clients() as JSON\n"
            "5. Tell me which packages to install with pip",
        ))
        lay.addWidget(_prompt_block(
            "PROMPT B — From a cURL command (best results)",
            "I captured this API call from my router admin panel using browser dev tools "
            "(F12 → Network → right-click request → Copy as cURL). "
            "Convert it to a Python function using requests, with timeout=10 on every call.\n\n"
            "[Paste your cURL command here]\n\n"
            "Then wrap the result in the NetSentinel plugin format:\n"
            "- Constants: HARDWARE_NAME (str), HARDWARE_TYPE (exactly one of: router, modem, "
            "ap, switch, other)\n"
            "- Functions: get_info(), get_status(), optionally get_clients()\n"
            "- If the cURL command contains a password, move it to the OS keychain via the "
            "`keyring` package (NetSentinel/hardware/<ip>) instead of leaving it in the "
            "script — do not hard-code the captured credential\n"
            "- Read the device address from a `_NETSENTINEL_INSTANCE_IP` global if present, "
            "falling back to a HARDWARE_IP constant, so the plugin still works if I add a "
            "second device of the same type at a different IP\n"
            "- Catch every exception in get_status()/get_clients() and return it as "
            "{\"extra\": {\"error\": \"PREFIX: message\"}} — AUTH:/NET:/DEPS:/ERR: — never "
            "let an exception escape these functions\n"
            "- if __name__ == '__main__': print all results as JSON",
        ))
        lay.addWidget(_prompt_block(
            "PROMPT C — Debug an error",
            "This NetSentinel hardware plugin raises the following error:\n\n"
            "[Paste your plugin script here]\n\n"
            "[Paste the error message here]\n\n"
            "Fix it. Do not change the HARDWARE_NAME, HARDWARE_TYPE, get_info(), or "
            "get_status() signatures, and keep every exception classified with the "
            "AUTH:/NET:/DEPS:/ERR: prefix convention already used in the script.",
        ))

        lay.addWidget(_sub_header("1c  Spy on your own router with browser dev tools"))
        lay.addWidget(_para(
            "Open your router admin panel in a browser, press F12, go to the Network tab, "
            "reload the page, look for JSON responses, and right-click → Copy as cURL. "
            "Paste into Prompt B above."
        ))
        return frame

    def _build_step2(self) -> QWidget:
        frame, lay = _step_card(2, "Get the script written (template + AI)")
        lay.addWidget(_para(
            "Either fill in the template yourself or hand it to an AI."
        ))
        lay.addWidget(_sub_header("Template"))

        template_edit = QTextEdit()
        template_edit.setReadOnly(True)
        template_edit.setPlainText(_TEMPLATE)
        template_edit.setFont(QFont("Consolas", 8))
        template_edit.setFixedHeight(240)
        _s.themed_ss(template_edit, "QTextEdit {{ background:{BG_DARK}; color:{TEXT_PRIMARY};"
            " border:1px solid {BORDER}; border-radius:4px; }}")
        lay.addWidget(template_edit)

        from PyQt6.QtWidgets import QHBoxLayout
        btn_row = QHBoxLayout()
        btn_copy = _btn("⎘  Copy template")
        btn_save = _btn("💾  Save template as .py…")
        btn_copy.clicked.connect(lambda: _copy_text(btn_copy, _TEMPLATE))
        btn_save.clicked.connect(self._on_save_template)
        btn_row.addWidget(btn_copy)
        btn_row.addWidget(btn_save)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        lay.addWidget(_prompt_block(
            "PROMPT — Ask AI to complete the template",
            "I want to integrate my [Brand] [Model] router/modem into a monitoring app. "
            "I have a Python plugin template. Hardware details:\n"
            "- Admin panel URL: http://192.168.1.1\n"
            "- Username: admin  Password: admin\n\n"
            "Please complete get_info() and get_status() (and get_clients() if the API "
            "supports it) using the real API for my hardware. Keep every other part of the "
            "template exactly as-is: _load_password(), the _fmt_err() error-prefix helper, "
            "the try/except structure in get_status(), and the standalone-test / shim blocks "
            "at the bottom. Use requests with timeout=10 on every call.\n"
            "[Paste the template here]",
        ))
        return frame

    def _build_step3(self) -> QWidget:
        frame, lay = _step_card(3, "Test locally, then import via ＋ Add Integration above")
        lay.addWidget(_para(
            "Once your script prints correct data when run standalone "
            "(python your_file.py), click ＋ Add Integration at the top of this page. "
            "NetSentinel validates the interface, then runs the script and shows the result "
            "in the Hub above."
        ))
        return frame

    def _build_step4(self) -> QWidget:
        frame, lay = _step_card(4, "Share your script with the community")
        lay.addWidget(_para(
            "A script that works for you almost certainly works for everyone with "
            "the same hardware. Open a GitHub Issue at github.com/ossianericson/netsentinel "
            "with title: [Hardware Plugin] Brand Model XYZ. Attach your .py file."
        ))
        return frame

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _on_save_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save integration template", "netsentinel_hardware.py",
            "Python files (*.py)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        try:
            Path(path).write_text(_TEMPLATE, encoding="utf-8")
        except Exception:
            pass  # non-fatal
