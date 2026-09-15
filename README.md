# Validazione Start-up — signal engine

Sistema autonomo che raccoglie segnali di **domanda insoddisfatta** (Reddit, HN, recensioni 1-2★, Trustpilot, Indie Hackers), di **offerta** (Product Hunt) e di **trend** (Google Trends), li struttura su Firestore, e fa avanzare ogni opportunità in un **funnel di validazione** con soglie configurabili. Quando un'idea arriva alla fase *"verifica che paghino con la carta di credito"* ti arriva una **mail HTML**.

Il layer semantico (estrazione problema, clustering, scoring, domande Mom Test, stima mercato, competitor, founder fit) è in [app/services/analysis.py](app/services/analysis.py) e usa **qualsiasi LLM OpenAI-compatibile** (Mistral free tier di default; Groq/OpenRouter cambiando 3 variabili) + **Tavily** per la ricerca web.

```
Fonti ──▶ raw_signals ──(LLM)──▶ problem_clusters ──▶ opportunity_scoring ──▶ funnel ──▶ 📧
          competitor_signals ─────────────────────────────────┘        ▲
          trend_snapshots                                   validation_experiments
```

## Stack
- Python 3.12 · FastAPI · **Firestore** (firebase-admin) · Docker
- Runtime 24/7: **GitHub Actions** (scheduler, senza server) + **Cloud Run** (API, scale-to-zero) + **cron-job.org** (trigger esterno)
- LLM: Mistral `ministral-8b-latest` (free) via API OpenAI-compatibile · ricerca web Tavily (free)
- Email: SMTP (Gmail app password) o Resend

## Struttura
```
app/
  config.py            variabili d'ambiente (pydantic-settings)
  db.py                Firestore: collection, helper, insert_new_only (dedup)
  heuristics.py        flag regex di willingness-to-pay (no LLM)
  models.py            Pydantic: RawSignal + payload API
  scrapers/            reddit, hackernews, indiehackers, trustpilot, appstores, trends, producthunt
  services/
    runner.py          orchestrazione run
    export.py          CSV/JSON leggibile (senza username)
    market.py          TAM/SAM/SOM per componenti
    funnel.py          motore fasi + soglie + scoring
    notify.py          email HTML
    analysis.py        LLM: extract -> cluster -> enrich (score, Mom Test, TAM/SAM/SOM, competitor, founder fit)
  routers/             keyword_sets, runs, signals+export, opportunities, cron
scripts/
  seed_firestore.py    fasi funnel (soglie placeholder) + keyword set iniziali
  run_pipeline.py      CLI: scrape | analyze | funnel | all | export | seed
firestore/SCHEMA.md    schema dettagliato
.github/workflows/     pipeline.yml (scheduler), deploy-cloudrun.yml
```

## Setup locale (10 minuti)
1. Firebase Console → crea progetto → **Firestore Database** (modalità produzione, regione `eur3`) → Project settings → Service accounts → *Generate new private key* → salva come `serviceAccount.json` nella root (è in `.gitignore`).
2. `cp .env.example .env` e compila `FIREBASE_PROJECT_ID`, `CRON_TOKEN`, `API_TOKEN`.
3. Reddit: https://www.reddit.com/prefs/apps → *create app* → tipo **script** → copia client id/secret in `.env`.
4. (Opzionale) Product Hunt: https://www.producthunt.com/v2/oauth/applications → *Developer Token*.
5. Email: Gmail → sicurezza → verifica in 2 passaggi → **Password per le app** → `SMTP_PASSWORD`.
6. ```bash
   python -m venv .venv && .venv/Scripts/activate      # (Linux/mac: source .venv/bin/activate)
   pip install -r requirements.txt
   python -m scripts.seed_firestore                    # fasi funnel + keyword set
   uvicorn app.main:app --reload                       # http://localhost:8000/docs
   ```
7. Primo test senza chiavi: `python -m scripts.run_pipeline scrape --sources hackernews`
8. Test email: `POST /notifications/test` (header `X-API-Token`).

