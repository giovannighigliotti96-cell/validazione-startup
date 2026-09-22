# -*- coding: utf-8 -*-
"""Instagram plan for @poltronalibera. Different from Facebook: carousels that teach (swipe), daily stories with one
tip each, a visual grid that alternates dark / cream / photo. Audience on IG is mostly professionals, so most
value goes to them; owners get one carousel a week. Assets: scripts/make_ig_assets.py -> public/poltrona/ig/."""

SITE = "https://poltronalibera.it"

# Carousel: (slug, weekday, caption, [(slide title, slide body), ...]) — first slide is the cover, last is the CTA
CAROUSELS = [
    ("quanto_guadagni", 1, "Quanto guadagni davvero in proprio? I conti li facciamo con i numeri di Milano, non con le promesse. Salva il post per quando decidi. 🔖\n\nPostazioni disponibili: link in bio.",
     [("Quanto guadagni davvero con una poltrona in affitto", "Il conto, con i numeri di Milano. Scorri →"),
      ("4 clienti al giorno × 45 €", "= 180 € al giorno. 20 giorni al mese = 3.600 €."),
      ("Meno la postazione", "300-700 € al mese a Milano, secondo zona e giorni. Restano ~3.000 €."),
      ("Meno prodotti e contributi", "Prodotti 10-12%. Forfettario al 5% i primi 5 anni + INPS artigiani (~250 €/mese)."),
      ("In tasca: 2.000-2.300 €", "Contro 1.150-1.250 € netti da dipendente a 44 ore. Orari tuoi, clienti tue."),
      ("Il rischio vero", "Il canone lo paghi anche il mese in cui lavori poco. Serve avere 30-40 clienti proprie prima di partire."),
      ("Le postazioni con il numero della titolare", "Guardi, chiami, visiti, decidi. Gratis. Link in bio.")]),
    ("visita_salone", 3, "Prima di dire sì a una postazione, guarda queste 7 cose. Le abbiamo raccolte dalle professioniste che ci sono già passate.\n\nPostazioni disponibili: link in bio.",
     [("7 cose da guardare quando visiti un salone per una postazione", "Prima di firmare. Scorri →"),
      ("1 · La postazione", "Luce, specchio, poltrona, lavatesta dedicato o condiviso. Fai una foto: la confronti dopo."),
      ("2 · Cosa è incluso", "Prodotti? Phon? Asciugamani e lavaggio? Ricevimento clienti? Ogni «no» vale 50-100 € di canone in meno."),
      ("3 · I giorni", "Chi usa la postazione gli altri giorni? Puoi lasciare le tue cose?"),
      ("4 · Le clienti", "Ognuna le proprie, o condivise con regole? Chiedilo prima, mettetelo per iscritto."),
      ("5 · Il prezzo", "Fisso, percentuale o misto. Chiedi «oppure da concordare»: chi è flessibile chiude prima."),
      ("6 · La prova", "Un mese di prova con uscita libera per entrambe. Chi è serio te lo propone."),
      ("7 · La titolare", "Ti presenta alle sue clienti? Ha già affittato? Fatti raccontare com'è andata."),
      ("Le postazioni con foto, prezzo e numero", "Link in bio. Gratis.")]),
    ("cosa_scrivere_contratto", 5, "Per le titolari: le 12 cose da scrivere in un accordo di affitto di poltrona. Senza avvocato, ma per iscritto.\n\nHai una poltrona libera? Pubblicala gratis: link in bio.",
     [("Affitti una poltrona? Le 12 cose da scrivere", "Per titolari di salone. Scorri →"),
      ("1-3", "La postazione esatta e cosa è incluso · giorni e fasce orarie · canone, quando e come si paga."),
      ("4-6", "Cauzione (un mese) · durata 12 mesi con un mese di prova · disdetta con 60 giorni."),
      ("7-9", "Le clienti: di chi sono · i prodotti: suoi o a consumo · assicurazione RC a suo carico."),
      ("10-12", "Regole della casa (pulizia, chiavi, chiusura) · cosa succede se non paga · lei decide orari, clienti e prezzi: non è una dipendente."),
      ("Il modello di categoria esiste", "CNA e Confartigianato hanno i contratti tipo. Il commercialista li adatta in un'ora."),
      ("Pubblica la postazione, gratis", "Zona, giorni, prezzo, una foto, il tuo numero. Le professioniste ti chiamano. Link in bio.")]),
    ("domicilio", 1, "Lavori a domicilio? Questo post è per te. Nessuna morale, solo il conto.\n\nPostazioni a Milano: link in bio.",
     [("A domicilio o in una postazione?", "Il confronto onesto. Scorri →"),
      ("A domicilio", "Zero canone. Ma: la borsa in macchina, la luce della cliente, 30-40 minuti di spostamento tra una e l'altra, 4-5 clienti al giorno al massimo."),
      ("In una postazione", "300-700 € al mese. Ma: 7-8 clienti al giorno, un indirizzo dove vengono loro, lavatesta e luce vere, le clienti del salone che ti scoprono."),
      ("Il punto di pareggio", "Con 45 € a servizio, una postazione da 500 € si ripaga con 11 clienti in più al mese. Due a settimana."),
      ("Puoi fare entrambe", "Molte postazioni sono 2-3 giorni a settimana. Tieni il domicilio e provi il salone."),
      ("Guarda le postazioni part-time", "Foto, giorni, prezzo, numero. Link in bio.")]),
    ("annuncio_titolari", 3, "Titolari: il vostro annuncio non riceve risposte? Il problema, quasi sempre, è l'annuncio. 7 regole.\n\nPubblica la postazione gratis: link in bio.",
     [("Perché nessuno risponde al tuo annuncio", "Per titolari di salone. Scorri →"),
      ("1 · Apri con l'offerta", "Non «cercasi parrucchiera con esperienza». Ma «postazione con clientela avviata, giorno libero fisso, provvigione sui prodotti»."),
      ("2 · Scrivi i numeri", "Orari veri, giorni, quanto si guadagna. Chi non li scrive viene scartata: «se non lo scrive, è basso»."),
      ("3 · Foto vera", "Del salone e della postazione. Non il logo."),
      ("4 · Firmalo", "«Sono Annalisa, il salone è mio da 4 anni». Il doppio delle risposte."),
      ("5 · Una cosa sola per rispondere", "Un WhatsApp. Il CV dopo."),
      ("6 · Niente aggettivi", "Seria, motivata, dinamica: non filtrano nessuno e allontanano le brave."),
      ("7 · Ripubblica ogni 7 giorni", "Con una foto diversa. Gli algoritmi seppelliscono i post vecchi."),
      ("I 3 annunci pronti da copiare", "Sono nella guida «La dipendente è andata via». Link in bio.")]),
    ("bandiere_rosse", 5, "5 segnali che quel salone non fa per te. Meglio saperlo prima di portare le tue clienti.\n\nPostazioni verificate: link in bio.",
     [("5 bandiere rosse quando cerchi una postazione", "Scorri →"),
      ("🚩 «Paghi in base a come va»", "Senza numeri scritti. Chiedi la formula esatta e mettila nel contratto."),
      ("🚩 «Le clienti sono del salone»", "Se non è scritto il contrario, vale. Chiedi: ognuna le proprie?"),
      ("🚩 Nessun contratto", "«Ci fidiamo». Senza contratto sei una dipendente in nero con un altro nome."),
      ("🚩 Orari e listino decisi dal salone", "Allora non è una postazione in affitto: è un lavoro subordinato senza tutele."),
      ("🚩 Prova gratis di un mese", "Un mese di prova sì, a prezzo pieno e con uscita libera per entrambe. Gratis no."),
      ("Le postazioni con giorni, prezzo e numero in chiaro", "Link in bio.")]),
]

