"""
Scheduled scan engine + desktop notification dispatcher.

Runs a background thread that fires a full device scan every N minutes.
On completion, compares results against the last baseline and fires a
desktop notification if new or changed devices are found.

Desktop notifications:
  Windows  — PowerShell toast via the Windows.UI.Notifications API
  macOS    — osascript notification
  Linux    — notify-send
All fallback gracefully if the platform notification API is unavailable.
"""

import platform
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional


# ── Notification helpers ──────────────────────────────────────────────────────

def _escape_ps_string(s: str) -> str:
    """Escape a string for safe embedding inside a PowerShell double-quoted literal."""
    return s.replace("`", "``").replace('"', '`"').replace("$", "`$")


def _escape_applescript_string(s: str) -> str:
    """Escape a string for safe embedding inside an AppleScript double-quoted literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _notify(title: str, message: str) -> None:
    """Best-effort desktop notification. Silently ignores all errors."""
    system = platform.system()
    try:
        if system == "Windows":
            # Try PowerShell toast (no extra package needed on Win10+)
            ps_title = _escape_ps_string(title)
            ps_message = _escape_ps_string(message)
            ps = (
                f'[Windows.UI.Notifications.ToastNotificationManager,'
                f'Windows.UI.Notifications,ContentType=WindowsRuntime] | Out-Null;'
                f'$t=[Windows.UI.Notifications.ToastTemplateType]::ToastText02;'
                f'$x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($t);'
                f'$x.GetElementsByTagName("text")[0].AppendChild($x.CreateTextNode("{ps_title}")) | Out-Null;'
                f'$x.GetElementsByTagName("text")[1].AppendChild($x.CreateTextNode("{ps_message}")) | Out-Null;'
                f'$n=[Windows.UI.Notifications.ToastNotification]::new($x);'
                f'[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("NetSentinel").Show($n)'
            )
            subprocess.run(
                ["powershell", "-WindowStyle", "Hidden", "-Command", ps],
                timeout=5,
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        elif system == "Darwin":
            as_title = _escape_applescript_string(title)
            as_message = _escape_applescript_string(message)
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{as_message}" with title "{as_title}"'],
                timeout=5,
                capture_output=True,
            )
        else:
            subprocess.run(
                ["notify-send", title, message, "--icon=network-wired"],
                timeout=5,
                capture_output=True,
            )
    except Exception:
        pass  # non-fatal


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ScheduledScanResult:
    timestamp: float = field(default_factory=time.time)
    new_devices: List[dict] = field(default_factory=list)
    changed_devices: List[dict] = field(default_factory=list)
    total_devices: int = 0
    scan_data: dict = field(default_factory=dict)


# ── Scheduler ─────────────────────────────────────────────────────────────────

class ScanScheduler:
    """
    Runs device scans on a configurable interval.
    Emits callbacks for scan completion and new/changed device alerts.
    """

    def __init__(
        self,
        interval_minutes: int = 15,
        offenders_path=None,
        on_result: Optional[Callable[[ScheduledScanResult], None]] = None,
        on_alert: Optional[Callable[[str, str], None]] = None,   # title, message
        on_status: Optional[Callable[[str], None]] = None,
        stop_event: Optional[threading.Event] = None,
        notify_desktop: bool = True,
    ):
        self.interval_s     = interval_minutes * 60
        self.offenders_path = offenders_path
        self.on_result      = on_result  or (lambda r: None)
        self.on_alert       = on_alert   or (lambda t, m: None)
        self.on_status      = on_status  or (lambda m: None)
        self.stop_event     = stop_event or threading.Event()
        self.notify_desktop = notify_desktop
        self._baseline: dict = {}   # mac → device info dict

    def _run_scan(self) -> dict:
        from modules.rogue_device import scan as m1_scan
        from modules.utils import get_offenders_path, flush_network_caches, get_local_ip, ping_sweep_subnet

        path = self.offenders_path or get_offenders_path()
        self.on_status("Scheduled scan: flushing caches…")
        flush_network_caches()
        local_ip = get_local_ip()
        self.on_status("Scheduled scan: discovering devices…")
        ping_sweep_subnet(local_ip)
        self.on_status("Scheduled scan: fingerprinting devices…")
        return m1_scan(path)

    def _diff(self, scan_data: dict) -> ScheduledScanResult:
        from modules.utils import diff_devices_against_baseline
        devices = scan_data.get("devices", [])
        device_dicts = []
        for d in devices:
            if isinstance(d, dict):
                device_dicts.append(d)
            else:
                device_dicts.append({
                    "mac": d.mac, "ip": d.ip,
                    "hostname": d.hostname, "vendor": d.vendor,
                    "risk_level": d.risk_level,
                })

        new_macs = diff_devices_against_baseline(device_dicts, self._baseline)
        changed: List[dict] = []
        for d in device_dicts:
            mac = d.get("mac", "")
            if mac in self._baseline:
                prev = self._baseline[mac]
                if prev.get("ip") != d.get("ip"):
                    changed.append({**d, "prev_ip": prev.get("ip")})

        return ScheduledScanResult(
            new_devices=new_macs,
            changed_devices=changed,
            total_devices=len(device_dicts),
            scan_data=scan_data,
        )

    def _alert(self, result: ScheduledScanResult) -> None:
        if result.new_devices:
            count = len(result.new_devices)
            macs  = ", ".join(d.get("mac", "?") for d in result.new_devices[:3])
            title = f"NetSentinel — {count} new device(s)"
            msg   = f"New: {macs}{' …' if count > 3 else ''}"
            self.on_alert(title, msg)
            if self.notify_desktop:
                _notify(title, msg)

        for d in result.changed_devices:
            title = "NetSentinel — Device IP changed"
            msg   = f"{d.get('mac', '?')} moved: {d.get('prev_ip', '?')} → {d.get('ip', '?')}"
            self.on_alert(title, msg)
            if self.notify_desktop:
                _notify(title, msg)

        high = [d for d in result.new_devices if d.get("risk_level") == "HIGH"]
        if high:
            title = "⚠ NetSentinel — HIGH RISK device!"
            msg   = f"{high[0].get('vendor', '?')} ({high[0].get('mac', '?')}) — {high[0].get('ip', '?')}"
            self.on_alert(title, msg)
            if self.notify_desktop:
                _notify(title, msg)

    def run(self):
        """Blocking run loop — call from a QThread or background thread."""
        self.on_status(
            f"Scheduled scanner active — scanning every {self.interval_s // 60} min."
        )
        while not self.stop_event.is_set():
            try:
                scan_data = self._run_scan()
                result    = self._diff(scan_data)
                self._alert(result)
                self.on_result(result)
                self.on_status(
                    f"Scheduled scan complete — {result.total_devices} device(s), "
                    f"{len(result.new_devices)} new."
                )
            except Exception as exc:
                self.on_status(f"Scheduled scan error: {exc}")

            # Sleep in 1-second ticks so stop() is responsive
            for _ in range(self.interval_s):
                if self.stop_event.is_set():
                    break
                time.sleep(1)

        self.on_status("Scheduled scanner stopped.")

    def stop(self):
        self.stop_event.set()
