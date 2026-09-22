"""Instagram (@poltronalibera) editorial engine: carousels that teach, 5 stories a day, a 'postazione del giorno'
story built from a real listing. Separate queue kinds in social_posts: ig_carousel, ig_story, ig_postazione.
Published by the same 30-minute job (app.services.social.publish_due -> publish_ig)."""
from __future__ import annotations

import io
import logging
import os
import time
from datetime import datetime, timedelta, timezone

import httpx

from app import db
from app.config import get_settings
from app.services.social import ROME, base

log = logging.getLogger("instagram")
GRAPH = "https://graph.facebook.com/v21.0"
STORY_TIMES = [(9, 0), (11, 30), (14, 0), (17, 0), (19, 30)]
CAROUSEL_TIME = (13, 0)


def _creds() -> tuple[str, str]:
    s = get_settings()
    tok = getattr(s, "meta_access_token", "") or os.environ.get("META_ACCESS_TOKEN", "")
    pid = getattr(s, "meta_page_id", "") or os.environ.get("META_PAGE_ID", "")
    r = httpx.get(f"{GRAPH}/{pid}", params={"access_token": tok, "fields": "instagram_business_account"}, timeout=15).json()
    return (r.get("instagram_business_account") or {}).get("id") or "", tok


def _wait(cid: str, tok: str) -> None:
    for _ in range(12):
        st = httpx.get(f"{GRAPH}/{cid}", params={"access_token": tok, "fields": "status_code"}, timeout=15).json().get("status_code")
        if st == "FINISHED":
            return
        if st == "ERROR":
            raise RuntimeError("IG media container error")
        time.sleep(3)


def publish_carousel(images: list[str], caption: str) -> str:
    ig, tok = _creds()
    if not ig:
        raise RuntimeError("Instagram non collegato")
    kids = []
    for u in images[:10]:
        c = httpx.post(f"{GRAPH}/{ig}/media", data={"image_url": u, "is_carousel_item": "true", "access_token": tok}, timeout=60).json()
        if "error" in c:
            raise RuntimeError("IG item: " + c["error"].get("message", "")[:140])
        _wait(c["id"], tok)
        kids.append(c["id"])
    c = httpx.post(f"{GRAPH}/{ig}/media", data={"media_type": "CAROUSEL", "children": ",".join(kids), "caption": caption[:2200], "access_token": tok}, timeout=60).json()
    if "error" in c:
        raise RuntimeError("IG carousel: " + c["error"].get("message", "")[:140])
    _wait(c["id"], tok)
    r = httpx.post(f"{GRAPH}/{ig}/media_publish", data={"creation_id": c["id"], "access_token": tok}, timeout=60).json()
    if "error" in r:
        raise RuntimeError("IG publish: " + r["error"].get("message", "")[:140])
    return r.get("id", "")


def publish_story(image_url: str) -> str:
    ig, tok = _creds()
    if not ig:
        raise RuntimeError("Instagram non collegato")
    c = httpx.post(f"{GRAPH}/{ig}/media", data={"media_type": "STORIES", "image_url": image_url, "access_token": tok}, timeout=60).json()
    if "error" in c:
        raise RuntimeError("IG story: " + c["error"].get("message", "")[:140])
    _wait(c["id"], tok)
    r = httpx.post(f"{GRAPH}/{ig}/media_publish", data={"creation_id": c["id"], "access_token": tok}, timeout=60).json()
    if "error" in r:
        raise RuntimeError("IG story publish: " + r["error"].get("message", "")[:140])
    return r.get("id", "")


