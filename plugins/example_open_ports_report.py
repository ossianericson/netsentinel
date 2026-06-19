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