## Uso via API (Swagger su `/docs`, header `X-API-Token`)
| cosa | endpoint |
|---|---|
| Config fonti | `GET/POST/PATCH /keyword-sets` |
| Lancia scraping | `POST /runs` `{ "keyword_set_ids": null, "sources": ["reddit","hackernews"] }` → `GET /runs` |
| Segnali | `GET /signals?min_wtp=3&source=reddit` · `GET /signals/stats/summary` |
| **Export per interviste** | `GET /export/signals.csv?min_wtp=3` (o `.json`, o `?cluster_id=...`) |
| Cluster (manuale finché non c'è l'LLM) | `POST /clusters` `{name, problem_statement, persona, signal_ids:[...]}` |
| Opportunità | `GET /opportunities` · `PATCH /opportunities/{id}` (saturation, founder_fit, why_now…) |
| Mercato | `PUT /opportunities/{id}/market/n_entities` `{value, unit, source_url, confidence}` (idem `annual_spend`, `geo_share`, `segment_share`, `capture_share`) |
| Competitor | `POST /competitors` · `POST /competitors/{id}/assign/{cluster_id}` |
| Esperimenti | `POST /experiments` `{cluster_id, type:"interview", status:"done", metrics:{n_interviews:6, n_confirmed_problem:5, n_currently_paying:2}}` |
| Funnel | `GET /funnel/stages` · `PATCH /funnel/stages/{key}` (soglie) · `POST /funnel/evaluate` |
| **Analisi LLM** | `POST /analyze` (background) · `POST /analyze/sync` · `POST /clusters/{id}/enrich?force=true` |

Ogni PATCH/PUT/POST su opportunità, mercato ed esperimenti **rivaluta il funnel** e manda la mail se scatta una fase con `notify=true`.

## Il funnel — modalità "cecchino"
Principio: fasi 2-5 automatiche e severe (il sistema uccide), fasi 6-8 umane (tu decidi). Target: 2-3 cluster/mese arrivano alle interviste.

| # | fase | entra se… | mail |
|---|---|---|---|
| 1 | signal_collected | cluster creato | |
| 2 | problem_clustered | ≥20 segnali, ≥2 fonti (→3 con Reddit), ≥15 autori distinti, WTP medio ≥3 (max tra regex EN e proxy LLM multilingua), ≥50% segnali negli ultimi 30gg, **attack_vector ∈ {feature_gap, no_solution_exists}**, ≥50% segnali attaccabili | |
| 3 | market_sized | componenti TAM/SAM/SOM compilati, SAM ≥ €30M, confidenza ≥ medium | |
| 4 | competition_checked | competitor mappati ≤12, saturazione ≠ red, leader <500 recensioni, check prodotti morti fatto | |
| 5 | founder_fit_checked | founder_fit ≥4, canale raggiungibile, why-now, **barriere = kill** (regolatorio/enterprise/due lati/capitale), **margine lordo ≥60%**, non service-heavy, **prezzo coerente col canale** (outbound ≥€1.200/anno, self-serve ≥€240), MVP ≤8 settimane | ✉ |
| 6 | interviews_done | ≥8 interviste, ≥60% confermano, ≥40% spontanee, ≥40% pagano già, ≥3 costi quantificati | |
| 7 | **presale_validation** | landing ≥150 visite, signup ≥8% con prezzo visibile | **✉ "VERIFICA CHE PAGHINO"** |
| 8 | validated | ≥5 paganti, conversione ≥3% | ✉ |

**Perché un post singolo non conta**: un cluster passa la fase 2 solo con ≥15 autori distinti su ≥3 fonti. Un problema scritto da una persona resta a fase 1.

**attack_vector** (assegnato dall'LLM a ogni segnale, aggregato per cluster): `no_solution_exists` (usano fogli/manuale/hack) > `feature_gap` (i tool esistenti non fanno X per il segmento Y) ≫ `quality_complaint` (il tool fa X ma male: bug, lentezza, UI — **non** è un'opportunità) · `price_complaint`. È il filtro che separa "QuickBooks è lento" (139 cluster nel primo run, tutti rumore) da un gap reale.

