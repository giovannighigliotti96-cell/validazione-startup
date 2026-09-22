"""Morning report (09:00 Rome) and zone alerts for professionals whose area has no listing yet."""
from __future__ import annotations

import logging
from datetime import timedelta
from html import escape

from app import db
from app.config import get_settings
from app.services import guida as G
from app.services import notify
from app.services import poltrona as P

log = logging.getLogger("daily")


# ----------------------------------------------------------------------------- morning report
def _ads() -> dict:
    try:
        import httpx

        from scripts.meta_campaign import env

        e = env()
        out = {}
        for cid, label in (("120260088307320456", "poltrona"), ("120260149689220456", "guide")):
            r = httpx.get(f"https://graph.facebook.com/v21.0/{cid}/insights",
                          params={"access_token": e["META_ACCESS_TOKEN"], "fields": "spend,impressions,inline_link_clicks,actions", "date_preset": "yesterday"}, timeout=20).json().get("data", [])
            if r:
                a = {x["action_type"]: float(x["value"]) for x in r[0].get("actions", [])}
                out[label] = {"spesa": float(r[0]["spend"]), "impression": int(r[0]["impressions"]), "click": int(r[0].get("inline_link_clicks") or 0),
                              "lead": int(a.get("lead", 0)), "acquisti": int(a.get("purchase", 0))}
        return out
    except Exception as e:  # noqa: BLE001
        log.error("ads stats: %s", e)
        return {}


def report(send: bool = True) -> str:
    client = db.get_db()
    y = db.now() - timedelta(days=1)
    owners = [d.to_dict() for d in client.collection(db.PROBLEM_CLUSTERS).document(P.OWNERS).collection("leads").stream() if not P.is_test(d.to_dict().get("email"))]
    pros = [d.to_dict() for d in client.collection(db.PROBLEM_CLUSTERS).document(P.PROS).collection("leads").stream() if not P.is_test(d.to_dict().get("email"))]
    listings = [{"id": d.id, **d.to_dict()} for d in client.collection("listings").stream() if not P.is_test(d.to_dict().get("email"))]
    online = [x for x in listings if x.get("status") == "online"]
    drafts = [x for x in listings if x.get("status") == "bozza"]
    waiting = [x for x in listings if x.get("status") == "in_verifica"]
    calls = sum(int((x.get("clicks") or {}).get("call", 0)) + int((x.get("clicks") or {}).get("whatsapp", 0)) for x in listings)
    buyers = G.buyers()
    new = lambda items, key="at": [i for i in items if i.get(key) and i[key] >= y]  # noqa: E731
    matches = [d.to_dict() for d in client.collection("matches").stream()]
    ads = _ads()
    rows = [
        ("Saloni iscritti", len(owners), len(new(owners))),
        ("Professioniste iscritte", len(pros), len(new(pros))),
        ("Annunci online", len(online), len([x for x in online if x.get("approved_at") and x["approved_at"] >= y])),
        ("Annunci da approvare", len(waiting), ""),
        ("Bozze non finite", len(drafts), ""),
        ("Tap su chiama/WhatsApp", calls, ""),
        ("Match notificati", sum(1 for m in matches if m.get("match")), len([m for m in matches if m.get("match") and m.get("created_at") and m["created_at"] >= y])),
        ("Guide vendute", len(buyers), len(new(buyers, "created_at"))),
    ]
    tbl = "".join(f"<tr><td style='padding:6px 10px'>{escape(k)}</td><td style='padding:6px 10px'><b>{v}</b></td>"
                  f"<td style='padding:6px 10px;color:#2f6f4e'>{('+' + str(d)) if d else ''}</td></tr>" for k, v, d in rows)
    ad_tbl = "".join(f"<tr><td style='padding:6px 10px'>{escape(k)}</td><td style='padding:6px 10px'>{v['spesa']:.2f} €</td><td style='padding:6px 10px'>{v['impression']} imp · {v['click']} click</td>"
                     f"<td style='padding:6px 10px'><b>{v['lead'] or v['acquisti']}</b> {'lead' if v['lead'] else 'acquisti'}</td></tr>" for k, v in ads.items())
    todo = []
    if waiting:
        todo.append(f"{len(waiting)} annunci da approvare: <a href='{P.base()}/pl/admin'>pannello</a>")
    if drafts:
        todo.append(f"{len(drafts)} bozze ferme: un WhatsApp sblocca ({', '.join(escape(d.get('salone') or '') for d in drafts[:4])})")
    pros_no_zone = [p for p in pros if not any((p.get("extra") or {}).get("zona", "").strip().lower()[:4] in (x.get("zona") or "").lower() for x in online)]
    if pros_no_zone:
        todo.append(f"{len(pros_no_zone)} professioniste senza postazioni nella loro zona")
    html = (f"<div style='font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;line-height:1.6'>"
            f"<h2 style='font-family:Georgia,serif'>Poltrona Libera · {db.now():%d/%m}</h2>"
            f"<table style='border-collapse:collapse;width:100%;background:#fffdf9;border:1px solid #e3dbd0;border-radius:8px'>{tbl}</table>"
            + (f"<h3 style='font-size:15px;margin-top:18px'>Ads di ieri</h3><table style='border-collapse:collapse;width:100%'>{ad_tbl}</table>" if ad_tbl else "")
            + (f"<h3 style='font-size:15px;margin-top:18px'>Da fare oggi</h3><ul>{''.join('<li>' + t + '</li>' for t in todo)}</ul>" if todo else "<p>Niente in sospeso.</p>")
            + f"<p><a href='{P.base()}/pl/admin'>Apri il pannello</a></p></div>")
    if send:
        try:
            notify.send_email(f"☀️ Poltrona Libera · {db.now():%d/%m}: {len(online)} annunci online, {len(owners)} saloni, {len(pros)} professioniste", html)
        except Exception as e:  # noqa: BLE001
            log.error("report: %s", e)
    return html


