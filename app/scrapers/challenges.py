"""
Institutional problem statements: open-innovation challenges with a sponsor and a prize.
A different signal type — not "I complain" but "we pay whoever solves this". Persona = the sponsoring organisation.

Sources (checked 2026-09-16), read from each site's OWN challenge sitemap (the public, robots-allowed index):
  - Nesta Challenge Works  challengeworks.org/challenge-prizes-sitemap.xml
  - HeroX                  herox.com/sitemap_challenges.xml
Not integrated: OpenIDEO (broken TLS + JS pages), MIT Solve (JS-rendered Livewire, no feed), TechCrunch Battlefield
(finalists = startups, not problem statements — covered by arbitrage.py via the TechCrunch feed).

Config: {"sources": ["nesta", "herox", "openideo"], "max_per_source": 15}
Weekly is plenty (few new challenges per week). The keyword-set guard `challenges_last_run` enforces >= 6 days between runs.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup
from dateutil import parser as dtparser

from app.db import hash_author
from app.models import RawSignal
from app.scrapers.base import clip, http_client, log, polite_sleep


def _text(html: str, limit: int = 3000) -> str:
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "nav", "footer", "header"]):
        t.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    return re.sub(r"\s+", " ", main.get_text(" ", strip=True))[:limit]


def _from_sitemap(sitemap_url: str, source_key: str, channel: str, sponsor: str, max_n: int, must_match: str = r"challenge|prize|competition|award|solution|winner") -> list[RawSignal]:
    """Canonical, robots-friendly path: the site's own challenge sitemap -> newest pages -> main text."""
    out = []
    with http_client(timeout=25) as c:
        r = c.get(sitemap_url)
        entries = re.findall(r"<url>\s*<loc>(.*?)</loc>(?:\s*<lastmod>(.*?)</lastmod>)?", r.text, re.S)
        entries.sort(key=lambda e: e[1] or "", reverse=True)
        for loc, lastmod in entries[:max_n]:
            try:
                rr = c.get(loc)
                if rr.status_code != 200:
                    continue
                s2 = BeautifulSoup(rr.text, "lxml")
                title = s2.find("h1").get_text(strip=True) if s2.find("h1") else loc.rstrip("/").rsplit("/", 1)[-1]
                body = _text(rr.text)
                if title in body[:1500]:  # drop site chrome before the challenge title
                    body = body[body.index(title):]
                if len(body) < 200 or not re.search(must_match, body, re.I):
                    continue
                prize = re.search(r"(\$|€|£)\s?[\d,]{4,}", body)
                try:
                    pub = dtparser.parse(lastmod) if lastmod else datetime.now(timezone.utc)
                except Exception:  # noqa: BLE001
                    pub = datetime.now(timezone.utc)
                out.append(RawSignal(source="challenge", signal_type="post", external_id=f"{source_key}_" + re.sub(r"\W+", "_", loc)[-70:], url=loc, title=title,
                                     text=clip(body), author_hash=hash_author("challenge", f"{sponsor}:{loc}"),
                                     published_at=pub if pub.tzinfo else pub.replace(tzinfo=timezone.utc), keyword=source_key, channel=channel,
                                     engagement={"sponsor": sponsor, "prize": prize.group(0) if prize else None}))
            except Exception as e:  # noqa: BLE001
                log.warning("%s %s: %s", source_key, loc, e)
            polite_sleep(); polite_sleep()
    return out


def _nesta(max_n: int) -> list[RawSignal]:
    return _from_sitemap("https://challengeworks.org/challenge-prizes-sitemap.xml", "nesta", "challengeworks.org", "Challenge Works (Nesta)", max_n)


def _herox(max_n: int) -> list[RawSignal]:
    return _from_sitemap("https://www.herox.com/sitemap_challenges.xml", "herox", "herox.com", "HeroX sponsor", max_n)


def _openideo(max_n: int) -> list[RawSignal]:
    return []  # challenges.openideo.com has a broken TLS certificate and JS-only pages (2026-09); revisit


def fetch(keyword_set: dict, config: dict) -> list[RawSignal]:
    from app import db

    ksid = keyword_set.get("id")
    if ksid:
        last = (db.get(db.KEYWORD_SETS, ksid) or {}).get("challenges_last_run")
        if last and last > datetime.now(timezone.utc) - timedelta(days=6):
            log.info("challenges skipped (ran <6 days ago)")
            return []
        db.upsert(db.KEYWORD_SETS, ksid, {"challenges_last_run": datetime.now(timezone.utc)})
    n = int(config.get("max_per_source", 15))
    out: list[RawSignal] = []
    for name, fn in (("nesta", _nesta), ("herox", _herox), ("openideo", _openideo)):
        if name in (config.get("sources") or ["nesta", "herox", "openideo"]):
            try:
                got = fn(n); out += got; log.info("challenges %s: %d", name, len(got))
            except Exception as e:  # noqa: BLE001
                log.error("challenges %s failed: %s", name, e)
    return out