Soglie in `funnel_stages` (Firestore), modificabili con `PATCH /funnel/stages/{key}`. Chiavi supportate: `app/services/funnel.py::_check`.

## Loop interviste (fase 6)
1. `POST /clusters/{id}/recruiting-pack` → screener per Respondent/User Interviews, reply Reddit, email HN, messaggio LinkedIn + query di ricerca, dove trovare la persona.
2. Reclutamento: outreach diretto dai segnali (gratis: autori HN con email nel profilo, reply pubblica su Reddit, LinkedIn) + **Respondent.io** per professionisti B2B (~€60-120/intervista). Budget realistico: 8 interviste ≈ €400-800.
3. Dopo ogni intervista: `POST /clusters/{id}/interviews` `{"notes": "<appunti o trascrizione>", "interviewee_role": "...", "source": "respondent|reddit|linkedin"}` → l'LLM estrae `confirmed_problem`, `spontaneous`, `currently_paying`, `quantified_cost`, citazioni → il funnel si aggiorna da solo.

## Digest e discovery
- **Digest settimanale** (lunedì 07:00 UTC, o `POST /digest/send`): top 5 cluster, cosa li blocca, azione suggerita. Serve a tarare i filtri: archivia il rumore con `PATCH /opportunities/{id}` `{"is_archived": true, "archive_reason": "..."}`.
- **Discovery** (1° del mese, o `POST /discover/verticals`): l'LLM propone 5 nuovi verticali con fonti concrete → keyword set creati **disattivati** (`proposed_by: llm`); li attivi con `PATCH /keyword-sets/{id}` `{"is_active": true}`.
- **Why-now scan** (`POST /discover/why-now`): ricerca news per verticale (regolamenti, deadline, price hike, shutdown) → `why_now_candidates` sul keyword set, usati nello scoring.
- Set iniziali con why-now regolatorio: `eu_einvoicing_mandate` (fattura elettronica B2B DE/FR/BE/PL 2026-28) e `italia_professionisti`.

## Autonomia 24/7
### A) GitHub Actions (consigliato come motore principale, gratis, nessun server)
1. Push su GitHub. Settings → Secrets → aggiungi: `FIREBASE_SERVICE_ACCOUNT_B64` (`base64 -w0 serviceAccount.json`), `FIREBASE_PROJECT_ID`, `CRON_TOKEN`, `REDDIT_*`, `PRODUCTHUNT_TOKEN`, `SMTP_USER`, `SMTP_PASSWORD`, `NOTIFY_EMAIL_TO`, `NOTIFY_EMAIL_FROM`. Variable: `PUBLIC_BASE_URL`.
2. [pipeline.yml](.github/workflows/pipeline.yml) gira: scraping+funnel ogni 6h, funnel ogni ora. Il CSV `min_wtp≥3` è scaricabile come artifact di ogni run.
3. Da **cron-job.org** puoi forzare un run chiamando l'API GitHub (`repository_dispatch`):
   - URL `https://api.github.com/repos/<user>/<repo>/dispatches`, POST, header `Authorization: Bearer <fine-grained PAT con permesso Contents:write>`, `Accept: application/vnd.github+json`, body `{"event_type":"run-pipeline","client_payload":{"command":"all"}}`.

### B) Cloud Run (API sempre raggiungibile, per export/edit manuali e per cron-job.org diretto)
```bash
gcloud auth login && gcloud config set project validation-start-up
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com
gcloud run deploy validazione-startup --source . --region europe-west1 --allow-unauthenticated \
  --min-instances 0 --max-instances 1 --timeout 3600 --memory 512Mi \
  --set-env-vars "FIREBASE_PROJECT_ID=validation-start-up,CRON_TOKEN=...,API_TOKEN=...,REDDIT_CLIENT_ID=...,REDDIT_CLIENT_SECRET=...,EMAIL_PROVIDER=smtp,SMTP_USER=...,SMTP_PASSWORD=...,NOTIFY_EMAIL_TO=...,NOTIFY_EMAIL_FROM=..."
```
Su Cloud Run le credenziali Firestore arrivano automaticamente (ADC) se il service account di Cloud Run ha il ruolo *Cloud Datastore User*. Il deploy automatico è in [deploy-cloudrun.yml](.github/workflows/deploy-cloudrun.yml).

