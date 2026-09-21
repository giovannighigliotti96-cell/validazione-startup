"""Sales pages, checkout, delivery and webhook for the paid guides (A/B: squadra / poltrona)."""
from __future__ import annotations

import logging
from html import escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app import db
from app.config import get_settings
from app.routers.poltrona import CSS
from app.services import guida as G
from app.services import poltrona as P

log = logging.getLogger("guida")
router = APIRouter(prefix="/pl/guida", tags=["guida"])

EXTRA_CSS = """<style>
.hero{display:grid;grid-template-columns:1.15fr .85fr;gap:36px;align-items:center;padding:34px 0 10px}
.hero h1{font-size:38px}.hero .kick{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--acc);font-weight:700;margin-bottom:10px}
.cover{box-shadow:0 24px 60px rgba(28,25,23,.25);border-radius:6px;transform:rotate(-2deg);max-width:100%}
.pricebox{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin:14px 0 6px}.pricebox .now{font-family:"Fraunces",Georgia,serif;font-size:40px;font-weight:600}.pricebox .was{color:var(--mut);text-decoration:line-through;font-size:20px}.pricebox .tag{background:var(--acc);color:#fff;font-size:12px;font-weight:700;padding:3px 10px;border-radius:999px}
.trustline{display:flex;gap:16px;flex-wrap:wrap;color:var(--mut);font-size:14px;margin-top:10px}.trustline span:before{content:"✓ ";color:var(--ok);font-weight:700}
.pains{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin:8px 0}.pains blockquote{margin:0;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;font-family:"Fraunces",Georgia,serif;font-size:19px;font-style:italic}.pains small{display:block;font-family:"Source Sans 3",sans-serif;font-style:normal;color:var(--mut);margin-top:8px;font-size:13px}
.chapters{list-style:none;padding:0;margin:0;counter-reset:c}.chapters li{counter-increment:c;display:grid;grid-template-columns:34px 1fr;gap:12px;padding:12px 0;border-bottom:1px solid var(--line)}.chapters li:before{content:counter(c);font-family:"Fraunces",Georgia,serif;color:var(--acc);font-size:22px;font-weight:600;line-height:1}.chapters b{display:block}.chapters span{color:var(--mut)}
.previews{display:flex;gap:14px;overflow-x:auto;padding:6px 2px 14px;scroll-snap-type:x mandatory}.previews img{width:240px;flex:0 0 auto;border:1px solid var(--line);border-radius:6px;box-shadow:0 10px 30px rgba(28,25,23,.12);scroll-snap-align:start}
.two{display:grid;grid-template-columns:1fr 1fr;gap:18px}.two ul{margin:6px 0 0;padding-left:18px}
.kit{display:flex;flex-wrap:wrap;gap:8px}.kit span{background:var(--card);border:1px solid var(--line);border-radius:999px;padding:6px 12px;font-size:14px}
.author{display:grid;grid-template-columns:96px 1fr;gap:18px;align-items:start}.author img{width:96px;height:96px;border-radius:50%;object-fit:cover}
.buy{background:var(--ink);color:#f6f3ee;border-radius:18px;padding:28px;display:grid;grid-template-columns:1fr auto;gap:22px;align-items:center}.buy h2{color:#f6f3ee;margin:0 0 6px}.buy .muted{color:#c9bfb2}.buy .btn{font-size:18px;padding:16px 28px}
.faq details{border-bottom:1px solid var(--line);padding:10px 0}.faq summary{font-weight:700;cursor:pointer}.faq p{color:var(--mut);margin:8px 0 0}
.guarantee{display:flex;gap:14px;align-items:center;background:var(--okbg);color:var(--ok);border-radius:14px;padding:16px 18px;font-weight:600}
.sticky{position:fixed;left:0;right:0;bottom:0;background:var(--card);border-top:1px solid var(--line);padding:10px 16px;display:none;z-index:9}.sticky .btn{width:100%}
@media(max-width:820px){.hero{grid-template-columns:1fr;gap:18px}.hero h1{font-size:29px}.cover{transform:none;max-width:70%;margin:0 auto}.two{grid-template-columns:1fr}.buy{grid-template-columns:1fr}.sticky{display:block}body{padding-bottom:74px}.author{grid-template-columns:72px 1fr}.author img{width:72px;height:72px}}
</style>"""


def _pixel(pv_id: str, extra: str = "") -> str:
    from app.routers.landing import _pixel as px

    return px("PageView", pv_id, "", extra)


