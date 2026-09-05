"""The unclean-exit strip (B1) — the only thing that ever mentions a silent death.

A1 writes a session record marked `clean_exit: false` and flips it only on a real
shutdown, so an OOM kill, a hang-then-kill or a native FailFast leaves the record
exactly as it was. That has been true since A1 landed and no user has ever seen
it: the records sit in `%LOCALAPPDATA%\\NetSentinel\\sessions\\` beside four other
write-only logs. This strip is the whole of the read path.

The behaviour that carries the risk is **dismissal**. A strip that cannot be
dismissed is a nag; a strip dismissed once and never shown again is A1 back where
it started, silently. The key has to identify one death.
"""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication

#: A stable, obviously-synthetic start time. See _record().
_FIXED_EPOCH = 1_700_000_500.0


@pytest.fixture
def strip(monkeypatch):
    """A real strip, with the dismissal store actually isolated.

    `tests/conftest.py`'s autouse `isolated_settings` redirects QSettings by
    setting a unique `QCoreApplication` organization/application name — which
    only affects the no-argument `QSettings()` constructor. `ui/context_banners.py`
    passes org and app **explicitly** (`QSettings("NetSentinel", "NetSentinel")`),
    so it resolves to the developer's real `HKCU\\Software\\NetSentinel` and slips
    straight past that fixture. Two consequences, both observed here: the tests
    litter the real registry, and dismissals leak between tests — a banner key
    derived from `time.time()` collides for any two tests that run inside the
    same second, so one test's dismissal silently hides another's strip.

    Rebinding the name so it honours the per-test application identity keeps the
    real `should_show_banner`/`mark_banner_seen` code under test (the button must
    be wired to the real store, not a stub — RULE-DBG5) while writing nowhere
    real.
    """
    from PyQt6.QtCore import QSettings

    from ui.widgets.unclean_exit_strip import UncleanExitStrip

    monkeypatch.setattr("ui.context_banners.QSettings", lambda *a, **k: QSettings())

    w = UncleanExitStrip()
    yield w
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # already destroyed by an earlier teardown
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def _record(started=None, page="Network Logger"):
    """A session record shaped exactly as `session_record.begin_session()` writes one.

    `started_at` defaults to a fixed epoch rather than `time.time()` on purpose:
    the dismissal key truncates it to whole seconds, so two tests using "now"
    collide whenever they run inside the same second — which is every run.
    """
    return {
        "started_at": _FIXED_EPOCH if started is None else started,
        "app_version": "2.2.8",
        "clean_exit": False,
        "last_page": page,
    }


def test_no_unclean_sessions_means_no_strip(strip):
    """A clean quit must leave Home exactly as it was.

    This is the common case by a wide margin, and a warning strip that appears
    after a normal exit trains the user to ignore it — which costs the real one
    its only chance to be read.
    """
    strip.set_sessions([])
    assert strip.isVisible() is False


def test_an_unclean_session_shows_the_strip_naming_the_last_page(strip):
    """`last_page` is the only answer there will ever be to "where were they?".

    Nothing else survives an OOM kill: no traceback, no faulthandler entry, no
    Windows event with a usable stack. Putting it in the strip's own sentence is
    what turns "it crashed" into something a person can act on.
    """
    strip.set_sessions([_record(page="Network Logger")])

    assert strip.isVisible() is True
    assert "Network Logger" in strip._title_lbl.text()
    assert "closed unexpectedly" in strip._title_lbl.text().lower()


def test_a_session_that_died_before_any_navigation_still_reads_correctly(strip):
    """`last_page` is absent when the process died during startup.

    Which is exactly when a crash is most interesting, so the sentence has to
    survive its absence rather than trailing off into "while you were on ".
    """
    strip.set_sessions([_record(page="")])

    assert strip.isVisible() is True
    text = strip._title_lbl.text()
    assert "while you were on" not in text
    assert text.endswith(".")


def test_dismissing_hides_this_crash_but_not_the_next_one(strip):
    """The invariant the dismissal key exists for.

    A single "unclean_exit_seen" flag would silence every future crash after the
    first dismissal — A1 back to writing files nobody reads, with no visible
    symptom. Keying on the dead session's own start time means dismissal is
    scoped to the death the user actually saw.
    """
    first = _record(started=1_700_000_000.0)
    strip.set_sessions([first])
    strip._dismiss()
    assert strip.isVisible() is False

    strip.set_sessions([first])
    assert strip.isVisible() is False, "the dismissed crash came back"

    strip.set_sessions([_record(started=1_800_000_000.0)])
    assert strip.isVisible() is True, "a NEW crash was silenced by an old dismissal"


def test_a_truncated_record_is_still_dismissable(strip):
    """A record killed mid-write is the expected artefact of the failure itself.

    `session_record` is explicitly required to tolerate one, so the strip must
    too — and in particular must not produce a strip with no working dismiss
    button, which is the one outcome the user cannot escape.
    """
    strip.set_sessions([{"clean_exit": False}])
    assert strip.isVisible() is True

    strip._dismiss()
    strip.set_sessions([{"clean_exit": False}])
    assert strip.isVisible() is False


def test_the_button_writes_a_real_report_and_announces_where(strip, tmp_path, monkeypatch):
    """The button has to produce a file, not just a satisfying click.

    Driving the real slot rather than calling `write_report()` directly is the
    point: the defect this guards against is a button wired to nothing, which no
    test of the report module can see (RULE-DBG5).
    """
    from PyQt6.QtWidgets import QMessageBox

    shown: list = []
    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: shown.append(a))
    )

    created: list = []
    strip.report_created.connect(created.append)
    strip.set_sessions([_record()])
    strip._report_btn.click()

    assert len(created) == 1
    assert (tmp_path / "reports").exists()
    reports = list((tmp_path / "reports").glob("netsentinel-diagnostic-*.md"))
    assert len(reports) == 1
    assert shown, "the user was never told where the report went"


def test_a_failed_write_warns_and_leaves_the_strip_up(strip, monkeypatch):
    """If there is no report, the offer must stay on screen.

    Hiding the strip on failure would remove the only route back to the action
    that just failed.
    """
    from PyQt6.QtWidgets import QMessageBox

    warned: list = []
    monkeypatch.setattr(
        "ui.widgets.feedback_dialog.write_diagnostic_report", lambda: None
    )
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(a))
    )

    strip.set_sessions([_record()])
    strip._report_btn.click()

    assert warned, "a silent failure leaves the user believing a report exists"
    assert strip.isVisible() is True
