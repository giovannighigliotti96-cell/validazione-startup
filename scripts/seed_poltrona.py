"""Poltrona Libera — two-sided landing test for the chair-rental marketplace hypothesis (titolari / professioniste).
Quotes are from public posts by salon owners (Facebook/Instagram/press), role only, no names. Run: python -m scripts.seed_poltrona"""
import copy

from app import db

NL = chr(10)
NL2 = NL + NL
BASE = "https://validazione-startup-148506634481.europe-west1.run.app"
COMMON = dict(product_name="Poltrona Libera", logo_url=f"{BASE}/static/poltrona/logo_512.png", cover_url=f"{BASE}/static/poltrona/cover_1640x856.png",
              active_variants=["A"], generated_by="manual", theme="warm", hero_photo_url=f"{BASE}/static/poltrona/salone_1.jpg",
              photo_credits="Foto: pig1103pig (CC BY-SA 2.0), The Miami Story (CC BY 2.0), Welcome to Switzerland backstage! (CC BY 2.0), bzmills (CC BY 2.0), Phalinn Ooi (CC BY 2.0), Haldane Martin / Micky Hoyle (CC BY 2.0), via Flickr. Immagini di esempio, non dei saloni iscritti.",
              notes="Marketplace affitto di poltrona: due lati, due landing. Citazioni da post pubblici di titolari, ruolo senza nome.")

