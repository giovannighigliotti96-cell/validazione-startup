"""
Trustpilot — 1-2 star reviews of configured company domains.
ToS forbid scraping; Cloudflare blocks aggressive clients. Disabled by default
(ENABLE_TRUSTPILOT=false). When enabled: 1 request / ~3s, a few pages per domain,
honest User-Agent. Use for personal research only.

Strategy: the review page embeds a Next.js JSON blob (__NEXT_DATA__) with the
reviews; we parse that instead of the DOM (more stable). Falls back to [] if absent.

Config: {"domains": ["dentrix.com", ...], "pages": 3, "stars": [1, 2]}
"""
from __future__ import annotations

import json

from bs4 import BeautifulSoup
from dateutil import parser as dtparser

from app.config import get_settings
from app.db import hash_author
from app.models import RawSignal
from app.scrapers.base import clip, http_client, log, polite_sleep

BASE = "https://www.trustpilot.com/review/"


def _walk_reviews(obj):
    """Depth-first search for lists of dicts that look like reviews."""
    if isinstance(obj, dict):
        if "reviews" in obj and isinstance(obj["reviews"], list):
            yield from obj["reviews"]
        for v in obj.values():
            yield from _walk_reviews(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_reviews(v)


def fetch(keyword_set: dict, config: dict) -> list[RawSignal]:
    if not get_settings().enable_trustpilot:
        log.info("trustpilot disabled (ENABLE_TRUSTPILOT=false)")
        return []
    stars = config.get("stars", [1, 2])
    pages = int(config.get("pages", 3))
    out: list[RawSignal] = []
    seen: set[str] = set()
    with http_client() as client:
        for domain in config.get("domains", []):
            for page in range(1, pages + 1):
                params = [("stars", s) for s in stars] + [("page", page)]
                try:
                    r = client.get(BASE + domain, params=params)
                    if r.status_code in (403, 429):
                        log.warning("trustpilot blocked (%s) on %s — stopping", r.status_code, domain)
                        break
                    r.raise_for_status()
                except Exception as e:  # noqa: BLE001
                    log.error("trustpilot %s p%s failed: %s", domain, page, e)
                    break
                soup = BeautifulSoup(r.text, "lxml")
                blob = soup.find("script", id="__NEXT_DATA__")
                if not blob:
                    log.warning("trustpilot: __NEXT_DATA__ not found for %s (markup changed?)", domain)
                    break
                try:
                    data = json.loads(blob.string or "{}")
                except json.JSONDecodeError:
                    break
                got = 0
                for rv in _walk_reviews(data):
                    rid = str(rv.get("id") or "")
                    if not rid or rid in seen or not isinstance(rv.get("text"), str):
                        continue
                    seen.add(rid)
                    rating = rv.get("rating")
                    if rating is not None and int(rating) not in stars:
                        continue
                    dates = rv.get("dates") or {}
                    published = None
                    for k in ("publishedDate", "experiencedDate"):
                        if dates.get(k):
                            try:
                                published = dtparser.isoparse(dates[k])
                                break
                            except Exception:  # noqa: BLE001
                                pass
                    consumer = rv.get("consumer") or {}
                    out.append(
                        RawSignal(
                            source="trustpilot",
                            signal_type="review",
                            external_id=rid,
                            url=f"https://www.trustpilot.com/reviews/{rid}",
                            title=rv.get("title"),
                            text=clip(rv.get("text")),
                            author_hash=hash_author("trustpilot", consumer.get("id") or consumer.get("displayName")),
                            published_at=published,
                            rating=float(rating) if rating is not None else None,
                            score=(rv.get("likes") or 0),
                            engagement={"verified": rv.get("labels", {}).get("verification", {}).get("isVerified")},
                            keyword=domain,
                            channel=domain,
                        )
                    )
                    got += 1
                if got == 0:
                    break
                polite_sleep()
                polite_sleep()  # extra-polite for Trustpilot
    return out
