"""
Human explanations of funnel criteria (Italian). The funnel speaks in keys ("min_sources") — the founder
reads sentences: what is measured, current value vs required, and what to do about it.
"""
from __future__ import annotations

from typing import Any

STAGE_LABELS = {
    "signal_collected": "1 · Segnali raccolti",
    "problem_clustered": "2 · Problema ricorrente",
    "market_sized": "3 · Mercato stimato",
    "competition_checked": "4 · Competizione verificata",
    "founder_fit_checked": "5 · Economia e barriere",
    "interviews_done": "6 · Interviste fatte",
    "presale_validation": "7 · Verifica che paghino",
    "validated": "8 · Validata",
}

STAGE_ORDER = list(STAGE_LABELS)


def _pct(v) -> str:
    try:
        return f"{float(v) * 100:.0f}%"
    except (TypeError, ValueError):
        return "—"


def _num(v) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        return f"{int(f)}" if f.is_integer() else f"{f:.1f}"
    except (TypeError, ValueError):
        return str(v)


def _eur(v) -> str:
    if v is None:
        return "—"
    v = float(v)
    return f"€{v/1e6:.0f}M" if v >= 1e6 else f"€{v/1e3:.0f}k"


def explain(key: str, threshold: Any, m: dict[str, Any]) -> dict[str, str]:
    """Returns {"label", "current", "required", "why", "action"} for one failing criterion."""
    src_n = m.get("sources") or 0
    table: dict[str, dict[str, str]] = {
        "min_signals": dict(label="Volume di segnali", current=_num(m.get("signals")), required=f"≥ {threshold}",
                            why="Servono abbastanza persone che descrivono lo stesso problema perché non sia un caso isolato.",
                            action="Nessuna azione: lo scraping ogni 6 ore accumula. Se resta fermo per settimane, il problema è raro."),
        "min_authors": dict(label="Persone diverse", current=_num(m.get("authors")), required=f"≥ {threshold}",
                            why="Contiamo gli autori distinti, non i messaggi: 30 post della stessa persona valgono 1.",
                            action="Come sopra: accumulo. Reddit moltiplica gli autori."),
        "min_sources": dict(label="Fonti indipendenti", current=f"{src_n} ({'una sola fonte' if src_n == 1 else 'fonti'})", required=f"≥ {threshold}",
                            why="Se tutti i segnali vengono da un unico sito, può essere un bias di quella community. Due fonti diverse (es. forum + YouTube, o Reddit + recensioni) lo escludono.",
                            action="Aggiungi una fonte al keyword set (Reddit quando attivo, YouTube, un altro forum) o attendi che ne arrivi una."),
        "min_recent_share": dict(label="Problema vivo oggi", current=_pct(m.get("recent_share")) + " dei segnali negli ultimi 30 gg", required=f"≥ {_pct(threshold)}",
                                 why="Un problema discusso tre anni fa e non più oggi è probabilmente già risolto da qualcuno.",
                                 action="Nessuna azione: se la fonte è viva, la quota sale da sola al prossimo scrape."),
        "min_wtp_avg": dict(label="Disponibilità a pagare", current=_num(m.get("wtp_avg")) + "/10", required=f"≥ {threshold}",
                            why="Cerchiamo segnali di budget: usano già un tool a pagamento, quantificano ore o euro persi, chiedono esplicitamente uno strumento.",
                            action="Se resta basso, il problema è fastidioso ma non vale soldi: candidato da archiviare."),
        "min_heuristic_avg": dict(label="Disponibilità a pagare (regex)", current=_num(m.get("heuristic_avg")) + "/10", required=f"≥ {threshold}",
                                  why="Proxy testuale di budget (tool citati, costi, richieste di strumenti).", action="Vedi disponibilità a pagare."),
        "attack_vector_in": dict(label="Tipo di problema", current=str(m.get("dominant_attack_vector") or "non classificato"), required="gap di funzionalità o nessuna soluzione",
                                 why="Se la maggior parte dei segnali si lamenta di un prodotto esistente (lento, bug, supporto) non è un'opportunità: è un incumbent con clienti scontenti che restano.",
                                 action="Nessuna: è un filtro di qualità. Se il vettore è 'quality_complaint', archivia."),
        "min_attackable_share": dict(label="Quota di segnali attaccabili", current=_pct(m.get("attackable_share")), required=f"≥ {_pct(threshold)}",
                                     why="Almeno metà delle persone deve descrivere un buco (nessun tool lo fa), non un difetto di un tool esistente.",
                                     action="Nessuna: filtro di qualità."),
        "require_market_components": dict(label="Stima di mercato", current="incompleta", required="n. clienti potenziali × spesa annua compilati",
                                          why="Senza numero di clienti e spesa annua non esiste TAM/SAM/SOM.",
                                          action="L'arricchimento automatico li compila; puoi correggerli a mano con PUT /opportunities/{id}/market/…"),
        "min_sam_eur": dict(label="Mercato raggiungibile (SAM)", current=_eur(m.get("sam_eur")), required=f"≥ {_eur(threshold)}",
                            why="Sotto questa soglia anche vincendo non c'è una startup, c'è un side project.",
                            action="Verifica i componenti (clienti potenziali, spesa annua): se sono sottostimati correggili con fonte."),
        "min_market_confidence": dict(label="Affidabilità della stima", current=str(m.get("market_confidence") or "—"), required=f"≥ {threshold}",
                                      why="Un SAM da €50M con confidenza 'low' è un numero inventato.",
                                      action="Trova una fonte reale per il numero di clienti potenziali (ISTAT, Eurostat, report di settore) e aggiornala."),
        "require_competitors_checked": dict(label="Competitor mappati", current="non ancora", required="analisi fatta",
                                            why="Serve sapere chi c'è già prima di decidere.", action="L'arricchimento automatico la fa; oppure POST /clusters/{id}/enrich"),
        "max_competitor_count": dict(label="Numero di competitor", current=_num(m.get("competitor_count")), required=f"≤ {threshold}",
                                     why="Oltre questa soglia è un mercato affollato.", action="Cerca una nicchia più stretta dentro il problema."),
        "saturation_not_in": dict(label="Saturazione", current=str(m.get("saturation") or "—").upper(), required="non ROSSO",
                                  why="Rosso = più di 12 player o un leader dominante che risolve bene il problema.",
                                  action="Se rosso, archivia o restringi la persona (es. solo studi italiani)."),
        "max_leader_reviews": dict(label="Forza del leader", current=_num(m.get("leader_reviews")) + " recensioni", required=f"≤ {threshold}",
                                   why="Un leader con centinaia di recensioni ha già i clienti e la fiducia: batterlo da soli è quasi impossibile.",
                                   action="Restringi a un segmento che il leader serve male (verticale, paese, lingua)."),
        "require_dead_product_check": dict(label="Prodotti morti", current="non verificato", required="verificato",
                                           why="Chi ci ha già provato e ha fallito ti dice il rischio nascosto.", action="Fatto dall'arricchimento automatico."),
        "min_founder_fit": dict(label="Founder fit", current=_num(m.get("founder_fit")) + "/5", required=f"≥ {threshold}",
                                why="Puoi arrivare ai primi 20 clienti da solo, con i tuoi canali, in 3 mesi?",
                                action="Compila n_reachable_linkedin e il canale in PATCH /opportunities/{id}; se il fit è basso, archivia."),
        "require_channel_reachable": dict(label="Canale raggiungibile", current="no", required="sì",
                                          why="Senza un canale che sai usare (LinkedIn, SEO, community) non vendi.", action="Indica il canale in PATCH /opportunities/{id}."),
        "require_why_now": dict(label="Perché adesso", current="mancante", required="presente con fonte",
                                why="Le opportunità vere nascono da un cambiamento recente (norma, tecnologia, prezzo, piattaforma).",
                                action="Cerca il cambiamento; se non esiste, chiediti perché nessuno l'ha fatto prima."),
        "barriers_must_be_false": dict(label="Barriere", current=", ".join(k for k, v in (m.get("barriers") or {}).items() if v) or "nessuna", required="no regolatorio / enterprise / marketplace",
                                       why="Per un founder solo senza network sono kill criteria, non penalità.", action="Archivia o trova un angolo senza quella barriera."),
        "min_gross_margin_pct": dict(label="Margine lordo", current=_pct(m.get("gross_margin_pct")), required=f"≥ {_pct(threshold)}",
                                     why="Oceano blu senza margine non è un business: se per servire ogni cliente serve lavoro umano ricorrente, il margine crolla.",
                                     action="Se il margine è basso per natura del problema (servizio, non software), archivia."),
        "delivery_model_not_in": dict(label="Modello di consegna", current=str(m.get("delivery_model") or "—"), required="software (self-serve o con vendita assistita)",
                                      why="Un modello 'service-heavy' (onboarding manuale, lavoro per cliente) non scala per un founder solo.",
                                      action="Chiediti se il lavoro umano può diventare software; se no, archivia."),
        "price_channel_consistent": dict(label="Prezzo coerente col canale", current=(f"€{m.get('price_eur_year'):.0f}/anno" if m.get("price_eur_year") else "—") + f" · canale {m.get('channel_type') or '—'}", required="outbound ≥ €1.200/anno · self-serve ≥ €240/anno",
                                         why="Vendere a mano (LinkedIn, email) costa ore per cliente: sotto ~€100/mese non rientri mai. Un prezzo basso regge solo con un canale self-serve (app store, SEO).",
                                         action="Alza il prezzo (segmento più ricco, più valore) o cambia canale; se nessuno dei due è possibile, archivia."),
        "max_mvp_weeks_solo": dict(label="Settimane per un MVP da solo", current=_num(m.get("mvp_weeks_solo")), required=f"≤ {threshold}",
                                   why="Oltre due mesi di sviluppo prima del primo euro, la validazione è già costata troppo.", action="Riduci lo scope al singolo job più doloroso."),
        "require_eg_analyzed": dict(label="Analisi execution-gap", current="non fatta", required="fatta",
                                    why="Per questo percorso servono: salute della categoria, perché i clienti restano, se cambiano davvero, vantaggio di esecuzione.", action="POST /clusters/{id}/execution-gap"),
        "max_eg_core_rating": dict(label="Rating medio del prodotto core (Capterra/G2)", current=_num(m.get("eg_avg_core_rating")), required=f"≤ {threshold}",
                                   why="Misurato sul prodotto vero, non sull'app companion: se la categoria è mediamente sopra 4 gli incumbent non fanno schifo, li usano e basta.",
                                   action="Se il core è buono e solo il mobile è pessimo, il gap è laterale: valuta se vale un prodotto a sé."),
        "max_eg_store_rating": dict(label="Rating medio app negli store", current=_num(m.get("eg_avg_store_rating")), required=f"≤ {threshold}", why="Segnale secondario (app companion).", action="—"),
        "min_eg_rated": dict(label="Incumbent con rating trovato", current=_num(m.get("eg_n_rated")), required=f"≥ {threshold}",
                             why="Per dire 'tutti fanno schifo' servono i voti di almeno 3 player.", action="Aggiungi competitor a mano se mancano (POST /competitors)."),
        "require_no_excellent_leader": dict(label="Nessun leader eccellente", current="esiste" if m.get("eg_excellent_leader") else "nessuno", required="nessuno",
                                            why="Se uno dei 10 lavora bene (≥4,5 con volume), gli scontenti vanno da lui, non da te.", action="Se esiste, il gap è già coperto: archivia o trova un segmento che lui non serve."),
        "eg_lockin_not_in": dict(label="Lock-in degli incumbent", current=str(m.get("eg_lockin_level") or "—"), required="non alto",
                                 why="Se restano per fossati veri (commercialista che impone il tool, anni di dati, integrazioni, contratti), non se ne andranno neanche per te.",
                                 action="Cerca il segmento senza lock-in (es. attività nuove senza storico) o archivia."),
        "eg_switch_in": dict(label="Cambiano davvero?", current=str(m.get("eg_do_they_switch") or "—"), required="sì o lentamente",
                             why="Lamentarsi e restare non è un mercato. Serve evidenza di migrazioni: challenger che crescono, post 'sono passato da X a Y'.",
                             action="Se 'raramente': archivia. Se 'unknown': cerca evidenze a mano."),
        "min_eg_seeking_share": dict(label="Quota che cerca alternative", current=_pct(m.get("eg_seeking_share")), required=f"≥ {_pct(threshold)}",
                                     why="Percentuale di segnali che chiedono esplicitamente un'alternativa o dicono di voler cambiare.", action="Accumulo."),
        "require_eg_structural_edge": dict(label="Vantaggio di esecuzione strutturale", current=(m.get("eg_edge") or "—")[:80], required="nominabile e strutturale",
                                           why="'Faremo meglio' non basta: serve una debolezza che l'incumbent non può correggere (architettura desktop, modello di prezzo, ecosistema).",
                                           action="Se il vantaggio è solo 'più impegno', archivia: lo copiano."),
        "max_eg_weeks_to_parity": dict(label="Settimane per pareggiare il job core", current=_num(m.get("eg_weeks_to_parity")), required=f"≤ {threshold}",
                                       why="Devi eguagliare l'incumbent sul lavoro principale prima di poter essere 'migliore'.", action="Restringi al singolo job."),
        "min_interviews": dict(label="Interviste fatte", current=_num(m.get("interviews")), required=f"≥ {threshold}",
                               why="Meno di 8 conversazioni non bastano per decidere.", action="Genera il recruiting pack e fissa le interviste."),
        "min_interview_confirm_rate": dict(label="Confermano il problema", current=_pct(m.get("interview_confirm_rate")), required=f"≥ {_pct(threshold)}",
                                           why="Deve succedere davvero a loro, non 'sì, sarebbe utile'.", action="Se sotto soglia dopo 8 interviste: archivia."),
        "min_interview_spontaneous_rate": dict(label="Lo dicono spontaneamente", current=_pct(m.get("interview_spontaneous_rate")), required=f"≥ {_pct(threshold)}",
                                               why="Se lo nominano prima che tu lo descriva, è in cima ai loro pensieri.", action="Nelle prossime interviste non anticipare il problema."),
        "min_interview_paying_rate": dict(label="Pagano già qualcosa", current=_pct(m.get("interview_paying_rate")), required=f"≥ {_pct(threshold)}",
                                          why="Chi paga già (tool, persona, servizio) per aggirare il problema ha un budget.", action="Chiedi sempre: cosa usi oggi e quanto ti costa?"),
        "min_interview_quantified_cost_count": dict(label="Costi quantificati", current=_num(m.get("interview_quantified_cost_count")), required=f"≥ {threshold}",
                                                    why="Ore/settimana o euro/mese: senza numeri non puoi prezzare.", action="Chiedi 'quanto tempo ci hai messo l'ultima volta?'"),
        "min_landing_visitors": dict(label="Visite alla landing", current=_num(m.get("landing_visitors")), required=f"≥ {threshold}",
                                     why="Sotto questa soglia il tasso di iscrizione non è statisticamente leggibile.", action="Manda traffico: outreach + €100-200 di ads."),
        "min_landing_signup_rate": dict(label="Iscrizioni con prezzo visibile", current=_pct(m.get("landing_signup_rate")), required=f"≥ {_pct(threshold)}",
                                        why="Con il prezzo in pagina, chi si iscrive ha già accettato di pagare.", action="Mostra il prezzo; se il tasso crolla, il prezzo o il problema sono sbagliati."),
        "min_presale_paid": dict(label="Hanno pagato", current=_num(m.get("presale_paid")), required=f"≥ {threshold}",
                                 why="Solo la carta di credito valida.", action="Payment link, pre-order, sconto fondatore."),
        "min_presale_conversion": dict(label="Conversione a pagamento", current=_pct(m.get("presale_conversion")), required=f"≥ {_pct(threshold)}",
                                       why="Tra chi arriva alla pagina con prezzo, quanti pagano.", action="—"),
        "min_presale_revenue_eur": dict(label="Incassato", current=_eur(m.get("presale_revenue_eur")), required=f"≥ {_eur(threshold)}", why="", action="—"),
        "min_unanswered_asks": dict(label="Richieste senza risposta", current=_num(m.get("unanswered_asks")), required=f"≥ {threshold}",
                                    why="Post che chiedono un tool e nessuno ne indica uno = domanda senza offerta.", action="—"),
        "min_velocity_30d": dict(label="Trend", current=_num(m.get("velocity_30d")), required=f"≥ {threshold}", why="Segnali ultimi 30gg / 30gg precedenti.", action="—"),
    }
    e = table.get(key)
    if not e:
        return dict(label=key, current=str(m.get(key.replace("min_", "").replace("max_", ""), "—")), required=str(threshold), why="", action="")
    return e


def next_stage_key(current: str | None) -> str | None:
    if current not in STAGE_ORDER:
        return STAGE_ORDER[1]
    i = STAGE_ORDER.index(current)
    return STAGE_ORDER[i + 1] if i + 1 < len(STAGE_ORDER) else None
