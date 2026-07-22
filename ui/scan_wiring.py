"""
scan_wiring.py — ScanResultMixin for Dashboard scan result handlers.

Extracted from ui/dashboard.py (Sprint 4, S1-2).
Dashboard inherits ScanResultMixin to receive these methods.
"""
from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QSettings, QThread, pyqtSignal
from PyQt6.QtWidgets import QTableWidgetItem

from modules.network_segments import upsert_segment
from modules.scan_persistence import persist_alert, upsert_known_device

from ui.tabs import _add_row
from ui.tabs_helpers import format_scan_status, risk_to_label

from ui import styles as _s
from ui.nav.labels import NavLabel as L
from ui.scan_enrichment import ScanEnrichmentMixin

if TYPE_CHECKING:
    from modules.metric_store_schema import KnownDevice


class _VendorBatchWorker(QThread):
    """Background OUI vendor lookup for devices showing 'Unknown' vendor.

    Processes MACs one at a time so the macvendors.com rate limit (≈1 req/s)
    is respected. Emits vendor_resolved(mac, vendor) for each hit so the table
    cell can be updated immediately rather than waiting for all lookups.
    """

    vendor_resolved = pyqtSignal(str, str)  # (normalised_mac, vendor_name)

    def __init__(self, macs: list[str], parent=None, *, allow_online: bool = True) -> None:
        super().__init__(parent)
        self._macs = macs
        self._allow_online = allow_online
        self._stop_event = threading.Event()

    def stop(self) -> None:
        """Cooperative stop — checked between MACs so an in-flight (bounded,
        5s-timeout) HTTP lookup finishes naturally instead of the thread being
        force-terminated mid-syscall."""
        self._stop_event.set()

    def run(self) -> None:
        try:
            from modules.mac_lookup import lookup_vendor
            for mac in self._macs:
                if self._stop_event.is_set():
                    break
                if not mac:
                    continue
                vendor = lookup_vendor(mac, allow_online=self._allow_online)
                if vendor:
                    self.vendor_resolved.emit(mac.lower(), vendor)
        except Exception:
            pass  # non-fatal — table shows 'Unknown' if lookup fails


