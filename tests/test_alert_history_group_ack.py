"""
tests/test_alert_history_group_ack.py — RULE-T7 behavioural coverage for the
Alert History table's grouped acknowledge (Phase 1b, notifications rework).

The table collapses alerts by (rule_name, host) into "×N" rows. Before this
fix, every ack path (bulk bar, alert drawer) wrote only the group's
representative id, so the other N-1 members stayed unacked and reappeared on
the next 30s refresh. Reproduced live against the user's DB: 87 unacked alerts
collapsed into 43 rows, so acking every visible row left 44 unacked.

RULE-T3: these fail before the fix (group ids are not carried on the row;
_bulk_acknowledge does not exist).
"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

pytestmark = pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")


def _cleanup(widget):
    app = QApplication.instance()
    try:
        widget.deleteLater()
    except RuntimeError:
        pass  # already destroyed — safe to skip
    if app:
        for _ in range(3):
            app.processEvents()


@pytest.fixture()
def store(tmp_path):
    from modules.metric_store import MetricStore
    s = MetricStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


@pytest.fixture()
def page(store):
    from ui.pages.notifications_page import NotificationsPage
    p = NotificationsPage()
    p.set_store(store)
    p.resize(1000, 600)
    p.show()
    QApplication.instance().processEvents()
    yield p
    _cleanup(p)


def _seed(store) -> dict:
    """3 alerts collapsing to one row, plus 1 alert in its own row."""
    gone = [
        store.record_alert_fired("Device Gone", "192.168.68.59", "WARNING", f"gone {i}")
        for i in range(3)
    ]
    churn = [store.record_alert_fired("IP Churn", "192.168.68.70", "WARNING", "churn")]
    return {"gone": gone, "churn": churn}


def _refresh(page):
    page._chk_unacked_only.setChecked(True)
    page._refresh_alert_history()
    QApplication.instance().processEvents()


# ── Grouping carries every member id ──────────────────────────────────────────

def test_grouped_row_carries_all_member_ids(page, store):
    ids = _seed(store)
    _refresh(page)

    t = page._alert_history_table
    assert t.rowCount() == 2, "3 same-(rule,host) alerts must collapse into 1 row"

    from ui.pages.notif_alert_history import _GROUP_IDS_ROLE
    by_row = {
        t.item(r, 0).data(_GROUP_IDS_ROLE) and len(t.item(r, 0).data(_GROUP_IDS_ROLE)): r
        for r in range(t.rowCount())
    }
    assert 3 in by_row, "the ×3 row must carry all 3 member ids, not just the first"
    assert 1 in by_row

    all_ids = set()
    for r in range(t.rowCount()):
        all_ids.update(t.item(r, 0).data(_GROUP_IDS_ROLE))
    assert all_ids == set(ids["gone"]) | set(ids["churn"])


def test_selecting_the_grouped_row_reports_every_alert_it_stands_for(page, store):
    _seed(page._store)
    _refresh(page)

    t = page._alert_history_table
    from ui.pages.notif_alert_history import _GROUP_IDS_ROLE
    grouped_row = next(
        r for r in range(t.rowCount()) if len(t.item(r, 0).data(_GROUP_IDS_ROLE)) == 3
    )
    t.selectRow(grouped_row)

    assert len(page._selected_alert_ids()) == 3


# ── Acknowledging clears the whole group ──────────────────────────────────────

def test_bulk_acknowledge_clears_every_member_of_every_selected_group(page, store):
    _seed(store)
    _refresh(page)
    assert len(store.get_unacked_alerts()) == 4

    page._select_all_alerts()
    page._bulk_acknowledge()

    assert store.get_unacked_alerts() == [], (
        "acking all visible rows must clear all 4 alerts, not just the 2 "
        "group representatives"
    )


def test_acked_group_does_not_reappear_on_refresh(page, store):
    _seed(store)
    _refresh(page)

    page._select_all_alerts()
    page._bulk_acknowledge()
    _refresh(page)

    assert page._alert_history_table.rowCount() == 0


def test_drawer_ack_clears_the_whole_group(page, store):
    _seed(store)
    _refresh(page)

    t = page._alert_history_table
    from ui.pages.notif_alert_history import _GROUP_IDS_ROLE
    grouped_row = next(
        r for r in range(t.rowCount()) if len(t.item(r, 0).data(_GROUP_IDS_ROLE)) == 3
    )
    item = t.item(grouped_row, 0)
    page._alert_drawer.open(item.data(0x0100), group_ids=item.data(_GROUP_IDS_ROLE))
    page._alert_drawer._ack_confirm_btn.click()
    QApplication.instance().processEvents()
    # open() spawns a parented _EvidenceWorker QThread; reap it before the
    # fixture tears the page down (RULE-WIN4).
    page._alert_drawer.close_drawer()
    QApplication.instance().processEvents()

    remaining = {a["rule_name"] for a in store.get_unacked_alerts()}
    assert remaining == {"IP Churn"}, (
        "the drawer acked only its representative alert; the other 2 members "
        "of the group stayed unacked"
    )


def test_already_acked_members_are_not_re_acked(page, store):
    ids = _seed(store)
    store.acknowledge_alert(ids["gone"][0], acked_by="alice", comment="first responder")
    _refresh(page)

    page._select_all_alerts()
    page._bulk_acknowledge()

    rows = {a["id"]: a for a in store.get_recent_alerts(hours=1)}
    assert rows[ids["gone"][0]]["acked_by"] == "alice"
    assert rows[ids["gone"][0]]["acked_comment"] == "first responder"


# ── The Message column (Phase 4) ──────────────────────────────────────────────

def test_message_is_shown_and_is_the_stretch_column(page, store):
    store.record_alert_fired(
        "Device Gone", "192.168.68.59", "WARNING",
        "Device 192.168.68.59 has not responded to 3 consecutive scans",
    )
    _refresh(page)

    from PyQt6.QtWidgets import QHeaderView
    from ui.pages.notif_alert_history import _COL_MESSAGE, _COL_RULE

    t = page._alert_history_table
    header = [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())]
    assert header == ["Time", "Rule", "Host", "Message", "Severity", "Status"]

    hh = t.horizontalHeader()
    assert hh.sectionResizeMode(_COL_MESSAGE) == QHeaderView.ResizeMode.Stretch
    assert hh.sectionResizeMode(_COL_RULE) != QHeaderView.ResizeMode.Stretch, (
        "Rule must not stretch — a short fixed vocabulary in a very wide column "
        "reads as a permanently empty column"
    )
    assert t.item(0, _COL_MESSAGE).text().startswith("Device 192.168.68.59 has not")
