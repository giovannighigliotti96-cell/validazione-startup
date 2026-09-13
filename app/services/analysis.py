"""
=============================================================================
 SEMANTIC LAYER (any OpenAI-compatible LLM: Mistral / Groq free tier)
=============================================================================

Pipeline (each step re-runnable, idempotent):

 1. process_unprocessed()   raw_signals (is_processed=False) -> batches -> LLM JSON
                            -> llm_problem_statement, llm_urgency, llm_frequency,
                               llm_metadata{persona, is_noise, attack_vector, tools, pain}
 2. cluster_pending()       non-noise processed signals not yet in a cluster -> LLM sees existing
                            clusters + new statements -> assigns or creates (max 3 NEW per batch)
 3. merge_clusters()        LLM proposes merges of near-duplicate clusters -> signals moved, dupes deleted
 4. enrich_cluster(id)      for clusters with enough signals: scoring + Mom Test + why-now,
                            market components (Tavily), competitors + saturation, founder fit
 5. funnel.evaluate_all()   advance stages + email

Extras: ingest_interview_notes() (closes the interview loop), recruiting_pack(),
discover_verticals() (proposes new keyword sets, inactive until approved), scan_why_now().

Budget: LLM_MAX_CALLS_PER_RUN caps calls per run; LLM_RPM throttles.
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app import db
from app.config import get_settings
from app.services import funnel, market

log = logging.getLogger("analysis")

FOUNDER_PROFILE = (
    "Solo founder based in Italy, background in digital marketing and B2B sales, can build web products alone "
    "(FastAPI / Next.js / Firebase), NO network, NO capital for paid acquisition beyond a few hundred euros. "
    "Speaks Italian and English. Reachable channels: LinkedIn/email outbound, SEO/content, vertical communities "
    "(Reddit, Facebook groups, trade forums), partnerships with trade associations. "
    "Reaching the FIRST 20 paying customers alone matters more than total market size. "
    "Penalize: enterprise sales cycles, heavy regulation, two-sided marketplaces, capital-intensive or hardware businesses."
)

AttackVector = Literal["feature_gap", "no_solution_exists", "quality_complaint", "price_complaint", "other"]
ATTACKABLE = {"feature_gap", "no_solution_exists"}


# ----------------------------------------------------------------------------
# LLM client (OpenAI-compatible) + budget + optional web search
# ----------------------------------------------------------------------------
class Budget:
    def __init__(self) -> None:
        self.calls = 0
        self.last_call = 0.0

    def reset(self) -> None:
        self.calls, self.last_call = 0, 0.0

    def remaining(self) -> int:
        return get_settings().llm_max_calls_per_run - self.calls

    def tick(self) -> None:
        s = get_settings()
        if self.calls >= s.llm_max_calls_per_run:
            raise BudgetExhausted(f"LLM_MAX_CALLS_PER_RUN={s.llm_max_calls_per_run} reached")
        wait = 60.0 / max(s.llm_rpm, 1) - (time.time() - self.last_call)
        if wait > 0:
            time.sleep(wait)
        self.calls += 1
        self.last_call = time.time()


class BudgetExhausted(RuntimeError):
    pass


class RateLimited(RuntimeError):
    pass


budget = Budget()
_client = None


def _llm():
    global _client
    if _client is None:
        from openai import OpenAI

        s = get_settings()
        if not s.llm_api_key:
            raise RuntimeError("LLM_API_KEY not set")
        _client = OpenAI(api_key=s.llm_api_key, base_url=s.llm_base_url)
    return _client


def _strip_fences(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return m.group(1).strip() if m else text


def web_search(query: str, max_results: int = 6, topic: str = "general", days: int | None = None) -> str:
    """Tavily (free tier) -> compact text context. '' if no key / failure."""
    key = get_settings().tavily_api_key
    if not key:
        return ""
    try:
        from tavily import TavilyClient

        kw: dict[str, Any] = {"max_results": max_results, "search_depth": "basic", "topic": topic}
        if days:
            kw["days"] = days
        res = TavilyClient(api_key=key).search(query, **kw)
        return "\n".join(f"- {r.get('title')}: {(r.get('content') or '')[:400]} ({r.get('url')})" for r in res.get("results", []))
    except Exception as e:  # noqa: BLE001
        log.warning("tavily search failed: %s", e)
        return ""


@retry(retry=retry_if_exception_type(RateLimited), stop=stop_after_attempt(5), wait=wait_exponential(multiplier=5, min=5, max=60))
def llm_json(prompt: str, schema: type[BaseModel] | None = None, grounded: bool = False, temperature: float = 0.2,
             search_queries: list[str] | None = None) -> Any:
    from openai import APIStatusError, RateLimitError

    context = ""
    if grounded and search_queries:
        joined = "\n".join(x for x in (web_search(q) for q in search_queries) if x)
        if joined:
            context = f"WEB SEARCH RESULTS (use these, cite URLs; if insufficient say so in notes):\n{joined}\n\n"
    schema_txt = f"\n\nRespond with a single JSON object matching this JSON Schema exactly:\n{json.dumps(schema.model_json_schema())}" if schema else ""
    budget.tick()
    try:
        resp = _llm().chat.completions.create(
            model=get_settings().llm_model, temperature=temperature, response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a precise analyst. Output ONLY valid JSON, no prose, no markdown fences."},
                {"role": "user", "content": context + prompt + schema_txt},
            ],
        )
    except RateLimitError as e:
        raise RateLimited(str(e)) from e
    except APIStatusError as e:
        if e.status_code in (429, 503):
            raise RateLimited(str(e)) from e
        raise
    text = resp.choices[0].message.content or ""
    try:
        data = json.loads(_strip_fences(text))
    except json.JSONDecodeError:
        m = re.search(r"(\{.*\}|\[.*\])", text, re.S)
        if not m:
            raise ValueError(f"LLM returned non-JSON: {text[:200]!r}")
        data = json.loads(m.group(1))
    if schema is not None:
        data = schema.model_validate(data).model_dump()
    return data


# ----------------------------------------------------------------------------
# 1. EXTRACTION
# ----------------------------------------------------------------------------
class ExtractedItem(BaseModel):
    idx: int
    is_noise: bool = Field(description="True if not a person describing a concrete problem, frustration, workaround or request for a tool")
    problem_statement: str = Field(description="One sentence, third person, about the JOB they fail to get done (not the product): WHO struggles with WHAT and WHY it hurts. Empty if noise.")
    persona: str = Field(description="Job title or business type. Empty if noise.")
    attack_vector: AttackVector = Field(description=(
        "feature_gap = existing tools do not do X for this segment (attackable niche); "
        "no_solution_exists = they use spreadsheets/manual work/hacks because nothing fits (best); "
        "quality_complaint = a tool does X but badly (bugs, slow, UI, support) - NOT attackable alone; "
        "price_complaint = too expensive / forced upgrade; other."))
    urgency: int = Field(ge=1, le=5, description="1=mild annoyance, 5=actively losing money/customers/hours now")
    frequency: int = Field(ge=1, le=5, description="1=rare edge case, 5=daily/weekly recurring workflow pain")
    mentioned_tools: list[str] = Field(default_factory=list)
    quantified_pain: str = Field(default="", description="e.g. '5 hours/week', '$300/month', '' if none")


class ExtractionResponse(BaseModel):
    items: list[ExtractedItem]


EXTRACT_PROMPT = """You are a market researcher looking for UNMET NEEDS people express online, to find startup opportunities.
For each numbered item (a Reddit/HN post or comment, or a 1-2 star app review), extract a structured record.
Be strict on `is_noise`. Reviews of a product ARE valid signals: describe the JOB the reviewer fails to get done, and classify `attack_vector`
honestly — "the app crashes / is slow / bad support / new UI is worse" is quality_complaint, not an opportunity.
Only call it feature_gap when a concrete capability is missing for a concrete segment; no_solution_exists when they resort to spreadsheets, manual work, VAs or scripts.
Write problem_statement in English, third person, concrete. Return one record per item, same idx.

