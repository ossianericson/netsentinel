"""
Automation Hooks — trigger local scripts when network events occur.

Events watched:
  device_joined  — a new (or returning) MAC appeared on the network
  device_left    — a known MAC stopped responding to ARP
  alert_fired    — the alert engine raised an alert at a given level

Rule storage:  get_app_data_dir() / "automation_rules.json"

Script execution:
  subprocess.Popen  (non-blocking; stdout/stderr forwarded to an optional
  streaming callback so the UI can display them in an Automation Log panel)

Built-in template rules (as factory functions):
  template_wol(target_mac, broadcast)   — sends Wake-on-LAN
  template_log_to_file()                — appends event JSON to a log file
  template_notify(title)                — sends a desktop toast (via notification_router)
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional

from modules.utils import get_app_data_dir


# ── Constants ─────────────────────────────────────────────────────────────────

_RULES_FILE = "automation_rules.json"


# ── Data model ────────────────────────────────────────────────────────────────

class Trigger(str, Enum):
    DEVICE_JOINED = "device_joined"
    DEVICE_LEFT   = "device_left"
    ALERT_FIRED   = "alert_fired"


@dataclass
class AutomationRule:
    """One automation rule."""
    id:          str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name:        str   = ""
    trigger:     str   = Trigger.DEVICE_JOINED.value   # Trigger enum value
    # Condition — match on MAC address, IP address, hostname, or alert level.
    # Use "*" or "" to match anything.
    match_field: str   = "mac"    # "mac" | "ip" | "hostname" | "alert_level" | "any"
    match_value: str   = "*"      # e.g. "AA:BB:CC:DD:EE:FF" or "HIGH"
    # Execution
    script_path: str   = ""
    args:        str   = ""       # extra CLI arguments (space-separated or with $VARS)
    enabled:     bool  = True
    # Metadata
    description: str   = ""


# ── Rules engine ──────────────────────────────────────────────────────────────

class AutomationEngine:
    """
    Load/save rules and evaluate them against incoming network events.

    Instantiated once and shared; safe to call from any thread.
    Script execution always runs in a daemon thread so it never blocks callers.
    """

    def __init__(self) -> None:
        self._lock  = threading.Lock()
        self._rules: List[AutomationRule] = []
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _rules_path(self) -> Path:
        return get_app_data_dir() / _RULES_FILE

    def _load(self) -> None:
        try:
            p = self._rules_path()
            if p.exists():
                raw = json.loads(p.read_text(encoding="utf-8"))
                with self._lock:
                    self._rules = [AutomationRule(**r) for r in raw]
        except Exception:
            pass  # corrupt file → start fresh

    def save(self) -> None:
        try:
            p = self._rules_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                data = [asdict(r) for r in self._rules]
            p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def get_rules(self) -> List[AutomationRule]:
        with self._lock:
            return list(self._rules)

    def add_rule(self, rule: AutomationRule) -> None:
        with self._lock:
            self._rules.append(rule)
        self.save()

    def update_rule(self, rule: AutomationRule) -> None:
        with self._lock:
            for i, r in enumerate(self._rules):
                if r.id == rule.id:
                    self._rules[i] = rule
                    break
        self.save()

    def delete_rule(self, rule_id: str) -> None:
        with self._lock:
            self._rules = [r for r in self._rules if r.id != rule_id]
        self.save()

    def set_enabled(self, rule_id: str, enabled: bool) -> None:
        with self._lock:
            for r in self._rules:
                if r.id == rule_id:
                    r.enabled = enabled
                    break
        self.save()

    # ── Event evaluation ──────────────────────────────────────────────────────

    def evaluate(
        self,
        trigger: str,
        event_data: Dict,
        on_log: Optional[Callable[[str, str, str], None]] = None,
    ) -> None:
        """
        Evaluate all enabled rules against the trigger + event_data.

        event_data keys (all optional):
          mac, ip, hostname, vendor, risk_level, alert_level, message

        on_log(rule_id, stream, text) — called with stdout/stderr lines
          stream ∈ {"stdout", "stderr", "system"}
        """
        with self._lock:
            candidates = [r for r in self._rules
                          if r.enabled and r.trigger == trigger]

        for rule in candidates:
            if self._matches(rule, event_data):
                threading.Thread(
                    target=self._run_rule,
                    args=(rule, event_data, on_log),
                    daemon=True,
                ).start()

    def _matches(self, rule: AutomationRule, event_data: Dict) -> bool:
        if rule.match_field in ("", "any", "*"):
            return True
        val = rule.match_value.strip().lower()
        if not val or val == "*":
            return True
        field_val = str(event_data.get(rule.match_field, "")).lower()
        return field_val == val

    def _run_rule(
        self,
        rule: AutomationRule,
        event_data: Dict,
        on_log: Optional[Callable[[str, str, str], None]],
    ) -> None:
        """Execute a rule's script in a subprocess, streaming output."""
        def _log(stream: str, text: str) -> None:
            if on_log:
                try:
                    on_log(rule.id, stream, text)
                except Exception:
                    pass

        script = rule.script_path.strip()
        if not script:
            _log("system", f"[Rule '{rule.name}'] No script configured — skipped")
            return

        # Expand environment placeholders in args
        args_str = _expand_vars(rule.args, event_data)
        try:
            argv = _build_argv(script, args_str)
        except Exception as exc:
            _log("system", f"[Rule '{rule.name}'] Arg parse error: {exc}")
            return

        _log("system", f"[Rule '{rule.name}'] → {' '.join(argv)}")

        # Build env with event data injected as NS_* variables
        env = os.environ.copy()
        for k, v in event_data.items():
            env[f"NS_{k.upper()}"] = str(v)

        popen_kwargs: dict = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text":   True,
            "env":    env,
        }
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        try:
            proc = subprocess.Popen(argv, **popen_kwargs)
        except FileNotFoundError:
            _log("system", f"[Rule '{rule.name}'] Script not found: {argv[0]}")
            return
        except Exception as exc:
            _log("system", f"[Rule '{rule.name}'] Launch error: {exc}")
            return

        # Stream stdout/stderr concurrently
        def _drain(pipe, stream: str) -> None:
            for line in pipe:
                _log(stream, line.rstrip("\n"))

        t_out = threading.Thread(target=_drain, args=(proc.stdout, "stdout"), daemon=True)
        t_err = threading.Thread(target=_drain, args=(proc.stderr, "stderr"), daemon=True)
        t_out.start(); t_err.start()
        proc.wait(timeout=120)
        t_out.join(timeout=5); t_err.join(timeout=5)
        _log("system", f"[Rule '{rule.name}'] Exit code: {proc.returncode}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _expand_vars(args: str, event_data: Dict) -> str:
    """Replace $MAC, $IP, $HOSTNAME, $ALERT_LEVEL in args string."""
    result = args
    for k, v in event_data.items():
        result = result.replace(f"${k.upper()}", str(v))
    return result


def _build_argv(script: str, args_str: str) -> List[str]:
    """Split script + args into argv, detecting interpreter."""
    import shlex
    argv = [script]
    if args_str.strip():
        argv += shlex.split(args_str)
    return argv


# ── Template rule factories ───────────────────────────────────────────────────

def template_wol(target_mac: str = "", broadcast: str = "255.255.255.255") -> AutomationRule:
    """Rule: send Wake-on-LAN to target_mac using the built-in wol helper."""
    if not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", broadcast):
        broadcast = "255.255.255.255"
    ns_root = str(Path(__file__).resolve().parent.parent)
    # MAC comes from NS_MAC env var injected by the engine at runtime; ns_root
    # and broadcast are passed as argv so no user data is embedded in the code string.
    code = (
        "import sys,os;"
        "sys.path.insert(0,sys.argv[1]);"
        "from modules.utils import send_wol;"
        "send_wol(os.environ.get('NS_MAC',''),sys.argv[2])"
    )
    args = f"-c {shlex.quote(code)} {shlex.quote(ns_root)} {shlex.quote(broadcast)}"
    return AutomationRule(
        name="Wake-on-LAN",
        trigger=Trigger.DEVICE_JOINED.value,
        match_field="mac",
        match_value=target_mac or "*",
        script_path=sys.executable,
        args=args,
        description="Send WoL magic packet when a device joins. Set match_value to the trigger MAC.",
    )


def template_log_to_file(log_path: str = "") -> AutomationRule:
    """Rule: append event JSON to a log file."""
    if not log_path:
        log_path = str(get_app_data_dir() / "automation_events.jsonl")
    ns_root = str(Path(__file__).resolve().parent.parent)
    # MAC/IP come from NS_MAC/NS_IP env vars injected by the engine; log_path
    # and ns_root are passed as argv so no user data is embedded in the code string.
    code = (
        "import sys,os,json,datetime;"
        "sys.path.insert(0,sys.argv[1]);"
        "f=open(sys.argv[2],'a');"
        "f.write(json.dumps({"
        "'ts':str(datetime.datetime.now()),"
        "'mac':os.environ.get('NS_MAC',''),"
        "'ip':os.environ.get('NS_IP','')"
        "})+chr(10));"
        "f.close()"
    )
    args = f"-c {shlex.quote(code)} {shlex.quote(ns_root)} {shlex.quote(log_path)}"
    return AutomationRule(
        name="Log Event to File",
        trigger=Trigger.DEVICE_JOINED.value,
        match_field="any",
        match_value="*",
        script_path=sys.executable,
        args=args,
        description=f"Append device join event to {log_path}.",
    )


# ── Module-level singleton ────────────────────────────────────────────────────

_engine: Optional[AutomationEngine] = None


def get_engine() -> AutomationEngine:
    """Return the module-level AutomationEngine singleton."""
    global _engine
    if _engine is None:
        _engine = AutomationEngine()
    return _engine
