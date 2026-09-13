"""
Reddit via PRAW (official API, OAuth "script" app).

Limits: 100 req/min per OAuth client. PRAW handles rate limiting for us.
Strategy: Reddit's own search is poor, so we pull `new` + `top(time_filter)` per
subreddit and filter locally with keyword_set["keywords"].
Config: {"subreddits": [...], "sorts": ["new","top"], "time_filter": "week"}
"""
from __future__ import annotations

from app.config import get_settings
from app.db import hash_author
from app.heuristics import matches_keywords
from app.models import RawSignal
from app.scrapers.base import clip, log, lookback_cutoff, ts

_reddit = None


def _client():
    global _reddit
    if _reddit is None:
        import praw

        s = get_settings()
        if not s.reddit_client_id or not s.reddit_client_secret:
            raise RuntimeError("REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set")
        _reddit = praw.Reddit(
            client_id=s.reddit_client_id,
            client_secret=s.reddit_client_secret,
            user_agent=s.reddit_user_agent,
            check_for_async=False,
        )
        _reddit.read_only = True
    return _reddit


def fetch(keyword_set: dict, config: dict) -> list[RawSignal]:
    s = get_settings()
    reddit = _client()
    keywords: list[str] = keyword_set.get("keywords") or []
    cutoff = lookback_cutoff()
    out: list[RawSignal] = []
    seen: set[str] = set()

    for sub in config.get("subreddits", []):
        subreddit = reddit.subreddit(sub)
        for sort in config.get("sorts", ["new"]):
            try:
                if sort == "top":
                    listing = subreddit.top(time_filter=config.get("time_filter", "week"), limit=s.reddit_post_limit)
                elif sort == "hot":
                    listing = subreddit.hot(limit=s.reddit_post_limit)
                else:
                    listing = subreddit.new(limit=s.reddit_post_limit)

                for post in listing:
                    if post.id in seen:
                        continue
                    seen.add(post.id)
                    created = ts(post.created_utc)
                    if created and created < cutoff:
                        continue
                    body = post.selftext or ""
                    kw = matches_keywords(f"{post.title}\n{body}", keywords)
                    if kw is None:
                        continue
                    out.append(
                        RawSignal(
                            source="reddit",
                            signal_type="post",
                            external_id=post.id,
                            url=f"https://www.reddit.com{post.permalink}",
                            title=post.title,
                            text=clip(body) or post.title,
                            author_hash=hash_author("reddit", str(post.author) if post.author else None),
                            published_at=created,
                            score=int(post.score or 0),
                            num_comments=int(post.num_comments or 0),
                            engagement={"upvote_ratio": post.upvote_ratio, "sort": sort, "flair": post.link_flair_text},
                            keyword=kw or None,
                            channel=f"r/{sub}",
                            raw={"is_self": post.is_self, "over_18": post.over_18},
                        )
                    )
                    # comments: only for posts with some traction, top-level only
                    if s.reddit_comments_per_post and (post.num_comments or 0) >= 3:
                        try:
                            post.comments.replace_more(limit=0)
                            for c in post.comments[: s.reddit_comments_per_post]:
                                if not getattr(c, "body", None) or c.body in ("[deleted]", "[removed]"):
                                    continue
                                out.append(
                                    RawSignal(
                                        source="reddit",
                                        signal_type="comment",
                                        external_id=c.id,
                                        parent_external_id=post.id,
                                        url=f"https://www.reddit.com{c.permalink}",
                                        title=post.title,
                                        text=clip(c.body),
                                        author_hash=hash_author("reddit", str(c.author) if c.author else None),
                                        published_at=ts(c.created_utc),
                                        score=int(c.score or 0),
                                        engagement={"is_op": c.is_submitter},
                                        keyword=kw or None,
                                        channel=f"r/{sub}",
                                    )
                                )
                        except Exception as e:  # noqa: BLE001
                            log.warning("reddit comments failed for %s: %s", post.id, e)
            except Exception as e:  # noqa: BLE001
                log.error("reddit r/%s (%s) failed: %s", sub, sort, e)
    return out
