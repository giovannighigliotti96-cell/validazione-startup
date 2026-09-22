"""Minimal, learning-safe change to the live Poltrona campaign (no new ad sets, no budget change):
  - pause the two ads that spent with zero results and carry stale copy (prof_offerta: 99 EUR; prof_cento: "40% di uno stipendio")
  - add one new ad per ad set, using the copy that works, pointing at the same landings (owners -> owners landing,
    professionals -> professionals landing), with utm so every visit stays traceable.
Run: python -m scripts.meta_poltrona_tweak [--dry]"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.meta_campaign import call, env  # noqa: E402
from scripts.meta_poltrona import BRAND, upload  # noqa: E402

CAMPAIGN = "120260088307320456"
BASE = "https://poltronalibera.it"
PAUSE = ["prof_offerta", "prof_cento"]  # spent with 0 clicks / stale offer

NEW_ADS = {
    "professioniste": {
        "subject": "postazioni_6",
        "landing": f"{BASE}/pl/postazioni",
        "images": "prof_libera",  # reuse the winning creative set (same hashes, no new upload)
        "primary": ("Ci sono 6 postazioni libere in saloni di Milano, in questo momento.\n\n"
                    "Zona, giorni, prezzo, cosa è incluso, le foto e il numero della titolare: guardi e chiami tu, direttamente. "
                    "Nessun modulo, nessun costo: Poltrona Libera è gratis per chi cerca una postazione.\n\n"
                    "Lavori a domicilio o vuoi metterti in proprio senza aprire un salone? Guarda se c'è la tua zona."),
        "headline": "6 postazioni libere a Milano",
        "description": "Guardi e chiami. Gratis.",
    },
    "titolari": {
        "subject": "chiamano_loro",
        "landing": f"{BASE}/lp/poltrona_libera_titolari",
        "images": "reddito",
        "primary": ("La tua poltrona vuota può ricevere chiamate già questa settimana.\n\n"
                    "Pubblichi l'annuncio in cinque minuti: zona, giorni, prezzo, una foto e il numero da chiamare. "
                    "Lo controlliamo e lo mettiamo online; le parrucchiere e i barbieri di Milano che cercano una postazione ti chiamano direttamente.\n\n"
                    "Gratis, nessuna commissione: vi accordate voi su giorni, orari e prezzo."),
        "headline": "Pubblica la postazione: ti chiamano",
        "description": "Gratis, in cinque minuti.",
    },
}


def run(dry: bool = False) -> dict:
    e = env()
    tok, acc, page, pixel = e["META_ACCESS_TOKEN"], e["META_AD_ACCOUNT_ID"], e["META_PAGE_ID"], e["META_PIXEL_ID"]
    out: dict = {"paused": [], "created": []}
    ads = call("GET", f"{CAMPAIGN}/ads", tok, fields="id,name,adset_id,effective_status", limit=50).get("data", [])
    for a in ads:
        if a["name"].split("· ")[-1] in PAUSE and a["effective_status"] == "ACTIVE":
            if not dry:
                call("POST", a["id"], tok, status="PAUSED")
            out["paused"].append(a["name"])
    sets = {s["name"].split(" ·")[0].lower(): s["id"] for s in call("GET", f"{CAMPAIGN}/adsets", tok, fields="id,name").get("data", [])}
    hashes = upload(tok, acc)
    pt = next(p["access_token"] for p in call("GET", "me/accounts", tok, fields="id,access_token")["data"] if p["id"] == page)
    ig = (call("GET", f"{page}/page_backed_instagram_accounts", pt, fields="id").get("data") or [{}])[0].get("id")
    for key, cfg in NEW_ADS.items():
        asid = sets.get(key)
        if not asid:
            continue
        name = f"{BRAND} · {key} · {cfg['subject']}"
        if any(a["name"] == name for a in ads):
            out["created"].append(name + " (esiste)")
            continue
        link = f"{cfg['landing']}?utm_source=meta&utm_medium=paid&utm_campaign=poltrona_milano&utm_content={key}_{cfg['subject']}"
        pre = cfg["images"]
        afs = {"images": [{"hash": hashes[f"{pre}_{lab_src}.png"], "adlabels": [{"name": lab}]} for lab_src, lab in (("1x1", "sq"), ("4x5", "p45"), ("9x16", "v916")) if f"{pre}_{lab_src}.png" in hashes],
               "bodies": [{"text": cfg["primary"]}], "titles": [{"text": cfg["headline"][:40]}], "descriptions": [{"text": cfg["description"][:30]}],
               "link_urls": [{"website_url": link}], "call_to_action_types": ["LEARN_MORE" if key == "professioniste" else "SIGN_UP"], "ad_formats": ["SINGLE_IMAGE"],
               "asset_customization_rules": [
                   {"customization_spec": {"publisher_platforms": ["facebook", "instagram"], "facebook_positions": ["story", "facebook_reels"], "instagram_positions": ["story", "reels"]}, "image_label": {"name": "v916"}},
                   {"customization_spec": {"publisher_platforms": ["instagram"], "instagram_positions": ["stream"]}, "image_label": {"name": "p45"}},
                   {"customization_spec": {"publisher_platforms": ["facebook"], "facebook_positions": ["feed"]}, "image_label": {"name": "sq"}}]}
        if dry:
            out["created"].append(name + " (dry)")
            continue
        cr = call("POST", f"{acc}/adcreatives", tok, name=name, object_story_spec=json.dumps({"page_id": page, "instagram_user_id": ig}), asset_feed_spec=json.dumps(afs), instagram_user_id=ig)
        ad = call("POST", f"{acc}/ads", tok, name=name, adset_id=asid, status="ACTIVE", creative=json.dumps({"creative_id": cr["id"]}))
        out["created"].append({"name": name, "id": ad["id"], "link": link})
    return out


if __name__ == "__main__":
    print(json.dumps(run("--dry" in sys.argv), indent=2, ensure_ascii=False))
