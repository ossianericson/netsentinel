"""Error-surfacing census — classifier unit tests and shrink-only ratchets.

Error-surfacing audit S0.1 (`docs/internal/error-surfacing-audit-2026-09-15.md`).
The crash net catches what escapes; this file watches what does NOT escape — failures
that are caught and then reach no one, reach the user as a raw exception string, or
render as a clean result. `tools/check_error_surfacing.py` measures four things:

  (a) raw exception text written to a user-visible sink (RULE-A2)
  (b) broad `except` handlers that swallow silently — body is only `pass` or a
      constant/name fallback, with no log line, no signal, no UI write (D6)
  (c) `ToastManager.show()` calls with a kind `toast.py` does not define
  (d) scan-registry labels that can be set running/fresh but never error/not_testable

Every count is a pointer, not a verdict: most silent swallows are legitimate (a widget
already closed, an optional probe). The ratchets therefore only forbid NEW ones; the
S7–S8 sprints work the (b) baselines down. (a) is a hard zero since S6b, together with a
guard that a caught exception reaches the error helpers as itself.
"""
from __future__ import annotations

import ast
import textwrap

import pytest

from tools import check_error_surfacing as ces


def _classify(handler_src: str) -> str:
    """Classify the single except handler in *handler_src*, wrapped in a function."""
    src = "def f():\n    try:\n        g()\n" + textwrap.indent(textwrap.dedent(handler_src), "    ")
    tree = ast.parse(src)
    handler = next(n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler))
    return ces.classify_handler(handler)


def _is_broad(handler_src: str) -> bool:
    src = "try:\n    g()\n" + textwrap.dedent(handler_src)
    handler = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ExceptHandler))
    return ces.is_broad(handler)


# ── Classifier ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("handler_src, expected", [
    ("except Exception:\n    pass  # widget already closed\n", "pass"),
    ("except Exception:\n    return None\n", "silent_default"),
    ("except Exception:\n    return []\n", "silent_default"),
    ("except Exception:\n    return self._cached\n", "silent_default"),
    ("except Exception:\n    value = -1\n", "silent_default"),
    ("except Exception:\n    continue\n", "silent_default"),
    ("except Exception:\n    return compute_fallback()\n", "other"),
    ("except Exception:\n    _log.debug('x', exc_info=True)\n", "log_low_only"),
    ("except Exception as exc:\n    _log.warning('failed: %s', exc)\n", "log_high"),
    ("except Exception:\n    logging.getLogger(__name__).exception('x')\n", "log_high"),
    ("except Exception:\n    traceback.print_exc()\n", "log_high"),
    ("except Exception as exc:\n    self.error.emit(str(exc))\n", "surfaced"),
    ("except Exception as exc:\n    QMessageBox.warning(self, 'T', 'plain')\n", "surfaced"),
    ("except Exception:\n    ToastManager.show('Export failed', 'error')\n", "surfaced"),
    ("except Exception:\n    self._status.setText('Could not load')\n", "surfaced"),
    ("except Exception:\n    raise\n", "reraise"),
])
def test_classify_handler(handler_src: str, expected: str) -> None:
    assert _classify(handler_src) == expected


def test_log_warning_is_a_log_line_not_a_ui_surface() -> None:
    """Pin the trap the first census fell into.

    `QMessageBox.warning` and `_log.warning` share the attribute name. A classifier
    keyed on the attribute alone counts every log line as a user-visible surface and
    inflates "surfaced" with exactly the failures that reach no one. The receiver
    decides, not the method name.
    """
    assert _classify("except Exception:\n    log.warning('x')\n") == "log_high"
    assert _classify("except Exception:\n    QMessageBox.warning(None, 'a', 'b')\n") == "surfaced"


@pytest.mark.parametrize("handler_src, broad", [
    ("except:\n    pass\n", True),
    ("except Exception:\n    pass\n", True),
    ("except BaseException:\n    pass\n", True),
    ("except (OSError, Exception):\n    pass\n", True),
    ("except OSError:\n    pass\n", False),
    ("except (RuntimeError, ValueError):\n    pass\n", False),
])
def test_is_broad(handler_src: str, broad: bool) -> None:
    assert _is_broad(handler_src) is broad


