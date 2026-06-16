"""
context_banners.py — QSettings helpers for first-visit page context banners (S7-1).

QSettings key: banner/<page_key>_seen
  True  → user has dismissed (or already seen) the banner for this page; never show again.
  False / absent → show the banner the next time PageHeaderBar.show_first_visit_banner()
  is called for this page_key.
"""
from __future__ import annotations

from PyQt6.QtCore import QSettings


def should_show_banner(page_key: str) -> bool:
    qs = QSettings("NetSentinel", "NetSentinel")
    return not qs.value(f"banner/{page_key}_seen", False, type=bool)


def mark_banner_seen(page_key: str) -> None:
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.setValue(f"banner/{page_key}_seen", True)
