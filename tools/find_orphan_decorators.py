"""Find orphaned @pyqtSlot decorators in dashboard.py."""
from pathlib import Path

lines = Path("ui/dashboard.py").read_text(encoding="utf-8").splitlines()
orphans = []
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith("@pyqtSlot"):
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j < len(lines):
            next_stripped = lines[j].strip()
            if not (next_stripped.startswith("def ") or next_stripped.startswith("@")):
                orphans.append((i + 1, stripped, next_stripped[:60]))

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
print("Orphaned @pyqtSlot lines:")
for lineno, dec, nxt in orphans:
    print(f"  line {lineno}: {dec!r}")
    print(f"    -> next non-blank: {repr(nxt[:40])}")
