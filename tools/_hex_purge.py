"""Sprint 12 — S10-2 hex colour purge helper."""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent

MAPPING = [
    # 6-digit (longest first to avoid partial matches)
    ('#FFFFFF', 'WHITE'), ('#F9F9F9', 'HTML_BG_ALT'), ('#F5F5F5', 'HTML_BG_LIGHT'),
    ('#F4F4F4', 'BG_DARK'), ('#F7F9FC', 'BG_ALT_ROW'), ('#FAFBFC', 'CHART_PLOT_BG'),
    ('#FEF3C7', 'INLINE_WARN_BG'), ('#FFF3CD', 'ADMIN_WARN_BG'), ('#FFF8E7', 'AMBER_BG'),
    ('#FFF0F0', 'PRO_WARN_BG'), ('#FFA726', 'ORANGE'), ('#FF9F0A', 'OVERLAY_ORANGE'),
    ('#F3F4F6', 'BADGE_OFF_BG'), ('#F39C12', 'HTML_AMBER'), ('#E8EDF2', 'CHART_GRID'),
    ('#EAEAEA', 'TABLE_ROW_BORDER'), ('#ECECEC', 'CARD_HDR_BORDER'), ('#E74C3C', 'HTML_RED'),
    ('#E6EDF3', 'CANVAS_FG'), ('#E65100', 'DEEP_ORANGE'), ('#E3B341', 'CANVAS_AMBER'),
    ('#D93025', 'RED'), ('#D1FAE5', 'BADGE_OK_BG'), ('#D1D5DB', 'BADGE_OFF_BORDER'),
    ('#D4D4D4', 'BORDER'), ('#CCCCCC', 'HTML_MUTED'), ('#B3D4F5', 'INFO_BOX_BORDER'),
    ('#B0C4D8', 'BTN_DISABLED_BORDER'), ('#AEAEB2', 'OVERLAY_FG3'), ('#A8B8C8', 'SIDEBAR_ITEM_FG'),
    ('#A78BFA', 'LOG_SOURCE_PLUGIN'), ('#9BA8B4', 'INPUT_PLACEHOLDER'),
    ('#92400E', 'INLINE_WARN_FG'), ('#8E8E93', 'OVERLAY_FG2'), ('#8B949E', 'CANVAS_GRAY'),
    ('#88CC88', 'IP_CALC_HOST_FG'), ('#7EB8F7', 'IP_CALC_NET_FG'), ('#7C3AED', 'ACCENT_PURPLE'),
    ('#6B7280', 'BADGE_OFF_FG'), ('#6B7A8D', 'TEXT_MUTED'), ('#636366', 'STATUS_OFFLINE'),
    ('#5A6A7A', 'TEXT_SECONDARY'), ('#4CAF8A', 'GRADE_B_COLOR'), ('#4CAF50', 'CHART_UP'),
    ('#484F58', 'CANVAS_DIM'), ('#409CFF', 'OVERLAY_BLUE2'), ('#3FB950', 'CANVAS_GREEN'),
    ('#3A4F63', 'MAP_LAND_BORDER'), ('#3A3A3C', 'OVERLAY_BG3'), ('#333333', 'HTML_TEXT'),
    ('#2F81F7', 'CANVAS_ACCENT'), ('#2E7D32', 'GREEN'), ('#2D4A2D', 'IP_CALC_HOST_BIT_BG'),
    ('#2C2C2E', 'OVERLAY_BG2'), ('#2A4A6A', 'TH_BORDER'), ('#27AE60', 'HTML_GREEN'),
    ('#2196F3', 'CHART_DOWN'), ('#1E2D3D', 'MAP_LAND_BG'), ('#1C1C1E', 'OVERLAY_BG'),
    ('#1A6FC4', 'ACCENT_DARK'), ('#1A4A7A', 'INFO_BOX_FG'), ('#1A3A5C', 'TH_BG'),
    ('#1A2435', 'IP_CALC_ALT_ROW'), ('#10B981', 'BADGE_OK_BORDER'), ('#0D1117', 'CANVAS_BG'),
    ('#0A84FF', 'OVERLAY_BLUE'), ('#0078D4', 'ACCENT'), ('#06855B', 'BADGE_OK_FG'),
    ('#065F46', 'BADGE_OK_FG'), ('#006BBD', 'ACCENT_DARK'), ('#005FA3', 'ACCENT_DARK'),
    ('#005A9E', 'ACCENT_DARK'), ('#00897B', 'TEAL'), ('#254A6E', 'TH_BORDER'),
    ('#EBF4FF', 'INFO_BOX_BG'), ('#F59E0B', 'AMBER'), ('#F0A500', 'ADMIN_WARN_BORDER'),
    ('#000000', 'BLACK'),
    # 3-digit (last — only after all 6-digit are checked)
    ('#FFF', 'WHITE'), ('#F9F', 'HTML_BG_ALT'), ('#CCC', 'HTML_MUTED'),
    ('#333', 'HTML_TEXT'), ('#000', 'BLACK'),
]
HEX_MAP = {h.upper(): t for h, t in MAPPING}
HEX_RE = re.compile(r'#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b')

