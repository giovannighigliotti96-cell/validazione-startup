"""One-off: create a draft listing for every owner lead that has none and email them their personal link."""
from html import escape

from app import db
from app.services import poltrona as P
from app.services import notify

SKIP = {"giovannighigliotti96@gmail.com"}
c = db.get_db()
for d in c.collection(db.PROBLEM_CLUSTERS).document(P.OWNERS).collection("leads").stream():
    lead = d.to_dict()
    if lead["email"] in SKIP:
        continue
    had = list(c.collection("listings").where("lead_id", "==", d.id).limit(1).stream())
    li = P.create_draft(lead, d.id)
    if had:
        print("already", lead["email"]); continue
    nome = ((lead.get("extra") or {}).get("nome") or "").split(" ")[0]
    body = P._mail([f"Ciao {nome}," if nome else "Ciao,",
                    f"grazie per esserti registrata su Poltrona Libera per {lead.get('business') or 'il tuo salone'}. Abbiamo cambiato una cosa importante: pubblicare la tua postazione è gratis, senza commissioni. Tu pubblichi l'annuncio, le professioniste di Milano lo vedono e chiedono il tuo contatto, e vi mettete d'accordo direttamente.",
                    "Ci vogliono due minuti: giorni, prezzo, una foto e il numero da chiamare. Il tuo link personale:", f"<p><a href='{P.link(li)}' style='display:inline-block;background:#b5532c;color:#fff;padding:12px 20px;border-radius:999px;text-decoration:none;font-weight:700'>Pubblica la tua postazione</a></p>",
                    "Nell'annuncio compaiono nome del salone, zona, giorni, prezzo, foto e il numero da chiamare: le professioniste ti chiamano direttamente.",
                    "Se hai domande rispondi a questa email.", "A presto,<br>Giovanni Ghigliotti<br>Poltrona Libera"])
    st = notify.send_email("Pubblica gratis la tua postazione — Poltrona Libera", body, to=lead["email"], from_name="Poltrona Libera", reply_to=db.get_db and __import__("app.config", fromlist=["get_settings"]).get_settings().notify_email_to)
    print("sent", lead["email"], lead.get("business"), st)
