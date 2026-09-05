"""The session sentinel (A1) — the only thing that will ever see a silent death.

The Store baseline was **8 memory failures and 5 hangs**. None of those produce a Python
traceback, a `faulthandler` entry, or any other trace: the OS takes the process and the
app learns nothing, so "the user quit" and "Windows killed us for memory" are the same
observation. Microsoft's own guidance for terminations it cannot symbolicate is to log
lifecycle boundaries and infer the last good state — which is exactly what a record
written at start, updated on navigation, and marked clean only on a real shutdown gives.

Pure Python, no PyQt: `modules/` cannot import it (ARCH RULE 1), and the clean-exit write
has to happen inside `ui/shutdown.py` because `Dashboard.closeEvent()` ends in
`os._exit(0)`, which skips `atexit` entirely.
"""
from __future__ import annotations

import pytest

_DEVANAGARI = "नमस्ते"


def _new_process():
    """Model a fresh process: forget the in-progress session, keep the files.

    Deliberately reaches into the module rather than calling a `_reset_for_test()`
    helper on it. A reset hook would be production API that only tests use, which
    `tests/test_orphan_functions.py` counts against a shrink-only budget — and rightly:
    it is one more thing shipping in every binary for nobody's benefit.
    """
    from modules import session_record

    session_record._current_path = None


@pytest.fixture(autouse=True)
def appdata(tmp_path, monkeypatch):
    """Redirect app-data to a non-Latin path, and reset the module between tests.

    The path is Devanagari for the same reason `tests/test_crash_net.py` uses one: a
    hi-IN machine's ANSI codepage is cp1252, which cannot represent it at all, so every
    unencoded write on that path fails deterministically (RULE-WIN24). Making it the
    default here means every test in this file exercises the encoding contract, not
    just the one that names it.
    """
    target = tmp_path / (_DEVANAGARI + "-home") / "NetSentinel"
    target.mkdir(parents=True)
    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: target)

    _new_process()
    yield target
    _new_process()


def test_a_session_that_never_ends_cleanly_is_reported_by_the_next_run():
    """The whole point, end to end: a death leaves a record and the next launch sees it.

    `begin_session()` writes `clean_exit: false` up front, so the only way a record ever
    becomes clean is an explicit shutdown. Anything that skips that write — OOM kill,
    native FailFast, hang-then-kill, power loss — leaves the record exactly as it was,
    which is the signal.
    """
    from modules import session_record

    session_record.begin_session(app_version="2.2.8")     # the run that dies
    _new_process()                      # process gone; nothing ran
    session_record.begin_session(app_version="2.2.8")     # the next launch

    unclean = session_record.find_unclean_sessions()

    assert len(unclean) == 1, f"expected the previous run only, got {unclean}"
    assert unclean[0]["clean_exit"] is False


def test_a_clean_quit_leaves_nothing_for_the_next_run_to_report():
    """The false-positive half, and the one that decides whether B1's strip is trusted.

    A banner that appears after an ordinary quit is noise, and a user learns to dismiss
    it without reading — which costs the real crash its only chance of being reported.
    """
    from modules import session_record

    session_record.begin_session(app_version="2.2.8")
    session_record.end_session_clean()
    _new_process()
    session_record.begin_session(app_version="2.2.8")

    assert session_record.find_unclean_sessions() == []


def test_the_last_page_visited_survives_a_death_that_writes_nothing_else():
    """The only datum that will ever say *where* the user was when the OS took us.

    An OOM kill or a hang-then-kill produces no traceback and no faulthandler entry, so
    there is no stack to read. A page label recorded on every navigation is the entire
    substitute — Microsoft's own advice for terminations it cannot symbolicate.
    """
    from modules import session_record

    session_record.begin_session(app_version="2.2.8")
    session_record.heartbeat("Network Map")
    session_record.heartbeat("Devices")
    _new_process()                      # killed here, mid-Devices
    session_record.begin_session(app_version="2.2.8")

    unclean = session_record.find_unclean_sessions()

    assert unclean[0]["last_page"] == "Devices"
    assert unclean[0]["last_beat"] >= unclean[0]["started_at"]


def test_the_record_carries_the_environment_fingerprint():
    """A1 without A2 says a machine died; together they say *which kind* of machine.

    The v2.2.8 triage had a market code and a count and had to guess the codepage pair
    from it. An unclean record that carries the measured pair, the real OS locale and
    the app-data path booleans is the difference between that guess and an answer.
    """
    from modules import session_record
    from tests.test_environment_fingerprint import ALLOWED_FIELDS

    session_record.begin_session(app_version="2.2.8")
    _new_process()
    session_record.begin_session(app_version="2.2.8")

    env = session_record.find_unclean_sessions()[0]["environment"]

    assert set(env) == ALLOWED_FIELDS, "the record must carry the whole fingerprint"
    assert env["appdata_path_is_ascii"] is False, (
        "the fingerprint was computed against a different path than the record's own"
    )


