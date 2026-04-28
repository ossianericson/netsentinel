# NetSentinel — Feature Gap Backlog

> Last updated: 2026-04-28  
> Purpose: ordered list of remaining capabilities grouped by priority. Completed items have been removed.

---

## Tier 1 — Next up

1. **NetFlow / traffic flow analysis**
   Who is talking to whom and how much. Requires a flow exporter on the router side.

2. **Distributed probe support**
   Run a lightweight agent on a second machine to monitor a VLAN or subnet that the main host cannot reach directly.

---

## Tier 2 — Medium priority

3. **Agent-based monitoring**
   Install a small agent on Windows/Linux hosts to report CPU, disk, memory, process health back to the dashboard (bypasses SNMP limitations).

4. **Template/profile system**
   Apply a "home router" or "NAS" monitoring template to a device type automatically on discovery.

5. **Trigger expression language**
   Compose complex alert conditions: `avg(rtt, 5m) > 50 AND loss% > 5`.

6. **Problem escalation timeline**
   If a problem isn't acknowledged within N minutes, escalate (notify a second channel).

---

## Ecosystem ideas (future consideration)

- **Geolocation map** — plot discovered public IPs on a world map (MaxMind GeoLite2)
- **QoS policy advisor** — analyse traffic mix and suggest DSCP/QoS rules
- **802.1X port-auth detection** — detect and report EAP frames on the LAN
