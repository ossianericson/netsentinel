#!/usr/bin/env python3
"""
tools/scan_navigate_test.py - Scan-then-navigate-away churn tester for NetSentinel
====================================================================================
Neither monkey_test.py (UIA control clicking) nor monkey_mouse_test.py (raw-input
mouse fuzzing) deliberately triggers a real scan and then immediately leaves its
page before the worker finishes. That specific sequence — start a background
QThread worker, navigate away before its result_ready signal fires, let it fire
against a page that is no longer the active one — is a distinct bug class from
both: a worker updating a hidden/torn-down widget, a stale `_nav_set_scan_state`
call racing a page switch, or a crash in a `result_ready` slot that assumed its
page was still visible (RULE 4 / RULE-SS1 territory).

This script does not fuzz. Each iteration is deliberate and known:
  1. Navigate to a specific page (keyboard command palette — not mouse).
  2. Click its specific, named scan-start button (UIA `click_input()` — precise
     targeting is correct here, unlike monkey_mouse_test.py, because we already
     know exactly which control we mean).
  3. Wait a short, randomized "still probably running" delay.
  4. Navigate away to an unrelated read-only page.
  5. Wait a "settle" delay for the scan to finish in the background.
  6. Check for a stray error dialog, then verify the app is still alive.

Scan whitelist (see _SCAN_TARGETS) — deliberately excludes:
  * Login Test / credentialed scan — can lock real accounts on repeated runs.
  * TLS & Exposure — no persistent single-click trigger; its only button
    (cert_page.py "Scan Network") is an EmptyStateCard CTA that disappears
    after the first host is added, then becomes an "+ Add Host" text-entry
    flow, not a repeatable click target.
  * The Overview page's collapsible "Security Scan" panel ("Run Selected")
    — behavior depends on which checkboxes are ticked, an ambiguous default
    state not worth automating around when 8 unambiguous single-button
    triggers already cover the same worker/page-lifecycle risk.

Usage (source - skips build step, faster iteration):
    python tools/scan_navigate_test.py --source

Usage (exe):
    python tools/scan_navigate_test.py "dist\\NetSentinel.exe"

Options (in addition to every monkey_test.py option — see its --help):
    --interrupt-delay-min/max SECS  Random wait after clicking the scan
                                     button, before navigating away
                                     (default 1.0 / 6.0)
    --settle-delay-min/max SECS     Random wait on the "away" page before
                                     checking for damage (default 2.0 / 6.0)

Requirements: same as monkey_test.py — pip install pywinauto psutil Pillow

Exit codes: identical to monkey_test.py (0 clean, 1 crash/hang, 2 launch failure)
"""

import dataclasses
import random
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
try:
    import monkey_test as _mt
except ImportError:
    if __name__ == "__main__":
        sys.exit("ERROR: pywinauto/psutil required.  pip install pywinauto psutil")
    raise

# ── Scan whitelist ─────────────────────────────────────────────────────────────
# Ordered deliberately: Home first, so later iterations have real device data
# to work with (an empty device table can't meaningfully race a table repaint).
# "buttons" lists fallback candidates tried in order — Home shows "Rescan"
# only after a scan has already run once; before that, "Scan Network" is the
# visible button.
#
# "prefill": three of these buttons are wired to handlers that silently
# return without starting anything if their one QLineEdit is empty —
# _start_syn_scan()/_start_udp_scan() do `if not host: return`, and
# _start_cve_lookup() needs either manual text or rows in a *different*
# page's port-scan table that this whitelist never populates. Clicking the
# button alone looks identical to a successful click (no error, no dialog)
# but never starts a worker — this is exactly what silently made "the script
# just navigates, does not start the scans" true. "<gateway>" is a sentinel
# resolved to a real IP guess at run time (see _discover_gateway_ip); OS
# Detection is deliberately left without a prefill because it falls back to
# the last full-scan results when its field is blank.
_SCAN_TARGETS = [
    {"page": "Home", "buttons": ["▶  Rescan", "▶  Scan Network"]},
    {"page": "Full Device Discovery", "buttons": ["🚀  Start Discovery"]},
    {"page": "Port Scan (TCP)", "buttons": ["⚡  SYN Scan"], "prefill": "<gateway>"},
    {"page": "Port Scan (UDP)", "buttons": ["📻  UDP Scan"], "prefill": "<gateway>"},
    {"page": "OS Detection", "buttons": ["🖥  Fingerprint"]},
    {"page": "CVE Lookup", "buttons": ["🛡  Lookup CVEs"], "prefill": "OpenSSH 8.9p1"},
    {"page": "Threat Intel", "buttons": ["Update Feeds"]},
    {"page": "Exposed to Internet", "buttons": ["🌐  Check Exposure"]},
]

