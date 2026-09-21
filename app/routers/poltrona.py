"""Poltrona Libera pages: owner listing form (magic link), public catalogue with free contact requests, admin panel."""
from __future__ import annotations

import csv
import io
from html import escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import db
from app.config import get_settings
from app.services import poltrona as P

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
@media(max-width:600px){h1{font-size:25px}}</style>"""


def _top(base: str) -> str:
    return f"<div class='top'><div class='w'><a href='{base}/pl/postazioni' style='display:flex;align-items:center;gap:12px'><img src='{base}/static/poltrona/logo_512.png' alt=''><b>Poltrona Libera</b></a></div></div>"


def _pixel_html(event: str) -> str:
    from app.routers.landing import _pixel

    return _pixel(event)


def _page(title: str, body: str, pixel: str = "PageView", desc: str = "") -> HTMLResponse:
    base = P.base()
    return HTMLResponse(f"<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{escape(title)} — Poltrona Libera</title>"
                        f"<meta name='description' content='{escape(desc)}'>{CSS}{_pixel_html(pixel)}</head><body>{_top(base)}<main class='w'>{body}</main>"
                        f"<footer class='w muted' style='padding-bottom:30px'>Poltrona Libera · Milano · <a href='{base}/lp/{P.OWNERS}/privacy' style='color:inherit'>Privacy</a></footer></body></html>")


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
<p class='lead'>Gratis. Due minuti. Le professioniste vedono zona, giorni, prezzo, cosa è incluso e le foto, e chiedono a noi il tuo contatto: il telefono lo diamo solo a loro.</p>
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
<p class='muted' style='margin:0 0 6px'>Almeno una foto della postazione o del salone. Senza foto le professioniste non chiedono il contatto.</p>
<div class='photos'>{photos}</div>
<input type='file' id='foto' name='foto' accept='image/*' multiple>
<h2>4 · Contatto</h2>
<label for='titolare'>Il tuo nome</label><input id='titolare' name='titolare' value='{v("titolare")}' required>
<label for='telefono'>Numero che deve chiamare la professionista <small>lo diamo solo a chi chiede il contatto</small></label><input id='telefono' name='telefono' type='tel' value='{v("telefono")}' required>
<div class='row' style='margin-top:22px'><button class='btn' type='submit' name='submit' value='1'>{"Salva le modifiche" if status == "online" else "Pubblica l'annuncio"}</button><button class='btn sec' type='submit' name='submit' value='0'>Salva e finisci dopo</button>
{"<button class='btn sec' type='submit' name='submit' value='pausa'>Metti in pausa</button>" if status == "online" else "<button class='btn sec' type='submit' name='submit' value='riattiva'>Riattiva l'annuncio</button>" if status == "chiuso" else ""}</div>
<p class='muted' style='margin-top:12px'>Inviando accetti che il tuo contatto venga dato alle professioniste che lo richiedono. Gli accordi tra te e la professionista sono di vostra esclusiva competenza.</p>
</form>"""


@router.get("/annuncio/{token}", response_class=HTMLResponse)
def annuncio(token: str, saved: int = 0, nuovo: int = 0):
    li = P.by_token(token)
    if not li:
        raise HTTPException(404, "link non valido")
    return _page("Pubblica la tua postazione", _form_html(li, bool(saved), P.base()), pixel="Lead" if nuovo else "PageView")


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
    P.save(li, {k: form.get(k) for k in ("salone", "titolare", "telefono", "zona", "giorni", "prezzo", "incluso", "chi_cerchi", "descrizione")}, photos, submit)
    return RedirectResponse(f"{P.base()}/pl/annuncio/{token}?saved=1", status_code=303)


# ----------------------------------------------------------------------------- public catalogue
def _card(lp: dict, base: str, real: bool) -> str:
    tags = "".join(f"<span class='tag'>{escape(x)}</span>" for x in lp.get("tags", []))
    ph = f"<div class='ph' style=\"background-image:url('{escape(lp['photo_url'])}')\"></div>" if lp.get("photo_url") else "<div class='ph'></div>"
    cta = (f"<button class='btn' style='margin-top:10px' onclick=\"ask('{escape(lp['id'])}','{escape(lp.get('tags', [''])[0])}')\">Chiedi il contatto · gratis</button>" if real
           else f"<a class='btn sec' style='margin-top:10px' href='{base}/lp/{P.PROS}#lista'>Registrati: ti avvisiamo noi</a>")
    return (f"<div class='listing'>{ph}<div class='body'>{tags and '<div>' + tags + '</div>'}<h3>{escape(lp.get('title') or '')}</h3><p>{escape(lp.get('text') or '')}</p>"
            f"<div class='price'>{escape(lp.get('price') or '')}<span> {escape(lp.get('price_note') or '')}</span></div><div class='note'>{escape(lp.get('note') or '')}</div>{cta}</div></div>")


