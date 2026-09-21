"""Render the two guides to PDF (A4, brand typography) and produce preview PNGs for the sales pages.
Output: data/guide/<slug>.pdf (private, served only to buyers) and public/poltrona/guide/<slug>_p<N>.png (previews).
Run: python -X utf8 -m scripts.make_guida [squadra|poltrona]"""
from __future__ import annotations

import os
import sys
from html import escape

from scripts.guida_content import AUTHOR, DISCLAIMER, EDITION, GUIDES, SOURCES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PDF = os.path.join(ROOT, "data", "guide")
OUT_PNG = os.path.join(ROOT, "public", "poltrona", "guide")
PREVIEW_PAGES = {"squadra": [0, 2, 6, 8], "poltrona": [0, 2, 3, 8]}  # 0-based page indexes to expose as previews (cover, TOC, a chapter, a table)

CSS = """
@page { size: A4; margin: 18mm 17mm 20mm 17mm; }
@page :first { margin: 0; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: 'Source Sans 3', 'Segoe UI', Arial, sans-serif; font-size: 10.6pt; line-height: 1.5; color: #1c1917; margin: 0; }
h1, h2, h3, .serif { font-family: 'Fraunces', Georgia, serif; }
.cover { height: 297mm; width: 210mm; background: #1c1917; color: #f6f3ee; padding: 26mm 22mm; position: relative; page-break-after: always; }
.cover .kicker { font-size: 10pt; letter-spacing: .14em; text-transform: uppercase; color: #d7c9b8; }
.cover h1 { font-size: 44pt; line-height: 1.02; margin: 26mm 0 8mm; font-weight: 600; color: #f6f3ee; }
.cover h1 em { font-style: italic; color: #e07a4d; }
.cover .sub { font-size: 14pt; line-height: 1.4; color: #e8dfd2; max-width: 150mm; }
.cover .foot { position: absolute; bottom: 22mm; left: 22mm; right: 22mm; display: flex; justify-content: space-between; font-size: 9.5pt; color: #b8a996; border-top: 1px solid #3a332b; padding-top: 6mm; }
.cover .band { position: absolute; top: 0; right: 0; width: 14mm; height: 100%; background: #b5532c; }
.toc { page-break-after: always; }
.toc h2 { font-size: 22pt; margin: 0 0 8mm; }
.toc ol { list-style: none; padding: 0; margin: 0; counter-reset: c; }
.toc li { counter-increment: c; display: flex; gap: 6mm; padding: 3.2mm 0; border-bottom: 1px solid #e3dbd0; font-size: 12pt; }
.toc li:before { content: counter(c); font-family: 'Fraunces', Georgia, serif; color: #b5532c; width: 8mm; font-weight: 600; }
.toc .kit { margin-top: 8mm; font-size: 10.5pt; color: #6b625a; }
.chapter { page-break-before: always; }
.chapter .num { font-family: 'Fraunces', Georgia, serif; color: #b5532c; font-size: 30pt; line-height: 1; font-weight: 600; }
.chapter h2 { font-size: 22pt; line-height: 1.12; margin: 2mm 0 6mm; font-weight: 600; }
h3 { font-size: 13.5pt; margin: 7mm 0 2.5mm; font-weight: 600; }
p { margin: 0 0 3.2mm; }
p.lead { font-size: 12pt; color: #3f3a35; line-height: 1.45; margin-bottom: 5mm; }
ul, ol { margin: 0 0 3.5mm; padding-left: 5.5mm; }
li { margin: 0 0 1.6mm; }
table { border-collapse: collapse; width: 100%; margin: 2mm 0 5mm; font-size: 9.6pt; page-break-inside: auto; }
th, td { border: 1px solid #e3dbd0; padding: 2.2mm 2.6mm; vertical-align: top; text-align: left; }
th { background: #f3ede4; font-weight: 700; }
tr { page-break-inside: avoid; }
.box { background: #f6f3ee; border-left: 3px solid #b5532c; padding: 3.5mm 4.5mm; margin: 5mm 0; page-break-inside: avoid; }
.tpl { background: #fffdf9; border: 1px dashed #b5532c; border-radius: 3mm; padding: 4mm 5mm; margin: 3mm 0 5mm; font-size: 10pt; line-height: 1.55; page-break-inside: avoid; }
.kitpage { page-break-before: always; }
.kitpage .num { font-family: 'Fraunces', Georgia, serif; color: #8a6a3d; font-size: 11pt; letter-spacing: .1em; text-transform: uppercase; }
.kitpage h2 { font-size: 19pt; margin: 1mm 0 5mm; }
table.kit td, table.kit th { height: 8mm; }
ul.check { list-style: none; padding-left: 0; }
ul.check li { padding: 1.4mm 0; border-bottom: 1px dotted #e3dbd0; }
.small { font-size: 9pt; color: #6b625a; }
.sources { page-break-before: always; }
.sources h2 { font-size: 19pt; }
.sources li { font-size: 9.6pt; color: #3f3a35; margin-bottom: 2.4mm; }
a { color: #b5532c; text-decoration: none; }
"""


