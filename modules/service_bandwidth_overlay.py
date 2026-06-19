"""
modules/service_bandwidth_overlay.py — Bandwidth-context overlay for Service
Diagnostics (S6-6).

Combines a Service Diagnostics verdict (modules/service_diagnostics.py
ServiceDiagnosticResult.failure_layer) with live App Traffic device counts
(modules/metric_store_queries_metrics.py query_app_traffic_active_device_count)
to produce a sentence like:

    "Netflix reports no outages. Your local connection to Netflix is fine.
     Buffering is caused by bandwidth being shared with 3 other active devices."

Pure function — no PyQt, no DB access. Callers pass in already-queried values.
"""
from __future__ import annotations

from typing import Optional


def build_overlay_note(
    service_name: str,
    failure_layer: str,
    active_device_count: int,
) -> Optional[str]:
    """Return a bandwidth-context sentence, or None when it would add no value.

    Only fires when the diagnostic itself found nothing wrong (`failure_layer
    == "none"`) — if a real failure layer was identified, that explanation
    already covers the symptom and a bandwidth note would be a distraction.
    `active_device_count` is the caller-supplied count of other devices
    generating measurable traffic on the network (best-effort — see
    metric_store_queries_metrics.query_app_traffic_active_device_count).
    """
    if failure_layer != "none":
        return None
    if active_device_count <= 0:
        return None

    plural = "device" if active_device_count == 1 else "devices"
    return (
        f"{service_name} reports no outages. Your local connection to "
        f"{service_name} is fine. If you're seeing slowdowns, it may be "
        f"caused by bandwidth being shared with {active_device_count} "
        f"other active {plural}."
    )
