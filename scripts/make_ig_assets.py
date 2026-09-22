"""Instagram assets for @poltronalibera: carousel slides (1080x1350), story cards (1080x1920), highlight covers.
Visual system: alternating ink / cream, big serif titles, a terracotta counter, photo slides for real listings.
Run: python -m scripts.make_ig_assets   -> public/poltrona/ig/"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFilter

from scripts.ig_plan import CAROUSELS, HIGHLIGHTS, STORIES
from scripts.make_creatives_poltrona import ACC, INK, PAPER, SANS, SANS_B, SERIF_B, SERIF_I, F, draw_lines, wrap

OUT = "public/poltrona/ig"
SOFT = (200, 190, 175)


def _bar(d, w, h, dark):
    d.text((72, h - 96), "@poltronalibera", font=F(SANS_B, 32), fill=PAPER if dark else INK)
    d.text((72, h - 56), "postazioni in affitto · Milano", font=F(SANS, 26), fill=SOFT if dark else (107, 98, 90))


def slide(title: str, body: str, idx: int, total: int, dark: bool, cover: bool = False) -> Image.Image:
    w, h = 1080, 1350
    im = Image.new("RGB", (w, h), INK if dark else PAPER)
    d = ImageDraw.Draw(im)
    fg, mut = (PAPER, SOFT) if dark else (INK, (63, 58, 53))
    d.rectangle((0, 0, w, 14), fill=ACC)
    if cover:
        d.text((72, 96), "SALVA IL POST  ·  SCORRI →", font=F(SANS_B, 28), fill=ACC)
        tf = F(SERIF_B, 84)
        y = draw_lines(d, 72, 300, wrap(d, title, tf, w - 144), tf, fg, 96)
        bf = F(SANS, 40)
        draw_lines(d, 72, y + 30, wrap(d, body, bf, w - 160), bf, mut, 54)
    else:
        d.ellipse((72, 84, 172, 184), fill=ACC)
        d.text((72 + 50 - d.textlength(str(idx), font=F(SERIF_B, 52)) / 2, 100), str(idx), font=F(SERIF_B, 52), fill=PAPER)
        d.text((w - 72 - d.textlength(f"{idx}/{total}", font=F(SANS, 30)), 110), f"{idx}/{total}", font=F(SANS, 30), fill=mut)
        tf = F(SERIF_B, 72)
        y = draw_lines(d, 72, 290, wrap(d, title, tf, w - 144), tf, fg, 84)
        bf = F(SANS, 42)
        draw_lines(d, 72, y + 34, wrap(d, body, bf, w - 150), bf, mut, 58)
    _bar(d, w, h, dark)
    return im


def story(kind: str, lines: list[str], dark: bool) -> Image.Image:
    w, h = 1080, 1920
    im = Image.new("RGB", (w, h), INK if dark else PAPER)
    d = ImageDraw.Draw(im)
    fg, mut = (PAPER, SOFT) if dark else (INK, (63, 58, 53))
    label = {"tip": "IL CONSIGLIO DI OGGI", "numero": "UN NUMERO", "domanda": "DOMANDA", "cta": "POLTRONA LIBERA", "postazione": "POSTAZIONE DEL GIORNO"}.get(kind, "")
    d.text((72, 520), label, font=F(SANS_B, 30), fill=ACC)
    y = 640
    if kind == "numero":
        d.text((72, y), lines[0], font=F(SERIF_B, 160), fill=ACC)
        y += 200
        rest = lines[1:]
    else:
        tf = F(SERIF_B, 80)
        y = draw_lines(d, 72, y, wrap(d, lines[0], tf, w - 144), tf, fg, 92)
        rest = lines[1:]
    bf = F(SANS, 46)
    for ln in rest:
        y = draw_lines(d, 72, y + 26, wrap(d, ln, bf, w - 150), bf, mut, 60)
    if kind in ("cta", "postazione"):
        d.rounded_rectangle((72, h - 420, 72 + 620, h - 420 + 100), radius=999, fill=ACC)
        d.text((72 + 44, h - 420 + 26), "link in bio  ↑", font=F(SANS_B, 38), fill=PAPER)
    d.text((72, h - 200), "@poltronalibera", font=F(SANS_B, 34), fill=fg)
    return im


def highlight_cover(label: str) -> Image.Image:
    w = h = 1080
    im = Image.new("RGB", (w, h), INK)
    d = ImageDraw.Draw(im)
    d.ellipse((140, 140, 940, 940), fill=PAPER)
    tf = F(SERIF_B, 92)
    lines = wrap(d, label, tf, 640)
    y = 540 - len(lines) * 52
    for ln in lines:
        d.text((540 - d.textlength(ln, font=tf) / 2, y), ln, font=tf, fill=INK)
        y += 104
    return im


def main():
    os.makedirs(OUT, exist_ok=True)
    for slug, _wd, _cap, slides in CAROUSELS:
        n = len(slides)
        for i, (t, b) in enumerate(slides):
            slide(t, b, i, n - 1, dark=(i % 2 == 0), cover=(i == 0)).save(f"{OUT}/{slug}_{i + 1}.png")
    for i, (slug, kind, lines) in enumerate(STORIES):
        story(kind, lines, dark=bool(i % 2)).save(f"{OUT}/{slug}.png")
    for label, slug in HIGHLIGHTS:
        highlight_cover(label).save(f"{OUT}/hl_{slug}.png")
    print("ok", len(os.listdir(OUT)), "files")


if __name__ == "__main__":
    main()
