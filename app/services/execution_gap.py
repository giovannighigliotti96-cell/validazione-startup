"""
SECOND PATH — "execution gap": validated category, incumbents that execute badly.

The first path looks for problems nobody solves (attack_vector feature_gap / no_solution_exists).
This path takes clusters dominated by QUALITY complaints about existing tools and asks, with evidence:
  1. category_health   — are ALL players bad, or just one? Core-product ratings (Capterra/G2 via search) AND store app ratings
                         (Play + App Store, legitimate APIs). Companion-app vs core-product divergence is recorded, not confused.
  2. lockin            — WHY do users stay? (ecosystem gatekeepers like accountants/federations, data migration, integrations, contracts,
                         compliance). Named factors + level. Incumbents can afford to be bad only behind a moat.
  3. switch_intent     — do they actually switch? Signals seeking an alternative + "X alternative" threads + Trends slope.
  4. execution_edge    — what, concretely, would be done better and why the incumbent can't (legacy desktop, no mobile, no API, support).
Everything lands on opportunity_scoring.execution_gap and is judged by the execution-gap criteria in funnel_stages.
"""
from __future__ import annotations

import json
import re
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from app import db
from app.services import analysis, funnel

log = analysis.log
EXEC_VECTORS = {"quality_complaint", "price_complaint"}


# ----------------------------------------------------------------------------
# 1. category health from app stores (reliable, legitimate) + review sites (via search)
# ----------------------------------------------------------------------------
def _play_app(name: str) -> dict | None:
    try:
        from google_play_scraper import app as gp_app, search

        hits = search(name, lang="en", country="us", n_hits=3)
        for h in hits:
            if h.get("appId") and name.lower().split()[0] in (h.get("title") or "").lower():
                a = gp_app(h["appId"], lang="en", country="us")
                return {"store": "play", "app_id": h["appId"], "title": a.get("title"), "rating": a.get("score"), "ratings_count": a.get("ratings"),
                        "installs": a.get("installs"), "updated": a.get("updated")}
    except Exception as e:  # noqa: BLE001
        log.info("play lookup %s: %s", name, e)
    return None


def _apple_app(name: str) -> dict | None:
    try:
        r = httpx.get("https://itunes.apple.com/search", params={"term": name, "entity": "software", "limit": 3, "country": "us"}, timeout=15)
        for a in r.json().get("results", []):
            if name.lower().split()[0] in (a.get("trackName") or "").lower():
                return {"store": "apple", "app_id": a.get("trackId"), "title": a.get("trackName"), "rating": a.get("averageUserRating"),
                        "ratings_count": a.get("userRatingCount"), "updated": a.get("currentVersionReleaseDate")}
    except Exception as e:  # noqa: BLE001
        log.info("apple lookup %s: %s", name, e)
    return None


class ReviewSiteRatings(BaseModel):
    ratings: list[dict] = Field(description="items {name, site: capterra|g2|trustpilot|other, rating (0-5), reviews_count, url, top_complaints: [..]} ONLY from the search results")


REVIEW_SITE_PROMPT = """From the search results above, extract the CORE-PRODUCT ratings of these products on review sites (Capterra, G2, Software Advice, GetApp, Trustpilot).
Only report numbers that literally appear in the results; skip a product if no rating is shown. Also list the 2-3 most repeated complaint themes per product if visible.
PRODUCTS: {names}
"""


def category_health(cluster_id: str, competitor_names: list[str]) -> dict:
    stores = []
    for n in competitor_names[:8]:
        for f in (_play_app, _apple_app):
            a = f(n)
            if a:
                stores.append({"name": n, **a})
    try:
        rs = analysis.llm_json(REVIEW_SITE_PROMPT.format(names=", ".join(competitor_names[:8])), ReviewSiteRatings, grounded=True, strong=True,
                               search_queries=[f"site:capterra.com {n} reviews rating" for n in competitor_names[:4]] + [f"site:g2.com {n} reviews" for n in competitor_names[:3]])
        core = [x for x in rs.get("ratings", []) if isinstance(x, dict) and isinstance(x.get("rating"), (int, float))
                and isinstance(x.get("reviews_count"), (int, float)) and x["reviews_count"] >= 30]  # a rating without volume is a single review
    except Exception as e:  # noqa: BLE001
        log.warning("review-site ratings failed: %s", e)
        core = []
    store_r = [s["rating"] for s in stores if isinstance(s.get("rating"), (int, float)) and (s.get("ratings_count") or 0) >= 20]
    core_r = [c["rating"] for c in core]
    excellent = [c for c in core if c["rating"] >= 4.5 and (c.get("reviews_count") or 0) >= 200] + \
                [s for s in stores if (s.get("rating") or 0) >= 4.5 and (s.get("ratings_count") or 0) >= 1000]
    themes: dict[str, int] = {}
    for c in core:
        for t in c.get("top_complaints") or []:
            k = re.sub(r"\W+", " ", str(t).lower()).strip()[:40]
            themes[k] = themes.get(k, 0) + 1
    return {
        "store_apps": stores, "core_ratings": core,
        "avg_store_rating": round(sum(store_r) / len(store_r), 2) if store_r else None,
        "avg_core_rating": round(sum(core_r) / len(core_r), 2) if core_r else None,
        "n_rated": len(set([s["name"] for s in stores] + [c.get("name") for c in core])),
        "excellent_leader_exists": bool(excellent), "excellent_leaders": [x.get("name") or x.get("title") for x in excellent],
        "companion_vs_core_gap": (round(sum(core_r) / len(core_r) - sum(store_r) / len(store_r), 2) if core_r and store_r else None),
        "shared_complaint_themes": [{"theme": k, "products": v} for k, v in sorted(themes.items(), key=lambda kv: -kv[1])[:6]],
    }


