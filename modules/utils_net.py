"""
Network info helpers — get_network_info(), get_dhcp_info(), get_interface_details().

Extracted from modules/utils.py (S2-3 sprint split).
All three functions are re-exported from modules/utils for backwards compatibility.
"""
import platform
import re
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Tuple, TypeVar


def get_network_info() -> dict:
    """
    Collect local IP(s), subnet mask, default gateway and DNS servers.
    Returns dict with keys: local_ips (list of dicts), gateway (str|None),
    dns_servers (list of str), domain (str).
    """
    import socket as _sock
    system = platform.system()
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


def icmp_ping(host: str, timeout: float = 2.0) -> float:
    """Ping host once via the OS ping command. Returns RTT in ms, or -1.0 on failure/timeout.

    Shared by network_logger._ping_once and combined_discovery._ping_single so
    both scanners report identical RTT semantics (S-Phase2b).
    """
    system = platform.system()
    extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if system == "Windows" else {}
    try:
        if system == "Windows":
            r = subprocess.run(
                ["ping", "-n", "1", "-w", str(int(timeout * 1000)), host],
                capture_output=True, text=True, timeout=timeout + 2, **extra,
            )
            # "time=" is "tid=" on sv-SE and "tiempo=" on es-BO, so matching the
            # label returned -1.0 (i.e. "unreachable") for every reachable host on
            # a non-English Windows, killing RTT across network_logger and
            # combined_discovery. Match the untranslated reply structure instead.
            rtts = reply_rtts(r.stdout)
            if rtts:
                return rtts[0]
            # Fall back to a bare RTT match for output that carries no "TTL="
            # reply lines. Note "time<1ms" yields 1.0, not 0.5 — the original
            # code's 0.5 branch sat after a regex that already matched "<", so it
            # was unreachable; tests/test_utils_net.py pins that 1.0 contract.
            m = _REPLY_RTT_RE.search(r.stdout)
            if m:
                return _rtt_float(m.group(1))
        else:
            r = subprocess.run(
                ["ping", "-c", "1", "-W", str(int(timeout)), host],
                capture_output=True, text=True, timeout=timeout + 2,
            )
            m = re.search(r"time=([\d.]+)\s*ms", r.stdout)
            if m:
                return float(m.group(1))
    except Exception:
        pass  # non-fatal
    return -1.0


def tcp_probe(host: str, port: int, timeout: float = 3.0) -> Tuple[bool, float, str]:
    """Attempt a TCP connect to host:port. Returns (ok, rtt_ms, error).

    rtt_ms is -1.0 on failure; error is "" on success, str(exception) otherwise.
    Shared by ha_detector, cloud_metadata, isp_vs_router_test, private_endpoint_checker,
    service_monitor, and service_diagnostics_probes so every TCP reachability check
    reports identical connect-timing semantics (P4).
    """
    t0 = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, (time.monotonic() - t0) * 1000, ""
    except (OSError, UnicodeError, OverflowError) as exc:
        # UnicodeError: socket.create_connection IDNA-encodes the host, and a label
        # over 63 bytes raises it — ordinary wherever hostnames are not Latin script.
        # OverflowError: a port outside 0-65535, reachable from any user-typed target.
        # Neither is an OSError, and the callers (cloud_metadata._tcp_connect,
        # ha_detector._tcp_open) have no local guard, so an escape reaches a worker
        # instead of being reported as an unreachable host.
        return False, -1.0, str(exc)


def get_arp_snapshot() -> Dict[str, str]:
    """Return {ip: mac (lowercase, colon-separated)} from the OS ARP cache.

    POSIX tries `arp -n` first (no reverse-DNS lookups), falling back to `arp -a`
    if that fails. The broadcast MAC (ff:ff:ff:ff:ff:ff) and multicast/broadcast
    IPs (224.0.0.0/4, x.x.x.255) are filtered out — neither represents a real
    device. Shared by combined_discovery, network_logger, passive_observer,
    rogue_device, and dhcp_lease_scanner so all ARP-cache reads use identical
    parsing (P4).
    """
    system = platform.system()
    extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if system == "Windows" else {}
    result: Dict[str, str] = {}

    def _add(ip: str, mac: str) -> None:
        mac = mac.replace("-", ":").lower()
        if mac == "ff:ff:ff:ff:ff:ff" or ip.startswith("224.") or ip.endswith(".255"):
            return
        result[ip] = mac

    try:
        if system == "Windows":
            raw = subprocess.check_output(["arp", "-a"], text=True, timeout=10, **extra)
            for line in raw.splitlines():
                m = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([\da-fA-F-]{17})", line)
                if m:
                    _add(m.group(1), m.group(2))
        else:
            try:
                raw = subprocess.check_output(["arp", "-n"], text=True, timeout=10)
            except subprocess.CalledProcessError:
                raw = subprocess.check_output(["arp", "-a"], text=True, timeout=10)
            for line in raw.splitlines():
                m = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+\S+\s+([\da-fA-F:]{17})", line)
                if not m:
                    m = re.search(r"(\d+\.\d+\.\d+\.\d+).*?([\da-fA-F:]{17})", line)
                if m:
                    _add(m.group(1), m.group(2))
    except Exception:
        pass  # non-fatal — ARP table read is best-effort
    return result