def _shell(title: str, body: str, pixel_html: str, desc: str, beacon_id: str = "", utm: str = "", head_extra: str = "") -> HTMLResponse:
    base = P.base()
    beacon = ""
    if beacon_id:
        from app.templates.landing import BEHAVIOR_JS

        beacon = BEHAVIOR_JS % {"cid": beacon_id, "variant": "A", "utm": utm, "base": base}
    top = f"<div class='top'><div class='w'><a href='{base}/lp/{P.OWNERS}' style='display:flex;align-items:center;gap:12px'><img src='{base}/static/poltrona/logo_512.png' alt=''><b>Poltrona Libera</b></a></div></div>"
    return HTMLResponse(f"<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{escape(title)}</title>"
                        f"<meta name='description' content='{escape(desc)}'>{head_extra}{CSS}{EXTRA_CSS}{pixel_html}</head><body>{top}<main class='w'>{body}</main>{beacon}"
                        f"<footer class='w muted' style='padding-bottom:30px'><div style='color:var(--ink);font-size:15px;margin-bottom:10px'>{P.footer_html()}</div>Poltrona Libera · Milano · <a href='{base}/pl/privacy' style='color:inherit'>Privacy</a></footer></body></html>")


@router.get("/{slug}", response_class=HTMLResponse)
def sales(slug: str, request: Request, annullato: int = 0):
    g = G.CATALOG.get(slug)
    if not g:
        raise HTTPException(404)
    base = P.base()
    q = request.query_params
    utm = "/".join(x for x in (q.get("utm_source"), q.get("utm_campaign"), q.get("utm_content")) if x) or ("meta" if q.get("fbclid") else "")
    other = G.CATALOG[g["other"]]
    now, was = G.price_str(G.PRICE_CENTS), G.price_str(G.LIST_PRICE_CENTS)
    from app.services import capi

    pv_id, vc_id, ic_id = capi.new_event_id(), capi.new_event_id(), capi.new_event_id()
    ud = capi.user_data(request)
    capi.send("PageView", pv_id, str(request.url), ud)
    capi.send("ViewContent", vc_id, str(request.url), ud, {"content_name": slug, "content_type": "product", "value": G.PRICE_CENTS / 100, "currency": "EUR"})
    fbjs = f"try{{fbq('track','InitiateCheckout',{{content_name:'{slug}',value:{G.PRICE_CENTS / 100},currency:'EUR'}},{{eventID:'{ic_id}'}})}}catch(e){{}}"
    pre = G.prepare_checkout(slug, utm, (request.cookies.get("_fbp") or "", request.cookies.get("_fbc") or ""), (request.headers.get("x-forwarded-for") or "").split(",")[0].strip(), request.headers.get("user-agent") or "") if G.stripe_ready() else None
    if pre:  # instant: the button is a direct link to the ready session; the server-side InitiateCheckout is sent by a beacon
        buy_form = (f"<a class='btn' href='{escape(pre)}' onclick=\"{fbjs};try{{navigator.sendBeacon('{base}/pl/guida/{slug}/ic/{ic_id}')}}catch(e){{}}\">Scarica la guida · {now}</a>")
    else:
        buy_form = (f"<form method='post' action='{base}/pl/guida/{slug}/checkout'><input type='hidden' name='utm' value='{escape(utm)}'><input type='hidden' name='eid' value='{ic_id}'>"
                    f"<button class='btn' type='submit' onclick=\"{fbjs}\">Scarica la guida · {now}</button></form>")
    pains = "".join(f"<blockquote>{escape(p)}<small>Titolare di salone, Milano · settembre 2026</small></blockquote>" for p in g["pains"])
    chapters = "".join(f"<li><div><b>{escape(t)}</b><span>{escape(d)}</span></div></li>" for t, d in g["chapters"])
    previews = "".join(f"<img src='{base}/static/poltrona/guide/{slug}_p{p}.png' alt='Pagina {p} della guida' loading='lazy'>" for p in g["preview_pages"])
    kit = "".join(f"<span>{escape(k)}</span>" for k in g["kit"])
    body = f"""
{"<div class='ok-box' style='background:var(--warnbg);color:var(--warn);margin-top:14px'>Pagamento annullato: nessun addebito. Quando vuoi, il bottone è qui sotto.</div>" if annullato else ""}
<section class='hero' data-sec='hero'><div>
<div class='kick'>Guida PDF · {g['pages']} pagine + kit · per titolari di salone</div>
<h1>{escape(g['headline'])}</h1>
<p class='lead' style='margin-top:12px'>{escape(g['sub'])}</p>
<div class='pricebox'><span class='now'>{now}</span><span class='was'>{was}</span><span class='tag'>prezzo di lancio</span></div>
{buy_form}
<div class='trustline'><span>PDF subito via email</span><span>{g['pages']} pagine + kit da stampare</span><span>Carta, PayPal, Apple e Google Pay</span></div>
</div><div><img class='cover' src='{base}/static/poltrona/guide/{slug}_p1.png' alt='Copertina: {escape(g['title'])}'></div></section>

<h2 data-sec='anteprima' style='margin-top:10px'>Sfoglia la guida</h2>
<p class='muted' style='margin:0 0 10px'>Copertina, indice e due capitoli, così vedi com'è fatta prima di prenderla.</p>
<div class='previews'>{previews}</div>

<h2 data-sec='pains'>Ti riconosci?</h2>
<p class='muted' style='margin:0 0 10px'>Le risposte esatte che ci hanno scritto le titolari di salone quando abbiamo chiesto perché una postazione era vuota.</p>
<div class='pains'>{pains}</div>

<h2 data-sec='indice'>Cosa c'è dentro</h2>
<ol class='chapters'>{chapters}</ol>
<h3 style='margin-top:22px'>Il kit da stampare</h3><div class='kit'>{kit}</div>

<div class='two' data-sec='per_chi'><div class='card'><h3 style='margin-top:0'>È per te se</h3><ul>{"".join(f"<li>{escape(x)}</li>" for x in g['for'])}</ul></div>
<div class='card'><h3 style='margin-top:0'>Non è per te se</h3><ul>{"".join(f"<li>{escape(x)}</li>" for x in g['not_for'])}</ul><p class='muted' style='margin-top:10px'>L'altra guida: <a href='{base}/pl/guida/{g['other']}' style='color:var(--acc)'>«{escape(other['title'])}»</a></p></div></div>

<h2 data-sec='autore'>Chi l'ha scritta</h2>
<div class='author'><img src='{base}/static/poltrona/logo_512.png' alt=''><div><p><b>Giovanni Ghigliotti</b>, fondatore di Poltrona Libera, il servizio che mette in contatto i saloni con le professioniste che cercano una postazione. Questa guida nasce dalle conversazioni con le titolari che si sono iscritte: hanno tutte lo stesso problema, e quasi nessuna aveva un metodo. Ho messo insieme quello che funziona, con i numeri del 2026 e le fonti in fondo al PDF.</p>
<p class='muted'>Non è consulenza legale o fiscale: per il tuo caso restano necessari il consulente del lavoro e il commercialista. È il metodo, con i pezzi pronti.</p></div></div>

<div class='buy' data-sec='prezzo' style='margin-top:30px'><div><h2>«{escape(g['title'])}»</h2><p class='muted'>{g['pages']} pagine + kit da stampare · PDF subito via email · {escape(was)} da novembre, oggi <b style='color:#fff'>{escape(now)}</b></p></div><div>{buy_form}</div></div>
<div class='card' data-sec='costo' style='margin-top:14px'><h3 style='margin-top:0'>Quanto costa aspettare</h3><p class='muted' style='margin:0'>{"Una postazione vuota vale 500-1.000 € al mese di incassi mancati, e ogni mese senza una collega è un mese in cui fai tutto tu. La guida costa meno di una piega, e la applichi da domani mattina." if slug == "squadra" else "Una postazione vuota a Milano vale 500-1.200 € al mese di canone non incassato; in un anno sono 6.000-14.000 €. La guida costa meno di una piega, e il primo annuncio lo pubblichi in cinque minuti."}</p></div>

<h2 data-sec='faq'>Domande</h2>
<div class='faq'>
<details><summary>Come la ricevo?</summary><p>Subito dopo il pagamento arrivi su una pagina con il link e ricevi una email con lo stesso link. È un PDF: si apre su telefono, tablet e computer, e si stampa.</p></details>
<details><summary>Vale per tutta Italia?</summary><p>Sì. Le regole (CCNL, INPS, affitto di poltrona) sono nazionali; gli esempi di prezzo delle postazioni sono di Milano e nel kit trovi il calcolo per la tua zona.</p></details>
<details><summary>Posso avere la fattura?</summary><p>Sì: rispondi alla mail di consegna con i dati del salone (ragione sociale, P.IVA, codice destinatario) e la ricevi entro 2 giorni lavorativi.</p></details>
<details><summary>Che differenza c'è con l'altra guida?</summary><p>«La dipendente è andata via» è per chi vuole ricostruire la squadra (annunci, colloqui, premi, progetto). «Basta dipendenti» è per chi vuole smettere di assumere e affittare le postazioni. Se sei indecisa, parti dalla situazione di oggi: hai una poltrona vuota adesso? Leggi prima «Basta dipendenti».</p></details>
<details><summary>Cosa succede dopo il pagamento?</summary><p>Arrivi subito su una pagina con il bottone per scaricare il PDF e ricevi la stessa cosa via email. Nei giorni seguenti ti scrivo io con i capitoli da cui partire e, se vuoi, con una mano per pubblicare la tua postazione.</p></details>
<details><summary>È aggiornata?</summary><p>Prima edizione settembre 2026, con tabelle CCNL 2026, aliquote INPS 2026 e regole di Milano in vigore. Le fonti sono elencate in fondo al PDF.</p></details>
</div>
<div class='card' style='margin-top:24px;text-align:center'><b>Hai dubbi o domande?</b><br><span class='muted'>Chiama o scrivi su WhatsApp a Giovanni: </span><a href='tel:+393925909721' style='color:var(--acc);font-weight:700'>+39 392 590 9721</a> · <a href='https://wa.me/393925909721?text=Ciao%20Giovanni%2C%20ho%20una%20domanda%20sulla%20guida' style='color:var(--acc);font-weight:700'>WhatsApp</a></div>
<div class='sticky'>{buy_form}</div>"""
    import json as _json

    url = f"{base}/pl/guida/{slug}"
    ld_product = {"@context": "https://schema.org", "@type": "Product", "name": f"Guida «{g['title']}»", "description": g["sub"], "image": f"{base}/static/poltrona/guide/{slug}_p1.png",
                  "brand": {"@type": "Brand", "name": "Poltrona Libera"}, "category": "Guida PDF per titolari di salone",
                  "offers": {"@type": "Offer", "url": url, "priceCurrency": "EUR", "price": f"{G.PRICE_CENTS / 100:.2f}", "availability": "https://schema.org/InStock", "priceValidUntil": "2026-10-31"}}
    faqs = [("Come la ricevo?", "Subito dopo il pagamento arrivi su una pagina con il link e ricevi una email con lo stesso link. È un PDF: si apre su telefono, tablet e computer."),
            ("Vale per tutta Italia?", "Sì. Le regole (CCNL, INPS, affitto di poltrona) sono nazionali; gli esempi di prezzo delle postazioni sono di Milano e nel kit trovi il calcolo per la tua zona."),
            ("Che differenza c'è con l'altra guida?", "«La dipendente è andata via» è per chi vuole ricostruire la squadra; «Basta dipendenti» è per chi vuole smettere di assumere e affittare le postazioni.")]
    ld_faq = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]}
    head_extra = (f"<link rel='canonical' href='{url}'><meta property='og:type' content='product'><meta property='og:title' content='{escape(g['title'])} — guida per titolari di salone'>"
                  f"<meta property='og:description' content='{escape(g['headline'])}'><meta property='og:image' content='{base}/static/poltrona/guide/{slug}_p1.png'><meta property='og:url' content='{url}'>"
                  f"<meta property='og:locale' content='it_IT'><meta name='twitter:card' content='summary_large_image'>"
                  f"<script type='application/ld+json'>{_json.dumps(ld_product, ensure_ascii=False)}</script><script type='application/ld+json'>{_json.dumps(ld_faq, ensure_ascii=False)}</script>")
    return _shell(f"{g['title']} — guida per titolari di salone", body, _pixel(pv_id, f"fbq('track','ViewContent',{{content_name:'{slug}',content_type:'product',value:{G.PRICE_CENTS / 100},currency:'EUR'}},{{eventID:'{vc_id}'}});"), g["headline"], beacon_id=f"guida_{slug}", utm=utm or "diretto", head_extra=head_extra)


