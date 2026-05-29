"""
HardwareIntegrationPage — Hardware Hub

Primary view: live status cards for every imported hardware plugin.
Each card auto-refreshes on a configurable interval, shows key metrics,
and expands to a full signal/topology detail panel (v2.1).

Secondary view: collapsible "How to write a plugin" guide (steps 1-4).

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
"""

from __future__ import annotations

import ast
import collections
import hashlib
import json
import time
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QFileSystemWatcher, QSettings, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QCursor, QFont, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import QProcess

from workers.plugin_polling_worker import PluginPollingWorker
from ui.styles import (
    ACCENT,
    ACCENT_DARK,
    ACCENT_LITE,
    AMBER,
    BG_ALT_ROW,
    BG_CARD,
    BG_DARK,
    BG_HOVER,
    BORDER,
    CARD_HDR_BORDER,
    CARD_RADIUS,
    GREEN,
    RED,
    TABLE_ROW_BORDER,
    TABLE_SEL,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TH_BG,
    TH_BORDER,
    TH_TEXT,
    WHITE,
)

_SETTINGS_KEY      = "hardware/custom_scripts"
_SETTINGS_RESULT   = "hardware/last_result/{}"   # .format(path_hash)
_SETTINGS_INSTANCES = "hardware/instances"        # JSON list of instance dicts
_SETTINGS_CONFIG   = "hardware/config/{}"         # .format(instance_id) — CONFIG_SCHEMA values


def _find_python_exe() -> str:
    """Return a usable Python interpreter path.

    In development sys.executable is already python.exe.  In a frozen
    (PyInstaller onefile) bundle sys.executable is the .exe itself, so we
    search PATH for python3 / python.
    """
    import sys as _sys
    if not getattr(_sys, "frozen", False):
        return _sys.executable
    import shutil
    for candidate in ("python3", "python", "py"):
        found = shutil.which(candidate)
        if found:
            return found
    return "python"

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
import sys

# ── Metadata (required) ───────────────────────────────────────────────────────
HARDWARE_NAME = "My Router XYZ"     # displayed in the app
HARDWARE_TYPE = "router"            # router | modem | ap | switch | other
HARDWARE_IP   = "192.168.1.1"       # your device\'s LAN address
USERNAME      = "admin"


# ── Credentials (read from OS keychain — never hard-code passwords) ───────────

def _load_password() -> str:
    """Return the saved admin password from the OS keychain.

    The IP is resolved from the worker-injected globals() attribute first so
    multiple instances at different IPs each use the correct credential.
    Save the password using the Hardware Integration page in NetSentinel.
    """
    # globals() == this module\'s __dict__; PluginPollingWorker injects the IP here
    _ip = globals().get("_NETSENTINEL_INSTANCE_IP") or HARDWARE_IP
    try:
        import keyring
        _iid = globals().get("_NETSENTINEL_INSTANCE_ID") or ""
        pw = None
        if _iid:
            pw = keyring.get_password("NetSentinel/plugin", _iid)
        if not pw:
            pw = keyring.get_password("NetSentinel/hardware", _ip)
        if pw:
            return pw
    except Exception:
        pass
    raise RuntimeError(
        f"No password saved for {_ip}. "
        "Enter and save the password in the Hardware Integration page."
    )


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

    connected_clients  — total connected client count (shown on Overview tile)
    extra.nodes        — list of node dicts; drives topology mid-layer and
                         the "Group by node" button in the Devices table.
                         For a single router: one entry with role="primary".
                         Each node needs at least: name, mac, ip, role.
    """
    return {
        "wan_ip":            None,      # WAN/public IP if available
        "uptime_sec":        None,      # router uptime in seconds
        "download_mbps":     None,
        "upload_mbps":       None,
        "signal_dbm":        None,
        "connected_clients": 0,
        "mesh_nodes":        1,
        "extra": {
            "nodes": [
                # For a single router use one entry like this:
                {"name": HARDWARE_NAME, "mac": "", "ip": HARDWARE_IP, "role": "primary"},
            ],
        },
    }


# ── Optional interface ────────────────────────────────────────────────────────

def get_clients() -> list:
    """Return connected devices.

    unit  — name of the mesh node / AP this device is connected to.
             Populates the "Node" column in the Devices table and enables
             the "Group by node" button. For a single router use HARDWARE_NAME.
    band  — Wi-Fi band string, e.g. "2.4G", "5G", "6G", "Wired".
    """
    return []  # replace with: [{"ip": ..., "mac": ..., "hostname": ..., "unit": HARDWARE_NAME, "band": "5G"}, ...]


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__" and "--netsentinel" not in sys.argv:
    print("=== Hardware Info ===")
    print(json.dumps(get_info(), indent=2, default=str))
    print("\\n=== Live Status ===")
    print(json.dumps(get_status(), indent=2, default=str))
    print("\\n=== Clients ===")
    print(json.dumps(get_clients(), indent=2, default=str))

# ── NetSentinel plugin shim (do not remove) ───────────────────────────────────
import sys as _sys
if "--netsentinel" in _sys.argv:
    import json as _json
    try:
        _clients = get_clients()
    except NameError:
        _clients = []
    _sys.stdout.write(_json.dumps({
        "info":    get_info(),
        "status":  get_status(),
        "clients": _clients,
    }, default=str) + "\\n")
    _sys.exit(0)
'''


# ── Helpers ───────────────────────────────────────────────────────────────────

def _btn(label: str, accent: bool = False) -> QPushButton:
    b = QPushButton(label)
    b.setFixedHeight(26)
    b.setFont(QFont("Segoe UI", 9))
    if accent:
        b.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#fff; border:none;"
            f" border-radius:3px; padding:0 12px; }}"
            f"QPushButton:hover {{ background:{ACCENT_LITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
    else:
        b.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:0 10px; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
    return b


def _path_hash(path: str) -> str:
    return hashlib.md5(path.encode()).hexdigest()[:12]


def _parse_dict_literal(node: ast.Dict) -> dict:
    """Shallow-parse an AST Dict literal into a plain Python dict.

    Keys must be string constants.  Values may be constants or nested dicts.
    Used to extract CONFIG_SCHEMA without importing the plugin.
    """
    result: dict = {}
    for k, v in zip(node.keys, node.values):
        if not isinstance(k, ast.Constant) or not isinstance(k.value, str):
            continue
        if isinstance(v, ast.Constant):
            result[k.value] = v.value
        elif isinstance(v, ast.Dict):
            inner: dict = {}
            for ik, iv in zip(v.keys, v.values):
                if isinstance(ik, ast.Constant) and isinstance(iv, ast.Constant):
                    inner[ik.value] = iv.value
            result[k.value] = inner
    return result


def _validate_script(path: str) -> tuple[bool, str, dict]:
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
                    elif isinstance(node.value, ast.Dict):
                        top_names[target.id] = _parse_dict_literal(node.value)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_names.add(node.name)

    missing = ({"HARDWARE_NAME", "HARDWARE_TYPE", "get_info", "get_status"}
               - (set(top_names) | func_names))
    if missing:
        return False, f"Missing: {', '.join(sorted(missing))}", {}

    icon_path = str(top_names.get("ICON_PATH", ""))
    # Also look for icon.png / icon.jpg alongside the plugin file
    if not icon_path:
        for ext in ("icon.png", "icon.jpg", "icon.svg"):
            candidate = Path(path).parent / ext
            if candidate.exists():
                icon_path = str(candidate)
                break

    raw_schema = top_names.get("CONFIG_SCHEMA")
    config_schema = raw_schema if isinstance(raw_schema, dict) else {}

    return True, "OK", {
        "name":             str(top_names.get("HARDWARE_NAME", Path(path).stem)),
        "type":             str(top_names.get("HARDWARE_TYPE", "unknown")),
        "ip":               str(top_names.get("HARDWARE_IP", "")),
        "description":      str(top_names.get("DESCRIPTION", "")),
        "credential_label": str(top_names.get("CREDENTIAL_LABEL", "Password")),
        "pypi_package":     str(top_names.get("PYPI_PACKAGE", "")),
        "icon_path":        icon_path,
        "config_schema":    config_schema,
    }


def _load_paths() -> list[str]:
    s = QSettings("NetSentinel", "NetSentinel")
    raw = s.value(_SETTINGS_KEY, [])
    if isinstance(raw, str):
        raw = [raw]
    return [p for p in (raw or []) if p]


def _save_paths(paths: list[str]) -> None:
    QSettings("NetSentinel", "NetSentinel").setValue(_SETTINGS_KEY, paths)


# ── Instance registry (P2-1 multi-instance) ───────────────────────────────────
# Each entry: {"id": str, "path": str, "ip": str, "name": str}
# "id" is a short UUID fragment used as the keyring key.

def _load_instances() -> list[dict]:
    s = QSettings("NetSentinel", "NetSentinel")
    raw = s.value(_SETTINGS_INSTANCES, None)
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return data
        except Exception:
            pass
    # Migrate from legacy custom_scripts list on first access
    legacy = _load_paths()
    if not legacy:
        return []
    instances = []
    for p in legacy:
        ok, _, meta = _validate_script(p)
        instances.append({
            "id":   _path_hash(p)[:12],
            "path": p,
            "ip":   meta.get("ip", "") if ok else "",
            "name": meta.get("name", Path(p).stem) if ok else Path(p).stem,
        })
    _save_instances(instances)
    # Delete the legacy key now that instances have been promoted
    QSettings("NetSentinel", "NetSentinel").remove(_SETTINGS_KEY)
    return instances


def _save_instances(instances: list[dict]) -> None:
    QSettings("NetSentinel", "NetSentinel").setValue(
        _SETTINGS_INSTANCES, json.dumps(instances)
    )


def _instance_id(path: str, ip: str) -> str:
    """Stable ID for a (path, ip) pair — used as keyring key."""
    import hashlib
    return hashlib.sha256(f"{path}:{ip}".encode()).hexdigest()[:16]


# ── P4-1 unsigned plugin consent tracking ─────────────────────────────────────
_CONSENTED_HASHES_KEY = "hardware/consented_hashes"


def _is_consented(path: str) -> bool:
    """Return True if the user has previously consented to run this plugin content."""
    try:
        h = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except Exception:
        return True  # unreadable file — don't block on consent; validation will catch it
    s = QSettings("NetSentinel", "NetSentinel")
    try:
        consented = set(json.loads(s.value(_CONSENTED_HASHES_KEY, "[]") or "[]"))
    except Exception:
        consented = set()
    return h in consented


def _record_consent(path: str) -> None:
    """Persist a sha256 hash of the plugin file so the warning is not shown again."""
    try:
        h = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except Exception:
        return
    s = QSettings("NetSentinel", "NetSentinel")
    try:
        consented = set(json.loads(s.value(_CONSENTED_HASHES_KEY, "[]") or "[]"))
    except Exception:
        consented = set()
    consented.add(h)
    s.setValue(_CONSENTED_HASHES_KEY, json.dumps(sorted(consented)))


def _migrate_stale_paths() -> None:
    """Module-level function: replace stale _MEI* paths with stable AppData copies.

    PyInstaller extracts to a new _MEI<n> dir on every launch; paths saved from
    a previous run are immediately invalid.  This copies the plugin once to
    get_app_data_dir()/plugins/ and updates QSettings so subsequent launches
    work without user action.

    Extracted from the page method so tests can import and call it directly.
    """
    import shutil as _sh
    from modules.utils import get_app_data_dir as _gad
    paths = _load_paths()
    changed = False
    new_paths = []
    for p in paths:
        if Path(p).exists():
            new_paths.append(p)
            continue
        # Try to find the same filename in AppData plugins dir
        appdata_copy = _gad() / "plugins" / Path(p).name
        if appdata_copy.exists():
            new_paths.append(str(appdata_copy))
            changed = True
            continue
        # Plugin source is still accessible (running from source after a bundle
        # run): copy from the source plugins/ dir if available
        src_candidate = Path(__file__).parent.parent.parent / "plugins" / Path(p).name
        if src_candidate.exists():
            try:
                appdata_copy.parent.mkdir(parents=True, exist_ok=True)
                _sh.copy2(src_candidate, appdata_copy)
                new_paths.append(str(appdata_copy))
                changed = True
                continue
            except Exception:
                pass
        # Path is genuinely gone — keep it so the card can show the error
        new_paths.append(p)
    if changed:
        _save_paths(new_paths)


def _load_last_result(path: str) -> Optional[dict]:
    s = QSettings("NetSentinel", "NetSentinel")
    raw = s.value(_SETTINGS_RESULT.format(_path_hash(path)), None)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _save_last_result(path: str, data: dict) -> None:
    s = QSettings("NetSentinel", "NetSentinel")
    try:
        s.setValue(_SETTINGS_RESULT.format(_path_hash(path)), json.dumps(data, default=str))
    except Exception:
        pass  # QSettings write failure (e.g. serialisation error) is non-critical — skip silently


# ── Plugin health tracking ────────────────────────────────────────────────────
_HEALTH_KEY = "hardware/health/{}"   # .format(path_hash)
_CIRCUIT_BREAK_THRESHOLD = 10        # consecutive errors → auto-disable
_DEGRADED_HOURS          = 24        # hours without success → amber


def _health_key(path: str) -> str:
    return _HEALTH_KEY.format(_path_hash(path))


def _load_health(path: str) -> dict:
    s = QSettings("NetSentinel", "NetSentinel")
    raw = s.value(_health_key(path), None)
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return {"success": 0, "errors": 0, "consecutive": 0,
            "last_ok": 0.0, "last_err": "", "disabled": False}


def _save_health(path: str, h: dict) -> None:
    QSettings("NetSentinel", "NetSentinel").setValue(
        _health_key(path), json.dumps(h, default=str)
    )


def _record_success(path: str) -> dict:
    import time as _t
    h = _load_health(path)
    h["success"]    += 1
    h["consecutive"] = 0
    h["last_ok"]     = _t.time()
    h["disabled"]    = False
    _save_health(path, h)
    return h


def _record_error(path: str, msg: str) -> dict:
    h = _load_health(path)
    h["errors"] += 1
    # AUTH errors are not transient — wrong credentials won't fix themselves by
    # retrying.  Don't count them toward the consecutive circuit-breaker so the
    # card stays in the "Re-enter Password" state rather than auto-disabling.
    if msg.startswith("AUTH:"):
        h["consecutive"] = 0
    else:
        h["consecutive"] = h.get("consecutive", 0) + 1
    h["last_err"] = msg
    if h["consecutive"] >= _CIRCUIT_BREAK_THRESHOLD:
        h["disabled"] = True
    _save_health(path, h)
    return h


def _reset_health(path: str) -> None:
    """Re-enable a disabled plugin and clear the circuit breaker."""
    h = _load_health(path)
    h["consecutive"] = 0
    h["disabled"]    = False
    _save_health(path, h)


# ── P2-2 CONFIG_SCHEMA per-instance config storage ────────────────────────────

def _load_instance_config(instance_id: str) -> dict:
    s = QSettings("NetSentinel", "NetSentinel")
    raw = s.value(_SETTINGS_CONFIG.format(instance_id), None)
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return {}


def _save_instance_config(instance_id: str, cfg: dict) -> None:
    QSettings("NetSentinel", "NetSentinel").setValue(
        _SETTINGS_CONFIG.format(instance_id), json.dumps(cfg)
    )


def _safe_set_text(lbl: "QLabel", text: str) -> None:
    try:
        lbl.setText(text)
    except RuntimeError:
        pass  # Qt widget deleted before the timer/worker callback fired — safe to ignore


def _age_str(ts: float) -> str:
    if ts <= 0:
        return "never"
    age = int(time.time() - ts)
    if age < 60:
        return "just now"
    if age < 3600:
        return f"{age // 60} min ago"
    if age < 86400:
        return f"{age // 3600} h ago"
    return f"{age // 86400} d ago"


def _rsrp_color(v) -> str:
    if v is None:
        return TEXT_MUTED
    try:
        f = float(v)
    except (TypeError, ValueError):
        return TEXT_MUTED
    if f >= -80:
        return GREEN
    if f >= -100:
        return AMBER
    return RED


def _sinr_color(v) -> str:
    if v is None:
        return TEXT_MUTED
    try:
        f = float(v)
    except (TypeError, ValueError):
        return TEXT_MUTED
    if f >= 13:
        return GREEN
    if f >= 5:
        return AMBER
    return RED


# ── P3-4 Community index background threads ───────────────────────────────────

class _CommunityIndexThread(QThread):
    """Fetch community plugin index JSON in a background thread."""

    done  = pyqtSignal(list)   # list of plugin dicts
    error = pyqtSignal(str)

    def __init__(self, url: str, parent=None) -> None:
        super().__init__(parent)
        self._url = url

    def run(self) -> None:
        try:
            import urllib.request
            with urllib.request.urlopen(self._url, timeout=15) as resp:  # noqa: S310
                data = resp.read().decode("utf-8", errors="replace")
            import json as _json
            entries = _json.loads(data)
            if not isinstance(entries, list):
                self.error.emit("Index is not a JSON array")
                return
            self.done.emit(entries)
        except Exception as exc:
            self.error.emit(str(exc))


class _CommunityDownloadThread(QThread):
    """Download a community plugin file, verify SHA-256, save to AppData/plugins/."""

    done  = pyqtSignal(str)    # path to saved .py file
    error = pyqtSignal(str)

    def __init__(self, url: str, expected_sha256: str, plugin_name: str, parent=None) -> None:
        super().__init__(parent)
        self._url      = url
        self._expected = expected_sha256
        self._name     = plugin_name

    def run(self) -> None:
        try:
            import urllib.request
            import hashlib as _hl
            import re
            from modules.utils import get_app_data_dir

            with urllib.request.urlopen(self._url, timeout=30) as resp:  # noqa: S310
                data = resp.read()

            if self._expected:
                actual = _hl.sha256(data).hexdigest()
                if actual != self._expected:
                    self.error.emit(
                        f"SHA-256 mismatch for '{self._name}' — "
                        f"expected {self._expected[:16]}… got {actual[:16]}…"
                    )
                    return

            safe = re.sub(r"[^a-zA-Z0-9_]", "_", self._name.lower()).strip("_") or "plugin"
            dest_dir = get_app_data_dir() / "plugins"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f"{safe}.py"
            dest.write_bytes(data)
            self.done.emit(str(dest))
        except Exception as exc:
            self.error.emit(str(exc))


# ── Signal detail panel (modem) ───────────────────────────────────────────────

class _ModemDetailPanel(QFrame):
    """Two-column signal grid: 5G NR | LTE Primary."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("modemDetailPanel")
        self.setStyleSheet(
            f"QFrame#modemDetailPanel {{ background:{BG_DARK}; border:none;"
            f" border-top:1px solid {BORDER}; }}"
        )
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._nr_col  = self._make_col("5G NR",       ACCENT, border_right=True)
        self._lte_col = self._make_col("LTE Primary",  AMBER,  border_right=False)
        root.addWidget(self._nr_col[0], 1)
        root.addWidget(self._lte_col[0], 1)

        _ls = f"color:{TEXT_SECONDARY}; font-size:10px; border:none; background:transparent;"
        _vs = f"color:{TEXT_PRIMARY}; font-size:10px; font-weight:bold; border:none; background:transparent;"

        def _row(col_lay, label, attr):
            h = QHBoxLayout()
            h.setContentsMargins(0, 1, 0, 1)
            h.setSpacing(6)
            l = QLabel(f"{label}:")
            l.setFixedWidth(52)
            l.setStyleSheet(_ls)
            v = QLabel("—")
            v.setStyleSheet(_vs)
            setattr(self, attr, v)
            h.addWidget(l)
            h.addWidget(v, 1)
            col_lay.addLayout(h)

        _row(self._nr_col[1],  "Band",  "_nr_band")
        _row(self._nr_col[1],  "RSRP",  "_nr_rsrp")
        _row(self._nr_col[1],  "SINR",  "_nr_sinr")
        _row(self._nr_col[1],  "RSRQ",  "_nr_rsrq")
        _row(self._nr_col[1],  "PCI",   "_nr_pci")
        _row(self._nr_col[1],  "ARFCN", "_nr_arfcn")
        self._nr_col[1].addStretch()

        _row(self._lte_col[1], "Band",   "_lte_band")
        _row(self._lte_col[1], "RSRP",   "_lte_rsrp")
        _row(self._lte_col[1], "SNR",    "_lte_snr")
        _row(self._lte_col[1], "RSRQ",   "_lte_rsrq")
        _row(self._lte_col[1], "PCI",    "_lte_pci")
        _row(self._lte_col[1], "EARFCN", "_lte_earfcn")
        self._lte_col[1].addStretch()

        # Connection strip
        conn = QFrame()
        conn.setStyleSheet(
            f"background:{BG_DARK}; border:none; border-bottom:1px solid {BORDER};"
        )
        cl = QHBoxLayout(conn)
        cl.setContentsMargins(12, 4, 12, 4)
        cl.setSpacing(0)

        def _cpair(label, attr):
            ll = QLabel(f"{label}: ")
            ll.setStyleSheet(_ls)
            vl = QLabel("—")
            vl.setStyleSheet(_vs)
            setattr(self, attr, vl)
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.VLine)
            sep.setStyleSheet(f"border:none; border-left:1px solid {BORDER}; margin:0 12px;")
            cl.addWidget(ll); cl.addWidget(vl); cl.addWidget(sep)

        _cpair("Operator", "_conn_op")
        _cpair("Cell ID",  "_conn_cell")
        _cpair("WAN IP",   "_conn_ip")
        cl.addStretch()

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(conn)

        body = QFrame()
        body.setStyleSheet(f"background:{BG_DARK}; border:none;")
        body.setLayout(root)
        outer.addWidget(body)

        self.setLayout(outer)

    def _make_col(self, title: str, color: str, border_right: bool):
        col = QFrame()
        border = f"border-right:1px solid {BORDER};" if border_right else ""
        col.setStyleSheet(f"background:{BG_DARK}; border:none; {border}")
        lay = QVBoxLayout(col)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet(
            f"color:{color}; font-size:10px; font-weight:bold; border:none;"
            f" border-bottom:1px solid {BORDER}; background:transparent;"
            f" padding-bottom:3px; margin-bottom:2px;"
        )
        lay.addWidget(t)
        return col, lay

    def update(self, extra: dict, status: dict | None = None) -> None:
        # wan_ip lives at status top-level in most plugins, not inside extra
        merged = {**(status or {}), **extra}
        def _s(v): return str(v) if v is not None else "—"
        def _dbm(v): return f"{float(v):.1f} dBm" if v is not None else "—"
        def _db(v):  return f"{float(v):.1f} dB"  if v is not None else "—"

        self._nr_band.setText(_s(merged.get("nr5g_band")))
        nr_rsrp = merged.get("nr5g_rsrp_dbm")
        self._nr_rsrp.setText(_dbm(nr_rsrp))
        self._nr_rsrp.setStyleSheet(
            f"color:{_rsrp_color(nr_rsrp)}; font-size:10px; font-weight:bold;"
            f" border:none; background:transparent;"
        )
        nr_sinr = merged.get("nr5g_sinr_db")
        self._nr_sinr.setText(_db(nr_sinr))
        self._nr_sinr.setStyleSheet(
            f"color:{_sinr_color(nr_sinr)}; font-size:10px; font-weight:bold;"
            f" border:none; background:transparent;"
        )
        self._nr_rsrq.setText(_db(merged.get("nr5g_rsrq_db")))
        self._nr_pci.setText(_s(merged.get("nr5g_pci")))
        self._nr_arfcn.setText(_s(merged.get("nr5g_arfcn")))

        lte_rsrp = merged.get("lte_rsrp_dbm")
        self._lte_band.setText(_s(merged.get("lte_band")))
        self._lte_rsrp.setText(_dbm(lte_rsrp))
        self._lte_rsrp.setStyleSheet(
            f"color:{_rsrp_color(lte_rsrp)}; font-size:10px; font-weight:bold;"
            f" border:none; background:transparent;"
        )
        lte_snr = merged.get("lte_snr_db")
        self._lte_snr.setText(_db(lte_snr))
        self._lte_snr.setStyleSheet(
            f"color:{_sinr_color(lte_snr)}; font-size:10px; font-weight:bold;"
            f" border:none; background:transparent;"
        )
        self._lte_rsrq.setText(_db(merged.get("lte_rsrq_db")))
        self._lte_pci.setText(_s(merged.get("lte_pci")))
        self._lte_earfcn.setText(_s(merged.get("lte_earfcn")))

        mcc, mnc = merged.get("mcc"), merged.get("mnc")
        self._conn_op.setText(f"{mcc}-{mnc}" if mcc and mnc else "—")
        cell = merged.get("cell_id")
        enb  = merged.get("enb_id")
        self._conn_cell.setText(
            f"{cell} (eNB: {enb})" if cell and enb else _s(cell)
        )
        self._conn_ip.setText(_s(merged.get("wan_ip")))