ALL_TOKENS = {
    'NAV_BAR','SIDEBAR_BG','SIDEBAR_HOVER','SIDEBAR_SEL','SIDEBAR_ITEM_FG',
    'SIDEBAR_SEL_BG','BG_DARK','BG_CARD','BG_HOVER','BG_ALT_ROW',
    'ACCENT','ACCENT_LITE','ACCENT_DARK','TEXT_PRIMARY','TEXT_SECONDARY','TEXT_MUTED',
    'TH_BG','TH_TEXT','TH_BORDER','TABLE_SEL','TABLE_ROW_BORDER',
    'RED','AMBER','GREEN','BLUE','RED_BG','AMBER_BG','GREEN_BG',
    'BORDER','BORDER_LITE','BORDER_MED','CARD_HDR_BORDER',
    'BTN_HOVER_BG','BTN_EXPORT_HOVER','BTN_DISABLED_BORDER','BTN_DISABLED_FG',
    'INPUT_BTN_BG','INPUT_PLACEHOLDER','PROGRESS_TRACK','SCROLLBAR_TRACK',
    'SCROLLBAR_HANDLE','LABEL_SUBTITLE','TOOLTIP_BG','TOOLTIP_BORDER',
    'UPDATE_BAR_BG','UPDATE_BAR_BORDER','UPDATE_BAR_FG',
    'ADMIN_WARN_FG','ADMIN_WARN_BG','ADMIN_WARN_BORDER','ADMIN_WARN_HOVER',
    'PRO_BANNER_BORDER','PRO_WARN_BG','SIDEBAR_SECTION_BG','SIDEBAR_SECTION_FG',
    'AUDIT_RED','NAV_DIVIDER','WHITE','GRADE_A_BG','GRADE_B_FG','GRADE_B_BG',
    'GRADE_C_BG','GRADE_D_BG','GRADE_F_FG','GRADE_F_BG','CHART_BG','CHART_PLOT_BG',
    'CHART_GRID','CHART_TITLE','CRITICAL',
    'CHART_DOWN','CHART_UP','CHART_AXIS','CHART_PURPLE',
    'MAP_LAND_BG','MAP_LAND_BORDER','IP_CALC_ALT_ROW','IP_CALC_NET_BIT_BG',
    'IP_CALC_HOST_BIT_BG','IP_CALC_NET_FG','IP_CALC_HOST_FG',
    'LOG_SOURCE_PLUGIN','GRADE_B_COLOR','BLACK','ORANGE','STATUS_OFFLINE',
    'INLINE_WARN_FG','INLINE_WARN_BG',
    'BADGE_OK_FG','BADGE_OK_BG','BADGE_OK_BORDER',
    'BADGE_OFF_FG','BADGE_OFF_BG','BADGE_OFF_BORDER',
    'TEAL','DEEP_ORANGE','ACCENT_PURPLE',
    'INFO_BOX_BG','INFO_BOX_BORDER','INFO_BOX_FG',
    'HTML_GREEN','HTML_RED','HTML_AMBER','HTML_TEXT','HTML_MUTED','HTML_BG_LIGHT','HTML_BG_ALT',
    'OVERLAY_BG','OVERLAY_BG2','OVERLAY_BG3','OVERLAY_FG2','OVERLAY_FG3',
    'OVERLAY_BLUE','OVERLAY_BLUE2','OVERLAY_ORANGE',
    'CANVAS_BG','CANVAS_FG','CANVAS_ACCENT','CANVAS_GREEN','CANVAS_AMBER',
    'CANVAS_GRAY','CANVAS_DIM',
    'RISK_COLORS','RISK_BG','MAIN_STYLE',
    'CARD_RADIUS','FONT_XS','FONT_SM','FONT_MD','FONT_LG','FONT_XL',
    'SPLASH_BG','SPLASH_TITLE_FG','SPLASH_SUBTITLE_FG','SPLASH_VERSION_FG','SPLASH_MSG_FG',
}


def get_token(h: str) -> str | None:
    return HEX_MAP.get(h.upper())


def replace_in_src(src: str) -> str:
    lines = src.splitlines(keepends=True)
    result = []
    for line in lines:
        if not HEX_RE.search(line):
            result.append(line)
            continue
        # Build replacement from right to left to preserve positions
        new_line = line
        for m in reversed(list(HEX_RE.finditer(line))):
            token = get_token(m.group())
            if not token:
                continue
            pos = m.start()
            end = m.end()
            prefix = line[:pos]
            suffix = line[end:]
            char_before = prefix[-1] if prefix else ''
            char_before2 = prefix[-2:] if len(prefix) >= 2 else ''

            in_fstring = bool(re.search(r'f["\']', prefix))
            # Sole string: "#HEX" or '#HEX'
            sole_string = (
                char_before in ('"', "'")
                and suffix[:1] in ('"', "'")
                and char_before2[0:1] not in ('f', 'F')
            )
            # matplotlib kwarg: facecolor="#HEX"
            kwarg_eq = bool(re.search(r'=\s*$', prefix.rstrip()))
            kwarg_eq = kwarg_eq and char_before in ('"', "'")

            if sole_string or kwarg_eq:
                # Remove quotes and use bare token
                new_line = new_line[:pos - 1] + token + new_line[end + 1:]
            elif in_fstring:
                new_line = new_line[:pos] + '{' + token + '}' + new_line[end:]
            else:
                # bare assignment or argument
                new_line = new_line[:pos] + token + new_line[end:]
        result.append(new_line)
    return ''.join(result)


