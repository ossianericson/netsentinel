"""
ui.nav — Activity-rail navigation widget package.

Re-exports the public surface so callers can do:
    from ui.nav import _RailButton, _FlyoutPanel, _make_nav_icon
    from ui.nav import _NavBuilderMixin, _AUTO_HELP_PAGES
"""
from ui.nav.rail import (
    _LUCIDE,
    _make_nav_icon,
    _NavEntry,
    _RailButton,
    _FlyoutItem,
    _FlyoutPanel,
    _CanvasClickFilter,
    _ClickLabel,
    _SmoothProgressBar,
)
from ui.nav.builder import _NavBuilderMixin, _AUTO_HELP_PAGES

__all__ = [
    "_LUCIDE",
    "_make_nav_icon",
    "_NavEntry",
    "_RailButton",
    "_FlyoutItem",
    "_FlyoutPanel",
    "_CanvasClickFilter",
    "_ClickLabel",
    "_SmoothProgressBar",
    "_NavBuilderMixin",
    "_AUTO_HELP_PAGES",
]