ITEMS:
{items}
"""


def _fmt_signal(i: int, s: dict) -> str:
    title = (s.get("title") or "").strip()
    text = (s.get("text") or "").strip().replace("\n", " ")
    ctx = f"[{s.get('source')} · {s.get('channel') or ''}" + (f" · rating {s.get('rating')}★" if s.get("rating") else "") + "]"
    body = (f"{title} — " if title and title != text[: len(title)] else "") + text
    return f"{i}. {ctx} {body[:1200]}"


def extract_batch(signals: list[dict]) -> dict[str, dict]:
    items = "\n".join(_fmt_signal(i, s) for i, s in enumerate(signals))
    data = llm_json(EXTRACT_PROMPT.format(items=items), ExtractionResponse)
    out: dict[str, dict] = {}
    for it in data.get("items", []):
        try:
            out[signals[int(it["idx"])]["id"]] = it
        except (KeyError, IndexError, ValueError, TypeError):
            continue
    return out


def process_unprocessed(limit: int | None = None, keyword_set_id: str | None = None) -> dict:
    s = get_settings()
    q = db.get_db().collection(db.RAW_SIGNALS).where("is_processed", "==", False)
    if keyword_set_id:
        q = q.where("keyword_set_id", "==", keyword_set_id)
    pending = [db.doc_to_dict(d) for d in q.limit(limit or 5000).stream()]
    pending.sort(key=lambda x: (x.get("heuristic_score") or 0, x.get("score") or 0), reverse=True)
    processed = noise = 0
    client = db.get_db()
    for chunk in db.chunks(pending, s.llm_batch_size):
        try:
            extracted = extract_batch(chunk)
        except BudgetExhausted as e:
            log.warning("extraction stopped: %s", e)
            break
        except Exception as e:  # noqa: BLE001
            log.error("extraction batch failed: %s", e)
            continue
        batch = client.batch()
        for sig in chunk:
            it = extracted.get(sig["id"])
            if not it:
                continue
            is_noise = bool(it.get("is_noise"))
            noise += is_noise
            batch.update(client.collection(db.RAW_SIGNALS).document(sig["id"]), {
                "is_processed": True,
                "llm_problem_statement": None if is_noise else (it.get("problem_statement") or None),
                "llm_urgency": None if is_noise else it.get("urgency"),
                "llm_frequency": None if is_noise else it.get("frequency"),
                "attack_vector": None if is_noise else it.get("attack_vector"),
                "llm_metadata": {
                    "is_noise": is_noise, "persona": it.get("persona"), "attack_vector": it.get("attack_vector"),
                    "mentioned_tools": it.get("mentioned_tools") or [], "quantified_pain": it.get("quantified_pain") or "",
                    "model": s.llm_model, "processed_at": db.now(),
                },
                "cluster_id": None, "updated_at": db.now(),
            })
            processed += 1
        batch.commit()
    return {"pending": len(pending), "processed": processed, "noise": noise, "calls": budget.calls}


# ----------------------------------------------------------------------------
# 2. CLUSTERING (incremental assignment) + 3. MERGE
# ----------------------------------------------------------------------------
class Assignment(BaseModel):
    idx: int
    cluster: str = Field(description="Existing cluster id (from the list) or 'NEW'")
    new_name: str = Field(default="", description="If NEW: short cluster name (max 8 words), about the job-to-be-done, never a product name")
    new_statement: str = Field(default="", description="If NEW: one-sentence problem statement generalizing this signal")
    relevance: float = Field(ge=0, le=1, default=0.8)


class ClusterResponse(BaseModel):
    assignments: list[Assignment]


CLUSTER_PROMPT = """You group problem statements into clusters. One cluster = one distinct JOB-TO-BE-DONE that a single product could solve for one persona.
Cluster by the underlying job and persona, NOT by the product being complained about: "QuickBooks crashes", "QuickBooks slow", "QuickBooks logs out" are ONE cluster ("accounting app reliability"), not three.
Rules: reuse an existing cluster whenever relevance >= 0.5. Create at most 3 NEW clusters in this batch; if more would be needed, put the rest in the closest existing one with lower relevance.
Vertical: {vertical}.

