"""
Plugin System — lightweight extensible check engine.

Scans a plugins directory for .py files. Each plugin must expose:

    PLUGIN_META = {
        "name":        "My Plugin",
        "version":     "1.0.0",
        "description": "What it checks",
        "author":      "Your Name",
        "tags":        ["cloud", "AD", "ICS"],   # optional
    }

    def run(devices: list, **kwargs) -> PluginResult:
        ...

Plugin search order (first found wins):
  1. Sibling `plugins/` folder next to the executable / app.py
  2. ~/.config/NetSentinel/plugins/

A bundled example plugin is written to the plugins/ folder on first run
so users have a working template to copy.

Public API:
    load_plugins()              -> List[PluginInfo]
    run_plugin(info, devices)   -> PluginResult
    plugins_dir()               -> Path
"""

from __future__ import annotations

import importlib.util
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import sys


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class PluginResult:
    plugin_name: str
    findings:    List[str] = field(default_factory=list)
    risk_level:  str = "LOW"           # LOW / MEDIUM / HIGH / CRITICAL
    raw_data:    Dict[str, Any] = field(default_factory=dict)
    error:       str = ""

    @property
    def plain_verdict(self) -> str:
        if self.error:
            return f"[{self.plugin_name}] Error: {self.error}"
        if not self.findings:
            return f"[{self.plugin_name}] No findings."
        return f"[{self.plugin_name}] {self.risk_level} — " + "; ".join(self.findings[:3])


@dataclass
class PluginInfo:
    name:        str
    version:     str
    description: str
    author:      str
    tags:        List[str]
    path:        Path
    _run_fn:     Optional[Callable] = field(default=None, repr=False)

    @property
    def tag_str(self) -> str:
        return ", ".join(self.tags) if self.tags else "—"


# ── Plugin directory ─────────────────────────────────────────────────────────

def plugins_dir() -> Path:
    """Return the active plugins directory, creating it if needed."""
    # Next to exe/app.py
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent.parent
    candidate = base / "plugins"
    if not candidate.exists():
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except OSError:
            candidate = None

    # Fallback to ~/.config/NetSentinel/plugins/
    if not candidate or not candidate.exists():
        candidate = Path.home() / ".config" / "NetSentinel" / "plugins"
        candidate.mkdir(parents=True, exist_ok=True)

    return candidate


def _ensure_example_plugin(directory: Path) -> None:
    """Write the bundled example plugin if the directory is empty."""
    if any(directory.glob("*.py")):
        return
    example = directory / "example_open_ports_report.py"
    example.write_text(
        '''\
"""
Example NetSentinel Plugin — Open Port Reporter
================================================
Scans the scan results for devices with high-risk ports open and
reports them in a structured way.

Copy this file, rename it, and modify run() to build your own check.
"""

PLUGIN_META = {
    "name":        "Open Port Reporter",
    "version":     "1.0.0",
    "description": "Lists all devices with HIGH-risk ports open (Telnet, RDP, VNC, SMB, MQTT).",
    "author":      "NetSentinel built-in example",
    "tags":        ["ports", "risk"],
}

HIGH_RISK = {23: "Telnet", 445: "SMB", 1883: "MQTT", 3389: "RDP", 5900: "VNC", 7547: "CWMP"}


def run(devices, **kwargs):
    from modules.plugin_system import PluginResult
    findings = []
    raw = {}
    for device in devices:
        ip = getattr(device, "ip", None) or (device.get("ip") if isinstance(device, dict) else "?")
        ports = getattr(device, "open_ports", None) or (device.get("open_ports", []) if isinstance(device, dict) else [])
        hit = []
        for p in ports:
            pnum = p if isinstance(p, int) else (p.get("port") if isinstance(p, dict) else getattr(p, "port", 0))
            if pnum in HIGH_RISK:
                hit.append(f"{pnum}/{HIGH_RISK[pnum]}")
        if hit:
            findings.append(f"{ip}: {', '.join(hit)}")
            raw[ip] = hit

    risk = "HIGH" if findings else "CLEAN"
    return PluginResult(
        plugin_name=PLUGIN_META["name"],
        findings=findings,
        risk_level=risk,
        raw_data=raw,
    )
''',
        encoding="utf-8",
    )


# ── Loader ────────────────────────────────────────────────────────────────────

def load_plugins() -> List[PluginInfo]:
    """
    Discover and import all .py plugins from the plugins directory.
    Returns a list of PluginInfo objects (already imported, ready to run).
    """
    directory = plugins_dir()
    _ensure_example_plugin(directory)

    plugins: List[PluginInfo] = []
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                f"netsentinel_plugin_{path.stem}", path
            )
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)          # type: ignore[attr-defined]

            meta = getattr(mod, "PLUGIN_META", {})
            run_fn = getattr(mod, "run", None)
            if not callable(run_fn):
                continue

            plugins.append(PluginInfo(
                name        = str(meta.get("name",        path.stem)),
                version     = str(meta.get("version",     "?")),
                description = str(meta.get("description", "")),
                author      = str(meta.get("author",      "Unknown")),
                tags        = list(meta.get("tags",        [])),
                path        = path,
                _run_fn     = run_fn,
            ))
        except Exception:
            # Record broken plugin with error info
            plugins.append(PluginInfo(
                name=path.stem, version="?", description="Failed to load",
                author="?", tags=[], path=path, _run_fn=None,
            ))
    return plugins


def run_plugin(info: PluginInfo, devices: list, **kwargs) -> PluginResult:
    """Execute a loaded plugin against a device list."""
    if info._run_fn is None:
        return PluginResult(
            plugin_name=info.name,
            error="Plugin failed to load — check the file for syntax errors.",
        )
    try:
        result = info._run_fn(devices, **kwargs)
        if not isinstance(result, PluginResult):
            return PluginResult(
                plugin_name=info.name,
                error=f"Plugin returned {type(result).__name__} instead of PluginResult.",
            )
        return result
    except Exception:
        return PluginResult(
            plugin_name=info.name,
            error=traceback.format_exc(limit=5),
        )
