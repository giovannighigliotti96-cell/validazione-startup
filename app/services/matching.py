"""Poltrona Libera matching: reads what a listing asks for and what a professional does, and decides if they fit.

Runs when a listing goes online (against every registered professional) and when a professional registers
(against every online listing). A match = email to the professional with the listing and the owner's number
("chiamala oggi"), plus an email to Giovanni with a one-tap WhatsApp link to nudge her personally.
The judgement is made by the strong LLM with an explicit rubric (specialty first, then zone), never by keyword luck:
a nail technician does not get a hairdresser's chair and vice versa.

Firestore: matches/{listing_id}_{lead_id} = {score, reason, status, notified_at}.
"""
from __future__ import annotations

import logging
from html import escape
from urllib.parse import quote

from pydantic import BaseModel

from app import db
from app.config import get_settings
from app.services import notify
from app.services import poltrona as P
from app.services.analysis import llm_json

log = logging.getLogger("matching")
THRESHOLD = 70


class Verdict(BaseModel):
    match: bool
    score: int
    reason: str
    specialty_fit: str  # yes|partial|no
    zone_fit: str  # yes|partial|no|unknown


PROMPT = """Sei l'assistente di Poltrona Libera (Milano): decidi se una professionista è adatta a una postazione in affitto.

POSTAZIONE (annuncio del salone)
- salone: {salone} · zona: {zona}
- cosa cerca la titolare: {chi_cerchi}
- cosa è incluso: {incluso}
- descrizione: {descrizione}
- giorni: {giorni} · prezzo: {prezzo}

PROFESSIONISTA (iscrizione)
- nome: {nome}
- cosa fa: {specialita}
- zona che vuole: {pzona}
- come lavora oggi / cosa cerca: {answer}

REGOLE
1. Prima la specialità: il mestiere deve corrispondere a ciò che il salone cerca. Categorie: parrucchiera/o (taglio, colore, piega, schiariture, armocromia capelli), barbiere (uomo, barba), onicotecnica/manicure/pedicure, estetista (cabina, trattamenti viso/corpo, ceretta), make-up/ciglia/sopracciglia. Se il salone cerca "estetista - onicotecnica" una parrucchiera NON è adatta (specialty_fit=no) anche se la zona è perfetta. Se il salone non specifica chi cerca, assumi che cerchi il mestiere coerente con "cosa è incluso" (piano manicure = mani; lavatesta/postazione = capelli).
2. Poi la zona: usa la geografia di Milano e hinterland. "Centro e dintorni" copre Porta Romana, Cinque Giornate, Duomo, Brera, Porta Venezia, Navigli vicini. "Nord/est" copre NoLo, Bicocca, Lambrate, Città Studi, Sesto. Rozzano, San Donato, Brugherio, Legnano sono comuni fuori Milano: compatibili solo con zone vicine. Se la zona è vaga o "Milano" in generale, zone_fit=partial. Se la professionista scrive solo "Milano" e la postazione è in città, va bene.
3. score 0-100: 90+ specialità e zona perfette; 70-89 specialità giusta e zona compatibile o non specificata; sotto 70 non è un match. match=true solo se score>=70 e specialty_fit != "no".
4. reason: una frase in italiano, concreta, che potrei incollare in una email alla professionista (es. "cerca proprio un'onicotecnica e Porta Romana è a due passi dal centro che hai indicato").

Rispondi solo con il JSON richiesto."""


def _fmt(listing: dict, lead: dict) -> str:
    e = lead.get("extra") or {}
    return PROMPT.format(salone=listing.get("salone") or "", zona=listing.get("zona") or "", chi_cerchi=listing.get("chi_cerchi") or "(non specificato)",
                         incluso=listing.get("incluso") or "", descrizione=listing.get("descrizione") or "", giorni=listing.get("giorni") or "", prezzo=listing.get("prezzo") or "",
                         nome=e.get("nome") or "", specialita=e.get("specialita") or "(non indicato)", pzona=e.get("zona") or "(non indicata)", answer=lead.get("answer") or "")


def evaluate(listing: dict, lead: dict) -> Verdict | None:
    try:
        data = llm_json(_fmt(listing, lead), Verdict, strong=True, temperature=0.1)
        v = Verdict(**data)
        v.score = max(0, min(100, int(v.score)))
        if v.specialty_fit == "no":
            v.match = False
        return v
    except Exception as ex:  # noqa: BLE001
        log.error("evaluate %s / %s: %s", listing.get("salone"), lead.get("email"), ex)
        return None


PARTICLES = {"de", "di", "da", "del", "della", "dello", "dei", "degli", "la", "lo", "le", "van", "von", "mc", "d'"}