# ----------------------------------------------------------------------------- zone alerts
def zone_alerts(max_per_run: int = 20) -> int:
    """A professional with no listing in her area gets one email (once every 10 days) with the closest ones."""
    client = db.get_db()
    online = P.online_listings()
    if not online:
        return 0
    n = 0
    for d in client.collection(db.PROBLEM_CLUSTERS).document(P.PROS).collection("leads").stream():
        lead = d.to_dict()
        if P.is_test(lead.get("email")) or n >= max_per_run:
            continue
        last = lead.get("zone_alert_at")
        if last and db.now() - last < timedelta(days=10):
            continue
        e = lead.get("extra") or {}
        zona = (e.get("zona") or "").strip()
        # skip if a listing already covers her zone (a match would have been sent instead)
        if zona and any(zona.lower()[:4] in (li.get("zona") or "").lower() for li in online):
            continue
        cards = "".join(f"<li><b>{escape(li.get('salone') or '')}</b> · {escape(li.get('zona') or '')} — {escape(li.get('giorni') or '')} · {escape(li.get('prezzo') or '')} · "
                        f"chiama {escape(P.first_name(li.get('titolare') or ''))} {escape(li.get('telefono') or '')}</li>" for li in online[:4])
        P._sender(f"{len(online)} postazioni libere a Milano — Poltrona Libera", P._mail([
            P.hi(e.get("nome") or ""),
            f"a {escape(zona)} non c'è ancora una postazione libera, e appena esce ti scrivo io. Intanto queste sono aperte adesso, forse una è raggiungibile:",
            f"<ul>{cards}</ul>",
            f"Le vedi tutte con foto e dettagli qui: {P.base()}/pl/postazioni — guardare e chiamare è gratis.",
            "Se vuoi che cerchi in una zona diversa, rispondi a questa email o scrivimi su WhatsApp al 392 590 9721.",
            "A presto,<br>Giovanni Ghigliotti<br>Poltrona Libera"]), lead["email"])
        d.reference.update({"zone_alert_at": db.now()})
        n += 1
    return n