# ----------------------------------------------------------------------------
# 2. lock-in: why do they stay?
# ----------------------------------------------------------------------------
class LockinResponse(BaseModel):
    lockin_level: Literal["low", "medium", "high"]
    factors: list[dict] = Field(description="items {factor: ecosystem_gatekeeper|data_migration|integrations|contracts|compliance|habit|price, evidence, strength: low|medium|high}")
    why_users_stay: str = Field(description="Plain explanation, grounded in evidence; say 'unknown' where evidence is missing")
    do_they_switch: Literal["yes", "slowly", "rarely", "unknown"]
    switch_evidence: str = Field(description="Cite concrete evidence of switching (challenger growth, 'switched from' posts, migration tools) or say none found")
    who_wins_switchers: str = Field(description="Which challenger currently captures switchers, if any")


LOCKIN_PROMPT = """Incumbents in this category get poor reviews yet keep customers. Explain WHY, with evidence from the search results above and the user quotes.
Distinguish real moats (an accountant/federation/insurer mandates the tool; years of data; payment/bank integrations; multi-year contracts; compliance certification)
from mere habit. Then answer honestly: do customers actually switch? Who to? If evidence is missing, say unknown — do not guess.

CATEGORY / PROBLEM: {statement}
PERSONA: {persona}
INCUMBENTS: {names}
USER QUOTES:
{quotes}
"""


def lockin_analysis(cluster_id: str, names: list[str]) -> dict:
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    quotes = "\n".join(f"- \"{q['quote'][:160]}\"" for q in (c.get("evidence_quotes") or [])[:6])
    data = analysis.llm_json(LOCKIN_PROMPT.format(statement=c.get("problem_statement"), persona=c.get("persona"), names=", ".join(names[:6]), quotes=quotes),
                             LockinResponse, grounded=True, strong=True,
                             search_queries=[f"why do businesses stay with {names[0]} despite complaints switching cost" if names else "switching cost accounting software",
                                             f"{names[0]} alternative switched from migration" if names else "switch alternative",
                                             f"{c.get('persona')} {names[0] if names else ''} lock-in integrations accountant"])
    return data


# ----------------------------------------------------------------------------
# 3. switch intent: do they look for alternatives?
# ----------------------------------------------------------------------------
def switch_intent(cluster_id: str, names: list[str]) -> dict:
    sigs = analysis._cluster_signals(cluster_id, limit=300)
    seeking = [s for s in sigs if s.get("asks_for_recommendation") or re.search(r"\b(alternative|switch(ed|ing)? (from|to)|moving (away|off)|migrat)", (s.get("text") or ""), re.I)]
    threads = 0
    try:
        from app.scrapers import reddit_search

        for n in names[:2]:
            res = reddit_search._search(f"\"{n}\" alternative OR \"switched from {n}\" site:reddit.com", 365, 8)
            threads += len(res)
    except Exception as e:  # noqa: BLE001
        log.info("switch-intent search failed: %s", e)
    return {"signals_seeking_alternative": len(seeking), "seeking_share": round(len(seeking) / len(sigs), 2) if sigs else 0.0,
            "alternative_threads_found": threads, "sample": [(s.get("text") or "")[:140] for s in seeking[:3]]}


# ----------------------------------------------------------------------------
# 4. execution edge (what would be done better, concretely)
# ----------------------------------------------------------------------------
class EdgeResponse(BaseModel):
    execution_edge: str = Field(description="One concrete sentence: what the new product does better and WHY incumbents structurally cannot (legacy desktop, no mobile, no API, offshore support, pricing model). 'none' if you cannot name one.")
    edge_is_structural: bool = Field(description="True only if the incumbent's weakness is structural (architecture, business model, ecosystem), not just effort")
    wedge_segment: str = Field(description="The narrowest segment where the edge matters most and switching is easiest (e.g. new businesses without data history)")
    weeks_to_parity_on_core_job: int = Field(description="Weeks for a solo founder to match the incumbent on the ONE core job (not the whole product)")


EDGE_PROMPT = """Given a validated category with poorly-executing incumbents, define the execution edge honestly.
CATEGORY: {statement} · PERSONA: {persona}
INCUMBENTS + shared complaints: {themes}
LOCK-IN: {lockin}
Answer at PRODUCT level for THIS persona only (do not bend it toward any particular founder or another industry).
If the honest answer is that a small team cannot beat them on execution within ~8 weeks on the core job, say so (edge 'none').
"""


