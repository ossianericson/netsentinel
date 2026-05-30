"""
Shared utilities: admin-privilege detection, path helpers,
network-cache flushing, subnet ping sweep, and device baseline management.

Network-info functions (get_network_info, get_dhcp_info, get_interface_details)
live in modules/utils_net.py and are re-exported here for backwards compatibility.

IPv6 scanning functions (get_ipv6_devices, ping_sweep_ipv6) live in
modules/utils_platform.py and are re-exported here for backwards compatibility.
"""
import concurrent.futures
import os
import platform
import re
import socket
import subprocess
import sys
import threading
from pathlib import Path
from typing import List, Optional, Tuple

# Backwards-compatible re-exports (do not remove — callers import from here)
from modules.utils_net import get_network_info, get_dhcp_info, get_interface_details
from modules.utils_platform import get_ipv6_devices, ping_sweep_ipv6


def is_admin() -> bool:
    """Return True if the process has administrator / root privileges."""
    system = platform.system()
    try:
        if system == "Windows":
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:
            return os.getuid() == 0
    except Exception:
        return False


_is_store_app_cache: list = []


def is_store_app() -> bool:
    """Return True when running inside a Windows Store MSIX package (AppContainer).

    Uses GetPackageFamilyName(): returns ERROR_INSUFFICIENT_BUFFER (122) when
    the process is packaged, APPMODEL_ERROR_NO_PACKAGE (15700) when it is not.
    Cached after first call — the result never changes within a process lifetime.
    Always returns False on non-Windows platforms.
    """
    if _is_store_app_cache:
        return _is_store_app_cache[0]
    result = False
    if platform.system() == "Windows":
        try:
            import ctypes
            buf_len = ctypes.c_uint32(0)
            ret = ctypes.windll.kernel32.GetPackageFamilyName(
                ctypes.windll.kernel32.GetCurrentProcess(),
                ctypes.byref(buf_len),
                None,
            )
            result = (ret == 122)  # ERROR_INSUFFICIENT_BUFFER → we are packaged
        except Exception:
            result = False
    _is_store_app_cache.append(result)
    return result


# ── Npcap / libpcap detection ─────────────────────────────────────────────────

def is_npcap_available() -> bool:
    """
    Return True if the packet-capture driver needed by Scapy is installed.

    Windows  — checks the Npcap registry installation key (instantaneous).
    macOS    — checks for libpcap shared library in standard locations.
    Linux    — checks for libpcap shared library in standard locations.

    Cached after first call so repeated page-builds are free.
    """
    return _npcap_available()


_npcap_cache: list = []


def _npcap_available() -> bool:
    if _npcap_cache:
        return _npcap_cache[0]

    system = platform.system()
    try:
        if system == "Windows":
            import winreg
            winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Npcap",
                access=winreg.KEY_READ | winreg.KEY_WOW64_32KEY,
            ).Close()
            result = True
        elif system == "Darwin":
            result = any(
                Path(p).exists() for p in [
                    "/usr/lib/libpcap.dylib",
                    "/usr/local/lib/libpcap.dylib",
                    "/opt/homebrew/lib/libpcap.dylib",
                ]
            )
        else:
            result = any(
                Path(p).exists() for p in [
                    "/usr/lib/libpcap.so.0",
                    "/usr/lib/libpcap.so",
                    "/usr/lib/x86_64-linux-gnu/libpcap.so.0.8",
                    "/usr/lib/x86_64-linux-gnu/libpcap.so.1",
                ]
            )
    except Exception:
        result = False

    _npcap_cache.append(result)
    return result


def get_offenders_path() -> Path:
    """Locate offenders.json whether running from source or as a PyInstaller bundle."""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).parent.parent
    return base / "offenders.json"


def get_app_data_dir() -> Path:
    """
    Return the per-user application data directory for NetSentinel.

    Platform mapping
    ────────────────
    Windows  → %LOCALAPPDATA%\\NetSentinel
    macOS    → ~/Library/Application Support/NetSentinel
    Linux    → $XDG_CONFIG_HOME/NetSentinel  (default: ~/.config/NetSentinel)

    The directory is created with exist_ok=True before returning.
    """
    import platform as _plat
    system = _plat.system()
    if system == "Windows":
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        app_dir = Path(local) / "NetSentinel"
    elif system == "Darwin":
        app_dir = Path.home() / "Library" / "Application Support" / "NetSentinel"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME", "")
        base = Path(xdg) if xdg else Path.home() / ".config"
        app_dir = base / "NetSentinel"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