# ── Router/AP detail panel ────────────────────────────────────────────────────

class _RouterDetailPanel(QFrame):
    """Mesh nodes table + connected clients table for router/AP plugins.

    The client list supports two view modes toggled by a button in the header:
      flat    — QTableWidget sorted by hostname (default)
      grouped — QTreeWidget with each mesh node as a collapsible group header

    Both modes work for all plugins: Deco (many nodes), FritzBox/Netgear (single
    router group), UniFi, MikroTik, etc. Clients with no unit field go to a
    "Router" fallback group.

    Right-click context menus mirror mesh_router_page:
      Nodes:   Geo Map | Copy IP | Copy MAC
      Clients: Port Scan | Geo Map | AbuseIPDB | Copy IP | Copy MAC
    """

    # Emitted on context-menu actions — parent page connects to its own signals
    geo_map_ip     = pyqtSignal(str)
    port_scan_ip   = pyqtSignal(str)
    check_abuse_ip = pyqtSignal(str)

    _TABLE_SS = (
        f"QTableWidget {{ border:none; font-size:10px; color:{TEXT_PRIMARY}; }}"
        f"QHeaderView::section {{"
        f"  background:{TH_BG}; color:{TH_TEXT}; font-size:10px;"
        f"  font-weight:bold; padding:3px 5px; border:none;"
        f"  border-right:1px solid {TH_BORDER};"
        f"}}"
        f"QTableWidget::item:selected {{ background:{TABLE_SEL}; color:{TEXT_PRIMARY}; }}"
        f"QTableWidget::item:alternate {{ background:{BG_ALT_ROW}; }}"
        f"QTableWidget::item {{ border-bottom:1px solid {TABLE_ROW_BORDER}; }}"
    )
    _TREE_SS = (
        f"QTreeWidget {{ border:none; font-size:10px; color:{TEXT_PRIMARY};"
        f"  background:{BG_DARK}; alternate-background-color:{BG_ALT_ROW}; }}"
        f"QTreeWidget::item {{ border-bottom:1px solid {TABLE_ROW_BORDER};"
        f"  padding:2px 0; }}"
        f"QTreeWidget::item:selected {{ background:{TABLE_SEL}; color:{TEXT_PRIMARY}; }}"
        f"QHeaderView::section {{"
        f"  background:{TH_BG}; color:{TH_TEXT}; font-size:10px;"
        f"  font-weight:bold; padding:3px 5px; border:none;"
        f"  border-right:1px solid {TH_BORDER};"
        f"}}"
        f"QTreeWidget::branch:has-children:!has-siblings:closed,"
        f"QTreeWidget::branch:closed:has-children:has-siblings {{"
        f"  image: none; border-image: none; }}"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._view_mode = "flat"
        self._last_clients: list = []
        self._last_nodes: list = []

        self.setObjectName("routerDetailPanel")
        self.setStyleSheet(
            f"QFrame#routerDetailPanel {{ background:{BG_DARK}; border:none;"
            f" border-top:1px solid {BORDER}; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 10)
        lay.setSpacing(8)

        # ── Mesh nodes ────────────────────────────────────────────────────────
        nodes_hdr = QLabel("MESH NODES")
        nodes_hdr.setStyleSheet(
            f"color:{ACCENT}; font-size:9px; font-weight:bold; border:none;"
            f" background:transparent; letter-spacing:0.5px;"
        )
        lay.addWidget(nodes_hdr)

        self._node_table = QTableWidget(0, 3)
        self._node_table.setHorizontalHeaderLabels(["Node", "Role", "MAC"])
        self._node_table.horizontalHeader().setStretchLastSection(True)
        self._node_table.setAlternatingRowColors(True)
        self._node_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._node_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._node_table.verticalHeader().setVisible(False)
        self._node_table.setShowGrid(True)
        self._node_table.verticalHeader().setDefaultSectionSize(22)
        self._node_table.setMaximumHeight(180)
        self._node_table.setStyleSheet(self._TABLE_SS)
        lay.addWidget(self._node_table)

        # ── Connected clients header ──────────────────────────────────────────
        cli_hdr_row = QHBoxLayout()
        cli_hdr_row.setContentsMargins(0, 4, 0, 0)
        clients_hdr = QLabel("CONNECTED CLIENTS")
        clients_hdr.setStyleSheet(
            f"color:{AMBER}; font-size:9px; font-weight:bold; border:none;"
            f" background:transparent; letter-spacing:0.5px;"
        )
        self._client_count_lbl = QLabel("")
        self._client_count_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:9px; border:none; background:transparent;"
        )
        self._toggle_btn = QPushButton("Group by node")
        self._toggle_btn.setFixedHeight(20)
        self._toggle_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_DARK}; color:{TEXT_MUTED}; border:1px solid {BORDER};"
            f"  border-radius:3px; font-size:9px; padding:0 6px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; border-color:{ACCENT}; }}"
            f"QPushButton:checked {{ background:{ACCENT}; color:#000; border-color:{ACCENT}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.toggled.connect(self._on_toggle)
        cli_hdr_row.addWidget(clients_hdr)
        cli_hdr_row.addWidget(self._client_count_lbl)
        cli_hdr_row.addStretch()
        cli_hdr_row.addWidget(self._toggle_btn)
        lay.addLayout(cli_hdr_row)

        # ── Client stack (flat table / grouped tree) ──────────────────────────
        self._client_stack = QStackedWidget()

        # Page 0: flat QTableWidget — cols: Hostname, IP, Band, Node, ↑ KB/s, ↓ KB/s
        self._client_table = QTableWidget(0, 6)
        self._client_table.setHorizontalHeaderLabels(
            ["Hostname", "IP", "Band", "Node", "↑ KB/s", "↓ KB/s"]
        )
        hdr = self._client_table.horizontalHeader()
        hdr.setSectionResizeMode(0, hdr.ResizeMode.Stretch)
        self._client_table.setColumnWidth(1, 115)
        self._client_table.setColumnWidth(2, 68)
        self._client_table.setColumnWidth(3, 95)
        self._client_table.setColumnWidth(4, 62)
        self._client_table.setColumnWidth(5, 62)
        self._client_table.setAlternatingRowColors(True)
        self._client_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._client_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._client_table.verticalHeader().setVisible(False)
        self._client_table.setShowGrid(True)
        self._client_table.verticalHeader().setDefaultSectionSize(20)
        self._client_table.setMaximumHeight(220)
        self._client_table.setStyleSheet(self._TABLE_SS)
        self._client_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._client_table.customContextMenuRequested.connect(self._client_context_menu)
        self._client_stack.addWidget(self._client_table)  # index 0

        # Page 1: grouped QTreeWidget — cols: Node/Hostname, IP, Band, ↑ KB/s, ↓ KB/s
        self._tree_widget = QTreeWidget()
        self._tree_widget.setHeaderLabels(["Node / Hostname", "IP", "Band", "↑ KB/s", "↓ KB/s"])
        thdr = self._tree_widget.header()
        thdr.setSectionResizeMode(0, thdr.ResizeMode.Stretch)
        self._tree_widget.setColumnWidth(1, 115)
        self._tree_widget.setColumnWidth(2, 68)
        self._tree_widget.setColumnWidth(3, 62)
        self._tree_widget.setColumnWidth(4, 62)
        self._tree_widget.setAlternatingRowColors(True)
        self._tree_widget.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        self._tree_widget.setSelectionBehavior(QTreeWidget.SelectionBehavior.SelectRows)
        self._tree_widget.setMaximumHeight(220)
        self._tree_widget.setStyleSheet(self._TREE_SS)
        self._tree_widget.setRootIsDecorated(True)
        self._tree_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree_widget.customContextMenuRequested.connect(self._tree_context_menu)
        self._client_stack.addWidget(self._tree_widget)   # index 1

        # Node table context menu
        self._node_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._node_table.customContextMenuRequested.connect(self._node_context_menu)

        lay.addWidget(self._client_stack)

    # ── Toggle ────────────────────────────────────────────────────────────────

    def _on_toggle(self, checked: bool) -> None:
        self._view_mode = "grouped" if checked else "flat"
        self._toggle_btn.setText("Show flat list" if checked else "Group by node")
        self._client_stack.setCurrentIndex(1 if checked else 0)
        if checked:
            self._rebuild_tree(self._last_clients, self._last_nodes)

    # ── Data population ───────────────────────────────────────────────────────

    @staticmethod
    def _display_name(c: dict) -> str:
        import re as _re
        _mac_re = _re.compile(r"^([0-9a-f]{2}[:\-]){5}[0-9a-f]{2}$", _re.I)
        hostname = c.get("hostname", "") or ""
        return hostname if hostname and not _mac_re.match(hostname) else c.get("ip", "—")

    @staticmethod
    def _bw_str(val) -> str:
        try:
            v = float(val)
            return f"{v:.0f}" if v else ""
        except (TypeError, ValueError):
            return ""

    def update(self, status: dict, clients: list) -> None:
        if not isinstance(status, dict):
            status = {}
        nodes   = [n for n in (status.get("extra", {}).get("nodes") or []) if isinstance(n, dict)]
        clients = [c for c in (clients or []) if isinstance(c, dict)]
        n_cli = status.get("connected_clients") or len(clients)

        self._last_clients = clients
        self._last_nodes   = nodes

        # Node table — store IP in col 2, MAC col 3 (IP hidden by default but accessible for menu)
        self._node_table.setRowCount(0)
        for node in nodes:
            r = self._node_table.rowCount()
            self._node_table.insertRow(r)
            self._node_table.setItem(r, 0, QTableWidgetItem(node.get("name", "—")))
            role_item = QTableWidgetItem(node.get("role", "—"))
            if node.get("role") == "master":
                role_item.setForeground(QColor(GREEN))
            self._node_table.setItem(r, 1, role_item)
            # MAC in col 2 — store IP as UserRole for context menu
            mac_item = QTableWidgetItem(node.get("mac", "—"))
            mac_item.setData(Qt.ItemDataRole.UserRole, node.get("ip", ""))
            self._node_table.setItem(r, 2, mac_item)

        self._client_count_lbl.setText(
            f"({n_cli} device{'s' if n_cli != 1 else ''})" if n_cli is not None else ""
        )

        # Flat table
        self._client_table.setRowCount(0)
        for c in clients:
            r = self._client_table.rowCount()
            self._client_table.insertRow(r)
            hn_item = QTableWidgetItem(self._display_name(c))
            hn_item.setData(Qt.ItemDataRole.UserRole, {"ip": c.get("ip", ""), "mac": c.get("mac", "")})
            self._client_table.setItem(r, 0, hn_item)
            self._client_table.setItem(r, 1, QTableWidgetItem(c.get("ip", "—")))
            band = c.get("band", "") or ""
            band_item = QTableWidgetItem(band if band else "—")
            if "5" in band:
                band_item.setForeground(QColor(ACCENT))
            self._client_table.setItem(r, 2, band_item)
            self._client_table.setItem(r, 3, QTableWidgetItem(c.get("unit", "") or "—"))
            ul = QTableWidgetItem(self._bw_str(c.get("upload_kbps")))
            ul.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            dl = QTableWidgetItem(self._bw_str(c.get("download_kbps")))
            dl.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._client_table.setItem(r, 4, ul)
            self._client_table.setItem(r, 5, dl)

        if self._view_mode == "grouped":
            self._rebuild_tree(clients, nodes)

    def _rebuild_tree(self, clients: list, nodes: list) -> None:
        self._tree_widget.clear()

        node_names = [n.get("name", "") for n in nodes if n.get("name")]
        groups: dict[str, list] = {name: [] for name in node_names}
        ungrouped: list = []

        for c in clients:
            unit = (c.get("unit") or "").strip()
            if unit in groups:
                groups[unit].append(c)
            elif unit:
                groups.setdefault(unit, []).append(c)
            else:
                ungrouped.append(c)

        if ungrouped:
            groups["Router"] = ungrouped

        for group_name, group_clients in groups.items():
            node_meta = next((n for n in nodes if n.get("name") == group_name), {})
            role = node_meta.get("role", "")
            role_suffix = " (main)" if role == "master" else (" (satellite)" if role == "slave" else "")
            n = len(group_clients)
            header = QTreeWidgetItem([
                f"{group_name}{role_suffix}  ·  {n} device{'s' if n != 1 else ''}",
                "", "", "", "",
            ])
            header.setForeground(0, QColor(ACCENT if role == "master" else TEXT_MUTED))
            self._tree_widget.addTopLevelItem(header)

            for c in group_clients:
                band = c.get("band", "") or ""
                child = QTreeWidgetItem([
                    self._display_name(c),
                    c.get("ip", "—"),
                    band if band else "—",
                    self._bw_str(c.get("upload_kbps")),
                    self._bw_str(c.get("download_kbps")),
                ])
                child.setData(0, Qt.ItemDataRole.UserRole,
                              {"ip": c.get("ip", ""), "mac": c.get("mac", "")})
                if "5" in band:
                    child.setForeground(2, QColor(ACCENT))
                for col in (3, 4):
                    child.setTextAlignment(col, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                header.addChild(child)

            header.setExpanded(True)

    # ── Context menus ─────────────────────────────────────────────────────────

    def _node_context_menu(self, pos) -> None:
        row = self._node_table.rowAt(pos.y())
        if row < 0:
            return
        mac_item = self._node_table.item(row, 2)
        ip  = (mac_item.data(Qt.ItemDataRole.UserRole) or "") if mac_item else ""
        mac = self._node_table.item(row, 2).text() if self._node_table.item(row, 2) else ""
        menu = QMenu(self)
        if ip:
            menu.addAction("Show on Geo Map", lambda: self.geo_map_ip.emit(ip))
            menu.addSeparator()
            menu.addAction(f"Copy IP  {ip}", lambda: QApplication.clipboard().setText(ip))
        if mac and mac != "—":
            menu.addAction(f"Copy MAC  {mac}", lambda: QApplication.clipboard().setText(mac))
        if not menu.isEmpty():
            menu.exec(QCursor.pos())

    def _client_context_menu(self, pos) -> None:
        row = self._client_table.rowAt(pos.y())
        if row < 0:
            return
        data = self._client_table.item(row, 0)
        info = data.data(Qt.ItemDataRole.UserRole) if data else {}
        ip  = info.get("ip", "") if info else ""
        mac = info.get("mac", "") if info else ""
        self._show_client_menu(ip, mac)

    def _tree_context_menu(self, pos) -> None:
        item = self._tree_widget.itemAt(pos)
        if not item or item.parent() is None:
            return  # top-level node header — no client menu
        info = item.data(0, Qt.ItemDataRole.UserRole) or {}
        self._show_client_menu(info.get("ip", ""), info.get("mac", ""))

    def _show_client_menu(self, ip: str, mac: str) -> None:
        menu = QMenu(self)
        if ip:
            menu.addAction("Port Scan", lambda: self.port_scan_ip.emit(ip))
            menu.addAction("Show on Geo Map", lambda: self.geo_map_ip.emit(ip))
            menu.addAction("Check IP (AbuseIPDB)", lambda: self.check_abuse_ip.emit(ip))
            menu.addSeparator()
            menu.addAction(f"Copy IP  {ip}", lambda: QApplication.clipboard().setText(ip))
        if mac and mac != "—":
            menu.addAction(f"Copy MAC  {mac}", lambda: QApplication.clipboard().setText(mac))
        if not menu.isEmpty():
            menu.exec(QCursor.pos())


# ── Plugin connection tester (live-test before registration) ─────────────────

class _PluginConnectionTester(QThread):
    """Runs get_info() + get_status() in a background thread with temporary credentials.

    Emits success(dict) if both calls return without error, or failure(str) with
    a human-readable message.  The caller is responsible for persisting the
    credential to keyring ONLY on success.
    """

    success = pyqtSignal(dict)  # {"info": ..., "status": ...}
    failure = pyqtSignal(str)   # plain-English error message

    def __init__(self, path: str, ip: str, pw: str, parent=None) -> None:
        super().__init__(parent)
        self._path = path
        self._ip   = ip
        self._pw   = pw

    def run(self) -> None:
        import importlib.util
        import os as _os

        # Temporarily save credential so the plugin can read it via keyring.
        try:
            import keyring as _kr
            _kr.set_password("NetSentinel/hardware", self._ip, self._pw)
        except Exception:
            pass  # keyring unavailable — plugin reads from its own field

        # Legacy env-var shim: set NETSENTINEL_PLUGIN_IP so older plugins that
        # haven't adopted _NETSENTINEL_INSTANCE_IP still work.  We save/restore
        # so concurrent testers don't pollute each other's IP (RULE-PL1).
        _prev_ip = _os.environ.get("NETSENTINEL_PLUGIN_IP")
        _os.environ["NETSENTINEL_PLUGIN_IP"] = self._ip

        try:
            if not Path(self._path).exists():
                self.failure.emit(f"Plugin file not found: {self._path}")
                return

            # Ensure NetSentinel modules are importable
            _ns_root = next(
                (p for p in __import__("sys").path
                 if p and Path(p, "modules", "utils.py").exists()),
                str(Path(__file__).parent.parent.parent),
            )
            import sys as _sys
            if _ns_root not in _sys.path:
                _sys.path.insert(0, _ns_root)

            spec = importlib.util.spec_from_file_location(
                f"_ns_test_{Path(self._path).stem}", self._path
            )
            if spec is None or spec.loader is None:
                self.failure.emit("Cannot load plugin file.")
                return

            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]

            # Inject IP directly into the module namespace (RULE-PL1).
            # This takes precedence over the env-var shim above.
            mod._NETSENTINEL_INSTANCE_IP = self._ip
            mod._NETSENTINEL_INSTANCE_ID = ""  # no stable ID yet at test time

            get_info   = getattr(mod, "get_info",   None)
            get_status = getattr(mod, "get_status", None)

            if not callable(get_info) or not callable(get_status):
                self.failure.emit("Plugin is missing get_info() or get_status().")
                return

            info   = get_info()
            status = get_status()

            # Treat an error inside extra as a failure so the user can fix it now
            err = (status.get("extra") or {}).get("error", "")
            if err:
                self.failure.emit(_classify_error(str(err)))
                return

            self.success.emit({"info": info, "status": status})

        except SystemExit:
            self.failure.emit("Plugin called sys.exit() unexpectedly.")
        except Exception as exc:
            self.failure.emit(_classify_error(str(exc)))
        finally:
            # Always restore the env var to its pre-test value (RULE-PL1).
            if _prev_ip is None:
                _os.environ.pop("NETSENTINEL_PLUGIN_IP", None)
            else:
                _os.environ["NETSENTINEL_PLUGIN_IP"] = _prev_ip