def test_find_silent_broad_handlers_counts_only_pass_and_constant_fallbacks() -> None:
    sources = {
        "modules/a.py": textwrap.dedent("""
            def f():
                try:
                    g()
                except Exception:
                    pass  # silent
                try:
                    g()
                except Exception:
                    return None
                try:
                    g()
                except Exception:
                    _log.debug("recorded at debug", exc_info=True)
                try:
                    g()
                except OSError:
                    pass  # narrow -- not counted
        """),
        "ui/b.py": textwrap.dedent("""
            def h(self):
                try:
                    g()
                except Exception as exc:
                    self._status.setText("Could not refresh")
        """),
    }
    hits = ces.find_silent_broad_handlers(sources)
    assert [(h.path, h.detail) for h in hits] == [
        ("modules/a.py", "pass"),
        ("modules/a.py", "silent_default"),
    ]
    assert ces.count_by_area(hits) == {"modules": 2}


def test_area_of() -> None:
    assert ces.area_of("modules/utils_net.py") == "modules"
    assert ces.area_of("ui/pages/home_page.py") == "ui"
    assert ces.area_of("workers/scan_worker.py") == "workers"
    assert ces.area_of("app.py") == "entrypoints"


# ── (a) raw exception text in user-visible sinks ─────────────────────────────

def _raw_sinks(src: str) -> list[int]:
    return [h.line for h in ces.find_raw_exception_ui_sinks({"ui/x.py": textwrap.dedent(src)})]


def test_raw_sink_except_bound_name_in_toast() -> None:
    assert _raw_sinks("""
        def export(self):
            try:
                write()
            except Exception as exc:
                ToastManager.show(f"Export failed: {exc}", "error")
    """) == [6]


def test_raw_sink_str_of_exception_in_message_box() -> None:
    assert _raw_sinks("""
        def copy(self):
            try:
                write()
            except OSError as err:
                QMessageBox.warning(self, "Copy Failed", str(err))
    """) == [6]


def test_raw_sink_error_signal_lambda() -> None:
    assert _raw_sinks("""
        def wire(self):
            self._worker.error.connect(lambda e: self._status.setText(f"⚠ {e}"))
    """) == [3]


def test_raw_sink_error_slot_parameter() -> None:
    assert _raw_sinks("""
        class Page:
            def on_error(self, msg):
                self._status_lbl.setText(f"⚠ {msg}")

            def _on_scan_failed(self, text):
                self._status_bar.showMessage(text)
    """) == [4, 7]


# S6b.4 — the sink shapes S6's sizing found the census could not see.

def test_raw_sink_chart_title_and_axes_text() -> None:
    assert _raw_sinks("""
        def wire(self):
            self._worker.error.connect(lambda e: self._ax.set_title(f"⚠ {e}"))

        def _on_error(self, msg):
            self._ax.text(0.5, 0.5, msg, ha="center")
    """) == [3, 6]


def test_raw_sink_list_item_and_local_status_function() -> None:
    assert _raw_sinks("""
        def _on_fetch_error(self, msg):
            self._list.addItem(QListWidgetItem(f"⚠ {msg}"))

        def dialog(self):
            def _set_status(text, color):
                status.setText(text)

            def _on_failure(msg):
                _set_status(f"✗ {msg}", "red")
    """) == [3, 10]


def test_raw_sink_not_testable_slot() -> None:
    assert _raw_sinks("""
        def _on_abuse_not_testable(self, msg):
            self._lookup.setText(f"AbuseIPDB: could not test — {msg}")
    """) == [3]


def test_raw_sink_append_family_counts_in_ui_only() -> None:
    src = textwrap.dedent("""
        def run(self):
            try:
                work()
            except Exception as exc:
                self._log.appendHtml(f"<b>{exc}</b>")
                self._box.insertPlainText(str(exc))
                self._view.setHtml(str(exc))
                self._log.append(f"failed: {exc}")
    """)
    assert [h.line for h in ces.find_raw_exception_ui_sinks({"ui/x.py": src})] == [6, 7, 8, 9]
    # A module's `errors.append(str(exc))` is data, not a widget write (owner decision S6.4).
    assert ces.find_raw_exception_ui_sinks({"modules/x.py": src}) == []


