"""
UI colour palette and QSS stylesheet for Layer2 Ghost Hunter.
"""

# ── Palette ──────────────────────────────────────────────────────────────────
BG_DARK     = "#0d0d1a"
BG_CARD     = "#13132a"
BG_HOVER    = "#1a1a35"
ACCENT      = "#7c3aed"
ACCENT_LITE = "#a78bfa"
TEXT_PRIMARY   = "#e0e0f0"
TEXT_SECONDARY = "#888899"
TEXT_MUTED     = "#555570"

RED    = "#ef4444"
AMBER  = "#f59e0b"
GREEN  = "#22c55e"
BLUE   = "#3b82f6"

RED_BG    = "#2d0a0a"
AMBER_BG  = "#2d1a00"
GREEN_BG  = "#0a2d14"

RISK_COLORS = {
    "HIGH":    RED,
    "STORM":   RED,
    "MEDIUM":  AMBER,
    "WARNING": AMBER,
    "LOW":     BLUE,
    "CLEAN":   GREEN,
    "UNKNOWN": TEXT_SECONDARY,
}

RISK_BG = {
    "HIGH":    RED_BG,
    "STORM":   RED_BG,
    "MEDIUM":  AMBER_BG,
    "WARNING": AMBER_BG,
    "LOW":     "#0a1a2d",
    "CLEAN":   GREEN_BG,
    "UNKNOWN": BG_CARD,
}

