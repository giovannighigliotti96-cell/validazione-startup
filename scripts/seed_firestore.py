"""
Seed Firestore: funnel stages (with PLACEHOLDER thresholds) + initial keyword sets.
Safe to re-run: upserts by key/name. Run:  python -m scripts.seed_firestore
"""
from __future__ import annotations

from app import db

# ----------------------------------------------------------------------------
# FUNNEL STAGES — criteria = thresholds required to ENTER the stage.
# >>> ALL NUMBERS ARE PLACEHOLDERS TO TUNE TOGETHER. Edit via PATCH /funnel/stages/{key}.
# Supported keys: see app/services/funnel.py::_check
# ----------------------------------------------------------------------------
FUNNEL_STAGES = [
    dict(position=1, key="signal_collected", name="Segnali raccolti",
         description="Il cluster esiste e ha almeno un segnale. Punto di ingresso automatico.",
         criteria={}, notify=False, is_terminal=False),
    dict(position=2, key="problem_clustered", name="Problema ricorrente",
         description="Il problema è espresso da più persone, su più fonti, non da un singolo thread.",
         # min_sources 2 until Reddit is live (then 3). min_recent_share: >=50% of signals from the last 30 days = problem alive.
         criteria={"min_signals": 20, "min_sources": 2, "min_authors": 15, "min_heuristic_avg": 3.0, "min_recent_share": 0.5,
                   "attack_vector_in": ["feature_gap", "no_solution_exists"], "min_attackable_share": 0.5},
         notify=False, is_terminal=False),
    dict(position=3, key="market_sized", name="Mercato stimato",
         description="TAM/SAM/SOM compilati per componenti (anche a mano) e SAM sopra soglia.",
         criteria={"require_market_components": True, "min_sam_eur": 30_000_000, "min_market_confidence": "medium"},
         notify=False, is_terminal=False),
    dict(position=4, key="competition_checked", name="Competizione verificata",
         description="Offerta mappata (Product Hunt / G2 / Capterra). Non è oceano rosso.",
         criteria={"require_competitors_checked": True, "max_competitor_count": 12, "saturation_not_in": ["red"],
                   "max_leader_reviews": 500, "require_dead_product_check": True},
         notify=False, is_terminal=False),
    dict(position=5, key="founder_fit_checked", name="Founder fit",
         description="Posso raggiungere i primi 20 clienti da solo con un canale che so usare. C'è un why-now.",
         criteria={"min_founder_fit": 4, "require_channel_reachable": True, "require_why_now": True,
                   "barriers_must_be_false": ["regulatory", "enterprise_sales", "two_sided"]},
         notify=True, is_terminal=False),
    dict(position=6, key="interviews_done", name="Interviste Mom Test",
         description="Interviste fatte; la maggioranza conferma il problema e una parte già paga per soluzioni.",
         criteria={"min_interviews": 8, "min_interview_confirm_rate": 0.6, "min_interview_spontaneous_rate": 0.4,
                   "min_interview_paying_rate": 0.4, "min_interview_quantified_cost_count": 3},
         notify=False, is_terminal=False),
    dict(position=7, key="presale_validation", name="VERIFICA CHE PAGHINO (carta di credito)",
         description="Tutto il resto è confermato. Ora: landing con prezzo + payment link / smoke test ads. È QUI che arriva la mail.",
         criteria={"min_landing_visitors": 150, "min_landing_signup_rate": 0.08},
         notify=True, is_terminal=False),
    dict(position=8, key="validated", name="Validata",
         description="Qualcuno ha pagato prima che il prodotto esista.",
         criteria={"min_presale_paid": 5, "min_presale_conversion": 0.03},
         notify=True, is_terminal=True),
]

# ----------------------------------------------------------------------------
# App ids verified 2026-09-13. Find others: google_play_scraper.search('Name') / Apple: number in the App Store URL.
# KEYWORD SETS — "founders_*" = people who BUILD (red-ocean bias). "vertical_*" = people who BUY.
# ----------------------------------------------------------------------------
FOUNDER_KEYWORDS = ["struggling with", "is there a tool", "wish there was", "anyone know", "frustrat",
                    "manually", "spreadsheet", "waste", "pain"]

