"""The fatal dialog as a reporting affordance (B3).

`app.py::_fatal()` is the last thing a user sees when the app dies, and it spent
that moment showing them a raw Python traceback — a RULE-A2 violation, and a
wasted opportunity: the one instant when the person is looking at the crash,
motivated, and holding every log the crash produced.

Two constraints bound the change and neither may be relaxed:

* **RULE-WIN20.** PyQt6 routes an exception escaping `QThread.run()` through
  `sys.excepthook`, so `_fatal` is legitimately entered on a worker thread, where
  constructing a QWidget is undefined behaviour. Only the GUI-thread branch gains
  buttons; the thread-affinity guard is untouched and
  `tests/test_crash_handler_encoding.py` still pins it.
* **The evidence must survive the prettier presentation.** A dialog that shows a
  plain-English sentence and then drops the traceback on the floor is strictly
  worse than the raw one it replaced.
"""
from __future__ import annotations

import pytest

_TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "C:\\Code\\netsentinel\\ui\\scan_enrichment.py", line 412, in _norm_mac\n'
    "AttributeError: 'NoneType' object has no attribute 'strip'\n"
)


class _FakeButton:
    def __init__(self, text=""):
        self._text = text

    def text(self):
        return self._text


@pytest.fixture
def dialog(monkeypatch):
    """Replace QMessageBox with a recorder, and report what `_fatal` did to it.

    A recorder rather than a real QMessageBox because `exec()` blocks forever
    with nobody to click it. The enum members are taken off the real class so a
    typo in an enum path still fails here rather than only in front of a user.
    """
    from PyQt6 import QtWidgets

    real = QtWidgets.QMessageBox
    seen: dict = {"buttons": [], "clicked_text": None}

    class _Recorder:
        Icon = real.Icon
        ButtonRole = real.ButtonRole
        StandardButton = real.StandardButton

        def __init__(self, *a, **k):
            seen["constructed"] = True

        def setIcon(self, icon):
            seen["icon"] = icon

        def setWindowTitle(self, title):
            seen["title"] = title

        def setText(self, text):
            seen["text"] = text

        def setInformativeText(self, text):
            seen["informative"] = text

        def setDetailedText(self, text):
            seen["detailed"] = text

        def addButton(self, *args):
            btn = _FakeButton(args[0] if isinstance(args[0], str) else "standard")
            seen["buttons"].append(btn)
            return btn

        def exec(self):
            seen["exec"] = True
            return 0

        def clickedButton(self):
            for btn in seen["buttons"]:
                if btn.text() == seen["clicked_text"]:
                    return btn
            return None

    monkeypatch.setattr(QtWidgets, "QMessageBox", _Recorder)
    return seen


def _call_fatal(**kwargs):
    """Drive `_fatal` on the GUI thread, absorbing its deliberate `sys.exit(1)`."""
    import app as _app

    with pytest.raises(SystemExit):
        _app._fatal("Unhandled Error", **kwargs)


def test_the_user_sees_plain_english_and_the_traceback_sits_behind_details(
    dialog, tmp_path, monkeypatch
):
    """RULE-A2 and RULE-A1 in one dialog: plain English first, detail available.

    `setDetailedText` is Qt's own collapsible "Show Details..." pane, so the
    traceback is one click away for anyone who wants it and absent for everyone
    who does not — which is the distinction RULE-A1 asks for, rather than a
    choice between dumping it and losing it.
    """
    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: tmp_path)

    _call_fatal(message="NetSentinel hit an unexpected error.", details=_TRACEBACK)

    assert "Traceback" not in dialog["text"], (
        "the raw traceback is still the dialog's main text (RULE-A2)"
    )
    assert "Traceback" in dialog.get("detailed", ""), (
        "the traceback was dropped rather than moved behind Details"
    )


