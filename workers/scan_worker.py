"""
Background QThread workers — one per scan module.
Each worker emits signals that the dashboard connects to.
"""

import threading
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal


# ── Scapy process-isolation targets ──────────────────────────────────────────
# These run inside a separate process so a Scapy/Npcap C-level crash (access
# violation, driver fault) cannot kill the main application.
# MUST be module-level functions to be picklable by multiprocessing on Windows.

def _stp_scan_process_target(gateway_mac, duration, result_q, event_q, mp_stop):
    """Runs stp_detector.scan() in an isolated process."""
    import threading as _threading
    import time as _time

    def _ev(kind, payload):
        try:
            event_q.put((kind, payload))
        except Exception:
            pass  # non-fatal

    try:
        from modules.stp_detector import scan

        _thread_stop = _threading.Event()

        def _stop_monitor():
            while not _thread_stop.is_set():
                if mp_stop.is_set():
                    _thread_stop.set()
                    return
                _time.sleep(0.25)

        _threading.Thread(target=_stop_monitor, daemon=True).start()

        data = scan(
            gateway_mac=gateway_mac,
            on_bpdu=lambda b: _ev("bpdu", b),
            on_error=lambda m: _ev("error", m),
            duration=duration,
            progress_cb=lambda m: _ev("status", m),
            stop_event=_thread_stop,
        )
        _thread_stop.set()
        result_q.put(data)
    except Exception as exc:
        _ev("error", str(exc))
        result_q.put({
            "bpdus": [], "rogue_count": 0, "total_bpdus": 0,
            "plain_verdict": f"STP scan error: {exc}",
        })


def _storm_scan_process_target(duration, warn_threshold, storm_threshold,
                                known_rogue_macs, result_q, event_q, mp_stop):
    """Runs storm_analyser.scan() in an isolated process."""

    def _ev(kind, payload):
        try:
            event_q.put((kind, payload))
        except Exception:
            pass  # non-fatal

    try:
        from modules.storm_analyser import scan
        data = scan(
            duration=duration,
            warn_threshold=warn_threshold,
            storm_threshold=storm_threshold,
            known_rogue_macs=known_rogue_macs,
            progress_cb=lambda m: _ev("status", m),
            on_error=lambda m: _ev("error", m),
            stop_event=mp_stop,
        )
        result_q.put(data)
    except Exception as exc:
        _ev("error", str(exc))
        try:
            from modules.storm_analyser import StormResult
            result_q.put(StormResult(
                plain_verdict=f"Storm scan error: {exc}",
                storm_level="UNKNOWN",
            ))
        except Exception:
            pass  # non-fatal


class Module1Worker(QThread):
    """Rogue Device Fingerprinter."""
    result       = pyqtSignal(dict)
    status       = pyqtSignal(str)
    error        = pyqtSignal(str)
    device_found = pyqtSignal(dict)  # {"ip": str, "name": str, "type": str}

    def __init__(self, offenders_path: Path, parent=None):
        super().__init__(parent)
        self.offenders_path = offenders_path

    def run(self):
        try:
            from modules.rogue_device import scan
            self.status.emit("Scanning ARP table and fingerprinting devices...")
            data = scan(self.offenders_path)
            for d in data.get("devices", []):
                self.device_found.emit({
                    "ip":   d.get("ip",   "") if isinstance(d, dict) else getattr(d, "ip",          ""),
                    "name": d.get("hostname", "") if isinstance(d, dict) else getattr(d, "hostname",     ""),
                    "type": d.get("device_type", "") if isinstance(d, dict) else getattr(d, "device_type",  ""),
                })
            self.result.emit(data)
        except Exception as exc:
            self.error.emit(f"Module 1 error: {exc}")


