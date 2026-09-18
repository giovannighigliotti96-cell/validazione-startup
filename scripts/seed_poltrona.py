"""Poltrona Libera — two-sided landing test for the chair-rental marketplace hypothesis (titolari / professioniste).
Quotes are from public posts by salon owners (Facebook/Instagram/press), role only, no names. Run: python -m scripts.seed_poltrona"""
import copy

from app import db

NL = chr(10)
NL2 = NL + NL
BASE = "https://validazione-startup-148506634481.europe-west1.run.app"
COMMON = dict(product_name="Poltrona Libera", logo_url=f"{BASE}/static/poltrona/logo_512.png", cover_url=f"{BASE}/static/poltrona/cover_1640x856.png",
              active_variants=["A"], generated_by="manual", theme="warm", listings_title="Così appaiono gli annunci", listings_hint="Esempi di annuncio: foto reali di saloni, dati indicativi. Nome e indirizzo sempre nascosti fino alla richiesta di contatto.", hero_photo_url=f"{BASE}/static/poltrona/salone_1.jpg",
              photo_credits="Foto: pig1103pig (CC BY-SA 2.0), The Miami Story (CC BY 2.0), Welcome to Switzerland backstage! (CC BY 2.0), bzmills (CC BY 2.0), Phalinn Ooi (CC BY 2.0), Haldane Martin / Micky Hoyle (CC BY 2.0), via Flickr. Immagini di esempio, non dei saloni iscritti.",
              notes="Marketplace affitto di poltrona: due lati, due landing. Citazioni da post pubblici di titolari, ruolo senza nome.")

