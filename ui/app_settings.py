"""
app_settings.py — Window geometry and QSettings persistence helpers.

Extracted from ui/dashboard.py (Sprint 6, S13-4).
These are pure persistence functions: they take a Dashboard window reference
and read/write QSettings / window geometry.  No UI construction logic.
"""
from __future__ import annotations

from pathlib import Path


def settings_path() -> Path:
    """
    Return the path to NetSentinel.ini.

    Priority:
      1. Same directory as the running executable / script (portable use —
         settings travel with the exe on a USB stick or shared folder).
      2. Fallback: ~/.config/NetSentinel/NetSentinel.ini (if the exe dir
         is not writable, e.g. installed in Program Files).
    """
    import sys as _sys
    exe_dir = Path(_sys.executable).parent if getattr(_sys, "frozen", False) \
        else Path(__file__).resolve().parent.parent
    candidate = exe_dir / "NetSentinel.ini"
    try:
        candidate.touch(exist_ok=True)
        return candidate
    except OSError:
        fallback = Path.home() / ".config" / "NetSentinel" / "NetSentinel.ini"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return fallback


def center_on_screen(window, w: int, h: int) -> None:
    """Resize window to w×h and center on the primary screen."""
    from PyQt6.QtGui import QGuiApplication
    screen = QGuiApplication.primaryScreen()
    if screen is not None:
        ag = screen.availableGeometry()
        x = ag.x() + (ag.width()  - w) // 2
        y = ag.y() + (ag.height() - h) // 2
        window.setGeometry(x, y, w, h)
    else:
        window.resize(w, h)


def save_settings(window) -> None:
    """Persist window geometry, nav state, and scan inputs to NetSentinel.ini."""
    from PyQt6.QtCore import QSettings
    s = QSettings(str(window._settings_path()), QSettings.Format.IniFormat)
    # Window geometry (save maximized state separately — restoreGeometry alone
    # is unreliable for frameless windows before show() is called)
    s.setValue("window/geometry", window.saveGeometry().toBase64().data().decode())
    s.setValue("window/maximized", str(window.isMaximized()))
    # Persist the pre-maximize size so the next startup restores correctly.
    if window.isMaximized() and window._pre_maximize_geo is not None:
        r = window._pre_maximize_geo
        s.setValue("window/normal_x", r.x())
        s.setValue("window/normal_y", r.y())
        s.setValue("window/normal_width", r.width())
        s.setValue("window/normal_height", r.height())
    # Sidebar nav state
    s.setValue("nav/collapsed", str(window._nav_collapsed))
    for _hrow, _grp in window._nav_section_groups.items():
        if _grp["level"] == 0:
            s.setValue(f"nav/section_{_hrow}_collapsed", str(_grp["collapsed"]))
    if hasattr(window, "_ps_host"):
        s.setValue("scan/last_port_scan_host", window._ps_host.text())
    if hasattr(window, "_ps_mode"):
        s.setValue("scan/port_scan_mode", window._ps_mode.currentText())
    if hasattr(window, "_syn_host"):
        s.setValue("scan/last_syn_host", window._syn_host.text())
    if hasattr(window, "_syn_ports_combo"):
        s.setValue("scan/syn_port_range", window._syn_ports_combo.currentText())
    if hasattr(window, "_syn_rate"):
        s.setValue("scan/syn_rate_pps", window._syn_rate.value())
    if hasattr(window, "_udp_host"):
        s.setValue("scan/last_udp_host", window._udp_host.text())
    s.sync()
    # Refresh cache so changeEvent() picks up any settings change without a restart
    window._minimize_to_tray = QSettings("NetSentinel", "NetSentinel").value(
        "tray/minimize_window_to_tray", False, type=bool)


