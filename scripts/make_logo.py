"""Dispensa logo: a pantry shelf glyph (two shelves, jars) on a warm amber tile + wordmark. Pure vector drawing with PIL."""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw, ImageFont

AMBER = (245, 158, 11)
AMBER_D = (217, 119, 6)
SLATE = (15, 23, 42)
CREAM = (255, 251, 235)
FONT_DIR = r"C:\Windows\Fonts"


def glyph(size: int, bg=AMBER, fg=SLATE, jar_col=CREAM) -> Image.Image:
    """Pantry icon: rounded tile, cabinet outline with two shelves and five jars."""
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s, s], radius=int(s * 0.22), fill=bg)
    # cabinet
    m = int(s * 0.19)
    x0, y0, x1, y1 = m, int(s * 0.16), s - m, s - int(s * 0.16)
    lw = max(3, int(s * 0.055))
    d.rounded_rectangle([x0, y0, x1, y1], radius=int(s * 0.06), outline=fg, width=lw)
    # shelves
    sh1 = y0 + int((y1 - y0) * 0.36)
    sh2 = y0 + int((y1 - y0) * 0.68)
    for sh in (sh1, sh2):
        d.line([(x0, sh), (x1, sh)], fill=fg, width=lw)
    # jars on shelves: (cx, width, height) relative
    def jar(cx, base_y, w, h):
        jx0, jx1 = cx - w // 2, cx + w // 2
        jy0 = base_y - h
        d.rounded_rectangle([jx0, jy0, jx1, base_y - lw // 2], radius=int(w * 0.2), fill=jar_col)
        # lid
        d.rounded_rectangle([jx0 + int(w * 0.12), jy0 - int(h * 0.16), jx1 - int(w * 0.12), jy0 + int(h * 0.08)], radius=int(w * 0.1), fill=fg)
    inner_w = x1 - x0
    # three rows of jars: two shelves + cabinet floor
    rows = [(sh1, [(0.17, 0.22), (0.14, 0.16), (0.19, 0.24)]), (sh2, [(0.2, 0.2), (0.15, 0.24), (0.17, 0.18)]), (y1, [(0.16, 0.2), (0.2, 0.16), (0.15, 0.23)])]
    for base_y, jars in rows:
        for i, (rw, rh) in enumerate(jars):
            cx = x0 + int(inner_w * (0.22 + i * 0.28))
            jar(cx, base_y, int(inner_w * rw), int((y1 - y0) * rh))
    return img


def wordmark(w: int, h: int, glyph_size: int, dark_bg: bool = True) -> Image.Image:
    bg = SLATE if dark_bg else (255, 255, 255)
    fg = (255, 255, 255) if dark_bg else SLATE
    img = Image.new("RGB", (w, h), bg)
    g = glyph(glyph_size)
    gy = (h - glyph_size) // 2
    gx = int(w * 0.06)
    img.paste(g, (gx, gy), g)
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(os.path.join(FONT_DIR, "arialbd.ttf"), int(glyph_size * 0.62))
    tx = gx + glyph_size + int(glyph_size * 0.28)
    ty = gy + int(glyph_size * 0.08)
    d.text((tx, ty), "Dispensa", font=f, fill=fg)
    f2 = ImageFont.truetype(os.path.join(FONT_DIR, "arial.ttf"), int(glyph_size * 0.15))
    d.text((tx + int(glyph_size * 0.02), ty + int(glyph_size * 0.72)), "L'inventario del tuo locale, senza fogli e quaderni.", font=f2, fill=(203, 213, 225) if dark_bg else (71, 85, 105))
    return img


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "public/dispensa"
    os.makedirs(out, exist_ok=True)
    glyph(1024).convert("RGB").save(os.path.join(out, "logo_1024.png"))
    glyph(512).save(os.path.join(out, "logo_512.png"))
    # page profile (500x500): glyph with a little padding on slate so the round crop looks good
    p = Image.new("RGB", (500, 500), SLATE); g = glyph(360); p.paste(g, (70, 70), g); p.save(os.path.join(out, "page_profile_500x500.png"))
    wordmark(1640, 856, 300).save(os.path.join(out, "page_cover_1640x856.png"))
    wordmark(1200, 400, 220, dark_bg=False).save(os.path.join(out, "wordmark_light.png"))
    print("logo assets ->", out)


if __name__ == "__main__":
    main()