@router.get("/postazioni", response_class=HTMLResponse)
def postazioni():
    base = P.base()
    real = [P.public_card(x) for x in P.online_listings()]
    offer = (db.get(db.OPPORTUNITY_SCORING, P.PROS) or {}).get("offer") or {}
    examples = offer.get("listings") or []
    real_html = "".join(_card(x, base, True) for x in real)
    ex_html = "".join(_card(x, base, False) for x in examples)
    intro = (f"<p class='lead'>{len(real)} postazion{'e' if len(real) == 1 else 'i'} verificat{'a' if len(real) == 1 else 'e'} a Milano. Guardi gratis; quando ne trovi una che ti interessa chiedi il contatto e ti scriviamo noi con nome e telefono della titolare. Poi vi mettete d'accordo tra di voi."
             if real else "<p class='lead'>I primi saloni stanno pubblicando le loro postazioni. Registrati gratis: ti avvisiamo appena c'è una postazione nella tua zona.</p>")
    body = f"""<h1>Postazioni disponibili a Milano</h1>{intro}
{('<div class="grid">' + real_html + '</div>') if real else ''}
<h2>{'Altri esempi di annuncio' if real else 'Così appaiono gli annunci'}</h2><p class='muted' style='margin:0 0 12px'>Esempi con dati indicativi e foto di saloni reali: mostrano cosa vedrai. Non sono saloni iscritti.</p>
<div class='grid'>{ex_html}</div>
<div class='card' style='margin-top:28px'><h2 style='margin-top:0'>Non trovi la tua zona?</h2><p class='muted'>Registrati gratis e ti scriviamo appena un salone della tua zona pubblica una postazione.</p><a class='btn' href='{base}/lp/{P.PROS}#lista'>Registrati gratis</a></div>
<dialog id='dlg'><form method='post' class='in' id='askf'><h2 style='margin:0 0 4px'>Chiedi il contatto</h2><p class='muted' id='dlgz' style='margin:0 0 6px'></p>
<label for='a_nome'>Nome e cognome</label><input id='a_nome' name='nome' required><label for='a_tel'>Cellulare</label><input id='a_tel' name='telefono' type='tel' required>
<label for='a_email'>Email</label><input id='a_email' name='email' type='email' required><label for='a_spec'>Cosa fai <small>es. colore e taglio donna, barber…</small></label><input id='a_spec' name='specialita'>
<label for='a_msg'>Un messaggio per la titolare <small>facoltativo</small></label><textarea id='a_msg' name='messaggio' rows='2'></textarea>
<div class='row' style='margin-top:16px'><button class='btn' type='submit'>Invia · gratis</button><button class='btn sec' type='button' onclick="document.getElementById('dlg').close()">Annulla</button></div>
<p class='muted' style='margin-top:10px'>Entro 24 ore ricevi nome e telefono della titolare via email.</p></form></dialog>
<script>function ask(id,z){{var f=document.getElementById('askf');f.action='{base}/pl/contatto/'+id;document.getElementById('dlgz').textContent='Postazione a '+z;document.getElementById('dlg').showModal();try{{fbq('track','ViewContent')}}catch(e){{}}}}</script>"""
    return _page("Postazioni disponibili a Milano", body, desc="Postazioni in affitto in saloni di Milano: guardi gratis, chiedi il contatto della titolare.")


@router.post("/contatto/{listing_id}")
async def contatto(listing_id: str, request: Request):
    form = await request.form()
    req = P.request_contact(listing_id, dict(form))
    if not req:
        raise HTTPException(404, "annuncio non disponibile")
    body = f"<h1>Richiesta inviata</h1><div class='ok-box'>Grazie {escape(req['nome'])}: entro 24 ore ti scriviamo a {escape(req['email'])} con nome e telefono della titolare.</div><p style='margin-top:18px'><a class='btn sec' href='{P.base()}/pl/postazioni'>Torna alle postazioni</a></p>"
    return _page("Richiesta inviata", body, pixel="Lead")


# ----------------------------------------------------------------------------- admin
def _auth(request: Request, token: str | None) -> Response | None:
    expected = get_settings().api_token
    tok = token or request.cookies.get("pl_admin")
    if expected and tok != expected:
        raise HTTPException(401, "token mancante: apri /pl/admin?token=API_TOKEN")
    return None


def _set_cookie(resp: Response, token: str | None) -> Response:
    if token:
        resp.set_cookie("pl_admin", token, max_age=60 * 60 * 24 * 90, httponly=True, samesite="lax")
    return resp


