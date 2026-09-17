"""Poltrona Libera — two-sided landing test for the chair-rental marketplace hypothesis (titolari / professioniste).
Quotes are from public posts by salon owners (Facebook/Instagram/press), role only, no names. Run: python -m scripts.seed_poltrona"""
from app import db

BASE = "https://validazione-startup-148506634481.europe-west1.run.app"
COMMON = dict(product_name="Poltrona Libera", logo_url=f"{BASE}/static/poltrona/logo_512.png", cover_url=f"{BASE}/static/poltrona/cover_1640x856.png",
              active_variants=["A"], generated_by="manual",
              notes="Marketplace affitto di poltrona: due lati, due landing. Citazioni da post pubblici di titolari, ruolo senza nome.")

OWNERS = dict(**COMMON, kicker="Per titolari di saloni · Milano e Genova", lock_text="canone medio Milano €500-700/mese", form_name_label="Nome del salone",
    form_question="Perché la postazione oggi è vuota? (es. dipendente andata via, non trovo personale…)",
    form_extra=[{"name": "citta", "placeholder": "Città", "required": True}, {"name": "zona", "placeholder": "Zona / quartiere"},
                {"name": "canone", "placeholder": "Canone mensile che vorresti (€)"}, {"name": "dipendenti", "placeholder": "Quanti dipendenti hai oggi?", "type": "number"},
                {"name": "telefono", "placeholder": "Telefono (per fissare la visita)", "type": "tel"}],
    quotes=[{"quote": "Prima del Covid era facile trovare dipendenti: lo scrivevi su un social, mettevi un foglio A4 in vetrina e arrivavano. Adesso niente.", "role": "Titolare di salone"},
            {"quote": "Dieci ore al giorno per 1.200 euro: i giovani non vogliono più farlo. E io resto sola a mandare avanti il negozio.", "role": "Titolare di salone, Firenze"},
            {"quote": "Cerchiamo parrucchiera/e per affitto poltrona: salone moderno, curato, in viale centrale. Scrivici su WhatsApp.", "role": "Titolare di salone, Modena"},
            {"quote": "Affitto poltrona per parrucchiere o barbiere, zona San Giovanni. Per info chiamare.", "role": "Titolare di salone, Roma"}],
    variants=[dict(key="A", target_language="it", headline="Hai una postazione vuota? Affittala a una professionista con P.IVA.",
        subheadline="La poltrona che oggi non usi vale €400-900 al mese. Ti presentiamo professioniste verificate della tua zona; contratto a norma, comunicazione SUAP, assicurazione e incasso mensile li facciamo noi.",
        cta="Pubblica la postazione (gratis)", price_eur_month=0, price_text="Pubblicare è gratis · 50% del primo canone solo alla firma",
        price_justification="Nessun abbonamento. Paghi una volta, solo se firmi un contratto con una professionista che ti abbiamo presentato.",
        benefits=["Contratto standard a norma di legge, già pronto", "Professionista verificata: P.IVA, qualifica di acconciatore, assicurazione RC",
                  "Canone incassato automaticamente ogni mese", "Zero dipendenti da gestire: lei è un'impresa, con le sue clienti e i suoi orari",
                  "Clausole anti-furbetti: rating, cauzione e recesso chiari"],
        how_it_works=["Pubblichi la postazione: 3 foto, giorni disponibili, canone che vorresti.",
                      "Ti presentiamo 2-3 professioniste della tua zona che cercano una poltrona; le incontri in salone.",
                      "Firmate il contratto standard: noi facciamo la comunicazione al SUAP e l'incasso del canone."],
        objections=[{"objection": "Mi porta via le clienti?", "answer": "Le sue clienti sono sue, le tue sono tue: è scritto nel contratto. In pratica una postazione occupata porta più passaggio in salone, non meno."},
                    {"objection": "È legale?", "answer": "Sì: l'affitto di poltrona è previsto dalla normativa per acconciatori ed estetisti dal 2018. Serve una comunicazione al SUAP del Comune, che prepariamo noi."},
                    {"objection": "Quante postazioni posso affittare?", "answer": "Dipende dai tuoi dipendenti: 1 postazione fino a 3 dipendenti, 2 da 4 a 9, 3 oltre i 10."},
                    {"objection": "Posso affittarla alla mia ex dipendente?", "answer": "No: la legge vieta di affittare a chi è stato tuo dipendente negli ultimi 5 anni. Per questo ti presentiamo professioniste che vengono da altri saloni."},
                    {"objection": "Quanto posso chiedere?", "answer": "A Milano: 350-500 € in periferia, 500-700 in semicentro, 700-1.200 in centro. A Genova un po' meno. Ti aiutiamo a fissare il canone giusto."},
                    {"objection": "Cosa vi devo?", "answer": "Il 50% del primo canone, una sola volta, quando firmi. Pubblicare e ricevere candidature è gratis."}])])

