"""
Product Hunt — SUPPLY side (competitor_signals), via the official GraphQL API v2.
Token: https://www.producthunt.com/v2/oauth/applications -> "Developer Token".
Rate limit: 6250 complexity points / 15 min (generous for our use).

The API has no free-text search, so we page through posts by TOPIC and filter
by keywords in name/tagline/description locally.
Config: {"topics": ["health", "productivity"], "keywords": ["dental"], "max_pages": 5}

What this tells you: launches per keyword in the last 24 months = how contested the
category is *among builders* (leading indicator of red ocean). A product with
launched_at 2 years ago and a dead website = "prior failed attempt" (flag is_dead manually).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import db
from app.config import get_settings
from app.heuristics import matches_keywords
from app.scrapers.base import http_client, log, polite_sleep

API = "https://api.producthunt.com/v2/api/graphql"
QUERY = """
query($topic: String!, $after: String, $postedAfter: DateTime) {
  posts(topic: $topic, after: $after, postedAfter: $postedAfter, order: VOTES, first: 50) {
    pageInfo { hasNextPage endCursor }
    edges { node {
      id name tagline description url website votesCount commentsCount createdAt
      topics(first: 5) { edges { node { slug } } }
    } }
  }
}
"""


def fetch(keyword_set: dict, config: dict) -> dict:
    """Persists into competitor_signals. Returns stats."""
    s = get_settings()
    if not s.producthunt_token:
        log.info("producthunt skipped: PRODUCTHUNT_TOKEN not set")
        return {"fetched": 0, "inserted": 0, "skipped_no_token": True}
    keywords = config.get("keywords") or []
    max_pages = int(config.get("max_pages", 5))
    posted_after = (datetime.now(timezone.utc) - timedelta(days=int(config.get("lookback_days", 730)))).isoformat()
    docs: dict[str, dict] = {}
    fetched = 0
    with http_client() as client:
        client.headers["Authorization"] = f"Bearer {s.producthunt_token}"
        for topic in config.get("topics", []):
            after, page = None, 0
            while page < max_pages:
                try:
                    r = client.post(API, json={"query": QUERY, "variables": {"topic": topic, "after": after, "postedAfter": posted_after}})
                    r.raise_for_status()
                    data = r.json()["data"]["posts"]
                except Exception as e:  # noqa: BLE001
                    log.error("producthunt topic %s failed: %s", topic, e)
                    break
                for edge in data["edges"]:
                    n = edge["node"]
                    fetched += 1
                    blob = f"{n['name']} {n.get('tagline') or ''} {n.get('description') or ''}"
                    kw = matches_keywords(blob, keywords)
                    if kw is None:
                        continue
                    doc_id = db.safe_id("producthunt", n["id"])
                    docs[doc_id] = {
                        "keyword_set_id": keyword_set.get("id"),
                        "cluster_id": None,
                        "source": "producthunt",
                        "external_id": n["id"],
                        "name": n["name"],
                        "url": n.get("website") or n.get("url"),
                        "tagline": n.get("tagline"),
                        "keyword": kw or topic,
                        "launched_at": (n.get("createdAt") or "")[:10] or None,
                        "votes": n.get("votesCount"),
                        "reviews_count": n.get("commentsCount"),
                        "is_dead": None,
                        "raw": {"topics": [t["node"]["slug"] for t in n["topics"]["edges"]], "ph_url": n.get("url")},
                        "captured_at": db.now(),
                    }
                if not data["pageInfo"]["hasNextPage"]:
                    break
                after = data["pageInfo"]["endCursor"]
                page += 1
                polite_sleep()
    inserted, existing = db.insert_new_only(db.COMPETITOR_SIGNALS, docs)
    return {"fetched": fetched, "matched": len(docs), "inserted": inserted, "existing": existing}
