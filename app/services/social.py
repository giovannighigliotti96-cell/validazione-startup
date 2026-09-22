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
SLOTS = [(1, 12, 30), (3, 12, 30), (5, 12, 30)]  # weekday (0=Mon), hour, minute: Tue / Thu / Sat 12:30
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


def next_slots(n: int, start: datetime | None = None) -> list[datetime]:
    """The next n editorial slots (Rome time) after `start`."""
    t = (start or datetime.now(ROME)).astimezone(ROME)
    out = []
    day = t.replace(hour=0, minute=0, second=0, microsecond=0)
    while len(out) < n:
        for wd, h, m in SLOTS:
            if day.weekday() == wd:
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
    slots = next_slots(len(todo))
    n = 0
    for (slug, audience, headline, _acc, text), when in zip(todo, slots):
        client.collection("social_posts").document(f"piano_{slug}").set({
            "slug": slug, "kind": "piano", "audience": audience, "headline": headline, "text": text,
            "image_url": f"{base()}/static/poltrona/social/{slug}.png", "link": "", "when": when.astimezone(timezone.utc),
            "status": "in_coda", "created_at": db.now()})
        n += 1
    return n


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
def publish(post: dict) -> dict:
    pid, ptok = _page()
    if post.get("image_url"):
        r = httpx.post(f"{GRAPH}/{pid}/photos", data={"url": post["image_url"], "message": post["text"], "access_token": ptok}, timeout=60).json()
    else:
        r = httpx.post(f"{GRAPH}/{pid}/feed", data={"message": post["text"], "link": post.get("link") or "", "access_token": ptok}, timeout=60).json()
    if "error" in r:
        raise RuntimeError(r["error"].get("message", str(r))[:200])
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
            r = publish(p)
            d.reference.update({"status": "pubblicato", "fb_id": r.get("post_id") or r.get("id"), "published_at": db.now()})
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
