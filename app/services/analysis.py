"""
=============================================================================
 FASE 2 — SEMANTIC LAYER (any OpenAI-compatible LLM: Mistral / Groq free tier)
=============================================================================

Pipeline (each step re-runnable, idempotent):

 1. process_unprocessed()      raw_signals (is_processed=False) -> batches of N -> LLM JSON
                               -> llm_problem_statement, llm_urgency, llm_frequency, llm_metadata{persona, is_noise, tools, pain}
 2. cluster_pending()          non-noise processed signals not yet in a cluster -> LLM sees existing
                               clusters + new statements -> assigns or creates -> problem_clusters/{id}/signals
 3. enrich_cluster(id)         for clusters with enough signals and no enrichment yet:
                               scoring (urgency/frequency/wtp 0-10) + Mom Test questions + persona,
                               market components (Tavily web search if configured), competitors, founder fit
 4. funnel.evaluate_all()      advance stages + email

Free-tier budgeting: LLM_MAX_CALLS_PER_RUN caps calls per run; LLM_RPM throttles.
Market sizing / competitor search use Tavily web search when TAVILY_API_KEY is set.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app import db
from app.config import get_settings
from app.services import funnel, market

log = logging.getLogger("analysis")

FOUNDER_PROFILE = (
    "Solo founder, background in digital marketing and B2B sales, can build web products alone "
    "(FastAPI / Next.js / Firebase), NO network, NO capital for paid acquisition beyond a few hundred euros. "
    "Reachable channels: LinkedIn/email outbound, SEO/content, vertical communities (Reddit, Facebook groups), "
    "partnerships with trade associations. Penalize: enterprise sales cycles, heavy regulation, "
    "two-sided marketplaces, capital-intensive or hardware businesses."
)


# ----------------------------------------------------------------------------
# LLM client (OpenAI-compatible: Mistral / Groq / OpenRouter ...) + budget + optional web search
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


def web_search(query: str, max_results: int = 6) -> str:
    """Tavily (free tier) -> compact text context for the LLM. Returns '' if no key / failure."""
    key = get_settings().tavily_api_key
    if not key:
        return ""
    try:
        from tavily import TavilyClient

        res = TavilyClient(api_key=key).search(query, max_results=max_results, search_depth="basic")
        return "\n".join(f"- {r.get('title')}: {(r.get('content') or '')[:400]} ({r.get('url')})" for r in res.get("results", []))
    except Exception as e:  # noqa: BLE001
        log.warning("tavily search failed: %s", e)
        return ""


@retry(retry=retry_if_exception_type(RateLimited), stop=stop_after_attempt(5), wait=wait_exponential(multiplier=5, min=5, max=60))
def llm_json(prompt: str, schema: type[BaseModel] | None = None, grounded: bool = False, temperature: float = 0.2,
             search_queries: list[str] | None = None) -> Any:
    """
    One chat call returning parsed JSON (json_object mode). If `schema` is given the JSON schema is
    appended to the prompt and the result validated. `search_queries` -> Tavily snippets prepended as context.
    """
    from openai import APIStatusError, RateLimitError

    context = ""
    if grounded and search_queries:
        snippets = [web_search(q) for q in search_queries]
        joined = "\n".join(x for x in snippets if x)
        if joined:
            context = f"WEB SEARCH RESULTS (use these, cite URLs; if insufficient say so in notes):\n{joined}\n\n"
    schema_txt = ""
    if schema is not None:
        schema_txt = f"\n\nRespond with a single JSON object matching this JSON Schema exactly:\n{json.dumps(schema.model_json_schema())}"
    budget.tick()
    try:
        resp = _llm().chat.completions.create(
            model=get_settings().llm_model,
            temperature=temperature,
            response_format={"type": "json_object"},
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
    is_noise: bool = Field(description="True if not a real unmet need / complaint (spam, meta, off-topic, praise, generic chatter)")
    problem_statement: str = Field(description="One sentence, third person, specific: WHO struggles with WHAT and WHY it hurts. Empty if noise.")
    persona: str = Field(description="Who has the problem: job title or business type. Empty if noise.")
    urgency: int = Field(ge=1, le=5, description="1=mild annoyance, 5=actively losing money/customers/hours now")
    frequency: int = Field(ge=1, le=5, description="1=rare edge case, 5=daily/weekly recurring workflow pain")
    mentioned_tools: list[str] = Field(default_factory=list)
    quantified_pain: str = Field(default="", description="e.g. '5 hours/week', '$300/month', '' if none")


class ExtractionResponse(BaseModel):
    items: list[ExtractedItem]


EXTRACT_PROMPT = """You are a market researcher looking for UNMET NEEDS people express online, to find startup opportunities.
For each numbered item below (a Reddit/HN post or comment, or a 1-2 star app review), extract a structured record.
Be strict on `is_noise`: mark as noise anything that is not a person describing a concrete problem, frustration, workaround or request for a tool.
Reviews complaining about a specific product ARE valid signals (problem = the job the product fails to do), unless purely emotional with no substance.
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
    """Returns {signal_id: extracted dict}."""
    items = "\n".join(_fmt_signal(i, s) for i, s in enumerate(signals))
    data = llm_json(EXTRACT_PROMPT.format(items=items), ExtractionResponse)
    out: dict[str, dict] = {}
    for it in data.get("items", []):
        try:
            idx = int(it["idx"])
            out[signals[idx]["id"]] = it
        except (KeyError, IndexError, ValueError, TypeError):
            continue
    return out