# ── Network-cache flushing ────────────────────────────────────────────────────

def flush_network_caches() -> List[Tuple[str, bool]]:
    """
    Flush DNS resolver cache, ARP table and IPv6 neighbour cache.
    Returns list of (label, success) tuples.
    """
    system = platform.system()
    if system == "Windows":
        _si = subprocess.STARTUPINFO()
        _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        _si.wShowWindow = 0  # SW_HIDE
        extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": _si}
    else:
        extra = {}
    results: List[Tuple[str, bool]] = []

    if system == "Windows":
        commands: List[Tuple[str, List[str]]] = [
            ("Flush DNS cache",         ["ipconfig", "/flushdns"]),
            ("Clear ARP table",         ["arp", "-d", "*"]),
            ("Clear IPv6 neighbours",   ["netsh", "interface", "ipv6", "delete", "neighbors"]),
        ]
    elif system == "Darwin":
        commands = [
            ("Flush DNS cache",         ["dscacheutil", "-flushcache"]),
            ("Restart mDNSResponder",   ["killall", "-HUP", "mDNSResponder"]),
            ("Clear ARP table",         ["arp", "-d", "-a"]),
        ]
    else:
        commands = [
            ("Clear ARP/neigh table",   ["ip", "-s", "-s", "neigh", "flush", "all"]),
            ("Flush systemd DNS cache", ["resolvectl", "flush-caches"]),
        ]

    for label, cmd in commands:
        try:
            subprocess.run(cmd, timeout=6, capture_output=True, **extra)
            results.append((label, True))
        except Exception:
            results.append((label, False))
    return results


# ── Local-IP helper ───────────────────────────────────────────────────────────

