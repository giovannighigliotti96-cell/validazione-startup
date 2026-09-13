"""
Common scraper interface.

Every scraper exposes:
    fetch(keyword_set: dict, config: dict) -> list[RawSignal]

`config` is the per-source block from keyword_set["sources"][<source>].
`keyword_set["keywords"]` is a local text filter applied by the scraper (empty = keep everything).
Scrapers must never raise on a single bad item — log and continue. A scraper raising
as a whole is caught by the runner and recorded in scrape_runs.stats[<source>].error.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from app.config import get_settings

log = logging.getLogger("scrapers")


def lookback_cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=get_settings().lookback_days)


def polite_sleep() -> None:
    time.sleep(get_settings().request_delay_seconds)


def http_client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; validazione-startup/0.1; research; +mailto:contact@example.com)",
            "Accept-Language": "en-US,en;q=0.9",
        },
        follow_redirects=True,
    )


def ts(epoch: int | float | None) -> datetime | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc)


def clip(text: str | None, n: int = 20000) -> str:
    return (text or "")[:n]