def process_unprocessed(limit: int | None = None, keyword_set_id: str | None = None) -> dict:
    """Extract problems from raw_signals where is_processed == False. Stops when the budget is exhausted."""
    s = get_settings()
    q = db.get_db().collection(db.RAW_SIGNALS).where("is_processed", "==", False)
    if keyword_set_id:
        q = q.where("keyword_set_id", "==", keyword_set_id)
    pending = [db.doc_to_dict(d) for d in q.limit(limit or 5000).stream()]
    # highest heuristic score first: spend the free quota on the most promising signals
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
            batch.update(
                client.collection(db.RAW_SIGNALS).document(sig["id"]),
                {
                    "is_processed": True,
                    "llm_problem_statement": None if is_noise else (it.get("problem_statement") or None),
                    "llm_urgency": None if is_noise else it.get("urgency"),
                    "llm_frequency": None if is_noise else it.get("frequency"),
                    "llm_metadata": {
                        "is_noise": is_noise, "persona": it.get("persona"), "mentioned_tools": it.get("mentioned_tools") or [],
                        "quantified_pain": it.get("quantified_pain") or "", "model": s.llm_model, "processed_at": db.now(),
                    },
                    "cluster_id": None,
                    "updated_at": db.now(),
                },
            )
            processed += 1
        batch.commit()
    return {"pending": len(pending), "processed": processed, "noise": noise, "calls": budget.calls}


# ----------------------------------------------------------------------------
# 2. CLUSTERING (incremental assignment)
# ----------------------------------------------------------------------------
class Assignment(BaseModel):
    idx: int
    cluster: str = Field(description="Existing cluster id (from the list) or 'NEW'")
    new_name: str = Field(default="", description="If NEW: short cluster name (max 8 words)")
    new_statement: str = Field(default="", description="If NEW: one-sentence problem statement generalizing this signal")
    relevance: float = Field(ge=0, le=1, default=0.8)


class ClusterResponse(BaseModel):
    assignments: list[Assignment]


CLUSTER_PROMPT = """You group problem statements into clusters, where one cluster = one distinct underlying PROBLEM that a single product could solve for a specific PERSONA.
Two statements belong together if the same solution would relieve both. Keep clusters specific (not "small business admin is hard").
Do NOT create a new cluster if an existing one fits (relevance >= 0.6). Prefer reusing. Vertical context: {vertical}.

EXISTING CLUSTERS (id :: name :: statement):
{existing}

NEW SIGNALS (idx :: persona :: problem statement):
{signals}

Return one assignment per signal idx.
"""


def _processed_unclustered(keyword_set_id: str | None, limit: int) -> list[dict]:
    q = db.get_db().collection(db.RAW_SIGNALS).where("is_processed", "==", True).where("cluster_id", "==", None)
    if keyword_set_id:
        q = q.where("keyword_set_id", "==", keyword_set_id)
    rows = [db.doc_to_dict(d) for d in q.limit(limit).stream()]
    return [r for r in rows if r.get("llm_problem_statement") and not (r.get("llm_metadata") or {}).get("is_noise")]


