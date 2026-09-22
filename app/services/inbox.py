"""Comments and DMs on our own Facebook page and Instagram account: answer the frequent questions in Giovanni's
voice, forward everything else to him on WhatsApp/email. Never writes to people who did not write to us first.

social_inbox/{id}: platform, kind (comment|dm), from, text, reply, status (risposto|inoltrato|ignorato), at
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx

from app import db
from app.config import get_settings
from app.services import notify
from app.services import poltrona as P

log = logging.getLogger("inbox")
GRAPH = "https://graph.facebook.com/v21.0"
SITE = "https://poltronalibera.it"

# (regex, reply) — first match wins; written to sound like Giovanni, never pushy
RULES: list[tuple[str, str]] = [
    (r"\b(quanto costa|prezzo|costa|costi|a pagamento|gratis|gratuito)\b",
     "Per chi cerca una postazione è gratis: guardi gli annunci e chiami direttamente la titolare. Anche pubblicare la postazione, per i saloni, è gratis. Le trovi tutte su poltronalibera.it 🙂"),
    (r"\b(p\.?\s?iva|partita iva|fattur|contributi|inps|forfettario)\b",
     "Gli accordi li fate direttamente tu e il salone: noi vi mettiamo in contatto e non entriamo nella parte fiscale. Se vuoi ne parliamo, scrivimi pure in privato."),
    (r"\b(come funziona|come si fa|come fare|informazioni|info)\b",
     "Funziona così: i saloni pubblicano la postazione libera con zona, giorni, prezzo, foto e numero; tu guardi gli annunci su poltronalibera.it e chiami direttamente. Gratis per entrambi."),
    (r"\b(dove|zona|zone|quartier|milano|citt)\w*\b.*\b(postazion|poltron|salon)",
     "Per ora siamo su Milano e hinterland. Le postazioni online le vedi su poltronalibera.it: se non c'è la tua zona, registrati e ti avviso appena ne esce una vicina."),
    (r"\b(cerco|cerchi|cercate|disponibil)\w*\b.*\b(postazion|poltron|posto)\b",
     "Le postazioni disponibili sono su poltronalibera.it, con foto, giorni, prezzo e il numero della titolare: chiami tu, direttamente. Se non trovi la tua zona scrivimi, ti avviso appena esce."),
    (r"\b(ho un salone|sono titolare|affittare|affitto).*\b(poltron|postazion)\b",
     "Perfetto: pubblicare è gratis e ci vogliono cinque minuti (zona, giorni, prezzo, una foto e il numero). Da qui: poltronalibera.it — o scrivimi e lo pubblico io per te."),
    (r"\b(serve|serve un|contratto|contratti)\b",
     "Il contratto lo fate voi due: noi non entriamo nell'accordo. Sul sito, nelle guide, trovi i punti da mettere per iscritto."),
]
FALLBACK_COMMENT = "Grazie del messaggio! Ti rispondo in privato 🙂"


def _creds() -> tuple[str, str, str]:
    s = get_settings()
    tok = getattr(s, "meta_access_token", "") or os.environ.get("META_ACCESS_TOKEN", "")
    pid = getattr(s, "meta_page_id", "") or os.environ.get("META_PAGE_ID", "")
    r = httpx.get(f"{GRAPH}/{pid}", params={"access_token": tok, "fields": "access_token,instagram_business_account"}, timeout=15).json()
    return pid, r.get("access_token") or tok, (r.get("instagram_business_account") or {}).get("id") or ""


def answer_for(text: str) -> str | None:
    t = (text or "").lower()
    for pattern, reply in RULES:
        if re.search(pattern, t):
            return reply
    return None


def _wa_link(text: str) -> str:
    return f"https://wa.me/39{P.PHONE}?text={quote(text[:400])}"


def _notify_founder(kind: str, platform: str, who: str, text: str, replied: str | None, link: str = "") -> None:
    try:
        notify.send_email(f"💬 {platform}: {kind} da {who}",
                          f"<div style='font-family:-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.6'>"
                          f"<p><b>{who}</b> su {platform} ({kind}):</p><blockquote style='border-left:3px solid #b5532c;padding-left:12px;margin:8px 0'>{text[:600]}</blockquote>"
                          + (f"<p>Risposta automatica inviata: <i>{replied}</i></p>" if replied else "<p><b>Nessuna risposta automatica: rispondi tu.</b></p>")
                          + (f"<p><a href='{link}'>Apri su {platform}</a></p>" if link else "")
                          + f"<p><a href='{SITE}/pl/admin'>Pannello</a></p></div>")
    except Exception as e:  # noqa: BLE001
        log.error("notify: %s", e)


def _seen(uid: str) -> bool:
    ref = db.get_db().collection("social_inbox").document(uid)
    if ref.get().exists:
        return True
    return False


def _save(uid: str, doc: dict) -> None:
    db.get_db().collection("social_inbox").document(uid).set({**doc, "at": db.now()})


def run(limit_posts: int = 8) -> dict:
    """Every 15 minutes: new comments on our last posts (FB + IG) and new DMs; answer what we know, forward the rest."""
    pid, ptok, ig = _creds()
    out = {"comments": 0, "dms": 0, "answered": 0}
    since = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())
    # --- Facebook comments
    try:
        posts = httpx.get(f"{GRAPH}/{pid}/posts", params={"access_token": ptok, "fields": "id,permalink_url,comments.limit(25){id,message,from,created_time}", "limit": limit_posts, "since": since}, timeout=30).json().get("data", [])
        for post in posts:
            for c in (post.get("comments") or {}).get("data", []):
                uid = f"fb_{c['id']}"
                who = (c.get("from") or {}).get("name") or "utente Facebook"
                if _seen(uid) or (c.get("from") or {}).get("id") == pid:
                    continue
                text = c.get("message") or ""
                reply = answer_for(text)
                try:
                    httpx.post(f"{GRAPH}/{c['id']}/comments", data={"message": reply or FALLBACK_COMMENT, "access_token": ptok}, timeout=20)
                except Exception as e:  # noqa: BLE001
                    log.error("fb reply: %s", e)
                _save(uid, {"platform": "facebook", "kind": "commento", "from": who, "text": text, "reply": reply or FALLBACK_COMMENT, "status": "risposto" if reply else "inoltrato"})
                _notify_founder("commento", "Facebook", who, text, reply, post.get("permalink_url", ""))
                out["comments"] += 1
                out["answered"] += bool(reply)
    except Exception as e:  # noqa: BLE001
        log.error("fb comments: %s", e)
    # --- Instagram comments
    if ig:
        try:
            media = httpx.get(f"{GRAPH}/{ig}/media", params={"access_token": ptok, "fields": "id,permalink,comments.limit(25){id,text,username,timestamp}", "limit": limit_posts}, timeout=30).json().get("data", [])
            for m in media:
                for c in (m.get("comments") or {}).get("data", []):
                    uid = f"ig_{c['id']}"
                    who = "@" + (c.get("username") or "utente")
                    if _seen(uid) or c.get("username") == "poltronalibera":
                        continue
                    text = c.get("text") or ""
                    reply = answer_for(text)
                    try:
                        httpx.post(f"{GRAPH}/{c['id']}/replies", data={"message": reply or FALLBACK_COMMENT, "access_token": ptok}, timeout=20)
                    except Exception as e:  # noqa: BLE001
                        log.error("ig reply: %s", e)
                    _save(uid, {"platform": "instagram", "kind": "commento", "from": who, "text": text, "reply": reply or FALLBACK_COMMENT, "status": "risposto" if reply else "inoltrato"})
                    _notify_founder("commento", "Instagram", who, text, reply, m.get("permalink", ""))
                    out["comments"] += 1
                    out["answered"] += bool(reply)
        except Exception as e:  # noqa: BLE001
            log.error("ig comments: %s", e)
    # --- DMs (Facebook + Instagram inboxes)
    for platform, params in (("facebook", {"platform": "messenger"}), ("instagram", {"platform": "instagram"})):
        try:
            convs = httpx.get(f"{GRAPH}/{pid}/conversations", params={"access_token": ptok, "fields": "id,updated_time,participants,messages.limit(5){id,message,from,created_time}", "limit": 15, **params}, timeout=30).json().get("data", [])
        except Exception as e:  # noqa: BLE001
            log.error("%s dms: %s", platform, e)
            continue
        for conv in convs:
            msgs = (conv.get("messages") or {}).get("data", [])
            if not msgs:
                continue
            last = msgs[0]
            if (last.get("from") or {}).get("id") == pid:
                continue  # we answered last
            uid = f"dm_{last['id']}"
            if _seen(uid):
                continue
            who = (last.get("from") or {}).get("name") or (last.get("from") or {}).get("username") or "utente"
            text = last.get("message") or ""
            reply = answer_for(text)
            if reply:
                try:
                    httpx.post(f"{GRAPH}/{pid}/messages", json={"recipient": {"id": (last.get("from") or {}).get("id")}, "message": {"text": reply}, "messaging_type": "RESPONSE", "access_token": ptok}, timeout=20)
                except Exception as e:  # noqa: BLE001
                    log.error("dm reply: %s", e)
            _save(uid, {"platform": platform, "kind": "messaggio", "from": who, "text": text, "reply": reply or "", "status": "risposto" if reply else "inoltrato"})
            _notify_founder("messaggio", platform.capitalize(), who, text, reply)
            out["dms"] += 1
            out["answered"] += bool(reply)
    log.info("inbox: %s", out)
    return out


def recent(n: int = 30) -> list[dict]:
    items = [{"id": d.id, **d.to_dict()} for d in db.get_db().collection("social_inbox").stream()]
    items.sort(key=lambda x: str(x.get("at") or ""), reverse=True)
    return items[:n]
