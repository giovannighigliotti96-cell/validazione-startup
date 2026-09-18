"""Meta Ad Library, broad-first digital-product discovery (Giovanni's method, running 24/7).

Rule: an advertiser that has kept the SAME ad active for 6+ months is making money with it. So every search uses
active_status=active + start_date <= today-180d, country ALL: what comes back is only proven ads, a few hundred
per term instead of millions. Then, one cheap-LLM call per advertiser page: digital product? which niche? is it a
faceless brand or a named professional (lawyer, MD, coach) whose credentials sell it? Each niche label found is
pushed back into the search queue (snowball), so the map grows on its own. Per niche: number of proven
advertisers = competitors. 1-2 faceless competitors = SWEET_SPOT; 3+ = CROWDED; 0 = UNPROVEN.

Firestore: adlib_queue/{term}, adlib_ads/{ad_id}, adlib_pages/{page}, adlib_niches/{niche}.
"""
from __future__ import annotations

import logging
import re
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote, urlparse

from pydantic import BaseModel

from app import db
from app.services.analysis import BudgetExhausted, budget, llm_json

log = logging.getLogger("adlib")

MIN_AGE_DAYS = 180
MAX_SCROLLS = 120
SEED_TERMS = [
    # only words that a seller of DOWNLOADABLE files uses (no courses, no generic nouns)
    "instant download", "digital download", "digital product", "printable", "printables", "printable pdf", "pdf guide", "pdf download",
    "ebook", "editable template", "templates bundle", "done for you", "swipe file", "script library", "worksheets", "workbook",
    "digital planner", "checklist pdf", "toolkit pdf", "presets", "lifetime access", "one time payment", "commercial license", "plr",
    "master resell rights", "canva template", "notion template", "excel template", "google sheets template", "spreadsheet template",
    "powerpoint template", "pitch deck template", "study guide pdf", "study notes", "cheat sheet", "flashcards pdf", "exam prep pdf",
    "practice questions pdf", "prompt pack", "pattern pdf", "plans pdf", "contract template", "agreement template", "recipes ebook",
    "meal plan pdf", "workout plan pdf", "training program pdf", "resume template", "invoice template", "svg bundle", "fonts bundle",
    "lightroom presets", "procreate brushes", "lut pack", "sample pack", "midi pack", "sheet music pdf", "crochet pattern", "sewing pattern",
    "embroidery pattern", "cross stitch pattern", "knitting pattern", "3d print files", "stl files", "cricut files", "sublimation designs",
    "wall art printable", "coloring pages", "kids printables", "lesson plans pdf", "homeschool printables", "teacher resources",
    "therapy worksheets", "counseling worksheets", "coaching templates", "budget spreadsheet", "wedding templates", "real estate templates",
    "small business forms", "social media templates", "email templates", "sales scripts", "guided meditation scripts",
    # IT
    "prodotto digitale", "download immediato", "scarica subito", "stampabile", "modello editabile", "fac simile", "guida pdf", "ebook pdf",
    "kit completo pdf", "pagamento unico", "fogli di lavoro", "schede stampabili", "modelli canva", "fogli excel", "planner digitale",
    "ricettario pdf", "scheda allenamento pdf", "contratto modello", "preset lightroom", "cartamodello", "schema uncinetto", "file stl",
    "schede didattiche",
]
APP_HOSTS = ("play.google.com", "apps.apple.com", "itunes.apple.com")
MONTHS = {"gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6, "lug": 7, "ago": 8, "set": 9, "ott": 10, "nov": 11, "dic": 12}
DATE_RE = re.compile(r"(\d{1,2}) (gen|feb|mar|apr|mag|giu|lug|ago|set|ott|nov|dic) (\d{4})")
SKIP_LINES = ("Inserzioni che usano", "Apri il menu", "Vedi ", "Scopri di più", "Acquista", "Ulteriori informazioni", "Iscriviti", "Invia")

JS_CARDS = r"""
() => {
  const out = [];
  const nodes = [...document.querySelectorAll('div,span')].filter(e => e.childElementCount === 0 && /^ID libreria: \d+/.test(e.textContent.trim()));
  for (const n of nodes) {
    let card = n; for (let i = 0; i < 12 && card.parentElement; i++) { card = card.parentElement; if (card.querySelector('video, a[href*="l.facebook.com/l.php"]') && card.textContent.includes('Sponsorizzato')) break; }
    const links = [...card.querySelectorAll('a[href*="l.facebook.com/l.php"]')].map(a => a.href);
    let dest = null; if (links.length) { try { dest = new URL(links[0]).searchParams.get('u'); } catch (e) {} }
    out.push({id: n.textContent.trim().replace('ID libreria: ', ''), video: !!card.querySelector('video'), dest, text: card.innerText.slice(0, 1800)});
  }
  return out;
}"""


def _model(cls, data):
    """Small LLMs sometimes wrap the object in a list or nest a dict where a string is expected."""
    if isinstance(data, list):
        data = next((x for x in data if isinstance(x, dict)), {})
    if not isinstance(data, dict):
        data = {}
    fixed = {}
    for name, field in cls.model_fields.items():
        v = data.get(name)
        if field.annotation is str:
            v = "" if v is None else (v if isinstance(v, str) else str(v)[:200])
        elif field.annotation is bool:
            v = bool(v) if not isinstance(v, str) else v.strip().lower() in ("true", "yes", "1")
        fixed[name] = v
    return cls(**fixed)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")[:80] or "x"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ----------------------------------------------------------------------------- harvest
def library_url(term: str, min_age_days: int = MIN_AGE_DAYS) -> str:
    max_start = (date.today() - timedelta(days=min_age_days)).isoformat()
    return (f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&q={quote(term)}"
            f"&search_type=keyword_unordered&media_type=all&start_date[min]=2018-01-01&start_date[max]={max_start}")


def parse_card(c: dict, term: str) -> dict | None:
    lines = [x.strip() for x in c["text"].splitlines() if x.strip() and x.strip() != "​"]
    if "Sponsorizzato" not in lines:
        return None
    k = lines.index("Sponsorizzato")
    page = lines[k - 1] if k else None
    if not page or page.startswith(("ID libreria", "Piattaforme")):
        return None
    head = "\n".join(lines[:k])
    m = DATE_RE.search(head)
    start = date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1))).isoformat() if m else None
    body = " ".join(x for x in lines[k + 1:] if not x.startswith(SKIP_LINES))
    host = urlparse(c["dest"]).netloc.lower().replace("www.", "") if c.get("dest") else None
    return {"id": c["id"], "page": page, "page_slug": slug(page), "active": "Attiva" in lines[:3], "start": start, "text": body[:900],
            "dest": (c.get("dest") or "")[:300], "host": host, "video": bool(c["video"]), "term": term, "seen_at": now()}