def get_local_ip() -> str:
    """Return the primary local (non-loopback) IPv4 address via UDP trick."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


# ── Subnet ping sweep ─────────────────────────────────────────────────────────

def ping_sweep_subnet(local_ip: str, progress_cb=None) -> List[str]:
    """
    Concurrently ping all 254 hosts in the /24 that contains *local_ip*.

    Primary purpose: populate the OS ARP table so a subsequent 'arp -a'
    shows every live device, not just those already in the stale cache.
    Returns a list of IPs that responded.
    """
    system = platform.system()
    parts = local_ip.split(".")
    if len(parts) != 4:
        return []
    prefix = ".".join(parts[:3])
    hosts = [f"{prefix}.{i}" for i in range(1, 255)]
    if system == "Windows":
        _si = subprocess.STARTUPINFO()
        _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        _si.wShowWindow = 0
        extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": _si}
    else:
        extra = {}
    responsive: List[str] = []
    _lock = threading.Lock()
    done_count = [0]

    def _ping(ip: str) -> Tuple[str, bool]:
        try:
            if system == "Windows":
                r = subprocess.run(
                    ["ping", "-n", "1", "-w", "300", ip],
                    capture_output=True, timeout=2, **extra,
                )
            else:
                r = subprocess.run(
                    ["ping", "-c", "1", "-W", "1", ip],
                    capture_output=True, timeout=2,
                )
            return ip, r.returncode == 0
        except Exception:
            return ip, False
        finally:
            with _lock:
                done_count[0] += 1
                _count = done_count[0]
            if progress_cb and _count % 30 == 0:
                progress_cb(f"Ping sweep: {_count}/{len(hosts)} hosts…")

    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as ex:
        for ip, alive in ex.map(_ping, hosts):
            if alive:
                responsive.append(ip)
    return responsive


# ── Wake-on-LAN ────────────────────────────────────────────────────────────

def send_wol(mac: str, broadcast: str = "255.255.255.255") -> bool:
    """
    Send a Wake-on-LAN magic packet to the given MAC address.
    mac can be in any of: aa:bb:cc:dd:ee:ff, aa-bb-cc-dd-ee-ff, aabbccddeeff.
    Returns True on success, False on failure.
    """
    import struct as _struct
    try:
        mac_clean = mac.replace(":", "").replace("-", "").replace(".", "")
        if len(mac_clean) != 12:
            return False
        mac_bytes = bytes.fromhex(mac_clean)
        packet = b"\xff" * 6 + mac_bytes * 16
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(packet, (broadcast, 9))
        return True
    except Exception:
        return False


# ── Device baseline (new-device detection) ──────────────────────────────────

def _baseline_path() -> Path:
    p = get_app_data_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p / "device_baseline.json"


def load_device_baseline() -> dict:
    """
    Return {mac: {ip, hostname, vendor, first_seen, last_seen}} from the
    persistent baseline file.  Returns empty dict if none exists.
    """
    import json
    try:
        return json.loads(_baseline_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_device_baseline(baseline: dict) -> None:
    """Write the baseline dict back to disk."""
    import json
    try:
        _baseline_path().write_text(
            json.dumps(baseline, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def diff_devices_against_baseline(
    devices: List[dict],
    baseline: dict,
) -> List[dict]:
    """
    Compare a list of scan device dicts against the saved baseline.
    Returns a list of *new* devices (MAC not in baseline).
    Also updates last_seen for known devices and adds new ones.
    Each device dict must have at least keys: mac, ip, hostname, vendor.
    """
    import time as _time
    now = _time.strftime("%Y-%m-%dT%H:%M:%S")
    new_devices: List[dict] = []
    for d in devices:
        mac = (d.get("mac") or "").lower().strip()
        if not mac:
            continue
        if mac not in baseline:
            baseline[mac] = {
                "ip":         d.get("ip", ""),
                "hostname":   d.get("hostname", ""),
                "vendor":     d.get("vendor", ""),
                "first_seen": now,
                "last_seen":  now,
            }
            new_devices.append(d)
        else:
            baseline[mac]["last_seen"] = now
            baseline[mac]["ip"] = d.get("ip", baseline[mac]["ip"])
    return new_devices


# ── CIDR range ping sweep ─────────────────────────────────────────────────────

def ping_sweep_cidr(cidr: str, progress_cb=None) -> List[str]:
    """
    Ping sweep a CIDR range (e.g. '192.168.2.0/24', '10.0.0.0/22').
    Returns a list of responding IPs.
    Limited to /16 or smaller to avoid accidental huge sweeps.
    """
    import ipaddress as _ip
    try:
        network = _ip.ip_network(cidr, strict=False)
    except ValueError as exc:
        if progress_cb:
            progress_cb(f"Invalid CIDR '{cidr}': {exc}")
        return []

    if network.num_addresses > 65536:
        if progress_cb:
            progress_cb(f"Range {cidr} is too large (>{65536} hosts). Use /16 or smaller.")
        return []

    hosts_list = [str(h) for h in network.hosts()]
    if progress_cb:
        progress_cb(f"CIDR sweep: pinging {len(hosts_list)} hosts in {cidr}…")

    system = platform.system()
    extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if system == "Windows" else {}
    responsive: List[str] = []
    _lock = threading.Lock()
    done_count = [0]

    def _ping(ip: str) -> Tuple[str, bool]:
        try:
            if system == "Windows":
                r = subprocess.run(
                    ["ping", "-n", "1", "-w", "300", ip],
                    capture_output=True, timeout=2, **extra,
                )
            else:
                r = subprocess.run(
                    ["ping", "-c", "1", "-W", "1", ip],
                    capture_output=True, timeout=2,
                )
            return ip, r.returncode == 0
        except Exception:
            return ip, False
        finally:
            with _lock:
                done_count[0] += 1
                _count = done_count[0]
            if progress_cb and _count % 50 == 0:
                progress_cb(f"CIDR sweep: {_count}/{len(hosts_list)} done…")

    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as ex:
        for ip, alive in ex.map(_ping, hosts_list):
            if alive:
                responsive.append(ip)

    if progress_cb:
        progress_cb(f"CIDR sweep done: {len(responsive)} hosts responded in {cidr}.")
    return responsive