OWNERS = dict(**COMMON, clarity_id="yka3nisvdz", kicker="Per titolari di saloni · Milano", hero_card_title="In tre passi", quotes_title="Ti riconosci?", quotes_lead="Frasi vere di titolari di salone.",
    listings_title="Così appaiono gli annunci", listings_hint="Esempi con dati indicativi e foto di saloni reali. Il tuo annuncio mostrerà zona, giorni, prezzo, cosa è incluso e le foto.",
    confirm_email={"subject": "Pubblica la tua postazione — {brand}", "body": (
        "Ciao{nome_sp}," + NL2 + "grazie per la registrazione su {brand}. Pubblicare la tua postazione è gratis e ci vogliono due minuti: giorni, prezzo, una foto e il numero da chiamare." + NL2 +
        "Il tuo annuncio lo completi qui (il link è personale, tienilo):" + NL + "{link_annuncio}" + NL2 +
        "Nell'annuncio le professioniste vedono il nome del salone, zona, giorni, prezzo, foto e il numero da chiamare: ti chiamano direttamente e vi mettete d'accordo tra di voi." + NL2 +
        "A presto," + NL + "Giovanni Ghigliotti" + NL + "{brand}")},
    trust=["Pubblicare è gratis, nessuna commissione", "Le professioniste ti chiamano direttamente", "Vi accordate tra di voi, senza intermediari"],
    hero_photo_caption="Una postazione libera è un'entrata in più, non un problema in più.", lock_text="", price_badge="", founder_note="Stiamo partendo a Milano con i primi saloni. Pubblicare è gratis e resta gratis per chi si iscrive adesso.", hero_note="Nell'annuncio: nome del salone, zona, giorni, prezzo, foto e il numero da chiamare.", form_name_label="Nome del salone",
    form_question="Perché la postazione oggi è vuota? (es. dipendente andata via, non trovo personale…)",
    form_positions=["hero", "bottom"], hero_show_justification=False,
    form_extra=[{"name": "nome", "placeholder": "Nome e cognome", "required": True, "first": True},
                {"name": "telefono", "placeholder": "Cellulare", "type": "tel", "required": True},
                {"name": "zona", "placeholder": "Zona / quartiere di Milano", "required": True},
],
    quotes=[{"quote": "Prima del Covid era facile trovare dipendenti: lo scrivevi su un social, mettevi un foglio A4 in vetrina e arrivavano. Adesso niente.", "role": "Titolare di salone"},
            {"quote": "Dieci ore al giorno per 1.200 euro: i giovani non vogliono più farlo. E io resto sola a mandare avanti il negozio.", "role": "Titolare di salone, Firenze"},
            {"quote": "Cerchiamo parrucchiera/e per affitto poltrona: salone moderno, curato, in viale centrale. Scrivici su WhatsApp.", "role": "Titolare di salone, Modena"},
            {"quote": "Affitto poltrona per parrucchiere o barbiere, zona San Giovanni. Per info chiamare.", "role": "Titolare di salone, Roma"}],
    variants=[dict(key="A", target_language="it", headline="Hai una poltrona libera? *Pubblicala gratis* e ricevi le chiamate delle professioniste.",
        subheadline="Non trovi personale e una postazione resta vuota? Affittala a una professionista che lavora in proprio. Pubblichi l'annuncio in due minuti: zona, giorni, prezzo e una foto. Le professioniste di Milano lo vedono e ti chiamano direttamente: giorni, orari, prezzo e tipo di collaborazione li decidete voi.",
        cta="Pubblica gratis la tua postazione", price_eur_month=0, price_text="Gratis · pubblicare e ricevere chiamate non costa nulla",
        price_justification="",
        benefits=["Le professioniste ti chiamano direttamente: nessun passaggio in mezzo", "Il prezzo lo decidi tu: canone fisso, misto o percentuale sugli incassi", "Ti chiama solo chi ha visto l'annuncio con giorni, prezzo e cosa cerchi", "Vi accordate direttamente: giorni, orari, prova, condizioni", "Modifichi o metti in pausa l'annuncio quando vuoi", "Nessun costo, nessuna commissione"],
        how_it_works=["Ti registri e pubblichi la postazione: nome del salone, zona, giorni, prezzo, cosa è incluso, una foto e il numero da chiamare. Due minuti.", "Lo controlliamo e lo mettiamo online in giornata. Le professioniste di Milano lo vedono con il tuo numero.", "Ti chiamano direttamente. Le incontri in salone e vi mettete d'accordo tra di voi."],
        objections=[{"objection": "Quanto costa?", "answer": "Niente. Pubblicare l'annuncio e ricevere le chiamate delle professioniste è gratis. Nessuna commissione sul canone."},
                    {"objection": "Chi vede il mio annuncio?", "answer": "Le parrucchiere e i barbieri che cercano una postazione a Milano. Vedono nome del salone, zona, giorni, prezzo, cosa è incluso, foto e il numero da chiamare: tutto in chiaro, così ti chiamano direttamente."},
                    {"objection": "Che tipo di professionista arriva?", "answer": "Parrucchiere e barbieri che vogliono lavorare in proprio senza aprire un salone: chi lavora a domicilio, chi ha lasciato un salone, chi vuole una postazione qualche giorno a settimana. Nell'annuncio scrivi tu chi cerchi (es. esperta in schiariture, taglio uomo, part-time)."},
                    {"objection": "Come funziona l'accordo?", "answer": "Lo fate tra di voi: giorni, orari, prezzo, prova, cosa è incluso. Le formule più usate a Milano sono canone fisso (350-500 € in periferia, 500-700 in semicentro, 700-1.200 in centro), percentuale sugli incassi, o mista. Noi pubblichiamo l'annuncio, il resto lo decidete voi."},
                    {"objection": "E le clienti?", "answer": "Lo decidete voi: ognuna con le proprie, oppure condivise con regole chiare. Mettetelo per iscritto quando vi accordate."},
                    {"objection": "Posso pubblicare più postazioni?", "answer": "Sì, una per annuncio. Scrivici e ti attiviamo il secondo."},
                    {"objection": "Ricevo troppe chiamate?", "answer": "Nell'annuncio scrivi tu chi cerchi (specialità, giorni, part-time): ti chiama chi si riconosce. Se vuoi una pausa, metti l'annuncio in pausa dal tuo link personale."},
                    {"objection": "Posso togliere l'annuncio?", "answer": "Quando vuoi, dal tuo link personale: lo metti in pausa o lo chiudi in un clic."}])])