Su **cron-job.org** crea:
| job | metodo/URL | header | ogni |
|---|---|---|---|
| scrape | `POST https://<cloud-run-url>/cron/scrape` | `X-Cron-Token: <CRON_TOKEN>` | 6h |
| funnel | `POST https://<cloud-run-url>/cron/funnel` | idem | 1h |

Nota: `/cron/scrape` risponde subito (202) e lavora in background, ma Cloud Run può throttlare la CPU dopo la risposta (a meno di `--no-cpu-throttling`, che costa). **Configurazione consigliata**: scraping su GitHub Actions (job lunghi, gratis), Cloud Run solo per API/export/funnel, cron-job.org che chiama `/cron/funnel` ogni ora.

## Rischi/limiti fonti (riassunto)
| fonte | stato | nota |
|---|---|---|
| Reddit | ✅ API ufficiale | 100 req/min; PRAW gestisce i limiti. Search interno pessimo → scarichiamo new/top e filtriamo. |
| Hacker News | ✅ Algolia pubblica | la più pulita |
| App Store | ✅ RSS ufficiale | max 500 recensioni recenti/app |
| Play Store | ⚠️ libreria non ufficiale, stabile | |
| Product Hunt | ✅ API ufficiale | serve token; nessuna ricerca testuale → per topic + filtro locale |
| Google Trends | ⚠️ pytrends fragile, 429 | 1 snapshot/keyword/giorno, retry; valori relativi |
| Trustpilot | ❌ off di default | ToS vietano scraping; solo bassa frequenza |
| Indie Hackers | ❌ off di default | nessuna API; markup instabile |
| GDPR | — | niente username salvati/esportati; solo `author_hash` |

## Layer LLM — come funziona
`python -m scripts.run_pipeline analyze` (o `POST /analyze`):
1. **extract** — batch di 25 segnali non processati (prima quelli con WTP più alto) → `llm_problem_statement`, persona, urgenza/frequenza 1-5, tool citati, dolore quantificato, `is_noise`
2. **cluster** — assegnazione incrementale: il modello vede i cluster esistenti del keyword set + 40 nuovi statement e decide "assegna" o "NEW"
3. **enrich** — per i cluster con ≥5 segnali non ancora arricchiti (4 chiamate ciascuno): scoring 0-10 + domande Mom Test + why-now; componenti TAM/SAM/SOM (con Tavily); competitor + saturazione; founder fit
4. `funnel.evaluate_all()` → avanzamento fasi + email

Budget: `LLM_MAX_CALLS_PER_RUN` e `LLM_RPM` nel `.env`. Cambiare provider = `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`.
Il profilo founder usato per `assess_founder_fit` è `FOUNDER_PROFILE` in analysis.py.

## Deploy attuale
- API: https://validazione-startup-148506634481.europe-west1.run.app (Cloud Run, europe-west1, min 0 / max 1 istanza, budget alert €5)
- Scheduler: GitHub Actions ogni 6h (scrape+analyze+funnel), ogni ora (funnel)
- cron-job.org: `POST /cron/funnel` ogni ora, `GET /cron/health` ogni 30 min (header `X-Cron-Token`)
- Redeploy manuale: `gcloud run deploy validazione-startup --source . --region europe-west1 --env-vars-file runtime.yaml`

## Avvertenze di metodo
- I 4 subreddit founder producono **bias verso tool-per-founder** (oceano rosso). I set `vertical_*` sono dove cercare il blue ocean: aggiungine di nuovi via API.
- Il sistema non sostituisce le interviste: prime 5 interviste anche con dati "sporchi".
- Google Trends è relativo: ogni set include `crm software` come riferimento.
