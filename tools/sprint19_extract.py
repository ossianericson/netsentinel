"""
Sprint 19 extraction script — removes extracted methods from ui/dashboard.py
and wires in the three new mixins.
Run once from the project root: python tools/sprint19_extract.py
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent
DASH = ROOT / "ui" / "dashboard.py"

src = DASH.read_text(encoding="utf-8")
lines = src.splitlines(keepends=True)
n = len(lines)
print(f"dashboard.py: {n} lines")

# ── Build a set of line indices (0-based) to REMOVE ──────────────────────────
# We identify blocks by scanning for anchor strings.

def find_line(text_prefix, start=0):
    """Return 0-based index of first line starting with text_prefix, or None."""
    for i in range(start, len(lines)):
        if lines[i].lstrip().startswith(text_prefix.lstrip()):
            return i
    return None

def find_exact(text, start=0):
    """Return 0-based index of first line whose stripped content == text, or None."""
    for i in range(start, len(lines)):
        if lines[i].rstrip() == text:
            return i
    return None

def find_method_end(start_idx):
    """
    Given 0-based index of a 'def ' line, return the 0-based index of the last
    line of the method body (the line before the next top-level def/class/comment
    at the same or lower indentation level).
    """
    if start_idx is None:
        return None
    # Determine indentation of the def line
    def_line = lines[start_idx]
    indent = len(def_line) - len(def_line.lstrip())
    # Scan forward for next non-blank, non-continuation line at same/lower indent
    i = start_idx + 1
    while i < len(lines):
        stripped = lines[i].rstrip()
        if stripped and not stripped.startswith(" " * (indent + 1)):
            # Check if it's a decorator, def, class or comment at same level
            l = lines[i]
            l_stripped = l.lstrip()
            if l_stripped and len(l) - len(l_stripped) <= indent:
                return i - 1
        i += 1
    return len(lines) - 1

remove = set()

def remove_range(start, end):
    """Mark lines start..end (0-based, inclusive) for removal."""
    if start is None or end is None:
        print(f"  WARNING: remove_range called with None: {start}, {end}")
        return
    for i in range(start, end + 1):
        remove.add(i)
    print(f"  Removing L{start+1}..L{end+1} ({end-start+1} lines)")

# ── 1. Module-level: _color_for_level, _bg_for_level, RiskBadge, VerdictPanel ──

# Find start: def _color_for_level
start_colors = find_exact("def _color_for_level(level: str) -> str:")
# Find end: just before "# ─── Module Tab Helpers" or "from ui.tabs import"
end_colors = None
for i in range(start_colors, len(lines)):
    if lines[i].rstrip().startswith("# ─── Module Tab Helpers") or \
       lines[i].rstrip().startswith("from ui.tabs import"):
        end_colors = i - 1
        break
remove_range(start_colors, end_colors)

# ── 2. _AUTO_HELP_PAGES block ──────────────────────────────────────────────────
# Remove _AUTO_HELP_PAGES definition (it's now in nav/builder.py)
start_auto = find_exact("_AUTO_HELP_PAGES: frozenset[str] = frozenset({")
if start_auto is None:
    start_auto = find_line("_AUTO_HELP_PAGES")
# End: the closing "})" or next blank line sequence
end_auto = start_auto
for i in range(start_auto, min(start_auto + 20, len(lines))):
    if "})" in lines[i]:
        end_auto = i
        break
# Also remove the comment before it if present
if start_auto and lines[start_auto - 1].rstrip().startswith("# Pages that auto-expand"):
    start_auto -= 1
    if start_auto and not lines[start_auto - 1].strip():
        start_auto -= 1
remove_range(start_auto, end_auto)

# ── 3. Nav methods block (L520-L1694 approx) ──────────────────────────────────
# Start: the nav state comments section
start_nav = None
for i in range(400, 600):
    if "#   _nav_current_section" in lines[i] or \
       lines[i].rstrip().startswith("    #   _nav_current_section"):
        start_nav = i
        break
if start_nav is None:
    # Fallback: start at _nav_add_section
    start_nav = find_exact("    def _nav_add_section(self, label: str, icon: str = \"■\",")
    if start_nav:
        # Back up to include any preceding comments
        while start_nav > 0 and lines[start_nav-1].strip().startswith("#"):
            start_nav -= 1
        if start_nav > 0 and not lines[start_nav-1].strip():
            start_nav -= 1

# End: just before `# ── Module 1` or `# ── Alert badge` whichever comes first
# We remove including _refresh_alert_badge (it's in _MonitorStateMixin)
# Find `# ── Module 1` section header
end_nav = None
for i in range(start_nav + 200, len(lines)):
    s = lines[i].rstrip()
    if s == "    # ── Module 1 ──────────────────────────────────────────────────────────────":
        end_nav = i - 1
        break
if end_nav is None:
    # Fallback: find _build_kpi_bar
    kpi = find_exact("    def _build_kpi_bar(self) -> QWidget:")
    if kpi:
        end_nav = kpi - 1
        # back up over comments and blanks
        while end_nav > 0 and (not lines[end_nav].strip() or lines[end_nav].strip().startswith("#")):
            end_nav -= 1

remove_range(start_nav, end_nav)

# ── 4. _build_kpi_bar + _update_kpi_tiles (and section header) ─────────────────
start_kpi_header = None
for i in range(end_nav or 1600, len(lines)):
    if "# ── Module 1" in lines[i]:
        start_kpi_header = i
        break
end_kpi = find_exact("    def _show_how_to_fix(self, title: str, remediation: str):")
if end_kpi:
    end_kpi -= 1
    while end_kpi > 0 and (not lines[end_kpi].strip() or lines[end_kpi].strip().startswith("#")):
        end_kpi -= 1
if start_kpi_header and end_kpi:
    remove_range(start_kpi_header, end_kpi)

# ── 5. Verdict area section (comment + methods) ────────────────────────────────
start_verdict = None
for i in range(1900, 2100):
    if "# ── Verdict area" in lines[i]:
        start_verdict = i
        break
end_verdict = find_exact("    def _show_alert_toast(self, alert) -> None:")
if end_verdict:
    end_verdict -= 1
    while end_verdict > 0 and (not lines[end_verdict].strip() or lines[end_verdict].strip().startswith("#")):
        end_verdict -= 1
if start_verdict and end_verdict:
    remove_range(start_verdict, end_verdict)

# ── 6. _launch_modules + _launch_modules_impl ─────────────────────────────────
# Find the @pyqtSlot() just before _launch_modules
start_launch = find_exact("    @pyqtSlot()")
# We need the one just before _launch_modules, not other @pyqtSlot()
launch_def = find_exact("    def _launch_modules(self):")
if launch_def and start_launch:
    # Verify the @pyqtSlot is right before _launch_modules
    while start_launch and lines[start_launch].rstrip() != "    @pyqtSlot()":
        start_launch = find_exact("    @pyqtSlot()", start_launch + 1)
    # Find the one immediately before launch_def
    for i in range(launch_def - 3, launch_def):
        if lines[i].rstrip() == "    @pyqtSlot()":
            start_launch = i
            break

end_launch = find_exact("    # ── Module result handlers ────────────────────────────────────────────────")
if end_launch:
    end_launch -= 1
    while end_launch > 0 and not lines[end_launch].strip():
        end_launch -= 1
if start_launch and end_launch:
    remove_range(start_launch, end_launch)

# ── 7. Plugin page methods (_check_hw_autodetect through _reload_section) ─────
# Also include _update_monitor_badge + _refresh_section_badges which follow
start_plugin = find_exact("    def _check_hw_autodetect(self) -> None:")
# End: just before _check_scheduled_scan
end_plugin = find_exact("    def _check_scheduled_scan(self) -> None:")
if end_plugin:
    end_plugin -= 1
    while end_plugin > 0 and (not lines[end_plugin].strip() or lines[end_plugin].strip().startswith("#")):
        end_plugin -= 1
if start_plugin and end_plugin:
    remove_range(start_plugin, end_plugin)

# ── 8. Orphaned @pyqtSlot(dict) decorators before _on_plugin_page_added ───────
# These were left in the file; they have already been removed as part of block 7
# but check if any extras remain near the plugin block area
# (These were at L3152-3154 in the original; they're part of block 7 removed above)

# ── 9. _set_flyout_dot through _refresh_hardware_badge ────────────────────────
start_flyout = find_exact("    def _set_flyout_dot(self, label: str, color: str) -> None:")
# End: just before _on_plugin_page_test
end_flyout = find_exact("    @pyqtSlot(str)")
# Find the @pyqtSlot(str) that precedes _on_plugin_page_test
plugin_test = find_exact("    def _on_plugin_page_test(self, path: str) -> None:")
if plugin_test:
    for i in range(plugin_test - 3, plugin_test):
        if lines[i].rstrip() == "    @pyqtSlot(str)":
            end_flyout = i - 1
            while end_flyout > 0 and not lines[end_flyout].strip():
                end_flyout -= 1
            break
if start_flyout and end_flyout:
    remove_range(start_flyout, end_flyout)

# ── 10. _update_overall_verdict ───────────────────────────────────────────────
# Find the section comment before it
start_verdict2 = None
for i in range(3750, len(lines)):
    if "# ── Overall verdict" in lines[i]:
        start_verdict2 = i
        break
end_verdict2 = find_exact("    # ── Export ────────────────────────────────────────────────────────────────────")
if end_verdict2 is None:
    end_verdict2 = find_exact("    # ── Export ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────")
    if end_verdict2 is None:
        # Find @pyqtSlot() before _run_full_report
        run_report = find_exact("    def _run_full_report(self):")
        if run_report:
            for i in range(run_report - 5, run_report):
                if "# ── Export" in lines[i]:
                    end_verdict2 = i - 1
                    while end_verdict2 > 0 and not lines[end_verdict2].strip():
                        end_verdict2 -= 1
                    break
if start_verdict2 and end_verdict2:
    remove_range(start_verdict2, end_verdict2)

# ── Build new lines ────────────────────────────────────────────────────────────
new_lines = [l for i, l in enumerate(lines) if i not in remove]
print(f"Lines removed: {len(remove)}")
print(f"New line count before import updates: {len(new_lines)}")

result = "".join(new_lines)

# ── Update imports ─────────────────────────────────────────────────────────────

# 1. After "from ui.scan_wiring import ScanResultMixin" block, add new mixin imports
result = result.replace(
    "from ui.scan_wiring import ScanResultMixin\nfrom ui.header import AppHeaderMixin\nfrom ui.tabs import TabBuilderMixin",
    "from ui.scan_wiring import ScanResultMixin\nfrom ui.header import AppHeaderMixin\nfrom ui.tabs import TabBuilderMixin\nfrom ui.nav.builder import _NavBuilderMixin, _AUTO_HELP_PAGES\nfrom ui.monitor_state import (\n    _color_for_level, _bg_for_level, RiskBadge, VerdictPanel, _MonitorStateMixin,\n)\nfrom ui.plugin_page_mixin import _PluginPageMixin",
    1
)

# 2. Update Dashboard class definition
result = result.replace(
    "class Dashboard(ScanResultMixin, AppHeaderMixin, TabBuilderMixin, QMainWindow):",
    "class Dashboard(ScanResultMixin, AppHeaderMixin, TabBuilderMixin,\n               _NavBuilderMixin, _MonitorStateMixin, _PluginPageMixin, QMainWindow):",
    1
)

# ── Write result ───────────────────────────────────────────────────────────────
DASH.write_text(result, encoding="utf-8")
final_lines = result.count("\n")
print(f"dashboard.py written: ~{final_lines} lines")
print("Done.")
