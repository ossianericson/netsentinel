"""
plugin_page_mixin.py — _PluginPageMixin.

Extracted from ui/dashboard.py (Sprint 19).
Covers: hardware auto-detection, integration banner, plugin page add/remove/rename,
section reload, and the launch-modules scan-start wiring.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from PyQt6.QtCore import QSettings, pyqtSlot

# Part 1/C3 — scan watchdog budget. A fixed 120s timeout was sized for a home
# /24 and fired a false "took too long" on a large corporate ARP table while
# the scan was still genuinely working. Base + a per-device allowance (derived
# from the last known "n/total" progress message) scales the budget to the
# network actually being scanned; the hard ceiling bounds how long a single
# scan attempt is ever allowed to keep extending itself.
_WATCHDOG_BASE_MS = 120_000
_WATCHDOG_PER_DEVICE_MS = 400
_WATCHDOG_CEILING_MS = 15 * 60_000


class _PluginPageMixin:
    """Methods that manage plugin-provided nav pages and launch core scan workers."""

    # ── Hardware auto-detection ───────────────────────────────────────────────

    def _check_hw_autodetect(self) -> None:
        """Run hardware catalogue detection once per gateway IP per session."""
        gw_ip  = (self._net_info or {}).get("gateway", "").strip()
        gw_mac = (self._net_info or {}).get("gateway_mac", "").strip()
        if not gw_ip:
            return
        # Only re-run when the gateway IP changes (avoid redundant HTTP probes)
        if getattr(self, "_hw_detect_last_gw", "") == gw_ip:
            return
        existing = getattr(self, "_hw_detect_worker", None)
        if existing and existing.isRunning():
            return
        self._hw_detect_last_gw = gw_ip
        from workers.hw_detect_worker import HwDetectWorker
        worker = HwDetectWorker(ip=gw_ip, gateway_mac=gw_mac or None, parent=self)
        worker.detected.connect(self._on_hw_detected)
        worker.error.connect(self._on_hw_detect_error)
        self._hw_detect_worker = worker
        worker.start()

    @pyqtSlot(list)
    def _on_hw_detected(self, matches: list) -> None:
        if hasattr(self, "_hardware_integration_page"):
            self._hardware_integration_page.on_hardware_detected(matches)
        if hasattr(self, "_home_page") and matches:
            self._home_page.on_hw_detected(matches)

    @pyqtSlot(str)
    def _on_hw_detect_error(self, msg: str) -> None:
        if hasattr(self, "_hardware_integration_page"):
            self._hardware_integration_page.on_hardware_detect_error(msg)

    def _plugin_gateway_map(self) -> dict:
        """Return {ip: plugin_name} for all bundled plugins. Cached per session."""
        if hasattr(self, "_plugin_gateway_map_cache"):
            return self._plugin_gateway_map_cache
        import ast
        plugins_dir = Path(__file__).parent.parent / "plugins"
        result: dict = {}
        if not plugins_dir.is_dir():
            self._plugin_gateway_map_cache = result
            return result
        for py in plugins_dir.glob("*.py"):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
                ip = name = None
                for node in ast.walk(tree):
                    if isinstance(node, ast.Assign):
                        for t in node.targets:
                            if isinstance(t, ast.Name):
                                if t.id == "HARDWARE_IP" and isinstance(node.value, ast.Constant):
                                    ip = node.value.value
                                elif t.id == "HARDWARE_NAME" and isinstance(node.value, ast.Constant):
                                    name = node.value.value
                if ip and name:
                    result[ip] = name
            except Exception:
                continue
        self._plugin_gateway_map_cache = result
        return result

    def _check_integration_banner(self, devices: list) -> None:
        """Show discovery banner when a scanned device matches an un-imported bundled plugin."""
        if not hasattr(self, "_m1_int_banner"):
            return
        try:
            gateway_map = self._plugin_gateway_map()
            if not gateway_map:
                self._m1_int_banner.setVisible(False)
                return

            # Find which plugin IPs are already imported (old script list) or
            # registered as Hub instances — either means the user is already set up.
            from PyQt6.QtCore import QSettings as _QS
            import json as _json
            _qs = _QS("NetSentinel", "NetSentinel")
            _imported_paths = set(_qs.value("hardware/plugin_paths", [], type=list))
            import ast
            imported_ips: set = set()
            for p in _imported_paths:
                try:
                    tree = ast.parse(Path(p).read_text(encoding="utf-8", errors="replace"))
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Assign):
                            for t in node.targets:
                                if (isinstance(t, ast.Name) and t.id == "HARDWARE_IP"
                                        and isinstance(node.value, ast.Constant)):
                                    imported_ips.add(node.value.value)
                except Exception:
                    continue
            # Also collect IPs from Hub-registered instances (hardware/instances)
            try:
                _raw_inst = _qs.value("hardware/instances", None)
                if _raw_inst:
                    for _inst in _json.loads(_raw_inst):
                        _ip = _inst.get("ip", "")
                        if _ip:
                            imported_ips.add(_ip)
            except Exception:
                pass  # non-fatal

            # Collect scanned IPs
            scanned_ips = {
                (d.ip if not isinstance(d, dict) else d.get("ip", ""))
                for d in devices
            }

            # Find matches: gateway IP in scan AND plugin not yet imported
            matches = [
                name for ip, name in gateway_map.items()
                if ip in scanned_ips and ip not in imported_ips
            ]

            if matches:
                names = ", ".join(matches[:3])
                if len(matches) > 3:
                    names += f" +{len(matches) - 3} more"
                self._m1_int_lbl.setText(
                    f"⚡  Hardware detected — {names} available for integration"
                )
                self._m1_int_banner.setVisible(True)
            else:
                self._m1_int_banner.setVisible(False)
        except Exception:
            self._m1_int_banner.setVisible(False)

    # ── Plugin page lifecycle ─────────────────────────────────────────────────

    @pyqtSlot(str, str)
    def _on_plugin_page_added(self, path: str, label: str) -> None:
        """Create a nav item under Extend for a newly-installed hardware plugin."""
        from ui.pages.plugin_device_page import PluginDevicePage
        from ui.pages.hardware_integration_page import _validate_script
        from ui.nav.rail import _NavEntry
        if path in getattr(self, "_plugin_pages", {}):
            return  # already registered
        ok, _, meta = _validate_script(path)
        hw_type  = meta.get("type", "other") if ok else "other"
        hw_ip    = meta.get("ip", "") if ok else ""
        cred_lbl = meta.get("credential_label", "Password") if ok else "Password"
        pg = PluginDevicePage(path, label, hw_type, hw_ip=hw_ip,
                              credential_label=cred_lbl, parent=None)
        pg.test_requested.connect(self._on_plugin_page_test)
        pg.navigate_to.connect(self._nav_rail_go_to)
        if not ok or not Path(path).is_file():
            pg.mark_unavailable()
        self._plugin_pages[path] = pg
        # Add to the stack and register under "Extend" in _nav_sections
        if self._stack.indexOf(pg) < 0:
            self._stack.addWidget(pg)
        self._nav_label_to_widget[label] = pg
        self._nav_page_to_section[label] = "Extend"
        entry = _NavEntry(
            label=label, page=pg,
            admin_required=False, audit_item=False,
            pinned=label in self._nav_pinned_labels,
        )
        extend_sec = next((s for s in self._nav_sections if s["name"] == "Extend"), None)
        if extend_sec:
            extend_sec["entries"].append(entry)
        self._log_hub_page.update_plugin_sources(
            [p._label for p in self._plugin_pages.values()]
        )
        self._refresh_hardware_badge()
        if hasattr(self, "_home_page"):
            self._home_page.refresh_hw_strip()
        # Immediately refresh the Extend flyout so the new nav item is visible
        # without requiring the user to click away and back (RULE-PL3).
        self._reload_section("Extend", force_open=True)
        # Navigate to the new page immediately so the user sees live status (P3-2).
        self._nav_rail_go_to(label)

    @pyqtSlot(str)
    def _on_plugin_page_removed(self, path: str) -> None:
        """Remove a plugin's nav item when it is deleted from the Hardware page."""
        pg = self._plugin_pages.pop(path, None)
        if pg is None:
            return
        label = pg._label
        # Remove from nav data structures
        self._nav_label_to_widget.pop(label, None)
        self._nav_page_to_section.pop(label, None)
        extend_sec = next((s for s in self._nav_sections if s["name"] == "Extend"), None)
        if extend_sec:
            extend_sec["entries"] = [
                e for e in extend_sec["entries"] if e.label != label
            ]
        # Remove from stack
        idx = self._stack.indexOf(pg)
        if idx >= 0:
            self._stack.removeWidget(pg)
        pg.deleteLater()
        self._log_hub_page.update_plugin_sources(
            [p._label for p in self._plugin_pages.values()]
        )
        self._refresh_hardware_badge()
        # Refresh the Extend flyout so the removed item disappears immediately (RULE-PL3).
        if getattr(self, "_nav_open_section", "") == "Extend":
            self._reload_section("Extend")

    @pyqtSlot(str, str, str)
    def _on_plugin_page_renamed(self, path: str, old_label: str, new_label: str) -> None:
        """P3-4: Propagate a plugin display-name rename to all nav data structures."""
        pg = getattr(self, "_plugin_pages", {}).get(path)
        if pg is None or old_label == new_label:
            return

        pg._label = new_label

        # Update nav lookup dicts
        self._nav_label_to_widget.pop(old_label, None)
        self._nav_label_to_widget[new_label] = pg
        if hasattr(self, "_nav_page_to_section"):
            self._nav_page_to_section.pop(old_label, None)
            self._nav_page_to_section[new_label] = "Extend"

        # Update the _nav_sections entry in-place
        extend_sec = next((s for s in self._nav_sections if s["name"] == "Extend"), None)
        if extend_sec:
            for entry in extend_sec["entries"]:
                if entry.label == old_label:
                    entry.label = new_label
                    break

        # Update pinned labels if this item was pinned
        if old_label in self._nav_pinned_labels:
            self._nav_pinned_labels.remove(old_label)
            self._nav_pinned_labels.append(new_label)
            self._save_pinned_labels()

        # Reload flyout and update breadcrumb
        self._reload_section("Extend")
        if getattr(self, "_nav_current_page_label", "") == old_label:
            self._nav_current_page_label = new_label
            if hasattr(self, "_breadcrumb_lbl"):
                self._breadcrumb_lbl.setText(f"Extend  ›  {new_label}")

    def _reload_section(self, name: str, force_open: bool = False) -> None:
        """Reload the flyout for the named section and optionally force it open."""
        sec = next((s for s in self._nav_sections if s["name"] == name), None)
        if sec is None or not hasattr(self, "_nav_flyout"):
            return
        entries = [
            (e.label, e.label in self._nav_pinned_labels,
             e.admin_required or e.audit_item)
            for e in sec["entries"]
        ]
        try:
            self._nav_flyout.load_section(
                title=name,
                entries=entries,
                active_label=self._nav_current_page_label,
                on_click=self._nav_rail_go_to,
                on_pin_toggle=self._on_rail_pin_toggle,
                on_pin_move=self._on_rail_pin_move,
            )
            for _lbl, _clr in getattr(self, "_flyout_dots", {}).items():
                if _clr:
                    self._nav_flyout.apply_dot(_lbl, _clr)
            if force_open:
                self._nav_open_section = name
                if name in getattr(self, "_nav_rail_buttons", {}):
                    self._nav_rail_buttons[name].setChecked(True)
                    for _n, _b in self._nav_rail_buttons.items():
                        if _n != name:
                            _b.setChecked(False)
                self._nav_flyout.open()
        except Exception:
            pass  # flyout not yet built; safe to skip on very early calls

    # ── Scan launch ───────────────────────────────────────────────────────────

    @pyqtSlot()
    def _launch_modules(self):
        try:
            self._launch_modules_impl()
        except Exception as exc:
            self._scan_watchdog.stop()
            self._set_status(f"Scan startup failed: {exc}")
            self._set_scanning(False)
            self._verdict.update(f"Scan failed to start: {exc}", "HIGH")

    @pyqtSlot(str)
    def _on_prescan_error(self, msg: str):
        """Pre-scan failed (G5) — clear the scanning state instead of hanging forever."""
        self._scan_watchdog.stop()
        self._set_scanning(False)
        self._set_status(f"Pre-scan failed: {msg}")
        self._verdict.update(f"Pre-scan failed: {msg}", "UNKNOWN")

    def _known_device_count_hint(self) -> int:
        """Best-known device count from the status bar's last "n/total" message
        (e.g. resolve_batch's "Identifying devices: n/total…", C1/C2) — 0 if unknown."""
        msg = ""
        if hasattr(self, "_status_bar"):
            try:
                msg = self._status_bar.currentMessage()
            except RuntimeError:
                msg = ""  # status bar already destroyed -- fall back to unknown
        m = re.search(r"(\d+)\s*/\s*(\d+)", msg or "")
        return int(m.group(2)) if m else 0

    def _scan_watchdog_budget_ms(self) -> int:
        """Base 120s + a per-device allowance, clamped to a 15-minute ceiling."""
        budget = _WATCHDOG_BASE_MS + self._known_device_count_hint() * _WATCHDOG_PER_DEVICE_MS
        return min(budget, _WATCHDOG_CEILING_MS)

    def _on_scan_watchdog_timeout(self) -> None:
        """
        Guards against a scan leaving the UI stuck on "Scanning…" forever — but
        must never CLAIM a stop that did not happen (G5's original defect, seen
        live on a large corporate network: the watchdog fired and said "took too
        long and was stopped" while Module 1 was still resolving names and
        delivered a complete 715-device result about a minute later).

        If any scan worker is still actually running, extend the deadline and
        report honestly instead of clearing state — up to a hard ceiling, past
        which we do stop waiting (but say a worker may still be running, not
        that the scan "was stopped").
        """
        if not self._is_scanning:
            return  # scan already finished normally; stale timer, ignore

        still_running = any(w.isRunning() for w in getattr(self, "_workers", []))
        elapsed_ms = (time.time() - getattr(self, "_scan_started_at", 0.0)) * 1000

        if still_running and elapsed_ms < _WATCHDOG_CEILING_MS:
            device_count = self._known_device_count_hint()
            note = f" ({device_count} devices found so far)" if device_count else ""
            self._set_status(f"Still scanning — this network is large{note}. This can take several minutes.")
            self._scan_watchdog.start(self._scan_watchdog_budget_ms())
            return

        self._active_count = 0
        self._set_scanning(False)
        if still_running:
            msg = "Scan is taking unusually long and may still be running in the background."
        else:
            msg = "Scan took too long and was stopped."
        self._set_status(msg)
        self._verdict.update(msg, "UNKNOWN")

    def _launch_modules_impl(self):
        from workers.scan_worker import (
            Module1Worker, Module2Worker, Module3Worker,
            Module4Worker, Module5Worker,
        )

        gateway_ip   = self._net_info.get("gateway") if self._net_info else None
        gateway_mac  = self._net_info.get("gateway_mac") if self._net_info else None
        # Pre-populate rogue MACs from the previous scan (best-effort; M1 and M3 run concurrently)
        rogue_macs: list = []
        if self._m1_result:
            for _d in self._m1_result.get("devices", []):
                _risk = _d.risk_level if not isinstance(_d, dict) else _d.get("risk_level", "")
                _mac  = _d.mac        if not isinstance(_d, dict) else _d.get("mac", "")
                if _risk == "HIGH" and _mac:
                    rogue_macs.append(_mac)

        self._verdict.update("Scan in progress…", "UNKNOWN")
        self._workers.clear()
        self._active_count = 0
        # Refresh network info now that caches have been flushed (Fix #14)
        self._refresh_network_info()

        # Module 1 — always runs
        if hasattr(self, "_m1_table"):
            # Clear the previous scan's rows and disable sorting before the
            # live-preview stream starts inserting -- _m1_populate_device_table
            # re-enables sorting once the authoritative rebuild runs (Part 2/L7).
            self._m1_table.setSortingEnabled(False)
            self._m1_table.setRowCount(0)
            self._m1_stream_rows = {}

        # Part 2/L8: fetch the known_device snapshot here (before the worker
        # starts) so rogue_device.scan() can skip re-resolving any MAC whose
        # hostname was actively resolved within the last 7 days. No MetricStore
        # import in modules/rogue_device.py -- this is the one read for it.
        _known_for_cache = self._store.get_known_devices() if getattr(self, "_store", None) else None
        # Part 2/L5: bound the ARP-table pass to the declared scope (computed in
        # ui/tabs_network.py::_update_net_info_ui alongside self._net_env) — None
        # when unbounded (home network, or the user disabled bounding in Settings).
        _scope_cidr = getattr(self, "_scan_scope_cidr", None)
        w1 = Module1Worker(self._offenders_path, known_devices=_known_for_cache, scope_cidr=_scope_cidr)
        w1.result.connect(self._on_m1_result)
        w1.status.connect(lambda m: (
            self._set_status(m), self._m1_status.setText(m),
            hasattr(self, "_home_page") and self._home_page.set_scan_progress(m),
        ))
        w1.error.connect(lambda e: self._m1_status.setText(f"Error: {e}"))
        w1.finished.connect(self._on_worker_done)
        if hasattr(self, "_home_page"):
            w1.device_found.connect(self._home_page.on_device_found)
        if hasattr(self, "_m1_table"):
            w1.device_found.connect(self._m1_stream_device_row)
        self._workers.append(w1)
        self._active_count += 1

        _scan_qs = QSettings("NetSentinel", "NetSentinel")

        # Module 2 — needs admin + Scapy
        if _scan_qs.value("scan/stp_enabled", True, type=bool):
            _stp_dur = _scan_qs.value("scan/stp_duration_s", 10, type=int)
            w2 = Module2Worker(gateway_mac, duration=_stp_dur)
            w2.bpdu_found.connect(self._on_bpdu_found)
            w2.result.connect(self._on_m2_result)
            w2.status.connect(lambda m: (self._set_status(m), self._m2_status.setText(m)))
            w2.error.connect(lambda e: self._m2_status.setText(f"⚠ {e}"))
            w2.finished.connect(self._on_worker_done)
            self._workers.append(w2)
            self._active_count += 1

        # Module 3
        if _scan_qs.value("scan/storm_enabled", True, type=bool):
            _storm_dur = _scan_qs.value("scan/storm_duration_s", 10, type=int)
            w3 = Module3Worker(
                duration=_storm_dur,
                known_rogue_macs=rogue_macs,
            )
            w3.result.connect(self._on_m3_result)
            w3.status.connect(lambda m: (self._set_status(m), self._m3_status.setText(m)))
            w3.error.connect(lambda e: self._m3_status.setText(f"⚠ {e}"))
            w3.finished.connect(self._on_worker_done)
            self._workers.append(w3)
            self._active_count += 1

        # Module 4
        if _scan_qs.value("scan/wifi_enabled", True, type=bool):
            w4 = Module4Worker()
            w4.result.connect(self._on_m4_result)
            w4.status.connect(lambda m: (self._set_status(m), self._m4_status.setText(m)))
            w4.error.connect(lambda e: self._m4_status.setText(f"⚠ {e}"))
            w4.finished.connect(self._on_worker_done)
            self._workers.append(w4)
            self._active_count += 1

        # Module 5
        if _scan_qs.value("scan/dns_enabled", True, type=bool):
            w5 = Module5Worker(gateway_ip=gateway_ip)
            w5.ping_point.connect(self._on_ping_point)
            w5.dns_point.connect(self._on_dns_point)
            w5.result.connect(self._on_m5_result)
            w5.status.connect(lambda m: (self._set_status(m), self._m5_status.setText(m)))
            w5.error.connect(lambda e: self._m5_status.setText(f"⚠ {e}"))
            w5.finished.connect(self._on_worker_done)
            self._workers.append(w5)
            self._active_count += 1
            self._graph_timer.start()

        for w in self._workers:
            w.start()
