"""
Reddit via its OFFICIAL public RSS/Atom feeds — the channel Reddit provides for feed readers, no key, no OAuth.

  https://www.reddit.com/r/<sub>/new.rss                      newest posts (full self-text, real date, permalink)
  https://www.reddit.com/r/<sub>/search.rss?q=..&restrict_sr=1 keyword search inside a subreddit
  https://www.reddit.com/r/<sub>/comments/<id>/.rss           one thread: post + comments

We behave exactly like a feed reader, which is the conventional use of these feeds:
  - honest User-Agent with a contact address, never masked;
  - ONE request per minute (the unauthenticated limit Reddit advertises in x-ratelimit-* headers), 429 => stop;
  - a hard cap of requests per run, round-robin over keyword sets (each set at most every 2 days);
  - no usernames stored (salted hash), raw text purged after 30 days (services/retention.py), never displayed publicly.

Config (same shape as the PRAW scraper, so keyword sets need no change):
  {"subreddits": [...], "queries": [...optional search terms...], "threads_per_set": 6}
"""
from __future__ import annotations

import html
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import httpx
from dateutil import parser as dtparser

from app.db import hash_author
from app.heuristics import analyze as heuristics, matches_keywords
from app.models import RawSignal
from app.scrapers.base import clip, log, lookback_cutoff

NS = {"a": "http://www.w3.org/2005/Atom"}
UA = "validazione-startup-feedreader/1.0 (personal RSS reader; contact giovannighigliotti96@gmail.com)"
MIN_INTERVAL = 61.0          # seconds between requests: the public feed limit is ~1/min
MAX_REQUESTS_PER_RUN = 90    # ~1.5 h of polite reading per pipeline run
SET_COOLDOWN_DAYS = 2
_last_call = 0.0
_requests_this_run = 0


class FeedLimit(Exception):
    pass


def _get(client: httpx.Client, url: str) -> ET.Element | None:
    global _last_call, _requests_this_run
    if _requests_this_run >= MAX_REQUESTS_PER_RUN:
        raise FeedLimit("per-run request cap reached")
    wait = MIN_INTERVAL - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()
    _requests_this_run += 1
    r = client.get(url)
    if r.status_code == 429:
        reset = float(r.headers.get("x-ratelimit-reset") or 60)
        log.warning("reddit_rss 429 on %s: backing off %.0fs and stopping this run", url, reset)
        time.sleep(min(reset, 90))
        raise FeedLimit("429")
    if r.status_code != 200:
        log.warning("reddit_rss %s -> %s", url, r.status_code)
        return None
    try:
        return ET.fromstring(r.content)
    except ET.ParseError as e:
        log.warning("reddit_rss parse error %s: %s", url, e)
        return None


def _clean(content: str) -> str:
    t = re.sub(r"<[^>]+>", " ", html.unescape(content or ""))
    t = re.sub(r"\s*submitted by\s*/u/\S+.*$", "", t, flags=re.S)  # link-post boilerplate
    t = t.replace("[link]", "").replace("[comments]", "")
    return re.sub(r"\s+", " ", t).strip()


def _entries(root: ET.Element) -> list[dict]:
    out = []
    for e in root.findall("a:entry", NS):
        link = e.find("a:link", NS)
        author = e.find("a:author/a:name", NS)
        out.append({
            "title": html.unescape(e.findtext("a:title", default="", namespaces=NS)),
            "url": link.get("href") if link is not None else "",
            "author": author.text if author is not None else None,
            "published": e.findtext("a:published", default="", namespaces=NS) or e.findtext("a:updated", default="", namespaces=NS),
            "text": _clean(e.findtext("a:content", default="", namespaces=NS)),
        })
    return out


_ID = re.compile(r"/comments/([a-z0-9]+)/(?:[^/]+/)?([a-z0-9]+)?")


def _ids(url: str) -> tuple[str | None, str | None]:
    m = _ID.search(url or "")
    return (m.group(1), m.group(2)) if m else (None, None)


