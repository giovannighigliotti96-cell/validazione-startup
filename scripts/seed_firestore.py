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
         # min_wtp_avg = max(regex heuristic, LLM proxy from urgency/quantified pain/tools) -> works for DE/FR/IT sources too
         criteria={"min_signals": 20, "min_sources": 2, "min_authors": 15, "min_wtp_avg": 3.0, "min_recent_share": 0.5,
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
         # barriers = finished; margin = finished; price must cover the channel
         criteria={"min_founder_fit": 4, "require_channel_reachable": True, "require_why_now": True,
                   "barriers_must_be_false": ["regulatory", "enterprise_sales", "two_sided", "capital"],
                   "min_gross_margin_pct": 0.6, "delivery_model_not_in": ["service_heavy"],
                   "price_channel_consistent": {"outbound": 1200, "partnerships": 900, "seo_content": 300, "community": 300, "self_serve_marketplace": 240},
                   "max_mvp_weeks_solo": 8},
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
    # founders_general: people who BUILD, not buy -> developer-tool noise (red ocean). Kept for reference, inactive.
    dict(name="founders_general", vertical="founders", is_active=False,
         description="Le 4 community founder di partenza. Alto rumore, forte bias verso tool-per-founder.",
         keywords=FOUNDER_KEYWORDS,
         sources={
             "reddit": {"subreddits": ["Entrepreneur", "SaaS", "startups", "smallbusiness"], "sorts": ["new", "top"], "time_filter": "week"},
             "hackernews": {"queries": ["is there a tool", "wish there was a tool", "how do you handle", "frustrated with"]},
             "indiehackers": {"queries": ["struggling", "looking for a tool"]},
             "trends": {"keywords": ["small business software", "crm software"], "geo": "", "timeframe": "today 12-m"},
             "producthunt": {"topics": ["saas", "productivity"], "keywords": []},
             "reddit_search": {"queries": ['is there a tool that', 'still doing this in a spreadsheet'], "subreddits": ["Entrepreneur", "SaaS", "startups", "smallbusiness"], "days": 365, "max_results": 8},
         }),
    dict(name="vertical_dental", vertical="dentistry", is_active=True,
         description="Verticale: studi dentistici. Chi paga, non chi costruisce.", keywords=[],
         sources={
             "reddit": {"subreddits": ["Dentistry", "DentalHygiene", "dentalassistant"], "sorts": ["new", "top"], "time_filter": "month"},
             "hackernews": {"queries": ["dental practice software"]},
             "youtube": {"queries": ["dental office insurance verification workflow", "dental front desk software tutorial"], "videos_per_query": 4},
             "trends": {"keywords": ["dental practice management software", "crm software"], "geo": "US", "timeframe": "today 12-m"},
             "producthunt": {"topics": ["health"], "keywords": ["dental", "dentist"]},
             "reddit_search": {"queries": ['dental office insurance verification spreadsheet', 'front desk software frustrating dental'], "subreddits": ["Dentistry", "DentalHygiene", "dentalassistant"], "days": 365, "max_results": 8},
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
             "reddit_search": {"queries": ['scheduling invoicing software small plumbing hvac business', 'still use spreadsheet for jobs contractor'], "subreddits": ["Plumbing", "electricians", "HVAC", "Construction", "Landscaping"], "days": 365, "max_results": 8},
         }),
    dict(name="vertical_property", vertical="property_management", is_active=True,
         description="Verticale: property management / affitti.", keywords=[],
         sources={
             "reddit": {"subreddits": ["PropertyManagement", "Landlord", "realestateinvesting"], "sorts": ["new", "top"], "time_filter": "month"},
             "hackernews": {"queries": ["property management software", "landlord software"]},
             "playstore": {"app_ids": ["com.appfolio.appfolio_property_manager"], "country": "us", "lang": "en"},
             "trends": {"keywords": ["property management software", "crm software"], "geo": "", "timeframe": "today 12-m"},
             "producthunt": {"topics": ["real-estate"], "keywords": []},
             "reddit_search": {"queries": ['property management software small landlord frustrating', 'tenant maintenance requests spreadsheet'], "subreddits": ["PropertyManagement", "Landlord", "realestateinvesting"], "days": 365, "max_results": 8},
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
             "reddit_search": {"queries": ['bookkeeping workflow month end manual spreadsheet', 'is there a tool for client document collection bookkeeper'], "subreddits": ["Accounting", "Bookkeeping", "taxpros"], "days": 365, "max_results": 8},
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
             "reddit_search": {"queries": ['e-rechnung 2026 software kleinunternehmen', 'facture electronique 2026 logiciel TPE'], "subreddits": ["de_EDV", "Finanzen", "selbststaendig", "vosfinances", "entrepreneur_fr", "smallbusiness", "Peppol"], "days": 365, "max_results": 8},
         }),
    dict(name="italia_professionisti", vertical="it_professionals", is_active=True, country="IT",
         description="Commercialisti, avvocati, geometri, consulenti del lavoro in Italia: adempimenti ricorrenti, software datati, raggiungibili via LinkedIn/ordini professionali.",
         keywords=[],
         sources={
             "reddit": {"subreddits": ["ItaliaPersonalFinance", "commercialisti", "Avvocati", "ItalyInformatica", "italy"], "sorts": ["new", "top"], "time_filter": "month"},
             "hackernews": {"queries": ["fatturazione elettronica", "commercialista software"]},
             "trends": {"keywords": ["software commercialisti", "gestionale studio legale", "software consulente del lavoro", "crm software"], "geo": "IT", "timeframe": "today 12-m"},
             "reddit_search": {"queries": ['software commercialisti lento gestionale', 'studio legale gestionale scadenze'], "subreddits": ["ItaliaPersonalFinance", "commercialisti", "Avvocati", "ItalyInformatica", "italy"], "days": 365, "max_results": 8},
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
             "reddit_search": {"queries": ['automate manual process small business spreadsheet every week', 'zapier make workflow small business manual'], "subreddits": [], "days": 365, "max_results": 8},
         }),
    dict(name="ecommerce_merchants", vertical="ecommerce_smb", is_active=True,
         description="Merchant Shopify (compratori, non builder): operazioni, inventario, spedizioni, contabilità.",
         keywords=[],  # no local filter: the LLM noise/attack_vector gate does the filtering
         sources={
             "forum": {"forums": [{"base_url": "https://community.shopify.com", "categories": [], "searches": ["is there an app that", "manually every", "spreadsheet"]}], "topics_per_forum": 30, "posts_per_topic": 3},
             "reddit": {"subreddits": ["shopify", "ecommerce"], "sorts": ["new", "top"], "time_filter": "month"},
             "youtube": {"queries": ["shopify inventory reconciliation spreadsheet", "shopify reorder point purchase orders small store",
                                     "shopify profit margin tracking spreadsheet cogs", "shopify multi channel inventory sync manual"], "videos_per_query": 4},
             "producthunt": {"topics": ["e-commerce"], "keywords": []},
             "reddit_search": {"queries": ['shopify inventory reconciliation spreadsheet manual', 'shopify is there an app that'], "subreddits": ["shopify", "ecommerce"], "days": 365, "max_results": 8},
         }),
    # --- Hand-curated verticals with REAL communities (buyers, not builders). Reddit runs once REDDIT_CLIENT_ID is set.
    dict(name="vertical_service_businesses", vertical="local_service_businesses", is_active=True,
         description="Imprese di servizi locali (pulizie, giardinaggio, traslochi, pest control): r/sweatystartup è la community dei proprietari.",
         keywords=[],
         sources={
             "reddit": {"subreddits": ["sweatystartup", "Cleaningbusiness", "lawncare", "Landscaping"], "sorts": ["new", "top"], "time_filter": "month"},
             "youtube": {"queries": ["cleaning business scheduling and invoicing workflow", "lawn care business software small crew"], "videos_per_query": 4},
             "trends": {"keywords": ["cleaning business software", "lawn care software", "crm software"], "geo": "", "timeframe": "today 12-m"},
             "reddit_search": {"queries": ['cleaning business scheduling invoicing spreadsheet', 'lawn care business software frustrating'], "subreddits": ["sweatystartup", "Cleaningbusiness", "lawncare", "Landscaping"], "days": 365, "max_results": 8},
         }),
    dict(name="vertical_msp_it_services", vertical="msp", is_active=True,
         description="Managed Service Providers (piccole aziende IT che gestiscono PMI): budget alto, tool frammentati, community attivissima.",
         keywords=[],
         sources={
             "reddit": {"subreddits": ["msp", "ITManagers"], "sorts": ["new", "top"], "time_filter": "month"},
             "hackernews": {"queries": ["MSP tooling", "managed service provider software"]},
             "youtube": {"queries": ["msp business documentation billing workflow small", "msp psa rmm alternatives small shop"], "videos_per_query": 4},
             "trends": {"keywords": ["msp software", "psa software", "crm software"], "geo": "", "timeframe": "today 12-m"},
             "reddit_search": {"queries": ['msp documentation billing tool frustrating small', 'psa rmm alternatives small msp'], "subreddits": ["msp", "ITManagers"], "days": 365, "max_results": 8},
         }),
    dict(name="vertical_nonprofits", vertical="nonprofit_ops", is_active=True,
         description="Piccole nonprofit: donor management, grant reporting, volontari. Cronicamente sotto-servite e con budget (grant).",
         keywords=[],
         sources={
             "reddit": {"subreddits": ["nonprofit", "grantwriting"], "sorts": ["new", "top"], "time_filter": "month"},
             "youtube": {"queries": ["small nonprofit donor management spreadsheet workflow", "grant reporting process small nonprofit"], "videos_per_query": 4},
             "trends": {"keywords": ["nonprofit crm", "grant management software", "crm software"], "geo": "", "timeframe": "today 12-m"},
             "reddit_search": {"queries": ['small nonprofit donor management spreadsheet', 'grant reporting nonprofit manual'], "subreddits": ["nonprofit", "grantwriting"], "days": 365, "max_results": 8},
         }),
    dict(name="vertical_restaurants_bars", vertical="hospitality_owners", is_active=True,
         description="Proprietari di ristoranti/bar: inventario, turni, fornitori, margini. Pagano già (POS) e odiano i tool.",
         keywords=[],
         sources={
             "reddit": {"subreddits": ["restaurantowners", "BarOwners", "KitchenConfidential"], "sorts": ["new", "top"], "time_filter": "month"},
             "youtube": {"queries": ["restaurant inventory management spreadsheet owner", "restaurant scheduling and food cost workflow"], "videos_per_query": 4},
             "trends": {"keywords": ["restaurant inventory software", "restaurant scheduling software", "crm software"], "geo": "", "timeframe": "today 12-m"},
             "reddit_search": {"queries": ['restaurant inventory spreadsheet owner', 'restaurant scheduling software frustrating'], "subreddits": ["restaurantowners", "BarOwners", "KitchenConfidential"], "days": 365, "max_results": 8},
         }),
    dict(name="vertical_logistics_freight", vertical="freight_logistics", is_active=True,
         description="Piccoli spedizionieri, freight broker, autotrasportatori: documenti, tracking, fatturazione — molto manuale.",
         keywords=[],
         sources={
             "reddit": {"subreddits": ["FreightBrokers", "Truckers", "logistics", "supplychain"], "sorts": ["new", "top"], "time_filter": "month"},
             "youtube": {"queries": ["freight broker daily workflow load tracking spreadsheet", "small trucking company dispatch invoicing process"], "videos_per_query": 4},
             "trends": {"keywords": ["tms software small carrier", "freight broker software", "crm software"], "geo": "", "timeframe": "today 12-m"},
             "reddit_search": {"queries": ['freight broker load tracking spreadsheet', 'small trucking dispatch invoicing manual'], "subreddits": ["FreightBrokers", "Truckers", "logistics", "supplychain"], "days": 365, "max_results": 8},
         }),
    dict(name="vertical_law_firms_small", vertical="small_law_firms", is_active=True,
         description="Studi legali piccoli e paralegal: intake, scadenze, fatturazione oraria, documenti.",
         keywords=[],
         sources={
             "reddit": {"subreddits": ["LawFirm", "paralegal", "Lawyertalk"], "sorts": ["new", "top"], "time_filter": "month"},
             "youtube": {"queries": ["solo law firm client intake workflow", "small law firm billing and deadlines process"], "videos_per_query": 4},
             "trends": {"keywords": ["law practice management software", "legal billing software", "crm software"], "geo": "", "timeframe": "today 12-m"},
             "reddit_search": {"queries": ['solo law firm intake software frustrating', 'law firm deadlines tracking spreadsheet'], "subreddits": ["LawFirm", "paralegal", "Lawyertalk"], "days": 365, "max_results": 8},
         }),
    dict(name="vertical_insurance_agents", vertical="insurance_agencies", is_active=True,
         description="Agenzie assicurative indipendenti: rinnovi, quote da più carrier, follow-up — spreadsheet ovunque.",
         keywords=[],
         sources={
             "reddit": {"subreddits": ["InsuranceAgent", "Insurance"], "sorts": ["new", "top"], "time_filter": "month"},
             "youtube": {"queries": ["independent insurance agency renewal tracking workflow", "insurance agent crm spreadsheet follow up"], "videos_per_query": 4},
             "trends": {"keywords": ["insurance agency management system", "insurance crm", "crm software"], "geo": "", "timeframe": "today 12-m"},
             "reddit_search": {"queries": ['independent insurance agency renewals spreadsheet', 'insurance agent crm frustrating'], "subreddits": ["InsuranceAgent", "Insurance"], "days": 365, "max_results": 8},
         }),
    dict(name="vertical_amazon_sellers", vertical="marketplace_sellers", is_active=True,
         description="Venditori Amazon FBA / multi-marketplace: riconciliazione pagamenti, resi, inventario multi-canale.",
         keywords=[],
         sources={
             "reddit": {"subreddits": ["FulfillmentByAmazon", "AmazonSeller", "ecommerce"], "sorts": ["new", "top"], "time_filter": "month"},
             "youtube": {"queries": ["amazon fba seller bookkeeping reconciliation spreadsheet", "multi channel inventory sync small seller workflow"], "videos_per_query": 4},
             "trends": {"keywords": ["amazon seller software", "fba accounting software", "crm software"], "geo": "", "timeframe": "today 12-m"},
             "producthunt": {"topics": ["e-commerce"], "keywords": ["amazon", "seller", "marketplace"]},
             "reddit_search": {"queries": ['amazon fba reconciliation spreadsheet', 'multi channel inventory sync manual seller'], "subreddits": ["FulfillmentByAmazon", "AmazonSeller", "ecommerce"], "days": 365, "max_results": 8},
         }),
    # --- Expansion round 2 (2026-09-15): buyers with recurring workflows, reachable solo. Reddit blocks run only via reddit_search.
    dict(name="vertical_str_hosts", vertical="short_term_rental_hosts", is_active=True,
         description="Host Airbnb/B&B con 2-20 unità: pulizie, check-in, prezzi, messaggi ospiti, tasse di soggiorno.", keywords=[],
         sources={
             "reddit": {"subreddits": ["airbnb_hosts", "AirBnBHosts", "vrbo"], "sorts": ["new", "top"], "time_filter": "month"},
             "reddit_search": {"queries": ["airbnb host cleaning turnover spreadsheet", "airbnb host software frustrating multiple listings"], "subreddits": ["airbnb_hosts", "AirBnBHosts"], "days": 365, "max_results": 8},
             "youtube": {"queries": ["airbnb host cleaning turnover workflow small portfolio", "short term rental host tools spreadsheet"], "videos_per_query": 4},
             "trends": {"keywords": ["airbnb host software", "vacation rental software", "crm software"], "geo": "", "timeframe": "today 12-m"},
         }),
    dict(name="vertical_fitness_business", vertical="fitness_business_owners", is_active=True,
         description="Personal trainer e piccole palestre/studi: programmi, pagamenti ricorrenti, no-show, retention.", keywords=[],
         sources={
             "reddit": {"subreddits": ["personaltraining", "gymowners"], "sorts": ["new", "top"], "time_filter": "month"},
             "reddit_search": {"queries": ["personal trainer client tracking spreadsheet software", "gym owner software frustrating members"], "subreddits": ["personaltraining"], "days": 365, "max_results": 8},
             "youtube": {"queries": ["personal trainer business admin workflow clients", "small gym owner software billing"], "videos_per_query": 4},
             "trends": {"keywords": ["personal trainer software", "gym management software", "crm software"], "geo": "", "timeframe": "today 12-m"},
         }),
    dict(name="vertical_photographers", vertical="photo_video_pros", is_active=True,
         description="Fotografi e videomaker (matrimoni, eventi, corporate): preventivi, contratti, consegna file, pagamenti.", keywords=[],
         sources={
             "reddit": {"subreddits": ["WeddingPhotography", "videography", "photography"], "sorts": ["new", "top"], "time_filter": "month"},
             "reddit_search": {"queries": ["wedding photographer client workflow contracts invoices spreadsheet", "videographer delivery client galleries frustrating"], "subreddits": ["WeddingPhotography", "videography"], "days": 365, "max_results": 8},
             "youtube": {"queries": ["wedding photographer business workflow clients contracts", "videographer client management tools"], "videos_per_query": 4},
             "trends": {"keywords": ["photography business software", "crm for photographers", "crm software"], "geo": "", "timeframe": "today 12-m"},
         }),
    dict(name="vertical_real_estate_agents", vertical="real_estate_agents", is_active=True,
         description="Agenti immobiliari e piccole agenzie: lead, visite, documenti, follow-up.", keywords=[],
         sources={
             "reddit": {"subreddits": ["realtors"], "sorts": ["new", "top"], "time_filter": "month"},
             "reddit_search": {"queries": ["realtor lead follow up spreadsheet crm frustrating", "real estate agent transaction paperwork manual"], "subreddits": ["realtors"], "days": 365, "max_results": 8},
             "youtube": {"queries": ["real estate agent daily workflow leads follow up tools", "small brokerage transaction management"], "videos_per_query": 4},
             "trends": {"keywords": ["real estate crm", "transaction management software", "crm software"], "geo": "", "timeframe": "today 12-m"},
         }),
    dict(name="vertical_auto_repair", vertical="auto_repair_shops", is_active=True,
         description="Officine meccaniche e carrozzerie indipendenti: preventivi, ricambi, appuntamenti, storico veicoli.", keywords=[],
         sources={
             "reddit_search": {"queries": ["auto repair shop owner software estimates frustrating", "independent mechanic shop management spreadsheet"], "subreddits": [], "days": 365, "max_results": 8},
             "youtube": {"queries": ["auto repair shop management workflow estimates parts", "small mechanic shop software review"], "videos_per_query": 4},
             "trends": {"keywords": ["auto repair shop software", "shop management system mechanic", "crm software"], "geo": "", "timeframe": "today 12-m"},
         }),
    dict(name="vertical_woocommerce_sellers", vertical="woocommerce_smb", is_active=True,
         description="Merchant WooCommerce/WordPress (no Shopify): plugin che si rompono, inventario, spedizioni, contabilità.", keywords=[],
         sources={
             "reddit": {"subreddits": ["woocommerce", "ecommerce"], "sorts": ["new", "top"], "time_filter": "month"},
             "reddit_search": {"queries": ["woocommerce store owner manual inventory plugin", "woocommerce is there a plugin that"], "subreddits": ["woocommerce"], "days": 365, "max_results": 8},
             "youtube": {"queries": ["woocommerce store owner inventory workflow plugins", "woocommerce accounting sync manual"], "videos_per_query": 4},
             "trends": {"keywords": ["woocommerce inventory plugin", "woocommerce accounting", "crm software"], "geo": "", "timeframe": "today 12-m"},
         }),
    dict(name="vertical_travel_agents", vertical="travel_agencies_small", is_active=True,
         description="Agenzie di viaggio piccole e travel advisor indipendenti: preventivi, itinerari, pagamenti fornitori, documenti.", keywords=[],
         sources={
             "reddit": {"subreddits": ["travelagents"], "sorts": ["new", "top"], "time_filter": "month"},
             "reddit_search": {"queries": ["travel agent itinerary software frustrating spreadsheet", "independent travel advisor tools invoicing suppliers"], "subreddits": ["travelagents"], "days": 365, "max_results": 8},
             "youtube": {"queries": ["travel agent itinerary building workflow tools", "travel advisor business admin software"], "videos_per_query": 4},
             "trends": {"keywords": ["travel agency software", "itinerary builder software", "crm software"], "geo": "", "timeframe": "today 12-m"},
         }),
    dict(name="vertical_etsy_handmade", vertical="handmade_sellers", is_active=True,
         description="Venditori Etsy/handmade: costi materiali, prezzi, inventario, spedizioni, tasse.", keywords=[],
         sources={
             "reddit": {"subreddits": ["EtsySellers", "Etsy"], "sorts": ["new", "top"], "time_filter": "month"},
             "reddit_search": {"queries": ["etsy seller bookkeeping spreadsheet cost of materials", "etsy seller inventory tracking manual"], "subreddits": ["EtsySellers"], "days": 365, "max_results": 8},
             "youtube": {"queries": ["etsy seller bookkeeping pricing spreadsheet workflow", "etsy shop inventory management small"], "videos_per_query": 4},
             "trends": {"keywords": ["etsy bookkeeping software", "etsy inventory management", "crm software"], "geo": "", "timeframe": "today 12-m"},
         }),
    dict(name="vertical_marketing_agencies", vertical="small_agencies", is_active=True,
         description="Piccole agenzie marketing/web e freelance: reporting clienti, proposte, ore, fatturazione ricorrente.", keywords=[],
         sources={
             "reddit": {"subreddits": ["agency", "PPC", "SEO"], "sorts": ["new", "top"], "time_filter": "month"},
             "reddit_search": {"queries": ["agency owner client reporting manual hours every month", "small marketing agency proposals invoicing tool frustrating"], "subreddits": ["agency"], "days": 365, "max_results": 8},
             "youtube": {"queries": ["small marketing agency client reporting workflow", "agency owner operations tools stack"], "videos_per_query": 4},
             "trends": {"keywords": ["agency reporting software", "agency management software", "crm software"], "geo": "", "timeframe": "today 12-m"},
         }),
    dict(name="vertical_recruiters_small", vertical="small_recruiting_firms", is_active=True,
         description="Recruiter indipendenti e piccole agenzie di staffing: candidati, clienti, follow-up, fatturazione a placement.", keywords=[],
         sources={
             "reddit": {"subreddits": ["recruiting"], "sorts": ["new", "top"], "time_filter": "month"},
             "reddit_search": {"queries": ["independent recruiter ats spreadsheet frustrating", "small staffing agency software candidates clients"], "subreddits": ["recruiting"], "days": 365, "max_results": 8},
             "youtube": {"queries": ["independent recruiter workflow candidates tools", "small staffing agency software review"], "videos_per_query": 4},
             "trends": {"keywords": ["recruiting software small agency", "applicant tracking system small", "crm software"], "geo": "", "timeframe": "today 12-m"},
         }),
    dict(name="vertical_construction_estimators", vertical="construction_smb", is_active=True,
         description="Piccole imprese edili e stimatori: preventivi, computi, subappalti, stati avanzamento.", keywords=[],
         sources={
             "reddit": {"subreddits": ["estimators", "Construction", "Contractor"], "sorts": ["new", "top"], "time_filter": "month"},
             "reddit_search": {"queries": ["construction estimator spreadsheet takeoff frustrating", "small contractor estimating software too expensive"], "subreddits": ["estimators", "Construction"], "days": 365, "max_results": 8},
             "youtube": {"queries": ["small construction company estimating workflow spreadsheet", "contractor bidding software small business"], "videos_per_query": 4},
             "trends": {"keywords": ["construction estimating software", "takeoff software", "crm software"], "geo": "", "timeframe": "today 12-m"},
         }),
    dict(name="vertical_salons_barbers", vertical="salons_barbers", is_active=True,
         description="Saloni, barbieri, centri estetici: prenotazioni, no-show, magazzino prodotti, personale.", keywords=[],
         sources={
             "reddit": {"subreddits": ["Hairstylist", "Barber", "Esthetics"], "sorts": ["new", "top"], "time_filter": "month"},
             "reddit_search": {"queries": ["salon owner booking software frustrating no show", "barber shop owner tools inventory staff"], "subreddits": ["Hairstylist", "Barber"], "days": 365, "max_results": 8},
             "youtube": {"queries": ["salon owner booking software comparison small", "barbershop management workflow tools"], "videos_per_query": 4},
             "trends": {"keywords": ["salon software", "barber booking app", "crm software"], "geo": "", "timeframe": "today 12-m"},
         }),
    dict(name="vertical_farms_small", vertical="small_farms", is_active=True,
         description="Piccole aziende agricole e vendita diretta: registri, tracciabilità, CSA/abbonamenti, vendite a mercati.", keywords=[],
         sources={
             "reddit": {"subreddits": ["farming", "homestead", "Agriculture"], "sorts": ["new", "top"], "time_filter": "month"},
             "reddit_search": {"queries": ["small farm record keeping spreadsheet software", "farm direct sales csa management manual"], "subreddits": ["farming"], "days": 365, "max_results": 8},
             "youtube": {"queries": ["small farm record keeping software workflow", "csa farm management tools"], "videos_per_query": 4},
             "trends": {"keywords": ["farm management software small", "csa software", "crm software"], "geo": "", "timeframe": "today 12-m"},
         }),
    # --- Italy-specific (Italian queries; Reddit is thin in Italian -> reddit_search + YouTube + Trends IT)
    dict(name="italia_amministratori_condominio", vertical="it_condo_managers", is_active=True, country="IT",
         description="Amministratori di condominio: assemblee, riparti, morosità, bonus edilizi, comunicazioni ai condomini. Obblighi normativi ricorrenti.", keywords=[],
         sources={
             "reddit_search": {"queries": ["amministratore di condominio software gestionale problemi", "amministratore condominio assemblea gestione morosità"], "subreddits": [], "days": 365, "max_results": 8},
             "youtube": {"queries": ["amministratore di condominio gestionale come lavoro", "software condominio riparto spese tutorial"], "videos_per_query": 4, "relevance_language": "it"},
             "trends": {"keywords": ["software amministratore condominio", "gestionale condominio", "crm software"], "geo": "IT", "timeframe": "today 12-m"},
         }),
    dict(name="italia_agenzie_immobiliari", vertical="it_real_estate", is_active=True, country="IT",
         description="Agenzie immobiliari italiane: portali, incarichi, visite, documenti, antiriciclaggio.", keywords=[],
         sources={
             "reddit_search": {"queries": ["agente immobiliare gestionale portali problemi", "agenzia immobiliare software crm frustrante"], "subreddits": [], "days": 365, "max_results": 8},
             "youtube": {"queries": ["agente immobiliare gestionale giornata tipo strumenti", "software agenzia immobiliare tutorial"], "videos_per_query": 4, "relevance_language": "it"},
             "trends": {"keywords": ["gestionale agenzia immobiliare", "crm immobiliare", "crm software"], "geo": "IT", "timeframe": "today 12-m"},
         }),
    dict(name="italia_autoscuole", vertical="it_driving_schools", is_active=True, country="IT",
         description="Autoscuole: prenotazione guide, pratiche motorizzazione, quiz, pagamenti rateali.", keywords=[],
         sources={
             "reddit_search": {"queries": ["autoscuola gestionale prenotazione guide software", "autoscuola pratiche motorizzazione gestione"], "subreddits": [], "days": 365, "max_results": 8},
             "youtube": {"queries": ["autoscuola gestionale software tutorial", "gestione autoscuola prenotazioni guide"], "videos_per_query": 4, "relevance_language": "it"},
             "trends": {"keywords": ["gestionale autoscuola", "software autoscuola", "crm software"], "geo": "IT", "timeframe": "today 12-m"},
         }),
    dict(name="italia_ristoranti", vertical="it_restaurants", is_active=True, country="IT",
         description="Ristoratori italiani: turni, food cost, fornitori, prenotazioni, recensioni.", keywords=[],
         sources={
             "reddit_search": {"queries": ["ristoratore gestionale food cost fornitori excel", "ristorante software prenotazioni turni problemi"], "subreddits": ["italy", "ItaliaPersonalFinance"], "days": 365, "max_results": 8},
             "youtube": {"queries": ["ristoratore food cost excel gestione fornitori", "gestionale ristorante turni software"], "videos_per_query": 4, "relevance_language": "it"},
             "trends": {"keywords": ["gestionale ristorante", "software food cost", "crm software"], "geo": "IT", "timeframe": "today 12-m"},
         }),
    dict(name="italia_studi_dentistici", vertical="it_dental", is_active=True, country="IT",
         description="Studi dentistici italiani: agenda, richiami, preventivi, fatturazione, consensi.", keywords=[],
         sources={
             "reddit_search": {"queries": ["studio dentistico gestionale problemi segreteria", "dentista software agenda richiami pazienti"], "subreddits": [], "days": 365, "max_results": 8},
             "youtube": {"queries": ["studio dentistico gestionale segreteria tutorial", "software odontoiatrico agenda richiami"], "videos_per_query": 4, "relevance_language": "it"},
             "trends": {"keywords": ["gestionale studio dentistico", "software odontoiatrico", "crm software"], "geo": "IT", "timeframe": "today 12-m"},
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
             "reddit_search": {"queries": ['private practice scheduling billing software frustrating', 'therapist admin work hours per week'], "subreddits": ["physicaltherapy", "therapists", "Optometry", "veterinaryprofession"], "days": 365, "max_results": 8},
         }),
]


def main() -> None:
    for st in FUNNEL_STAGES:
        db.upsert(db.FUNNEL_STAGES, st["key"], st, merge=False)  # criteria must be REPLACED, not merged (old keys would linger)
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
