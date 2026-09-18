"""Meta Ad Library scanner (public web UI, no login): for a keyword, collect ads, group by advertiser page,
and measure how long each page has been advertising continuously. Used to spot digital-product niches
with 1-2 long-running advertisers (someone paying for 3+ months = the product sells).

  python -m scripts.adlib_scan "meditation scripts" --scroll 12 --country ALL
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import defaultdict
from datetime import date, datetime

MONTHS = {"gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6, "lug": 7, "ago": 8, "set": 9, "ott": 10, "nov": 11, "dic": 12}
DATE_RE = re.compile(r"(\d{1,2}) (gen|feb|mar|apr|mag|giu|lug|ago|set|ott|nov|dic) (\d{4})")
STOP = {"", "​", "Piattaforme", "Sponsorizzato", "Apri il menu a discesa", "Vedi i dettagli di riepilogo", "Vedi dettagli inserzione"}


def _date(s: str) -> date | None:
    m = DATE_RE.search(s)
    return date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1))) if m else None


def fetch(keyword: str, scroll: int = 10, country: str = "ALL", status: str = "all") -> str:
    from playwright.sync_api import sync_playwright

    q = keyword.replace(" ", "%20")
    url = (f"https://www.facebook.com/ads/library/?active_status={status}&ad_type=all&country={country}&q={q}"
           f"&search_type=keyword_unordered&media_type=all")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1300, "height": 900}, locale="it-IT")
        pg.goto(url, wait_until="domcontentloaded")
        time.sleep(7)
        for _ in range(scroll):
            pg.mouse.wheel(0, 4000)
            time.sleep(2.2)
        txt = pg.inner_text("body")
        b.close()
    return txt


def parse(txt: str) -> tuple[str | None, list[dict]]:
    lines = [ln.strip() for ln in txt.splitlines()]
    m = re.search(r"~?([\d.]+) risultat", txt)
    total = m.group(1) if m else None
    ads, i = [], 0
    while i < len(lines):
        if lines[i].startswith("ID libreria:"):
            ad = {"id": lines[i].split(":")[1].strip(), "active": lines[i - 1] == "Attiva"}
            j = i + 1
            while j < len(lines) and not DATE_RE.search(lines[j]) and j < i + 4:
                j += 1
            ds = [d for d in DATE_RE.finditer(lines[j])] if j < len(lines) else []
            ad["start"] = _date(lines[j]) if ds else None
            ad["end"] = date(int(ds[1].group(3)), MONTHS[ds[1].group(2)], int(ds[1].group(1))) if len(ds) > 1 else (None if ad["active"] else ad["start"])
            # page name = first "real" line after the platforms block, followed by "Sponsorizzato"
            k = j + 1
            page, body = None, []
            while k < len(lines) and not lines[k].startswith("ID libreria:") and k < j + 60:
                if lines[k] == "Sponsorizzato" and k > 0:
                    page = lines[k - 1]
                    body = [x for x in lines[k + 1:k + 8] if x not in STOP and not x.startswith("Inserzioni che usano")]
                    break
                k += 1
            ad["page"] = page
            ad["text"] = " ".join(body)[:300]
            mm = re.search(r"Inserzioni che usano questa creativit\S* e questo testo: (\d+)", "\n".join(lines[i:i + 12]))
            ad["variants"] = int(mm.group(1)) if mm else 1
            ads.append(ad)
            i = k
        else:
            i += 1
    return total, ads


def summarize(ads: list[dict], today: date | None = None) -> list[dict]:
    today = today or date.today()
    by_page: dict[str, list[dict]] = defaultdict(list)
    for a in ads:
        if a.get("page"):
            by_page[a["page"]].append(a)
    out = []
    for page, items in by_page.items():
        starts = [a["start"] for a in items if a["start"]]
        if not starts:
            continue
        first = min(starts)
        active = [a for a in items if a["active"]]
        last = today if active else max((a["end"] or a["start"]) for a in items if a["start"])
        # continuity: months with at least one ad running
        months = set()
        for a in items:
            if not a["start"]:
                continue
            s, e = a["start"], (today if a["active"] else (a["end"] or a["start"]))
            y, mo = s.year, s.month
            while (y, mo) <= (e.year, e.month):
                months.add((y, mo))
                mo += 1
                if mo > 12:
                    y, mo = y + 1, 1
        span_months = (last.year - first.year) * 12 + last.month - first.month + 1
        out.append({"page": page, "ads": len(items), "active_ads": len(active), "first_seen": first.isoformat(), "last_seen": last.isoformat(),
                    "months_active": len(months), "span_months": span_months, "continuous": len(months) >= span_months - 1,
                    "days_running": (last - first).days, "sample": max(items, key=lambda a: a["variants"])["text"]})
    out.sort(key=lambda r: (-r["active_ads"], -r["days_running"]))
    return out


def scan(keyword: str, scroll: int = 10, country: str = "ALL") -> dict:
    txt = fetch(keyword, scroll, country)
    total, ads = parse(txt)
    pages = summarize(ads)
    strong = [p for p in pages if p["active_ads"] > 0 and p["days_running"] >= 90]
    return {"keyword": keyword, "country": country, "results_reported": total, "ads_seen": len(ads), "advertisers": len(pages),
            "long_running_active": len(strong), "pages": pages, "scanned_at": datetime.utcnow().isoformat()}


if __name__ == "__main__":
    kw = sys.argv[1]
    sc = int(sys.argv[sys.argv.index("--scroll") + 1]) if "--scroll" in sys.argv else 10
    co = sys.argv[sys.argv.index("--country") + 1] if "--country" in sys.argv else "ALL"
    r = scan(kw, sc, co)
    json.dump(r, open("scratch_adlib_scan.json", "w"), indent=1, default=str)
    print(f"{kw!r}: reported {r['results_reported']} | seen {r['ads_seen']} ads | {r['advertisers']} advertisers | long-running active: {r['long_running_active']}")
    for p in r["pages"][:40]:
        print(f"  {p['page'][:40]:40s} ads {p['ads']:3d} active {p['active_ads']:3d} {p['first_seen']} → {p['last_seen']} ({p['days_running']}d, {p['months_active']}/{p['span_months']} mesi) | {p['sample'][:90]}")
