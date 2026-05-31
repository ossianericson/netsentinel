"""
scan_enrichment.py — ScanEnrichmentMixin: mesh and hardware plugin enrichment handlers.

Extracted from ui/scan_wiring.py (Sprint 13) to keep that file within budget.
ScanResultMixin inherits ScanEnrichmentMixin.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QTableWidgetItem

from ui.tabs import _add_row
from ui.styles import (
    ACCENT, ACCENT_LITE, ACCENT_DARK, AMBER,
    BG_CARD, BORDER, BLUE, GREEN, RED,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
)

if TYPE_CHECKING:
    from ui.dashboard import Dashboard


class ScanEnrichmentMixin:
    """Mixin providing mesh and hardware plugin enrichment handlers for Dashboard.

    Extracted from ui/scan_wiring.py (Sprint 13).
    ScanResultMixin inherits from this mixin.
    """

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
        from ui.dashboard import _color_for_level
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
