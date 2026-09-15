"""
Reddit via a web search engine (Tavily) — NOT the Reddit API.

Why: Reddit's Data API requires explicit approval that is rarely granted to external research pipelines.
A search engine index of public Reddit pages is a legitimate, low-volume alternative: we store title, URL
and the search snippet (a few hundred chars), never full threads or usernames. No Reddit ToS involved
(we never call reddit.com); Tavily's free tier is 1,000 searches/month, so keep queries few and specific.

Config: {"queries": ["dental office insurance verification spreadsheet", ...],
         "subreddits": ["Dentistry", "dentalassistant"],   # optional: restricts with site:reddit.com/r/<sub>
         "days": 365, "max_results": 8}
Each query is run once per subreddit group (or once globally) -> ~1-3 searches per query.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from dateutil import parser as dtparser

from app.config import get_settings
from app.heuristics import matches_keywords
from app.models import RawSignal
from app.scrapers.base import clip, log, polite_sleep

_POST = re.compile(r"reddit\.com/r/([^/]+)/comments/([a-z0-9]+)", re.I)
_CHROME = re.compile(
    r"(Reddit - The heart of the internet|Skip to main content|Open navigation\s*Go to Reddit Home|Open navigation|Go to Reddit Home|"
    r"Sign Up\s*Sign up for Reddit to Reddit|Sign up for Reddit|Expand user menu\s*Open settings menu|Expand user menu|Open settings menu|"
    r"Open menu|Log In|Get app|Get the Reddit app|Image \d+ Go to \w+|Go to \w+\.|\d+(\.\d+)?[KM]? Members Online|Members Online|"
    r"Additional Keywords,?|Title:\s*|: r/\w+|r/\w+\s*#|^#+\s*)", re.I)


def _clean(text: str) -> str:
    text = _CHROME.sub(" ", text)
    text = re.sub(r"#+\s*", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" -:|.")
    return text


_STOP = {"the", "a", "an", "for", "to", "of", "and", "is", "in", "on", "my", "how", "do", "you", "with", "that", "there", "tool", "software",
         "il", "la", "di", "per", "un", "una", "e", "con", "che", "come", "del", "della", "gestione", "gestionale"}


def _relevant(query: str, text: str, min_hits: int = 2) -> bool:
    """At least 2 meaningful query words must appear in the snippet: search engines return loosely related threads."""
    words = [w for w in re.findall(r"[a-zà-ú]{4,}", query.lower()) if w not in _STOP]
    if len(words) < 2:
        return True
    low = text.lower()
    return sum(1 for w in words if w[:5] in low) >= min(min_hits, len(words))


def _search(query: str, days: int, max_results: int) -> list[dict]:
    from tavily import TavilyClient

    key = get_settings().tavily_api_key
    if not key:
        raise RuntimeError("TAVILY_API_KEY not set")
    res = TavilyClient(api_key=key).search(query, max_results=max_results, search_depth="basic", days=days, include_domains=["reddit.com"])
    return res.get("results", [])


def fetch(keyword_set: dict, config: dict) -> list[RawSignal]:
    # budget guard: Tavily free tier = 1,000 searches/month -> at most one reddit_search pass per keyword set per day
    from datetime import timedelta

    from app import db

    ksid = keyword_set.get("id")
    if ksid:
        last = (db.get(db.KEYWORD_SETS, ksid) or {}).get("reddit_search_last_run")
        if last and last > datetime.now(timezone.utc) - timedelta(hours=23):
            log.info("reddit_search skipped for %s (ran <23h ago)", keyword_set.get("name"))
            return []
        db.upsert(db.KEYWORD_SETS, ksid, {"reddit_search_last_run": datetime.now(timezone.utc)})
    keywords = keyword_set.get("keywords") or []
    days = int(config.get("days", 365))
    max_results = int(config.get("max_results", 8))
    subs = config.get("subreddits") or []
    out: list[RawSignal] = []
    seen: set[str] = set()
    for q in config.get("queries", []):
        # one search per group of up to 3 subreddits (site: filters), or one global reddit search
        groups = [subs[i : i + 3] for i in range(0, len(subs), 3)] or [[]]
        for group in groups:
            scope = " OR ".join(f"site:reddit.com/r/{s}" for s in group) if group else "site:reddit.com"
            try:
                results = _search(f"{q} {scope}", days, max_results)
            except Exception as e:  # noqa: BLE001
                log.error("reddit_search %r failed: %s", q, e)
                continue
            for r in results:
                url = r.get("url") or ""
                m = _POST.search(url)
                if not m:
                    continue
                sub, post_id = m.group(1), m.group(2)
                if post_id in seen:
                    continue
                seen.add(post_id)
                title = _clean((r.get("title") or "").replace(" : r/" + sub, ""))
                snippet = _clean(r.get("content") or "")
                # snippets usually repeat the title: drop every occurrence of it
                if title and len(title) > 15:
                    snippet = snippet.replace(title, " ").strip(" -:|.")
                snippet = re.sub(r"\s{2,}", " ", snippet)
                if len(snippet) < 60 or not _relevant(q, f"{title} {snippet}"):
                    continue
                kw = matches_keywords(f"{title}\n{snippet}", keywords)
                if kw is None:
                    continue
                published = None
                if r.get("published_date"):
                    try:
                        published = dtparser.parse(r["published_date"])
                        if published.tzinfo is None:
                            published = published.replace(tzinfo=timezone.utc)
                    except Exception:  # noqa: BLE001
                        published = None
                out.append(RawSignal(
                    source="reddit", signal_type="post", external_id=post_id,
                    url=f"https://www.reddit.com/r/{sub}/comments/{post_id}/", title=title, text=clip(snippet),
                    author_hash=hashlib.sha256(f"reddit-thread:{post_id}".encode()).hexdigest()[:32],  # one thread = one person (no username stored)
                    published_at=published or datetime.now(timezone.utc),
                    score=None, num_comments=None,
                    engagement={"via": "search_snippet", "score_hint": r.get("score")},
                    keyword=kw or q, channel=f"r/{sub}",
                    raw={"note": "snippet from search engine; open the permalink for the full thread"}))
            polite_sleep()
    return out