@router.post("/{slug}/ic/{eid}")
def ic_beacon(slug: str, eid: str, request: Request):
    from app.services import capi

    capi.send("InitiateCheckout", eid, f"{P.base()}/pl/guida/{slug}", capi.user_data(request), {"content_name": slug, "content_type": "product", "value": G.PRICE_CENTS / 100, "currency": "EUR"})
    return {"ok": True}


@router.post("/{slug}/checkout")
async def checkout(slug: str, request: Request):
    form = await request.form()
    from app.services import capi

    eid = str(form.get("eid") or "") or capi.new_event_id()
    capi.send("InitiateCheckout", eid, f"{P.base()}/pl/guida/{slug}", capi.user_data(request), {"content_name": slug, "content_type": "product", "value": G.PRICE_CENTS / 100, "currency": "EUR"})
    url = G.create_checkout(slug, str(form.get("utm") or ""), fb=(request.cookies.get("_fbp") or "", request.cookies.get("_fbc") or ""), ip=(request.headers.get("x-forwarded-for") or "").split(",")[0].strip(), ua=request.headers.get("user-agent") or "")
    if not url:
        raise HTTPException(503, "Pagamenti non ancora attivi: riprova tra poco o scrivi su WhatsApp al 392 590 9721.")
    return RedirectResponse(url, status_code=303)