EXISTING CLUSTERS (id :: name :: statement):
{existing}

NEW SIGNALS (idx :: persona :: attack_vector :: problem statement):
{signals}

Return one assignment per signal idx.
"""


def _processed_unclustered(keyword_set_id: str | None, limit: int) -> list[dict]:
    q = db.get_db().collection(db.RAW_SIGNALS).where("is_processed", "==", True).where("cluster_id", "==", None)
    if keyword_set_id:
        q = q.where("keyword_set_id", "==", keyword_set_id)
    rows = [db.doc_to_dict(d) for d in q.limit(limit).stream()]
    return [r for r in rows if r.get("llm_problem_statement") and not (r.get("llm_metadata") or {}).get("is_noise")]


def _attach(cluster_id: str, sig: dict, relevance: float) -> None:
    client = db.get_db()
    client.collection(db.PROBLEM_CLUSTERS).document(cluster_id).collection(db.CLUSTER_SIGNALS_SUB).document(sig["id"]).set(
        {"relevance": relevance, "attached_at": db.now()})
    client.collection(db.RAW_SIGNALS).document(sig["id"]).update({"cluster_id": cluster_id})


def cluster_pending(keyword_set_id: str | None = None, limit: int = 2000) -> dict:
    ks_map = {k["id"]: k for k in db.list_all(db.KEYWORD_SETS)}
    sets = [keyword_set_id] if keyword_set_id else list(ks_map)
    created = assigned = 0
    for ksid in sets:
        pending = _processed_unclustered(ksid, limit)
        if not pending:
            continue
        vertical = (ks_map.get(ksid) or {}).get("vertical") or "general"
        for chunk in db.chunks(pending, 40):
            existing = db.list_all(db.PROBLEM_CLUSTERS, keyword_set_id=ksid)
            ex_txt = "\n".join(f"{c['id']} :: {c['name']} :: {c.get('problem_statement') or ''}" for c in existing) or "(none yet)"
            sig_txt = "\n".join(
                f"{i} :: {(s.get('llm_metadata') or {}).get('persona') or '?'} :: {s.get('attack_vector') or '?'} :: {s['llm_problem_statement']}"
                for i, s in enumerate(chunk))
            try:
                data = llm_json(CLUSTER_PROMPT.format(vertical=vertical, existing=ex_txt, signals=sig_txt), ClusterResponse)
            except BudgetExhausted as e:
                log.warning("clustering stopped: %s", e)
                return {"created": created, "assigned": assigned, "calls": budget.calls, "stopped": True}
            except Exception as e:  # noqa: BLE001
                log.error("clustering batch failed: %s", e)
                continue
            valid_ids = {c["id"] for c in existing}
            new_by_name: dict[str, str] = {}
            touched: set[str] = set()
            for a in data.get("assignments", []):
                try:
                    sig = chunk[int(a["idx"])]
                except (KeyError, IndexError, ValueError, TypeError):
                    continue
                cid = a.get("cluster")
                if cid not in valid_ids:
                    name = (a.get("new_name") or "").strip() or sig["llm_problem_statement"][:60]
                    key = name.lower()
                    if key not in new_by_name:
                        if len(new_by_name) >= 3 and existing:
                            # over the NEW cap: fall back to the largest existing cluster with low relevance
                            cid = max(existing, key=lambda c: c.get("signal_count") or 0)["id"]
                            _attach(cid, sig, 0.3); touched.add(cid); assigned += 1
                            continue
                        new_by_name[key] = db.upsert(db.PROBLEM_CLUSTERS, None, {
                            "keyword_set_id": ksid, "name": name, "problem_statement": a.get("new_statement") or sig["llm_problem_statement"],
                            "vertical": vertical, "persona": (sig.get("llm_metadata") or {}).get("persona"), "signal_count": 0,
                            "created_by": "llm", "created_at": db.now()})
                        created += 1
                    cid = new_by_name[key]
                _attach(cid, sig, float(a.get("relevance") or 0.8))
                touched.add(cid); assigned += 1
            for cid in touched:
                funnel.refresh_cluster_stats(cid)
                funnel.ensure_opportunity(cid)
    return {"created": created, "assigned": assigned, "calls": budget.calls}


class MergeGroup(BaseModel):
    keep: str = Field(description="cluster id to keep")
    merge: list[str] = Field(description="cluster ids to merge into `keep`")
    name: str = Field(description="final name for the merged cluster (job-to-be-done, no product names)")
    problem_statement: str


class MergeResponse(BaseModel):
    groups: list[MergeGroup]


MERGE_PROMPT = """These clusters were created incrementally and many are duplicates or fragments of the same job-to-be-done.
Propose merges: group clusters that a SINGLE product for a SINGLE persona would address. Be aggressive on fragments of the same
product complaint (reliability/UI/sync/login of the same app = one cluster). Keep genuinely different jobs separate.
Return only groups with at least one merge; clusters not listed stay as they are.

