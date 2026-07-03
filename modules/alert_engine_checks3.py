"""
alert_engine_checks3.py — _AlertChecksMixin3: NEW_OPEN_PORT / NEW_CVE /
NEW_EXPOSURE rule evaluation (V6 Sprint 3 — "scheduled security posture +
diffing").

New file rather than growing alert_engine_checks2.py further — keeps both
files (and alert_engine.py, already at the RULE-AH1 budget) under the
600-line limit (see tests/test_module_loc.py).

Provides:
  evaluate_port_sweep_checks()  — NEW_OPEN_PORT: one alert per newly opened
                                   port from modules.port_sweep.PortSweepReport
  evaluate_cve_recheck_checks() — NEW_CVE: one alert per newly discovered CVE
                                   from modules.cve_recheck.CveRecheckReport
  evaluate_exposure_checks()    — NEW_EXPOSURE: one alert per newly
                                   internet-exposed port from
                                   modules.exposure_watch.ExposureWatchReport

None of these three fire a resolution alert — a port closing again, a CVE
being patched, or exposure closing is itself the "all clear" (there is no
persistent "still open" state to track, unlike HOST_DOWN/RTT_ANOMALY), so
there is no `*_since` bookkeeping here — same reasoning as IOT_BEHAVIOR in
alert_engine_checks2.py.
"""
from __future__ import annotations

import time
from typing import List

from modules.alert_types import AlertFired
from modules.port_sweep import port_label


class _AlertChecksMixin3:
    """Mixin for AlertEngine providing NEW_OPEN_PORT/NEW_CVE/NEW_EXPOSURE checks."""

    def evaluate_port_sweep_checks(self, report) -> List[AlertFired]:
        """NEW_OPEN_PORT — a device from the nightly port sweep now has a
        port open that was not open on the prior sweep."""
        fired: List[AlertFired] = []
        now = int(time.time())

        for rule in self._rules:
            if not rule.enabled or rule.rule_type != "NEW_OPEN_PORT":
                continue
            for host, port in report.new_ports:
                if rule.host and rule.host != host:
                    continue
                alert = self._fire_if_cooled(
                    rule, f"{host}::{port}", now,
                    message=self._append_action(
                        f"Port {port}/{port_label(port)} opened on {host} since the last sweep.",
                        "NEW_OPEN_PORT",
                    ),
                    severity="WARNING",
                    value=float(port),
                )
                if alert:
                    alert.host = host
                    alert.cta_filter = host
                    fired.append(alert)
                    if self._on_alert:
                        self._on_alert(alert)

        return fired

    def evaluate_cve_recheck_checks(self, report) -> List[AlertFired]:
        """NEW_CVE — a tracked (host, service) pair gained a CVE that
        wasn't there on the last scheduled re-check."""
        fired: List[AlertFired] = []
        now = int(time.time())

        for rule in self._rules:
            if not rule.enabled or rule.rule_type != "NEW_CVE":
                continue
            for host, service, cve in report.new_cves:
                if rule.host and rule.host != host:
                    continue
                severity = "CRITICAL" if cve.severity in ("CRITICAL", "HIGH") else "WARNING"
                alert = self._fire_if_cooled(
                    rule, f"{host}::{cve.cve_id}", now,
                    message=self._append_action(
                        f"{host}: {service} is affected by {cve.cve_id} "
                        f"(CVSS {cve.cvss_score:.1f}, {cve.severity}) — {cve.description}",
                        "NEW_CVE",
                    ),
                    severity=severity,
                    value=cve.cvss_score,
                )
                if alert:
                    alert.host = host
                    alert.cta_filter = host
                    fired.append(alert)
                    if self._on_alert:
                        self._on_alert(alert)

        return fired

    def evaluate_exposure_checks(self, report) -> List[AlertFired]:
        """NEW_EXPOSURE — a port became newly reachable from the internet
        since the last weekly exposure check."""
        fired: List[AlertFired] = []
        now = int(time.time())

        for rule in self._rules:
            if not rule.enabled or rule.rule_type != "NEW_EXPOSURE":
                continue
            for host, port in report.new_exposed:
                if rule.host and rule.host != host:
                    continue
                alert = self._fire_if_cooled(
                    rule, f"{host}::{port}", now,
                    message=self._append_action(
                        f"Port {port} on {host} is now reachable from the internet.",
                        "NEW_EXPOSURE",
                    ),
                    severity="CRITICAL",
                    value=float(port),
                )
                if alert:
                    alert.host = host
                    alert.cta_filter = host
                    fired.append(alert)
                    if self._on_alert:
                        self._on_alert(alert)

        return fired
