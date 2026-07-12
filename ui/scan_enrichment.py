"""
scan_enrichment.py — ScanEnrichmentMixin: mesh and hardware plugin enrichment handlers.

Extracted from ui/scan_wiring.py (Sprint 13) to keep that file within budget.
ScanResultMixin inherits ScanEnrichmentMixin.
"""
from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QSettings, pyqtSlot
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QTableWidgetItem

from modules.scan_persistence import (
    persist_alert, record_mesh_snapshot, record_plugin_snapshot, record_rtt,
)

from ui.tabs import _add_row
from ui.nav.labels import NavLabel as L
from ui import styles as _s

if TYPE_CHECKING:
    pass


class ScanEnrichmentMixin:
    """Mixin providing mesh and hardware plugin enrichment handlers for Dashboard.

    Extracted from ui/scan_wiring.py (Sprint 13).
    ScanResultMixin inherits from this mixin.
    """

    def _save_mesh_enrichment_cache(self) -> None:
        """No-op base — overridden by ScanResultMixin with the full file-write implementation."""

    def _on_mesh_result(self, data: dict) -> None:
        """Receive mesh scan result and enrich the Devices table."""
        clients  = data.get("clients", [])
        provider = data.get("provider", "mesh").title()
        self._mesh_units      = data.get("units", [])
        from modules.deco_client import _norm_mac as _nm
        self._mesh_enrichment = {_nm(c.mac): c for c in clients}
        self._apply_mesh_enrichment()
        matched  = len(clients)
        summary  = getattr(self, "_m1_scan_summary", "")
        self._m1_status.setText(
            f"{summary}  ·  {provider}: {matched} device{'s' if matched != 1 else ''} enriched"
        )

        # Compute mesh health once — used by both alert evaluation and snapshot logging.
        units        = self._mesh_units
        unit_count   = len(units)
        online_count = sum(1 for u in units if getattr(u, "online", True))
        worst_name, worst_rssi = None, None
        for u in units:
            rssi = getattr(u, "rssi", None) or getattr(u, "signal_level", None)
            if rssi is not None and (worst_rssi is None or rssi < worst_rssi):
                worst_rssi = rssi
                worst_name = getattr(u, "name", "") or getattr(u, "device_id", "")

        # V6 Sprint 1 — MESH_DEGRADED: evaluated on every mesh result, independent
        # of whether Monitor logging is enabled below.
        if unit_count > 0 and self._alert_engine is not None:
            for a in self._alert_engine.evaluate_mesh_checks(unit_count, online_count, worst_name, worst_rssi):
                self._show_alert_toast(a)
                self._home_page.on_alert(a)
                if self._store is not None:
                    try:
                        persist_alert(self._store, a)
                    except Exception:
                        pass  # non-fatal — persistence failure must not block the scan handler

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
                    try:
                        record_mesh_snapshot(
                            self._store,
                            unit_count=unit_count,
                            online_count=online_count,
                            worst_unit=worst_name,
                            worst_rssi=worst_rssi,
                        )
                        self._last_mesh_log_ts = now
                    except Exception:
                        pass  # non-fatal

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
                    record_plugin_snapshot(self._store, hw_name, data)
            return  # modem plugins have no LAN clients to enrich

        # ── Router/AP/mesh plugins: enrich Devices table + topology ──────────
        # Key by instance_id (stable across renames/restarts), not path or hw_name.
        inst_id = data.get("_instance_id") or data.get("_path", hw_name)
        # Exclude the gateway's own MAC so the router's MAC never appears as a
        # "client" entry — the root vector for hostname clobbering (Bug C/D).
        _gw_mac_filter = _norm_mac(self._net_info.get("gateway_mac", "")) if self._net_info else ""
        self._plugin_enrichments[inst_id] = {
            _norm_mac(c.get("mac", "")): c
            for c in clients
            if c.get("mac") and _norm_mac(c.get("mac", "")) != _gw_mac_filter
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
        self._save_mesh_enrichment_cache()  # persist so Network Map loads correctly next startup
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
                record_plugin_snapshot(self._store, hw_name, data)

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

        from ui.tabs_helpers import risk_to_label as _r2l
        self._m3_status.setText(f"✓  Storm level: {_r2l(level)} ({bps:.1f} bcast/s)")
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

            row_idx = self._m4_table.rowCount()
            self._m4_table.insertRow(row_idx)

            ssid_item = QTableWidgetItem(ssid_d)
            if backhaul:
                from PyQt6.QtGui import QColor
                ssid_item.setForeground(QColor(_s.TEXT_MUTED))
                ssid_item.setToolTip(
                    "Hidden SSID used for inter-node mesh communication.\n"
                    "Not a user network — safe to ignore."
                )

            bssid_item = QTableWidgetItem(bssid)

            nodes_item = QTableWidgetItem(str(node_count) if node_count > 1 else "")
            if node_count > 1:
                nodes_item.setToolTip(node_tip)
                from PyQt6.QtGui import QColor
                nodes_item.setForeground(QColor(_s.ACCENT))

            sig_item  = QTableWidgetItem(sig_d)
            rogue_item = QTableWidgetItem("⚠ Yes" if rogue else "No")
            conf_item  = QTableWidgetItem("⚠ Yes" if conflict else "No")
            conn_item  = QTableWidgetItem("✓ Yes" if connected else "")

            from PyQt6.QtGui import QColor as _QC
            if rogue:
                rogue_item.setForeground(_QC(_s.RED))
            if conflict:
                conf_item.setForeground(_QC(_s.AMBER))
            if connected:
                conn_item.setForeground(_QC(_s.GREEN))

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
        _m4_verdict = (
            f"{len(networks)} networks — {rogue_c} suspicious, {hidden_c} hidden"
            + (f"  ·  connected: {my_ssid}" if my_ssid else "")
        )
        self._nav_set_scan_state(L.WIFI_NETWORKS, "fresh", ts=time.time(), verdict=_m4_verdict)

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
            color = _s.GREEN if p.status == "OK" else (_s.AMBER if p.status == "SLOW" else _s.RED)
            rtt_str = f"{p.rtt_ms:.0f}" if p.rtt_ms >= 0 else "unreachable"
            row = self._diag_ping_table.rowCount()
            self._diag_ping_table.insertRow(row)
            for col, val in enumerate([p.host, p.ip, rtt_str, p.status]):
                item = QTableWidgetItem(str(val))
                item.setForeground(
                    QColor(color if col == 3 else _s.TEXT_PRIMARY)
                )
                self._diag_ping_table.setItem(row, col, item)

        # DNS table
        self._diag_dns_table.setRowCount(0)
        for d in result.dns_results:
            color = _s.GREEN if d.status == "OK" else (_s.AMBER if d.status == "SLOW" else _s.RED)
            lat_str = f"{d.latency_ms:.0f} ms" if d.latency_ms >= 0 else "failed"
            row = self._diag_dns_table.rowCount()
            self._diag_dns_table.insertRow(row)
            for col, val in enumerate([d.server, lat_str, d.resolved_ip, d.status]):
                item = QTableWidgetItem(str(val))
                item.setForeground(
                    QColor(color if col == 3 else _s.TEXT_PRIMARY)
                )
                self._diag_dns_table.setItem(row, col, item)

        # HTTP labels
        for i, h in enumerate(result.http_results):
            if i < len(self._diag_http_labels):
                lbl = self._diag_http_labels[i]
                code_str = str(h.status_code) if h.status_code else "—"
                lbl.setText(f"● {h.url}: {h.status} ({code_str})")
                _s.themed_ss(lbl, lambda st=h.status: (
                    f"color:{_s.GREEN if st == 'OK' else (_s.AMBER if st == 'PARTIAL' else _s.RED)};"
                    f" font-size:11px; padding:0 10px;"))

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
        gw_col = _s.GREEN if gw_ping and gw_ping.status == "OK" else (_s.AMBER if gw_ping and gw_ping.status == "SLOW" else _s.RED)
        self._update_stat(self._diag_gw_lbl, gw_str, gw_col)

        speed_str = (
            f"{result.download_mbps:.1f} Mbps"
            if result.download_mbps >= 1
            else (f"{result.download_mbps * 1000:.0f} Kbps" if result.download_mbps > 0 else "—")
        )
        self._update_stat(self._diag_speed_lbl, speed_str, _s.GREEN if result.download_mbps > 0 else _s.RED)
        self._update_stat(self._diag_public_lbl, result.public_ip or "—", _s.BLUE if result.public_ip else _s.RED)

        sys_dns = next((d for d in result.dns_results if d.server == "System DNS"), None)
        dns_str = f"{sys_dns.latency_ms:.0f} ms" if sys_dns and sys_dns.latency_ms >= 0 else "—"
        dns_col = _s.GREEN if sys_dns and sys_dns.status == "OK" else (_s.AMBER if sys_dns and sys_dns.status == "SLOW" else _s.RED)
        self._update_stat(self._diag_dns_lbl, dns_str, dns_col)

        self._diag_status_lbl.setText(f"Diagnostics complete.  {result.plain_verdict}")
        self._btn_diag.setEnabled(True)

        # DNS Leak
        leak = getattr(result, "dns_leak", None)
        self._diag_leak_table.setRowCount(0)
        if leak:
            self._diag_leak_lbl.setText(leak.plain_verdict)
            _s.themed_ss(self._diag_leak_lbl, lambda d=leak.leak_detected: (
                f"color:{_s.RED if d else _s.GREEN}; font-size:11px; padding-left:10px;"))
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
        if hasattr(self, "_security_overview_page"):
            self._security_overview_page.on_cred_result(res)
        flags = res.risk_flags
        self._cred_verdict.setText(res.plain_verdict + (f"\n⚠ {' | '.join(flags)}" if flags else ""))
        _s.themed_ss(self._cred_verdict, lambda f=bool(flags): (
            f"color:{_s.RED if f else _s.GREEN};font-size:11px;font-weight:bold;padding:4px;"
            f"background:{_s.BG_CARD};border-radius:4px;"
        ))
        self._cred_verdict.show()
        self._cred_status.setText("Credentialed scan complete.")
        self._nav_set_scan_state(L.LOGIN_TEST, "fresh", ts=time.time(), verdict=res.plain_verdict)

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
        self._nav_set_scan_state(L.FULL_DEVICE_DISCOVERY, "fresh", ts=time.time(), verdict=res.plain_verdict)
        _store_ref = getattr(self, "_store", None)
        for dev in res.devices:
            r = self._recon_disc_table.rowCount()
            self._recon_disc_table.insertRow(r)
            ms = f"{dev.response_ms:.0f}" if dev.response_ms else ""
            for c, v in enumerate([dev.ip, dev.mac, dev.hostname,
                                    ", ".join(dev.discovery_methods), ms]):
                self._recon_disc_table.setItem(r, c, _TWI(v))
            if _store_ref and dev.response_ms > 0 and dev.ip:
                try:
                    record_rtt(_store_ref, dev.ip, dev.response_ms)
                except Exception:
                    pass  # non-fatal — table may not exist on schema upgrade

    def _on_smb_result(self, res):
        from PyQt6.QtWidgets import QTableWidgetItem as _TWI
        flags = res.risk_flags
        _smb_sev = "RED" if any("Anonymous" in f or "DC" in f for f in flags) else ("AMBER" if flags else "GREEN")
        self._smb_verdict.setText(res.plain_verdict + (f"\n⚠ {' | '.join(flags)}" if flags else ""))
        _s.themed_ss(self._smb_verdict, lambda tk=_smb_sev: (
            f"color:{getattr(_s, tk)};font-size:11px;font-weight:bold;padding:4px;"
            f"background:{_s.BG_CARD};border-radius:4px;"
        ))
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
                    item.setForeground(QColor(_s.RED))
                self._recon_smb_shares_table.setItem(r, c, item)

        for u in res.users:
            r = self._recon_smb_users_table.rowCount()
            self._recon_smb_users_table.insertRow(r)
            for c, v in enumerate([u.username, u.uid, u.full_name, u.last_logon]):
                self._recon_smb_users_table.setItem(r, c, _TWI(v))

    # ── M1 table / mesh enrichment helpers (Sprint 18) ─────────────────────────

    def _m1_highlight_mac(self, mac: str) -> None:
        """Scroll the Devices table to the row matching `mac` and select it."""
        if not hasattr(self, "_m1_table"):
            return
        mac_lower = mac.lower()
        for row in range(self._m1_table.rowCount()):
            item = self._m1_table.item(row, 2)  # MAC Address column
            if item and item.text().lower() == mac_lower:
                self._m1_table.selectRow(row)
                self._m1_table.scrollToItem(
                    item, self._m1_table.ScrollHint.PositionAtCenter
                )
                break

    def _effective_mesh_render_params(self) -> tuple:
        """Return (mesh_units, mesh_enrichment) merging native and plugin sources.

        Native MeshWorker data takes priority; plugin node/client data is used
        as fallback so topology renders correctly for plugin-only mesh users.
        """
        _all_plugin: dict = {}
        for _pe in self._plugin_enrichments.values():
            _all_plugin.update(_pe)

        _eff_units  = getattr(self, "_mesh_units", None)
        _eff_enrich = self._mesh_enrichment or None

        if not _eff_units and _all_plugin:
            from types import SimpleNamespace as _SN
            from modules.deco_client import _norm_mac
            _pnodes_flat: list = []
            for _pnlist in getattr(self, "_plugin_nodes", {}).values():
                for _n in _pnlist:
                    _pnodes_flat.append(_SN(
                        name=_n.get("name", ""), role=_n.get("role", "satellite"),
                        mac=_norm_mac(_n.get("mac", "")), online=True,
                    ))
            if _pnodes_flat:
                _eff_units = _pnodes_flat
                _single = _pnodes_flat[0].name if len(_pnodes_flat) == 1 else ""
                _eff_enrich = {
                    mac: _SN(mac=mac, ip=c.get("ip", ""), name=c.get("hostname", ""),
                             band=c.get("band", ""),
                             unit_name=c.get("unit", "") or _single,
                             upload_kbps=0, download_kbps=0)
                    for mac, c in _all_plugin.items()
                }

        return _eff_units, _eff_enrich

    def _apply_mesh_enrichment(self) -> None:
        """Merge MeshClient and plugin client data into the M1 table rows."""
        # Build the full plugin MAC→client map first so the guard below can
        # check whether there is any data to apply (RULE-PL4).
        _all_plugin: dict = {}
        for _pe in self._plugin_enrichments.values():
            _all_plugin.update(_pe)
        # Require a scan result to do anything.
        if not self._m1_result:
            return
        from modules.deco_client import _norm_mac

        _mac_re = re.compile(r"^([0-9a-f]{2}[:\-]){5}[0-9a-f]{2}$", re.I)
        any_matched = False
        plugin_any_matched = False

        for row in range(self._m1_table.rowCount()):
            mac_item = self._m1_table.item(row, 2)
            if not mac_item:
                continue
            mc = self._mesh_enrichment.get(_norm_mac(mac_item.text()))
            if not mc:
                continue

            any_matched = True

            # Override hostname (col 1) with Deco-assigned name when it looks like a real name
            if mc.name and not _mac_re.match(mc.name):
                name_item = QTableWidgetItem(mc.name)
                name_item.setForeground(QColor(_s.TEXT_PRIMARY))
                name_item.setToolTip("Name assigned in Deco app")
                self._m1_table.setItem(row, 1, name_item)

            # Node column (col 6)
            node_item = QTableWidgetItem(mc.unit_name)
            node_item.setForeground(QColor(_s.TEXT_PRIMARY))
            self._m1_table.setItem(row, 6, node_item)

            # Band column (col 7) with speed tooltip
            band_item = QTableWidgetItem(mc.band)
            band_item.setForeground(QColor(_s.TEXT_PRIMARY))
            band_item.setToolTip(
                f"Upload:   {mc.upload_kbps} KB/s\n"
                f"Download: {mc.download_kbps} KB/s"
            )
            self._m1_table.setItem(row, 7, band_item)

        # Reveal Node and Band columns once any Deco data is present
        if any_matched:
            self._m1_table.setColumnHidden(6, False)
            self._m1_table.setColumnHidden(7, False)
            if self._m1_group_by_node:
                self._regroup_m1_by_satellite()

        # Plugin enrichment — update hostname column for any matching MAC or IP
        plugin_enrichment = _all_plugin
        plugin_name = getattr(self, "_plugin_hardware_name", "plugin")
        if plugin_enrichment:
            _gw_ip_guard = self._net_info.get("gateway") if self._net_info else None
            # Build IP index as fallback for MAC-randomized devices (iOS/Android)
            plugin_by_ip = {c.get("ip"): c for c in plugin_enrichment.values() if c.get("ip")}
            for row in range(self._m1_table.rowCount()):
                ip_item  = self._m1_table.item(row, 0)
                row_ip   = ip_item.text() if ip_item else ""
                mac_item = self._m1_table.item(row, 2)
                pc = plugin_enrichment.get(_norm_mac(mac_item.text())) if mac_item else None
                if pc is None and ip_item:
                    pc = plugin_by_ip.get(row_ip)
                if not pc:
                    continue
                plugin_any_matched = True
                # Backfill MAC into the table row when ARP scan left it blank
                if (not mac_item or not mac_item.text()) and pc.get("mac"):
                    _mac_fill = QTableWidgetItem(pc["mac"])
                    _mac_fill.setForeground(QColor(_s.TEXT_PRIMARY))
                    _mac_fill.setToolTip(f"MAC from {plugin_name}")
                    self._m1_table.setItem(row, 2, _mac_fill)
                # Never overwrite the gateway row's hostname with a client hostname
                # from the plugin.  Band/node enrichment is still valid for the router.
                if not (_gw_ip_guard and row_ip == _gw_ip_guard):
                    hostname = pc.get("hostname", "")
                    if hostname and not _mac_re.match(hostname):
                        name_item = QTableWidgetItem(hostname)
                        name_item.setForeground(QColor(_s.TEXT_PRIMARY))
                        name_item.setToolTip(f"Name from {plugin_name}")
                        self._m1_table.setItem(row, 1, name_item)
                # Fall back to hw name so single-AP plugins still enable grouping
                unit = pc.get("unit", "") or plugin_name
                if unit:
                    node_item = QTableWidgetItem(unit)
                    node_item.setForeground(QColor(_s.TEXT_PRIMARY))
                    node_item.setToolTip(f"Node from {plugin_name}")
                    self._m1_table.setItem(row, 6, node_item)
                    self._m1_table.setColumnHidden(6, False)
                band = pc.get("band", "")
                if band:
                    band_item = QTableWidgetItem(band)
                    band_item.setForeground(QColor(_s.TEXT_PRIMARY))
                    band_item.setToolTip(f"Band from {plugin_name}")
                    self._m1_table.setItem(row, 7, band_item)
                    self._m1_table.setColumnHidden(7, False)

        if plugin_any_matched and self._m1_group_by_node:
            self._regroup_m1_by_satellite()

        # Mirror enrichment onto DeviceInfo objects so exports include it
        for d in self._m1_result.get("devices", []):
            mac = _norm_mac(d.mac if not isinstance(d, dict) else d.get("mac", ""))
            mc = self._mesh_enrichment.get(mac)
            if mc:
                if isinstance(d, dict):
                    d["mesh_unit"]      = mc.unit_name
                    d["mesh_band"]      = mc.band
                    d["mesh_up_kbps"]   = mc.upload_kbps
                    d["mesh_down_kbps"] = mc.download_kbps
                else:
                    d.mesh_unit      = mc.unit_name
                    d.mesh_band      = mc.band
                    d.mesh_up_kbps   = mc.upload_kbps
                    d.mesh_down_kbps = mc.download_kbps

        # Mirror plugin band/unit onto DeviceInfo objects so exports include them
        for d in self._m1_result.get("devices", []):
            _dmac = _norm_mac(d.mac if not isinstance(d, dict) else d.get("mac", ""))
            _pc = _all_plugin.get(_dmac)
            if not _pc:
                continue
            _pu, _pb = _pc.get("unit", ""), _pc.get("band", "")
            if _pu:
                if isinstance(d, dict): d["mesh_unit"] = _pu
                else: d.mesh_unit = _pu
            if _pb:
                if isinstance(d, dict): d["mesh_band"] = _pb
                else: d.mesh_band = _pb

        # Sync every enriched hostname from the table back onto the DeviceInfo
        # objects so the topology render sees the same names as the Devices table.
        # Keyed by IP (not MAC) to avoid hostname collision when two devices share
        # the same MAC entry (proxy ARP / gateway MAC misidentification).
        _sync_gw_ip = self._net_info.get("gateway") if self._net_info else None
        _ip_to_host: dict = {}
        for _r in range(self._m1_table.rowCount()):
            _h  = self._m1_table.item(_r, 1)
            _ip = self._m1_table.item(_r, 0)
            if _h and _ip and _ip.text() and _ip.text() != "—":
                txt = _h.text().strip()
                if txt and txt != "—":
                    _ip_to_host[_ip.text()] = txt
        for _d in self._m1_result.get("devices", []):
            _dip = _d.ip if not isinstance(_d, dict) else _d.get("ip", "")
            if _sync_gw_ip and _dip == _sync_gw_ip:
                continue  # never overwrite gateway hostname from table-cell sync
            if _dip in _ip_to_host:
                if isinstance(_d, dict):
                    _d["hostname"] = _ip_to_host[_dip]
                else:
                    _d.hostname = _ip_to_host[_dip]

        # Re-classify any device still showing "Unknown Device" that now has
        # a usable hostname from mesh/plugin enrichment.
        try:
            from modules.device_classifier import classify_registry_first as _cd
            from PyQt6.QtGui import QColor as _QC
            from PyQt6.QtWidgets import QTableWidgetItem as _QTI
            _mac_to_row: dict = {}
            for _r in range(self._m1_table.rowCount()):
                _mi = self._m1_table.item(_r, 2)
                if _mi and _mi.text():
                    _mac_to_row[_norm_mac(_mi.text())] = _r
            for _d in self._m1_result.get("devices", []):
                _cur_type = (_d.device_type if not isinstance(_d, dict) else _d.get("device_type", "")) or ""
                if _cur_type and _cur_type != "Unknown Device":
                    continue
                _is_dict = isinstance(_d, dict)
                _new_type = _cd(
                    mac=_d.get("mac", "") if _is_dict else getattr(_d, "mac", ""),
                    vendor=_d.get("vendor", "") if _is_dict else getattr(_d, "vendor", ""),
                    hostname=_d.get("hostname", "") if _is_dict else getattr(_d, "hostname", ""),
                    open_ports=set(_d.get("open_ports", []) if _is_dict else (getattr(_d, "open_ports", []) or [])),
                    os_family=_d.get("os_family", "") if _is_dict else getattr(_d, "os_family", ""),
                )
                if not _new_type or _new_type == "Unknown Device":
                    continue
                if isinstance(_d, dict):
                    _d["device_type"] = _new_type
                else:
                    _d.device_type = _new_type
                _dmac2 = _norm_mac(_d.mac if not isinstance(_d, dict) else _d.get("mac", ""))
                _row2 = _mac_to_row.get(_dmac2)
                if _row2 is not None:
                    _ti = _QTI(_new_type)
                    _ti.setForeground(_QC(_s.TEXT_PRIMARY))
                    _ti.setToolTip("Device type inferred from hostname")
                    self._m1_table.setItem(_row2, 5, _ti)

            # Sync device_type cells from DeviceInfo for all devices that have a
            # known type — guards against the race where the table cell was written
            # from a stale DeviceInfo before is_gateway classification ran.
            for _d in self._m1_result.get("devices", []):
                _dip   = _d.ip         if not isinstance(_d, dict) else _d.get("ip", "")
                _dtype = (_d.device_type if not isinstance(_d, dict) else _d.get("device_type", "")) or ""
                if not _dtype or _dtype == "Unknown Device":
                    continue
                for _r in range(self._m1_table.rowCount()):
                    _ri = self._m1_table.item(_r, 0)
                    if _ri and _ri.text() == _dip:
                        _ti = _QTI(_dtype)
                        _ti.setForeground(_QC(_s.TEXT_PRIMARY))
                        self._m1_table.setItem(_r, 5, _ti)
                        break
        except Exception:
            pass  # non-fatal — enrichment re-classification is best-effort

        # Refresh the Network Info tab device table with enriched hostnames
        try:
            self._net_devices_table.setRowCount(0)
            for _d in self._m1_result.get("devices", []):
                _level  = _d.risk_level if not isinstance(_d, dict) else _d.get("risk_level", "UNKNOWN")
                _ip     = _d.ip         if not isinstance(_d, dict) else _d.get("ip", "?")
                _host   = _d.hostname   if not isinstance(_d, dict) else _d.get("hostname", "")
                _mac    = _d.mac        if not isinstance(_d, dict) else _d.get("mac", "?")
                _vendor = _d.vendor     if not isinstance(_d, dict) else _d.get("vendor", "Unknown")
                _add_row(self._net_devices_table, [_ip, _host or "—", _mac, _vendor, _level], _level)
        except Exception:
            pass  # non-fatal

        # Refresh AvailabilityWorker targets so Uptime page labels use enriched names
        try:
            if hasattr(self, "_avail_worker") and self._m1_result:
                from modules.availability_monitor import TargetConfig
                _targets = []
                for _d in self._m1_result.get("devices", []):
                    _ip  = _d.ip       if not isinstance(_d, dict) else _d.get("ip", "")
                    _mac = _d.mac      if not isinstance(_d, dict) else _d.get("mac", "")
                    _hn  = _d.hostname if not isinstance(_d, dict) else _d.get("hostname", "")
                    if _ip:
                        _targets.append(TargetConfig(
                            host=_ip, mac=_mac or None,
                            hostname=_hn or None, label=_hn or _ip,
                        ))
                if _targets:
                    self._avail_worker.set_targets(_targets)
        except Exception:
            pass  # non-fatal

        # Refresh MAC → device-name label map for App Traffic and Live Bandwidth
        # so both show hostnames/vendors instead of raw MAC addresses.
        try:
            _label_map: dict = {}
            for _d in self._m1_result.get("devices", []):
                _mac    = _d.mac      if not isinstance(_d, dict) else _d.get("mac", "")
                _hn     = _d.hostname if not isinstance(_d, dict) else _d.get("hostname", "")
                _vendor = _d.vendor   if not isinstance(_d, dict) else _d.get("vendor", "")
                if _mac:
                    _label_map[_mac.lower()] = _hn or _vendor or _mac
            # This machine's own network adapters — overlay "This PC" labels so
            # App Traffic / Bandwidth Usage / Timeline never show a bare MAC for
            # traffic that originates from the box the app is running on.
            from modules.utils_net import get_local_mac_label_map
            _label_map.update(get_local_mac_label_map())
            if _label_map:
                if hasattr(self, "_app_traffic_page"):
                    self._app_traffic_page.set_label_map(_label_map)
                if getattr(self, "_bw_worker", None) is not None:
                    self._bw_worker.label_map = _label_map
                if hasattr(self, "_timeline_page"):
                    self._timeline_page.set_label_map(_label_map)
        except Exception:
            pass  # non-fatal

        # Re-render topology — native mesh preferred; fall back to plugin node data
        try:
            gw_ip  = self._net_info.get("gateway")     if self._net_info else None
            gw_mac = self._net_info.get("gateway_mac") if self._net_info else None
            _eff_units, _eff_enrich = self._effective_mesh_render_params()
            _map_page = getattr(self, "_network_map_page", None)
            if _map_page is not None:
                # Merge enrichment into existing kwargs so segments/edges/lldp/diff are
                # preserved from the initial scan render — both classic and Cytoscape views
                # are updated via NetworkMapPage.render() in one call.
                _kw = dict(_map_page._last_render_kwargs) if _map_page._last_render_kwargs else {}
                _kw.update({
                    "devices":         self._m1_result.get("devices", []),
                    "gateway_ip":      gw_ip,
                    "gateway_mac":     gw_mac,
                    "mesh_units":      _eff_units,
                    "mesh_enrichment": _eff_enrich,
                    "modem_data":      getattr(self, "_last_modem_data", None),
                })
                _map_page.render(**_kw)
            else:
                self._topology_widget.render(
                    self._m1_result.get("devices", []), gw_ip, gw_mac,
                    mesh_units=_eff_units,
                    mesh_enrichment=_eff_enrich,
                    modem_data=getattr(self, "_last_modem_data", None),
                )
        except Exception:
            pass  # non-fatal

        # Update the Deco band-usage chips on the WiFi Networks page
        self._update_m4_deco_chips()

        # Synthesize M1 rows for mesh clients that ARP scan did not see
        # (e.g. phones connected to a satellite that did not respond to ARP)
        _existing_macs: set = set()
        _existing_ips: set = set()
        for _r in range(self._m1_table.rowCount()):
            _mi = self._m1_table.item(_r, 2)
            if _mi and _mi.text():
                _existing_macs.add(_norm_mac(_mi.text()))
            _ii = self._m1_table.item(_r, 0)
            if _ii and _ii.text() and _ii.text() != "—":
                _existing_ips.add(_ii.text().strip())
        _synth_added = False
        for _mc in self._mesh_enrichment.values():
            if _norm_mac(_mc.mac) in _existing_macs:
                continue
            # Also skip if the device's IP is already in the table (ARP found it without MAC)
            if _mc.ip and _mc.ip in _existing_ips:
                continue
            _add_row(
                self._m1_table,
                [_mc.ip or "—", _mc.name or "—", _mc.mac, "", "CLEAN",
                 "Wireless Client", _mc.unit_name, _mc.band,
                 "Mesh-only — not visible to ARP scan"],
                "CLEAN",
            )
            _synth_item = self._m1_table.item(self._m1_table.rowCount() - 1, 0)
            if _synth_item:
                _synth_item.setData(Qt.ItemDataRole.UserRole + 10, "__mesh_synth__")
            _existing_macs.add(_norm_mac(_mc.mac))
            _synth_added = True
        if _synth_added:
            self._m1_table.setColumnHidden(6, False)
            self._m1_table.setColumnHidden(7, False)

        # Synthesize rows for plugin-only clients not seen by ARP scan
        # (e.g. a phone connected to the router that didn't reply to ARP)
        _plugin_synth_added = False
        for _pmac, _pc in _all_plugin.items():
            if not _pmac or _pmac in _existing_macs:
                continue
            _pip   = _pc.get("ip", "") or "—"
            _phn   = _pc.get("hostname", "") or "—"
            if _pip == "—" and _phn == "—":
                continue  # nothing useful to show
            # Skip if the device's IP is already in the table (ARP found it without MAC)
            if _pip != "—" and _pip in _existing_ips:
                continue
            _add_row(
                self._m1_table,
                [_pip, _phn, _pmac, "", "CLEAN",
                 "Wireless Client", _pc.get("unit", ""), _pc.get("band", ""),
                 "Plugin-only — not visible to ARP scan"],
                "CLEAN",
            )
            _psi = self._m1_table.item(self._m1_table.rowCount() - 1, 0)
            if _psi:
                _psi.setData(Qt.ItemDataRole.UserRole + 10, "__plugin_synth__")
            _existing_macs.add(_pmac)
            _plugin_synth_added = True
        if _plugin_synth_added:
            self._m1_table.setColumnHidden(6, False)
            self._m1_table.setColumnHidden(7, False)

        # Regroup M1 table into collapsible satellite sections (only when toggle is ON)
        if (any_matched or _synth_added or plugin_any_matched or _plugin_synth_added) \
                and getattr(self, "_m1_group_by_node", False):
            self._regroup_m1_by_satellite()

    @pyqtSlot(bool)
    def _on_node_group_toggled(self, checked: bool) -> None:
        self._m1_group_by_node = checked
        QSettings("NetSentinel", "NetSentinel").setValue("devices/group_by_node", checked)
        if hasattr(self, "_m1_seg_list"):
            _s.themed_ss(
                self._m1_seg_list,
                self._m1_seg_inactive_ss if checked else self._m1_seg_active_ss,
            )
            _s.themed_ss(
                self._m1_seg_node,
                self._m1_seg_active_ss if checked else self._m1_seg_inactive_ss,
            )
        if checked:
            self._regroup_m1_by_satellite()
        else:
            self._m1_flatten_table()

    def _m1_flatten_table(self) -> None:
        """Strip satellite section headers — restore flat device list."""
        from PyQt6.QtGui import QColor as _QC
        from ui.dashboard import _color_for_level
        rows_data = []
        for row in range(self._m1_table.rowCount()):
            first = self._m1_table.item(row, 0)
            if first and first.data(Qt.ItemDataRole.UserRole) == "__sat_header__":
                continue
            cells, risk = [], "CLEAN"
            for col in range(self._m1_table.columnCount()):
                item = self._m1_table.item(row, col)
                cells.append({
                    "text":    item.text()    if item else "",
                    "tooltip": item.toolTip() if item else "",
                })
            risk_item = self._m1_table.item(row, 4)
            if risk_item:
                risk = risk_item.text().strip()
            rows_data.append({"cells": cells, "risk": risk})

        if not rows_data:
            return
        self._m1_table.setSortingEnabled(False)
        self._m1_table.setRowCount(0)
        self._m1_group_btn.setVisible(False)
        for rd in rows_data:
            r = self._m1_table.rowCount()
            self._m1_table.insertRow(r)
            rc = _color_for_level(rd["risk"])
            high = rd["risk"] in ("HIGH", "STORM")
            for col, cell in enumerate(rd["cells"]):
                item = QTableWidgetItem(cell["text"])
                item.setForeground(_QC(rc if (col == 4 or high) else _s.TEXT_PRIMARY))
                if cell["tooltip"]:
                    item.setToolTip(cell["tooltip"])
                self._m1_table.setItem(r, col, item)
        self._m1_table.resizeColumnsToContents()
        self._m1_table.setSortingEnabled(True)

    def _regroup_m1_by_satellite(self) -> None:
        """Rebuild M1 table with collapsible satellite section header rows."""
        from PyQt6.QtGui import QColor, QFont
        from ui.dashboard import _color_for_level

        # Collect device row data — skip any existing header rows
        rows_data = []
        for row in range(self._m1_table.rowCount()):
            first = self._m1_table.item(row, 0)
            if first and first.data(Qt.ItemDataRole.UserRole) == "__sat_header__":
                continue
            cells = []
            for col in range(self._m1_table.columnCount()):
                item = self._m1_table.item(row, col)
                cells.append({
                    "text":    item.text() if item else "",
                    "tooltip": item.toolTip() if item else "",
                })
            node_item = self._m1_table.item(row, 6)
            node = (node_item.text().strip() if node_item else "") or "__unassigned__"
            risk_item = self._m1_table.item(row, 4)
            risk = risk_item.text().strip() if risk_item else "CLEAN"
            rows_data.append({"cells": cells, "node": node, "risk": risk})

        if not rows_data:
            return

        # Group by node
        groups: dict = {}
        for rd in rows_data:
            groups.setdefault(rd["node"], []).append(rd)

        sorted_nodes = sorted(k for k in groups if k != "__unassigned__")
        has_named_nodes = bool(sorted_nodes)
        self._m1_has_named_nodes = has_named_nodes
        if "__unassigned__" in groups:
            sorted_nodes.append("__unassigned__")

        # Rebuild table — sorting must be off to prevent sentinel rows from scrambling
        self._m1_table.setSortingEnabled(False)
        self._m1_table.setRowCount(0)
        n_cols = self._m1_table.columnCount()

        for node_name in sorted_nodes:
            device_rows = groups[node_name]
            if node_name == "__unassigned__":
                display_name = "Other / Direct" if has_named_nodes else "All devices"
            else:
                display_name = node_name
            expanded = self._m1_sat_expanded.get(node_name, True)
            arrow = "▼" if expanded else "▶"
            nc = len(device_rows)

            # Header row
            hdr_row = self._m1_table.rowCount()
            self._m1_table.insertRow(hdr_row)
            hdr_text = f"   {arrow}  {display_name}   ·   {nc} device{'s' if nc != 1 else ''}"
            hdr_item = QTableWidgetItem(hdr_text)
            hdr_item.setData(Qt.ItemDataRole.UserRole, "__sat_header__")
            hdr_item.setData(Qt.ItemDataRole.UserRole + 1, node_name)
            hdr_item.setForeground(QColor(_s.TEXT_PRIMARY))
            hdr_item.setBackground(QColor(_s.BG_DARK))
            f = QFont()
            f.setBold(True)
            f.setItalic(True)
            hdr_item.setFont(f)
            hdr_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._m1_table.setItem(hdr_row, 0, hdr_item)
            self._m1_table.setSpan(hdr_row, 0, 1, n_cols)
            self._m1_table.setRowHeight(hdr_row, 26)

            # Device rows
            for rd in device_rows:
                dev_row = self._m1_table.rowCount()
                self._m1_table.insertRow(dev_row)
                risk_color = _color_for_level(rd["risk"])
                high_risk = rd["risk"] in ("HIGH", "STORM")
                for col, cell in enumerate(rd["cells"]):
                    item = QTableWidgetItem(cell["text"])
                    if col == 4:
                        item.setForeground(QColor(risk_color))
                    elif high_risk:
                        item.setForeground(QColor(risk_color))
                    else:
                        item.setForeground(QColor(_s.TEXT_PRIMARY))
                    if cell["tooltip"]:
                        item.setToolTip(cell["tooltip"])
                    self._m1_table.setItem(dev_row, col, item)
                if not expanded:
                    self._m1_table.setRowHidden(dev_row, True)

        self._m1_grouping_active = True
        self._m1_group_btn.setVisible(True)
        # Sorting stays OFF in grouped mode — re-enabled by _m1_flatten_table on switch back
        # Connect click handler once
        if not getattr(self, "_m1_group_click_connected", False):
            self._m1_table.cellClicked.connect(self._m1_toggle_sat_section)
            self._m1_group_click_connected = True

    def _m1_toggle_sat_section(self, row: int, col: int) -> None:
        """Toggle a satellite section open/closed when its header row is clicked."""
        first = self._m1_table.item(row, 0)
        if not first or first.data(Qt.ItemDataRole.UserRole) != "__sat_header__":
            return
        node_name = first.data(Qt.ItemDataRole.UserRole + 1)
        expanded = not self._m1_sat_expanded.get(node_name, False)
        self._m1_sat_expanded[node_name] = expanded

        # Count device rows in this section (rows until next header or end)
        nc = 0
        next_row = row + 1
        while next_row < self._m1_table.rowCount():
            r_first = self._m1_table.item(next_row, 0)
            if r_first and r_first.data(Qt.ItemDataRole.UserRole) == "__sat_header__":
                break
            nc += 1
            next_row += 1

        _hn = getattr(self, "_m1_has_named_nodes", False)
        if node_name == "__unassigned__":
            display_name = "Other / Direct" if _hn else "All devices"
        else:
            display_name = node_name
        arrow = "▼" if expanded else "▶"
        first.setText(f"   {arrow}  {display_name}   ·   {nc} device{'s' if nc != 1 else ''}")

        for dev_row in range(row + 1, next_row):
            self._m1_table.setRowHidden(dev_row, not expanded)

        # Update button label
        self._m1_update_group_btn()

    def _m1_set_all_expanded(self, expanded: bool) -> None:
        """Show or hide all satellite sections without rebuilding the table."""
        for row in range(self._m1_table.rowCount()):
            first = self._m1_table.item(row, 0)
            if not first or first.data(Qt.ItemDataRole.UserRole) != "__sat_header__":
                continue
            node_name = first.data(Qt.ItemDataRole.UserRole + 1)
            self._m1_sat_expanded[node_name] = expanded

            # Count and show/hide following device rows
            nc = 0
            next_row = row + 1
            while next_row < self._m1_table.rowCount():
                r_first = self._m1_table.item(next_row, 0)
                if r_first and r_first.data(Qt.ItemDataRole.UserRole) == "__sat_header__":
                    break
                nc += 1
                next_row += 1

            _hn = getattr(self, "_m1_has_named_nodes", False)
            if node_name == "__unassigned__":
                display_name = "Other / Direct" if _hn else "All devices"
            else:
                display_name = node_name
            arrow = "▼" if expanded else "▶"
            first.setText(f"   {arrow}  {display_name}   ·   {nc} device{'s' if nc != 1 else ''}")
            for dev_row in range(row + 1, next_row):
                self._m1_table.setRowHidden(dev_row, not expanded)

    def _m1_toggle_all_groups(self) -> None:
        """Expand all if any are collapsed; collapse all if all are expanded."""
        all_expanded = bool(self._m1_sat_expanded) and all(
            self._m1_sat_expanded.get(n, False) for n in self._m1_sat_expanded
        )
        self._m1_set_all_expanded(not all_expanded)
        self._m1_update_group_btn()

    def _m1_update_group_btn(self) -> None:
        """Sync the expand/collapse button label with current state."""
        all_expanded = bool(self._m1_sat_expanded) and all(
            self._m1_sat_expanded.get(n, False) for n in self._m1_sat_expanded
        )
        self._m1_group_btn.setText("▼▼  Collapse All" if all_expanded else "▶▶  Expand All")

    def _on_dhcp_scan_result(self, scan_result: object) -> None:
        """
        Receive a completed DHCPScanResult and apply any VCI fingerprints to the
        Devices table.  The dhcp_detector.scan() already called update_cache(), so
        the module-level cache is populated; we just need to propagate upgrades into
        the live table and DeviceInfo objects.
        """
        try:
            from modules.dhcp_fingerprint import update_cache as _upd
            fps = getattr(scan_result, "fingerprints", {})
            if fps:
                _upd(fps)
        except Exception:
            pass  # non-fatal
        self._apply_dhcp_fingerprints()

    def _apply_dhcp_fingerprints(self) -> None:
        """
        For each device still showing 'Unknown Device', look up its MAC in the DHCP
        fingerprint cache.  If a high-confidence VCI match exists, upgrade device_type
        (and os_family when missing) and update the corresponding table cell.

        This runs after the DHCP scan window closes, so the cache is fully populated.
        Priority relative to other enrichment:
            is_gateway  →  Router/Gateway       (highest)
            MAC registry model hit              (specific model)
            DHCP VCI fingerprint (high conf)    ← this method
            Passive protocol observation        (next)
            OUI + hostname heuristics           (existing classifier)
            "Unknown Device"                    (fallback)
        """
        if not self._m1_result:
            return
        try:
            from modules.dhcp_fingerprint import get_fingerprint as _get_fp
            from modules.deco_client import _norm_mac
            from PyQt6.QtGui import QColor
            from PyQt6.QtWidgets import QTableWidgetItem as _QTI

            _mac_to_row: dict = {}
            if hasattr(self, "_m1_table"):
                for _r in range(self._m1_table.rowCount()):
                    _mi = self._m1_table.item(_r, 2)
                    if _mi and _mi.text():
                        _mac_to_row[_norm_mac(_mi.text())] = _r

            for _d in self._m1_result.get("devices", []):
                _cur_type = (
                    _d.device_type if not isinstance(_d, dict)
                    else _d.get("device_type", "")
                ) or ""
                if _cur_type and _cur_type != "Unknown Device":
                    continue  # already classified — don't overwrite

                _mac = (
                    _d.mac if not isinstance(_d, dict) else _d.get("mac", "")
                ) or ""
                if not _mac:
                    continue

                # Override guard — never touch user-overridden devices
                _store_ref2 = getattr(self, "_store", None)
                if _store_ref2:
                    try:
                        if _store_ref2.get_classification_override(_mac):
                            continue
                    except Exception:
                        pass  # non-fatal

                fp = _get_fp(_mac)
                if not fp or fp.confidence != "high" or not fp.device_hint:
                    continue

                # Upgrade device_type on DeviceInfo
                if isinstance(_d, dict):
                    _d["device_type"] = fp.device_hint
                    if fp.os_hint and not _d.get("os_family"):
                        _d["os_family"] = fp.os_hint
                else:
                    _d.device_type = fp.device_hint
                    if fp.os_hint and not getattr(_d, "os_family", ""):
                        try:
                            _d.os_family = fp.os_hint
                        except AttributeError:
                            pass  # dataclass may be frozen

                # Record class upgrade in device audit trail
                _store_ref = getattr(self, "_store", None)
                if _store_ref and _mac:
                    try:
                        from modules.device_tracker import record_event as _rec_ev
                        _rec_ev(_mac, "class_changed",
                                _cur_type or "Unknown Device", fp.device_hint,
                                "dhcp", _store_ref)
                    except Exception:
                        pass  # non-fatal — audit trail is best-effort

                # Update Device Type cell (col 5) in the Devices table
                _row = _mac_to_row.get(_norm_mac(_mac))
                if _row is not None and hasattr(self, "_m1_table"):
                    _ti = _QTI(fp.device_hint)
                    _ti.setForeground(QColor(_s.TEXT_PRIMARY))
                    _ti.setToolTip(fp.evidence or "Device type from DHCP VCI fingerprint")
                    self._m1_table.setItem(_row, 5, _ti)

        except Exception:
            pass  # non-fatal — DHCP fingerprint enrichment is best-effort

    def _on_passive_observation(self, obs: object) -> None:
        """
        Handle a PassiveObservation from the passive listener.

        Upgrades the device_type of any scanned device that currently shows
        "Unknown Device" or has a lower-confidence classification.
        Only "high" confidence passive observations replace existing labels.
        """
        try:
            from modules.device_classifier import classify_from_observation as _cfo
            from PyQt6.QtGui import QColor
            from PyQt6.QtWidgets import QTableWidgetItem as _QTI

            if not self._m1_result:
                return

            obs_ip   = getattr(obs, "ip", "")
            obs_conf = getattr(obs, "confidence", "low")
            if not obs_ip:
                return

            new_result = _cfo(obs)
            new_type   = new_result.device_type
            if not new_type or new_type == "Unknown Device":
                return

            for _d in self._m1_result.get("devices", []):
                _dip = _d.ip if not isinstance(_d, dict) else _d.get("ip", "")
                if _dip != obs_ip:
                    continue

                # Override guard — never touch user-overridden devices
                _mac_ov = (
                    _d.get("mac", "") if isinstance(_d, dict)
                    else getattr(_d, "mac", "")
                ) or ""
                _store_ov = getattr(self, "_store", None)
                if _mac_ov and _store_ov:
                    try:
                        if _store_ov.get_classification_override(_mac_ov):
                            break
                    except Exception:
                        pass  # non-fatal

                _cur = (_d.device_type if not isinstance(_d, dict)
                        else _d.get("device_type", "")) or ""
                # Only overwrite if current label is unknown or the observation is high confidence
                if _cur and _cur != "Unknown Device" and obs_conf != "high":
                    break
                # Don't overwrite a high-confidence existing label with a low-confidence one
                if _cur and _cur not in ("Unknown Device", "") and obs_conf == "low":
                    break

                if isinstance(_d, dict):
                    _d["device_type"] = new_type
                    _methods = _d.get("discovery_methods", [])
                    _proto = getattr(obs, "protocol", "")
                    _tag   = f"passive-{_proto}" if _proto else "passive"
                    if _tag not in _methods:
                        _methods.append(_tag)
                        _d["discovery_methods"] = _methods
                else:
                    _d.device_type = new_type
                    _proto = getattr(obs, "protocol", "")
                    _tag   = f"passive-{_proto}" if _proto else "passive"
                    _methods = list(getattr(_d, "discovery_methods", None) or [])
                    if _tag not in _methods:
                        _methods.append(_tag)
                        try:
                            _d.discovery_methods = _methods
                        except AttributeError:
                            pass  # dataclass may be frozen in some code paths

                # Record class upgrade in device audit trail
                _mac_str = (_d.get("mac", "") if isinstance(_d, dict)
                            else getattr(_d, "mac", "")) or ""
                _store_ref = getattr(self, "_store", None)
                if _store_ref and _mac_str:
                    try:
                        from modules.device_tracker import record_event as _rec_ev
                        _rec_ev(_mac_str, "class_changed",
                                _cur or "Unknown Device", new_type,
                                "passive", _store_ref)
                    except Exception:
                        pass  # non-fatal — audit trail is best-effort

                # Update the M1 table cell
                if hasattr(self, "_m1_table"):
                    for _r in range(self._m1_table.rowCount()):
                        _ri = self._m1_table.item(_r, 0)
                        if _ri and _ri.text() == obs_ip:
                            _ti = _QTI(new_type)
                            _ti.setForeground(QColor(_s.TEXT_PRIMARY))
                            _summary = getattr(obs, "raw_summary", "")
                            _ti.setToolTip(
                                f"Observed via {_summary}" if _summary else
                                f"Observed via passive-{getattr(obs, 'protocol', '')}"
                            )
                            self._m1_table.setItem(_r, 5, _ti)
                            break
                break
        except Exception:
            pass  # non-fatal — passive enrichment is best-effort

    def _apply_passive_observations(self) -> None:
        """
        Apply all buffered passive observations to the current scan result.

        Called once after a full scan completes so that observations that
        arrived before the scan was done are not lost.
        """
        try:
            from modules.passive_observer import get_observations as _get_obs
            for _obs in _get_obs():
                self._on_passive_observation(_obs)
        except Exception:
            pass  # non-fatal

    @pyqtSlot(str)
    def _filter_m1_by_nl(self, text: str):
        """Filter Device Fingerprinter rows using the NL query engine."""
        text = text.strip()
        # Clear filter — restore each section's individual collapsed/expanded state
        if not text:
            if self._m1_grouping_active:
                for row in range(self._m1_table.rowCount()):
                    first = self._m1_table.item(row, 0)
                    if first and first.data(Qt.ItemDataRole.UserRole) == "__sat_header__":
                        self._m1_table.setRowHidden(row, False)
                        node_name = first.data(Qt.ItemDataRole.UserRole + 1)
                        exp = self._m1_sat_expanded.get(node_name, False)
                        next_row = row + 1
                        while next_row < self._m1_table.rowCount():
                            r = self._m1_table.item(next_row, 0)
                            if r and r.data(Qt.ItemDataRole.UserRole) == "__sat_header__":
                                break
                            self._m1_table.setRowHidden(next_row, not exp)
                            next_row += 1
            else:
                for row in range(self._m1_table.rowCount()):
                    self._m1_table.setRowHidden(row, False)
            if self._m1_result:
                self._m1_status.setText(
                    f"✓  {self._m1_result.get('total_count', 0)} devices scanned — "
                    f"{self._m1_result.get('high_risk_count', 0)} HIGH RISK"
                )
            return
        if not self._m1_result:
            return
        try:
            from modules.nl_query import query as _nl_query
            devices = self._m1_result.get("devices", [])
            result = _nl_query(devices, text)
            if result.error:
                self._m1_status.setText(f"⚠  {result.error}")
                return
            matched_ips = {
                (m.device.ip if not isinstance(m.device, dict) else m.device.get("ip", ""))
                for m in result.matches
            }
            for row in range(self._m1_table.rowCount()):
                first = self._m1_table.item(row, 0)
                if first and first.data(Qt.ItemDataRole.UserRole) == "__sat_header__":
                    self._m1_table.setRowHidden(row, False)  # always keep headers visible
                    continue
                ip_item = first
                ip = ip_item.text() if ip_item else ""
                self._m1_table.setRowHidden(row, ip not in matched_ips)
            self._m1_status.setText(
                f"Filter: {len(matched_ips)} match(es) — {result.explanation}"
            )
        except Exception as exc:
            self._m1_status.setText(f"Filter error: {exc}")