def harvest_term(term: str, max_scrolls: int = MAX_SCROLLS) -> tuple[int, int, str | None]:
    """Returns (cards seen, ads saved, results reported by the library)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        pg = b.new_page(viewport={"width": 1300, "height": 900}, locale="it-IT")
        try:
            pg.goto(library_url(term), wait_until="domcontentloaded")
            time.sleep(6)
            reported = None
            mm = re.search(r"~?([\d.]+) risultat", pg.inner_text("body"))
            reported = mm.group(1) if mm else None
            last, stale = 0, 0
            for i in range(max_scrolls):
                pg.mouse.wheel(0, 5000)
                time.sleep(1.3)
                if i % 10 == 9:
                    n = pg.evaluate("() => document.body.innerText.split('ID libreria:').length")
                    stale = stale + 1 if n == last else 0
                    if stale >= 2:  # two checks (20 scrolls) without new cards: the list is exhausted
                        break
                    if n == last:
                        time.sleep(4)  # slow network: give the next batch time to arrive
                    last = n
            cards = pg.evaluate(JS_CARDS)
        finally:
            b.close()
    col = db.get_db().collection("adlib_ads")
    batch, nb, saved = db.get_db().batch(), 0, 0
    for c in cards:
        a = parse_card(c, term)
        if not a:
            continue
        batch.set(col.document(a["id"]), a, merge=True)
        nb += 1
        saved += 1
        if nb >= 400:
            batch.commit()
            batch, nb = db.get_db().batch(), 0
    if nb:
        batch.commit()
    return len(cards), saved, reported


# ----------------------------------------------------------------------------- classify
class PageVerdict(BaseModel):
    digital_product: bool
    product: str
    niche: str
    audience: str
    format: str  # pdf|template|course|bundle|app|physical|service|other
    faceless: bool
    who_is_behind: str
    price: str


CLASSIFY_PROMPT = (
    "Ad Library research on digital products. Advertiser page: '{page}'. Destination site: '{host}'. Ad texts:\n{texts}\n\n"
    "digital_product: true only if the ads sell a DOWNLOADABLE FILE product delivered instantly (pdf, templates, printables, scripts, ebook, "
    "presets, patterns, spreadsheets, fonts, svg, stl, audio packs, or a bundle of such files) - NOT courses/video courses/masterclasses/"
    "memberships, not apps/SaaS, not physical goods, not live services, not coaching calls, not free lead magnets for an agency or a service. product: what exactly is sold (<=12 words). niche: a short generic English label "
    "of the market, product type + audience (2-5 words, e.g. 'divorce agreement templates', 'therapy worksheets', 'lightroom presets'). "
    "audience: who buys. format: pdf|template|course|bundle|app|physical|service|other. faceless: true if sold by a brand/shop with no named "
    "expert; false if a named person or professional (lawyer, MD, therapist, coach, teacher with credentials) is the selling point. "
    "who_is_behind: brand or person (<=10 words). price: as written in the ads, else ''.")


def classify_new_pages(limit: int = 250) -> list[dict]:
    """One LLM call per advertiser page not yet classified. Returns the classified page docs."""
    client = db.get_db()
    done = {d.id for d in client.collection("adlib_pages").select([]).stream()}
    by_page: dict[str, list[dict]] = defaultdict(list)
    for d in client.collection("adlib_ads").stream():
        a = d.to_dict()
        if a["page_slug"] not in done:
            by_page[a["page_slug"]].append(a)
    out = []
    for ps, items in list(by_page.items())[:limit]:
        page = items[0]["page"]
        hosts = Counter(a["host"] for a in items if a["host"])
        host = hosts.most_common(1)[0][0] if hosts else ""
        texts = sorted({a["text"] for a in items if a["text"]}, key=len, reverse=True)[:3]
        if host and any(h in host for h in APP_HOSTS):
            v = PageVerdict(digital_product=False, product="mobile app", niche="app", audience="", format="app", faceless=True, who_is_behind="app publisher", price="")
        elif not texts:
            v = PageVerdict(digital_product=False, product="", niche="unknown", audience="", format="other", faceless=True, who_is_behind="", price="")
        else:
            try:
                v = _model(PageVerdict, llm_json(CLASSIFY_PROMPT.format(page=page, host=host or "unknown", texts="\n---\n".join(t[:600] for t in texts)), PageVerdict))
            except BudgetExhausted:
                break
            except Exception as e:  # noqa: BLE001
                log.warning("classify %s: %s", page, e)
                continue
        starts = sorted(a["start"] for a in items if a["start"])
        days = (date.today() - date.fromisoformat(starts[0])).days if starts else 0
        doc = {**v.model_dump(), "page": page, "niche_slug": slug(v.niche), "host": host, "ads": len(items), "video_ads": sum(a["video"] for a in items),
               "first_seen": starts[0] if starts else None, "days_running": days, "terms": sorted({a["term"] for a in items}),
               "dest": next((a["dest"] for a in items if a["dest"]), ""), "sample": texts[0][:300] if texts else "", "classified_at": now()}
        client.collection("adlib_pages").document(ps).set(doc, merge=True)
        out.append(doc)
    return out


# ----------------------------------------------------------------------------- queue (snowball)
def enqueue(term: str, source: str, priority: int = 0) -> bool:
    term = re.sub(r"\s+", " ", term.strip().lower())
    if not ((1 if source == "seed" else 2) <= len(term.split()) <= 5) or len(term) > 60:
        return False
    ref = db.get_db().collection("adlib_queue").document(slug(term))
    if ref.get().exists:
        return False
    ref.set({"term": term, "source": source, "priority": priority, "status": "pending", "created_at": now()})
    return True


def seed_queue() -> int:
    return sum(enqueue(t, "seed", 10) for t in SEED_TERMS)


def next_terms(n: int) -> list[dict]:
    """Half generic seeds (breadth), half snowballed niche labels (depth), oldest first."""
    q = [d.to_dict() for d in db.get_db().collection("adlib_queue").where("status", "==", "pending").stream()]
    seeds = sorted((t for t in q if t["source"] == "seed"), key=lambda t: t["created_at"])
    snow = sorted((t for t in q if t["source"] != "seed"), key=lambda t: t["created_at"])
    out = []
    while len(out) < n and (seeds or snow):
        if snow and (len(out) % 2 == 1 or not seeds):
            out.append(snow.pop(0))
        elif seeds:
            out.append(seeds.pop(0))
    return out


# ----------------------------------------------------------------------------- niches
def rebuild_niches(only: set[str] | None = None) -> list[dict]:
    """Per niche label: proven (6m+ active) digital-product advertisers = competitors. Verdict per Giovanni's rule."""
    client = db.get_db()
    groups: dict[str, list[dict]] = defaultdict(list)
    for d in client.collection("adlib_pages").stream():
        p = d.to_dict()
        if p.get("digital_product") and p.get("niche_slug") not in ("app", "unknown", "x"):
            groups[p["niche_slug"]].append(p)
    searched = {d.id: d.to_dict() for d in client.collection("adlib_queue").where("status", "==", "done").stream()}
    out = []
    for ns, items in groups.items():
        if only and ns not in only:
            continue
        faceless = [p for p in items if p["faceless"]]
        n = len(items)
        verdict = "SWEET_SPOT" if 1 <= n <= 2 else "CROWDED" if n >= 3 else "UNPROVEN"
        if verdict == "SWEET_SPOT" and not faceless:
            verdict = "SWEET_BUT_FACE"  # only named professionals: cannot compete without a face
        if ns not in searched and n < 3:
            verdict = "PENDING"  # competitors are only counted for real once the niche's own words have been searched
        leaders = sorted(items, key=lambda x: -x["days_running"])[:6]
        doc = {"niche": items[0]["niche"], "slug": ns, "competitors": n, "faceless": len(faceless), "verdict": verdict,
               "term_searched": ns in searched, "video_share": round(sum(p["video_ads"] for p in items) / max(1, sum(p["ads"] for p in items)), 2),
               "leaders": [{"page": p["page"], "days": p["days_running"], "faceless": p["faceless"], "who": p["who_is_behind"], "product": p["product"],
                            "price": p["price"], "host": p["host"], "dest": p.get("dest", ""), "site_check": p.get("site_check")} for p in leaders],
               "updated_at": now()}
        client.collection("adlib_niches").document(ns).set(doc)
        out.append(doc)
    return out


