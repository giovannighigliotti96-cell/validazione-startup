"""Landing page template: problem-first, evidence-driven, price visible, waitlist with price lock. Inline CSS, mobile-first."""
from __future__ import annotations

import re

from html import escape

T = {
    "it": dict(kicker="Per ristoratori e gestori di locali", ricon="Ti riconosci?", ricon_sub="Frasi vere di gestori come te.",
               how="Come funziona", price="Prezzo", mo="/mese", lock="Prezzo bloccato per i primi 30 locali in lista", faq="Domande frequenti",
               email="La tua email", name="Nome del locale (facoltativo)", q="Qual è la cosa che ti fa perdere più tempo oggi?",
               thanks="Sei in lista. Ti scriviamo entro pochi giorni per una chiamata di 15 minuti.", founder="Progetto in fase di validazione con un gruppo ristretto di locali. Il prezzo indicato è quello reale al lancio: nessuna sorpresa.",
               cta_note="Nessun pagamento ora. Solo la tua email.", benefits="Cosa cambia", privacy="Usiamo la tua email solo per contattarti su questo progetto. Niente newsletter, niente cessione a terzi."),
    "en": dict(kicker="For owners and managers", ricon="Sound familiar?", ricon_sub="Real words from operators like you.",
               how="How it works", price="Pricing", mo="/month", lock="Price locked for the first 30 businesses on the list", faq="Questions",
               email="Your email", name="Business name (optional)", q="What costs you the most time today?",
               thanks="You're on the list. We'll reach out within days for a 15-minute call.", founder="Early-access project with a small group of businesses. The price shown is the real launch price.",
               cta_note="No payment now. Just your email.", benefits="What changes", privacy="We use your email only to contact you about this project. No newsletter, never shared."),
}