def restore_settings(window) -> None:
    """Restore window geometry, nav state, and scan inputs from NetSentinel.ini."""
    from PyQt6.QtCore import QSettings, QByteArray
    s = QSettings(str(window._settings_path()), QSettings.Format.IniFormat)
    # Window geometry
    geom_b64 = s.value("window/geometry", "")
    was_maximized = s.value("window/maximized", "False") == "True"
    # Fresh-install / no-saved-geometry fallback: 1280×800 centered on primary screen.
    center_on_screen(window, 1280, 800)
    if was_maximized:
        nx = s.value("window/normal_x")
        ny = s.value("window/normal_y")
        nw = s.value("window/normal_width", "1280")
        nh = s.value("window/normal_height", "800")
        try:
            nw_i, nh_i = int(nw), int(nh)
        except (ValueError, TypeError):
            nw_i, nh_i = 1280, 800
        window.resize(nw_i, nh_i)
        # Store for SetWindowPlacement in app.py (fixes showNormal() restore position).
        try:
            window._pending_normal_geo = (
                (int(nx), int(ny), nw_i, nh_i)
                if nx is not None and ny is not None else None
            )
        except (ValueError, TypeError):
            window._pending_normal_geo = None
        # Show maximized HERE during construction, with no prior setGeometry().
        # The HWND is created with Qt's default position — there is no
        # "animate-from-normal" rect for the maximize transition, so Windows
        # cannot animate from the saved off-screen-left position through the splash.
        # The backbuffer stays unpainted until _splash.close() fires in app.py,
        # giving an atomic transition (same DWM frame) from splash to app.
        # This is the same pattern that worked in v1.9.17.
        window.showMaximized()
    elif geom_b64:
        try:
            window.restoreGeometry(QByteArray.fromBase64(geom_b64.encode()))
        except Exception:
            pass
    # Sidebar nav state
    if s.value("nav/collapsed", "False") == "True" and not window._nav_collapsed:
        window._toggle_sidebar()
    for _hrow in list(window._nav_section_groups.keys()):
        _grp = window._nav_section_groups[_hrow]
        if _grp["level"] == 0:
            # Top-level sections
            _saved = s.value(f"nav/section_{_hrow}_collapsed", None)
            if _saved is not None and (_saved == "True") != _grp["collapsed"]:
                window._nav_toggle_section(_hrow)
        else:
            # Subgroups: restore saved preference; fall back to the group's own default
            _saved = s.value(f"nav/group_{_hrow}_collapsed", None)
            _want_collapsed = (_saved == "True") if _saved is not None else _grp["collapsed"]
            if _want_collapsed != _grp["collapsed"]:
                window._nav_toggle_section(_hrow)
    if hasattr(window, "_ps_host"):
        host = s.value("scan/last_port_scan_host", "")
        if host:
            window._ps_host.setText(host)
    if hasattr(window, "_ps_mode"):
        mode = s.value("scan/port_scan_mode", "")
        if mode:
            idx = window._ps_mode.findText(mode)
            if idx >= 0:
                window._ps_mode.setCurrentIndex(idx)
    if hasattr(window, "_syn_host"):
        syn_host = s.value("scan/last_syn_host", "")
        if syn_host:
            window._syn_host.setText(syn_host)
    if hasattr(window, "_syn_ports_combo"):
        syn_range = s.value("scan/syn_port_range", "")
        if syn_range:
            idx = window._syn_ports_combo.findText(syn_range)
            if idx >= 0:
                window._syn_ports_combo.setCurrentIndex(idx)
    if hasattr(window, "_syn_rate"):
        rate = s.value("scan/syn_rate_pps", 500, type=int)
        window._syn_rate.setValue(rate)
    if hasattr(window, "_udp_host"):
        udp_host = s.value("scan/last_udp_host", "")
        if udp_host:
            window._udp_host.setText(udp_host)
    window._rebuild_nav_for_mode()

    # On first launch, default the logger to auto-start so monitoring begins immediately.
    _qs_app = QSettings("NetSentinel", "NetSentinel")
    if _qs_app.value("logger/auto_start") is None:
        _qs_app.setValue("logger/auto_start", True)
        if hasattr(window, "_log_chk_autostart"):
            window._log_chk_autostart.setChecked(True)

    # Auto-start stability logger if the user opted in (or on first launch)
    if _qs_app.value("logger/auto_start", True, type=bool):
        from PyQt6.QtCore import QTimer as _QTimer
        _QTimer.singleShot(1500, window._toggle_logger)

    # Retention helpers — run after the event loop is warm
    from PyQt6.QtCore import QTimer as _QT2
    _QT2.singleShot(2000, window._compute_last_visit_summary)
    _QT2.singleShot(4000, window._maybe_send_weekly_digest)

    # Cache minimize-to-tray setting once so changeEvent() has no QSettings I/O
    window._minimize_to_tray = QSettings("NetSentinel", "NetSentinel").value(
        "tray/minimize_window_to_tray", False, type=bool)