class Module2Worker(QThread):
    """STP / BPDU Detector."""
    bpdu_found = pyqtSignal(object)   # BPDUInfo instance
    result     = pyqtSignal(dict)
    status     = pyqtSignal(str)
    error      = pyqtSignal(str)

    def __init__(self, gateway_mac: Optional[str], duration: int = 30, parent=None):
        super().__init__(parent)
        self.gateway_mac = gateway_mac
        self.duration = duration
        self._stop_event = threading.Event()

    def run(self):
        import multiprocessing as _mp
        import time as _time
        p = None
        try:
            result_q = _mp.Queue()
            event_q  = _mp.Queue()
            mp_stop  = _mp.Event()

            p = _mp.Process(
                target=_stp_scan_process_target,
                args=(self.gateway_mac, self.duration, result_q, event_q, mp_stop),
                daemon=True,
            )
            p.start()
            self.status.emit(f"STP scan running (pid {p.pid})\u2026")

            deadline = _time.monotonic() + self.duration + 15
            while _time.monotonic() < deadline:
                # Drain subprocess events
                while True:
                    try:
                        kind, payload = event_q.get_nowait()
                        if kind == "bpdu":
                            self.bpdu_found.emit(payload)
                        elif kind == "status":
                            self.status.emit(payload)
                        elif kind == "error":
                            self.error.emit(payload)
                    except Exception:
                        break
                if self._stop_event.is_set():
                    mp_stop.set()
                if not p.is_alive():
                    break
                _time.sleep(0.25)

            # Final queue drain after subprocess exits
            while True:
                try:
                    kind, payload = event_q.get_nowait()
                    if kind == "bpdu":
                        self.bpdu_found.emit(payload)
                    elif kind == "status":
                        self.status.emit(payload)
                    elif kind == "error":
                        self.error.emit(payload)
                except Exception:
                    break

            if p.is_alive():
                p.terminate()
                p.join(timeout=3)

            if not result_q.empty():
                self.result.emit(result_q.get())
            else:
                # Subprocess crashed (e.g. Npcap driver fault) — report gracefully
                self.error.emit(
                    f"STP scan process ended unexpectedly (exit {p.exitcode}). "
                    "Ensure Npcap is installed and up to date."
                )
                self.result.emit({
                    "bpdus": [], "rogue_count": 0, "total_bpdus": 0,
                    "plain_verdict": "STP scan unavailable \u2014 packet capture failed.",
                })
        except Exception as exc:
            self.error.emit(f"Module 2 error: {exc}")
        finally:
            if p is not None and p.is_alive():
                p.terminate()
                p.join(timeout=3)

    def stop(self):
        self._stop_event.set()


class Module3Worker(QThread):
    """Broadcast Storm Analyser."""
    result = pyqtSignal(object)   # StormResult instance
    status = pyqtSignal(str)
    error  = pyqtSignal(str)

    def __init__(
        self,
        duration: int = 10,
        warn_threshold: int = 50,
        storm_threshold: int = 150,
        known_rogue_macs=None,
        parent=None,
    ):
        super().__init__(parent)
        self.duration = duration
        self.warn_threshold = warn_threshold
        self.storm_threshold = storm_threshold
        self.known_rogue_macs = known_rogue_macs or []
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        import multiprocessing as _mp
        import time as _time
        p = None
        try:
            result_q = _mp.Queue()
            event_q  = _mp.Queue()
            mp_stop  = _mp.Event()

            p = _mp.Process(
                target=_storm_scan_process_target,
                args=(self.duration, self.warn_threshold, self.storm_threshold,
                      self.known_rogue_macs, result_q, event_q, mp_stop),
                daemon=True,
            )
            p.start()
            self.status.emit(f"Storm analysis running (pid {p.pid})\u2026")

            deadline = _time.monotonic() + self.duration + 15
            while _time.monotonic() < deadline:
                while True:
                    try:
                        kind, payload = event_q.get_nowait()
                        if kind == "status":
                            self.status.emit(payload)
                        elif kind == "error":
                            self.error.emit(payload)
                    except Exception:
                        break
                if self._stop_event.is_set():
                    mp_stop.set()
                if not p.is_alive():
                    break
                _time.sleep(0.25)

            # Final drain
            while True:
                try:
                    kind, payload = event_q.get_nowait()
                    if kind == "status":
                        self.status.emit(payload)
                    elif kind == "error":
                        self.error.emit(payload)
                except Exception:
                    break

            if p.is_alive():
                p.terminate()
                p.join(timeout=3)

            if not result_q.empty():
                self.result.emit(result_q.get())
            else:
                exit_code = p.exitcode
                self.error.emit(
                    f"Storm scan process ended unexpectedly (exit {exit_code}). "
                    "Ensure Npcap is installed and up to date."
                )
                # Emit a safe fallback dict so _on_m3_result never receives None
                self.result.emit({
                    "storm_level": "UNKNOWN",
                    "bcast_per_sec": 0.0,
                    "mcast_per_sec": 0.0,
                    "bcast_ratio": 0.0,
                    "top_sources": [],
                    "rogue_matches": [],
                    "plain_verdict": "Storm scan unavailable \u2014 packet capture failed.",
                })
        except Exception as exc:
            self.error.emit(f"Module 3 error: {exc}")
        finally:
            if p is not None and p.is_alive():
                p.terminate()
                p.join(timeout=3)


