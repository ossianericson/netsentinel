"""
modules/network_infrastructure.py — shared hardware state singleton.

Updated by dashboard signal handlers (ZteWorker, MeshWorker, PluginPollingWorker).
Consumed by any surface that needs hardware context without holding a reference
to the dashboard: speed test, log hub, hardware hub tabs, topology.

No Qt dependency — plain Python dataclass + module-level singleton.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NetworkInfrastructureState:
    """Single source of truth for all active hardware data.

    All fields may be None/empty while no hardware is connected.
    Consumers should guard for None before using signal values.
    """

    # ── Modem ─────────────────────────────────────────────────────────────────
    modem_signal: Optional[dict] = None  # normalized signal dict (any source)
    modem_source: str = ""               # "zte" | plugin file path
    modem_hw_name: str = ""              # display name shown in UI

    # ── Router / mesh ─────────────────────────────────────────────────────────
    router_clients: list = field(default_factory=list)  # list[dict]
    router_nodes: list   = field(default_factory=list)  # list[dict]
    router_source: str = ""
    router_hw_name: str = ""

    # ── WAN (filled by either modem or router status) ─────────────────────────
    wan_ip: Optional[str] = None

    # ── Update helpers ────────────────────────────────────────────────────────

    def update_modem(
        self,
        signal: dict,
        source: str,
        hw_name: str = "",
    ) -> None:
        self.modem_signal  = signal
        self.modem_source  = source
        self.modem_hw_name = hw_name or source
        self.wan_ip        = signal.get("wan_ip") or self.wan_ip

    def update_router(
        self,
        clients: list,
        nodes: list,
        source: str,
        hw_name: str = "",
    ) -> None:
        self.router_clients = clients
        self.router_nodes   = nodes
        self.router_source  = source
        self.router_hw_name = hw_name or source
        # wan_ip may come from router status — callers can set it directly

    def clear_modem(self) -> None:
        self.modem_signal  = None
        self.modem_source  = ""
        self.modem_hw_name = ""

    def clear_router(self) -> None:
        self.router_clients = []
        self.router_nodes   = []
        self.router_source  = ""
        self.router_hw_name = ""


# Module-level singleton — import and mutate directly.
hw_state = NetworkInfrastructureState()
