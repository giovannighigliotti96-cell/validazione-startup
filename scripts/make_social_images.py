"""Square images for the Facebook page posts (typographic, brand colours) -> public/poltrona/social/<slug>.png
Run: python -m scripts.make_social_images"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

from scripts.make_creatives_poltrona import ACC, INK, PAPER, SANS, SANS_B, SERIF_B, SERIF_I, F, brand_bar, draw_lines, wrap
from scripts.social_plan import POSTS

OUT = "public/poltrona/social"
KICKER = {"titolari": "PER TITOLARI DI SALONE", "professioniste": "PER PARRUCCHIERE E BARBIERI", "entrambi": "POLTRONA LIBERA · MILANO"}


def card(headline: str, accent: str | None, audience: str, dark: bool) -> Image.Image:
    w = h = 1080
    im = Image.new("RGB", (w, h), INK if dark else PAPER)
    d = ImageDraw.Draw(im)
    fg = PAPER if dark else INK
    d.rectangle((0, 0, w, 14), fill=ACC)
    d.text((72, 84), KICKER.get(audience, KICKER["entrambi"]), font=F(SANS_B, 28), fill=ACC if not dark else (220, 150, 120))
    big = F(SERIF_B, 96)
    ital = F(SERIF_I, 96)
    lines = wrap(d, headline, big, w - 144)
    y = (h - len(lines) * 108) // 2 - 40
    for ln in lines:
        if accent and accent in ln:
            pre, post = ln.split(accent, 1)
            d.text((72, y), pre, font=big, fill=fg)
            x = 72 + d.textlength(pre, font=big)
            d.text((x, y), accent, font=ital, fill=ACC if not dark else (230, 130, 90))
            x += d.textlength(accent, font=ital)
            d.text((x, y), post, font=big, fill=fg)
        else:
            d.text((72, y), ln, font=big, fill=fg)
        y += 108
    brand_bar(d, w, h, dark, "poltronalibera.it")
    return im


def main():
    os.makedirs(OUT, exist_ok=True)
    for i, (slug, audience, headline, accent, _text) in enumerate(POSTS):
        card(headline, accent, audience, dark=bool(i % 2)).save(f"{OUT}/{slug}.png")
    print("ok", len(POSTS), "images")


if __name__ == "__main__":
    main()
