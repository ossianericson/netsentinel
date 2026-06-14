"""Tests for modules/snmp_poller.py ifTable error polling (Cat2-V4)."""

from unittest.mock import patch


# ── Dataclass tests ────────────────────────────────────────────────────────────

def test_if_error_entry_import():
    from modules.snmp_poller import IfErrorEntry
    e = IfErrorEntry(if_index=1, if_descr="eth0", in_errors=5, out_errors=2,
                     in_discards=0, out_discards=1)
    assert e.total_issues == 8
    assert e.has_issues is True


def test_if_error_entry_clean():
    from modules.snmp_poller import IfErrorEntry
    e = IfErrorEntry(if_index=2, if_descr="lo")
    assert e.total_issues == 0
    assert e.has_issues is False


def test_if_error_entry_defaults():
    from modules.snmp_poller import IfErrorEntry
    e = IfErrorEntry(if_index=3)
    assert e.if_descr == ""
    assert e.in_errors == 0
    assert e.out_errors == 0
    assert e.in_discards == 0
    assert e.out_discards == 0


# ── poll_if_errors unit tests ──────────────────────────────────────────────────

def _make_snmp_responses(if_count: int, errors_by_idx: dict) -> dict:
    """Build a lookup of OID-string → return value for _snmp_get_single."""
    responses = {
        "1.3.6.1.2.1.2.1.0": str(if_count),
    }
    for idx in range(1, if_count + 1):
        errs = errors_by_idx.get(idx, {})
        responses[f"1.3.6.1.2.1.2.2.1.2.{idx}"]  = errs.get("descr",   f"eth{idx}")
        responses[f"1.3.6.1.2.1.2.2.1.14.{idx}"]  = errs.get("in_err",  "0")
        responses[f"1.3.6.1.2.1.2.2.1.20.{idx}"]  = errs.get("out_err", "0")
        responses[f"1.3.6.1.2.1.2.2.1.13.{idx}"]  = errs.get("in_dis",  "0")
        responses[f"1.3.6.1.2.1.2.2.1.19.{idx}"]  = errs.get("out_dis", "0")
    return responses


def test_poll_if_errors_basic():
    from modules.snmp_poller import poll_if_errors

    responses = _make_snmp_responses(
        if_count=2,
        errors_by_idx={
            1: {"descr": "eth0", "in_err": "10", "out_err": "2", "in_dis": "0", "out_dis": "1"},
            2: {"descr": "lo",   "in_err": "0",  "out_err": "0", "in_dis": "0", "out_dis": "0"},
        },
    )

    def fake_get(host, oid, community, timeout):
        return responses.get(oid, "<error: not found>")

    with patch("modules.snmp_poller._snmp_get_single", side_effect=fake_get):
        entries = poll_if_errors("192.168.1.1")

    assert len(entries) == 2
    eth0 = entries[0]
    assert eth0.if_descr == "eth0"
    assert eth0.in_errors == 10
    assert eth0.out_errors == 2
    assert eth0.out_discards == 1
    assert eth0.total_issues == 13
    lo = entries[1]
    assert lo.has_issues is False


def test_poll_if_errors_no_snmp():
    """Host that doesn't respond — ifNumber returns error → no entries."""
    from modules.snmp_poller import poll_if_errors

    def fake_get(host, oid, community, timeout):
        return "<error: timeout>"

    with patch("modules.snmp_poller._snmp_get_single", side_effect=fake_get):
        entries = poll_if_errors("10.0.0.1", max_interfaces=4)

    assert entries == []


def test_poll_if_errors_max_interfaces_cap():
    """max_interfaces limits how many indices are probed."""
    from modules.snmp_poller import poll_if_errors

    responses = _make_snmp_responses(
        if_count=100,
        errors_by_idx={i: {"descr": f"if{i}"} for i in range(1, 101)},
    )

    def fake_get(host, oid, community, timeout):
        return responses.get(oid, "<error: not found>")

    with patch("modules.snmp_poller._snmp_get_single", side_effect=fake_get):
        entries = poll_if_errors("192.168.1.1", max_interfaces=8)

    assert len(entries) == 8


# ── SNMPIfErrorWorker tests ────────────────────────────────────────────────────

def test_snmp_if_error_worker_import():
    from workers.scan_worker import SNMPIfErrorWorker
    assert SNMPIfErrorWorker is not None


def test_snmp_if_error_worker_lifecycle(qt_app):
    """Worker starts, emits result_ready, and can be joined cleanly."""
    from workers.scan_worker import SNMPIfErrorWorker
    from modules.snmp_poller import IfErrorEntry

    received: list = []

    def fake_get(host, oid, community, timeout):
        responses = _make_snmp_responses(
            if_count=1,
            errors_by_idx={1: {"descr": "eth0", "in_err": "3"}},
        )
        return responses.get(oid, "<error: timeout>")

    worker = SNMPIfErrorWorker(host="127.0.0.1", community="public")
    worker.result_ready.connect(lambda entries: received.extend(entries))

    with patch("modules.snmp_poller._snmp_get_single", side_effect=fake_get):
        worker.start()
        assert worker.wait(5000), "Worker did not finish within 5 s"

    # Flush queued cross-thread signals
    for _ in range(5):
        qt_app.processEvents()

    try:
        worker.deleteLater()
    except RuntimeError:
        pass  # non-fatal
    for _ in range(3):
        qt_app.processEvents()

    assert len(received) == 1
    assert isinstance(received[0], IfErrorEntry)
    assert received[0].in_errors == 3
