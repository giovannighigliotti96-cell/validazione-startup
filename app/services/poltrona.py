"""Poltrona Libera marketplace (v2: free on both sides).

Owners publish a listing themselves (magic link, no password), Giovanni approves it from /pl/admin, professionals browse
online listings anonymously and ask for the contact for free; Giovanni connects the two by hand. No money moves yet:
the test is (a) do owners complete a real listing, (b) do professionals ask for contacts.

Firestore: listings/{id}, contact_requests/{id}. Leads stay under problem_clusters/<cluster>/leads.
"""
from __future__ import annotations

import io
import logging
import re
import secrets
from datetime import timedelta
from html import escape

from app import db
from app.config import get_settings
from app.services import notify

log = logging.getLogger("poltrona")

OWNERS = "poltrona_libera_titolari"
PROS = "poltrona_libera_professioniste"
BRAND = "Poltrona Libera"
BUCKET = "poltrona-libera-foto"
STATUSES = ("bozza", "in_verifica", "online", "rifiutato", "chiuso")
REMINDERS_H = (1, 24, 72, 168)  # hours after the draft was created (the first one lands right away, at the next hourly run)


PHONE = "3925909721"


PARTICLES = {"de", "di", "da", "del", "della", "dello", "dei", "degli", "la", "lo", "le", "van", "von", "mc"}
TITLES = {"dott", "dottssa", "dott.ssa", "ssa", "sig", "sig.ra", "sigra", "dr", "dr.ssa"}


def first_name(full: str) -> str:
    """'De Maria Dina' -> 'Dina'; 'DOTT SSA BARBARA LIDIA CORLEONE' -> 'Barbara'; 'Annalisa cao' -> 'Annalisa'."""
    toks = [t for t in (full or "").replace(".", " ").split() if t.lower() not in TITLES]
    if not toks:
        return ""
    if toks[0].lower() in PARTICLES and len(toks) > 1:
        return toks[-1].title()
    return toks[0].title()


def hi(full: str) -> str:
    n = first_name(full)
    return f"Ciao {n}," if n else "Ciao,"


def base() -> str:
    return get_settings().public_base_url.rstrip("/")


def footer_html() -> str:
    """Shared footer: Giovanni's number (call/WhatsApp) and the entry point of the listing flow."""
    b = base()
    return (f"Hai dubbi o domande? Chiama o scrivi su WhatsApp a Giovanni: <a href='tel:+39{PHONE}'>392 590 9721</a> "
            f"<a href='https://wa.me/39{PHONE}?text=Ciao%20Giovanni%2C%20ho%20una%20domanda%20su%20Poltrona%20Libera' target='_blank' rel='noopener'>WhatsApp</a>"
            f"<span class='sep'>·</span><a href='{b}/lp/{OWNERS}#lista-hero'>Pubblica il tuo annuncio</a><span class='sep'>·</span><a href='{b}/pl/postazioni'>Postazioni disponibili</a>")


def _sender(subject: str, html: str, to: str) -> None:
    try:
        notify.send_email(subject, html, to=to, from_name=BRAND, reply_to=get_settings().notify_email_to)
    except Exception as e:  # noqa: BLE001
        log.error("email to %s failed: %s", to, e)


def _mail(paras: list[str]) -> str:
    """Paragraphs that contain markup are used as-is; plain ones are escaped and wrapped."""
    body = "".join(p if p.startswith("<") else (f"<p>{p}</p>" if "<" in p else f"<p>{escape(p)}</p>") for p in paras if p)
    return f"<div style='font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:600px;color:#1c1917;line-height:1.6'>{body}</div>"


