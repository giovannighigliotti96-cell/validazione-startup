# -*- coding: utf-8 -*-
"""Editorial plan for the Poltrona Libera Facebook page, 4 posts a week for 4 weeks, written by hand (no LLM on public copy):
  Tue 12:30  valore (a piece of the guides, useful on its own)          -> closes on the guide or on publishing a listing
  Thu 12:30  valore
  Sat 11:00  "Postazioni della settimana" (built automatically from online listings)
  Sun 18:00  community (a question, a real number, a public answer)
Listing posts are also queued automatically when a listing is approved (app.services.social.enqueue_listing).
Images: scripts/make_social_images.py -> public/poltrona/social/<slug>.png"""

SITE = "https://poltronalibera.it"
OWNERS = f"{SITE}/lp/poltrona_libera_titolari"
PROS = f"{SITE}/lp/poltrona_libera_professioniste"
CATALOG = f"{SITE}/pl/postazioni"
GUIDA_A = f"{SITE}/pl/guida/squadra"
GUIDA_B = f"{SITE}/pl/guida/poltrona"
WA = "392 590 9721"

# slot: "tue" | "thu" | "sun"   (sat is the automatic listings roundup)
# (slug, slot, audience, image headline, accent word, text)
POSTS = [
    # ---------------------------------------------------------------- settimana 1
    ("apertura", "tue", "entrambi", "La poltrona vuota del tuo salone.", "vuota",
     "Poltrona Libera nasce da una frase che ci hanno scritto le titolari di salone: «non trovo personale», «la dipendente è andata via».\n\n"
     "Dall'altra parte ci sono parrucchiere e barbieri che vogliono lavorare in proprio senza aprire un salone.\n\n"
     "Facciamo una cosa sola: i saloni pubblicano la postazione libera (gratis), le professioniste la vedono con foto, giorni, prezzo e numero, e chiamano direttamente. Poi vi accordate tra di voi.\n\n"
     f"Hai una poltrona libera? 👉 {OWNERS}\nCerchi una postazione? 👉 {PROS}"),
    ("annuncio_7_regole", "thu", "titolari", "Perché nessuno risponde al tuo annuncio.", "nessuno",
     "«Cercasi parrucchiera con esperienza, seria, disponibile sabato.» Dice cosa vuoi tu; non dice niente di quello che offri. Le brave hanno tre annunci così davanti ogni giorno e non rispondono a nessuno.\n\n"
     "Le 7 regole dell'annuncio che riceve candidature:\n1. Apri con l'offerta, non con la richiesta.\n2. Scrivi i numeri: orari veri, giorni, quanto si guadagna.\n3. Una foto vera del salone, non il logo.\n4. Firmalo: «sono Annalisa, il salone è mio da 4 anni».\n5. Chiedi una cosa sola per rispondere: un WhatsApp.\n6. Niente aggettivi (seria, motivata, dinamica).\n7. Ripubblica ogni 7 giorni con una foto diversa.\n\n"
     f"I 3 annunci pronti da copiare sono nella guida «La dipendente è andata via»: {GUIDA_A}"),
    ("community_prezzo", "sun", "entrambi", "Quanto vale una postazione nella tua zona?", "tua zona",
     "Domanda aperta, ci interessa davvero: nella tua zona di Milano, quanto chiedereste (o paghereste) al mese per una postazione a tempo pieno in un salone avviato?\n\n"
     "Le cifre che vediamo negli annunci: 350-500 € in periferia, 500-700 in semicentro, 700-1.200 in centro. Voi che ne dite? Scrivete zona e cifra nei commenti."),
    # ---------------------------------------------------------------- settimana 2
    ("conto_dipendente", "tue", "titolari", "Quanto ti costa davvero una dipendente.", "davvero",
     "Il conto che quasi nessun titolare fa. Minimo contrattuale di una qualificata (CCNL 2026): circa 1.470-1.550 € lordi. Costo per te, con contributi, TFR, tredicesima e ferie: circa 2.050-2.200 € al mese.\n\n"
     "Per andare in pari deve incassare almeno 4.500 € di servizi al mese. Sotto, ci perdi. E in tasca lei vede 1.200 €: la ragione per cui se ne va in proprio.\n\n"
     f"La stessa postazione affittata rende 500-1.200 € al mese, senza busta paga. Il confronto completo su 12 mesi è nella guida «Basta dipendenti»: {GUIDA_B}"),
    ("48_ore", "thu", "titolari", "«Me ne vado.» Le prime 48 ore.", "48 ore",
     "Quando una dipendente ti dice che se ne va, quello che fai nei primi due giorni vale più dei tre mesi dopo.\n\n"
     "1. Ascolta, non reagire: dove va e perché. Una sola controproposta scritta, se ha senso.\n2. Dieci minuti con il resto della squadra, lo stesso giorno.\n3. Scrivi alle sue clienti abituali una per una, entro 7 giorni: così ne tieni il 60-70%.\n4. Non lasciare la postazione vuota: pubblica lo stesso giorno l'annuncio per una collega e quello per una professionista in affitto.\n\n"
     f"La lettera per le clienti e il piano dei 90 giorni sono nella guida: {GUIDA_A}\nLa postazione la pubblichi gratis qui: {OWNERS}"),
    ("community_numeri", "sun", "entrambi", "Questa settimana, a Milano.", "Milano",
     "Un aggiornamento vero, senza gonfiare: i saloni che hanno pubblicato una postazione su Poltrona Libera sono online nel catalogo, con giorni, prezzo e foto; le professioniste registrate ricevono una mail appena esce una postazione adatta a loro, per mestiere e per zona.\n\n"
     f"Le postazioni disponibili adesso: {CATALOG}\nSe hai una poltrona libera: {OWNERS}"),
    # ---------------------------------------------------------------- settimana 3
    ("in_proprio", "tue", "professioniste", "Lavora in proprio, senza aprire un salone.", "in proprio",
     "Aprire un salone vuol dire affitto, attrezzature, fideiussioni. Affittare una poltrona vuol dire una postazione vera in un salone vero, con i tuoi orari e le tue clienti, da 300-400 € al mese per 2-3 giorni a settimana.\n\n"
     f"Su Poltrona Libera vedi le postazioni di Milano con zona, giorni, prezzo, foto e il numero della titolare. Chiami tu, direttamente. Gratis. 👉 {CATALOG}"),
    ("colloquio_10", "thu", "titolari", "Il colloquio in 20 minuti.", "20 minuti",
     "Un colloquio lungo non ti dice di più. Venti minuti con la stessa struttura per tutte, così le confronti sulle stesse cose:\n\n"
     "3 minuti tu presenti il salone (con i numeri dell'annuncio). 10 minuti di domande. 5 minuti di prova pratica breve e retribuita. 2 minuti di chiusura con la domanda più importante: «cosa ti serve, in soldi e orari, per dire sì?».\n\n"
     "Tre domande che rivelano tutto: «quante delle tue clienti ti seguirebbero qui?», «il sabato: che rapporto hai con il sabato?», «tra tre anni: dipendente, in proprio o un salone tuo?».\n\n"
     f"Le 10 domande e la scheda da stampare: {GUIDA_A}"),
    ("community_domanda", "sun", "titolari", "Cosa vi fa perdere una brava dipendente?", "perdere",
     "Ci hanno scritto: «dipendente andata via», «non trovo personale», «in maternità e non rientra», «si è licenziato e ora non voglio più personale».\n\n"
     "Voi titolari: qual è stata l'ultima volta che avete perso una persona brava, e perché? Rispondete nei commenti o in privato: le risposte ci servono per capire dove aiutare."),
    # ---------------------------------------------------------------- settimana 4
    ("formule", "tue", "titolari", "Fisso, misto o percentuale?", "percentuale",
     "Tre modi per affittare una postazione, nessuno giusto per tutti.\n\n"
     "Canone fisso: entrata certa (a Milano 350-1.200 € al mese secondo la zona). Percentuale sugli incassi (30-50%): rende di più se lei lavora tanto, ma serve un modo trasparente di contare. Mista, la più usata: canone ridotto più una percentuale, es. 300 € + 20%. La parte variabile non può superare metà del corrispettivo.\n\n"
     f"Nell'annuncio scrivi la formula che preferisci e aggiungi «oppure da concordare». Pubblica gratis: {OWNERS}\nIl calcolo del canone per la tua zona è nella guida: {GUIDA_B}"),
    ("premi", "thu", "titolari", "I premi che fanno restare.", "restare",
     "Le persone non restano per il fisso. Restano quando vedono che se il salone cresce, crescono anche loro.\n\n"
     "Fisso corretto + tre premi: 10-15% sui prodotti venduti (è margine tuo, dividerlo non costa), 10-20% sull'incasso servizi oltre una soglia mensile, 5-10 € per ogni nuova cliente che torna. Scritto in una pagina, firmato in due, rivisto ogni 12 mesi.\n\n"
     f"Esempio: fisso 1.470 € + 225 € di variabile su 5.800 € incassati. Lo schema da firmare è nel kit della guida: {GUIDA_A}"),
    ("community_clienti", "sun", "professioniste", "Le tue clienti restano tue.", "tue",
     "Lavorare in una postazione in affitto non vuol dire regalare le clienti al salone: come gestirle lo decidete voi due, per iscritto, prima di iniziare. Ognuna con le proprie, oppure condivise con regole chiare.\n\n"
     f"Voi come fate oggi, a domicilio o in salone? E se cercate una postazione con il numero della titolare già nell'annuncio: {CATALOG}"),
]