_T = TypeVar("_T")
_R = TypeVar("_R")


def parallel_map(fn: Callable[[_T], _R], items: Iterable[_T], workers: int = 8) -> List[_R]:
    """Run fn(item) across items on a bounded thread pool; returns results in input order.

    Thin wrapper around ThreadPoolExecutor.map so scan-worker fan-outs (host discovery,
    hostname resolution, TCP/SNMP polling) share one pool-sizing and iteration idiom (P4).
    An exception raised by fn propagates to the caller exactly as ThreadPoolExecutor.map
    does — wrap fn yourself if you need a per-item fallback value instead of a raised
    exception, or need incremental per-item progress reporting.
    """
    items = list(items)
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=min(workers, len(items))) as ex:
        return list(ex.map(fn, items))


def get_local_mac_label_map() -> dict:
    """Return {mac (lowercase) -> "This PC (<hostname>)"} for this machine's own adapters.

    Used to overlay device-label maps (App Traffic, Bandwidth Usage, Timeline, ...) so
    traffic captured from the box the app is running on never displays as a bare MAC.
    """
    label_map: dict = {}
    try:
        import socket
        hostname = socket.gethostname()
        for iface in get_interface_details():
            mac = (iface.get("mac") or "").lower()
            if mac:
                label_map[mac] = f"This PC ({hostname})"
    except Exception:
        pass  # non-fatal — local adapter enumeration is best-effort
    return label_map


# ── Locale-independent ping parsing ──────────────────────────────────────────
# Windows translates every ping label ("time=" -> "tid=" / "tiempo=" / "время="),
# and on Cyrillic locales it translates the *unit* too: ru/uk/bg emit "44мс", not
# "44ms". "TTL=" and the "="/"<" separator do stay English everywhere, so those
# remain the anchors.
#
# RTT_UNIT is an enumerated set, deliberately NOT generalised to "a short letter
# run after the number". Measured against real output, a generic run reads
# `bytes=32 time<1ms TTL=64` — plain en-US, the shape every LAN ping produces —
# as 32, because "time" is followed by "<" rather than "=". Add a spelling here
# when a real sample turns one up; never widen the shape.
#
# Shared with modules/service_diagnostics_probes.py and the three tracert parsers
# so every consumer reports identical semantics.
#
# The decimal separator has no observed trigger — every sampled Windows ping
# emits a whole number of milliseconds. The comma alternative is bounded to a
# 1-2 digit fraction on purpose: `1,234` is a decimal in de/fr/ru and a
# THOUSANDS grouping in en-US, and reading a grouped `1,234ms` as 1.234 would
# report a badly-latent link as excellent. No grouping produces a 1-2 digit
# tail, so an ambiguous `1,234` falls through to no match — a visible -1.0
# rather than a silent 1000x under-report.
RTT_UNIT = r"(?:ms|мс)"
_RTT_NUMBER = r"(\d+(?:\.\d+)?|\d+,\d{1,2})"
_REPLY_RTT_RE = re.compile(r"[=<]\s*" + _RTT_NUMBER + r"\s*" + RTT_UNIT, re.IGNORECASE)


def _rtt_float(raw: str) -> float:
    """Parse an RTT digit run that may carry a comma decimal separator."""
    return float(raw.replace(",", "."))


def reply_rtts(output: str) -> list:
    """Return the RTT of every successful ping reply line, locale-independently."""
    rtts = []
    for line in output.splitlines():
        if "TTL=" not in line.upper():
            continue
        m = _REPLY_RTT_RE.search(line)
        if m:
            rtts.append(_rtt_float(m.group(1)))
    return rtts
