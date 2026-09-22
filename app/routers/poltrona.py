"""Poltrona Libera pages: owner listing form (magic link), public catalogue with free contact requests, admin panel."""
from __future__ import annotations

import csv
import logging
import io
from html import escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import db
from app.config import get_settings
from app.services import poltrona as P

log = logging.getLogger("poltrona.web")
router = APIRouter(prefix="/pl", tags=["poltrona"])

CSS = """<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:wght@500;600&family=Source+Sans+3:wght@400;600;700&display=swap">
<style>:root{--paper:#f6f3ee;--card:#fffdf9;--ink:#1c1917;--mut:#6b625a;--line:#e3dbd0;--acc:#b5532c;--acc2:#8a6a3d;--ok:#2f6f4e;--okbg:#dcefe3;--warn:#8a6a3d;--warnbg:#f1e7d3;--bad:#9b2c2c;--badbg:#f6dede}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:"Source Sans 3",system-ui,sans-serif;font-size:16px;line-height:1.5}
.top{background:var(--paper);border-bottom:1px solid var(--line)}.top .w{display:flex;align-items:center;gap:12px;padding:12px 16px}.top img{width:36px;height:36px;border-radius:9px}.top b{font-size:18px;letter-spacing:-.02em}.top a{color:var(--ink);text-decoration:none}
.w{max-width:960px;margin:0 auto;padding:0 16px}main.w{padding:26px 16px 60px}
h1{font-family:"Fraunces",Georgia,serif;font-weight:600;font-size:30px;line-height:1.12;margin:0 0 8px;text-wrap:balance}h2{font-family:"Fraunces",Georgia,serif;font-weight:600;font-size:21px;margin:26px 0 8px}
.lead{color:var(--mut);margin:0 0 20px;max-width:62ch}.muted{color:var(--mut);font-size:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px}
label{display:block;font-weight:600;margin:14px 0 4px}label small{display:block;font-weight:400;color:var(--mut);font-size:13px}
input,textarea,select{width:100%;padding:11px 12px;border:1px solid var(--line);border-radius:9px;font:inherit;background:#fff;color:var(--ink)}input:focus,textarea:focus{outline:2px solid var(--acc);outline-offset:1px}
.btn{display:inline-block;background:var(--acc);color:#fff;border:0;border-radius:999px;padding:13px 22px;font:inherit;font-weight:700;cursor:pointer;text-decoration:none}.btn.sec{background:transparent;color:var(--ink);border:1px solid var(--line)}.btn:disabled{opacity:.5}
.steps{display:flex;gap:6px;margin:0 0 18px;flex-wrap:wrap}.steps span{font-size:13px;padding:5px 10px;border-radius:999px;background:var(--card);border:1px solid var(--line);color:var(--mut)}.steps span.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:700;white-space:nowrap}.pill.ok{background:var(--okbg);color:var(--ok)}.pill.warn{background:var(--warnbg);color:var(--warn)}.pill.bad{background:var(--badbg);color:var(--bad)}.pill.gray{background:#eee9e2;color:var(--mut)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}
.listing{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;display:flex;flex-direction:column}.listing .ph{aspect-ratio:4/3;background:#e8e1d6 center/cover no-repeat}.listing .body{padding:14px 16px 16px;display:flex;flex-direction:column;gap:6px;flex:1}
.tag{display:inline-block;font-size:12px;padding:2px 8px;border-radius:999px;background:#efe9e0;color:var(--mut);margin:0 4px 4px 0}.listing h3{margin:2px 0 0;font-size:18px;font-family:"Fraunces",Georgia,serif;font-weight:600}.listing p{margin:0;color:var(--mut);font-size:14px}.price{font-weight:700;font-size:18px;margin-top:auto}.price span{font-weight:400;color:var(--mut);font-size:14px}.note{font-size:12px;color:var(--acc2)}
.photos{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}.photos img{width:110px;height:82px;object-fit:cover;border-radius:8px;border:1px solid var(--line)}
.tbl{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:12px}table{border-collapse:collapse;width:100%;min-width:760px;font-size:14px}th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut)}tr:last-child td{border-bottom:0}
.ok-box{background:var(--okbg);color:var(--ok);border-radius:12px;padding:16px 18px;font-weight:600}
dialog{border:0;border-radius:16px;padding:0;max-width:440px;width:calc(100% - 32px)}dialog::backdrop{background:rgba(28,25,23,.45)}dialog .in{padding:22px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
footer a{color:var(--ink);font-weight:700;text-decoration:none;border-bottom:1px solid var(--acc)}footer .sep{color:var(--mut);margin:0 8px}
@media(max-width:600px){h1{font-size:25px}}</style>"""


def _top(base: str) -> str:
    return f"<div class='top'><div class='w'><a href='{base}/pl' style='display:flex;align-items:center;gap:12px'><img src='{base}/static/poltrona/logo_512.png' alt=''><b>Poltrona Libera</b></a></div></div>"


def _pixel_html(event: str, request: Request | None = None, ev_id: str = "", url: str = "") -> str:
    from app.routers.landing import _pixel
    from app.services import capi

    if not event:
        return ""
    pv_id = capi.new_event_id()
    if request is not None and event == "Lead":
        capi.send("PageView", pv_id, url or str(request.url), capi.user_data(request))
    return _pixel(event, pv_id, ev_id)