def test_a_message_that_is_already_plain_english_is_not_replaced(dialog, tmp_path, monkeypatch):
    """`_fatal` has callers whose message is already the right thing to show.

    `_check_python_version()` and `_check_pyqt()` pass actionable prose with no
    traceback at all. Swapping in a generic "unexpected error" line would make
    those two worse, so the plain-English body belongs at the traceback call
    sites, not inside `_fatal`.
    """
    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: tmp_path)

    _call_fatal(message="PyQt6 is not installed.\nRun:  pip install -r requirements.txt")

    assert "pip install" in dialog["text"]
    assert "detailed" not in dialog


def test_the_dialog_offers_to_save_a_report_and_to_copy_the_details(
    dialog, tmp_path, monkeypatch
):
    """The affordance itself — without buttons this is just a nicer traceback."""
    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: tmp_path)

    _call_fatal(message="NetSentinel hit an unexpected error.", details=_TRACEBACK)

    labels = [b.text() for b in dialog["buttons"]]
    assert "Save report" in labels
    assert "Copy details" in labels


def test_clicking_save_report_writes_a_real_report(dialog, tmp_path, monkeypatch):
    """The button must produce a file, not merely exist (RULE-DBG5).

    And the report is worth more than the traceback it came from: `crash_net`'s
    `_excepthook` writes the traceback to `netsentinel_exceptions.log` *before*
    calling this notifier, so `build_report()` tails it back in — arriving with
    the environment fingerprint and the session history around it.
    """
    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: tmp_path)
    dialog["clicked_text"] = "Save report"

    _call_fatal(message="NetSentinel hit an unexpected error.", details=_TRACEBACK)

    reports = list((tmp_path / "reports").glob("netsentinel-diagnostic-*.md"))
    assert len(reports) == 1, "Save report is wired to nothing"


def test_clicking_copy_details_puts_the_traceback_on_the_clipboard(
    dialog, tmp_path, monkeypatch
):
    """For the user who is going to paste it into an issue right now."""
    from PyQt6.QtWidgets import QApplication

    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: tmp_path)
    dialog["clicked_text"] = "Copy details"

    _call_fatal(message="NetSentinel hit an unexpected error.", details=_TRACEBACK)

    assert "AttributeError" in QApplication.clipboard().text()


def test_the_fallback_log_still_carries_the_traceback_not_just_the_summary(
    tmp_path, monkeypatch
):
    """When no dialog can be built, the evidence must not shrink to a summary.

    This is the path taken on a machine where Qt itself is broken — exactly the
    case where the written file is the only artefact that will ever exist.
    """
    from PyQt6 import QtWidgets

    import app as _app

    class _NoGui:
        def __init__(self, *a, **k):
            raise RuntimeError("no GUI available")

    monkeypatch.setattr(QtWidgets, "QMessageBox", _NoGui)
    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: tmp_path)

    with pytest.raises(SystemExit):
        _app._fatal(
            "Unhandled Error",
            message="NetSentinel hit an unexpected error.",
            details=_TRACEBACK,
        )

    written = (tmp_path / "netsentinel_error.log").read_text(encoding="utf-8")
    assert "AttributeError" in written, "the traceback never reached the fallback log"


def test_the_excepthook_wiring_routes_the_traceback_into_details(dialog, tmp_path, monkeypatch):
    """The notifier `crash_net` actually calls must use the new shape.

    `crash_net.install()` invokes `on_unhandled(title, traceback_text)` — a
    two-positional-argument contract it does not know has changed. Passing
    `_fatal` straight through would put the traceback back into the dialog's main
    text and quietly restore the RULE-A2 violation, with every other test here
    still green. This drives the real installed hook instead.
    """
    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: tmp_path)

    import app as _app

    notifier = _app._crash_notifier
    with pytest.raises(SystemExit):
        notifier("Unhandled Error", _TRACEBACK)

    assert "Traceback" not in dialog["text"]
    assert "Traceback" in dialog.get("detailed", "")
