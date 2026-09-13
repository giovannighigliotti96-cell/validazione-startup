# Firestore schema

Tutte le collection sono scritte solo dal backend (Admin SDK). Le regole client sono `deny all`.

## `keyword_sets/{id}` — cosa monitorare (editabile senza codice)
| campo | tipo | note |
|---|---|---|
| name | string, unique | es. `vertical_dental` |
| description, vertical | string | `vertical` = settore di chi **compra** (vedi README: founder-bias) |
| is_active | bool | i cron scrappano solo gli attivi |
| keywords | string[] | filtro testuale locale applicato dagli scraper; vuoto = tutto |
| sources | map | config per fonte, vedi sotto |

`sources` esempio:
```json
{
  "reddit":      {"subreddits": ["Dentistry"], "sorts": ["new","top"], "time_filter": "month"},
  "hackernews":  {"queries": ["dental practice software"], "tags": "(story,comment)"},
  "indiehackers":{"queries": ["dental"]},
  "trustpilot":  {"domains": ["dentrix.com"], "pages": 3, "stars": [1,2]},
  "playstore":   {"app_ids": ["com.dentrix.ascend"], "country": "us", "lang": "en", "max_stars": 2},
  "appstore":    {"app_ids": ["123456789"], "country": "us", "max_stars": 2},
  "trends":      {"keywords": ["dental practice software", "crm software"], "geo": "US", "timeframe": "today 12-m"},
  "producthunt": {"topics": ["health"], "keywords": ["dental"], "max_pages": 5, "lookback_days": 730}
}
```

## `scrape_runs/{id}`
`keyword_set_id, keyword_set_name, trigger (manual|cron|github_actions), status (running|done|partial|failed), started_at, finished_at, stats{source: {fetched, inserted, existing, error}}`

## `raw_signals/{source}__{external_id}` — lato DOMANDA
Doc id = chiave naturale ⇒ dedup gratis, run incrementali.

| gruppo | campi |
|---|---|
| identità | source, signal_type (post/comment/review/story), external_id, parent_external_id, url, channel, keyword |
| contenuto | title, text, lang, published_at, scraped_at, raw |
| privacy | `author_hash` (sha256 salato) — **mai lo username** |
| engagement | score, num_comments, rating (1-5, review), engagement{} |
| flag WTP (regex, no LLM) | mentions_existing_tool, mentions_diy_workaround, asks_for_recommendation, mentions_cost_or_time, expresses_frustration, **heuristic_score** 0-10 |
| LLM (TODO) | is_processed, llm_problem_statement, llm_urgency, llm_frequency, llm_metadata |
| link | run_id, keyword_set_id |

## `trend_snapshots/{keyword}__{geo}__{timeframe}__{YYYY-MM-DD}`
`keyword, geo, timeframe, captured_at, series[{date,value}], slope_90d, mean_last_90d, mean_prev_90d, related_queries{rising,top}` — 1 snapshot/keyword/giorno. Valori **relativi**: confronta sempre con una keyword di riferimento nello stesso set.

## `problem_clusters/{id}` — un problema candidato (LLM, o manuale)
`name, problem_statement, vertical, persona, keyword_set_id, signal_count, distinct_sources, distinct_authors, heuristic_avg, first_seen, last_seen, velocity_30d, urgency_score, frequency_score, wtp_score, mom_test_questions[], llm_metadata`
Sub-collection **`signals/{signal_id}`** `{relevance, attached_at}` = join cluster↔segnale. `funnel.refresh_cluster_stats()` ricalcola i contatori.

## `competitor_signals/{source}__{external_id}` — lato OFFERTA
`cluster_id?, keyword_set_id?, source (producthunt|g2|capterra|keyword_planner|crunchbase|upwork|manual), name, url, tagline, keyword, launched_at, founded_year, reviews_count, rating, votes, pricing_monthly_usd, funding_usd, is_dead, search_volume, cpc_usd, competition, notes, raw, captured_at`

## `opportunity_scoring/{cluster_id}` — stato del funnel + scoring
| gruppo | campi |
|---|---|
| competizione | competitor_count, leader_reviews, saturation (blue/purple/red), saturation_notes |
| mercato | **market_estimates{component: {value, unit, source_url, method, confidence, notes, created_by}}** con component ∈ n_entities, annual_spend, geo_share, segment_share, capture_share; derivati: tam_eur, sam_eur, som_eur, market_components_complete, market_confidence |
| founder fit | founder_fit 1-5, acquisition_channel, acquisition_channel_reachable, barriers{regulatory, enterprise_sales, two_sided, capital}, why_now, prior_failed_attempts |
| funnel | funnel_stage, stage_entered_at, stage_history[{stage, at, reason}], notified_stages[], overall_score 0-100 |
| stato | is_archived, archive_reason, notes |

Formula mercato: `TAM = n_entities × annual_spend; SAM = TAM × geo_share × segment_share; SOM = SAM × capture_share`.

## `funnel_stages/{key}`
`position, key, name, description, criteria{}, notify, is_terminal` — le **soglie** vivono qui (vedi `scripts/seed_firestore.py`, chiavi interpretate in `app/services/funnel.py::_check`).

## `validation_experiments/{id}`
`cluster_id, type (interview|landing_page|ads_smoke|presale|concierge|other), status, platform, cost_eur, started_at, ended_at, metrics{}, outcome, notes, source_signal_ids[]`

`metrics` letti dal funnel:
- interview: `n_interviews, n_confirmed_problem, n_currently_paying`
- landing_page: `visitors, signups` · ads_smoke: `spend_eur, impressions, clicks, signups`
- presale: `visitors, checkout_started, paid, revenue_eur`

## `notifications/{id}`
`cluster_id, stage_key, channel, recipient, subject, status (sent|failed|skipped), error, sent_at`