def _classify_error(msg: str) -> str:
    """Convert a raw or prefixed error string into a human-readable sentence.

    Handles structured prefixes emitted by plugin _fmt_err() helpers:
      FILE: <msg>  — plugin file not found (moved / deleted)
      DEPS: <msg>  — missing pip package
      AUTH: <msg>  — authentication failure
      NET:  <msg>  — network / connectivity failure
      ERR:  <msg>  — other error
    Also parses unstructured legacy messages for backwards compatibility.
    """
    import re
    # Structured prefixes from plugin _fmt_err()
    if msg.startswith("FILE:"):
        return "Plugin file was moved or deleted — re-import it to restore functionality."
    if msg.startswith("DEPS:"):
        body = msg[5:].strip()
        m = re.search(r"pip install\s+(\S+)", body)
        if m:
            return f"Missing library: {m.group(1)}\nRun: pip install {m.group(1)}"
        return f"Missing dependency — {body}"
    if msg.startswith("AUTH:"):
        return f"Authentication failed — {msg[5:].strip()}"
    if msg.startswith("NET:"):
        return f"Cannot reach the device — {msg[4:].strip()}"
    if msg.startswith("ERR:"):
        return msg[4:].strip()
    # Legacy / unstructured fallback
    m = re.search(r"pip install\s+(\S+)", msg)
    if m:
        return f"Missing library: {m.group(1)}\nRun: pip install {m.group(1)}"
    low = msg.lower()
    if "wrong password" in low or "auth" in low or "login" in low or "401" in low:
        return "Authentication failed — check your password."
    if "connection refused" in low or "timed out" in low or "unreachable" in low:
        return "Cannot reach the device — check the IP address and that the device is online."
    if "no saved password" in low or "no password" in low:
        return "No password saved — enter a password and try again."
    return msg


# ── Pip install dialog ────────────────────────────────────────────────────────