CSS = """
:root{--ink:#0f172a;--ink2:#1e293b;--mut:#64748b;--line:#e2e8f0;--soft:#f8fafc;--acc:#38bdf8;--acc2:#0ea5e9;--cta:#f59e0b;--cta2:#fbbf24}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;font-family:Inter,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:#fff;line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:inherit}.w{max-width:1040px;margin:0 auto;padding:0 20px}
.hero{position:relative;overflow:hidden;background:radial-gradient(1200px 600px at 85% -10%,rgba(56,189,248,.35),transparent 60%),linear-gradient(160deg,#0b1220 0%,#111c33 55%,#0f172a 100%);color:#fff;padding:64px 0 60px}
.hero:after{content:"";position:absolute;inset:0;background-image:radial-gradient(rgba(255,255,255,.06) 1px,transparent 1px);background-size:22px 22px;pointer-events:none}
.hero .w{position:relative;z-index:1;display:grid;gap:36px;grid-template-columns:1fr;align-items:center}
@media(min-width:880px){.hero .w{grid-template-columns:1.25fr .75fr}.hero{padding:84px 0 76px}}
.kicker{display:inline-block;font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--acc);font-weight:700;margin-bottom:16px;padding:6px 12px;border:1px solid rgba(56,189,248,.35);border-radius:999px;background:rgba(56,189,248,.08)}
h1{font-size:clamp(34px,5.4vw,56px);line-height:1.04;margin:0 0 18px;font-weight:800;letter-spacing:-.03em}
.sub{font-size:clamp(17px,2.1vw,20px);color:#cbd5e1;max-width:620px;margin:0 0 28px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;background:var(--cta);color:var(--ink);padding:16px 26px;border-radius:14px;font-weight:800;text-decoration:none;font-size:16px;border:0;cursor:pointer;box-shadow:0 10px 30px rgba(245,158,11,.25);transition:transform .12s ease,background .12s ease}
.btn:hover{background:var(--cta2);transform:translateY(-1px)}.muted{color:var(--mut);font-size:13px}
.trust{display:flex;flex-wrap:wrap;gap:10px 18px;margin-top:22px;color:#94a3b8;font-size:13px}.trust span:before{content:"✓";color:var(--acc);font-weight:800;margin-right:6px}
.herocard{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);border-radius:20px;padding:22px;backdrop-filter:blur(6px)}
.herocard b{display:block;font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:#94a3b8;margin-bottom:12px}.herocard li{margin:0 0 10px;color:#e2e8f0;font-size:15px;list-style:none;padding-left:26px;position:relative}
.herocard li:before{content:"";position:absolute;left:0;top:7px;width:14px;height:14px;border-radius:999px;background:var(--acc)}.herocard ul{margin:0;padding:0}
section{padding:60px 0}h2{font-size:clamp(24px,3.2vw,34px);margin:0 0 10px;letter-spacing:-.02em;font-weight:800}.lead{color:#475569;margin:0 0 28px;font-size:17px;max-width:700px}
.quotes{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(250px,1fr))}
.q{background:#fff;border:1px solid var(--line);border-radius:16px;padding:20px 20px 18px;font-size:15.5px;color:#1f2937;position:relative;box-shadow:0 1px 2px rgba(15,23,42,.04)}
.q:before{content:"“";position:absolute;top:-8px;left:14px;font-size:54px;line-height:1;color:var(--acc);font-family:Georgia,serif;opacity:.8}
.q small{display:block;margin-top:12px;color:var(--mut);font-size:12.5px;font-weight:600;letter-spacing:.02em}
.grid{display:grid;gap:18px;grid-template-columns:repeat(auto-fit,minmax(250px,1fr))}
.card{border:1px solid var(--line);border-radius:18px;padding:22px;background:#fff;box-shadow:0 1px 2px rgba(15,23,42,.04)}.card b{display:block;font-size:16.5px;margin-bottom:6px;line-height:1.35}.card p{margin:0;color:#475569;font-size:15px}
.num{display:inline-flex;width:34px;height:34px;border-radius:12px;background:var(--ink);color:#fff;align-items:center;justify-content:center;font-weight:800;margin-bottom:12px}
.pricing{background:linear-gradient(180deg,#fff,var(--soft));border:1px solid var(--line);border-radius:24px;padding:32px;display:grid;gap:28px;grid-template-columns:1fr;align-items:start;box-shadow:0 20px 60px rgba(15,23,42,.06)}
@media(min-width:760px){.pricing{grid-template-columns:1fr 1.15fr;padding:40px}}
.price{font-size:52px;font-weight:800;letter-spacing:-.03em;line-height:1.1}.price span{font-size:18px;color:var(--mut);font-weight:500}
.lock{display:inline-block;background:#e0f2fe;color:#075985;padding:6px 12px;border-radius:999px;font-size:13px;font-weight:700;margin-top:10px}
form{display:flex;flex-direction:column;gap:10px}input,textarea{padding:14px 15px;border:1px solid #cbd5e1;border-radius:12px;font-size:15px;font-family:inherit;width:100%;background:#fff}
input:focus,textarea:focus{outline:2px solid var(--acc);border-color:var(--acc)}
details{border-bottom:1px solid var(--line);padding:14px 0}summary{cursor:pointer;font-weight:700;font-size:15.5px;list-style:none;display:flex;justify-content:space-between;align-items:center}
summary:after{content:"+";color:var(--mut);font-weight:400;font-size:20px}details[open] summary:after{content:"–"}details p{color:#475569;margin:10px 0 0;font-size:15px}
footer{padding:28px 0 44px;color:#94a3b8;font-size:12px;border-top:1px solid var(--line)}
.ok{background:#ecfdf5;color:#065f46;padding:18px 20px;border-radius:14px;font-weight:600}
.sticky{position:fixed;left:0;right:0;bottom:0;padding:10px 16px calc(10px + env(safe-area-inset-bottom));background:rgba(15,23,42,.92);backdrop-filter:blur(8px);display:none;z-index:50}
.sticky .btn{width:100%}@media(max-width:760px){.sticky{display:block}body{padding-bottom:78px}}
"""

