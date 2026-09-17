"""Registry: source name -> fetch callable. Add a new source = add one line here + one module."""
from app.scrapers import appstores, challenges, discourse, hackernews, indiehackers, producthunt, reddit, reddit_rss, reddit_search, trends, trustpilot, youtube

# Demand-side scrapers: return list[RawSignal] -> persisted to raw_signals by the runner
SIGNAL_SCRAPERS = {
    "reddit": reddit.fetch,
    "hackernews": hackernews.fetch,
    "indiehackers": indiehackers.fetch,
    "trustpilot": trustpilot.fetch,
    "playstore": appstores.fetch_playstore,
    "appstore": appstores.fetch_appstore,
    "youtube": youtube.fetch,
    "forum": discourse.fetch,
    "reddit_rss": reddit_rss.fetch,  # Reddit's official public RSS feeds, feed-reader pace (1 req/min), no API key
    "reddit_search": reddit_search.fetch,  # search-engine snippets of Reddit threads (no Reddit API needed)
    "challenges": challenges.fetch,  # institutional problem statements with a prize (Nesta Challenge Works, HeroX — via their sitemaps)
}

# Metric / supply-side scrapers: persist themselves, return a stats dict
SIDE_SCRAPERS = {
    "trends": trends.fetch,
    "producthunt": producthunt.fetch,
}

ALL_SOURCES = list(SIGNAL_SCRAPERS) + list(SIDE_SCRAPERS)