# ----------------------------------------------------------------------------- listings
def create_draft(lead: dict, lead_id: str) -> dict:
    """One draft per owner lead; returns the existing one if the owner already has a listing."""
    client = db.get_db()
    existing = list(client.collection("listings").where("lead_id", "==", lead_id).limit(1).stream())
    if existing:
        return {"id": existing[0].id, **existing[0].to_dict()}
    ex = lead.get("extra") or {}
    doc = {"lead_id": lead_id, "token": secrets.token_urlsafe(18), "email": lead["email"], "salone": lead.get("business") or "",
           "titolare": ex.get("nome") or "", "telefono": ex.get("telefono") or "", "zona": ex.get("zona") or "",
           "giorni": "", "prezzo": "", "incluso": "", "chi_cerchi": "", "descrizione": "", "photos": [],
           "status": "bozza", "reminders_sent": 0, "created_at": db.now(), "updated_at": db.now()}
    ref = client.collection("listings").document()
    ref.set(doc)
    return {"id": ref.id, **doc}


def by_token(token: str) -> dict | None:
    if not token or len(token) < 10:
        return None
    found = list(db.get_db().collection("listings").where("token", "==", token).limit(1).stream())
    return {"id": found[0].id, **found[0].to_dict()} if found else None


def link(listing: dict) -> str:
    return f"{base()}/pl/annuncio/{listing['token']}"


def upload_photo(listing_id: str, data: bytes, idx: int) -> str | None:
    """Resize to max 1600px JPEG and store in the public bucket; returns the public URL."""
    from firebase_admin import storage as fb_storage
    from PIL import Image, ImageOps

    try:
        im = Image.open(io.BytesIO(data))
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((1600, 1600))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=82, optimize=True)
        name = f"{listing_id}/{idx}_{secrets.token_hex(4)}.jpg"
        db.get_db()  # makes sure the firebase app (and its credentials) is initialised
        blob = fb_storage.bucket(BUCKET).blob(name)
        blob.cache_control = "public, max-age=86400"
        blob.upload_from_string(out.getvalue(), content_type="image/jpeg")
        return f"https://storage.googleapis.com/{BUCKET}/{name}"
    except Exception as e:  # noqa: BLE001
        log.error("photo upload failed: %s", e)
        return None


def save(listing: dict, fields: dict, new_photos: list[bytes], submit: bool) -> dict:
    client = db.get_db()
    upd = {k: str(fields.get(k) or "").strip()[:600] for k in ("salone", "titolare", "telefono", "zona", "giorni", "prezzo", "incluso", "chi_cerchi", "descrizione", "instagram")}
    upd["instagram"] = upd["instagram"].strip().lstrip("@").split("/")[-1].split("?")[0][:60]
    photos = list(listing.get("photos") or [])
    for i, data in enumerate(new_photos):
        if len(photos) >= 6:
            break
        url = upload_photo(listing["id"], data, len(photos) + i)
        if url:
            photos.append(url)
    upd["photos"] = photos
    upd["updated_at"] = db.now()
    complete = all(upd[k] for k in ("salone", "telefono", "zona", "giorni", "prezzo")) and bool(photos)
    if submit and complete and listing.get("status") in ("bozza", "rifiutato"):
        upd["status"] = "in_verifica"
        upd["submitted_at"] = db.now()
    client.collection("listings").document(listing["id"]).update(upd)
    out = {**listing, **upd}
    if upd.get("status") == "in_verifica":
        _on_submitted(out)
    return out


