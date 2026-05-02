#!/usr/bin/env python3
"""
generate_icons.py — generate all NetSentinel icon assets from the embedded design.

Usage:  python generate_icons.py
Needs:  pip install Pillow   (already in build environment)

Outputs (assets/icons/):
  NetSentinel.ico              — Windows app icon, 16/24/32/48/64/128/256 px
  netsentinel.png              — macOS / Linux app icon, 512x512
  StoreLogo.png                — MS Store / winget tile, 50x50
  Square44x44Logo.png          — Windows taskbar, 44x44
  Square71x71Logo.png          — Start menu small, 71x71
  Square150x150Logo.png        — Start menu medium, 150x150
  Square310x310Logo.png        — Start menu large, 310x310
  Wide310x150Logo.png          — Start menu wide, 310x150
  SplashScreen.png             — Inno Setup installer splash, 620x300
"""
import math
import os
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Colour palette (RGBA)
# ---------------------------------------------------------------------------
BLUE       = (0, 120, 212, 255)   # #0078D4 — primary
DARK_BLUE  = (0, 90,  158, 255)   # #005A9E — hexagon border
CYAN_RGB   = (0, 180, 216)        # #00B4D8 — ripple rings (alpha added per ring)
WHITE      = (255, 255, 255, 255)
TRANSPARENT = (0, 0, 0, 0)
BG_WHITE   = (255, 255, 255, 255)

ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icons")


def cyan(opacity: float) -> tuple:
    """Return CYAN_RGB with the given opacity (0–1)."""
    return (*CYAN_RGB, int(opacity * 255))


# ---------------------------------------------------------------------------
# Core render
# ---------------------------------------------------------------------------

def render_icon(size: int) -> Image.Image:
    """
    Render the NetSentinel hexagon + ripple + shield icon at `size` pixels.
    Draws at 4× resolution then downsamples with LANCZOS for smooth edges.
    Returns an RGBA image with transparent background.
    """
    SS = 4
    S  = size * SS
    cx = cy = S / 2

    img  = Image.new("RGBA", (S, S), TRANSPARENT)
    draw = ImageDraw.Draw(img)

    pad = S * 0.07
    r   = S / 2 - pad          # hex vertex radius

    # -- Hexagon (pointy-top: vertex 0 at top, going clockwise) ---------------
    def hex_pt(i):
        a = math.radians(60 * i - 90)
        return (cx + r * math.cos(a), cy + r * math.sin(a))

    pts = [hex_pt(i) for i in range(6)]

    # Fill then outline (two-pass so the fill doesn't cover the outline)
    draw.polygon(pts, fill=BLUE)
    border_w = max(SS, round(S * 0.012))
    draw.polygon(pts, outline=DARK_BLUE, width=border_w)

    # -- Ripple rings (omit at very small sizes to avoid noise) ----------------
    if size >= 48:
        # Ratios relative to vertex radius r (derived from SVG master):
        # rings at r_svg=78,58,36 with hex_r_svg=108 → ratios 0.722, 0.537, 0.333
        for ratio, alpha in [(0.722, 0.15), (0.537, 0.35), (0.333, 0.60)]:
            rr  = r * ratio
            rw  = max(SS, round(S * 0.006))
            box = [cx - rr, cy - rr, cx + rr, cy + rr]
            draw.ellipse(box, outline=cyan(alpha), width=rw)

    # -- Centre origin dot -----------------------------------------------------
    if size >= 16:
        dr  = max(SS * 0.5, r * 0.032)
        box = [cx - dr, cy - dr, cx + dr, cy + dr]
        draw.ellipse(box, fill=cyan(0.8))

    # -- Shield (white outline) ------------------------------------------------
    # Proportions from SVG master (hex r=108, center=128,128):
    #   half_w/r = 40/108 = 0.370,  top_off/r = 53/108 = 0.491
    #   angle_y/r = 20/108 = 0.185, point_y/r = 57/108 = 0.528
    #   corner/r  = 6/108  = 0.056
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

    elif size >= 16:
        # Minimal shield for 16 px — just the three key anchor points
        sw  = r * 0.36
        st  = cy - r * 0.46
        sa  = cy + r * 0.18
        sp  = cy + r * 0.50
        shield = [
            (cx - sw, st), (cx + sw, st),
            (cx + sw, sa), (cx, sp),
            (cx - sw, sa),
        ]
        draw.polygon(shield, outline=WHITE, width=max(SS, round(S * 0.012)))

    return img.resize((size, size), Image.LANCZOS)


