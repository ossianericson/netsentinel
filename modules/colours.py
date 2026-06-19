"""
Module-layer colour palette — single source of truth for all hex colours
used in matplotlib chart exports (log_chart.py), network benchmark scoring
(network_benchmark.py), and HTML report generation (report_exporter.py).

These values are independent of the PyQt6 UI theme (which lives in
ui/styles.py).  Semantic colours (RED / AMBER / GREEN / ACCENT) deliberately
mirror the Arctic Clean light theme from ui/styles.py; update both files
together when the palette changes.

Architecture note: modules/ has no dependency on ui/.  This file is the
bridge that lets modules use named colours without importing PyQt.
"""

# ── Semantic colours (mirror ui/styles.py Arctic Clean) ──────────────────────
RED        = "#D93025"
AMBER      = "#F59E0B"
GREEN      = "#2E7D32"
ACCENT     = "#0078D4"
TEXT_MUTED = "#9BA8B4"

# ── Dark export palette ───────────────────────────────────────────────────────
# Used by log_chart.py (PNG exports) and report_exporter.py (HTML reports).
# Intentionally dark — these are standalone documents, not Qt UI widgets.

EXPORT_BG          = "#0d0d1a"   # page / figure background
EXPORT_ISP_HEADER  = "#0a0a1a"   # ISP report header (slightly darker)
EXPORT_CARD        = "#13132a"   # card / panel background
EXPORT_BORDER      = "#2a2a4a"   # card border / grid lines
EXPORT_TEXT        = "#e0e0f0"   # body text
EXPORT_HEADING_FG  = "#7c3aed"   # page heading (purple)
EXPORT_ACCENT_FG   = "#a78bfa"   # table heading / module heading (purple)
EXPORT_TH_BG       = "#1e1e3a"   # table header background
EXPORT_ROW_HOVER   = "#1a1a2e"   # table row hover
EXPORT_META        = "#666666"   # meta / footer text
EXPORT_NOTE_BG     = "#0d0d1e"   # evidence-note background

# Verdict box backgrounds and borders (bright colours on dark background)
EXPORT_RED_BG      = "#3b0000"
EXPORT_AMBER_BG    = "#2d1a00"
EXPORT_GREEN_BG    = "#001a0f"
EXPORT_RED_FG      = "#ef4444"
EXPORT_AMBER_FG    = "#f59e0b"
EXPORT_GREEN_FG    = "#22c55e"

# Risk badge background / foreground pairs
BADGE_HIGH_BG      = "#7f1d1d"
BADGE_HIGH_FG      = "#fca5a5"
BADGE_MEDIUM_BG    = "#78350f"
BADGE_MEDIUM_FG    = "#fcd34d"
BADGE_LOW_BG       = "#1e3a5f"
BADGE_LOW_FG       = "#93c5fd"
BADGE_CLEAN_BG     = "#14532d"
BADGE_CLEAN_FG     = "#86efac"
BADGE_UNKNOWN_BG   = "#374151"
BADGE_UNKNOWN_FG   = "#d1d5db"

# ISP report grade-box colours (background / foreground / border)
GRADE_A_BG         = "#14532d"
GRADE_A_FG         = "#4ade80"
GRADE_A_BORDER     = "#22c55e"
GRADE_B_BG         = "#1a3a1a"
GRADE_B_FG         = "#86efac"
GRADE_B_BORDER     = "#4ade80"
GRADE_C_BG         = "#451a03"
GRADE_C_FG         = "#fcd34d"
GRADE_C_BORDER     = "#f59e0b"
GRADE_D_BG         = "#7f1d1d"
GRADE_D_FG         = "#fca5a5"
GRADE_D_BORDER     = "#ef4444"
GRADE_F_BG         = "#3b0000"
GRADE_F_FG         = "#ff4444"
GRADE_F_BORDER     = "#dc2626"

# ── Dark chart line palette ───────────────────────────────────────────────────
# Used by log_chart.py for multi-host RTT line rotation.

CHART_DARK_ACCENT  = "#00c8ff"   # primary series / RTT
CHART_DARK_RED     = "#ff3366"   # outage / fail spans
CHART_DARK_AMBER   = "#ffaa00"   # slow spans
CHART_DARK_TEXT    = "#e0e0ff"   # axis tick labels
CHART_DARK_DNS     = "#f472b6"   # DNS secondary axis line
CHART_DARK_LINES   = [
    CHART_DARK_ACCENT, "#a78bfa", "#34d399", "#fb923c",
    CHART_DARK_DNS,    "#facc15", "#60a5fa", "#4ade80",
]

# ── Application traffic category colours ─────────────────────────────────────
# Used by modules/app_traffic_classifier.py and ui/pages/app_traffic_page.py.
# Data-dimension colours (not UI chrome) — theme-independent.
APP_WEB     = "#2196F3"   # Web / HTTP / HTTPS
APP_DNS     = "#4CAF50"   # DNS
APP_STREAM  = "#E91E63"   # Streaming (Plex, RTMP)
APP_SSH     = "#F44336"   # SSH / RDP / Admin
APP_EMAIL   = "#FF9800"   # Email (SMTP / IMAP)
APP_GAMING  = "#9C27B0"   # Gaming (Steam, Xbox, PlayStation)
APP_VPN     = "#009688"   # VPN (OpenVPN, WireGuard, IPSec)
APP_P2P     = "#FF5722"   # P2P / BitTorrent
APP_FILE    = "#795548"   # File Share (SMB, FTP, NFS)
APP_DB      = "#607D8B"   # Database (MySQL, PostgreSQL, Redis)
APP_IOT     = "#8BC34A"   # IoT / MQTT / Smart Home
APP_SYS     = "#9E9E9E"   # System (NTP, SNMP, Syslog)
APP_DISC    = "#00BCD4"   # Discovery (mDNS, SSDP)
APP_VOIP    = "#CDDC39"   # VoIP / SIP
APP_OTHER   = "#BDBDBD"   # Uncategorised

APP_CATEGORY_COLORS: dict = {
    "Web":        APP_WEB,
    "DNS":        APP_DNS,
    "Streaming":  APP_STREAM,
    "SSH/Admin":  APP_SSH,
    "Email":      APP_EMAIL,
    "Gaming":     APP_GAMING,
    "VPN":        APP_VPN,
    "P2P":        APP_P2P,
    "File Share": APP_FILE,
    "Database":   APP_DB,
    "IoT":        APP_IOT,
    "System":     APP_SYS,
    "Discovery":  APP_DISC,
    "VoIP":       APP_VOIP,
    "Other":      APP_OTHER,
}