def cluster_pending(keyword_set_id: str | None = None, limit: int = 2000) -> dict:
    ks_map = {k["id"]: k for k in db.list_all(db.KEYWORD_SETS)}
    sets = [keyword_set_id] if keyword_set_id else list(ks_map)
    created = assigned = 0
    client = db.get_db()
    for ksid in sets:
        pending = _processed_unclustered(ksid, limit)
        if not pending:
            continue
        vertical = (ks_map.get(ksid) or {}).get("vertical") or "general"
        for chunk in db.chunks(pending, 40):
            existing = db.list_all(db.PROBLEM_CLUSTERS, keyword_set_id=ksid)
            ex_txt = "\n".join(f"{c['id']} :: {c['name']} :: {c.get('problem_statement') or ''}" for c in existing) or "(none yet)"
            sig_txt = "\n".join(
                f"{i} :: {(s.get('llm_metadata') or {}).get('persona') or '?'} :: {s['llm_problem_statement']}" for i, s in enumerate(chunk)
            )
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
                        new_by_name[key] = db.upsert(
                            db.PROBLEM_CLUSTERS, None,
                            {"keyword_set_id": ksid, "name": name, "problem_statement": a.get("new_statement") or sig["llm_problem_statement"],
                             "vertical": vertical, "persona": (sig.get("llm_metadata") or {}).get("persona"), "signal_count": 0,
                             "created_by": "llm", "created_at": db.now()},
                        )
                        created += 1
                    cid = new_by_name[key]
                sub = client.collection(db.PROBLEM_CLUSTERS).document(cid).collection(db.CLUSTER_SIGNALS_SUB)
                sub.document(sig["id"]).set({"relevance": float(a.get("relevance") or 0.8), "attached_at": db.now()})
                client.collection(db.RAW_SIGNALS).document(sig["id"]).update({"cluster_id": cid})
                touched.add(cid)
                assigned += 1
            for cid in touched:
                funnel.refresh_cluster_stats(cid)
                funnel.ensure_opportunity(cid)
    return {"created": created, "assigned": assigned, "calls": budget.calls}


# ----------------------------------------------------------------------------
# 3. CLUSTER ENRICHMENT
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


SCORE_PROMPT = """You are validating a startup opportunity. Below is a cluster of online signals describing the same problem.
1. Rewrite `name` (max 8 words) and `problem_statement` (one precise sentence: persona + job-to-be-done + current pain).
2. Score 0-10: urgency (how acute), frequency (how often it recurs), wtp (willingness to pay: mentions of paid tools, budgets, quantified losses, DIY effort).
3. Write 6-8 Mom-Test interview questions: ask about the LAST TIME it happened, what they did, what it cost, what they tried, who else was involved. Never ask "would you use/pay".
4. If the signals hint at a recent change that makes this problem newly solvable or newly painful, describe it in `why_now`.

CLUSTER: {name}
STATEMENT: {statement}
PERSONA: {persona}
SIGNALS ({n} total, sample):
{signals}
"""

MARKET_PROMPT = """Estimate the market for this B2B problem using a BOTTOM-UP method. Use the web search results above (if any) to find real numbers and cite the source URL for each; otherwise use your best knowledge and mark confidence low.
Problem: {statement}
Persona / buyer: {persona}
Vertical: {vertical}

Return ONLY a JSON object with this exact shape (no prose):
{{
  "n_entities":    {{"value": <number of buyer entities worldwide (businesses/practices/professionals)>, "unit": "entities", "source_url": "...", "method": "census|industry_report|proxy|assumption", "confidence": "low|medium|high", "notes": "..."}},
  "annual_spend":  {{"value": <realistic EUR/year one entity would pay for a software solving this>, "unit": "EUR/year", "source_url": "...", "method": "competitor_pricing|labor_cost_replaced|assumption", "confidence": "low|medium|high", "notes": "..."}},
  "geo_share":     {{"value": <0-1 share reachable from Europe/US English-speaking>, "unit": "ratio", "source_url": "", "method": "assumption", "confidence": "low", "notes": "..."}},
  "segment_share": {{"value": <0-1 share of entities that actually have this problem and would adopt software>, "unit": "ratio", "source_url": "", "method": "assumption", "confidence": "low", "notes": "..."}},
  "capture_share": {{"value": <0-1 realistic share a solo founder could win in 3 years, typically 0.002-0.02>, "unit": "ratio", "source_url": "", "method": "assumption", "confidence": "low", "notes": "..."}}
}}
"""