def test_an_exception_handed_to_the_translator_is_not_raw() -> None:
    """worker_error_text(spec, exc) shows only the spec's (or explain()'s) wording — never exc's text."""
    assert _raw_sinks("""
        def save(self):
            try:
                write()
            except OSError as exc:
                self._set_status(worker_error_text(WE.SAVE, exc))
                self._log.appendPlainText(f"  {worker_error_text(WE.SAVE, exc)}")
                self._set_status(f"{worker_error_text(WE.SAVE, exc)} ({exc})")
    """) == [8]


# ── A caught exception reaches the error helpers as itself (S6b.4) ──────────────

def _stringified(src: str) -> list[int]:
    return [h.line for h in ces.find_stringified_exception_args({"ui/x.py": textwrap.dedent(src)})]


def test_helpers_given_str_of_the_caught_exception_are_flagged() -> None:
    assert _stringified("""
        def save(self):
            try:
                write()
            except OSError as exc:
                show_worker_error(self._lbl, str(exc), WE.SAVE)
                export_failed(exc.args[0], WE.SAVE)
                self._set_status(worker_error_text(WE.SAVE, f"{exc}"))
                record_worker_error(WE.SAVE, repr(exc))
                show_error_dialog(self, str(exc), WE.SAVE)
    """) == [6, 7, 8, 9, 10]


def test_helpers_given_the_exception_or_a_worker_string_are_not_flagged() -> None:
    assert _stringified("""
        def save(self):
            try:
                write()
            except OSError as exc:
                show_worker_error(self._lbl, exc, WE.SAVE)
                self._set_status(worker_error_text(WE.SAVE))
                self._nav_set_scan_state("Devices", "error", error=str(exc))

        def _on_error(self, msg):
            show_worker_error(self._lbl, msg, WE.SAVE)
    """) == []


@pytest.mark.parametrize("src", [
    # a loop variable that happens to be called `e` is not an exception
    """
    def render(self, rows):
        for e in rows:
            self._lbl.setText(f"{e}")
    """,
    # the raw text belongs in the Details pane / tooltip -- that is the fix, not the defect
    """
    def fail(self):
        try:
            write()
        except Exception as exc:
            box.setDetailedText(str(exc))
            self._lbl.setToolTip(str(exc))
            self._lbl.setText("Could not save the report.")
    """,
    # a non-error signal's lambda parameter is data, not an error
    """
    def wire(self):
        self._worker.status.connect(lambda m: self._status.setText(m))
    """,
])
def test_raw_sink_negatives(src: str) -> None:
    assert _raw_sinks(src) == []


# ── (c) toast kinds ──────────────────────────────────────────────────────────

def test_valid_toast_kinds_are_read_from_the_toast_module() -> None:
    """Derived from toast.py, never duplicated: adding a kind there updates the check."""
    assert ces.valid_toast_kinds() == frozenset({"success", "error", "warning", "info", "action"})


def test_find_invalid_toast_kinds() -> None:
    src = textwrap.dedent("""
        def f(self):
            ToastManager.show("ok", "success")
            ToastManager.show("default kind")
            ToastManager.show("grade dropped", "warning")
            ToastManager.show("boom", kind="fatal")
    """)
    hits = ces.find_invalid_toast_kinds({"ui/x.py": src}, valid=frozenset({"success", "error"}))
    assert [(h.line, h.detail) for h in hits] == [(5, "warning"), (6, "fatal")]


# ── (d) scan-state error paths ───────────────────────────────────────────────