OWNERS = dict(**COMMON, kicker="Per titolari di saloni · Milano", hero_card_title="In tre passi", quotes_title="Ti riconosci?", quotes_lead="Frasi vere di titolari di salone.",
    confirm_email={"subject": "Sei in lista — {brand}", "body": (
        "Ciao{nome_sp}," + NL2 + "grazie: la tua postazione è in lista su {brand}." + NL2 +
        "Cosa succede adesso: entro 2-3 giorni ti chiamo io, Giovanni, per 15 minuti. Mi racconti il salone, la postazione e il canone che vorresti; "
        "poi cerco tra le professioniste della tua zona e ti presento le prime 2-3 che hanno senso per te. Se preferisci, rispondi a questa email con il giorno e l'orario migliori per la chiamata." + NL2 +
        "Per te non ci sono costi: tratteniamo il 15% del canone solo nei mesi in cui la postazione è occupata, e ti giriamo il resto entro il 5 di ogni mese." + NL2 +
        "A presto," + NL + "Giovanni Ghigliotti" + NL + "{brand}")},
    trust=["Canone incassato da noi e girato a te entro il 5 del mese", "Contratto registrato, SCIA al SUAP e sostituzione inclusi", "Zero costi fissi: tratteniamo il 15% solo quando rende"],
    hero_photo_caption="Una postazione libera è un'entrata in più, non un problema in più.", lock_text="", price_badge="", founder_note="Stiamo partendo a Milano con un primo gruppo di saloni. Le condizioni indicate sono quelle reali: nessuna sorpresa.", hero_note="Nome e indirizzo del salone visibili solo dopo la richiesta di contatto.", form_name_label="Nome del salone (non sarà mostrato)",
    form_question="Perché la postazione oggi è vuota? (es. dipendente andata via, non trovo personale…)",
    form_positions=["hero", "bottom"], 
    form_extra=[{"name": "nome", "placeholder": "Nome e cognome", "required": True, "first": True},
                {"name": "telefono", "placeholder": "Cellulare", "type": "tel", "required": True},
                {"name": "piva", "placeholder": "Partita IVA del salone", "required": True},
                {"name": "zona", "placeholder": "Zona / quartiere di Milano", "required": True},
],
    quotes=[{"quote": "Prima del Covid era facile trovare dipendenti: lo scrivevi su un social, mettevi un foglio A4 in vetrina e arrivavano. Adesso niente.", "role": "Titolare di salone"},
            {"quote": "Dieci ore al giorno per 1.200 euro: i giovani non vogliono più farlo. E io resto sola a mandare avanti il negozio.", "role": "Titolare di salone, Firenze"},
            {"quote": "Cerchiamo parrucchiera/e per affitto poltrona: salone moderno, curato, in viale centrale. Scrivici su WhatsApp.", "role": "Titolare di salone, Modena"},
            {"quote": "Affitto poltrona per parrucchiere o barbiere, zona San Giovanni. Per info chiamare.", "role": "Titolare di salone, Roma"}],
    variants=[dict(key="A", target_language="it", headline="La poltrona vuota del tuo salone *rende 500 euro al mese*. Senza fare nulla.",
        subheadline="La gestiamo noi: annuncio anonimo, selezione delle professioniste con P.IVA, visite, contratto a norma, comunicazione SUAP e incasso mensile. Tu ricevi il canone entro il 5 di ogni mese. Nessun costo fisso: tratteniamo il 15% solo quando la postazione è occupata.",
        cta="Affitta la tua postazione", price_eur_month=0, price_text="Nessun costo fisso · 15% del canone, solo quando la postazione è occupata",
        price_justification="Come un gestore per la casa: pubblichiamo, selezioniamo, facciamo firmare, incassiamo e ti giriamo il canone ogni mese. Se la professionista se ne va, la sostituiamo noi. Postazione vuota = zero costi per te.",
        benefits=["Incasso gestito: la professionista paga la piattaforma, tu ricevi il canone entro il 5 del mese", "Selezione fatta da noi: solo professioniste con P.IVA, qualifica e assicurazione RC", "Contratto a norma (modello CNA), registrazione e SCIA al SUAP preparati da noi: tu firmi e basta", "Se la professionista lascia, troviamo noi la sostituta: la postazione non resta vuota", "Annuncio anonimo: chi guarda vede foto, zona, giorni e canone, non chi sei"],
        how_it_works=["Ci dai in gestione la postazione: 3 foto, zona, giorni, canone. Firmi un mandato di 12 mesi, senza costi.", "Selezioniamo le professioniste e organizziamo le visite in salone: incontri solo chi ha senso per te.", "Firmate il contratto preparato da noi. Da lì incassiamo noi ogni mese e ti giriamo l'85% entro il 5."],
        objections=[{"objection": "E le clienti?", "answer": "Lo decidete voi e lo mettiamo per iscritto: ognuna con le proprie, oppure condivise con regole chiare. Il contratto standard prevede entrambe le opzioni."},
                    {"objection": "È legale?", "answer": "Sì. In Italia dal 2012 (accordo nazionale CNA / CCNL acconciatura); a Milano è regolato dalla delibera comunale n. 120 del 26/01/2018. Il contratto va registrato all'Agenzia delle Entrate e la professionista presenta una SCIA al SUAP: prepariamo noi entrambe le cose."},
                    {"objection": "Quante postazioni posso affittare?", "answer": "Dipende dai tuoi dipendenti: 1 postazione fino a 3 dipendenti, 2 da 4 a 9, 3 oltre i 10."},
                    {"objection": "Posso affittarla alla mia ex dipendente?", "answer": "No: le linee guida vietano di affittare a chi è stato tuo dipendente negli ultimi 5 anni, e vietano l'affitto ai saloni che hanno fatto licenziamenti negli ultimi 12-24 mesi (salvo giusta causa). Per questo ti presentiamo professioniste che vengono da altri saloni."},
                    {"objection": "Chi può prenderla in affitto?", "answer": "Solo un'impresa artigiana iscritta alla Camera di Commercio, con la qualifica di acconciatore e la P.IVA, che lavora da sola (niente collaboratori). Non basta la sola P.IVA: lo verifichiamo noi prima di presentartela."},
                    {"objection": "Quanto posso chiedere?", "answer": "A Milano: 350-500 € in periferia, 500-700 in semicentro, 700-1.200 in centro. Ti aiutiamo a fissare il canone giusto."},
                    {"objection": "Canone fisso o percentuale sugli incassi?", "answer": "Il contratto standard (modello CNA) prevede un canone fisso e, se vuoi, una quota variabile legata agli incassi della professionista fino al 50% del corrispettivo. Il fisso ti dà un'entrata certa; la quota rende di più se lei lavora tanto. Decidi tu la formula, noi la mettiamo nel contratto."},
                    {"objection": "Che garanzie ho?", "answer": "Cauzione di un mese, canone pagato in piattaforma prima che il mese inizi, assicurazione RC della professionista, contratto scritto con recesso chiaro, e se lascia la sostituiamo noi. Il tuo salone non resta mai senza tutela né senza canone dovuto."},
                    {"objection": "Quanto dura il contratto e come lo disdico?", "answer": "Il contratto standard dura 12 mesi, con 1 mese di prova iniziale in cui entrambi potete uscire senza motivo, poi disdetta con 60 giorni di preavviso via PEC o raccomandata. Cauzione di un canone, restituita alla fine."},
                    {"objection": "Perché non farlo da soli su Facebook?", "answer": "Puoi. Ma la maggior parte dei titolari non trova nessuno, e chi trova firma un accordo a voce: senza contratto e SUAP è lavoro subordinato mascherato, con contributi e sanzioni a carico tuo se passa l'ispettorato. E poi ogni mese devi chiedere i soldi. Noi facciamo tutto questo."},
                    {"objection": "Cosa vi costa?", "answer": "Il 15% del canone, trattenuto solo nei mesi in cui la postazione è occupata e pagata. Niente abbonamento, niente costi se resta vuota. Su 500 € ricevi 425 €, senza fare nulla."},
                    {"objection": "E se mi accordo direttamente con la professionista?", "answer": "Il mandato è in esclusiva per 12 mesi: se firmi fuori dalla piattaforma sono dovuti 3 mesi di commissione. Ma il punto è un altro: fuori dovresti fare da solo contratto, SUAP, incasso, solleciti e sostituzione. È esattamente il lavoro che ti togliamo."},
                    {"objection": "E se la professionista non paga?", "answer": "Paga la piattaforma con carta o addebito SEPA, prima che il mese inizi. Se non paga, la postazione torna libera e la sostituiamo: tu non rincorri nessuno."},
                    {"objection": "Chi vede il mio annuncio?", "answer": "Chiunque vede foto, zona, giorni e canone. Nome del salone, indirizzo e telefono li vedono solo le professioniste che hanno chiesto il contatto e accettato le condizioni."}])])

