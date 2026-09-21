"""Meta campaign (DRAFT, paused) for the two paid guides: objective Sales, pixel Purchase, one ad set per guide (A/B on the
pain angle), 4 ads each, targeting salon owners in Milan (same audience as the owners' lead campaign).
Run:  python -m scripts.meta_guida create [--budget 1000]   (never activates: Giovanni switches it on)"""
from __future__ import annotations

import json
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.meta_campaign import call, env  # noqa: E402
from scripts.meta_poltrona import BRAND, MILANO, OWNER_JOBS, PRO_INTERESTS, upload  # noqa: E402

BASE = "https://poltronalibera.it"
PRICE = "49,90 €"

ADSETS = {
    "squadra": {
        "name": "Guida A · La dipendente è andata via · titolari Milano 28-62",
        "landing": f"{BASE}/pl/guida/squadra",
        "ads": [
            {"subject": "andata_via", "primary": "«Dipendente andata via.» Se è successo anche a te, la guida dice cosa fare nelle prossime 48 ore (le clienti richiamate una per una, la postazione mai vuota), come scrivere l'annuncio che riceve candidature, il colloquio di 20 minuti e i premi sul fatturato che fanno restare la prossima. 24 pagine + kit da stampare, scritta per titolari di salone di Milano. PDF subito, garanzia 14 giorni.",
             "headline": "La dipendente è andata via: cosa fare", "description": f"Guida PDF + kit · {PRICE}"},
            {"subject": "non_trovo", "primary": "«Non trovo personale.» Il problema di solito non è il canale: è l'annuncio. Le 7 regole dell'annuncio che riceve candidature a Milano, 3 modelli pronti da copiare, dove pubblicare (e cosa costa), il colloquio in 20 minuti con le 10 domande giuste. Guida pratica per titolari di salone, 24 pagine + kit.",
             "headline": "Non trovi personale? Non è il canale", "description": f"3 annunci pronti · {PRICE}"},
            {"subject": "maternita", "primary": "«In maternità, e mi ha detto che non rientra.» Si poteva evitare, e si può ancora: il part-time che fa rientrare, la sostituta che ti costa la metà (lo sgravio che quasi nessun salone usa), e il piano dei 90 giorni per ricostruire la squadra. Guida per titolari di salone, 24 pagine + kit da stampare.",
             "headline": "Maternità e non rientra: il piano", "description": f"Guida PDF + kit · {PRICE}"},
            {"subject": "libro", "primary": "Nuova guida per titolari di salone: «La dipendente è andata via». Come ricostruire la squadra in 90 giorni, tenerla, e non ritrovarti mai più con una poltrona vuota. Annunci pronti, scheda colloquio, schema premi da firmare in due, lettera alle clienti, piano dei 90 giorni. PDF subito via email, garanzia 14 giorni.",
             "headline": "Guida: la dipendente è andata via", "description": f"24 pagine + kit · {PRICE}"},
        ],
    },
    "poltrona": {
        "name": "Guida B · Basta dipendenti · titolari Milano 28-62",
        "landing": f"{BASE}/pl/guida/poltrona",
        "ads": [
            {"subject": "basta", "primary": "«Si è licenziato. E ora non voglio più personale.» Allora la postazione vuota può pagarti un canone ogni mese, invece di costarti una busta paga. La guida all'affitto di poltrona per titolari di Milano: i numeri veri, le regole che ti proteggono, formula e prezzo, il contratto in 12 punti, come trovare la professionista giusta in una settimana. 20 pagine + kit.",
             "headline": "Basta dipendenti: la poltrona in affitto", "description": f"Guida PDF + kit · {PRICE}"},
            {"subject": "conto", "primary": "Una dipendente qualificata ti costa circa 2.100 € al mese. La stessa postazione affittata a una professionista in proprio te ne rende 500-1.200, senza contributi, ferie, malattie e preavvisi. Il confronto su 12 mesi, il calcolo del canone per la tua zona, il contratto in 12 punti. Guida per titolari di salone di Milano.",
             "headline": "2.100 € di costo o 500-1.200 € di canone?", "description": f"Il conto, capitolo 2 · {PRICE}"},
            {"subject": "legale", "primary": "Smettere di assumere è legale dal 2012, e a Milano è regolato dal 2018. Ma va fatto bene: quante postazioni puoi affittare, a chi no, cosa scrivere nel contratto (12 punti), come convivere nello stesso salone, gli 8 casi che vanno storti e come evitarli. La guida completa all'affitto di poltrona, 20 pagine + kit.",
             "headline": "Affitto di poltrona: come si fa bene", "description": f"Guida PDF + kit · {PRICE}"},
            {"subject": "libro", "primary": "Nuova guida per titolari di salone: «Basta dipendenti». Affitta le postazioni del tuo salone a professioniste in proprio: canone mensile al posto della busta paga. Numeri, regole, formula e prezzo, contratto in 12 punti, regole della casa. PDF subito via email, garanzia 14 giorni.",
             "headline": "Guida: basta dipendenti", "description": f"20 pagine + kit · {PRICE}"},
        ],
    },
}


