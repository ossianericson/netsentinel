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
        flush_caches: bool = True,
    ):
        self.interval_s     = interval_minutes * 60
        self.offenders_path = offenders_path
        self.on_result      = on_result  or (lambda r: None)
        self.on_alert       = on_alert   or (lambda t, m: None)
        self.on_status      = on_status  or (lambda m: None)
        self.stop_event     = stop_event or threading.Event()
        self.notify_desktop = notify_desktop
        self.flush_caches   = flush_caches
        self._baseline: dict = {}   # mac → device info dict

    def _run_scan(self) -> dict:
        from modules.rogue_device import scan as m1_scan
        from modules.utils import get_offenders_path, flush_network_caches, get_local_ip, ping_sweep_subnet

        path = self.offenders_path or get_offenders_path()
        if self.flush_caches:
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


# ── Scheduled-scan next-run arithmetic ───────────────────────────────────────
# Shared by ui/dashboard.py (the 60 s tick that fires the scan) and
# ui/pages/settings_cards.py (which saves the next run when the user edits the
# schedule). These used to carry separate copies that disagreed — the consumer
# looped with `while`, the writer advanced once with `if` — so a schedule several
# intervals in the past was saved still in the past and fired on the next tick.

_VALID_INTERVAL_HOURS = (1, 6, 12, 24)
_DEFAULT_INTERVAL_HOURS = 24


def _coerce_int(value: object, default: int, lo: int, hi: int) -> int:
    """Clamp an untyped QSettings value into ``[lo, hi]``, falling back to ``default``.

    QSettings on Windows round-trips through untyped INI text, so any of these can
    arrive here: an int, a numeric string, an empty string, ``None``, or garbage
    left by an unrelated writer. A scheduling slot must never raise on any of them.
    """
    try:
        out = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, out))


def next_scheduled_run(
    *,
    now: float,
    hour: object,
    minute: object,
    interval_hours: object,
) -> float:
    """Return the next run strictly after ``now``, as an epoch timestamp.

    ``interval_hours`` is clamped to a positive value before it is used as a loop
    increment. A zero or negative increment can never carry the candidate past
    ``now``, so the advance loop would not terminate — and its callers run it on
    the GUI thread, where that is an unrecoverable "Not Responding" hang rather
    than a slow function.

    Local wall-clock arithmetic is deliberate: a schedule of "02:00" means 02:00
    where the user is, so a DST shift should move it by the same hour the clock
    moved. Half-hour zones (India +5:30, Adelaide +9:30) need no special handling —
    naive ``.timestamp()`` resolves against the platform's real local zone.
    """
    import datetime as _dt

    hh = _coerce_int(hour, 2, 0, 23)
    mm = _coerce_int(minute, 0, 0, 59)
    step = _coerce_int(interval_hours, _DEFAULT_INTERVAL_HOURS, 1, 24 * 7)
    if step not in _VALID_INTERVAL_HOURS and step <= 0:
        step = _DEFAULT_INTERVAL_HOURS

    nxt = _dt.datetime.fromtimestamp(now).replace(
        hour=hh, minute=mm, second=0, microsecond=0
    )
    # Bounded: `step` is >= 1 hour, so this terminates in at most 24*7 iterations
    # even if `now` sat a full week past the anchor.
    while nxt.timestamp() <= now:
        nxt += _dt.timedelta(hours=step)
    return nxt.timestamp()
