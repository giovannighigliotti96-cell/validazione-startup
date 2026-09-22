"""Square images for the Facebook page posts (typographic, brand colours) -> public/poltrona/social/<slug>.png
Run: python -m scripts.make_social_images"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

from scripts.make_creatives_poltrona import ACC, INK, PAPER, SANS, SANS_B, SERIF_B, SERIF_I, F, draw_lines, wrap
from scripts.social_plan import POSTS

OUT = "public/poltrona/social"
SOFT = (200, 190, 175)
KICKER = {"titolari": "PER TITOLARI DI SALONE", "professioniste": "PER PARRUCCHIERE E BARBIERI", "entrambi": "POLTRONA LIBERA · MILANO"}


def card(headline: str, accent: str | None, audience: str, dark: bool) -> Image.Image:
    """4:5 — the format Instagram shows whole, in the feed and in the grid. Wide margins: nothing gets cropped."""
    w, h = 1080, 1350
    m = 130
    im = Image.new("RGB", (w, h), INK if dark else PAPER)
    d = ImageDraw.Draw(im)
    fg = PAPER if dark else INK
    d.rectangle((0, 0, w, 14), fill=ACC)
    d.text((m, 130), KICKER.get(audience, KICKER["entrambi"]), font=F(SANS_B, 28), fill=ACC if not dark else (220, 150, 120))
    big = F(SERIF_B, 92)
    ital = F(SERIF_I, 92)
    lines = wrap(d, headline, big, w - 2 * m)
    y = (h - len(lines) * 106) // 2 - 20
    for ln in lines:
        if accent and accent in ln:
            pre, post = ln.split(accent, 1)
            d.text((m, y), pre, font=big, fill=fg)
            x = m + d.textlength(pre, font=big)
            d.text((x, y), accent, font=ital, fill=ACC if not dark else (230, 130, 90))
            x += d.textlength(accent, font=ital)
            d.text((x, y), post, font=big, fill=fg)
        else:
            d.text((m, y), ln, font=big, fill=fg)
        y += 106
    d.text((m, h - 130), "@poltronalibera", font=F(SANS_B, 32), fill=fg)
    d.text((m, h - 88), "postazioni in affitto · Milano", font=F(SANS, 26), fill=SOFT if dark else (107, 98, 90))
    return im


def main():
    os.makedirs(OUT, exist_ok=True)
    for i, (slug, _slot, audience, headline, accent, _text) in enumerate(POSTS):
        card(headline, accent, audience, dark=bool(i % 2)).save(f"{OUT}/{slug}.png")
    print("ok", len(POSTS), "images")


if __name__ == "__main__":
    main()
