"""Digital-product niche discovery on the Meta Ad Library (Giovanni's method, automated):
for each niche keyword → scan the public Ad Library → keep advertisers whose ad text really sells a digital
product in that niche (cheap LLM filter) → count how many run continuously for 3+ months and are still active.
Sweet spot: 1-2 long-running active advertisers (someone is paying for months = it sells; not crowded = room to enter).
Zero = nobody proved it; 3+ = crowded. Results in Firestore `adlib_niches/{slug}` and a printed table.

  python -X utf8 -m scripts.adlib_discover                # default keyword list
  python -X utf8 -m scripts.adlib_discover "kw one" "kw two"
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timezone

from pydantic import BaseModel

from app import db
from app.services.analysis import llm_json
from scripts.adlib_scan import fetch, parse, summarize

# niches phrased the way the advertisers write them (English = the paid-traffic market that matters)
KEYWORDS = [
    "done for you scripts", "script library", "meditation scripts", "hypnosis scripts", "yoga nidra scripts",
    "done for you worksheets", "therapy worksheets", "counseling worksheets bundle", "coaching templates", "coaching toolkit",
    "canva templates for coaches", "social media templates bundle", "notion template", "spreadsheet template", "excel dashboard template",
    "printable planner", "digital planner", "budget planner template", "wedding planner template", "meal plan template",
    "lesson plans bundle", "teacher resources bundle", "homeschool printables", "speech therapy materials", "occupational therapy printables",
    "resume template", "cover letter template", "interview questions guide", "pitch deck template", "business plan template",
    "contract templates", "legal templates bundle", "lease agreement template", "nda template", "invoice template",
    "recipe ebook", "workout program pdf", "12 week program", "prompt pack", "chatgpt prompts bundle",
    "lightroom presets", "procreate brushes", "fonts bundle", "svg bundle", "embroidery patterns",
    "sewing patterns pdf", "crochet patterns", "knitting patterns", "woodworking plans", "3d print files",
    "sheet music pdf", "guitar tabs", "sample pack", "drum kit samples", "lut pack",
    "dental practice templates", "veterinary forms", "nursing study guide", "nclex study guide", "cpa exam notes",
    "real estate agent templates", "airbnb host templates", "salon forms", "photography contracts", "wedding photography guide",
    "trucking dispatch forms", "cleaning business forms", "landscaping business forms", "hvac forms", "electrician forms",
]


class Verdict(BaseModel):
    relevant: bool
    product_type: str  # e.g. "pdf bundle", "course", "app", "physical", "service", "other"
    niche_note: str


def classify(keyword: str, page: dict) -> Verdict:
    prompt = (f"Ad Library research. Keyword niche: '{keyword}'. Advertiser page: '{page['page']}'. Ad text: {page['sample'][:400]!r}\n"
              "relevant=true ONLY if the ad text itself offers, for sale, a DOWNLOADABLE digital product of exactly this niche "
              "(files, templates, scripts, printables, ebook, presets, patterns, a self-paced course about producing/using them). "
              "relevant=false for: apps/SaaS, physical goods, live coaching/services/certifications, agencies, personal-growth programs, "
              "memberships or brands like Mindvalley, and any ad that does not explicitly mention the product type. Be strict: when in doubt, false.")
    try:
        return Verdict(**llm_json(prompt, Verdict))
    except Exception as e:  # noqa: BLE001
        return Verdict(relevant=False, product_type="unknown", niche_note=f"llm error {e}"[:80])


def analyse(keyword: str, scroll: int = 12) -> dict:
    txt = fetch(keyword, scroll, "ALL")
    total, ads = parse(txt)
    pages = summarize(ads)
    keep = []
    for p in pages[:30]:
        if p["days_running"] < 30 and p["active_ads"] == 0:
            continue  # short dead tests: no signal either way
        toks = [t for t in keyword.lower().split() if len(t) > 3 and t not in ("done", "bundle", "template", "templates", "guide")]
        hay = (p["page"] + " " + p["sample"]).lower()
        if toks and not any(t.rstrip("s") in hay for t in toks):
            continue  # ad text never names the niche: skip the LLM
        v = classify(keyword, p)
        if v.relevant:
            keep.append({**p, "product_type": v.product_type, "note": v.niche_note})
    long_active = [p for p in keep if p["active_ads"] > 0 and p["days_running"] >= 90]
    long_dead = [p for p in keep if p["active_ads"] == 0 and p["days_running"] >= 90]
    n = len(long_active)
    verdict = ("SWEET_SPOT" if 1 <= n <= 2 else "CROWDED" if n >= 3 else "UNPROVEN")
    if len(long_dead) >= max(2, 2 * n):
        verdict = "ABANDONED"  # several advertisers ran 3+ months and left: the niche burns money (meditation scripts pattern)
    return {"keyword": keyword, "slug": re.sub(r"[^a-z0-9]+", "_", keyword.lower()).strip("_"), "results_reported": total, "ads_seen": len(ads),
            "advertisers_seen": len(pages), "relevant": len(keep), "long_running_active": n, "long_running_stopped": len(long_dead),
            "verdict": verdict, "pages": keep, "scanned_at": datetime.now(timezone.utc).isoformat()}


def main(keywords: list[str]):
    rows = []
    for kw in keywords:
        try:
            r = analyse(kw)
        except Exception as e:  # noqa: BLE001
            print("ERR", kw, e); continue
        rows.append(r)
        db.get_db().collection("adlib_niche_checks").document(r["slug"]).set(r, merge=True)
        act = ", ".join(f"{p['page']}({p['days_running']}d)" for p in r["pages"] if p["active_ads"] and p["days_running"] >= 90)
        print(f"{r['verdict']:10s} {kw[:34]:34s} reported {str(r['results_reported']):>8s} | rilevanti {r['relevant']:2d} | attivi 3m+ {r['long_running_active']} | fermati 3m+ {r['long_running_stopped']} | {act[:100]}", flush=True)
    json.dump(rows, open("scratch_adlib_discover.json", "w"), indent=1, default=str)
    print("\nSWEET SPOT:", [r["keyword"] for r in rows if r["verdict"] == "SWEET_SPOT"])


if __name__ == "__main__":
    main(sys.argv[1:] or KEYWORDS)