@router.get("/{slug}/grazie", response_class=HTMLResponse)
def grazie(slug: str, request: Request, session_id: str = ""):
    g = G.CATALOG.get(slug)
    if not g:
        raise HTTPException(404)
    from app.services import capi

    buyer = None
    if session_id and G.stripe_ready():
        try:
            buyer = G.fulfil_session(session_id)
        except Exception as e:  # noqa: BLE001
            log.error("fulfil %s: %s", session_id, e)
    base = P.base()
    if buyer:
        body = f"""<div style='max-width:640px;margin:30px auto;text-align:center'><div style='font-size:52px'>✅</div><h1>Grazie: la guida è tua</h1>
<p class='lead' style='margin:10px auto 22px'>Ti abbiamo mandato il link anche a <b>{escape(buyer['email'])}</b>. Scaricala adesso:</p>
<p><a class='btn' href='{G.download_url(buyer)}'>Scarica «{escape(g['title'])}» (PDF)</a></p>
<p class='muted' style='margin-top:18px'>{"Da dove partire: capitolo 2 (le prime 48 ore) e capitolo 5 (i premi sul fatturato)." if slug == "squadra" else "Da dove partire: capitolo 2 (i numeri) e capitolo 6 (il contratto in 12 punti)."}</p>
<p class='muted'>Hai una postazione vuota? <a href='{base}/lp/{P.OWNERS}#lista-hero' style='color:var(--acc)'>Pubblicala gratis su Poltrona Libera</a> in cinque minuti.</p></div>"""
        px = _pixel(capi.new_event_id(), f"fbq('track','Purchase',{{value:{(buyer.get('amount') or G.PRICE_CENTS) / 100},currency:'EUR',content_name:'{slug}',content_type:'product'}},{{eventID:'{escape(buyer['id'])}'}});")
    else:
        body = "<div style='max-width:640px;margin:30px auto;text-align:center'><h1>Stiamo confermando il pagamento</h1><p class='lead'>Ricarica questa pagina tra qualche secondo. Se hai pagato ma non ricevi nulla entro 10 minuti, scrivi su WhatsApp al 392 590 9721.</p></div>"
        px = ""
    return _shell("Grazie — Poltrona Libera", body, px, "")