# Read-only pages to sit on while a triggered scan finishes in the background —
# reused verbatim from monkey_test.py's own vetted list so a bug here can never
# be blamed on this script triggering a second scan on the "away" page.
_AWAY_PAGES = list(_mt._SAFE_PAGES)


def _navigate_to_page(win, label: str, log) -> bool:
    """Force navigation to *label* via the Ctrl+K command palette (keyboard)."""
    try:
        win.type_keys("^k")
        time.sleep(0.45)
        win.type_keys(label[:6], with_spaces=True, pause=0.04)
        time.sleep(0.30)
        win.type_keys("{ENTER}")
        time.sleep(0.50)
        log.info("[nav] Navigated to %r via command palette", label)
        return True
    except Exception as exc:
        log.warning("[nav] Navigation to %r failed: %s", label, exc)
        try:
            win.type_keys("{ESC}")
        except Exception:
            pass  # non-fatal — next iteration's dialog/focus guards recover
        return False


def _discover_gateway_ip() -> str:
    """Best-effort local gateway guess for filling scan-target host fields.

    Not security-sensitive — this only needs to be a plausible, likely-live
    LAN host so a probe-only scan (SYN/UDP against your own gateway) actually
    starts instead of silently no-op'ing on an empty host field. Opening a
    UDP socket to a public IP never sends a packet (no connect handshake for
    UDP) — it only asks the OS to pick a local source address/route, which is
    how we learn this machine's own LAN IP without any network traffic.
    """
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        finally:
            s.close()
        octets = local_ip.split(".")
        return ".".join(octets[:3] + ["1"])   # .1 is the overwhelming default for home routers
    except Exception:
        return "192.168.1.1"


def _fill_edit_field(win, text: str, log) -> bool:
    """Type *text* into the first visible, enabled Edit control on the
    current page. Manual descendants() walk + type filter, mirroring
    monkey_test.py's own pattern, rather than trusting an unverified
    descendants(control_type=...) kwarg."""
    try:
        descendants = win.descendants()
    except Exception:
        descendants = []
    for ctrl in descendants:
        try:
            if _mt._safe_type(ctrl) != "Edit":
                continue
            if not ctrl.is_visible() or not ctrl.is_enabled():
                continue
            ctrl.set_edit_text(text)
            log.info("[scan] Filled input field with %r", text)
            return True
        except Exception:
            continue
    return False


def _find_and_click_button(win, candidates, log):
    """Try each candidate button text in order; click and return the first
    one found enabled. Returns None if none of the candidates are present
    (e.g. an admin-required banner is covering the button)."""
    for label in candidates:
        try:
            btn = win.child_window(title=label, control_type="Button")
            if btn.exists(timeout=1.0) and btn.is_enabled():
                btn.click_input()
                log.info("[scan] Clicked %r", label)
                return label
        except Exception:
            continue
    return None


# ── Config ─────────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class ScanNavConfig(_mt.Config):
    iterations: int = 60   # 8 targets cycle quickly; each iteration is several seconds
    interrupt_delay_min: float = 1.0
    interrupt_delay_max: float = 6.0
    settle_delay_min: float = 2.0
    settle_delay_max: float = 6.0


# ── Tester ─────────────────────────────────────────────────────────────────────