class ScanResultMixin(ScanEnrichmentMixin):
    """Mixin providing all _on_*_result scan wiring methods for Dashboard."""

    def _on_port_scan_result(self, data):
        from PyQt6.QtGui import QColor
        self._last_portscan_result = data   # cache for Nmap XML export
        self._ps_table.setRowCount(0)
        for p in data.open_ports:
            row = self._ps_table.rowCount()
            self._ps_table.insertRow(row)
            risk_color = _s.RED if p.risk == "HIGH" else _s.TEXT_PRIMARY
            for col, val in enumerate([str(p.port), p.name, p.service_version or "", p.banner or "", p.risk]):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(risk_color if col in (1, 4) else _s.TEXT_PRIMARY))
                self._ps_table.setItem(row, col, item)
        if hasattr(self, "_ps_status"):
            self._ps_status.setText(data.plain_verdict)
        if hasattr(self, "_monitor_overview_page"):
            self._monitor_overview_page.set_open_port_count(len(data.open_ports))
        if hasattr(self, "_security_overview_page"):
            self._security_overview_page.on_port_scan_result(data)
        # ── Update NetworkDocPage with accumulated port data ──────────────────
        try:
            if data.open_ports:
                _host_key = getattr(data, "host", "") or getattr(data, "ip", "")
                if _host_key:
                    self._port_data_cache[_host_key] = [
                        {"port": str(p.port), "protocol": "tcp",
                         "service": p.name or "", "state": "open",
                         "banner": p.banner or p.service_version or ""}
                        for p in data.open_ports
                    ]
            _nd_cert: list = []
            if self._store is not None:
                for _c in self._store.query_cert_status():
                    _nd_cert.append({"host": _c.host, "cn": _c.subject or "",
                                     "issuer": _c.issuer or "", "not_after": _c.not_after or "",
                                     "days_remaining": _c.days_remaining})
            self._network_doc_page.set_scan_data(
                devices=self._last_scan_devices,
                port_data=self._port_data_cache,
                cert_data=_nd_cert,
                topo_widget=getattr(self, "_topology_widget", None),
            )
        except Exception:
            pass  # non-fatal
        if hasattr(self, "_compute_suggestions"):
            self._compute_suggestions()
        # Auto-run risk scorer with M1 device list (_run_risk_scorer() itself
        # no-ops safely if M1 hasn't run yet — self._m1_result may be None)
        if hasattr(self, "_run_risk_scorer"):
            try:
                self._run_risk_scorer()
            except Exception:
                pass  # non-fatal — risk scorer may fail on limited M1 data
        # Update OS tab status with device count
        if hasattr(self, "_update_os_tab_from_m1"):
            try:
                self._update_os_tab_from_m1()
            except Exception:
                pass  # non-fatal
        # Pre-fill OS Detection table with low-confidence inferred guesses
        if hasattr(self, "_prefill_os_from_m1"):
            try:
                self._prefill_os_from_m1()
            except Exception:
                pass  # non-fatal

    def _on_ipv6_result(self, devices: list):
        from PyQt6.QtGui import QColor

        def _norm(m: str) -> str:
            return (m or "").lower().replace("-", "").replace(":", "")

        mac_to_ipv4 = {}
        if self._m1_result:
            for d in self._m1_result.get("devices", []):
                d_mac = (d.mac if not isinstance(d, dict) else d.get("mac", "")) or ""
                d_ip  = (d.ip if not isinstance(d, dict) else d.get("ip", "")) or ""
                if d_mac and d_ip:
                    mac_to_ipv4[_norm(d_mac)] = d_ip

        self._ipv6_table.setRowCount(0)
        for d in devices:
            row = self._ipv6_table.rowCount()
            self._ipv6_table.insertRow(row)
            source_color = _s.ACCENT_LITE if d.get("source") == "active" else _s.TEXT_SECONDARY
            state_color  = _s.GREEN if d.get("state", "").upper() == "REACHABLE" else _s.TEXT_SECONDARY
            ipv4 = mac_to_ipv4.get(_norm(d.get("mac", "")), "—")
            for col, val in enumerate([
                d.get("ip6", ""), d.get("mac", ""), ipv4,
                d.get("state", ""), d.get("source", ""),
            ]):
                item = QTableWidgetItem(str(val))
                if col == 3:
                    item.setForeground(QColor(state_color))
                elif col == 4:
                    item.setForeground(QColor(source_color))
                else:
                    item.setForeground(QColor(_s.TEXT_PRIMARY))
                self._ipv6_table.setItem(row, col, item)
        if not devices:
            self._ipv6_status.setText(
                "No IPv6 devices found — this is normal for most home networks"
            )
        else:
            self._ipv6_status.setText(
                f"{len(devices)} IPv6 device(s) found  "
                f"({sum(1 for d in devices if d.get('source')=='active')} via active sweep, "
                f"{sum(1 for d in devices if d.get('source')=='cache')} from cache)"
            )

    def _on_cloud_local_result(self, result):
        risk_color = {"NONE": _s.GREEN, "INFO": _s.AMBER, "HIGH": _s.RED}.get(result.risk_level, _s.TEXT_SECONDARY)
        risk_icon  = {"NONE": "✔", "INFO": "ℹ", "HIGH": "⚠"}.get(result.risk_level, "?")
        lines = [
            f"<b style='color:{risk_color}'>{risk_icon} [{risk_to_label(result.risk_level)}]  {result.plain_verdict}</b>",
        ]
        if result.provider:
            lines.append(f"<br><b>Provider:</b> {result.provider}")
            if result.instance_id:
                lines.append(f"<b>Instance:</b> {result.instance_id}")
            if result.region:
                lines.append(f"<b>Region:</b> {result.region}")
            if result.account_id:
                lines.append(f"<b>Account:</b> {result.account_id}")
            if result.public_ip:
                lines.append(f"<b>Public IP:</b> {result.public_ip}")
            if result.ami_id:
                lines.append(f"<b>AMI:</b> {result.ami_id}")
            if result.project_id:
                lines.append(f"<b>Project:</b> {result.project_id}")
            if result.imdsv2_enforced is not None:
                v2_color = _s.GREEN if result.imdsv2_enforced else _s.RED
                v2_txt   = "enforced (secure)" if result.imdsv2_enforced else "NOT enforced — HIGH RISK"
                lines.append(f"<b>IMDSv2:</b> <span style='color:{v2_color}'>{v2_txt}</span>")
        for finding in result.findings:
            lines.append(f"<br><span style='color:{_s.AMBER}'>⚠ {finding}</span>")
        self._cloud_local_box.setHtml("<br>".join(lines))
        # RULE-SS1 — an unreachable IMDS legitimately means "not a cloud VM", so
        # this is a genuine clean result rather than not_testable.
        self._nav_set_scan_state(
            L.CLOUD_METADATA_PROBE, "fresh",
            ts=time.time(),
            verdict=result.plain_verdict,
        )

    def _on_cloud_network_result(self, results: list):
        from PyQt6.QtGui import QColor
        self._cloud_network_table.setRowCount(0)
        for r in results:
            row = self._cloud_network_table.rowCount()
            self._cloud_network_table.insertRow(row)
            exposed_color = _s.RED if r.exposed else _s.GREEN
            row_color = _s.RED if r.exposed else _s.TEXT_SECONDARY
            finding_str = r.findings[0][:100] if r.findings else "—"
            for col, val in enumerate([
                r.device_ip, r.device_mac, r.hostname,
                "YES" if r.exposed else "no",
                r.risk_level, finding_str,
            ]):
                item = QTableWidgetItem(str(val))
                if col == 3:
                    item.setForeground(QColor(exposed_color))
                elif col in (4, 5):
                    item.setForeground(QColor(row_color))
                else:
                    item.setForeground(QColor(_s.TEXT_SECONDARY if not r.exposed else _s.RED))
                self._cloud_network_table.setItem(row, col, item)
        _exposed = sum(1 for r in results if r.exposed)
        self._nav_set_scan_state(
            L.CLOUD_METADATA_PROBE, "fresh",
            ts=time.time(),
            verdict=(f"{_exposed} of {len(results)} devices expose cloud metadata"
                     if _exposed else f"No cloud metadata exposure ({len(results)} checked)"),
        )

    def _on_snmp_result(self, result):
        if not result.reachable:
            return
        row = self._snmp_table.rowCount()
        self._snmp_table.insertRow(row)
        for col, val in enumerate([
            result.host, result.sys_name, result.sys_descr[:80],
            result.sys_uptime, result.if_count, result.cpu_load, result.sys_contact,
        ]):
            self._snmp_table.setItem(row, col, QTableWidgetItem(str(val)))

    def _on_snmp_if_result(self, entries: list) -> None:
        """Populate interface error table and bar chart (V4 — Cat2).

        Colours are read live (via ``_s``) so ``refresh_theme`` (which re-invokes
        this with the cached ``_snmp_if_last_entries``) recolours the chart.
        """
        from PyQt6.QtGui import QColor
        self._snmp_if_last_entries = list(entries)   # cached for live theme redraw
        self._snmp_if_table.setRowCount(0)
        for entry in entries:
            row = self._snmp_if_table.rowCount()
            self._snmp_if_table.insertRow(row)
            cells = [
                entry.if_descr,
                str(entry.in_errors),
                str(entry.out_errors),
                str(entry.in_discards),
                str(entry.out_discards),
            ]
            for col, val in enumerate(cells):
                item = QTableWidgetItem(val)
                if col > 0 and int(val) > 0:
                    item.setForeground(QColor(_s.RED if int(val) > 10 else _s.AMBER))
                self._snmp_if_table.setItem(row, col, item)

        # Update chart
        ax = getattr(self, "_snmp_if_ax", None)
        canvas = getattr(self, "_snmp_if_canvas", None)
        if ax is None or canvas is None or not entries:
            return
        ax.clear()
        ax.set_facecolor(_s.CHART_PLOT_BG)
        ax.tick_params(colors=_s.TEXT_SECONDARY, labelsize=8)
        ax.grid(True, color=_s.CHART_GRID, linewidth=0.8, axis="y")
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        for sp in ("bottom", "left"):
            ax.spines[sp].set_color(_s.CHART_SPINE)

        labels  = [e.if_descr[:12] for e in entries]
        in_err  = [e.in_errors   for e in entries]
        out_err = [e.out_errors  for e in entries]
        in_dis  = [e.in_discards for e in entries]
        out_dis = [e.out_discards for e in entries]
        xs = list(range(len(labels)))
        w  = 0.2
        ax.bar([x - 1.5 * w for x in xs], in_err,  w, label="In Errors",    color=_s.RED)
        ax.bar([x - 0.5 * w for x in xs], out_err, w, label="Out Errors",   color=_s.AMBER)
        ax.bar([x + 0.5 * w for x in xs], in_dis,  w, label="In Discards",  color=_s.BLUE)
        ax.bar([x + 1.5 * w for x in xs], out_dis, w, label="Out Discards", color=_s.GREEN)
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, rotation=25, ha="right")
        ax.legend(fontsize=7, framealpha=0.7)
        ax.set_title("Error distribution per interface", fontsize=9, color=_s.TEXT_PRIMARY, pad=4)
        try:
            canvas.draw()
        except Exception:
            pass  # non-fatal if canvas is detached

    def _on_syn_result(self, result):
        from PyQt6.QtGui import QColor
        self._syn_stack.setCurrentIndex(1)   # switch from empty state to table
        self._recon_syn_table.setRowCount(0)
        # Build quick CVE-count lookup by service keyword from MetricStore
        _cve_counts: dict[str, int] = {}
        try:
            if self._store is not None:
                _all_cves = self._store.list_cve_lifecycles() or []
                for _cve in _all_cves:
                    _svc = (_cve.get("service") or "").split()[0].lower()
                    if _svc:
                        _cve_counts[_svc] = _cve_counts.get(_svc, 0) + 1
        except Exception:
            pass  # non-fatal
        for p in result.open_ports:
            row = self._recon_syn_table.rowCount()
            self._recon_syn_table.insertRow(row)
            color = _s.RED if p.state == "open" else _s.AMBER
            _cols = [str(p.port), p.state, p.proto, p.service, p.service_version, p.banner]
            for col, val in enumerate(_cols):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(color))
                self._recon_syn_table.setItem(row, col, item)
            # CVE count badge (col 6)
            svc_key = (p.service or "").split()[0].lower()
            cve_n = _cve_counts.get(svc_key, 0)
            cve_item = QTableWidgetItem(f"{cve_n} CVEs" if cve_n else "—")
            cve_item.setForeground(QColor(_s.AMBER if cve_n else _s.TEXT_MUTED))
            if cve_n:
                cve_item.setToolTip(_s.safe_tooltip(f"Click to view {cve_n} CVE(s) for {p.service}"))
            self._recon_syn_table.setItem(row, 6, cve_item)
        _ts_syn = time.time()
        _syn_verdict = result.plain_verdict if not result.error else f"⚠ {result.error}"
        self._syn_status.setText(format_scan_status(_syn_verdict, _ts_syn))
        if getattr(result, "not_testable", False):
            if hasattr(self, "_port_scan_not_testable_hosts") and result.host:
                self._port_scan_not_testable_hosts.add(result.host)
            self._nav_set_scan_state(
                L.PORT_SCAN_TCP, "not_testable", ts=_ts_syn, error=result.not_testable_reason,
            )
        else:
            self._nav_set_scan_state(L.PORT_SCAN_TCP, "fresh", ts=_ts_syn, verdict=_syn_verdict)
        if hasattr(self, "_security_overview_page"):
            self._security_overview_page.on_port_scan_result(result)
        # ── Update NetworkDocPage with accumulated port data ──────────────────
        try:
            if result.open_ports:
                _host_key = getattr(result, "host", "") or getattr(result, "ip", "")
                if _host_key:
                    self._port_data_cache[_host_key] = [
                        {"port": str(p.port), "protocol": p.proto or "tcp",
                         "service": p.service or "", "state": p.state or "open",
                         "banner": p.banner or ""}
                        for p in result.open_ports
                    ]
            _nd_cert: list = []
            if self._store is not None:
                for _c in self._store.query_cert_status():
                    _nd_cert.append({"host": _c.host, "cn": _c.subject or "",
                                     "issuer": _c.issuer or "", "not_after": _c.not_after or "",
                                     "days_remaining": _c.days_remaining})
            self._network_doc_page.set_scan_data(
                devices=self._last_scan_devices,
                port_data=self._port_data_cache,
                cert_data=_nd_cert,
                topo_widget=getattr(self, "_topology_widget", None),
            )
        except Exception:
            pass  # non-fatal
        # Auto-refresh Device Risk Score with this scan's findings (F-47).
        # _run_risk_scorer() itself no-ops safely if M1 hasn't run yet.
        if hasattr(self, "_run_risk_scorer"):
            try:
                self._run_risk_scorer()
            except Exception:
                pass  # non-fatal — risk scorer may fail on limited M1 data
        if getattr(self, "_pending_security_tools", []):
            self._advance_security_audit()

    def _on_udp_result(self, result):
        from PyQt6.QtGui import QColor
        self._udp_stack.setCurrentIndex(1)
        self._recon_udp_table.setRowCount(0)
        for p in result.open_ports:
            row = self._recon_udp_table.rowCount()
            self._recon_udp_table.insertRow(row)
            color = _s.AMBER if p.state == "open|filtered" else _s.GREEN
            for col, val in enumerate([str(p.port), p.state, p.service]):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(color))
                self._recon_udp_table.setItem(row, col, item)
        _ts_udp = time.time()
        _udp_verdict = result.plain_verdict if not result.error else f"⚠ {result.error}"
        self._udp_status.setText(format_scan_status(_udp_verdict, _ts_udp))
        if getattr(result, "not_testable", False):
            if hasattr(self, "_port_scan_not_testable_hosts") and result.host:
                self._port_scan_not_testable_hosts.add(result.host)
            self._nav_set_scan_state(
                L.PORT_SCAN_UDP, "not_testable", ts=_ts_udp, error=result.not_testable_reason,
            )
        else:
            self._nav_set_scan_state(L.PORT_SCAN_UDP, "fresh", ts=_ts_udp, verdict=_udp_verdict)
        if hasattr(self, "_security_overview_page"):
            self._security_overview_page.on_port_scan_result(result)

    def _on_os_result(self, data: dict):
        self._os_stack.setCurrentIndex(1)
        guesses = data.get("guesses", [])
        for guess in guesses:
            row = self._recon_os_table.rowCount()
            self._recon_os_table.insertRow(row)
            for col, val in enumerate([
                getattr(guess, "ip", ""),
                str(getattr(guess, "ttl", "")),
                getattr(guess, "os_family", ""),
                getattr(guess, "confidence", ""),
                getattr(guess, "tcp_window", ""),
                getattr(guess, "banner_hint", ""),
            ]):
                self._recon_os_table.setItem(row, col, QTableWidgetItem(str(val)))
        if hasattr(self, "_os_detect_not_testable_hosts"):
            for guess in guesses:
                if getattr(guess, "not_testable", False) and getattr(guess, "ip", ""):
                    self._os_detect_not_testable_hosts.add(guess.ip)
        _ts_os = time.time()
        _os_verdict = f"Fingerprinted {len(guesses)} host(s)."
        self._os_status.setText(format_scan_status(_os_verdict, _ts_os))
        _os_not_testable = bool(guesses) and all(getattr(g, "not_testable", False) for g in guesses)
        if _os_not_testable:
            _os_reason = next(
                (g.not_testable_reason for g in guesses if getattr(g, "not_testable_reason", "")), ""
            )
            self._nav_set_scan_state(L.OS_DETECTION, "not_testable", ts=_ts_os, error=_os_reason)
        else:
            self._nav_set_scan_state(L.OS_DETECTION, "fresh", ts=_ts_os, verdict=_os_verdict)

    def _on_cve_result(self, service_version: str, result):
        from PyQt6.QtGui import QColor
        self._cve_stack.setCurrentIndex(1)
        for cve in result.cves:
            row = self._recon_cve_table.rowCount()
            self._recon_cve_table.insertRow(row)
            sev = (cve.severity or "NONE").upper()
            color = (_s.RED if sev in ("CRITICAL", "HIGH") else
                     _s.AMBER if sev == "MEDIUM" else
                     _s.BLUE if sev == "LOW" else _s.TEXT_SECONDARY)
            for col, val in enumerate([
                cve.cve_id, service_version,
                f"{cve.cvss_score:.1f}", sev,
                cve.published, cve.description,
            ]):
                item = QTableWidgetItem(str(val))
                item.setForeground(QColor(color if col in (2, 3) else _s.TEXT_PRIMARY))
                self._recon_cve_table.setItem(row, col, item)
        if hasattr(self, "_cve_batch_results"):
            self._cve_batch_results.append(result)
        if hasattr(self, "_monitor_overview_page"):
            self._monitor_overview_page.set_cve_count(self._recon_cve_table.rowCount())
        _cve_n = self._recon_cve_table.rowCount()
        _cve_verdict = f"{_cve_n} CVE{'s' if _cve_n != 1 else ''} found" if _cve_n else "No CVEs found"
        self._nav_set_scan_state(L.CVE_LOOKUP, "fresh", ts=time.time(), verdict=_cve_verdict)

    def _on_exposure_result(self, result):
        from PyQt6.QtGui import QColor
        self._exposure_verdict.setText(result.plain_verdict)
        _s.themed_ss(self._exposure_verdict, lambda risk=result.risk: (
            f"color:{_s.RED if risk == 'HIGH' else _s.AMBER if risk == 'MEDIUM' else _s.GREEN};"
            f"font-size:12px;font-weight:bold;padding:6px;"
            f"background:{_s.RED_BG if risk == 'HIGH' else _s.AMBER_BG};border-radius:4px;"
        ))
        self._exposure_verdict.show()
        self._recon_exposure_table.setRowCount(0)
        for m in result.upnp_mappings:
            row = self._recon_exposure_table.rowCount()
            self._recon_exposure_table.insertRow(row)
            row_color = _s.RED if m.enabled else _s.TEXT_SECONDARY
            for col, val in enumerate([
                m.internal_ip, str(m.external_port), str(m.internal_port),
                m.protocol, m.description, "Yes" if m.enabled else "No",
            ]):
                item = QTableWidgetItem(str(val))
                item.setForeground(QColor(row_color))
                self._recon_exposure_table.setItem(row, col, item)
        _ts_exp = time.time()
        _exp_verdict = (
            f"WAN IP: {result.wan_ip or 'unknown'} | "
            f"CGNAT: {'Yes' if result.cgnat else 'No'} | "
            f"UPnP mappings: {len(result.upnp_mappings)}"
        )
        self._exposure_status.setText(format_scan_status(_exp_verdict, _ts_exp))
        if getattr(result, "not_testable", False):
            self._nav_set_scan_state(
                L.EXPOSED_TO_INTERNET, "not_testable", ts=_ts_exp, error=result.not_testable_reason,
            )
        else:
            self._nav_set_scan_state(L.EXPOSED_TO_INTERNET, "fresh", ts=_ts_exp, verdict=_exp_verdict)
        if getattr(self, "_pending_security_tools", []):
            self._advance_security_audit()

    def _start_vendor_lookups(self, devices: list) -> None:
        """Kick off background OUI vendor lookup for devices still showing Unknown vendor.

        Results arrive via _on_vendor_resolved() and update the table and DeviceInfo
        in-place, so vendor data fills in asynchronously on the first scan instead of
        requiring a second scan for the lookup cache to warm up.
        """
        from modules.device_classifier import is_randomized_mac
        pending = []
        for d in devices:
            mac    = (d.mac    if not isinstance(d, dict) else d.get("mac",    "")) or ""
            vendor = (d.vendor if not isinstance(d, dict) else d.get("vendor", "")) or ""
            if vendor not in ("Unknown", "") or not mac:
                continue
            if is_randomized_mac(mac):
                continue  # privacy MAC — OUI lookup meaningless by design
            pending.append(mac)

        if not pending:
            return

        # Cancel any still-running lookup from a previous scan. stop() is
        # cooperative (checked between MACs) rather than terminate() — the
        # in-flight lookup has its own bounded HTTP timeout, so it exits on
        # its own shortly instead of being force-killed mid-syscall.
        existing = getattr(self, "_vendor_batch_worker", None)
        if existing and existing.isRunning():
            existing.vendor_resolved.disconnect()
            existing.stop()
            existing.wait(200)

        allow_online = QSettings("NetSentinel", "NetSentinel").value(
            "privacy/mac_vendor_online_lookup", True, type=bool
        )
        worker = _VendorBatchWorker(pending, self, allow_online=allow_online)
        worker.vendor_resolved.connect(self._on_vendor_resolved)
        self._vendor_batch_worker = worker
        worker.start()

    def _on_vendor_resolved(self, mac: str, vendor: str) -> None:
        """Update table cell and DeviceInfo when an async OUI lookup returns a result."""
        if not self._m1_result or not vendor:
            return
        norm = mac.lower().replace("-", "").replace(":", "")

        def _norm(m: str) -> str:
            return m.lower().replace("-", "").replace(":", "")

        # Update DeviceInfo objects in memory
        for d in self._m1_result.get("devices", []):
            d_mac = (d.mac if not isinstance(d, dict) else d.get("mac", "")) or ""
            if _norm(d_mac) == norm:
                if isinstance(d, dict):
                    d["vendor"] = vendor
                else:
                    d.vendor = vendor

        # Persist the resolved vendor to MetricStore so it survives restart.
        # Without this, the async OUI lookup result is lost on every app restart
        # and the Inventory page shows 'Unknown' vendor for all devices.
        _store = getattr(self, "_store", None)
        if _store is not None:
            try:
                upsert_known_device(_store, mac.lower(), vendor=vendor)
            except Exception:
                pass  # non-fatal — best-effort persistence

        # Update Inventory page _snap_table so the resolved vendor shows immediately
        # without requiring a restart or rescan.
        if hasattr(self, "_inventory_page"):
            try:
                self._inventory_page.update_device_vendor(mac, vendor)
            except Exception:
                pass  # non-fatal — table update is best-effort

        # Update the vendor cell (col 3) in _m1_table
        try:
            from PyQt6.QtGui import QColor as _QC
            for row in range(self._m1_table.rowCount()):
                mac_item = self._m1_table.item(row, 2)
                if not mac_item:
                    continue
                if _norm(mac_item.text()) == norm:
                    v_item = self._m1_table.item(row, 3)
                    if v_item and v_item.text() in ("Unknown", ""):
                        v_item.setText(vendor)
                        v_item.setForeground(_QC(_s.TEXT_PRIMARY))
                        v_item.setToolTip(_s.safe_tooltip(f"Vendor resolved from OUI database\n({mac_item.text()[:8].upper()})"))
                    break
        except Exception:
            pass  # non-fatal — table update is best-effort

    def _m1_stream_device_row(self, info: dict) -> None:
        """Live-preview upsert into the Devices table while Module 1 is still
        scanning (Part 2/L7) — the moment an ARP entry is known it appears
        here; as its hostname resolves the same row updates in place instead
        of a second one being appended. Purely a preview: _m1_populate_device_table()
        wipes and rebuilds this table authoritatively the instant the scan
        completes (_on_m1_result), so nothing streamed here needs to be exact.
        """
        ip = info.get("ip", "")
        if not ip:
            return
        rows = getattr(self, "_m1_stream_rows", None)
        if rows is None:
            rows = self._m1_stream_rows = {}
        level = (info.get("risk_level") or "UNKNOWN").upper()
        values = [
            ip, info.get("name") or "—", info.get("mac", ""),
            info.get("vendor") or "Unknown", level,
            info.get("type") or "—", "", "", info.get("verdict") or "Scanning…",
        ]
        row = rows.get(ip)
        _add_row(self._m1_table, values, level, row=row)
        if row is None:
            rows[ip] = self._m1_table.rowCount() - 1

    def _on_m1_result(self, data: dict):
        # Phase B2 (F4): one known_device snapshot shared across every step below
        # that would otherwise re-materialize the full table (was 5 SELECTs per
        # scan cycle: _merge_scan_with_persistent, _m1_populate_device_table's
        # _known_before, and 3 inside DeviceTracker.process_scan). Safe because
        # this whole handler runs synchronously on the GUI thread (no
        # processEvents() calls anywhere in the chain) — the only writers that
        # could race it are other GUI-thread slots, which can't preempt a
        # running slot, or the availability worker's background QThread, which
        # never inserts/updates known_device rows this snapshot would need to
        # see (it only writes device_state/rtt_sample and device_events). The
        # display-merging and audit-diff uses below tolerate that residual
        # staleness the same way the pre-B2 back-to-back independent reads did.
        _store_ref = getattr(self, "_store", None)
        _known_snapshot = _store_ref.get_known_devices() if _store_ref else {}
        self._m1_update_scan_registries(data)
        self._m1_refresh_segments_and_inventory(data, known=_known_snapshot)
        self._m1_populate_device_table(data, known=_known_snapshot)
        self._m1_check_baseline_diff(data)
        self._m1_feed_network_doc(data)
        self._m1_track_devices(data, known=_known_snapshot)
        self._m1_feed_geo_map(data)
        self._m1_restart_availability_worker(data)
        self._m1_update_verdict_and_kpis(data)
        self._m1_refresh_topology(data)
        self._m1_reapply_search_and_suggestions()
        self._m1_auto_snapshot_baseline(data)
        self._m1_run_post_scan_followups(data)

    def _m1_update_scan_registries(self, data: dict) -> None:
        """Stamp scan state + notify overview/security/monitor/home pages of the M1 result."""
        self._last_scan_time = time.time()
        self._nav_set_scan_state(L.DEVICES, "fresh", ts=self._last_scan_time)
        self._m1_result = data
        devices = data.get("devices", [])
        if hasattr(self, "_overview_page") and devices:
            self._overview_page.set_has_results(True)
        if hasattr(self, "_security_overview_page"):
            self._security_overview_page.notify_scan_complete()
            self._security_overview_page.on_scan_result(data)
        if hasattr(self, "_monitor_overview_page"):
            import datetime as _dt
            self._monitor_overview_page.set_last_scan_time(_dt.datetime.now())
        if hasattr(self, "_home_page") and devices:
            self._home_page._device_count = max(self._home_page._device_count, len(devices))

    def _m1_refresh_segments_and_inventory(
        self, data: dict, known: dict[str, "KnownDevice"] | None = None
    ) -> None:
        """Auto-detect network segments and merge live devices into the Inventory page."""
        devices = data.get("devices", [])
        if hasattr(self, "_inventory_page"):
            # Auto-detect segments before populating the snapshot table
            _inv_store = getattr(self, "_store", None)
            try:
                from modules.network_segments import (
                    auto_detect_segments, merge_segments,
                )
                _gw = ""
                _net_info = getattr(self, "_last_net_info", {}) or {}
                _gw = _net_info.get("gateway", "") or ""
                _detected = auto_detect_segments(devices, _gw)
                _stored: list = []
                if _inv_store:
                    try:
                        _stored = _inv_store.get_segments()
                    except Exception:
                        pass  # non-fatal — table may not exist on first run
                _merged = merge_segments(_detected, _stored)
                # Upsert new auto-created entries only
                for _seg in _merged:
                    if _seg.id == 0 and _inv_store:
                        try:
                            _new_id = upsert_segment(_inv_store, _seg)
                            _seg.id = _new_id
                        except Exception:
                            pass  # non-fatal — proceed without DB id
                self._inventory_page.set_segments(_merged)
                self._last_segments = _merged
            except Exception:
                pass  # non-fatal — segment detection is best-effort
            # Merge live devices with pinned/static-candidate offline devices
            self._inventory_page.set_scan_devices(
                self._merge_scan_with_persistent(devices, known=known)
            )

    def _m1_populate_device_table(
        self, data: dict, known: dict[str, "KnownDevice"] | None = None
    ) -> None:
        """Populate the M1 devices table (+ device-change audit + tooltips); mirror into Network Info."""
        devices = data.get("devices", [])
        # Disable sorting while inserting rows: with setSortingEnabled(True) and an
        # active sort indicator (set by a prior sortByColumn call), each setItem()
        # immediately re-sorts the row to its sorted position. The static `row`
        # variable in _add_row then writes subsequent columns into the wrong row,
        # producing blank cells everywhere. Re-enable after all rows are inserted;
        # the sortByColumn() call below will apply the persisted sort order cleanly.
        self._m1_table.setSortingEnabled(False)
        self._m1_table.setRowCount(0)
        _store_ref = getattr(self, "_store", None)
        # Snapshot known devices before the loop so we can detect IP/hostname changes.
        # Reuses the caller's pre-fetched snapshot (Phase B2 / F4) when supplied instead
        # of re-querying — see the comment in _on_m1_result for the staleness rationale.
        _known_before: dict = known if known is not None else (
            _store_ref.get_known_devices() if _store_ref else {}
        )
        for d in devices:
            level   = d.risk_level if not isinstance(d, dict) else d.get("risk_level", "UNKNOWN")
            ip      = d.ip       if not isinstance(d, dict) else d.get("ip", "?")
            host    = d.hostname if not isinstance(d, dict) else d.get("hostname", "")
            mac     = d.mac      if not isinstance(d, dict) else d.get("mac", "?")
            if _store_ref and mac and mac not in ("?", "00:00:00:00:00:00") and ip and ip != "?":
                # record_ip_observation() is NOT called here — DeviceTracker.process_scan()
                # (below, same handler) is the single write path for device_ip_history to
                # avoid double-incrementing seen_count per scan (Phase 3a fix).
                # ── Device change audit events ────────────────────────────────
                _old_kd = _known_before.get(mac.lower())
                if _old_kd:
                    try:
                        from modules.device_tracker import record_event as _rec_ev
                        if _old_kd.ip and ip and ip != _old_kd.ip:
                            _rec_ev(mac, "ip_changed", _old_kd.ip, ip, "scan", _store_ref)
                        _old_hn = _old_kd.hostname or ""
                        _new_hn = host or ""
                        if _old_hn and _new_hn and _new_hn != _old_hn:
                            _rec_ev(mac, "hostname_changed", _old_hn, _new_hn, "scan", _store_ref)
                    except Exception:
                        pass  # non-fatal — audit trail is best-effort
            vendor  = d.vendor   if not isinstance(d, dict) else d.get("vendor", "Unknown")
            model   = d.model    if not isinstance(d, dict) else d.get("model", "")
            vendor_d = f"{vendor} — {model}" if model else vendor
            dtype   = d.device_type if not isinstance(d, dict) else d.get("device_type", "")
            # Fall back to connection_type when device_type is blank
            if not dtype:
                dtype = d.connection_type if not isinstance(d, dict) else d.get("connection_type", "Unknown Device")
            verdict = d.verdict  if not isinstance(d, dict) else d.get("verdict", "")
            _add_row(self._m1_table, [ip, host or "—", mac, vendor_d, level, dtype, "", "", verdict], level)
            # Vendor tooltip — explain why vendor may be unknown
            _row_idx = self._m1_table.rowCount() - 1
            _v_item = self._m1_table.item(_row_idx, 3)
            if _v_item:
                try:
                    _mac_str = mac or ""
                    _first_octet = int(_mac_str.replace(":", "").replace("-", "")[:2], 16) if len(_mac_str) >= 2 else 0
                    _is_rand = bool(_first_octet & 0x02)
                except (ValueError, IndexError):
                    _is_rand = False
                if _is_rand:
                    _v_item.setToolTip(_s.safe_tooltip(
                        "MAC address uses privacy randomization\n"
                        "(iOS/Android feature) — vendor lookup not\n"
                        "possible by design. This is normal."
                    ))
                elif vendor in ("Unknown", ""):
                    _v_item.setToolTip(_s.safe_tooltip(
                        "OUI prefix not found in device database.\n"
                        "The device may be uncommon or use a\n"
                        "recently issued MAC range."
                    ))
                else:
                    _v_item.setToolTip(_s.safe_tooltip(f"Identified from OUI/device database\n({mac[:8].upper()})"))
            # Device type tooltip when inferred from hostname/ports
            _dt_item = self._m1_table.item(_row_idx, 5)
            if _dt_item and dtype == "Unknown Device":
                _dt_item.setToolTip(_s.safe_tooltip(
                    "Device type could not be determined.\n"
                    "Run a full port scan (Security Audit →\n"
                    "Port Scan) to improve classification."
                ))

        self._m1_table.setSortingEnabled(True)
        # Re-apply search/chip filter and restore persisted sort (FILTER-1 / FILTER-2)
        self._m1_apply_filter()
        _qs = QSettings("NetSentinel", "NetSentinel")
        _sc = _qs.value("home/m1_sort_col", -1, type=int)
        _so = _qs.value("home/m1_sort_order", 0, type=int)
        if _sc >= 0:
            self._m1_table.sortByColumn(_sc, Qt.SortOrder(_so))

        self._m1_scan_summary = (
            f"✓  {data.get('total_count', 0)} devices scanned — "
            f"{data.get('high_risk_count', 0)} HIGH RISK"
        )
        self._m1_status.setText(self._m1_scan_summary)
        # Mirror into Network Info tab
        self._net_devices_table.setRowCount(0)
        for d in data.get("devices", []):
            level   = d.risk_level if not isinstance(d, dict) else d.get("risk_level", "UNKNOWN")
            ip      = d.ip       if not isinstance(d, dict) else d.get("ip", "?")
            host    = d.hostname if not isinstance(d, dict) else d.get("hostname", "")
            mac     = d.mac      if not isinstance(d, dict) else d.get("mac", "?")
            vendor  = d.vendor   if not isinstance(d, dict) else d.get("vendor", "Unknown")
            _add_row(self._net_devices_table, [ip, host or "—", mac, vendor, level], level)


    def _m1_check_baseline_diff(self, data: dict) -> None:
        """Diff scanned devices against the saved device baseline and update the banner."""
        # ── Baseline diff ────────────────────────────────────────────────────
        try:
            from modules.utils import load_device_baseline, save_device_baseline, diff_devices_against_baseline
            # Convert device objects to plain dicts for the util function
            dev_dicts = []
            for d in data.get("devices", []):
                dev_dicts.append({
                    "mac":      (d.mac      if not isinstance(d, dict) else d.get("mac", "")),
                    "ip":       (d.ip       if not isinstance(d, dict) else d.get("ip", "")),
                    "hostname": (d.hostname if not isinstance(d, dict) else d.get("hostname", "")),
                    "vendor":   (d.vendor   if not isinstance(d, dict) else d.get("vendor", "")),
                })
            baseline = load_device_baseline()
            new_devs = diff_devices_against_baseline(dev_dicts, baseline)
            save_device_baseline(baseline)
            self._bl_table.setRowCount(0)
            if new_devs:
                self._bl_new_lbl.setText(f"⚠  {len(new_devs)} new device(s) detected since last scan!")
                _s.themed_ss(self._bl_new_lbl, "color:{AMBER}; font-size:11px;")
                for nd in new_devs:
                    first = baseline.get((nd.get("mac") or "").lower(), {}).get("first_seen", "—")
                    _add_row(self._bl_table,
                             [nd.get("ip","?"), nd.get("hostname","") or "—",
                              nd.get("mac","?"), nd.get("vendor","Unknown"), first],
                             "MEDIUM")
            else:
                self._bl_new_lbl.setText("✓  No new devices since last scan.")
                _s.themed_ss(self._bl_new_lbl, "color:{GREEN}; font-size:11px;")
        except Exception as _exc:
            self._bl_new_lbl.setText(f"Baseline check failed: {_exc}")

    def _m1_feed_network_doc(self, data: dict) -> None:
        """Feed the latest scan devices + cert status into the Network Doc page."""
        # ── Feed Network Doc page ─────────────────────────────────────────────
        self._last_scan_devices = data.get("devices", [])
        _cert_data: list = []
        if self._store is not None:
            try:
                for _c in self._store.query_cert_status():
                    _cert_data.append({
                        "host": _c.host,
                        "cn":   _c.subject or "",
                        "issuer":        _c.issuer or "",
                        "not_after":     _c.not_after or "",
                        "days_remaining": _c.days_remaining,
                    })
            except Exception:
                pass  # non-fatal
        self._network_doc_page.set_scan_data(
            devices=self._last_scan_devices,
            port_data=self._port_data_cache,
            cert_data=_cert_data,
            topo_widget=getattr(self, "_topology_widget", None),
        )

    def _m1_track_devices(
        self, data: dict, known: dict[str, "KnownDevice"] | None = None
    ) -> None:
        """Persist scan results via DeviceTracker; raise join/leave notices, alerts, and MQTT events."""
        # ── Persistent device tracking (MetricStore) ──────────────────────────
        if self._store is not None:
            try:
                from modules.device_tracker import DeviceTracker
                if not hasattr(self, "_device_tracker"):
                    self._device_tracker = DeviceTracker(self._store)
                tr = self._device_tracker.process_scan(data.get("devices", []), known=known)
                self._last_scan_new  = len(tr.new_devices)
                self._last_scan_gone = len(tr.gone_devices)
                self._last_new_ips: set = {d.ip for d in tr.new_devices if d.ip}
                if tr.new_devices:
                    if hasattr(self, "_live_bandwidth_page"):
                        self._live_bandwidth_page.annotate_event("Device joined", _s.GREEN)
                    msgs = [f"{d.ip or d.mac} ({d.vendor or 'Unknown'})"
                            for d in tr.new_devices[:3]]
                    extra = f" +{len(tr.new_devices)-3} more" if len(tr.new_devices) > 3 else ""
                    status_msg = f"🆕 {len(tr.new_devices)} new device(s): {', '.join(msgs)}{extra}"
                    self._set_status(status_msg)
                    # Tray notification — only if user opted in
                    from PyQt6.QtCore import QSettings as _QS
                    if (
                        self._tray_manager.is_available()
                        and _QS("NetSentinel", "NetSentinel").value(
                            "tray/notify_new_device", False, type=bool
                        )
                    ):
                        summary = ", ".join(
                            f"{d.ip or d.mac}" for d in tr.new_devices[:2]
                        )
                        if len(tr.new_devices) > 2:
                            summary += f" +{len(tr.new_devices)-2} more"
                        self._tray_manager.show_notification(
                            "New Device Joined",
                            summary,
                            "WARNING",
                        )
                        self._tray_manager.increment_badge()
                    # ── Naming suggestion toast (S5-1) — only the first new device,
                    # to avoid spamming a toast per device on a busy scan.
                    try:
                        from modules.device_naming import suggest_device_name
                        first = tr.new_devices[0]
                        suggested = suggest_device_name(
                            first.hostname, first.vendor, first.device_type
                        )
                        if suggested != "Unnamed Device":
                            from ui.widgets.toast import ToastManager
                            _mac = first.mac

                            def _name_it(_checked=False, _mac=_mac, _name=suggested):
                                self._nav_rail_go_to(L.INVENTORY_CHANGES)
                                if hasattr(self, "_inventory_page"):
                                    self._inventory_page.open_device_drawer(_mac, _name)

                            ToastManager.show(
                                f"New device: {suggested} ({first.ip or first.mac}) — name it?",
                                "action",
                                action_label="Name it",
                                action_callback=_name_it,
                            )
                    except Exception:
                        pass  # non-fatal — naming suggestion must never break the scan handler
                if tr.gone_devices:
                    gone_msgs = [f"{d.ip or d.mac}" for d in tr.gone_devices[:2]]
                    self._set_status(
                        f"⚠  {len(tr.gone_devices)} device(s) gone: {', '.join(gone_msgs)}"
                    )
                # Feed tracker result into alert engine + MQTT
                if self._alert_engine is not None:
                    for a in self._alert_engine.evaluate_tracker_result(tr):
                        self._show_alert_toast(a)
                        self._home_page.on_alert(a)
                        self._mqtt_page.on_alert(a.severity, a.message, a.host)
                        try:
                            persist_alert(self._store, a)
                        except Exception:
                            pass  # non-fatal — persistence failure must not block the scan handler
                    # V6 Sprint 1 — IP_CHURN: device_ip_history churn since last scan
                    try:
                        churn = self._store.query_ip_churn(hours=24.0, min_ips=3)
                    except Exception:
                        churn = {}
                    for a in self._alert_engine.evaluate_ip_churn_checks(churn):
                        self._show_alert_toast(a)
                        self._home_page.on_alert(a)
                        try:
                            persist_alert(self._store, a)
                        except Exception:
                            pass  # non-fatal — persistence failure must not block the scan handler
                # Forward device events to MQTT publisher
                for _d in tr.new_devices:
                    self._mqtt_page.on_device_event("joined", {
                        "mac": _d.mac or "", "ip": _d.ip or "",
                        "hostname": _d.hostname or "", "vendor": _d.vendor or "",
                    })
                for _d in tr.gone_devices:
                    self._mqtt_page.on_device_event("left", {
                        "mac": _d.mac or "", "ip": _d.ip or "",
                        "hostname": _d.hostname or "", "vendor": _d.vendor or "",
                    })
            except Exception:
                pass   # tracker errors must never break the scan result handler

    def _m1_feed_geo_map(self, data: dict) -> None:
        """Feed discovered device IPs to the Geolocation Map (public IPs auto-filtered)."""
        # ── Feed Geolocation Map with discovered device IPs (public ones auto-filtered) ─
        try:
            _ips = [
                (d.ip if not isinstance(d, dict) else d.get("ip", ""))
                for d in data.get("devices", [])
            ]
            self._geo_map_page.add_ips([ip for ip in _ips if ip])
        except Exception:
            pass  # non-fatal

    def _m1_restart_availability_worker(self, data: dict) -> None:
        """Start or retarget the AvailabilityWorker after each scan."""
        # ── Start / refresh AvailabilityWorker after each scan ────────────────
        try:
            if self._store is not None and data.get("devices"):
                from workers.availability_worker import AvailabilityWorker
                from modules.availability_monitor import TargetConfig
                _targets = []
                for _d in data.get("devices", []):
                    _ip  = _d.ip       if not isinstance(_d, dict) else _d.get("ip", "")
                    _mac = _d.mac      if not isinstance(_d, dict) else _d.get("mac", "")
                    _hn  = _d.hostname if not isinstance(_d, dict) else _d.get("hostname", "")
                    if _ip:
                        _targets.append(TargetConfig(
                            host=_ip, mac=_mac or None,
                            hostname=_hn or None, label=_hn or _ip,
                        ))
                if _targets:
                    if hasattr(self, "_avail_worker") and self._avail_worker.isRunning():
                        self._avail_worker.set_targets(_targets)
                    else:
                        self._avail_worker = AvailabilityWorker(
                            store=self._store, targets=_targets, interval_s=60,
                        )
                        self._avail_worker.cycle_done.connect(self._on_avail_cycle_done)
                        self._avail_worker.start()
        except Exception:
            pass  # non-fatal

    def _m1_update_verdict_and_kpis(self, data: dict) -> None:
        """Refresh the overall verdict banner + KPI tiles, and reveal the M1 table."""
        self._update_overall_verdict()
        self._update_kpi_tiles(data)
        # Show the table (hide the empty-state placeholder)
        self._m1_stack.setCurrentIndex(1)
        # Show benchmark content pane (user can now grade without being sent elsewhere)
        if hasattr(self, "_bm_stack"):
            self._bm_stack.setCurrentIndex(1)

    def _m1_refresh_topology(self, data: dict) -> None:
        """Rebuild edge health overlays, compute the topology diff, and re-render the map."""
        # Refresh topology widget with new device list + segment colours + health
        try:
            gw_ip  = self._net_info.get("gateway") if self._net_info else None
            gw_mac = self._net_info.get("gateway_mac") if self._net_info else None
            _topo_segs = getattr(self, "_last_segments", None)

            # Sprint 3 — build edge health overlays from MetricStore
            _topo_edges: list = []
            _topo_down_ips: set = set()
            _topo_new_ips: set = getattr(self, "_last_new_ips", set())
            try:
                if self._store is not None and gw_ip:
                    from modules.topology_layout import TopologyEdge as _TE
                    for _d in data.get("devices", []):
                        _ip = _d.ip if not isinstance(_d, dict) else _d.get("ip", "")
                        if not _ip or _ip == gw_ip or _ip in ("?", "0.0.0.0"):
                            continue
                        _state_hist = self._store.query_device_state_history(_ip, hours=2.0)
                        _latest = _state_hist[-1] if _state_hist else None
                        _status = "unknown"
                        _latency: float | None = None
                        _loss: float | None = None
                        if _latest:
                            _s = _latest.state
                            _status = (
                                "down"     if _s == "DOWN"     else
                                "degraded" if _s == "DEGRADED" else
                                "up"
                            )
                            _latency = _latest.rtt_ms
                            if _status == "down":
                                _topo_down_ips.add(_ip)
                        if _latency is None:
                            _rtt_hist = self._store.query_rtt_history(_ip, hours=2.0)
                            if _rtt_hist:
                                _last_rtt = _rtt_hist[-1]
                                _latency = _last_rtt.rtt_ms
                                _loss = _last_rtt.loss_pct / 100.0
                                if _status == "unknown":
                                    _status = (
                                        "degraded" if (_latency > 100 or _loss > 0.2)
                                        else "up"
                                    )
                        _topo_edges.append(_TE(
                            src_ip=gw_ip,
                            dst_ip=_ip,
                            latency_ms=_latency,
                            packet_loss=_loss,
                            bandwidth_mbps=None,
                            status=_status,
                        ))
            except Exception:
                pass  # non-fatal — health overlays degrade gracefully

            # Sprint 4 — topology change detection: load previous snapshot,
            # compute diff before render, save current snapshot after.
            _topo_diff = None
            _topo_curr_snap = None
            try:
                if self._store is not None:
                    from modules.topology_snapshot import (
                        build_snapshot as _build_topo_snap,
                        diff_snapshots as _diff_topo,
                        load_last_snapshot as _load_topo_snap,
                        save_snapshot as _save_topo_snap,
                    )
                    _topo_curr_snap = _build_topo_snap(
                        data.get("devices", []), gw_ip
                    )
                    _topo_prev_snap = _load_topo_snap(self._store)
                    if _topo_prev_snap is not None:
                        _computed = _diff_topo(_topo_curr_snap, _topo_prev_snap)
                        self._topo_diff = _computed
                        if getattr(self, "_topo_diff_mode", False):
                            _topo_diff = _computed
                    else:
                        self._topo_diff = None
            except Exception:
                pass  # non-fatal — diff overlay is best-effort

            self._network_map_page.render(
                data.get("devices", []), gw_ip, gw_mac,
                mesh_units=getattr(self, "_mesh_units", None),
                mesh_enrichment=getattr(self, "_mesh_enrichment", None),
                modem_data=getattr(self, "_last_modem_data", None),
                segments=_topo_segs,
                edges=_topo_edges or None,
                down_ips=_topo_down_ips or None,
                new_ips=_topo_new_ips or None,
                diff=_topo_diff,
            )

            # Persist current snapshot (after render so DB write doesn't block)
            try:
                if _topo_curr_snap is not None and self._store is not None:
                    _save_topo_snap(_topo_curr_snap, self._store)
            except Exception:
                pass  # non-fatal

            # Update the "N new · M gone" badge label
            try:
                _diff_lbl = getattr(self, "_topo_diff_lbl", None)
                if _diff_lbl is not None:
                    _diff_text = (
                        self._topo_diff.summary
                        if self._topo_diff and not self._topo_diff.is_empty
                        else ""
                    )
                    _diff_lbl.setText(_diff_text)
                    _diff_lbl.setVisible(bool(_diff_text))
            except Exception:
                pass  # non-fatal

        except AttributeError:
            pass  # network_map_page not yet initialised
        except Exception as _topo_exc:
            self._set_status(f"Topology render error: {_topo_exc}")

    def _m1_reapply_search_and_suggestions(self) -> None:
        """Re-apply any active NL search filter, then recompute suggestion cards."""
        # Re-apply any active NL search now that new data is loaded
        if hasattr(self, "_m1_search") and self._m1_search.text().strip():
            self._filter_m1_by_nl(self._m1_search.text())

        self._compute_suggestions()

    def _m1_auto_snapshot_baseline(self, data: dict) -> None:
        """DEVICE-5: take an auto config-baseline snapshot and evaluate drift, when enabled."""
        # DEVICE-5: auto-snapshot when setting is on
        try:
            _qs_d5 = QSettings("NetSentinel", "NetSentinel")
            if _qs_d5.value("baseline/auto_snapshot", False, type=bool) and self._store is not None:
                from modules.config_baseline import (
                    build_snapshot_from_scan,
                    diff_snapshots,
                    list_snapshots as _ls,
                    store_snapshot as _ss,
                    delete_snapshot as _ds,
                )
                import datetime as _dt_d5
                _label = f"Auto · {_dt_d5.datetime.now().strftime('%Y-%m-%d %H:%M')}"
                _dev_dicts = []
                for _d in data.get("devices", []):
                    _dev_dicts.append({
                        "mac":      (_d.mac      if not isinstance(_d, dict) else _d.get("mac", "")),
                        "ip":       (_d.ip       if not isinstance(_d, dict) else _d.get("ip", "")),
                        "hostname": (_d.hostname if not isinstance(_d, dict) else _d.get("hostname", "")),
                        "vendor":   (_d.vendor   if not isinstance(_d, dict) else _d.get("vendor", "")),
                        "device_type": (getattr(_d, "device_type", "") if not isinstance(_d, dict) else _d.get("device_type", "")),
                        "open_ports": (list(getattr(_d, "open_ports", [])) if not isinstance(_d, dict) else _d.get("open_ports", [])),
                    })
                _new_snap = build_snapshot_from_scan(_dev_dicts, label=_label)

                # Load previous auto-snapshots for drift check
                _all_snaps = _ls(self._store, limit=200)
                _auto_snaps = [s for s in _all_snaps if (s.label or "").startswith("Auto ·")]

                _prev = _auto_snaps[0] if _auto_snaps else None
                if _prev:
                    _diff = diff_snapshots(_prev, _new_snap)
                    if _diff.has_drift:
                        self._baseline_has_drift = True
                        self._refresh_section_badges()
                        from ui.widgets.toast import ToastManager
                        ToastManager.show(
                            f"Baseline drift: {_diff.summary()} — Config Snapshots",
                            "info",
                        )

                # V6 Sprint 4.3 — diff this scheduled-scan snapshot against the
                # user-blessed baseline (set via ★ Set as Baseline on Config
                # Snapshots) and route added/removed/role-changed devices
                # through the alert pipeline, not just a toast.
                if self._alert_engine is not None:
                    from modules.config_baseline import load_snapshot as _load_blessed
                    from ui.pages.baseline_page import _blessed_snapshot_id
                    _blessed_id = _blessed_snapshot_id()
                    if _blessed_id:
                        _blessed_snap = _load_blessed(self._store, _blessed_id)
                        if _blessed_snap is not None:
                            _drift_diff = diff_snapshots(_blessed_snap, _new_snap)
                            for a in self._alert_engine.evaluate_config_drift_checks(_drift_diff):
                                self._show_alert_toast(a)
                                self._home_page.on_alert(a)
                                try:
                                    persist_alert(self._store, a)
                                except Exception:
                                    pass  # non-fatal — persistence failure must not block the scan handler

                _ss(self._store, _new_snap)

                # Keep only last 10 auto-snapshots; never touch manually-labelled ones
                _all_snaps2 = _ls(self._store, limit=200)
                _auto_only = [s for s in _all_snaps2 if (s.label or "").startswith("Auto ·")]
                for _old in _auto_only[10:]:
                    try:
                        _ds(self._store, _old.id)
                    except Exception:
                        pass  # non-fatal
        except Exception:
            pass  # auto-snapshot errors must never break the scan result handler

    def _m1_run_post_scan_followups(self, data: dict) -> None:
        """Coach marks, enrichment, vendor lookups, plugin wake, WAN IP, and LLDP follow-ups."""
        devices = data.get("devices", [])
        # After scan from home: show post-scan coach marks on first scan only.
        if getattr(self, "_scan_from_home", False) and len(devices) > 0:
            self._scan_from_home = False
            from PyQt6.QtCore import QSettings as _QS
            _qs = _QS("NetSentinel", "NetSentinel")
            if not _qs.value("tour/post_scan_done", False, type=bool):
                _qs.setValue("tour/post_scan_done", True)
                from PyQt6.QtCore import QTimer as _QT
                _QT.singleShot(600, self._start_post_scan_coach_marks)

        # Always apply enrichment — re-classifies device types and rebuilds dependent
        # views even on the first scan; also layers in cached mesh/plugin data when present.
        self._apply_mesh_enrichment()

        # Apply any passive SSDP/mDNS observations buffered before the scan finished.
        self._apply_passive_observations()

        # Async OUI vendor lookup for devices still showing Unknown vendor.
        # Updates table cells and DeviceInfo objects as results arrive.
        self._start_vendor_lookups(devices)

        # Wake any router/AP plugin workers so fresh client data arrives quickly
        # rather than waiting up to 60 s for the next scheduled poll cycle.
        try:
            _hw_page = getattr(self, "_hardware_integration_page", None)
            if _hw_page:
                for _pw in _hw_page._poll_workers.values():
                    if getattr(_pw, "_hw_type", "modem") != "modem" and _pw.isRunning():
                        _pw.trigger_now()
        except Exception:
            pass  # defensive guard — _hardware_integration_page may not be initialised yet

        # Safety-net: re-apply enrichment 15 s after scan so hostnames appear even
        # when the first plugin poll completes after _on_m1_result() returns.
        if not hasattr(self, "_post_scan_enrich_timer"):
            from PyQt6.QtCore import QTimer as _QTE
            self._post_scan_enrich_timer = _QTE(self)
            self._post_scan_enrich_timer.setSingleShot(True)
            self._post_scan_enrich_timer.timeout.connect(self._apply_mesh_enrichment)
        self._post_scan_enrich_timer.start(15_000)

        self._check_hw_autodetect()

        # Fetch WAN IP in background so geo map can resolve LAN devices later
        if not self._wan_ip:
            self._fetch_wan_ip()

        # Integration discovery banner — show when scanned devices match a
        # bundled plugin gateway that isn't already imported
        self._check_integration_banner(devices)

        # Sprint 5 — LLDP multi-hop discovery: start background sniff on the
        # active interface to discover managed switches invisible to ARP scanning.
        self._start_lldp_discovery()


    def _merge_scan_with_persistent(
        self, live_devices: list, known: dict[str, "KnownDevice"] | None = None
    ) -> list:
        """Return live devices augmented with pinned/static-candidate offline devices.

        Devices that appeared in the live scan are returned as-is; the inventory
        page treats any device without an explicit display_state as "online".
        Offline static candidates (pinned, infrastructure roles, or IP-stable
        devices seen 3+ times) are appended as plain dicts with display_state set
        to "pinned", "cached" (<24 h), or "stale" (<7 d).  Devices older than 7
        days and not pinned are omitted — they are already excluded from the
        startup cache restore and would just clutter the view.

        `known`: an optional pre-fetched get_known_devices() snapshot (Phase B2 /
        F4) — reused instead of re-querying when the caller already has one.
        """
        import time as _mt
        _store = getattr(self, "_store", None)
        if _store is None:
            return live_devices
        try:
            from modules.device_stability import is_static_candidate as _is_static

            _now   = int(_mt.time())
            _24h   = 86_400
            _7d    = 7 * _24h

            # Build MAC set for live devices so we don't double-list them
            _live_macs: set[str] = set()
            for _d in live_devices:
                _mac = (_d.mac if not isinstance(_d, dict) else _d.get("mac", "")) or ""
                if _mac and _mac not in ("?", "00:00:00:00:00:00"):
                    _live_macs.add(_mac.lower())

            _extras: list = []
            _known_devices = known if known is not None else _store.get_known_devices()
            for _kd in _known_devices.values():
                if not _kd.ip or _kd.ip in ("?", "0.0.0.0", ""):
                    continue
                if (_kd.mac or "").lower() in _live_macs:
                    continue
                if not _is_static(
                    ip_stability=float(_kd.ip_stability or 0.0),
                    scan_count=int(_kd.scan_count or 0),
                    inferred_role=_kd.inferred_role,
                    is_pinned=bool(_kd.is_pinned),
                ):
                    continue
                _age_s = _now - int(_kd.last_seen or 0)
                if _kd.is_pinned:
                    _state = "pinned"
                elif _age_s <= _24h:
                    _state = "cached"
                elif _age_s <= _7d:
                    _state = "stale"
                else:
                    continue  # older than 7 days and not pinned — skip
                _extras.append({
                    "ip":            _kd.ip,
                    "hostname":      _kd.custom_name or _kd.hostname or "",
                    "mac":           _kd.mac or "?",
                    "vendor":        _kd.vendor or "Unknown",
                    "risk_level":    "UNKNOWN",
                    "device_type":   _kd.device_type or "Unknown Device",
                    "verdict":       "",
                    "display_state": _state,
                    "last_seen_ts":  int(_kd.last_seen or 0),
                    "inferred_role": _kd.inferred_role,
                    "scan_count":    _kd.scan_count,
                    "ip_stability":  _kd.ip_stability,
                    "is_pinned":     _kd.is_pinned,
                })
            return list(live_devices) + _extras
        except Exception:
            return live_devices  # non-fatal — fall back to live-only list

    def _on_lldp_result(self, neighbors: list) -> None:
        """Handle LLDP neighbor results from LldpWorker."""
        self._lldp_result = neighbors
        try:
            admin_needed = not neighbors and not getattr(self, "_lldp_admin_ok", True)
            self._network_map_page.update_lldp_neighbors(
                neighbors, admin_needed=admin_needed
            )
        except AttributeError:
            pass  # non-fatal — network_map_page may not be initialised

    def _start_lldp_discovery(self) -> None:
        """Launch LldpWorker on the active interface after a scan completes."""
        try:
            from workers.lldp_worker import LldpWorker
            from modules.utils import is_admin

            self._lldp_admin_ok = is_admin()

            iface = ""
            net_info = getattr(self, "_net_info", None) or {}
            iface = net_info.get("interface", "") or ""

            if not iface:
                return  # cannot sniff without a known interface

            # Cancel any previous still-running worker
            prev = getattr(self, "_lldp_worker", None)
            if prev and prev.isRunning():
                try:
                    prev.result_ready.disconnect()
                except Exception:
                    pass  # non-fatal — signal may already be disconnected
                prev.terminate()
                prev.wait(300)

            worker = LldpWorker(iface=iface, passive=True, parent=self)
            worker.result_ready.connect(self._on_lldp_result)
            self._lldp_worker = worker
            worker.start()
        except Exception:
            pass  # non-fatal — LLDP discovery is best-effort

    def _on_plugin_result(self, res):
        if res.error:
            tb_lines = res.error.strip().splitlines()
            if len(tb_lines) > 10:
                tb_lines = ["(… truncated …)"] + tb_lines[-10:]
            lines = [
                f"Plugin: {res.plugin_name}",
                "",
                "The plugin encountered an error while running.",
                "Likely cause: a coding error in the plugin or missing expected device data.",
                "What to try:  right-click the plugin row and choose 'Show validation',",
                "              or open the plugins folder to edit the file.",
                "",
                "— Error details —",
            ] + tb_lines
            self._plugin_result_text.setPlainText("\n".join(lines))
            self._plugin_status.setText(f"'{res.plugin_name}' failed — see output below.")
            _s.themed_ss(self._plugin_status, "color:{RED};font-size:11px;")
            self._nav_set_scan_state(
                L.RECON_PLUGINS, "error",
                error=f"{res.plugin_name}: {tb_lines[-1] if tb_lines else 'plugin failed'}",
            )
            return
        lines = [f"Plugin: {res.plugin_name}", f"Risk: {risk_to_label(res.risk_level)}"]
        if res.findings:
            lines.append(f"Findings ({len(res.findings)}):")
            for f in res.findings:
                lines.append(f"  • {f}")
        else:
            lines.append("No findings.")
        self._plugin_result_text.setPlainText("\n".join(lines))
        self._plugin_status.setText(
            f"'{res.plugin_name}' complete — {risk_to_label(res.risk_level)} "
            f"({len(res.findings)} finding{'s' if len(res.findings) != 1 else ''})."
        )
        _s.themed_ss(self._plugin_status, lambda rl=res.risk_level: (
            f"color:{_s.RED if rl in ('HIGH', 'CRITICAL') else (_s.AMBER if rl == 'MEDIUM' else _s.GREEN)};"
            f"font-size:11px;"
        ))
        self._nav_set_scan_state(
            L.RECON_PLUGINS, "fresh",
            ts=time.time(),
            verdict=(f"{res.plugin_name}: {risk_to_label(res.risk_level)} "
                     f"({len(res.findings)} finding"
                     f"{'s' if len(res.findings) != 1 else ''})"),
        )

    # ── Startup cache restore ─────────────────────────────────────────────────

    def _restore_cached_scan(self) -> None:
        """Pre-populate Devices table and Network Map from last-known MetricStore data.

        Called once at startup before any live scan.  Risk levels are omitted
        (shown as "—") because they are point-in-time and stale.  Each device
        carries a display_state key (pinned / cached / stale) so the Inventory
        page can show appropriate freshness indicators without waiting for a scan.
        A live scan always replaces this view via the normal _on_m1_result() path.
        """
        import time as _time
        _store_ref = getattr(self, "_store", None)
        if _store_ref is None:
            return
        try:
            known = _store_ref.get_known_devices()
        except Exception:
            return  # non-fatal — store may not be initialised yet

        now = int(_time.time())
        _24h = 86_400
        _7d  = 7 * _24h

        # Determine display_state and sort priority for each known device.
        # Include: pinned devices always; others if seen within 7 days.
        raw_devices = []
        for kd in known.values():
            if not kd.ip or kd.ip in ("?", "0.0.0.0", ""):
                continue
            age_s = now - int(kd.last_seen or 0)
            if kd.is_pinned:
                state = "pinned"
                priority = 0
            elif age_s <= _24h:
                state = "cached"
                priority = 1
            elif age_s <= _7d:
                state = "stale"
                priority = 2
            else:
                continue  # older than 7 days and not pinned — skip
            raw_devices.append((priority, kd.ip, {
                "ip":            kd.ip or "?",
                "hostname":      kd.custom_name or kd.hostname or "",
                "mac":           kd.mac or "?",
                "vendor":        kd.vendor or "Unknown",
                "risk_level":    "UNKNOWN",
                "device_type":   kd.device_type or "Unknown Device",
                "verdict":       "",
                "display_state": state,
                "last_seen_ts":  int(kd.last_seen or 0),
                "inferred_role": kd.inferred_role,
                "scan_count":    kd.scan_count,
                "ip_stability":  kd.ip_stability,
                "is_pinned":     kd.is_pinned,
            }))

        if not raw_devices:
            return  # first-ever launch — leave empty state in place

        # Sort: pinned first, then cached, then stale; IP within each group
        raw_devices.sort(key=lambda t: (t[0], t[1]))
        devices = [t[2] for t in raw_devices]

        # Loaded once — feeds both the Network Map below and self._m1_result.
        # _on_modem_signal/mesh-enrichment re-renders read devices from
        # self._m1_result, not from locals here, so it must carry the real
        # classification too or those re-renders undo this fix moments later.
        try:
            from modules.network_map_cache import load_render_cache
            _map_cache = load_render_cache()
        except Exception:
            _map_cache = None

        # Populate the Devices table — prefer map cache (full data: hostname,
        # MAC, vendor, device_type, risk_level, mesh_unit/band) over the DB
        # reconstruction which may have NULL fields for unresolved devices.
        _m1_src = _map_cache["devices"] if _map_cache else devices
        self._m1_table.setRowCount(0)
        _has_mesh = False
        for d in _m1_src:
            _g = d.get if isinstance(d, dict) else lambda k, dv="": getattr(d, k, dv)
            _ip = _g("ip", "?") or "?"
            _hn = _g("hostname", "") or ""
            _mc = _g("mac", "") or "?"
            _vn = _g("vendor", "") or "Unknown"
            _dt = _g("device_type", "") or "Unknown Device"
            _rl = _g("risk_level", "") or "UNKNOWN"
            _mu = _g("mesh_unit", "") or ""
            _mb = _g("mesh_band", "") or ""
            if _mu:
                _has_mesh = True
            _add_row(self._m1_table,
                     [_ip, _hn or "—", _mc, _vn, _rl, _dt, _mu, _mb, ""], _rl)
        if _has_mesh:
            self._m1_table.setColumnHidden(6, False)
            self._m1_table.setColumnHidden(7, False)

        # Switch from empty-state placeholder to table view
        if hasattr(self, "_m1_stack"):
            self._m1_stack.setCurrentIndex(1)

        # Status label shows both freshness and device count
        _age = self._cached_scan_age_str(_store_ref)
        pinned_n = sum(1 for d in devices if d["display_state"] == "pinned")
        cached_n = sum(1 for d in devices if d["display_state"] == "cached")
        stale_n  = sum(1 for d in devices if d["display_state"] == "stale")
        _parts = []
        if pinned_n:
            _parts.append(f"{pinned_n} pinned")
        if cached_n:
            _parts.append(f"{cached_n} recent")
        if stale_n:
            _parts.append(f"{stale_n} stale")
        _summary = "  ·  ".join(_parts) if _parts else f"{len(devices)} devices"
        self._m1_status.setText(
            f"Cached — last scanned {_age}  ·  {_summary}  ·  Run Scan to refresh"
        )
        _s.themed_ss(self._m1_status, "color:{TEXT_MUTED};font-size:11px;padding:2px 0;")

        # Downstream pages read devices from here — prefer the cached
        # live-render data over the UNKNOWN-risk reconstruction.
        self._m1_result = {
            "devices":         _map_cache["devices"] if _map_cache else devices,
            "from_cache":      True,
            "total_count":     len(devices),
            "high_risk_count": 0,
        }

        # Feed Inventory page — prefer the map cache (same rich data the Network
        # Map uses: full hostname/vendor/device_type/risk_level from the last
        # live scan) over the DB reconstruction which may have NULL fields.
        # Inject display_state from the DB-age lookup so freshness dots are correct.
        if hasattr(self, "_inventory_page"):
            try:
                if _map_cache:
                    # Build IP → (display_state, last_seen_ts) from DB reconstruction
                    _state_by_ip: dict = {}
                    for _kd in devices:
                        _kd_ip = _kd.get("ip", "") if isinstance(_kd, dict) else getattr(_kd, "ip", "")
                        _kd_st = _kd.get("display_state", "") if isinstance(_kd, dict) else getattr(_kd, "display_state", "")
                        _kd_ls = _kd.get("last_seen_ts", 0) if isinstance(_kd, dict) else getattr(_kd, "last_seen_ts", 0)
                        if _kd_ip:
                            _state_by_ip[_kd_ip] = (_kd_st or "cached", int(_kd_ls or 0))
                    # Enrich map-cache devices with display_state so Inventory shows
                    # correct freshness dots (◌ amber cached / ○ gray stale)
                    _inv_devices = []
                    for _cd in _map_cache["devices"]:
                        _cd_ip = _cd.get("ip", "") if isinstance(_cd, dict) else getattr(_cd, "ip", "")
                        _st, _ls = _state_by_ip.get(_cd_ip, ("cached", 0))
                        if isinstance(_cd, dict):
                            _copy = dict(_cd)
                            _copy["display_state"] = _st
                            _copy["last_seen_ts"]  = _ls
                            _inv_devices.append(_copy)
                        else:
                            # DeviceInfo object: convert to dict so display_state can be added
                            import dataclasses as _dc
                            _base = _dc.asdict(_cd) if _dc.is_dataclass(_cd) else vars(_cd)
                            _base["display_state"] = _st
                            _base["last_seen_ts"]  = _ls
                            _inv_devices.append(_base)
                    self._inventory_page.set_scan_devices(_inv_devices)
                else:
                    self._inventory_page.set_scan_devices(devices)
            except Exception:
                pass  # non-fatal

        # Feed Network Map — load mesh cache FIRST so the single initial render
        # includes satellite grouping (avoiding a two-render sequence where the
        # incremental Cytoscape update fires before the first setHtml() has loaded).
        if hasattr(self, "_network_map_page"):
            # Step 1: attempt to restore mesh enrichment cache
            _startup_mesh_units, _startup_mesh_enrich = None, None
            try:
                import json as _json
                from modules.utils import get_app_data_dir as _gad
                _cache_path = _gad() / "mesh_enrichment_cache.json"
                if _cache_path.exists():
                    _cached = _json.loads(_cache_path.read_text(encoding="utf-8"))
                    if _cached.get("plugin_enrichments"):
                        self._plugin_enrichments = _cached["plugin_enrichments"]
                    if _cached.get("plugin_nodes"):
                        self._plugin_nodes = _cached["plugin_nodes"]
                    if _cached.get("plugin_hardware_name"):
                        self._plugin_hardware_name = _cached["plugin_hardware_name"]
                    _startup_mesh_units, _startup_mesh_enrich = (
                        self._effective_mesh_render_params()
                    )
            except Exception:
                pass  # non-fatal — render without mesh if cache unavailable

            # Step 2: single combined render (topology snapshot + mesh data)
            try:
                _gw_ip: str | None = None
                try:
                    from modules.topology_snapshot import load_last_snapshot as _ls
                    from collections import Counter as _Ctr
                    _snap = _ls(_store_ref)
                    if _snap and _snap.edges:
                        _gw_ip = _Ctr(e[0] for e in _snap.edges).most_common(1)[0][0]
                except Exception:
                    pass  # non-fatal — render without gateway_ip

                if _map_cache is not None:
                    self._network_map_page.render(
                        devices=_map_cache["devices"],
                        gateway_ip=_map_cache["gateway_ip"] or _gw_ip,
                        gateway_mac=_map_cache["gateway_mac"],
                        mesh_units=_startup_mesh_units,
                        mesh_enrichment=_startup_mesh_enrich,
                        modem_data=_map_cache["modem_data"],
                        edges=_map_cache["edges"],
                        persist_cache=False,
                    )
                else:
                    self._network_map_page.render(
                        devices=devices,
                        gateway_ip=_gw_ip,
                        mesh_units=_startup_mesh_units,
                        mesh_enrichment=_startup_mesh_enrich,
                        persist_cache=False,
                    )
                if hasattr(self._network_map_page, "_stale_label"):
                    self._network_map_page._stale_label.setVisible(True)
            except Exception:
                pass  # non-fatal

        # Re-apply plugin enrichment so satellite grouping is restored on startup
        # without waiting for the HW plugin poll to fire (10–14 s delay).
        if _map_cache and getattr(self, "_plugin_enrichments", {}):
            try:
                self._apply_mesh_enrichment()
            except Exception:
                pass  # non-fatal

    def _save_mesh_enrichment_cache(self) -> None:
        """Persist plugin mesh enrichment so the Network Map shows node grouping at startup."""
        try:
            import json as _json
            from modules.utils import get_app_data_dir as _gad
            _data = {
                "plugin_enrichments": {
                    k: dict(v) for k, v in
                    getattr(self, "_plugin_enrichments", {}).items()
                },
                "plugin_nodes":         dict(getattr(self, "_plugin_nodes", {})),
                "plugin_hardware_name": getattr(self, "_plugin_hardware_name", ""),
            }
            (_gad() / "mesh_enrichment_cache.json").write_text(
                _json.dumps(_data), encoding="utf-8"
            )
        except Exception:
            pass  # non-fatal — best-effort cache write

    def _cached_scan_age_str(self, store) -> str:
        """Return a human-readable age string for the most recent topology snapshot."""
        try:
            from modules.topology_snapshot import load_last_snapshot as _load_snap
            snap = _load_snap(store)
            if snap is None:
                return "unknown time ago"
            import datetime as _dt
            delta = _dt.datetime.now() - snap.timestamp
            total_s = int(delta.total_seconds())
            hours, remainder = divmod(total_s, 3600)
            minutes = remainder // 60
            if hours >= 48:
                return f"{hours // 24}d ago"
            if hours >= 1:
                return f"{hours}h ago"
            return f"{minutes}m ago"
        except Exception:
            return "unknown time ago"

    def _on_pe_result(self, res):
        from PyQt6.QtGui import QColor
        row = self._pe_table.rowCount()
        self._pe_table.insertRow(row)

        status_color = _s.GREEN if res.status == "PASS" else (_s.AMBER if res.status == "WARN" else _s.RED)
        ips_str  = ", ".join(res.resolved_ips[:3]) + ("…" if len(res.resolved_ips) > 3 else "")
        priv_str = "✔ Yes" if res.is_private else ("⚠ LEAK" if res.dns_leak else "—")
        tcp_str  = "✔" if res.tcp_open else "✘"
        tls_str  = str(res.cert.days_left) if (res.cert and not res.cert.error and res.cert.days_left >= 0) else "—"
        findings = " | ".join(res.findings) if res.findings else "All checks passed"
        if res.dns_server:
            findings += f"  [resolver: {res.dns_server}]"

        vals = [res.status, res.spec.label, res.cloud or "—", ips_str,
                priv_str, tcp_str, tls_str, findings]
        for col, val in enumerate(vals):
            item = QTableWidgetItem(str(val))
            c = status_color if col == 0 else (
                (_s.GREEN if "✔" in str(val) else (_s.RED if "✘" in str(val) or "LEAK" in str(val) else _s.TEXT_PRIMARY))
            )
            item.setForeground(QColor(c))
            self._pe_table.setItem(row, col, item)