STYLISTS = dict(**COMMON, clarity_id="yka1e47v91", thanks_text="Registrazione confermata, è gratis. Ti abbiamo mandato una email: appena c'è una postazione nella tua zona ti scriviamo noi. Intanto puoi guardare le postazioni già online e chiamare direttamente.", kicker="Per parrucchiere e barbieri · Milano", hero_card_title="In tre passi", quotes_title="Saloni che cercano una professionista", quotes_lead="Annunci pubblicati da titolari nelle ultime settimane.",
    listings_title="Così appaiono gli annunci", listings_hint="Esempi con dati indicativi e foto di saloni reali: mostrano cosa vedrai. Quando un salone pubblica una postazione vera, vedi nome del salone, zona, giorni, prezzo, cosa è incluso, foto e il numero da chiamare.",
    confirm_email={"subject": "Registrazione confermata — {brand}", "body": (
        "Ciao{nome_sp}," + NL2 + "la tua registrazione su {brand} è confermata: è gratis e resta gratis." + NL2 +
        "Cosa succede adesso: appena un salone della tua zona pubblica una postazione ti scriviamo noi, con nome del salone, zona, giorni, prezzo, foto e il numero della titolare. La chiami, visiti il salone e vi mettete d'accordo tra di voi su giorni, orari e condizioni." + NL2 +
        "Le postazioni già online le vedi qui: " + BASE + "/pl/postazioni" + NL2 +
        "A presto," + NL + "Giovanni Ghigliotti" + NL + "{brand}")},
    trust=["Guardare e chiamare è gratis", "Scegli tu giorni, orari e tipo di collaborazione, insieme al salone", "Visiti il salone e incontri la titolare prima di decidere"],
    hero_photo_caption="Una postazione vera, in un salone vero.", lock_text="", price_badge="", founder_note="Stiamo partendo a Milano. Per le professioniste è gratis: registrarsi, guardare, chiamare.", hero_note="Negli annunci veri trovi nome del salone e numero della titolare: chiami tu, direttamente.", form_name_label="",
    form_question="Come lavori oggi? (in un salone, a domicilio, ferma…) e cosa cerchi?",
    form_positions=["hero", "bottom"], hero_show_justification=False,
    form_extra=[{"name": "nome", "placeholder": "Nome e cognome", "required": True, "first": True},
                {"name": "telefono", "placeholder": "Cellulare", "type": "tel", "required": True},
                {"name": "zona", "placeholder": "Zona di Milano dove vorresti lavorare", "required": True},
                {"name": "specialita", "placeholder": "Cosa fai (colore, taglio donna, uomo/barba, extension…)"}],
    quotes=[{"quote": "Affittiamo una postazione nel nostro salone: moderno, curato, in viale centrale. Cerchiamo una professionista indipendente.", "role": "Titolare di salone, Modena"},
            {"quote": "Offro affitto poltrona nel salone, Milano centro.", "role": "Titolare di salone, Milano"},
            {"quote": "Affitto poltrona per parrucchiere o barbiere, zona San Giovanni.", "role": "Titolare di salone, Roma"},
            {"quote": "Cerchiamo un talento indipendente che voglia condividere con noi uno spazio di lavoro.", "role": "Titolare di salone"}],
    variants=[dict(key="A", target_language="it", headline="Non aprire un salone. Lavora in proprio: *affitta una poltrona*.",
        subheadline="Trova una postazione in un salone di Milano e lavora alle tue condizioni: scegli giorni, orari e tipo di collaborazione insieme alla titolare. Guardi gli annunci gratis, chiami il salone che ti piace, lo visiti e vi mettete d'accordo tra di voi.",
        cta="Registrati gratis", price_eur_month=0, price_text="Gratis · nessun pagamento per cercare né per chiamare",
        price_justification="",
        benefits=["Lavori in proprio senza aprire un salone: niente locale, niente attrezzature, niente investimento", "Scegli tu giorni, orari e tipo di collaborazione, insieme al salone", "Vedi nome del salone, zona, giorni, prezzo, cosa è incluso, foto e numero: chiami tu", "Visiti il salone e incontri la titolare prima di decidere", "Gratis: registrarti, guardare e chiamare non costano nulla"],
        how_it_works=["Ti registri gratis e guardi le postazioni di Milano: salone, zona, giorni, prezzo, foto, numero.", "Quella che ti piace? Chiami la titolare, direttamente dall'annuncio.", "Visiti il salone e vi mettete d'accordo tra di voi: giorni, orari, prezzo, prova."],
        objections=[{"objection": "Quanto costa?", "answer": "Niente. Registrarti, guardare gli annunci e chiamare i saloni è gratis."},
                    {"objection": "Cosa vedo negli annunci?", "answer": "Zona, giorni e orari disponibili, prezzo al mese, cosa è incluso (lavatesta, prodotti, phon…), foto, che professionista cerca il salone, il nome del salone e il numero da chiamare."},
                    {"objection": "Come mi accordo con il salone?", "answer": "Direttamente con la titolare: giorni, orari, prezzo (fisso, percentuale o misto), periodo di prova, clienti. Noi pubblichiamo gli annunci, il resto lo decidete voi."},
                    {"objection": "Posso lavorare solo qualche giorno a settimana?", "answer": "Sì, molti saloni offrono postazioni part-time. Negli annunci trovi i giorni disponibili e nel messaggio alla titolare scrivi cosa cerchi."},
                    {"objection": "Quanto guadagno davvero?", "answer": "Esempio: 4 clienti al giorno × 45 € × 20 giorni = 3.600 € al mese, meno il prezzo della postazione (300-700 €) e i prodotti. Il resto è tuo."},
                    {"objection": "E se il salone non mi piace?", "answer": "Nessun obbligo: chiami, visiti, decidi. Puoi chiamare tutti i saloni che vuoi."},
                    {"objection": "Non ci sono postazioni nella mia zona", "answer": "Registrati lo stesso: appena un salone della tua zona pubblica una postazione ti scriviamo noi."}])])