class PipInstallDialog(QDialog):
    """Runs `pip install <package>` in a QProcess and streams output to a log.

    Usage:
        dlg = PipInstallDialog("fritzconnection", parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # library is now installed
    """

    def __init__(self, package: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._package = package
        self._success = False
        self.setWindowTitle(f"Install {package}")
        self.setMinimumWidth(520)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        hdr = QLabel(f"Installing <b>{package}</b> via pip…")
        hdr.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:14px;")
        lay.addWidget(hdr)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(200)
        self._log.setStyleSheet(
            f"background:{BG_DARK}; color:{TEXT_SECONDARY}; "
            f"font-family:monospace; font-size:12px; border:none;"
        )
        lay.addWidget(self._log)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)  # indeterminate
        self._bar.setTextVisible(False)
        lay.addWidget(self._bar)

        btn_row = QHBoxLayout()
        self._btn_close = QPushButton("Cancel")
        self._btn_close.setFixedHeight(32)
        self._btn_close.clicked.connect(self._on_cancel)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_close)
        lay.addLayout(btn_row)

        self._proc = QProcess(self)
        self._proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._proc.readyReadStandardOutput.connect(self._on_output)
        self._proc.finished.connect(self._on_finished)

        python = _find_python_exe()
        self._proc.start(python, ["-m", "pip", "install", "--upgrade", package])

    def _on_output(self) -> None:
        from PyQt6.QtGui import QTextCursor
        data = bytes(self._proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._log.moveCursor(QTextCursor.MoveOperation.End)
        self._log.insertPlainText(data)
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_finished(self, exit_code: int, _status) -> None:
        self._bar.setRange(0, 1)
        self._bar.setValue(1)
        if exit_code == 0:
            self._success = True
            self._log.append(f"\n✓  {self._package} installed successfully.")
            self._btn_close.setText("Done")
            self._btn_close.clicked.disconnect()
            self._btn_close.clicked.connect(self.accept)
        else:
            self._log.append(f"\n✗  pip exited with code {exit_code}.")
            self._btn_close.setText("Close")

    def _on_cancel(self) -> None:
        if self._proc.state() != QProcess.ProcessState.NotRunning:
            self._proc.kill()
        self.reject()


# ── Hub card ──────────────────────────────────────────────────────────────────

class HubCard(QFrame):
    """Live status card for one imported hardware plugin."""

    refresh_clicked         = pyqtSignal(str)   # path
    remove_clicked          = pyqtSignal(str)   # path
    stop_clicked            = pyqtSignal(str)   # path — stop polling worker
    reenable_clicked        = pyqtSignal(str)   # path — re-enable after circuit break
    install_completed       = pyqtSignal(str)   # path — pip install succeeded, reload worker
    add_another             = pyqtSignal(str)   # path — add a second instance of this plugin
    update_credentials_clicked = pyqtSignal(str)  # instance_id — open credential dialog
    reimport_clicked        = pyqtSignal(str)   # path — plugin file not found, browse for new
    rename_requested        = pyqtSignal(str, str, str)  # (instance_id, old_name, new_name)

    def __init__(self, path: str, meta: dict, last_result: Optional[dict],
                 instance_id: str = "", display_name: str = "",
                 instance_ip: str = "", parent=None):
        super().__init__(parent)
        self._path          = path
        self._meta          = meta
        self._instance_id   = instance_id or _path_hash(path)[:12]
        self._instance_ip   = instance_ip or meta.get("ip", "")
        self._pending_pkg   = ""   # pypi package to install when dep error shown
        self._last_ts    = last_result.get("_ts", 0.0) if isinstance(last_result, dict) else 0.0
        self._hw_type    = meta.get("type", "unknown")
        self._detail_visible = False
        # Use custom display name if provided (for multi-instance)
        if display_name:
            meta = dict(meta)
            meta["name"] = display_name

        self.setObjectName("hubCard")
        self.setStyleSheet(
            f"QFrame#hubCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header row ────────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setObjectName("hubCardHdr")
        hdr.setStyleSheet(
            f"QFrame#hubCardHdr {{ background:{BG_CARD}; border:none;"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(12, 8, 10, 8)
        hdr_lay.setSpacing(8)

        # Status dot — clickable to expand/collapse detail
        self._dot = QLabel("●")
        self._dot.setStyleSheet(f"color:{TEXT_MUTED}; font-size:13px; border:none;")
        self._dot.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dot.setToolTip("Click to expand / collapse detail")
        self._dot.mousePressEvent = lambda _: self._toggle_detail()
        hdr_lay.addWidget(self._dot)

        # Plugin icon (P2-3) — 24×24 QPixmap if icon.png found alongside script
        icon_path = meta.get("icon_path", "")
        if icon_path:
            try:
                px = QPixmap(icon_path).scaled(
                    24, 24,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                if not px.isNull():
                    icon_lbl = QLabel()
                    icon_lbl.setPixmap(px)
                    icon_lbl.setFixedSize(26, 26)
                    icon_lbl.setStyleSheet("border:none; background:transparent;")
                    hdr_lay.addWidget(icon_lbl)
            except Exception:
                pass  # icon load failure is non-critical

        # Name + type badge
        name_col = QVBoxLayout()
        name_col.setSpacing(1)
        name_col.setContentsMargins(0, 0, 0, 0)
        self._name_lbl = QLabel(f"<b>{meta.get('name', Path(path).stem)}</b>")
        self._name_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._name_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:12px; border:none; background:transparent;"
        )
        hw_type = meta.get("type", "")
        hw_ip   = self._instance_ip or meta.get("ip", "")
        sub_txt = "  ·  ".join(filter(None, [hw_type, hw_ip]))
        self._sub_lbl = QLabel(sub_txt)
        self._sub_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:9px; border:none; background:transparent;"
        )
        name_col.addWidget(self._name_lbl)
        name_col.addWidget(self._sub_lbl)
        hdr_lay.addLayout(name_col)

        # Metrics summary (centre)
        self._metrics_lbl = QLabel("Never run")
        self._metrics_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:10px; border:none; background:transparent;"
        )
        hdr_lay.addWidget(self._metrics_lbl, 1)

        # Timestamp
        self._ts_lbl = QLabel("")
        self._ts_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:9px; border:none; background:transparent;"
        )
        hdr_lay.addWidget(self._ts_lbl)

        # Health counter — "42/45 ✓" shown in small muted text
        self._health_lbl = QLabel("")
        self._health_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:9px; border:none; background:transparent;"
        )
        self._health_lbl.setVisible(False)
        hdr_lay.addWidget(self._health_lbl)

        # Install dependency button — hidden until a dep error is detected
        self._btn_install = _btn("⬇ Install dependency", accent=True)
        self._btn_install.setFixedHeight(26)
        self._btn_install.setToolTip("Install the missing Python library via pip")
        self._btn_install.setVisible(False)
        self._btn_install.clicked.connect(self._on_install_dep)
        hdr_lay.addWidget(self._btn_install)

        # Re-enable button — shown after circuit breaker fires
        self._btn_reenable = _btn("↺ Re-enable")
        self._btn_reenable.setFixedHeight(26)
        self._btn_reenable.setToolTip("Reset error counter and resume polling")
        self._btn_reenable.setVisible(False)
        self._btn_reenable.clicked.connect(self._on_reenable)
        hdr_lay.addWidget(self._btn_reenable)

        # Update credentials button — shown when an AUTH: error is detected (P4-1)
        self._btn_update_cred = _btn("🔑 Re-enter Password")
        self._btn_update_cred.setFixedHeight(26)
        self._btn_update_cred.setToolTip(
            "Authentication failed — click to update the saved password"
        )
        self._btn_update_cred.setVisible(False)
        self._btn_update_cred.clicked.connect(
            lambda: self.update_credentials_clicked.emit(self._instance_id)
        )
        hdr_lay.addWidget(self._btn_update_cred)

        # Re-import button — shown when FILE: error indicates plugin file is gone (P6-2)
        self._btn_reimport = _btn("⤵ Re-import")
        self._btn_reimport.setFixedHeight(26)
        self._btn_reimport.setToolTip(
            "Plugin file was moved or deleted — browse to locate it again"
        )
        self._btn_reimport.setVisible(False)
        self._btn_reimport.clicked.connect(
            lambda: self.reimport_clicked.emit(self._path)
        )
        hdr_lay.addWidget(self._btn_reimport)

        # Refresh button
        self._btn_refresh = _btn("↻")
        self._btn_refresh.setFixedWidth(28)
        self._btn_refresh.setToolTip("Refresh now")
        self._btn_refresh.clicked.connect(lambda: self.refresh_clicked.emit(self._path))
        hdr_lay.addWidget(self._btn_refresh)

        # Stop polling button
        self._btn_stop = _btn("■")
        self._btn_stop.setFixedWidth(28)
        self._btn_stop.setToolTip("Stop polling (disconnect)")
        self._btn_stop.clicked.connect(lambda: self.stop_clicked.emit(self._path))
        hdr_lay.addWidget(self._btn_stop)

        # Add Another Instance button
        btn_add_another = _btn("＋")
        btn_add_another.setFixedWidth(28)
        btn_add_another.setToolTip("Add another instance of this plugin (different device / IP)")
        btn_add_another.clicked.connect(lambda: self.add_another.emit(self._path))
        hdr_lay.addWidget(btn_add_another)

        # Log console toggle button (P3-3)
        self._btn_logs = QPushButton("≡")
        self._btn_logs.setFixedSize(28, 26)
        self._btn_logs.setCheckable(True)
        self._btn_logs.setToolTip("Show / hide plugin log")
        self._btn_logs.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_logs.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
            f"QPushButton:checked {{ background:{ACCENT}22; border-color:{ACCENT}; color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
        )
        self._btn_logs.toggled.connect(self._toggle_logs)
        hdr_lay.addWidget(self._btn_logs)

        # Configure button (P2-2) — only shown when plugin declares CONFIG_SCHEMA
        self._config_schema: dict = meta.get("config_schema", {}) or {}
        self._btn_configure = QPushButton("⚙")
        self._btn_configure.setFixedSize(28, 26)
        self._btn_configure.setCheckable(True)
        self._btn_configure.setToolTip("Configure plugin settings")
        self._btn_configure.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_configure.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
            f"QPushButton:checked {{ background:{ACCENT}22; border-color:{ACCENT}; color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
        )
        self._btn_configure.toggled.connect(self._toggle_config_panel)
        self._btn_configure.setVisible(bool(self._config_schema))
        hdr_lay.addWidget(self._btn_configure)

        # Rename button — inline display-name edit (P3-4)
        btn_rename = _btn("✎")
        btn_rename.setFixedWidth(28)
        btn_rename.setToolTip("Rename this plugin instance")
        btn_rename.clicked.connect(self._on_rename_btn)
        hdr_lay.addWidget(btn_rename)

        # Remove button
        btn_remove = _btn("✕")
        btn_remove.setFixedWidth(28)
        btn_remove.setToolTip("Remove this instance")
        btn_remove.clicked.connect(lambda: self.remove_clicked.emit(self._path))
        hdr_lay.addWidget(btn_remove)

        outer.addWidget(hdr)

        # ── Password row ──────────────────────────────────────────────────────
        pw_row = QFrame()
        pw_row.setObjectName("hubCardPwRow")
        pw_row.setStyleSheet(
            f"QFrame#hubCardPwRow {{ background:{BG_CARD}; border:none;"
            f" border-top:1px solid {BORDER}; border-radius:0px; }}"
        )
        pw_lay = QHBoxLayout(pw_row)
        pw_lay.setContentsMargins(40, 4, 10, 4)
        pw_lay.setSpacing(6)

        hw_ip_for_pw = meta.get("ip", "")
        pw_lbl = QLabel(f"Password ({hw_ip_for_pw or 'IP unknown'}):")
        pw_lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:9px; border:none;")
        pw_lay.addWidget(pw_lbl)

        self._pw_edit = QLineEdit()
        self._pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_edit.setPlaceholderText("enter password…")
        self._pw_edit.setFixedHeight(20)
        self._pw_edit.setFont(QFont("Segoe UI", 9))
        self._pw_edit.setStyleSheet(
            f"QLineEdit {{ background:{BG_DARK}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:0 6px; }}"
        )
        pw_lay.addWidget(self._pw_edit, 1)

        self._pw_status = QLabel("")
        self._pw_status.setStyleSheet(f"color:{GREEN}; font-size:9px; border:none;")
        self._pw_status.setFixedWidth(60)
        pw_lay.addWidget(self._pw_status)

        btn_pw_save = _btn("Save")
        btn_pw_save.setToolTip("Save password in OS keychain")
        btn_pw_save.clicked.connect(
            lambda: self._save_password(hw_ip_for_pw, self._pw_edit, self._pw_status)
        )
        pw_lay.addWidget(btn_pw_save)

        btn_pw_forget = _btn("Forget")
        btn_pw_forget.setToolTip("Remove saved password from OS keychain")
        btn_pw_forget.clicked.connect(
            lambda: self._forget_password(hw_ip_for_pw, self._pw_status)
        )
        pw_lay.addWidget(btn_pw_forget)
        outer.addWidget(pw_row)

        # Security note — reassure user password is not stored in plain text
        _sec_lbl = QLabel("🔒  Saved securely in the OS keychain — never written to disk or this file")
        _sec_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:9px; background:transparent; border:none;"
            " padding:0 0 2px 40px;"
        )
        outer.addWidget(_sec_lbl)

        # ── Detail panel (v2.1) ───────────────────────────────────────────────
        if self._hw_type == "modem":
            self._detail = _ModemDetailPanel()
        else:
            self._detail = _RouterDetailPanel()
        self._detail.setVisible(False)
        outer.addWidget(self._detail)

        # Log console panel (P3-3) — collapsible, hidden by default
        self._log_lines: collections.deque = collections.deque(maxlen=100)
        self._log_panel = QTextEdit()
        self._log_panel.setReadOnly(True)
        self._log_panel.setMaximumHeight(130)
        self._log_panel.setFont(QFont("Consolas", 8))
        self._log_panel.setStyleSheet(
            f"QTextEdit {{ background:{BG_DARK}; color:{TEXT_SECONDARY}; border:none;"
            f" border-top:1px solid {BORDER}; font-family:Consolas,monospace; }}"
        )
        self._log_panel.setVisible(False)
        outer.addWidget(self._log_panel)

        # Config panel (P2-2) — auto-generated from CONFIG_SCHEMA, hidden by default
        self._config_panel: Optional[QFrame] = None
        self._config_fields: dict = {}   # key → widget
        if self._config_schema:
            self._config_panel = self._build_config_panel(self._config_schema)
            self._config_panel.setVisible(False)
            outer.addWidget(self._config_panel)

        # Apply persisted result immediately if available
        if isinstance(last_result, dict):
            self._apply_result(last_result)

        # Apply persisted health state (circuit-breaker may already be tripped)
        self.refresh_health_ui()

    # ── Public interface ──────────────────────────────────────────────────────

    def update_result(self, data: dict, ts: float) -> None:
        self._last_ts = ts
        self._apply_result(data)

    def set_error(self, msg: str) -> None:
        import re as _re
        self._dot.setStyleSheet(f"color:{RED}; font-size:13px; border:none;")
        m = _re.search(r"pip install\s+(\S+)", msg)
        if m:
            self._pending_pkg = m.group(1)
            self._metrics_lbl.setText(f"Missing library: {self._pending_pkg}")
            self._btn_install.setText(f"⬇ Install {self._pending_pkg}")
            self._btn_install.setVisible(True)
            self._btn_update_cred.setVisible(False)
            self._btn_reimport.setVisible(False)
        elif msg.startswith("Authentication failed"):
            # P4-1: auth error — show credential update button, not circuit-breaker path
            self._pending_pkg = ""
            self._metrics_lbl.setText(f"Error: {msg[:80]}")
            self._btn_update_cred.setVisible(True)
            self._btn_reimport.setVisible(False)
        elif msg.startswith("Plugin file was moved or deleted"):
            # P6-2: file gone — show re-import button
            self._pending_pkg = ""
            self._metrics_lbl.setText("Plugin file not found — re-import required")
            self._btn_reimport.setVisible(True)
            self._btn_update_cred.setVisible(False)
            self._btn_install.setVisible(False)
        else:
            self._pending_pkg = ""
            self._metrics_lbl.setText(f"Error: {msg[:80]}")
            self._btn_update_cred.setVisible(False)
            self._btn_install.setVisible(False)
            self._btn_reimport.setVisible(False)
        self._metrics_lbl.setStyleSheet(
            f"color:{AMBER}; font-size:10px; border:none; background:transparent;"
        )
        self._btn_refresh.setEnabled(True)
        self._btn_refresh.setText("↻")

    def _on_install_dep(self) -> None:
        if not self._pending_pkg:
            return
        dlg = PipInstallDialog(self._pending_pkg, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._btn_install.setVisible(False)
            self._pending_pkg = ""
            self._metrics_lbl.setText("Library installed — reloading plugin…")
            self._metrics_lbl.setStyleSheet(
                f"color:{GREEN}; font-size:10px; border:none; background:transparent;"
            )
            # P1-6: signal the page to invalidate module cache and restart worker
            self.install_completed.emit(self._path)

    def set_refreshing(self, active: bool) -> None:
        self._btn_refresh.setEnabled(not active)
        self._btn_refresh.setText("…" if active else "↻")

    def tick_timestamp(self) -> None:
        if self._last_ts > 0:
            self._ts_lbl.setText(_age_str(self._last_ts))

    def refresh_health_ui(self) -> None:
        """Read persisted health state and update the dot colour + counter label."""
        import time as _t
        h = _load_health(self._path)
        total = h["success"] + h["errors"]

        if h.get("disabled"):
            self.mark_disabled()
            return

        # Circuit-breaker: degraded (amber) if no success in _DEGRADED_HOURS
        if h["success"] > 0 and h["last_ok"] > 0:
            hours_since = (_t.time() - h["last_ok"]) / 3600
            if hours_since > _DEGRADED_HOURS:
                self._dot.setStyleSheet(f"color:{AMBER}; font-size:13px; border:none;")
                self._dot.setToolTip(
                    f"Degraded — no successful poll in {int(hours_since)} h"
                )

        # Health counter label: "42/45" only after at least 3 polls
        if total >= 3:
            pct = int(100 * h["success"] / total) if total else 0
            colour = GREEN if pct >= 90 else AMBER if pct >= 60 else RED
            self._health_lbl.setText(f"{h['success']}/{total}")
            self._health_lbl.setStyleSheet(
                f"color:{colour}; font-size:9px; border:none; background:transparent;"
            )
            self._health_lbl.setVisible(True)
        else:
            self._health_lbl.setVisible(False)

    def mark_disabled(self) -> None:
        """Show the circuit-breaker 'Auto-disabled' state with a Re-enable button."""
        h = _load_health(self._path)
        self._dot.setStyleSheet(f"color:{RED}; font-size:13px; border:none;")
        self._metrics_lbl.setText(
            f"Auto-disabled after {h.get('consecutive', _CIRCUIT_BREAK_THRESHOLD)} errors"
        )
        self._metrics_lbl.setStyleSheet(
            f"color:{RED}; font-size:10px; border:none; background:transparent;"
        )
        self._btn_refresh.setEnabled(False)
        self._btn_reenable.setVisible(True)
        self._btn_install.setVisible(False)

    def _on_reenable(self) -> None:
        _reset_health(self._path)
        self._btn_reenable.setVisible(False)
        self._btn_refresh.setEnabled(True)
        self._dot.setStyleSheet(f"color:{TEXT_MUTED}; font-size:13px; border:none;")
        self._metrics_lbl.setText("Re-enabled — waiting for next poll…")
        self._metrics_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:10px; border:none; background:transparent;"
        )
        self.reenable_clicked.emit(self._path)

    # ── Private ───────────────────────────────────────────────────────────────

    def _apply_result(self, data: dict) -> None:
        if not isinstance(data, dict):
            return
        info    = data.get("info", {}) or {}
        status  = data.get("status", {}) or {}
        # Guard: QSettings round-trip can corrupt list-of-dicts to list-of-strings
        clients = [c for c in (data.get("clients") or []) if isinstance(c, dict)]
        extra   = status.get("extra", {}) or {}
        hw_type = info.get("type", self._hw_type)

        # If the plugin returned an error inside extra (e.g. missing pip package),
        # route it through set_error so the pip-install button appears if applicable.
        err_msg = extra.get("error", "")
        if err_msg:
            self.set_error(str(err_msg))
            return

        self._dot.setStyleSheet(f"color:{GREEN}; font-size:13px; border:none;")
        self._ts_lbl.setText(_age_str(self._last_ts))

        # Build metrics summary
        if hw_type == "modem":
            parts = []
            nt = extra.get("network_type")
            if nt:
                parts.append(nt)
            band = extra.get("nr5g_band") or extra.get("lte_band")
            if band:
                parts.append(band)
            rsrp = extra.get("nr5g_rsrp_dbm") or extra.get("lte_rsrp_dbm")
            if rsrp is not None:
                try:
                    parts.append(f"RSRP {float(rsrp):.0f} dBm")
                except (TypeError, ValueError):
                    pass
            sinr = extra.get("nr5g_sinr_db") or extra.get("lte_snr_db")
            if sinr is not None:
                try:
                    parts.append(f"SINR {float(sinr):.1f} dB")
                except (TypeError, ValueError):
                    pass
            summary = "  ·  ".join(parts) if parts else "Online"
            self._metrics_lbl.setText(summary)
            self._metrics_lbl.setStyleSheet(
                f"color:{TEXT_PRIMARY}; font-size:10px; border:none; background:transparent;"
            )
            if isinstance(self._detail, _ModemDetailPanel):
                self._detail.update(extra, status)
        else:
            n_nodes  = status.get("mesh_nodes") or 0
            n_cli    = status.get("connected_clients") or len(clients)
            parts = []
            if n_nodes:
                parts.append(f"{n_nodes} node{'s' if n_nodes != 1 else ''}")
            if n_cli is not None:
                parts.append(f"{n_cli} client{'s' if n_cli != 1 else ''}")
            summary = "  ·  ".join(parts) if parts else "Online"
            self._metrics_lbl.setText(summary)
            self._metrics_lbl.setStyleSheet(
                f"color:{TEXT_PRIMARY}; font-size:10px; border:none; background:transparent;"
            )
            if isinstance(self._detail, _RouterDetailPanel):
                self._detail.update(status, clients)

        self._btn_refresh.setEnabled(True)
        self._btn_refresh.setText("↻")
        self._btn_update_cred.setVisible(False)

        # Auto-expand detail on first successful result
        if not self._detail_visible:
            self._toggle_detail()

    def _toggle_detail(self) -> None:
        self._detail_visible = not self._detail_visible
        self._detail.setVisible(self._detail_visible)
        self._dot.setToolTip(
            "Click to collapse detail" if self._detail_visible else "Click to expand detail"
        )

    # ── Log console (P3-3) ────────────────────────────────────────────────────

    def append_log(self, line: str) -> None:
        """Append a structured log entry from the polling worker."""
        self._log_lines.append(line)
        try:
            self._log_panel.setPlainText("\n".join(self._log_lines))
            sb = self._log_panel.verticalScrollBar()
            sb.setValue(sb.maximum())
        except RuntimeError:
            pass  # QTextEdit deleted before the worker callback fired — safe to ignore

    def _toggle_logs(self, checked: bool) -> None:
        self._log_panel.setVisible(checked)

    # ── Config panel (P2-2) ───────────────────────────────────────────────────

    def _build_config_panel(self, schema: dict) -> QFrame:
        """Auto-generate a config form from a CONFIG_SCHEMA dict."""
        from PyQt6.QtWidgets import QFormLayout, QCheckBox, QSpinBox
        panel = QFrame()
        panel.setStyleSheet(
            f"QFrame {{ background:{BG_DARK}; border:none;"
            f" border-top:1px solid {BORDER}; }}"
        )
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(4)

        hdr = QLabel("Plugin Configuration")
        hdr.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:9px; font-weight:bold;"
            " border:none; background:transparent;"
        )
        lay.addWidget(hdr)

        form = QFormLayout()
        form.setSpacing(4)
        form.setContentsMargins(0, 2, 0, 2)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        saved = _load_instance_config(self._instance_id)

        _fss = (
            f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};"
            " border-radius:3px; padding:2px 5px; font-size:11px;"
        )

        for key, spec in schema.items():
            if not isinstance(spec, dict):
                continue
            label = spec.get("label", key)
            typ   = spec.get("type", "str")
            default = saved.get(key, spec.get("default", ""))

            if typ == "bool":
                w = QCheckBox()
                w.setChecked(bool(default))
                w.setStyleSheet("border:none; background:transparent;")
            elif typ == "int":
                w = QSpinBox()
                w.setRange(int(spec.get("min", 0)), int(spec.get("max", 99999)))
                try:
                    w.setValue(int(default))
                except (TypeError, ValueError):
                    w.setValue(int(spec.get("default", 0)))
                w.setStyleSheet(_fss)
                w.setFixedHeight(24)
            else:
                w = QLineEdit(str(default))
                w.setStyleSheet(_fss)
                w.setFixedHeight(24)

            self._config_fields[key] = w
            form.addRow(label, w)

        lay.addLayout(form)

        btn_save = _btn("Save", accent=True)
        btn_save.setFixedHeight(24)
        btn_save.clicked.connect(self._apply_config)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_save)
        lay.addLayout(btn_row)
        return panel

    def _toggle_config_panel(self, checked: bool) -> None:
        if self._config_panel is not None:
            self._config_panel.setVisible(checked)

    def _apply_config(self) -> None:
        """Read config field values and persist them."""
        from PyQt6.QtWidgets import QCheckBox, QSpinBox
        cfg: dict = {}
        for key, w in self._config_fields.items():
            if isinstance(w, QCheckBox):
                cfg[key] = w.isChecked()
            elif isinstance(w, QSpinBox):
                cfg[key] = w.value()
            else:
                cfg[key] = w.text()
        _save_instance_config(self._instance_id, cfg)
        self._btn_configure.setChecked(False)

    def _save_password(self, hw_ip: str, pw_edit: QLineEdit, status: QLabel) -> None:
        pw = pw_edit.text().strip()
        if not pw:
            status.setText("Empty!")
            status.setStyleSheet(f"color:{AMBER}; font-size:9px;")
            return
        if not hw_ip:
            status.setText("No IP")
            status.setStyleSheet(f"color:{AMBER}; font-size:9px;")
            return
        try:
            import keyring
            keyring.set_password("NetSentinel/hardware", hw_ip, pw)
            pw_edit.clear()
            status.setText("✓ Saved")
            status.setStyleSheet(f"color:{GREEN}; font-size:9px;")
            QTimer.singleShot(3000, lambda s=status: _safe_set_text(s, ""))
        except Exception as exc:
            status.setText("Error")
            status.setStyleSheet(f"color:{RED}; font-size:9px;")
            status.setToolTip(str(exc))

    def _forget_password(self, hw_ip: str, status: QLabel) -> None:
        if not hw_ip:
            return
        try:
            import keyring
            # Clear all services that a plugin might read credentials from
            for service in ("NetSentinel/hardware", "NetSentinel/modem", "NetSentinel/mesh"):
                try:
                    keyring.delete_password(service, hw_ip)
                except Exception:
                    pass
            status.setText("Forgotten")
            status.setStyleSheet(f"color:{TEXT_MUTED}; font-size:9px;")
        except Exception:
            status.setText("Not saved")
            status.setStyleSheet(f"color:{TEXT_MUTED}; font-size:9px;")
        QTimer.singleShot(3000, lambda s=status: _safe_set_text(s, ""))

    def _on_rename_btn(self) -> None:
        """P3-4: Inline rename — prompt for a new display name, update card and emit signal."""
        from PyQt6.QtWidgets import QInputDialog
        current_name = self._meta.get("name", Path(self._path).stem)
        new_name, ok = QInputDialog.getText(
            self, "Rename Plugin",
            "Display name:", text=current_name,
        )
        new_name = new_name.strip()
        if not ok or not new_name or new_name == current_name:
            return
        self._meta = dict(self._meta)
        self._meta["name"] = new_name
        self._name_lbl.setText(f"<b>{new_name}</b>")
        self.rename_requested.emit(self._instance_id, current_name, new_name)


