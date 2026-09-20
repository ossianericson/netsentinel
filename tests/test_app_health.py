"""App-health conditions — "NetSentinel can't see X" as a state, not a log line (D1, D3).

Every producer this registry exists for already *detects* its failure: the six
background monitors emit ``error``, the REST worker emits ``error``, the notification
router marks a delivery ``FAILED``. What none of them has is somewhere to put it that
**persists while the fault does and clears when it stops** — the status bar is one
line that the next progress update overwrites (matrix row F2-G6), and a log record is
history, not state.

The contracts pinned here are the ones S4's surface will read without re-checking:

* **One condition per key, however many times it fires.** A monitor failing every
  60 s for a day is one condition with a count, never 1,440 rows.
* **The first success resolves it** — and a later failure is a new episode, so
  "failing since" is honest about the current outage, not the first one ever.
* **The change callback fires on transitions only** (raised, resolved), never on a
  repeat. S4 repaints on it; a repaint per retry would be exactly the noise D2 exists
  to avoid.
* **Severity is the canonical UI set** (RULE-A3). Nothing else is accepted.
"""
from __future__ import annotations

import pytest


class _Clock:
    def __init__(self, t: float = 1_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def _spec(**over):
    from modules.app_health import ConditionSpec
    base = dict(
        key="monitor:availability",
        source="Availability monitor",
        severity="Warning",
        what="Availability monitoring is not running correctly",
        why="Its last check failed.",
        next_step="It retries on its next interval; if this stays, save a diagnostic report.",
        cta_label="Availability History",
    )
    base.update(over)
    return ConditionSpec(**base)


def test_a_reported_failure_is_active_until_the_first_success():
    from modules.app_health import AppHealth

    clock = _Clock()
    health = AppHealth(clock=clock)
    spec = _spec()

    health.report_failure(spec, detail="boom")

    (cond,) = health.active()
    assert cond.key == spec.key
    assert cond.what == spec.what
    assert cond.cta_label == "Availability History"
    assert cond.detail == "boom"
    assert (cond.first_seen, cond.last_seen, cond.count) == (1_000.0, 1_000.0, 1)
    assert cond.resolved_at is None

    clock.t = 1_060.0
    health.report_ok(spec.key)

    assert health.active() == []
    assert health.get(spec.key).resolved_at == 1_060.0


def test_repeated_failures_are_one_condition_with_a_count():
    from modules.app_health import AppHealth

    clock = _Clock()
    health = AppHealth(clock=clock)
    spec = _spec()

    health.report_failure(spec, detail="first")
    clock.t = 1_060.0
    health.report_failure(spec, detail="second")

    (cond,) = health.active()
    assert (cond.first_seen, cond.last_seen, cond.count) == (1_000.0, 1_060.0, 2)
    assert cond.detail == "second"  # the newest raw error is the useful one


def test_a_failure_after_resolution_is_a_new_episode():
    from modules.app_health import AppHealth

    clock = _Clock()
    health = AppHealth(clock=clock)
    spec = _spec()

    health.report_failure(spec)
    health.report_failure(spec)
    clock.t = 1_060.0
    health.report_ok(spec.key)
    clock.t = 5_000.0
    health.report_failure(spec)

    (cond,) = health.active()
    assert (cond.first_seen, cond.count, cond.resolved_at) == (5_000.0, 1, None)


def test_report_ok_for_a_key_that_never_failed_is_a_no_op():
    from modules.app_health import AppHealth

    health = AppHealth(clock=_Clock())
    assert health.report_ok("rest_api:serve") is None
    assert health.get("rest_api:serve") is None


def test_subscribers_hear_transitions_not_repeats():
    from modules.app_health import AppHealth

    clock = _Clock()
    health = AppHealth(clock=clock)
    heard = []
    health.subscribe(lambda c: heard.append((c.key, c.resolved_at is None, c.count)))
    spec = _spec()

    health.report_failure(spec)
    health.report_failure(spec)
    health.report_failure(spec)
    health.report_ok(spec.key)
    health.report_ok(spec.key)  # already resolved: nothing changed

    assert heard == [(spec.key, True, 1), (spec.key, False, 3)]


def test_a_subscriber_may_read_the_registry_it_is_called_from():
    """Called outside the lock — S4's bridge re-reads ``active()`` in its slot."""
    from modules.app_health import AppHealth

    health = AppHealth(clock=_Clock())
    seen = []
    health.subscribe(lambda _c: seen.append(len(health.active())))

    health.report_failure(_spec())

    assert seen == [1]


def test_a_raising_subscriber_neither_breaks_reporting_nor_silences_the_others(caplog):
    from modules.app_health import AppHealth

    health = AppHealth(clock=_Clock())
    heard = []

    def _bad(_c):
        raise RuntimeError("subscriber bug")

    health.subscribe(_bad)
    health.subscribe(lambda c: heard.append(c.key))

    with caplog.at_level("ERROR", logger="modules.app_health"):
        health.report_failure(_spec())

    assert len(health.active()) == 1
    assert heard == ["monitor:availability"]
    assert any(r.exc_info for r in caplog.records)  # RULE-SURF2: logged, with the traceback


@pytest.mark.parametrize("bad", ["Error", "HIGH", "Medium", "STORM", ""])
def test_severity_is_the_canonical_ui_set_only(bad):
    """RULE-A3 — and an internal risk level like STORM is not a severity label either."""
    with pytest.raises(ValueError):
        _spec(severity=bad)


def test_active_is_most_severe_first_then_longest_standing():
    from modules.app_health import AppHealth

    clock = _Clock()
    health = AppHealth(clock=clock)
    health.report_failure(_spec(key="a", severity="Warning"))
    clock.t += 1
    health.report_failure(_spec(key="b", severity="High"))
    clock.t += 1
    health.report_failure(_spec(key="c", severity="Warning"))
    clock.t += 1
    health.report_failure(_spec(key="d", severity="Info"))

    assert [c.key for c in health.active()] == ["b", "a", "c", "d"]


def test_concurrent_reports_from_worker_threads_lose_no_count():
    """Notification delivery reports from one thread per send."""
    import threading
    from modules.app_health import AppHealth

    health = AppHealth()
    spec = _spec()
    raised = []
    health.subscribe(lambda c: raised.append(c))

    def _hammer():
        for _ in range(500):
            health.report_failure(spec)

    threads = [threading.Thread(target=_hammer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert health.get(spec.key).count == 4_000
    assert len(raised) == 1


def test_a_repeat_with_a_different_cause_shows_the_newest_cause():
    """The REST port was taken, then the user picked a reserved one: say the second thing."""
    from modules.app_health import AppHealth

    health = AppHealth(clock=_Clock())
    health.report_failure(_spec(why="Another program is using this port."))
    health.report_failure(_spec(why="Windows reserves this port.", next_step="Pick another."))

    (cond,) = health.active()
    assert (cond.why, cond.next_step, cond.count) == ("Windows reserves this port.", "Pick another.", 2)
