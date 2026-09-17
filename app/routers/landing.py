"""
Hosted landing pages for smoke tests. PUBLIC routes (no API token).

GET  /lp/{cluster_id}            -> serves one variant (A/B/C): sticky per visitor via cookie, or ?v=B to force
POST /lp/{cluster_id}/signup     -> stores the lead (email + optional answer) under problem_clusters/{id}/leads
GET  /lp/{cluster_id}/stats      -> per-variant visitors / signups (token required)

Every view and signup updates validation_experiments/lp_{cluster_id} (type landing_page, status running):
metrics = {"visitors": n, "signups": n, "by_variant": {"A": {"visitors":..,"signups":..}, ...}}
-> funnel stage 7 (presale_validation) reads it automatically. Price is always visible on the page.
Meta pixel: set META_PIXEL_ID to inject the pixel (PageView on load, Lead on signup).
"""
from __future__ import annotations

import hashlib
import secrets
from html import escape

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from google.cloud.firestore_v1 import Increment

from app import db
from app.auth import require_api
from app.config import get_settings

router = APIRouter(prefix="/lp", tags=["landing"])


def _offer(cluster_id: str) -> tuple[dict, dict, dict]:
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    o = db.get(db.OPPORTUNITY_SCORING, cluster_id) or {}
    offer = o.get("offer")
    if not c or not offer or not offer.get("variants"):
        raise HTTPException(404, "no landing for this cluster (generate an offer first: POST /clusters/{id}/offer)")
    return c, o, offer


def _pick_variant(offer: dict, forced: str | None, cookie: str | None) -> dict:
    variants = [v for v in offer["variants"] if v["key"] in (offer.get("active_variants") or [v["key"] for v in offer["variants"]])]
    keys = [v["key"] for v in variants]
    if forced in keys:
        return next(v for v in variants if v["key"] == forced)
    if cookie in keys:
        return next(v for v in variants if v["key"] == cookie)
    return secrets.choice(variants)


def _bump(cluster_id: str, variant: str, field: str, ip_ua_hash: str | None = None) -> None:
    client = db.get_db()
    ref = client.collection(db.VALIDATION_EXPERIMENTS).document(f"lp_{cluster_id}")
    if not ref.get().exists:
        ref.set({"cluster_id": cluster_id, "type": "landing_page", "status": "running", "platform": "hosted landing (/lp)",
                 "cost_eur": 0, "started_at": db.now(), "metrics": {"visitors": 0, "signups": 0, "by_variant": {}},
                 "created_at": db.now(), "updated_at": db.now()})
    ref.update({f"metrics.{field}": Increment(1), f"metrics.by_variant.{variant}.{field}": Increment(1), "updated_at": db.now()})


def _pixel(event: str = "PageView") -> str:
    pid = getattr(get_settings(), "meta_pixel_id", "") or ""
    if not pid:
        return ""
    return f"""<script>!function(f,b,e,v,n,t,s){{if(f.fbq)return;n=f.fbq=function(){{n.callMethod?n.callMethod.apply(n,arguments):n.queue.push(arguments)}};
if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}}
(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');fbq('init','{escape(pid)}');fbq('track','{event}');</script>"""


def render(c: dict, offer: dict, v: dict, base: str, signed_up: bool = False) -> str:
    from app.templates.landing import render_landing

    return render_landing(c, offer, v, base, pixel_html=_pixel("Lead" if signed_up else "PageView"), signed_up=signed_up)


