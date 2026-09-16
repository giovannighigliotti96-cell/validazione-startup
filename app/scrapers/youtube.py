"""
YouTube comments — official Data API v3 (free, 10,000 units/day; search = 100 units, commentThreads = 1 unit).

Why it works: under "how to do X in <tool>" tutorials, the comments are practitioners saying
"what if I need Y?" / "this doesn't work for Z" = feature gaps stated by the right persona.

Config: {"queries": ["quickbooks payroll tutorial", ...], "videos_per_query": 5, "comments_per_video": 100, "relevance_language": "en", "max_kept_per_video": 4}
Comments are noisy ("great tutorial!"): we keep at most `max_kept_per_video` comments per video, and only those that
mention a pain/need (heuristic flags) — one viral tutorial must never dominate a cluster.
Budget per query: ~100 + 5 units. Keep queries few and specific.
Key: YOUTUBE_API_KEY (Google Cloud > APIs > YouTube Data API v3 > credentials).
"""
from __future__ import annotations

from dateutil import parser as dtparser

from app.config import get_settings
from app.db import hash_author
from app.heuristics import matches_keywords
from app.models import RawSignal
from app.scrapers.base import clip, http_client, log, lookback_cutoff, polite_sleep

API = "https://www.googleapis.com/youtube/v3"


def fetch(keyword_set: dict, config: dict) -> list[RawSignal]:
    s = get_settings()
    if not s.youtube_api_key:
        log.info("youtube skipped: YOUTUBE_API_KEY not set")
        return []
    keywords = keyword_set.get("keywords") or []
    per_q = int(config.get("videos_per_query", 5))
    per_v = min(int(config.get("comments_per_video", 100)), 100)
    max_keep = int(config.get("max_kept_per_video", 4))
    cutoff = lookback_cutoff()
    out: list[RawSignal] = []
    seen: set[str] = set()
    with http_client() as client:
        for q in config.get("queries", []):
            try:
                r = client.get(f"{API}/search", params={"part": "snippet", "q": q, "type": "video", "maxResults": per_q,
                                                         "relevanceLanguage": config.get("relevance_language", "en"),
                                                         "order": "relevance", "key": s.youtube_api_key})
                r.raise_for_status()
                videos = [(it["id"]["videoId"], it["snippet"]["title"]) for it in r.json().get("items", []) if it.get("id", {}).get("videoId")]
            except Exception as e:  # noqa: BLE001
                log.error("youtube search %r failed: %s", q, e)
                continue
            for vid, vtitle in videos:
                try:
                    r = client.get(f"{API}/commentThreads", params={"part": "snippet", "videoId": vid, "maxResults": per_v,
                                                                     "order": "relevance", "textFormat": "plainText", "key": s.youtube_api_key})
                    if r.status_code == 403:  # comments disabled
                        continue
                    r.raise_for_status()
                    threads = r.json().get("items", [])
                except Exception as e:  # noqa: BLE001
                    log.error("youtube comments %s failed: %s", vid, e)
                    continue
                kept_here = 0
                for t in threads:
                    if kept_here >= max_keep:
                        break
                    c = t["snippet"]["topLevelComment"]["snippet"]
                    cid = t["snippet"]["topLevelComment"]["id"]
                    text = (c.get("textDisplay") or "").strip()
                    if cid in seen or len(text) < 40:
                        continue
                    seen.add(cid)
                    published = dtparser.isoparse(c["publishedAt"])
                    if published < cutoff:
                        continue
                    kw = matches_keywords(text, keywords)
                    if kw is None:
                        continue
                    from app.heuristics import analyze as _hx

                    hx = _hx(text)
                    if hx.heuristic_score < 2 and not (hx.asks_for_recommendation or hx.mentions_diy_workaround or hx.mentions_existing_tool):
                        continue  # praise / questions about the tutorial itself are not signals
                    kept_here += 1
                    out.append(RawSignal(
                        source="youtube", signal_type="comment", external_id=cid, parent_external_id=vid,
                        url=f"https://www.youtube.com/watch?v={vid}&lc={cid}", title=vtitle, text=clip(text),
                        author_hash=hash_author("youtube", c.get("authorChannelId", {}).get("value") or c.get("authorDisplayName")),
                        published_at=published, score=int(c.get("likeCount") or 0), num_comments=int(t["snippet"].get("totalReplyCount") or 0),
                        engagement={"video_title": vtitle}, keyword=kw or q, channel=f"yt:{vid}"))
                polite_sleep()
    return out
