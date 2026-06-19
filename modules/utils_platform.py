"""
IPv6 network scanning helpers — get_ipv6_devices(), ping_sweep_ipv6().

Extracted from modules/utils.py (S2-3 sprint split).
Both functions are re-exported from modules/utils for backwards compatibility.
"""
import platform
import re
import subprocess
from typing import List


def get_ipv6_devices() -> List[dict]:
    """
    Read the IPv6 neighbour cache and return link-local and global devices.
    Returns list of dicts: {ip6, mac, state}.
    Does not require admin — reads the OS neighbour table.
    """
    system = platform.system()
    extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if system == "Windows" else {}
    devices: List[dict] = []
    seen: set = set()

    try:
        if system == "Windows":
            raw = subprocess.check_output(
                ["netsh", "interface", "ipv6", "show", "neighbors"], text=True, timeout=10, **extra
            )
            for line in raw.splitlines():
                parts = line.split()
                if len(parts) >= 3:
                    ipv6 = parts[0] if ":" in parts[0] else None
                    mac  = None
                    for p in parts:
                        if re.match(r"([0-9a-f]{2}-){5}[0-9a-f]{2}", p, re.IGNORECASE):
                            mac = p.replace("-", ":").lower()
                    if ipv6 and mac and ipv6 not in seen:
                        seen.add(ipv6)
                        devices.append({"ip6": ipv6, "mac": mac, "state": parts[-1] if len(parts) > 3 else ""})
        else:
            raw = subprocess.check_output(["ip", "-6", "neigh", "show"], text=True, timeout=10)
            for line in raw.splitlines():
                m = re.search(
                    r"^([\da-f:]+)\s+.*lladdr\s+([\da-f:]{17})\s+(\w+)", line, re.IGNORECASE
                )
                if m:
                    ipv6 = m.group(1)
                    mac  = m.group(2).lower()
                    state = m.group(3)
                    if ipv6 not in seen:
                        seen.add(ipv6)
                        devices.append({"ip6": ipv6, "mac": mac, "state": state})
    except Exception:
        pass  # non-fatal
    return devices


def ping_sweep_ipv6(progress_cb=None) -> List[dict]:
    """
    Discover IPv6 devices on the local link-local segment.

    Strategy:
      1. Read the OS neighbour cache via get_ipv6_devices() (no admin needed).
      2. Enumerate every active network interface that has a link-local IPv6
         address, then concurrently ping every address in the fe80::/10 range
         that is likely reachable.
      3. After the sweep re-reads the neighbour cache to capture newly learned
         MACs and states.
      4. Deduplicates by ip6 and returns a merged list with source="cache" or
         source="active".

    Returns list of dicts: {ip6, mac, state, source}.
    Does NOT require admin on Windows.
    """
    import concurrent.futures as _cf

    system = platform.system()
    extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if system == "Windows" else {}

    if progress_cb:
        progress_cb("IPv6: reading neighbour cache…")
    cache_devices = get_ipv6_devices()
    results: List[dict] = [dict(d, source="cache") for d in cache_devices]
    seen_ip6: set = {d["ip6"] for d in cache_devices}

    iface_addrs: List[tuple] = []
    try:
        if system == "Windows":
            raw = subprocess.check_output(
                ["netsh", "interface", "ipv6", "show", "addresses"],
                text=True, timeout=10, **extra,
            )
            current_iface = None
            for line in raw.splitlines():
                m_iface = re.search(r"Interface\s+\d+:\s+(.+)", line)
                if m_iface:
                    current_iface = m_iface.group(1).strip()
                m_addr = re.search(r"(fe80::[0-9a-f:%]+)", line, re.IGNORECASE)
                if m_addr and current_iface:
                    iface_addrs.append((current_iface, m_addr.group(1).lower()))
        else:
            raw = subprocess.check_output(["ip", "-6", "addr", "show"], text=True, timeout=10)
            current_iface = None
            for line in raw.splitlines():
                m_iface = re.match(r"^\d+:\s+(\S+):", line)
                if m_iface:
                    current_iface = m_iface.group(1)
                m_addr = re.search(r"inet6\s+(fe80::[0-9a-f:]+)/", line, re.IGNORECASE)
                if m_addr and current_iface:
                    iface_addrs.append((current_iface, f"{m_addr.group(1).lower()}%{current_iface}"))
    except Exception:
        pass  # non-fatal

    if not iface_addrs:
        if progress_cb:
            progress_cb("IPv6: no link-local interfaces found, using cache only.")
        return results

    targets_per_iface: List[tuple] = []
    for iface_name, local_addr in iface_addrs:
        scope_id = local_addr.split("%")[1] if "%" in local_addr else iface_name
        targets_per_iface.append((f"ff02::1%{scope_id}", iface_name))
        for suffix in range(1, 0x100):
            targets_per_iface.append((f"fe80::{suffix:x}%{scope_id}", iface_name))

    total = len(targets_per_iface)
    done_count = [0]

    def _ping6(target_iface: tuple) -> None:
        target, _iface = target_iface
        try:
            if system == "Windows":
                subprocess.run(
                    ["ping", "-6", "-n", "1", "-w", "300", target],
                    capture_output=True, timeout=2, **extra,
                )
            else:
                subprocess.run(
                    ["ping6", "-c", "1", "-W", "1", target],
                    capture_output=True, timeout=2,
                )
        except Exception:
            pass  # non-fatal
        finally:
            done_count[0] += 1
            if progress_cb and done_count[0] % 64 == 0:
                progress_cb(f"IPv6 sweep: {done_count[0]}/{total} probes sent…")

    if progress_cb:
        progress_cb(f"IPv6: active sweep across {len(iface_addrs)} interface(s)…")

    with _cf.ThreadPoolExecutor(max_workers=64) as ex:
        list(ex.map(_ping6, targets_per_iface))

    if progress_cb:
        progress_cb("IPv6: re-reading neighbour cache after sweep…")
    fresh = get_ipv6_devices()
    for d in fresh:
        if d["ip6"] not in seen_ip6:
            seen_ip6.add(d["ip6"])
            results.append(dict(d, source="active"))
        else:
            for existing in results:
                if existing["ip6"] == d["ip6"]:
                    if d.get("state", "").upper() == "REACHABLE":
                        existing["state"] = d["state"]
                    break

    if progress_cb:
        progress_cb(f"IPv6: found {len(results)} device(s).")
    return results
