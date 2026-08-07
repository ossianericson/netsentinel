"""
Device stability scoring and role inference engine.

Reads device_ip_history to compute how stable a device's IP address is over
time (ip_stability 0.0–1.0) and infers a human-readable role (gateway, printer,
server, infrastructure, workstation, iot) from behavioral patterns.

**`inferred_role` is the alert-eligibility gate** — `is_device_alert_in_scope()`
admits a device to all ten device-scoped alert rules when the role is
`gateway`/`infrastructure` — so getting it wrong is not cosmetic. Measured
against a real 25.4-day database, it was wrong for 8 of 13 assignments, and the
gate it feeds admitted 53.4 % of every candidate alert. Signal Quality Phase 2
therefore removed the two things it used to accept as evidence:

  * **"always on and never changed IP"** (`scan_count >= 10 and
    ip_stability >= 0.9 -> infrastructure`) was a catch-all describing every
    printer, streaming stick and games console on a home network. It alone
    produced 9 of the 9 wrong promotions: a PS4, an Xbox, a Chromecast, a
    Lexmark printer, three unidentifiable privacy MACs and the SSDP multicast
    group. Deleted outright — uptime says nothing about function.
  * **`device_type` on its own.** It is a heuristic guess: on the same network
    it called an iPad a "Domain Controller" and the real mesh AP a "Video
    Doorbell". It now needs a second, independent signal.

Promotion to gateway/infrastructure now requires an `IdentityClass.IDENTIFIED`
device (so a multicast group or an unnameable privacy MAC can never hold the
role) plus corroboration: the real gateway address, the DHCP server's identity,
the mesh plugin's own node list, a DNS/DHCP open-port fingerprint, an
OUI-registered networking vendor, or an explicit infrastructure `device_type`
paired with sustained stability.

Pure Python — no PyQt imports. Called from DeviceTracker after each scan.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, FrozenSet, List, Optional

from modules.device_identity import (
    IdentityClass,
    classify_identity,
    is_promotable_to_infrastructure,
)
from modules.device_importance import vendor_suggests_infrastructure

if TYPE_CHECKING:
    from modules.metric_store import MetricStore


# ── Role inference constants ──────────────────────────────────────────────────

_GATEWAY_OCTETS = {"1", "254"}
_INFRASTRUCTURE_TYPES = {"router", "access point", "switch", "firewall", "gateway", "wireless ap"}
_SERVER_TYPES = {"server", "nas", "storage"}
_PRINTER_TYPES = {"printer", "mfp", "scanner"}
_PRINTER_PORTS = {9100, 515, 631}
# Serving DNS or DHCP is a function, not a guess — a host doing either is
# infrastructure regardless of what the classifier decided to call it.
_INFRA_SERVICE_PORTS = {53, 67}
_IOT_TYPES = {"iot", "smart home", "camera", "ip camera", "smart tv", "thermostat", "hub"}
_WORKSTATION_TYPES = {"phone", "laptop", "tablet", "desktop", "pc", "computer", "workstation"}

# An infrastructure device_type is only trusted alongside sustained stability:
# an access point does not move, a mislabelled doorbell may.
_INFRA_TYPE_MIN_SCANS = 5
_INFRA_TYPE_MIN_STABILITY = 0.9


def _type_matches(dt_lower: str, types) -> bool:
    """Word-boundary aware check — prevents 'ap' matching inside 'laptop'."""
    padded = f" {dt_lower} "
    return any(f" {t} " in padded for t in types)


@dataclass(frozen=True)
class RoleEvidence:
    """Corroborating facts about the network, gathered outside the device row.

    Every field is optional. A caller that cannot supply a signal leaves it
    unset and inference simply has one fewer route to promotion — never a
    different, wrong answer. `ui/scan_wiring.py` supplies all four, from the
    cached `_net_info` dict and the mesh plugin's node list — none of them
    probes anything, so nothing here puts subprocess work on the scan path
    (RULE-WIN1); `NetworkInfoWorker` already paid that cost off the main thread.
    """

    gateway_ip: Optional[str] = None
    dhcp_server_ip: Optional[str] = None
    mesh_node_macs: FrozenSet[str] = frozenset()
    mesh_node_ips: FrozenSet[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "mesh_node_macs",
            frozenset(m.lower().strip() for m in self.mesh_node_macs if m),
        )
        object.__setattr__(
            self, "mesh_node_ips",
            frozenset(i.strip() for i in self.mesh_node_ips if i),
        )

    def names_mesh_node(self, mac: Optional[str], ip: Optional[str]) -> bool:
        """True when the mesh system itself reports this device as one of its nodes."""
        if mac and mac.lower().strip() in self.mesh_node_macs:
            return True
        return bool(ip) and (ip or "").strip() in self.mesh_node_ips

    @classmethod
    def from_network(
        cls,
        net_info: Optional[dict] = None,
        mesh_units: Optional[list] = None,
    ) -> "RoleEvidence":
        """Build evidence from a `get_network_info()` dict and mesh unit list.

        Lives here rather than in `ui/scan_wiring.py` so it is unit-testable
        without a Dashboard (ARCH RULE 1). Every field is defensive: RULE-NET1
        — `net_info["gateway"]` is initialised to None and only overwritten on a
        successful route/ARP resolution, a normal runtime state on VPN or a
        just-flushed ARP cache — and a mesh unit list comes from a third-party
        router plugin, so it may hold anything at all.
        """
        info = net_info or {}
        # The DHCP server IP lives one level down in the live producer:
        # NetworkInfoWorker builds `info["dhcp"] = get_dhcp_info()`
        # (workers/scan_worker.py), and that same dict is what reaches this
        # method. Top level is still honoured first so a caller synthesising a
        # flat dict (tools/alert_replay.py, tests) keeps working.
        dhcp = info.get("dhcp")
        nested_dhcp_server = dhcp.get("dhcp_server") if isinstance(dhcp, dict) else None
        if not isinstance(nested_dhcp_server, str):
            nested_dhcp_server = None
        macs: set = set()
        ips: set = set()
        for unit in mesh_units or []:
            try:
                if isinstance(unit, dict):
                    mac, ip = unit.get("mac"), unit.get("ip")
                else:
                    mac, ip = getattr(unit, "mac", None), getattr(unit, "ip", None)
                if isinstance(mac, str) and mac.strip():
                    macs.add(mac)
                if isinstance(ip, str) and ip.strip():
                    ips.add(ip)
            except Exception:
                continue  # a plugin-supplied unit must never break a scan
        return cls(
            gateway_ip=(info.get("gateway") or "").strip() or None,
            dhcp_server_ip=(
                (info.get("dhcp_server") or nested_dhcp_server or "").strip() or None
            ),
            mesh_node_macs=frozenset(macs),
            mesh_node_ips=frozenset(ips),
        )


_NO_EVIDENCE = RoleEvidence()


# ── Public API ────────────────────────────────────────────────────────────────

def compute_ip_stability(mac: str, store: "MetricStore") -> float:
    """
    Return IP stability score (0.0–1.0) for a MAC.

    Stability = seen_count_at_canonical_ip / total_seen_count.
    Canonical IP = the IP with the highest seen_count in device_ip_history.
    Returns 0.0 for unknown MACs or when only one scan has been recorded.
    """
    rows = store.get_ip_history_stats(mac)
    if not rows:
        return 0.0
    total = sum(int(r[1] or 0) for r in rows)
    if total == 0:
        return 0.0
    canonical_count = max(int(r[1] or 0) for r in rows)
    return canonical_count / total


def _has_infrastructure_evidence(
    ip: Optional[str],
    mac: Optional[str],
    vendor: Optional[str],
    dt_lower: str,
    open_ports: Optional[List[int]],
    scan_count: int,
    ip_stability: float,
    evidence: RoleEvidence,
) -> bool:
    """True when something other than uptime says this device is infrastructure.

    Each route is an independent claim about *function*: it hands out leases,
    the mesh reports it as a node, it serves DNS/DHCP, its OUI-registered vendor
    sells networking hardware, or the classifier named it network equipment and
    it has held one address long enough for that to be believable.
    """
    if evidence.dhcp_server_ip and ip and ip.strip() == evidence.dhcp_server_ip.strip():
        return True
    if evidence.names_mesh_node(mac, ip):
        return True
    if open_ports and any(p in _INFRA_SERVICE_PORTS for p in open_ports):
        return True
    if vendor_suggests_infrastructure(vendor):
        return True
    return (
        _type_matches(dt_lower, _INFRASTRUCTURE_TYPES)
        and scan_count >= _INFRA_TYPE_MIN_SCANS
        and ip_stability >= _INFRA_TYPE_MIN_STABILITY
    )


def infer_role(
    ip: Optional[str],
    device_type: Optional[str],
    custom_name: Optional[str],
    scan_count: int,
    ip_stability: float,
    open_ports: Optional[List[int]] = None,
    *,
    mac: Optional[str] = None,
    hostname: Optional[str] = None,
    vendor: Optional[str] = None,
    evidence: Optional[RoleEvidence] = None,
) -> Optional[str]:
    """
    Infer device role from behavioral patterns. Returns role string or None.

    Priority order (first match wins):
    1. custom_name is set → None (user label takes precedence; no inference override)
    2. Not an endpoint (multicast/broadcast/malformed) → None
    3. Identified + IP matches the known gateway (or .1/.254 when none is known)
       → "gateway"
    4. Identified + corroborating infrastructure evidence → "infrastructure"
    5. Identified + high stability + many scans + server type → "server"
    6. High stability + many scans + printer type or ports → "printer"
    7. device_type in workstation set → "workstation"
    8. device_type in IoT set → "iot"
    9. default → None

    Steps 3-5 are gated on `IdentityClass.IDENTIFIED`, which needs the MAC.
    A caller that supplies no `mac` keeps the pre-Phase-2 ungated behaviour
    rather than being refused outright; every production caller supplies one.
    """
    if custom_name:
        return None

    identity = classify_identity(mac, hostname, vendor, ip) if mac else None
    if identity is not None and identity.identity_class is IdentityClass.NOT_A_DEVICE:
        return None
    promotable = identity is None or is_promotable_to_infrastructure(identity)

    dt_lower = (device_type or "").lower()
    ev = evidence or _NO_EVIDENCE

    if promotable and ip:
        known_gateway = (ev.gateway_ip or "").strip()
        if known_gateway:
            # A real gateway address supersedes the guess in both directions:
            # this IS the gateway, or we know for a fact it is not.
            if ip.strip() == known_gateway:
                return "gateway"
        elif "." in ip and ip.rsplit(".", 1)[-1] in _GATEWAY_OCTETS:
            return "gateway"

    if promotable and _has_infrastructure_evidence(
        ip, mac, vendor, dt_lower, open_ports, scan_count, ip_stability, ev
    ):
        return "infrastructure"

    if promotable and scan_count >= 5 and ip_stability >= 0.9:
        if _type_matches(dt_lower, _SERVER_TYPES):
            return "server"

    if scan_count >= 3 and ip_stability >= 0.85:
        if _type_matches(dt_lower, _PRINTER_TYPES):
            return "printer"
        if open_ports and any(p in _PRINTER_PORTS for p in open_ports):
            return "printer"

    if _type_matches(dt_lower, _WORKSTATION_TYPES):
        return "workstation"

    if _type_matches(dt_lower, _IOT_TYPES):
        return "iot"

    return None


def is_static_candidate(
    ip_stability: float,
    scan_count: int,
    inferred_role: Optional[str],
    is_pinned: bool = False,
) -> bool:
    """
    Return True if this device should be persistently displayed even when offline.

    Static candidates are: pinned devices, infrastructure roles (gateway, printer,
    server, infrastructure), and any device seen 3+ times with stable IP.
    """
    if is_pinned:
        return True
    if inferred_role in ("gateway", "printer", "server", "infrastructure"):
        return True
    return ip_stability >= 0.85 and scan_count >= 3


def update_stability_for_device(
    mac: str,
    ip: Optional[str],
    device_type: Optional[str],
    custom_name: Optional[str],
    store: "MetricStore",
    hostname: Optional[str] = None,
    vendor: Optional[str] = None,
    evidence: Optional[RoleEvidence] = None,
) -> None:
    """
    Recompute and persist ip_stability, scan_count, and inferred_role for one MAC.

    Called by DeviceTracker after each scan for every device that was seen.
    Uses device_ip_history as the authoritative source for scan_count and stability.
    Never overwrites inferred_role if the device has a custom_name (user label wins).

    `hostname`/`vendor` are what let the identity gate tell a privacy MAC that
    the app *can* name (`Ossians-iPhone-2022`) from one it cannot — without
    them every randomised MAC would read as anonymous and lose its role.
    """
    stability = compute_ip_stability(mac, store)
    scan_count = store.get_total_seen_count(mac)

    role = infer_role(
        ip=ip,
        device_type=device_type,
        custom_name=custom_name,
        scan_count=scan_count,
        ip_stability=stability,
        mac=mac,
        hostname=hostname,
        vendor=vendor,
        evidence=evidence,
    )

    # Only update inferred_role when we have a non-None result — never clear an
    # existing inference (e.g. if device_type is temporarily blank after a scan).
    store.update_device_stability(
        mac=mac,
        scan_count=scan_count,
        ip_stability=stability,
        inferred_role=role,
    )


def recompute_roles(
    store: "MetricStore",
    evidence: Optional[RoleEvidence] = None,
) -> Dict[str, Optional[str]]:
    """Re-derive `inferred_role` for every known_device row. Returns what changed.

    A one-time migration, not a per-scan path. It exists because the stored
    values cannot be trusted and cannot self-heal:

      * 9 of the reference database's role assignments were written by the
        deleted always-on catch-all, and a device that is never seen again
        keeps its wrong role forever;
      * `update_device_stability()` deliberately *never clears* a role (so a
        momentarily-blank `device_type` cannot wipe a good one), which means
        even a rescanned device would keep the stale value. Clearing therefore
        needs the explicit `clear_inferred_role()` path.

    Recomputes from stored columns only — no network access — so it is safe to
    run at startup. A row that fails is skipped rather than aborting the pass:
    a partially-migrated inventory is strictly better than none.
    """
    changed: Dict[str, Optional[str]] = {}
    for mac, row in (store.get_known_devices() or {}).items():
        try:
            role = infer_role(
                ip=getattr(row, "ip", None),
                device_type=getattr(row, "device_type", None),
                custom_name=getattr(row, "custom_name", None),
                scan_count=int(getattr(row, "scan_count", 0) or 0),
                ip_stability=float(getattr(row, "ip_stability", 0.0) or 0.0),
                mac=mac,
                hostname=getattr(row, "hostname", None),
                vendor=getattr(row, "vendor", None),
                evidence=evidence,
            )
            if role == getattr(row, "inferred_role", None):
                continue
            if role is None:
                store.clear_inferred_role(mac)
            else:
                store.update_device_stability(
                    mac=mac,
                    scan_count=int(getattr(row, "scan_count", 0) or 0),
                    ip_stability=float(getattr(row, "ip_stability", 0.0) or 0.0),
                    inferred_role=role,
                )
            changed[mac] = role
        except Exception:
            continue  # one bad row must not abort the migration for the rest
    return changed


def migration_key(name: str, db_path: Optional[str]) -> str:
    """Return the QSettings key recording that migration `name` ran on `db_path`.

    QSettings is **per user**; the database is **per install path**. A source run
    (`python app.py` from the repo) uses `MetricStore._default_path()` tier 1 —
    the exe/repo directory — while the installed app falls through to
    `%LOCALAPPDATA%\\NetSentinel\\`. Two databases, and with a bare key like
    `signal_quality/roles_recomputed_v2` they share one flag: whichever launches
    first marks the migration done and the other skips it permanently, leaving
    its inventory unmigrated with no way to notice.

    Scoping by a digest of the resolved path gives each database its own record.
    The digest must be **hashlib**, never the builtin `hash()`: `hash()` on a str
    is salted per process by PYTHONHASHSEED, so the key would differ on every
    launch and every migration would re-run forever — for `purge_non_devices`
    that means re-deleting rows on every boot. Pinned by
    tests/test_migration_key_scoping.py::test_key_is_identical_across_processes.

    A `None` path (in-memory store, unresolved backend) still yields a usable
    key: a startup migration must never raise because it could not identify its
    own database.
    """
    import hashlib
    import os

    resolved = os.path.normcase(os.path.abspath(db_path)) if db_path else "<none>"
    digest = hashlib.sha256(resolved.encode("utf-8", "replace")).hexdigest()[:12]
    return f"signal_quality/{name}_{digest}"


def purge_non_devices(store: "MetricStore") -> Dict[str, str]:
    """Delete every `known_device` row that is not an endpoint. Returns {mac: reason}.

    A one-time migration and the last step of the Signal Quality Program's
    acceptance criterion 3 — "`239.255.255.250` and every other `NOT_A_DEVICE`
    entry is *absent* from `known_device`". Phase 1 stopped new multicast rows
    being written and Phase 2 stopped them holding a role, but neither removed
    the rows already there: nothing in the tree deleted a `known_device` row at
    all, so the SSDP group sat in the reference inventory with 654 scans against
    it, counted as a device and displayed as one.

    **Only `NOT_A_DEVICE` is purgeable.** `ANONYMOUS` is a real host the app
    cannot name — 8 of the reference network's 30 devices carry a randomised
    MAC and are perfectly real — so deleting those would remove live devices
    from the user's inventory. The identity test is delegated to
    `classify_identity()` rather than re-derived here; a second copy of the
    multicast/broadcast arithmetic is one more thing to drift.

    Retracts an inventory claim only. Event history keyed by the same MAC is
    left intact (see `MetricStore.delete_known_device`). A row that fails is
    skipped rather than aborting the pass, matching recompute_roles().
    """
    purged: Dict[str, str] = {}
    for mac, row in (store.get_known_devices() or {}).items():
        try:
            identity = classify_identity(
                mac,
                hostname=getattr(row, "hostname", None),
                vendor=getattr(row, "vendor", None),
                ip=getattr(row, "ip", None),
            )
            if identity.is_real_device:
                continue
            store.delete_known_device(mac)
            purged[mac] = identity.reason
        except Exception:
            continue  # one bad row must not abort the migration for the rest
    return purged
