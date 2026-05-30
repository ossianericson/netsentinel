"""
scan_wiring.py — ScanResultMixin for Dashboard scan result handlers.

Extracted from ui/dashboard.py (Sprint 4, S1-2).
Dashboard inherits ScanResultMixin to receive these methods.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QTableWidgetItem

from ui.styles import (
    ACCENT, ACCENT_LITE, ACCENT_DARK, AMBER,
    BG_CARD, BORDER, GREEN, RED, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    BLUE,
)

if TYPE_CHECKING:
    from ui.dashboard import Dashboard


class ScanResultMixin:
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
            pass

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
            pass
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
            pass

    def _on_udp_result(self, result):
        from PyQt6.QtGui import QColor
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
        self._m1_table.setRowCount(0)
        for d in devices:
            level   = d.risk_level if not isinstance(d, dict) else d.get("risk_level", "UNKNOWN")
            ip      = d.ip       if not isinstance(d, dict) else d.get("ip", "?")
            host    = d.hostname if not isinstance(d, dict) else d.get("hostname", "")
            mac     = d.mac      if not isinstance(d, dict) else d.get("mac", "?")
            vendor  = d.vendor   if not isinstance(d, dict) else d.get("vendor", "Unknown")
            dtype   = d.device_type if not isinstance(d, dict) else d.get("device_type", "")
            # Fall back to connection_type when device_type is blank
            if not dtype:
                dtype = d.connection_type if not isinstance(d, dict) else d.get("connection_type", "Unknown Device")
            verdict = d.verdict  if not isinstance(d, dict) else d.get("verdict", "")
            _add_row(self._m1_table, [ip, host or "—", mac, vendor, level, dtype, "", "", verdict], level)

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
                pass
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

        # ── Feed Geo Map with discovered device IPs (public ones auto-filtered) ─
        try:
            _ips = [
                (d.ip if not isinstance(d, dict) else d.get("ip", ""))
                for d in data.get("devices", [])
            ]
            self._geo_map_page.add_ips([ip for ip in _ips if ip])
        except Exception:
            pass

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
            pass

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
                        pass
        except Exception:
            pass  # auto-snapshot errors must never break the scan result handler


        # Auto-navigate to Overview on the very first scan only (home page onboarding).
        # After that the user knows the app — leave them where they are.
        _qs = QSettings("NetSentinel", "NetSentinel")
        _first_scan = not _qs.value("app/has_scanned_before", False, type=bool)
        if getattr(self, "_scan_from_home", False) and len(devices) > 0 and _first_scan:
            self._scan_from_home = False
            _qs.setValue("app/has_scanned_before", True)
            self._nav_rail_go_to("Overview")

        # Re-apply cached mesh/plugin enrichment immediately so names/nodes are
        # visible without waiting for the async worker.
        if self._mesh_enrichment or any(self._plugin_enrichments.values()):
            self._apply_mesh_enrichment()

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

        self._check_hw_autodetect()

        # Fetch WAN IP in background so geo map can resolve LAN devices later
        if not self._wan_ip:
            self._fetch_wan_ip()

        # Integration discovery banner — show when scanned devices match a
        # bundled plugin gateway that isn't already imported
        self._check_integration_banner(devices)

        # OUTPUT-4: post-scan summary sheet
        if hasattr(self, "_scan_sheet") and self._store is not None:
            try:
                import time as _t_o4
                _pending = [
                    a for a in self._store.get_recent_alerts(hours=24)
                    if not a.get("acked_ts")
                ]
                self._scan_sheet.show_sheet(
                    total_devices=len(devices),
                    new_devices=getattr(self, "_last_scan_new", 0),
                    missing_devices=getattr(self, "_last_scan_gone", 0),
                    pending_alerts=len(_pending),
                    baseline_diffs=1 if getattr(self, "_baseline_has_drift", False) else 0,
                    new_cves=0,
                )
            except Exception:
                pass

    def _on_mesh_result(self, data: dict) -> None:
        """Receive mesh scan result and enrich the Devices table."""
        clients  = data.get("clients", [])
        provider = data.get("provider", "mesh").title()
        self._mesh_units      = data.get("units", [])
        self._mesh_enrichment = {c.mac: c for c in clients}
        self._apply_mesh_enrichment()
        matched  = sum(1 for c in clients if c.mac in self._mesh_enrichment)
        summary  = getattr(self, "_m1_scan_summary", "")
        self._m1_status.setText(
            f"{summary}  ·  {provider}: {matched} device{'s' if matched != 1 else ''} enriched"
        )
        # Monitor logging — live entry + throttled DB write
        if hasattr(self, "_log_hub_page"):
            from PyQt6.QtCore import QSettings
            import time as _time
            s = QSettings()
            if s.value("logging/mesh_enabled", False, type=bool):
                self._log_hub_page.add_mesh_entry(data)
                interval_s = s.value("logging/mesh_interval_min", 5, type=int) * 60
                now = _time.time()
                if self._store and now - self._last_mesh_log_ts >= interval_s:
                    units        = self._mesh_units
                    unit_count   = len(units)
                    online_count = sum(1 for u in units if getattr(u, "online", True))
                    worst_name, worst_rssi = None, None
                    for u in units:
                        rssi = getattr(u, "rssi", None) or getattr(u, "signal_level", None)
                        if rssi is not None and (worst_rssi is None or rssi < worst_rssi):
                            worst_rssi = rssi
                            worst_name = getattr(u, "name", "") or getattr(u, "device_id", "")
                    try:
                        self._store.record_mesh_snapshot(
                            unit_count=unit_count,
                            online_count=online_count,
                            worst_unit=worst_name,
                            worst_rssi=worst_rssi,
                        )
                        self._last_mesh_log_ts = now
                    except Exception:
                        pass

    def _on_hardware_plugin_result(self, data: dict) -> None:
        """Route a successful plugin Test result to the relevant existing page.

        modem plugins  → Modem page + Overview tile (via _on_modem_signal)
        router/ap/mesh → Devices table hostname enrichment (via _plugin_enrichments[path])
        """
        import time as _t
        from modules.deco_client import _norm_mac

        info    = data.get("info", {})
        status  = data.get("status", {})
        clients = data.get("clients", [])
        hw_type = info.get("type", "")
        hw_name = info.get("name", "plugin")
        self._plugin_hardware_name = hw_name

        # Clear discovery banner cache so next scan re-evaluates imported plugins
        self.__dict__.pop("_plugin_gateway_map_cache", None)

        # ── Modem plugins: route signal to Modem page + Overview tile ─────────
        if hw_type == "modem":
            # Track which plugin page corresponds to the active modem
            _modem_path = data.get("_path", hw_name)
            if _modem_path in getattr(self, "_plugin_pages", {}):
                self._active_modem_plugin_label = self._plugin_pages[_modem_path]._label
            extra = status.get("extra", {})
            self._on_modem_signal({
                "ts":               int(_t.time()),
                "wan_ip":           status.get("wan_ip"),
                "wan_status":       status.get("wan_status"),
                "firmware_version": extra.get("firmware"),
                "network_type":     extra.get("network_type"),
                "signal_bars":      extra.get("signal_bars"),
                "mcc":              extra.get("mcc"),
                "mnc":              extra.get("mnc"),
                "cell_id":          extra.get("cell_id"),
                "enb_id":           extra.get("enb_id"),
                "nr5g_rsrp_dbm":    extra.get("nr5g_rsrp_dbm"),
                "nr5g_sinr_db":     extra.get("nr5g_sinr_db"),
                "nr5g_rsrq_db":     extra.get("nr5g_rsrq_db"),
                "nr5g_band":        extra.get("nr5g_band"),
                "nr5g_pci":         extra.get("nr5g_pci"),
                "nr5g_arfcn":       extra.get("nr5g_arfcn"),
                "lte_rsrp_dbm":     extra.get("lte_rsrp_dbm"),
                "lte_snr_db":       extra.get("lte_snr_db"),
                "lte_rsrq_db":      extra.get("lte_rsrq_db"),
                "lte_band":         extra.get("lte_band"),
                "lte_pci":          extra.get("lte_pci"),
                "lte_earfcn":       extra.get("lte_earfcn"),
                "endc_info":        extra.get("endc_info"),
            })
            path = data.get("_path", hw_name)
            if path in getattr(self, "_plugin_pages", {}):
                self._plugin_pages[path].update(data)
            self._refresh_hardware_badge()
            if hasattr(self, "_log_hub_page"):
                _plugin_names = [pg._label for pg in getattr(self, "_plugin_pages", {}).values()]
                self._log_hub_page.add_plugin_entry(data)
                self._log_hub_page.update_plugin_sources(_plugin_names)
                _qs_key = hw_name.lower().replace(" ", "_")
                from PyQt6.QtCore import QSettings as _QS_pl
                if self._store and _QS_pl().value(f"logging/plugin_{_qs_key}_enabled", False, type=bool):
                    self._store.record_plugin_snapshot(hw_name, data)
            return  # modem plugins have no LAN clients to enrich

        # ── Router/AP/mesh plugins: enrich Devices table + topology ──────────
        # Key by instance_id (stable across renames/restarts), not path or hw_name.
        inst_id = data.get("_instance_id") or data.get("_path", hw_name)
        self._plugin_enrichments[inst_id] = {
            _norm_mac(c.get("mac", "")): c
            for c in clients
            if c.get("mac")
        }
        # Store node list so topology can group devices by AP/satellite.
        # If the plugin returned clients but no nodes (single-AP router),
        # synthesize one node so topology and "Group by node" still work.
        nodes = status.get("extra", {}).get("nodes", [])
        if not nodes and clients and hw_type in ("router", "mesh", "ap"):
            nodes = [{"name": hw_name, "role": "primary",
                      "ip": info.get("ip", ""), "mac": ""}]
        self._plugin_nodes[inst_id] = nodes
        self._apply_mesh_enrichment()  # handles topology + regrouping + synthesis
        from modules.network_infrastructure import hw_state
        path = data.get("_path", hw_name)
        hw_state.update_router(clients, nodes, source=path, hw_name=hw_name)
        n = len(self._plugin_enrichments[inst_id])
        if hasattr(self, "_m1_status"):
            summary = getattr(self, "_m1_scan_summary", "")
            self._m1_status.setText(
                f"{summary}  ·  {hw_name}: {n} device{'s' if n != 1 else ''} enriched"
            )

        # Update plugin device page (modem path returns early above, so this
        # only runs for router/AP/switch types).
        if path in getattr(self, "_plugin_pages", {}):
            self._plugin_pages[path].update(data)

        self._refresh_hardware_badge()
        if hasattr(self, "_log_hub_page"):
            _plugin_names = [pg._label for pg in getattr(self, "_plugin_pages", {}).values()]
            self._log_hub_page.add_plugin_entry(data)
            self._log_hub_page.update_plugin_sources(_plugin_names)
            _qs_key = hw_name.lower().replace(" ", "_")
            from PyQt6.QtCore import QSettings as _QS_pl
            if self._store and _QS_pl().value(f"logging/plugin_{_qs_key}_enabled", False, type=bool):
                self._store.record_plugin_snapshot(hw_name, data)

    def _on_m2_result(self, data: dict):
        self._m2_stack.setCurrentIndex(1)
        self._m2_result = data
        rogue = data.get("rogue_count", 0)
        total = data.get("total_bpdus", 0)
        self._m2_status.setText(
            f"✓  {total} BPDU frame(s) captured — {rogue} rogue Root Bridge claim(s)"
        )
        self._update_overall_verdict()

    def _on_m3_result(self, storm):
        self._m3_stack.setCurrentIndex(1)
        self._m3_result = storm
        level = storm.storm_level if not isinstance(storm, dict) else storm.get("storm_level", "?")
        bps   = storm.bcast_per_sec if not isinstance(storm, dict) else storm.get("bcast_per_sec", 0)
        mps   = storm.mcast_per_sec if not isinstance(storm, dict) else storm.get("mcast_per_sec", 0)
        ratio = storm.bcast_ratio if not isinstance(storm, dict) else storm.get("bcast_ratio", 0)
        top5  = storm.top_sources if not isinstance(storm, dict) else storm.get("top_sources", [])
        rogues = set(storm.rogue_matches if not isinstance(storm, dict) else storm.get("rogue_matches", []))

        self._update_stat(self._m3_bcast_lbl, f"{bps:.1f}", _color_for_level(level))
        self._update_stat(self._m3_mcast_lbl, f"{mps:.1f}")
        self._update_stat(self._m3_ratio_lbl, f"{ratio:.1%}")
        self._update_stat(self._m3_level_lbl, level, _color_for_level(level))

        self._m3_table.setRowCount(0)
        for mac, count in top5:
            is_rogue = mac in rogues
            _add_row(
                self._m3_table,
                [mac, str(count), "⚠ YES — CONFIRMED SABOTAGE" if is_rogue else "No"],
                "HIGH" if is_rogue else "CLEAN",
            )

        self._m3_status.setText(f"✓  Storm level: {level} ({bps:.1f} bcast/s)")
        self._update_overall_verdict()
        if hasattr(self, "_monitor_overview_page"):
            self._monitor_overview_page.set_storm_status(level)

    def _on_m4_result(self, wifi):
        self._m4_stack.setCurrentIndex(1)
        self._m4_result = wifi
        networks = wifi.networks if not isinstance(wifi, dict) else wifi.get("networks", [])
        my_ssid  = (wifi.my_ssid if not isinstance(wifi, dict) else wifi.get("my_ssid", "")) or ""
        self._m4_table.setRowCount(0)

        def _g(obj, attr, default):
            return getattr(obj, attr, default) if not isinstance(obj, dict) else obj.get(attr, default)

        # Clear co-channel flags for BSSIDs whose OUI matches a known mesh unit
        mesh_units = getattr(self, "_mesh_units", None)
        mesh_ouis: set = set()
        if mesh_units:
            mesh_ouis = {
                u.mac[:8] for u in mesh_units
                if hasattr(u, "mac") and len(u.mac) >= 8
            }
            for _n in networks:
                if _g(_n, "co_channel_conflict", False):
                    _bssid = _g(_n, "bssid", "")
                    if _bssid and len(_bssid) >= 8 and _bssid[:8] in mesh_ouis:
                        if not isinstance(_n, dict):
                            _n.co_channel_conflict = False
                        else:
                            _n["co_channel_conflict"] = False

        # Build OUI set from ALL named SSIDs so we can identify backhaul hidden SSIDs
        # even when Deco API data isn't available.
        named_ouis: set = set()
        for n in networks:
            ssid  = _g(n, "ssid", "")
            bssid = _g(n, "bssid", "")
            if ssid and bssid and len(bssid) >= 8:
                named_ouis.add(bssid[:8])
        # Also include Deco-API OUIs
        named_ouis |= mesh_ouis

        # Deco node-name lookup: mac[:17].lower() → node name
        deco_names: dict = {}
        if mesh_units:
            for u in mesh_units:
                if hasattr(u, "mac") and hasattr(u, "name"):
                    deco_names[u.mac[:17].lower()] = u.name

        def _is_backhaul(bssid: str) -> bool:
            """True when a hidden SSID's OUI matches the mesh system's named OUI."""
            if len(bssid) < 8:
                return False
            oui = bssid[:8]
            # Locally-administered variants of named OUIs are common for backhaul.
            # Check exact match and also the canonical (globally-administered) form.
            canon = bssid[0]
            try:
                first = int(bssid[0:2], 16)
                canon_first = first & 0xFD  # clear locally-administered bit
                canon_oui = f"{canon_first:02x}{bssid[2:8]}"
            except ValueError:
                canon_oui = oui
            return oui in named_ouis or canon_oui in named_ouis

        # Group named SSIDs; group hidden SSIDs by (channel, band)
        ssid_groups: dict = {}
        hidden_groups: dict = {}
        for n in networks:
            ssid = _g(n, "ssid", "")
            if ssid:
                ssid_groups.setdefault(ssid, []).append(n)
            else:
                ch   = _g(n, "channel", 0)
                band = _g(n, "band", "?")
                hidden_groups.setdefault((ch, band), []).append(n)

        display_rows: list = []

        for ssid, group in ssid_groups.items():
            best     = max(group, key=lambda x: _g(x, "signal_dbm", -100))
            worst    = min(group, key=lambda x: _g(x, "signal_dbm", -100))
            rogue    = any(_g(x, "is_rogue_ssid",      False) for x in group)
            conflict = any(_g(x, "co_channel_conflict", False) for x in group)
            bssid    = _g(best, "bssid", "")
            # Build per-node tooltip: prefer Deco names, fall back to raw BSSIDs
            node_tips = []
            for x in sorted(group, key=lambda x: _g(x, "signal_dbm", -100), reverse=True):
                b = _g(x, "bssid", "")
                name = deco_names.get(b[:17].lower(), "")
                sig  = _g(x, "signal_dbm", 0)
                node_tips.append(f"{name or b}  {sig} dBm")
            display_rows.append((
                best, ssid, bssid, len(group), node_tips,
                rogue, conflict, False,
                _g(best, "signal_dbm", 0), _g(worst, "signal_dbm", 0),
            ))

        for (_ch, _band), group in hidden_groups.items():
            best     = max(group, key=lambda x: _g(x, "signal_dbm", -100))
            worst    = min(group, key=lambda x: _g(x, "signal_dbm", -100))
            rogue    = any(_g(x, "is_rogue_ssid",      False) for x in group)
            conflict = any(_g(x, "co_channel_conflict", False) for x in group)
            bssid    = _g(best, "bssid", "")
            backhaul = _is_backhaul(bssid)
            node_tips = [_g(x, "bssid", "") for x in group]
            display_rows.append((
                best, None, bssid, len(group), node_tips,
                rogue, conflict, backhaul,
                _g(best, "signal_dbm", 0), _g(worst, "signal_dbm", 0),
            ))

        from PyQt6.QtWidgets import QTableWidgetItem
        for n, ssid, bssid, node_count, node_tips, rogue, conflict, backhaul, sig_best, sig_worst in display_rows:
            ch   = _g(n, "channel", 0)
            band = _g(n, "band", "?")
            connected = bool(my_ssid and ssid and ssid == my_ssid)

            # SSID display
            if ssid:
                ssid_d = ssid
            elif backhaul:
                ssid_d = "Mesh Backhaul"
            else:
                ssid_d = "[HIDDEN]"

            # Signal: show range when nodes differ by more than 2 dBm
            if node_count > 1 and abs(sig_best - sig_worst) > 2:
                sig_d = f"{sig_best} / {sig_worst} dBm"
            else:
                sig_d = f"{sig_best} dBm"

            # Nodes column tooltip
            node_tip = "\n".join(node_tips) if node_tips else ""

            level = "HIGH" if rogue else ("MEDIUM" if conflict else "CLEAN")

            row_idx = self._m4_table.rowCount()
            self._m4_table.insertRow(row_idx)

            ssid_item = QTableWidgetItem(ssid_d)
            if backhaul:
                from PyQt6.QtGui import QColor
                ssid_item.setForeground(QColor(TEXT_MUTED))
                ssid_item.setToolTip(
                    "Hidden SSID used for inter-node mesh communication.\n"
                    "Not a user network — safe to ignore."
                )

            bssid_item = QTableWidgetItem(bssid)

            nodes_item = QTableWidgetItem(str(node_count) if node_count > 1 else "")
            if node_count > 1:
                nodes_item.setToolTip(node_tip)
                from PyQt6.QtGui import QColor
                nodes_item.setForeground(QColor(ACCENT))

            sig_item  = QTableWidgetItem(sig_d)
            rogue_item = QTableWidgetItem("⚠ Yes" if rogue else "No")
            conf_item  = QTableWidgetItem("⚠ Yes" if conflict else "No")
            conn_item  = QTableWidgetItem("✓ Yes" if connected else "")

            from PyQt6.QtGui import QColor as _QC
            if rogue:
                rogue_item.setForeground(_QC(RED))
            if conflict:
                conf_item.setForeground(_QC(AMBER))
            if connected:
                conn_item.setForeground(_QC(GREEN))

            for col, item in enumerate([
                ssid_item, bssid_item, nodes_item,
                QTableWidgetItem(str(ch)), QTableWidgetItem(band),
                sig_item, rogue_item, conf_item, conn_item,
            ]):
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self._m4_table.setItem(row_idx, col, item)

        rogue_c  = wifi.rogue_count  if not isinstance(wifi, dict) else wifi.get("rogue_count", 0)
        hidden_c = wifi.hidden_count if not isinstance(wifi, dict) else wifi.get("hidden_count", 0)
        self._m4_status.setText(
            f"✓  {len(networks)} networks — {rogue_c} suspicious SSIDs, {hidden_c} hidden"
            + (f"  ·  connected: {my_ssid}" if my_ssid else "")
        )
        self._update_overall_verdict()

    def _on_m5_result(self, corr):
        self._m5_result = corr
        self._graph_timer.stop()
        self._graph.redraw()

        outages  = corr.micro_outages   if not isinstance(corr, dict) else corr.get("micro_outages", [])
        stp_list = corr.stp_signatures  if not isinstance(corr, dict) else corr.get("stp_signatures", [])
        self._m5_outage_table.setRowCount(0)
        for o in outages:
            is_stp = o in stp_list
            level = "HIGH" if is_stp else "MEDIUM"
            _add_row(
                self._m5_outage_table,
                [
                    o.get("target", "?"),
                    f"{o.get('duration', 0):.1f}",
                    str(o.get("consecutive_drops", 0)),
                    "⚠ YES — STP" if is_stp else "No",
                    level,
                ],
                level,
            )

        self._m5_status.setText(
            f"\u2713  {len(outages)} outage(s) \u2014 "
            f"{len(stp_list)} "
            "STP reconvergence signature(s)"
        )
        self._update_overall_verdict()

    def _on_diag_result(self, result):
        from ui.styles import GREEN, AMBER, RED, TEXT_SECONDARY, TEXT_PRIMARY, BLUE

        self._diag_result = result
        self._protocol_viz_page.set_context(
            net_info=self._net_info,
            devices=self._m1_result.get("devices", []) if self._m1_result else [],
            diag_result=self._diag_result,
            m2_result=self._m2_result,
        )

        # Ping table
        self._diag_ping_table.setRowCount(0)
        for p in result.ping_results:
            color = GREEN if p.status == "OK" else (AMBER if p.status == "SLOW" else RED)
            rtt_str = f"{p.rtt_ms:.0f}" if p.rtt_ms >= 0 else "unreachable"
            row = self._diag_ping_table.rowCount()
            self._diag_ping_table.insertRow(row)
            for col, val in enumerate([p.host, p.ip, rtt_str, p.status]):
                item = QTableWidgetItem(str(val))
                item.setForeground(
                    __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(
                        color if col == 3 else TEXT_PRIMARY
                    )
                )
                self._diag_ping_table.setItem(row, col, item)

        # DNS table
        self._diag_dns_table.setRowCount(0)
        for d in result.dns_results:
            color = GREEN if d.status == "OK" else (AMBER if d.status == "SLOW" else RED)
            lat_str = f"{d.latency_ms:.0f} ms" if d.latency_ms >= 0 else "failed"
            row = self._diag_dns_table.rowCount()
            self._diag_dns_table.insertRow(row)
            for col, val in enumerate([d.server, lat_str, d.resolved_ip, d.status]):
                item = QTableWidgetItem(str(val))
                item.setForeground(
                    __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(
                        color if col == 3 else TEXT_PRIMARY
                    )
                )
                self._diag_dns_table.setItem(row, col, item)

        # HTTP labels
        for i, h in enumerate(result.http_results):
            if i < len(self._diag_http_labels):
                lbl = self._diag_http_labels[i]
                color = GREEN if h.status == "OK" else (AMBER if h.status == "PARTIAL" else RED)
                code_str = str(h.status_code) if h.status_code else "—"
                lbl.setText(f"● {h.url}: {h.status} ({code_str})")
                lbl.setStyleSheet(f"color:{color}; font-size:11px; padding:0 10px;")

        # Traceroute
        self._diag_trace_table.setRowCount(0)
        for hop in result.trace_hops:
            rtt_str = f"{hop.rtt_ms:.0f}" if hop.rtt_ms >= 0 else "—"
            row = self._diag_trace_table.rowCount()
            self._diag_trace_table.insertRow(row)
            for col, val in enumerate([str(hop.hop), hop.ip, rtt_str]):
                self._diag_trace_table.setItem(row, col, QTableWidgetItem(val))

        # Summary stats
        gw_ping = next((p for p in result.ping_results if p.host == "Gateway"), None)
        gw_str = (f"{gw_ping.rtt_ms:.0f} ms" if gw_ping and gw_ping.rtt_ms >= 0 else "—")
        gw_col = GREEN if gw_ping and gw_ping.status == "OK" else (AMBER if gw_ping and gw_ping.status == "SLOW" else RED)
        self._update_stat(self._diag_gw_lbl, gw_str, gw_col)

        speed_str = (
            f"{result.download_mbps:.1f} Mbps"
            if result.download_mbps >= 1
            else (f"{result.download_mbps * 1000:.0f} Kbps" if result.download_mbps > 0 else "—")
        )
        self._update_stat(self._diag_speed_lbl, speed_str, GREEN if result.download_mbps > 0 else RED)
        self._update_stat(self._diag_public_lbl, result.public_ip or "—", BLUE if result.public_ip else RED)

        sys_dns = next((d for d in result.dns_results if d.server == "System DNS"), None)
        dns_str = f"{sys_dns.latency_ms:.0f} ms" if sys_dns and sys_dns.latency_ms >= 0 else "—"
        dns_col = GREEN if sys_dns and sys_dns.status == "OK" else (AMBER if sys_dns and sys_dns.status == "SLOW" else RED)
        self._update_stat(self._diag_dns_lbl, dns_str, dns_col)

        self._diag_status_lbl.setText(f"Diagnostics complete.  {result.plain_verdict}")
        self._btn_diag.setEnabled(True)

        # DNS Leak
        from PyQt6.QtGui import QColor
        leak = getattr(result, "dns_leak", None)
        self._diag_leak_table.setRowCount(0)
        if leak:
            color = RED if leak.leak_detected else GREEN
            self._diag_leak_lbl.setText(leak.plain_verdict)
            self._diag_leak_lbl.setStyleSheet(f"color:{color}; font-size:11px; padding-left:10px;")
            for e in leak.resolvers_seen:
                r = self._diag_leak_table.rowCount()
                self._diag_leak_table.insertRow(r)
                for col, val in enumerate([e.server_ip, e.country, e.org]):
                    self._diag_leak_table.setItem(r, col, QTableWidgetItem(val))

        self._update_overall_verdict()
        if self._auto_report_pending:
            self._auto_report_diag_done = True
            self._maybe_auto_report()
        if getattr(self, "_pending_isp_report", False):
            self._pending_isp_report = False
            self._export_isp_report()

    def _on_cred_result(self, res):
        from PyQt6.QtWidgets import QTableWidgetItem as _TWI
        flags = res.risk_flags
        color = RED if flags else GREEN
        self._cred_verdict.setText(res.plain_verdict + (f"\n⚠ {' | '.join(flags)}" if flags else ""))
        self._cred_verdict.setStyleSheet(
            f"color:{color};font-size:11px;font-weight:bold;padding:4px;"
            f"background:{BG_CARD};border-radius:4px;"
        )
        self._cred_verdict.show()
        self._cred_status.setText("Credentialed scan complete.")

        # ── Device Info tab ───────────────────────────────────────────────
        info_rows = [
            ("OS",             res.patch_info.os_version or res.os_type),
            ("Kernel / Build", res.patch_info.kernel),
            ("Last Update",    res.patch_info.last_update),
            ("Pending Updates",str(res.patch_info.pending_updates)),
            ("Serial Number",  res.serial_number or "—"),
            ("Failed Logins (24 h)", str(res.failed_logins)),
        ]
        for field_name, value in info_rows:
            r = self._recon_cred_info_table.rowCount()
            self._recon_cred_info_table.insertRow(r)
            self._recon_cred_info_table.setItem(r, 0, _TWI(field_name))
            self._recon_cred_info_table.setItem(r, 1, _TWI(value))

        # ── Active Sessions tab ───────────────────────────────────────────
        if res.active_sessions:
            for session_user in res.active_sessions:
                r = self._recon_cred_sessions_table.rowCount()
                self._recon_cred_sessions_table.insertRow(r)
                self._recon_cred_sessions_table.setItem(r, 0, _TWI(session_user))
        else:
            r = self._recon_cred_sessions_table.rowCount()
            self._recon_cred_sessions_table.insertRow(r)
            self._recon_cred_sessions_table.setItem(r, 0, _TWI("No active interactive sessions detected"))

        for sw in res.software:
            r = self._recon_cred_sw_table.rowCount()
            self._recon_cred_sw_table.insertRow(r)
            for c, v in enumerate([sw.name, sw.version, sw.source]):
                self._recon_cred_sw_table.setItem(r, c, _TWI(v))

        for svc in res.services:
            r = self._recon_cred_svc_table.rowCount()
            self._recon_cred_svc_table.insertRow(r)
            for c, v in enumerate([svc.name, svc.status, str(svc.pid) if svc.pid else ""]):
                self._recon_cred_svc_table.setItem(r, c, _TWI(v))

        for u in res.users:
            r = self._recon_cred_user_table.rowCount()
            self._recon_cred_user_table.insertRow(r)
            for c, v in enumerate([u.username, u.uid, u.home, u.shell]):
                self._recon_cred_user_table.setItem(r, c, _TWI(v))

    def _on_discovery_result(self, res):
        from PyQt6.QtWidgets import QTableWidgetItem as _TWI
        self._disc_status.setText(res.plain_verdict)
        for dev in res.devices:
            r = self._recon_disc_table.rowCount()
            self._recon_disc_table.insertRow(r)
            ms = f"{dev.response_ms:.0f}" if dev.response_ms else ""
            for c, v in enumerate([dev.ip, dev.mac, dev.hostname,
                                    ", ".join(dev.discovery_methods), ms]):
                self._recon_disc_table.setItem(r, c, _TWI(v))

    def _on_smb_result(self, res):
        from PyQt6.QtWidgets import QTableWidgetItem as _TWI
        flags = res.risk_flags
        color = RED if any("Anonymous" in f or "DC" in f for f in flags) else (AMBER if flags else GREEN)
        self._smb_verdict.setText(res.plain_verdict + (f"\n⚠ {' | '.join(flags)}" if flags else ""))
        self._smb_verdict.setStyleSheet(
            f"color:{color};font-size:11px;font-weight:bold;padding:4px;"
            f"background:{BG_CARD};border-radius:4px;"
        )
        self._smb_verdict.show()
        self._smb_status.setText("SMB enumeration complete.")

        high_risk = {"DISK"}
        for share in res.shares:
            r = self._recon_smb_shares_table.rowCount()
            self._recon_smb_shares_table.insertRow(r)
            risk = "HIGH" if (share.share_type in high_risk and not share.name.endswith("$")) else "—"
            for c, v in enumerate([share.name, share.share_type, share.comment, risk]):
                item = _TWI(v)
                if risk == "HIGH":
                    from PyQt6.QtGui import QColor
                    item.setForeground(QColor(RED))
                self._recon_smb_shares_table.setItem(r, c, item)

        for u in res.users:
            r = self._recon_smb_users_table.rowCount()
            self._recon_smb_users_table.insertRow(r)
            for c, v in enumerate([u.username, u.uid, u.full_name, u.last_logon]):
                self._recon_smb_users_table.setItem(r, c, _TWI(v))

    def _on_plugin_result(self, res):
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
