"""
Tests for modules/device_reenrichment.py.

Every identity fix so far only affects FUTURE writes. The rows a user already
has keep whatever a previous build decided — measured on the reference network,
8 of 34 rows carried a vendor that disagreed with what `lookup_vendor()` answers
today, including one whose stored vendor was "Sonos" for a device whose IEEE
vendor is "Frontier Silicon Ltd", and three rows with a NULL device_type.

So a classifier fix silently does nothing for the install that needed it, until
something happens to rewrite each row. This pass closes that gap on upgrade.
"""
from __future__ import annotations

import pytest

from modules.metric_store import MetricStore


@pytest.fixture
def store(tmp_path):
    s = MetricStore(db_path=tmp_path / "reenrich.db")
    yield s
    s.close()


@pytest.fixture
def known_vendor(monkeypatch):
    """Pin vendor lookup so the test does not depend on the bundled IEEE data."""
    table = {
        "aa:bb:cc:00:01:01": "Intel Corporate",
        "aa:bb:cc:00:01:02": "Frontier Silicon Ltd",
        "aa:bb:cc:00:01:03": "Raspberry Pi",
        "aa:bb:cc:00:01:04": "",
    }
    monkeypatch.setattr(
        "modules.device_reenrichment.lookup_vendor",
        lambda mac: table.get(mac.lower(), ""),
    )
    return table


class TestVendorHealing:
    def test_a_stale_vendor_is_corrected(self, store, known_vendor):
        """The measured case: stored "Sonos" for a Frontier Silicon device."""
        from modules.device_reenrichment import reenrich_known_devices

        mac = "aa:bb:cc:00:01:02"
        store.upsert_known_device(mac, ip="10.0.0.2", vendor="Sonos",
                                  device_type="Streaming Stick")
        result = reenrich_known_devices(store)

        assert store.get_known_devices()[mac].vendor == "Frontier Silicon Ltd"
        assert result.vendors_corrected == 1

    def test_an_absent_ieee_answer_leaves_the_stored_vendor_alone(
        self, store, known_vendor
    ):
        """A randomized MAC has no IEEE vendor. Blanking a stored one on that
        basis would destroy information rather than correct it."""
        from modules.device_reenrichment import reenrich_known_devices

        mac = "aa:bb:cc:00:01:04"
        store.upsert_known_device(mac, ip="10.0.0.4", vendor="Some Vendor",
                                  device_type="Smart TV")
        reenrich_known_devices(store)

        assert store.get_known_devices()[mac].vendor == "Some Vendor"


class TestClassificationHealing:
    def test_an_unknown_row_gains_a_type_the_current_rules_can_derive(
        self, store, known_vendor
    ):
        """The zero-confidence rows: an Intel NIC that no shipped rule could
        classify until the generic computer rule existed."""
        from modules.device_reenrichment import reenrich_known_devices

        mac = "aa:bb:cc:00:01:01"
        store.upsert_known_device(mac, ip="10.0.0.1", vendor="Intel Corporate",
                                  device_type="Unknown Device")
        reenrich_known_devices(store)

        dev = store.get_known_devices()[mac]
        assert dev.device_type == "Computer / Workstation"
        assert dev.confidence > 0.0

    def test_a_wrong_label_is_replaced_when_the_evidence_supports_another(
        self, store, known_vendor
    ):
        """Barnens-rum: shown as Streaming Stick, is a Philips audio device."""
        from modules.device_reenrichment import reenrich_known_devices

        mac = "aa:bb:cc:00:01:02"
        store.upsert_known_device(mac, ip="10.0.0.2", vendor="Sonos",
                                  device_type="Streaming Stick")
        reenrich_known_devices(store)

        assert store.get_known_devices()[mac].device_type == "Smart Speaker / Audio"

    def test_it_never_downgrades_an_informative_label_to_unknown(
        self, store, known_vendor
    ):
        """The safety property.

        A device with no vendor and no hostname can carry a real label from a
        product-specific announcement this pass cannot see (a printer known
        only from _ipp._tcp). Replacing that with "Unknown Device" on upgrade
        would read as data loss, and the next scan re-derives it properly
        anyway. Re-enrichment upgrades; it never blanks.
        """
        from modules.device_reenrichment import reenrich_known_devices

        mac = "aa:bb:cc:00:01:04"
        store.upsert_known_device(mac, ip="10.0.0.4", vendor="",
                                  device_type="Print Server")
        reenrich_known_devices(store)

        assert store.get_known_devices()[mac].device_type == "Print Server"

    def test_a_user_override_is_never_touched(self, store, known_vendor):
        from modules.device_reenrichment import reenrich_known_devices

        mac = "aa:bb:cc:00:01:01"
        store.upsert_known_device(mac, ip="10.0.0.1", vendor="Intel Corporate",
                                  device_type="Router / Gateway")
        store.set_classification_override(mac, "Router / Gateway")
        reenrich_known_devices(store)

        assert store.get_known_devices()[mac].device_type == "Router / Gateway"


