"""
Hacker News via Algolia HN Search API (public, no key, ~10k req/h).
Docs: https://hn.algolia.com/api
Config: {"queries": ["...", "..."], "tags": "(story,comment)"}
Ask HN threads are the richest source of "how do you deal with X" pain.
"""
from __future__ import annotations

from html import unescape
import re

from app.config import get_settings
from app.db import hash_author
from app.models import RawSignal
from app.scrapers.base import clip, http_client, log, lookback_cutoff, polite_sleep, ts

API = "https://hn.algolia.com/api/v1/search_by_date"
_TAG = re.compile(r"<[^>]+>")


def _strip_html(s: str | None) -> str:
    return unescape(_TAG.sub(" ", s or "")).strip()


def fetch(keyword_set: dict, config: dict) -> list[RawSignal]:
    s = get_settings()
    cutoff = int(lookback_cutoff().timestamp())
    tags = config.get("tags", "(story,comment)")
    out: list[RawSignal] = []
    seen: set[str] = set()

    with http_client() as client:
        for q in config.get("queries", []):
            page, fetched = 0, 0
            while fetched < s.hn_hits_per_query:
                try:
                    r = client.get(
                        API,
                        params={
                            "query": f"\"{q}\"" if " " in q and not q.startswith("\"") else q,  # phrase match
                            "tags": tags,
                            "numericFilters": f"created_at_i>{cutoff}",
                            "hitsPerPage": 100,
                            "page": page,
                        },
                    )
                    r.raise_for_status()
                    data = r.json()
                except Exception as e:  # noqa: BLE001
                    log.error("hn query %r page %s failed: %s", q, page, e)
                    break
                hits = data.get("hits", [])
                if not hits:
                    break
                for h in hits:
                    oid = str(h.get("objectID"))
                    if oid in seen:
                        continue
                    seen.add(oid)
                    is_story = "story" in (h.get("_tags") or [])
                    text = _strip_html(h.get("story_text") or h.get("comment_text") or "")
                    title = h.get("title") or h.get("story_title")
                    if not text and not title:
                        continue
                    out.append(
                        RawSignal(
                            source="hackernews",
                            signal_type="story" if is_story else "comment",
                            external_id=oid,
                            parent_external_id=None if is_story else str(h.get("story_id") or ""),
                            url=f"https://news.ycombinator.com/item?id={oid}",
                            title=title,
                            text=clip(text) or title or "",
                            author_hash=hash_author("hackernews", h.get("author")),
                            published_at=ts(h.get("created_at_i")),
                            score=h.get("points"),
                            num_comments=h.get("num_comments"),
                            engagement={"story_url": h.get("url")},
                            keyword=q,
                            channel="hn",
                        )
                    )
                fetched += len(hits)
                page += 1
                if page >= data.get("nbPages", 1):
                    break
                polite_sleep()
    return out