class Module4Worker(QThread):
    """WiFi / Hidden SSID Scanner."""
    result = pyqtSignal(object)   # WifiScanResult instance
    status = pyqtSignal(str)
    error  = pyqtSignal(str)

    def run(self):
        try:
            from modules.wifi_scanner import scan
            self.status.emit("Scanning WiFi networks...")
            data = scan()
            self.result.emit(data)
        except Exception as exc:
            self.error.emit(f"Module 4 error: {exc}")


class Module5Worker(QThread):
    """DNS / Ping Correlator."""
    ping_point = pyqtSignal(object)   # PingPoint
    dns_point  = pyqtSignal(object)   # DnsPoint
    result     = pyqtSignal(object)   # CorrelatorResult
    status     = pyqtSignal(str)
    error      = pyqtSignal(str)

    def __init__(self, gateway_ip: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.gateway_ip = gateway_ip
        self._stop = threading.Event()

    def run(self):
        try:
            from modules.dns_correlator import scan
            self.status.emit("Starting ping and DNS correlation (60 seconds)...")
            data = scan(
                gateway_ip=self.gateway_ip,
                on_ping=lambda p: self.ping_point.emit(p),
                on_dns=lambda d: self.dns_point.emit(d),
                progress_cb=lambda m: self.status.emit(m),
                stop_event=self._stop,
            )
            self.result.emit(data)
        except Exception as exc:
            self.error.emit(f"Module 5 error: {exc}")

    def stop(self):
        self._stop.set()


# ── Logger worker ─────────────────────────────────────────────────────────────

class LoggerWorker(QThread):
    """
    Wraps NetworkLogger so the long-term background ping loop runs in a
    QThread (keeps the GUI responsive and lets PyQt signals deliver results
    to the UI thread safely).
    """
    entry_received = pyqtSignal(object)   # LogEntry
    status         = pyqtSignal(str)
    error          = pyqtSignal(str)
    rotated        = pyqtSignal(str, int) # new filename, segment number

    def __init__(
        self,
        interval_s: int = 60,
        targets=None,
        enable_jitter: bool = False,
        enable_dns: bool = False,
        enable_http: bool = False,
        enable_arp: bool = False,
        rotation_hours: int = 12,
        parent=None,
    ):
        super().__init__(parent)
        self.interval_s = interval_s
        self.targets = targets or ["8.8.8.8", "1.1.1.1", "google.com"]
        self.enable_jitter = enable_jitter
        self.enable_dns = enable_dns
        self.enable_http = enable_http
        self.enable_arp = enable_arp
        self.rotation_hours = rotation_hours
        self._logger = None

    def run(self):
        try:
            from modules.network_logger import NetworkLogger
            self._logger = NetworkLogger(
                interval_s=self.interval_s,
                targets=self.targets,
                enable_jitter=self.enable_jitter,
                enable_dns=self.enable_dns,
                enable_http=self.enable_http,
                enable_arp=self.enable_arp,
                rotation_hours=self.rotation_hours,
            )
            options = []
            if self.enable_jitter: options.append("Jitter")
            if self.enable_dns:    options.append("DNS")
            if self.enable_http:   options.append("HTTP")
            if self.enable_arp:    options.append("ARP watch")
            extras = f" + {', '.join(options)}" if options else ""
            self.status.emit(
                f"Logger started — pinging every {self.interval_s}s{extras}"
                f" → {self._logger.log_file.name}"
            )
            self._logger.start(
                on_entry=lambda e: self.entry_received.emit(e),
                on_rotate=lambda p, n: self.rotated.emit(p.name, n),
            )
            self._logger._stop_event.wait()
        except Exception as exc:
            self.error.emit(f"Logger error: {exc}")

    def stop_logger(self):
        if self._logger:
            self._logger.stop()
        self.status.emit("Logger stopped.")

    def get_summary(self):
        if self._logger:
            return self._logger.get_summary()
        return None

    @property
    def log_file(self):
        return self._logger.log_file if self._logger else None

class PreScanWorker(QThread):
    """
    Runs before any module worker.

    1. Flushes DNS, ARP and IPv6 neighbour caches so the scan shows
       *current* devices rather than hours-old cached entries.
    2. Pings every host in the /24 subnet to populate the ARP table so
       Module 1 discovers devices that have never been communicated with.
    """
    status = pyqtSignal(str)
    done   = pyqtSignal()
    error  = pyqtSignal(str)

    def __init__(self, flush_caches: bool = True, parent=None):
        super().__init__(parent)
        self.flush_caches = flush_caches

    def run(self):
        try:
            from modules.utils import flush_network_caches, get_local_ip, ping_sweep_subnet
            if self.flush_caches:
                self.status.emit("Flushing DNS / ARP / IPv6 neighbour caches…")
                flush_network_caches()
            self.status.emit("Discovering devices — pinging subnet…")
            local_ip = get_local_ip()
            ping_sweep_subnet(local_ip, progress_cb=lambda m: self.status.emit(m))
            self.status.emit("Pre-scan complete.  Starting module analysis…")
            self.done.emit()
        except Exception as exc:
            self.error.emit(str(exc))


# ── Network-info worker ───────────────────────────────────────────────────────

class NetworkInfoWorker(QThread):
    """Collects local IP / gateway / DNS / DHCP / adapter info in a background thread."""
    result = pyqtSignal(dict)
    error  = pyqtSignal(str)

    def run(self):
        try:
            from modules.utils import get_network_info, get_dhcp_info, get_interface_details
            info = get_network_info()
            info["dhcp"] = get_dhcp_info()
            info["adapters"] = get_interface_details()
            self.result.emit(info)
        except Exception as exc:
            self.error.emit(str(exc))


# ── Diagnostics worker ────────────────────────────────────────────────────────

class DiagnosticsWorker(QThread):
    """Runs Module-6 network health diagnostics."""
    result = pyqtSignal(object)  # DiagnosticsResult
    status = pyqtSignal(str)
    error  = pyqtSignal(str)

    def __init__(self, gateway_ip: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.gateway_ip = gateway_ip
        self._stop = threading.Event()

    def run(self):
        try:
            from modules.network_diagnostics import scan
            data = scan(
                gateway_ip=self.gateway_ip,
                progress_cb=lambda m: self.status.emit(m),
                stop_event=self._stop,
            )
            self.result.emit(data)
        except Exception as exc:
            self.error.emit(f"Diagnostics error: {exc}")

    def stop(self):
        self._stop.set()


# ── Port scanner worker ───────────────────────────────────────────────────────

class PortScanWorker(QThread):
    """TCP connect-scan of common ports on a single host. No admin required."""
    result = pyqtSignal(object)   # PortScanResult
    status = pyqtSignal(str)
    error  = pyqtSignal(str)

    def __init__(self, host: str, mode: str = "normal", parent=None):
        super().__init__(parent)
        self.host = host
        self.mode = mode

    def run(self):
        try:
            from modules.port_scanner import scan
            self.status.emit(f"Port scanning {self.host} ({self.mode} mode)…")
            data = scan(self.host, mode=self.mode)
            self.status.emit(
                f"Scan complete — {len(data.open_ports)} open port(s) on {self.host}"
            )
            self.result.emit(data)
        except Exception as exc:
            self.error.emit(f"Port scan error: {exc}")


# ── MTR (continuous traceroute) worker ────────────────────────────────────────

class MTRWorker(QThread):
    """
    Continuous hop-by-hop traceroute (MTR-style).
    Emits hop_result per hop per cycle so the UI can accumulate per-hop
    loss % and average RTT just like the real mtr tool.
    Runs until stop() is called.
    """
    hop_result = pyqtSignal(int, str, float)   # hop_num, ip, rtt_ms
    cycle_done = pyqtSignal(int)               # cycle_number
    status     = pyqtSignal(str)
    error      = pyqtSignal(str)

    def __init__(self, target: str = "8.8.8.8", max_hops: int = 15,
                 interval_s: float = 3.0, parent=None):
        super().__init__(parent)
        self.target = target
        self.max_hops = max_hops
        self.interval_s = interval_s
        self._stop = threading.Event()

    def run(self):
        import platform
        import re
        import subprocess
        system = platform.system()
        if system == "Windows":
            _si = subprocess.STARTUPINFO()
            _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            _si.wShowWindow = 0
            extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": _si}
        else:
            extra = {}
        cycle = 0
        self.status.emit(f"MTR running to {self.target}…  (click Stop to end)")
        while not self._stop.is_set():
            cycle += 1
            try:
                if system == "Windows":
                    r = subprocess.run(
                        ["tracert", "-d", "-h", str(self.max_hops), "-w", "800", self.target],
                        capture_output=True, text=True, timeout=60, **extra,
                    )
                    for line in r.stdout.splitlines():
                        m = re.match(
                            r"\s*(\d+)\s+(?:<\s*1|(\d+))\s+ms.*?(\d+\.\d+\.\d+\.\d+|\*)",
                            line,
                        )
                        if m:
                            rtt = float(m.group(2)) if m.group(2) else 0.5
                            ip = m.group(3) if m.group(3) != "*" else "*"
                            self.hop_result.emit(int(m.group(1)), ip, rtt)
                else:
                    r = subprocess.run(
                        ["traceroute", "-n", "-m", str(self.max_hops), "-w", "1", self.target],
                        capture_output=True, text=True, timeout=60,
                    )
                    for line in r.stdout.splitlines():
                        m = re.match(
                            r"\s*(\d+)\s+(\d+\.\d+\.\d+\.\d+|\*)\s+([0-9.]+)\s+ms", line
                        )
                        if m:
                            self.hop_result.emit(
                                int(m.group(1)), m.group(2), float(m.group(3))
                            )
            except Exception as exc:
                self.error.emit(f"MTR error: {exc}")
            self.cycle_done.emit(cycle)
            self._stop.wait(self.interval_s)

    def stop(self):
        self._stop.set()


# ── ARP spoof monitor worker ──────────────────────────────────────────────────

class ARPMonitorWorker(QThread):
    """Monitors live ARP traffic for spoofing / MITM events."""
    event_found = pyqtSignal(object)   # SpoofEvent
    result      = pyqtSignal(object)   # ARPScanResult
    status      = pyqtSignal(str)
    error       = pyqtSignal(str)

    def __init__(self, gateway_ip: Optional[str] = None, duration: int = 30, parent=None):
        super().__init__(parent)
        self.gateway_ip = gateway_ip
        self.duration   = duration
        self._stop      = threading.Event()

    def run(self):
        try:
            from modules.arp_monitor import scan
            data = scan(
                gateway_ip=self.gateway_ip,
                on_event=lambda e: self.event_found.emit(e),
                on_error=lambda m: self.error.emit(m),
                duration=self.duration,
                progress_cb=lambda m: self.status.emit(m),
                stop_event=self._stop,
            )
            self.result.emit(data)
        except Exception as exc:
            self.error.emit(f"ARP monitor error: {exc}")

    def stop(self):
        self._stop.set()


# ── Rogue DHCP detector worker ────────────────────────────────────────────────

class DHCPDetectorWorker(QThread):
    """Detects rogue DHCP servers on the LAN."""
    offer_found = pyqtSignal(object)   # DHCPOffer
    result      = pyqtSignal(object)   # DHCPScanResult
    status      = pyqtSignal(str)
    error       = pyqtSignal(str)

    def __init__(
        self,
        known_dhcp_server: Optional[str] = None,
        duration: int = 10,
        parent=None,
    ):
        super().__init__(parent)
        self.known_dhcp_server = known_dhcp_server
        self.duration          = duration
        self._stop             = threading.Event()

    def run(self):
        try:
            from modules.dhcp_detector import scan
            data = scan(
                known_dhcp_server=self.known_dhcp_server,
                on_offer=lambda o: self.offer_found.emit(o),
                on_error=lambda m: self.error.emit(m),
                duration=self.duration,
                progress_cb=lambda m: self.status.emit(m),
                stop_event=self._stop,
            )
            self.result.emit(data)
        except Exception as exc:
            self.error.emit(f"DHCP detector error: {exc}")

    def stop(self):
        self._stop.set()


# ── Bandwidth monitor worker ──────────────────────────────────────────────────

class BandwidthWorker(QThread):
    """Captures per-device bandwidth and emits snapshots every interval_s seconds."""
    snapshot = pyqtSignal(object)   # BandwidthSnapshot
    status   = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(
        self,
        interval_s: float = 5.0,
        label_map: Optional[dict] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.interval_s = interval_s
        self.label_map  = label_map or {}
        self._stop      = threading.Event()

    def run(self):
        try:
            from modules.bandwidth_monitor import BandwidthMonitor
            monitor = BandwidthMonitor(
                interval_s=self.interval_s,
                on_snapshot=lambda s: self.snapshot.emit(s),
                on_error=lambda m: self.error.emit(m),
                label_map=self.label_map,
                stop_event=self._stop,
            )
            self.status.emit(f"Bandwidth monitor started (window: {self.interval_s:.0f}s)…")
            monitor.run()
        except Exception as exc:
            self.error.emit(f"Bandwidth monitor error: {exc}")

    def stop(self):
        self._stop.set()


# ── Scheduled scanner worker ──────────────────────────────────────────────────

class SchedulerWorker(QThread):
    """Runs periodic device scans and emits alerts for new/changed devices."""
    scan_result = pyqtSignal(object)   # ScheduledScanResult
    alert       = pyqtSignal(str, str) # title, message
    status      = pyqtSignal(str)
    error       = pyqtSignal(str)

    def __init__(
        self,
        interval_minutes: int = 15,
        offenders_path=None,
        notify_desktop: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.interval_minutes = interval_minutes
        self.offenders_path   = offenders_path
        self.notify_desktop   = notify_desktop
        self._stop            = threading.Event()
        self._scheduler       = None

    def run(self):
        try:
            from modules.scheduler import ScanScheduler
            self._scheduler = ScanScheduler(
                interval_minutes=self.interval_minutes,
                offenders_path=self.offenders_path,
                on_result=lambda r: self.scan_result.emit(r),
                on_alert=lambda t, m: self.alert.emit(t, m),
                on_status=lambda m: self.status.emit(m),
                stop_event=self._stop,
                notify_desktop=self.notify_desktop,
            )
            self._scheduler.run()
        except Exception as exc:
            self.error.emit(f"Scheduler error: {exc}")

    def stop(self):
        self._stop.set()
        if self._scheduler:
            self._scheduler.stop()


# ── SNMP poller worker ────────────────────────────────────────────────────────

class SNMPWorker(QThread):
    """Polls a list of hosts via SNMP and emits results."""
    host_result = pyqtSignal(object)   # SNMPResult
    status      = pyqtSignal(str)
    error       = pyqtSignal(str)

    def __init__(
        self,
        hosts: list,
        community: str = "public",
        timeout: float = 2.0,
        parent=None,
    ):
        super().__init__(parent)
        self.hosts     = hosts
        self.community = community
        self.timeout   = timeout

    def run(self):
        try:
            from modules.snmp_poller import poll_hosts
            self.status.emit(f"SNMP polling {len(self.hosts)} host(s)…")
            results = poll_hosts(
                self.hosts,
                community=self.community,
                timeout=self.timeout,
                progress_cb=lambda m: self.status.emit(m),
            )
            for r in results:
                self.host_result.emit(r)
            reachable = sum(1 for r in results if r.reachable)
            self.status.emit(f"SNMP done — {reachable}/{len(results)} host(s) responded.")
        except Exception as exc:
            self.error.emit(f"SNMP error: {exc}")


class SNMPIfErrorWorker(QThread):
    """Polls ifTable error/discard counters for a single host."""
    result_ready = pyqtSignal(list)   # list[IfErrorEntry]
    status       = pyqtSignal(str)
    error        = pyqtSignal(str)

    def __init__(
        self,
        host: str,
        community: str = "public",
        timeout: float = 2.0,
        parent=None,
    ):
        super().__init__(parent)
        self.host      = host
        self.community = community
        self.timeout   = timeout

    def run(self):
        try:
            from modules.snmp_poller import poll_if_errors
            self.status.emit(f"Polling interface errors on {self.host}…")
            entries = poll_if_errors(self.host, self.community, self.timeout)
            self.result_ready.emit(entries)
            total = sum(e.total_issues for e in entries)
            self.status.emit(
                f"Interface poll done — {len(entries)} interface(s), {total} total error/discard events."
            )
        except Exception as exc:
            self.error.emit(f"Interface error poll failed: {exc}")


# ── Recon workers ─────────────────────────────────────────────────────────────

class SYNScanWorker(QThread):
    """SYN stealth scan worker — requires admin + Npcap (Windows)."""
    result = pyqtSignal(object)   # SYNScanResult
    status = pyqtSignal(str)
    error  = pyqtSignal(str)

    def __init__(self, host: str, ports=None, rate_pps: int = 500, parent=None):
        super().__init__(parent)
        self.host     = host
        self.ports    = ports
        self.rate_pps = rate_pps
        self._stop    = __import__("threading").Event()

    def stop(self):
        self._stop.set()

    def run(self):
        try:
            from modules.syn_scanner import syn_scan
            result = syn_scan(
                self.host,
                ports=self.ports,
                rate_pps=self.rate_pps,
                progress_cb=lambda m: self.status.emit(m),
                stop_event=self._stop,
            )
            if result.error:
                self.error.emit(result.error)
            else:
                self.result.emit(result)
        except Exception as exc:
            self.error.emit(f"SYN scan error: {exc}")


class UDPScanWorker(QThread):
    """UDP scan worker — requires admin + Npcap (Windows)."""
    result = pyqtSignal(object)   # SYNScanResult (scan_type="udp")
    status = pyqtSignal(str)
    error  = pyqtSignal(str)

    def __init__(self, host: str, ports=None, timeout: float = 2.0, parent=None):
        super().__init__(parent)
        self.host    = host
        self.ports   = ports
        self.timeout = timeout

    def run(self):
        try:
            from modules.syn_scanner import udp_scan
            result = udp_scan(
                self.host,
                ports=self.ports,
                timeout=self.timeout,
                progress_cb=lambda m: self.status.emit(m),
            )
            if result.error:
                self.error.emit(result.error)
            else:
                self.result.emit(result)
        except Exception as exc:
            self.error.emit(f"UDP scan error: {exc}")


class OSFingerprintWorker(QThread):
    """Deep OS fingerprint worker — tier-2 (Scapy) runs if admin available."""
    result = pyqtSignal(dict)    # {"guesses": [OSGuess, ...]}
    status = pyqtSignal(str)
    error  = pyqtSignal(str)

    def __init__(self, ips: list, parent=None):
        super().__init__(parent)
        self.ips = ips

    def run(self):
        try:
            from modules.os_fingerprint import fingerprint_hosts
            results = fingerprint_hosts(
                self.ips,
                progress_cb=lambda m: self.status.emit(m),
            )
            self.result.emit({"guesses": list(results.values())})
        except Exception as exc:
            self.error.emit(f"OS fingerprint error: {exc}")


class CVELookupWorker(QThread):
    """Queries NVD API v2 for CVEs matching detected service versions."""
    cve_result = pyqtSignal(str, object)  # (service_version, CVELookupResult)
    status     = pyqtSignal(str)
    finished_all = pyqtSignal()

    def __init__(self, service_versions: list, parent=None):
        super().__init__(parent)
        self.service_versions = service_versions

    def run(self):
        try:
            from modules.cve_lookup import lookup_many
            results = lookup_many(
                self.service_versions,
                progress_cb=lambda m: self.status.emit(m),
            )
            for sv, res in results.items():
                self.cve_result.emit(sv, res)
            self.finished_all.emit()
        except Exception as exc:
            self.status.emit(f"CVE lookup error: {exc}")
            self.finished_all.emit()


class InternetExposureWorker(QThread):
    """Checks WAN IP, CGNAT status, and UPnP port-forwarding rules."""
    result = pyqtSignal(object)   # ExposureResult
    status = pyqtSignal(str)
    error  = pyqtSignal(str)

    def run(self):
        try:
            from modules.internet_exposure import check_exposure
            res = check_exposure(progress_cb=lambda m: self.status.emit(m))
            if res.error:
                self.error.emit(res.error)
            else:
                self.result.emit(res)
        except Exception as exc:
            self.error.emit(f"Exposure check error: {exc}")


class CredentialedScanWorker(QThread):
    """SSH credentialed deep scan — installed packages, users, services, patches."""
    result = pyqtSignal(object)   # CredScanResult
    status = pyqtSignal(str)
    error  = pyqtSignal(str)

    def __init__(self, host: str, ssh_port: int = 22, username: str = "root",
                 password: str = "", key_path: str = "", os_hint: str = "auto",
                 parent=None):
        super().__init__(parent)
        self.host     = host
        self.ssh_port = ssh_port
        self.username = username
        self.password = password or None
        self.key_path = key_path or None
        self.os_hint  = os_hint
        self._stop    = __import__("threading").Event()

    def stop(self):
        self._stop.set()

    def run(self):
        try:
            from modules.credentialed_scan import credentialed_ssh_scan
            res = credentialed_ssh_scan(
                self.host,
                ssh_port=self.ssh_port,
                username=self.username,
                password=self.password,
                key_path=self.key_path,
                os_hint=self.os_hint,
                progress_cb=lambda m: self.status.emit(m),
                stop_event=self._stop,
            )
            if res.error:
                self.error.emit(res.error)
            else:
                self.result.emit(res)
        except Exception as exc:
            self.error.emit(f"Credentialed scan error: {exc}")


class CombinedDiscoveryWorker(QThread):
    """Ultra-fast parallel device discovery (ARP cache + ARP sweep + ICMP + TCP + mDNS)."""
    result = pyqtSignal(object)   # DiscoveryResult
    status = pyqtSignal(str)
    error  = pyqtSignal(str)

    def __init__(self, cidr: str = "", passive_only: bool = False,
                 resolve_hostnames: bool = True, parent=None):
        super().__init__(parent)
        self.cidr              = cidr or None
        self.passive_only      = passive_only
        self.resolve_hostnames = resolve_hostnames
        self._stop             = __import__("threading").Event()

    def stop(self):
        self._stop.set()

    def run(self):
        try:
            from modules.combined_discovery import discover
            res = discover(
                self.cidr,
                passive_only=self.passive_only,
                resolve_hostnames=self.resolve_hostnames,
                progress_cb=lambda m: self.status.emit(m),
                stop_event=self._stop,
            )
            if res.error:
                self.error.emit(res.error)
            else:
                self.result.emit(res)
        except Exception as exc:
            self.error.emit(f"Combined discovery error: {exc}")


class SMBEnumWorker(QThread):
    """SMB / NetBIOS enumeration — shares, users, sessions, domain info."""
    result = pyqtSignal(object)   # SMBEnumResult
    status = pyqtSignal(str)
    error  = pyqtSignal(str)

    def __init__(self, host: str, username: str = "", password: str = "",
                 domain: str = "", parent=None):
        super().__init__(parent)
        self.host     = host
        self.username = username
        self.password = password
        self.domain   = domain
        self._stop    = __import__("threading").Event()

    def stop(self):
        self._stop.set()

    def run(self):
        try:
            from modules.smb_enumerator import enumerate_smb
            res = enumerate_smb(
                self.host,
                username=self.username,
                password=self.password,
                domain=self.domain,
                progress_cb=lambda m: self.status.emit(m),
                stop_event=self._stop,
            )
            if res.error:
                self.error.emit(res.error)
            else:
                self.result.emit(res)
        except Exception as exc:
            self.error.emit(f"SMB enum error: {exc}")


class PluginWorker(QThread):
    """Runs one plugin against a device list in a background thread."""
    result = pyqtSignal(object)   # PluginResult
    status = pyqtSignal(str)
    error  = pyqtSignal(str)

    def __init__(self, plugin_info, devices: list, parent=None):
        super().__init__(parent)
        self._info    = plugin_info
        self._devices = devices

    def run(self):
        try:
            from modules.plugin_system import run_plugin
            self.status.emit(f"Running plugin: {self._info.name}…")
            res = run_plugin(self._info, self._devices)
            if res.error:
                self.error.emit(res.error)
            else:
                self.result.emit(res)
        except Exception as exc:
            self.error.emit(f"Plugin error: {exc}")


class PrivateEndpointWorker(QThread):
    """Checks a list of private endpoints (DNS, TCP, TLS) in a background thread."""
    result    = pyqtSignal(object)   # EndpointResult per endpoint
    status    = pyqtSignal(str)
    finished_all = pyqtSignal()
    error     = pyqtSignal(str)

    def __init__(self, specs: list, parent=None):
        super().__init__(parent)
        self._specs = specs

    def run(self):
        try:
            from modules.private_endpoint_checker import check_endpoint
            total = len(self._specs)
            for i, spec in enumerate(self._specs, 1):
                self.status.emit(f"Checking {spec.label}… ({i}/{total})")
                res = check_endpoint(spec)
                self.result.emit(res)
            self.finished_all.emit()
        except Exception as exc:
            self.error.emit(f"Private endpoint check error: {exc}")


# ── IPv6 sweep worker ─────────────────────────────────────────────────────────

class IPv6Worker(QThread):
    """
    Discovers IPv6 devices on the local link-local segment.
    Reads the OS neighbour cache first, then optionally does an active ping6
    sweep across fe80::/8 on each interface.
    """
    result   = pyqtSignal(list)   # List[dict] with {ip6, mac, state, source}
    status   = pyqtSignal(str)
    error    = pyqtSignal(str)

    def run(self):
        try:
            from modules.utils import ping_sweep_ipv6
            self.status.emit("IPv6: scanning neighbour cache + active sweep…")
            devices = ping_sweep_ipv6(progress_cb=lambda m: self.status.emit(m))
            self.status.emit(f"IPv6: {len(devices)} device(s) found.")
            self.result.emit(devices)
        except Exception as exc:
            self.error.emit(f"IPv6 scan error: {exc}")


# ── Cloud metadata worker ─────────────────────────────────────────────────────

class CloudMetadataWorker(QThread):
    """
    Probes cloud metadata endpoints (AWS IMDSv1/v2, Azure, GCP) to check
    whether this machine is running inside a cloud VM, and scans the network
    for devices that may be exposing metadata as an SSRF proxy.
    """
    local_result   = pyqtSignal(object)   # CloudMetadataResult
    network_result = pyqtSignal(list)     # List[NetworkExposureResult]
    status         = pyqtSignal(str)
    error          = pyqtSignal(str)

    def __init__(self, devices: list = None, parent=None):
        super().__init__(parent)
        self._devices = devices or []

    def run(self):
        try:
            from modules.cloud_metadata import check_local_imds, check_network_imds_exposure
            self.status.emit("Cloud metadata: probing IMDS endpoints…")
            local = check_local_imds()
            self.local_result.emit(local)

            if self._devices:
                self.status.emit("Cloud metadata: checking network for SSRF exposure…")
                net = check_network_imds_exposure(self._devices)
                self.network_result.emit(net)

            self.status.emit("Cloud metadata check complete.")
        except Exception as exc:
            self.error.emit(f"Cloud metadata error: {exc}")
