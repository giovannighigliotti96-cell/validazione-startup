"""
Vertical forums running Discourse — the richest blue-ocean source: practitioners talking to practitioners.
Discourse exposes public JSON without a key: /latest.json, /c/<slug>/<id>.json, /search.json?q=..., /t/<id>.json
(Rate limit ~ 1 req/s for anonymous; we stay polite.) Respect each forum's robots.txt; anonymous read of public categories is what the UI does.

How to find them: many trade forums are Discourse (look for "/latest" URL pattern or "Powered by Discourse" in the footer).
Examples worth trying (verify they are Discourse before adding): community.dentaltown? (no, vBulletin), meta forums of vertical SaaS
(e.g. community.xero.com is not Discourse; community.monday.com is), forum.openoffice, discuss.pixls.us... The seed ships with a few.

Config: {"forums": [{"base_url": "https://community.example.com", "categories": ["general"], "searches": ["spreadsheet", "is there a way"]}],
         "topics_per_forum": 40, "posts_per_topic": 5}
"""
from __future__ import annotations

from html import unescape
import re

from dateutil import parser as dtparser

from app.db import hash_author
from app.heuristics import matches_keywords
from app.models import RawSignal
from app.scrapers.base import clip, http_client, log, lookback_cutoff, polite_sleep

_TAG = re.compile(r"<[^>]+>")


def _strip(s: str | None) -> str:
    return unescape(_TAG.sub(" ", s or "")).strip()


def _topic_posts(client, base: str, topic_id: int, limit: int) -> list[dict]:
    r = client.get(f"{base}/t/{topic_id}.json")
    r.raise_for_status()
    posts = (r.json().get("post_stream") or {}).get("posts") or []
    return posts[:limit]


def fetch(keyword_set: dict, config: dict) -> list[RawSignal]:
    keywords = keyword_set.get("keywords") or []
    per_forum = int(config.get("topics_per_forum", 40))
    per_topic = int(config.get("posts_per_topic", 5))
    cutoff = lookback_cutoff()
    out: list[RawSignal] = []
    seen: set[str] = set()
    with http_client() as client:
        for forum in config.get("forums", []):
            base = forum["base_url"].rstrip("/")
            host = re.sub(r"^https?://", "", base)
            topic_ids: list[tuple[int, str]] = []
            # 1) latest + categories
            urls = [f"{base}/latest.json"] + [f"{base}/c/{c}.json" for c in forum.get("categories", [])]
            for u in urls:
                try:
                    r = client.get(u)
                    if r.status_code != 200:
                        continue
                    for t in (r.json().get("topic_list") or {}).get("topics", [])[:per_forum]:
                        topic_ids.append((t["id"], t.get("title") or ""))
                except Exception as e:  # noqa: BLE001
                    log.warning("discourse %s failed: %s", u, e)
                polite_sleep()
            # 2) searches
            for q in forum.get("searches", []):
                try:
                    r = client.get(f"{base}/search.json", params={"q": q})
                    if r.status_code == 200:
                        for t in r.json().get("topics", [])[:per_forum]:
                            topic_ids.append((t["id"], t.get("title") or ""))
                except Exception as e:  # noqa: BLE001
                    log.warning("discourse search %s %r failed: %s", host, q, e)
                polite_sleep()
            # 3) posts
            done: set[int] = set()
            for tid, title in topic_ids:
                if tid in done:
                    continue
                done.add(tid)
                try:
                    posts = _topic_posts(client, base, tid, per_topic)
                except Exception as e:  # noqa: BLE001
                    log.warning("discourse topic %s/%s failed: %s", host, tid, e)
                    continue
                for p in posts:
                    ext = f"{host}:{p['id']}"
                    if ext in seen:
                        continue
                    seen.add(ext)
                    text = _strip(p.get("cooked"))
                    if len(text) < 40:
                        continue
                    published = dtparser.isoparse(p["created_at"])
                    if published < cutoff:
                        continue
                    kw = matches_keywords(f"{title}\n{text}", keywords)
                    if kw is None:
                        continue
                    out.append(RawSignal(
                        source="forum", signal_type="post" if p.get("post_number") == 1 else "comment",
                        external_id=ext, parent_external_id=None if p.get("post_number") == 1 else f"{host}:t{tid}",
                        url=f"{base}/t/{tid}/{p.get('post_number', 1)}", title=title, text=clip(text),
                        author_hash=hash_author("forum", p.get("username")), published_at=published,
                        score=int(p.get("score") or 0), num_comments=int(p.get("reply_count") or 0),
                        engagement={"reads": p.get("reads"), "likes": (p.get("actions_summary") or [{}])[0].get("count")},
                        keyword=kw or None, channel=host))
                polite_sleep()
    return out