# ---------------------------------------------------------------------------
# Composite renders
# ---------------------------------------------------------------------------

def render_wide(w: int = 310, h: int = 150) -> Image.Image:
    """Wide Start Menu tile — icon centred on white background."""
    icon_size = round(h * 0.78)
    icon = render_icon(icon_size)
    canvas = Image.new("RGBA", (w, h), BG_WHITE)
    ix = (w - icon_size) // 2
    iy = (h - icon_size) // 2
    canvas.paste(icon, (ix, iy), icon)
    return canvas


def render_splash(w: int = 620, h: int = 300) -> Image.Image:
    """
    Inno Setup installer splash — white background, 8 px blue left strip,
    icon centred in the left half, app name + subtitle in the right half.
    Text is rasterised using Pillow's default font (no external font needed).
    """
    SS = 3
    W, H = w * SS, h * SS
    canvas = Image.new("RGBA", (W, H), BG_WHITE)
    draw   = ImageDraw.Draw(canvas)

    # Left accent strip
    draw.rectangle([0, 0, 8 * SS - 1, H - 1], fill=BLUE)

    # Icon — centred in left half (x: 8..310 at 1×)
    icon_h  = round(H * 0.42)
    icon    = render_icon(icon_h)
    left_cx = round((8 * SS + 310 * SS) / 2)
    canvas.paste(icon, (left_cx - icon_h // 2, H // 2 - icon_h // 2), icon)

    # App name (large) — drawn as a filled rectangle stand-in if no font,
    # but Pillow's ImageFont.load_default(size=N) works in Pillow ≥ 10.
    try:
        from PIL import ImageFont
        font_lg = ImageFont.load_default(size=round(42 * SS / 3))
        font_sm = ImageFont.load_default(size=round(17 * SS / 3))
        font_xs = ImageFont.load_default(size=round(13 * SS / 3))

        tx = round(330 * SS / 3)
        draw.text((tx, round(118 * SS / 3)), "NetSentinel",
                  font=font_lg, fill=BLUE)
        draw.text((tx, round(158 * SS / 3)), "Network Security Scanner",
                  font=font_sm, fill=(90, 106, 122, 255))
        draw.text((round(608 * SS / 3), round(273 * SS / 3)),
                  "Free · Open Source · Local",
                  font=font_xs, fill=(138, 154, 176, 255),
                  anchor="rs")
    except Exception:
        pass   # silently skip text if font loading fails

    return canvas.resize((w, h), Image.LANCZOS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def save_png(img: Image.Image, path: str) -> None:
    img.convert("RGBA").save(path, format="PNG")
    print(f"  wrote  {os.path.relpath(path)}  ({img.width}×{img.height})")


def save_ico(path: str, sizes=(16, 24, 32, 48, 64, 128, 256)) -> None:
    """Generate a multi-resolution ICO — each size rendered independently."""
    imgs = [render_icon(s).convert("RGBA") for s in sorted(sizes, reverse=True)]
    imgs[0].save(
        path,
        format="ICO",
        append_images=imgs[1:],
        sizes=[(s, s) for s in sorted(sizes, reverse=True)],
    )
    print(f"  wrote  {os.path.relpath(path)}  (ICO: {sorted(sizes)})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs(ICONS_DIR, exist_ok=True)
    print("Generating NetSentinel icons…")

    # Square PNG tiles
    for size, name in [
        (50,   "StoreLogo.png"),
        (44,   "Square44x44Logo.png"),
        (71,   "Square71x71Logo.png"),
        (150,  "Square150x150Logo.png"),
        (310,  "Square310x310Logo.png"),
        (512,  "netsentinel.png"),         # macOS / Linux app icon
    ]:
        save_png(render_icon(size), os.path.join(ICONS_DIR, name))

    # Wide tile
    save_png(render_wide(), os.path.join(ICONS_DIR, "Wide310x150Logo.png"))

    # Installer splash
    save_png(render_splash(), os.path.join(ICONS_DIR, "SplashScreen.png"))

    # Windows ICO (multi-resolution)
    save_ico(os.path.join(ICONS_DIR, "NetSentinel.ico"))

    print("Done.")
