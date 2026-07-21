"""Behavioural tests -- _MonitorStateMixin._set_status() driving the real progress bar.

Part 1/C2: the progress bar (self._progress) must go determinate whenever a status
message carries a real "n/total" count (pre-scan ping sweep, Module 1 name
resolution) and fall back to indeterminate for messages with no known total
(Modules 2-5), rather than staying permanently indeterminate regardless of
what's actually happening (the original bug).

Exercises the real mixin method against a lightweight double instead of
constructing the full widget tree (RULE-T7 / RULE-TP4-DASH).
"""
from unittest.mock import MagicMock

from ui.monitor_state import _MonitorStateMixin


def _fake():
    fake = MagicMock()
    fake._status_bar = MagicMock()
    fake._progress = MagicMock()
    return fake


class TestSetStatusProgressBar:
    def test_message_with_count_sets_determinate_range(self):
        fake = _fake()
        _MonitorStateMixin._set_status(fake, "Identifying devices: 210/715…")
        fake._progress.setRange.assert_called_once_with(0, 715)
        fake._progress.setValue.assert_called_once_with(210)

    def test_ping_sweep_message_sets_determinate_range(self):
        fake = _fake()
        _MonitorStateMixin._set_status(fake, "Ping sweep: 60/254 hosts…")
        fake._progress.setRange.assert_called_once_with(0, 254)
        fake._progress.setValue.assert_called_once_with(60)

    def test_message_without_count_falls_back_to_indeterminate(self):
        fake = _fake()
        _MonitorStateMixin._set_status(fake, "Scanning for rogue bridges…")
        fake._progress.setRange.assert_called_once_with(0, 0)
        fake._progress.setValue.assert_not_called()

    def test_completion_message_sets_full_range(self):
        fake = _fake()
        _MonitorStateMixin._set_status(fake, "Identifying devices: 715/715…")
        fake._progress.setRange.assert_called_once_with(0, 715)
        fake._progress.setValue.assert_called_once_with(715)

    def test_still_updates_status_bar_text(self):
        fake = _fake()
        _MonitorStateMixin._set_status(fake, "Ready.")
        fake._status_bar.showMessage.assert_called_once_with("  Ready.")

    def test_safe_when_progress_bar_not_yet_constructed(self):
        """During early __init__, self._progress may not exist yet -- must not raise."""
        fake = MagicMock()
        fake._status_bar = MagicMock()
        del fake._progress
        _MonitorStateMixin._set_status(fake, "Starting…")  # must not raise