LISTINGS = [
    {"photo_url": f"{BASE}/static/poltrona/postazione_1.jpg", "tags": ["Isola", "Mar–Sab", "1 postazione"], "title": "Postazione in salone di 80 mq, luce naturale",
     "text": "Poltrona, specchio, lavatesta condiviso, prodotti esclusi. Salone con 2 titolari, clientela 30-55 anni.", "price": "550 €", "price_note": "al mese", "note": "Esempio di annuncio"},
    {"photo_url": f"{BASE}/static/poltrona/postazione_2.jpg", "tags": ["Porta Romana", "Lun–Ven", "colore"], "title": "Postazione in salone con color bar",
     "text": "Ideale per colorista: lavatesta dedicato, prodotti a consumo. Salone di 6 postazioni, aperto dal 2015.", "price": "700 €", "price_note": "al mese", "note": "Esempio di annuncio"},
    {"photo_url": f"{BASE}/static/poltrona/postazione_3.jpg", "tags": ["Città Studi", "Mar–Sab", "libera da ottobre"], "title": "Postazione con lavatesta in pietra, salone storico",
     "text": "Salone di quartiere con clientela fidelizzata; postazione vicino all'ingresso. Prodotti inclusi fino a 60 €/mese.", "price": "480 €", "price_note": "al mese", "note": "Esempio di annuncio"},
    {"photo_url": f"{BASE}/static/poltrona/postazione_4.jpg", "tags": ["Navigli", "Gio–Sab", "anche part-time"], "title": "Mezza settimana in salone da 4 postazioni",
     "text": "Postazione condivisa: 3 giorni a settimana, orario continuato. Perfetta per chi parte in proprio.", "price": "300 €", "price_note": "al mese", "note": "Esempio di annuncio"},
    {"photo_url": f"{BASE}/static/poltrona/postazione_5.jpg", "tags": ["Bicocca", "Mar–Sab", "uomo/barba"], "title": "Postazione per barber in salone unisex",
     "text": "Poltrona reclinabile, lavatesta, sterilizzatore. Il salone cerca un barber per la clientela maschile del quartiere.", "price": "420 €", "price_note": "al mese", "note": "Esempio di annuncio"},
]

STATEMENT = ("I saloni non trovano personale e restano con postazioni vuote; le professioniste che vogliono mettersi in proprio non possono aprire un salone. "
             "L'affitto di poltrona esiste dal 2018 ma si fa alla cieca su Facebook.")

if __name__ == "__main__":
    STYLISTS["hero_photo_url"] = f"{BASE}/static/poltrona/salone_2.jpg"  # newer, brighter salon for the professionals page
    OWNERS["hero_photo_url"] = f"{BASE}/static/poltrona/salone_4.jpg"  # modern salon (Glam 5, CC BY) for the owners page
    OWNERS["listings"] = LISTINGS
    STYLISTS["listings"] = LISTINGS
    for offer in (OWNERS, STYLISTS):  # variant B: same copy, bronze accent + bronze CTA (A/B on colour only)
        b = copy.deepcopy(offer["variants"][0]); b.update(key="B", accent="#8a6a3d", cta_bg="#5b4526")
        offer["variants"] = [offer["variants"][0], b]; offer["active_variants"] = ["A", "B"]
    for cid, offer, name, persona in (("poltrona_libera_titolari", OWNERS, "Affitto di poltrona — lato titolari di saloni", "titolare di salone"),
                                      ("poltrona_libera_professioniste", STYLISTS, "Affitto di poltrona — lato professioniste", "parrucchiera/barbiere freelance")):
        db.upsert(db.PROBLEM_CLUSTERS, cid, {"name": name, "vertical": "salons_barbers", "persona": persona, "status": "hypothesis", "problem_statement": STATEMENT,
                                             "created_by": "manual", "created_at": db.now(), "signal_count": 0, "path": "marketplace_test",
                                             "evidence_sources": ["post pubblici titolari Facebook/Instagram", "stampa Firenze", "guide CNA/CGIA/Confartigianato"]})
        from google.cloud.firestore_v1 import DELETE_FIELD

        ref = db.get_db().collection(db.OPPORTUNITY_SCORING).document(cid)
        if ref.get().exists:
            ref.update({"offer.listing_preview": DELETE_FIELD, "offer.hero_card_title": DELETE_FIELD})
        db.upsert(db.OPPORTUNITY_SCORING, cid, {"cluster_id": cid, "funnel_stage": "signal_collected", "offer": offer, "is_archived": False, "created_at": db.now()})
        print("ok", cid)
