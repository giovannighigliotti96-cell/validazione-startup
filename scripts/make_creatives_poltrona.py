"""Poltrona Libera — page assets + ad creatives (warm editorial palette, same as the landing).
5 distinct ads: 3 single images (different photo/typographic treatment AND message) + 2 carousels (how it works / objections).
Output: creatives/poltrona/<subject>_1x1.png, _4x5.png, _9x16.png and carousel cards; public/poltrona/page_*.png.
Run: python -m scripts.make_creatives_poltrona
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = "creatives/poltrona"
PUB = "public/poltrona"
FONTS = r"C:\Windows\Fonts"
SERIF_B = os.path.join(FONTS, "georgiab.ttf")
SERIF_I = os.path.join(FONTS, "georgiai.ttf")
SANS = os.path.join(FONTS, "segoeui.ttf")
SANS_B = os.path.join(FONTS, "segoeuib.ttf")
PAPER, INK, ACC, MUT, SAGE = (247, 242, 234), (28, 25, 23), (181, 72, 43), (107, 98, 90), (63, 94, 74)
SIZES = {"1x1": (1080, 1080), "4x5": (1080, 1350), "9x16": (1080, 1920)}


def F(path, size):
    return ImageFont.truetype(path, size)


def wrap(d, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= max_w:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def draw_lines(d, x, y, lines, font, fill, lh):
    for ln in lines:
        d.text((x, y), ln, font=font, fill=fill); y += lh
    return y


def photo_bg(path, size, darken=0.45):
    im = Image.open(path).convert("RGB"); w, h = size
    r = max(w / im.width, h / im.height); im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1))
    x, y = (im.width - w) // 2, (im.height - h) // 2; im = im.crop((x, y, x + w, y + h))
    ov = Image.new("RGB", size, INK); im = Image.blend(im, ov, darken)
    return im


def brand_bar(d, w, h, light: bool):
    fill = PAPER if light else INK
    d.text((72, h - 96), "Poltrona Libera", font=F(SANS_B, 34), fill=fill)
    d.text((72, h - 56), "poltronalibera · Milano", font=F(SANS, 26), fill=(MUT if not light else (200, 190, 175)))


def ad_photo(subject, photo, headline, sub, badge, size_key):
    w, h = SIZES[size_key]; im = photo_bg(photo, (w, h), 0.5); d = ImageDraw.Draw(im)
    s = w / 1080
    d.rounded_rectangle((72, 72, 72 + int(d.textlength(badge, font=F(SANS_B, int(30 * s))) + 44), 72 + int(58 * s)), radius=999, fill=ACC)
    d.text((94, 72 + int(12 * s)), badge, font=F(SANS_B, int(30 * s)), fill=PAPER)
    y = h * (0.42 if size_key != "9x16" else 0.48)
    lines = wrap(d, headline, F(SERIF_B, int(84 * s)), w - 144)
    y = draw_lines(d, 72, y, lines, F(SERIF_B, int(84 * s)), PAPER, int(96 * s))
    y = draw_lines(d, 72, y + 18, wrap(d, sub, F(SANS, int(38 * s)), w - 160), F(SANS, int(38 * s)), (230, 224, 214), int(50 * s))
    brand_bar(d, w, h, True)
    return im


def ad_typo(headline, sub, size_key, accent_word=None):
    w, h = SIZES[size_key]; im = Image.new("RGB", (w, h), PAPER); d = ImageDraw.Draw(im)
    s = w / 1080
    d.rectangle((0, 0, w, int(14 * s)), fill=ACC)
    d.text((72, 84), "PER TITOLARI DI SALONE · MILANO", font=F(SANS_B, int(28 * s)), fill=ACC)
    y = h * 0.22 if size_key != "9x16" else h * 0.3
    big = F(SERIF_B, int(104 * s))
    for ln in wrap(d, headline, big, w - 144):
        if accent_word and accent_word in ln:
            pre, post = ln.split(accent_word, 1)
            d.text((72, y), pre, font=big, fill=INK); x = 72 + d.textlength(pre, font=big)
            d.text((x, y), accent_word, font=F(SERIF_I, int(104 * s)), fill=ACC); x += d.textlength(accent_word, font=F(SERIF_I, int(104 * s)))
            d.text((x, y), post, font=big, fill=INK)
        else:
            d.text((72, y), ln, font=big, fill=INK)
        y += int(116 * s)
    y = draw_lines(d, 72, y + 24, wrap(d, sub, F(SANS, int(40 * s)), w - 160), F(SANS, int(40 * s)), (63, 58, 53), int(54 * s))
    d.rounded_rectangle((72, y + 40, 72 + int(520 * s), y + 40 + int(92 * s)), radius=999, fill=INK)
    d.text((72 + int(48 * s), y + 40 + int(22 * s)), "Affitta la tua postazione →", font=F(SANS_B, int(34 * s)), fill=PAPER)
    brand_bar(d, w, h, False)
    return im


def card(title, text, n=None, photo=None, dark=False):
    w = h = 1080; im = Image.new("RGB", (w, h), INK if dark else PAPER)
    if photo:
        im = photo_bg(photo, (w, h), 0.62)
    d = ImageDraw.Draw(im); fg = PAPER if (dark or photo) else INK; sub = (222, 214, 202) if (dark or photo) else (63, 58, 53)
    if n:
        d.ellipse((72, 72, 72 + 96, 72 + 96), fill=ACC); d.text((72 + 30, 72 + 16), str(n), font=F(SERIF_B, 56), fill=PAPER)
    y = 300
    y = draw_lines(d, 72, y, wrap(d, title, F(SERIF_B, 78), w - 144), F(SERIF_B, 78), fg, 90)
    draw_lines(d, 72, y + 24, wrap(d, text, F(SANS, 40), w - 144), F(SANS, 40), sub, 54)
    brand_bar(d, w, h, dark or bool(photo))
    return im


def page_assets():
    os.makedirs(PUB, exist_ok=True)
    # profile: warm logo (ink square, cream mirror ring, terracotta glass)
    S = 720; im = Image.new("RGBA", (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, S, S), radius=S // 5, fill=INK)
    k = S / 512
    d.ellipse((156 * k, 78 * k, 356 * k, 278 * k), outline=PAPER, width=int(22 * k)); d.ellipse((196 * k, 118 * k, 316 * k, 238 * k), fill=ACC)
    d.rounded_rectangle((146 * k, 318 * k, 366 * k, 372 * k), radius=int(18 * k), fill=PAPER)
    d.rounded_rectangle((176 * k, 372 * k, 206 * k, 440 * k), radius=int(8 * k), fill=PAPER); d.rounded_rectangle((306 * k, 372 * k, 336 * k, 440 * k), radius=int(8 * k), fill=PAPER)
    im.save(f"{PUB}/page_profile_720.png"); im.resize((512, 512)).save(f"{PUB}/logo_512.png")
    # cover 1640x856 (fb) — cream, serif title, photo strip
    W, H = 1640, 856; cv = Image.new("RGB", (W, H), PAPER); d = ImageDraw.Draw(cv)
    strip = photo_bg(f"{PUB}/salone_1.jpg", (560, H), 0.15); cv.paste(strip, (W - 560, 0))
    d.rectangle((0, 0, W, 12), fill=ACC)
    d.text((80, 150), "Poltrona Libera", font=F(SANS_B, 44), fill=ACC)
    y = draw_lines(d, 80, 230, ["La poltrona vuota", "del tuo salone", "rende 500 € al mese."], F(SERIF_B, 80), INK, 92)
    draw_lines(d, 80, y + 20, wrap(d, "Postazioni in affitto nei saloni di Milano. Selezione, contratto, SUAP e incasso gestiti da noi.", F(SANS, 34), 900), F(SANS, 34), (63, 58, 53), 46)
    cv.save(f"{PUB}/page_cover_1640x856.png")
    cv.resize((820, 428)).save(f"{PUB}/page_cover_820x428.png")


def main():
    os.makedirs(OUT, exist_ok=True); page_assets()
    P = lambda n: f"{PUB}/postazione_{n}.jpg"
    # 1) reddito — photo
    for k in SIZES:
        ad_photo("reddito", P(1), "La poltrona vuota rende 500 € al mese.", "Selezione, contratto, SUAP e incasso li facciamo noi. Tu ricevi il canone entro il 5. Zero costi fissi.", "MILANO · SALONI", k).save(f"{OUT}/reddito_{k}.png")
    # 2) personale — typographic
    for k in SIZES:
        ad_typo("Non trovi personale? Affitta la postazione.", "Una professionista con P.IVA porta le sue clienti e paga un canone. Annuncio anonimo, contratto a norma, incasso gestito.", k, "personale?").save(f"{OUT}/personale_{k}.png")
    # 3) zero sbattimento — photo 2, different angle
    for k in SIZES:
        ad_photo("gestito", P(3), "Incasso gestito. Sostituzione inclusa.", "Se la professionista lascia, la sostituiamo noi. Se non paga, non rincorri nessuno. 15% solo quando la postazione rende.", "NESSUN COSTO FISSO", k).save(f"{OUT}/gestito_{k}.png")
    # 4) carousel: how it works
    cards = [("Ci dai in gestione la postazione", "3 foto, zona, giorni, canone. Mandato di 12 mesi, senza costi.", 1, None),
             ("Selezioniamo e organizziamo le visite", "Solo professioniste con P.IVA, qualifica e assicurazione. Incontri chi ha senso per te.", 2, None),
             ("Contratto e SUAP li prepariamo noi", "Tu firmi e basta. A norma dal 2018.", 3, None),
             ("Incassiamo noi, ti giriamo l'85%", "Entro il 5 di ogni mese. Se lascia, la sostituiamo.", 4, None),
             ("Affitta la tua postazione", "Stiamo partendo a Milano con i primi 30 saloni: 10% invece del 15% per un anno.", None, P(2))]
    for i, (t, x, n, ph) in enumerate(cards, 1):
        card(t, x, n, ph, dark=(n is None and ph is None)).save(f"{OUT}/carousel_come_{i}.png")
    # 5) carousel: objections
    obj = [("Mi porta via le clienti?", "Le sue clienti sono sue, le tue sono tue: è scritto nel contratto. Una postazione occupata porta più passaggio, non meno.", None, P(1)),
           ("È legale?", "Sì, dal 2018. Serve una comunicazione al SUAP: la prepariamo noi.", None, None),
           ("Posso affittarla alla mia ex dipendente?", "No, la legge lo vieta per 5 anni. Per questo ti presentiamo professioniste che vengono da altri saloni.", None, None),
           ("Cosa vi costa?", "Il 15% del canone, solo nei mesi in cui la postazione è occupata. Su 500 € ricevi 425 €.", None, None),
           ("E se non paga?", "Paga la piattaforma prima che il mese inizi. Se non paga, la sostituiamo: tu non rincorri nessuno.", None, P(3))]
    for i, (t, x, n, ph) in enumerate(obj, 1):
        card(t, x, n, ph, dark=(i % 2 == 0 and not ph)).save(f"{OUT}/carousel_faq_{i}.png")
    print("ok", sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
