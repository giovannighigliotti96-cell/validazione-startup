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
        "name": "Guida A · La dipendente è andata via · titolari Italia 28-62",
        "landing": f"{BASE}/pl/guida/squadra",
        "ads": [
            {"subject": "andata_via", "primary": "La tua dipendente è andata via?\n\nSe è successo anche a te, sai come ci si sente: agenda da spostare, clienti da richiamare, la poltrona vuota. Questa guida in PDF (24 pagine + kit da stampare) dice cosa fare nelle prossime 48 ore per non perdere le clienti, come scrivere l'annuncio a cui rispondono davvero, il colloquio di 20 minuti, e i premi sul fatturato che fanno restare la prossima.\n\nScritta per titolari di salone, con i numeri del 2026. 49,90 € (prezzo di lancio), PDF subito via email, garanzia 14 giorni.\n\n👉 Scarica la guida: {link}",
             "headline": "La dipendente è andata via: cosa fare", "description": "Guida PDF + kit · 49,90 €"},
            {"subject": "non_trovo", "primary": "Non trovi personale per il tuo salone?\n\nDi solito il problema non è il canale: è l'annuncio. Nella guida trovi le 7 regole dell'annuncio che riceve candidature, 3 modelli pronti da copiare (social, Indeed, scuole), dove pubblicare e cosa costa, e il colloquio in 20 minuti con le 10 domande giuste.\n\nGuida PDF per titolari di salone, 24 pagine + kit. 49,90 €, subito via email, garanzia 14 giorni.\n\n👉 Scarica la guida: {link}",
             "headline": "Non trovi personale? Non è il canale", "description": "3 annunci pronti · 49,90 €"},
            {"subject": "maternita", "primary": "In maternità, e ti ha detto che non rientra?\n\nSi poteva evitare, e si può ancora: il part-time che fa rientrare la maggior parte delle persone, la sostituta che ti costa la metà (lo sgravio che quasi nessun salone usa), e il piano dei 90 giorni per ricostruire la squadra.\n\nGuida PDF per titolari di salone, 24 pagine + kit da stampare. 49,90 €, garanzia 14 giorni.\n\n👉 Scarica la guida: {link}",
             "headline": "Maternità e non rientra: il piano", "description": "Guida PDF + kit · 49,90 €"},
            {"subject": "libro", "primary": "Quante volte hai ricominciato da zero con il personale?\n\n«La dipendente è andata via» è la guida per titolari di salone che vogliono smettere di tappare buchi: come ricostruire la squadra in 90 giorni, tenerla, e non ritrovarsi mai più con una poltrona vuota. Dentro: annunci pronti, scheda colloquio, schema premi da firmare in due, lettera alle clienti, piano dei 90 giorni.\n\nPDF di 24 pagine, subito via email. 49,90 € (89 € da novembre), garanzia 14 giorni.\n\n👉 Scarica la guida: {link}",
             "headline": "Guida: la dipendente è andata via", "description": "24 pagine + kit · 49,90 €"},
            {"subject": "faq", "carousel": True, "primary": "«E le sue clienti?» «Perché nessuno risponde all'annuncio?» «Quanto devo offrirle?» «Come capisco che se ne va?» Le 5 domande che si fa ogni titolare quando una dipendente se ne va, con le risposte. Sono nella guida «La dipendente è andata via»: 24 pagine + kit, PDF subito via email, 49,90 €, garanzia 14 giorni.\n\n👉 Scarica la guida: {link}",
             "headline": "Le 5 domande di ogni titolare", "cards": ["E le sue clienti?", "Perché nessuno risponde?", "Quanto devo offrire?", "Come capisco che se ne va?", "Maternità e non rientra?"]},
        ],
    },
    "poltrona": {
        "name": "Guida B · Basta dipendenti · titolari Italia 28-62",
        "landing": f"{BASE}/pl/guida/poltrona",
        "ads": [
            {"subject": "basta", "primary": "Stanca di dipendenti che se ne vanno?\n\nLa postazione vuota del tuo salone può pagarti un canone ogni mese, invece di costarti una busta paga. Si chiama affitto di poltrona, è legale dal 2012, e questa guida in PDF spiega come farlo bene: i numeri veri, le regole che ti proteggono, formula e prezzo, il contratto in 12 punti, come trovare la professionista giusta in una settimana.\n\n20 pagine + kit da stampare. 49,90 € (prezzo di lancio), subito via email, garanzia 14 giorni.\n\n👉 Scarica la guida: {link}",
             "headline": "Basta dipendenti: la poltrona in affitto", "description": "Guida PDF + kit · 49,90 €"},
            {"subject": "conto", "primary": "Sai quanto ti costa davvero una dipendente?\n\nUna qualificata a tempo pieno: circa 2.100 € al mese tra busta, contributi, TFR e ferie. La stessa postazione affittata a una professionista in proprio te ne rende 500-1.200, senza malattie, preavvisi e sostituzioni. Nella guida: il confronto su 12 mesi, il calcolo del canone per la tua zona, il contratto in 12 punti.\n\nGuida PDF per titolari di salone, 20 pagine + kit. 49,90 €, garanzia 14 giorni.\n\n👉 Scarica la guida: {link}",
             "headline": "2.100 € di costo o 500-1.200 € di canone?", "description": "Il conto, capitolo 2 · 49,90 €"},
            {"subject": "legale", "primary": "Vorresti affittare una poltrona ma hai paura di sbagliare?\n\nÈ legale dal 2012, ma va fatto bene: quante postazioni puoi affittare, a chi no, cosa scrivere nel contratto (12 punti), come convivere nello stesso salone, gli 8 casi che vanno storti e come evitarli. Tutto in una guida PDF di 20 pagine con il kit: calcolo del canone, checklist documenti, traccia di accordo, regole della casa.\n\n49,90 €, subito via email, garanzia 14 giorni.\n\n👉 Scarica la guida: {link}",
             "headline": "Affitto di poltrona: come si fa bene", "description": "Guida PDF + kit · 49,90 €"},
            {"subject": "libro", "primary": "Il dipendente si è licenziato e ora non vuoi più personale?\n\nCe l'ha scritto una titolare, e non è l'unica. «Basta dipendenti» è la guida per chi vuole un modello diverso: le postazioni affittate a professioniste in proprio, canone mensile al posto della busta paga. Numeri, regole, formula e prezzo, contratto in 12 punti, regole della casa.\n\nPDF di 20 pagine + kit, subito via email. 49,90 € (89 € da novembre), garanzia 14 giorni.\n\n👉 Scarica la guida: {link}",
             "headline": "Guida: basta dipendenti", "description": "20 pagine + kit · 49,90 €"},
            {"subject": "faq", "carousel": True, "primary": "«È legale?» «Quanto mi rende?» «E se non paga?» «Mi porta via le clienti?» «Dove la trovo?» Le 5 domande che si fa ogni titolare prima di affittare una poltrona, con le risposte. Sono nella guida «Basta dipendenti»: 20 pagine + kit, PDF subito via email, 49,90 €, garanzia 14 giorni.\n\n👉 Scarica la guida: {link}",
             "headline": "Le 5 domande prima di affittare", "cards": ["È legale?", "Quanto mi rende?", "E se non paga?", "Mi porta via le clienti?", "Dove la trovo?"]},
        ],
    },
}