def html_for(g: dict) -> str:
    title = g["title"]
    # italicise the last two words of the title on the cover
    words = title.split(" ")
    cover_title = " ".join(words[:-2]) + (" <em>" + " ".join(words[-2:]) + "</em>" if len(words) > 2 else "")
    toc = "".join(f"<li><span>{escape(t)}</span></li>" for t, _ in g["chapters"])
    kit_list = " · ".join(escape(t) for t, _ in g["kit"])
    chapters = "".join(f"<section class='chapter'><div class='num'>{i + 1}</div><h2>{escape(t)}</h2>{body}</section>" for i, (t, body) in enumerate(g["chapters"]))
    kit = "".join(f"<section class='kitpage'><div class='num'>Kit · {i + 1} di {len(g['kit'])}</div><h2>{escape(t)}</h2>{body}</section>" for i, (t, body) in enumerate(g["kit"]))
    sources = "".join(f"<li>{escape(s)}</li>" for s in SOURCES)
    return f"""<!doctype html><html lang="it"><head><meta charset="utf-8"><title>{escape(title)}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,500;0,600;1,500;1,600&family=Source+Sans+3:wght@400;600;700&display=swap">
<style>{CSS}</style></head><body>
<div class="cover"><div class="band"></div><div class="kicker">Guida pratica per titolari di salone · Milano 2026</div>
<h1>{cover_title}</h1><div class="sub">{escape(g['subtitle'])}</div>
<div class="foot"><span>{escape(AUTHOR)}</span><span>poltronalibera.it</span></div></div>
<section class="toc"><h2>Indice</h2><ol>{toc}</ol><p class="kit"><b>Kit finale</b> (da stampare): {kit_list}.</p>
<p class="small" style="margin-top:8mm">{escape(EDITION)}. {escape(DISCLAIMER)}</p></section>
{chapters}
{kit}
<section class="sources"><h2>Fonti</h2><ol>{sources}</ol><p class="small">{escape(DISCLAIMER)}</p>
<p class="small">© {AUTHOR}. Copia personale dell'acquirente: non è consentita la ridistribuzione.</p></section>
</body></html>"""


def build(slug: str) -> tuple[str, int, list[str]]:
    from playwright.sync_api import sync_playwright

    g = GUIDES[slug]
    os.makedirs(OUT_PDF, exist_ok=True)
    os.makedirs(OUT_PNG, exist_ok=True)
    html_path = os.path.join(OUT_PDF, f"{slug}.html")
    pdf_path = os.path.join(OUT_PDF, f"{slug}.pdf")
    open(html_path, "w", encoding="utf-8").write(html_for(g))
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto("file:///" + html_path.replace("\\", "/"), wait_until="networkidle")
        pg.wait_for_timeout(1200)  # web fonts
        pg.pdf(path=pdf_path, format="A4", print_background=True, prefer_css_page_size=True,
               display_header_footer=True, header_template="<span></span>",
               footer_template="<div style='width:100%;font-size:8px;color:#8a8078;font-family:Arial;padding:0 17mm;display:flex;justify-content:space-between'><span>" + escape(g["title"]) + " · poltronalibera.it</span><span class='pageNumber'></span></div>",
               margin={"top": "18mm", "bottom": "20mm", "left": "17mm", "right": "17mm"})
        b.close()
    import pymupdf

    doc = pymupdf.open(pdf_path)
    previews = []
    for i in PREVIEW_PAGES[slug]:
        if i < len(doc):
            pix = doc[i].get_pixmap(dpi=110)
            out = os.path.join(OUT_PNG, f"{slug}_p{i + 1}.png")
            pix.save(out)
            previews.append(out)
    n = len(doc)
    doc.close()
    return pdf_path, n, previews


if __name__ == "__main__":
    for slug in (sys.argv[1:] or list(GUIDES)):
        pdf, n, prev = build(slug)
        print(slug, "->", pdf, n, "pages; previews:", [os.path.basename(x) for x in prev])
