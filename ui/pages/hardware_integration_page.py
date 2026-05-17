"""
HardwareIntegrationPage — teach users to integrate any router / modem / AP
into NetSentinel via a simple Python plugin file.

Layout
──────
  Title + subtitle
  Scrollable body:
    Step 1  — Find your hardware's local API
    Step 2  — Write the Python integration script (template + Copy/Save)
    Step 3  — Test locally then import (.py file → validate → list)
    Step 4  — Share with the community (GitHub instructions)

Plugin interface contract
─────────────────────────
  Required at module level:
    HARDWARE_NAME: str
    HARDWARE_TYPE: str   ("router" | "modem" | "ap" | "switch" | "other")
    get_info()  -> dict
    get_status() -> dict

  Optional:
    get_clients() -> list[dict]

Scripts are stored as file paths in QSettings("NetSentinel","NetSentinel")
under the key  hardware/custom_scripts.
Testing runs the script in a child process so a buggy plugin cannot crash
the app.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt, QSettings, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
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
    CARD_HDR_BORDER,
    CARD_RADIUS,
    GREEN,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

_SETTINGS_KEY = "hardware/custom_scripts"

_TEMPLATE = '''\
"""
NetSentinel Hardware Integration Script
Hardware: <YOUR HARDWARE NAME>
Author:   <YOUR NAME>

Test this script standalone first:
    python this_file.py

Once the output looks correct, import it via the
Hardware Integration page in NetSentinel.

Tip: search "<your model> local API" or "<your model> REST API"
     to find community docs for your specific hardware.
