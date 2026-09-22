"""Facebook page manager for Poltrona Libera: an editorial queue (hand-written plan + automatic posts for every
approved listing), published by the Cloud Run Job every 30 minutes via the Graph API. Giovanni sees the queue in
/pl/admin and can skip or publish any post before it goes out.

social_posts/{id}: when, kind (piano|annuncio), audience, text, image_url, link, status (in_coda|pubblicato|saltato|errore), fb_id
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from app import db
from app.config import get_settings

log = logging.getLogger("social")
ROME = ZoneInfo("Europe/Rome")
SLOTS = [(1, 12, 30), (3, 12, 30), (5, 11, 0), (6, 18, 0)]  # weekday (0=Mon), hour, minute: Tue/Thu 12:30 valore · Sat 11:00 postazioni · Sun 18:00 community
SLOT_NAME = {1: "tue", 3: "thu", 5: "sat", 6: "sun"}
GRAPH = "https://graph.facebook.com/v21.0"


def base() -> str:
    return get_settings().public_base_url.rstrip("/")


def _page() -> tuple[str, str]:
    """(page id, page access token) from the system-user token."""
    s = get_settings()
    tok = getattr(s, "meta_access_token", "") or os.environ.get("META_ACCESS_TOKEN", "")
    pid = getattr(s, "meta_page_id", "") or os.environ.get("META_PAGE_ID", "")
    r = httpx.get(f"{GRAPH}/{pid}", params={"access_token": tok, "fields": "access_token"}, timeout=15).json()
    return pid, r.get("access_token") or tok


def next_slots(n: int, start: datetime | None = None, only: str | None = None) -> list[datetime]:
    """The next n editorial slots (Rome time) after `start`; `only` = 'tue'|'thu'|'sat'|'sun' to pick one kind of slot."""
    t = (start or datetime.now(ROME)).astimezone(ROME)
    out = []
    day = t.replace(hour=0, minute=0, second=0, microsecond=0)
    while len(out) < n:
        for wd, h, m in SLOTS:
            if day.weekday() == wd and (only is None or SLOT_NAME[wd] == only):
                when = day.replace(hour=h, minute=m)
                if when > t:
                    out.append(when)
        day += timedelta(days=1)
    return out[:n]


# ----------------------------------------------------------------------------- queue
def seed_plan(force: bool = False) -> int:
    """Load the hand-written plan into the queue (once), one post per slot from the next slot on."""
    from scripts.social_plan import POSTS

    client = db.get_db()
    existing = {d.to_dict().get("slug") for d in client.collection("social_posts").stream()}
    todo = [p for p in POSTS if force or p[0] not in existing]
    used: dict[str, int] = {}
    n = 0
    for slug, slot, audience, headline, _acc, text in todo:
        k = used.get(slot, 0)
        when = next_slots(k + 1, only=slot)[k]  # k-th upcoming slot of that kind
        used[slot] = k + 1
        client.collection("social_posts").document(f"piano_{slug}").set({
            "slug": slug, "kind": "piano", "audience": audience, "headline": headline, "text": text,
            "image_url": f"{base()}/static/poltrona/social/{slug}.png", "link": "", "when": when.astimezone(timezone.utc),
            "status": "in_coda", "created_at": db.now()})
        n += 1
    n += roundup_posts()
    return n


def roundup_posts() -> int:
    """Saturday 11:00: 'Postazioni della settimana', built from what is online at publish time (text refreshed then)."""
    client = db.get_db()
    n = 0
    for when in next_slots(4, only="sat"):
        pid = f"postazioni_{when.strftime('%Y%m%d')}"
        if client.collection("social_posts").document(pid).get().exists:
            continue
        client.collection("social_posts").document(pid).set({
            "slug": pid, "kind": "postazioni", "audience": "professioniste", "headline": "Postazioni della settimana", "text": "",
            "image_url": "", "link": f"{base()}/pl/postazioni", "when": when.astimezone(timezone.utc), "status": "in_coda", "created_at": db.now()})
        n += 1
    return n


def _roundup_text() -> tuple[str, str]:
    """(text, image) for the weekly roundup from the listings online now."""
    from app.services import poltrona as P

    items = P.online_listings()
    if not items:
        return "", ""
    lines = []
    for li in items[:6]:
        lines.append(f"• {li.get('salone')} · {li.get('zona')} — {li.get('giorni') or 'giorni da concordare'} · {li.get('prezzo') or 'da concordare'} · chiama {P.first_name(li.get('titolare') or '')} {li.get('telefono')}")
    text = ("🪑 Postazioni disponibili questa settimana a Milano\n\n" + "\n".join(lines) +
            f"\n\nTutte con foto e dettagli, e il numero della titolare: chiami tu, direttamente, gratis. 👉 {base()}/pl/postazioni"
            f"\n\nHai una poltrona libera nel tuo salone? Pubblicala gratis: {base()}/lp/{P.OWNERS}")
    return text, (items[0].get("photos") or [""])[0]


def enqueue_listing(listing: dict) -> str | None:
    """A listing went online: post it (photo + text) at the next free slot, or within the hour if the next slot is far."""
    if not listing.get("photos"):
        return None
    client = db.get_db()
    ref = client.collection("social_posts").document(f"annuncio_{listing['id']}")
    if ref.get().exists:
        return ref.id
    now = datetime.now(ROME)
    slot = next_slots(1)[0]
    when = slot if (slot - now) < timedelta(hours=20) else now + timedelta(hours=1)
    # never more than one post per 3 hours: shift by the number already queued that day
    same_day = [d.to_dict() for d in client.collection("social_posts").where("status", "==", "in_coda").stream()
                if d.to_dict().get("when") and d.to_dict()["when"].astimezone(ROME).date() == when.date()]
    when = when + timedelta(hours=3 * len(same_day))
    if when.hour >= 21:
        when = (when + timedelta(days=1)).replace(hour=10, minute=30)
    salone, zona = listing.get("salone") or "Salone", listing.get("zona") or "Milano"
    text = (f"🪑 Postazione libera a {zona}\n\n{salone} affitta una postazione: {listing.get('giorni') or 'giorni da concordare'} · {listing.get('prezzo') or 'prezzo da concordare'}."
            + (f"\nIncluso: {listing['incluso']}." if listing.get("incluso") else "")
            + (f"\nCerca: {listing['chi_cerchi']}." if listing.get("chi_cerchi") else "")
            + f"\n\nChiama {listing.get('titolare') or 'la titolare'} al {listing.get('telefono')}, direttamente. Gratis.\n\nTutte le postazioni a Milano: {base()}/pl/postazioni")
    ref.set({"slug": f"annuncio_{listing['id']}", "kind": "annuncio", "audience": "professioniste", "headline": f"{salone} · {zona}", "text": text,
             "image_url": listing["photos"][0], "link": f"{base()}/pl/postazioni", "listing_id": listing["id"], "when": when.astimezone(timezone.utc),
             "status": "in_coda", "created_at": db.now()})
    return ref.id


def queue() -> list[dict]:
    items = [{"id": d.id, **d.to_dict()} for d in db.get_db().collection("social_posts").stream()]
    items.sort(key=lambda x: (x.get("status") != "in_coda", str(x.get("when") or "")))
    return items


def set_status(post_id: str, status: str) -> None:
    db.get_db().collection("social_posts").document(post_id).update({"status": status, "updated_at": db.now()})


# ----------------------------------------------------------------------------- publish
def _instagram_id(pid: str, tok: str) -> str | None:
    r = httpx.get(f"{GRAPH}/{pid}", params={"access_token": tok, "fields": "instagram_business_account"}, timeout=15).json()
    return (r.get("instagram_business_account") or {}).get("id")


def publish_instagram(post: dict) -> str | None:
    """Same post on @poltronalibera (image required; links are not clickable on IG, so the caption says 'link in bio')."""
    if not post.get("image_url"):
        return None
    s = get_settings()
    tok = getattr(s, "meta_access_token", "") or os.environ.get("META_ACCESS_TOKEN", "")
    pid = getattr(s, "meta_page_id", "") or os.environ.get("META_PAGE_ID", "")
    ig = _instagram_id(pid, tok)
    if not ig:
        return None
    caption = post["text"]
    for u in ("https://poltronalibera.it/pl/postazioni", "https://poltronalibera.it/lp/poltrona_libera_titolari", "https://poltronalibera.it/lp/poltrona_libera_professioniste",
              "https://poltronalibera.it/pl/guida/squadra", "https://poltronalibera.it/pl/guida/poltrona"):
        caption = caption.replace(u, "link in bio")
    caption = (caption + "\n\n#parrucchieri #barbieri #milano #salone #affittopoltrona #poltronalibera")[:2200]
    c = httpx.post(f"{GRAPH}/{ig}/media", data={"image_url": post["image_url"], "caption": caption, "access_token": tok}, timeout=60).json()
    if "error" in c:
        raise RuntimeError("IG: " + c["error"].get("message", "")[:160])
    import time as _t

    for _ in range(10):  # wait for Meta to fetch the image
        st = httpx.get(f"{GRAPH}/{c['id']}", params={"access_token": tok, "fields": "status_code"}, timeout=15).json().get("status_code")
        if st == "FINISHED":
            break
        if st == "ERROR":
            raise RuntimeError("IG: media container error")
        _t.sleep(3)
    r = httpx.post(f"{GRAPH}/{ig}/media_publish", data={"creation_id": c["id"], "access_token": tok}, timeout=60).json()
    if "error" in r:
        raise RuntimeError("IG publish: " + r["error"].get("message", "")[:160])
    return r.get("id")


def publish(post: dict) -> dict:
    pid, ptok = _page()
    if post.get("image_url"):
        r = httpx.post(f"{GRAPH}/{pid}/photos", data={"url": post["image_url"], "message": post["text"], "access_token": ptok}, timeout=60).json()
    else:
        r = httpx.post(f"{GRAPH}/{pid}/feed", data={"message": post["text"], "link": post.get("link") or "", "access_token": ptok}, timeout=60).json()
    if "error" in r:
        raise RuntimeError(r["error"].get("message", str(r))[:200])
    try:
        r["ig_id"] = publish_instagram(post)
    except Exception as e:  # noqa: BLE001
        log.error("instagram publish: %s", e)
        r["ig_error"] = str(e)[:160]
    return r


def publish_due(force_id: str | None = None) -> int:
    """Every 30 minutes: publish what is due (or one post now, from the panel)."""
    client = db.get_db()
    now = datetime.now(timezone.utc)
    n = 0
    for d in client.collection("social_posts").where("status", "==", "in_coda").stream():
        p = {"id": d.id, **d.to_dict()}
        if force_id and p["id"] != force_id:
            continue
        if not force_id and p.get("when") and p["when"] > now:
            continue
        try:
            if str(p.get("kind", "")).startswith("ig_"):
                from app.services import instagram

                r = instagram.publish_ig(p)
                d.reference.update({"status": "pubblicato", "ig_id": r.get("ig_id"), "published_at": db.now()})
                n += 1
                continue
            if p.get("kind") == "postazioni":
                text, img = _roundup_text()
                if not text:
                    d.reference.update({"status": "saltato", "error": "nessuna postazione online", "updated_at": db.now()})
                    continue
                p["text"], p["image_url"] = text, img
                d.reference.update({"text": text, "image_url": img})
            r = publish(p)
            d.reference.update({"status": "pubblicato", "fb_id": r.get("post_id") or r.get("id"), "ig_id": r.get("ig_id"), "ig_error": r.get("ig_error"), "published_at": db.now()})
            n += 1
        except Exception as e:  # noqa: BLE001
            log.error("publish %s: %s", p["id"], e)
            d.reference.update({"status": "errore", "error": str(e)[:200], "updated_at": db.now()})
    return n


def week_summary() -> str:
    """Monday email: what went out last week and what is scheduled."""
    items = queue()
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    done = [p for p in items if p.get("status") == "pubblicato" and p.get("published_at") and p["published_at"] >= week_ago]
    nxt = [p for p in items if p.get("status") == "in_coda"][:6]
    fmt = lambda p: f"<li>{(p.get('when') or datetime.now(timezone.utc)).astimezone(ROME).strftime('%a %d/%m %H:%M')} · {p.get('kind')} · {p.get('headline') or p.get('text', '')[:60]}</li>"  # noqa: E731
    return (f"<h3>Pagina Facebook</h3><p>Pubblicati la settimana scorsa: {len(done)}</p><ul>{''.join(fmt(p) for p in done)}</ul>"
            f"<p>In coda:</p><ul>{''.join(fmt(p) for p in nxt)}</ul><p><a href='{base()}/pl/admin'>Pannello</a></p>")
