"""Registry: source name -> fetch callable. Add a new source = add one line here + one module."""
from app.scrapers import appstores, hackernews, indiehackers, producthunt, reddit, trends, trustpilot

# Demand-side scrapers: return list[RawSignal] -> persisted to raw_signals by the runner
SIGNAL_SCRAPERS = {
    "reddit": reddit.fetch,
    "hackernews": hackernews.fetch,
    "indiehackers": indiehackers.fetch,
    "trustpilot": trustpilot.fetch,
    "playstore": appstores.fetch_playstore,
    "appstore": appstores.fetch_appstore,
}

# Metric / supply-side scrapers: persist themselves, return a stats dict
SIDE_SCRAPERS = {
    "trends": trends.fetch,
    "producthunt": producthunt.fetch,
}

ALL_SOURCES = list(SIGNAL_SCRAPERS) + list(SIDE_SCRAPERS)