CSS_WARM = """
:root{--paper:#f7f2ea;--paper2:#efe7da;--ink:#1c1917;--mut:#6b625a;--line:#e4dccf;--acc:#b5482b;--acc2:#9a3b22;--sage:#3f5e4a}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;font-family:"Source Sans 3",Inter,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);background:var(--paper);line-height:1.6;-webkit-font-smoothing:antialiased}
a{color:inherit}.w{max-width:1080px;margin:0 auto;padding:0 20px}
.hero{background:var(--paper);color:var(--ink);padding:36px 0 40px;border-bottom:1px solid var(--line)}
.hero .w{display:grid;gap:34px;grid-template-columns:1fr;align-items:center}
@media(min-width:900px){.hero .w{grid-template-columns:1.05fr .95fr}.hero{padding:64px 0 72px}}
.kicker{display:inline-block;font-size:13px;letter-spacing:.04em;color:var(--acc);font-weight:700;margin-bottom:14px}
h1{font-family:"Fraunces",Georgia,"Times New Roman",serif;font-weight:600;font-size:clamp(36px,5.6vw,62px);line-height:1.02;margin:0 0 18px;letter-spacing:-.02em}
h1 em{font-style:italic;color:var(--acc)}
.sub{font-size:clamp(17px,2.1vw,20px);color:#3f3a35;max-width:560px;margin:0 0 26px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;background:var(--ink);color:#fff;padding:16px 26px;border-radius:999px;font-weight:700;text-decoration:none;font-size:16px;border:0;cursor:pointer;transition:background .12s ease,transform .12s ease}
.btn:hover{background:#000;transform:translateY(-1px)}.muted{color:var(--mut);font-size:13px}
.trust{display:flex;flex-wrap:wrap;gap:8px 18px;margin-top:20px;color:var(--mut);font-size:14px}.trust span:before{content:"—";color:var(--acc);margin-right:6px}
.listing{background:#fff;border:1px solid var(--line);border-radius:18px;overflow:hidden;box-shadow:0 24px 50px rgba(28,25,23,.10);max-width:420px;margin:0 auto;transform:rotate(-1.2deg)}
.listing .ph{aspect-ratio:4/3;background:linear-gradient(135deg,var(--paper2),#d9cdb9);display:flex;align-items:center;justify-content:center;color:var(--mut);font-size:13px;letter-spacing:.06em;text-transform:uppercase}
.listing .body{padding:16px 18px 18px}.listing .tag{display:inline-block;font-size:12px;background:var(--paper2);color:var(--ink);padding:4px 10px;border-radius:999px;margin:0 6px 8px 0}
.listing h3{margin:6px 0 4px;font-family:"Fraunces",Georgia,serif;font-weight:600;font-size:20px}.listing p{margin:0 0 10px;color:#3f3a35;font-size:14.5px}
.listing .price{font-size:22px;font-weight:700;letter-spacing:-.01em}.listing .price span{font-size:13px;color:var(--mut);font-weight:500}
.listing .note{font-size:12px;color:var(--mut);border-top:1px dashed var(--line);padding-top:10px;margin-top:10px}
section{padding:56px 0}h2{font-family:"Fraunces",Georgia,serif;font-weight:600;font-size:clamp(26px,3.4vw,38px);margin:0 0 10px;letter-spacing:-.01em}.lead{color:#3f3a35;margin:0 0 26px;font-size:17px;max-width:640px}
.quotes{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.q{background:#fff;border:1px solid var(--line);border-radius:14px;padding:18px 18px 16px;font-size:15.5px;color:#2a2622;font-family:"Fraunces",Georgia,serif;font-style:italic;line-height:1.5}
.q small{display:block;margin-top:10px;color:var(--mut);font-size:12.5px;font-style:normal;font-family:"Source Sans 3",sans-serif;font-weight:600}
.grid{display:grid;gap:0;grid-template-columns:1fr;border-top:1px solid var(--line)}
.card{border-bottom:1px solid var(--line);padding:18px 0;background:transparent;display:grid;grid-template-columns:auto 1fr;gap:14px;align-items:start}.card b{display:block;font-size:17px;margin:0;line-height:1.4;font-weight:600}.card p{margin:0;color:#3f3a35;font-size:15.5px}
.card b:before{content:"✓";color:var(--sage);margin-right:10px}
.num{display:inline-flex;width:34px;height:34px;border-radius:999px;background:var(--acc);color:#fff;align-items:center;justify-content:center;font-weight:700;font-family:"Fraunces",serif;margin-top:2px}
.pricing{background:#fff;border:1px solid var(--line);border-radius:22px;padding:30px;display:grid;gap:26px;grid-template-columns:1fr;align-items:start;box-shadow:0 20px 60px rgba(28,25,23,.06)}
@media(min-width:760px){.pricing{grid-template-columns:1fr 1.15fr;padding:40px}}
.price{font-family:"Fraunces",Georgia,serif;font-weight:600;font-size:44px;letter-spacing:-.01em;line-height:1.1}.price span{font-size:18px;color:var(--mut);font-weight:500}
.lock{display:inline-block;background:var(--paper2);color:var(--ink);padding:6px 12px;border-radius:999px;font-size:13px;font-weight:600;margin-top:10px}
form{display:flex;flex-direction:column;gap:10px}input,textarea{padding:14px 15px;border:1px solid #cfc5b5;border-radius:12px;font-size:15px;font-family:inherit;width:100%;background:#fff}
input:focus,textarea:focus{outline:2px solid var(--acc);border-color:var(--acc)}
details{border-bottom:1px solid var(--line);padding:14px 0}summary{cursor:pointer;font-weight:600;font-size:16px;list-style:none;display:flex;justify-content:space-between;align-items:center}
summary::-webkit-details-marker{display:none}summary:after{content:"+";color:var(--mut);font-weight:400;font-size:22px}details[open] summary:after{content:"–"}details p{color:#3f3a35;margin:10px 0 0;font-size:15.5px}
footer{padding:28px 0 44px;color:var(--mut);font-size:12px;border-top:1px solid var(--line)}
.ok{background:#e9f1ea;color:#274a34;padding:18px 20px;border-radius:14px;font-weight:600}
.sticky{position:fixed;left:0;right:0;bottom:0;padding:10px 16px calc(10px + env(safe-area-inset-bottom));background:rgba(247,242,234,.94);backdrop-filter:blur(8px);display:none;z-index:50;border-top:1px solid var(--line)}
.sticky .btn{width:100%}@media(max-width:760px){.sticky{display:block}body{padding-bottom:78px}}
"""