CLUSTERS (id :: signals :: name :: statement):
{clusters}
"""


def merge_into(keep: str, merge_ids: list[str], name: str | None = None, statement: str | None = None) -> int:
    client = db.get_db()
    moved = 0
    keep_sub = client.collection(db.PROBLEM_CLUSTERS).document(keep).collection(db.CLUSTER_SIGNALS_SUB)
    for mid in merge_ids:
        if mid == keep or not db.get(db.PROBLEM_CLUSTERS, mid):
            continue
        sub = client.collection(db.PROBLEM_CLUSTERS).document(mid).collection(db.CLUSTER_SIGNALS_SUB)
        for d in sub.stream():
            keep_sub.document(d.id).set(d.to_dict() or {"relevance": 0.7})
            client.collection(db.RAW_SIGNALS).document(d.id).update({"cluster_id": keep})
            d.reference.delete()
            moved += 1
        db.delete(db.PROBLEM_CLUSTERS, mid)
        db.delete(db.OPPORTUNITY_SCORING, mid)
    upd = {k: v for k, v in {"name": name, "problem_statement": statement}.items() if v}
    if upd:
        db.upsert(db.PROBLEM_CLUSTERS, keep, upd)
    funnel.refresh_cluster_stats(keep)
    return moved


def merge_clusters(keyword_set_id: str | None = None) -> dict:
    sets = [keyword_set_id] if keyword_set_id else [k["id"] for k in db.list_all(db.KEYWORD_SETS)]
    merged = groups = 0
    for ksid in sets:
        clusters = db.list_all(db.PROBLEM_CLUSTERS, keyword_set_id=ksid)
        if len(clusters) < 2:
            continue
        clusters.sort(key=lambda c: -(c.get("signal_count") or 0))
        for chunk in db.chunks(clusters, 60):
            txt = "\n".join(f"{c['id']} :: {c.get('signal_count') or 0} :: {c['name']} :: {(c.get('problem_statement') or '')[:160]}" for c in chunk)
            try:
                data = llm_json(MERGE_PROMPT.format(clusters=txt), MergeResponse)
            except BudgetExhausted as e:
                return {"groups": groups, "merged": merged, "stopped": str(e)}
            except Exception as e:  # noqa: BLE001
                log.error("merge failed: %s", e)
                continue
            ids = {c["id"] for c in chunk}
            used: set[str] = set()
            for g in data.get("groups", []):
                keep = g.get("keep")
                targets = [m for m in (g.get("merge") or []) if m in ids and m != keep and m not in used]
                if keep not in ids or keep in used or not targets:
                    continue
                merged += merge_into(keep, targets, g.get("name"), g.get("problem_statement"))
                used.update(targets); used.add(keep); groups += 1
    return {"groups": groups, "merged_clusters": merged, "calls": budget.calls}


# ----------------------------------------------------------------------------
# 4. CLUSTER ENRICHMENT
# ----------------------------------------------------------------------------
class ScoreResponse(BaseModel):
    name: str
    problem_statement: str
    persona: str
    urgency_score: float = Field(ge=0, le=10)
    frequency_score: float = Field(ge=0, le=10)
    wtp_score: float = Field(ge=0, le=10, description="Willingness to pay: evidence of budget, existing paid tools, quantified losses")
    mom_test_questions: list[str] = Field(description="6-8 open questions about PAST behaviour, never hypotheticals")
    why_now: str = Field(default="", description="Recent change (regulation, tech, platform, behaviour) that opens this window; '' if none evident")
    why_now_source_url: str = Field(default="")


SCORE_PROMPT = """You are validating a startup opportunity. Below is a cluster of online signals describing the same problem.
1. Rewrite `name` (max 8 words, job-to-be-done, no product names) and `problem_statement` (persona + job + current pain).
2. Score 0-10: urgency, frequency, wtp (mentions of paid tools, budgets, quantified losses, DIY effort).
3. Write 6-8 Mom-Test interview questions about the LAST TIME it happened, what they did, what it cost, what they tried. Never "would you use/pay".
4. `why_now`: a recent change making this newly solvable or newly painful. Use the WHY-NOW CANDIDATES below if relevant (cite the URL), else ''.

