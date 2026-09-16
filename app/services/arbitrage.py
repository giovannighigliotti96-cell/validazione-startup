"""
THIRD PATH — "US -> Italy arbitrage": recently launched / funded products abroad whose PROBLEM has no
localized solution in Italy/EU yet. Evidence-based, like the other two paths:

 1. collect_launches()      Product Hunt (last 30 days, broad topics), HN "Launch HN"/"Show HN", TechCrunch RSS
 2. screen()                strong model: problem solved, persona, category, consumer/B2B, why-now; skip pure hype
 3. italy_check()           Tavily: does an Italian/EU localized equivalent exist? (names verified by URL); Italian demand
                            signals for the same problem (reddit_search IT + youtube IT) -> stored as raw_signals
 4. verdict                 if >= 3 real Italian signals and no localized player -> hypothesis cluster (path=arbitrage)
                            else watchlist. Everything lands in `us_launches` for the weekly digest.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from app import db
from app.config import get_settings
from app.scrapers.base import http_client
from app.services import analysis, funnel

log = analysis.log
COLL = "us_launches"


# ----------------------------------------------------------------------------
# 1. collect
# ----------------------------------------------------------------------------
def _producthunt(days: int = 30, topics=("saas", "productivity", "fintech", "health", "marketing", "artificial-intelligence", "developer-tools", "e-commerce")) -> list[dict]:
    s = get_settings()
    if not s.producthunt_token:
        return []
    q = """query($topic:String!,$after:DateTime){ posts(topic:$topic, postedAfter:$after, order:VOTES, first:20){ edges{ node{ id name tagline description url website votesCount createdAt topics(first:3){edges{node{slug}}} } } } }"""
    after = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    out = []
    with http_client() as c:
        c.headers["Authorization"] = f"Bearer {s.producthunt_token}"
        for t in topics:
            try:
                r = c.post("https://api.producthunt.com/v2/api/graphql", json={"query": q, "variables": {"topic": t, "after": after}})
                for e in r.json()["data"]["posts"]["edges"]:
                    n = e["node"]
                    if n["votesCount"] >= 150:
                        out.append({"source": "producthunt", "name": n["name"], "tagline": n.get("tagline"), "description": (n.get("description") or "")[:400],
                                    "url": n.get("website") or n.get("url"), "votes": n["votesCount"], "date": n["createdAt"][:10], "topic": t})
            except Exception as ex:  # noqa: BLE001
                log.warning("ph launches %s: %s", t, ex)
    return out


def _hn_launches(days: int = 30) -> list[dict]:
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    out = []
    with http_client() as c:
        for q in ("Launch HN", "Show HN"):
            try:
                r = c.get("https://hn.algolia.com/api/v1/search", params={"query": f'"{q}"', "tags": "story", "numericFilters": f"created_at_i>{cutoff},points>80", "hitsPerPage": 40})
                for h in r.json().get("hits", []):
                    out.append({"source": "hackernews", "name": (h.get("title") or "").replace(q + ":", "").strip()[:80], "tagline": h.get("title"),
                                "description": (h.get("story_text") or "")[:400], "url": h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
                                "votes": h.get("points"), "date": (h.get("created_at") or "")[:10], "topic": "hn"})
            except Exception as ex:  # noqa: BLE001
                log.warning("hn launches: %s", ex)
    return out


def _techcrunch(days: int = 30) -> list[dict]:
    out = []
    with http_client(timeout=20) as c:
        for feed in ("https://techcrunch.com/category/startups/feed/", "https://techcrunch.com/category/venture/feed/"):
            try:
                root = ET.fromstring(c.get(feed).content)
                for it in root.findall(".//item")[:40]:
                    title = it.findtext("title") or ""
                    if re.search(r"raises|launch|funding|seed|series", title, re.I):
                        out.append({"source": "techcrunch", "name": title[:90], "tagline": title, "description": re.sub(r"<[^>]+>", " ", it.findtext("description") or "")[:400],
                                    "url": it.findtext("link"), "votes": None, "date": (it.findtext("pubDate") or "")[:16], "topic": "news"})
            except Exception as ex:  # noqa: BLE001
                log.warning("techcrunch feed: %s", ex)
    return out


def collect_launches(days: int = 30) -> list[dict]:
    items = _producthunt(days) + _hn_launches(days) + _techcrunch(days)
    seen, out = set(), []
    for it in items:
        k = re.sub(r"\W+", "", (it.get("name") or "").lower())[:30]
        if k and k not in seen:
            seen.add(k); out.append(it)
    return out


# ----------------------------------------------------------------------------
# 2. screen
# ----------------------------------------------------------------------------
class Screened(BaseModel):
    idx: int
    keep: bool = Field(description="False for hype, crypto, dev-tools for developers, agencies, hardware, or unclear problem")
    problem: str = Field(description="The concrete problem solved, one sentence, for whom")
    persona: str
    category: str = Field(description="e.g. 'invoice collection for freelancers', 'clinic scheduling'")
    audience: Literal["b2b_smb", "b2b_enterprise", "prosumer", "consumer"]
    two_sided: bool
    why_now: str = Field(default="")
    italian_search_terms: list[str] = Field(default_factory=list, description="2-3 Italian queries an Italian buyer would type when looking for this")
    replicable_solo: bool = Field(description="Could a small team ship a credible version in <= 10 weeks?")
    thesis: Literal["ai_native_service", "saas_challenger", "company_brain", "none"] = Field(default="none", description="Which active market thesis this launch fits, if any")


class ScreenResponse(BaseModel):
    items: list[Screened]


SCREEN_PROMPT = """These products were launched or funded recently (mostly US). For each, say what PROBLEM it solves and for whom, and whether it is a
candidate for an Italy/EU localized version built by a solo founder (Italy, marketing/sales background, builds web software alone, no capital).
Be selective: keep only products with a clear, recurring problem and a paying persona. Hype, crypto, developer tools, hardware, enterprise-only, agencies -> keep=false.
Tag each kept item with the market thesis it fits: ai_native_service (sells the outcome of an outsourced service), saas_challenger (replaces legacy software cheaper/AI-native), company_brain, or none.