"""

import json

# ── Metadata (required) ───────────────────────────────────────────────────────
HARDWARE_NAME = "My Router XYZ"     # displayed in the app
HARDWARE_TYPE = "router"            # router | modem | ap | switch | other
HARDWARE_IP   = "192.168.1.1"       # your device's LAN address
USERNAME      = "admin"
PASSWORD      = "admin"


# ── Required interface ────────────────────────────────────────────────────────

def get_info() -> dict:
    """Static metadata — called once when the script is first imported."""
    return {
        "name":         HARDWARE_NAME,
        "type":         HARDWARE_TYPE,
        "ip":           HARDWARE_IP,
        "manufacturer": "Brand Name",
        "model":        "XYZ-1000",
        "firmware":     "v1.0.0",       # fetch from device API or hardcode
    }


def get_status() -> dict:
    """Live status — called periodically when the page is visible.

    Connect to your device here using whatever method works:
      - HTTP REST (most modern routers)      - Form-based login + scrape (older routers)
      - SNMP (managed switches / APs)
      - SSH / Paramiko

    Return None for any field you cannot yet populate.
    """
    # ── Example: HTTP REST ────────────────────────────────────────────────────
    # import requests
    # session = requests.Session()
    # session.post(f"http://{HARDWARE_IP}/login",
    #              data={"username": USERNAME, "password": PASSWORD}, timeout=5)
    # data = session.get(f"http://{HARDWARE_IP}/api/status", timeout=5).json()

    return {
        "wan_ip":            None,   # str   — public WAN IP
        "uptime_sec":        None,   # int   — device uptime in seconds
        "download_mbps":     None,   # float — current download throughput
        "upload_mbps":       None,   # float — current upload throughput
        "signal_dbm":        None,   # float — RF signal level (modem / AP)
        "connected_clients": [],     # populated by get_clients() or inline here
        "extra":             {},     # any additional fields you want visible
    }


# ── Optional interface ────────────────────────────────────────────────────────

def get_clients() -> list:
    """Currently connected devices — optional but recommended.

    Each item should be a dict with at least:
        ip, mac, hostname   (any value can be None if unknown)
    """
    return [
        # {"ip": "192.168.1.10", "mac": "aa:bb:cc:dd:ee:ff", "hostname": "mylaptop"},
    ]


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Hardware Info ===")
    print(json.dumps(get_info(), indent=2, default=str))
    print("\\n=== Live Status ===")
    print(json.dumps(get_status(), indent=2, default=str))
    print("\\n=== Clients ===")
    print(json.dumps(get_clients(), indent=2, default=str))
'''


# ── Worker — runs the user script in a subprocess ─────────────────────────────

class _TestWorker(QThread):
    done = pyqtSignal(str, bool)   # (output_text, success)

    def __init__(self, script_path: str) -> None:
        super().__init__()
        self._path = script_path

    def run(self) -> None:
        try:
            result = subprocess.run(
                [sys.executable, self._path],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                self.done.emit(result.stdout or "(no output)", True)
            else:
                out = (result.stderr or result.stdout or "Script exited with an error.").strip()
                self.done.emit(out, False)
        except subprocess.TimeoutExpired:
            self.done.emit("Timed out after 15 seconds — check for blocking network calls.", False)
        except Exception as exc:
            self.done.emit(str(exc), False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _btn(label: str, accent: bool = False) -> QPushButton:
    b = QPushButton(label)
    b.setFixedHeight(28)
    b.setFont(QFont("Segoe UI", 9))
    if accent:
        b.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#fff; border:none;"
            f" border-radius:3px; padding:0 12px; }}"
            f"QPushButton:hover {{ background:{ACCENT_LITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; }}"
        )
    else:
        b.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:0 10px; }}"
            f"QPushButton:hover {{ background:{BORDER}; }}"
        )
    return b


def _step_card(number: int, title: str) -> tuple[QWidget, QVBoxLayout]:
    """Numbered step card — returns (frame, inner_layout)."""
    frame = QFrame()
    frame.setStyleSheet(
        f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
        f" border-radius:{CARD_RADIUS}; }}"
    )
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    hdr = QWidget()
    hdr.setStyleSheet(f"background:{BG_CARD}; border-bottom:1px solid {CARD_HDR_BORDER};")
    hdr_lay = QHBoxLayout(hdr)
    hdr_lay.setContentsMargins(12, 8, 12, 8)
    hdr_lay.setSpacing(10)

    badge = QLabel(str(number))
    badge.setFixedSize(22, 22)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
    badge.setStyleSheet(
        f"background:{ACCENT}; color:#fff; border-radius:11px; border:none;"
    )

    title_lbl = QLabel(title)
    title_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
    title_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; border:none; background:transparent;")

    hdr_lay.addWidget(badge)
    hdr_lay.addWidget(title_lbl)
    hdr_lay.addStretch()
    outer.addWidget(hdr)

    body = QWidget()
    body.setStyleSheet(f"background:{BG_CARD};")
    body_lay = QVBoxLayout(body)
    body_lay.setContentsMargins(14, 10, 14, 12)
    body_lay.setSpacing(8)
    outer.addWidget(body)

    return frame, body_lay


def _para(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
    return lbl


def _sub_header(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
    lbl.setStyleSheet(
        f"color:{TEXT_PRIMARY}; border:none;"
        f" border-bottom:1px solid {BORDER}; padding-bottom:3px; margin-top:2px;"
    )
    return lbl


def _copy_text(btn: QPushButton, text: str) -> None:
    QApplication.clipboard().setText(text)
    orig = btn.text()
    btn.setText("✓  Copied!")
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(2000, lambda: btn.setText(orig))


def _code_chip(code: str) -> QWidget:
    """Monospace inline snippet with a Copy button — used for search strings."""
    frame = QFrame()
    frame.setStyleSheet(
        f"QFrame {{ background:{BG_DARK}; border:1px solid {BORDER}; border-radius:3px; }}"
    )
    row = QHBoxLayout(frame)
    row.setContentsMargins(8, 4, 6, 4)
    row.setSpacing(8)
    lbl = QLabel(code)
    lbl.setFont(QFont("Consolas", 8))
    lbl.setStyleSheet(f"color:{ACCENT}; border:none; background:transparent;")
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    copy_btn = _btn("⎘")
    copy_btn.setFixedSize(24, 20)
    copy_btn.setToolTip("Copy to clipboard")
    copy_btn.clicked.connect(lambda: _copy_text(copy_btn, code))
    row.addWidget(lbl, 1)
    row.addWidget(copy_btn)
    return frame


def _prompt_block(label: str, text: str) -> QWidget:
    """Labeled multi-line prompt block with a Copy button — used for AI prompts."""
    frame = QFrame()
    frame.setStyleSheet(
        f"QFrame {{ background:{BG_DARK}; border:1px solid {BORDER}; border-radius:4px; }}"
    )
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(10, 6, 10, 8)
    outer.setSpacing(4)

    hdr = QHBoxLayout()
    hdr.setContentsMargins(0, 0, 0, 0)
    lbl_w = QLabel(label)
    lbl_w.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
    lbl_w.setStyleSheet(f"color:{AMBER}; border:none; background:transparent;")
    copy_btn = _btn("⎘  Copy prompt")
    copy_btn.setFixedHeight(20)
    copy_btn.clicked.connect(lambda: _copy_text(copy_btn, text))
    hdr.addWidget(lbl_w)
    hdr.addStretch()
    hdr.addWidget(copy_btn)
    outer.addLayout(hdr)

    body = QLabel(text)
    body.setFont(QFont("Consolas", 8))
    body.setWordWrap(True)
    body.setStyleSheet(
        f"color:{TEXT_SECONDARY}; font-size:9px; border:none; background:transparent;"
    )
    body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    outer.addWidget(body)
    return frame


def _validate_script(path: str) -> tuple[bool, str, dict]:
    """AST-validate the script without executing it.

    Returns (ok, message, metadata) where metadata has 'name' and 'type'
    when ok is True.
    """
    try:
        source = Path(path).read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return False, f"Syntax error: {exc}", {}
    except Exception as exc:
        return False, str(exc), {}

    top_names: dict[str, object] = {}
    func_names: set[str] = set()

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if isinstance(node.value, ast.Constant):
                        top_names[target.id] = node.value.value
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_names.add(node.name)

    required_vars  = {"HARDWARE_NAME", "HARDWARE_TYPE"}
    required_funcs = {"get_info", "get_status"}
    missing = (required_vars | required_funcs) - (set(top_names) | func_names)
    if missing:
        return False, f"Missing: {', '.join(sorted(missing))}", {}

    return True, "OK", {
        "name": str(top_names.get("HARDWARE_NAME", Path(path).stem)),
        "type": str(top_names.get("HARDWARE_TYPE", "unknown")),
    }


def _load_paths() -> list[str]:
    s = QSettings("NetSentinel", "NetSentinel")
    raw = s.value(_SETTINGS_KEY, [])
    if isinstance(raw, str):
        raw = [raw]
    return [p for p in (raw or []) if p]


def _save_paths(paths: list[str]) -> None:
    s = QSettings("NetSentinel", "NetSentinel")
    s.setValue(_SETTINGS_KEY, paths)


# ── Main page ─────────────────────────────────────────────────────────────────

class HardwareIntegrationPage(QWidget):
    """Teach, scaffold, and import custom hardware integration scripts."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._test_worker: Optional[_TestWorker] = None
        self._build_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 8)
        root.setSpacing(6)

        # Title
        title = QLabel("Integrate Any Hardware")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY};")
        sub = QLabel(
            "NetSentinel works with any router, modem, or access point — "
            "as long as you can write a small Python script that talks to it. "
            "Follow the four steps below to write, test, and load your integration. "
            "Shared scripts become part of the main product for everyone."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
        root.addWidget(title)
        root.addWidget(sub)

        # Scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        body = QWidget()
        body.setStyleSheet(f"background:{BG_DARK};")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 4, 0, 8)
        body_lay.setSpacing(10)

        body_lay.addWidget(self._build_step1())
        body_lay.addWidget(self._build_step2())
        body_lay.addWidget(self._build_step3())
        body_lay.addWidget(self._build_step4())
        body_lay.addStretch()

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    def _build_step1(self) -> QWidget:
        frame, lay = _step_card(1, "Find your hardware's local API")

        lay.addWidget(_para(
            "You do not need to be a programmer to do this — an AI can write almost "
            "all the code for you. Your job is to find out HOW your specific hardware "
            "exposes data, then hand that information to the AI. "
            "Work through the three sub-steps below in order."
        ))

        # ── 1a: Search GitHub ──────────────────────────────────────────────────
        lay.addWidget(_sub_header("1a  Search GitHub for an existing implementation"))
        lay.addWidget(_para(
            "Someone has often already written a Python script for your hardware. "
            "Go to github.com and paste one of these search strings into the search box. "
            "Replace 'Brand' and 'Model' with your own hardware name:"
        ))
        searches = [
            '"Brand Model" python router',
            '"Brand Model" python api',
            '"Brand" router python script',
            '"Brand" modem python library',
        ]
        for s in searches:
            lay.addWidget(_code_chip(s))

        lay.addWidget(_para(
            "Also check these specific places — they cover hundreds of devices:"
        ))
        repos = [
            ("Home Assistant integrations",
             "github.com/home-assistant/core/tree/dev/homeassistant/components  "
             "Search your brand name in the folder list. Each folder is a ready-made "
             "Python integration you can learn from or copy."),
            ("Home Assistant custom components (HACS)",
             "github.com/hacs/integration  —  then search 'hacs [Brand]' on Google. "
             "HACS has thousands of community-built integrations for consumer hardware."),
            ("OpenWrt wiki",
             "wiki.openwrt.org  —  if your router runs OpenWrt or a similar firmware, "
             "the LuCI API is documented there. Search 'openwrt luci api python'."),
            ("RouterSploit (read-only reference)",
             "github.com/threat9/routersploit  —  contains login/auth code for many "
             "router brands. Use as a reference for authentication patterns only."),
        ]
        for name, desc in repos:
            row = QHBoxLayout()
            row.setSpacing(8)
            row.setContentsMargins(0, 0, 0, 0)
            dot = QLabel("›")
            dot.setStyleSheet(f"color:{GREEN}; font-size:13px; font-weight:bold;")
            dot.setFixedWidth(12)
            txt = QLabel(f"<b style='color:{TEXT_PRIMARY};'>{name}</b>  "
                         f"<span style='color:{TEXT_SECONDARY};font-size:10px;'>{desc}</span>")
            txt.setWordWrap(True)
            txt.setTextFormat(Qt.TextFormat.RichText)
            row.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
            row.addWidget(txt)
            lay.addLayout(row)

        # ── 1b: Ask AI ────────────────────────────────────────────────────────
        lay.addWidget(_sub_header("1b  Ask an AI to write the script for you"))
        lay.addWidget(_para(
            "Claude, ChatGPT, and Gemini can write the full Python script if you give "
            "them the right information. Copy one of the prompts below, fill in your "
            "hardware details, and paste it into any AI chat:"
        ))

        lay.addWidget(_prompt_block(
            "PROMPT A — General (start here if you know nothing else)",
            "I want to write a Python script that reads live data from my [Brand] [Model] "
            "router/modem. The admin panel is at http://192.168.1.1 "
            "(adjust if yours is different). Login: username 'admin', password 'admin' "
            "(replace with your real credentials).\n\n"
            "Please:\n"
            "1. Find out if this router has a local JSON REST API or requires HTML scraping\n"
            "2. Write a Python script using the requests library that logs in and returns:\n"
            "   - WAN IP address\n"
            "   - Uptime (seconds or formatted string)\n"
            "   - List of connected clients (name, IP, MAC address)\n"
            "   - Download and upload speed if available\n"
            "3. Add a main block at the bottom that prints all results as JSON\n"
            "4. Tell me which packages to install with pip before running the script",
        ))

        lay.addWidget(_prompt_block(
            "PROMPT B — From a cURL command (best results, use after step 1c below)",
            "I captured this API call from my router admin panel using browser dev tools "
            "(F12 -> Network tab -> right-click a request -> Copy as cURL). "
            "Convert it to a Python function using the requests library.\n\n"
            "[Paste your cURL command here]\n\n"
            "Then wrap the result in the NetSentinel plugin format:\n"
            "- HARDWARE_NAME = 'Brand Model'\n"
            "- HARDWARE_TYPE = 'router'\n"
            "- def get_info() -> dict  (static metadata)\n"
            "- def get_status() -> dict  (live data)\n"
            "- def get_clients() -> list  (connected devices)\n"
            "- if __name__ == '__main__': print all results as JSON",
        ))

        lay.addWidget(_prompt_block(
            "PROMPT C — Fix a broken script",
            "I am writing a Python script to read data from my [Brand] [Model] router "
            "but it is not working. Here is my script and the error:\n\n"
            "[Paste your script]\n\n"
            "Error message:\n"
            "[Paste the exact error text]\n\n"
            "Router admin panel: http://192.168.1.1\n"
            "Login: username='admin', password='admin'\n\n"
            "Please fix the script and explain what was wrong.",
        ))

        # ── 1c: Spy on your own router ────────────────────────────────────────
        lay.addWidget(_sub_header("1c  Spy on your own router with browser dev tools"))
        lay.addWidget(_para(
            "If searches turn up nothing, you can discover the API yourself in about "
            "5 minutes. This gives you the exact URL and data format to hand to an AI:"
        ))
        steps = [
            ("Open your router admin panel", "Type your router IP into a browser address bar. "
             "Usually 192.168.1.1, 192.168.0.1, or 10.0.0.1. Log in normally."),
            ("Open dev tools and go to the Network tab",
             "Press F12 (Windows/Linux) or Cmd+Option+I (Mac). Click the 'Network' tab. "
             "Check the 'Fetch/XHR' filter if available — this shows only API calls, not images."),
            ("Reload the page", "Press F5 while dev tools is open. You will see a list of "
             "network requests appear. Click through them and look at the ones whose "
             "Response tab shows JSON data — that is the API."),
            ("Copy the request as cURL",
             "Right-click any interesting request -> 'Copy' -> 'Copy as cURL'. "
             "Paste it directly into Prompt B above and the AI will convert it to Python."),
            ("Check the login request",
             "Reload the page from the login screen to capture the login request too. "
             "This is the POST request with your username and password — the AI needs it "
             "to handle authentication in the script."),
        ]
        for i, (title, desc) in enumerate(steps, 1):
            row = QHBoxLayout()
            row.setSpacing(8)
            row.setContentsMargins(0, 0, 0, 0)
            num = QLabel(str(i))
            num.setFixedSize(18, 18)
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            num.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            num.setStyleSheet(
                f"background:{BG_CARD}; color:{TEXT_SECONDARY};"
                f" border:1px solid {BORDER}; border-radius:9px;"
            )
            txt = QLabel(f"<b style='color:{TEXT_PRIMARY};'>{title}</b>  "
                         f"<span style='color:{TEXT_SECONDARY};font-size:10px;'>{desc}</span>")
            txt.setWordWrap(True)
            txt.setTextFormat(Qt.TextFormat.RichText)
            row.addWidget(num, 0, Qt.AlignmentFlag.AlignTop)
            row.addWidget(txt)
            lay.addLayout(row)

        return frame

    def _build_step2(self) -> QWidget:
        frame, lay = _step_card(2, "Get the script written (template + AI shortcut)")

        lay.addWidget(_para(
            "You can either fill in the template yourself or hand it to an AI and let "
            "it do the work. Both paths end up with the same runnable .py file."
        ))

        lay.addWidget(_sub_header("Option A — Fill in the template yourself"))
        lay.addWidget(_para(
            "Save the template below as a .py file. Edit HARDWARE_IP, USERNAME, PASSWORD, "
            "and the body of get_status() with the API calls you found in Step 1. "
            "The if __name__ block at the bottom lets you test it standalone with: "
            "python your_file.py"
        ))

        self._template_edit = QTextEdit()
        self._template_edit.setReadOnly(True)
        self._template_edit.setPlainText(_TEMPLATE)
        self._template_edit.setFont(QFont("Consolas", 8))
        self._template_edit.setFixedHeight(270)
        self._template_edit.setStyleSheet(
            f"QTextEdit {{ background:{BG_DARK}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:4px;"
            f" font-family:Consolas,monospace; }}"
        )
        lay.addWidget(self._template_edit)

        btn_row = QHBoxLayout()
        btn_copy = _btn("⎘  Copy template")
        btn_save = _btn("💾  Save template as .py…")
        btn_copy.clicked.connect(self._on_copy_template)
        btn_save.clicked.connect(self._on_save_template)
        btn_row.addWidget(btn_copy)
        btn_row.addWidget(btn_save)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        lay.addWidget(_sub_header("Option B — Let an AI fill it in for you (recommended)"))
        lay.addWidget(_para(
            "Copy the prompt below into any AI chat (Claude, ChatGPT, Gemini). "
            "Replace the placeholders, paste the template when asked, and the AI will "
            "return a completed script you can run immediately:"
        ))
        lay.addWidget(_prompt_block(
            "PROMPT — Ask AI to complete the template",
            "I want to integrate my [Brand] [Model] router/modem into a monitoring app. "
            "I have a Python plugin template that needs the following filled in:\n\n"
            "Hardware details:\n"
            "- Admin panel URL: http://192.168.1.1  (replace with yours)\n"
            "- Username: admin  (replace with yours)\n"
            "- Password: admin  (replace with yours)\n\n"
            "Here is the template — please complete get_info() and get_status() "
            "using the real API or web scraping for my specific hardware. "
            "Add any required pip install commands as a comment at the top.\n\n"
            "[Paste the template here — use the Copy template button above]",
        ))
        return frame

    def _build_step3(self) -> QWidget:
        frame, lay = _step_card(3, "Test locally, then import into NetSentinel")
        lay.addWidget(_para(
            "Once your script prints correct data when run standalone, import it here. "
            "NetSentinel validates the interface (HARDWARE_NAME, HARDWARE_TYPE, "
            "get_info, get_status) without executing the script. Press Test to run it "
            "in a safe sandbox and see the output."
        ))

        import_row = QHBoxLayout()
        btn_browse = _btn("📂  Browse for script (.py)…", accent=True)
        btn_browse.clicked.connect(self._on_browse)
        import_row.addWidget(btn_browse)
        import_row.addStretch()
        lay.addLayout(import_row)

        # Status label (shown briefly after import attempt)
        self._import_status = QLabel("")
        self._import_status.setStyleSheet(f"font-size:10px; color:{TEXT_MUTED};")
        lay.addWidget(self._import_status)

        # Container for the imported scripts list (rebuilt on each import/remove)
        self._scripts_container = QWidget()
        self._scripts_container.setStyleSheet("background:transparent;")
        self._scripts_lay = QVBoxLayout(self._scripts_container)
        self._scripts_lay.setContentsMargins(0, 0, 0, 0)
        self._scripts_lay.setSpacing(6)
        lay.addWidget(self._scripts_container)

        self._refresh_scripts_list()
        return frame

    def _build_step4(self) -> QWidget:
        frame, lay = _step_card(4, "Share your script with the community")
        lay.addWidget(_para(
            "A script that works for you almost certainly works for everyone with "
            "the same hardware. Shared scripts are reviewed and merged into NetSentinel "
            "as first-class integrations — your hardware then appears in the app for "
            "all users automatically."
        ))

        how = [
            ("Open a GitHub Issue",
             "Go to github.com/ossianericson/netsentinel and open a new issue. "
             "Use the title format: [Hardware Plugin] Brand Model XYZ. "
             "Attach your .py file, describe what data get_status() returns, "
             "and note any pip dependencies."),
            ("What happens next",
             "The script is reviewed, tested on the same hardware model (or by "
             "community volunteers), and merged. It becomes part of the built-in "
             "hardware library and shows up in the Hardware Integration page for "
             "everyone — with your name as contributor."),
            ("No GitHub account?",
             "Email the script to the address in Help & Reference with subject "
             "[Hardware Plugin]. Include your hardware model and firmware version."),
        ]
        for title, desc in how:
            row = QHBoxLayout()
            row.setSpacing(8)
            row.setContentsMargins(0, 0, 0, 0)
            dot = QLabel("›")
            dot.setStyleSheet(f"color:{GREEN}; font-size:13px; font-weight:bold;")
            dot.setFixedWidth(12)
            txt = QLabel(f"<b style='color:{TEXT_PRIMARY};'>{title}</b>  "
                         f"<span style='color:{TEXT_SECONDARY};font-size:10px;'>{desc}</span>")
            txt.setWordWrap(True)
            txt.setTextFormat(Qt.TextFormat.RichText)
            row.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
            row.addWidget(txt)
            lay.addLayout(row)

        return frame

    # ── Script list ───────────────────────────────────────────────────────────

    def _refresh_scripts_list(self) -> None:
        # Clear existing rows
        while self._scripts_lay.count():
            item = self._scripts_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        paths = _load_paths()
        if not paths:
            empty = QLabel("No scripts imported yet.")
            empty.setStyleSheet(f"color:{TEXT_MUTED}; font-size:10px; padding:4px 0;")
            self._scripts_lay.addWidget(empty)
            return

        for path in paths:
            self._scripts_lay.addWidget(self._make_script_row(path))

    def _make_script_row(self, path: str) -> QWidget:
        ok, msg, meta = _validate_script(path)
        exists = Path(path).exists()

        row = QFrame()
        row.setStyleSheet(
            f"QFrame {{ background:{BG_DARK}; border:1px solid {BORDER};"
            f" border-radius:4px; }}"
        )
        lay = QHBoxLayout(row)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(8)

        # Status dot
        dot = QLabel("●")
        if not exists:
            dot.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px;")
        elif ok:
            dot.setStyleSheet(f"color:{GREEN}; font-size:11px;")
        else:
            dot.setStyleSheet(f"color:{AMBER}; font-size:11px;")
        dot.setFixedWidth(16)
        lay.addWidget(dot)

        # Name + path
        name   = meta.get("name", Path(path).stem) if ok else Path(path).stem
        hw_type = meta.get("type", "") if ok else ""
        type_str = f"  [{hw_type}]" if hw_type else ""
        info = QLabel(f"<b style='color:{TEXT_PRIMARY};'>{name}</b>"
                      f"<span style='color:{TEXT_MUTED};'>{type_str}</span>")
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setToolTip(path)
        sub_lbl = QLabel(path)
        sub_lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:9px;")
        sub_lbl.setToolTip(path)

        info_col = QVBoxLayout()
        info_col.setSpacing(1)
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.addWidget(info)
        info_col.addWidget(sub_lbl)
        lay.addLayout(info_col, 1)

        # Buttons
        if exists and ok:
            btn_test = _btn("▶  Test")
            btn_test.setToolTip("Run the script in a subprocess and show its output")
            btn_test.clicked.connect(lambda _, p=path, r=row: self._on_test(p, r))
            lay.addWidget(btn_test)

        btn_remove = _btn("✕")
        btn_remove.setFixedWidth(32)
        btn_remove.setToolTip("Remove this script from the list")
        btn_remove.clicked.connect(lambda _, p=path: self._on_remove(p))
        lay.addWidget(btn_remove)

        # Output area (hidden until Test is run)
        wrapper = QVBoxLayout()
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.setSpacing(4)

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        outer.addLayout(lay)

        output = QTextEdit()
        output.setReadOnly(True)
        output.setFont(QFont("Consolas", 8))
        output.setFixedHeight(120)
        output.setVisible(False)
        output.setStyleSheet(
            f"QTextEdit {{ background:{BG_DARK}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px;"
            f" font-family:Consolas,monospace; }}"
        )
        outer.addWidget(output)

        container = QFrame()
        container.setStyleSheet(
            f"QFrame {{ background:{BG_DARK}; border:1px solid {BORDER};"
            f" border-radius:4px; }}"
        )
        container.setLayout(outer)

        # Attach output reference so _on_test can find it
        row._output_edit = output    # type: ignore[attr-defined]
        row._outer_frame = container  # type: ignore[attr-defined]
        return container

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _on_copy_template(self) -> None:
        QApplication.clipboard().setText(_TEMPLATE)
        sender = self.sender()
        if sender:
            sender.setText("✓  Copied!")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(2000, lambda: sender.setText("⎘  Copy template"))

    def _on_save_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save integration template", "netsentinel_hardware.py",
            "Python files (*.py)",
        )
        if not path:
            return
        try:
            Path(path).write_text(_TEMPLATE, encoding="utf-8")
            self._import_status.setText(f"Template saved to {Path(path).name}")
            self._import_status.setStyleSheet(f"font-size:10px; color:{GREEN};")
        except Exception as exc:
            self._import_status.setText(f"Save failed: {exc}")
            self._import_status.setStyleSheet(f"font-size:10px; color:{RED};")

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select hardware integration script", "",
            "Python files (*.py)",
        )
        if not path:
            return

        ok, msg, meta = _validate_script(path)
        if not ok:
            self._import_status.setText(f"Validation failed: {msg}")
            self._import_status.setStyleSheet(f"font-size:10px; color:{AMBER};")
            return

        paths = _load_paths()
        if path not in paths:
            paths.append(path)
            _save_paths(paths)

        name = meta.get("name", Path(path).stem)
        self._import_status.setText(f"Imported '{name}' successfully.")
        self._import_status.setStyleSheet(f"font-size:10px; color:{GREEN};")
        self._refresh_scripts_list()

    def _on_remove(self, path: str) -> None:
        paths = [p for p in _load_paths() if p != path]
        _save_paths(paths)
        self._import_status.setText(f"Removed {Path(path).name}.")
        self._import_status.setStyleSheet(f"font-size:10px; color:{TEXT_MUTED};")
        self._refresh_scripts_list()

    def _on_test(self, path: str, row_frame) -> None:
        output: QTextEdit = row_frame._output_edit
        output.setPlainText("Running…")
        output.setVisible(True)

        if self._test_worker and self._test_worker.isRunning():
            self._test_worker.terminate()

        self._test_worker = _TestWorker(path)
        self._test_worker.done.connect(
            lambda text, ok, out=output: self._on_test_done(text, ok, out)
        )
        self._test_worker.start()

    def _on_test_done(self, text: str, success: bool, output: QTextEdit) -> None:
        output.setPlainText(text)
        color = TEXT_PRIMARY if success else AMBER
        output.setStyleSheet(
            f"QTextEdit {{ background:{BG_DARK}; color:{color};"
            f" border:1px solid {BORDER}; border-radius:3px;"
            f" font-family:Consolas,monospace; }}"
        )
