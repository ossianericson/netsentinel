"""Tests for Ctrl+K natural-language aliases (Sprint 7, S7-5).

The command palette matches typed text as a substring against a per-item
"search" string built in `_NavBuilderMixin._build_palette_items()` as
``f"{name} {desc} {tags}".lower()`` (see ui/nav/builder.py). These tests
replicate that exact construction against `_FEATURES` so a future change to
either file that breaks the alias wiring is caught without needing a full
Dashboard instance.
"""
from ui.pages.discover_data import _FEATURES


def _search_string_for_page(page_label: str) -> str:
    """Build the same combined search string _build_palette_items() builds,
    for the first _FEATURES entry whose page matches page_label."""
    entry = next(f for f in _FEATURES if f.get("page") == page_label)
    tags = " ".join(entry.get("tags", []))
    return f"{entry['name']} {entry['desc']} {tags}".lower()


class TestNaturalLanguageAliases:
    def test_netflix_slow_routes_to_service_diagnostics(self):
        assert "netflix slow" in _search_string_for_page("Service Diagnostics")

    def test_who_is_online_routes_to_devices(self):
        assert "who is online" in _search_string_for_page("Devices")

    def test_is_my_internet_ok_routes_to_dashboard(self):
        assert "is my internet ok" in _search_string_for_page("Dashboard")

    def test_existing_short_tags_still_present(self):
        # Additive only — original substring tags from earlier sprints must remain
        assert "netflix" in _search_string_for_page("Service Diagnostics")
        assert "devices" in _search_string_for_page("Devices")
        assert "dashboard" in _search_string_for_page("Dashboard")

    def test_aliases_do_not_leak_into_other_pages(self):
        # "netflix slow" should not accidentally match the Devices or Dashboard entry
        assert "netflix slow" not in _search_string_for_page("Devices")
        assert "netflix slow" not in _search_string_for_page("Dashboard")