def create(budget_cents: int = 1000) -> dict:
    warnings.filterwarnings("ignore")
    e = env()
    tok, acc, page, pixel = e["META_ACCESS_TOKEN"], e["META_AD_ACCOUNT_ID"], e["META_PAGE_ID"], e["META_PIXEL_ID"]
    name = f"{BRAND} · Guide · vendite · A/B"
    ex = [c for c in call("GET", f"{acc}/campaigns", tok, fields="id,name", limit=50).get("data", []) if c["name"] == name]
    cid = ex[0]["id"] if ex else call("POST", f"{acc}/campaigns", tok, name=name, objective="OUTCOME_SALES", status="PAUSED", special_ad_categories="[]",
                                       buying_type="AUCTION", is_adset_budget_sharing_enabled="false")["id"]
    hashes = upload(tok, acc)
    pt = next(p["access_token"] for p in call("GET", "me/accounts", tok, fields="id,access_token")["data"] if p["id"] == page)
    pbia = call("GET", f"{page}/page_backed_instagram_accounts", pt, fields="id").get("data") or [call("POST", f"{page}/page_backed_instagram_accounts", pt)]
    ig = pbia[0]["id"]
    out = {"campaign_id": cid, "adsets": [], "status": "PAUSED"}
    existing_sets = {a["name"]: a["id"] for a in call("GET", f"{cid}/adsets", tok, fields="id,name").get("data", [])}
    targeting = {"geo_locations": {"custom_locations": [MILANO]}, "age_min": 28, "age_max": 62, "locales": [10],
                 "flexible_spec": [{"interests": PRO_INTERESTS, "work_positions": OWNER_JOBS}],
                 "publisher_platforms": ["facebook", "instagram"], "facebook_positions": ["feed", "story", "facebook_reels"], "instagram_positions": ["stream", "story", "reels"],
                 "targeting_automation": {"advantage_audience": 0}}
    for key, cfg in ADSETS.items():
        asid = existing_sets.get(cfg["name"]) or call("POST", f"{acc}/adsets", tok, name=cfg["name"], campaign_id=cid, status="PAUSED", daily_budget=budget_cents,
                                                      billing_event="IMPRESSIONS", optimization_goal="OFFSITE_CONVERSIONS",
                                                      promoted_object=json.dumps({"pixel_id": pixel, "custom_event_type": "PURCHASE"}),
                                                      bid_strategy="LOWEST_COST_WITHOUT_CAP", targeting=json.dumps(targeting))["id"]
        ex_ads = {a["name"]: a["id"] for a in call("GET", f"{asid}/ads", tok, fields="id,name").get("data", [])}
        ads = []
        for ad in cfg["ads"]:
            ad_name = f"{BRAND} · guida {key} · {ad['subject']}"
            if ad_name in ex_ads:
                ads.append({"ad_id": ex_ads[ad_name], "name": ad_name, "note": "existing"})
                continue
            link = f"{cfg['landing']}?utm_source=meta&utm_medium=paid&utm_campaign=guide_ab&utm_content={key}_{ad['subject']}"
            pre = f"guida_{key}_{ad['subject']}"
            h1, h45, h916 = hashes.get(f"{pre}_1x1.png"), hashes.get(f"{pre}_4x5.png"), hashes.get(f"{pre}_9x16.png")
            afs = {"images": [{"hash": h, "adlabels": [{"name": lab}]} for h, lab in ((h1, "sq"), (h45, "p45"), (h916, "v916")) if h],
                   "bodies": [{"text": ad["primary"]}], "titles": [{"text": ad["headline"][:40]}], "descriptions": [{"text": ad.get("description", "")[:30]}],
                   "link_urls": [{"website_url": link}], "call_to_action_types": ["SHOP_NOW"], "ad_formats": ["SINGLE_IMAGE"],
                   "asset_customization_rules": [
                       {"customization_spec": {"publisher_platforms": ["facebook", "instagram"], "facebook_positions": ["story", "facebook_reels"], "instagram_positions": ["story", "reels"]}, "image_label": {"name": "v916"}},
                       {"customization_spec": {"publisher_platforms": ["instagram"], "instagram_positions": ["stream"]}, "image_label": {"name": "p45"}},
                       {"customization_spec": {"publisher_platforms": ["facebook"], "facebook_positions": ["feed"]}, "image_label": {"name": "sq"}}]}
            cr = call("POST", f"{acc}/adcreatives", tok, name=ad_name, object_story_spec=json.dumps({"page_id": page, "instagram_user_id": ig}), asset_feed_spec=json.dumps(afs), instagram_user_id=ig)
            a = call("POST", f"{acc}/ads", tok, name=ad_name, adset_id=asid, status="PAUSED", creative=json.dumps({"creative_id": cr["id"]}))
            ads.append({"ad_id": a["id"], "creative_id": cr["id"], "name": ad_name})
        out["adsets"].append({"key": key, "adset_id": asid, "daily_budget_eur": budget_cents / 100, "ads": ads})
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "create"
    budget = int(sys.argv[sys.argv.index("--budget") + 1]) if "--budget" in sys.argv else 1000
    if cmd == "create":
        print(json.dumps(create(budget), indent=2, ensure_ascii=False))
