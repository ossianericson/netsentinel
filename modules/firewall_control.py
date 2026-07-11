"""
modules/firewall_control.py — Windows Firewall (netsh) control helpers.

Pure Python, no PyQt imports. Extracted from ui/pages/connections_page.py so
the blocking subprocess.run() calls can be driven from a QThread worker
(workers/firewall_worker.py) instead of the GUI thread (RULE 4).
"""
from __future__ import annotations

import subprocess
import sys


def rule_name(exe_name: str) -> str:
    return f"NS-Block-{exe_name}"


def block_process(exe_path: str, exe_name: str) -> tuple[bool, str]:
    """Create an outbound-deny firewall rule. Returns (success, message)."""
    if sys.platform != "win32":
        return False, "Firewall control is only available on Windows"
    if not exe_path:
        return False, f"Cannot block '{exe_name}' — executable path unknown"
    rule = rule_name(exe_name)
    cmd = [
        "netsh", "advfirewall", "firewall", "add", "rule",
        f"name={rule}",
        "dir=out",
        "action=block",
        f"program={exe_path}",
        "enable=yes",
        "profile=any",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return True, f"Blocked: {exe_name}"
        return False, result.stderr.strip() or result.stdout.strip()
    except Exception as exc:
        return False, str(exc)


def unblock_process(exe_name: str) -> tuple[bool, str]:
    """Remove the NS-Block-* firewall rule for exe_name."""
    if sys.platform != "win32":
        return False, "Windows only"
    rule = rule_name(exe_name)
    cmd = [
        "netsh", "advfirewall", "firewall", "delete", "rule",
        f"name={rule}",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return True, f"Unblocked: {exe_name}"
        return False, result.stderr.strip() or "Rule not found"
    except Exception as exc:
        return False, str(exc)


def get_blocked_rules() -> list[str]:
    """Return list of exe names currently blocked by NS-Block-* rules."""
    if sys.platform != "win32":
        return []
    try:
        result = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule",
             "name=all", "dir=out", "verbose"],
            capture_output=True, text=True, timeout=15
        )
        rules = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("Rule Name:") and "NS-Block-" in line:
                name = line.split("NS-Block-", 1)[1].strip()
                rules.append(name)
        return rules
    except Exception:
        return []
