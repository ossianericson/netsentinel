"""
Module 4 — Hidden SSID & Co-Channel Interference Scanner

Uses the system WiFi adapter to scan for:
  - Hidden / broadcast-suppressed SSIDs
  - Networks sharing channels with your primary connection
  - Known rogue setup SSIDs (GoogleSetup, _setup, Nest, etc.)
  - WPS-enabled networks (PIN brute-force attack surface)
  - Connected client list (devices associated to *your* AP, Windows only)

Windows: netsh wlan show networks mode=bssid  +  netsh wlan show hostednetwork
macOS:   /System/Library/PrivateFrameworks/Apple80211.framework/.../airport -s
Linux:   nmcli dev wifi  (fallback: iwlist scanning)
"""

import platform
import re
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# Suspicious SSID patterns (case-insensitive)
ROGUE_SSID_PATTERNS = [
    r"googlesetup",
    r"_setup",
    r"nest",
    r"_goog",
    r"chromecast",
    r"eerosetup",
    r"ring[-_]setup",
]

# Known 2.4GHz non-overlapping channels
CHANNELS_24GHZ = {1, 6, 11}
# Common 5GHz channels
CHANNELS_5GHZ = {36, 40, 44, 48, 149, 153, 157, 161}


@dataclass
class NetworkInfo:
    ssid: str           # empty string = hidden
    bssid: str
    channel: int = 0
    signal_dbm: int = -100
    band: str = "Unknown"   # 2.4GHz / 5GHz
    is_hidden: bool = False
    is_rogue_ssid: bool = False
    co_channel_conflict: bool = False
    wps_enabled: bool = False   # WPS detected (PIN brute-force risk)
    authentication: str = ""    # WPA2, WPA3, Open, etc.
    verdict: str = ""


@dataclass
class ConnectedClient:
    """A device currently associated to this machine's hosted/AP interface."""
    mac: str
    ip: str = ""
    hostname: str = ""
    signal_dbm: int = -100


@dataclass
class WifiScanResult:
    networks: List[NetworkInfo] = field(default_factory=list)
    my_channel: int = 0
    my_ssid: str = ""
    hidden_count: int = 0
    rogue_count: int = 0
    co_channel_count: int = 0
    wps_count: int = 0
    connected_clients: List[ConnectedClient] = field(default_factory=list)
    plain_verdict: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Platform-specific WiFi scan
# ---------------------------------------------------------------------------

def _channel_from_freq(freq_mhz: int) -> int:
    if 2412 <= freq_mhz <= 2484:
        if freq_mhz == 2484:
            return 14
        return (freq_mhz - 2412) // 5 + 1
    if 5170 <= freq_mhz <= 5825:
        return (freq_mhz - 5000) // 5
    return 0


def _band_from_channel(ch: int) -> str:
    if 1 <= ch <= 14:
        return "2.4GHz"
    if 36 <= ch <= 177:
        return "5GHz"
    return "Unknown"