def _page(title: str, body: str, pixel: str = "PageView", desc: str = "", request: Request | None = None, ev_id: str = "", beacon_id: str = "") -> HTMLResponse:
    base = P.base()
    beacon = ""
    if beacon_id:
        from app.templates.landing import BEHAVIOR_JS

        q = request.query_params if request is not None else {}
        utm = "/".join(x for x in (q.get("utm_source"), q.get("utm_campaign"), q.get("utm_content")) if x) or ("meta" if q.get("fbclid") else "diretto")
        beacon = BEHAVIOR_JS % {"cid": beacon_id, "variant": "A", "utm": utm, "base": base}
    return HTMLResponse(f"<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{escape(title)} — Poltrona Libera</title>"
                        f"<meta name='description' content='{escape(desc)}'>{CSS}{_pixel_html(pixel, request, ev_id)}</head><body>{_top(base)}<main class='w'>{body}</main>{beacon}"
                        f"<footer class='w muted' style='padding-bottom:30px'><div style='color:var(--ink);font-size:15px;margin-bottom:10px'>{P.footer_html()}</div>Poltrona Libera · Milano · <a href='{base}/pl/privacy' style='color:inherit'>Privacy</a></footer></body></html>")



# ----------------------------------------------------------------------------- home: the door (link in bio, ads, direct traffic)
@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Two doors: salon owner -> owners landing; professional -> catalogue. Nothing else on the page."""
    base = P.base()
    body = f"""<section style='text-align:center;padding:34px 0 10px'>
<h1 style='font-size:34px;margin-bottom:10px'>Postazioni in affitto nei saloni di Milano</h1>
<p class='lead' style='margin:0 auto 26px'>I saloni pubblicano la poltrona libera, gratis. Parrucchiere e barbieri la vedono con foto, giorni, prezzo e numero, e chiamano direttamente.</p>
<p class='muted' style='margin:0 0 22px'><b>Chi sei?</b></p></section>
<div class='grid' style='grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px;align-items:stretch'>
  <a class='card' href='{base}/pl/postazioni' style='text-decoration:none;color:inherit;display:flex;flex-direction:column;gap:10px'>
    <div style='font-size:34px'>&#128136;</div>
    <h2 style='margin:0;font-size:22px'>Sono parrucchiera o barbiere</h2>
    <p class='muted' style='margin:0'>Cerco una postazione dove lavorare in proprio. Guardo gli annunci e chiamo io il salone. Gratis.</p>
    <span class='btn' style='margin-top:auto;align-self:flex-start'>Vedi le postazioni &rarr;</span></a>
  <a class='card' href='{base}/lp/{P.OWNERS}' style='text-decoration:none;color:inherit;display:flex;flex-direction:column;gap:10px'>
    <div style='font-size:34px'>&#129681;</div>
    <h2 style='margin:0;font-size:22px'>Ho un salone</h2>
    <p class='muted' style='margin:0'>Ho una poltrona vuota e voglio affittarla. Pubblico l'annuncio in cinque minuti e mi chiamano loro.</p>
    <span class='btn sec' style='margin-top:auto;align-self:flex-start'>Pubblica gratis la tua postazione &rarr;</span></a>