COMPETITOR_PROMPT = """Find existing products that solve (or claim to solve) this problem. Use the web search results above (if any) plus your knowledge of G2, Capterra, Product Hunt.
Problem: {statement}
Persona: {persona}

Return ONLY a JSON object (no prose):
{{
  "competitors": [
    {{"name": "...", "url": "...", "tagline": "...", "source": "g2|capterra|producthunt|web", "reviews_count": <int or null>, "rating": <float or null>,
      "pricing_monthly_usd": <number or null>, "founded_year": <int or null>, "funding_usd": <number or null>, "is_dead": <bool>, "notes": "..."}}
  ],
  "leader_reviews": <reviews count of the category leader, or null>,
  "saturation": "blue|purple|red",
  "saturation_notes": "why: how many credible players, how entrenched, are they solving it well, any dead products (prior failed attempts) and why they died",
  "prior_failed_attempts": "..."
}}
Rules: blue = <=4 credible players or all incumbents are generic/horizontal tools; purple = 5-12 players but clear underserved segment; red = >12 players or a dominant leader with 500+ reviews solving it well.
"""


class FounderFitResponse(BaseModel):
    founder_fit: int = Field(ge=1, le=5)
    acquisition_channel: str
    acquisition_channel_reachable: bool
    barriers: dict[str, bool] = Field(description="keys: regulatory, enterprise_sales, two_sided, capital, technical")
    reasoning: str


FOUNDER_PROMPT = """Assess founder-market fit for this opportunity.
FOUNDER: {profile}
OPPORTUNITY: {statement}
PERSONA / BUYER: {persona}
SATURATION: {saturation} — {saturation_notes}
COMPETITORS: {competitors}

Return founder_fit 1-5 (5 = this founder can realistically reach the first 20 paying customers alone within 3 months),
the single best acquisition channel and whether it is reachable for this founder, and the barriers map.
"""


def score_cluster(cluster_id: str) -> dict:
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    client = db.get_db()
    sub = client.collection(db.PROBLEM_CLUSTERS).document(cluster_id).collection(db.CLUSTER_SIGNALS_SUB)
    ids = [d.id for d in sub.limit(60).stream()]
    sigs = [x for x in (db.doc_to_dict(s) for s in client.get_all([client.collection(db.RAW_SIGNALS).document(i) for i in ids])) if x]
    sample = "\n".join(
        f"- ({s.get('source')}, wtp={s.get('heuristic_score')}, pain='{(s.get('llm_metadata') or {}).get('quantified_pain') or ''}') "
        f"{s.get('llm_problem_statement')} || {(s.get('text') or '')[:300].replace(chr(10), ' ')}"
        for s in sigs[:30]
    )
    data = llm_json(SCORE_PROMPT.format(name=c["name"], statement=c.get("problem_statement"), persona=c.get("persona"), n=c.get("signal_count"), signals=sample), ScoreResponse)
    db.upsert(db.PROBLEM_CLUSTERS, cluster_id, {
        "name": data["name"], "problem_statement": data["problem_statement"], "persona": data["persona"],
        "urgency_score": data["urgency_score"], "frequency_score": data["frequency_score"], "wtp_score": data["wtp_score"],
        "mom_test_questions": data["mom_test_questions"], "llm_metadata": {**(c.get("llm_metadata") or {}), "scored_at": db.now(), "model": get_settings().llm_model},
    })
    if data.get("why_now"):
        db.upsert(db.OPPORTUNITY_SCORING, cluster_id, {"why_now": data["why_now"]})
    return data


def estimate_market_components(cluster_id: str) -> dict:
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    data = llm_json(
        MARKET_PROMPT.format(statement=c.get("problem_statement"), persona=c.get("persona"), vertical=c.get("vertical")),
        grounded=True,
        search_queries=[f"number of {c.get('persona')} worldwide statistics", f"{c.get('vertical')} software pricing per month {c.get('persona')}"],
    )
    out = {}
    for comp in market.COMPONENTS:
        d = data.get(comp)
        if isinstance(d, dict) and isinstance(d.get("value"), (int, float)):
            out = market.set_component(cluster_id, comp, {k: d.get(k) for k in ("value", "unit", "source_url", "method", "confidence", "notes")}, created_by="llm")
    return out