CLUSTER: {name}
STATEMENT: {statement}
PERSONA: {persona}
ATTACK VECTORS: {attack}
WHY-NOW CANDIDATES (from news scan of this vertical):
{why_now}
SIGNALS ({n} total, sample):
{signals}
"""

MARKET_PROMPT = """Estimate the market for this B2B problem BOTTOM-UP. Use the web search results above (if any) to find real numbers and cite the source URL; otherwise use your best knowledge and mark confidence low.
Problem: {statement}
Persona / buyer: {persona}
Vertical: {vertical}

Return ONLY a JSON object with this exact shape:
{{
  "n_entities":    {{"value": <number of buyer entities worldwide>, "unit": "entities", "source_url": "...", "method": "census|industry_report|proxy|assumption", "confidence": "low|medium|high", "notes": "..."}},
  "annual_spend":  {{"value": <realistic EUR/year one entity would pay for software solving this>, "unit": "EUR/year", "source_url": "...", "method": "competitor_pricing|labor_cost_replaced|assumption", "confidence": "low|medium|high", "notes": "..."}},
  "geo_share":     {{"value": <0-1 share reachable from Europe + English-speaking markets>, "unit": "ratio", "source_url": "", "method": "assumption", "confidence": "low", "notes": "..."}},
  "segment_share": {{"value": <0-1 share of entities that actually have this problem and would adopt software>, "unit": "ratio", "source_url": "", "method": "assumption", "confidence": "low", "notes": "..."}},
  "capture_share": {{"value": <0-1 realistic share a solo founder could win in 3 years, typically 0.002-0.02>, "unit": "ratio", "source_url": "", "method": "assumption", "confidence": "low", "notes": "..."}}
}}
"""

COMPETITOR_PROMPT = """Find existing products that solve (or claim to solve) this problem. Use the web search results above (if any) plus your knowledge of G2, Capterra, Product Hunt.
Problem: {statement}
Persona: {persona}

Return ONLY a JSON object:
{{
  "competitors": [
    {{"name": "...", "url": "...", "tagline": "...", "source": "g2|capterra|producthunt|web", "reviews_count": <int|null>, "rating": <float|null>,
      "pricing_monthly_usd": <number|null>, "founded_year": <int|null>, "funding_usd": <number|null>, "is_dead": <bool>, "notes": "..."}}
  ],
  "leader_reviews": <reviews count of the category leader, or null>,
  "saturation": "blue|purple|red",
  "saturation_notes": "how many credible players, how entrenched, are they solving it well for THIS persona",
  "prior_failed_attempts": "dead/pivoted products in this space and the likely reason, or 'none found'"
}}
Rules: blue = <=4 credible players or only generic/horizontal tools; purple = 5-12 players but a clear underserved segment; red = >12 players or a dominant leader with 500+ reviews solving it well.
"""


class FounderFitResponse(BaseModel):
    founder_fit: int = Field(ge=1, le=5)
    acquisition_channel: str
    acquisition_channel_reachable: bool
    first_20_customers_plan: str = Field(description="Concrete: where exactly to find the first 20 buyers and what to send them")
    barriers: dict[str, bool] = Field(description="keys: regulatory, enterprise_sales, two_sided, capital, technical")
    reasoning: str


FOUNDER_PROMPT = """Assess founder-market fit.
FOUNDER: {profile}
OPPORTUNITY: {statement}
PERSONA / BUYER: {persona}
SATURATION: {saturation} — {saturation_notes}
COMPETITORS: {competitors}