# ----------------------------------------------------------------------------- listing story (photo + text overlay)
def listing_story_url(listing: dict) -> str | None:
    """Story image for a real listing: its photo as background, zone/days/price/number on top; uploaded to the public bucket."""
    from firebase_admin import storage as fb_storage
    from PIL import Image, ImageDraw, ImageFilter

    from scripts.make_creatives_poltrona import ACC, F, PAPER, SANS, SANS_B, SERIF_B, draw_lines, wrap

    photo = (listing.get("photos") or [None])[0]
    if not photo:
        return None
    try:
        raw = httpx.get(photo, timeout=30).content
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = 1080, 1920
        scale = max(w / im.width, h / im.height)
        im = im.resize((int(im.width * scale) + 1, int(im.height * scale) + 1))
        im = im.crop(((im.width - w) // 2, (im.height - h) // 2, (im.width - w) // 2 + w, (im.height - h) // 2 + h))
        dark = Image.new("RGB", (w, h), (0, 0, 0))
        im = Image.blend(im, dark, 0.45)
        d = ImageDraw.Draw(im)
        d.text((72, 520), "POSTAZIONE DEL GIORNO", font=F(SANS_B, 30), fill=(230, 130, 90))
        tf = F(SERIF_B, 84)
        y = draw_lines(d, 72, 600, wrap(d, f"{listing.get('salone')} · {listing.get('zona')}", tf, w - 144), tf, PAPER, 96)
        bf = F(SANS, 46)
        for ln in (listing.get("giorni") or "", listing.get("prezzo") or "", (listing.get("chi_cerchi") or "")[:60]):
            if ln:
                y = draw_lines(d, 72, y + 22, wrap(d, ln, bf, w - 150), bf, (235, 228, 218), 60)
        d.rounded_rectangle((72, h - 460, 72 + 760, h - 460 + 104), radius=999, fill=ACC)
        d.text((72 + 44, h - 460 + 28), f"chiama {listing.get('telefono')}", font=F(SANS_B, 38), fill=PAPER)
        d.text((72, h - 200), "@poltronalibera · link in bio", font=F(SANS_B, 34), fill=PAPER)
        out = io.BytesIO()
        im.save(out, "JPEG", quality=88)
        db.get_db()
        blob = fb_storage.bucket("poltrona-libera-foto").blob(f"stories/{listing['id']}_{int(time.time())}.jpg")
        blob.cache_control = "public, max-age=86400"
        blob.upload_from_string(out.getvalue(), content_type="image/jpeg")
        return f"https://storage.googleapis.com/poltrona-libera-foto/{blob.name}"
    except Exception as e:  # noqa: BLE001
        log.error("listing story image: %s", e)
        return None


# ----------------------------------------------------------------------------- queue
def seed(days: int = 21) -> int:
    """Carousels on their weekdays at 13:00 (one per slot, in plan order), 5 stories a day (4 from the bank + 1 listing of the day)."""
    from scripts.ig_plan import CAROUSELS, STORIES

    client = db.get_db()
    existing = {d.id for d in client.collection("social_posts").select([]).stream()}
    n = 0
    today = datetime.now(ROME).replace(hour=0, minute=0, second=0, microsecond=0)
    # carousels: walk the plan, each takes the next occurrence of its weekday
    cursor = today
    for slug, wd, caption, slides in CAROUSELS:
        day = cursor
        while day.weekday() != wd or day.replace(hour=CAROUSEL_TIME[0], minute=CAROUSEL_TIME[1]) < datetime.now(ROME):
            day += timedelta(days=1)
        when = day.replace(hour=CAROUSEL_TIME[0], minute=CAROUSEL_TIME[1])
        pid = f"ig_car_{slug}"
        if pid not in existing:
            client.collection("social_posts").document(pid).set({
                "slug": pid, "kind": "ig_carousel", "audience": "professioniste", "headline": slides[0][0], "text": caption,
                "image_url": f"{base()}/static/poltrona/ig/{slug}_1.png", "images": [f"{base()}/static/poltrona/ig/{slug}_{i + 1}.png" for i in range(len(slides))],
                "when": when.astimezone(timezone.utc), "status": "in_coda", "created_at": db.now()})
            n += 1
        cursor = day + timedelta(days=1)
    # stories: 5 a day; slot 3 (14:00) is the listing of the day, the others rotate through the bank
    k = 0
    for dday in range(days):
        day = today + timedelta(days=dday)
        for si, (hh, mm) in enumerate(STORY_TIMES):
            when = day.replace(hour=hh, minute=mm)
            if when < datetime.now(ROME):
                continue
            pid = f"ig_story_{when.strftime('%Y%m%d_%H%M')}"
            if pid in existing:
                continue
            if si == 2:
                doc = {"kind": "ig_postazione", "headline": "Postazione del giorno", "text": "", "image_url": ""}
            else:
                slug, kind, lines = STORIES[k % len(STORIES)]
                k += 1
                doc = {"kind": "ig_story", "headline": lines[0], "text": " / ".join(lines), "image_url": f"{base()}/static/poltrona/ig/{slug}.png"}
            client.collection("social_posts").document(pid).set({**doc, "slug": pid, "audience": "professioniste", "when": when.astimezone(timezone.utc), "status": "in_coda", "created_at": db.now()})
            n += 1
    return n


def publish_ig(post: dict) -> dict:
    """Dispatch for the IG kinds; returns {'ig_id': ...}."""
    if post["kind"] == "ig_carousel":
        return {"ig_id": publish_carousel(post.get("images") or [post["image_url"]], post["text"])}
    if post["kind"] == "ig_story":
        return {"ig_id": publish_story(post["image_url"])}
    if post["kind"] == "ig_postazione":
        from app.services import poltrona as P

        items = P.online_listings()
        if not items:
            raise RuntimeError("nessuna postazione online")
        # rotate: pick the listing least recently featured
        client = db.get_db()
        featured = [d.to_dict().get("listing_id") for d in client.collection("social_posts").where("kind", "==", "ig_postazione").where("status", "==", "pubblicato").stream()]
        items.sort(key=lambda li: featured.count(li["id"]))
        li = items[0]
        url = listing_story_url(li)
        if not url:
            raise RuntimeError("immagine storia non generata")
        client.collection("social_posts").document(post["id"]).update({"listing_id": li["id"], "image_url": url, "headline": f"Postazione del giorno · {li.get('salone')}"})
        return {"ig_id": publish_story(url)}
    raise RuntimeError(f"kind sconosciuto {post['kind']}")
