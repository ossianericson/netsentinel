"""
MetricStore device-inventory write mixin — device_ip_history, device_annotations,
device_events (audit trail), topology_snapshots, device_state, device_event,
known_device, and classification-override write methods.

Extracted from modules/metric_store.py (Phase 3 split, per that module's own
"Split plan" note) to keep metric_store.py under the RULE-AH1 600-line budget.
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
        """
        rows = self._execute_read(
            "SELECT inferred_role, alert_opt_in FROM known_device WHERE ip = ? OR mac = ?",
            (identifier, identifier),
        )
        if not rows:
            return False
        row = rows[0]
        return row["inferred_role"] in ("gateway", "infrastructure") or bool(row["alert_opt_in"])

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
