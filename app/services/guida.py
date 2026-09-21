"""Paid guides for salon owners (A/B on the pain angle): Stripe Checkout, instant delivery, buyer email workflow.

buyers/{id}: email, name, slug, amount, stripe_session, token (download), created_at, steps_sent, source (utm)
Workflow after purchase (hourly cron, app.services.guida.run_workflow):
  D+0  delivery email with the download link (and Giovanni notified with a WhatsApp link)
  D+1  'da dove partire' — the two chapters to read first
  D+3  'la postazione vuota' — publish the listing for free on Poltrona Libera (free for a little longer)
  D+7  'come è andata?' — a personal check-in, reply or WhatsApp
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import timedelta
from html import escape
from urllib.parse import quote

from app import db
from app.config import get_settings
from app.services import notify
from app.services import poltrona as P

log = logging.getLogger("guida")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PDF_DIR = os.path.join(ROOT, "data", "guide")

PRICE_CENTS = 4990
LIST_PRICE_CENTS = 8900
GUARANTEE_DAYS = 14

CATALOG = {
    "squadra": {
        "title": "La dipendente è andata via",
        "subtitle": "Come ricostruire la squadra del tuo salone in 90 giorni, tenerla, e non ritrovarti mai più con una poltrona vuota.",
        "pages": 24,
        "headline": "La tua dipendente è andata via. Ecco cosa fare nelle prossime 48 ore, nei prossimi 30 giorni e per non ritrovarti mai più qui.",
        "sub": "Una guida pratica per titolari di salone: annunci che ricevono candidature, il colloquio di 20 minuti, i premi sul fatturato che trattengono, il progetto a 12 mesi, il piano dei 90 giorni. Con il kit da stampare.",
        "pains": ["«Dipendente andata via.»", "«Non trovo personale.»", "«In maternità, e mi ha detto che non rientra.»"],
        "chapters": [
            ("Prima di tutto: respira", "le tre verità da cui partire, e come usare la guida nell'emergenza"),
            ("Le prime 48 ore", "colloquio d'uscita, squadra, clienti richiamate una per una, postazione mai vuota"),
            ("Il progetto a 12 mesi", "la pagina che fa restare le persone: numeri, ruoli, regole della casa, riunione del lunedì"),
            ("Trovare la persona giusta", "le 7 regole dell'annuncio, dove pubblicare a Milano, il colloquio in 20 minuti, i 6 segnali che se ne andrà"),
            ("I premi sul fatturato", "fisso + tre premi, come fissare la soglia, tre esempi con i numeri veri del 2026"),
            ("Tenerle", "il colloquio dei 3 mesi, i segnali che arrivano prima, la maternità gestita bene (e lo sgravio che quasi nessuno usa)"),
            ("Il piano dei 90 giorni", "settimana per settimana, da spuntare"),
            ("Il piano B", "quando non conviene più assumere: la poltrona in affitto, in breve"),
        ],
        "kit": ["La pagina del progetto", "3 annunci pronti (social, Indeed, scuole/vetrina)", "Scheda colloquio", "Schema premi da firmare in due", "Lettera alle clienti dopo un'uscita", "Costi a confronto 2026", "Annuncio di postazione in affitto"],
        "preview_pages": [1, 3, 7, 9],
        "for": ["Hai perso una dipendente (o sta per andarsene) e hai la poltrona vuota", "Vuoi ricostruire una squadra che resta, non tappare un buco", "Hai un salone da 2 a 8 persone e fai tutto tu"],
        "not_for": ["Cerchi un modello di contratto: qui c'è il metodo, i modelli te li dà il consulente", "Vuoi smettere di assumere: allora ti serve l'altra guida, «Basta dipendenti»"],
        "other": "poltrona",
    },
    "poltrona": {
        "title": "Basta dipendenti",
        "subtitle": "Affitta le postazioni del tuo salone a professioniste in proprio: canone mensile al posto della busta paga.",
        "pages": 20,
        "headline": "Stanca di dipendenti che se ne vanno? La postazione vuota può pagarti un canone ogni mese, invece di costarti una busta paga.",
        "sub": "La guida completa all'affitto di poltrona per titolari di salone: i numeri veri, le regole che ti proteggono, formula e prezzo, come trovare la professionista giusta in una settimana, il contratto in 12 punti, la convivenza, i casi che vanno storti. Con il kit da stampare.",
        "pains": ["«Si è licenziato, e ora non voglio più personale.»", "«Non trovo personale.»", "«Dipendente andata via.»"],
        "chapters": [
            ("Perché sempre più saloni smettono di assumere", "dipendente vs professionista in affitto, in una tabella; per chi è e per chi no"),
            ("I numeri", "quanto rende una postazione affittata: fisso, percentuale, mista, confronto su 12 mesi, le entrate nascoste"),
            ("Le regole che ti proteggono", "legale dal 2012, Milano 2018, quante postazioni, a chi no, la frase che vale più di tutte"),
            ("Formula e prezzo", "come decidere, come fissare il canone, cosa includere"),
            ("Trovare la professionista giusta", "annuncio, dove, il colloquio-visita in 30 minuti, i segnali d'allarme"),
            ("Il contratto in 12 punti", "tutto quello che va scritto, e cosa fare dopo la firma"),
            ("Convivere", "le regole della casa, il primo mese, i mesi dopo"),
            ("Quando va storto", "gli otto casi e come evitarli"),
        ],
        "kit": ["Calcolo del canone", "Annuncio di postazione", "Checklist visita e documenti", "Traccia di accordo in 12 punti", "Le regole della casa da appendere"],
        "preview_pages": [1, 3, 4, 9],
        "for": ["Hai una o più postazioni vuote e gli annunci non funzionano", "Sei stanca di fare la datrice di lavoro: buste, ferie, malattie, preavvisi", "Vuoi un'entrata certa che copra affitto e utenze"],
        "not_for": ["Vuoi controllare orari e servizi di chi lavora nel salone: allora ti serve una dipendente", "Cerchi come ricostruire la squadra: allora ti serve l'altra guida, «La dipendente è andata via»"],
        "other": "squadra",
    },
}


def base() -> str:
    return get_settings().public_base_url.rstrip("/")


def price_str(cents: int) -> str:
    return f"{cents // 100},{cents % 100:02d} €"


def pdf_path(slug: str) -> str:
    return os.path.join(PDF_DIR, f"{slug}.pdf")


def stripe_ready() -> bool:
    return bool(get_settings().stripe_secret_key)


# ----------------------------------------------------------------------------- checkout
def create_checkout(slug: str, utm: str = "", fb: tuple[str, str] = ("", ""), ip: str = "", ua: str = "") -> str | None:
    """Stripe Checkout session; returns the URL to redirect to, or None if Stripe is not configured."""
    if slug not in CATALOG or not stripe_ready():
        return None
    import stripe

    stripe.api_key = get_settings().stripe_secret_key
    g = CATALOG[slug]
    session = stripe.checkout.Session.create(
        mode="payment",
        locale="it",
        line_items=[{"quantity": 1, "price_data": {"currency": "eur", "unit_amount": PRICE_CENTS,
                                                    "product_data": {"name": f"Guida «{g['title']}»", "description": g["subtitle"][:200],
                                                                     "images": [f"{base()}/static/poltrona/guide/{slug}_p1.png"]}}}],
        customer_creation="always",
        billing_address_collection="auto",
        phone_number_collection={"enabled": True},  # for the WhatsApp follow-up (optional field)
        payment_method_configuration="pmc_1S1173KZdRNh4BbI0EYOQDgI",  # card + Apple Pay + Google Pay + Link + PayPal + Amazon Pay
        custom_text={"submit": {"message": f"Ricevi il PDF subito via email. Garanzia {GUARANTEE_DAYS} giorni: rimborso senza domande."},
                     "after_submit": {"message": "Grazie! Nella pagina successiva trovi il link per scaricare la guida."}},
        allow_promotion_codes=True,
        metadata={"slug": slug, "utm": utm[:80], "fbp": fb[0][:80], "fbc": fb[1][:120], "ip": ip[:45], "ua": ua[:200]},
        success_url=f"{base()}/pl/guida/{slug}/grazie?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base()}/pl/guida/{slug}?annullato=1",
    )
    return session.url


def fulfil_session(session_id: str) -> dict | None:
    """Idempotent: called from the success page and from the webhook. Records the buyer and sends the delivery email once."""
    import stripe

    stripe.api_key = get_settings().stripe_secret_key
    s = stripe.checkout.Session.retrieve(session_id, expand=["customer_details"])
    if s.get("payment_status") != "paid":
        return None
    client = db.get_db()
    ref = client.collection("buyers").document(session_id)
    snap = ref.get()
    if snap.exists:
        return {"id": session_id, **snap.to_dict()}
    slug = (s.get("metadata") or {}).get("slug") or "squadra"
    details = s.get("customer_details") or {}
    buyer = {"email": (details.get("email") or "").lower(), "name": details.get("name") or "", "phone": details.get("phone") or "",
             "slug": slug, "amount": int(s.get("amount_total") or 0), "currency": s.get("currency") or "eur", "utm": (s.get("metadata") or {}).get("utm") or "",
             "token": secrets.token_urlsafe(20), "created_at": db.now(), "steps_sent": 0, "downloads": 0, "status": "pagato"}
    ref.set(buyer)
    buyer["id"] = session_id
    send_delivery(buyer)
    try:  # Purchase to the Conversions API with full match data; same event_id as the browser pixel on the thank-you page
        from app.services import capi

        md = s.get("metadata") or {}
        nm = (buyer["name"] or "").split(" ")
        ud = capi.user_data(None, email=buyer["email"], phone=buyer.get("phone"), first_name=nm[0] if nm else None, last_name=nm[-1] if len(nm) > 1 else None, external_id=session_id)
        for k_src, k_dst in (("fbp", "fbp"), ("fbc", "fbc"), ("ip", "client_ip_address"), ("ua", "client_user_agent")):
            if md.get(k_src):
                ud[k_dst] = md[k_src]
        capi.send("Purchase", session_id, f"{base()}/pl/guida/{slug}", ud, {"content_name": slug, "content_type": "product", "value": buyer["amount"] / 100, "currency": "EUR", "order_id": session_id})
    except Exception as e:  # noqa: BLE001
        log.error("capi purchase: %s", e)
    return buyer


# ----------------------------------------------------------------------------- emails
def download_url(buyer: dict) -> str:
    return f"{base()}/pl/guida/download/{buyer['token']}"


def _first(buyer: dict) -> str:
    return P.first_name(buyer.get("name") or "")


def _hi(buyer: dict) -> str:
    n = _first(buyer)
    return f"Ciao {n}," if n else "Ciao,"


def _send(buyer: dict, subject: str, paras: list[str]) -> None:
    if not buyer.get("email"):
        return
    try:
        notify.send_email(subject, P._mail(paras), to=buyer["email"], from_name=P.BRAND, reply_to=get_settings().notify_email_to)
    except Exception as e:  # noqa: BLE001
        log.error("guida email to %s failed: %s", buyer.get("email"), e)


def send_delivery(buyer: dict) -> None:
    g = CATALOG.get(buyer["slug"], CATALOG["squadra"])
    url = download_url(buyer)
    _send(buyer, f"La tua guida «{g['title']}» — Poltrona Libera", [
        _hi(buyer),
        f"grazie: ecco la tua copia di <b>«{escape(g['title'])}»</b> ({g['pages']} pagine + kit, PDF).",
        f"<p style='margin:22px 0'><a href='{url}' style='display:inline-block;background:#b5532c;color:#fff;padding:13px 22px;border-radius:999px;text-decoration:none;font-weight:700'>Scarica la guida (PDF)</a></p>",
        f"Il link è personale e resta valido: salva il PDF sul telefono o sul computer. Se hai problemi ad aprirlo rispondi a questa email.",
        ("Da dove partire, se sei nell'emergenza: capitolo 2 (le prime 48 ore) e capitolo 5 (i premi sul fatturato). Il resto nel weekend."
         if buyer["slug"] == "squadra" else "Da dove partire: capitolo 2 (i numeri della tua postazione) e capitolo 6 (il contratto in 12 punti)."),
        f"Garanzia: se entro {GUARANTEE_DAYS} giorni pensi che non ti sia servita, rispondi a questa email e ti rimborso, senza domande.",
        "Se vuoi parlarne a voce, sono su WhatsApp al 392 590 9721.",
        "Buon lavoro,<br>Giovanni Ghigliotti<br>Poltrona Libera",
    ])
    wa = f"https://wa.me/39{P.PHONE}"  # placeholder, replaced below with the buyer's number when present
    text = f"Ciao {_first(buyer)}, sono Giovanni di Poltrona Libera: grazie per la guida! Se hai una postazione vuota, la pubblico io gratis per te in cinque minuti: mi mandi zona, giorni, prezzo e una foto?"
    if buyer.get("phone"):
        digits = "".join(ch for ch in buyer["phone"] if ch.isdigit())
        digits = digits if digits.startswith("39") else "39" + digits.lstrip("0")
        wa = f"https://wa.me/{digits}?text={quote(text)}"
    try:
        notify.send_email(f"💶 Guida venduta: {g['title']} — {buyer.get('name') or buyer.get('email')} ({price_str(buyer.get('amount') or PRICE_CENTS)})",
                          f"<div style='font-family:-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.6'><p><b>{escape(buyer.get('name') or '')}</b> · {escape(buyer.get('email') or '')} · {escape(buyer.get('phone') or 'telefono non fornito')}<br>"
                          f"Guida: {escape(g['title'])} · provenienza: {escape(buyer.get('utm') or 'diretto')}</p>"
                          + (f"<p><a href='{wa}' style='display:inline-block;background:#25d366;color:#fff;padding:12px 18px;border-radius:999px;text-decoration:none;font-weight:700'>WhatsApp: le pubblico io l'annuncio</a></p>" if buyer.get("phone") else "<p>Senza telefono: scrivile per email quando vuoi.</p>")
                          + f"<p><a href='{base()}/pl/admin'>Pannello</a></p></div>")
    except Exception as e:  # noqa: BLE001
        log.error("guida founder notify failed: %s", e)


STEPS = [  # (days after purchase, subject, paragraphs builder)
    (1, "Da dove partire (2 minuti) — Poltrona Libera", lambda b, g: [
        _hi(b),
        (f"ieri ti è arrivata «{escape(g['title'])}». Se non l'hai ancora aperta, ti dico da dove partire, perché la parte utile sta in due capitoli.")
        , ("<b>Capitolo 2, le prime 48 ore</b>: se la dipendente è andata via da poco, fai oggi la cosa più importante di tutta la guida: scrivi alle sue clienti abituali, una per una (la lettera è nel kit). Recuperi il 60-70% delle clienti; senza, ne perdi metà nel primo mese senza accorgertene.<br><br>"
           "<b>Capitolo 5, i premi sul fatturato</b>: è il motivo per cui la prossima resterà. Mezz'ora con la calcolatrice e hai lo schema da firmare in due."
           if b["slug"] == "squadra" else
           "<b>Capitolo 2, i numeri</b>: fai il calcolo del canone della tua postazione con il foglio del kit (10 minuti): ti dice sotto quale cifra non scendere e quanto vale nella tua zona.<br><br>"
           "<b>Capitolo 6, il contratto in 12 punti</b>: leggilo prima di parlare con chiunque, così sai cosa chiedere e cosa scrivere."),
        f"Il PDF lo riscarichi quando vuoi da qui: {download_url(b)}",
        "Se hai una domanda mentre leggi, rispondi a questa email: leggo tutto io.",
        "Giovanni<br>Poltrona Libera",
    ]),
    (3, "La postazione vuota, intanto — Poltrona Libera", lambda b, g: [
        _hi(b),
        "una cosa pratica, mentre applichi la guida: la postazione vuota costa ogni mese che passa (a Milano 500-1.000 € di canone non incassato, più gli incassi di chi ci lavorerebbe).",
        "Su Poltrona Libera i saloni di Milano pubblicano la postazione in cinque minuti (zona, giorni, prezzo, una foto, il numero) e le professioniste che cercano proprio quello li chiamano direttamente. Ci sono già professioniste registrate per il centro, il nord e il sud di Milano.",
        "<b>In fase di lancio pubblicare è gratis, e resta gratis per chi si iscrive adesso</b>: tra poco per i nuovi saloni sarà a pagamento.",
        f"<p style='margin:22px 0'><a href='{base()}/lp/poltrona_libera_titolari#lista-hero' style='display:inline-block;background:#b5532c;color:#fff;padding:13px 22px;border-radius:999px;text-decoration:none;font-weight:700'>Pubblica gratis la tua postazione</a></p>",
        "Oppure mandami zona, giorni, prezzo e una foto su WhatsApp al 392 590 9721: lo pubblico io per te in giornata.",
        "Giovanni<br>Poltrona Libera",
    ]),
    (7, "Come è andata? — Poltrona Libera", lambda b, g: [
        _hi(b),
        f"è passata una settimana da quando hai preso «{escape(g['title'])}». Ti scrivo per una cosa sola: come è andata? Hai pubblicato l'annuncio, fatto colloqui, scritto alle clienti?",
        "Se qualcosa non ha funzionato, dimmelo: rispondi a questa email o scrivimi su WhatsApp al 392 590 9721. Le risposte dei titolari sono quello che migliora la guida (e Poltrona Libera).",
        f"E se la postazione è ancora vuota, il modo più veloce è sempre lo stesso: {base()}/lp/poltrona_libera_titolari — gratis, cinque minuti.",
        "Grazie,<br>Giovanni<br>Poltrona Libera",
    ]),
]


def run_workflow() -> int:
    """Hourly: send the next workflow email to buyers whose time has come."""
    client = db.get_db()
    n = 0
    for d in client.collection("buyers").stream():
        b = {"id": d.id, **d.to_dict()}
        if P.is_test(b.get("email")) or not b.get("created_at"):
            continue
        step = int(b.get("steps_sent") or 0)
        if step >= len(STEPS):
            continue
        days, subject, build = STEPS[step]
        if db.now() - b["created_at"] < timedelta(days=days):
            continue
        g = CATALOG.get(b["slug"], CATALOG["squadra"])
        _send(b, subject, build(b, g))
        d.reference.update({"steps_sent": step + 1, "last_step_at": db.now()})
        n += 1
    return n


def by_token(token: str) -> dict | None:
    if not token or len(token) < 10:
        return None
    found = list(db.get_db().collection("buyers").where("token", "==", token).limit(1).stream())
    return {"id": found[0].id, **found[0].to_dict()} if found else None


def buyers() -> list[dict]:
    items = [{"id": d.id, **d.to_dict()} for d in db.get_db().collection("buyers").stream() if not P.is_test(d.to_dict().get("email"))]
    items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return items
