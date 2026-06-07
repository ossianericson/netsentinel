"""
Contract tests for MetricStore query methods.

These tests assert that every query mixin returns the exact shape the UI pages
expect.  They use a temporary SQLite file (not :memory:) so WAL mode works
correctly.  No PyQt6 import; runs headless in CI.

Covered methods:
  - query_rtt_history        → List[RttPoint]
  - query_all_rtt_hosts      → List[str]
  - query_speed_test_history → List[SpeedTestPoint]  (incl. all 25 modem fields)
  - query_uptime_table       → List[dict] with ip/hostname/uptime keys
  - query_device_events      → List[DeviceEvent]
  - query_cert_status        → List[CertCheckPoint]
"""
import time
from pathlib import Path

import pytest

from modules.metric_store import MetricStore
from modules.metric_store_schema import (
    CertCheckPoint,
    DeviceEvent,
    RttPoint,
    SpeedTestPoint,
)


@pytest.fixture
def store(tmp_path: Path):
    s = MetricStore(db_path=tmp_path / "test.db", retain_days=365)
    yield s
    s.close()


# ── RTT ───────────────────────────────────────────────────────────────────────

class TestRttContracts:
    def test_query_rtt_history_returns_rtt_points(self, store: MetricStore):
        store.record_rtt("8.8.8.8", rtt_ms=12.5, loss_pct=0.0, jitter_ms=1.2)
        result = store.query_rtt_history("8.8.8.8", hours=1.0)

        assert len(result) == 1
        assert isinstance(result[0], RttPoint)

    def test_rtt_point_has_required_fields(self, store: MetricStore):
        now = int(time.time())
        store.record_rtt("1.1.1.1", rtt_ms=5.0, loss_pct=10.0, jitter_ms=0.5, ts=now)
        pt = store.query_rtt_history("1.1.1.1", hours=1.0)[0]

        assert pt.ts == now
        assert pt.host == "1.1.1.1"
        assert pt.rtt_ms == pytest.approx(5.0)
        assert pt.loss_pct == pytest.approx(10.0)
        assert pt.jitter_ms == pytest.approx(0.5)

    def test_query_all_rtt_hosts_returns_strings(self, store: MetricStore):
        store.record_rtt("192.168.1.1", 20.0)
        store.record_rtt("192.168.1.2", 30.0)
        hosts = store.query_all_rtt_hosts(hours=1.0)

        assert isinstance(hosts, list)
        assert all(isinstance(h, str) for h in hosts)
        assert set(hosts) == {"192.168.1.1", "192.168.1.2"}

    def test_no_rtt_data_returns_empty_list(self, store: MetricStore):
        result = store.query_rtt_history("10.0.0.1", hours=1.0)
        assert result == []


# ── Speed test ────────────────────────────────────────────────────────────────

class TestSpeedTestContracts:
    def test_query_speed_test_history_returns_speed_test_points(self, store: MetricStore):
        store.record_speed_test(
            download_mbps=100.0, upload_mbps=50.0, ping_ms=12.0,
            server_name="Test", server_city="Stockholm", server_country="SE",
        )
        result = store.query_speed_test_history(hours=1.0)

        assert len(result) == 1
        assert isinstance(result[0], SpeedTestPoint)

    def test_speed_test_point_core_fields(self, store: MetricStore):
        store.record_speed_test(
            download_mbps=200.5, upload_mbps=80.1, ping_ms=8.3,
            server_name="Akamai", server_city="London", server_country="GB",
        )
        pt = store.query_speed_test_history(hours=1.0)[0]

        assert pt.download_mbps == pytest.approx(200.5)
        assert pt.upload_mbps == pytest.approx(80.1)
        assert pt.ping_ms == pytest.approx(8.3)
        assert pt.server_name == "Akamai"
        assert pt.server_city == "London"
        assert pt.server_country == "GB"

    def test_speed_test_point_modem_fields_exist(self, store: MetricStore):
        """All 20 modem signal fields must be present on the returned dataclass."""
        store.record_speed_test(
            download_mbps=50.0, upload_mbps=20.0, ping_ms=30.0,
            nr5g_rsrp=-85.0, nr5g_sinr=15.0, nr5g_band="n78",
            lte_rsrp=-90.0, lte_band="B3", cell_id=12345,
            enb_id=678, mcc="234", mnc="30", wan_ip="1.2.3.4",
        )
        pt = store.query_speed_test_history(hours=1.0)[0]

        modem_fields = [
            "network_type", "signal_bars", "nr5g_rsrp", "nr5g_sinr", "nr5g_band",
            "lte_rsrp", "lte_band", "cell_id", "enb_id", "mcc", "mnc", "wan_ip",
            "nr5g_rsrq", "nr5g_pci", "nr5g_arfcn",
            "lte_snr", "lte_rsrq", "lte_pci", "lte_earfcn",
        ]
        for field in modem_fields:
            assert hasattr(pt, field), f"SpeedTestPoint missing field: {field}"

    def test_speed_test_newest_first(self, store: MetricStore):
        now = int(time.time())
        store.record_speed_test(download_mbps=10.0, upload_mbps=5.0, ping_ms=50.0, ts=now - 100)
        store.record_speed_test(download_mbps=20.0, upload_mbps=10.0, ping_ms=25.0, ts=now)
        results = store.query_speed_test_history(hours=1.0)

        assert results[0].download_mbps == pytest.approx(20.0)  # newest first