# ── Step-guide helper widgets (guide section) ─────────────────────────────────

def _step_card(number: int, title: str) -> tuple[QWidget, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("hubStepCard")
    frame.setStyleSheet(
        f"QFrame#hubStepCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
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
    QTimer.singleShot(2000, lambda: btn.setText(orig))


def _code_chip(code: str) -> QWidget:
    frame = QFrame()
    frame.setStyleSheet(
        f"background:{BG_DARK}; border:1px solid {BORDER}; border-radius:3px;"
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
    frame = QFrame()
    frame.setStyleSheet(
        f"background:{BG_DARK}; border:1px solid {BORDER}; border-radius:4px;"
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


# ── Main page ─────────────────────────────────────────────────────────────────

class HardwareIntegrationPage(QWidget):
    """Hardware Hub — live status dashboard for all imported hardware plugins."""

    # data dict has "_path" embedded so dashboard knows which plugin
    plugin_result    = pyqtSignal(dict)
    plugin_page_added = pyqtSignal(str, str)  # (script_path, display_label) — new plugin installed at runtime
    plugin_page_removed = pyqtSignal(str)     # script_path — plugin removed at runtime
    plugin_renamed   = pyqtSignal(str, str, str)  # (path, old_label, new_label) — instance display name changed
    navigate_to      = pyqtSignal(str)   # page label → _nav_rail_go_to
    geo_map_ip       = pyqtSignal(str)   # open geo map for this IP
    port_scan_ip     = pyqtSignal(str)   # pre-fill port scanner with this IP
    check_abuse_ip   = pyqtSignal(str)   # check IP on AbuseIPDB

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._poll_workers: Dict[str, PluginPollingWorker] = {}
        self._cards:   Dict[str, HubCard] = {}
        # Tab indices — set by _build_ui
        self._tabs: Optional[QTabWidget] = None
        self._suggested_tab_idx: int = 1
        self._suggested_lay:  Optional[QVBoxLayout]        = None

        self._build_ui()

        # Tick timer — updates "X min ago" labels every 30s
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(30_000)
        self._tick_timer.timeout.connect(self._tick_timestamps)
        self._tick_timer.start()

        # P6-4: file watcher — detects plugin edits (trigger re-poll) and deletions (FILE: error)
        self._file_watcher = QFileSystemWatcher(self)
        self._file_watcher.fileChanged.connect(self._on_plugin_file_changed)

        # Start persistent poll workers for all imported plugins, staggered 3 s apart
        self._start_all_poll_workers()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 8)
        root.setSpacing(8)

        # Page header — outside tabs so it's always visible
        hdr_row = QHBoxLayout()
        title = QLabel("Hardware")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY};")
        hdr_row.addWidget(title)
        hdr_row.addStretch()
        self._btn_new_plugin = _btn("⬡  New Plugin")
        self._btn_new_plugin.setToolTip(
            "Launch the wizard to create a new plugin script from a template"
        )
        self._btn_new_plugin.clicked.connect(self._on_create_plugin)
        hdr_row.addWidget(self._btn_new_plugin)

        self._btn_add = _btn("＋  Add Integration", accent=True)
        self._btn_add.clicked.connect(self._on_browse)
        hdr_row.addWidget(self._btn_add)

        # P3-5: Import .nspkg bundle
        self._btn_nspkg = _btn("⬡  Import .nspkg")
        self._btn_nspkg.setToolTip("Import a .nspkg plugin bundle (ZIP containing plugin.py + manifest.json)")
        self._btn_nspkg.clicked.connect(self._on_import_nspkg)
        hdr_row.addWidget(self._btn_nspkg)

        root.addLayout(hdr_row)

        # Status label (import feedback) — outside tabs
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"font-size:10px; color:{TEXT_MUTED};")
        root.addWidget(self._status_lbl)

        # ── Tab widget ────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            f"QTabWidget::pane {{ border:1px solid {BORDER}; border-radius:4px; }}"
            f"QTabBar::tab {{ background:{BG_CARD}; color:{TEXT_MUTED};"
            f" padding:5px 14px; border:none; border-bottom:2px solid transparent; }}"
            f"QTabBar::tab:selected {{ color:{TEXT_PRIMARY};"
            f" border-bottom:2px solid {ACCENT}; }}"
            f"QTabBar::tab:hover {{ color:{TEXT_PRIMARY}; }}"
        )
        root.addWidget(self._tabs, 1)

        # ── Tab 0: Hardware (HubCards + guide) — always visible ──────────────
        hub_tab = QWidget()
        hub_tab.setStyleSheet(f"background:{BG_DARK};")
        hub_tab_lay = QVBoxLayout(hub_tab)
        hub_tab_lay.setContentsMargins(0, 6, 0, 0)
        hub_tab_lay.setSpacing(6)

        sub = QLabel(
            "Live status for all integrated hardware. "
            "Modem plugins refresh every 60 s · router/AP every 2 min · switch every 5 min. "
            "Click ● to expand the signal / topology detail panel."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px; padding:0 8px;")
        hub_tab_lay.addWidget(sub)

        self._hub_scroll = QScrollArea()
        self._hub_scroll.setWidgetResizable(True)
        self._hub_scroll.setStyleSheet("QScrollArea { border: none; }")
        self._hub_body = QWidget()
        self._hub_body.setStyleSheet(f"background:{BG_DARK};")
        self._hub_lay = QVBoxLayout(self._hub_body)
        self._hub_lay.setContentsMargins(0, 4, 0, 4)
        self._hub_lay.setSpacing(8)
        self._rebuild_hub()
        self._hub_scroll.setWidget(self._hub_body)
        hub_tab_lay.addWidget(self._hub_scroll, 3)

        guide_toggle_row = QHBoxLayout()
        guide_toggle_row.setContentsMargins(8, 0, 8, 0)
        self._guide_toggle = _btn("▶  How to write a plugin script")
        self._guide_toggle.clicked.connect(self._toggle_guide)
        guide_toggle_row.addWidget(self._guide_toggle)
        guide_toggle_row.addStretch()
        hub_tab_lay.addLayout(guide_toggle_row)

        self._guide_area = QScrollArea()
        self._guide_area.setWidgetResizable(True)
        self._guide_area.setStyleSheet("QScrollArea { border: none; }")
        self._guide_area.setVisible(False)
        guide_body = QWidget()
        guide_body.setStyleSheet(f"background:{BG_DARK};")
        guide_lay = QVBoxLayout(guide_body)
        guide_lay.setContentsMargins(0, 4, 0, 8)
        guide_lay.setSpacing(10)
        guide_lay.addWidget(self._build_step1())
        guide_lay.addWidget(self._build_step2())
        guide_lay.addWidget(self._build_step3_guide())
        guide_lay.addWidget(self._build_step4())
        guide_lay.addStretch()
        self._guide_area.setWidget(guide_body)
        hub_tab_lay.addWidget(self._guide_area, 2)

        if not _load_paths():
            self._guide_area.setVisible(True)
            self._guide_toggle.setText("▼  How to write a plugin script")

        self._tabs.addTab(hub_tab, "Hardware")

        # ── Tab 1: Suggested — hidden until hw_detect finds matches ───────────
        suggested_tab = QWidget()
        suggested_tab.setStyleSheet(f"background:{BG_DARK};")
        suggested_outer = QVBoxLayout(suggested_tab)
        suggested_outer.setContentsMargins(0, 0, 0, 0)
        suggested_outer.setSpacing(0)

        sug_hdr = QFrame()
        sug_hdr.setObjectName("hubSugHdr")
        sug_hdr.setStyleSheet(
            f"QFrame#hubSugHdr {{ background:{BG_CARD}; border:none;"
            f" border-bottom:1px solid {BORDER}; }}"
        )
        sug_hdr_lay = QHBoxLayout(sug_hdr)
        sug_hdr_lay.setContentsMargins(12, 7, 10, 7)
        sug_title = QLabel("Suggested for your network")
        sug_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        sug_title.setStyleSheet(f"color:{AMBER}; border:none; background:transparent;")
        sug_hdr_lay.addWidget(sug_title)
        sug_hdr_lay.addStretch()
        suggested_outer.addWidget(sug_hdr)

        sug_scroll = QScrollArea()
        sug_scroll.setWidgetResizable(True)
        sug_scroll.setStyleSheet("QScrollArea { border: none; }")
        sug_inner = QWidget()
        sug_inner.setStyleSheet(f"background:{BG_DARK};")
        self._suggested_lay = QVBoxLayout(sug_inner)
        self._suggested_lay.setContentsMargins(0, 2, 0, 6)
        self._suggested_lay.setSpacing(0)
        sug_scroll.setWidget(sug_inner)
        suggested_outer.addWidget(sug_scroll)

        self._suggested_tab_idx = self._tabs.addTab(suggested_tab, "Suggested")
        self._tabs.setTabVisible(self._suggested_tab_idx, False)

        # ── Tab 2: Browse community plugins (P3-4) ────────────────────────────
        self._browse_index_thread: Optional[QThread] = None
        self._browse_tab_idx = self._tabs.addTab(self._build_browse_tab(), "Browse")

    def _toggle_guide(self) -> None:
        visible = not self._guide_area.isVisible()
        self._guide_area.setVisible(visible)
        self._guide_toggle.setText(
            "▼  How to write a plugin script" if visible
            else "▶  How to write a plugin script"
        )

    # ── Browse tab (P3-4 community plugin index) ──────────────────────────────

    # URL of the community plugin index JSON.  Override by setting
    # QSettings("NetSentinel","NetSentinel")["hardware/community_index_url"].
    _DEFAULT_COMMUNITY_URL = (
        "https://raw.githubusercontent.com/netsentinel/"
        "netsentinel-plugins/main/index.json"
    )

    def _build_browse_tab(self) -> QWidget:
        tab = QWidget()
        tab.setStyleSheet(f"background:{BG_DARK};")
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        # Toolbar
        bar = QHBoxLayout()
        title = QLabel("Community Plugins")
        title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY}; border:none;")
        bar.addWidget(title)
        bar.addStretch()
        self._browse_status = QLabel("Press Refresh to fetch the index.")
        self._browse_status.setStyleSheet(f"color:{TEXT_MUTED}; font-size:10px; border:none;")
        bar.addWidget(self._browse_status)
        btn_refresh = _btn("↻  Refresh")
        btn_refresh.clicked.connect(self._fetch_community_index)
        bar.addWidget(btn_refresh)
        lay.addLayout(bar)

        # Plugin card area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        self._browse_inner = QWidget()
        self._browse_inner.setStyleSheet(f"background:{BG_DARK};")
        self._browse_lay = QVBoxLayout(self._browse_inner)
        self._browse_lay.setContentsMargins(0, 4, 0, 4)
        self._browse_lay.setSpacing(4)
        self._browse_lay.addStretch()
        scroll.setWidget(self._browse_inner)
        lay.addWidget(scroll, 1)

        return tab

    def _fetch_community_index(self) -> None:
        """Fetch community index JSON in a background thread."""
        if self._browse_index_thread is not None and self._browse_index_thread.isRunning():
            return
        url = (
            QSettings("NetSentinel", "NetSentinel")
            .value("hardware/community_index_url", self._DEFAULT_COMMUNITY_URL)
        )
        self._browse_status.setText("Fetching index…")
        self._browse_index_thread = _CommunityIndexThread(url, parent=self)
        self._browse_index_thread.done.connect(self._on_community_index_done,
                                                Qt.ConnectionType.QueuedConnection)
        self._browse_index_thread.error.connect(self._on_community_index_error,
                                                 Qt.ConnectionType.QueuedConnection)
        self._browse_index_thread.start()

    @pyqtSlot(list)
    def _on_community_index_done(self, entries: list) -> None:
        self._browse_status.setText(f"{len(entries)} plugin(s) found.")
        self._rebuild_browse_cards(entries)

    @pyqtSlot(str)
    def _on_community_index_error(self, msg: str) -> None:
        self._browse_status.setText(f"Error: {msg}")

    def _rebuild_browse_cards(self, entries: list) -> None:
        # Remove existing cards (keep the trailing stretch)
        while self._browse_lay.count() > 1:
            item = self._browse_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for entry in entries:
            card = self._build_community_card(entry)
            self._browse_lay.insertWidget(self._browse_lay.count() - 1, card)

    def _build_community_card(self, entry: dict) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 8, 10, 8)
        lay.setSpacing(10)

        info = QVBoxLayout()
        name_lbl = QLabel(f"<b>{entry.get('name', 'Unknown')}</b>")
        name_lbl.setTextFormat(Qt.TextFormat.RichText)
        name_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; border:none; background:transparent;")
        info.addWidget(name_lbl)

        author = entry.get("author", "")
        pypi   = entry.get("pypi", "")
        meta_parts = [p for p in [f"by {author}" if author else "", f"pip: {pypi}" if pypi else ""] if p]
        sub = QLabel("  ·  ".join(meta_parts))
        sub.setStyleSheet(f"color:{TEXT_MUTED}; font-size:9px; border:none; background:transparent;")
        info.addWidget(sub)

        desc = entry.get("desc", entry.get("description", ""))
        if desc:
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px; border:none; background:transparent;")
            desc_lbl.setWordWrap(True)
            info.addWidget(desc_lbl)

        lay.addLayout(info, 1)

        btn_install = _btn("⬇ Install", accent=True)
        has_url = bool(entry.get("file_url"))
        btn_install.setEnabled(has_url)
        if not has_url:
            btn_install.setToolTip("No download URL provided")
        btn_install.clicked.connect(lambda _=False, e=entry: self._install_community_plugin(e))
        lay.addWidget(btn_install)
        return card

    def _install_community_plugin(self, entry: dict) -> None:
        """Download, SHA-256 verify, and import a community plugin."""
        file_url  = entry.get("file_url", "")
        expected  = entry.get("sha256", "")
        name      = entry.get("name", "plugin")

        if not file_url:
            self._set_status("No download URL for this plugin.", error=True)
            return

        self._browse_status.setText(f"Downloading {name}…")
        thread = _CommunityDownloadThread(file_url, expected, name, parent=self)
        thread.done.connect(
            lambda path: self._on_community_download_done(path, entry),
            Qt.ConnectionType.QueuedConnection,
        )
        thread.error.connect(
            lambda msg: self._on_community_download_error(msg),
            Qt.ConnectionType.QueuedConnection,
        )
        # Keep a reference so it isn't GC'd
        self._browse_index_thread = thread
        thread.start()

    @pyqtSlot(str)
    def _on_community_download_done(self, plugin_path: str, entry: dict) -> None:
        self._browse_status.setText(f"Downloaded — importing '{entry.get('name', plugin_path)}'…")
        self._import_bundled(plugin_path)

    @pyqtSlot(str)
    def _on_community_download_error(self, msg: str) -> None:
        self._browse_status.setText(f"Download error: {msg}")

    # ── Hub management ────────────────────────────────────────────────────────

    @staticmethod
    def _bundled_plugins_dir() -> Path:
        return Path(__file__).parent.parent.parent / "plugins"

    def _rebuild_hub(self) -> None:
        # Remove all existing card widgets
        while self._hub_lay.count():
            item = self._hub_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()

        # ── Catalog: bundled plugins not yet imported ─────────────────────────
        self._rebuild_catalog()

        # ── Active integrations ───────────────────────────────────────────────
        instances = _load_instances()

        if not instances:
            empty = QLabel(
                "No hardware imported yet.\n"
                "Click  ＋ Add Integration  to import a script."
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                f"color:{TEXT_MUTED}; font-size:11px; padding:24px 0;"
            )
            self._hub_lay.addWidget(empty)
        else:
            for inst in instances:
                path = inst["path"]
                ok, _, meta = _validate_script(path)
                if not ok:
                    meta = {"name": Path(path).stem, "type": "unknown", "ip": ""}
                last_result = _load_last_result(inst["id"])
                card = HubCard(
                    path, meta, last_result,
                    instance_id=inst["id"],
                    display_name=inst.get("name", ""),
                    instance_ip=inst.get("ip", ""),
                    parent=self._hub_body,
                )
                card.refresh_clicked.connect(self._run_plugin)
                card.remove_clicked.connect(self._remove_plugin)
                card.stop_clicked.connect(self._stop_poll_worker)
                card.reenable_clicked.connect(self._on_reenable_plugin)
                card.install_completed.connect(self._on_install_completed)
                card.add_another.connect(self._on_add_another_instance)
                card.update_credentials_clicked.connect(self._on_update_credentials)
                card.reimport_clicked.connect(self._on_reimport_plugin)
                card.rename_requested.connect(self._on_rename_card)
                self._hub_lay.addWidget(card)
                # Key by instance_id so multiple instances of same plugin coexist
                self._cards[inst["id"]] = card

        self._hub_lay.addStretch()

    def _rebuild_catalog(self) -> None:
        """Inject catalog cards for bundled plugins that are not yet imported."""
        bdir = self._bundled_plugins_dir()
        if not bdir.is_dir():
            return
        imported = {inst["path"] for inst in _load_instances()}
        entries: list[tuple[str, dict]] = []
        for pyf in sorted(bdir.glob("*_plugin.py")):
            if "template" in pyf.stem.lower():
                continue
            ps = str(pyf)
            if ps in imported:
                continue
            ok, _, meta = _validate_script(ps)
            if ok:
                entries.append((ps, meta))
        if not entries:
            return

        # Section header
        hdr_lbl = QLabel("AVAILABLE PLUGINS")
        hdr_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:10px; font-weight:bold;"
            " letter-spacing:0.5px; padding:4px 8px 2px 8px;"
        )
        self._hub_lay.addWidget(hdr_lbl)

        for path, meta in entries:
            self._hub_lay.addWidget(self._build_catalog_card(path, meta))

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(
            f"border:none; border-top:1px solid {BORDER}; background:transparent;"
        )
        sep.setFixedHeight(1)
        self._hub_lay.addWidget(sep)

    def _build_catalog_card(self, path: str, meta: dict) -> QFrame:
        _TYPE_ICON = {"modem": "📡", "router": "🔀", "ap": "📶",
                      "switch": "🔗", "other": "🔌"}
        card = QFrame()
        card.setObjectName("hubCatalogCard")
        card.setStyleSheet(
            f"QFrame#hubCatalogCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:4px; }}"
        )
        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        # Use PNG icon if available (P2-3), else fall back to emoji type icon
        icon_path = meta.get("icon_path", "")
        icon_widget_added = False
        if icon_path:
            try:
                px = QPixmap(icon_path).scaled(
                    24, 24,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                if not px.isNull():
                    icon_lbl = QLabel()
                    icon_lbl.setPixmap(px)
                    icon_lbl.setFixedSize(26, 26)
                    icon_lbl.setStyleSheet("background:transparent; border:none;")
                    lay.addWidget(icon_lbl)
                    icon_widget_added = True
            except Exception:
                pass
        if not icon_widget_added:
            icon_lbl = QLabel(_TYPE_ICON.get(meta.get("type", ""), "🔌"))
            icon_lbl.setFixedWidth(22)
            icon_lbl.setStyleSheet("background:transparent; border:none;")
            lay.addWidget(icon_lbl)

        txt = QVBoxLayout()
        txt.setSpacing(1)
        name_lbl = QLabel(meta.get("name", Path(path).stem))
        name_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:12px; font-weight:bold;"
            " background:transparent; border:none;"
        )
        txt.addWidget(name_lbl)
        desc = meta.get("description", "")
        if desc:
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(
                f"color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;"
            )
            desc_lbl.setWordWrap(True)
            txt.addWidget(desc_lbl)
        lay.addLayout(txt, 1)

        ip_lbl = QLabel(meta.get("ip", ""))
        ip_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:10px; background:transparent; border:none;"
        )
        lay.addWidget(ip_lbl)

        add_btn = QPushButton("＋  Add")
        add_btn.setFixedHeight(26)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#fff; border:none;"
            " border-radius:3px; font-size:11px; padding:0 12px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        add_btn.clicked.connect(lambda _, p=path: self._import_bundled(p))
        lay.addWidget(add_btn)
        return card

    def _register_plugin(self, path: str, source: str = "browse") -> None:
        """Unified plugin registration pipeline — all entry points call this.

        Steps (always in this order, regardless of source):
        1. Validate script
        2. Check and install PYPI deps
        3. Copy to AppData stable path
        4. Show credential dialog → live test → capture confirmed IP
        5. Write instance registry entry using confirmed IP
        6. Rebuild hub card
        7. Start poll worker
        8. Emit plugin_page_added → nav updates

        source: "browse" | "bundled" | "community" | "nspkg"
        """
        ok, msg, meta = _validate_script(path)
        if not ok:
            self._set_status(f"Validation failed: {msg}", error=True)
            return

        # Step 2: PYPI dependency check and install
        pypi_pkg = meta.get("pypi_package", "")
        if pypi_pkg:
            import importlib.util
            module_name = pypi_pkg.replace("-", "_")
            if importlib.util.find_spec(module_name) is None:
                dlg = PipInstallDialog(pypi_pkg, parent=self)
                if dlg.exec() != QDialog.DialogCode.Accepted:
                    self._set_status("Dependency install cancelled.", error=True)
                    return
                import importlib
                importlib.invalidate_caches()
                if importlib.util.find_spec(module_name) is None:
                    self._set_status(
                        f"'{pypi_pkg}' still not importable — check pip output.",
                        error=True,
                    )
                    return

        # Step 3: copy to stable AppData plugins dir.
        # Bundled/frozen plugins live in a _MEI* temp dir recreated each launch.
        # Browse plugins may be anywhere on disk.  Both are copied once to
        # get_app_data_dir()/plugins/ so the stored path is always valid.
        import shutil as _shutil
        from modules.utils import get_app_data_dir as _gad
        try:
            _dest_dir = _gad() / "plugins"
            _dest_dir.mkdir(parents=True, exist_ok=True)
            _dest = _dest_dir / Path(path).name
            if Path(path).resolve() != _dest.resolve():
                _shutil.copy2(path, _dest)
            path = str(_dest)
        except Exception as _exc:
            self._set_status(f"Failed to install plugin: {_exc}", error=True)
            return

        # Step 4: credential dialog
        cred_label = meta.get("credential_label", "")
        hw_ip      = meta.get("ip", "")
        if cred_label and hw_ip:
            try:
                import keyring as _kr
                existing_pw = _kr.get_password("NetSentinel/hardware", hw_ip)
            except Exception:
                existing_pw = None
            if not existing_pw:
                accepted, confirmed_ip = self._show_credential_dialog(
                    meta.get("name", Path(path).stem), hw_ip, cred_label,
                    plugin_path=path,
                )
                if not accepted:
                    self._set_status("Setup cancelled.", error=True)
                    return
                hw_ip = confirmed_ip or hw_ip

        # Step 5: instance registry
        label   = meta.get("name", Path(path).stem)
        inst_ip = hw_ip
        instances = _load_instances()
        inst_id = _instance_id(path, inst_ip or path)
        is_new  = not any(i["id"] == inst_id for i in instances)
        if is_new:
            instances.append({"id": inst_id, "path": path, "ip": inst_ip, "name": label})
            _save_instances(instances)

        # Steps 6–8: rebuild, start, emit
        self._set_status(f"Imported '{label}' — running first check…", error=False)
        self._rebuild_hub()
        self._start_poll_worker_inst(inst_id)
        if is_new:
            self.plugin_page_added.emit(path, label)

    def _import_bundled(self, path: str) -> None:
        """Add a bundled plugin — delegates to the unified registration pipeline."""
        self._register_plugin(path, source="bundled")

    def _show_credential_dialog(self, name: str, default_ip: str, cred_label: str,
                                plugin_path: str = "") -> tuple[bool, str]:
        """Credential dialog with live connection test.

        Shows IP + password fields.  The primary button ("Test & Add") runs a
        live connection test in a background thread before accepting.  The dialog
        only closes with Accepted after a successful test, so the plugin is never
        registered when it cannot connect.

        Returns (accepted, confirmed_ip).  confirmed_ip is the IP the user
        actually entered (may differ from default_ip), or "" on cancel.
        """
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout
        dlg = QDialog(self)
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

        keyring_note = QLabel("🔒  Password saved to OS keychain — never written to disk")
        keyring_note.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:9px;")
        lay.addWidget(keyring_note)

        # ── Status area ───────────────────────────────────────────────────────
        status_lbl = QLabel("")
        status_lbl.setWordWrap(True)
        status_lbl.setVisible(False)
        status_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY}; padding:4px 0;")
        lay.addWidget(status_lbl)

        # ── Buttons ───────────────────────────────────────────────────────────
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

        # "Add Without Testing" — hidden initially; appears after a live-test failure
        # so the user can still register when the device is temporarily offline.
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

        # ── Live-test logic ───────────────────────────────────────────────────
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
                    # Per-instance namespace (P4-2)
                    iid = _instance_id(plugin_path or ip, ip)
                    _kr.set_password("NetSentinel/plugin", iid, pw)
                    # Legacy namespace for backwards-compat
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
                    # Per-instance namespace (P4-2)
                    iid = _instance_id(plugin_path or ip, ip)
                    _kr.set_password("NetSentinel/plugin", iid, pw)
                    # Legacy namespace for backwards-compat
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
                skip_btn.setVisible(True)  # offer skip only after a real failure

            tester.success.connect(_on_success, Qt.ConnectionType.QueuedConnection)
            tester.failure.connect(_on_failure, Qt.ConnectionType.QueuedConnection)
            tester.start()

        skip_btn.clicked.connect(_save_and_accept)
        test_btn.clicked.connect(_run_test)
        pw_edit.returnPressed.connect(_run_test)

        result = dlg.exec()
        confirmed_ip = ip_edit.text().strip()

        # Stop any running tester
        for t in _tester:
            if t.isRunning():
                t.wait(500)

        accepted = result == QDialog.DialogCode.Accepted
        return accepted, (confirmed_ip if accepted else "")

    def _start_all_poll_workers(self) -> None:
        self._migrate_stale_paths()
        for i, inst in enumerate(_load_instances()):
            inst_id = inst["id"]
            QTimer.singleShot(100, lambda iid=inst_id: self._smoke_check_deps_inst(iid))
            QTimer.singleShot(
                i * 3000, lambda iid=inst_id: self._start_poll_worker_inst(iid)
            )

    def _smoke_check_deps(self, path: str) -> None:
        """Check PYPI_PACKAGE dep; set card to error immediately if missing."""
        ok, _, meta = _validate_script(path)
        if not ok:
            return
        pypi_pkg = meta.get("pypi_package", "")
        if not pypi_pkg:
            return
        import importlib.util
        module_name = pypi_pkg.replace("-", "_")
        if importlib.util.find_spec(module_name) is not None:
            return
        err_msg = f"DEPS: {pypi_pkg} not installed. Run: pip install {pypi_pkg}"
        # Cards are keyed by instance_id now; look across all cards for this path
        for inst_id, card in self._cards.items():
            if card._path == path:
                card.set_error(_classify_error(err_msg))

    def _smoke_check_deps_inst(self, instance_id: str) -> None:
        inst = next((i for i in _load_instances() if i["id"] == instance_id), None)
        if inst:
            self._smoke_check_deps(inst["path"])

    def _migrate_stale_paths(self) -> None:
        """Delegate to the module-level _migrate_stale_paths() helper."""
        _migrate_stale_paths()

    def _start_poll_worker(self, path: str) -> None:
        """Start a worker for the first instance whose path matches."""
        for inst in _load_instances():
            if inst["path"] == path:
                self._start_poll_worker_inst(inst["id"])
                return

    def _start_poll_worker_inst(self, instance_id: str) -> None:
        if instance_id in self._poll_workers:
            return
        inst = next((i for i in _load_instances() if i["id"] == instance_id), None)
        if inst is None:
            return
        path = inst["path"]

        # P4-2: verify bundled plugin signature before execution
        try:
            from modules.plugin_tools import verify_signature as _vsig
            _signed, _sig_msg = _vsig(path)
            if "MISMATCH" in _sig_msg:
                card = self._cards.get(instance_id)
                if card:
                    card.set_error(
                        f"ERR: Plugin hash mismatch — possible tampering. "
                        f"Re-import the original plugin or reinstall NetSentinel."
                    )
                return
        except Exception:
            pass  # hash DB unavailable — proceed without check

        ok, _, meta = _validate_script(path)
        hw_type = meta.get("type", "other") if ok else "other"
        saved_config = _load_instance_config(instance_id)
        worker = PluginPollingWorker(
            path=path, hw_type=hw_type,
            instance_id=instance_id,
            instance_ip=inst.get("ip", ""),
            config=saved_config or None,
            parent=self,
        )
        worker.result.connect(
            lambda data, iid=instance_id: self._on_plugin_result(iid, data),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda msg, iid=instance_id: self._on_plugin_error(iid, msg),
            Qt.ConnectionType.QueuedConnection,
        )
        # P3-3: wire log output to the card's console panel
        card = self._cards.get(instance_id)
        if card is not None:
            worker.log_line.connect(
                lambda line, c=card: c.append_log(line),
                Qt.ConnectionType.QueuedConnection,
            )
        worker.start()
        self._poll_workers[instance_id] = worker
        # P6-4: watch plugin file for changes / deletion
        if Path(path).exists() and path not in self._file_watcher.files():
            self._file_watcher.addPath(path)

    def _stop_poll_worker(self, path_or_id: str) -> None:
        """Stop by instance_id (preferred) or by path (legacy)."""
        # Try direct instance_id lookup first
        worker = self._poll_workers.pop(path_or_id, None)
        if worker is None:
            # Fallback: find by path
            for iid, w in list(self._poll_workers.items()):
                if getattr(w, "_path", "") == path_or_id:
                    self._poll_workers.pop(iid, None)
                    worker = w
                    break
        if worker:
            worker.stop()
            worker.wait(2000)

    @pyqtSlot(str)
    def _on_reimport_plugin(self, path: str) -> None:
        """P6-2: Plugin file gone — open file browser so user can locate the new path."""
        self._on_browse()

    @pyqtSlot(str)
    def _on_add_another_instance(self, path: str) -> None:
        """Add a second instance of the same plugin type with a different IP."""
        ok, _, meta = _validate_script(path)
        if not ok:
            return
        cred_label = meta.get("credential_label", "Password")
        default_ip = meta.get("ip", "")
        hw_name    = meta.get("name", Path(path).stem)

        # Show credential dialog; IP field is editable so user sets the new device IP.
        # The confirmed_ip returned is what the user actually typed.
        accepted, confirmed_ip = self._show_credential_dialog(
            f"{hw_name} (new instance)", default_ip, cred_label, plugin_path=path
        )
        if not accepted:
            return

        inst_ip = confirmed_ip or default_ip
        instances = _load_instances()
        existing_names = [i["name"] for i in instances if i["path"] == path]
        idx  = len(existing_names) + 1
        name = f"{hw_name} #{idx}"

        inst_id = _instance_id(path, inst_ip)
        new_inst = {"id": inst_id, "path": path, "ip": inst_ip, "name": name}
        instances.append(new_inst)
        _save_instances(instances)
        self._rebuild_hub()
        self._start_poll_worker_inst(inst_id)
        self.plugin_page_added.emit(path, name)

    @pyqtSlot()
    def _tick_timestamps(self) -> None:
        for card in self._cards.values():
            card.tick_timestamp()

    # ── Plugin execution ──────────────────────────────────────────────────────

    @pyqtSlot(str)
    def _run_plugin(self, path: str) -> None:
        """Trigger an immediate poll — called by Refresh button or import."""
        card = self._cards.get(path)
        if card:
            card.set_refreshing(True)
        worker = self._poll_workers.get(path)
        if worker and worker.isRunning():
            worker.trigger_now()
        else:
            self._start_poll_worker(path)

    def _on_plugin_result(self, instance_id: str, data: dict) -> None:
        ts = time.time()
        data["_ts"] = ts
        data["_instance_id"] = instance_id
        # Resolve path for backwards-compat fields
        inst = next((i for i in _load_instances() if i["id"] == instance_id), None)
        path = inst["path"] if inst else instance_id
        data["_path"] = path
        _save_last_result(instance_id, data)
        err_in_data = (data.get("status") or {}).get("extra", {}).get("error", "")
        if err_in_data:
            h = _record_error(instance_id, err_in_data)
            if h.get("disabled"):
                self._stop_poll_worker(instance_id)
        else:
            _record_success(instance_id)
        card = self._cards.get(instance_id)
        if card:
            card.update_result(data, ts)
            card.refresh_health_ui()
        self.plugin_result.emit(data)

    def _instance_id_for_path(self, path: str) -> "str | None":
        """Return the instance_id whose card._path matches *path*, or None."""
        for iid, card in self._cards.items():
            if card._path == path:
                return iid
        return None

    @pyqtSlot(str)
    def _on_plugin_file_changed(self, path: str) -> None:
        """P6-4: QFileSystemWatcher callback — plugin file was modified or deleted.

        File modified → re-add the watch path (OS removes it after notification on some
        platforms) then trigger an immediate re-poll so the worker picks up the new code.
        File deleted  → emit FILE: error to the card immediately without waiting for the
        next poll cycle.
        """
        if Path(path).exists():
            # OS may have removed the path from the watcher after the change event
            if path not in self._file_watcher.files():
                self._file_watcher.addPath(path)
            # Wake the worker immediately to pick up the edited plugin
            for iid, worker in self._poll_workers.items():
                if getattr(worker, "_path", "") == path and worker.isRunning():
                    worker.trigger_now()
                    break
        else:
            # File deleted — surface the error on the card right away
            inst_id = self._instance_id_for_path(path)
            if inst_id:
                self._on_plugin_error(inst_id, f"FILE: plugin file not found at {path}")

    def _on_plugin_error(self, instance_id: str, msg: str) -> None:
        h = _record_error(instance_id, msg)
        card = self._cards.get(instance_id)
        if card:
            classified = _classify_error(msg)
            card.set_error(classified)
            card.refresh_health_ui()
            if h.get("disabled"):
                self._stop_poll_worker(instance_id)
                card.mark_disabled()

    # ── Health / re-enable / reload ───────────────────────────────────────────

    @pyqtSlot(str)
    def _on_reenable_plugin(self, path: str) -> None:
        """Reset circuit breaker and restart the poll worker."""
        self._start_poll_worker(path)

    @pyqtSlot(str)
    def _on_install_completed(self, path: str) -> None:
        """P1-6: pip install succeeded — reload plugin without restarting the app."""
        import importlib
        importlib.invalidate_caches()
        self._stop_poll_worker(path)
        _reset_health(path)
        card = self._cards.get(path)
        if card:
            card._btn_install.setVisible(False)
            card._btn_reenable.setVisible(False)
            card._dot.setStyleSheet(f"color:{TEXT_MUTED}; font-size:13px; border:none;")
            card._metrics_lbl.setText("Library installed — reconnecting…")
        QTimer.singleShot(300, lambda p=path: self._start_poll_worker(p))

    @pyqtSlot(str)
    def _on_update_credentials(self, instance_id: str) -> None:
        """P4-1: Re-open credential dialog for an AUTH-error card.

        On success, saves the new credential to the per-instance keyring key
        and restarts the poll worker so it picks up the new password.
        """
        inst = next((i for i in _load_instances() if i["id"] == instance_id), None)
        if inst is None:
            return
        path = inst["path"]
        ok, _, meta = _validate_script(path)
        if not ok:
            return
        cred_label = meta.get("credential_label", "Password")
        hw_name    = inst.get("name") or meta.get("name", Path(path).stem)
        current_ip = inst.get("ip") or meta.get("ip", "")

        accepted, confirmed_ip = self._show_credential_dialog(
            hw_name, current_ip, cred_label, plugin_path=path
        )
        if not accepted:
            return

        # Update stored IP if the user changed it
        if confirmed_ip and confirmed_ip != current_ip:
            instances = _load_instances()
            for i in instances:
                if i["id"] == instance_id:
                    i["ip"] = confirmed_ip
            _save_instances(instances)

        # Reset circuit breaker and restart the worker
        _reset_health(path)
        self._stop_poll_worker(instance_id)
        card = self._cards.get(instance_id)
        if card:
            card._btn_update_cred.setVisible(False)
            card._btn_reenable.setVisible(False)
            card._dot.setStyleSheet(f"color:{TEXT_MUTED}; font-size:13px; border:none;")
            card._metrics_lbl.setText("Credentials updated — reconnecting…")
        QTimer.singleShot(300, lambda iid=instance_id: self._start_poll_worker_inst(iid))

    @pyqtSlot(str, str, str)
    def _on_rename_card(self, instance_id: str, old_name: str, new_name: str) -> None:
        """P3-4: Persist display name change and propagate to dashboard nav (plugin_renamed)."""
        instances = _load_instances()
        path = ""
        for inst in instances:
            if inst["id"] == instance_id:
                inst["name"] = new_name
                path = inst.get("path", "")
                break
        if path:
            _save_instances(instances)
            self.plugin_renamed.emit(path, old_name, new_name)

    # ── Import / remove ───────────────────────────────────────────────────────

    @pyqtSlot()
    def _on_create_plugin(self) -> None:
        """P3-2: Template wizard — generate a new plugin .py from user-supplied fields.

        Presents a dialog collecting hardware name, type, IP, credential label,
        optional PyPI package, and author.  On "Create", writes a filled-in
        template to get_app_data_dir()/plugins/ and offers to import it immediately.
        """
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

        from PyQt6.QtWidgets import QFormLayout
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

        # Output file path (auto, shown read-only)
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

            # Build file content from _TEMPLATE with substitutions
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

            # Insert PYPI_PACKAGE and/or CREDENTIAL_LABEL before the credential helper
            extra_consts = ""
            if pypi_pkg:
                extra_consts += f'\nPYPI_PACKAGE    = "{pypi_pkg}"'
            extra_consts += f'\nCREDENTIAL_LABEL = "{cred_label}"'
            if extra_consts:
                content = content.replace(
                    '\n# ── Credentials',
                    extra_consts + '\n\n# ── Credentials',
                )

            # Write to user plugins dir
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / fname
                dest.write_text(content, encoding="utf-8")
                _created_path.append(str(dest))
                dlg.accept()
            except Exception as exc:
                status_lbl.setText(f"Failed to create file: {exc}")
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

        # Offer to open the file in the system editor
        from PyQt6.QtWidgets import QMessageBox
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

    def _on_import_nspkg(self) -> None:
        """Import a .nspkg plugin bundle (P3-5)."""
        from PyQt6.QtWidgets import QMessageBox
        path, _ = QFileDialog.getOpenFileName(
            self, "Import plugin bundle", "",
            "NetSentinel plugin bundles (*.nspkg);;ZIP files (*.zip)",
        )
        if not path:
            return

        try:
            from modules.nspkg import unpack_nspkg
            from modules.utils import get_app_data_dir
            dest_dir = get_app_data_dir() / "plugins"
            plugin_path, manifest = unpack_nspkg(path, dest_dir)
        except Exception as exc:
            self._set_status(f"Import failed: {exc}", error=True)
            return

        # Treat the extracted .py as a user-supplied script (show consent if unsigned)
        if not _is_consented(str(plugin_path)):
            if not self._show_unsigned_warning(str(plugin_path)):
                return
            _record_consent(str(plugin_path))

        ok, msg, meta = _validate_script(str(plugin_path))
        if not ok:
            self._set_status(f"Bundle plugin invalid: {msg}", error=True)
            return

        name = manifest.get("name") or meta.get("name", plugin_path.stem)
        self._set_status(f"Importing '{name}' from bundle…", error=False)
        self._import_bundled(str(plugin_path))

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select hardware integration script", "",
            "Python files (*.py)",
        )
        if not path:
            return

        # P4-1: one-time unsigned plugin warning for scripts not in the bundled dir
        bundled_dir = self._bundled_plugins_dir()
        is_bundled = Path(path).resolve().parent == bundled_dir.resolve()
        if not is_bundled and not _is_consented(path):
            if not self._show_unsigned_warning(path):
                return
            _record_consent(path)

        self._register_plugin(path, source="browse")

    def _show_unsigned_warning(self, path: str) -> bool:
        """One-time consent dialog shown before adding any non-bundled plugin.

        Returns True when the user clicks 'I understand — Add anyway'.
        The caller records consent so the dialog is not shown again for the same content.
        """
        try:
            sz = Path(path).stat().st_size
            sz_str = f"{sz:,} bytes"
        except Exception:
            sz_str = "unknown size"

        dlg = QDialog(self)
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

    @pyqtSlot(str)
    def _remove_plugin(self, path_or_id: str) -> None:
        """Remove by instance_id (preferred) or by path (removes first matching instance)."""
        self._stop_poll_worker(path_or_id)
        instances = _load_instances()
        # Try exact instance_id match first
        remaining = [i for i in instances if i["id"] != path_or_id]
        if len(remaining) == len(instances):
            # No match on id — try path (remove first matching)
            removed = next((i for i in instances if i["path"] == path_or_id), None)
            if removed:
                remaining = [i for i in instances if i["id"] != removed["id"]]
                path_or_id = removed["path"]
        _save_instances(remaining)
        self._set_status(f"Removed {Path(path_or_id).name}.", error=False)
        self._rebuild_hub()
        self.plugin_page_removed.emit(path_or_id)

    # ── Status helper ─────────────────────────────────────────────────────────

    def _set_status(self, text: str, error: bool = False) -> None:
        color = AMBER if error else GREEN
        self._status_lbl.setText(text)
        self._status_lbl.setStyleSheet(f"font-size:10px; color:{color};")
        QTimer.singleShot(5000, lambda: self._status_lbl.setText(""))

    # ── Hardware auto-detection ───────────────────────────────────────────────

    def on_hardware_detected(self, matches: list) -> None:
        """Populate the Suggested tab from catalogue matches.

        Called from dashboard after HwDetectWorker finishes.
        Skips devices that are already installed.
        """
        if self._suggested_lay is None or self._tabs is None:
            return

        from modules.hw_detect import already_installed
        visible = [m for m in matches if not already_installed(m["plugin"].get("id", ""))]

        if not visible:
            self._tabs.setTabVisible(self._suggested_tab_idx, False)
            return

        # Clear previous rows
        while self._suggested_lay.count():
            item = self._suggested_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        imported = set(_load_paths())
        for match in visible:
            plugin     = match["plugin"]
            confidence = match["confidence"]
            signals    = match["signals"]
            # Consider a plugin "already active" if its bundled script is imported
            plugin_file = plugin.get("file", "")
            native_active = bool(plugin_file and any(
                Path(p).name == Path(plugin_file).name for p in imported
            ))
            self._suggested_lay.addWidget(
                self._build_detect_row(plugin, confidence, signals, native_active)
            )

        self._suggested_lay.addStretch()
        n = len(visible)
        self._tabs.setTabText(self._suggested_tab_idx, f"Suggested ({n})")
        self._tabs.setTabVisible(self._suggested_tab_idx, True)

    def _build_detect_row(
        self, plugin: dict, confidence: float, signals: list,
        native_active: bool = False,
    ) -> QWidget:
        row = QFrame()
        row.setStyleSheet(
            f"background:transparent; border:none;"
            f" border-bottom:1px solid {BORDER};"
        )
        lay = QHBoxLayout(row)
        lay.setContentsMargins(12, 8, 10, 8)
        lay.setSpacing(10)

        # Confidence dot
        dot = QLabel("●")
        if confidence >= 0.7:
            dot.setStyleSheet(f"color:{GREEN}; font-size:11px; border:none;")
            dot.setToolTip(f"Strong match ({confidence:.0%})")
        else:
            dot.setStyleSheet(f"color:{AMBER}; font-size:11px; border:none;")
            dot.setToolTip(f"Possible match ({confidence:.0%})")
        lay.addWidget(dot)

        # Device info
        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        info_col.setContentsMargins(0, 0, 0, 0)
        name_lbl = QLabel(f"<b>{plugin.get('name', '?')}</b>  "
                          f"<span style='color:{TEXT_MUTED}; font-size:9px;'>"
                          f"{plugin.get('manufacturer','')}</span>")
        name_lbl.setTextFormat(Qt.TextFormat.RichText)
        name_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:11px; border:none;")
        sig_lbl = QLabel(" · ".join(signals[:3]))
        sig_lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:9px; border:none;")
        sig_lbl.setWordWrap(True)
        info_col.addWidget(name_lbl)
        info_col.addWidget(sig_lbl)
        lay.addLayout(info_col, 1)

        # Action buttons
        native_page = plugin.get("native_page", "")
        has_bundled = bool(plugin.get("file"))
        has_prompt  = bool(plugin.get("ai_prompt"))

        if native_active and native_page:
            # Device is already supplying live data via its native worker.
            # Show "Open page" instead of Install — no script copy needed.
            status_lbl = QLabel("Active")
            status_lbl.setStyleSheet(
                f"color:{GREEN}; font-size:9px; font-weight:bold; border:none;"
            )
            lay.addWidget(status_lbl)
            btn_open = _btn(f"Open {native_page} →", accent=True)
            btn_open.setFixedHeight(24)
            btn_open.setToolTip(f"Navigate to the {native_page} page")
            btn_open.clicked.connect(lambda _=False, pg=native_page: self.navigate_to.emit(pg))
            lay.addWidget(btn_open)
        else:
            if has_bundled:
                btn_install = _btn("⬇  Install", accent=True)
                btn_install.setFixedHeight(24)
                btn_install.setToolTip(
                    "Copy bundled plugin into your NetSentinel data folder and register it"
                )
                btn_install.clicked.connect(lambda _=False, p=plugin: self._install_from_catalogue(p))
                lay.addWidget(btn_install)

            if has_prompt:
                btn_prompt = _btn("⎘  Copy AI prompt")
                btn_prompt.setFixedHeight(24)
                btn_prompt.setToolTip("Copy a pre-written prompt for an AI to generate this plugin")
                btn_prompt.clicked.connect(
                    lambda _=False, p=plugin: self._copy_ai_prompt(p, btn_prompt)
                )
                lay.addWidget(btn_prompt)

        return row

    def _install_from_catalogue(self, plugin: dict) -> None:
        """Copy a bundled plugin to the user data dir and register it.

        If the plugin requires a PyPI library that is not yet installed,
        opens PipInstallDialog first and only proceeds on success.
        """
        # ── 1. Check / install PyPI dependency ────────────────────────────────
        pypi_lib = plugin.get("pypi_library", "")
        if pypi_lib:
            import importlib.util
            # Map dash-separated package names to their importable module name
            module_name = pypi_lib.replace("-", "_")
            if importlib.util.find_spec(module_name) is None:
                dlg = PipInstallDialog(pypi_lib, parent=self)
                if dlg.exec() != QDialog.DialogCode.Accepted:
                    self._set_status("Dependency install cancelled.", error=True)
                    return
                # Verify the library is now importable after pip install
                import importlib
                importlib.invalidate_caches()
                if importlib.util.find_spec(module_name) is None:
                    self._set_status(
                        f"Library '{pypi_lib}' still not importable after install — "
                        "check the pip output for errors.",
                        error=True,
                    )
                    return

        # ── 2. Copy the bundled plugin script to the user data dir ────────────
        from modules.hw_detect import bundled_plugin_path
        file_rel = plugin.get("file", "")
        if not file_rel:
            self._set_status("No bundled plugin file for this entry.", error=True)
            return

        src = bundled_plugin_path(file_rel)
        if src is None:
            self._set_status(f"Bundled file not found: {file_rel}", error=True)
            return

        import shutil
        from pathlib import Path as _Path
        try:
            dest_dir = _Path.home() / ".netsentinel" / "plugins"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / src.name
            if dest != src:
                shutil.copy2(src, dest)
            dest_str = str(dest)
        except Exception as exc:
            self._set_status(f"Copy failed: {exc}", error=True)
            return

        ok, msg, _ = _validate_script(dest_str)
        if not ok:
            self._set_status(f"Plugin validation failed: {msg}", error=True)
            return

        paths = _load_paths()
        is_new = dest_str not in paths
        if is_new:
            paths.append(dest_str)
            _save_paths(paths)

        name = plugin.get("name", src.name)
        self._set_status(f"Installed '{name}' — opening password field…", error=False)
        self._rebuild_hub()
        self._start_poll_worker(dest_str)
        if is_new:
            self.plugin_page_added.emit(dest_str, name)
        # Hide the Suggested tab since the device is now installed
        if self._tabs is not None:
            self._tabs.setTabVisible(self._suggested_tab_idx, False)

    def _copy_ai_prompt(self, plugin: dict, btn: QPushButton) -> None:
        """Copy the catalogue AI prompt to clipboard, replacing {ip} placeholder."""
        prompt = plugin.get("ai_prompt", "")
        default_ip = (plugin.get("fingerprints", {}).get("default_ips") or ["192.168.1.1"])[0]
        prompt = prompt.replace("{ip}", default_ip)
        QApplication.clipboard().setText(prompt)
        orig = btn.text()
        btn.setText("✓  Copied!")
        QTimer.singleShot(2000, lambda: btn.setText(orig))

    # ── Guide content (collapsible) ───────────────────────────────────────────

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
            "I want to write a Python script that reads live data from my [Brand] [Model] "
            "router/modem. The admin panel is at http://192.168.1.1. "
            "Login: username 'admin', password 'admin'.\n\n"
            "Please:\n"
            "1. Find if this router has a local JSON REST API or requires HTML scraping\n"
            "2. Write a Python script using requests that logs in and returns:\n"
            "   - WAN IP, Uptime, Connected clients (name, IP, MAC)\n"
            "3. Add a main block at the bottom that prints all results as JSON\n"
            "4. Tell me which packages to install with pip",
        ))
        lay.addWidget(_prompt_block(
            "PROMPT B — From a cURL command (best results)",
            "I captured this API call from my router admin panel using browser dev tools "
            "(F12 → Network → right-click request → Copy as cURL). "
            "Convert it to a Python function using requests.\n\n"
            "[Paste your cURL command here]\n\n"
            "Then wrap the result in the NetSentinel plugin format:\n"
            "- HARDWARE_NAME, HARDWARE_TYPE, get_info(), get_status(), get_clients()\n"
            "- if __name__ == '__main__': print all results as JSON",
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
        template_edit.setStyleSheet(
            f"QTextEdit {{ background:{BG_DARK}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:4px; }}"
        )
        lay.addWidget(template_edit)

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
            "Please complete get_info() and get_status() using the real API for my hardware.\n"
            "[Paste the template here]",
        ))
        return frame

    def _build_step3_guide(self) -> QWidget:
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

    def _on_save_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save integration template", "netsentinel_hardware.py",
            "Python files (*.py)",
        )
        if not path:
            return
        try:
            Path(path).write_text(_TEMPLATE, encoding="utf-8")
            self._set_status(f"Template saved to {Path(path).name}", error=False)
        except Exception as exc:
            self._set_status(f"Save failed: {exc}", error=True)
