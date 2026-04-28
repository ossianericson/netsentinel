"""Patch _build_header: fix brand squish + bar height."""
import pathlib, sys

TARGET = pathlib.Path(__file__).parent.parent / "ui" / "dashboard.py"
text = TARGET.read_text(encoding="utf-8")

# ── Fix 1: bar height 52 → 56 ────────────────────────────────────────────────
text = text.replace(
    'w.setObjectName("appBar")\n        w.setFixedHeight(52)',
    'w.setObjectName("appBar")\n        w.setFixedHeight(56)',
)

# ── Fix 2: brand QVBoxLayout → fixed-width QWidget container ─────────────────
OLD = '''\
        # Brand
        title = QLabel("NetSentinel")
        title.setObjectName("lblTitle")
        subtitle = QLabel("Network Security Scanner  \u2022  Rogue Device Detector")
        subtitle.setObjectName("lblSubtitle")
        brand = QVBoxLayout()
        brand.setSpacing(1)
        brand.addWidget(title)
        brand.addWidget(subtitle)
        lay.addLayout(brand)'''

NEW = '''\
        # Brand \u2014 fixed width so the filter input never squishes it
        title = QLabel("NetSentinel")
        title.setObjectName("lblTitle")
        subtitle = QLabel("Network Security Scanner  \u2022  Rogue Device Detector")
        subtitle.setObjectName("lblSubtitle")
        brand = QWidget()
        brand.setFixedWidth(240)
        brand_lay = QVBoxLayout(brand)
        brand_lay.setContentsMargins(0, 0, 0, 0)
        brand_lay.setSpacing(1)
        brand_lay.addWidget(title)
        brand_lay.addWidget(subtitle)
        lay.addWidget(brand)'''

if OLD in text:
    text = text.replace(OLD, NEW)
    print("Brand fix applied")
else:
    print("ERROR: Brand block not found")
    # show what's there
    idx = text.find('title = QLabel("NetSentinel")')
    if idx >= 0:
        print(repr(text[idx-50:idx+300]))
    sys.exit(1)

# ── Fix 3: spacing 6 → 8 in header ───────────────────────────────────────────
text = text.replace(
    'lay.setContentsMargins(16, 0, 12, 0)\n        lay.setSpacing(6)\n\n        # Brand',
    'lay.setContentsMargins(16, 0, 12, 0)\n        lay.setSpacing(8)\n\n        # Brand',
)

TARGET.write_text(text, encoding="utf-8")
print("Done.")