def create(budget_cents: int = 1000, recreate: bool = False) -> dict:
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
    targeting = {"geo_locations": {"countries": ["IT"]}, "age_min": 28, "age_max": 62, "locales": [10],
                 "flexible_spec": [{"interests": PRO_INTERESTS, "work_positions": OWNER_JOBS}],
                 "publisher_platforms": ["facebook", "instagram"], "facebook_positions": ["feed", "story", "facebook_reels"], "instagram_positions": ["stream", "story", "reels"],
                 "targeting_automation": {"advantage_audience": 0}}
    for key, cfg in ADSETS.items():
        old_name = cfg["name"].replace("Italia", "Milano")
        asid = existing_sets.get(cfg["name"]) or existing_sets.get(old_name) or call("POST", f"{acc}/adsets", tok, name=cfg["name"], campaign_id=cid, status="PAUSED", daily_budget=budget_cents,
                                                      billing_event="IMPRESSIONS", optimization_goal="OFFSITE_CONVERSIONS",
                                                      promoted_object=json.dumps({"pixel_id": pixel, "custom_event_type": "PURCHASE"}),
                                                      bid_strategy="LOWEST_COST_WITHOUT_CAP", targeting=json.dumps(targeting))["id"]
        call("POST", asid, tok, name=cfg["name"], targeting=json.dumps(targeting))  # keep name/targeting in sync (Italy)
        ex_ads = {a["name"]: a["id"] for a in call("GET", f"{asid}/ads", tok, fields="id,name").get("data", [])}
        if recreate:  # copy, cta or images changed: delete every existing ad and build again
            for name_, id_ in ex_ads.items():
                call("POST", id_, tok, status="DELETED")
            ex_ads = {}
        ads = []
        for ad in cfg["ads"]:
            ad_name = f"{BRAND} · guida {key} · {ad['subject']}"
            if ad_name in ex_ads:
                ads.append({"ad_id": ex_ads[ad_name], "name": ad_name, "note": "existing"})
                continue
            link = f"{cfg['landing']}?utm_source=meta&utm_medium=paid&utm_campaign=guide_ab&utm_content={key}_{ad['subject']}"
            primary = ad["primary"].replace("{link}", link)
            if ad.get("carousel"):
                cards = [{"image_hash": hashes[f"guida_{key}_faq_{i}.png"], "name": t[:40], "description": "", "link": link} for i, t in enumerate(ad["cards"], 1)]
                oss = {"page_id": page, "instagram_user_id": ig, "link_data": {"link": link, "message": primary, "name": ad["headline"][:40], "child_attachments": cards,
                                                                             "call_to_action": {"type": "DOWNLOAD", "value": {"link": link}}, "multi_share_optimized": False, "multi_share_end_card": False}}
                cr = call("POST", f"{acc}/adcreatives", tok, name=ad_name, object_story_spec=json.dumps(oss), instagram_user_id=ig)
            else:
                pre = f"guida_{key}_{ad['subject']}"
                h1, h45, h916 = hashes.get(f"{pre}_1x1.png"), hashes.get(f"{pre}_4x5.png"), hashes.get(f"{pre}_9x16.png")
                afs = {"images": [{"hash": h, "adlabels": [{"name": lab}]} for h, lab in ((h1, "sq"), (h45, "p45"), (h916, "v916")) if h],
                       "bodies": [{"text": primary}], "titles": [{"text": ad["headline"][:40]}], "descriptions": [{"text": ad.get("description", "")[:30]}],
                       "link_urls": [{"website_url": link}], "call_to_action_types": ["DOWNLOAD"], "ad_formats": ["SINGLE_IMAGE"],
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
        print(json.dumps(create(budget, recreate="--recreate" in sys.argv), indent=2, ensure_ascii=False))