class ScanNavigateTester(_mt.MonkeyTester):
    """Reuses MonkeyTester's launch/connect/dialog-guard/health-monitor/crash-report
    machinery unchanged; overrides only the per-iteration action — a deliberate
    scan-trigger + navigate-away sequence instead of a random UIA control or
    raw mouse point."""

    def __init__(self, cfg: ScanNavConfig):
        super().__init__(cfg)
        self.cfg: ScanNavConfig = cfg
        self._target_idx = 0
        self._gateway_ip = _discover_gateway_ip()

    def _pick_away_page(self, exclude_label: str) -> str:
        pool = [p for p in _AWAY_PAGES if p != exclude_label]
        return random.choice(pool) if pool else exclude_label

    def _do_scan_navigate(self, n: int) -> "_mt.Action":
        ts = datetime.now().strftime("%H:%M:%S")
        target = _SCAN_TARGETS[self._target_idx % len(_SCAN_TARGETS)]
        self._target_idx += 1
        page = target["page"]

        if not _navigate_to_page(self._win, page, self.log):
            return _mt.Action(n=n, ts=ts, ctype="ScanNav", name=page,
                               auto_id="", action="nav_failed", result="err")

        prefill = target.get("prefill")
        if prefill == "<gateway>":
            prefill = self._gateway_ip
        if prefill:
            _fill_edit_field(self._win, prefill, self.log)

        clicked = _find_and_click_button(self._win, target["buttons"], self.log)
        if clicked is None:
            return _mt.Action(n=n, ts=ts, ctype="ScanNav", name=page,
                               auto_id="", action="button_not_found", result="skipped")

        interrupt_delay = random.uniform(self.cfg.interrupt_delay_min, self.cfg.interrupt_delay_max)
        time.sleep(interrupt_delay)

        away = self._pick_away_page(page)
        _navigate_to_page(self._win, away, self.log)

        settle_delay = random.uniform(self.cfg.settle_delay_min, self.cfg.settle_delay_max)
        time.sleep(settle_delay)

        # Catch any error/exception dialog the background scan's completion
        # may have raised while its originating page was hidden — exactly
        # the class of bug this tester exists to surface.
        self._dismiss_blocking_dialogs()

        self.stats.record("ScanNav", f"{page}:{clicked}")
        return _mt.Action(
            n=n, ts=ts, ctype="ScanNav", name=page, auto_id="",
            action=(f"prefill={prefill!r} clicked={clicked!r} interrupt={interrupt_delay:.1f}s "
                    f"away={away!r} settle={settle_delay:.1f}s"),
            result="ok",
        )

    def _run_one(self, n: int) -> bool:
        if self._proc:
            _mt._wait_cpu(self._proc, self.cfg.cpu_threshold, self.cfg.cpu_wait_max)

        if not self._alive():
            self.log.error("Process died before iteration %d", n)
            return False
        if not self._window_ok():
            self.log.error("Window gone before iteration %d", n)
            return False

        self._dismiss_blocking_dialogs()

        if not self._assert_focus():
            self.log.warning("[focus] skipping iteration %d (could not reclaim foreground)", n)
            self.stats.skipped += 1
            self.stats.completed += 1
            self._last_iter_time = time.time()
            return True

        rec = self._do_scan_navigate(n)
        self.hist.add(rec)
        self.log.info("[%4d] %-10s %-24s  %s", n, rec.ctype, rec.name, rec.action)
        self.stats.completed += 1
        self._last_iter_time = time.time()
        return True


# ── CLI ────────────────────────────────────────────────────────────────────────

def _build_parser():
    p = _mt._build_parser()
    p.description = "Scan-trigger + navigate-away churn tester for NetSentinel"
    p.epilog = __doc__
    p.set_defaults(iterations=60)
    p.add_argument("--interrupt-delay-min", type=float, default=1.0, metavar="SECS",
                   help="Min seconds to wait after clicking the scan button before "
                        "navigating away (default 1.0)")
    p.add_argument("--interrupt-delay-max", type=float, default=6.0, metavar="SECS",
                   help="Max seconds to wait after clicking the scan button before "
                        "navigating away (default 6.0)")
    p.add_argument("--settle-delay-min", type=float, default=2.0, metavar="SECS",
                   help="Min seconds to wait on the away page before checking for "
                        "damage (default 2.0)")
    p.add_argument("--settle-delay-max", type=float, default=6.0, metavar="SECS",
                   help="Max seconds to wait on the away page before checking for "
                        "damage (default 6.0)")
    return p


def main() -> None:
    args = _build_parser().parse_args()

    if not args.source and not args.connect and not args.exe_path:
        print("ERROR: provide an exe path, --source, or --connect", file=sys.stderr)
        sys.exit(2)

    if args.exe_path and not Path(args.exe_path).exists():
        print(f"ERROR: exe not found: {args.exe_path}", file=sys.stderr)
        sys.exit(2)

    if args.tracemalloc and not args.source:
        print("WARNING: --tracemalloc only works with --source (ignored for exe/connect mode)",
              file=sys.stderr)

    cfg = ScanNavConfig(
        exe_path=args.exe_path,
        use_source=args.source,
        connect_only=args.connect,
        iterations=args.iterations,
        duration_secs=args.duration,
        chaos=args.chaos,
        seed=args.seed,
        screenshots=not args.no_screenshots,
        mem_limit_mb=args.mem_limit,
        output_dir=args.output_dir,
        log_file=args.log,
        focus_interval=args.focus_interval,
        prevent_sleep=not args.no_prevent_sleep,
        tracemalloc=args.tracemalloc and args.source,
        max_restarts=args.max_restarts,
        warmup_secs=args.warmup_secs,
        interrupt_delay_min=args.interrupt_delay_min,
        interrupt_delay_max=args.interrupt_delay_max,
        settle_delay_min=args.settle_delay_min,
        settle_delay_max=args.settle_delay_max,
    )

    sys.exit(ScanNavigateTester(cfg).run())


if __name__ == "__main__":
    main()