class SiteCheck(BaseModel):
    product: str
    price: str
    named_expert: bool
    expert_desc: str
    platform: str  # shopify|etsy|gumroad|systeme|clickfunnels|wordpress|other
    has_upsell_or_bundle: bool
    notes: str


def deep_check(limit: int = 5) -> int:
    """Read the destination site of sweet-spot leaders: real product, price, and whether a named expert is the selling point."""
    import httpx

    client = db.get_db()
    n = 0
    for d in client.collection("adlib_niches").where("verdict", "in", ["SWEET_SPOT", "SWEET_BUT_FACE"]).stream():
        for lead in (d.to_dict().get("leaders") or [])[:2]:
            if lead.get("site_check") or not lead.get("dest") or n >= limit:
                continue
            try:
                html = httpx.get(lead["dest"], timeout=20, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}).text
                text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
                text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))[:6000]
                plat = "shopify" if "cdn.shopify" in html else next((k for k in ("etsy", "gumroad", "systeme", "clickfunnels") if k in lead["dest"] or k in html[:20000]), "wordpress" if "wp-content" in html else "other")
                sc = _model(SiteCheck, llm_json(f"Landing page text of an advertiser ({lead['dest']}). Platform hint: {plat}.\n{text}\n\nExtract: product sold, price, "
                                          "named_expert (is a named person with credentials/photo the selling point?), expert_desc, platform, has_upsell_or_bundle, notes (<=30 words).", SiteCheck))
                client.collection("adlib_pages").document(slug(lead["page"])).set({"site_check": {**sc.model_dump(), "checked_at": now()}}, merge=True)
                n += 1
            except BudgetExhausted:
                return n
            except Exception as e:  # noqa: BLE001
                log.warning("deep %s: %s", lead["page"], e)
    return n


