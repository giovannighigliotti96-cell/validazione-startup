"""Creatives for the guide sales campaign: one per owner pain (from the form answers), plus the book mockup.
Run: python -m scripts.make_creatives_guida"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

from scripts.make_creatives_poltrona import ACC, INK, OUT, PAPER, SANS, SANS_B, SERIF_B, SERIF_I, SIZES, F, brand_bar, draw_lines, photo_bg, wrap

COVER = {"squadra": "public/poltrona/guide/squadra_p1.png", "poltrona": "public/poltrona/guide/poltrona_p1.png"}


def book(slug: str, h: int, light_edge: bool = False) -> Image.Image:
    """Cover page rendered as a tilted book with a shadow (and a cream edge on dark grounds so it does not vanish)."""
    im = Image.open(COVER[slug]).convert("RGB")
    im = im.resize((int(h * im.width / im.height), h))
    if light_edge:
        edged = Image.new("RGB", (im.width + 10, im.height + 10), PAPER)
        edged.paste(im, (5, 5))
        im = edged
    pad = 60
    canvas = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((pad + 18, pad + 26, pad + im.width + 18, pad + im.height + 26), radius=6, fill=(0, 0, 0, 120))
    from PIL import ImageFilter

    shadow = shadow.filter(ImageFilter.GaussianBlur(22))
    canvas.alpha_composite(shadow)
    canvas.paste(im, (pad, pad))
    return canvas.rotate(-4, resample=Image.BICUBIC, expand=True)


def ad_pain(slug: str, quote: str, headline: str, sub: str, size_key: str, dark: bool = True, photo: str | None = None) -> Image.Image:
    w, h = SIZES[size_key]
    s = w / 1080
    if photo:
        im = photo_bg(photo, (w, h), 0.62)
    else:
        im = Image.new("RGB", (w, h), INK if dark else PAPER)
    d = ImageDraw.Draw(im)
    fg = PAPER if (dark or photo) else INK
    mut = (200, 190, 175) if (dark or photo) else (107, 98, 90)
    d.text((72, 84), "GUIDA PDF PER TITOLARI DI SALONE", font=F(SANS_B, int(26 * s)), fill=mut)
    # the owner's own words, big and italic
    y = int(h * 0.15)
    qf = F(SERIF_I, int(64 * s))
    y = draw_lines(d, 72, y, wrap(d, quote, qf, w - 144), qf, ACC if not photo else (255, 190, 160), int(74 * s))
    d.text((72, y + 6), "— una titolare di salone, settembre 2026", font=F(SANS, int(28 * s)), fill=mut)
    y += int(80 * s)
    hf = F(SERIF_B, int(66 * s))
    y = draw_lines(d, 72, y, wrap(d, headline, hf, w - 144), hf, fg, int(76 * s))
    sf = F(SANS, int(34 * s))
    y = draw_lines(d, 72, y + 14, wrap(d, sub, sf, w - 160), sf, mut, int(46 * s))
    # book at the bottom right, CTA bottom left
    avail = h - y - int(200 * s)  # never let the book cover the text (rotation + shadow add margin)
    bk = book(slug, max(int(h * 0.13), min(int(h * 0.30), avail)), light_edge=dark or bool(photo))
    im.paste(bk, (w - bk.width - int(20 * s), h - bk.height - int(100 * s)), bk)
    cta = "Scarica la guida · 49,90 €"
    cw = int(d.textlength(cta, font=F(SANS_B, int(34 * s))) + int(96 * s))
    cy = h - int(190 * s)
    d.rounded_rectangle((72, cy, 72 + cw, cy + int(92 * s)), radius=999, fill=ACC if (dark or photo) else INK)
    d.text((72 + int(48 * s), cy + int(22 * s)), cta, font=F(SANS_B, int(34 * s)), fill=PAPER)
    brand_bar(d, w, h, dark or bool(photo), "poltronalibera.it")
    return im


def faq_card(slug: str, n: int, question: str, answer: str, chapter: str) -> Image.Image:
    """Carousel card: one question a salon owner asks herself, the answer in two lines, the chapter that covers it."""
    w = h = 1080
    im = Image.new("RGB", (w, h), INK if n % 2 else PAPER)
    dark = bool(n % 2)
    d = ImageDraw.Draw(im)
    fg, mut = (PAPER, (200, 190, 175)) if dark else (INK, (107, 98, 90))
    d.ellipse((72, 72, 168, 168), fill=ACC)
    d.text((100, 88), str(n), font=F(SERIF_B, 56), fill=PAPER)
    y = 260
    qf = F(SERIF_B, 72)
    y = draw_lines(d, 72, y, wrap(d, question, qf, w - 144), qf, fg, 82)
    af = F(SANS, 40)
    y = draw_lines(d, 72, y + 26, wrap(d, answer, af, w - 144), af, mut, 54)
    d.text((72, h - 250), chapter.upper(), font=F(SANS_B, 26), fill=ACC)
    bk = book(slug, 300, light_edge=dark)
    im.paste(bk, (w - bk.width - 10, h - bk.height - 60), bk)
    brand_bar(d, w, h, dark, "poltronalibera.it")
    return im


FAQ_CARDS = {
    "squadra": [
        ("La mia dipendente se ne va: e le sue clienti?", "Le richiami tu, una per una, entro 7 giorni, con la lettera pronta nel kit. Così ne tieni il 60-70%.", "Capitolo 2 · le prime 48 ore"),
        ("Perché nessuno risponde al mio annuncio?", "Perché dice cosa vuoi tu e non cosa offri. Le 7 regole e 3 annunci pronti da copiare.", "Capitolo 4 · trovare la persona giusta"),
        ("Quanto devo offrire per farla restare?", "Fisso corretto + tre premi sul fatturato, con i numeri: costa solo quando incassi.", "Capitolo 5 · i premi sul fatturato"),
        ("Come capisco che sta per andarsene?", "Cinque segnali arrivano 2-3 mesi prima. E il colloquio di 20 minuti che evita l'80% dei «me ne vado».", "Capitolo 6 · tenerle"),
        ("In maternità e non rientra: potevo evitarlo?", "Sì: il part-time che fa rientrare e la sostituta che ti costa la metà (sgravio 50%).", "Capitolo 6 · maternità"),
    ],
    "poltrona": [
        ("Basta dipendenti: ma è legale?", "Sì, dal 2012. Quante postazioni, a chi no, cosa scrivere: le regole che ti proteggono.", "Capitolo 3 · le regole"),
        ("Quanto mi rende la poltrona affittata?", "Canone 350-1.200 € al mese, o una percentuale: il confronto su 12 mesi con una dipendente.", "Capitolo 2 · i numeri"),
        ("E se non paga il canone?", "Canone anticipato entro il 5, cauzione, sospensione dopo 10 giorni: è nel contratto in 12 punti.", "Capitolo 6 · il contratto"),
        ("Mi porta via le clienti?", "Regola scritta sulle clienti, e le tue le richiami tu. Più le regole della casa per convivere.", "Capitolo 7 · convivere"),
        ("Dove trovo una professionista seria?", "Annuncio con foto e prezzo, il colloquio-visita in 30 minuti, i 5 segnali d'allarme.", "Capitolo 5 · trovarla"),
    ],
}


def ad_book(slug: str, title: str, sub: str, size_key: str) -> Image.Image:
    """Cream, the book big in the middle: the product shot."""
    w, h = SIZES[size_key]
    s = w / 1080
    im = Image.new("RGB", (w, h), PAPER)
    d = ImageDraw.Draw(im)
    d.text((72, 84), "NUOVA GUIDA · 2026", font=F(SANS_B, int(26 * s)), fill=(107, 98, 90))
    hf = F(SERIF_B, int(70 * s))
    y = draw_lines(d, 72, int(h * 0.12), wrap(d, title, hf, w - 144), hf, INK, int(80 * s))
    sf = F(SANS, int(34 * s))
    y = draw_lines(d, 72, y + 12, wrap(d, sub, sf, w - 160), sf, (63, 58, 53), int(46 * s))
    bk = book(slug, int(h * 0.42))
    im.paste(bk, ((w - bk.width) // 2, h - bk.height - int(120 * s)), bk)
    brand_bar(d, w, h, False, "poltronalibera.it")
    return im


ADS = {
    # slug, name, quote, headline, sub, style
    "squadra": [
        ("andata_via", "«Dipendente andata via.»", "Cosa fare nelle prossime 48 ore, e per non ritrovarti mai più qui.", "Clienti richiamate una per una, l'annuncio che riceve candidature, i premi sul fatturato che trattengono. 24 pagine + kit da stampare.", "dark"),
        ("non_trovo", "«Non trovo personale.»", "Non è il canale. È l'annuncio.", "Le 7 regole dell'annuncio che riceve candidature a Milano, 3 modelli pronti, il colloquio in 20 minuti. Guida PDF + kit.", "photo"),
        ("maternita", "«In maternità, e mi ha detto che non rientra.»", "Si poteva evitare. E si può ancora.", "Il part-time che fa rientrare, la sostituta che ti costa la metà (lo sgravio che quasi nessun salone usa), il piano dei 90 giorni.", "dark"),
        ("libro", "La dipendente è andata via", "Come ricostruire la squadra del tuo salone in 90 giorni, tenerla, e non ritrovarti mai più con una poltrona vuota.", "", "book"),
    ],
    "poltrona": [
        ("basta", "«Si è licenziato. E ora non voglio più personale.»", "La poltrona vuota può pagarti un canone, invece di costarti una busta paga.", "Affitto di poltrona: i numeri veri, le regole, il contratto in 12 punti, come trovare la professionista in una settimana. 20 pagine + kit.", "dark"),
        ("conto", "«Non trovo personale.»", "Una dipendente ti costa 2.100 € al mese. Una postazione affittata te ne rende 500-1.200.", "Il confronto su 12 mesi, formula fissa/mista/percentuale, il calcolo del canone per la tua zona. Guida PDF + kit.", "photo"),
        ("legale", "«Dipendente andata via.»", "Smettere di assumere è legale dal 2012. Ecco come si fa bene a Milano.", "Le regole che ti proteggono, cosa scrivere nel contratto, la convivenza, gli 8 casi che vanno storti e come evitarli.", "dark"),
        ("libro", "Basta dipendenti", "Affitta le postazioni del tuo salone a professioniste in proprio: canone mensile al posto della busta paga.", "", "book"),
    ],
}


def main():
    os.makedirs(OUT, exist_ok=True)
    photos = {"squadra": "public/poltrona/salone_4.jpg", "poltrona": "public/poltrona/salone_2.jpg"}
    for slug, items in ADS.items():
        for name, quote, headline, sub, style in items:
            for k in ("1x1", "4x5", "9x16"):
                if style == "book":
                    im = ad_book(slug, quote, headline, k)
                else:
                    im = ad_pain(slug, quote, headline, sub, k, dark=(style == "dark"), photo=photos[slug] if style == "photo" else None)
                im.save(f"{OUT}/guida_{slug}_{name}_{k}.png")
    for slug, cards in FAQ_CARDS.items():
        for i, (q, a, ch) in enumerate(cards, 1):
            faq_card(slug, i, q, a, ch).save(f"{OUT}/guida_{slug}_faq_{i}.png")
    print("ok", len([f for f in os.listdir(OUT) if f.startswith("guida_")]), "files")


if __name__ == "__main__":
    main()
