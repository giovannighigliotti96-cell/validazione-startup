"""Broad-first digital-product discovery on the Meta Ad Library (Marco Cappelli method, automated).

Phase 1 HARVEST   generic terms x markets -> every ad card (page, dates, active, text, destination domain, video/image)
Phase 2 CLASSIFY  one cheap-LLM call per advertiser page: digital product? what? niche label? faceless brand or a
                  named professional (lawyer, MD, coach with credentials) whose face/credentials sell it?
Phase 3 CLUSTER   merge niche labels into canonical niches; per niche count advertisers, long-running (90d+) active,
                  stopped, faceless share, media mix -> SWEET_SPOT (1-2 long-running active, faceless-competable)
Phase 4 DEEP      for sweet spots: read the destination site, confirm product/price/who is behind it.

State lives in Firestore: adlib_ads/{ad_id}, adlib_pages/{page_slug}, adlib_niches_broad/{niche_slug}.

  set LLM_MAX_CALLS_PER_RUN=5000
  python -X utf8 -m scripts.adlib_broad harvest [--countries US,GB,IT] [--scrolls 60] [--terms "a,b"]
  python -X utf8 -m scripts.adlib_broad classify
  python -X utf8 -m scripts.adlib_broad cluster
  python -X utf8 -m scripts.adlib_broad deep
  python -X utf8 -m scripts.adlib_broad report
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from urllib.parse import urlparse

from pydantic import BaseModel

from app import db
from app.services.analysis import llm_json
from scripts.adlib_scan import DATE_RE, MONTHS

# generic words digital-product sellers put in their ads (EN + IT); the niche emerges from the harvest, not from the query
TERMS_EN = ["instant download", "digital download", "printable", "editable template", "done for you", "pdf guide", "ebook",
            "templates bundle", "swipe file", "script library", "worksheets", "planner", "checklist", "toolkit", "presets",
            "lifetime access", "one time payment", "canva template", "notion template", "excel template", "google sheets template",
            "commercial license", "plr", "mega bundle", "printable pdf", "workbook", "study guide", "cheat sheet", "spreadsheet"]
TERMS_IT = ["download immediato", "scarica subito", "modello editabile", "template", "ebook", "guida pdf", "checklist",
            "planner", "kit completo", "accesso a vita", "pagamento unico", "fogli di lavoro", "schede stampabili", "modelli canva"]
APP_HOSTS = ("play.google.com", "apps.apple.com", "itunes.apple.com")

JS = r"""
() => {
  const out = [];
  const nodes = [...document.querySelectorAll('div,span')].filter(e => e.childElementCount === 0 && /^ID libreria: \d+/.test(e.textContent.trim()));
  for (const n of nodes) {
    let card = n; for (let i = 0; i < 12 && card.parentElement; i++) { card = card.parentElement; if (card.querySelector('video, a[href*="l.facebook.com/l.php"]') && card.textContent.includes('Sponsorizzato')) break; }
    const links = [...card.querySelectorAll('a[href*="l.facebook.com/l.php"]')].map(a => a.href);
    let dest = null; if (links.length) { try { dest = new URL(links[0]).searchParams.get('u'); } catch (e) {} }
    out.push({id: n.textContent.trim().replace('ID libreria: ', ''), video: !!card.querySelector('video'), imgs: card.querySelectorAll('img').length, dest, text: card.innerText.slice(0, 1800)});
  }
  return out;
}"""

SKIP_LINES = ("Inserzioni che usano", "Apri il menu", "Vedi ", "Scopri di più", "Acquista", "Ulteriori informazioni")


def _d(m) -> date:
    return date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))


def parse_card(c: dict, keyword: str, country: str) -> dict | None:
    lines = [x.strip() for x in c["text"].splitlines() if x.strip() and x.strip() != "​"]
    if "Sponsorizzato" not in lines:
        return None
    k = lines.index("Sponsorizzato")
    page = lines[k - 1] if k else None
    head = "\n".join(lines[:k])
    active = "Attiva" in lines[:3]
    ds = list(DATE_RE.finditer(head))
    start = _d(ds[0]) if ds else None
    end = _d(ds[1]) if len(ds) > 1 else (None if active else start)
    body = [x for x in lines[k + 1:] if not x.startswith(SKIP_LINES)]
    mm = re.search(r"Inserzioni che usano questa creativit\S* e questo testo: (\d+)", head)
    host = urlparse(c["dest"]).netloc.lower().replace("www.", "") if c.get("dest") else None
    return {"id": c["id"], "page": page, "active": active, "start": start.isoformat() if start else None, "end": end.isoformat() if end else None,
            "text": " ".join(body)[:900], "dest": (c.get("dest") or "")[:300], "host": host, "video": bool(c["video"]),
            "variants": int(mm.group(1)) if mm else 1, "keyword": keyword, "country": country, "seen_at": datetime.now(timezone.utc).isoformat()}


def harvest(terms: list[str], countries: list[str], scrolls: int = 60) -> None:
    from playwright.sync_api import sync_playwright

    col = db.get_db().collection("adlib_ads")
    with sync_playwright() as p:
        b = p.chromium.launch()
        for country in countries:
            for term in terms:
                pg = b.new_page(viewport={"width": 1300, "height": 900}, locale="it-IT")
                url = (f"https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country={country}&q={term.replace(' ', '%20')}"
                       f"&search_type=keyword_unordered&media_type=all")
                try:
                    pg.goto(url, wait_until="domcontentloaded")
                    time.sleep(6)
                    last = 0
                    for i in range(scrolls):
                        pg.mouse.wheel(0, 5000)
                        time.sleep(1.4)
                        if i % 15 == 14:
                            n = pg.evaluate("() => document.querySelectorAll('div,span').length")
                            if n == last:
                                break
                            last = n
                    cards = pg.evaluate(JS)
                except Exception as e:  # noqa: BLE001
                    print("ERR", country, term, e)
                    pg.close()
                    continue
                pg.close()
                saved = 0
                batch = db.get_db().batch()
                nb = 0
                for c in cards:
                    a = parse_card(c, term, country)
                    if not a or not a["page"]:
                        continue
                    batch.set(col.document(a["id"]), a, merge=True)
                    nb += 1
                    saved += 1
                    if nb >= 400:
                        batch.commit()
                        batch = db.get_db().batch()
                        nb = 0
                if nb:
                    batch.commit()
                print(f"{country} {term!r}: {len(cards)} cards, {saved} saved", flush=True)
        b.close()


class PageVerdict(BaseModel):
    digital_product: bool
    product: str
    niche: str
    audience: str
    format: str  # pdf|template|course|bundle|app|physical|service|other
    faceless: bool
    who_is_behind: str
    price: str


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")[:80] or "x"


CLASSIFY_PROMPT = (
    "Ad Library research on digital products. Advertiser page: '{page}'. Destination site: '{host}'. Ad texts:\n{texts}\n\n"
    "Questions. digital_product: true only if the ads sell a DOWNLOADABLE/online-access product (pdf, templates, printables, scripts, "
    "ebook, presets, patterns, spreadsheets, self-paced course or bundle) - not apps/SaaS, not physical goods, not live services, "
    "not coaching calls, not lead magnets for an agency. product: what exactly is sold (<=12 words). niche: a short generic English "
    "label of the market (2-5 words, e.g. 'divorce agreement templates', 'therapy worksheets', 'lightroom presets'). audience: who buys. "
    "format: pdf|template|course|bundle|app|physical|service|other. faceless: true if sold by a brand/shop with no named expert; "
    "false if a named person or professional (lawyer, MD, therapist, coach, teacher with credentials) is the selling point. "
    "who_is_behind: brand or person description (<=10 words). price: as written in the ads, else ''.")


def classify(limit: int = 100000) -> None:
    client = db.get_db()
    ads = [d.to_dict() for d in client.collection("adlib_ads").stream()]
    by_page: dict[str, list[dict]] = defaultdict(list)
    for a in ads:
        by_page[a["page"]].append(a)
    done = {d.id for d in client.collection("adlib_pages").select([]).stream()}
    todo = [(p, items) for p, items in by_page.items() if _slug(p) not in done][:limit]
    print(f"pages {len(by_page)}, to classify {len(todo)}", flush=True)
    for i, (page, items) in enumerate(todo):
        hosts = Counter(a["host"] for a in items if a["host"])
        host = hosts.most_common(1)[0][0] if hosts else ""
        texts = sorted({a["text"] for a in items if a["text"]}, key=len, reverse=True)[:3]
        if host and any(h in host for h in APP_HOSTS):
            v = PageVerdict(digital_product=False, product="mobile app", niche="app", audience="", format="app", faceless=True, who_is_behind="app publisher", price="")
        elif not texts:
            v = PageVerdict(digital_product=False, product="", niche="unknown", audience="", format="other", faceless=True, who_is_behind="", price="")
        else:
            prompt = CLASSIFY_PROMPT.format(page=page, host=host or "unknown", texts="\n---\n".join(t[:600] for t in texts))
            try:
                v = PageVerdict(**llm_json(prompt, PageVerdict))
            except Exception as e:  # noqa: BLE001
                print("llm err", page, str(e)[:80])
                continue
        starts = [a["start"] for a in items if a["start"]]
        active = [a for a in items if a["active"]]
        first = min(starts) if starts else None
        last = (date.today().isoformat() if active else max((a["end"] or a["start"]) for a in items if a["start"])) if starts else None
        days = (date.fromisoformat(last) - date.fromisoformat(first)).days if first and last else 0
        doc = {**v.model_dump(), "page": page, "niche_slug": _slug(v.niche), "host": host, "ads": len(items), "active_ads": len(active),
               "video_ads": sum(a["video"] for a in items), "first_seen": first, "last_seen": last, "days_running": days,
               "countries": sorted({a["country"] for a in items}), "keywords": sorted({a["keyword"] for a in items}),
               "sample": texts[0][:300] if texts else "", "classified_at": datetime.now(timezone.utc).isoformat()}
        client.collection("adlib_pages").document(_slug(page)).set(doc, merge=True)
        if i % 25 == 0:
            print(f"  {i}/{len(todo)} {page[:40]!r} -> digital={v.digital_product} niche={v.niche!r} faceless={v.faceless}", flush=True)


class Merge(BaseModel):
    mapping: dict[str, str]


def cluster() -> None:
    client = db.get_db()
    pages = [d.to_dict() for d in client.collection("adlib_pages").stream()]
    digital = [p for p in pages if p.get("digital_product")]
    labels = sorted({p["niche"] for p in digital})
    print(f"digital-product advertisers {len(digital)} / {len(pages)} pages; raw niche labels {len(labels)}", flush=True)
    canon: dict[str, str] = {}
    for i in range(0, len(labels), 120):
        chunk = labels[i:i + 120]
        prompt = ("Merge these market-niche labels into canonical niches: map each label to a canonical label (reuse an existing label from the list "
                  "as the canonical one; merge only true synonyms or the same product-for-same-audience, keep distinct markets distinct, e.g. "
                  "'therapy worksheets' != 'teacher worksheets'). Return mapping {label: canonical} covering EVERY label.\n" + json.dumps(chunk))
        try:
            m = Merge(**llm_json(prompt, Merge)).mapping
        except Exception as e:  # noqa: BLE001
            print("merge err", str(e)[:80])
            m = {}
        for lab in chunk:
            canon[lab] = m.get(lab, lab)
    groups: dict[str, list[dict]] = defaultdict(list)
    for p in digital:
        groups[canon.get(p["niche"], p["niche"])].append(p)
    out = []
    for niche, items in groups.items():
        long_active = [p for p in items if p["active_ads"] > 0 and p["days_running"] >= 90]
        long_stop = [p for p in items if p["active_ads"] == 0 and p["days_running"] >= 90]
        faced = [p for p in long_active if not p["faceless"]]
        n = len(long_active)
        verdict = "SWEET_SPOT" if 1 <= n <= 2 else "CROWDED" if n >= 3 else "UNPROVEN"
        if len(long_stop) >= max(2, 2 * n):
            verdict = "ABANDONED"
        if verdict == "SWEET_SPOT" and len(faced) == n:
            verdict = "SWEET_BUT_FACE"  # the only long-runners are named professionals: can't compete faceless
        leaders = sorted(items, key=lambda x: (-bool(x["active_ads"]), -x["days_running"]))[:6]
        doc = {"niche": niche, "slug": _slug(niche), "advertisers": len(items), "long_running_active": n, "long_running_stopped": len(long_stop),
               "active_any": sum(1 for p in items if p["active_ads"]), "faceless_share": round(sum(1 for p in items if p["faceless"]) / len(items), 2),
               "video_share": round(sum(p["video_ads"] for p in items) / max(1, sum(p["ads"] for p in items)), 2), "verdict": verdict,
               "leaders": [{"page": p["page"], "days": p["days_running"], "active": p["active_ads"], "faceless": p["faceless"], "who": p["who_is_behind"],
                            "product": p["product"], "price": p["price"], "host": p["host"], "countries": p["countries"]} for p in leaders],
               "updated_at": datetime.now(timezone.utc).isoformat()}
        out.append(doc)
        client.collection("adlib_niches_broad").document(doc["slug"]).set(doc)
    json.dump(out, open("scratch_adlib_broad_niches.json", "w"), indent=1, default=str)
    report(out)


class SiteCheck(BaseModel):
    product: str
    price: str
    named_expert: bool
    expert_desc: str
    platform: str  # shopify|etsy|gumroad|systeme|clickfunnels|wordpress|other
    has_upsell_or_bundle: bool
    notes: str


def _platform(url: str, html: str) -> str:
    if "cdn.shopify" in html:
        return "shopify"
    for k in ("etsy", "gumroad", "systeme", "clickfunnels"):
        if k in url or k in html[:20000]:
            return k
    return "wordpress" if "wp-content" in html else "other"


def deep() -> None:
    import requests

    client = db.get_db()
    for d in client.collection("adlib_niches_broad").where("verdict", "in", ["SWEET_SPOT", "SWEET_BUT_FACE"]).stream():
        n = d.to_dict()
        for lead in n["leaders"][:3]:
            pref = client.collection("adlib_pages").document(_slug(lead["page"]))
            pg = pref.get().to_dict() or {}
            if pg.get("site_check"):
                continue
            ads = [a.to_dict() for a in client.collection("adlib_ads").where("page", "==", lead["page"]).limit(5).stream()]
            url = next((a["dest"] for a in ads if a.get("dest")), None)
            if not url:
                continue
            try:
                html = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"}).text
                text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
                text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))[:6000]
                sc = SiteCheck(**llm_json(f"Landing page text of an advertiser ({url}). Platform hint: {_platform(url, html)}.\n{text}\n\nExtract: product sold, "
                                          "price, named_expert (is a named person with credentials/photo the selling point?), expert_desc, platform, "
                                          "has_upsell_or_bundle, notes (<=30 words).", SiteCheck))
                check = {**sc.model_dump(), "url": url, "checked_at": datetime.now(timezone.utc).isoformat()}
                pref.set({"site_check": check}, merge=True)
                print(f"{n['niche'][:30]:30s} {lead['page'][:30]:30s} {sc.price:>10s} expert={sc.named_expert} {sc.platform} | {sc.product[:60]}", flush=True)
            except Exception as e:  # noqa: BLE001
                print("deep err", lead["page"], str(e)[:80])


def report(out: list[dict] | None = None) -> None:
    out = out or [d.to_dict() for d in db.get_db().collection("adlib_niches_broad").stream()]
    order = {"SWEET_SPOT": 0, "SWEET_BUT_FACE": 1, "UNPROVEN": 2, "CROWDED": 3, "ABANDONED": 4}
    out.sort(key=lambda r: (order.get(r["verdict"], 9), -r["long_running_active"], -r["advertisers"]))
    print(f"\n{'VERDETTO':15s} {'NICCHIA':42s} adv  3m+att  3m+stop faceless video | leader")
    for r in out:
        if r["verdict"] == "UNPROVEN" and r["advertisers"] < 2:
            continue
        lead = r["leaders"][0] if r["leaders"] else {}
        print(f"{r['verdict']:15s} {r['niche'][:42]:42s} {r['advertisers']:3d}  {r['long_running_active']:5d}  {r['long_running_stopped']:6d}  "
              f"{r['faceless_share']:.2f}    {r['video_share']:.2f} | {lead.get('page', '')[:28]} {lead.get('days', '')}d "
              f"{'brand' if lead.get('faceless') else 'PERSONA'} {lead.get('price', '')}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    args = sys.argv[2:]

    def opt(k: str, d: str) -> str:
        return args[args.index(k) + 1] if k in args else d

    if cmd == "harvest":
        terms = opt("--terms", "").split(",") if "--terms" in args else (TERMS_EN + TERMS_IT)
        harvest(terms, opt("--countries", "US,GB,IT").split(","), int(opt("--scrolls", "60")))
    elif cmd == "classify":
        classify(int(opt("--limit", "100000")))
    elif cmd == "cluster":
        cluster()
    elif cmd == "deep":
        deep()
    else:
        report()