class TestRunsOnce:
    def test_second_call_is_a_no_op(self, store, known_vendor):
        """Gated on a meta marker so it costs nothing on every later startup."""
        from modules.device_reenrichment import reenrich_known_devices

        store.upsert_known_device("aa:bb:cc:00:01:02", ip="10.0.0.2",
                                  vendor="Sonos", device_type="Streaming Stick")
        first = reenrich_known_devices(store)
        second = reenrich_known_devices(store)

        assert first.ran is True
        assert second.ran is False
        assert second.rows_examined == 0

    def test_force_reruns_regardless_of_the_marker(self, store, known_vendor):
        from modules.device_reenrichment import reenrich_known_devices

        store.upsert_known_device("aa:bb:cc:00:01:02", ip="10.0.0.2",
                                  vendor="Sonos", device_type="Streaming Stick")
        reenrich_known_devices(store)
        forced = reenrich_known_devices(store, force=True)

        assert forced.ran is True
        assert forced.rows_examined == 1

    def test_an_empty_inventory_is_harmless(self, store, known_vendor):
        from modules.device_reenrichment import reenrich_known_devices

        result = reenrich_known_devices(store)
        assert result.ran is True
        assert result.rows_examined == 0
        assert result.vendors_corrected == 0
        assert result.types_corrected == 0


class TestItDoesNotDisturbPresence:
    def test_last_seen_is_preserved(self, store, known_vendor):
        """Re-enrichment is a data repair, not an observation.

        `upsert_known_device()` sets `last_seen` to now by default, so a naive
        repair marks every corrected device as just-seen — including ones that
        have been offline for days. That feeds presence episodes and the
        LEFT/RECOVERED edge triggers, so it would suppress a real "device gone"
        or manufacture a return. Measured: a plain upsert moved a 3-day-old
        `last_seen` forward by exactly 3 days.
        """
        import time
        from modules.device_reenrichment import reenrich_known_devices

        mac = "aa:bb:cc:00:01:02"
        three_days_ago = int(time.time()) - 86400 * 3
        store.upsert_known_device(mac, ip="10.0.0.2", vendor="Sonos",
                                  device_type="Streaming Stick",
                                  ts=three_days_ago)

        reenrich_known_devices(store)

        dev = store.get_known_devices()[mac]
        assert dev.vendor == "Frontier Silicon Ltd", "precondition: the row was repaired"
        assert dev.last_seen == three_days_ago, (
            f"last_seen moved {dev.last_seen - three_days_ago}s — the repair "
            f"reported the device as seen"
        )


class TestItIsActuallyWired:
    """RULE-DBG5. This codebase has twice shipped a fix that ran nowhere — the
    v2.2.4 passive-observation MAC match had zero production callers, and the
    A4 arbiter was structurally bypassed. Both passed their own unit tests.

    `tools/debug_launch.py` constructs `Dashboard()` directly and never runs
    `main()`, so COMMIT GATE Step 3 cannot see this call site at all.
    """

    def test_app_main_calls_the_reenrichment_pass(self):
        import ast
        from pathlib import Path

        src = Path(__file__).resolve().parent.parent / "app.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))

        called = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "reenrich_known_devices"
            for node in ast.walk(tree)
        )
        assert called, (
            "app.py never calls reenrich_known_devices(), so every device row "
            "written by an earlier build keeps its stale vendor and label"
        )

    def test_it_runs_against_a_store_the_way_main_does(self, store, known_vendor):
        """The call site passes only the store; prove that signature works."""
        from modules.device_reenrichment import reenrich_known_devices

        store.upsert_known_device("aa:bb:cc:00:01:02", ip="10.0.0.2",
                                  vendor="Sonos", device_type="Streaming Stick")
        result = reenrich_known_devices(store)
        assert result.ran and result.rows_examined == 1
