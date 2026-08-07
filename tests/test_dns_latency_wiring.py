"""Phase 4 C5 — the DNS measurement must reach the alert engine unconditionally.

`NetworkLogger` measures DNS latency every cycle, but only behind
`enable_dns` — the "DNS latency" checkbox on the Network Logger page, which
defaults OFF. That is the same defect shape C2 fixed for mesh and modem: an
opt-in *logging* toggle silently disabling an unrelated *alert*. It matters more
here than it looks, because the logger itself auto-starts on every launch
(`logger/auto_start`, ui/app_settings.py), so the checkbox was the only thing
standing between DNS_LATENCY and real data.

The fix deliberately does NOT ungate `LogEntry.dns_ms`. That field has five live
consumers, one of which raises a Lab Mode live-challenge banner on Home at
>200 ms (ui/pages/log_source_panel.py) — ungating it would start firing an
unrelated feature for users who never asked for DNS logging. Alerting gets its
own channel instead, the same way C4 added `plugin_reachability` rather than
overloading `plugin_result`.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from modules.network_logger import NetworkLogger

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ── NetworkLogger measures regardless of the checkbox ────────────────────────

class _Recorder:
    """Drives exactly one _loop pass, then stops it."""

    def __init__(self, logger):
        self.logger = logger
        self.dns: list = []
        self.entries: list = []

    def on_dns(self, value):
        self.dns.append(value)

    def on_entry(self, entry):
        self.entries.append(entry)
        self.logger._stop_event.set()


def _run_one_cycle(monkeypatch, tmp_path, *, enable_dns, dns_value=42.0):
    from modules import network_logger as mod

    monkeypatch.setattr(mod, "_dns_latency_system", lambda domain="google.com": dns_value)
    monkeypatch.setattr(mod, "_ping_once", lambda host: 10.0)

    logger = NetworkLogger(
        interval_s=1,
        targets=["8.8.8.8"],
        log_path=tmp_path / "log.csv",
        enable_dns=enable_dns,
    )
    rec = _Recorder(logger)
    logger._on_entry = rec.on_entry
    logger._on_dns = rec.on_dns
    with open(logger.log_path, "w", newline="", encoding="utf-8") as f:
        import csv
        csv.writer(f).writerow(logger._build_headers())
    logger._loop()
    return rec


def test_dns_is_measured_even_with_the_checkbox_off(monkeypatch, tmp_path):
    rec = _run_one_cycle(monkeypatch, tmp_path, enable_dns=False)
    assert rec.dns == [42.0], (
        "DNS_LATENCY must not depend on the 'DNS latency' logging checkbox — "
        "that is the C2 defect shape"
    )


def test_dns_is_measured_with_the_checkbox_on(monkeypatch, tmp_path):
    rec = _run_one_cycle(monkeypatch, tmp_path, enable_dns=True)
    assert rec.dns == [42.0]


def test_log_entry_dns_stays_gated_by_the_checkbox(monkeypatch, tmp_path):
    """The five LogEntry.dns_ms consumers must see no change at all."""
    off = _run_one_cycle(monkeypatch, tmp_path, enable_dns=False)
    assert off.entries[0].dns_ms == -1.0, (
        "ungating LogEntry.dns_ms would start firing log_source_panel.py's "
        "Lab Mode live challenge for users who never enabled DNS logging"
    )

    on = _run_one_cycle(monkeypatch, tmp_path, enable_dns=True)
    assert on.entries[0].dns_ms == 42.0


def test_csv_header_is_unchanged_when_the_checkbox_is_off(monkeypatch, tmp_path):
    logger = NetworkLogger(targets=["8.8.8.8"], log_path=tmp_path / "l.csv", enable_dns=False)
    assert "dns_ms" not in logger._build_headers()


def test_a_failed_probe_is_reported_as_negative(monkeypatch, tmp_path):
    rec = _run_one_cycle(monkeypatch, tmp_path, enable_dns=False, dns_value=-1.0)
    assert rec.dns == [-1.0], "the engine needs to see the failure to ignore it"


def test_on_dns_failure_does_not_break_the_cycle(monkeypatch, tmp_path):
    """A callback raising must not kill the logger thread."""
    from modules import network_logger as mod

    monkeypatch.setattr(mod, "_dns_latency_system", lambda domain="google.com": 42.0)
    monkeypatch.setattr(mod, "_ping_once", lambda host: 10.0)

    logger = NetworkLogger(
        interval_s=1, targets=["8.8.8.8"], log_path=tmp_path / "log.csv",
    )
    entries: list = []

    def _boom(_v):
        raise RuntimeError("downstream blew up")

    def _entry(e):
        entries.append(e)
        logger._stop_event.set()

    logger._on_dns = _boom
    logger._on_entry = _entry
    with open(logger.log_path, "w", newline="", encoding="utf-8") as f:
        import csv
        csv.writer(f).writerow(logger._build_headers())
    logger._loop()
    assert len(entries) == 1


def test_start_accepts_the_on_dns_callback(tmp_path):
    """The keyword LoggerWorker.run() passes."""
    import inspect
    assert "on_dns" in inspect.signature(NetworkLogger.start).parameters


# ── LoggerWorker re-emits it as a signal ─────────────────────────────────────

def test_worker_declares_the_signal():
    from workers.scan_worker import LoggerWorker
    assert hasattr(LoggerWorker, "dns_sample")


def test_worker_passes_on_dns_to_the_logger():
    """AST, not a live run: LoggerWorker.run() blocks on the logger's stop event.

    Scoped to the LoggerWorker class body on purpose — Module5Worker (the
    on-demand DNS/ping correlator) also passes an `on_dns=` callback, so a
    whole-file search matches something unrelated and passes for free.
    """
    tree = ast.parse((_REPO_ROOT / "workers" / "scan_worker.py").read_text(encoding="utf-8"))
    cls = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == "LoggerWorker"
    )
    kwargs = {
        kw.arg
        for n in ast.walk(cls) if isinstance(n, ast.Call)
        for kw in n.keywords
    }
    assert "on_dns" in kwargs, (
        "LoggerWorker.run() must pass on_dns= into NetworkLogger.start()"
    )


# ── The Dashboard handler evaluates it ───────────────────────────────────────

def _dashboard():
    pytest.importorskip("PyQt6")
    from ui.dashboard import Dashboard
    return Dashboard


def _fake_dashboard(engine, gateway="192.168.1.1"):
    Dashboard = _dashboard()
    fake = MagicMock()
    fake._alert_engine = engine
    fake._alerts_seen = []
    fake._surface_alert_in_app = fake._alerts_seen.append
    fake._store = MagicMock()
    fake._net_info = {"gateway": gateway}
    # Bind the REAL helper. Left as a MagicMock auto-attribute it returns a
    # MagicMock, which iterates empty — so `any(h in ... for h in hosts)` is
    # always False and every suppression test passes without suppressing.
    fake._dns_outage_hosts = lambda: Dashboard._dns_outage_hosts(fake)
    return fake


def _engine():
    from modules.alert_engine import AlertEngine, AlertRule
    return AlertEngine(rules=[
        AlertRule(name="DNS Latency", rule_type="DNS_LATENCY", cooldown_s=0, enabled=True)
    ])


def test_handler_fires_after_a_warm_baseline_and_two_slow_samples():
    from modules.alert_engine_checks5 import _DNS_MIN_SAMPLES
    Dashboard = _dashboard()
    fake = _fake_dashboard(_engine())

    for i in range(_DNS_MIN_SAMPLES):
        Dashboard._on_dns_sample(fake, 20.0 + (1 if i % 2 else -1))
    assert fake._alerts_seen == []

    Dashboard._on_dns_sample(fake, 900.0)
    assert fake._alerts_seen == [], "one slow lookup is a blip"
    Dashboard._on_dns_sample(fake, 900.0)

    assert len(fake._alerts_seen) == 1
    assert fake._alerts_seen[0].rule_type == "DNS_LATENCY"


def test_handler_nominates_the_gateway_as_an_outage_host():
    """A gateway outage must mute DNS slowness — it is a symptom of the outage."""
    from modules.alert_engine_checks5 import _DNS_MIN_SAMPLES
    Dashboard = _dashboard()
    engine = _engine()
    fake = _fake_dashboard(engine, gateway="192.168.1.1")

    for i in range(_DNS_MIN_SAMPLES):
        Dashboard._on_dns_sample(fake, 20.0 + (1 if i % 2 else -1))
    engine._host_down_since["192.168.1.1"] = 1

    for _ in range(6):
        Dashboard._on_dns_sample(fake, 900.0)
    assert fake._alerts_seen == []


def test_outage_hosts_are_the_gateway_plus_the_internet_probes():
    from modules.availability_monitor import DEFAULT_TARGETS
    Dashboard = _dashboard()
    hosts = Dashboard._dns_outage_hosts(_fake_dashboard(_engine()))
    assert hosts == ("192.168.1.1", *DEFAULT_TARGETS)


def test_outage_hosts_exclude_scanned_lan_devices():
    """The reason this list is nominated rather than read off _host_down_since,
    which has held every scanned LAN device since C3."""
    Dashboard = _dashboard()
    hosts = Dashboard._dns_outage_hosts(_fake_dashboard(_engine()))
    assert "192.168.1.57" not in hosts


def test_handler_survives_an_unresolved_gateway():
    """RULE-NET1: net_info['gateway'] is Optional[str] and is
    present-but-None on a VPN or a just-flushed ARP cache, so a `.get(k, "")`
    default does not apply and a bare "" would be nominated as an outage host."""
    from modules.availability_monitor import DEFAULT_TARGETS
    Dashboard = _dashboard()
    fake = _fake_dashboard(_engine(), gateway=None)
    assert Dashboard._dns_outage_hosts(fake) == tuple(DEFAULT_TARGETS)
    Dashboard._on_dns_sample(fake, 20.0)   # must not raise


def test_handler_is_a_no_op_without_an_engine():
    Dashboard = _dashboard()
    fake = _fake_dashboard(None)
    Dashboard._on_dns_sample(fake, 900.0)
    assert fake._alerts_seen == []


def test_worker_signal_is_connected_to_the_handler():
    """RULE-DW1: the emit is useless unless something is listening."""
    tree = ast.parse((_REPO_ROOT / "ui" / "tabs_logger.py").read_text(encoding="utf-8"))

    wired = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute) and n.func.attr == "connect"
        and isinstance(n.func.value, ast.Attribute)
        and n.func.value.attr == "dns_sample"
    ]
    assert len(wired) == 1, (
        "ui/tabs_logger.py must connect LoggerWorker.dns_sample exactly once; "
        f"found {len(wired)}"
    )