STYLISTS = dict(**COMMON, kicker="Per parrucchiere e barbieri con P.IVA (o che vogliono aprirla)", lock_text="postazioni da €400/mese", form_name_label="Come ti chiami",
    form_question="Cosa ti ha frenato finora dal metterti in proprio?",
    form_extra=[{"name": "citta", "placeholder": "Città in cui vuoi lavorare", "required": True}, {"name": "zona", "placeholder": "Zona preferita"},
                {"name": "specialita", "placeholder": "Specialità (colore, taglio uomo, extension…)"}, {"name": "piva", "placeholder": "Hai già la P.IVA? (sì / no)"},
                {"name": "telefono", "placeholder": "Telefono", "type": "tel"}],
    quotes=[{"quote": "Affittiamo una postazione nel nostro salone: moderno, curato, in viale centrale. Cerchiamo una professionista indipendente.", "role": "Titolare di salone, Modena"},
            {"quote": "Offro affitto poltrona nel salone, Milano centro.", "role": "Titolare di salone, Milano"},
            {"quote": "Affitto poltrona per parrucchiere o barbiere, zona San Giovanni.", "role": "Titolare di salone, Roma"},
            {"quote": "Cerchiamo un talento indipendente che voglia condividere con noi uno spazio di lavoro.", "role": "Titolare di salone"}],
    variants=[dict(key="A", target_language="it", headline="Lavora in proprio senza aprire un salone.",
        subheadline="Postazioni in saloni veri a Milano e Genova da €400 al mese. Le clienti sono tue, gli orari sono tuoi, l'incasso è tuo. Contratto a norma incluso; se non hai ancora la P.IVA ti aiutiamo ad aprirla.",
        cta="Trova la tua postazione", price_eur_month=0, price_text="€99 una tantum, solo quando firmi",
        price_justification="Cercare e visitare le postazioni è gratis. Paghi €99 una sola volta, quando firmi il contratto per la tua poltrona.",
        benefits=["Zero investimento: niente locale, niente attrezzature, niente fideiussioni", "Tieni il 100% di quello che incassi, non il 40% di uno stipendio",
                  "Postazioni verificate, con canone chiaro e cosa è incluso (prodotti, lavatesta, luce, acqua)", "Aiuto per P.IVA in regime forfettario, qualifica e assicurazione RC",
                  "Cambi salone quando vuoi: il contratto ha un preavviso chiaro"],
        how_it_works=["Ci dici città, zona, giorni e budget.", "Ti mostriamo le postazioni disponibili e visiti quelle che ti piacciono, con la titolare.",
                      "Firmi il contratto standard: da quel giorno la poltrona è tua."],
        objections=[{"objection": "Serve la P.IVA?", "answer": "Sì, l'affitto di poltrona è tra due imprese. Con il forfettario paghi il 5% di tasse i primi 5 anni; ti mettiamo in contatto con chi te la apre in due giorni."},
                    {"objection": "Serve la qualifica?", "answer": "Sì, serve l'abilitazione di acconciatore (o barbiere). Se ce l'hai, sei pronta."},
                    {"objection": "Posso affittare nel salone dove lavoravo?", "answer": "No: la legge lo vieta per 5 anni. Ma nel salone accanto sì, ed è proprio per questo che esistiamo."},
                    {"objection": "Quanto guadagno davvero?", "answer": "Esempio: 4 clienti al giorno × 45 € × 20 giorni = 3.600 €/mese, meno il canone (400-700 €) e i prodotti. Il resto è tuo."},
                    {"objection": "E se il salone non mi piace?", "answer": "Il contratto standard prevede un mese di prova e un preavviso di 30 giorni: nessun vincolo lungo."}])])

STATEMENT = ("I saloni non trovano personale e restano con postazioni vuote; le professioniste che vogliono mettersi in proprio non possono aprire un salone. "
             "L'affitto di poltrona esiste dal 2018 ma si fa alla cieca su Facebook.")

if __name__ == "__main__":
    for cid, offer, name, persona in (("poltrona_libera_titolari", OWNERS, "Affitto di poltrona — lato titolari di saloni", "titolare di salone"),
                                      ("poltrona_libera_professioniste", STYLISTS, "Affitto di poltrona — lato professioniste", "parrucchiera/barbiere freelance")):
        db.upsert(db.PROBLEM_CLUSTERS, cid, {"name": name, "vertical": "salons_barbers", "persona": persona, "status": "hypothesis", "problem_statement": STATEMENT,
                                             "created_by": "manual", "created_at": db.now(), "signal_count": 0, "path": "marketplace_test",
                                             "evidence_sources": ["post pubblici titolari Facebook/Instagram", "stampa Firenze", "guide CNA/CGIA/Confartigianato"]})
        db.upsert(db.OPPORTUNITY_SCORING, cid, {"cluster_id": cid, "funnel_stage": "signal_collected", "offer": offer, "is_archived": False, "created_at": db.now()})
        print("ok", cid)
