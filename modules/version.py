"""The application version, importable from `modules/` (and therefore from anywhere).

`app.py`'s ``setApplicationVersion("…")`` call stays the canonical source of truth —
``bump_version.py`` and ``tests/test_version_consistency.py`` both key on it, and eleven
files already mirror it. This is the twelfth mirror, and it exists because the other
eleven are unreachable from the places that now need the version:

* ``modules/`` cannot import ``app.py`` (ARCH RULE 1), and
* ``modules/app_logging.py::configure()`` runs long before a ``QApplication`` exists to
  ask ``applicationVersion()``, at every entry point.

``svc.py`` is the reason this is a shared constant rather than a literal passed in by
each caller: it has no version string of its own, and it is the binary that runs
unattended as a Windows service, where "which build wrote this log?" is hardest to
answer by any other means.
"""
from __future__ import annotations

__all__ = ["APP_VERSION"]

#: Kept in step with app.py by bump_version.py; enforced by test_version_consistency.py.
APP_VERSION = "2.4.0"