def _scan_windows() -> Tuple[List[NetworkInfo], str, int]:
    """Returns (networks, my_ssid, my_channel)."""
    networks: List[NetworkInfo] = []
    my_ssid = ""
    my_channel = 0
    try:
        raw = subprocess.check_output(
            ["netsh", "wlan", "show", "networks", "mode=bssid"],
            text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception as exc:
        return networks, my_ssid, my_channel

    # Get current connection
    try:
        connected_raw = subprocess.check_output(
            ["netsh", "wlan", "show", "interfaces"],
            text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        m = re.search(r"SSID\s+:\s+(.+)", connected_raw)
        if m:
            my_ssid = m.group(1).strip()
        m = re.search(r"Channel\s+:\s+(\d+)", connected_raw)
        if m:
            my_channel = int(m.group(1))
    except Exception:
        pass

    # Parse network blocks
    blocks = re.split(r"SSID \d+ :", raw)[1:]
    for block in blocks:
        # Take only the first line for the SSID — strip CR so that CRLF output
        # from netsh on Windows doesn't let \s* consume the blank line and
        # capture the next field (e.g. "Network type : Infrastructure") as SSID.
        ssid = block.split("\n")[0].strip("\r").strip()

        bssids = re.findall(
            r"BSSID \d+\s+:\s+([\da-fA-F:]{17})", block
        )
        signals = re.findall(r"Signal\s+:\s+(\d+)%", block)
        channels = re.findall(r"Channel\s+:\s+(\d+)", block)

        for i, bssid in enumerate(bssids):
            ch = int(channels[i]) if i < len(channels) else 0
            sig_pct = int(signals[i]) if i < len(signals) else 50
            # Convert Windows signal % to approximate dBm
            sig_dbm = int(sig_pct / 2) - 100

            # WPS detection — look for "WPS" keyword in the block segment
            # netsh shows "Authentication" and sometimes "WPS" in the BSSID block
            wps = bool(re.search(r"WPS\s*:\s*Supported|WPS.*Yes", block, re.I))
            auth_m = re.search(r"Authentication\s*:\s*(.+)", block)
            auth = auth_m.group(1).strip() if auth_m else ""

            net = NetworkInfo(
                ssid=ssid,
                bssid=bssid.lower(),
                channel=ch,
                signal_dbm=sig_dbm,
                band=_band_from_channel(ch),
                is_hidden=(ssid == "" or ssid.lower() == "hidden network"),
                wps_enabled=wps,
                authentication=auth,
            )
            networks.append(net)

    return networks, my_ssid, my_channel


def _scan_macos() -> Tuple[List[NetworkInfo], str, int]:
    networks: List[NetworkInfo] = []
    my_ssid = ""
    my_channel = 0
    airport = (
        "/System/Library/PrivateFrameworks/Apple80211.framework"
        "/Versions/Current/Resources/airport"
    )
    try:
        raw = subprocess.check_output([airport, "-s"], text=True, timeout=15)
    except Exception:
        try:
            raw = subprocess.check_output(
                ["networksetup", "-listallhardwareports"], text=True, timeout=5
            )
        except Exception:
            return networks, my_ssid, my_channel

    # airport -s output: SSID  BSSID  RSSI  CHANNEL  HT  CC  SECURITY
    for line in raw.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            bssid = parts[-5] if len(parts) >= 5 else ""
            rssi = int(parts[-4]) if len(parts) >= 4 else -100
            ch_raw = parts[-3] if len(parts) >= 3 else "0"
            ch = int(re.match(r"(\d+)", ch_raw).group(1)) if re.match(r"\d", ch_raw) else 0
            ssid = " ".join(parts[:-5]).strip()
            net = NetworkInfo(
                ssid=ssid,
                bssid=bssid.lower(),
                channel=ch,
                signal_dbm=rssi,
                band=_band_from_channel(ch),
                is_hidden=(ssid == "" or ssid == "HIDDEN"),
            )
            networks.append(net)
        except Exception:
            continue

    return networks, my_ssid, my_channel


def _scan_linux() -> Tuple[List[NetworkInfo], str, int]:
    networks: List[NetworkInfo] = []
    my_ssid = ""
    my_channel = 0
    try:
        raw = subprocess.check_output(
            ["nmcli", "-t", "-f", "SSID,BSSID,CHAN,FREQ,SIGNAL", "dev", "wifi"],
            text=True, timeout=15,
        )
        for line in raw.splitlines():
            parts = line.split(":")
            if len(parts) < 5:
                continue
            ssid = parts[0]
            bssid = ":".join(parts[1:7]).lower()
            try:
                ch = int(parts[7]) if len(parts) > 7 else 0
                sig = int(parts[-1])
                sig_dbm = int(sig / 2) - 100
            except Exception:
                ch, sig_dbm = 0, -100
            net = NetworkInfo(
                ssid=ssid,
                bssid=bssid,
                channel=ch,
                signal_dbm=sig_dbm,
                band=_band_from_channel(ch),
                is_hidden=(ssid == "" or ssid == "--"),
            )
            networks.append(net)
    except Exception:
        pass
    return networks, my_ssid, my_channel


# ---------------------------------------------------------------------------
# Main scan function
# ---------------------------------------------------------------------------

def scan() -> WifiScanResult:
    system = platform.system()

    if system == "Windows":
        nets, my_ssid, my_channel = _scan_windows()
    elif system == "Darwin":
        nets, my_ssid, my_channel = _scan_macos()
    else:
        nets, my_ssid, my_channel = _scan_linux()

    result = WifiScanResult(my_ssid=my_ssid, my_channel=my_channel)

    if not nets:
        result.error = (
            "No WiFi networks found. Ensure WiFi is enabled and the adapter is active."
        )
        result.plain_verdict = result.error
        return result

    rogue_pat = re.compile("|".join(ROGUE_SSID_PATTERNS), re.IGNORECASE)

    # OUIs (xx:xx:xx) of every BSSID that broadcasts my primary SSID — these are
    # all radios on the same mesh hardware.  Hidden backhaul SSIDs share the same
    # OUI, so they are own infrastructure, not external co-channel interference.
    own_ouis: set = set()
    if my_ssid:
        own_ouis = {
            n.bssid[:8] for n in nets
            if n.ssid == my_ssid and len(n.bssid) >= 8
        }

    for net in nets:
        # Rogue SSID detection
        if rogue_pat.search(net.ssid):
            net.is_rogue_ssid = True
            net.verdict = (
                f"Suspicious SSID '{net.ssid}' matches known rogue device setup pattern. "
                f"Signal: {net.signal_dbm}dBm on channel {net.channel}."
            )

        # Co-channel interference (only flag if close in signal)
        if my_channel and net.channel == my_channel and net.ssid != my_ssid:
            net_oui = net.bssid[:8] if len(net.bssid) >= 8 else ""
            if net_oui and net_oui in own_ouis:
                # Same mesh hardware (hidden backhaul or secondary band) — not a conflict
                pass
            elif net.signal_dbm >= -70:
                net.co_channel_conflict = True
                if not net.verdict:
                    net.verdict = (
                        f"Co-channel interference: this {'hidden ' if net.is_hidden else ''}network "
                        f"is on your channel ({my_channel}) at {net.signal_dbm}dBm, "
                        "which will degrade your WiFi throughput."
                    )

        if not net.verdict:
            hidden_label = "[HIDDEN] " if net.is_hidden else ""
            net.verdict = (
                f"{hidden_label}SSID: '{net.ssid}', CH {net.channel} "
                f"({net.band}), {net.signal_dbm}dBm — no immediate threat."
            )

    result.networks = nets
    result.hidden_count = sum(1 for n in nets if n.is_hidden)
    result.rogue_count = sum(1 for n in nets if n.is_rogue_ssid)
    result.co_channel_count = sum(1 for n in nets if n.co_channel_conflict)
    result.wps_count = sum(1 for n in nets if n.wps_enabled)

    threats = []
    if result.rogue_count:
        rogue_names = [n.ssid or "[hidden]" for n in nets if n.is_rogue_ssid]
        threats.append(
            f"{result.rogue_count} suspicious SSID(s) detected: {', '.join(rogue_names)}"
        )
    if result.co_channel_count:
        threats.append(
            f"{result.co_channel_count} network(s) causing co-channel interference on "
            f"your channel ({my_channel})"
        )
    if result.hidden_count:
        threats.append(f"{result.hidden_count} hidden network(s) detected nearby")

    if threats:
        result.plain_verdict = "WiFi issues found: " + ". ".join(threats) + "."
    else:
        result.plain_verdict = (
            f"WiFi scan clean. {len(nets)} network(s) found. "
            "No rogue SSIDs or co-channel interference detected."
        )

    # Collect connected clients (Windows only — other platforms skipped gracefully)
    result.connected_clients = _get_connected_clients()

    return result


# ── Connected client list ─────────────────────────────────────────────────────

def _get_connected_clients() -> List[ConnectedClient]:
    """
    Return devices currently associated to this machine's WiFi adapter.

    Windows:  `netsh wlan show hostednetwork` lists associated stations.
              Falls back to parsing ARP table filtered by WiFi subnet.
    macOS/Linux: returns empty list (requires hostapd access — out of scope
                 for a passive scanner).
    """
    clients: List[ConnectedClient] = []
    if platform.system() != "Windows":
        return clients
    try:
        raw = subprocess.check_output(
            ["netsh", "wlan", "show", "hostednetwork"],
            text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        # Parse associated stations block
        in_stations = False
        for line in raw.splitlines():
            if "Number of clients" in line or "Stations" in line:
                in_stations = True
                continue
            if in_stations:
                m = re.search(r"([\da-fA-F]{2}(?:[:\-][\da-fA-F]{2}){5})", line)
                if m:
                    mac = m.group(1).replace("-", ":").lower()
                    clients.append(ConnectedClient(mac=mac))
    except Exception:
        pass

    # Attempt to enrich with IPs from ARP cache
    if clients:
        try:
            arp_raw = subprocess.check_output(
                ["arp", "-a"], text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            mac_to_ip: dict = {}
            for line in arp_raw.splitlines():
                m = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([\da-fA-F\-]{17})", line)
                if m:
                    ip  = m.group(1)
                    mac = m.group(2).replace("-", ":").lower()
                    mac_to_ip[mac] = ip
            for client in clients:
                client.ip = mac_to_ip.get(client.mac, "")
        except Exception:
            pass

    return clients
