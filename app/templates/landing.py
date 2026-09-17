"""Landing page template: problem-first, evidence-driven, price visible, waitlist with price lock. Inline CSS, mobile-first."""
from __future__ import annotations

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
*{box-sizing:border-box}body{margin:0;font-family:Inter,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#0f172a;background:#fff;line-height:1.5}
a{color:inherit}.w{max-width:960px;margin:0 auto;padding:0 20px}
.hero{background:linear-gradient(180deg,#0f172a 0%,#1e293b 100%);color:#fff;padding:56px 0 48px}
.kicker{display:inline-block;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#93c5fd;font-weight:600;margin-bottom:14px}
h1{font-size:clamp(30px,5vw,46px);line-height:1.1;margin:0 0 16px;font-weight:800;letter-spacing:-.02em}
.sub{font-size:clamp(17px,2.2vw,20px);color:#cbd5e1;max-width:640px;margin:0 0 26px}
.btn{display:inline-block;background:#f59e0b;color:#0f172a;padding:15px 24px;border-radius:12px;font-weight:800;text-decoration:none;font-size:16px;border:0;cursor:pointer}
.btn:hover{background:#fbbf24}.muted{color:#64748b;font-size:13px}
section{padding:48px 0}h2{font-size:clamp(22px,3vw,30px);margin:0 0 8px;letter-spacing:-.01em}.lead{color:#475569;margin:0 0 24px}
.quotes{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(260px,1fr))}
.q{background:#fff7ed;border-left:4px solid #f59e0b;padding:16px 18px;border-radius:10px;font-size:15px;color:#1f2937}
.q small{display:block;margin-top:8px;color:#9a3412;font-size:12px}
.grid{display:grid;gap:18px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.card{border:1px solid #e2e8f0;border-radius:14px;padding:20px;background:#fff}.card b{display:block;font-size:17px;margin-bottom:6px}.card p{margin:0;color:#475569;font-size:15px}
.num{display:inline-flex;width:30px;height:30px;border-radius:999px;background:#0f172a;color:#fff;align-items:center;justify-content:center;font-weight:700;margin-bottom:10px}
.pricing{background:#f8fafc;border:1px solid #e2e8f0;border-radius:18px;padding:28px;display:grid;gap:24px;grid-template-columns:1fr;align-items:center}
@media(min-width:760px){.pricing{grid-template-columns:1fr 1.2fr}}
.price{font-size:54px;font-weight:800;letter-spacing:-.03em}.price span{font-size:18px;color:#64748b;font-weight:500}
.lock{display:inline-block;background:#dcfce7;color:#166534;padding:6px 12px;border-radius:999px;font-size:13px;font-weight:600;margin-top:8px}
form{display:flex;flex-direction:column;gap:10px}input,textarea{padding:13px 14px;border:1px solid #cbd5e1;border-radius:10px;font-size:15px;font-family:inherit;width:100%}
details{border-bottom:1px solid #e2e8f0;padding:12px 0}summary{cursor:pointer;font-weight:600;font-size:15px}details p{color:#475569;margin:8px 0 0;font-size:15px}
footer{padding:28px 0 40px;color:#94a3b8;font-size:12px;border-top:1px solid #e2e8f0}
.ok{background:#ecfdf5;color:#065f46;padding:16px 18px;border-radius:12px;font-weight:600}
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
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
{pixel_html}<style>{CSS}</style></head>
<body>
<header class="hero"><div class="w">
  {("<div style='display:flex;align-items:center;gap:12px;margin-bottom:22px'><img src='" + logo + "' alt='' style='width:44px;height:44px;border-radius:10px'><span style='font-weight:800;font-size:22px;letter-spacing:-.02em'>" + escape(brand) + "</span></div>") if brand else ""}
  <span class="kicker">{escape(kicker)}</span>
  <h1>{escape(v['headline'])}</h1>
  <p class="sub">{escape(v['subheadline'])}</p>
  <a class="btn" href="#lista">{escape(v['cta'])}</a>
  <div class="muted" style="color:#94a3b8;margin-top:12px">{escape(price_text)} · {escape(lock_text)}</div>
</div></header>

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