def fix_imports(src: str) -> str:
    import_re = re.compile(
        r'(from\s+ui\.styles\s+import\s*\()([^)]*)\)',
        re.DOTALL,
    )
    m = import_re.search(src)
    if not m:
        return src

    existing_block = m.group(2)
    already = set(re.findall(r'\b([A-Z][A-Z0-9_]+)\b', existing_block))

    # Find tokens used in the rest of the file
    rest = src[:m.start()] + src[m.end():]
    used = {t for t in ALL_TOKENS if re.search(r'\b' + t + r'\b', rest)}

    missing = used - already
    if not missing:
        return src

    all_sorted = sorted(already | missing)
    indent = '    '
    chunks = [all_sorted[i:i + 4] for i in range(0, len(all_sorted), 4)]
    new_body = '\n'.join(indent + ', '.join(c) + ',' for c in chunks)
    new_import = m.group(1) + '\n' + new_body + '\n)'
    return src[:m.start()] + new_import + src[m.end():]


TARGET_FILES = [
    # Complex pages
    'ui/pages/settings_cards.py', 'ui/pages/ookla_cli_banner.py',
    'ui/pages/baseline_page.py', 'ui/first_run_dialog.py',
    'ui/widgets/protocol_canvas.py', 'ui/dashboard.py', 'ui/widgets/coach_mark.py',
    # Prior pass (re-run is idempotent)
    'ui/pages/reports_page.py',
    'ui/pages/inventory_page.py', 'ui/widgets/overview_tile.py',
    'ui/pages/cve_page.py', 'ui/pages/geo_map_page.py',
    'ui/pages/ip_calculator_page.py', 'ui/pages/log_source_panel.py',
    'ui/pages/notif_channel_panels.py',
    'ui/pages/trigger_builder_page.py', 'ui/pages/protocol_viz_page.py',
    'ui/pages/log_hub_page.py', 'ui/tabs.py', 'ui/tabs_scan.py',
    'ui/tabs_helpers.py', 'ui/live_graph.py', 'ui/nav/rail.py',
    'ui/pages/automation_page.py', 'ui/pages/lab_mode_page.py',
    'ui/pages/overview_page.py', 'ui/pages/rest_api_page.py',
    'ui/pages/speed_test_page.py', 'ui/pages/wifi_heatmap_page.py',
    'ui/pages/history_page.py', 'ui/pages/home_automation_page.py',
    'ui/pages/syslog_page.py', 'ui/widgets/home_widgets.py',
    'ui/widgets/hub_card.py',
    'ui/npcap_banner.py', 'ui/pages/cert_page.py',
    'ui/pages/connections_page.py', 'ui/pages/discover_page.py',
    'ui/pages/live_bandwidth_page.py', 'ui/pages/plugin_device_page.py',
    'ui/pages/security_overview_page.py', 'ui/pages/service_page.py',
    'ui/pages/uptime_page.py', 'ui/system_tray.py',
    'ui/pages/hardware_browse_mixin.py', 'ui/pages/mqtt_page.py',
    'ui/pages/settings_page.py', 'ui/pages/snmp_trap_page.py',
    'ui/pages/timeline_page.py', 'ui/widgets/density_toggle.py',
    'ui/widgets/explainer_panel.py', 'ui/widgets/page_header.py',
    'ui/widgets/pulsing_dot.py',
]


def main() -> None:
    changed = []
    errors = []
    for fpath in TARGET_FILES:
        p = ROOT / fpath
        if not p.exists():
            errors.append(f'MISSING: {fpath}')
            continue
        try:
            src = p.read_text(encoding='utf-8')
            new_src = replace_in_src(src)
            new_src = fix_imports(new_src)
            if new_src != src:
                p.write_text(new_src, encoding='utf-8')
                changed.append(fpath)
        except Exception as exc:
            errors.append(f'ERROR {fpath}: {exc}')

    print(f'Changed {len(changed)} files:')
    for f in changed:
        print(f'  {f}')
    if errors:
        print('\nErrors:')
        for e in errors:
            print(f'  {e}')

    print('\n--- Remaining hex violations ---')
    any_remaining = False
    for fpath in TARGET_FILES:
        p = ROOT / fpath
        if not p.exists():
            continue
        src = p.read_text(encoding='utf-8')
        hits = HEX_RE.findall(src)
        if hits:
            unique = sorted({h.upper() for h in hits})
            print(f'  {fpath}: {unique}')
            any_remaining = True
    if not any_remaining:
        print('  None! All target files clean.')


if __name__ == '__main__':
    main()