def _render_legacy(c: dict, offer: dict, v: dict, base: str, signed_up: bool = False) -> str:
    lang = v.get("target_language") or "en"
    t = {"it": {"how": "Come funziona", "price": "Prezzo", "mo": "/mese", "faq": "Domande frequenti", "email": "La tua email di lavoro",
                "q": "Qual è la parte più frustrante oggi? (facoltativo)", "thanks": "Grazie! Ti scriviamo entro pochi giorni.", "founder": "Un progetto in fase di validazione: il prezzo indicato è quello reale al lancio."},
         "en": {"how": "How it works", "price": "Pricing", "mo": "/month", "faq": "Questions", "email": "Your work email",
                "q": "What's the most frustrating part today? (optional)", "thanks": "Thanks! We'll be in touch within days.", "founder": "Early-access project: the price shown is the real launch price."}}[lang if lang in ("it", "en") else "en"]
    pay = offer.get("payment_link_url")
    cta_html = (f'<a href="{escape(pay)}" onclick="try{{fbq(\'track\',\'InitiateCheckout\')}}catch(e){{}}" style="display:inline-block;background:#111827;color:#fff;padding:14px 22px;border-radius:10px;font-weight:700;text-decoration:none;font-size:16px">{escape(v["cta"])}</a>'
                if pay else f"""<form method="post" action="{base}/lp/{escape(c['id'])}/signup" style="display:flex;flex-direction:column;gap:10px;max-width:420px">
      <input type="hidden" name="variant" value="{escape(v['key'])}">
      <input name="email" type="email" required placeholder="{t['email']}" style="padding:12px 14px;border:1px solid #d1d5db;border-radius:10px;font-size:15px">
      <input name="answer" placeholder="{t['q']}" style="padding:12px 14px;border:1px solid #d1d5db;border-radius:10px;font-size:15px">
      <button type="submit" style="background:#111827;color:#fff;padding:14px 22px;border:0;border-radius:10px;font-weight:700;font-size:16px;cursor:pointer">{escape(v['cta'])}</button>
    </form>""")
    if signed_up:
        cta_html = f'<div style="padding:16px;border-radius:10px;background:#ecfdf5;color:#065f46;font-weight:600">{t["thanks"]}</div>'
    benefits = "".join(f'<li style="margin:8px 0">{escape(b)}</li>' for b in v.get("benefits", []))
    steps = "".join(f'<li style="margin:8px 0">{escape(s)}</li>' for s in v.get("how_it_works", []))
    faq = "".join(f'<details style="margin:8px 0"><summary style="cursor:pointer;font-weight:600">{escape(o.get("objection",""))}</summary><p style="color:#374151;margin:6px 0 0">{escape(o.get("answer",""))}</p></details>' for o in v.get("objections", []))
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(v['headline'])}</title>{_pixel("Lead" if signed_up else "PageView")}
<style>body{{margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#111827;background:#fff}}.w{{max-width:720px;margin:0 auto;padding:32px 20px}}h1{{font-size:34px;line-height:1.15;margin:0 0 12px}}h2{{font-size:20px;margin:36px 0 10px}}p{{line-height:1.55}}.price{{display:flex;align-items:baseline;gap:6px}}.price b{{font-size:40px}}.tag{{display:inline-block;font-size:12px;color:#6b7280;border:1px solid #e5e7eb;border-radius:999px;padding:3px 10px;margin-bottom:16px}}</style></head>
<body><div class="w">
  <span class="tag">{escape(v.get('plan_name') or '')}</span>
  <h1>{escape(v['headline'])}</h1>
  <p style="font-size:18px;color:#374151">{escape(v['subheadline'])}</p>
  <ul style="font-size:16px;padding-left:20px">{benefits}</ul>
  <h2>{t['how']}</h2><ol style="font-size:16px;padding-left:20px">{steps}</ol>
  <h2>{t['price']}</h2>
  <div class="price"><b>€{v['price_eur_month']:.0f}</b><span style="color:#6b7280">{t['mo']}</span></div>
  <p style="color:#6b7280;font-size:14px">{escape(v.get('price_justification') or '')}</p>
  <div style="margin:20px 0 8px">{cta_html}</div>
  <p style="color:#9ca3af;font-size:12px">{t['founder']}</p>
  <h2>{t['faq']}</h2>{faq}
</div></body></html>"""


@router.get("/{cluster_id}", response_class=HTMLResponse)
def landing(cluster_id: str, request: Request, v: str | None = None, ok: int = 0):
    c, o, offer = _offer(cluster_id)
    cookie = request.cookies.get(f"lpv_{cluster_id}")
    var = _pick_variant(offer, v, cookie)
    # count one visitor per (variant, ip+ua, day); crude bot filter: skip obvious crawlers
    ua = request.headers.get("user-agent", "")
    if not ok and not any(b in ua.lower() for b in ("bot", "crawler", "spider", "curl", "python-requests", "facebookexternalhit")):
        h = hashlib.sha256(f"{request.client.host if request.client else ''}|{ua}|{db.now():%Y-%m-%d}".encode()).hexdigest()[:24]
        seen_ref = db.get_db().collection(db.PROBLEM_CLUSTERS).document(cluster_id).collection("lp_visits").document(h)
        if not seen_ref.get().exists:
            seen_ref.set({"variant": var["key"], "at": db.now()})
            _bump(cluster_id, var["key"], "visitors")
    base = get_settings().public_base_url.rstrip("/")
    resp = HTMLResponse(render(c, offer, var, base, signed_up=bool(ok)))
    resp.set_cookie(f"lpv_{cluster_id}", var["key"], max_age=60 * 60 * 24 * 30, samesite="lax")
    return resp


@router.post("/{cluster_id}/signup")
def signup(cluster_id: str, email: str = Form(...), variant: str = Form("A"), answer: str = Form(""), business: str = Form("")):
    c, o, offer = _offer(cluster_id)
    lead_id = hashlib.sha256(email.strip().lower().encode()).hexdigest()[:20]
    ref = db.get_db().collection(db.PROBLEM_CLUSTERS).document(cluster_id).collection("leads").document(lead_id)
    if not ref.get().exists:
        ref.set({"email": email.strip().lower(), "variant": variant, "answer": answer[:1000], "business": business[:200], "at": db.now()})
        _bump(cluster_id, variant, "signups")
    base = get_settings().public_base_url.rstrip("/")
    return RedirectResponse(f"{base}/lp/{cluster_id}?v={variant}&ok=1", status_code=303)


@router.get("/{cluster_id}/stats", dependencies=[Depends(require_api)])
def stats(cluster_id: str):
    exp = db.get(db.VALIDATION_EXPERIMENTS, f"lp_{cluster_id}") or {}
    m = exp.get("metrics") or {}
    out = {"visitors": m.get("visitors", 0), "signups": m.get("signups", 0),
           "signup_rate": round(m.get("signups", 0) / m["visitors"], 3) if m.get("visitors") else 0.0, "by_variant": {}}
    for k, v in (m.get("by_variant") or {}).items():
        out["by_variant"][k] = {**v, "signup_rate": round(v.get("signups", 0) / v["visitors"], 3) if v.get("visitors") else 0.0}
    leads = [d.to_dict() for d in db.get_db().collection(db.PROBLEM_CLUSTERS).document(cluster_id).collection("leads").stream()]
    out["leads"] = [{"variant": l.get("variant"), "answer": l.get("answer"), "at": l.get("at")} for l in leads]  # emails only via Firestore
    return out


@router.get("/privacy", response_class=HTMLResponse)
def privacy_tool():
    """Privacy policy of the research tool itself (public posts analysis) — the URL given in API access requests."""
    return HTMLResponse("""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Privacy — startup problem research</title>
<style>body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:720px;margin:0 auto;padding:32px 20px;color:#0f172a;line-height:1.6}h1{font-size:26px}h2{font-size:18px;margin-top:24px}</style></head><body>
<h1>Privacy policy — startup problem research tool</h1>
<p><b>Controller</b>: Giovanni Ghigliotti, giovannighigliotti96@gmail.com (Italy). Personal, non-commercial research project: finding recurring, unsolved problems that small businesses describe in public.</p>
<h2>What is processed</h2><p>Publicly available posts, comments and reviews from developer/community APIs and feeds (Hacker News, app stores, public forums, YouTube comments, Reddit Data API when authorised). For each item we keep the public permalink, a machine-extracted one-sentence problem statement, numeric scores, and a salted one-way hash used only to count distinct authors. <b>We never store usernames, profile data or private messages.</b></p>
<h2>Retention</h2><p>The original text of Reddit items is deleted 30 days after collection; only the permalink, the extracted statement and aggregate statistics remain. Items are removed on request of the author or the platform. Nothing is sold, licensed, redistributed or used to train models.</p>
<h2>Publication</h2><p>Aggregate findings (e.g. "N distinct people describe problem X") may be used internally to decide which product ideas to test. Reddit content is never displayed on public pages.</p>
<h2>Your rights</h2><p>Access, rectification or erasure: write to the email above. You may lodge a complaint with the Italian Data Protection Authority (Garante).</p>
</body></html>""")


@router.get("/{cluster_id}/privacy", response_class=HTMLResponse)
def privacy(cluster_id: str):
    c, o, offer = _offer(cluster_id)
    brand = offer.get("product_name") or "questo progetto"
    return HTMLResponse(f"""<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Privacy — {escape(brand)}</title>
<style>body{{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:720px;margin:0 auto;padding:32px 20px;color:#0f172a;line-height:1.6}}h1{{font-size:26px}}h2{{font-size:18px;margin-top:24px}}</style></head><body>
<h1>Informativa privacy — {escape(brand)}</h1>
<p><b>Titolare del trattamento</b>: Giovanni Ghigliotti, giovannighigliotti96@gmail.com.</p>
<h2>Quali dati raccogliamo</h2><p>L'indirizzo email e, se lo indichi, il nome del locale e la risposta libera che inserisci nel modulo. Dati tecnici di navigazione (pagina vista, variante mostrata) in forma aggregata.</p>
<h2>Perché</h2><p>Per contattarti in merito a {escape(brand)}, un progetto in fase di validazione, e per misurare l'interesse verso il servizio. Base giuridica: il tuo consenso, espresso inviando il modulo. Nessuna newsletter, nessuna cessione a terzi.</p>
<h2>Pixel di Meta</h2><p>La pagina usa il pixel di Meta Platforms per misurare l'efficacia degli annunci (eventi: visualizzazione pagina, iscrizione). Puoi limitarne l'uso tramite le impostazioni del browser o le <a href="https://www.facebook.com/ads/preferences">preferenze pubblicitarie di Meta</a>.</p>
<h2>Conservazione e diritti</h2><p>I dati sono conservati su Google Cloud (Firestore, regione UE) per 12 mesi o fino a tua richiesta di cancellazione. Puoi chiedere accesso, rettifica o cancellazione scrivendo all'email sopra. Hai diritto di reclamo al Garante per la protezione dei dati personali.</p>
</body></html>""")