KEYWORD_SETS = [
    dict(name="founders_general", vertical="founders", is_active=True,
         description="Le 4 community founder di partenza. Alto rumore, forte bias verso tool-per-founder.",
         keywords=FOUNDER_KEYWORDS,
         sources={
             "reddit": {"subreddits": ["Entrepreneur", "SaaS", "startups", "smallbusiness"], "sorts": ["new", "top"], "time_filter": "week"},
             "hackernews": {"queries": ["is there a tool", "wish there was a tool", "how do you handle", "frustrated with"]},
             "indiehackers": {"queries": ["struggling", "looking for a tool"]},
             "trends": {"keywords": ["small business software", "crm software"], "geo": "", "timeframe": "today 12-m"},
             "producthunt": {"topics": ["saas", "productivity"], "keywords": []},
         }),
    dict(name="vertical_dental", vertical="dentistry", is_active=True,
         description="Verticale: studi dentistici. Chi paga, non chi costruisce.", keywords=[],
         sources={
             "reddit": {"subreddits": ["Dentistry", "DentalHygiene", "dentalassistant"], "sorts": ["new", "top"], "time_filter": "month"},
             "hackernews": {"queries": ["dental practice software"]},
             "youtube": {"queries": ["dental office insurance verification workflow", "dental front desk software tutorial"], "videos_per_query": 4},
             "trends": {"keywords": ["dental practice management software", "crm software"], "geo": "US", "timeframe": "today 12-m"},
             "producthunt": {"topics": ["health"], "keywords": ["dental", "dentist"]},
         }),
    dict(name="vertical_trades", vertical="trades", is_active=True,
         description="Verticale: artigiani / edilizia / idraulici / elettricisti / HVAC.", keywords=[],
         sources={
             "reddit": {"subreddits": ["Plumbing", "electricians", "HVAC", "Construction", "Landscaping"], "sorts": ["new", "top"], "time_filter": "month"},
             "hackernews": {"queries": ["field service software", "contractor software"]},
             "playstore": {"app_ids": ["com.servicetitan.work"], "country": "us", "lang": "en"},
             "youtube": {"queries": ["plumbing business scheduling software tutorial", "hvac contractor invoicing workflow"], "videos_per_query": 4},
             "trends": {"keywords": ["field service management software", "crm software"], "geo": "US", "timeframe": "today 12-m"},
             "producthunt": {"topics": ["productivity"], "keywords": ["contractor", "field service", "plumber"]},
         }),
    dict(name="vertical_property", vertical="property_management", is_active=True,
         description="Verticale: property management / affitti.", keywords=[],
         sources={
             "reddit": {"subreddits": ["PropertyManagement", "Landlord", "realestateinvesting"], "sorts": ["new", "top"], "time_filter": "month"},
             "hackernews": {"queries": ["property management software", "landlord software"]},
             "playstore": {"app_ids": ["com.appfolio.appfolio_property_manager"], "country": "us", "lang": "en"},
             "trends": {"keywords": ["property management software", "crm software"], "geo": "", "timeframe": "today 12-m"},
             "producthunt": {"topics": ["real-estate"], "keywords": []},
         }),
    dict(name="vertical_accounting", vertical="accounting", is_active=True,
         description="Verticale: commercialisti / bookkeepers.", keywords=[],
         sources={
             "reddit": {"subreddits": ["Accounting", "Bookkeeping", "taxpros"], "sorts": ["new", "top"], "time_filter": "month"},
             "hackernews": {"queries": ["bookkeeping software", "accounting workflow"]},
             "playstore": {"app_ids": ["com.intuit.quickbooks", "com.xero.touch"], "country": "us", "lang": "en"},
             "appstore": {"app_ids": ["584606479"], "country": "us"},
             "youtube": {"queries": ["bookkeeping workflow for small accounting firm", "month end close process bookkeeper tutorial"], "videos_per_query": 4},
             "rss": {"feeds": ["https://www.accountingtoday.com/feed", "https://www.journalofaccountancy.com/rss/all-news.xml"]},
             "trends": {"keywords": ["bookkeeping software", "crm software"], "geo": "", "timeframe": "today 12-m"},
             "producthunt": {"topics": ["fintech"], "keywords": ["bookkeeping", "accountant", "invoice"]},
         }),
    # --- EU / Italy: why-now = B2B e-invoicing mandates (DE 2025-28, FR 2026-27, BE 2026, PL 2026) + Italian professions
    dict(name="eu_einvoicing_mandate", vertical="eu_sme_compliance", is_active=True, country="EU",
         description="PMI e studi professionali in DE/FR/BE/PL che devono adottare la fattura elettronica B2B (obbligo 2026-2028). Why-now regolatorio.",
         keywords=["e-invoic", "einvoic", "e-rechnung", "xrechnung", "zugferd", "facture électronique", "peppol", "factur-x"],
         sources={
             "reddit": {"subreddits": ["de_EDV", "Finanzen", "selbststaendig", "vosfinances", "entrepreneur_fr", "smallbusiness", "Peppol"], "sorts": ["new", "top"], "time_filter": "month"},
             "hackernews": {"queries": ["e-invoicing", "Peppol", "XRechnung", "ZUGFeRD"]},
             "trends": {"keywords": ["e-rechnung software", "facture électronique logiciel", "peppol", "crm software"], "geo": "", "timeframe": "today 12-m"},
             "youtube": {"queries": ["e-rechnung pflicht 2026 kleinunternehmen", "facture électronique 2026 obligation TPE"], "videos_per_query": 4, "relevance_language": "de"},
             "rss": {"feeds": ["https://peppol.org/feed/", "https://www.haufe.de/rss/steuern"]},
             "producthunt": {"topics": ["fintech"], "keywords": ["invoice", "e-invoicing", "peppol"]},
         }),
    dict(name="italia_professionisti", vertical="it_professionals", is_active=True, country="IT",
         description="Commercialisti, avvocati, geometri, consulenti del lavoro in Italia: adempimenti ricorrenti, software datati, raggiungibili via LinkedIn/ordini professionali.",
         keywords=[],
         sources={
             "reddit": {"subreddits": ["ItaliaPersonalFinance", "commercialisti", "Avvocati", "ItalyInformatica", "italy"], "sorts": ["new", "top"], "time_filter": "month"},
             "hackernews": {"queries": ["fatturazione elettronica", "commercialista software"]},
             "trends": {"keywords": ["software commercialisti", "gestionale studio legale", "software consulente del lavoro", "crm software"], "geo": "IT", "timeframe": "today 12-m"},
         }),
    # --- Discourse forums (verified 2026-09-13). Automation communities = people describing manual processes nobody's tool covers.
    dict(name="workaround_builders", vertical="smb_ops_automation", is_active=True,
         description="Utenti Make/n8n che automatizzano processi manuali di PMI: descrivono il job che nessun tool fa (no_solution_exists).",
         keywords=["manual", "manually", "spreadsheet", "every week", "every day", "client", "customer", "invoice", "hours"],
         sources={
             "forum": {"forums": [
                 {"base_url": "https://community.make.com", "categories": [], "searches": ["manually every week", "spreadsheet workflow", "is there a way to"]},
                 {"base_url": "https://community.n8n.io", "categories": [], "searches": ["manual process", "spreadsheet", "small business workflow"]},
             ], "topics_per_forum": 30, "posts_per_topic": 3},
         }),
    dict(name="ecommerce_merchants", vertical="ecommerce_smb", is_active=True,
         description="Merchant Shopify (compratori, non builder): operazioni, inventario, spedizioni, contabilità.",
         keywords=["is there an app", "manually", "spreadsheet", "wish", "hours", "no app", "can't find"],
         sources={
             "forum": {"forums": [{"base_url": "https://community.shopify.com", "categories": [], "searches": ["is there an app that", "manually every", "spreadsheet"]}], "topics_per_forum": 30, "posts_per_topic": 3},
             "reddit": {"subreddits": ["shopify", "ecommerce"], "sorts": ["new", "top"], "time_filter": "month"},
             "youtube": {"queries": ["shopify inventory management small store workflow"], "videos_per_query": 3},
             "producthunt": {"topics": ["e-commerce"], "keywords": []},
         }),
    # --- Hand-curated verticals with REAL communities (buyers, not builders). Reddit runs once REDDIT_CLIENT_ID is set.
    dict(name="vertical_service_businesses", vertical="local_service_businesses", is_active=True,
         description="Imprese di servizi locali (pulizie, giardinaggio, traslochi, pest control): r/sweatystartup è la community dei proprietari.",
         keywords=[],
         sources={
             "reddit": {"subreddits": ["sweatystartup", "Cleaningbusiness", "lawncare", "Landscaping"], "sorts": ["new", "top"], "time_filter": "month"},
             "youtube": {"queries": ["cleaning business scheduling and invoicing workflow", "lawn care business software small crew"], "videos_per_query": 4},
             "trends": {"keywords": ["cleaning business software", "lawn care software", "crm software"], "geo": "", "timeframe": "today 12-m"},
         }),
    dict(name="vertical_msp_it_services", vertical="msp", is_active=True,
         description="Managed Service Providers (piccole aziende IT che gestiscono PMI): budget alto, tool frammentati, community attivissima.",
         keywords=[],
         sources={
             "reddit": {"subreddits": ["msp", "ITManagers"], "sorts": ["new", "top"], "time_filter": "month"},
             "hackernews": {"queries": ["MSP tooling", "managed service provider software"]},
             "youtube": {"queries": ["msp business documentation billing workflow small", "msp psa rmm alternatives small shop"], "videos_per_query": 4},
             "trends": {"keywords": ["msp software", "psa software", "crm software"], "geo": "", "timeframe": "today 12-m"},
         }),
    dict(name="vertical_nonprofits", vertical="nonprofit_ops", is_active=True,
         description="Piccole nonprofit: donor management, grant reporting, volontari. Cronicamente sotto-servite e con budget (grant).",
         keywords=[],
         sources={
             "reddit": {"subreddits": ["nonprofit", "grantwriting"], "sorts": ["new", "top"], "time_filter": "month"},
             "youtube": {"queries": ["small nonprofit donor management spreadsheet workflow", "grant reporting process small nonprofit"], "videos_per_query": 4},
             "trends": {"keywords": ["nonprofit crm", "grant management software", "crm software"], "geo": "", "timeframe": "today 12-m"},
         }),
    dict(name="vertical_restaurants_bars", vertical="hospitality_owners", is_active=True,
         description="Proprietari di ristoranti/bar: inventario, turni, fornitori, margini. Pagano già (POS) e odiano i tool.",
         keywords=[],
         sources={
             "reddit": {"subreddits": ["restaurantowners", "BarOwners", "KitchenConfidential"], "sorts": ["new", "top"], "time_filter": "month"},
             "youtube": {"queries": ["restaurant inventory management spreadsheet owner", "restaurant scheduling and food cost workflow"], "videos_per_query": 4},
             "trends": {"keywords": ["restaurant inventory software", "restaurant scheduling software", "crm software"], "geo": "", "timeframe": "today 12-m"},
         }),
    dict(name="vertical_logistics_freight", vertical="freight_logistics", is_active=True,
         description="Piccoli spedizionieri, freight broker, autotrasportatori: documenti, tracking, fatturazione — molto manuale.",
         keywords=[],
         sources={
             "reddit": {"subreddits": ["FreightBrokers", "Truckers", "logistics", "supplychain"], "sorts": ["new", "top"], "time_filter": "month"},
             "youtube": {"queries": ["freight broker daily workflow load tracking spreadsheet", "small trucking company dispatch invoicing process"], "videos_per_query": 4},
             "trends": {"keywords": ["tms software small carrier", "freight broker software", "crm software"], "geo": "", "timeframe": "today 12-m"},
         }),
    dict(name="vertical_law_firms_small", vertical="small_law_firms", is_active=True,
         description="Studi legali piccoli e paralegal: intake, scadenze, fatturazione oraria, documenti.",
         keywords=[],
         sources={
             "reddit": {"subreddits": ["LawFirm", "paralegal", "Lawyertalk"], "sorts": ["new", "top"], "time_filter": "month"},
             "youtube": {"queries": ["solo law firm client intake workflow", "small law firm billing and deadlines process"], "videos_per_query": 4},
             "trends": {"keywords": ["law practice management software", "legal billing software", "crm software"], "geo": "", "timeframe": "today 12-m"},
         }),
    dict(name="vertical_insurance_agents", vertical="insurance_agencies", is_active=True,
         description="Agenzie assicurative indipendenti: rinnovi, quote da più carrier, follow-up — spreadsheet ovunque.",
         keywords=[],
         sources={
             "reddit": {"subreddits": ["InsuranceAgent", "Insurance"], "sorts": ["new", "top"], "time_filter": "month"},
             "youtube": {"queries": ["independent insurance agency renewal tracking workflow", "insurance agent crm spreadsheet follow up"], "videos_per_query": 4},
             "trends": {"keywords": ["insurance agency management system", "insurance crm", "crm software"], "geo": "", "timeframe": "today 12-m"},
         }),
    dict(name="vertical_amazon_sellers", vertical="marketplace_sellers", is_active=True,
         description="Venditori Amazon FBA / multi-marketplace: riconciliazione pagamenti, resi, inventario multi-canale.",
         keywords=[],
         sources={
             "reddit": {"subreddits": ["FulfillmentByAmazon", "AmazonSeller", "ecommerce"], "sorts": ["new", "top"], "time_filter": "month"},
             "youtube": {"queries": ["amazon fba seller bookkeeping reconciliation spreadsheet", "multi channel inventory sync small seller workflow"], "videos_per_query": 4},
             "trends": {"keywords": ["amazon seller software", "fba accounting software", "crm software"], "geo": "", "timeframe": "today 12-m"},
             "producthunt": {"topics": ["e-commerce"], "keywords": ["amazon", "seller", "marketplace"]},
         }),
    dict(name="vertical_healthcare_practices", vertical="healthcare_practices", is_active=True,
         description="Verticale: fisioterapisti, psicologi, optometristi, veterinari.", keywords=[],
         sources={
             "reddit": {"subreddits": ["physicaltherapy", "therapists", "Optometry", "veterinaryprofession"], "sorts": ["new", "top"], "time_filter": "month"},
             "hackernews": {"queries": ["practice management software", "patient scheduling"]},
             "playstore": {"app_ids": ["com.simplepractice.simple"], "country": "us", "lang": "en"},
             "youtube": {"queries": ["private practice therapist admin workflow", "physical therapy clinic scheduling software"], "videos_per_query": 4},
             "trends": {"keywords": ["practice management software", "crm software"], "geo": "", "timeframe": "today 12-m"},
             "producthunt": {"topics": ["health"], "keywords": ["clinic", "therapist", "practice"]},
         }),
]


def main() -> None:
    for st in FUNNEL_STAGES:
        db.upsert(db.FUNNEL_STAGES, st["key"], st)
    print(f"funnel_stages: {len(FUNNEL_STAGES)} upserted")

    existing = {k["name"]: k["id"] for k in db.list_all(db.KEYWORD_SETS)}
    for ks in KEYWORD_SETS:
        doc_id = existing.get(ks["name"])
        payload = dict(ks)
        if not doc_id:
            payload["created_at"] = db.now()
        db.upsert(db.KEYWORD_SETS, doc_id, payload)
    print(f"keyword_sets: {len(KEYWORD_SETS)} upserted")


if __name__ == "__main__":
    main()