def test_a_half_written_record_does_not_hide_the_others(appdata):
    """A truncated record is the *expected* artefact here, not an exotic edge case.

    The process is killed mid-write often enough that this is exactly what an OOM kill
    during a heartbeat leaves behind. If one unreadable file aborted the scan, the kill
    that produced it would also erase the evidence of every other run.
    """
    from modules import session_record

    session_record.begin_session(app_version="2.2.8")     # the run that dies
    _new_process()
    (appdata / "sessions" / "truncated.json").write_text('{"started_at": 1', encoding="utf-8")
    session_record.begin_session(app_version="2.2.8")

    unclean = session_record.find_unclean_sessions()

    assert len(unclean) == 1, f"the unreadable file cost us a real record: {unclean}"
    assert unclean[0]["app_version"] == "2.2.8"


def test_no_entry_point_can_raise_even_when_app_data_is_unreachable(monkeypatch):
    """This runs on the startup path, on every navigation, and inside the shutdown drain.

    An instrumentation module that throws in any of those places is strictly worse than
    the blindness it was written to fix: it would turn a diagnosable crash into a
    startup failure, a broken navigation, or a hang on quit.
    """
    from modules import session_record

    def _boom():
        raise OSError("the app-data directory is not reachable")

    monkeypatch.setattr("modules.utils.get_app_data_dir", _boom)

    assert session_record.begin_session(app_version="2.2.8") is None
    session_record.heartbeat("Devices")          # must not raise
    session_record.end_session_clean()           # must not raise
    assert session_record.find_unclean_sessions() == []


def test_unclean_sessions_come_back_newest_first(monkeypatch):
    """B1's strip names one session, and it has to be the one the user just lost.

    Directory order is arbitrary — uuid4 filenames sort randomly — so without an
    explicit sort the strip would eventually report a week-old crash as "last time".

    The clock is driven by the test rather than read from the machine: three real
    `begin_session()` calls in a tight loop land on the *same* `time.time()` value at
    Windows clock resolution, which makes any ordering assertion trivially true and the
    test incapable of failing.
    """
    from modules import session_record

    ticks = iter(range(1000, 1100))
    monkeypatch.setattr(session_record.time, "time", lambda: float(next(ticks)))

    for _ in range(3):
        session_record.begin_session(app_version="2.2.8")
        _new_process()
    session_record.begin_session(app_version="2.2.8")

    starts = [r["started_at"] for r in session_record.find_unclean_sessions()]

    assert starts == [1002.0, 1001.0, 1000.0], f"not newest-first: {starts}"


def test_the_sessions_directory_is_bounded(appdata):
    """One file per launch, forever, is how the other eight logs got to ~6.78 MB.

    Ten records is already more history than anything reads — B1 names the last one and
    B2 tails a handful — so the bound is set where the data stops being useful rather
    than where the disk starts to hurt.
    """
    from modules import session_record

    for _ in range(session_record.MAX_SESSIONS + 5):
        session_record.begin_session(app_version="2.2.8")
        session_record.end_session_clean()
        _new_process()

    kept = list((appdata / "sessions").glob("*.json"))
    assert len(kept) <= session_record.MAX_SESSIONS, (
        f"{len(kept)} records kept, bound is {session_record.MAX_SESSIONS}"
    )


#: (module, function) pairs the shipped app must actually call. Without this, every
#: test above passes against a module nothing imports — the RULE-DBG5 failure shape,
#: where a fix is "done" while 100% of traffic still takes the old path.
REQUIRED_WIRING = (
    ("app.py", "begin_session"),
    ("ui/shutdown.py", "end_session_clean"),
    ("ui/nav/builder.py", "heartbeat"),
)


@pytest.mark.parametrize("source_file,func", REQUIRED_WIRING)
def test_the_shipped_app_actually_calls_the_sentinel(source_file, func):
    """Each of the three lifecycle writes needs a real caller in production code.

    They are three separate wirings with three separate failure modes: no
    `begin_session` and nothing is ever recorded; no `end_session_clean` and every
    ordinary quit is reported as a crash; no `heartbeat` and an unclean record cannot
    say where the user was, which is the only thing it had to offer.
    """
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    tree = ast.parse((root / source_file).read_text(encoding="utf-8"))

    # app.py imports its late helpers under leading-underscore aliases
    # (`_install_crash_net`, `_harden_stdio`), so resolve aliases back to the real
    # name — the question is whether production calls the function, not what it
    # happened to name the local binding.
    aliases = {
        alias.asname: alias.name
        for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        for alias in node.names if alias.asname
    }
    called = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = (node.func.attr if isinstance(node.func, ast.Attribute)
                else getattr(node.func, "id", None))
        if name is not None:
            called.add(aliases.get(name, name))

    assert func in called, (
        f"{source_file} never calls {func}() — the session sentinel is wired at one "
        f"end only, so it records nothing that anything reads"
    )
