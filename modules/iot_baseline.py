"""
IoT Behavioral Baseline — learns normal traffic patterns for IoT devices
and raises "Compromised IoT" alerts when behavior deviates.

How it works
────────────
1. LEARNING PHASE  — capture N seconds of traffic (via Scapy) and record,
   per device MAC: which remote IPs it contacts, which destination ports it
   uses, and its average packet rate.  Persist the baseline to a JSON file
   so it survives restarts.

2. MONITORING PHASE — stream live packets and compare against the stored
   baseline.  Trigger an IoTAlert when:

   • NEW_DEST      — device contacts an IP not in its baseline
   • NEW_PORT      — device opens a port not in its baseline
   • METADATA_PROBE— device contacts a cloud-metadata IP
                     (169.254.169.254, 100.100.100.200, fd00:ec2::254, etc.)
   • SYN_SCAN      — device sends SYN packets to 5+ distinct ports within
                     60 s (port-scan-like behaviour)
   • RATE_SPIKE    — current pps > baseline_pps * RATE_SPIKE_FACTOR

3. RISK SCORER INTEGRATION — IoTAlert.severity maps to a score delta that
   callers can inject into a RiskAssessment via inject_into_assessment().

Requires Scapy + admin/root.  Gracefully degrades when unavailable.
"""

from __future__ import annotations

import json
import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

SCAPY_AVAILABLE = False
try:
    from scapy.all import AsyncSniffer, IP, TCP, UDP  # type: ignore
    SCAPY_AVAILABLE = True
except ImportError:
    pass  # non-fatal

# ── Cloud-metadata / sensitive endpoint ranges ────────────────────────────────
# Any IoT device contacting these IPs should trigger an immediate alert.
_METADATA_IPS: Set[str] = {
    "169.254.169.254",   # AWS / GCP / Azure / OpenStack IMDS
    "169.254.170.2",     # AWS ECS metadata
    "100.100.100.200",   # Alibaba Cloud metadata
    "192.0.0.192",       # Azure IMDS alt
    "fd00:ec2::254",     # AWS IPv6 IMDS
}

# Ports that are *always* anomalous for a typical IoT appliance
_ALWAYS_ALERT_PORTS: Set[int] = {
    22,    # SSH outbound from IoT — rare, suggests backdoor
    23,    # Telnet
    445,   # SMB — IoT has no business touching Windows shares
    3389,  # RDP
    5900,  # VNC
    6667,  # IRC — classic C2 channel
    4444,  # Metasploit default
    9001,  # Tor OR port
    1080,  # SOCKS proxy
}

# Ratio by which pps must exceed baseline to trigger RATE_SPIKE
RATE_SPIKE_FACTOR = 5.0
# Number of distinct new ports within window to trigger SYN_SCAN
SYN_SCAN_THRESHOLD = 5
SYN_SCAN_WINDOW_S  = 60

# Device types we consider "IoT" for baseline tracking
IOT_DEVICE_TYPES: Set[str] = {
    "IoT Device", "IP Camera", "Smart Speaker", "Smart Speaker / Display",
    "Smart Display", "Smart Home Hub", "Smart TV", "Streaming Stick",
    "Video Doorbell", "Smart Thermostat", "Security Device", "Wearable",
}

_DEFAULT_BASELINE_PATH = Path.home() / "Documents" / "NetSentinel" / "iot_baseline.json"


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class DeviceBaseline:
    mac: str
    ip: str
    device_type: str
    vendor: str
    model: str
    known_ips: List[str]       = field(default_factory=list)
    known_ports: List[int]     = field(default_factory=list)
    avg_pps: float             = 0.0   # average packets per second during learning
    learned_at: str            = ""    # ISO timestamp
    sample_seconds: int        = 0


