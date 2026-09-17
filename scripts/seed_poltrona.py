"""Poltrona Libera — two-sided landing test for the chair-rental marketplace hypothesis (titolari / professioniste).
Quotes are from public posts by salon owners (Facebook/Instagram/press), role only, no names. Run: python -m scripts.seed_poltrona"""
from app import db

NL = chr(10)
NL2 = NL + NL
BASE = "https://validazione-startup-148506634481.europe-west1.run.app"
COMMON = dict(product_name="Poltrona Libera", logo_url=f"{BASE}/static/poltrona/logo_512.png", cover_url=f"{BASE}/static/poltrona/cover_1640x856.png",
              active_variants=["A"], generated_by="manual", theme="warm", hero_photo_url=f"{BASE}/static/poltrona/salone_1.jpg",
              photo_credits="Foto: Welcome to Switzerland backstage! (Flickr, CC BY 2.0); pig1103pig (Flickr, CC BY-SA 2.0). Immagini di esempio, non dei saloni iscritti.",
              notes="Marketplace affitto di poltrona: due lati, due landing. Citazioni da post pubblici di titolari, ruolo senza nome.")

OWNERS = dict(**COMMON, kicker="Per titolari di saloni · Milano e Genova", hero_card_title="In tre passi",
    confirm_email={"subject": "Sei in lista — {brand}", "body": (
        "Ciao{nome_sp}," + NL2 + "grazie: la tua postazione è in lista su {brand}." + NL2 +
        "Cosa succede adesso: entro 2-3 giorni ti chiamo io, Giovanni, per 15 minuti. Mi racconti il salone, la postazione e il canone che vorresti; "
        "poi cerco tra le professioniste della tua zona e ti presento le prime 2-3 che hanno senso per te. Se preferisci, rispondi a questa email con il giorno e l'orario migliori per la chiamata." + NL2 +
        "Pubblicare e ricevere candidature è gratis: pagherai il 50% del primo canone solo se firmi un contratto con una professionista che ti ho presentato." + NL2 +
        "A presto," + NL + "Giovanni Ghigliotti" + NL + "{brand}")},
    trust=["Annuncio anonimo: niente nome, niente indirizzo", "Previsto dalla legge dal 2018, contratto e SUAP inclusi", "Gratis per il salone"],
    hero_photo_caption="Una postazione libera è un'entrata in più, non un problema in più.",
    listing_preview={"photo_url": f"{BASE}/static/poltrona/postazione_1.jpg", "tags": ["Milano · Isola", "Mar–Sab", "1 postazione"], "title": "Postazione in salone di 80 mq, luce naturale",
                     "text": "Poltrona, specchio, lavatesta condiviso, prodotti esclusi. Salone con 2 titolari, clientela 30-55 anni.", "price": "550 €", "price_note": "al mese",
                     "note": "Nome e indirizzo del salone visibili solo dopo la richiesta di contatto."}, lock_text="canone medio Milano 500-700 € al mese", form_name_label="Nome del salone (non sarà mostrato)",
    form_question="Perché la postazione oggi è vuota? (es. dipendente andata via, non trovo personale…)",
    form_extra=[{"name": "citta", "placeholder": "Città", "required": True}, {"name": "zona", "placeholder": "Zona / quartiere"},
                {"name": "canone", "placeholder": "Canone mensile che vorresti (€)"}, {"name": "dipendenti", "placeholder": "Quanti dipendenti hai oggi?", "type": "number"},
                {"name": "telefono", "placeholder": "Telefono (per fissare la visita)", "type": "tel"}],
    quotes=[{"quote": "Prima del Covid era facile trovare dipendenti: lo scrivevi su un social, mettevi un foglio A4 in vetrina e arrivavano. Adesso niente.", "role": "Titolare di salone"},
            {"quote": "Dieci ore al giorno per 1.200 euro: i giovani non vogliono più farlo. E io resto sola a mandare avanti il negozio.", "role": "Titolare di salone, Firenze"},
            {"quote": "Cerchiamo parrucchiera/e per affitto poltrona: salone moderno, curato, in viale centrale. Scrivici su WhatsApp.", "role": "Titolare di salone, Modena"},
            {"quote": "Affitto poltrona per parrucchiere o barbiere, zona San Giovanni. Per info chiamare.", "role": "Titolare di salone, Roma"}],
    variants=[dict(key="A", target_language="it", headline="La poltrona vuota del tuo salone *vale 500 euro al mese*.",
        subheadline="Affittala a una parrucchiera con partita IVA che porta le sue clienti. Il tuo annuncio è anonimo: foto, zona e disponibilità, senza nome né indirizzo. Contratto a norma e comunicazione SUAP li prepariamo noi. Per te è gratis, sempre.",
        cta="Pubblica la postazione", price_eur_month=0, price_text="Gratis per il salone, sempre",
        price_justification="Il salone non paga niente: né per pubblicare, né alla firma. Paga solo la professionista, alla firma del contratto, la metà del primo canone. Tu ricevi richieste di contatto e scegli chi incontrare.",
        benefits=["Contratto standard a norma di legge, già pronto", "Professionista verificata: P.IVA, qualifica di acconciatore, assicurazione RC",
                  "Annuncio anonimo: chi guarda vede foto, zona, giorni e canone — non chi sei", "Il canone lo incassi tu, direttamente: nessuna commissione", "Zero dipendenti da gestire: lei è un'impresa, con le sue clienti e i suoi orari",
                  "Clausole anti-furbetti: rating, cauzione e recesso chiari"],
        how_it_works=["Pubblichi la postazione: 3 foto, zona, giorni disponibili, canone. Senza nome né indirizzo.",
                      "Le professioniste interessate chiedono il contatto: vedi profilo, specialità e P.IVA, e scegli chi incontrare in salone.",
                      "Firmate il contratto standard: noi prepariamo la comunicazione al SUAP. Da lì il rapporto è vostro."],
        objections=[{"objection": "Mi porta via le clienti?", "answer": "Le sue clienti sono sue, le tue sono tue: è scritto nel contratto. In pratica una postazione occupata porta più passaggio in salone, non meno."},
                    {"objection": "È legale?", "answer": "Sì: l'affitto di poltrona è previsto dalla normativa per acconciatori ed estetisti dal 2018. Serve una comunicazione al SUAP del Comune, che prepariamo noi."},
                    {"objection": "Quante postazioni posso affittare?", "answer": "Dipende dai tuoi dipendenti: 1 postazione fino a 3 dipendenti, 2 da 4 a 9, 3 oltre i 10."},
                    {"objection": "Posso affittarla alla mia ex dipendente?", "answer": "No: la legge vieta di affittare a chi è stato tuo dipendente negli ultimi 5 anni. Per questo ti presentiamo professioniste che vengono da altri saloni."},
                    {"objection": "Quanto posso chiedere?", "answer": "A Milano: 350-500 € in periferia, 500-700 in semicentro, 700-1.200 in centro. A Genova un po' meno. Ti aiutiamo a fissare il canone giusto."},
                    {"objection": "Quanto dura il contratto e come lo disdico?", "answer": "Il contratto standard dura 12 mesi, con 1 mese di prova iniziale in cui entrambi potete uscire senza motivo, poi disdetta con 60 giorni di preavviso via PEC o raccomandata. Cauzione di un canone, restituita alla fine."},
                    {"objection": "Perché non farlo da soli su Facebook?", "answer": "Puoi. Ma la maggior parte dei titolari non trova nessuno, e chi trova firma un accordo a voce: senza contratto e SUAP è lavoro subordinato mascherato, con contributi e sanzioni a carico tuo se passa l'ispettorato. Noi ti portiamo la persona e ti mettiamo in regola."},
                    {"objection": "Cosa vi devo?", "answer": "Niente. Il salone non paga mai. Paga la professionista alla firma (la metà del primo canone), che al momento del contatto accetta che il salone le è stato presentato da noi."},
                    {"objection": "Chi vede il mio annuncio?", "answer": "Chiunque vede foto, zona, giorni e canone. Nome del salone, indirizzo e telefono li vedono solo le professioniste che hanno sbloccato il contatto."}])])