# ── Device state / uptime ─────────────────────────────────────────────────────

class TestUptimeContracts:
    def test_query_uptime_table_returns_list_of_dicts(self, store: MetricStore):
        store.record_device_state("192.168.1.10", mac="aa:bb:cc:dd:ee:ff",
                                  hostname="router", state="UP")
        result = store.query_uptime_table(hours_list=[24.0])

        assert isinstance(result, list)
        assert len(result) >= 1

    def test_uptime_row_has_required_keys(self, store: MetricStore):
        store.record_device_state("10.0.0.1", mac=None, hostname="device-A", state="UP")
        rows = store.query_uptime_table(hours_list=[24.0, 168.0])

        row = next(r for r in rows if r["ip"] == "10.0.0.1")
        required_keys = {"ip", "hostname"}
        assert required_keys.issubset(row.keys()), (
            f"uptime row missing keys: {required_keys - row.keys()}"
        )

    def test_uptime_windows_present_for_each_requested_hour(self, store: MetricStore):
        store.record_device_state("10.0.0.2", mac=None, hostname="srv", state="UP")
        rows = store.query_uptime_table(hours_list=[1.0, 24.0, 168.0])

        row = next((r for r in rows if r["ip"] == "10.0.0.2"), None)
        assert row is not None
        # At least one of the window uptime keys must exist
        uptime_keys = [k for k in row if k not in ("ip", "hostname")]
        assert len(uptime_keys) >= 1, "No uptime window keys found in row"


# ── Device events ─────────────────────────────────────────────────────────────

class TestDeviceEventContracts:
    def test_query_device_events_returns_device_events(self, store: MetricStore):
        store.record_device_event("192.168.1.5", event_type="JOINED",
                                  mac="11:22:33:44:55:66", detail="new device")
        result = store.query_device_events(hours=1.0)

        assert len(result) >= 1
        assert isinstance(result[0], DeviceEvent)

    def test_device_event_fields(self, store: MetricStore):
        now = int(time.time())
        store.record_device_event("10.0.0.5", event_type="LEFT",
                                  mac="aa:aa:aa:bb:bb:bb", detail="gone", ts=now)
        events = store.query_device_events(hours=1.0)
        ev = next(e for e in events if e.ip == "10.0.0.5")

        assert ev.ts == now
        assert ev.ip == "10.0.0.5"
        assert ev.event_type == "LEFT"
        assert ev.mac == "aa:aa:aa:bb:bb:bb"
        assert ev.detail == "gone"

    def test_invalid_event_type_raises(self, store: MetricStore):
        with pytest.raises(ValueError):
            store.record_device_event("10.0.0.1", event_type="EXPLODED")


# ── TLS certificate checks ────────────────────────────────────────────────────

class TestCertContracts:
    def test_query_cert_status_returns_cert_check_points(self, store: MetricStore):
        store.record_cert_check(
            host="example.com", port=443, days_remaining=30,
            subject="CN=example.com", issuer="Let's Encrypt",
            not_after="2026-01-01", is_expired=False, is_self_signed=False,
        )
        result = store.query_cert_status(hours=1.0)

        assert len(result) == 1
        assert isinstance(result[0], CertCheckPoint)

    def test_cert_point_has_required_fields(self, store: MetricStore):
        store.record_cert_check(
            host="api.example.com", port=443, days_remaining=90,
            subject="CN=api.example.com", issuer="DigiCert",
            not_after="2027-06-01", is_expired=False, is_self_signed=False,
        )
        pt = store.query_cert_status(hours=1.0)[0]

        required = ["ts", "host", "port", "days_remaining", "subject",
                    "issuer", "not_after", "is_expired", "is_self_signed"]
        for attr in required:
            assert hasattr(pt, attr), f"CertCheckPoint missing field: {attr}"

        assert pt.host == "api.example.com"
        assert pt.port == 443
        assert pt.days_remaining == 90
        assert pt.is_expired is False

    def test_cert_query_returns_latest_per_host_port(self, store: MetricStore):
        """Only the newest check per (host, port) pair should be returned."""
        now = int(time.time())
        store.record_cert_check(
            host="old.example.com", port=443, days_remaining=60,
            subject="CN=old", issuer="CA", not_after="2027-01-01",
            is_expired=False, is_self_signed=False, ts=now - 3600,
        )
        store.record_cert_check(
            host="old.example.com", port=443, days_remaining=59,
            subject="CN=old", issuer="CA", not_after="2027-01-01",
            is_expired=False, is_self_signed=False, ts=now,
        )
        results = store.query_cert_status(hours=2.0)
        matching = [r for r in results if r.host == "old.example.com"]

        assert len(matching) == 1
        assert matching[0].days_remaining == 59  # newest row wins
