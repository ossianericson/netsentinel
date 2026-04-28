"""
Shared utilities: admin-privilege detection, path helpers,
network-cache flushing, subnet ping sweep, and network-info gathering.
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


def _npcap_available(_cache: list = []) -> bool:   # noqa: B006
    if _cache:
        return _cache[0]

    system = platform.system()
    try:
        if system == "Windows":
            import winreg
            # Npcap installer writes to HKLM\SOFTWARE\Npcap
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
        else:   # Linux / other POSIX
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

    _cache.append(result)
    return result


def get_offenders_path() -> Path:
    """Locate offenders.json whether running from source or as a PyInstaller bundle."""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).parent.parent
    return base / "offenders.json"


# ── Network-cache flushing ────────────────────────────────────────────────────

def flush_network_caches() -> List[Tuple[str, bool]]:
    """
    Flush DNS resolver cache, ARP table and IPv6 neighbour cache.
    Returns list of (label, success) tuples.

    Stale caches cause scans to show devices that are no longer present and
    miss devices that have recently joined.  Flushing before a scan ensures
    the ARP table reflects the current live state of the network.
    """
    system = platform.system()
    extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if system == "Windows" else {}
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
    else:  # Linux
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
            if progress_cb and _count % 30 == 0:
                progress_cb(f"Ping sweep: {_count}/{len(hosts)} hosts\u2026")

    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as ex:
        for ip, alive in ex.map(_ping, hosts):
            if alive:
                responsive.append(ip)
    return responsive


# ── Network info ──────────────────────────────────────────────────────────────

def get_network_info() -> dict:
    """
    Collect local IP(s), subnet mask, default gateway and DNS servers.
    Returns dict with keys: local_ips (list of dicts), gateway (str|None),
    dns_servers (list of str), domain (str).
    """
    system = platform.system()
    extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if system == "Windows" else {}
    info: dict = {
        "local_ips":   [],   # [{"ip": ..., "mask": ..., "adapter": ...}]
        "gateway":     None,
        "dns_servers": [],
        "domain":      "",
    }

    if system == "Windows":
        try:
            raw = subprocess.check_output(["ipconfig", "/all"], text=True, timeout=10, **extra)
            current_adapter = "Unknown"
            last_was_dns = False
            for line in raw.splitlines():
                stripped = line.strip()
                if line and not line[0].isspace() and ":" in line and len(line) < 80:
                    current_adapter = line.split(":")[0].strip()
                    last_was_dns = False
                elif "IPv4 Address" in stripped:
                    m = re.search(r"(\d+\.\d+\.\d+\.\d+)", stripped)
                    if m:
                        info["local_ips"].append(
                            {"ip": m.group(1), "mask": "", "adapter": current_adapter}
                        )
                    last_was_dns = False
                elif "Subnet Mask" in stripped:
                    m = re.search(r"(\d+\.\d+\.\d+\.\d+)", stripped)
                    if m and info["local_ips"]:
                        info["local_ips"][-1]["mask"] = m.group(1)
                    last_was_dns = False
                elif "Default Gateway" in stripped:
                    m = re.search(r"(\d+\.\d+\.\d+\.\d+)", stripped)
                    if m and not info["gateway"]:
                        info["gateway"] = m.group(1)
                    last_was_dns = False
                elif "DNS Servers" in stripped:
                    m = re.search(r"(\d+\.\d+\.\d+\.\d+)", stripped)
                    if m:
                        info["dns_servers"].append(m.group(1))
                    last_was_dns = True
                elif last_was_dns and re.match(r"^\s{20,}\d+\.\d+\.\d+\.\d+", line):
                    m = re.search(r"(\d+\.\d+\.\d+\.\d+)", stripped)
                    if m:
                        info["dns_servers"].append(m.group(1))
                elif "DNS Suffix" in stripped and not info["domain"]:
                    m = re.search(r":\s*(\S+)", stripped)
                    if m and m.group(1) not in (":", ""):
                        info["domain"] = m.group(1)
                    last_was_dns = False
                elif stripped:
                    last_was_dns = False
        except Exception:
            pass

    elif system == "Darwin":
        try:
            for iface in ("en0", "en1"):
                try:
                    ip = subprocess.check_output(
                        ["ipconfig", "getifaddr", iface],
                        text=True, timeout=5, stderr=subprocess.DEVNULL,
                    ).strip()
                    if ip:
                        info["local_ips"].append({"ip": ip, "mask": "", "adapter": iface})
                except Exception:
                    pass
        except Exception:
            pass
        try:
            raw = subprocess.check_output(["route", "get", "default"], text=True, timeout=5)
            m = re.search(r"gateway:\s*(\d+\.\d+\.\d+\.\d+)", raw)
            if m:
                info["gateway"] = m.group(1)
        except Exception:
            pass
        try:
            with open("/etc/resolv.conf") as f:
                for line in f:
                    if line.startswith("nameserver"):
                        info["dns_servers"].append(line.split()[1].strip())
        except Exception:
            pass

    else:  # Linux
        try:
            raw = subprocess.check_output(["ip", "addr", "show"], text=True, timeout=5)
            for m in re.finditer(
                r"inet (\d+\.\d+\.\d+\.\d+)/(\d+).*?scope global", raw
            ):
                info["local_ips"].append({"ip": m.group(1), "mask": m.group(2), "adapter": ""})
        except Exception:
            pass
        try:
            raw = subprocess.check_output(
                ["ip", "route", "show", "default"], text=True, timeout=5
            )
            m = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", raw)
            if m:
                info["gateway"] = m.group(1)
        except Exception:
            pass
        try:
            with open("/etc/resolv.conf") as f:
                for line in f:
                    if line.startswith("nameserver"):
                        info["dns_servers"].append(line.split()[1].strip())
        except Exception:
            pass

    # De-duplicate DNS servers while preserving order
    seen: set = set()
    info["dns_servers"] = [
        s for s in info["dns_servers"] if not (s in seen or seen.add(s))  # type: ignore[func-returns-value]
    ]

    # Resolve gateway MAC from ARP cache (used by STP rogue-root detection)
    info["gateway_mac"] = None
    if info["gateway"]:
        try:
            if platform.system() == "Windows":
                arp_out = subprocess.check_output(
                    ["arp", "-a", info["gateway"]], text=True, timeout=5, **extra
                )
                m = re.search(r"([0-9a-f]{2}[:-]){5}[0-9a-f]{2}", arp_out, re.IGNORECASE)
            else:
                arp_out = subprocess.check_output(
                    ["arp", "-n", info["gateway"]], text=True, timeout=5
                )
                m = re.search(r"([0-9a-f]{2}:){5}[0-9a-f]{2}", arp_out, re.IGNORECASE)
            if m:
                info["gateway_mac"] = m.group(0).lower()
        except Exception:
            pass

    return info


# ── DHCP lease info ───────────────────────────────────────────────────────────

def get_dhcp_info() -> dict:
    """
    Return DHCP lease details for the primary connected adapter.

    Keys: dhcp_enabled (bool), dhcp_server (str), lease_obtained (str),
          lease_expires (str), lease_duration_h (float).
    Empty strings / 0.0 when not available or DHCP is off.
    """
    import datetime
    system = platform.system()
    extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if system == "Windows" else {}
    result: dict = {
        "dhcp_enabled":    False,
        "dhcp_server":     "",
        "lease_obtained":  "",
        "lease_expires":   "",
        "lease_duration_h": 0.0,
    }

    if system == "Windows":
        try:
            raw = subprocess.check_output(["ipconfig", "/all"], text=True, timeout=10, **extra)
            in_section = False
            for line in raw.splitlines():
                stripped = line.strip()
                if "DHCP Enabled" in stripped:
                    in_section = "Yes" in stripped
                    if in_section:
                        result["dhcp_enabled"] = True
                if not in_section:
                    continue
                if "DHCP Server" in stripped:
                    m = re.search(r":\s*(\S+)", stripped)
                    if m:
                        result["dhcp_server"] = m.group(1)
                elif "Lease Obtained" in stripped:
                    m = re.search(r":\s*(.+)", stripped)
                    if m:
                        result["lease_obtained"] = m.group(1).strip()
                elif "Lease Expires" in stripped:
                    m = re.search(r":\s*(.+)", stripped)
                    if m:
                        result["lease_expires"] = m.group(1).strip()
        except Exception:
            pass
        # Compute duration
        if result["lease_obtained"] and result["lease_expires"]:
            for fmt in (
                "%A, %B %d, %Y %I:%M:%S %p",   # Tuesday, April 22, 2025 10:30:00 AM
                "%d/%m/%Y %H:%M:%S",             # European locale
                "%m/%d/%Y %H:%M:%S",
            ):
                try:
                    t0 = datetime.datetime.strptime(result["lease_obtained"], fmt)
                    t1 = datetime.datetime.strptime(result["lease_expires"], fmt)
                    result["lease_duration_h"] = round((t1 - t0).total_seconds() / 3600, 1)
                    break
                except ValueError:
                    pass

    elif system == "Darwin":
        for iface in ("en0", "en1"):
            try:
                raw = subprocess.check_output(
                    ["ipconfig", "getpacket", iface],
                    text=True, timeout=6, stderr=subprocess.DEVNULL,
                )
                if "dhcp_server_identifier" in raw:
                    result["dhcp_enabled"] = True
                    m = re.search(r"dhcp_server_identifier[^:]*:\s*([\d.]+)", raw)
                    if m:
                        result["dhcp_server"] = m.group(1)
                    m = re.search(r"lease_time.*?:\s*(\d+)", raw)
                    if m:
                        result["lease_duration_h"] = round(int(m.group(1)) / 3600, 1)
                    break
            except Exception:
                pass

    else:  # Linux — try nmcli first, fallback to dhclient lease file
        try:
            raw = subprocess.check_output(
                ["nmcli", "-f", "IP4.GATEWAY,DHCP4.OPTION", "device", "show"],
                text=True, timeout=6, stderr=subprocess.DEVNULL,
            )
            if "dhcp_server_identifier" in raw:
                result["dhcp_enabled"] = True
                m = re.search(r"dhcp_server_identifier\s*=\s*([\d.]+)", raw)
                if m:
                    result["dhcp_server"] = m.group(1)
        except Exception:
            pass
        if not result["dhcp_server"]:
            try:
                for lease_file in [
                    "/var/lib/dhcp/dhclient.leases",
                    "/var/lib/NetworkManager/internal.conf",
                ]:
                    p = Path(lease_file)
                    if p.exists():
                        text = p.read_text()
                        m = re.search(r"dhcp-server-identifier\s+([\d.]+)", text)
                        if m:
                            result["dhcp_enabled"] = True
                            result["dhcp_server"] = m.group(1)
                        break
            except Exception:
                pass

    return result


# ── Network adapter details ───────────────────────────────────────────────────

def get_interface_details() -> List[dict]:
    """
    Return a list of network adapters (excluding loopback) with fields:
      name, type ("Wi-Fi"/"Ethernet"), mac, ipv4, speed_mbps (int),
      signal_pct (int, -1 if not wireless), connected (bool).

    Windows: `ipconfig /all` + `netsh wlan show interfaces`.
    macOS:   `networksetup -listallhardwareports`.
    Linux:   /sys/class/net.
    """
    system = platform.system()
    extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if system == "Windows" else {}
    adapters: List[dict] = []

    if system == "Windows":
        # ── Parse ipconfig /all for sections ────────────────────────────────
        try:
            raw = subprocess.check_output(["ipconfig", "/all"], text=True, timeout=10, **extra)
            current: dict = {}

            def _flush() -> None:
                if current.get("name") and current["type"] != "Loopback":
                    adapters.append(dict(current))

            for line in raw.splitlines():
                # Section header: "Ethernet adapter Ethernet:" / "Wireless LAN adapter Wi-Fi:"
                if line and not line[0].isspace() and "adapter" in line.lower():
                    _flush()
                    name = line.split(":")[0].strip()
                    t = "Wi-Fi" if any(
                        k in line.lower() for k in ("wi-fi", "wireless", "wlan")
                    ) else "Loopback" if "loopback" in line.lower() else "Ethernet"
                    current = {
                        "name": name, "type": t, "mac": "",
                        "ipv4": "", "speed_mbps": 0,
                        "signal_pct": -1, "connected": False,
                    }
                stripped = line.strip()
                if "Physical Address" in stripped:
                    m = re.search(
                        r"([\dA-Fa-f]{2}[-:][\dA-Fa-f]{2}[-:][\dA-Fa-f]{2}"
                        r"[-:][\dA-Fa-f]{2}[-:][\dA-Fa-f]{2}[-:][\dA-Fa-f]{2})",
                        stripped,
                    )
                    if m:
                        current["mac"] = m.group(1).replace("-", ":").lower()
                elif "IPv4 Address" in stripped:
                    m = re.search(r"(\d+\.\d+\.\d+\.\d+)", stripped)
                    if m:
                        current["ipv4"] = m.group(1)
                        current["connected"] = True
                elif "Media State" in stripped and "disconnected" in stripped.lower():
                    current["connected"] = False
            _flush()
        except Exception:
            pass

        # ── WiFi signal + link speed from netsh wlan ────────────────────────
        try:
            raw = subprocess.check_output(
                ["netsh", "wlan", "show", "interfaces"],
                text=True, timeout=8, **extra,
            )
            signal_pct = -1
            tx_rate = 0
            ssid = ""
            for line in raw.splitlines():
                s = line.strip()
                if s.startswith("Signal") and ":" in s:
                    m = re.search(r":\s*(\d+)%", s)
                    if m:
                        signal_pct = int(m.group(1))
                elif "Transmit rate" in s and ":" in s:
                    m = re.search(r":\s*([\d.]+)", s)
                    if m:
                        tx_rate = int(float(m.group(1)))
                elif s.startswith("SSID") and "BSSID" not in s and ":" in s:
                    ssid = s.split(":", 1)[1].strip()
            for a in adapters:
                if a["type"] == "Wi-Fi" and a["connected"]:
                    a["signal_pct"] = signal_pct
                    if tx_rate:
                        a["speed_mbps"] = tx_rate
                    if ssid:
                        a["ssid"] = ssid
        except Exception:
            pass

        # ── Ethernet link speed via PowerShell Get-NetAdapter ───────────────
        try:
            raw = subprocess.check_output(
                [
                    "powershell", "-NonInteractive", "-NoProfile", "-Command",
                    "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | "
                    "Select-Object Name,LinkSpeed | ConvertTo-Csv -NoTypeInformation",
                ],
                text=True, timeout=8, **extra,
            )
            for line in raw.splitlines()[1:]:
                parts = [p.strip('"') for p in line.split(",")]
                if len(parts) == 2:
                    name, speed_str = parts
                    # speed_str like "1 Gbps" / "100 Mbps" / "54 Mbps"
                    m = re.search(r"([\d.]+)\s*(Gbps|Mbps|Kbps)", speed_str, re.I)
                    if m:
                        val = float(m.group(1))
                        unit = m.group(2).lower()
                        mbps = int(val * 1000 if unit == "gbps" else (val / 1000 if unit == "kbps" else val))
                        for a in adapters:
                            # match by partial name
                            if name.lower() in a["name"].lower() or a["name"].lower() in name.lower():
                                if a["speed_mbps"] == 0:
                                    a["speed_mbps"] = mbps
        except Exception:
            pass

    elif system == "Darwin":
        try:
            raw = subprocess.check_output(
                ["networksetup", "-listallhardwareports"],
                text=True, timeout=8,
            )
            current = {}
            for line in raw.splitlines():
                if line.startswith("Hardware Port:"):
                    if current.get("name"):
                        adapters.append(dict(current))
                    name = line.split(":", 1)[1].strip()
                    t = "Wi-Fi" if "wi-fi" in name.lower() or "airport" in name.lower() else "Ethernet"
                    current = {"name": name, "type": t, "mac": "", "ipv4": "",
                               "speed_mbps": 0, "signal_pct": -1, "connected": False}
                elif line.startswith("Ethernet Address:"):
                    current["mac"] = line.split(":", 1)[1].strip().lower()
                elif line.startswith("Device:"):
                    iface = line.split(":", 1)[1].strip()
                    try:
                        ip = subprocess.check_output(
                            ["ipconfig", "getifaddr", iface],
                            text=True, timeout=3, stderr=subprocess.DEVNULL,
                        ).strip()
                        if ip:
                            current["ipv4"] = ip
                            current["connected"] = True
                    except Exception:
                        pass
            if current.get("name"):
                adapters.append(dict(current))
        except Exception:
            pass

    else:  # Linux
        try:
            net_path = Path("/sys/class/net")
            for iface in net_path.iterdir():
                if iface.name == "lo":
                    continue
                t = "Wi-Fi" if (iface / "wireless").exists() else "Ethernet"
                mac = ""
                try:
                    mac = (iface / "address").read_text().strip()
                except Exception:
                    pass
                speed_mbps = 0
                try:
                    speed_mbps = int((iface / "speed").read_text().strip())
                except Exception:
                    pass
                connected = False
                ipv4 = ""
                try:
                    operstate = (iface / "operstate").read_text().strip()
                    connected = operstate == "up"
                except Exception:
                    pass
                try:
                    raw = subprocess.check_output(
                        ["ip", "-4", "addr", "show", iface.name],
                        text=True, timeout=4,
                    )
                    m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", raw)
                    if m:
                        ipv4 = m.group(1)
                        connected = True
                except Exception:
                    pass
                adapters.append({
                    "name": iface.name, "type": t, "mac": mac, "ipv4": ipv4,
                    "speed_mbps": speed_mbps, "signal_pct": -1, "connected": connected,
                })
        except Exception:
            pass

    return [a for a in adapters if a.get("name")]


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
        # Magic packet: 6x 0xFF + 16x MAC
        packet = b"\xff" * 6 + mac_bytes * 16
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(packet, (broadcast, 9))
        return True
    except Exception:
        return False


# ── Device baseline (new-device detection) ──────────────────────────────────

def _baseline_path() -> Path:
    p = Path.home() / "Documents" / "NetSentinel"
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
                progress_cb(f"CIDR sweep: {_count}/{len(hosts_list)} done\u2026")

    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as ex:
        for ip, alive in ex.map(_ping, hosts_list):
            if alive:
                responsive.append(ip)

    if progress_cb:
        progress_cb(f"CIDR sweep done: {len(responsive)} hosts responded in {cidr}.")
    return responsive


# ── IPv6 neighbour discovery ──────────────────────────────────────────────────

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
                # Format: <iface>  <ipv6>  <mac>  <state>
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
        pass
    return devices


# ── IPv6 active sweep ─────────────────────────────────────────────────────────

def ping_sweep_ipv6(progress_cb=None) -> List[dict]:
    """
    Discover IPv6 devices on the local link-local segment.

    Strategy:
      1. Read the OS neighbour cache via get_ipv6_devices() (no admin needed).
      2. Enumerate every active network interface that has a link-local IPv6
         address, then concurrently ping every address in the fe80::/10 range
         that is likely reachable (we ping the multicast all-nodes address and
         then sweep fe80::1 through fe80::ffff on each interface — fast & safe).
      3. After the sweep re-reads the neighbour cache to capture newly learned
         MACs and states.
      4. Deduplicates by ip6 and returns a merged list with source="cache" or
         source="active".

    Returns list of dicts: {ip6, mac, state, source}.
    Does NOT require admin on Windows.  On Linux/macOS requires a working
    ping6 / ping binary (standard on all platforms).
    """
    import concurrent.futures as _cf
    import socket as _socket

    system = platform.system()
    extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if system == "Windows" else {}

    # ── Step 1: cache ─────────────────────────────────────────────────────────
    if progress_cb:
        progress_cb("IPv6: reading neighbour cache…")
    cache_devices = get_ipv6_devices()
    results: List[dict] = [dict(d, source="cache") for d in cache_devices]
    seen_ip6: set = {d["ip6"] for d in cache_devices}

    # ── Step 2: enumerate link-local interfaces ───────────────────────────────
    # Each interface with a fe80:: address is a candidate for active sweep.
    iface_addrs: List[tuple] = []   # (iface_name, fe80_addr_with_scope)
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
        pass

    if not iface_addrs:
        if progress_cb:
            progress_cb("IPv6: no link-local interfaces found, using cache only.")
        return results

    # ── Step 3: send pings to well-known link-local multicast & short range ───
    # We ping ff02::1 (all-nodes) on each interface to solicit all devices,
    # then sweep fe80::1 … fe80::ffff for each interface.
    targets_per_iface: List[tuple] = []   # (ping_target_with_scope, iface_name)

    for iface_name, local_addr in iface_addrs:
        scope_id = local_addr.split("%")[1] if "%" in local_addr else iface_name
        targets_per_iface.append((f"ff02::1%{scope_id}", iface_name))
        for suffix in range(1, 0x100):      # fe80::1 … fe80::ff
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
            pass
        finally:
            done_count[0] += 1
            if progress_cb and done_count[0] % 64 == 0:
                progress_cb(f"IPv6 sweep: {done_count[0]}/{total} probes sent…")

    if progress_cb:
        progress_cb(f"IPv6: active sweep across {len(iface_addrs)} interface(s)…")

    with _cf.ThreadPoolExecutor(max_workers=64) as ex:
        list(ex.map(_ping6, targets_per_iface))

    # ── Step 4: re-read cache to capture newly learned entries ────────────────
    if progress_cb:
        progress_cb("IPv6: re-reading neighbour cache after sweep…")
    fresh = get_ipv6_devices()
    for d in fresh:
        if d["ip6"] not in seen_ip6:
            seen_ip6.add(d["ip6"])
            results.append(dict(d, source="active"))
        else:
            # Update existing entry's state if it improved (REACHABLE > STALE)
            for existing in results:
                if existing["ip6"] == d["ip6"]:
                    if d.get("state", "").upper() == "REACHABLE":
                        existing["state"] = d["state"]
                    break

    if progress_cb:
        progress_cb(f"IPv6: found {len(results)} device(s).")
    return results