LAUNCHES (idx :: source :: name :: tagline :: description):
{items}
"""


def screen(items: list[dict]) -> list[dict]:
    kept = []
    for chunk in db.chunks(items, 15):
        txt = "\n".join(f"{i} :: {it['source']} :: {it['name']} :: {it.get('tagline') or ''} :: {(it.get('description') or '')[:200]}" for i, it in enumerate(chunk))
        try:
            data = analysis.llm_json(SCREEN_PROMPT.format(items=txt), ScreenResponse, strong=True)
        except Exception as ex:  # noqa: BLE001
            log.error("screen failed: %s", ex); continue
        for s in data.get("items", []):
            try:
                it = chunk[int(s["idx"])]
            except (KeyError, ValueError, IndexError, TypeError):
                continue
            if s.get("keep"):
                kept.append({**it, **{k: s.get(k) for k in ("problem", "persona", "category", "audience", "two_sided", "why_now", "italian_search_terms", "replicable_solo", "thesis")}})
    return kept


# ----------------------------------------------------------------------------
# 3. Italy check
# ----------------------------------------------------------------------------
class ItalyCheck(BaseModel):
    localized_players: list[dict] = Field(description="items {name, url, note}: Italian or EU-localized products solving the SAME problem, ONLY from the search results")
    global_player_serves_italy: bool = Field(description="True if the US product (or a global one) is already available in Italian with local payments/support")
    gap_note: str


ITALY_PROMPT = """Does an Italian (or EU-localized, in Italian) product already solve this problem? Use ONLY the search results above; every URL will be verified.
PROBLEM: {problem}
CATEGORY: {category}
US PRODUCT: {name} — {url}
"""


def italy_check(item: dict) -> dict:
    terms = item.get("italian_search_terms") or [item.get("category") or item["name"]]
    data = analysis.llm_json(ITALY_PROMPT.format(problem=item.get("problem"), category=item.get("category"), name=item["name"], url=item.get("url")),
                             ItalyCheck, grounded=True, strong=True,
                             search_queries=[f"{terms[0]} software italiano"] + [f"site:capterra.it {t}" for t in terms[:2]] + [f"{item['name']} italia OR italiano"])
    players = [p for p in data.get("localized_players", []) if isinstance(p, dict) and p.get("name") and analysis.verify_url(p.get("url"))]
    return {"localized_players": players, "global_serves_italy": data.get("global_player_serves_italy"), "gap_note": data.get("gap_note")}


def italian_demand(item: dict, keyword_set_id: str) -> int:
    """Look for Italian people expressing the same problem (reddit_search IT + youtube IT); store as raw_signals; return count kept."""
    from app.services import runner

    terms = (item.get("italian_search_terms") or [])[:2]
    if not terms:
        return 0
    ks = db.get(db.KEYWORD_SETS, keyword_set_id)
    ks2 = {**ks, "keywords": [], "sources": {"reddit_search": {"queries": terms, "subreddits": ["italy", "ItaliaPersonalFinance"], "days": 730, "max_results": 8},
                                              "youtube": {"queries": terms, "videos_per_query": 2, "relevance_language": "it"}}}
    db.upsert(db.KEYWORD_SETS, keyword_set_id, {"reddit_search_last_run": None})
    r = runner.run_keyword_set(ks2, ["reddit_search", "youtube"], "arbitrage")
    return sum((v.get("inserted") or 0) for v in r["stats"].values() if isinstance(v, dict))


# ----------------------------------------------------------------------------
# 4. run
# ----------------------------------------------------------------------------
def run(days: int = 30, max_items: int = 12) -> dict:
    ks = next((k for k in db.list_all(db.KEYWORD_SETS) if k["name"] == "arbitrage_us_it"), None)
    if not ks:
        kid = db.upsert(db.KEYWORD_SETS, None, {"name": "arbitrage_us_it", "vertical": "arbitrage", "country": "IT", "is_active": True, "keywords": [], "sources": {},
                                                 "description": "Terzo percorso: problemi risolti da lanci USA recenti, cercati in Italia.", "created_at": db.now()})
        ks = db.get(db.KEYWORD_SETS, kid)
    launches = collect_launches(days)
    known = {d.id for d in db.get_db().collection(COLL).select([]).stream()}
    fresh = [it for it in launches if db.safe_id(it["source"], it["name"]) not in known]
    kept = screen(fresh[:60])
    results = []
    for it in kept[:max_items]:
        doc_id = db.safe_id(it["source"], it["name"])
        try:
            ic = italy_check(it)
            n_it = italian_demand(it, ks["id"]) if not ic["localized_players"] else 0
        except analysis.BudgetExhausted:
            break
        except Exception as ex:  # noqa: BLE001
            log.error("arbitrage %s: %s", it["name"], ex); continue
        verdict = ("localized_exists" if ic["localized_players"] else "global_serves_italy" if ic.get("global_serves_italy") else
                   "candidate" if n_it >= 3 else "watchlist_no_it_signals")
        row = {**it, "italy": ic, "italian_signals": n_it, "verdict": verdict, "checked_at": db.now()}
        db.upsert(COLL, doc_id, row)
        results.append({"name": it["name"], "problem": it.get("problem"), "verdict": verdict, "it_players": [p["name"] for p in ic["localized_players"]], "it_signals": n_it})
    # candidates -> analysis pipeline picks the Italian signals up (extraction/clustering) in the next run
    for launch in db.get_db().collection(COLL).select([]).stream():
        pass
    return {"collected": len(launches), "new": len(fresh), "screened_kept": len(kept), "checked": results, "calls": analysis.budget.calls}