STYLISTS = dict(**COMMON, kicker="Per parrucchiere e barbieri con P.IVA (o che vogliono aprirla)", hero_card_title="In tre passi", quotes_title="Saloni che cercano una professionista", quotes_lead="Annunci pubblicati da titolari nelle ultime settimane.",
    confirm_email={"subject": "Sei in lista — {brand}", "body": (
        "Ciao{nome_sp}," + NL2 + "grazie: sei in lista su {brand}." + NL2 +
        "Cosa succede adesso: entro 2-3 giorni ti chiamo io, Giovanni, per 15 minuti. Mi dici zona, giorni e budget, e cosa ti serve (se non hai ancora la P.IVA, ti spiego come aprirla in due giorni). "
        "Poi ti mando le postazioni disponibili che corrispondono e fissiamo le visite con le titolari. Se preferisci, rispondi a questa email con il giorno e l'orario migliori per la chiamata." + NL2 +
        "Cercare e visitare è gratis: alla firma paghi 99 € una tantum, poi solo il canone concordato, ogni mese in piattaforma." + NL2 +
        "A presto," + NL + "Giovanni Ghigliotti" + NL + "{brand}")},
    trust=["Visiti il salone prima di firmare", "Contratto a norma con un mese di prova", "Canone in piattaforma con ricevuta: niente contanti"],
    hero_photo_caption="Una postazione vera, in un salone vero.", lock_text="postazioni da 400 € al mese", price_badge="Prime 30 iscritte: 99 € di attivazione azzerati alla firma", founder_note="Stiamo partendo a Milano con un primo gruppo di professioniste. Le condizioni indicate sono quelle reali: nessuna sorpresa.", hero_note="Chiedi il contatto per vedere nome e indirizzo e prenotare la visita. Gratis.", form_name_label="",
    form_question="Cosa ti ha frenato finora dal metterti in proprio?",
    form_positions=["hero", "bottom"], 
    form_extra=[{"name": "nome", "placeholder": "Nome e cognome", "required": True, "first": True},
                {"name": "telefono", "placeholder": "Cellulare", "type": "tel", "required": True},
                {"name": "piva", "placeholder": "Partita IVA (se non ce l'hai scrivi: no)", "required": True},
                {"name": "zona", "placeholder": "Zona di Milano preferita", "required": True},
                {"name": "specialita", "placeholder": "Specialità (colore, taglio uomo, extension…)"}],
    quotes=[{"quote": "Affittiamo una postazione nel nostro salone: moderno, curato, in viale centrale. Cerchiamo una professionista indipendente.", "role": "Titolare di salone, Modena"},
            {"quote": "Offro affitto poltrona nel salone, Milano centro.", "role": "Titolare di salone, Milano"},
            {"quote": "Affitto poltrona per parrucchiere o barbiere, zona San Giovanni.", "role": "Titolare di salone, Roma"},
            {"quote": "Cerchiamo un talento indipendente che voglia condividere con noi uno spazio di lavoro.", "role": "Titolare di salone"}],
    variants=[dict(key="A", target_language="it", headline="Lavora in proprio, *senza aprire un salone*.",
        subheadline="Postazioni in saloni veri a Milano da 400 € al mese. Guardi, visiti il salone, incontri la titolare, poi decidi. Orari tuoi, incasso tuo. Contratto a norma, SCIA e assicurazione inclusi; il canone lo paghi in piattaforma, con ricevuta. Se non hai ancora l'impresa ti aiutiamo ad aprirla.",
        cta="Guarda le postazioni", price_eur_month=0, price_text="Guardare e visitare è gratis · 99 € alla firma, poi solo il canone, in piattaforma",
        price_justification="Guardare, chiedere il contatto e visitare non costa nulla. Alla firma paghi 99 € una tantum (contratto, SUAP, assicurazione, attivazione). Poi paghi solo il canone concordato con il salone, ogni mese in piattaforma con carta o SEPA: ricevuta automatica, niente contanti, niente discussioni.",
        benefits=["Zero investimento: niente locale, niente attrezzature, niente fideiussioni", "Tieni il 100% di quello che incassi, non il 40% di uno stipendio",
                  "Postazioni verificate, con canone chiaro e cosa è incluso (prodotti, lavatesta, luce, acqua)", "Aiuto per aprire l'impresa (P.IVA, Camera di Commercio, INPS) e per l'assicurazione RC",
                  "Cambi salone quando vuoi: il contratto ha un preavviso chiaro"],
        how_it_works=["Guardi gli annunci della tua città: foto, zona, giorni, canone.", "Chiedi il contatto e prenoti la visita dalla piattaforma: incontri la titolare in salone prima di decidere.", "Firmi il contratto preparato da noi: da quel giorno la poltrona è tua. Il canone lo paghi ogni mese in piattaforma."],
        objections=[{"objection": "Serve la P.IVA?", "answer": "Serve un'impresa: P.IVA più iscrizione alla Camera di Commercio come impresa artigiana, con la qualifica di acconciatore. Costi reali: forfettario al 5% sul reddito i primi 5 anni, più i contributi INPS artigiani, un minimo fisso di circa 3.000 € l'anno (4.600 € senza la riduzione del 35% del forfettario). Ti mettiamo in contatto con chi apre tutto in pochi giorni."},
                    {"objection": "Posso avere una collaboratrice o un'apprendista?", "answer": "No: chi affitta la poltrona lavora da sola, è una regola delle linee guida. Se cresci al punto da avere bisogno di aiuto, è il momento di aprire il tuo salone (e noi ti facciamo il tifo)."},
                    {"objection": "Serve la qualifica?", "answer": "Sì, serve l'abilitazione di acconciatore (o barbiere). Se ce l'hai, sei pronta."},
                    {"objection": "Posso affittare nel salone dove lavoravo?", "answer": "No: la legge lo vieta per 5 anni. Ma nel salone accanto sì, ed è proprio per questo che esistiamo."},
                    {"objection": "Quanto guadagno davvero?", "answer": "Esempio: 4 clienti al giorno × 45 € × 20 giorni = 3.600 €/mese, meno il canone (400-700 €) e i prodotti. Il resto è tuo."},
                    {"objection": "Perché il canone si paga in piattaforma?", "answer": "Perché così hai contratto, SUAP, ricevute mensili e assicurazione inclusi, e se il salone non rispetta il contratto (spazi, orari, prodotti) hai qualcuno a cui rivolgerti. Il salone lo preferisce: incassa puntuale senza chiederti niente."},
                    {"objection": "Posso accordarmi direttamente con il salone?", "answer": "Il salone ha affidato la postazione a noi in esclusiva, quindi no. E senza di noi non avresti contratto, SUAP, assicurazione né tutela: saresti una dipendente in nero con altro nome."},
                    {"objection": "Quanto dura e come disdico?", "answer": "12 mesi rinnovabili, con 1 mese di prova in cui puoi uscire senza motivo; poi 60 giorni di preavviso. Cauzione di un canone, che ti viene restituita."},
                    {"objection": "E se il salone non mi piace?", "answer": "Nel mese di prova esci senza penali e ti mostriamo un'altra postazione. Nessun vincolo lungo."}])])

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
    OWNERS["hero_photo_url"] = f"{BASE}/static/poltrona/salone_3.jpg"  # modern salon (Glam 5, CC BY) for the owners page
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