def render_landing(c: dict, offer: dict, v: dict, base: str, pixel_html: str = "", signed_up: bool = False) -> str:
    lang = v.get("target_language") if v.get("target_language") in T else "en"
    t = T[lang]
    brand = offer.get("product_name") or ""
    logo = offer.get("logo_url") or f"{base}/static/dispensa/logo_512.png"
    cover = offer.get("cover_url") or f"{base}/static/dispensa/page_cover_1640x856.png"
    price_text = v.get("price_text") or f"€{v['price_eur_month']:.0f}{t['mo']}"
    lock_text = offer.get("lock_text") or t["lock"]
    kicker = offer.get("kicker") or t["kicker"]
    name_label = offer.get("form_name_label") or t["name"]
    question = offer.get("form_question") or t["q"]
    extra = "".join(f'<input name="{escape(f["name"])}" type="{escape(f.get("type") or "text")}" placeholder="{escape(f["placeholder"])}" {"required" if f.get("required") else ""}>' for f in (offer.get("form_extra") or []))
    warm = offer.get("theme") == "warm"
    css = CSS_WARM if warm else CSS
    fonts = ("https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,500;0,600;1,500&family=Source+Sans+3:wght@400;600;700&display=swap" if warm
             else "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap")
    lp = offer.get("listing_preview")
    listing_html = ""
    if lp:
        tags = "".join(f"<span class='tag'>{escape(x)}</span>" for x in lp.get("tags", []))
        listing_html = (f"<aside class='listing'><div class='ph'>{escape(lp.get('photo_label') or 'foto della postazione')}</div><div class='body'>{tags}"
                        f"<h3>{escape(lp.get('title') or '')}</h3><p>{escape(lp.get('text') or '')}</p>"
                        f"<div class='price'>{escape(lp.get('price') or '')}<span> {escape(lp.get('price_note') or '')}</span></div>"
                        f"<div class='note'>{escape(lp.get('note') or '')}</div></div></aside>")
    quotes = offer.get("quotes") or []  # curated (cleaned, translated, anonymised) from real signals; never raw scraped text on a public page
    pay = offer.get("payment_link_url")
    if signed_up:
        form = f'<div class="ok">{t["thanks"]}</div>'
    elif pay:
        form = f'<a class="btn" href="{escape(pay)}" onclick="try{{fbq(\'track\',\'InitiateCheckout\')}}catch(e){{}}">{escape(v["cta"])}</a>'
    else:
        form = f"""<form method="post" action="{base}/lp/{escape(c['id'])}/signup">
          <input type="hidden" name="variant" value="{escape(v['key'])}">
          <input name="email" type="email" required placeholder="{t['email']}">
          <input name="business" placeholder="{escape(name_label)}">
          {extra}
          <textarea name="answer" rows="2" placeholder="{escape(question)}"></textarea>
          <button class="btn" type="submit">{escape(v['cta'])}</button>
          <span class="muted">{t['cta_note']}</span>
        </form>"""
    quotes_html = "".join(f'<div class="q">&ldquo;{escape(q["quote"][:240])}&rdquo;<small>{escape(q.get("role") or "")}</small></div>' for q in quotes)
    note_q = " Testimonianze raccolte online, anonimizzate." if lang == "it" else " Collected online, anonymised."
    benefits = "".join(f'<div class="card"><b>✓ {escape(b)}</b></div>' for b in v.get("benefits", []))
    steps = "".join(f'<div class="card"><span class="num">{i+1}</span><p>{escape(s)}</p></div>' for i, s in enumerate(v.get("how_it_works", [])))
    faq = "".join(f'<details><summary>{escape(o.get("objection",""))}</summary><p>{escape(o.get("answer",""))}</p></details>' for o in v.get("objections", []))
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{(escape(brand) + " — ") if brand else ""}{escape(v['headline'])}</title><meta name="description" content="{escape(v['subheadline'][:150])}">
<link rel="icon" type="image/png" href="{logo}"><link rel="apple-touch-icon" href="{logo}">
<meta property="og:title" content="{(escape(brand) + ' — ') if brand else ''}{escape(v['headline'])}"><meta property="og:description" content="{escape(v['subheadline'][:150])}"><meta property="og:image" content="{cover}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="{fonts}" rel="stylesheet">
{pixel_html}<style>{css}</style></head>
<body>
<header class="hero"><div class="w">
  {("<div style='display:flex;align-items:center;gap:12px;margin-bottom:22px'><img src='" + logo + "' alt='' style='width:44px;height:44px;border-radius:10px'><span style='font-weight:800;font-size:22px;letter-spacing:-.02em'>" + escape(brand) + "</span></div>") if brand else ""}
  <div>
  <span class="kicker">{escape(kicker)}</span>
  <h1>{re.sub(r"\*(.+?)\*", r"<em>\1</em>", escape(v['headline']))}</h1>
  <p class="sub">{escape(v['subheadline'])}</p>
  <a class="btn" href="#lista">{escape(v['cta'])} &rarr;</a>
  <div class="muted" style="color:#94a3b8;margin-top:12px">{escape(price_text)} · {escape(lock_text)}</div>
  {("<div class='trust'>" + "".join("<span>" + escape(x) + "</span>" for x in offer.get("trust") or []) + "</div>") if offer.get("trust") else ""}
  </div>
  {listing_html or (("<aside class='herocard'><b>" + escape(offer.get("hero_card_title") or t["how"]) + "</b><ul>" + "".join("<li>" + escape(x) + "</li>" for x in v.get("how_it_works", [])[:3]) + "</ul></aside>") if v.get("how_it_works") else "")}
