"""
Web search behind ONE daily budget shared by every job (Cloud Run + local), across two free tiers:

  - Jina  (s.jina.ai)  : free token quota, no hard monthly cap -> spent first (volume: reddit_search)
  - Brave Search API   : 2,000 queries/month (~65/day)
  - Tavily             : 1,000 queries/month (~33/day) -> spent last
(Google Custom Search JSON API is closed to new projects since 2025.)

Usage counters live in Firestore `search_usage/{YYYY-MM-DD}` so nothing can silently burn the month in four days again
(2026-09-17: 47 keyword sets x ~5 reddit_search queries/day did exactly that).

Callers pass a `purpose`:
  - "scrape"  (reddit_search)          : may use at most SCRAPE_SHARE of the day's cap
  - "enrich"  (market/competitor/etc.) : may use the whole cap — these calls decide a cluster's fate

Result shape is provider-independent: [{"title", "content", "url"}].
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app import db
from app.config import get_settings
from app.scrapers.base import http_client, log

JINA_DAILY = 120
BRAVE_DAILY = 65
TAVILY_DAILY = 33
SCRAPE_SHARE = 0.6
COLL = "search_usage"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def usage() -> dict[str, int]:
    doc = db.get(COLL, _today()) or {}
    return {"jina": int(doc.get("jina") or 0), "brave": int(doc.get("brave") or 0), "tavily": int(doc.get("tavily") or 0)}


def _bump(provider: str) -> None:
    from google.cloud.firestore_v1 import Increment

    db.get_db().collection(COLL).document(_today()).set({provider: Increment(1), "updated_at": db.now()}, merge=True)


def remaining(purpose: str = "enrich") -> int:
    u = usage()
    s = get_settings()
    cap = (JINA_DAILY if s.jina_api_key else 0) + (BRAVE_DAILY if s.brave_search_api_key else 0) + (TAVILY_DAILY if s.tavily_api_key else 0)
    used = u["jina"] + u["brave"] + u["tavily"]
    allowed = int(cap * SCRAPE_SHARE) if purpose == "scrape" else cap
    return max(0, allowed - used)


def _jina(query: str, max_results: int, days: int | None, include_domains: list[str] | None) -> list[dict]:
    q = f"{query} site:{include_domains[0]}" if include_domains else query
    headers = {"Authorization": f"Bearer {get_settings().jina_api_key}", "Accept": "application/json", "X-Respond-With": "no-content"}
    with http_client(timeout=30) as c:
        r = c.get("https://s.jina.ai/", params={"q": q}, headers=headers)
        r.raise_for_status()
        items = (r.json().get("data") or [])[:max_results]
        return [{"title": it.get("title"), "content": it.get("description") or it.get("content") or "", "url": it.get("url")} for it in items]


def _brave(query: str, max_results: int, days: int | None, include_domains: list[str] | None) -> list[dict]:
    q = f"{query} site:{include_domains[0]}" if include_domains else query
    params: dict[str, Any] = {"q": q, "count": min(max_results, 20)}
    if days:
        params["freshness"] = "pd" if days <= 1 else "pw" if days <= 7 else "pm" if days <= 31 else "py"
    headers = {"X-Subscription-Token": get_settings().brave_search_api_key, "Accept": "application/json"}
    with http_client(timeout=20) as c:
        r = c.get("https://api.search.brave.com/res/v1/web/search", params=params, headers=headers)
        r.raise_for_status()
        return [{"title": it.get("title"), "content": it.get("description") or "", "url": it.get("url")} for it in (r.json().get("web") or {}).get("results", [])]


def _tavily(query: str, max_results: int, days: int | None, include_domains: list[str] | None, topic: str) -> list[dict]:
    from tavily import TavilyClient

    kw: dict[str, Any] = {"max_results": max_results, "search_depth": "basic", "topic": topic}
    if days:
        kw["days"] = days
    if include_domains:
        kw["include_domains"] = include_domains
    res = TavilyClient(api_key=get_settings().tavily_api_key).search(query, **kw)
    return [{"title": r.get("title"), "content": r.get("content") or "", "url": r.get("url")} for r in res.get("results", [])]


def search(query: str, max_results: int = 6, days: int | None = None, include_domains: list[str] | None = None,
           purpose: str = "enrich", topic: str = "general") -> list[dict]:
    """Budgeted search. Returns [] (never raises) when the budget for `purpose` is spent or every provider fails."""
    s = get_settings()
    if remaining(purpose) <= 0:
        log.info("search budget exhausted for %s: %r skipped", purpose, query[:60])
        return []
    u = usage()
    providers = []
    if s.jina_api_key and u["jina"] < JINA_DAILY:
        providers.append("jina")
    if s.brave_search_api_key and u["brave"] < BRAVE_DAILY:
        providers.append("brave")
    if s.tavily_api_key and u["tavily"] < TAVILY_DAILY:
        providers.append("tavily")
    if purpose == "enrich" and "brave" in providers:  # decisions get the best index first
        providers.remove("brave"); providers.insert(0, "brave")
    fns = {"jina": lambda: _jina(query, max_results, days, include_domains), "brave": lambda: _brave(query, max_results, days, include_domains),
           "tavily": lambda: _tavily(query, max_results, days, include_domains, topic)}
    for p in providers:
        try:
            _bump(p)
            return fns[p]()
        except Exception as e:  # noqa: BLE001
            log.warning("%s search failed for %r: %s", p, query[:60], str(e)[:120])
    return []