@router.get("/admin", response_class=HTMLResponse)
def admin(request: Request, token: str | None = None):
    _auth(request, token)
    d = P.admin_data()
    base = P.base()
    pill = {"in_verifica": "warn", "online": "ok", "bozza": "gray", "rifiutato": "bad", "chiuso": "gray"}
    rows = ""
    for li in d["listings"]:
        pics = "".join(f"<a href='{escape(u)}' target='_blank'><img src='{escape(u)}' style='height:44px;border-radius:5px;margin-right:3px'></a>" for u in (li.get("photos") or [])[:3])
        act = (f"<form method='post' action='{base}/pl/admin/listing/{li['id']}/status' class='row' style='gap:6px'>"
               f"<button class='btn' name='status' value='online' style='padding:6px 12px'>Approva</button>"
               f"<input name='note' placeholder='motivo (se rifiuti)' style='width:150px;padding:6px 8px'><button class='btn sec' name='status' value='rifiutato' style='padding:6px 12px'>Rifiuta</button>"
               f"<button class='btn sec' name='status' value='chiuso' style='padding:6px 12px'>Chiudi</button></form>")
        rows += (f"<tr><td><span class='pill {pill.get(li.get('status'), 'gray')}'>{escape(li.get('status') or '')}</span><br><small class='muted'>{str(li.get('updated_at'))[:16]}</small></td>"
                 f"<td><b>{escape(li.get('salone') or '')}</b><br>{escape(li.get('titolare') or '')}<br><a href='tel:{escape(li.get('telefono') or '')}'>{escape(li.get('telefono') or '')}</a><br>{escape(li.get('email') or '')}</td>"
                 f"<td>{escape(li.get('zona') or '')}<br><small>{escape(li.get('giorni') or '')}</small><br><b>{escape(li.get('prezzo') or '')}</b></td>"
                 f"<td>{escape(li.get('chi_cerchi') or '')}<br><small class='muted'>{escape((li.get('incluso') or '')[:80])}</small></td><td>{pics}</td>"
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
    reqs = "".join(f"<tr><td>{str(r.get('at'))[:16]}</td><td><b>{escape(r.get('nome') or '')}</b><br>{escape(r.get('telefono') or '')}<br>{escape(r.get('email') or '')}</td><td>{escape(r.get('salone') or '')} · {escape(r.get('zona') or '')}</td><td>{escape(r.get('specialita') or '')}<br><small>{escape(r.get('messaggio') or '')}</small></td><td><span class='pill gray'>{escape(r.get('status') or '')}</span></td></tr>" for r in d["requests"])
    body = f"""<h1>Pannello Poltrona Libera</h1>
<p class='lead'>Annunci {len(d['listings'])} · online {sum(1 for x in d['listings'] if x.get('status') == 'online')} · da approvare {sum(1 for x in d['listings'] if x.get('status') == 'in_verifica')} · saloni iscritti {len(d['owners'])} · professioniste {len(d['pros'])} · richieste contatto {len(d['requests'])}
<br><a href='{base}/pl/admin/export.csv?what=owners'>CSV saloni</a> · <a href='{base}/pl/admin/export.csv?what=pros'>CSV professioniste</a> · <a href='{base}/pl/admin/export.csv?what=listings'>CSV annunci</a> · <a href='{base}/pl/postazioni' target='_blank'>catalogo pubblico ↗</a></p>
<h2>Annunci</h2><div class='tbl'><table><thead><tr><th>Stato</th><th>Salone</th><th>Zona · giorni · prezzo</th><th>Cerca</th><th>Foto</th><th>Azioni</th></tr></thead><tbody>{rows or '<tr><td colspan=6 class=muted>nessun annuncio</td></tr>'}</tbody></table></div>
<h2>Richieste di contatto</h2><div class='tbl'><table><thead><tr><th>Quando</th><th>Professionista</th><th>Per</th><th>Note</th><th>Stato</th></tr></thead><tbody>{reqs or '<tr><td colspan=5 class=muted>nessuna</td></tr>'}</tbody></table></div>
<h2>Match per zona</h2><div class='grid'>{zones}</div>
<h2>Saloni iscritti</h2><div class='tbl'><table><thead><tr><th>Data</th><th>Titolare · salone</th><th>Contatti</th><th>Zona</th><th>P.IVA</th><th>Risposta</th><th>Form</th></tr></thead><tbody>{owners}</tbody></table></div>
<h2>Professioniste iscritte</h2><div class='tbl'><table><thead><tr><th>Data</th><th>Nome</th><th>Contatti</th><th>Zona</th><th>Specialità</th><th>Risposta</th><th>Form</th></tr></thead><tbody>{pros}</tbody></table></div>"""
    return _set_cookie(_page("Pannello", body, pixel=""), token)


@router.post("/admin/listing/{listing_id}/status")
async def admin_status(listing_id: str, request: Request):
    _auth(request, None)
    form = await request.form()
    if not P.set_status(listing_id, str(form.get("status") or ""), str(form.get("note") or "")):
        raise HTTPException(400, "stato non valido")
    return RedirectResponse(f"{P.base()}/pl/admin", status_code=303)


@router.get("/admin/export.csv")
def admin_export(request: Request, what: str = "owners", token: str | None = None):
    _auth(request, token)
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