def test_scan_state_label_spellings_are_merged() -> None:
    """A label is set both as a NavLabel member and as a bare string in this repo
    ("TLS & Exposure" vs L.TLS_EXPOSURE). Keyed on spelling, the two halves each look
    incomplete; keyed on the resolved value, the label is covered."""
    sources = {
        "ui/a.py": textwrap.dedent("""
            def start(self):
                self._nav_set_scan_state(L.SPEED_TEST, "running")
                self._nav_set_scan_state(NavLabel.WIFI_NETWORKS, "fresh", ts=1.0)
        """),
        "app.py": textwrap.dedent("""
            def wire(window, label):
                window._nav_set_scan_state("Speed Test", "error", error="x")
                window._nav_set_scan_state(label, "stale")   # unresolvable -- ignored
        """),
    }
    nav = {"SPEED_TEST": "Speed Test", "WIFI_NETWORKS": "WiFi Networks"}
    coverage = ces.scan_state_coverage(sources, nav_labels=nav)
    assert coverage == {"Speed Test": {"running", "error"}, "WiFi Networks": {"fresh"}}
    assert ces.find_scan_labels_without_error_path(sources, nav_labels=nav) == ["WiFi Networks"]


def test_not_testable_counts_as_an_error_path() -> None:
    sources = {"ui/a.py": 'def f(s):\n    s._nav_set_scan_state("X", "running")\n'
                          '    s._nav_set_scan_state("X", "not_testable")\n'}
    assert ces.find_scan_labels_without_error_path(sources, nav_labels={}) == []


def test_real_nav_labels_resolve() -> None:
    nav = ces.load_nav_labels()
    assert nav["SPEED_TEST"] == "Speed Test"
    assert nav["PORT_SCAN_TCP"] == "Port Scan (TCP)"


# ── S7.1 triage worksheet (--worksheet) ──────────────────────────────────────

_WORKSHEET_SRC = textwrap.dedent("""
    import platform

    try:
        import winreg
    except Exception:
        winreg = None  # optional off Windows

    class Scanner:
        def scan(self, hosts):
            out = []
            for h in hosts:
                try:
                    out.append(probe(h))
                except Exception:
                    continue  # host did not answer
            system = platform.system()
            if system == "Windows":
                try:
                    return read_netsh()
                except Exception:
                    return []
            elif system == "Darwin":
                try:
                    return read_airport()
                except Exception:
                    pass  # no airport binary
            else:
                try:
                    first()
                    second()
                except Exception:
                    try:
                        fallback()
                    except Exception:
                        pass
            return out

    def narrow():
        try:
            g()
        except OSError:
            pass  # narrow -- not in the worksheet
""")


def test_worksheet_has_one_row_per_silent_broad_handler() -> None:
    sources = {"modules/x.py": _WORKSHEET_SRC}
    rows = ces.build_worksheet(sources)
    assert [(r.path, r.line, r.category) for r in rows] == [
        (h.path, h.line, h.detail) for h in ces.find_silent_broad_handlers(sources)
    ]
    assert len(rows) == 5


def test_worksheet_row_names_function_attempt_fallback_and_comment() -> None:
    rows = ces.build_worksheet({"modules/x.py": _WORKSHEET_SRC})
    module_level, loop, windows, nested = rows[0], rows[1], rows[2], rows[4]
    assert module_level.function == "<module>"
    assert module_level.attempt == "import winreg"
    assert module_level.fallback == "winreg = None"
    assert module_level.comment == "optional off Windows"
    assert loop.function == "Scanner.scan"
    assert loop.attempt == "out.append(probe(h))"
    assert loop.fallback == "continue"
    assert loop.comment == "host did not answer"
    assert windows.fallback == "return []"
    assert windows.comment == ""
    assert nested.attempt == "fallback()"


def test_worksheet_shape_hints() -> None:
    """Facts the triager would otherwise re-derive by reading: none of them is a verdict."""
    rows = ces.build_worksheet({"modules/x.py": _WORKSHEET_SRC})
    assert [r.shapes for r in rows] == [
        ("import",),
        ("loop",),
        ("windows",),
        ("non-windows",),       # elif system == "Darwin"
        ("non-windows", "nested"),  # the else branch, a fallback inside a handler
    ]


def test_worksheet_platform_hint_follows_a_negated_test() -> None:
    src = textwrap.dedent("""
        def f():
            if platform.system() != "Windows":
                try:
                    a()
                except Exception:
                    pass
            if not IS_WINDOWS:
                return
            try:
                b()
            except Exception:
                pass
    """)
    first, second = ces.build_worksheet({"modules/p.py": src})
    assert first.shapes == ("non-windows",)
    assert second.shapes == (), "code after an early return is not inside the if -- no hint"