def find_competitors(cluster_id: str) -> dict:
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    data = llm_json(
        COMPETITOR_PROMPT.format(statement=c.get("problem_statement"), persona=c.get("persona")),
        grounded=True,
        search_queries=[f"best software for {c.get('persona')} {c.get('name')}", f"{c.get('name')} tool G2 Capterra reviews"],
    )
    comps = [x for x in data.get("competitors", []) if isinstance(x, dict) and x.get("name")]
    for x in comps:
        ext = re.sub(r"\W+", "-", x["name"].lower()).strip("-")
        db.upsert(db.COMPETITOR_SIGNALS, db.safe_id("llm", ext), {
            "cluster_id": cluster_id, "keyword_set_id": c.get("keyword_set_id"), "source": x.get("source") or "web", "external_id": ext,
            "name": x["name"], "url": x.get("url"), "tagline": x.get("tagline"), "reviews_count": x.get("reviews_count"), "rating": x.get("rating"),
            "pricing_monthly_usd": x.get("pricing_monthly_usd"), "founded_year": x.get("founded_year"), "funding_usd": x.get("funding_usd"),
            "is_dead": x.get("is_dead"), "notes": x.get("notes"), "captured_at": db.now(),
        })
    sat = data.get("saturation") if data.get("saturation") in ("blue", "purple", "red") else None
    db.upsert(db.OPPORTUNITY_SCORING, cluster_id, {
        "competitor_count": len([x for x in comps if not x.get("is_dead")]), "leader_reviews": data.get("leader_reviews"),
        "saturation": sat, "saturation_notes": data.get("saturation_notes"), "prior_failed_attempts": data.get("prior_failed_attempts"),
    })
    return {"competitors": len(comps), "saturation": sat}


def assess_founder_fit(cluster_id: str) -> dict:
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    o = db.get(db.OPPORTUNITY_SCORING, cluster_id) or {}
    comps = db.list_all(db.COMPETITOR_SIGNALS, cluster_id=cluster_id)
    data = llm_json(FOUNDER_PROMPT.format(
        profile=FOUNDER_PROFILE, statement=c.get("problem_statement"), persona=c.get("persona"),
        saturation=o.get("saturation"), saturation_notes=o.get("saturation_notes"),
        competitors=", ".join(x["name"] for x in comps[:12]) or "none found",
    ), FounderFitResponse)
    db.upsert(db.OPPORTUNITY_SCORING, cluster_id, {
        "founder_fit": data["founder_fit"], "acquisition_channel": data["acquisition_channel"],
        "acquisition_channel_reachable": data["acquisition_channel_reachable"], "barriers": data["barriers"],
        "notes": ((o.get("notes") or "") + "\n[founder-fit] " + data["reasoning"]).strip(),
    })
    return data


def enrich_cluster(cluster_id: str, force: bool = False) -> dict:
    """Score + market + competitors + founder fit (4 calls). Skipped if already enriched unless force."""
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    if not c:
        return {"error": "not found"}
    if not force and (c.get("llm_metadata") or {}).get("scored_at"):
        return {"skipped": "already enriched"}
    res: dict[str, Any] = {}
    for step, fn in (("score", score_cluster), ("market", estimate_market_components), ("competitors", find_competitors), ("founder_fit", assess_founder_fit)):
        try:
            r = fn(cluster_id)
            res[step] = "ok" if r else "empty"
        except BudgetExhausted as e:
            res[step] = f"budget: {e}"
            break
        except Exception as e:  # noqa: BLE001
            log.error("enrich %s/%s failed: %s", cluster_id, step, e)
            res[step] = f"error: {type(e).__name__}"
    return res


def enrich_ready_clusters(min_signals: int = 5, max_clusters: int = 10) -> dict:
    """Enrich the biggest un-enriched clusters first (4 LLM calls each)."""
    clusters = [c for c in db.list_all(db.PROBLEM_CLUSTERS) if (c.get("signal_count") or 0) >= min_signals and not (c.get("llm_metadata") or {}).get("scored_at")]
    clusters.sort(key=lambda c: (c.get("signal_count") or 0), reverse=True)
    out = {}
    for c in clusters[:max_clusters]:
        if budget.remaining() < 4:
            out[c["id"]] = "budget"
            break
        out[c["id"]] = enrich_cluster(c["id"])
    return out


# ----------------------------------------------------------------------------
# 4. FULL RUN
# ----------------------------------------------------------------------------
def run_full_analysis(keyword_set_id: str | None = None, extract_limit: int | None = None, send_notifications: bool = True) -> dict:
    budget.reset()
    res: dict[str, Any] = {}
    try:
        res["extract"] = process_unprocessed(limit=extract_limit, keyword_set_id=keyword_set_id)
        res["cluster"] = cluster_pending(keyword_set_id)
        res["enrich"] = enrich_ready_clusters()
    except BudgetExhausted as e:
        res["stopped"] = str(e)
    res["funnel"] = funnel.evaluate_all(send_notifications)
    res["llm_calls"] = budget.calls
    return res
