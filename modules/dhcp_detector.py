"""
Module 10 — Rogue DHCP Server Detector

Sends a DHCPDISCOVER broadcast and collects all DHCPOFFER replies.
More than one DHCPOFFER (or an offer from an unexpected IP) means there
is a rogue DHCP server on the LAN — it can redirect all client traffic
through an attacker-controlled gateway.

Requires Scapy + admin / root privileges and Npcap on Windows.
Gracefully degrades when Scapy is unavailable.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

SCAPY_AVAILABLE = False
try:
    from scapy.all import (  # type: ignore
        AsyncSniffer,
        BOOTP,
        DHCP,
        Ether,
        IP,
        UDP,
        sendp,
    )
    SCAPY_AVAILABLE = True
except ImportError:
    pass  # non-fatal


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class DHCPOffer:
    server_ip: str          # DHCP server that sent this offer
    server_mac: str
    offered_ip: str         # IP offered to the client
    gateway: str            # router option in the offer
    dns_servers: List[str] = field(default_factory=list)
    lease_time: int = 0     # seconds
    is_rogue: bool = False
    verdict: str = ""


@dataclass
class DHCPScanResult:
    offers: List[DHCPOffer] = field(default_factory=list)
    legitimate_server: str = ""   # IP of the expected / first-seen DHCP server
    plain_verdict: str = ""
    # MAC → DhcpFingerprint gathered from client DHCP packets during the scan window
    fingerprints: Dict[str, "DhcpFingerprint"] = field(default_factory=dict)  # type: ignore[name-defined]


# ── Packet builder ────────────────────────────────────────────────────────────

def _build_discover(client_mac: str) -> "Ether":
    """Build a DHCPDISCOVER broadcast packet."""
    mac_bytes = bytes.fromhex(client_mac.replace(":", ""))
    pkt = (
        Ether(dst="ff:ff:ff:ff:ff:ff", src=client_mac)
        / IP(src="0.0.0.0", dst="255.255.255.255")
        / UDP(sport=68, dport=67)
        / BOOTP(chaddr=mac_bytes, xid=0xDEADBEEF, flags=0x8000)
        / DHCP(options=[
            ("message-type", "discover"),
            ("param_req_list", [1, 3, 6, 28, 51]),   # subnet, router, DNS, bcast, lease
            "end",
        ])
    )
    return pkt


# ── Sniffer / scanner ─────────────────────────────────────────────────────────

class DHCPDetector:
    def __init__(
        self,
        on_offer: Callable[["DHCPOffer"], None],
        on_error: Callable[[str], None],
        known_server_ip: Optional[str] = None,
        timeout: int = 10,
        stop_event: Optional[threading.Event] = None,
    ):
        self.on_offer       = on_offer
        self.on_error       = on_error
        self.known_server   = known_server_ip
        self.timeout        = timeout
        self.stop_event     = stop_event or threading.Event()
        self._sniffer       = None
        self._seen_servers: set = set()
        self._fingerprints: dict = {}   # mac → DhcpFingerprint from client packets

    def _handle(self, pkt):
        try:
            if not (pkt.haslayer(DHCP) and pkt.haslayer(BOOTP) and pkt.haslayer(IP)):
                return
            dhcp_opts = {opt[0]: opt[1] for opt in pkt[DHCP].options if isinstance(opt, (list, tuple)) and len(opt) >= 2}
            msg_type  = dhcp_opts.get("message-type", 0)

            # ── Client packets: harvest VCI (option 60) + hostname (option 12) ──
            # DHCPDISCOVER (1) and DHCPREQUEST (3) come from clients and carry the
            # vendor class identifier and self-reported hostname.  Skip our own probe
            # packet (src MAC de:ad:be:ef:ca:fe) so we don't fingerprint ourselves.
            if msg_type in (1, 3) and pkt.haslayer(Ether):
                client_mac = pkt[Ether].src.lower()
                if client_mac and client_mac != "de:ad:be:ef:ca:fe":
                    try:
                        from modules.dhcp_fingerprint import fingerprint_from_options
                        fp = fingerprint_from_options(dhcp_opts)
                        if fp.confidence or fp.hostname:
                            self._fingerprints[client_mac] = fp
                    except Exception:
                        pass  # non-fatal — fingerprinting is best-effort

            if msg_type != 2:   # 2 = DHCPOFFER
                return

            server_ip  = pkt[IP].src
            server_mac = pkt[Ether].src.lower() if pkt.haslayer(Ether) else "unknown"
            offered_ip = pkt[BOOTP].yiaddr
            gateway    = dhcp_opts.get("router", "")
            if isinstance(gateway, (list, tuple)):
                gateway = str(gateway[0]) if gateway else ""
            else:
                gateway = str(gateway)

            dns_raw = dhcp_opts.get("name_server", [])
            if not isinstance(dns_raw, (list, tuple)):
                dns_raw = [dns_raw]
            dns_servers = [str(d) for d in dns_raw]

            lease = dhcp_opts.get("lease_time", 0)

            is_rogue = bool(self.known_server and server_ip != self.known_server)

            if is_rogue:
                verdict = (
                    f"ROGUE DHCP SERVER: {server_ip} ({server_mac}) is offering IP "
                    f"{offered_ip} with gateway {gateway}. "
                    f"Expected server was {self.known_server}. "
                    "This server can redirect ALL your traffic through any gateway it names. "
                    "FIX: Identify and disconnect this device immediately."
                )
            elif server_ip in self._seen_servers:
                return   # already reported this server
            else:
                verdict = (
                    f"DHCP server {server_ip} ({server_mac}) — "
                    f"offering {offered_ip}, gateway {gateway}, "
                    f"DNS {', '.join(dns_servers) if dns_servers else 'none'}, "
                    f"lease {lease}s."
                )

            self._seen_servers.add(server_ip)
            offer = DHCPOffer(
                server_ip=server_ip,
                server_mac=server_mac,
                offered_ip=offered_ip,
                gateway=gateway,
                dns_servers=dns_servers,
                lease_time=int(lease),
                is_rogue=is_rogue,
                verdict=verdict,
            )
            self.on_offer(offer)
        except Exception:
            pass  # non-fatal

    def run(self):
        if not SCAPY_AVAILABLE:
            self.on_error(
                "Scapy is not installed. Rogue DHCP detection requires:\n"
                "  pip install scapy\n"
                "  Windows: Npcap from https://npcap.com (run as Administrator)"
            )
            return

        # Use a probe MAC so we don't disturb real DHCP leases
        probe_mac = "de:ad:be:ef:ca:fe"
        try:
            self._sniffer = AsyncSniffer(
                filter="udp and port 68",
                prn=self._handle,
                store=False,
                timeout=self.timeout,
            )
            self._sniffer.start()
            time.sleep(0.3)   # let sniffer arm before sending the discover

            discover = _build_discover(probe_mac)
            sendp(discover, verbose=False)
        except Exception as exc:
            self.on_error(
                f"DHCP probe failed: {exc}\n"
                "Run as Administrator/root with Npcap installed."
            )

    def stop(self):
        try:
            if self._sniffer:
                self._sniffer.stop()
        except Exception:
            pass  # non-fatal

    @property
    def fingerprints(self) -> dict:
        """Return the collected {mac: DhcpFingerprint} dict (snapshot, not live)."""
        return dict(self._fingerprints)


# ── Public scan entry point ───────────────────────────────────────────────────

def scan(
    known_dhcp_server: Optional[str] = None,
    on_offer: Optional[Callable[["DHCPOffer"], None]] = None,
    on_error: Optional[Callable[[str], None]] = None,
    duration: int = 10,
    progress_cb: Optional[Callable[[str], None]] = None,
    stop_event: Optional[threading.Event] = None,
) -> DHCPScanResult:
    """
    Sends a DHCPDISCOVER and collects all DHCPOFFER replies for *duration* seconds.
    Returns DHCPScanResult.
    """
    _cb  = progress_cb or (lambda m: None)
    _err = on_error    or (lambda m: None)
    _off = on_offer    or (lambda o: None)

    if not SCAPY_AVAILABLE:
        msg = (
            "Scapy not available — rogue DHCP detection requires:\n"
            "  pip install scapy\n"
            "  Windows: Npcap from https://npcap.com (run as Administrator)"
        )
        _err(msg)
        result = DHCPScanResult()
        result.plain_verdict = msg
        return result

    offers: List[DHCPOffer] = []
    lock = threading.Lock()

    def _collect(offer: DHCPOffer):
        with lock:
            offers.append(offer)
        _off(offer)

    _cb("Sending DHCPDISCOVER broadcast…")
    detector = DHCPDetector(
        on_offer=_collect,
        on_error=_err,
        known_server_ip=known_dhcp_server,
        timeout=duration,
        stop_event=stop_event,
    )
    detector.run()

    for i in range(duration):
        if stop_event and stop_event.is_set():
            _cb("DHCP scan cancelled.")
            break
        time.sleep(1)
        _cb(f"DHCP scan: waiting {duration - i - 1}s for replies…")

    detector.stop()

    # Populate fingerprint cache from client packets captured during the scan window
    fingerprints: dict = detector.fingerprints
    try:
        from modules.dhcp_fingerprint import update_cache as _upd_cache
        _upd_cache(fingerprints)
    except Exception:
        pass  # non-fatal

    rogues = [o for o in offers if o.is_rogue]
    if rogues:
        plain = (
            f"🔴 CRITICAL: {len(rogues)} rogue DHCP server(s) detected! "
            + " | ".join(r.verdict for r in rogues[:2])
        )
    elif len(offers) > 1:
        plain = (
            f"🟡 {len(offers)} DHCP servers responded — only one is expected. "
            "Check for an unauthorised server."
        )
    elif offers:
        plain = (
            f"✅ Single DHCP server {offers[0].server_ip} ({offers[0].server_mac}). "
            f"Gateway: {offers[0].gateway}."
        )
    else:
        plain = "No DHCP offers received in scan window — try running as Administrator with Npcap."

    return DHCPScanResult(
        offers=offers,
        legitimate_server=offers[0].server_ip if offers else "",
        plain_verdict=plain,
        fingerprints=fingerprints,
    )