def _on_submitted(listing: dict) -> None:
    _sender(f"Il tuo annuncio è in verifica — {BRAND}", _mail([
        hi(listing.get("titolare") or ""),
        f"abbiamo ricevuto l'annuncio della postazione di {listing.get('salone')} ({listing.get('zona')}). Lo controlliamo noi a mano: se tutto va bene entro qualche ora è online e le professioniste della tua zona potranno chiamarti.",
        "Nell'annuncio compaiono nome del salone, zona, giorni, prezzo, foto e il numero da chiamare: le professioniste ti chiamano direttamente.",
        f"Per modificare l'annuncio in qualsiasi momento: {link(listing)}",
        "A presto,<br>Giovanni Ghigliotti<br>" + BRAND]), listing["email"])
    rows = "".join(f"<tr><td style='padding:4px 10px;color:#64748b'>{escape(k)}</td><td style='padding:4px 10px'><b>{escape(str(listing.get(k) or ''))}</b></td></tr>"
                   for k in ("salone", "titolare", "telefono", "email", "zona", "giorni", "prezzo", "incluso", "chi_cerchi", "descrizione"))
    pics = "".join(f"<a href='{escape(u)}'><img src='{escape(u)}' style='height:90px;margin:4px;border-radius:6px'></a>" for u in listing.get("photos") or [])
    try:
        notify.send_email(f"🪑 {BRAND}: annuncio da approvare — {listing.get('salone')} ({listing.get('zona')})",
                          f"<div style='font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px'><table>{rows}</table><div>{pics}</div>"
                          f"<p><a href='{base()}/pl/admin'>Apri il pannello</a></p></div>")
    except Exception as e:  # noqa: BLE001
        log.error("admin notify failed: %s", e)


REQUIRED = (("salone", "nome del salone"), ("zona", "zona"), ("giorni", "giorni"), ("prezzo", "prezzo"), ("telefono", "telefono"), ("titolare", "nome della titolare"))


def missing(listing: dict) -> list[str]:
    """What still stops a listing from going online (the same rule the owner form applies)."""
    out = [label for k, label in REQUIRED if not (listing.get(k) or "").strip()]
    if not listing.get("photos"):
        out.append("foto")
    return out


def set_status(listing_id: str, status: str, note: str = "", quiet: bool = False) -> dict | None:
    if status not in STATUSES:
        return None
    ref = db.get_db().collection("listings").document(listing_id)
    snap = ref.get()
    if not snap.exists:
        return None
    listing = {"id": listing_id, **snap.to_dict()}
    if status == "online" and missing(listing):
        return None  # never publish an incomplete listing, whoever clicks
    upd = {"status": status, "updated_at": db.now(), "admin_note": note[:500]}
    if status == "online":
        upd["approved_at"] = db.now()
    ref.update(upd)
    listing.update(upd)
    if status == "online":
        from app.services import jobs, social

        jobs.trigger("match_listing", listing_id)
        try:
            social.enqueue_listing(listing)
        except Exception as e:  # noqa: BLE001
            log.error("social enqueue: %s", e)
    if quiet:
        return listing
    if status == "online":
        _sender(f"Annuncio approvato: sei online — {BRAND}", _mail([
            hi(listing.get("titolare") or ""),
            f"il tuo annuncio è stato approvato ed è online: {base()}/pl/postazioni",
            "Da adesso le professioniste che lo vedono ti chiamano direttamente al numero che hai indicato, e vi mettete d'accordo tra di voi. Pubblicare e ricevere chiamate non costa nulla.",
            f"Per modificare o mettere in pausa l'annuncio: {link(listing)}",
            "A presto,<br>Giovanni Ghigliotti<br>" + BRAND]), listing["email"])
    elif status == "rifiutato":
        _sender(f"Il tuo annuncio: serve una modifica — {BRAND}", _mail([
            hi(listing.get("titolare") or ""),
            "abbiamo guardato l'annuncio e prima di pubblicarlo serve una modifica:", f"<p><b>{escape(note or 'aggiungi qualche dettaglio in più (foto, giorni, prezzo).')}</b></p>",
            f"Lo sistemi qui in un minuto: {link(listing)}", "A presto,<br>Giovanni Ghigliotti<br>" + BRAND]), listing["email"])
    return listing


def online_listings() -> list[dict]:
    items = [{"id": d.id, **d.to_dict()} for d in db.get_db().collection("listings").where("status", "==", "online").stream()]
    items.sort(key=lambda x: str(x.get("approved_at") or ""), reverse=True)
    return items