def test_worksheet_attempt_notes_further_statements() -> None:
    src = "def f():\n    try:\n        a()\n        b()\n        c()\n    except Exception:\n        pass\n"
    (row,) = ces.build_worksheet({"modules/p.py": src})
    assert row.attempt == "a()  (+2 more)"


def test_worksheet_filters_by_path_prefix() -> None:
    sources = {"modules/x.py": _WORKSHEET_SRC, "ui/y.py": _WORKSHEET_SRC}
    assert {r.path for r in ces.build_worksheet(sources, paths=["ui/"])} == {"ui/y.py"}
    assert {r.path for r in ces.build_worksheet(sources, paths=["modules/x.py"])} == {"modules/x.py"}
    assert {r.path for r in ces.build_worksheet(sources, paths=["modules\\x.py"])} == {"modules/x.py"}


def test_worksheet_markdown_groups_by_file_escapes_pipes_and_leaves_the_verdict_blank() -> None:
    src = "def f():\n    try:\n        a = b | c\n    except Exception:\n        pass  # x | y\n"
    text = ces.format_worksheet(ces.build_worksheet({"modules/p.py": src}))
    assert "### modules/p.py — 1" in text
    row = next(line for line in text.splitlines() if line.startswith("| 4 |"))
    assert "b \\| c" in row and "x \\| y" in row
    assert row.endswith("|  |"), "the verdict column is for the triager, never pre-filled"


def test_cli_worksheet_prints_only_the_worksheet(monkeypatch, capsys) -> None:
    monkeypatch.setattr(ces, "load_production_sources", lambda: {"modules/x.py": _WORKSHEET_SRC,
                                                                 "ui/y.py": _WORKSHEET_SRC})
    assert ces.main(["--worksheet", "modules/"]) == 0
    out = capsys.readouterr().out
    assert "### modules/x.py — 5" in out
    assert "ui/y.py" not in out
    assert "Broad/narrow except handlers" not in out


# ── Ratchets against the real tree ───────────────────────────────────────────
#
# Measured 2026-09-15 on 379bf5f. Shrink-only: raising a baseline to make a failure
# go away defeats the check. Lower a baseline in the same commit that removes hits;
# the *_is_not_stale tests force that once the real count drops below it.

STALE_SLACK = 5

# (b) broad handlers whose body is only `pass` or a constant/name fallback.
# modules 304 -> 224 at S7 (2026-09-19): the 80 detection-module handlers triaged in S7.1 —
# 75 expected (debug log with exc_info) + B1/B3/B4 (the result says what did not run). The
# 5 left in those files are S7b by decision: B2 x2, B5, B6, B7.
BASELINE_SILENT_BROAD = {"entrypoints": 37, "modules": 224, "ui": 376, "workers": 14}

# (c) (path, kind) -> count.
# Empty as of S1.3 (2026-09-16): "warning" is now a real kind in toast.py
# (AMBER, ⚠, 6s auto-dismiss), which fixed all three call sites at once.
KNOWN_INVALID_TOAST_KINDS: dict[tuple[str, str], int] = {}

# (d) labels set running/fresh but never error/not_testable.
# Empty as of S1.2 (2026-09-16) — every scan label can now reach "error".
# Behavioural coverage for the four page-level fixes: tests/test_error_surfacing_s1.py.
KNOWN_LABELS_WITHOUT_ERROR_PATH: frozenset[str] = frozenset()


def test_no_new_silent_broad_handlers() -> None:
    """A new broad `except` must not swallow silently (audit decision D6).

    If this fails, pick one for the new handler:
      * narrow it to the exception you actually expect (then it is not counted), or
      * `_log.debug("what failed", exc_info=True)` if the failure really is harmless, or
      * mark the result degraded / partial / not_testable if it changes what the user sees, or
      * surface it (signal, page status, scan state) if a feature stopped working.
    A comment on `pass` satisfies RULE-LINT2 but not this check -- the comment says why
    it is silenced, not whether anyone should have been told.
    """
    hits = ces.find_silent_broad_handlers()
    counts = ces.count_by_area(hits)
    grown = {
        area: (counts.get(area, 0), baseline)
        for area, baseline in BASELINE_SILENT_BROAD.items()
        if counts.get(area, 0) > baseline
    }
    assert not grown, (
        "New silent broad except handlers (area: now vs baseline): "
        f"{grown}. Run `python tools/check_error_surfacing.py` to list them."
    )