@router.get("/download/{token}")
def download(token: str):
    buyer = G.by_token(token)
    if not buyer:
        raise HTTPException(404, "link non valido")
    path = G.pdf_path(buyer["slug"])
    if not __import__("os").path.exists(path):
        raise HTTPException(503, "file non disponibile, scrivi su WhatsApp al 392 590 9721")
    try:
        from google.cloud.firestore_v1 import Increment

        db.get_db().collection("buyers").document(buyer["id"]).update({"downloads": Increment(1), "last_download_at": db.now()})
    except Exception:  # noqa: BLE001
        pass
    g = G.CATALOG[buyer["slug"]]
    return FileResponse(path, media_type="application/pdf", filename=f"{g['title']} - Poltrona Libera.pdf")


@router.post("/stripe/webhook")
async def webhook(request: Request):
    """Stripe → checkout.session.completed: fulfil even if the buyer closed the success page."""
    import stripe

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    s = get_settings()
    try:
        event = stripe.Webhook.construct_event(payload, sig, s.stripe_webhook_secret) if s.stripe_webhook_secret else stripe.Event.construct_from(__import__("json").loads(payload), s.stripe_secret_key)
    except Exception as e:  # noqa: BLE001
        log.error("stripe webhook rejected: %s (sig header present: %s, secret len: %s)", str(e)[:160], bool(sig), len(s.stripe_webhook_secret or ""))
        raise HTTPException(400, f"webhook: {e}")
    if event["type"] == "checkout.session.completed":
        try:
            G.fulfil_session(event["data"]["object"]["id"])
        except Exception as e:  # noqa: BLE001
            log.error("webhook fulfil: %s", e)
    return {"ok": True}