def public_card(listing: dict) -> dict:
    """Card for the landing rail and the catalogue: everything in the clear, the professional calls the owner directly."""
    tags = [t for t in (listing.get("zona"), listing.get("giorni")) if t][:2]
    if listing.get("chi_cerchi"):
        tags.append(listing["chi_cerchi"][:28])
    price = listing.get("prezzo") or ""
    per_day = bool(re.search(r"al giorno|/giorno|giornalier", price, re.I))  # some salons price per day, not per month
    m = re.search(r"\d[\d.]*", price)
    return {"photo_url": (listing.get("photos") or [None])[0], "tags": tags[:3], "title": f"{listing.get('salone')} · {listing.get('zona')}",
            "text": " · ".join(x for x in (listing.get("incluso"), listing.get("descrizione")) if x)[:180] or "Chiama la titolare per i dettagli.",
            "price": (m.group(0) + " €") if m else price[:24], "price_note": ("al giorno" if per_day else "al mese") if m else "",
            "note": f"Annuncio verificato · chiama {listing.get('titolare') or 'la titolare'}: {listing.get('telefono')}", "id": listing["id"],
            "telefono": listing.get("telefono"), "titolare": listing.get("titolare")}


def track_call(listing_id: str, kind: str) -> None:
    """A tap on 'Chiama' or 'WhatsApp' in the catalogue: the demand signal we measure instead of a paywall."""
    from google.cloud.firestore_v1 import Increment

    ref = db.get_db().collection("listings").document(listing_id)
    if ref.get().exists:
        ref.update({f"clicks.{'whatsapp' if kind == 'wa' else 'call'}": Increment(1), "last_click_at": db.now()})


# ----------------------------------------------------------------------------- reminders
def reminder_email(li: dict, sent: int) -> None:
    """One nudge for an unfinished listing; says exactly what is missing."""
    miss = missing(li)
    what = ", ".join(miss) if miss else "l'invio"
    subjects = ("Il tuo annuncio non è completo", "Non hai finito il tuo annuncio", "Ci sono professioniste che aspettano il tuo annuncio", "Ultimo promemoria: la tua postazione")
    subject = subjects[min(sent, len(subjects) - 1)]
    _sender(f"{subject} — {BRAND}", _mail([
        hi(li.get("titolare") or ""),
        f"l'annuncio della postazione di <b>{escape(li.get('salone') or 'del tuo salone')}</b> non è ancora online: manca <b>{escape(what)}</b>."
        + (" Basta una foto della postazione fatta col telefono." if miss == ["foto"] else " Ci vogliono due minuti."),
        f"<p style='margin:20px 0'><a href='{link(li)}' style='display:inline-block;background:#b5532c;color:#fff;padding:12px 20px;border-radius:999px;text-decoration:none;font-weight:700'>Completa l'annuncio</a></p>",
        "Le professioniste vedono solo gli annunci completi. Se preferisci, mandami la foto (e giorni e prezzo) su WhatsApp al 392 590 9721 e lo completo io per te.",
        "A presto,<br>Giovanni Ghigliotti<br>" + BRAND]), li["email"])


def send_reminders() -> int:
    """Hourly: owners who started a listing and did not send it get nudges at 1h, 24h, 72h and 7 days."""
    client = db.get_db()
    n = 0
    for d in client.collection("listings").where("status", "==", "bozza").stream():
        li = {"id": d.id, **d.to_dict()}
        if is_test(li.get("email")):
            continue
        sent = int(li.get("reminders_sent") or 0)
        if sent >= len(REMINDERS_H) or not li.get("created_at"):
            continue
        if db.now() - li["created_at"] < timedelta(hours=REMINDERS_H[sent]):
            continue
        reminder_email(li, sent)
        d.reference.update({"reminders_sent": sent + 1, "last_reminder_at": db.now()})
        n += 1
    return n