</div></header>
<div class="sticky"><a class="btn" href="#lista">{escape(v['cta'])}</a></div>

{("<section><div class='w'><h2>" + t['ricon'] + "</h2><p class='lead'>" + t['ricon_sub'] + "</p><div class='quotes'>" + quotes_html + "</div></div></section>") if quotes_html else ""}

<section style="background:#f8fafc"><div class="w"><h2>{t['benefits']}</h2><div class="grid">{benefits}</div></div></section>

<section><div class="w"><h2>{t['how']}</h2><div class="grid">{steps}</div></div></section>

<section id="lista"><div class="w"><div class="pricing">
  <div>
    <h2 style="margin-bottom:4px">{t['price']}</h2>
    <div class="muted">{escape(v.get('plan_name') or '')}</div>
    <div class="price" style="{'font-size:34px' if v.get('price_text') else ''}">{escape(v['price_text']) if v.get('price_text') else "€" + format(v['price_eur_month'], '.0f') + "<span>" + t['mo'] + "</span>"}</div>
    <span class="lock">🔒 {t['lock']}</span>
    <p class="muted" style="margin-top:12px">{escape(v.get('price_justification') or '')}</p>
  </div>
  <div>{form}</div>
</div>
<p class="muted" style="margin-top:14px">{t['founder']}</p></div></section>

{("<section><div class='w'><h2>" + t['faq'] + "</h2>" + faq + "</div></section>") if faq else ""}

<footer><div class="w">{(escape(brand) + " · ") if brand else ""}{t['privacy']} <a href="{base}/lp/{escape(c['id'])}/privacy">Privacy</a></div></footer>
</body></html>"""
