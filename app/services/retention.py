"""
Data retention — what we promise in the privacy policy and in the Reddit Data API request, enforced in code.

Reddit Data API Terms §3.2: "use or retain any User Content ... beyond your approved use case, and you must immediately
delete any data not required for it". Our approved use is aggregate problem research, so for Reddit-sourced signals:

  - raw text / title / raw payload are deleted RAW_TEXT_DAYS after collection (the LLM extraction is done long before);
  - we keep: permalink, the extracted problem statement (our own words), scores/flags, a salted author hash
    (never a username), cluster membership;
  - cluster evidence quotes never come from Reddit; landing pages never show Reddit content.

Runs daily from the scrape job. Idempotent.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import db
from app.scrapers.base import log

RAW_TEXT_DAYS = 30
SOURCES = ("reddit",)  # reddit_search snippets are stored with source="reddit" too


def apply(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RAW_TEXT_DAYS)
    client = db.get_db()
    purged = 0
    batch = client.batch()
    for src in SOURCES:
        q = client.collection(db.RAW_SIGNALS).where("source", "==", src).where("scraped_at", "<", cutoff).select(["text"])
        for d in q.stream():
            if not (d.to_dict() or {}).get("text"):
                continue  # already purged
            batch.update(d.reference, {"text": None, "title": None, "raw": None, "retention": {"raw_purged_at": now, "policy": f"{RAW_TEXT_DAYS}d"}})
            purged += 1
            if purged % 400 == 0:
                batch.commit()
                batch = client.batch()
    batch.commit()
    log.info("retention: raw text purged on %d signals older than %d days", purged, RAW_TEXT_DAYS)
    return {"purged": purged, "cutoff": cutoff.isoformat()}
