"""
Typographic ad creatives for Meta (no stock photos: problem-first text on a dark kitchen-inspired palette).
Formats: 1:1 (1080x1080 feed), 4:5 (1080x1350 feed), 9:16 (1080x1920 stories/reels). Plus page profile (500x500) and cover (1640x856).
Usage: python -m scripts.make_creatives <cluster_id> <out_dir>
"""
from __future__ import annotations

import os
import sys
import textwrap

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = r"C:\Windows\Fonts"
BOLD = os.path.join(FONT_DIR, "arialbd.ttf")
REG = os.path.join(FONT_DIR, "arial.ttf")
BG = (15, 23, 42)       # slate-900
BG2 = (30, 41, 59)      # slate-800
ACCENT = (245, 158, 11)  # amber-500
WHITE = (255, 255, 255)
MUTED = (203, 213, 225)


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _gradient(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        col = tuple(int(BG[i] * (1 - t) + BG2[i] * t) for i in range(3))
        d.line([(0, y), (w, y)], fill=col)
    # soft amber glow bottom-right
    glow = Image.new("RGB", (w, h), BG)
    gd = ImageDraw.Draw(glow)
    gd.ellipse([w * 0.55, h * 0.55, w * 1.35, h * 1.35], fill=(70, 50, 20))
    glow = glow.filter(ImageFilter.GaussianBlur(w // 6))
    return Image.blend(img, glow, 0.5)


def _wrap(d: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if d.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            lines.append(cur); cur = word
    if cur:
        lines.append(cur)
    return lines


def creative(w: int, h: int, brand: str, headline: str, sub: str, badge: str, cta: str, quote: str | None = None) -> Image.Image:
    img = _gradient(w, h)
    d = ImageDraw.Draw(img)
    pad = int(w * 0.08)
    scale = w / 1080
    # brand: logo glyph + wordmark
    try:
        from scripts.make_logo import glyph

        g = glyph(int(56 * scale))
        img.paste(g, (pad, pad - int(6 * scale)), g)
        d.text((pad + int(70 * scale), pad), brand, font=_font(BOLD, int(44 * scale)), fill=ACCENT)
    except Exception:  # noqa: BLE001
        d.text((pad, pad), brand, font=_font(BOLD, int(44 * scale)), fill=ACCENT)
    # badge
    bf = _font(BOLD, int(30 * scale))
    bw = d.textlength(badge, font=bf) + int(40 * scale)
    by = pad + int(90 * scale)
    d.rounded_rectangle([pad, by, pad + bw, by + int(56 * scale)], radius=int(28 * scale), fill=(22, 101, 52))
    d.text((pad + int(20 * scale), by + int(11 * scale)), badge, font=bf, fill=(220, 252, 231))
    # headline
    hf = _font(BOLD, int((92 if h > w else 84) * scale))
    lines = _wrap(d, headline, hf, w - 2 * pad)
    y = by + int(120 * scale)
    for ln in lines[:4]:
        d.text((pad, y), ln, font=hf, fill=WHITE); y += int(hf.size * 1.12)
    # sub
    sf = _font(REG, int(40 * scale))
    y += int(20 * scale)
    for ln in _wrap(d, sub, sf, w - 2 * pad)[:3]:
        d.text((pad, y), ln, font=sf, fill=MUTED); y += int(sf.size * 1.35)
    # quote (optional)
    if quote:
        y += int(30 * scale)
        qf = _font(REG, int(36 * scale))
        d.rectangle([pad, y, pad + int(8 * scale), y + int(qf.size * 1.35 * min(4, len(_wrap(d, "“" + quote + "”", qf, w - 2 * pad - int(40 * scale)))))], fill=ACCENT)
        for ln in _wrap(d, "“" + quote + "”", qf, w - 2 * pad - int(40 * scale))[:4]:
            d.text((pad + int(30 * scale), y), ln, font=qf, fill=(254, 243, 199)); y += int(qf.size * 1.35)
    # CTA pill bottom
    cf = _font(BOLD, int(38 * scale))
    cw = d.textlength(cta, font=cf) + int(60 * scale)
    cy = h - pad - int(84 * scale)
    d.rounded_rectangle([pad, cy, pad + cw, cy + int(84 * scale)], radius=int(20 * scale), fill=ACCENT)
    d.text((pad + int(30 * scale), cy + int(20 * scale)), cta, font=cf, fill=BG)
    return img


def page_assets(out: str, brand: str, tagline: str) -> None:
    # profile 500x500: wordmark on dark
    p = Image.new("RGB", (500, 500), BG); d = ImageDraw.Draw(p)
    f = _font(BOLD, 96); tw = d.textlength(brand[0], font=f)
    d.rounded_rectangle([60, 60, 440, 440], radius=80, fill=ACCENT)
    d.text(((500 - tw) / 2, 175), brand[0], font=f, fill=BG)
    p.save(os.path.join(out, "page_profile_500x500.png"))
    c = _gradient(1640, 856); d = ImageDraw.Draw(c)
    d.text((100, 250), brand, font=_font(BOLD, 120), fill=ACCENT)
    y = 400
    for ln in _wrap(d, tagline, _font(REG, 54), 1400)[:2]:
        d.text((100, y), ln, font=_font(REG, 54), fill=WHITE); y += 72
    c.save(os.path.join(out, "page_cover_1640x856.png"))


def main() -> None:
    import warnings; warnings.filterwarnings("ignore")
    from app import db

    cluster_id, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    o = db.get(db.OPPORTUNITY_SCORING, cluster_id); offer = o["offer"]
    brand = offer.get("product_name") or "Dispensa"
    import re

    def _short(q: str, n: int = 150) -> str:
        """Cut at the last sentence/clause boundary within n chars, never mid-sentence."""
        if len(q) <= n:
            return q
        cut = q[:n]
        m = max(cut.rfind(". "), cut.rfind("; "), cut.rfind(", "))
        return (cut[:m] if m > 60 else cut.rsplit(" ", 1)[0]) + "…"

    quotes = [_short(q["quote"]) for q in (offer.get("quotes") or [])]
    subjects = [
        dict(headline="Basta contare le scorte a mano", sub="Inventario, fornitori e food cost del tuo locale in un posto solo.", quote=None),
        dict(headline="Le liste scritte a mano finiscono qui", sub="Foto delle fatture, scorte aggiornate, ordini ai fornitori in due minuti.", quote=quotes[2] if len(quotes) > 2 else None),
        dict(headline="Sai quanto ti costa davvero ogni piatto?", sub="Food cost aggiornato dalle fatture, non dal foglio di fine mese.", quote=None),
        dict(headline="Quaderno, foglio Excel, WhatsApp: l'inventario non dovrebbe vivere lì", sub="Per ristoranti e locali di Milano. Prezzo bloccato per i primi 30.", quote=None),
        dict(headline="Sono pessimo con i fogli di inventario", sub="Lo dicono i ristoratori. Dispensa lo fa al posto tuo.", quote=quotes[1] if len(quotes) > 1 else None),
    ]
    formats = {"1x1": (1080, 1080), "4x5": (1080, 1350), "9x16": (1080, 1920)}
    n = 0
    for i, s in enumerate(subjects, 1):
        for name, (w, h) in formats.items():
            img = creative(w, h, brand, s["headline"], s["sub"], "Milano · lista d'attesa aperta", "Entra in lista →", s["quote"] if h >= 1350 else None)
            img.save(os.path.join(out, f"ad{i}_{name}.png"), optimize=True); n += 1
    page_assets(out, brand, "L'inventario del tuo locale senza fogli e quaderni.")
    print(f"{n} creatives + 2 page assets -> {out}")


if __name__ == "__main__":
    main()
