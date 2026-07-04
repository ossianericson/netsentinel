"""
hub_helpers.py — Pure data-persistence and utility helpers extracted from hub_card.py.

No widget-level logic lives here — no Qt widget classes, no QPushButton, no QFrame.
Imported by hub_card.py to keep that file focused on widget implementations.
"""
from __future__ import annotations

import ast
import hashlib
import json
import time
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QSettings

from ui.styles import AMBER, GREEN, RED, TEXT_MUTED
from ui.widgets.hub_plugin_template import _TEMPLATE  # noqa: F401 — re-exported for hub_card.py etc.

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

# ── Helpers ───────────────────────────────────────────────────────────────────

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

def _resolve_path(p: str) -> str:
    """Return a stable AppData copy path if *p* no longer exists (e.g. stale _MEI path)."""
    if Path(p).exists():
        return p
    try:
        from modules.utils import get_app_data_dir as _gad
        appdata_copy = _gad() / "plugins" / Path(p).name
        if appdata_copy.exists():
            return str(appdata_copy)
    except Exception:
        pass  # non-fatal — AppData lookup failure
    return p


def _load_instances() -> list[dict]:
    s = QSettings("NetSentinel", "NetSentinel")
    raw = s.value(_SETTINGS_INSTANCES, None)
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                # Resolve any stale paths (e.g. PyInstaller _MEI temp dirs that are gone)
                changed = False
                for inst in data:
                    resolved = _resolve_path(inst.get("path", ""))
                    if resolved != inst.get("path", ""):
                        inst["path"] = resolved
                        changed = True
                if changed:
                    _save_instances(data)

                # Auto-remove entries whose plugin file lives in a temp/pytest
                # directory.  Pytest artifacts escape into QSettings when tests
                # don't fully isolate their QSettings writes.  Real user plugins
                # on USB drives or network shares never have "pytest-of-" in
                # their path, so the pattern match is safe to apply silently.
                # Case-insensitive string comparison avoids relative_to() failures
                # on Windows when paths have mixed case or symlink components.
                import tempfile as _tf
                _tmp_str = str(Path(_tf.gettempdir()).resolve()).lower().replace("\\", "/")
                def _is_temp_artifact(inst: dict) -> bool:
                    p = Path(inst.get("path", ""))
                    p_str = str(p).lower().replace("\\", "/")
                    # Always remove pytest-generated temp paths, even if the file
                    # still exists (it may be a live test runner session).
                    if "pytest-of-" in p_str or "/pytest-" in p_str:
                        return True
                    if p.exists():
                        return False
                    # Remove any missing path that is under the system temp dir.
                    return p_str.startswith(_tmp_str)
                clean = [i for i in data if not _is_temp_artifact(i)]
                if len(clean) != len(data):
                    _save_instances(clean)
                    data = clean

                return data
        except Exception:
            pass  # corrupted QSettings value — fall through to migration path
    # Migrate from legacy custom_scripts list on first access
    legacy = _load_paths()
    if not legacy:
        return []
    instances = []
    for p in legacy:
        p = _resolve_path(p)  # resolve stale _MEI paths before saving
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

    Also fixes stale paths in the hardware/instances key (the current registry)
    so plugin device pages built at startup see valid paths.

    Extracted from the page method so tests can import and call it directly.
    """
    import shutil as _sh
    from modules.utils import get_app_data_dir as _gad

    # ── Fix legacy hardware/custom_scripts key ────────────────────────────────
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
                pass  # copy failed — keep original path so the card shows the error
        # Path is genuinely gone — keep it so the card can show the error
        new_paths.append(p)
    if changed:
        _save_paths(new_paths)

    # ── Fix hardware/instances paths (current registry) ───────────────────────
    # _load_instances() already calls _resolve_path() on every read, but calling
    # it here ensures the QSettings value is written back before tabs.py reads
    # instances at dashboard init time.
    _load_instances()


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
            pass  # non-fatal
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
            pass  # non-fatal
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