def first_name(full: str) -> str:
    """'De Maria Dina' -> 'Dina'; 'Gessica' -> 'Gessica'; 'DOTT SSA BARBARA LIDIA CORLEONE' -> 'Barbara'."""
    toks = [t for t in (full or "").replace(".", " ").split() if t.lower() not in ("dott", "dottssa", "dott.ssa", "ssa", "sig", "sig.ra", "sigra")]
    if not toks:
        return ""
    if toks[0].lower() in PARTICLES and len(toks) > 1:
        return toks[-1].title()
    return toks[0].title()


def _tel(phone: str) -> str:
    d = "".join(ch for ch in (phone or "") if ch.isdigit())
    return "+" + (d if d.startswith("39") and len(d) > 10 else "39" + d.lstrip("0"))


def _wa(phone: str, text: str) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit() or ch == "+")
    if digits.startswith("+"):
        digits = digits[1:]
    elif digits.startswith("00"):
        digits = digits[2:]
    elif not digits.startswith("39"):
        digits = "39" + digits.lstrip("0")
    return f"https://wa.me/{digits}?text={quote(text)}"


def _notify(listing: dict, lead: dict, v: Verdict) -> None:
    e = lead.get("extra") or {}
    first = first_name(e.get("nome") or "")
    base = P.base()
    owner_wa = _wa(listing.get("telefono") or "", f"Ciao {listing.get('titolare') or ''}, ho visto la postazione di {listing.get('salone')} su Poltrona Libera e mi interessa")
    photo = (listing.get("photos") or [None])[0]
    pro_paras = [
        f"Ciao {first}," if first else "Ciao,",
        f"abbiamo trovato una postazione che fa al caso tuo: <b>{escape(listing.get('salone') or '')}</b>, a <b>{escape(listing.get('zona') or '')}</b>. {escape(v.reason)}",
        (f"<p><a href='{escape(photo)}'><img src='{escape(photo)}' style='max-width:100%;border-radius:10px'></a></p>" if photo else ""),
        f"<ul><li><b>Giorni</b>: {escape(listing.get('giorni') or '')}</li><li><b>Prezzo</b>: {escape(listing.get('prezzo') or '')}</li><li><b>Incluso</b>: {escape(listing.get('incluso') or '-')}</li><li><b>Cerca</b>: {escape(listing.get('chi_cerchi') or '-')}</li></ul>",
        f"La titolare è <b>{escape(listing.get('titolare') or '')}</b>: chiamala oggi al <a href='tel:{_tel(listing.get('telefono') or '')}'><b>{escape(listing.get('telefono') or '')}</b></a> "
        f"oppure <a href='{owner_wa}'>scrivile su WhatsApp</a>. È l'unica postazione di questo tipo online adesso e la titolare sceglie la prima che la convince: non aspettare.",
        "Come vi accordate (giorni, orari, prezzo, prova) lo decidete tra di voi. Se vuoi un consiglio prima di chiamare, rispondi a questa email o scrivimi su WhatsApp al 392 590 9721.",
        "In bocca al lupo,<br>Giovanni Ghigliotti<br>Poltrona Libera",
    ]
    if lead.get("email"):
        try:
            notify.send_email(f"Trovata una postazione per te a {listing.get('zona')} — Poltrona Libera", P._mail([p for p in pro_paras if p]), to=lead["email"], from_name=P.BRAND, reply_to=get_settings().notify_email_to)
        except Exception as ex:  # noqa: BLE001
            log.error("match email to pro failed: %s", ex)
    # the owner too: a professional who fits has just been sent her number
    owner_first = first_name(listing.get("titolare") or "")
    owner_paras = [
        f"Ciao {owner_first}," if owner_first else "Ciao,",
        f"buone notizie: una professionista in linea con il tuo annuncio di <b>{escape(listing.get('salone') or '')}</b> si è iscritta su Poltrona Libera e le abbiamo appena mandato il tuo numero.",
        f"<ul><li><b>{escape(e.get('nome') or '')}</b></li><li>Cosa fa: {escape(e.get('specialita') or '-')}</li><li>Zona: {escape(e.get('zona') or '-')}</li>"
        + (f"<li>Come lavora oggi: {escape(lead.get('answer') or '')}</li>" if lead.get("answer") else "") + "</ul>",
        f"Perché è adatta: {escape(v.reason)}",
        f"Probabilmente ti chiamerà lei. Se preferisci anticiparla, il suo numero è <a href='tel:{_tel(e.get('telefono') or '')}'><b>{escape(e.get('telefono') or '')}</b></a>"
        + (f" oppure <a href='{_wa(e.get('telefono') or '', 'Ciao ' + first + ', sono ' + (listing.get('titolare') or '') + ' di ' + (listing.get('salone') or '') + ': ho visto su Poltrona Libera che cerchi una postazione')}'>scrivile su WhatsApp</a>." if e.get("telefono") else "."),
        "Come vi accordate (giorni, orari, prezzo, prova) lo decidete tra di voi. Per qualsiasi dubbio scrivimi su WhatsApp al 392 590 9721.",
        "A presto,<br>Giovanni Ghigliotti<br>Poltrona Libera",
    ]
    if listing.get("email"):
        try:
            notify.send_email(f"Una professionista per la tua postazione — Poltrona Libera", P._mail(owner_paras), to=listing["email"], from_name=P.BRAND, reply_to=get_settings().notify_email_to)
        except Exception as ex:  # noqa: BLE001
            log.error("match email to owner failed: %s", ex)
    wa_text = (f"Ciao {first}, sono Giovanni di Poltrona Libera. È online una postazione che fa al caso tuo: {listing.get('salone')} a {listing.get('zona')} "
               f"({listing.get('giorni')}, {listing.get('prezzo')}). {v.reason} Chiama {listing.get('titolare')} al {listing.get('telefono')}: è l'unica di questo tipo online adesso. "
               f"Dettagli e foto: {base}/pl/postazioni")
    try:
        notify.send_email(f"🎯 Match {v.score}: {e.get('nome')} ↔ {listing.get('salone')} ({listing.get('zona')})",
                          f"<div style='font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;line-height:1.6'>"
                          f"<p><b>{escape(e.get('nome') or '')}</b> · {escape(e.get('specialita') or '')} · zona {escape(e.get('zona') or '')} · {escape(e.get('telefono') or '')} · {escape(lead.get('email') or '')}<br>"
                          f"<i>{escape(lead.get('answer') or '')}</i></p><p><b>{escape(listing.get('salone') or '')}</b> ({escape(listing.get('zona') or '')}) cerca: {escape(listing.get('chi_cerchi') or '')}</p>"
                          f"<p>Punteggio {v.score} · specialità {v.specialty_fit} · zona {v.zone_fit}<br>{escape(v.reason)}</p>"
                          f"<p>Email alla professionista: inviata.</p><p><a href='{_wa(e.get('telefono') or '', wa_text)}' style='display:inline-block;background:#25d366;color:#fff;padding:12px 18px;border-radius:999px;text-decoration:none;font-weight:700'>Mandale il WhatsApp (1 tap)</a></p>"
                          f"<p><a href='{base}/pl/admin'>Pannello</a></p></div>")
    except Exception as ex:  # noqa: BLE001
        log.error("match email to founder failed: %s", ex)


