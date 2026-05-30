"""
remove_orphan_decorators.py — Remove orphaned @pyqtSlot decorators from dashboard.py.

These decorators were left behind when the _on_*_result methods were extracted to scan_wiring.py.
Each orphaned decorator was accidentally applying to an unrelated function.
"""
from pathlib import Path

DASHBOARD = Path("ui/dashboard.py")

# The 1-based line numbers of the orphaned @pyqtSlot decorators to remove
ORPHAN_LINES = {
    5271,   # was decorator for _on_port_scan_result → now before _send_wol
    5776,   # was decorator for _on_ipv6_result → now before cloud metadata section
    5861,   # was decorator for _on_cloud_local/network_result → now before log chart
    7579,   # was decorator for _on_snmp_result → now before SYN scan section
    7724,   # was decorator for _on_syn_result → now before UDP scan section
    7776,   # was decorator for _on_udp_result → now before OS fingerprint section
    7831,   # was decorator for _on_os_result → now before risk scorer section
    7958,   # was decorator for _on_cve_result → now before exposure section
    8018,   # was decorator for _on_exposure_result → now before help page section
    10572,  # was decorator for _on_hardware_plugin_result → now before cred scan
    10687,  # was decorator for _on_m2_result or similar → now before combined discovery
    10756,  # was decorator for _on_m3_result or similar → now before SMB section
    10849,  # was decorator for _on_m4_result or similar → now before plugin section
    10258,  # was decorator for _on_m5_result → now before _refresh_graph (CRASH)
}

lines = DASHBOARD.read_text(encoding="utf-8").splitlines(keepends=False)
kept = []
removed = []
for i, line in enumerate(lines):
    lineno = i + 1
    if lineno in ORPHAN_LINES:
        removed.append((lineno, line.strip()))
    else:
        kept.append(line)

DASHBOARD.write_text("\n".join(kept) + "\n", encoding="utf-8")
print(f"Removed {len(removed)} orphaned decorator lines:")
for ln, text in sorted(removed):
    print(f"  line {ln}: {text}")
print(f"dashboard.py: {len(lines)} -> {len(kept)} lines")
