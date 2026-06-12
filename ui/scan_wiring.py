"""
scan_wiring.py — ScanResultMixin for Dashboard scan result handlers.

Extracted from ui/dashboard.py (Sprint 4, S1-2).
Dashboard inherits ScanResultMixin to receive these methods.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QSettings, QThread, pyqtSignal
from PyQt6.QtWidgets import QTableWidgetItem

from ui.tabs import _add_row

from ui.styles import (
    ACCENT_LITE, AMBER, AMBER_BG,
    GREEN, RED, RED_BG, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    BLUE,
)
from ui.scan_enrichment import ScanEnrichmentMixin

if TYPE_CHECKING:
    pass


class _VendorBatchWorker(QThread):
    """Background OUI vendor lookup for devices showing 'Unknown' vendor.

    Processes MACs one at a time so the macvendors.com rate limit (≈1 req/s)
    is respected. Emits vendor_resolved(mac, vendor) for each hit so the table
    cell can be updated immediately rather than waiting for all lookups.
    """

    vendor_resolved = pyqtSignal(str, str)  # (normalised_mac, vendor_name)

    def __init__(self, macs: list[str], parent=None) -> None:
        super().__init__(parent)
        self._macs = macs

    def run(self) -> None:
        try:
            from modules.mac_lookup import lookup_vendor
            for mac in self._macs:
                if not mac:
                    continue
                vendor = lookup_vendor(mac)
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
            risk_color = RED if p.risk == "HIGH" else TEXT_PRIMARY
            for col, val in enumerate([str(p.port), p.name, p.service_version or "", p.banner or "", p.risk]):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(risk_color if col in (1, 4) else TEXT_PRIMARY))
                self._ps_table.setItem(row, col, item)
        if hasattr(self, "_ps_status"):
            self._ps_status.setText(data.plain_verdict)
        if hasattr(self, "_monitor_overview_page"):
            self._monitor_overview_page.set_open_port_count(len(data.open_ports))
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

    def _on_ipv6_result(self, devices: list):
        from PyQt6.QtGui import QColor
        self._ipv6_table.setRowCount(0)
        for d in devices:
            row = self._ipv6_table.rowCount()
            self._ipv6_table.insertRow(row)
            source_color = ACCENT_LITE if d.get("source") == "active" else TEXT_SECONDARY
            state_color  = GREEN if d.get("state", "").upper() == "REACHABLE" else TEXT_SECONDARY
            for col, val in enumerate([
                d.get("ip6", ""), d.get("mac", ""),
                d.get("state", ""), d.get("source", ""),
            ]):
                item = QTableWidgetItem(str(val))
                if col == 2:
                    item.setForeground(QColor(state_color))
                elif col == 3:
                    item.setForeground(QColor(source_color))
                else:
                    item.setForeground(QColor(TEXT_PRIMARY))
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
        risk_color = {"NONE": GREEN, "INFO": AMBER, "HIGH": RED}.get(result.risk_level, TEXT_SECONDARY)
        risk_icon  = {"NONE": "✔", "INFO": "ℹ", "HIGH": "⚠"}.get(result.risk_level, "?")
        lines = [
            f"<b style='color:{risk_color}'>{risk_icon} [{result.risk_level}]  {result.plain_verdict}</b>",
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
                v2_color = GREEN if result.imdsv2_enforced else RED
                v2_txt   = "enforced (secure)" if result.imdsv2_enforced else "NOT enforced — HIGH RISK"
                lines.append(f"<b>IMDSv2:</b> <span style='color:{v2_color}'>{v2_txt}</span>")
        for finding in result.findings:
            lines.append(f"<br><span style='color:{AMBER}'>⚠ {finding}</span>")
        self._cloud_local_box.setHtml("<br>".join(lines))

    def _on_cloud_network_result(self, results: list):
        from PyQt6.QtGui import QColor
        self._cloud_network_table.setRowCount(0)
        for r in results:
            row = self._cloud_network_table.rowCount()
            self._cloud_network_table.insertRow(row)
            exposed_color = RED if r.exposed else GREEN
            row_color = RED if r.exposed else TEXT_SECONDARY
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
                    item.setForeground(QColor(TEXT_SECONDARY if not r.exposed else RED))
                self._cloud_network_table.setItem(row, col, item)

    def _on_snmp_result(self, result):
        if not result.reachable:
            return
        row = self._snmp_table.rowCount()
        self._snmp_table.insertRow(row)
        for col, val in enumerate([
            result.host, result.sys_name, result.sys_descr[:80],
            result.sys_uptime, result.if_count, result.sys_contact,
        ]):
            self._snmp_table.setItem(row, col, QTableWidgetItem(str(val)))

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
            color = RED if p.state == "open" else AMBER
            for col, val in enumerate([str(p.port), p.state, p.proto, p.service]):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(color))
                self._recon_syn_table.setItem(row, col, item)
            # CVE count badge (col 4)
            svc_key = (p.service or "").split()[0].lower()
            cve_n = _cve_counts.get(svc_key, 0)
            cve_item = QTableWidgetItem(f"{cve_n} CVEs" if cve_n else "—")
            cve_item.setForeground(QColor(AMBER if cve_n else TEXT_MUTED))
            if cve_n:
                cve_item.setToolTip(f"Click to view {cve_n} CVE(s) for {p.service}")
            self._recon_syn_table.setItem(row, 4, cve_item)
        self._syn_status.setText(result.plain_verdict if not result.error else f"⚠ {result.error}")
        # ── Update NetworkDocPage with accumulated port data ──────────────────
        try:
            if result.open_ports:
                _host_key = getattr(result, "host", "") or getattr(result, "ip", "")
                if _host_key:
                    self._port_data_cache[_host_key] = [
                        {"port": str(p.port), "protocol": p.proto or "tcp",
                         "service": p.service or "", "state": p.state or "open",
                         "banner": ""}
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

    def _on_udp_result(self, result):
        from PyQt6.QtGui import QColor
        self._udp_stack.setCurrentIndex(1)
        self._recon_udp_table.setRowCount(0)
        for p in result.open_ports:
            row = self._recon_udp_table.rowCount()
            self._recon_udp_table.insertRow(row)
            color = AMBER if p.state == "open|filtered" else GREEN
            for col, val in enumerate([str(p.port), p.state, p.service]):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(color))
                self._recon_udp_table.setItem(row, col, item)
        self._udp_status.setText(result.plain_verdict if not result.error else f"⚠ {result.error}")

    def _on_os_result(self, data: dict):
        self._os_stack.setCurrentIndex(1)
        for guess in data.get("guesses", []):
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
        self._os_status.setText(f"Fingerprinted {len(data.get('guesses', []))} host(s).")

    def _on_cve_result(self, service_version: str, result):
        from PyQt6.QtGui import QColor
        self._cve_stack.setCurrentIndex(1)
        for cve in result.cves:
            row = self._recon_cve_table.rowCount()
            self._recon_cve_table.insertRow(row)
            sev = (cve.severity or "NONE").upper()
            color = (RED if sev in ("CRITICAL", "HIGH") else
                     AMBER if sev == "MEDIUM" else
                     BLUE if sev == "LOW" else TEXT_SECONDARY)
            for col, val in enumerate([
                cve.cve_id, service_version,
                f"{cve.cvss_score:.1f}", sev,
                cve.published, cve.description,
            ]):
                item = QTableWidgetItem(str(val))
                item.setForeground(QColor(color if col in (2, 3) else TEXT_PRIMARY))
                self._recon_cve_table.setItem(row, col, item)
        if hasattr(self, "_monitor_overview_page"):
            self._monitor_overview_page.set_cve_count(self._recon_cve_table.rowCount())

    def _on_exposure_result(self, result):
        from PyQt6.QtGui import QColor
        risk_color = RED if result.risk == "HIGH" else AMBER if result.risk == "MEDIUM" else GREEN
        self._exposure_verdict.setText(result.plain_verdict)
        self._exposure_verdict.setStyleSheet(
            f"color:{risk_color};font-size:12px;font-weight:bold;padding:6px;"
            f"background:{RED_BG};border-radius:4px;" if result.risk == "HIGH" else
            f"color:{risk_color};font-size:12px;font-weight:bold;padding:6px;"
            f"background:{AMBER_BG};border-radius:4px;"
        )
        self._exposure_verdict.show()
        self._recon_exposure_table.setRowCount(0)
        for m in result.upnp_mappings:
            row = self._recon_exposure_table.rowCount()
            self._recon_exposure_table.insertRow(row)
            row_color = RED if m.enabled else TEXT_SECONDARY
            for col, val in enumerate([
                m.internal_ip, str(m.external_port), str(m.internal_port),
                m.protocol, m.description, "Yes" if m.enabled else "No",
            ]):
                item = QTableWidgetItem(str(val))
                item.setForeground(QColor(row_color))
                self._recon_exposure_table.setItem(row, col, item)
        self._exposure_status.setText(
            f"WAN IP: {result.wan_ip or 'unknown'} | "
            f"CGNAT: {'Yes' if result.cgnat else 'No'} | "
            f"UPnP mappings: {len(result.upnp_mappings)}"
        )

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

        # Cancel any still-running lookup from a previous scan
        existing = getattr(self, "_vendor_batch_worker", None)
        if existing and existing.isRunning():
            existing.vendor_resolved.disconnect()
            existing.terminate()
            existing.wait(200)

        worker = _VendorBatchWorker(pending, self)
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

        # Update DeviceInfo objects
        for d in self._m1_result.get("devices", []):
            d_mac = (d.mac if not isinstance(d, dict) else d.get("mac", "")) or ""
            if _norm(d_mac) == norm:
                if isinstance(d, dict):
                    d["vendor"] = vendor
                else:
                    d.vendor = vendor

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
                        v_item.setForeground(_QC(TEXT_PRIMARY))
                        v_item.setToolTip(f"Vendor resolved from OUI database\n({mac_item.text()[:8].upper()})")
                    break
        except Exception:
            pass  # non-fatal — table update is best-effort

    def _on_m1_result(self, data: dict):
        import time as _t
        self._last_scan_time = _t.time()
        self._m1_result = data
        devices = data.get("devices", [])
        if hasattr(self, "_overview_page") and devices:
            self._overview_page.set_has_results(True)
        if hasattr(self, "_security_overview_page"):
            self._security_overview_page.notify_scan_complete()
        if hasattr(self, "_monitor_overview_page"):
            import datetime as _dt
            self._monitor_overview_page.set_last_scan_time(_dt.datetime.now())
        if hasattr(self, "_home_page") and devices:
            self._home_page._device_count = max(self._home_page._device_count, len(devices))
        if hasattr(self, "_inventory_page"):
            # Auto-detect segments before populating the snapshot table
            try:
                from modules.network_segments import (
                    auto_detect_segments, merge_segments,
                )
                _gw = ""
                _net_info = getattr(self, "_last_net_info", {}) or {}
                _gw = _net_info.get("gateway", "") or ""
                _detected = auto_detect_segments(devices, _gw)
                _stored: list = []
                if _store_ref:
                    try:
                        _stored = _store_ref.get_segments()
                    except Exception:
                        pass  # non-fatal — table may not exist on first run
                _merged = merge_segments(_detected, _stored)
                # Upsert new auto-created entries only
                for _seg in _merged:
                    if _seg.id == 0 and _store_ref:
                        try:
                            _new_id = _store_ref.upsert_segment(_seg)
                            _seg.id = _new_id
                        except Exception:
                            pass  # non-fatal — proceed without DB id
                self._inventory_page.set_segments(_merged)
            except Exception:
                pass  # non-fatal — segment detection is best-effort
            self._inventory_page.set_scan_devices(devices)
        self._m1_table.setRowCount(0)
        _store_ref = getattr(self, "_store", None)
        for d in devices:
            level   = d.risk_level if not isinstance(d, dict) else d.get("risk_level", "UNKNOWN")
            ip      = d.ip       if not isinstance(d, dict) else d.get("ip", "?")
            host    = d.hostname if not isinstance(d, dict) else d.get("hostname", "")
            mac     = d.mac      if not isinstance(d, dict) else d.get("mac", "?")
            if _store_ref and mac and mac not in ("?", "00:00:00:00:00:00") and ip and ip != "?":
                try:
                    from modules.device_tracker import record_ip_observation as _rec_ip
                    _rec_ip(mac, ip, _store_ref)
                except Exception:
                    pass  # non-fatal — table may not exist on schema upgrade
            vendor  = d.vendor   if not isinstance(d, dict) else d.get("vendor", "Unknown")
            dtype   = d.device_type if not isinstance(d, dict) else d.get("device_type", "")
            # Fall back to connection_type when device_type is blank
            if not dtype:
                dtype = d.connection_type if not isinstance(d, dict) else d.get("connection_type", "Unknown Device")
            verdict = d.verdict  if not isinstance(d, dict) else d.get("verdict", "")
            _add_row(self._m1_table, [ip, host or "—", mac, vendor, level, dtype, "", "", verdict], level)
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
                    _v_item.setToolTip(
                        "MAC address uses privacy randomization\n"
                        "(iOS/Android feature) — vendor lookup not\n"
                        "possible by design. This is normal."
                    )
                elif vendor in ("Unknown", ""):
                    _v_item.setToolTip(
                        "OUI prefix not found in device database.\n"
                        "The device may be uncommon or use a\n"
                        "recently issued MAC range."
                    )
                else:
                    _v_item.setToolTip(f"Identified from OUI/device database\n({mac[:8].upper()})")
            # Device type tooltip when inferred from hostname/ports
            _dt_item = self._m1_table.item(_row_idx, 5)
            if _dt_item and dtype == "Unknown Device":
                _dt_item.setToolTip(
                    "Device type could not be determined.\n"
                    "Run a full port scan (Security Audit →\n"
                    "Port Scan) to improve classification."
                )

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
                self._bl_new_lbl.setStyleSheet(f"color:{AMBER}; font-size:11px;")
                for nd in new_devs:
                    first = baseline.get((nd.get("mac") or "").lower(), {}).get("first_seen", "—")
                    _add_row(self._bl_table,
                             [nd.get("ip","?"), nd.get("hostname","") or "—",
                              nd.get("mac","?"), nd.get("vendor","Unknown"), first],
                             "MEDIUM")
            else:
                self._bl_new_lbl.setText("✓  No new devices since last scan.")
                self._bl_new_lbl.setStyleSheet(f"color:{GREEN}; font-size:11px;")
        except Exception as _exc:
            self._bl_new_lbl.setText(f"Baseline check failed: {_exc}")

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

        # ── Persistent device tracking (MetricStore) ──────────────────────────
        if self._store is not None:
            try:
                from modules.device_tracker import DeviceTracker
                if not hasattr(self, "_device_tracker"):
                    self._device_tracker = DeviceTracker(self._store)
                tr = self._device_tracker.process_scan(data.get("devices", []))
                self._last_scan_new  = len(tr.new_devices)
                self._last_scan_gone = len(tr.gone_devices)
                if tr.new_devices:
                    if hasattr(self, "_live_bandwidth_page"):
                        self._live_bandwidth_page.annotate_event("Device joined", GREEN)
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

        # ── Feed Geolocation Map with discovered device IPs (public ones auto-filtered) ─
        try:
            _ips = [
                (d.ip if not isinstance(d, dict) else d.get("ip", ""))
                for d in data.get("devices", [])
            ]
            self._geo_map_page.add_ips([ip for ip in _ips if ip])
        except Exception:
            pass  # non-fatal

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

        self._update_overall_verdict()
        self._update_kpi_tiles(data)
        # Show the table (hide the empty-state placeholder)
        self._m1_stack.setCurrentIndex(1)
        # Show benchmark content pane (user can now grade without being sent elsewhere)
        if hasattr(self, "_bm_stack"):
            self._bm_stack.setCurrentIndex(1)
        # Refresh topology widget with new device list
        try:
            gw_ip  = self._net_info.get("gateway") if self._net_info else None
            gw_mac = self._net_info.get("gateway_mac") if self._net_info else None
            self._topology_widget.render(
                data.get("devices", []), gw_ip, gw_mac,
                mesh_units=getattr(self, "_mesh_units", None),
                mesh_enrichment=getattr(self, "_mesh_enrichment", None),
                modem_data=getattr(self, "_last_modem_data", None),
            )
        except AttributeError:
            pass  # topology widget not yet initialised
        except Exception as _topo_exc:
            self._set_status(f"Topology render error: {_topo_exc}")
        # Re-apply any active NL search now that new data is loaded
        if hasattr(self, "_m1_search") and self._m1_search.text().strip():
            self._filter_m1_by_nl(self._m1_search.text())

        self._compute_suggestions()

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


        # After scan from home: show post-scan coach marks on first scan, else go to Overview.
        if getattr(self, "_scan_from_home", False) and len(devices) > 0:
            self._scan_from_home = False
            from PyQt6.QtCore import QSettings as _QS
            _qs = _QS("NetSentinel", "NetSentinel")
            if not _qs.value("tour/post_scan_done", False, type=bool):
                _qs.setValue("tour/post_scan_done", True)
                from PyQt6.QtCore import QTimer as _QT
                _QT.singleShot(600, self._start_post_scan_coach_marks)
            else:
                if not getattr(self, "_onboarding_active", False):
                    self._nav_rail_go_to("Overview")

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
            self._plugin_status.setStyleSheet(f"color:{RED};font-size:11px;")
            return
        lines = [f"Plugin: {res.plugin_name}", f"Risk: {res.risk_level}"]
        if res.findings:
            lines.append(f"Findings ({len(res.findings)}):")
            for f in res.findings:
                lines.append(f"  • {f}")
        else:
            lines.append("No findings.")
        self._plugin_result_text.setPlainText("\n".join(lines))
        color = RED if res.risk_level in ("HIGH", "CRITICAL") else (AMBER if res.risk_level == "MEDIUM" else GREEN)
        self._plugin_status.setText(
            f"'{res.plugin_name}' complete — {res.risk_level} "
            f"({len(res.findings)} finding{'s' if len(res.findings) != 1 else ''})."
        )
        self._plugin_status.setStyleSheet(f"color:{color};font-size:11px;")

    def _on_pe_result(self, res):
        from PyQt6.QtGui import QColor
        row = self._pe_table.rowCount()
        self._pe_table.insertRow(row)

        status_color = GREEN if res.status == "PASS" else (AMBER if res.status == "WARN" else RED)
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
                (GREEN if "✔" in str(val) else (RED if "✘" in str(val) or "LEAK" in str(val) else TEXT_PRIMARY))
            )
            item.setForeground(QColor(c))
            self._pe_table.setItem(row, col, item)
