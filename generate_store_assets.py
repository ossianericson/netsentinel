#!/usr/bin/env python3
"""
generate_store_assets.py — generate Microsoft Store listing artwork for NetSentinel.

Usage:  python generate_store_assets.py
Needs:  pip install Pillow   (already in build environment)

Outputs (assets/store/):
  PosterArt-720x1080.png     — 9:16 poster art, main Store logo (Windows 10/11 + Xbox)
  PosterArt-1440x2160.png    — 9:16 poster art, HiDPI / 4K variant
  BoxArt-1080x1080.png       — 1:1 box art (alternate main logo if no poster supplied)
  BoxArt-2160x2160.png       — 1:1 box art, HiDPI / 4K variant
  AppTileIcon-300x300.png    — 1:1 Store display icon, Windows 10/11 tile
  AppTileIcon-150x150.png    — 1:1 Store display icon, small variant
  AppTileIcon-71x71.png      — 1:1 Store display icon, extra-small variant
"""
import math
import os
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Shared palette
# ---------------------------------------------------------------------------
NAVY        = (20,  27,  45,  255)   # #141B2D — NAV_BAR / app dark background
SIDEBAR     = (31,  43,  62,  255)   # #1F2B3E — sidebar
BLUE        = (0,   120, 212, 255)   # #0078D4 — primary accent
DARK_BLUE   = (0,   90,  158, 255)   # #005A9E — hex border
CYAN_RGB    = (0,   180, 216)        # #00B4D8 — ripple / accent
WHITE       = (255, 255, 255, 255)
WHITE_DIM   = (255, 255, 255, 180)   # muted white for subtitles
GREY        = (90,  106, 122, 255)   # #5A6A7A — secondary text
TRANSPARENT = (0,   0,   0,   0)

STORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "store")


def cyan(opacity: float) -> tuple:
    return (*CYAN_RGB, int(opacity * 255))


# ---------------------------------------------------------------------------
# Hex+shield icon renderer (mirrors generate_icons.py)
# ---------------------------------------------------------------------------

def render_icon(size: int, bg: tuple = TRANSPARENT) -> Image.Image:
    SS = 4
    S  = size * SS
    cx = cy = S / 2
    img  = Image.new("RGBA", (S, S), bg)
    draw = ImageDraw.Draw(img)
    pad  = S * 0.07
    r    = S / 2 - pad

    def hex_pt(i):
        a = math.radians(60 * i - 90)
        return (cx + r * math.cos(a), cy + r * math.sin(a))

    pts = [hex_pt(i) for i in range(6)]
    draw.polygon(pts, fill=BLUE)
    border_w = max(SS, round(S * 0.012))
    draw.polygon(pts, outline=DARK_BLUE, width=border_w)

    if size >= 48:
        for ratio, alpha in [(0.722, 0.15), (0.537, 0.35), (0.333, 0.60)]:
            rr  = r * ratio
            rw  = max(SS, round(S * 0.006))
            box = [cx - rr, cy - rr, cx + rr, cy + rr]
            draw.ellipse(box, outline=cyan(alpha), width=rw)

    if size >= 16:
        dr  = max(SS * 0.5, r * 0.032)
        box = [cx - dr, cy - dr, cx + dr, cy + dr]
        draw.ellipse(box, fill=cyan(0.8))

    if size >= 24:
        sw   = r * 0.370
        st   = cy - r * 0.491
        sa   = cy + r * 0.185
        sp   = cy + r * 0.528
        cr   = r * 0.056
        shield = [
            (cx - sw + cr, st),
            (cx + sw - cr, st),
            (cx + sw,      st + cr),
            (cx + sw,      sa),
            (cx,           sp),
            (cx - sw,      sa),
            (cx - sw,      st + cr),
        ]
        sw2 = max(SS, round(S * 0.012))
        draw.polygon(shield, outline=WHITE, width=sw2)

    return img.resize((size, size), Image.LANCZOS)


# ---------------------------------------------------------------------------
# Subtle dot-grid texture
# ---------------------------------------------------------------------------