@dataclass
class IoTAlert:
    mac: str
    ip: str
    device_label: str          # e.g. "Google Nest Hub [192.168.1.5]"
    alert_type: str            # NEW_DEST | NEW_PORT | METADATA_PROBE | SYN_SCAN | RATE_SPIKE
    severity: str              # CRITICAL | HIGH | MEDIUM
    detail: str                # human-readable description
    remediation: str
    timestamp: str             = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))


# ── Persistence ────────────────────────────────────────────────────────────────

def _load_baselines(path: Path) -> Dict[str, DeviceBaseline]:
    """Load {mac: DeviceBaseline} from JSON file."""
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        return {
            mac: DeviceBaseline(**entry)
            for mac, entry in raw.items()
        }
    except Exception:
        return {}


def _save_baselines(baselines: Dict[str, DeviceBaseline], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({mac: asdict(b) for mac, b in baselines.items()}, fh, indent=2)


# ── Learning phase ─────────────────────────────────────────────────────────────

def learn(
    devices: list,
    duration_s: int = 60,
    baseline_path: Optional[Path] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
    device_type_key: str = "device_type",
) -> Dict[str, DeviceBaseline]:
    """
    Sniff traffic for ``duration_s`` seconds and build/update baselines for
    every device whose device_type is in IOT_DEVICE_TYPES.

    Parameters
    ----------
    devices       : List of dicts or objects with .ip / .mac / .device_type /
                    .vendor / .model attributes.
    duration_s    : How long to sniff (recommend 60–300 s for a useful baseline).
    baseline_path : Where to persist.  Defaults to ~/Documents/NetSentinel/iot_baseline.json.
    progress_cb   : Optional callback for status strings.

    Returns
    -------
    Dict[mac, DeviceBaseline] — updated baselines (merged with any existing).
    """
    path = baseline_path or _DEFAULT_BASELINE_PATH
    _cb  = progress_cb or (lambda m: None)

    if not SCAPY_AVAILABLE:
        _cb("Scapy unavailable — IoT baseline learning requires Scapy + admin/root.")
        return _load_baselines(path)

    def _get(obj, key):
        return obj.get(key, "") if isinstance(obj, dict) else getattr(obj, key, "")

    # Build lookup tables
    ip_to_mac:   Dict[str, str] = {}
    ip_to_dtype: Dict[str, str] = {}
    ip_to_vendor: Dict[str, str] = {}
    ip_to_model: Dict[str, str] = {}

    for d in devices:
        ip  = _get(d, "ip");  mac = _get(d, "mac")
        dtype = _get(d, device_type_key) or _get(d, "device_type")
        if ip and mac and dtype in IOT_DEVICE_TYPES:
            ip_to_mac[ip]   = mac
            ip_to_dtype[ip] = dtype
            ip_to_vendor[ip] = _get(d, "vendor")
            ip_to_model[ip]  = _get(d, "model")

    if not ip_to_mac:
        _cb("No IoT devices in device list — nothing to learn.")
        return _load_baselines(path)

    _cb(f"Learning baselines for {len(ip_to_mac)} IoT device(s) over {duration_s} s…")

    # Accumulate per-IP traffic
    dest_ips:   Dict[str, Set[str]] = defaultdict(set)
    dest_ports: Dict[str, Set[int]] = defaultdict(set)
    pkt_counts: Dict[str, int]      = defaultdict(int)
    lock = threading.Lock()

    def _handle(pkt):
        if not pkt.haslayer(IP):
            return
        src = pkt[IP].src
        dst = pkt[IP].dst
        if src not in ip_to_mac:
            return
        with lock:
            pkt_counts[src] += 1
            dest_ips[src].add(dst)
            if pkt.haslayer(TCP):
                dest_ports[src].add(pkt[TCP].dport)
            elif pkt.haslayer(UDP):
                dest_ports[src].add(pkt[UDP].dport)

    sniffer = AsyncSniffer(filter="ip", prn=_handle, store=False, timeout=duration_s)
    sniffer.start()
    sniffer.join()

    existing = _load_baselines(path)
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")

    for ip, mac in ip_to_mac.items():
        pps = pkt_counts[ip] / max(duration_s, 1)
        new_ips   = sorted(dest_ips[ip])
        new_ports = sorted(dest_ports[ip])

        if mac in existing:
            # Merge: add newly seen IPs/ports without wiping old ones
            b = existing[mac]
            merged_ips   = sorted(set(b.known_ips)   | set(new_ips))
            merged_ports = sorted(set(b.known_ports) | set(new_ports))
            b.known_ips   = merged_ips
            b.known_ports = merged_ports
            b.avg_pps = (b.avg_pps + pps) / 2
            b.sample_seconds += duration_s
        else:
            existing[mac] = DeviceBaseline(
                mac=mac, ip=ip,
                device_type=ip_to_dtype[ip],
                vendor=ip_to_vendor[ip],
                model=ip_to_model[ip],
                known_ips=new_ips,
                known_ports=new_ports,
                avg_pps=pps,
                learned_at=ts,
                sample_seconds=duration_s,
            )
        _cb(f"  Baseline for {ip} ({mac}): "
            f"{len(existing[mac].known_ips)} IPs, "
            f"{len(existing[mac].known_ports)} ports, "
            f"{pps:.1f} pps")

    _save_baselines(existing, path)
    _cb(f"Baselines saved to {path}")
    return existing


# ── Monitoring phase ───────────────────────────────────────────────────────────

class IoTMonitor:
    """
    Live anomaly detector.  Call ``start()`` to begin streaming; alerts
    are delivered via the ``on_alert`` callback.  Call ``stop()`` to end.
    """

    def __init__(
        self,
        baselines: Dict[str, DeviceBaseline],
        on_alert: Callable[[IoTAlert], None],
        on_error: Optional[Callable[[str], None]] = None,
        stop_event: Optional[threading.Event] = None,
        duration: int = 0,   # 0 = run until stop() called
    ):
        self._baselines   = baselines
        self._on_alert    = on_alert
        self._on_error    = on_error or (lambda m: None)
        self._stop        = stop_event or threading.Event()
        self._duration    = duration
        self._sniffer     = None

        # Build fast MAC→baseline lookup also keyed by IP
        self._ip_to_mac: Dict[str, str] = {b.ip: b.mac for b in baselines.values()}

        # SYN-scan tracking: mac → {port: first_seen_time}
        self._syn_ports: Dict[str, Dict[int, float]] = defaultdict(dict)

        # Rate tracking: mac → (window_start, pkt_count)
        self._rate: Dict[str, list] = defaultdict(lambda: [time.monotonic(), 0])

    # ── Packet handler ────────────────────────────────────────────────────────

    def _handle(self, pkt):
        try:
            if not pkt.haslayer(IP):
                return
            src_ip = pkt[IP].src
            mac    = self._ip_to_mac.get(src_ip)
            if mac is None or mac not in self._baselines:
                return

            baseline = self._baselines[mac]
            dst_ip   = pkt[IP].dst
            now      = time.monotonic()
            label    = f"{baseline.model or baseline.vendor or mac} [{src_ip}]"

            # ── Rate tracking ─────────────────────────────────────────────
            win_start, count = self._rate[mac]
            count += 1
            elapsed = now - win_start
            if elapsed >= 10.0:
                current_pps = count / elapsed
                self._rate[mac] = [now, 0]
                if baseline.avg_pps > 0 and current_pps > baseline.avg_pps * RATE_SPIKE_FACTOR:
                    self._emit(IoTAlert(
                        mac=mac, ip=src_ip, device_label=label,
                        alert_type="RATE_SPIKE",
                        severity="HIGH",
                        detail=(
                            f"Traffic rate {current_pps:.0f} pps is "
                            f"{current_pps/baseline.avg_pps:.0f}× the baseline "
                            f"({baseline.avg_pps:.1f} pps). "
                            "Possible data exfiltration or C2 beacon burst."
                        ),
                        remediation=(
                            "Block device's internet access temporarily and inspect "
                            "traffic with Wireshark. Check for firmware update."
                        ),
                    ))
            else:
                self._rate[mac][1] = count

            # ── Cloud metadata probe ──────────────────────────────────────
            if dst_ip in _METADATA_IPS:
                self._emit(IoTAlert(
                    mac=mac, ip=src_ip, device_label=label,
                    alert_type="METADATA_PROBE",
                    severity="CRITICAL",
                    detail=(
                        f"Device contacted cloud-metadata endpoint {dst_ip}. "
                        "This is a strong indicator of a server-side request forgery (SSRF) "
                        "exploit or malware attempting to steal cloud credentials."
                    ),
                    remediation=(
                        "Isolate device immediately. Block 169.254.169.254 at the router. "
                        "Factory-reset device and update firmware before reconnecting."
                    ),
                ))

            # ── New destination IP ────────────────────────────────────────
            if dst_ip not in baseline.known_ips and not dst_ip.startswith("224.") \
                    and not dst_ip.endswith(".255") and dst_ip != "255.255.255.255":
                self._emit(IoTAlert(
                    mac=mac, ip=src_ip, device_label=label,
                    alert_type="NEW_DEST",
                    severity="MEDIUM",
                    detail=(
                        f"Device contacted new IP {dst_ip} — not seen during baseline learning. "
                        "Could indicate a firmware update server, new cloud endpoint, or C2 server."
                    ),
                    remediation=(
                        f"Check what service is at {dst_ip} (use whois / reverse DNS). "
                        "If unexpected, block in router firewall and investigate."
                    ),
                ))
                # Temporarily add to suppress repeated alerts for same IP
                baseline.known_ips.append(dst_ip)

            # ── New/forbidden port ────────────────────────────────────────
            if pkt.haslayer(TCP):
                dport = pkt[TCP].dport
                flags = pkt[TCP].flags

                if dport in _ALWAYS_ALERT_PORTS:
                    self._emit(IoTAlert(
                        mac=mac, ip=src_ip, device_label=label,
                        alert_type="NEW_PORT",
                        severity="CRITICAL",
                        detail=(
                            f"Device attempted connection to port {dport} — "
                            "this port is never expected from an IoT appliance and is "
                            "associated with remote-control / C2 / lateral movement."
                        ),
                        remediation=(
                            "Isolate device from network. Run firmware integrity check. "
                            "Review router firewall logs for outbound connections."
                        ),
                    ))

                elif dport not in baseline.known_ports:
                    self._emit(IoTAlert(
                        mac=mac, ip=src_ip, device_label=label,
                        alert_type="NEW_PORT",
                        severity="MEDIUM",
                        detail=(
                            f"Device opened connection to port {dport} — "
                            "not observed during baseline learning."
                        ),
                        remediation=(
                            "Verify this is expected (firmware update, new feature). "
                            "If unexpected, block port in router and monitor."
                        ),
                    ))

                # ── SYN scan detection ────────────────────────────────────
                # SYN flag set, ACK not set → outgoing connection attempt
                if flags and (int(flags) & 0x02) and not (int(flags) & 0x10):
                    syn_map = self._syn_ports[mac]
                    syn_map[dport] = now
                    # Expire old entries outside the window
                    cutoff = now - SYN_SCAN_WINDOW_S
                    self._syn_ports[mac] = {
                        p: t for p, t in syn_map.items() if t > cutoff
                    }
                    if len(self._syn_ports[mac]) >= SYN_SCAN_THRESHOLD:
                        ports_str = ", ".join(str(p) for p in sorted(self._syn_ports[mac]))
                        self._emit(IoTAlert(
                            mac=mac, ip=src_ip, device_label=label,
                            alert_type="SYN_SCAN",
                            severity="CRITICAL",
                            detail=(
                                f"Device sent SYN packets to {len(self._syn_ports[mac])} "
                                f"distinct ports in {SYN_SCAN_WINDOW_S} s "
                                f"(ports: {ports_str}). "
                                "Classic port-scan pattern — device may be compromised and "
                                "performing lateral movement recon."
                            ),
                            remediation=(
                                "Isolate device immediately by blocking its MAC at the router. "
                                "Factory reset and update firmware before reconnecting. "
                                "Check other LAN devices for signs of lateral movement."
                            ),
                        ))
                        # Reset counter so we don't spam
                        self._syn_ports[mac] = {}

        except Exception:
            pass  # non-fatal

    def _emit(self, alert: IoTAlert) -> None:
        try:
            self._on_alert(alert)
        except Exception:
            pass  # non-fatal

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if not SCAPY_AVAILABLE:
            self._on_error(
                "Scapy unavailable — IoT monitoring requires Scapy + admin/root + Npcap."
            )
            return
        if not self._baselines:
            self._on_error(
                "No IoT baselines loaded. Run learn() first to record normal behavior."
            )
            return
        try:
            kwargs: dict = {"filter": "ip", "prn": self._handle, "store": False}
            if self._duration > 0:
                kwargs["timeout"] = self._duration
            self._sniffer = AsyncSniffer(**kwargs)
            self._sniffer.start()
        except Exception as exc:
            self._on_error(f"Failed to start IoT monitor: {exc}")

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._sniffer:
                self._sniffer.stop()
        except Exception:
            pass  # non-fatal


# ── Risk scorer integration ────────────────────────────────────────────────────

def inject_into_assessment(assessment, alerts: List[IoTAlert]) -> None:
    """
    Inject IoT anomaly findings into an existing RiskAssessment from risk_scorer.

    Modifies assessment in-place — adds findings and raises total_score.
    """
    from modules.risk_scorer import RiskFinding  # local import to avoid circular dep

    severity_pts = {"CRITICAL": 30, "HIGH": 20, "MEDIUM": 10}
    for alert in alerts:
        pts = severity_pts.get(alert.severity, 5)
        assessment.findings.append(RiskFinding(
            title=f"IoT Anomaly — {alert.alert_type.replace('_', ' ').title()}",
            score_contribution=pts,
            impact=alert.detail,
            remediation=alert.remediation,
        ))
        assessment.total_score = min(assessment.total_score + pts, 100)

    if alerts:
        worst = max(alerts, key=lambda a: severity_pts.get(a.severity, 0))
        if worst.severity == "CRITICAL":
            assessment.severity = "CRITICAL"
        elif worst.severity == "HIGH" and assessment.severity not in ("CRITICAL",):
            assessment.severity = "HIGH"

        assessment.plain_summary = (
            f"⚠ COMPROMISED IoT DEVICE — {len(alerts)} anomalous behaviour(s) detected. "
            + assessment.plain_summary
        )


# ── Convenience: one-shot scan+check ──────────────────────────────────────────

def load_or_create(
    devices: list,
    baseline_path: Optional[Path] = None,
    learn_duration_s: int = 60,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> Dict[str, DeviceBaseline]:
    """
    Load existing baselines from disk; for any IoT device not yet baselined,
    run a short learning pass automatically.

    Returns the full baselines dict.
    """
    path = baseline_path or _DEFAULT_BASELINE_PATH
    baselines = _load_baselines(path)

    def _get(obj, key):
        return obj.get(key, "") if isinstance(obj, dict) else getattr(obj, key, "")

    unlearned = [
        d for d in devices
        if _get(d, "device_type") in IOT_DEVICE_TYPES
        and _get(d, "mac") not in baselines
    ]

    if unlearned:
        _cb = progress_cb or (lambda m: None)
        _cb(f"{len(unlearned)} IoT device(s) have no baseline — starting {learn_duration_s}s learning pass…")
        baselines = learn(
            devices=unlearned,
            duration_s=learn_duration_s,
            baseline_path=path,
            progress_cb=progress_cb,
        )

    return baselines