def fetch(keyword_set: dict, config: dict) -> list[RawSignal]:
    global _requests_this_run
    from app import db

    ksid = keyword_set.get("id")
    if ksid:
        last = (db.get(db.KEYWORD_SETS, ksid) or {}).get("reddit_rss_last_run")
        if last and last > datetime.now(timezone.utc) - timedelta(days=SET_COOLDOWN_DAYS):
            return []
    subs = config.get("subreddits") or []
    if not subs:
        return []
    keywords = keyword_set.get("keywords") or []
    queries = (config.get("queries") or [])[:2]
    threads_budget = int(config.get("threads_per_set", 6))
    cutoff = lookback_cutoff()
    out: list[RawSignal] = []
    seen: set[str] = set()
    candidates: list[tuple[int, str, str, str]] = []  # (score, post_id, url, sub) for thread expansion

    def _post_signal(it: dict, sub: str, kw: str | None) -> None:
        pid, _ = _ids(it["url"])
        if not pid or pid in seen:
            return
        seen.add(pid)
        try:
            pub = dtparser.isoparse(it["published"]) if it["published"] else None
        except Exception:  # noqa: BLE001
            pub = None
        if pub and pub < cutoff:
            return
        text = it["text"] or it["title"]
        hx = heuristics(f"{it['title']}\n{text}")
        # feed-reader hygiene: link-only posts and posts with no pain/need signal are not worth an LLM call
        if not it["text"] or (hx.heuristic_score < 1 and not (hx.asks_for_recommendation or hx.mentions_diy_workaround or hx.mentions_existing_tool)):
            return
        out.append(RawSignal(source="reddit", signal_type="post", external_id=pid, url=it["url"], title=it["title"], text=clip(text),
                             author_hash=hash_author("reddit", it["author"]), published_at=pub, score=0, num_comments=None,
                             engagement={"via": "rss"}, keyword=kw, channel=f"r/{sub}", raw={"is_self": bool(it["text"])}))
        if hx.heuristic_score >= 2 and it["text"]:
            candidates.append((hx.heuristic_score, pid, it["url"], sub))

    try:
        with httpx.Client(timeout=25, headers={"User-Agent": UA}, follow_redirects=True) as client:
            for sub in subs:
                root = _get(client, f"https://www.reddit.com/r/{sub}/new.rss?limit=25")
                for it in _entries(root) if root is not None else []:
                    kw = matches_keywords(f"{it['title']}\n{it['text']}", keywords)
                    if kw is None:
                        continue
                    _post_signal(it, sub, kw)
                for q in queries:
                    root = _get(client, f"https://www.reddit.com/r/{sub}/search.rss?q={quote_plus(q)}&restrict_sr=1&sort=new")
                    for it in _entries(root) if root is not None else []:
                        _post_signal(it, sub, q)
            # comments: only for the most promising threads (real pain in the post), a few per set
            candidates.sort(reverse=True)
            for _, pid, url, sub in candidates[:threads_budget]:
                root = _get(client, url.rstrip("/") + "/.rss?limit=40")
                for it in (_entries(root) if root is not None else [])[1:]:
                    _, cid = _ids(it["url"])
                    if not cid or cid in seen or len(it["text"]) < 40 or it["text"] in ("[deleted]", "[removed]"):
                        continue
                    seen.add(cid)
                    try:
                        pub = dtparser.isoparse(it["published"]) if it["published"] else None
                    except Exception:  # noqa: BLE001
                        pub = None
                    out.append(RawSignal(source="reddit", signal_type="comment", external_id=cid, parent_external_id=pid, url=it["url"],
                                         title=it["title"], text=clip(it["text"]), author_hash=hash_author("reddit", it["author"]),
                                         published_at=pub, score=0, engagement={"via": "rss"}, keyword=None, channel=f"r/{sub}"))
    except FeedLimit as e:
        log.info("reddit_rss stopped for %s: %s (kept %d signals)", keyword_set.get("name"), e, len(out))
    if ksid and (out or _requests_this_run < MAX_REQUESTS_PER_RUN):
        db.upsert(db.KEYWORD_SETS, ksid, {"reddit_rss_last_run": datetime.now(timezone.utc)})
    return out


def reset_run_budget() -> None:
    global _requests_this_run
    _requests_this_run = 0