def _draw_dot_grid(draw: ImageDraw.Draw, w: int, h: int,
                   spacing: int = 40, radius: int = 1,
                   opacity: int = 18) -> None:
    colour = (255, 255, 255, opacity)
    for x in range(spacing // 2, w, spacing):
        for y in range(spacing // 2, h, spacing):
            draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                         fill=colour)


# ---------------------------------------------------------------------------
# Poster art  (9:16)
# ---------------------------------------------------------------------------

def render_poster(w: int, h: int) -> Image.Image:
    """9:16 poster — dark navy, centred icon, title, tagline, feature strip."""
    canvas = Image.new("RGBA", (w, h), NAVY)
    draw   = ImageDraw.Draw(canvas)

    # Dot grid texture
    _draw_dot_grid(draw, w, h, spacing=max(20, w // 18))

    # Subtle bottom-gradient overlay
    for y in range(h // 2, h):
        alpha = int(120 * (y - h // 2) / (h // 2))
        draw.line([(0, y), (w, y)], fill=(*SIDEBAR[:3], alpha))

    # Thin cyan top accent bar
    bar_h = max(3, h // 200)
    draw.rectangle([0, 0, w, bar_h - 1], fill=(*CYAN_RGB, 230))

    # Icon (centred in upper ~55 % of canvas)
    icon_sz = round(w * 0.58)
    icon    = render_icon(icon_sz)
    ix      = (w - icon_sz) // 2
    iy      = round(h * 0.08)
    canvas.paste(icon, (ix, iy), icon)

    # Text sizes proportional to width
    try:
        from PIL import ImageFont
        sz_title    = max(14, round(w * 0.088))
        sz_tagline  = max(9,  round(w * 0.042))
        sz_feature  = max(7,  round(w * 0.032))
        f_title   = ImageFont.load_default(size=sz_title)
        f_tagline = ImageFont.load_default(size=sz_tagline)
        f_feature = ImageFont.load_default(size=sz_feature)

        cx = w // 2
        title_y   = iy + icon_sz + round(h * 0.04)
        tagline_y = title_y + sz_title + round(h * 0.015)

        # App name
        draw.text((cx, title_y), "NetSentinel",
                  font=f_title, fill=WHITE, anchor="mt")

        # Tagline in cyan
        draw.text((cx, tagline_y), "Network Security Scanner",
                  font=f_tagline, fill=(*CYAN_RGB, 230), anchor="mt")

        # Divider
        div_y = tagline_y + sz_tagline + round(h * 0.025)
        dw    = round(w * 0.4)
        draw.line([(cx - dw // 2, div_y), (cx + dw // 2, div_y)],
                  fill=(*CYAN_RGB, 80), width=max(1, h // 400))

        # Feature bullets
        features = [
            "Device Inventory & Rogue Detection",
            "STP / Broadcast Storm Analyser",
            "Speed Test  •  CVE Lookup  •  TLS",
            "Protocol Visualizer & Lab Mode",
        ]
        fy = div_y + round(h * 0.025)
        for feat in features:
            draw.text((cx, fy), feat,
                      font=f_feature, fill=(*GREY[:3], 200), anchor="mt")
            fy += sz_feature + round(h * 0.012)

    except Exception:
        pass  # silently skip text if Pillow font loading fails

    return canvas


# ---------------------------------------------------------------------------
# Box art  (1:1)
# ---------------------------------------------------------------------------

def render_box(size: int) -> Image.Image:
    """1:1 box art — same design language as poster, square crop."""
    w = h = size
    canvas = Image.new("RGBA", (w, h), NAVY)
    draw   = ImageDraw.Draw(canvas)

    _draw_dot_grid(draw, w, h, spacing=max(20, w // 20))

    # Subtle radial glow behind icon
    glow_r = round(w * 0.42)
    for step in range(30, 0, -1):
        r_cur   = round(glow_r * step / 30)
        alpha   = int(12 * (1 - step / 30))
        box = [w // 2 - r_cur, h // 2 - r_cur, w // 2 + r_cur, h // 2 + r_cur]
        draw.ellipse(box, fill=(*BLUE[:3], alpha))

    bar_h = max(3, h // 200)
    draw.rectangle([0, 0, w, bar_h - 1], fill=(*CYAN_RGB, 220))

    icon_sz = round(w * 0.54)
    icon    = render_icon(icon_sz)
    ix      = (w - icon_sz) // 2
    iy      = round(h * 0.10)
    canvas.paste(icon, (ix, iy), icon)

    try:
        from PIL import ImageFont
        sz_title   = max(12, round(w * 0.082))
        sz_tagline = max(8,  round(w * 0.038))
        f_title    = ImageFont.load_default(size=sz_title)
        f_tagline  = ImageFont.load_default(size=sz_tagline)

        cx        = w // 2
        title_y   = iy + icon_sz + round(h * 0.04)
        tagline_y = title_y + sz_title + round(h * 0.018)

        draw.text((cx, title_y), "NetSentinel",
                  font=f_title, fill=WHITE, anchor="mt")
        draw.text((cx, tagline_y), "Network Security Scanner",
                  font=f_tagline, fill=(*CYAN_RGB, 220), anchor="mt")

    except Exception:
        pass  # silently skip text if Pillow font loading fails

    return canvas


# ---------------------------------------------------------------------------
# App tile icon  (square, for Store display tiles)
# ---------------------------------------------------------------------------

def render_tile(size: int) -> Image.Image:
    """Store display tile — navy background, centred icon, no text."""
    w = h = size
    canvas = Image.new("RGBA", (w, h), NAVY)
    draw   = ImageDraw.Draw(canvas)

    bar_h = max(1, h // 100)
    draw.rectangle([0, 0, w, bar_h - 1], fill=(*CYAN_RGB, 200))

    icon_sz = round(w * 0.70)
    icon    = render_icon(icon_sz)
    ix      = (w - icon_sz) // 2
    iy      = (h - icon_sz) // 2
    canvas.paste(icon, (ix, iy), icon)

    return canvas


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def save_png(img: Image.Image, path: str) -> None:
    img.convert("RGBA").save(path, format="PNG")
    print(f"  wrote  {os.path.relpath(path)}  ({img.width}×{img.height})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs(STORE_DIR, exist_ok=True)
    print("Generating NetSentinel Store listing assets…")

    # 9:16 Poster art
    for w, h in [(720, 1080), (1440, 2160)]:
        save_png(render_poster(w, h),
                 os.path.join(STORE_DIR, f"PosterArt-{w}x{h}.png"))

    # 1:1 Box art
    for sz in [1080, 2160]:
        save_png(render_box(sz),
                 os.path.join(STORE_DIR, f"BoxArt-{sz}x{sz}.png"))

    # Store display tile icons
    for sz in [300, 150, 71]:
        save_png(render_tile(sz),
                 os.path.join(STORE_DIR, f"AppTileIcon-{sz}x{sz}.png"))

    print()
    print("Done.  Upload assets/store/*.png to Partner Center.")
    print()
    print("Still needed — take 4+ screenshots of the running app:")
    print("  Recommended pages: Overview, Devices, Speed Test, Security Audit")
    print("  Size: 1366×768 px or larger  (1920×1080 ideal)")
    print("  Format: PNG, landscape")