STYLISTS = dict(**COMMON, kicker="Per parrucchiere e barbieri con P.IVA (o che vogliono aprirla)", hero_card_title="In tre passi",
    confirm_email={"subject": "Sei in lista — {brand}", "body": (
        "Ciao{nome_sp}," + NL2 + "grazie: sei in lista su {brand}." + NL2 +
        "Cosa succede adesso: entro 2-3 giorni ti chiamo io, Giovanni, per 15 minuti. Mi dici zona, giorni e budget, e cosa ti serve (se non hai ancora la P.IVA, ti spiego come aprirla in due giorni). "
        "Poi ti mando le postazioni disponibili che corrispondono e fissiamo le visite con le titolari. Se preferisci, rispondi a questa email con il giorno e l'orario migliori per la chiamata." + NL2 +
        "Cercare e visitare è gratis: pagherai una sola volta, alla firma del contratto, la metà del primo canone." + NL2 +
        "A presto," + NL + "Giovanni Ghigliotti" + NL + "{brand}")},
    trust=["Saloni veri, canone chiaro, foto reali", "Contratto a norma con un mese di prova", "Aiuto per P.IVA e assicurazione"],
    hero_photo_caption="La tua poltrona, le tue clienti, i tuoi orari.",
    listing_preview={"photo_url": f"{BASE}/static/poltrona/postazione_1.jpg", "tags": ["Milano · Isola", "Mar–Sab", "libera da ottobre"], "title": "Postazione in salone di 80 mq, luce naturale",
                     "text": "Poltrona, specchio, lavatesta condiviso, prodotti esclusi. Salone con 2 titolari, clientela 30-55 anni.", "price": "550 €", "price_note": "al mese",
                     "note": "Chiedi il contatto per vedere nome e indirizzo e prenotare la visita. Gratis."}, lock_text="postazioni da €400/mese", form_name_label="Come ti chiami",
    form_question="Cosa ti ha frenato finora dal metterti in proprio?",
    form_extra=[{"name": "citta", "placeholder": "Città in cui vuoi lavorare", "required": True}, {"name": "zona", "placeholder": "Zona preferita"},
                {"name": "specialita", "placeholder": "Specialità (colore, taglio uomo, extension…)"}, {"name": "piva", "placeholder": "Hai già la P.IVA? (sì / no)"},
                {"name": "telefono", "placeholder": "Telefono", "type": "tel"}],
    quotes=[{"quote": "Affittiamo una postazione nel nostro salone: moderno, curato, in viale centrale. Cerchiamo una professionista indipendente.", "role": "Titolare di salone, Modena"},
            {"quote": "Offro affitto poltrona nel salone, Milano centro.", "role": "Titolare di salone, Milano"},
            {"quote": "Affitto poltrona per parrucchiere o barbiere, zona San Giovanni.", "role": "Titolare di salone, Roma"},
            {"quote": "Cerchiamo un talento indipendente che voglia condividere con noi uno spazio di lavoro.", "role": "Titolare di salone"}],
    variants=[dict(key="A", target_language="it", headline="Lavora in proprio, *senza aprire un salone*.",
        subheadline="Postazioni in saloni veri a Milano e Genova da €400 al mese. Le clienti sono tue, gli orari sono tuoi, l'incasso è tuo. Contratto a norma incluso; se non hai ancora la P.IVA ti aiutiamo ad aprirla.",
        cta="Guarda le postazioni", price_eur_month=0, price_text="Guardare e visitare è gratis · 50% del primo canone solo alla firma",
        price_justification="Guardare gli annunci, chiedere il contatto e visitare non costa nulla. Paghi una sola volta, alla firma del contratto: la metà del primo canone (es. 250 € per una postazione da 500 €). Come con un'agenzia per la casa, ma la metà.",
        benefits=["Zero investimento: niente locale, niente attrezzature, niente fideiussioni", "Tieni il 100% di quello che incassi, non il 40% di uno stipendio",
                  "Postazioni verificate, con canone chiaro e cosa è incluso (prodotti, lavatesta, luce, acqua)", "Aiuto per P.IVA in regime forfettario, qualifica e assicurazione RC",
                  "Cambi salone quando vuoi: il contratto ha un preavviso chiaro"],
        how_it_works=["Guardi gli annunci della tua città: foto, zona, giorni, canone.", "Chiedi il contatto: ricevi nome e indirizzo del salone e prenoti la visita con la titolare.",
                      "Firmi il contratto standard: da quel giorno la poltrona è tua."],
        objections=[{"objection": "Serve la P.IVA?", "answer": "Sì, l'affitto di poltrona è tra due imprese. Con il forfettario paghi il 5% di tasse i primi 5 anni; ti mettiamo in contatto con chi te la apre in due giorni."},
                    {"objection": "Serve la qualifica?", "answer": "Sì, serve l'abilitazione di acconciatore (o barbiere). Se ce l'hai, sei pronta."},
                    {"objection": "Posso affittare nel salone dove lavoravo?", "answer": "No: la legge lo vieta per 5 anni. Ma nel salone accanto sì, ed è proprio per questo che esistiamo."},
                    {"objection": "Quanto guadagno davvero?", "answer": "Esempio: 4 clienti al giorno × 45 € × 20 giorni = 3.600 €/mese, meno il canone (400-700 €) e i prodotti. Il resto è tuo."},
                    {"objection": "E se poi mi accordo direttamente con il salone?", "answer": "Quando chiedi il contatto confermi che quel salone te l'abbiamo presentato noi: se firmi con loro entro 12 mesi, la fee è dovuta, come per un'agenzia. In cambio il contratto a norma, la comunicazione SUAP e l'assicurazione li prepariamo noi: firmare fuori vuol dire fare tutto da soli."},
                    {"objection": "Quanto dura e come disdico?", "answer": "12 mesi rinnovabili, con 1 mese di prova in cui puoi uscire senza motivo; poi 60 giorni di preavviso. Cauzione di un canone, che ti viene restituita."},
                    {"objection": "E se il salone non mi piace?", "answer": "Nel mese di prova esci senza penali e ti mostriamo un'altra postazione. Nessun vincolo lungo."}])])

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
