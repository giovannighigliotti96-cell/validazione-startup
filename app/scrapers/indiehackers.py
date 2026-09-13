"""
Indie Hackers — NO public API. Best-effort HTML scraper, disabled by default
(ENABLE_INDIEHACKERS=false). Their ToS discourage automated access; keep the
frequency very low (one run/day max) and expect breakage: the site is a React SPA
and server-rendered markup changes often. This should never be a primary source.

Config: {"queries": ["..."]}
Strategy: fetch the public search page and parse post cards. If the markup no
longer matches, we return [] and log a warning instead of failing the run.
"""
from __future__ import annotations

from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from app.config import get_settings
from app.heuristics import matches_keywords
from app.models import RawSignal
from app.scrapers.base import clip, http_client, log, polite_sleep

BASE = "https://www.indiehackers.com"


def fetch(keyword_set: dict, config: dict) -> list[RawSignal]:
    if not get_settings().enable_indiehackers:
        log.info("indiehackers disabled (ENABLE_INDIEHACKERS=false)")
        return []
    keywords = keyword_set.get("keywords") or []
    out: list[RawSignal] = []
    seen: set[str] = set()
    with http_client() as client:
        for q in config.get("queries", []):
            try:
                r = client.get(f"{BASE}/search?q={quote_plus(q)}")
                r.raise_for_status()
            except Exception as e:  # noqa: BLE001
                log.error("indiehackers search %r failed: %s", q, e)
                continue
            soup = BeautifulSoup(r.text, "lxml")
            # Post links look like /post/<slug>-<id> ; cards are anchors with that href.
            cards = soup.select("a[href^='/post/']")
            if not cards:
                log.warning("indiehackers: no post cards found for %r (markup changed?)", q)
            for a in cards:
                href = a.get("href", "")
                ext_id = href.rsplit("-", 1)[-1] if "-" in href else href.strip("/")
                if not ext_id or ext_id in seen:
                    continue
                seen.add(ext_id)
                title = a.get_text(" ", strip=True)
                if not title:
                    continue
                kw = matches_keywords(title, keywords)
                if kw is None:
                    continue
                out.append(
                    RawSignal(
                        source="indiehackers",
                        signal_type="post",
                        external_id=ext_id,
                        url=BASE + href,
                        title=title,
                        text=clip(title),  # body requires a second request per post; skipped to stay polite
                        keyword=q,
                        channel="indiehackers",
                    )
                )
            polite_sleep()
    return out
