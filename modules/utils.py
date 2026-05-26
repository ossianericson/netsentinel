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

    Stale caches cause scans to show devices that are no longer present and
    miss devices that have recently joined.  Flushing before a scan ensures
    the ARP table reflects the current live state of the network.
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
    if system == "Windows":
        _si = subprocess.STARTUPINFO()
        _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        _si.wShowWindow = 0
        extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": _si}
    else:
        extra = {}
    info: dict = {
        "local_ips":   [],   # [{"ip": ..., "mask": ..., "adapter": ...}]
        "gateway":     None,
        "dns_servers": [],
        "domain":      "",
    }

    if system == "Windows":
        try:
            import winreg as _wr
            import psutil as _ps
            import socket as _sock

            # Local IPs and masks via psutil (no subprocess needed)
            for iface, addr_list in _ps.net_if_addrs().items():
                for addr in addr_list:
                    if addr.family == _sock.AF_INET and not addr.address.startswith("127."):
                        info["local_ips"].append(
                            {"ip": addr.address, "mask": addr.netmask or "", "adapter": iface}
                        )

            _PARAMS = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters"
            _IFACES = _PARAMS + r"\Interfaces"

            def _rval(key, name, default=""):
                try:
                    v = _wr.QueryValueEx(key, name)[0]
                    if isinstance(v, list):
                        v = v[0] if v else ""
                    return v or default
                except OSError:
                    return default

            # Top-level domain suffix
            try:
                with _wr.OpenKey(_wr.HKEY_LOCAL_MACHINE, _PARAMS) as k:
                    info["domain"] = _rval(k, "Domain") or _rval(k, "DhcpDomain")
            except OSError:
                pass

            # Gateway, DNS, per-interface domain via registry
            try:
                with _wr.OpenKey(_wr.HKEY_LOCAL_MACHINE, _IFACES) as k:
                    idx = 0
                    while True:
                        try:
                            guid = _wr.EnumKey(k, idx)
                            idx += 1
                        except OSError:
                            break
                        try:
                            with _wr.OpenKey(k, guid) as ik:
                                dhcp_ip = _rval(ik, "DhcpIPAddress")
                                static_ip = _rval(ik, "IPAddress")
                                has_ip = (
                                    (dhcp_ip and dhcp_ip not in ("0.0.0.0", ""))
                                    or (static_ip and static_ip not in ("0.0.0.0", ""))
                                )
                                if not has_ip:
                                    continue
                                if not info["gateway"]:
                                    for gk in ("DefaultGateway", "DhcpDefaultGateway"):
                                        gw = _rval(ik, gk)
                                        if gw and re.match(r"\d+\.\d+\.\d+", gw):
                                            info["gateway"] = gw.split()[0]
                                            break
                                for dk in ("NameServer", "DhcpNameServer"):
                                    raw_dns = _rval(ik, dk)
                                    if raw_dns:
                                        for s in re.split(r"[,\s]+", raw_dns):
                                            if re.match(r"\d+\.\d+\.\d+\.\d+$", s):
                                                info["dns_servers"].append(s)
                                if not info["domain"]:
                                    info["domain"] = _rval(ik, "Domain") or _rval(ik, "DhcpDomain")
                        except OSError:
                            pass
            except OSError:
                pass
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
                import ctypes, struct
                _ip_bytes = socket.inet_aton(info["gateway"])
                _ip_dword = struct.unpack("I", _ip_bytes)[0]
                _mac_buf = (ctypes.c_ubyte * 6)()
                _mac_len = ctypes.c_ulong(6)
                if ctypes.windll.iphlpapi.SendARP(
                    _ip_dword, 0, ctypes.byref(_mac_buf), ctypes.byref(_mac_len)
                ) == 0:
                    info["gateway_mac"] = ":".join(f"{b:02x}" for b in _mac_buf)
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
    if system == "Windows":
        _si = subprocess.STARTUPINFO()
        _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        _si.wShowWindow = 0
        extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": _si}
    else:
        extra = {}
    result: dict = {
        "dhcp_enabled":    False,
        "dhcp_server":     "",
        "lease_obtained":  "",
        "lease_expires":   "",
        "lease_duration_h": 0.0,
    }

    if system == "Windows":
        try:
            import winreg as _wr
            _IFACES = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"

            def _rval(key, name, default=None):
                try:
                    return _wr.QueryValueEx(key, name)[0]
                except OSError:
                    return default

            with _wr.OpenKey(_wr.HKEY_LOCAL_MACHINE, _IFACES) as k:
                idx = 0
                while True:
                    try:
                        guid = _wr.EnumKey(k, idx)
                        idx += 1
                    except OSError:
                        break
                    try:
                        with _wr.OpenKey(k, guid) as ik:
                            if not _rval(ik, "EnableDHCP", 0):
                                continue
                            result["dhcp_enabled"] = True
                            srv = _rval(ik, "DhcpServer", "")
                            if srv and srv != "255.255.255.255":
                                result["dhcp_server"] = srv
                            for ts_key, res_key in (
                                ("LeaseObtainedTime", "lease_obtained"),
                                ("LeaseTerminatesTime", "lease_expires"),
                            ):
                                ts = _rval(ik, ts_key)
                                if ts:
                                    try:
                                        dt = datetime.datetime.fromtimestamp(ts)
                                        result[res_key] = dt.strftime(
                                            "%A, %B %d, %Y %I:%M:%S %p"
                                        )
                                    except Exception:
                                        pass
                            if result["dhcp_enabled"]:
                                break
                    except OSError:
                        pass
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
        # ── Adapter info via psutil (no subprocess) ──────────────────────────
        try:
            import psutil as _ps
            import socket as _sock

            if_addrs = _ps.net_if_addrs()
            if_stats = _ps.net_if_stats()

            for iface, addr_list in if_addrs.items():
                if "loopback" in iface.lower():
                    continue
                mac = ""
                ipv4 = ""
                connected = False
                t = (
                    "Wi-Fi"
                    if any(k in iface.lower() for k in ("wi-fi", "wireless", "wlan", "wifi"))
                    else "Ethernet"
                )
                for addr in addr_list:
                    if addr.family == _ps.AF_LINK:
                        mac = (addr.address or "").replace("-", ":").lower()
                    elif addr.family == _sock.AF_INET and not addr.address.startswith("127."):
                        ipv4 = addr.address
                        connected = True
                speed_mbps = 0
                if iface in if_stats:
                    st = if_stats[iface]
                    speed_mbps = st.speed
                    if not connected and st.isup:
                        connected = True
                adapters.append({
                    "name": iface, "type": t, "mac": mac, "ipv4": ipv4,
                    "speed_mbps": speed_mbps, "signal_pct": -1, "connected": connected,
                })
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