# Stories: one image each, 5 a day at 9:00, 11:30, 14:00, 17:00, 19:30 Rome. (slug, kind, text lines)
# kinds: tip (one idea), numero (a big number + line), domanda (a question to answer in DM), postazione (auto from listings), cta
STORIES = [
    ("s_tip_1", "tip", ["Prima di firmare una postazione", "chiedi: le clienti sono di chi le fa,", "o condivise con regole scritte?"]),
    ("s_num_1", "numero", ["3.600 €", "4 clienti al giorno × 45 € × 20 giorni.", "Meno la postazione, resta tuo."]),
    ("s_dom_1", "domanda", ["Lavori a domicilio", "o in un salone?", "Rispondi in DM: ti dico cosa cambia."]),
    ("s_tip_2", "tip", ["Postazioni part-time esistono:", "giovedì-sabato, o 2 giorni a settimana.", "Tieni le tue clienti, provi il salone."]),
    ("s_cta_1", "cta", ["Postazioni disponibili a Milano", "con foto, prezzo e numero.", "Link in bio."]),
    ("s_tip_3", "tip", ["Titolari: un annuncio firmato", "«sono Annalisa, il salone è mio da 4 anni»", "riceve il doppio delle risposte."]),
    ("s_num_2", "numero", ["2.100 €", "quanto costa davvero una dipendente al mese.", "Una postazione affittata ne rende 500-1.200."]),
    ("s_dom_2", "domanda", ["Titolari: quanto chiedereste", "per una postazione nella vostra zona?", "Rispondi in DM."]),
    ("s_tip_4", "tip", ["Il mese di prova", "si fa a prezzo pieno, con uscita libera.", "«Gratis un mese» è una bandiera rossa."]),
    ("s_cta_2", "cta", ["Hai una poltrona vuota?", "Pubblicala gratis: 5 minuti.", "Link in bio."]),
    ("s_tip_5", "tip", ["Affitto di poltrona: legale dal 2012.", "A Milano regolato dal 2018.", "Serve un contratto scritto e registrato."]),
    ("s_num_3", "numero", ["11 clienti", "in più al mese ripagano una postazione da 500 €.", "Due a settimana."]),
    ("s_dom_3", "domanda", ["Qual è la cosa che ti frena", "dal metterti in proprio?", "Rispondi in DM, leggo tutto io."]),
    ("s_tip_6", "tip", ["Chiama la titolare direttamente:", "il numero è nell'annuncio.", "Nessun modulo in mezzo."]),
    ("s_cta_3", "cta", ["Le postazioni della settimana", "sono online.", "Link in bio."]),
]

HIGHLIGHTS = [("Postazioni", "postazioni"), ("Come funziona", "come_funziona"), ("Saloni", "saloni"), ("Domande", "domande")]