def test_silent_broad_baseline_is_not_stale() -> None:
    counts = ces.count_by_area(ces.find_silent_broad_handlers())
    stale = {
        area: (counts.get(area, 0), baseline)
        for area, baseline in BASELINE_SILENT_BROAD.items()
        if counts.get(area, 0) < baseline - STALE_SLACK
    }
    assert not stale, f"Lower BASELINE_SILENT_BROAD to the current counts (now vs baseline): {stale}"


def test_no_raw_exception_ui_sinks() -> None:
    """RULE-A2: never show a raw exception as the message. Hard zero since S6b (2026-09-17).

    History: 95 at S0 -> 63 (S5 worker-error lambdas and slots) -> 26 (S6 exports, dialogs, the last
    worker sinks) -> 0 (S6b: the except-as label/status sites, after the census learned chart titles,
    Axes.text, list items, local status functions, not_testable slots and the ui/ append family).

    Fix a hit with ``ui/error_display.py``: ``show_worker_error(label, exc, WE.<ENTRY>)`` for a label,
    ``worker_error_text(WE.<ENTRY>, exc)`` + ``record_worker_error(WE.<ENTRY>, exc)`` for a sink with
    no tooltip (status bar, text pane, chart), ``export_failed`` / ``show_error_dialog`` for a save or
    a dialog. Entries live in ``ui/worker_error_catalogue.py``. Raw text belongs in the tooltip,
    ``setDetailedText()`` or the app log — never the message.
    """
    hits = ces.find_raw_exception_ui_sinks()
    assert not hits, (
        f"{len(hits)} raw exception sink(s) — see this test's docstring for the fix:\n"
        + "\n".join(f"  {h.path}:{h.line}  {h.detail}" for h in hits)
    )


def test_error_helpers_receive_the_exception_not_its_text() -> None:
    """Inside ``except ... as exc`` pass ``exc``: ``str(exc)`` silently loses explain() and the traceback."""
    hits = ces.find_stringified_exception_args()
    assert not hits, (
        "error-display helpers handed text of a caught exception — pass the exception itself:\n"
        + "\n".join(f"  {h.path}:{h.line}  {h.detail}" for h in hits)
    )


def test_no_new_invalid_toast_kinds() -> None:
    from collections import Counter

    found = Counter((h.path, h.detail) for h in ces.find_invalid_toast_kinds())
    new = {key: n for key, n in found.items() if n > KNOWN_INVALID_TOAST_KINDS.get(key, 0)}
    assert not new, (
        f"ToastManager.show() with an undefined kind: {new}. Valid kinds are "
        f"{sorted(ces.valid_toast_kinds())}; an unknown kind renders as a sticky info toast."
    )
    fixed = {key for key in KNOWN_INVALID_TOAST_KINDS if key not in found}
    assert not fixed, f"Remove fixed entries from KNOWN_INVALID_TOAST_KINDS: {sorted(fixed)}"


def test_no_new_scan_labels_without_error_path() -> None:
    """A label that can go running/fresh must be able to go error or not_testable too.

    Otherwise a failed run sits on "running" until restart, or keeps showing the last
    success -- the registry reports health the tool no longer has.
    """
    found = set(ces.find_scan_labels_without_error_path())
    new = found - KNOWN_LABELS_WITHOUT_ERROR_PATH
    assert not new, (
        f"Scan labels with no error/not_testable path: {sorted(new)}. Wire the worker's "
        "error slot to _nav_set_scan_state(label, 'error', error=...)."
    )
    fixed = KNOWN_LABELS_WITHOUT_ERROR_PATH - found
    assert not fixed, f"Remove fixed labels from KNOWN_LABELS_WITHOUT_ERROR_PATH: {sorted(fixed)}"