def _consider(listing: dict, lead_id: str, lead: dict) -> dict | None:
    if P.is_test(lead.get("email")) or listing.get("status") != "online":
        return None
    client = db.get_db()
    mid = f"{listing['id']}_{lead_id}"
    ref = client.collection("matches").document(mid)
    if ref.get().exists:
        return None
    v = evaluate(listing, lead)
    if v is None:
        return None
    e = lead.get("extra") or {}
    doc = {"listing_id": listing["id"], "lead_id": lead_id, "salone": listing.get("salone"), "zona": listing.get("zona"), "nome": e.get("nome"),
           "telefono": e.get("telefono"), "email": lead.get("email"), "specialita": e.get("specialita"), "score": v.score, "match": v.match,
           "reason": v.reason, "specialty_fit": v.specialty_fit, "zone_fit": v.zone_fit, "status": "notificata" if v.match else "scartata",
           "wa_link": _wa(e.get("telefono") or "", f"Ciao {first_name(e.get('nome') or '')}, sono Giovanni di Poltrona Libera: è online una postazione per te, {listing.get('salone')} a {listing.get('zona')}. Chiama {listing.get('titolare')} al {listing.get('telefono')}. Dettagli: {P.base()}/pl/postazioni") if v.match else "",
           "created_at": db.now()}
    ref.set(doc)
    if v.match:
        _notify(listing, lead, v)
        ref.update({"notified_at": db.now()})
    return doc


def match_listing(listing: dict) -> list[dict]:
    """A listing went online: check every registered professional."""
    out = []
    for d in db.get_db().collection(db.PROBLEM_CLUSTERS).document(P.PROS).collection("leads").stream():
        r = _consider(listing, d.id, d.to_dict())
        if r:
            out.append(r)
    log.info("match_listing %s: %s evaluated, %s matches", listing.get("salone"), len(out), sum(1 for r in out if r["match"]))
    return out


def match_lead(lead_id: str, lead: dict) -> list[dict]:
    """A professional registered: check every online listing."""
    out = []
    for li in P.online_listings():
        r = _consider(li, lead_id, lead)
        if r:
            out.append(r)
    log.info("match_lead %s: %s evaluated, %s matches", lead.get("email"), len(out), sum(1 for r in out if r["match"]))
    return out


def all_matches() -> list[dict]:
    items = [{"id": d.id, **d.to_dict()} for d in db.get_db().collection("matches").stream()]
    items.sort(key=lambda x: (not x.get("match"), -int(x.get("score") or 0)))
    return items
