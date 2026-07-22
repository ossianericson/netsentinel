"""
ui/widgets/device_popover.py — Device quick-profile popover (DEVICE-1)

Floating Qt.Popup QFrame showing name, MAC, first/last seen, active alerts,
tags, and two navigation buttons. Triggered via right-click "Device Info" in
Connections, Log Hub, CVE, and Threat Intel tables.

Usage:
    popover = DevicePopover(parent=main_window)
    popover.set_store(store)
    popover.navigate_to_inventory.connect(handler)
    popover.navigate_to_threat_intel.connect(handler)
    # from a context menu:
    popover.show_for("192.168.1.22", QCursor.pos())
"""
from __future__ import annotations

import re
import time

from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ui import styles as _s

_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _fmt_ts(ts: float) -> str:
    if not ts:
        return "—"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def _fmt_elapsed(ts: float) -> str:
    if not ts:
        return "—"
    elapsed = max(0, int(time.time()) - int(ts))
    if elapsed < 60:
        return f"{elapsed}s ago"
    if elapsed < 3600:
        return f"{elapsed // 60}m ago"
    if elapsed < 86400:
        h, m = divmod(elapsed, 3600)
        return f"{h}h {m // 60:02d}m ago"
    return f"{elapsed // 86400}d ago"


class DevicePopover(QFrame):
    """Floating device quick-profile popup.

    Signals:
        navigate_to_inventory(str)    — carries ip or mac; nav + select row
        navigate_to_threat_intel(str) — carries ip
    """

    navigate_to_inventory    = pyqtSignal(str)
    navigate_to_threat_intel = pyqtSignal(str)

    _WIDTH = 290

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint,
        )
        self.setFixedWidth(self._WIDTH)
        _s.themed_ss(self, "DevicePopover {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:6px; }}")
        self._store = None
        self._current_key = ""
        self._build_ui()

    # ── DI ───────────────────────────────────────────────────────────────────

    def set_store(self, store) -> None:
        self._store = store

    # ── Public API ────────────────────────────────────────────────────────────

    def show_for(self, ip_or_mac: str, global_pos: QPoint) -> None:
        """Populate and show the popover near global_pos."""
        self._current_key = ip_or_mac
        self._populate(ip_or_mac)
        self._reposition(global_pos)
        self.show()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setFixedHeight(36)
        _s.themed_ss(hdr, "background:{BG_DARK}; border-bottom:1px solid {BORDER};"
            " border-top-left-radius:6px; border-top-right-radius:6px;")
        hlay = QHBoxLayout(hdr)
        hlay.setContentsMargins(12, 0, 8, 0)
        hlay.setSpacing(6)

        self._name_lbl = QLabel("Device Info")
        _s.themed_ss(self._name_lbl, "color:{TEXT_PRIMARY}; font-size:11px; font-weight:bold;"
            " background:transparent; border:none;")

        self._alert_badge = QLabel()
        _s.themed_ss(self._alert_badge, "color:{WHITE}; font-size:9px; font-weight:bold;"
            " background:{RED}; border-radius:3px; padding:1px 5px; border:none;")
        self._alert_badge.setVisible(False)

        hlay.addWidget(self._name_lbl, 1)
        hlay.addWidget(self._alert_badge)
        root.addWidget(hdr)

        # Body
        body = QFrame()
        _s.themed_ss(body, "background:{BG_CARD}; border:none;")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(12, 10, 12, 8)
        bl.setSpacing(4)

        self._vendor_lbl  = self._row_label()
        self._mac_lbl     = self._row_label()
        self._ip_lbl      = self._row_label()
        self._first_lbl   = self._row_label()
        self._last_lbl    = self._row_label()
        self._tags_lbl    = self._row_label()

        for lbl in (self._vendor_lbl, self._mac_lbl, self._ip_lbl,
                    self._first_lbl, self._last_lbl, self._tags_lbl):
            bl.addWidget(lbl)

        root.addWidget(body)

        # Footer buttons
        ftr = QFrame()
        _s.themed_ss(ftr, "background:{BG_DARK}; border-top:1px solid {BORDER};"
            " border-bottom-left-radius:6px; border-bottom-right-radius:6px;")
        flay = QHBoxLayout(ftr)
        flay.setContentsMargins(8, 6, 8, 6)
        flay.setSpacing(6)

        self._inv_btn = QPushButton("Open in Inventory →")
        self._inv_btn.setFixedHeight(24)
        self._inv_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._inv_btn, "QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            " border-radius:3px; font-size:10px; padding:0 8px; }}"
            "QPushButton:hover {{ opacity:0.9; }}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}")
        self._inv_btn.clicked.connect(self._on_open_inventory)

        self._ti_btn = QPushButton("Threat Intel →")
        self._ti_btn.setFixedHeight(24)
        self._ti_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._ti_btn, "QPushButton {{ background:transparent; color:{ACCENT};"
            " border:1px solid {BORDER}; border-radius:3px; font-size:10px; padding:0 8px; }}"
            "QPushButton:hover {{ border-color:{ACCENT}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
        self._ti_btn.clicked.connect(self._on_open_threat_intel)

        flay.addWidget(self._inv_btn)
        flay.addWidget(self._ti_btn)
        root.addWidget(ftr)

    @staticmethod
    def _row_label() -> QLabel:
        lbl = QLabel()
        _s.themed_ss(lbl, "color:{TEXT_SECONDARY}; font-size:11px; background:transparent; border:none;")
        lbl.setVisible(False)
        return lbl

    # ── Populate ──────────────────────────────────────────────────────────────

    def _populate(self, ip_or_mac: str) -> None:
        dev = self._find_device(ip_or_mac)

        if dev is None:
            self._name_lbl.setText(f"{ip_or_mac}  —  Unknown")
            for lbl in (self._vendor_lbl, self._mac_lbl, self._ip_lbl,
                        self._first_lbl, self._last_lbl, self._tags_lbl):
                lbl.setVisible(False)
            self._alert_badge.setVisible(False)
            self._inv_btn.setEnabled(False)
            ip = ip_or_mac if _IP_RE.match(ip_or_mac) else ""
            self._ti_btn.setEnabled(bool(ip))
            return

        name = (getattr(dev, "custom_name", None) or
                getattr(dev, "hostname", None) or
                getattr(dev, "vendor", None) or
                "Unknown device")
        self._name_lbl.setText(name[:36])

        def _show(lbl: QLabel, prefix: str, val) -> None:
            if val:
                lbl.setText(f"{prefix}  {val}")
                lbl.setVisible(True)
            else:
                lbl.setVisible(False)

        _show(self._vendor_lbl, "Vendor", getattr(dev, "vendor", None))
        _show(self._mac_lbl,    "MAC",    getattr(dev, "mac", None))

        ip = getattr(dev, "ip", None)
        _show(self._ip_lbl, "IP", ip if ip != ip_or_mac else None)

        _show(self._first_lbl, "First seen", _fmt_ts(getattr(dev, "first_seen", 0)))
        _show(self._last_lbl,  "Last seen",  _fmt_elapsed(getattr(dev, "last_seen", 0)))
        _show(self._tags_lbl,  "Tags",       getattr(dev, "tags", None))

        # Active alert badge
        alert_count = self._count_active_alerts(ip_or_mac, ip)
        self._alert_badge.setText(f"  {alert_count} alert{'s' if alert_count != 1 else ''}  ")
        self._alert_badge.setVisible(alert_count > 0)

        self._inv_btn.setEnabled(True)
        self._ti_btn.setEnabled(bool(ip or _IP_RE.match(ip_or_mac)))

    def _find_device(self, ip_or_mac: str):
        if not self._store:
            return None
        try:
            devices = self._store.get_known_devices()
        except Exception:
            return None
        # Try MAC key first
        dev = devices.get(ip_or_mac)
        if dev:
            return dev
        # Try IP match
        for d in devices.values():
            if getattr(d, "ip", None) == ip_or_mac:
                return d
        return None

    def _count_active_alerts(self, *keys: str) -> int:
        if not self._store:
            return 0
        try:
            alerts = self._store.get_recent_alerts(hours=24)
        except Exception:
            return 0
        count = 0
        for a in alerts:
            host = a.get("host", "")
            if any(k and k == host for k in keys):
                count += 1
        return count

    # ── Positioning ───────────────────────────────────────────────────────────

    def _reposition(self, global_pos: QPoint) -> None:
        self.adjustSize()
        from PyQt6.QtWidgets import QApplication
        # global_pos is a virtual-desktop coordinate, so it may sit on any
        # monitor — clamp against the screen it actually lands on, not the
        # primary (which would drag the popover back onto the wrong monitor).
        screen = QApplication.screenAt(global_pos) or QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = min(global_pos.x() + 8, geo.right() - self.width() - 4)
            y = min(global_pos.y(), geo.bottom() - self.height() - 4)
            x = max(x, geo.left())
            y = max(y, geo.top())
            self.move(x, y)
        else:
            self.move(global_pos)

    # ── Action handlers ───────────────────────────────────────────────────────

    def _on_open_inventory(self) -> None:
        self.hide()
        self.navigate_to_inventory.emit(self._current_key)

    def _on_open_threat_intel(self) -> None:
        self.hide()
        dev = self._find_device(self._current_key)
        ip = (getattr(dev, "ip", None) if dev else None) or self._current_key
        self.navigate_to_threat_intel.emit(ip)