# ── QSS ──────────────────────────────────────────────────────────────────────
MAIN_STYLE = f"""
QMainWindow, QWidget {{
    background-color: {BG_DARK};
    color: {TEXT_PRIMARY};
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
}}

QTabWidget::pane {{
    border: 1px solid #2a2a4a;
    background: {BG_CARD};
    border-radius: 8px;
}}

QTabBar::tab {{
    background: #1a1a35;
    color: {TEXT_SECONDARY};
    padding: 8px 18px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
    font-size: 12px;
}}

QTabBar::tab:selected {{
    background: {BG_CARD};
    color: {ACCENT_LITE};
    font-weight: bold;
}}

QTabBar::tab:hover:!selected {{
    background: {BG_HOVER};
    color: {TEXT_PRIMARY};
}}

QPushButton#btnScan {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {ACCENT}, stop:1 #9333ea);
    color: white;
    border: none;
    border-radius: 10px;
    padding: 14px 40px;
    font-size: 18px;
    font-weight: bold;
    letter-spacing: 1px;
}}

QPushButton#btnScan:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #6d28d9, stop:1 #7c3aed);
}}

QPushButton#btnScan:disabled {{
    background: #2a1a4a;
    color: {TEXT_MUTED};
}}

QPushButton {{
    background: #1e1e3a;
    color: {ACCENT_LITE};
    border: 1px solid #3a3a6a;
    border-radius: 6px;
    padding: 7px 18px;
    font-size: 12px;
}}

QPushButton:hover {{
    background: {BG_HOVER};
    border-color: {ACCENT};
}}

QPushButton:pressed {{
    background: {ACCENT};
    color: white;
}}

QTreeWidget, QTableWidget, QListWidget {{
    background: {BG_CARD};
    alternate-background-color: #16162e;
    border: 1px solid #2a2a4a;
    border-radius: 6px;
    gridline-color: #1e1e3a;
    color: {TEXT_PRIMARY};
    outline: none;
}}

QTreeWidget::item:selected, QTableWidget::item:selected,
QListWidget::item:selected {{
    background: #2a1a5a;
    color: white;
}}

QHeaderView::section {{
    background: #1e1e3a;
    color: {ACCENT_LITE};
    padding: 6px 10px;
    border: none;
    border-right: 1px solid #2a2a4a;
    font-weight: bold;
    font-size: 12px;
}}

QScrollBar:vertical {{
    background: {BG_CARD};
    width: 8px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background: #3a3a6a;
    border-radius: 4px;
    min-height: 20px;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QScrollBar:horizontal {{
    background: {BG_CARD};
    height: 8px;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal {{
    background: #3a3a6a;
    border-radius: 4px;
    min-width: 20px;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QLabel#lblTitle {{
    font-size: 26px;
    font-weight: bold;
    color: {ACCENT_LITE};
}}

QLabel#lblSubtitle {{
    font-size: 12px;
    color: {TEXT_SECONDARY};
}}

QLabel#lblStatus {{
    font-size: 12px;
    color: {TEXT_SECONDARY};
    padding: 0 8px;
}}

QFrame#verdictFrame {{
    border-radius: 10px;
    padding: 4px;
}}

QLabel#verdictText {{
    font-size: 14px;
    line-height: 1.6;
    padding: 12px 16px;
}}

QProgressBar {{
    background: {BG_CARD};
    border: 1px solid #2a2a4a;
    border-radius: 6px;
    height: 8px;
    text-align: center;
}}

QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 6px;
}}

QSpinBox, QComboBox {{
    background: {BG_CARD};
    border: 1px solid #2a2a4a;
    border-radius: 5px;
    padding: 4px 26px 4px 8px;
    color: {TEXT_PRIMARY};
    min-width: 52px;
}}

QSpinBox:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}

QSpinBox::up-button, QSpinBox::down-button {{
    width: 18px;
    background: #1a1a35;
    border-left: 1px solid #2a2a4a;
}}

QSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    border-top-right-radius: 5px;
    border-bottom: 1px solid #2a2a4a;
}}

QSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    border-bottom-right-radius: 5px;
}}

QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: {ACCENT};
}}

QTextEdit {{
    background: {BG_CARD};
    border: 1px solid #2a2a4a;
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
}}

QGroupBox {{
    border: 1px solid #2a2a4a;
    border-radius: 8px;
    margin-top: 12px;
    padding: 8px;
    font-weight: bold;
    color: {ACCENT_LITE};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
}}

QCheckBox {{
    color: {TEXT_PRIMARY};
    spacing: 6px;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid #3a3a6a;
    border-radius: 3px;
    background: {BG_CARD};
}}

QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

QToolTip {{
    background: #1e1e3a;
    color: {TEXT_PRIMARY};
    border: 1px solid #3a3a6a;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}}

QPushButton#btnExport {{
    background: #1a2a1a;
    color: {GREEN};
    border: 1px solid {GREEN};
    border-radius: 6px;
    padding: 7px 18px;
    font-size: 12px;
    font-weight: bold;
}}

QPushButton#btnExport:hover {{
    background: #244a24;
    border-color: #34d55e;
}}

QPushButton#btnExport:disabled {{
    background: {BG_CARD};
    color: {TEXT_MUTED};
    border-color: #2a2a4a;
}}

QPushButton#btnDiag {{
    background: #0a1a2d;
    color: {BLUE};
    border: 1px solid {BLUE};
    border-radius: 6px;
    padding: 7px 22px;
    font-size: 12px;
    font-weight: bold;
}}

QPushButton#btnDiag:hover {{
    background: #122a4a;
    border-color: #60a5fa;
}}

QPushButton#btnDiag:disabled {{
    background: {BG_CARD};
    color: {TEXT_MUTED};
    border-color: #2a2a4a;
}}

QPushButton#btnNetRefresh {{
    background: {BG_CARD};
    color: {ACCENT_LITE};
    border: 1px solid #3a3a6a;
    border-radius: 6px;
    padding: 5px 14px;
    font-size: 11px;
}}

QPushButton#btnNetRefresh:hover {{
    background: {BG_HOVER};
    border-color: {ACCENT};
}}

QPushButton#btnRouterLink {{
    background: #0a1a2d;
    color: {BLUE};
    border: 1px solid {BLUE};
    border-radius: 5px;
    padding: 4px 12px;
    font-size: 11px;
    text-decoration: underline;
}}

QPushButton#btnRouterLink:hover {{
    background: #122a4a;
}}
"""
