"""
service_escalation.py — root-cause escalation for SERVICE_DOWN alerts (Sprint 1).

The service heartbeat (workers/service_worker.py) only knows a TCP connect
failed; it cannot tell the user *why*. This module turns a
DiagnosticEngine.run_custom() failure_layer classification (see
modules/service_diagnostics.py) into a plain-English explanation, so a
follow-up notification can say "filtered" (firewall/VPN/ISP silently
blocking the port) instead of leaving a real outage indistinguishable from
a false alarm.

Pure Python — no PyQt6 imports, no direct DB writes (ARCH RULE 1). The
DiagnosticEngine call itself is dispatched from app.py via the existing
workers/service_diagnostics_worker.py QThread (RULE 4) — this module only
provides the cooldown bookkeeping and the layer -> message/severity mapping.
"""
from __future__ import annotations

import time
from typing import Dict, Optional, Tuple

_DEFAULT_COOLDOWN_S = 600  # ~10 min — don't re-diagnose a flapping service every tick

# failure_layer (modules/service_diagnostics.py ServiceDiagnosticResult) ->
# (canonical UI severity per RULE-A3, plain-English explanation)
_LAYER_INFO: Dict[str, Tuple[str, str]] = {
    "filtered": (
        "Warning",
        "is reachable by ping but the connection itself is blocked — likely a "
        "firewall, VPN, or your ISP silently filtering this port, not a real outage",
    ),
    "device": (
        "High",
        "the problem appears to be on this device — check its network settings "
        "or restart it",
    ),
    "local_network": (
        "High",
        "the problem appears to be on your local network — check your router "
        "or switch",
    ),
    "dns": (
        "Warning",
        "DNS lookup is failing — the hostname isn't resolving correctly",
    ),
    "isp": (
        "High",
        "your ISP connection appears to be the problem",
    ),
    "routing": (
        "Warning",
        "traffic is not routing correctly to this destination",
    ),
    "remote_outage": (
        "Critical",
        "the remote service itself appears to be down",
    ),
    "none": (
        "Info",
        "no clear cause was identified",
    ),
}

# canonical UI severity (RULE-A3) -> internal AlertFired.severity vocabulary
# (kept intentionally distinct — see architecture.instructions.md "Risk levels")
_UI_TO_ALERT_SEVERITY: Dict[str, str] = {
    "Info":     "INFO",
    "Warning":  "WARNING",
    "High":     "CRITICAL",
    "Critical": "CRITICAL",
}


class ServiceEscalationTracker:
    """Per-host/port cooldown so a flapping service is diagnosed at most once per window."""

    def __init__(self, cooldown_s: int = _DEFAULT_COOLDOWN_S):
        self._cooldown_s = cooldown_s
        self._last_escalated: Dict[str, float] = {}

    def should_escalate(self, host: str, port: int, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        last = self._last_escalated.get(f"{host}:{port}")
        return last is None or now - last >= self._cooldown_s

    def mark_escalated(self, host: str, port: int, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        self._last_escalated[f"{host}:{port}"] = now


def parse_service_key(key: str) -> Tuple[str, int]:
    """
    Split a SERVICE_DOWN AlertFired.host key ("host:port") back into its
    parts. Returns ("", 0) for anything that doesn't match that shape.
    """
    if ":" not in key:
        return "", 0
    host, _, port_str = key.rpartition(":")
    if not host or not port_str.isdigit():
        return "", 0
    return host, int(port_str)


def layer_to_message(
    failure_layer: str, host: str, port: int, label: str = ""
) -> Tuple[str, str]:
    """
    Map a DiagnosticEngine failure_layer to a (ui_severity, message) pair.
    ui_severity is one of Info/Warning/High/Critical (RULE-A3) — the caller
    is responsible for converting it to AlertFired's internal severity via
    to_alert_severity() before dispatch.
    """
    target = label or f"{host}:{port}"
    severity, explanation = _LAYER_INFO.get(failure_layer, _LAYER_INFO["none"])
    return severity, f"{target} {explanation}."


def to_alert_severity(ui_severity: str) -> str:
    """Convert a canonical UI severity label to AlertFired's internal severity value."""
    return _UI_TO_ALERT_SEVERITY.get(ui_severity, "WARNING")


def is_filtered_message(message: str) -> bool:
    """
    True if `message` was produced by layer_to_message() for the "filtered"
    failure_layer — used by modules/digest_bullets.py to distinguish a
    firewall/VPN/ISP block from a real outage in the overnight summary,
    without duplicating the explanation text from _LAYER_INFO.
    """
    _, explanation = _LAYER_INFO["filtered"]
    return explanation in message