# ----------------------------------------------------------------------------- contact requests (free)
def request_contact(listing_id: str, form: dict) -> dict | None:
    client = db.get_db()
    snap = client.collection("listings").document(listing_id).get()
    if not snap.exists or snap.to_dict().get("status") != "online":
        return None
    li = {"id": listing_id, **snap.to_dict()}
    req = {"listing_id": listing_id, "zona": li.get("zona"), "salone": li.get("salone"), "nome": str(form.get("nome") or "")[:120],
           "telefono": str(form.get("telefono") or "")[:40], "email": str(form.get("email") or "").strip().lower()[:120],
           "specialita": str(form.get("specialita") or "")[:200], "messaggio": str(form.get("messaggio") or "")[:600], "status": "nuova", "at": db.now()}
    client.collection("contact_requests").document().set(req)
    # the professional also becomes a lead of the pros landing (same table Giovanni already uses)
    import hashlib

    if req["email"]:
        lead_id = hashlib.sha256(req["email"].encode()).hexdigest()[:20]
        client.collection(db.PROBLEM_CLUSTERS).document(PROS).collection("leads").document(lead_id).set(
            {"email": req["email"], "business": "", "variant": "cat", "placement": "catalogo", "answer": req["messaggio"],
             "extra": {"nome": req["nome"], "telefono": req["telefono"], "zona": req["zona"], "specialita": req["specialita"]}, "at": db.now()}, merge=True)
        _sender(f"Richiesta ricevuta — {BRAND}", _mail([
            hi(req["nome"]), f"abbiamo ricevuto la tua richiesta per la postazione a {li.get('zona')}. Entro 24 ore ti scriviamo con il nome del salone e il numero della titolare, e le diciamo che la contatterai tu.",
            "Non ti costa nulla. Come vi mettete d'accordo (giorni, orari, prezzo, tipo di collaborazione) lo decidete tra di voi.",
            f"Nel frattempo puoi guardare le altre postazioni: {base()}/pl/postazioni", "A presto,<br>Giovanni Ghigliotti<br>" + BRAND]), req["email"])
    try:
        notify.send_email(f"📞 {BRAND}: richiesta contatto — {req['nome']} → {li.get('salone')} ({li.get('zona')})",
                          f"<div style='font-family:-apple-system,Segoe UI,Roboto,sans-serif'><p><b>{escape(req['nome'])}</b> · {escape(req['telefono'])} · {escape(req['email'])}<br>{escape(req['specialita'])}<br>{escape(req['messaggio'])}</p>"
                          f"<p>Salone: <b>{escape(li.get('salone') or '')}</b> · {escape(li.get('titolare') or '')} · {escape(li.get('telefono') or '')} · {escape(li.get('email') or '')}</p>"
                          f"<p><a href='{base()}/pl/admin'>Pannello</a></p></div>")
    except Exception as e:  # noqa: BLE001
        log.error("contact notify failed: %s", e)
    return req


# ----------------------------------------------------------------------------- admin data
def is_test(email: str | None) -> bool:
    e = (email or "").lower()
    return any(t and (e == t or e.endswith("@" + t) or e.endswith(t)) for t in (x.strip().lower() for x in get_settings().pl_test_emails.split(",")))


def admin_data() -> dict:
    client = db.get_db()
    listings = [{"id": d.id, **d.to_dict()} for d in client.collection("listings").stream() if not is_test(d.to_dict().get("email"))]
    listings.sort(key=lambda x: ({"in_verifica": 0, "online": 1, "bozza": 2, "rifiutato": 3, "chiuso": 4}.get(x.get("status"), 9), str(x.get("updated_at") or "")))
    owners = [{"id": d.id, **d.to_dict()} for d in client.collection(db.PROBLEM_CLUSTERS).document(OWNERS).collection("leads").stream() if not is_test(d.to_dict().get("email"))]
    pros = [{"id": d.id, **d.to_dict()} for d in client.collection(db.PROBLEM_CLUSTERS).document(PROS).collection("leads").stream() if not is_test(d.to_dict().get("email"))]
    reqs = [{"id": d.id, **d.to_dict()} for d in client.collection("contact_requests").stream() if not is_test(d.to_dict().get("email"))]
    reqs.sort(key=lambda x: str(x.get("at") or ""), reverse=True)
    return {"listings": listings, "owners": owners, "pros": pros, "requests": reqs}
