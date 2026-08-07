"""
MetricStore device-inventory write mixin — device_ip_history, device_annotations,
device_events (audit trail), topology_snapshots, device_state, device_event,
known_device, and classification-override write methods.

Extracted from modules/metric_store.py (Phase 3 split, per that module's own
"Split plan" note) to keep metric_store.py under the RULE-AH1 780-line budget.
_DeviceWritesMixin is used via multiple inheritance in MetricStore — all
symbols remain accessible as MetricStore instance methods as before.

Requires self._execute_write(sql, params) to be provided by the host class.
"""
from __future__ import annotations

import datetime
import time
from typing import List, Optional


class _DeviceWritesMixin:
    """Write methods for device inventory / IP history / stability / topology."""

    # ── Write: device IP history / stability ──────────────────────────────────

    def record_ip_observation(
        self,
        mac: str,
        ip: str,
        ts: Optional[int] = None,
    ) -> None:
        """Upsert mac+ip combo into device_ip_history (single write path — see
        DeviceTracker.process_scan docstring for the last-seen/stability invariant)."""
        if not mac or not ip:
            return
        now = ts or int(time.time())
        now_str = datetime.datetime.utcfromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
        self._execute_write(
            """
            INSERT INTO device_ip_history (mac, ip, first_seen, last_seen, seen_count)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(mac, ip) DO UPDATE SET
                last_seen  = excluded.last_seen,
                seen_count = seen_count + 1
            """,
            (mac.lower(), ip, now_str, now_str),
        )

    def get_ip_history_stats(self, mac: str) -> List[tuple]:
        """Return [(ip, seen_count), ...] for a MAC from device_ip_history."""
        return self._execute_read(
            "SELECT ip, seen_count FROM device_ip_history WHERE mac = ?",
            (mac.lower(),),
        )

    def get_total_seen_count(self, mac: str) -> int:
        """Return SUM(seen_count) across all IPs a MAC has been observed at."""
        rows = self._execute_read(
            "SELECT COALESCE(SUM(seen_count), 0) FROM device_ip_history WHERE mac = ?",
            (mac.lower(),),
        )
        return int(rows[0][0]) if rows else 0

    # ── Write/read: device annotations ────────────────────────────────────────

    def save_device_annotations(self, mac: str, **kwargs) -> None:
        """Upsert user_label/location/owner/notes/asset_tag for a MAC."""
        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        self._execute_write(
            """
            INSERT INTO device_annotations (mac, user_label, location, owner, notes, asset_tag, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(mac) DO UPDATE SET
                user_label = COALESCE(NULLIF(excluded.user_label, ''), user_label),
                location   = COALESCE(NULLIF(excluded.location, ''),   location),
                owner      = COALESCE(NULLIF(excluded.owner, ''),      owner),
                notes      = COALESCE(NULLIF(excluded.notes, ''),      notes),
                asset_tag  = COALESCE(NULLIF(excluded.asset_tag, ''),  asset_tag),
                updated_at = excluded.updated_at
            """,
            (
                mac.lower(),
                kwargs.get("user_label", ""),
                kwargs.get("location", ""),
                kwargs.get("owner", ""),
                kwargs.get("notes", ""),
                kwargs.get("asset_tag", ""),
                now,
            ),
        )

    # ── Write: device change audit trail (device_events table) ───────────────
    # Distinct from record_device_event()/query_device_events(), which write the
    # JOINED/LEFT/UP/DOWN state-change table `device_event` (singular).

    def record_device_change_event(
        self,
        mac: str,
        event_type: str,
        old_value: str,
        new_value: str,
        source: str,
    ) -> None:
        """Write a row to the device_events audit table."""
        if not mac:
            return
        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        self._execute_write(
            """
            INSERT INTO device_events (mac, event_type, old_value, new_value, source, ts)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (mac.lower(), event_type, old_value or "", new_value or "", source or "", now),
        )

    # ── Write: topology snapshots ─────────────────────────────────────────────

    def save_topology_snapshot(self, ts: int, data_json: str, keep: int = 10) -> None:
        """Persist a topology snapshot row and prune to the `keep` most recent."""
        self._execute_write(
            "INSERT INTO topology_snapshots (ts, data_json) VALUES (?, ?)",
            (ts, data_json),
        )
        self._execute_write(
            "DELETE FROM topology_snapshots WHERE id NOT IN "
            "(SELECT id FROM topology_snapshots ORDER BY ts DESC LIMIT ?)",
            (keep,),
        )

    def update_device_stability(
        self,
        mac: str,
        scan_count: int,
        ip_stability: float,
        inferred_role: Optional[str] = None,
    ) -> None:
        """Persist scan_count/ip_stability/inferred_role for a MAC in known_device.

        Never clears an existing inferred_role — pass None to leave it untouched."""
        if inferred_role is not None:
            self._execute_write(
                """
                UPDATE known_device
                SET scan_count    = ?,
                    ip_stability  = ?,
                    inferred_role = ?
                WHERE mac = ?
                """,
                (scan_count, ip_stability, inferred_role, mac.lower()),
            )
        else:
            self._execute_write(
                """
                UPDATE known_device
                SET scan_count   = ?,
                    ip_stability = ?
                WHERE mac = ?
                """,
                (scan_count, ip_stability, mac.lower()),
            )

    # ── Write: device state snapshots ────────────────────────────────────────

    def record_device_state(
        self,
        ip: str,
        mac: Optional[str],
        hostname: Optional[str],
        state: str,
        rtt_ms: Optional[float] = None,
        ts: Optional[int] = None,
    ) -> None:
        now = ts or int(time.time())
        self._execute_write(
            "INSERT INTO device_state(ts, ip, mac, hostname, state, rtt_ms) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (now, ip, mac, hostname, state.upper(), rtt_ms),
        )

    # ── Write: device events ──────────────────────────────────────────────────

    def record_device_event(
        self,
        ip: str,
        event_type: str,
        mac: Optional[str] = None,
        detail: Optional[str] = None,
        ts: Optional[int] = None,
    ) -> None:
        now = ts or int(time.time())
        _valid = {"JOINED", "LEFT", "UP", "DOWN", "DEGRADED", "RECOVERED"}
        if event_type.upper() not in _valid:
            raise ValueError(f"event_type must be one of {_valid}, got {event_type!r}")
        self._execute_write(
            "INSERT INTO device_event(ts, ip, mac, event_type, detail) "
            "VALUES(?, ?, ?, ?, ?)",
            (now, ip, mac, event_type.upper(), detail),
        )

    # ── Write: known device inventory ─────────────────────────────────────────

    def upsert_known_device(
        self,
        mac: str,
        ip: Optional[str] = None,
        hostname: Optional[str] = None,
        vendor: Optional[str] = None,
        device_type: Optional[str] = None,
        is_authorized: Optional[bool] = True,
        ts: Optional[int] = None,
        services: Optional[str] = None,
        mac_randomized: Optional[bool] = None,
        confidence: Optional[float] = None,
        hostname_resolved_at: Optional[int] = None,
    ) -> None:
        now = ts or int(time.time())
        auth_val: Optional[int] = None if is_authorized is None else int(is_authorized)
        rand_val: Optional[int] = None if mac_randomized is None else int(mac_randomized)
        self._execute_write(
            """
            INSERT INTO known_device
                (mac, ip, hostname, vendor, device_type,
                 first_seen, last_seen, is_authorized,
                 services, mac_randomized, confidence, hostname_resolved_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, COALESCE(?, 1),
                   ?, COALESCE(?, 0), COALESCE(?, 0.0), ?)
            ON CONFLICT(mac) DO UPDATE SET
                ip            = COALESCE(excluded.ip, ip),
                hostname      = COALESCE(excluded.hostname, hostname),
                vendor        = COALESCE(excluded.vendor,   vendor),
                device_type   = COALESCE(excluded.device_type, device_type),
                last_seen     = excluded.last_seen,
                is_authorized = CASE WHEN ? IS NULL THEN is_authorized
                                     ELSE ? END,
                services      = COALESCE(excluded.services, services),
                mac_randomized = COALESCE(excluded.mac_randomized, mac_randomized),
                confidence    = COALESCE(excluded.confidence, confidence),
                hostname_resolved_at = COALESCE(excluded.hostname_resolved_at, hostname_resolved_at)
            """,
            (mac, ip, hostname, vendor, device_type, now, now, auth_val,
             services, rand_val, confidence, hostname_resolved_at,
             auth_val, auth_val),
        )

    def set_device_authorized(self, mac: str, authorized: bool) -> None:
        self._execute_write(
            "UPDATE known_device SET is_authorized = ? WHERE mac = ?",
            (int(authorized), mac),
        )

    # ── Write/read: per-device alert opt-in scope ────────────────────────────

    def set_device_alert_opt_in(self, mac: str, opt_in: bool) -> None:
        self._execute_write(
            "UPDATE known_device SET alert_opt_in = ? WHERE mac = ?",
            (int(opt_in), mac),
        )

    def is_device_alert_in_scope(self, identifier: str) -> bool:
        """True if device-scoped alerts are allowed for `identifier` (an IP or a MAC).

        Infrastructure-role devices are always in scope; everything else requires
        explicit opt-in. A device with no matching row is out of scope by default.

        Answers across ALL matching rows, not just the first. One IP routinely
        maps to several MACs — the reference network has three at
        192.168.68.64, one of them the mesh AP — so reading `rows[0]` made the
        verdict depend on row order, and reported the AP out of scope whenever a
        stale privacy MAC happened to sort first.

        The legacy gate — superseded by get_device_importance_tier() when
        `experimental/signal_quality_v2` is on, kept intact per RULE-EXP1.
        """
        rows = self._execute_read(
            "SELECT inferred_role, alert_opt_in FROM known_device WHERE ip = ? OR mac = ?",
            (identifier, identifier),
        )
        return any(
            row["inferred_role"] in ("gateway", "infrastructure")
            or bool(row["alert_opt_in"])
            for row in rows
        )

    def get_device_importance_tier(self, identifier: str) -> str:
        """Importance tier name for `identifier` (an IP or a MAC).

        Always recomputed from the row's current columns — never read back from
        a stored tier — because the `inferred_role` values this replaces are
        known to be wrong for 8 of 13 devices on the reference network. A device
        with no matching row is TRANSIENT, matching is_device_alert_in_scope()'s
        "unknown means out of scope" default.

        **Returns the HIGHEST tier among matching rows, not the first.** One IP
        routinely maps to several MACs — the reference network has three at
        192.168.68.64, one of them the mesh AP and two stale privacy MACs — and
        alerts are keyed by IP. Taking `rows[0]` (what is_device_alert_in_scope()
        does) would let arbitrary row order decide whether the gateway is
        alertable.
        """
        from modules.device_importance import Tier, classify_known_device

        rows = self._execute_read(
            "SELECT mac, ip, hostname, vendor, device_type, custom_name, is_pinned, "
            "mac_randomized, scan_count, ip_stability, inferred_role, alert_opt_in "
            "FROM known_device WHERE ip = ? OR mac = ?",
            (identifier, identifier),
        )
        if not rows:
            return Tier.TRANSIENT.value
        return max(
            (classify_known_device(dict(r)).tier for r in rows),
            default=Tier.TRANSIENT,
        ).value

    # ── Write/read: presence episodes (schema v22) ───────────────────────────

    def set_presence_state(
        self, mac: str, state: str, gone_notified_ts: Optional[int] = None
    ) -> None:
        """Record whether a MAC is currently present, and when LEFT was emitted.

        `gone_notified_ts` is always written, including when None — clearing it
        on return is what re-arms the device's NEXT absence. A "only overwrite
        when not None" COALESCE here would leave a stale stamp behind and
        silently suppress the following episode's LEFT forever.
        """
        if not mac:
            return
        self._execute_write(
            "UPDATE known_device SET presence_state = ?, gone_notified_ts = ? "
            "WHERE mac = ?",
            (state or None, gone_notified_ts, mac.lower()),
        )

    # ── Write/read: materialised importance tier (schema v22) ────────────────

    def refresh_importance_tiers(self) -> int:
        """Recompute `importance_tier`/`importance_source` for every row.

        Returns how many rows changed. One pass over the inventory rather than
        a per-device recompute on the scan path: the reference network has ~30
        rows, and the ranking layer wants the whole map at once anyway.

        **Recomputes; never reads the stored value.** The column is a cache for
        display and claim ranking, and the values it caches replaced an
        `inferred_role` that was wrong for 8 of 13 devices — trusting a stored
        verdict is the exact mistake device_importance exists to correct. The
        alert gate does not read this column at all; see
        get_device_importance_tier(), which recomputes per call.
        """
        from modules.device_importance import classify_known_device

        rows = self._execute_read(
            "SELECT mac, ip, hostname, vendor, device_type, custom_name, is_pinned, "
            "mac_randomized, scan_count, ip_stability, inferred_role, alert_opt_in, "
            "importance_tier, importance_source FROM known_device",
            (),
        )
        changed = 0
        for r in rows:
            try:
                verdict = classify_known_device(dict(r))
            except Exception:
                continue  # one bad row must not abort the pass
            if (
                r["importance_tier"] == verdict.tier.value
                and r["importance_source"] == verdict.source
            ):
                continue
            self._execute_write(
                "UPDATE known_device SET importance_tier = ?, importance_source = ? "
                "WHERE mac = ?",
                (verdict.tier.value, verdict.source, r["mac"]),
            )
            changed += 1
        return changed

    def get_importance_tiers(self) -> dict:
        """Return {ip_or_mac: tier_name} for the whole inventory, in one read.

        Keyed by both identifiers because claims are keyed by whichever the
        producing layer had. When several MACs share an IP the HIGHEST tier
        wins, matching get_device_importance_tier() — the reference network has
        three MACs at 192.168.68.64, one of them the mesh AP, so first-row-wins
        would let arbitrary row order decide how a gateway claim is ranked.
        """
        from modules.device_importance import Tier, tier_from_name

        rows = self._execute_read(
            "SELECT mac, ip, importance_tier FROM known_device "
            "WHERE importance_tier IS NOT NULL",
            (),
        )
        out: dict = {}

        def _offer(key: Optional[str], tier: Optional[Tier]) -> None:
            if not key or tier is None:
                return
            current = tier_from_name(out.get(key))
            if current is None or tier > current:
                out[key] = tier.value

        for r in rows:
            tier = tier_from_name(r["importance_tier"])
            _offer(r["mac"], tier)
            _offer(r["ip"], tier)
        return out

    def clear_inferred_role(self, mac: str) -> None:
        """Set inferred_role back to NULL for one MAC.

        update_device_stability() deliberately never clears a role — a
        momentarily-blank device_type must not wipe a good one — so undoing a
        wrong promotion needs its own path. Used by
        device_stability.recompute_roles() (Signal Quality Phase 2).
        """
        self._execute_write(
            "UPDATE known_device SET inferred_role = NULL WHERE mac = ?",
            (mac.lower(),),
        )

    def delete_known_device(self, mac: str) -> None:
        """Remove one MAC from the device inventory. Safe for an unknown MAC.

        The only deletion path for a `known_device` row — there was none at all
        before Signal Quality Phase 2's closeout, which is why the SSDP
        multicast group `01:00:5e:7f:ff:fa` stayed in the reference inventory
        with 654 scans against it after Phase 1 stopped writing new multicast
        rows and Phase 2 cleared its role.

        Deliberately narrow: it retracts an inventory *claim* and touches
        nothing else. `device_ip_history`, `device_event`, `device_state` and
        `device_events` rows for this MAC are append-only *records* and are left
        intact as forensics — no schema-level foreign key exists to cascade
        them, and none should. Driven by device_stability.purge_non_devices().
        """
        if not mac:
            return
        self._execute_write(
            "DELETE FROM known_device WHERE mac = ?",
            (mac.lower(),),
        )

    # ── Write: Classification overrides ──────────────────────────────────────

    def set_classification_override(self, mac: str, device_type: str) -> None:
        """Permanently override the device type for a MAC (survives all enrichment)."""
        self._execute_write(
            "INSERT INTO device_classification_overrides (mac, device_type) "
            "VALUES (?, ?) ON CONFLICT(mac) DO UPDATE SET "
            "device_type = excluded.device_type, overridden_at = datetime('now')",
            (mac.lower(), device_type),
        )

    def clear_classification_override(self, mac: str) -> None:
        """Remove the user type override for this MAC, restoring auto-classification."""
        self._execute_write(
            "DELETE FROM device_classification_overrides WHERE mac = ?",
            (mac.lower(),),
        )
