"""
Network info helpers — get_network_info(), get_dhcp_info(), get_interface_details().

Extracted from modules/utils.py (S2-3 sprint split).
All three functions are re-exported from modules/utils for backwards compatibility.
"""
import platform
import re
import subprocess
from pathlib import Path
from typing import List


def get_network_info() -> dict:
    """
    Collect local IP(s), subnet mask, default gateway and DNS servers.
    Returns dict with keys: local_ips (list of dicts), gateway (str|None),
    dns_servers (list of str), domain (str).
    """
    import socket as _sock
    system = platform.system()
    if system == "Windows":
        _si = subprocess.STARTUPINFO()
        _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        _si.wShowWindow = 0
        extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": _si}
    else:
        extra = {}
    info: dict = {
        "local_ips":   [],
        "gateway":     None,
        "dns_servers": [],
        "domain":      "",
    }

    if system == "Windows":
        try:
            import winreg as _wr
            import psutil as _ps

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

            try:
                with _wr.OpenKey(_wr.HKEY_LOCAL_MACHINE, _PARAMS) as k:
                    info["domain"] = _rval(k, "Domain") or _rval(k, "DhcpDomain")
            except OSError:
                pass  # non-fatal

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
                            pass  # non-fatal
            except OSError:
                pass  # non-fatal
        except Exception:
            pass  # non-fatal

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
                    pass  # non-fatal
        except Exception:
            pass  # non-fatal
        try:
            raw = subprocess.check_output(["route", "get", "default"], text=True, timeout=5)
            m = re.search(r"gateway:\s*(\d+\.\d+\.\d+\.\d+)", raw)
            if m:
                info["gateway"] = m.group(1)
        except Exception:
            pass  # non-fatal
        try:
            with open("/etc/resolv.conf") as f:
                for line in f:
                    if line.startswith("nameserver"):
                        info["dns_servers"].append(line.split()[1].strip())
        except Exception:
            pass  # non-fatal

    else:  # Linux
        try:
            raw = subprocess.check_output(["ip", "addr", "show"], text=True, timeout=5)
            for m in re.finditer(
                r"inet (\d+\.\d+\.\d+\.\d+)/(\d+).*?scope global", raw
            ):
                info["local_ips"].append({"ip": m.group(1), "mask": m.group(2), "adapter": ""})
        except Exception:
            pass  # non-fatal
        try:
            raw = subprocess.check_output(
                ["ip", "route", "show", "default"], text=True, timeout=5
            )
            m = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", raw)
            if m:
                info["gateway"] = m.group(1)
        except Exception:
            pass  # non-fatal
        try:
            with open("/etc/resolv.conf") as f:
                for line in f:
                    if line.startswith("nameserver"):
                        info["dns_servers"].append(line.split()[1].strip())
        except Exception:
            pass  # non-fatal

    seen: set = set()
    info["dns_servers"] = [
        s for s in info["dns_servers"] if not (s in seen or seen.add(s))  # type: ignore[func-returns-value]
    ]

    info["gateway_mac"] = None
    if info["gateway"]:
        try:
            import socket as _sock2
            if platform.system() == "Windows":
                import ctypes, struct
                _ip_bytes = _sock2.inet_aton(info["gateway"])
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
            pass  # non-fatal

    return info


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
                                        pass  # non-fatal
                            if result["dhcp_enabled"]:
                                break
                    except OSError:
                        pass  # non-fatal
        except Exception:
            pass  # non-fatal
        if result["lease_obtained"] and result["lease_expires"]:
            for fmt in (
                "%A, %B %d, %Y %I:%M:%S %p",
                "%d/%m/%Y %H:%M:%S",
                "%m/%d/%Y %H:%M:%S",
            ):
                try:
                    t0 = datetime.datetime.strptime(result["lease_obtained"], fmt)
                    t1 = datetime.datetime.strptime(result["lease_expires"], fmt)
                    result["lease_duration_h"] = round((t1 - t0).total_seconds() / 3600, 1)
                    break
                except ValueError:
                    pass  # non-fatal

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
                pass  # non-fatal

    else:  # Linux
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
            pass  # non-fatal
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
                pass  # non-fatal

    return result


def get_interface_details() -> List[dict]:
    """
    Return a list of network adapters (excluding loopback) with fields:
      name, type ("Wi-Fi"/"Ethernet"), mac, ipv4, speed_mbps (int),
      signal_pct (int, -1 if not wireless), connected (bool).

    Windows: psutil + ipconfig.
    macOS:   networksetup.
    Linux:   /sys/class/net.
    """
    system = platform.system()
    extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if system == "Windows" else {}
    adapters: List[dict] = []

    if system == "Windows":
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
            pass  # non-fatal

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
                        pass  # non-fatal
            if current.get("name"):
                adapters.append(dict(current))
        except Exception:
            pass  # non-fatal

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
                    pass  # non-fatal
                speed_mbps = 0
                try:
                    speed_mbps = int((iface / "speed").read_text().strip())
                except Exception:
                    pass  # non-fatal
                connected = False
                ipv4 = ""
                try:
                    operstate = (iface / "operstate").read_text().strip()
                    connected = operstate == "up"
                except Exception:
                    pass  # non-fatal
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
                    pass  # non-fatal
                adapters.append({
                    "name": iface.name, "type": t, "mac": mac, "ipv4": ipv4,
                    "speed_mbps": speed_mbps, "signal_pct": -1, "connected": connected,
                })
        except Exception:
            pass  # non-fatal

    return [a for a in adapters if a.get("name")]
