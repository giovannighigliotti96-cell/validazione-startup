"""One-off: owners with an unfinished listing get an email with the professionals that would already match
(first name + score), computed provisionally from what we know (salon name, zone, why the chair is free).
Run: python -X utf8 -m scripts.poltrona_nudge_matches [--dry]"""
import sys
from html import escape

from app import db
from app.config import get_settings
from app.services import matching, notify
from app.services import poltrona as P

DRY = "--dry" in sys.argv
c = db.get_db()
pros = [(d.id, d.to_dict()) for d in c.collection(db.PROBLEM_CLUSTERS).document(P.PROS).collection("leads").stream() if not P.is_test(d.to_dict().get("email"))]
owners = {d.id: d.to_dict() for d in c.collection(db.PROBLEM_CLUSTERS).document(P.OWNERS).collection("leads").stream()}

for d in c.collection("listings").stream():
    li = {"id": d.id, **d.to_dict()}
    if P.is_test(li.get("email")) or li.get("status") == "online":
        continue
    lead = owners.get(li["lead_id"], {})
    li2 = {**li, "chi_cerchi": li.get("chi_cerchi") or f"(non ancora indicato; il salone si chiama '{li.get('salone')}', motivo della postazione libera: {lead.get('answer') or 'n/d'})"}
    scored = []
    for _, pl in pros:
        v = matching.evaluate(li2, pl)
        if v and v.score >= 60 and v.specialty_fit != "no":
            e = pl.get("extra") or {}
            scored.append((v.score, (e.get("nome") or "").strip().split(" ")[0].title(), (e.get("specialita") or "").strip().lower(), (e.get("zona") or "").strip()))
    scored.sort(reverse=True)
    first = (li.get("titolare") or "").strip().split(" ")[0].title()
    first = "" if first.startswith("Dott") else first
    n = len(scored)
    if n:
        rows = "".join(f"<tr><td style='padding:8px 12px;border-bottom:1px solid #eee6da'><b>{escape(nm)}</b><br><span style='color:#6b625a;font-size:14px'>{escape(sp)}{(' · ' + escape(z)) if z else ''}</span></td>"
                       f"<td style='padding:8px 12px;border-bottom:1px solid #eee6da;text-align:right;white-space:nowrap'><b style='color:{'#2f6f4e' if sc >= 80 else '#8a6a3d'}'>{sc}/100</b></td></tr>" for sc, nm, sp, z in scored)
        middle = (f"<p>Nel frattempo si sono iscritte diverse professioniste, e {'una' if n == 1 else str(n)} di loro {'sembra' if n == 1 else 'sembrano'} adatt{'a' if n == 1 else 'e'} alla tua postazione, "
                  f"per mestiere e per zona. Ti lascio i nomi e quanto sono compatibili con quello che sappiamo finora del tuo salone:</p>"
                  f"<table style='border-collapse:collapse;width:100%;background:#fffdf9;border:1px solid #eee6da;border-radius:10px'>{rows}</table>"
                  f"<p>Il punteggio è provvisorio: appena scrivi cosa cerchi, i giorni e il prezzo, diventa preciso e possiamo presentartele davvero, con il loro numero.</p>")
    else:
        middle = "<p>Nel frattempo si stanno iscrivendo professioniste da tutta Milano. Per poterle presentare a te ci manca solo il tuo annuncio completo: chi cerchi, i giorni, il prezzo e una foto.</p>"
    html = P._mail([
        f"Ciao {first}," if first else "Ciao,",
        f"ti scrivo io, Giovanni. Il tuo annuncio per <b>{escape(li.get('salone') or 'il tuo salone')}</b> è ancora a metà, e mi dispiace perché è il momento giusto per pubblicarlo.",
        middle,
        f"<p style='margin:22px 0'><a href='{P.link(li)}' style='display:inline-block;background:#b5532c;color:#fff;padding:13px 22px;border-radius:999px;text-decoration:none;font-weight:700'>Completa l'annuncio (5 minuti)</a></p>",
        "È gratis, e resta gratis. Se preferisci farlo a voce, chiamami o scrivimi su WhatsApp al 392 590 9721: lo compilo io con te in cinque minuti.",
        "A presto,<br>Giovanni Ghigliotti<br>Poltrona Libera",
    ])
    subj = f"{first + ', ' if first else ''}{'abbiamo ' + ('una professionista' if n == 1 else str(n) + ' professioniste') + ' da presentarti' if n else 'le professioniste stanno arrivando'} — Poltrona Libera"
    print(f"{li.get('salone')!s:45s} -> {li.get('email')}  [{n} match] {[(s, nm) for s, nm, _, _ in scored]}")
    if not DRY:
        print("   ", notify.send_email(subj, html, to=li["email"], from_name=P.BRAND, reply_to=get_settings().notify_email_to))