founder_fit 1-5 (5 = this founder can realistically reach the first 20 paying customers alone within 3 months).
"""


def _cluster_signals(cluster_id: str, limit: int = 60) -> list[dict]:
    client = db.get_db()
    sub = client.collection(db.PROBLEM_CLUSTERS).document(cluster_id).collection(db.CLUSTER_SIGNALS_SUB)
    ids = [d.id for d in sub.limit(limit).stream()]
    return [x for x in (db.doc_to_dict(s) for s in client.get_all([client.collection(db.RAW_SIGNALS).document(i) for i in ids])) if x]


def score_cluster(cluster_id: str) -> dict:
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    ks = db.get(db.KEYWORD_SETS, c.get("keyword_set_id") or "") or {}
    sigs = _cluster_signals(cluster_id)
    sample = "\n".join(
        f"- ({s.get('source')}, wtp={s.get('heuristic_score')}, pain='{(s.get('llm_metadata') or {}).get('quantified_pain') or ''}') "
        f"{s.get('llm_problem_statement')} || {(s.get('text') or '')[:300].replace(chr(10), ' ')}" for s in sigs[:30])
    why_now = "\n".join(f"- {w.get('title')}: {w.get('summary')} ({w.get('url')})" for w in (ks.get("why_now_candidates") or [])[:8]) or "(none)"
    data = llm_json(SCORE_PROMPT.format(name=c["name"], statement=c.get("problem_statement"), persona=c.get("persona"),
                                        attack=json.dumps(c.get("attack_vector_dist") or {}), why_now=why_now,
                                        n=c.get("signal_count"), signals=sample), ScoreResponse)
    db.upsert(db.PROBLEM_CLUSTERS, cluster_id, {
        "name": data["name"], "problem_statement": data["problem_statement"], "persona": data["persona"],
        "urgency_score": data["urgency_score"], "frequency_score": data["frequency_score"], "wtp_score": data["wtp_score"],
        "mom_test_questions": data["mom_test_questions"],
        "llm_metadata": {**(c.get("llm_metadata") or {}), "scored_at": db.now(), "model": get_settings().llm_model}})
    if data.get("why_now"):
        db.upsert(db.OPPORTUNITY_SCORING, cluster_id, {"why_now": data["why_now"], "why_now_source_url": data.get("why_now_source_url") or None})
    return data


def estimate_market_components(cluster_id: str) -> dict:
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    data = llm_json(MARKET_PROMPT.format(statement=c.get("problem_statement"), persona=c.get("persona"), vertical=c.get("vertical")),
                    grounded=True, search_queries=[f"number of {c.get('persona')} worldwide statistics",
                                                   f"{c.get('vertical')} software pricing per month {c.get('persona')}"])
    out = {}
    for comp in market.COMPONENTS:
        d = data.get(comp)
        if isinstance(d, dict) and isinstance(d.get("value"), (int, float)):
            out = market.set_component(cluster_id, comp, {k: d.get(k) for k in ("value", "unit", "source_url", "method", "confidence", "notes")}, created_by="llm")
    return out


def find_competitors(cluster_id: str) -> dict:
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    data = llm_json(COMPETITOR_PROMPT.format(statement=c.get("problem_statement"), persona=c.get("persona")),
                    grounded=True, search_queries=[f"best software for {c.get('persona')} {c.get('name')}", f"{c.get('name')} tool G2 Capterra reviews"])
    comps = [x for x in data.get("competitors", []) if isinstance(x, dict) and x.get("name")]
    for x in comps:
        ext = re.sub(r"\W+", "-", x["name"].lower()).strip("-")
        db.upsert(db.COMPETITOR_SIGNALS, db.safe_id("llm", ext), {
            "cluster_id": cluster_id, "keyword_set_id": c.get("keyword_set_id"), "source": x.get("source") or "web", "external_id": ext,
            "name": x["name"], "url": x.get("url"), "tagline": x.get("tagline"), "reviews_count": x.get("reviews_count"), "rating": x.get("rating"),
            "pricing_monthly_usd": x.get("pricing_monthly_usd"), "founded_year": x.get("founded_year"), "funding_usd": x.get("funding_usd"),
            "is_dead": x.get("is_dead"), "notes": x.get("notes"), "captured_at": db.now()})
    sat = data.get("saturation") if data.get("saturation") in ("blue", "purple", "red") else None
    db.upsert(db.OPPORTUNITY_SCORING, cluster_id, {
        "competitor_count": len([x for x in comps if not x.get("is_dead")]), "leader_reviews": data.get("leader_reviews"),
        "dead_products_found": len([x for x in comps if x.get("is_dead")]),
        "saturation": sat, "saturation_notes": data.get("saturation_notes"), "prior_failed_attempts": data.get("prior_failed_attempts")})
    return {"competitors": len(comps), "saturation": sat}


def assess_founder_fit(cluster_id: str) -> dict:
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    o = db.get(db.OPPORTUNITY_SCORING, cluster_id) or {}
    comps = db.list_all(db.COMPETITOR_SIGNALS, cluster_id=cluster_id)
    data = llm_json(FOUNDER_PROMPT.format(profile=FOUNDER_PROFILE, statement=c.get("problem_statement"), persona=c.get("persona"),
                                          saturation=o.get("saturation"), saturation_notes=o.get("saturation_notes"),
                                          competitors=", ".join(x["name"] for x in comps[:12]) or "none found"), FounderFitResponse)
    db.upsert(db.OPPORTUNITY_SCORING, cluster_id, {
        "founder_fit": data["founder_fit"], "acquisition_channel": data["acquisition_channel"],
        "acquisition_channel_reachable": data["acquisition_channel_reachable"], "barriers": data["barriers"],
        "first_20_customers_plan": data["first_20_customers_plan"],
        "notes": ((o.get("notes") or "") + "\n[founder-fit] " + data["reasoning"]).strip()})
    return data


def enrich_cluster(cluster_id: str, force: bool = False) -> dict:
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    if not c:
        return {"error": "not found"}
    if not force and (c.get("llm_metadata") or {}).get("scored_at"):
        return {"skipped": "already enriched"}
    res: dict[str, Any] = {}
    for step, fn in (("score", score_cluster), ("market", estimate_market_components), ("competitors", find_competitors), ("founder_fit", assess_founder_fit)):
        try:
            res[step] = "ok" if fn(cluster_id) else "empty"
        except BudgetExhausted as e:
            res[step] = f"budget: {e}"
            break
        except Exception as e:  # noqa: BLE001
            log.error("enrich %s/%s failed: %s", cluster_id, step, e)
            res[step] = f"error: {type(e).__name__}"
    return res


def enrich_ready_clusters(min_signals: int = 8, max_clusters: int = 8) -> dict:
    """Enrich only clusters worth the calls: enough signals AND an attackable dominant vector."""
    clusters = [c for c in db.list_all(db.PROBLEM_CLUSTERS)
                if (c.get("signal_count") or 0) >= min_signals and not (c.get("llm_metadata") or {}).get("scored_at")
                and (c.get("dominant_attack_vector") in ATTACKABLE)]
    clusters.sort(key=lambda c: (c.get("signal_count") or 0), reverse=True)
    out = {}
    for c in clusters[:max_clusters]:
        if budget.remaining() < 4:
            out[c["id"]] = "budget"
            break
        out[c["id"]] = enrich_cluster(c["id"])
    return out


# ----------------------------------------------------------------------------
# INTERVIEW LOOP
# ----------------------------------------------------------------------------
class InterviewExtract(BaseModel):
    persona: str
    confirmed_problem: bool = Field(description="They described this problem as real for them")
    spontaneous: bool = Field(description="They raised the problem themselves before the interviewer described it")
    currently_paying: bool = Field(description="They currently pay money (tool, person, service) to cope with it")
    current_solution: str
    quantified_cost: str = Field(default="", description="hours/week, EUR/month, lost clients... '' if none")
    quantified_cost_eur_month: float | None = None
    key_quotes: list[str] = Field(description="2-4 verbatim quotes")
    objections: list[str] = Field(default_factory=list)
    would_intro_others: bool = False
    summary: str


INTERVIEW_PROMPT = """Extract structured findings from these customer-interview notes, judged against the problem under validation.
Be conservative: `confirmed_problem` only if they described it happening to them; `spontaneous` only if they raised it before being prompted.

