"""
Create a Meta Ads smoke-test campaign in PAUSED state (nothing spends until a human activates it).

  python -m scripts.meta_campaign create <cluster_id> <landing_url> <creatives_dir> [--budget-cents 800] [--radius-km 25]
  python -m scripts.meta_campaign status <campaign_id>
  python -m scripts.meta_campaign activate <campaign_id>      # explicit human step
  python -m scripts.meta_campaign pause <campaign_id>

Structure: 1 campaign (OUTCOME_LEADS) -> 1 ad set (manual targeting: Milano radius, age 25-60, restaurant interests,
optimization LEAD on the pixel, NO Advantage+ audience) -> N ads (one per creative subject; placement asset customization
maps 1:1 to feed, 4:5 to feed/explore, 9:16 to stories/reels).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import httpx

G = "https://graph.facebook.com/v21.0"


def env() -> dict:
    import os

    d = {k: v for k, v in os.environ.items() if k.startswith(("META_", "CRONJOB_"))}  # Cloud Run: service env vars
    if os.path.exists(".env"):
        for line in open(".env", encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); d[k] = v.split("  #")[0].strip()
    return d


def call(method: str, path: str, tok: str, **params):
    fn = httpx.post if method == "POST" else httpx.get
    files = params.pop("files", None)
    r = fn(f"{G}/{path}", params={"access_token": tok} if method == "GET" else None,
           data={**params, "access_token": tok} if method == "POST" else None, files=files, timeout=60) if method == "POST" else fn(f"{G}/{path}", params={"access_token": tok, **params}, timeout=60)
    j = r.json()
    if "error" in j:
        raise RuntimeError(f"{path}: {j['error'].get('message')} (code {j['error'].get('code')}, sub {j['error'].get('error_subcode')}) :: {j['error'].get('error_user_title')} — {j['error'].get('error_user_msg')}")
    return j


def find_interests(tok: str, terms: list[str]) -> list[dict]:
    out, seen = [], set()
    for t in terms:
        for it in call("GET", "search", tok, type="adinterest", q=t, limit=5).get("data", []):
            if it["id"] not in seen and it.get("audience_size_upper_bound", 0) > 10000:
                seen.add(it["id"]); out.append({"id": it["id"], "name": it["name"]}); break
    return out


def upload_images(tok: str, acc: str, folder: str) -> dict[str, str]:
    """Upload once; cache hashes next to the images (Meta rate-limits repeated uploads)."""
    cache_path = os.path.join(folder, ".meta_hashes.json")
    hashes = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
    for fn in sorted(os.listdir(folder)):
        if not fn.startswith("ad") or not fn.endswith(".png") or fn in hashes:
            continue
        with open(os.path.join(folder, fn), "rb") as f:
            j = call("POST", f"{acc}/adimages", tok, files={"filename": (fn, f, "image/png")})
        hashes[fn] = list(j["images"].values())[0]["hash"]
        json.dump(hashes, open(cache_path, "w"))
    return hashes


def create(cluster_id: str, landing: str, folder: str, budget_cents: int, radius_km: int) -> dict:
    import warnings; warnings.filterwarnings("ignore")
    from app import db

    e = env(); tok, acc, page, pixel = e["META_ACCESS_TOKEN"], e["META_AD_ACCOUNT_ID"], e["META_PAGE_ID"], e["META_PIXEL_ID"]
    o = db.get(db.OPPORTUNITY_SCORING, cluster_id); offer = o["offer"]
    brand = offer.get("product_name") or "Dispensa"
    # hand-picked (automatic search returns brands and TV shows): sector interests only
    interests = [{"id": "6003215365661", "name": "Ristorazione"}, {"id": "6003209775430", "name": "Restaurant management"}]
    print("interests:", [i["name"] for i in interests])
    name = f"{brand} · Milano · lista d'attesa"
    existing = [c for c in call("GET", f"{acc}/campaigns", tok, fields="id,name", limit=20).get("data", []) if c["name"] == name]
    if existing:
        cid = existing[0]["id"]
    else:
        cid = call("POST", f"{acc}/campaigns", tok, name=name, objective="OUTCOME_LEADS", status="PAUSED", special_ad_categories="[]",
                   buying_type="AUCTION", is_adset_budget_sharing_enabled="false")["id"]
    targeting = {
        "geo_locations": {"custom_locations": [{"latitude": 45.4642, "longitude": 9.19, "radius": radius_km, "distance_unit": "kilometer"}]},
        "age_min": 25, "age_max": 60, "locales": [10],  # 10 = Italian
        "flexible_spec": [{"interests": interests}],
        "publisher_platforms": ["facebook", "instagram"],
        "facebook_positions": ["feed", "story", "facebook_reels"], "instagram_positions": ["stream", "story", "reels"],
        "targeting_automation": {"advantage_audience": 0},  # explicit: no Advantage+ audience expansion
    }
    ex_sets = call("GET", f"{cid}/adsets", tok, fields="id,name").get("data", [])
    adset = ex_sets[0] if ex_sets else call("POST", f"{acc}/adsets", tok, name="Milano 25km · ristoratori 25-60", campaign_id=cid, status="PAUSED",
                 daily_budget=budget_cents, billing_event="IMPRESSIONS", optimization_goal="LEAD_GENERATION" if False else "OFFSITE_CONVERSIONS",
                 promoted_object=json.dumps({"pixel_id": pixel, "custom_event_type": "LEAD"}),
                 bid_strategy="LOWEST_COST_WITHOUT_CAP", targeting=json.dumps(targeting))
    asid = adset["id"]
    hashes = upload_images(tok, acc, folder)
    subjects = sorted({fn.split("_")[0] for fn in hashes})
    per_subject = offer.get("ad_set_copies") or {}
    copies = []
    for v in offer["variants"]:
        copies += v.get("ad_copies") or []
    ads = []
    existing_ads = {a["name"].split("· ")[-1]: a["id"] for a in call("GET", f"{asid}/ads", tok, fields="id,name").get("data", [])}
    for i, subj in enumerate(subjects):
        if subj in existing_ads:
            ads.append({"ad_id": existing_ads[subj], "subject": subj, "note": "existing"}); continue
        c = per_subject.get(subj) or (copies[i % len(copies)] if copies else {"primary_text": "Inventario, fornitori e food cost senza fogli e quaderni. Lista d'attesa aperta a Milano.", "headline": "Entra in lista"})
        link = f"{landing}?utm_source=meta&utm_campaign=milano&utm_content={subj}"
        h1, h45, h916 = hashes.get(f"{subj}_1x1.png"), hashes.get(f"{subj}_4x5.png"), hashes.get(f"{subj}_9x16.png")
        spec = {
            "page_id": page,
            "asset_feed_spec": {
                "images": [{"hash": h, "adlabels": [{"name": lab}]} for h, lab in ((h1, "sq"), (h45, "p45"), (h916, "v916")) if h],
                "bodies": [{"text": c.get("primary_text", "")}],
                "titles": [{"text": (c.get("headline") or "Entra in lista")[:40]}],
                "descriptions": [{"text": (c.get("description") or "Prezzo bloccato per i primi 30 locali.")[:30]}],
                "link_urls": [{"website_url": link}],
                "call_to_action_types": ["SIGN_UP"],
                "ad_formats": ["SINGLE_IMAGE"],
                "asset_customization_rules": [
                    {"customization_spec": {"publisher_platforms": ["facebook", "instagram"], "facebook_positions": ["story", "facebook_reels"], "instagram_positions": ["story", "reels"]}, "image_label": {"name": "v916"}},
                    {"customization_spec": {"publisher_platforms": ["instagram"], "instagram_positions": ["stream"]}, "image_label": {"name": "p45" if h45 else "sq"}},
                    {"customization_spec": {"publisher_platforms": ["facebook"], "facebook_positions": ["feed"]}, "image_label": {"name": "sq"}},
                ],
            },
        }
        cr = call("POST", f"{acc}/adcreatives", tok, name=f"{brand} {subj}", object_story_spec=json.dumps({"page_id": page}),
                  asset_feed_spec=json.dumps(spec["asset_feed_spec"]), use_page_actor_override="true")  # Page represents the brand on Instagram too
        ad = call("POST", f"{acc}/ads", tok, name=f"{brand} · {subj}", adset_id=asid, status="PAUSED", creative=json.dumps({"creative_id": cr["id"]}))
        ads.append({"ad_id": ad["id"], "creative_id": cr["id"], "subject": subj, "headline": c.get("headline")})
    res = {"campaign_id": cid, "adset_id": asid, "daily_budget_eur": budget_cents / 100, "radius_km": radius_km, "interests": interests, "ads": ads, "status": "PAUSED"}
    db.upsert(db.OPPORTUNITY_SCORING, cluster_id, {"meta_campaign": res})
    return res


def status(campaign_id: str) -> dict:
    tok = env()["META_ACCESS_TOKEN"]
    c = call("GET", campaign_id, tok, fields="name,status,effective_status,daily_budget")
    ins = call("GET", f"{campaign_id}/insights", tok, fields="spend,impressions,clicks,cpc,ctr,actions,cost_per_action_type", date_preset="maximum")
    return {"campaign": c, "insights": ins.get("data", [])}


def set_status(campaign_id: str, st: str) -> dict:
    tok = env()["META_ACCESS_TOKEN"]
    call("POST", campaign_id, tok, status=st)
    for a in call("GET", f"{campaign_id}/adsets", tok, fields="id").get("data", []):
        call("POST", a["id"], tok, status=st)
        for ad in call("GET", f"{a['id']}/ads", tok, fields="id").get("data", []):
            call("POST", ad["id"], tok, status=st)
    return status(campaign_id)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["create", "status", "activate", "pause"])
    p.add_argument("args", nargs="*")
    p.add_argument("--budget-cents", type=int, default=800)
    p.add_argument("--radius-km", type=int, default=25)
    a = p.parse_args()
    if a.cmd == "create":
        print(json.dumps(create(a.args[0], a.args[1], a.args[2], a.budget_cents, a.radius_km), indent=1, ensure_ascii=False))
    elif a.cmd == "status":
        print(json.dumps(status(a.args[0]), indent=1, ensure_ascii=False))
    else:
        print(json.dumps(set_status(a.args[0], "ACTIVE" if a.cmd == "activate" else "PAUSED"), indent=1, ensure_ascii=False))
