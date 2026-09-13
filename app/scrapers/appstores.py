"""
App store 1-2 star reviews — the best "already paying and frustrated" source.

Play Store : google-play-scraper (unofficial but stable, uses the internal batchexecute endpoint)
             config: {"app_ids": ["com.x.y"], "country": "us", "lang": "en", "max_stars": 2}
App Store  : Apple's public RSS feed for customer reviews (official, no key, 10 pages x 50 max)
             config: {"app_ids": ["123456789"], "country": "us", "max_stars": 2}

Tip: a competitor's 1-star reviews tell you exactly which feature gap to attack.
"""
from __future__ import annotations

from dateutil import parser as dtparser

from app.config import get_settings
from app.db import hash_author
from app.models import RawSignal
from app.scrapers.base import clip, http_client, log, lookback_cutoff, polite_sleep


def fetch_playstore(keyword_set: dict, config: dict) -> list[RawSignal]:
    from google_play_scraper import Sort, reviews

    s = get_settings()
    max_stars = int(config.get("max_stars", 2))
    cutoff = lookback_cutoff()
    out: list[RawSignal] = []
    for app_id in config.get("app_ids", []):
        for star in range(1, max_stars + 1):
            try:
                result, _ = reviews(
                    app_id,
                    lang=config.get("lang", "en"),
                    country=config.get("country", "us"),
                    sort=Sort.NEWEST,
                    count=s.store_review_limit,
                    filter_score_with=star,
                )
            except Exception as e:  # noqa: BLE001
                log.error("playstore %s (%s*) failed: %s", app_id, star, e)
                continue
            for rv in result:
                at = rv.get("at")
                if at and at.tzinfo is None:
                    from datetime import timezone

                    at = at.replace(tzinfo=timezone.utc)
                if at and at < cutoff:
                    continue
                out.append(
                    RawSignal(
                        source="playstore",
                        signal_type="review",
                        external_id=rv["reviewId"],
                        url=f"https://play.google.com/store/apps/details?id={app_id}&reviewId={rv['reviewId']}",
                        title=None,
                        text=clip(rv.get("content")),
                        author_hash=hash_author("playstore", rv.get("userName")),
                        published_at=at,
                        rating=float(rv.get("score") or star),
                        score=int(rv.get("thumbsUpCount") or 0),
                        engagement={"app_version": rv.get("reviewCreatedVersion"), "reply": bool(rv.get("replyContent"))},
                        keyword=app_id,
                        channel=app_id,
                    )
                )
            polite_sleep()
    return out


def fetch_appstore(keyword_set: dict, config: dict) -> list[RawSignal]:
    max_stars = int(config.get("max_stars", 2))
    country = config.get("country", "us")
    cutoff = lookback_cutoff()
    out: list[RawSignal] = []
    with http_client() as client:
        for app_id in config.get("app_ids", []):
            for page in range(1, 11):  # Apple caps the feed at 10 pages
                url = f"https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"
                try:
                    r = client.get(url)
                    r.raise_for_status()
                    entries = (r.json().get("feed") or {}).get("entry") or []
                except Exception as e:  # noqa: BLE001
                    log.error("appstore %s p%s failed: %s", app_id, page, e)
                    break
                if isinstance(entries, dict):
                    entries = [entries]
                if not entries:
                    break
                stop = False
                for e in entries:
                    try:
                        rating = float(e["im:rating"]["label"])
                        published = dtparser.isoparse(e["updated"]["label"])
                    except Exception:  # noqa: BLE001
                        continue
                    if published < cutoff:
                        stop = True
                        break
                    if rating > max_stars:
                        continue
                    rid = e["id"]["label"]
                    out.append(
                        RawSignal(
                            source="appstore",
                            signal_type="review",
                            external_id=rid,
                            url=f"https://apps.apple.com/{country}/app/id{app_id}?see-all=reviews",
                            title=e.get("title", {}).get("label"),
                            text=clip(e.get("content", {}).get("label")),
                            author_hash=hash_author("appstore", (e.get("author") or {}).get("name", {}).get("label")),
                            published_at=published,
                            rating=rating,
                            score=int((e.get("im:voteSum") or {}).get("label") or 0),
                            engagement={"version": (e.get("im:version") or {}).get("label")},
                            keyword=app_id,
                            channel=app_id,
                        )
                    )
                if stop:
                    break
                polite_sleep()
    return out