# ----------------------------------------------------------------------------- cycle
def run_cycle(max_terms: int = 4, max_minutes: int = 40) -> dict:
    """One hourly cycle: harvest a few queued terms, classify new pages, snowball niche labels into the queue,
    refresh niche verdicts, deep-check a few sweet spots."""
    budget.reset()
    t0 = time.time()
    client = db.get_db()
    seeded = seed_queue()
    done_terms = []
    for t in next_terms(max_terms):
        if (time.time() - t0) / 60 > max_minutes:
            break
        try:
            cards, saved, reported = harvest_term(t["term"])
        except Exception as e:  # noqa: BLE001
            log.error("harvest %s: %s", t["term"], e)
            client.collection("adlib_queue").document(slug(t["term"])).update({"status": "error", "error": str(e)[:200], "done_at": now()})
            continue
        client.collection("adlib_queue").document(slug(t["term"])).update({"status": "done", "cards": cards, "saved": saved, "reported": reported, "done_at": now()})
        done_terms.append((t["term"], cards, reported))
    pages = classify_new_pages(limit=250)
    new_terms = 0
    touched = set()
    for p in pages:
        if p["digital_product"] and p["niche_slug"] not in ("app", "unknown"):
            touched.add(p["niche_slug"])
            new_terms += enqueue(p["niche"], "snowball", 5)
    niches = rebuild_niches(touched or None)
    deep = deep_check(limit=5)
    res = {"seeded": seeded, "terms": done_terms, "pages_classified": len(pages), "digital_pages": sum(p["digital_product"] for p in pages),
           "new_terms": new_terms, "niches_touched": len(niches), "deep_checked": deep, "minutes": round((time.time() - t0) / 60, 1)}
    log.info("adlib cycle: %s", res)
    return res


def report(limit: int = 80) -> dict:
    client = db.get_db()
    niches = [d.to_dict() for d in client.collection("adlib_niches").stream() if "leaders" in d.to_dict()]
    order = {"SWEET_SPOT": 0, "SWEET_BUT_FACE": 1, "PENDING": 2, "UNPROVEN": 3, "CROWDED": 4}
    niches.sort(key=lambda r: (order.get(r["verdict"], 9), -r["competitors"]))
    q = Counter(d.to_dict()["status"] for d in client.collection("adlib_queue").stream())
    return {"queue": dict(q), "ads": db.count("adlib_ads"), "pages": db.count("adlib_pages"), "niches": len(niches),
            "by_verdict": dict(Counter(n["verdict"] for n in niches)), "top": niches[:limit]}
