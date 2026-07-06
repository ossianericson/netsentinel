"""Architectural gate (P3): every worker QThread must subclass BaseWorker.

New workers get the shared error/progress signals, the run()->work() template,
and cooperative stop for free by subclassing ``workers.base_worker.BaseWorker``.
This test enforces that going forward and ratchets the legacy tail downward:
as each pre-existing worker is migrated it drops out of ``LEGACY`` automatically
(``test_legacy_set_has_no_stale_entries`` fails if a migrated class is still
listed), so the exemption list can only shrink, never grow.

Detection is a runtime ``issubclass`` check (not AST) so it is immune to import
aliasing and indirect bases.  The worker modules are already imported by the
lifecycle suite, so importing them here adds no new dependency surface.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

from PyQt6.QtCore import QThread

from workers.base_worker import BaseWorker

WORKERS_ROOT = Path(__file__).resolve().parents[1] / "workers"

# Pre-existing workers not yet migrated onto BaseWorker, keyed "module:ClassName".
# This list may ONLY shrink.  When you migrate a worker, delete its entries here
# in the same commit — test_legacy_set_has_no_stale_entries enforces that.
LEGACY: set[str] = {
    "app_traffic_worker:AppTrafficWorker",
    "availability_worker:AvailabilityWorker",
    "bandwidth_worker:BandwidthOverlayWorker",
    "diagnosis_worker:DiagnosisWorker",
    "health_worker:HealthWorker",
    "iface_bw_worker:IfaceBwPoller",
    "isp_vs_router_worker:IspVsRouterWorker",
    "passive_observer_worker:PassiveObserverWorker",
    "plugin_polling_worker:PluginPollingWorker",
    "process_worker:ConnectionSnapshotWorker",
    "process_worker:ConnectionPollerWorker",
    "proactive_probe_worker:ProactiveProbeWorker",
    "report_scheduler_worker:ReportSchedulerWorker",
    "rest_api_worker:RestApiWorker",
    "service_diagnostics_worker:ServiceDiagnosticsWorker",
    "service_worker:ServiceWorker",
    "snmp_trap_worker:SnmpTrapWorker",
    "syslog_worker:SyslogWorker",
    "wifi_monitor_worker:WiFiMonitorWorker",
    # scan_worker.py family — migrated together with its family split (follow-up pass).
    "scan_worker:Module1Worker",
    "scan_worker:Module2Worker",
    "scan_worker:Module3Worker",
    "scan_worker:Module4Worker",
    "scan_worker:Module5Worker",
    "scan_worker:LoggerWorker",
    "scan_worker:PreScanWorker",
    "scan_worker:NetworkInfoWorker",
    "scan_worker:DiagnosticsWorker",
    "scan_worker:PortScanWorker",
    "scan_worker:MTRWorker",
    "scan_worker:ARPMonitorWorker",
    "scan_worker:DHCPDetectorWorker",
    "scan_worker:BandwidthWorker",
    "scan_worker:SchedulerWorker",
    "scan_worker:SNMPWorker",
    "scan_worker:SNMPIfErrorWorker",
    "scan_worker:SYNScanWorker",
    "scan_worker:UDPScanWorker",
    "scan_worker:OSFingerprintWorker",
    "scan_worker:CVELookupWorker",
    "scan_worker:InternetExposureWorker",
    "scan_worker:CredentialedScanWorker",
    "scan_worker:CombinedDiscoveryWorker",
    "scan_worker:SMBEnumWorker",
    "scan_worker:PluginWorker",
    "scan_worker:PrivateEndpointWorker",
    "scan_worker:IPv6Worker",
    "scan_worker:CloudMetadataWorker",
}


def _discover_worker_classes() -> list[tuple[str, type]]:
    """Return (key, cls) for every QThread subclass *defined in* a workers/ module."""
    found: list[tuple[str, type]] = []
    for path in sorted(WORKERS_ROOT.glob("*.py")):
        if path.stem.startswith("_") or path.stem == "base_worker":
            continue
        module = importlib.import_module(f"workers.{path.stem}")
        for name, obj in vars(module).items():
            if not inspect.isclass(obj):
                continue
            # Only classes actually defined in this module (skip re-imports).
            if obj.__module__ != module.__name__:
                continue
            if issubclass(obj, QThread) and obj is not QThread:
                found.append((f"{path.stem}:{name}", obj))
    return found


def test_every_worker_subclasses_base_worker(qt_app):
    """Every worker QThread must subclass BaseWorker, except the shrinking LEGACY tail."""
    offenders = [
        key
        for key, cls in _discover_worker_classes()
        if not issubclass(cls, BaseWorker) and key not in LEGACY
    ]
    assert not offenders, (
        "These worker QThread classes must subclass workers.base_worker.BaseWorker "
        "(or, if intentionally deferred, be added to LEGACY with a reason):\n"
        + "\n".join(f"  {o}" for o in sorted(offenders))
    )


def test_legacy_set_has_no_stale_entries(qt_app):
    """A LEGACY entry must name a real, still-unmigrated worker class (ratchet-down).

    If a class was migrated onto BaseWorker but left in LEGACY, or renamed/removed,
    this fails — forcing the exemption list to shrink as migration proceeds.
    """
    discovered = {key: cls for key, cls in _discover_worker_classes()}
    stale: list[str] = []
    for key in sorted(LEGACY):
        cls = discovered.get(key)
        if cls is None:
            stale.append(f"{key}  (no such worker class — renamed or removed?)")
        elif issubclass(cls, BaseWorker):
            stale.append(f"{key}  (now subclasses BaseWorker — remove from LEGACY)")
    assert not stale, "Stale LEGACY entries in test_worker_base_class.py:\n" + "\n".join(
        f"  {s}" for s in stale
    )