PROBLEM UNDER VALIDATION: {statement}
PERSONA TARGET: {persona}

INTERVIEW NOTES:
{notes}
"""


def ingest_interview_notes(cluster_id: str, notes: str, meta: dict | None = None) -> dict:
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    if not c:
        raise ValueError("cluster not found")
    data = llm_json(INTERVIEW_PROMPT.format(statement=c.get("problem_statement"), persona=c.get("persona"), notes=notes[:12000]), InterviewExtract)
    doc = {**data, **(meta or {}), "notes": notes, "cluster_id": cluster_id, "created_at": db.now()}
    iid = db.new_id()
    db.get_db().collection(db.PROBLEM_CLUSTERS).document(cluster_id).collection("interviews").document(iid).set(doc)
    return {"interview_id": iid, **data, "funnel": funnel.evaluate(cluster_id)}


class RecruitingPack(BaseModel):
    screener_questions: list[dict] = Field(description="5-7 items: {question, type: 'single|multi|text', options: [...], qualifying: '...'} for Respondent/User Interviews")
    reddit_reply: str = Field(description="Public reply to a thread where someone described the problem: honest, no pitch, asks for a 20-min call")
    hn_email: str = Field(description="Short email to an HN author (from profile email)")
    linkedin_message: str = Field(description="Connection note + follow-up, <300 chars each, separated by '---'")
    linkedin_search_query: str = Field(description="Boolean search string for LinkedIn/Sales Navigator to find the persona")
    where_to_find_them: list[str] = Field(description="5-8 concrete places: subreddits, FB groups, associations, forums, events")


RECRUIT_PROMPT = """Create a recruiting pack for customer-discovery interviews (Mom Test style). The founder is a solo founder in Italy with sales background.
PROBLEM: {statement}
PERSONA: {persona}
VERTICAL: {vertical}
MOM TEST QUESTIONS (for context, do not repeat): {questions}
Tone: human, curious, no product pitch, no "would you pay". Messages in English unless the persona is clearly Italian.
"""


def recruiting_pack(cluster_id: str) -> dict:
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    data = llm_json(RECRUIT_PROMPT.format(statement=c.get("problem_statement"), persona=c.get("persona"), vertical=c.get("vertical"),
                                          questions=json.dumps(c.get("mom_test_questions") or [])), RecruitingPack, temperature=0.5)
    db.upsert(db.PROBLEM_CLUSTERS, cluster_id, {"recruiting_pack": {**data, "generated_at": db.now()}})
    return data


# ----------------------------------------------------------------------------
# DISCOVERY: new verticals + why-now scan
# ----------------------------------------------------------------------------
class ProposedSet(BaseModel):
    name: str = Field(description="snake_case, prefix vertical_")
    vertical: str
    rationale: str
    country: str = Field(default="", description="IT, DE, FR, EU, US or ''")
    subreddits: list[str] = Field(default_factory=list)
    hn_queries: list[str] = Field(default_factory=list)
    trend_keywords: list[str] = Field(default_factory=list)
    producthunt_keywords: list[str] = Field(default_factory=list)
    candidate_apps_to_review: list[str] = Field(default_factory=list, description="mid-size vertical SaaS names (not giants) whose 1-star reviews to mine")


class DiscoveryResponse(BaseModel):
    proposals: list[ProposedSet]


DISCOVERY_PROMPT = """You help a solo founder find BLUE-OCEAN B2B verticals: professional/trade segments with recurring workflows, budget, and
software that is either absent or generic. Avoid: tools for founders/developers/marketers (red ocean), consumer apps, enterprise.
Given what we already monitor and what we learned, propose 5 NEW verticals or sub-verticals to monitor, with concrete sources.
Prefer European/Italian angles where a recent regulation or platform change creates a why-now.