</div>
<div class='card' style='margin-top:24px'><h2 style='margin-top:0;font-size:19px'>Come funziona</h2>
<p class='muted' style='margin:0'>Il salone pubblica zona, giorni, prezzo, cosa &egrave; incluso, una foto e il numero da chiamare. Noi controlliamo l'annuncio e lo mettiamo online. La professionista chiama direttamente la titolare e si accordano tra loro: giorni, orari, prezzo, prova. Per entrambe &egrave; gratis.</p></div>
<p class='muted' style='text-align:center;margin-top:22px'>Titolare di salone? Le guide pratiche: <a href='{base}/pl/guida/squadra' style='color:var(--acc)'>&laquo;La dipendente &egrave; andata via&raquo;</a> &middot; <a href='{base}/pl/guida/poltrona' style='color:var(--acc)'>&laquo;Basta dipendenti&raquo;</a></p>"""
    return _page("Poltrona Libera - postazioni in affitto a Milano", body, desc="Postazioni in affitto nei saloni di Milano: i saloni pubblicano gratis, parrucchiere e barbieri chiamano direttamente.", request=request, beacon_id="home")


# ----------------------------------------------------------------------------- privacy (also the Meta app's privacy policy URL)
PRIVACY_HTML = """<h1>Informativa sulla privacy</h1>
<p class='lead'>Poltrona Libera è un servizio di Giovanni Ghigliotti (Arenzano, GE, Italia) che mette in contatto titolari di saloni con parrucchiere e barbieri che cercano una postazione. Questa pagina spiega quali dati raccogliamo, perché, e come chiederne la cancellazione.</p>
<h2>Titolare del trattamento</h2><p>Giovanni Ghigliotti — email: giovannighigliotti96@gmail.com — telefono: +39 392 590 9721.</p>
<h2>Quali dati raccogliamo</h2>
<ul><li><b>Titolari di salone</b>: nome e cognome, email, numero di telefono, nome del salone, zona, dettagli della postazione (giorni, prezzo, cosa è incluso, descrizione), foto della postazione, motivo per cui la postazione è libera.</li>
<li><b>Professioniste/i</b>: nome e cognome, email, numero di telefono, zona di interesse, specialità, risposta libera nel modulo.</li>
<li><b>Dati tecnici</b>: pagine viste, sezioni scorse, campi del modulo compilati, variante della pagina mostrata, provenienza (annuncio), in forma aggregata e con identificativo di sessione casuale. Registrazioni di sessione anonime tramite Microsoft Clarity.</li>
<li><b>Dati dai servizi Meta</b> (Facebook/Instagram): usiamo il pixel di Meta per misurare l'efficacia degli annunci (eventi: visualizzazione pagina, iscrizione, contatto) e, tramite la nostra app Meta, gestiamo le inserzioni e pubblichiamo contenuti sulla pagina Facebook di Poltrona Libera. Non raccogliamo dati personali degli utenti Facebook/Instagram al di fuori di quanto Meta fornisce in forma aggregata (statistiche delle inserzioni e della pagina).</li></ul>
<h2>Perché li usiamo</h2>
<ul><li>Per pubblicare l'annuncio della postazione: <b>nome del salone, zona, giorni, prezzo, foto e numero di telefono della titolare sono visibili pubblicamente</b> nell'annuncio, con il consenso dato dalla titolare al momento della pubblicazione.</li>
<li>Per avvisare le professioniste quando c'è una postazione nella loro zona e per rispondere alle loro richieste.</li>
<li>Per contattare gli iscritti in merito al servizio (email di conferma, promemoria per completare l'annuncio, aggiornamenti).</li>
<li>Per misurare l'interesse verso il servizio e migliorare le pagine.</li></ul>
<p>Base giuridica: il consenso, espresso inviando i moduli, e l'esecuzione del servizio richiesto. Nessuna vendita o cessione dei dati a terzi per fini di marketing. Nessuna decisione automatizzata.</p>
<h2>Dove sono conservati e per quanto</h2><p>Su Google Cloud (Firestore e Cloud Storage, regione europe-west1, UE). Email inviate tramite il nostro provider di posta. Conservazione: finché l'annuncio o l'iscrizione sono attivi e comunque non oltre 24 mesi dall'ultimo contatto, o fino a richiesta di cancellazione.</p>
<h2>Come chiedere la cancellazione dei dati</h2><p>Scrivi a <a href='mailto:giovannighigliotti96@gmail.com?subject=Cancellazione%20dati%20Poltrona%20Libera'>giovannighigliotti96@gmail.com</a> con oggetto "Cancellazione dati", oppure su WhatsApp al +39 392 590 9721, indicando l'email o il telefono con cui ti sei registrata/o. Cancelliamo iscrizione, annuncio e foto entro 7 giorni e ti confermiamo via email. Hai inoltre diritto di accesso, rettifica, limitazione e portabilità dei dati, e di reclamo al Garante per la protezione dei dati personali (www.garanteprivacy.it).</p>
<h2>Cookie e strumenti di terze parti</h2><p>Cookie tecnici (variante della pagina, accesso al pannello). Pixel di Meta e Microsoft Clarity per statistiche: puoi limitarli dalle impostazioni del browser, dalle <a href='https://www.facebook.com/ads/preferences'>preferenze pubblicitarie di Meta</a> o con <a href='https://clarity.microsoft.com/terms'>l'opt-out di Clarity</a>.</p>
<p class='muted'>Ultimo aggiornamento: 21 settembre 2026.</p>"""


@router.api_route("/privacy", methods=["GET", "HEAD"], response_class=HTMLResponse)
def privacy():
    return _page("Informativa sulla privacy", PRIVACY_HTML, pixel="", desc="Informativa sulla privacy di Poltrona Libera: quali dati raccogliamo, perché, e come chiederne la cancellazione.")


# ----------------------------------------------------------------------------- owner listing form
def _form_html(li: dict, saved: bool, base: str) -> str:
    v = lambda k: escape(str(li.get(k) or ""))  # noqa: E731
    photos = "".join(f"<img src='{escape(u)}' alt=''>" for u in li.get("photos") or [])
    status = li.get("status")
    banner = ""
    if status == "in_verifica":
        banner = "<div class='ok-box'>Annuncio inviato: lo stiamo controllando. Se tutto va bene entro qualche ora è online e ti scriviamo. Puoi ancora modificarlo qui sotto.</div>"
    elif status == "online":
        banner = f"<div class='ok-box'>Il tuo annuncio è online: <a href='{base}/pl/postazioni' style='color:inherit'>vedilo nel catalogo</a>. Se modifichi qualcosa, lo ricontrolliamo prima di ripubblicarlo.</div>"
    elif status == "rifiutato":
        banner = f"<div class='ok-box' style='background:var(--warnbg);color:var(--warn)'>Serve una modifica prima di pubblicare: <b>{escape(li.get('admin_note') or 'aggiungi qualche dettaglio')}</b></div>"
    elif status == "chiuso":
        banner = "<div class='ok-box' style='background:#eee9e2;color:var(--mut)'>Annuncio in pausa: non è visibile. Riattivalo quando vuoi.</div>"
    elif saved:
        banner = "<div class='ok-box' style='background:var(--warnbg);color:var(--warn)'>Bozza salvata. Per pubblicare servono: giorni, prezzo, almeno una foto e il numero da chiamare.</div>"
    return f"""
<div class='steps'><span class='on'>1 · Postazione</span><span class='on'>2 · Chi cerchi</span><span class='on'>3 · Foto</span><span class='on'>4 · Contatto</span></div>
<h1>Pubblica la tua postazione</h1>
<p class='lead'>Gratis. Due minuti. Nell'annuncio le professioniste vedono nome del salone, zona, giorni, prezzo, cosa è incluso, le foto e il numero da chiamare: ti chiamano direttamente.</p>
{banner}
<form method='post' enctype='multipart/form-data' class='card' style='margin-top:16px' id='annuncio'>
<h2 style='margin-top:0'>1 · La postazione</h2>
<label for='salone'>Nome del salone</label><input id='salone' name='salone' value='{v("salone")}' required>
<label for='zona'>Zona / quartiere di Milano <small>es. Porta Romana, Rozzano, NoLo</small></label><input id='zona' name='zona' value='{v("zona")}' required>
<label for='giorni'>Giorni e orari disponibili <small>scrivi come vuoi, es. "martedì-sabato, orario negozio" oppure "solo 3 giorni a settimana"</small></label><input id='giorni' name='giorni' value='{v("giorni")}' required>
<label for='prezzo'>Prezzo al mese <small>scrivilo come preferisci: "500 €", "450 € + prodotti", "percentuale sugli incassi, da concordare"</small></label><input id='prezzo' name='prezzo' value='{v("prezzo")}' required>
<label for='incluso'>Cosa è incluso <small>lavatesta, prodotti, phon, asciugamani, ricevimento clienti…</small></label><input id='incluso' name='incluso' value='{v("incluso")}'>
<label for='descrizione'>Due righe sul salone <small>com'è, che clientela ha, da quanto è aperto</small></label><textarea id='descrizione' name='descrizione' rows='3'>{v("descrizione")}</textarea>
<h2>2 · Chi cerchi</h2>
<label for='chi_cerchi'>Che professionista cerchi? <small>es. "parrucchiera esperta in schiariture e taglio donna", "barber", "anche part-time"</small></label><input id='chi_cerchi' name='chi_cerchi' value='{v("chi_cerchi")}'>
<h2>3 · Foto</h2>
<p class='muted' style='margin:0 0 6px'>Almeno una foto della postazione o del salone. Senza foto le professioniste non chiamano.</p>
<div class='photos'>{photos}</div>
<input type='file' id='foto' name='foto' accept='image/*' multiple>
<h2>4 · Contatto</h2>
<label for='titolare'>Il tuo nome</label><input id='titolare' name='titolare' value='{v("titolare")}' required>
<label for='telefono'>Numero che deve chiamare la professionista <small>compare nell'annuncio</small></label><input id='telefono' name='telefono' type='tel' value='{v("telefono")}' required>
<div class='row' style='margin-top:22px'><button class='btn' type='submit' name='submit' value='1'>{"Salva le modifiche" if status == "online" else "Pubblica l'annuncio"}</button><button class='btn sec' type='submit' name='submit' value='0'>Salva e finisci dopo</button>
{"<button class='btn sec' type='submit' name='submit' value='pausa'>Metti in pausa</button>" if status == "online" else "<button class='btn sec' type='submit' name='submit' value='riattiva'>Riattiva l'annuncio</button>" if status == "chiuso" else ""}</div>
<p class='muted' style='margin-top:12px'>Inviando accetti che nome del salone e numero compaiano nell'annuncio pubblico. Gli accordi tra te e la professionista sono di vostra esclusiva competenza.</p>
</form>"""


@router.get("/annuncio/{token}", response_class=HTMLResponse)
def annuncio(token: str, request: Request, saved: int = 0, nuovo: int = 0, eid: str = ""):
    li = P.by_token(token)
    if not li:
        raise HTTPException(404, "link non valido")
    return _page("Pubblica la tua postazione", _form_html(li, bool(saved), P.base()), pixel="Lead" if nuovo else "PageView", request=request, ev_id=eid)


@router.post("/annuncio/{token}")
async def annuncio_post(token: str, request: Request):
    li = P.by_token(token)
    if not li:
        raise HTTPException(404, "link non valido")
    form = await request.form()
    photos = []
    for f in form.getlist("foto"):
        if hasattr(f, "read"):
            data = await f.read()
            if data and len(data) <= 12 * 1024 * 1024:
                photos.append(data)
    action = str(form.get("submit") or "0")
    if action in ("pausa", "riattiva"):
        P.set_status(li["id"], "chiuso" if action == "pausa" else ("online" if li.get("approved_at") else "in_verifica"), quiet=True)
        return RedirectResponse(f"{P.base()}/pl/annuncio/{token}", status_code=303)
    submit = action == "1"
    out = P.save(li, {k: form.get(k) for k in ("salone", "titolare", "telefono", "zona", "giorni", "prezzo", "incluso", "chi_cerchi", "descrizione")}, photos, submit)
    if out.get("status") in ("bozza", "rifiutato") and not P.is_test(out.get("email")):  # left without publishing: say right away what is missing
        try:
            P.reminder_email(out, int(out.get("reminders_sent") or 0))
            db.get_db().collection("listings").document(li["id"]).update({"reminders_sent": int(out.get("reminders_sent") or 0) + 1, "last_reminder_at": db.now()})
        except Exception as e:  # noqa: BLE001
            log.error("immediate reminder: %s", e)
    if submit and out.get("status") == "in_verifica" and li.get("status") != "in_verifica":
        return RedirectResponse(f"{P.base()}/pl/annuncio/{token}/grazie", status_code=303)
    return RedirectResponse(f"{P.base()}/pl/annuncio/{token}?saved=1", status_code=303)


@router.get("/annuncio/{token}/grazie", response_class=HTMLResponse)
def grazie(token: str):
    li = P.by_token(token)
    if not li:
        raise HTTPException(404, "link non valido")
    base = P.base()
    body = f"""<div style='max-width:640px;margin:30px auto;text-align:center'>
<div style='font-size:52px;line-height:1'>✅</div>
<h1 style='margin-top:14px'>Annuncio inviato: è in fase di approvazione</h1>
<p class='lead' style='margin:10px auto 22px'>Grazie {escape(li.get('titolare') or '')}. Controlliamo a mano ogni annuncio: se tutto va bene entro qualche ora la postazione di <b>{escape(li.get('salone') or '')}</b> è online e ti mandiamo una email di conferma.</p>
<div class='card' style='text-align:left'>
<b>Cosa succede adesso</b>
<ol style='margin:8px 0 0;padding-left:20px;line-height:1.7'><li>Approviamo l'annuncio e ti scriviamo a {escape(li.get('email') or '')}.</li><li>Le professioniste di Milano lo vedono con zona, giorni, prezzo, foto e il tuo numero.</li><li>Ti chiamano direttamente: vi mettete d'accordo tra di voi.</li></ol></div>
<p class='muted' style='margin-top:18px'>Vuoi modificare qualcosa? <a href='{base}/pl/annuncio/{escape(token)}' style='color:inherit'>Apri il tuo annuncio</a> (il link è anche nella email).</p></div>"""
    return _page("Annuncio inviato", body, pixel="Lead")


# ----------------------------------------------------------------------------- public catalogue
def _card(lp: dict, base: str, real: bool) -> str:
    tags = "".join(f"<span class='tag'>{escape(x)}</span>" for x in lp.get("tags", []))
    ph = f"<div class='ph' style=\"background-image:url('{escape(lp['photo_url'])}')\"></div>" if lp.get("photo_url") else "<div class='ph'></div>"
    tel = "".join(ch for ch in (lp.get("telefono") or "") if ch.isdigit() or ch == "+")
    wa = ("39" + tel.lstrip("0")) if tel and not tel.startswith("+") else tel.lstrip("+")
    cta = ((f"<div class='row' style='margin-top:10px'><a class='btn' href='tel:{escape(tel)}' onclick=\"hit('{escape(lp['id'])}','call')\">Chiama {escape(lp.get('titolare') or 'la titolare')}</a>"
            f"<a class='btn sec' href='https://wa.me/{escape(wa)}?text={escape('Ciao, ho visto la postazione su Poltrona Libera')}' target='_blank' rel='noopener' onclick=\"hit('{escape(lp['id'])}','wa')\">WhatsApp</a></div>") if real
           else f"<a class='btn sec' style='margin-top:10px' href='{base}/lp/{P.PROS}#lista'>Registrati: ti avvisiamo noi</a>")
    return (f"<div class='listing'>{ph}<div class='body'>{tags and '<div>' + tags + '</div>'}<h3>{escape(lp.get('title') or '')}</h3><p>{escape(lp.get('text') or '')}</p>"
            f"<div class='price'>{escape(lp.get('price') or '')}<span> {escape(lp.get('price_note') or '')}</span></div><div class='note'>{escape(lp.get('note') or '')}</div>{cta}</div></div>")


@router.get("/postazioni", response_class=HTMLResponse)
def postazioni(request: Request):
    base = P.base()
    real = [P.public_card(x) for x in P.online_listings()]
    offer = (db.get(db.OPPORTUNITY_SCORING, P.PROS) or {}).get("offer") or {}
    examples = offer.get("listings") or []
    real_html = "".join(_card(x, base, True) for x in real)
    ex_html = "".join(_card(x, base, False) for x in examples)
    intro = (f"<p class='lead'>{len(real)} postazion{'e' if len(real) == 1 else 'i'} verificat{'a' if len(real) == 1 else 'e'} a Milano. Guardi gratis; quando ne trovi una che ti interessa chiami direttamente la titolare al numero nell'annuncio. Poi vi mettete d'accordo tra di voi."
             if real else "<p class='lead'>I primi saloni stanno pubblicando le loro postazioni. Registrati gratis: ti avvisiamo appena c'è una postazione nella tua zona.</p>")
    body = f"""<h1 data-sec='hero'>Postazioni disponibili a Milano</h1>{intro}
{('<div class="grid">' + real_html + '</div>') if real else ''}
<h2 data-sec='esempi'>{'Altri esempi di annuncio' if real else 'Così appaiono gli annunci'}</h2><p class='muted' style='margin:0 0 12px'>Esempi con dati indicativi e foto di saloni reali: mostrano cosa vedrai. Non sono saloni iscritti.</p>
<div class='grid'>{ex_html}</div>
<div class='card' style='margin-top:28px'><h2 style='margin-top:0'>Hai un salone con una poltrona vuota?</h2><p class='muted'>Pubblicala: è gratis, ci vogliono cinque minuti, e ti chiamano direttamente le professioniste.</p><a class='btn sec' href='{base}/lp/{P.OWNERS}'>Pubblica gratis la tua postazione</a></div><div class='card' style='margin-top:18px'><h2 style='margin-top:0'>Non trovi la tua zona?</h2><p class='muted'>Registrati gratis e ti scriviamo appena un salone della tua zona pubblica una postazione.</p><a class='btn' href='{base}/lp/{P.PROS}#lista'>Registrati gratis</a></div>
<script>function hit(id,k){{try{{navigator.sendBeacon('{base}/pl/click/'+id+'/'+k)}}catch(e){{}}try{{fbq('track','Contact')}}catch(e){{}}}}</script>"""
    return _page("Postazioni disponibili a Milano", body, desc="Postazioni in affitto in saloni di Milano: guardi gratis e chiami direttamente la titolare.", request=request, beacon_id="catalogo")


@router.post("/click/{listing_id}/{kind}")
def click(listing_id: str, kind: str, request: Request):
    from app.services import capi

    P.track_call(listing_id, kind)
    capi.send("Contact", capi.new_event_id(), f"{P.base()}/pl/postazioni", capi.user_data(request), {"content_name": listing_id, "content_category": kind})
    return {"ok": True}


@router.post("/contatto/{listing_id}")
async def contatto(listing_id: str, request: Request):
    form = await request.form()
    req = P.request_contact(listing_id, dict(form))
    if not req:
        raise HTTPException(404, "annuncio non disponibile")
    body = f"<h1>Richiesta inviata</h1><div class='ok-box'>Grazie {escape(req['nome'])}: entro 24 ore ti scriviamo a {escape(req['email'])} con nome e telefono della titolare.</div><p style='margin-top:18px'><a class='btn sec' href='{P.base()}/pl/postazioni'>Torna alle postazioni</a></p>"
    return _page("Richiesta inviata", body, pixel="Lead")


# ----------------------------------------------------------------------------- admin
def _cookie_value() -> str:
    """What the browser stores: a hash of the password and the cron secret, never the password itself."""
    import hashlib

    s = get_settings()
    return hashlib.sha256(f"{s.pl_admin_password}|{s.cron_token}|pl-admin".encode()).hexdigest()


def _logged_in(request: Request) -> bool:
    pw = get_settings().pl_admin_password
    return bool(pw) and request.cookies.get("pl_admin") == _cookie_value()


def _login_page(error: str = "") -> HTMLResponse:
    base = P.base()
    closed = not get_settings().pl_admin_password
    body = f"""<div class='card' style='max-width:420px;margin:40px auto'><h1 style='font-size:24px'>Pannello</h1>
{"<p class='muted'>Pannello chiuso: manca PL_ADMIN_PASSWORD nella configurazione del server.</p>" if closed else f"<form method='post' action='{base}/pl/admin/login'><label for='pw'>Password</label><input id='pw' name='password' type='password' autocomplete='current-password' required>{('<p style=color:var(--bad)>' + escape(error) + '</p>') if error else ''}<div class='row' style='margin-top:16px'><button class='btn' type='submit'>Entra</button></div></form>"}
</div>"""
    return _page("Pannello", body, pixel="")


@router.post("/admin/login")
async def admin_login(request: Request):
    form = await request.form()
    s = get_settings()
    import secrets as _secrets

    if s.pl_admin_password and _secrets.compare_digest(str(form.get("password") or ""), s.pl_admin_password):
        resp = RedirectResponse(f"{P.base()}/pl/admin", status_code=303)
        resp.set_cookie("pl_admin", _cookie_value(), max_age=60 * 60 * 24 * 30, httponly=True, samesite="lax", secure=P.base().startswith("https"))
        return resp
    return _login_page("Password sbagliata.")


@router.get("/admin/logout")
def admin_logout():
    resp = RedirectResponse(f"{P.base()}/pl/admin", status_code=303)
    resp.delete_cookie("pl_admin")
    return resp


def _auth(request: Request, token: str | None = None) -> None:
    if not _logged_in(request):
        raise HTTPException(401, "login richiesto")


@router.get("/admin", response_class=HTMLResponse)
def admin(request: Request, token: str | None = None):
    if not _logged_in(request):
        return _login_page()
    d = P.admin_data()
    base = P.base()
    pill = {"in_verifica": "warn", "online": "ok", "bozza": "gray", "rifiutato": "bad", "chiuso": "gray"}
    rows = ""
    for li in d["listings"]:
        pics = "".join(f"<a href='{escape(u)}' target='_blank'><img src='{escape(u)}' style='height:44px;border-radius:5px;margin-right:3px'></a>" for u in (li.get("photos") or [])[:3])
        miss = P.missing(li)
        approve = (f"<button class='btn' name='status' value='online' style='padding:6px 12px'>Approva</button>" if not miss
                   else f"<span class='pill bad' title='Non approvabile'>⚠ manca: {escape(', '.join(miss))}</span>")
        act = (f"<form method='post' action='{base}/pl/admin/listing/{li['id']}/status' class='row' style='gap:6px'>{approve}"
               f"<input name='note' placeholder='motivo (se rifiuti)' style='width:150px;padding:6px 8px'><button class='btn sec' name='status' value='rifiutato' style='padding:6px 12px'>Rifiuta</button>"
               f"<button class='btn sec' name='status' value='chiuso' style='padding:6px 12px'>Chiudi</button></form>")
        rows += (f"<tr><td><span class='pill {pill.get(li.get('status'), 'gray')}'>{escape(li.get('status') or '')}</span><br><small class='muted'>{str(li.get('updated_at'))[:16]}</small></td>"
                 f"<td><b>{escape(li.get('salone') or '')}</b><br>{escape(li.get('titolare') or '')}<br><a href='tel:{escape(li.get('telefono') or '')}'>{escape(li.get('telefono') or '')}</a><br>{escape(li.get('email') or '')}</td>"
                 f"<td>{escape(li.get('zona') or '')}<br><small>{escape(li.get('giorni') or '')}</small><br><b>{escape(li.get('prezzo') or '')}</b></td>"
                 f"<td>{escape(li.get('chi_cerchi') or '')}<br><small class='muted'>{escape((li.get('incluso') or '')[:80])}</small><br><small>📞 {int((li.get('clicks') or {}).get('call', 0))} · WA {int((li.get('clicks') or {}).get('whatsapp', 0))}</small></td><td>{pics}</td>"
                 f"<td>{act}<a class='muted' href='{base}/pl/annuncio/{li['token']}' target='_blank'>modifica ↗</a></td></tr>")
    by_zone: dict[str, dict] = {}
    for o in d["owners"]:
        z = (o.get("extra") or {}).get("zona") or "?"
        by_zone.setdefault(z.strip().lower(), {"z": z, "o": [], "p": []})["o"].append(o)
    for p in d["pros"]:
        z = (p.get("extra") or {}).get("zona") or "?"
        by_zone.setdefault(z.strip().lower(), {"z": z, "o": [], "p": []})["p"].append(p)
    zones = "".join(f"<div class='card' style='padding:12px 14px'><b>{escape(g['z'])}</b><br><small class='muted'>Saloni</small><br>{'<br>'.join(escape((o.get('business') or '') + ' · ' + str((o.get('extra') or {}).get('telefono') or '')) for o in g['o']) or '<span class=muted>—</span>'}"
                    f"<br><small class='muted'>Professioniste</small><br>{'<br>'.join(escape(str((p.get('extra') or {}).get('nome') or '') + ' · ' + str((p.get('extra') or {}).get('telefono') or '')) for p in g['p']) or '<span class=muted>—</span>'}</div>"
                    for g in sorted(by_zone.values(), key=lambda g: -(len(g['o']) * len(g['p']))))
    lead_row = lambda l, who: (f"<tr><td>{str(l.get('at'))[:10]}</td><td><b>{escape(str((l.get('extra') or {}).get('nome') or ''))}</b>{('<br>' + escape(l.get('business') or '')) if who == 'o' else ''}</td>"  # noqa: E731
                               f"<td><a href='tel:{escape(str((l.get('extra') or {}).get('telefono') or ''))}'>{escape(str((l.get('extra') or {}).get('telefono') or ''))}</a><br>{escape(l.get('email') or '')}</td>"
                               f"<td>{escape(str((l.get('extra') or {}).get('zona') or ''))}</td><td>{escape(str((l.get('extra') or {}).get('specialita') or (l.get('extra') or {}).get('piva') or ''))}</td><td><small>{escape((l.get('answer') or '')[:120])}</small></td><td><small class='muted'>{escape(l.get('placement') or '')} · {escape(l.get('variant') or '')}</small></td></tr>")
    owners = "".join(lead_row(l, "o") for l in sorted(d["owners"], key=lambda x: str(x.get("at")), reverse=True))
    pros = "".join(lead_row(l, "p") for l in sorted(d["pros"], key=lambda x: str(x.get("at")), reverse=True))
    from app.services import guida as _g
    from app.services import matching as _m
    from app.services import social as _soc
    from zoneinfo import ZoneInfo as _Z

    def _srow(p: dict) -> str:
        when = p.get("when").astimezone(_Z("Europe/Rome")).strftime("%a %d/%m %H:%M") if p.get("when") else ""
        st = {"in_coda": "warn", "pubblicato": "ok", "saltato": "gray", "errore": "bad"}.get(p.get("status"), "gray")
        act = (f"<form method='post' action='{base}/pl/admin/social/{p['id']}' class='row' style='gap:6px'><button class='btn' name='op' value='now' style='padding:6px 12px'>Pubblica ora</button>"
               f"<button class='btn sec' name='op' value='skip' style='padding:6px 12px'>Salta</button></form>") if p.get("status") == "in_coda" else (f"<a href='https://facebook.com/{escape(str(p.get('fb_id') or ''))}' target='_blank'>vedi ↗</a>" if p.get("fb_id") else escape(p.get("error") or ""))
        return (f"<tr><td style='white-space:nowrap'>{when}</td><td>{escape(p.get('kind') or '')}<br><small class='muted'>{escape(p.get('audience') or '')}</small></td><td><b>{escape(p.get('headline') or '')}</b><br><small>{escape((p.get('text') or '')[:160])}…</small></td>"
                f"<td>{('<img src=' + chr(39) + escape(p['image_url']) + chr(39) + ' style=' + chr(39) + 'height:56px;border-radius:5px' + chr(39) + '>') if p.get('image_url') else ''}</td><td><span class='pill {st}'>{escape(p.get('status') or '')}</span></td><td>{act}</td></tr>")

    social_rows = "".join(_srow(p) for p in _soc.queue()[:30])

    buyers_rows = "".join(f"<tr><td>{str(b.get('created_at'))[:16]}</td><td><b>{escape(b.get('name') or '')}</b><br>{escape(b.get('email') or '')}<br>{escape(b.get('phone') or '')}</td><td>{escape(_g.CATALOG.get(b.get('slug'), {}).get('title', b.get('slug') or ''))}</td>"
                          f"<td>{_g.price_str(int(b.get('amount') or 0))}</td><td>{escape(b.get('utm') or 'diretto')}</td><td>{int(b.get('downloads') or 0)}</td><td>{int(b.get('steps_sent') or 0)}/3</td></tr>" for b in _g.buyers())

    def _mrow(m: dict) -> str:
        ok = "ok" if m.get("match") else "gray"
        wa = f"<a class='btn' style='padding:6px 12px;background:#25d366' href='{escape(m['wa_link'])}' target='_blank'>Invia</a>" if m.get("wa_link") else ""
        return (f"<tr><td><span class='pill {ok}'>{m.get('score')}</span><br><small class='muted'>{escape(m.get('specialty_fit') or '')}/{escape(m.get('zone_fit') or '')}</small></td>"
                f"<td><b>{escape(m.get('nome') or '')}</b><br>{escape(m.get('specialita') or '')}<br>{escape(m.get('telefono') or '')}</td><td>{escape(m.get('salone') or '')}<br>{escape(m.get('zona') or '')}</td>"
                f"<td><small>{escape(m.get('reason') or '')}</small></td><td><span class='pill {ok}'>{escape(m.get('status') or '')}</span></td><td>{wa}</td></tr>")

    matches = "".join(_mrow(m) for m in _m.all_matches())
    reqs = "".join(f"<tr><td>{str(r.get('at'))[:16]}</td><td><b>{escape(r.get('nome') or '')}</b><br>{escape(r.get('telefono') or '')}<br>{escape(r.get('email') or '')}</td><td>{escape(r.get('salone') or '')} · {escape(r.get('zona') or '')}</td><td>{escape(r.get('specialita') or '')}<br><small>{escape(r.get('messaggio') or '')}</small></td><td><span class='pill gray'>{escape(r.get('status') or '')}</span></td></tr>" for r in d["requests"])
    n_sub = sum(1 for x in d['listings'] if x.get('status') in ('in_verifica', 'online', 'rifiutato', 'chiuso'))
    n_on = sum(1 for x in d['listings'] if x.get('status') == 'online')
    n_wait = sum(1 for x in d['listings'] if x.get('status') == 'in_verifica')
    n_draft = sum(1 for x in d['listings'] if x.get('status') == 'bozza')
    calls = sum(int((x.get('clicks') or {}).get('call', 0)) + int((x.get('clicks') or {}).get('whatsapp', 0)) for x in d['listings'])
    kpi = lambda n, l: f"<div class='card' style='padding:12px 14px'><b style='font-size:26px;font-family:Fraunces,Georgia,serif'>{n}</b><br><span class='muted'>{l}</span></div>"  # noqa: E731
    body = f"""<div class='row' style='justify-content:space-between'><h1>Pannello Poltrona Libera</h1><a class='muted' href='{base}/pl/admin/logout'>esci</a></div>
<p class='muted' style='margin:0 0 14px'>Test esclusi ({escape(get_settings().pl_test_emails)}).</p>
<div class='grid' style='grid-template-columns:repeat(auto-fill,minmax(150px,1fr));margin-bottom:8px'>{kpi(len(d['owners']), 'saloni iscritti')}{kpi(n_sub, 'annunci inviati')}{kpi(n_wait, 'da approvare')}{kpi(n_on, 'online')}{kpi(n_draft, 'bozze non finite')}{kpi(len(d['pros']), 'professioniste iscritte')}{kpi(calls, 'tap su chiama / WhatsApp')}{kpi(len(_g.buyers()), 'guide vendute')}</div>
<p class='muted'><a href='{base}/pl/admin/export.csv?what=owners'>CSV saloni</a> · <a href='{base}/pl/admin/export.csv?what=pros'>CSV professioniste</a> · <a href='{base}/pl/admin/export.csv?what=listings'>CSV annunci</a> · <a href='{base}/pl/postazioni' target='_blank'>catalogo pubblico ↗</a></p>
<h2>Annunci</h2><div class='tbl'><table><thead><tr><th>Stato</th><th>Salone</th><th>Zona · giorni · prezzo</th><th>Cerca</th><th>Foto</th><th>Azioni</th></tr></thead><tbody>{rows or '<tr><td colspan=6 class=muted>nessun annuncio</td></tr>'}</tbody></table></div>
<h2>Pagina Facebook · coda dei post</h2><p class='muted' style='margin:0 0 8px'>3 post a settimana (mar/gio/sab 12:30) più un post per ogni annuncio approvato. Escono da soli; qui puoi saltarli o pubblicarli subito.</p>
<div class='tbl'><table><thead><tr><th>Quando</th><th>Tipo</th><th>Post</th><th>Immagine</th><th>Stato</th><th>Azioni</th></tr></thead><tbody>{social_rows or '<tr><td colspan=6 class=muted>coda vuota</td></tr>'}</tbody></table></div>
<h2>Guide vendute</h2><div class='tbl'><table><thead><tr><th>Quando</th><th>Acquirente</th><th>Guida</th><th>Importo</th><th>Provenienza</th><th>Download</th><th>Mail workflow</th></tr></thead><tbody>{buyers_rows or '<tr><td colspan=7 class=muted>nessuna vendita ancora</td></tr>'}</tbody></table></div>
<h2>Match automatici</h2><p class='muted' style='margin:0 0 8px'>Ogni annuncio online viene confrontato con ogni professionista iscritta (specialità prima, poi zona). Match ≥ 70: email alla professionista con il numero della titolare, e a te il link WhatsApp.</p>
<div class='tbl'><table><thead><tr><th>Punteggio</th><th>Professionista</th><th>Postazione</th><th>Perché</th><th>Stato</th><th>WhatsApp</th></tr></thead><tbody>{matches or '<tr><td colspan=6 class=muted>nessun confronto ancora</td></tr>'}</tbody></table></div>
<h2>Richieste di contatto</h2><div class='tbl'><table><thead><tr><th>Quando</th><th>Professionista</th><th>Per</th><th>Note</th><th>Stato</th></tr></thead><tbody>{reqs or '<tr><td colspan=5 class=muted>nessuna</td></tr>'}</tbody></table></div>
<h2>Match per zona</h2><div class='grid'>{zones}</div>
<h2>Saloni iscritti</h2><div class='tbl'><table><thead><tr><th>Data</th><th>Titolare · salone</th><th>Contatti</th><th>Zona</th><th>P.IVA</th><th>Risposta</th><th>Form</th></tr></thead><tbody>{owners}</tbody></table></div>
<h2>Professioniste iscritte</h2><div class='tbl'><table><thead><tr><th>Data</th><th>Nome</th><th>Contatti</th><th>Zona</th><th>Specialità</th><th>Risposta</th><th>Form</th></tr></thead><tbody>{pros}</tbody></table></div>"""
    return _page("Pannello", body, pixel="")


@router.post("/admin/social/{post_id}")
async def admin_social(post_id: str, request: Request):
    _auth(request)
    from app.services import jobs, social

    form = await request.form()
    if form.get("op") == "skip":
        social.set_status(post_id, "saltato")
    elif form.get("op") == "now":
        jobs.trigger("social_now", post_id)
    return RedirectResponse(f"{P.base()}/pl/admin", status_code=303)


@router.post("/admin/listing/{listing_id}/status")
async def admin_status(listing_id: str, request: Request):
    _auth(request)
    form = await request.form()
    if not P.set_status(listing_id, str(form.get("status") or ""), str(form.get("note") or "")):
        raise HTTPException(400, "non approvabile: annuncio incompleto (foto, prezzo, giorni…) o stato non valido")
    return RedirectResponse(f"{P.base()}/pl/admin", status_code=303)


@router.get("/admin/frizioni")
def frizioni(request: Request, token: str | None = None, days: int = 14):
    """Behaviour funnel per page (landings, sales pages, catalogue): what people reach, where they stop, what they click."""
    from app.auth import require_api
    from app.services import behaviour

    if not _logged_in(request):
        try:
            require_api(request.headers.get("x-api-token", "") or token or "")
        except Exception:
            raise HTTPException(401, "login o X-API-Token")
    return behaviour.report(days)


@router.get("/admin/export.csv")
def admin_export(request: Request, what: str = "owners", token: str | None = None):
    _auth(request)
    d = P.admin_data()
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    if what == "listings":
        cols = ["status", "salone", "titolare", "telefono", "email", "zona", "giorni", "prezzo", "incluso", "chi_cerchi", "descrizione", "photos", "created_at", "submitted_at"]
        w.writerow(cols)
        for li in d["listings"]:
            w.writerow([" ".join(li.get(c) or []) if c == "photos" else str(li.get(c) or "") for c in cols])
    else:
        rows = d["owners"] if what == "owners" else d["pros"]
        w.writerow(["data", "nome", "salone", "telefono", "email", "zona", "piva", "specialita", "risposta", "form", "variante"])
        for l in rows:
            e = l.get("extra") or {}
            w.writerow([str(l.get("at"))[:10], e.get("nome", ""), l.get("business", ""), e.get("telefono", ""), l.get("email", ""), e.get("zona", ""), e.get("piva", ""), e.get("specialita", ""), l.get("answer", ""), l.get("placement", ""), l.get("variant", "")])
    return Response(content="﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f"attachment; filename=poltrona_{what}.csv"})
