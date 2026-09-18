"""Poltrona Libera — Meta Ads DRAFT (everything PAUSED): 1 campaign, 2 ad sets (titolari / professioniste), Milano 25 km,
manual targeting (no Advantage+ audience), 3 single-image ads (feed/story/reels variants) + 2 carousels per ad set.

Best practices applied: OUTCOME_LEADS with pixel Lead event, lowest cost, one ad set per audience, 3-5 distinct creatives
(different visual AND message), primary text front-loaded (< 125 chars before the fold), headline <= 40, CTA Sign up,
UTM per ad, placements Facebook feed/story/reels + Instagram feed/story/reels, Italian locale, age bands per audience.

Run:  python -m scripts.meta_poltrona create | status | activate | pause
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.meta_campaign import call, env, set_status, status  # noqa: E402

BASE = "https://validazione-startup-148506634481.europe-west1.run.app"
FOLDER = "creatives/poltrona"
BRAND = "Poltrona Libera"
MILANO = {"latitude": 45.4642, "longitude": 9.19, "radius": 25, "distance_unit": "kilometer"}

# verified with /search type=adinterest and adworkposition on 2026-09-18 (professional signals only, no consumer hair-care interests)
PRO_INTERESTS = [{"id": "6003420035719", "name": "Davines"}, {"id": "6013863993356", "name": "Alfaparf Milano"}, {"id": "6003415798806", "name": "Hairdressers Journal"},
                 {"id": "6003217002665", "name": "Paul Mitchell (hairdresser)"}]  # CosmoProf and Barberia are deprecated on Meta (2026-09)
OWNER_JOBS = [{"id": "104291459629941", "name": "Hairdresser/Salon Owner"}, {"id": "144734248878211", "name": "Senior Hairdresser"}, {"id": "142566132433276", "name": "Owner/Barber"}]
STYLIST_JOBS = [{"id": "146841145351887", "name": "Hair Designer/Stylist"}, {"id": "138187402901447", "name": "Hair Stylist, colorist and Make-up artist"},
                {"id": "165586750150037", "name": "Hair Stylist & Hair Colorist"}, {"id": "107830429245196", "name": "Barber"}, {"id": "808626149192249", "name": "Barber Stylist"},
                {"id": "143282895701680", "name": "Apprentice Hairdresser"}]

ADSETS = {
    "titolari": {
        "name": "Titolari · Milano 25km · 28-62 · interessi pro + job title", "landing": f"{BASE}/lp/poltrona_libera_titolari", "age": (28, 62),
        "flexible_spec": [{"interests": PRO_INTERESTS, "work_positions": OWNER_JOBS}],
        "ads": [
            {"subject": "reddito", "primary": "La poltrona vuota del tuo salone rende 500 € al mese. Selezione, contratto, SUAP e incasso li facciamo noi: tu ricevi il canone entro il 5. Zero costi fissi, 15% solo quando è occupata. Stiamo partendo a Milano.",
             "headline": "Postazione vuota? Rende 500 €/mese", "description": "Gestita da noi. Zero costi fissi."},
            {"subject": "personale", "primary": "Non trovi personale? Affitta la postazione a una professionista con P.IVA: porta le sue clienti, paga un canone, non è una dipendente. Annuncio anonimo, contratto a norma dal 2018, incasso gestito da noi.",
             "headline": "Non trovi personale? Affitta la poltrona", "description": "Contratto e SUAP inclusi."},
            {"subject": "gestito", "primary": "Incasso gestito e sostituzione inclusa. Se la professionista lascia, la sostituiamo noi; se non paga, non rincorri nessuno. Tratteniamo il 15% solo nei mesi in cui la postazione rende. Primi 30 saloni di Milano: 10%.",
             "headline": "Zero sbattimento, canone entro il 5", "description": "Primi 30 saloni: 10%."},
            {"subject": "carousel_come", "carousel": True, "primary": "Come funziona l'affitto di poltrona gestito da noi, in 4 passi. Per te nessun costo fisso: tratteniamo il 15% solo quando la postazione è occupata.",
             "headline": "Come funziona", "cards": ["Ci dai in gestione la postazione", "Selezioniamo e organizziamo le visite", "Contratto e SUAP li prepariamo noi", "Incassiamo noi, ti giriamo l'85%", "Affitta la tua postazione"]},
            {"subject": "carousel_faq", "carousel": True, "primary": "\"Mi porta via le clienti?\" \"È legale?\" \"Cosa vi costa?\" Le 5 domande che ci fanno tutte le titolari, con le risposte. Stiamo partendo a Milano.",
             "headline": "Le domande delle titolari", "cards": ["Mi porta via le clienti?", "È legale?", "E la mia ex dipendente?", "Cosa vi costa?", "E se non paga?"]},
        ],
    },
    "professioniste": {
        "name": "Professioniste · Milano 25km · 22-50 · freelance/domicilio + job title + interessi pro", "landing": f"{BASE}/lp/poltrona_libera_professioniste", "age": (22, 50),
        "flexible_spec": [{"interests": PRO_INTERESTS, "work_positions": STYLIST_JOBS + [{"id": "121890827856661", "name": "Mobile Hairdresser"}]}],
        "ads": [
            {"subject": "reddito", "primary": "Lavora in proprio senza aprire un salone: postazioni a Milano da 400 € al mese, in saloni veri. Le clienti sono tue, gli orari sono tuoi, l'incasso è tuo. Guardi, visiti, poi decidi.",
             "headline": "In proprio, senza aprire un salone", "description": "Postazioni da 400 €/mese."},
            {"subject": "personale", "primary": "Stanca di lavorare per il 40% di uno stipendio? Con una postazione in affitto tieni il 100% di quello che incassi. Contratto a norma, mese di prova, aiuto per la P.IVA. Milano.",
             "headline": "Tieni il 100% di quello che incassi", "description": "Contratto a norma, mese di prova."},
            {"subject": "gestito", "primary": "Zero investimento: niente locale, niente attrezzature, niente fideiussioni. Solo una postazione in un salone di Milano, con canone chiaro e cosa è incluso. Visita gratis, firmi solo se ti convince.",
             "headline": "Zero investimento, una postazione tua", "description": "Visite gratis a Milano."},
            {"subject": "domicilio", "primary": "Lavori a domicilio e hai già la P.IVA? Ti manca solo il posto. Postazioni in saloni veri di Milano da 400 € al mese: lavatesta, luce, specchio, e le clienti vengono da te. Contratto a norma, SCIA e registrazione li facciamo noi.",
             "headline": "A domicilio? Prenditi una poltrona vera", "description": "Saloni di Milano, da 400 €/mese."},
        ],
    },
}


def upload(tok: str, acc: str) -> dict[str, str]:
    cache = os.path.join(FOLDER, ".meta_hashes.json")
    hashes = json.load(open(cache)) if os.path.exists(cache) else {}
    for fn in sorted(os.listdir(FOLDER)):
        if not fn.endswith(".png") or fn in hashes:
            continue
        with open(os.path.join(FOLDER, fn), "rb") as f:
            j = call("POST", f"{acc}/adimages", tok, files={"filename": (fn, f, "image/png")})
        hashes[fn] = list(j["images"].values())[0]["hash"]
        json.dump(hashes, open(cache, "w"))
    return hashes


def create(budget_cents: int = 800) -> dict:
    import warnings; warnings.filterwarnings("ignore")
    from app import db

    e = env(); tok, acc, page, pixel = e["META_ACCESS_TOKEN"], e["META_AD_ACCOUNT_ID"], e["META_PAGE_ID"], e["META_PIXEL_ID"]
    name = f"{BRAND} · Milano · test"
    ex = [c for c in call("GET", f"{acc}/campaigns", tok, fields="id,name", limit=50).get("data", []) if c["name"] == name]
    cid = ex[0]["id"] if ex else call("POST", f"{acc}/campaigns", tok, name=name, objective="OUTCOME_LEADS", status="PAUSED", special_ad_categories="[]",
                                       buying_type="AUCTION", is_adset_budget_sharing_enabled="false")["id"]
    hashes = upload(tok, acc)
    # Instagram identity: the Page's page-backed Instagram account (created once via the Page token)
    pt = next(p["access_token"] for p in call("GET", "me/accounts", tok, fields="id,access_token")["data"] if p["id"] == page)
    pbia = call("GET", f"{page}/page_backed_instagram_accounts", pt, fields="id").get("data") or [call("POST", f"{page}/page_backed_instagram_accounts", pt)]
    ig = pbia[0]["id"]
    out = {"campaign_id": cid, "adsets": [], "instagram_actor_id": ig}
    existing_sets = {a["name"]: a["id"] for a in call("GET", f"{cid}/adsets", tok, fields="id,name").get("data", [])}
    for key, cfg in ADSETS.items():
        targeting = {"geo_locations": {"custom_locations": [MILANO]}, "age_min": cfg["age"][0], "age_max": cfg["age"][1], "locales": [10],
                     "flexible_spec": cfg["flexible_spec"], "publisher_platforms": ["facebook", "instagram"],
                     "facebook_positions": ["feed", "story", "facebook_reels"], "instagram_positions": ["stream", "story", "reels"],
                     "targeting_automation": {"advantage_audience": 0}}
        # names changed -> find by key prefix; then keep targeting in sync
        asid = existing_sets.get(cfg["name"]) or next((v for k, v in existing_sets.items() if k.lower().startswith(key)), None) or call("POST", f"{acc}/adsets", tok, name=cfg["name"], campaign_id=cid, status="PAUSED", daily_budget=budget_cents,
                                                      billing_event="IMPRESSIONS", optimization_goal="OFFSITE_CONVERSIONS",
                                                      promoted_object=json.dumps({"pixel_id": pixel, "custom_event_type": "LEAD"}),
                                                      bid_strategy="LOWEST_COST_WITHOUT_CAP", targeting=json.dumps(targeting))["id"]
        if existing_sets:
            call("POST", asid, tok, name=cfg["name"], targeting=json.dumps(targeting))
        ex_ads = {a["name"]: a["id"] for a in call("GET", f"{asid}/ads", tok, fields="id,name").get("data", [])}
        for name_, id_ in list(ex_ads.items()):
            if name_.endswith("· personale"):  # image regenerated: recreate the ad with the new creative
                call("POST", id_, tok, status="DELETED"); ex_ads.pop(name_)
        ads = []
        for ad in cfg["ads"]:
            ad_name = f"{BRAND} · {key} · {ad['subject']}"
            if ad_name in ex_ads:
                ads.append({"ad_id": ex_ads[ad_name], "name": ad_name, "note": "existing"}); continue
            link = f"{cfg['landing']}?utm_source=meta&utm_medium=paid&utm_campaign=poltrona_milano&utm_content={key}_{ad['subject']}"
            if ad.get("carousel"):
                cards = [{"image_hash": hashes[f"{ad['subject']}_{i}.png"], "name": t[:40], "description": "", "link": link} for i, t in enumerate(ad["cards"], 1)]
                oss = {"page_id": page, "instagram_user_id": ig, "link_data": {"link": link, "message": ad["primary"], "name": ad["headline"][:40], "child_attachments": cards,
                                                      "call_to_action": {"type": "SIGN_UP", "value": {"link": link}}, "multi_share_optimized": False, "multi_share_end_card": False}}
                cr = call("POST", f"{acc}/adcreatives", tok, name=ad_name, object_story_spec=json.dumps(oss), instagram_user_id=ig)
            else:
                h1, h45, h916 = hashes.get(f"{ad['subject']}_1x1.png"), hashes.get(f"{ad['subject']}_4x5.png"), hashes.get(f"{ad['subject']}_9x16.png")
                afs = {"images": [{"hash": h, "adlabels": [{"name": lab}]} for h, lab in ((h1, "sq"), (h45, "p45"), (h916, "v916")) if h],
                       "bodies": [{"text": ad["primary"]}], "titles": [{"text": ad["headline"][:40]}], "descriptions": [{"text": ad.get("description", "")[:30]}],
                       "link_urls": [{"website_url": link}], "call_to_action_types": ["SIGN_UP"], "ad_formats": ["SINGLE_IMAGE"],
                       "asset_customization_rules": [
                           {"customization_spec": {"publisher_platforms": ["facebook", "instagram"], "facebook_positions": ["story", "facebook_reels"], "instagram_positions": ["story", "reels"]}, "image_label": {"name": "v916"}},
                           {"customization_spec": {"publisher_platforms": ["instagram"], "instagram_positions": ["stream"]}, "image_label": {"name": "p45"}},
                           {"customization_spec": {"publisher_platforms": ["facebook"], "facebook_positions": ["feed"]}, "image_label": {"name": "sq"}}]}
                cr = call("POST", f"{acc}/adcreatives", tok, name=ad_name, object_story_spec=json.dumps({"page_id": page, "instagram_user_id": ig}), asset_feed_spec=json.dumps(afs), instagram_user_id=ig)
            a = call("POST", f"{acc}/ads", tok, name=ad_name, adset_id=asid, status="PAUSED", creative=json.dumps({"creative_id": cr["id"]}))
            ads.append({"ad_id": a["id"], "creative_id": cr["id"], "name": ad_name})
        out["adsets"].append({"key": key, "adset_id": asid, "daily_budget_eur": budget_cents / 100, "ads": ads})
    for cid_ in ("poltrona_libera_titolari", "poltrona_libera_professioniste"):
        db.upsert(db.OPPORTUNITY_SCORING, cid_, {"meta_campaign": {**out, "status": "PAUSED"}})
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "create"
    if cmd == "create":
        print(json.dumps(create(int(sys.argv[2]) if len(sys.argv) > 2 else 800), indent=2, ensure_ascii=False))
    else:
        from app import db

        camp = (db.get(db.OPPORTUNITY_SCORING, "poltrona_libera_titolari") or {}).get("meta_campaign") or {}
        cid = camp.get("campaign_id")
        print(json.dumps(status(cid) if cmd == "status" else set_status(cid, "ACTIVE" if cmd == "activate" else "PAUSED"), indent=2, ensure_ascii=False))