ALREADY MONITORED: {existing}
CLUSTERS FOUND SO FAR (name :: vertical :: signals :: attack_vector): {clusters}
GOOGLE TRENDS RISING QUERIES: {rising}
"""


def discover_verticals() -> dict:
    sets = db.list_all(db.KEYWORD_SETS)
    clusters = sorted(db.list_all(db.PROBLEM_CLUSTERS), key=lambda c: -(c.get("signal_count") or 0))[:25]
    rising: list[str] = []
    for t in db.list_all(db.TREND_SNAPSHOTS, limit=100):
        for r in ((t.get("related_queries") or {}).get("rising") or [])[:5]:
            if isinstance(r, dict) and r.get("query"):
                rising.append(r["query"])
    data = llm_json(DISCOVERY_PROMPT.format(
        existing=", ".join(f"{k['name']} ({k.get('vertical')})" for k in sets),
        clusters="; ".join(f"{c['name']} :: {c.get('vertical')} :: {c.get('signal_count')} :: {c.get('dominant_attack_vector')}" for c in clusters),
        rising=", ".join(dict.fromkeys(rising))[:1500] or "(none)"), DiscoveryResponse, temperature=0.6)
    existing_names = {k["name"] for k in sets}
    created = []
    for p in data.get("proposals", []):
        if p["name"] in existing_names:
            continue
        sources: dict[str, Any] = {}
        if p.get("subreddits"):
            sources["reddit"] = {"subreddits": p["subreddits"], "sorts": ["new", "top"], "time_filter": "month"}
        if p.get("hn_queries"):
            sources["hackernews"] = {"queries": p["hn_queries"]}
        if p.get("trend_keywords"):
            sources["trends"] = {"keywords": p["trend_keywords"][:4] + ["crm software"], "geo": "", "timeframe": "today 12-m"}
        if p.get("producthunt_keywords"):
            sources["producthunt"] = {"topics": ["saas"], "keywords": p["producthunt_keywords"]}
        db.upsert(db.KEYWORD_SETS, None, {
            "name": p["name"], "vertical": p["vertical"], "country": p.get("country") or "", "description": p["rationale"],
            "is_active": False, "proposed_by": "llm", "candidate_apps_to_review": p.get("candidate_apps_to_review") or [],
            "keywords": [], "sources": sources, "created_at": db.now()})
        created.append(p["name"])
    return {"proposed": created, "calls": budget.calls}


class WhyNowItem(BaseModel):
    title: str
    summary: str
    url: str
    kind: Literal["regulation", "platform_change", "technology", "market_shift", "other"]
    relevance: float = Field(ge=0, le=1)


class WhyNowResponse(BaseModel):
    items: list[WhyNowItem]


WHY_NOW_PROMPT = """From the news snippets above, extract concrete recent CHANGES that create a new, time-bound need for {persona} in the "{vertical}" vertical:
regulation deadlines (e-invoicing mandates, compliance), platform/API changes, price hikes or shutdowns of incumbents, new technology. Ignore generic trend pieces.
Return up to 6 items with URL.
"""


def _rss_context(feeds: list[str], max_items: int = 12) -> str:
    """Titles + summaries from vertical newsletters/blogs (RSS/Atom), for the why-now scan."""
    import xml.etree.ElementTree as ET

    from app.scrapers.base import http_client

    out = []
    with http_client(timeout=15) as client:
        for url in feeds:
            try:
                r = client.get(url)
                r.raise_for_status()
                root = ET.fromstring(r.content)
                items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
                for it in items[:max_items]:
                    title = (it.findtext("title") or it.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
                    desc = (it.findtext("description") or it.findtext("{http://www.w3.org/2005/Atom}summary") or "")
                    link = (it.findtext("link") or "").strip() or (it.find("{http://www.w3.org/2005/Atom}link").get("href") if it.find("{http://www.w3.org/2005/Atom}link") is not None else "")
                    out.append(f"- {title}: {re.sub(r'<[^>]+>', ' ', desc)[:300].strip()} ({link})")
            except Exception as e:  # noqa: BLE001
                log.warning("rss %s failed: %s", url, e)
    return "\n".join(out)


def scan_why_now(keyword_set_id: str) -> dict:
    ks = db.get(db.KEYWORD_SETS, keyword_set_id)
    v = ks.get("vertical") or ks["name"]
    persona = ks.get("description") or v
    feeds = ((ks.get("sources") or {}).get("rss") or {}).get("feeds") or []
    ctx = "\n".join(x for x in (
        web_search(f"{v} new regulation 2026 deadline small business software", 6, topic="news", days=120),
        web_search(f"{v} software price increase OR discontinued OR shutting down 2026", 5, topic="news", days=120),
        _rss_context(feeds) if feeds else "",
    ) if x)
    if not ctx:
        return {"items": 0, "reason": "no search results / no TAVILY_API_KEY"}
    data = llm_json(f"NEWS SNIPPETS:\n{ctx}\n\n" + WHY_NOW_PROMPT.format(persona=persona, vertical=v), WhyNowResponse)
    items = [i for i in data.get("items", []) if i.get("relevance", 0) >= 0.5]
    db.upsert(db.KEYWORD_SETS, keyword_set_id, {"why_now_candidates": items, "why_now_scanned_at": db.now()})
    return {"items": len(items)}


# ----------------------------------------------------------------------------
# FULL RUN
# ----------------------------------------------------------------------------
def run_full_analysis(keyword_set_id: str | None = None, extract_limit: int | None = None, send_notifications: bool = True) -> dict:
    budget.reset()
    res: dict[str, Any] = {}
    try:
        res["extract"] = process_unprocessed(limit=extract_limit, keyword_set_id=keyword_set_id)
        res["cluster"] = cluster_pending(keyword_set_id)
        res["merge"] = merge_clusters(keyword_set_id)
        res["enrich"] = enrich_ready_clusters()
    except BudgetExhausted as e:
        res["stopped"] = str(e)
    res["funnel"] = funnel.evaluate_all(send_notifications)
    res["llm_calls"] = budget.calls
    return res
