"""
Web search behind ONE daily budget shared by every job (Cloud Run + local), across two free tiers:

  - Google Programmable Search JSON API : 100 queries/day (resets daily -> spent first)
  - Tavily                              : 1,000 queries/month (~33/day -> spent last, kept for what decides)

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

GOOGLE_DAILY = 100
TAVILY_DAILY = 33
SCRAPE_SHARE = 0.6
COLL = "search_usage"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def usage() -> dict[str, int]:
    doc = db.get(COLL, _today()) or {}
    return {"google": int(doc.get("google") or 0), "tavily": int(doc.get("tavily") or 0)}


def _bump(provider: str) -> None:
    from google.cloud.firestore_v1 import Increment

    db.get_db().collection(COLL).document(_today()).set({provider: Increment(1), "updated_at": db.now()}, merge=True)


def remaining(purpose: str = "enrich") -> int:
    u = usage()
    s = get_settings()
    cap = (GOOGLE_DAILY if s.google_cse_id and (s.google_search_api_key or s.youtube_api_key) else 0) + (TAVILY_DAILY if s.tavily_api_key else 0)
    used = u["google"] + u["tavily"]
    allowed = int(cap * SCRAPE_SHARE) if purpose == "scrape" else cap
    return max(0, allowed - used)


def _google(query: str, max_results: int, days: int | None, include_domains: list[str] | None) -> list[dict]:
    s = get_settings()
    params: dict[str, Any] = {"key": s.google_search_api_key or s.youtube_api_key, "cx": s.google_cse_id, "q": query, "num": min(max_results, 10)}
    if days:
        params["dateRestrict"] = f"d{days}"
    if include_domains:
        params["siteSearch"], params["siteSearchFilter"] = include_domains[0], "i"
    with http_client(timeout=15) as c:
        r = c.get("https://www.googleapis.com/customsearch/v1", params=params)
        if r.status_code == 429:
            raise RuntimeError("google cse daily quota")
        r.raise_for_status()
        return [{"title": it.get("title"), "content": it.get("snippet") or "", "url": it.get("link")} for it in r.json().get("items", [])]


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
    if s.google_cse_id and (s.google_search_api_key or s.youtube_api_key) and u["google"] < GOOGLE_DAILY:
        providers.append("google")
    if s.tavily_api_key and u["tavily"] < TAVILY_DAILY:
        providers.append("tavily")
    for p in providers:
        try:
            _bump(p)
            return _google(query, max_results, days, include_domains) if p == "google" else _tavily(query, max_results, days, include_domains, topic)
        except Exception as e:  # noqa: BLE001
            log.warning("%s search failed for %r: %s", p, query[:60], str(e)[:120])
    return []