def execution_edge(cluster_id: str, health: dict, lockin: dict) -> dict:
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    return analysis.llm_json(EDGE_PROMPT.format(statement=c.get("problem_statement"), persona=c.get("persona"),
                                                themes=json.dumps(health.get("shared_complaint_themes")), lockin=json.dumps({k: lockin.get(k) for k in ("lockin_level", "why_users_stay", "do_they_switch")})),
                             EdgeResponse, strong=True)


def _fs_safe(v):
    """Firestore forbids arrays nested in arrays and tuples: turn inner lists into dicts/strings."""
    if isinstance(v, dict):
        return {str(k): _fs_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [({"value": _fs_safe(x)} if isinstance(x, (list, tuple)) else _fs_safe(x)) for x in v]
    return v


# ----------------------------------------------------------------------------
# orchestration
# ----------------------------------------------------------------------------
def enrich_execution_gap(cluster_id: str, force: bool = False) -> dict:
    """Runs competitor verification (if missing) then health, lock-in, switch intent, edge. ~6-8 strong calls."""
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    o = db.get(db.OPPORTUNITY_SCORING, cluster_id) or funnel.ensure_opportunity(cluster_id)
    if not force and (o.get("execution_gap") or {}).get("analyzed_at"):
        return {"skipped": "already analyzed"}
    db.upsert(db.OPPORTUNITY_SCORING, cluster_id, {"path": "execution_gap"})
    res: dict[str, Any] = {}
    try:
        if not (c.get("llm_metadata") or {}).get("scored_at"):
            analysis.score_cluster(cluster_id)
        if o.get("competitor_count") is None:
            analysis.find_competitors(cluster_id)
        comps = db.list_all(db.COMPETITOR_SIGNALS, cluster_id=cluster_id)
        names = [x["name"] for x in comps if not x.get("is_dead")][:8]
        # incumbents named in the signals themselves come first (they are the ones being complained about)
        mentioned: dict[str, int] = {}
        for s in analysis._cluster_signals(cluster_id, limit=300):
            for t in (s.get("llm_metadata") or {}).get("mentioned_tools") or []:
                k = str(t).strip()
                if k:
                    mentioned[k] = mentioned.get(k, 0) + 1
        GENERIC = {"excel", "google sheets", "sheets", "spreadsheet", "word", "outlook", "gmail", "whatsapp", "zapier", "notion", "chatgpt", "unnamed app", "unnamed pos app", "web app"}
        top_mentioned = [k for k, _ in sorted(mentioned.items(), key=lambda kv: -kv[1])[:6] if k.lower() not in GENERIC]
        if (c.get("vertical") or "") != "accounting":
            top_mentioned = [k for k in top_mentioned if "quickbooks" not in k.lower() and "xero" not in k.lower()]
        names = [n for n in dict.fromkeys(top_mentioned + names) if n.lower() not in GENERIC]
        health = category_health(cluster_id, names); res["health"] = "ok"
        lock = lockin_analysis(cluster_id, names); res["lockin"] = lock.get("lockin_level")
        swi = switch_intent(cluster_id, names); res["switch"] = swi.get("signals_seeking_alternative")
        edge = execution_edge(cluster_id, health, lock); res["edge"] = edge.get("execution_edge", "")[:80]
        db.upsert(db.OPPORTUNITY_SCORING, cluster_id, {"execution_gap": _fs_safe({
            "incumbents": names, "category_health": health, "lockin": lock, "switch_intent": swi, "edge": edge, "analyzed_at": db.now()})})
        if not o.get("founder_fit"):
            analysis.assess_founder_fit(cluster_id)
    except analysis.BudgetExhausted as e:
        res["stopped"] = str(e)
    except Exception as e:  # noqa: BLE001
        log.error("execution gap %s failed: %s", cluster_id, e)
        res["error"] = f"{type(e).__name__}: {e}"
    return res


def run_all(min_signals: int = 10, max_clusters: int = 8) -> dict:
    """Assign path=execution_gap to complaint-dominated clusters with volume and analyze the biggest ones."""
    out = {}
    cands = [c for c in db.list_all(db.PROBLEM_CLUSTERS)
             if c.get("dominant_attack_vector") in EXEC_VECTORS and (c.get("signal_count") or 0) >= min_signals and not c.get("parent_cluster_id")]
    cands.sort(key=lambda c: -(c.get("signal_count") or 0))
    for c in cands:
        funnel.ensure_opportunity(c["id"])
        db.upsert(db.OPPORTUNITY_SCORING, c["id"], {"path": "execution_gap"})
    for c in cands[:max_clusters]:
        if analysis.budget.remaining() < 8:
            out[c["name"]] = "budget"
            break
        out[c["name"]] = enrich_execution_gap(c["id"])
        funnel.evaluate(c["id"])
    return {"candidates": len(cands), "analyzed": out, "calls": analysis.budget.calls}
