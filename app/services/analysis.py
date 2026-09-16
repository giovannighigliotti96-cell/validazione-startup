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
    "Founder based in Italy (small team possible; with today's tools team size is not a constraint), background in digital marketing and B2B sales, builds web products "
    "(FastAPI / Next.js / Firebase), NO capital for paid acquisition beyond a few hundred euros. Speaks Italian and English. "
    "DOMAIN EDGE: certified ski instructor (maestro di sci) with years inside the sports-professional world (ski schools, "
    "instructors, coaches, guides, clubs, mountain resorts) and a real network there; already built AND sold a marketplace "
    "connecting sports professionals with customers (~10 years ago). In SPORTS verticals founder fit is structurally high: "
    "he can reach instructors, ski schools, clubs and facility managers directly. Outside sports he has no network. "
    "Reachable channels: personal sports network, LinkedIn/email outbound, SEO/content, vertical communities, trade associations. "
    "Reaching the FIRST 20 paying customers quickly matters more than total market size. "
    "Penalize: enterprise sales cycles, heavy regulation, capital-intensive or hardware businesses. Two-sided marketplaces: "
    "he has done one before, so the barrier is lower than for most, but the economics rule still applies (both sides must be reachable and cheap)."
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
_clients: dict[str, Any] = {}


def _tier(strong: bool) -> tuple[str, str, str, int]:
    """(base_url, api_key, model, rpm) for the requested tier; falls back to the cheap tier if strong is not configured."""
    s = get_settings()
    if strong and s.llm_strong_api_key and s.llm_strong_model:
        return (s.llm_strong_base_url or s.llm_base_url, s.llm_strong_api_key, s.llm_strong_model, s.llm_strong_rpm)
    if not s.llm_api_key:
        raise RuntimeError("LLM_API_KEY not set")
    return (s.llm_base_url, s.llm_api_key, s.llm_model, s.llm_rpm)


def _llm(strong: bool = False):
    from openai import OpenAI

    base, key, model, _ = _tier(strong)
    if base not in _clients:
        _clients[base] = OpenAI(api_key=key, base_url=base)
    return _clients[base], model


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
             search_queries: list[str] | None = None, strong: bool = False) -> Any:
    """strong=True routes to LLM_STRONG_* (e.g. gpt-oss-120b on Groq) — use for the few calls that decide."""
    from openai import APIStatusError, RateLimitError

    context = ""
    if grounded and search_queries:
        joined = "\n".join(x for x in (web_search(q) for q in search_queries) if x)
        if joined:
            context = f"WEB SEARCH RESULTS (use these, cite URLs; if insufficient say so in notes):\n{joined}\n\n"
    schema_txt = f"\n\nRespond with a single JSON object matching this JSON Schema exactly:\n{json.dumps(schema.model_json_schema())}" if schema else ""
    budget.tick()
    client, model = _llm(strong)
    messages = [
        {"role": "system", "content": "You are a precise analyst. Output ONLY valid JSON, no prose, no markdown fences."},
        {"role": "user", "content": context + prompt + schema_txt},
    ]

    def _call(json_mode: bool):
        # Groq free tier counts max_tokens toward an 8k TPM limit: keep the strong tier's output budget small
        kw: dict[str, Any] = {"model": model, "temperature": temperature, "max_tokens": 4000 if strong else 8000, "messages": messages}
        if "gpt-oss" in model:  # reasoning models: keep the hidden reasoning short so the answer fits the budget
            kw["extra_body"] = {"reasoning_effort": "low"}
        if json_mode:
            kw["response_format"] = {"type": "json_object"}
        return client.chat.completions.create(**kw)

    try:
        try:
            resp = _call(True)
        except APIStatusError as e:
            # Groq's server-side JSON validation rejects long/complex outputs: retry in free-text mode and parse ourselves
            if e.status_code == 400 and "json" in str(e).lower():
                budget.tick()
                resp = _call(False)
            else:
                raise
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
        data = _validate_lenient(schema, data)
    return data


def _validate_lenient(schema: type[BaseModel], data: Any) -> dict:
    """
    Small models produce one bad item per batch. Validate list fields item by item and drop the bad ones
    instead of failing the whole call; fall back to strict validation for scalar-only schemas.
    """
    from pydantic import ValidationError

    try:
        return schema.model_validate(data).model_dump()
    except ValidationError as first_err:
        if not isinstance(data, dict):
            raise
        fields = schema.model_fields
        cleaned = dict(data)
        for name, f in fields.items():
            ann = f.annotation
            args = getattr(ann, "__args__", ())
            if getattr(ann, "__origin__", None) is list and args and isinstance(args[0], type) and issubclass(args[0], BaseModel):
                item_model, good = args[0], []
                for it in (data.get(name) or []):
                    try:
                        good.append(item_model.model_validate(_coerce_item(item_model, it)).model_dump())
                    except ValidationError:
                        continue
                cleaned[name] = good
        try:
            return schema.model_validate(cleaned).model_dump()
        except ValidationError:
            # scalar schema (e.g. FounderFitResponse): coerce common slips then retry once
            try:
                return schema.model_validate(_coerce_item(schema, cleaned)).model_dump()
            except ValidationError:
                raise first_err


def _coerce_item(model: type[BaseModel], it: Any) -> Any:
    """Fix the usual 8B slips: attack_vector synonyms, bools as strings, ints as strings, missing lists."""
    if not isinstance(it, dict):
        return it
    it = dict(it)
    av = it.get("attack_vector")
    if isinstance(av, str) and av not in ("feature_gap", "no_solution_exists", "quality_complaint", "price_complaint", "other"):
        a = av.lower()
        it["attack_vector"] = ("no_solution_exists" if "no_solution" in a or "manual" in a or "spreadsheet" in a
                               else "feature_gap" if "gap" in a or "missing" in a
                               else "price_complaint" if "price" in a or "cost" in a
                               else "quality_complaint" if "quality" in a or "bug" in a or "complaint" in a else "other")
    for k, f in model.model_fields.items():
        v = it.get(k)
        if f.annotation is bool and isinstance(v, str):
            it[k] = v.strip().lower() in ("true", "yes", "1")
        elif f.annotation is int and isinstance(v, str) and v.strip().lstrip("-").isdigit():
            it[k] = int(v)
        elif f.annotation is float and isinstance(v, str):
            try:
                it[k] = float(v)
            except ValueError:
                pass
        elif getattr(f.annotation, "__origin__", None) is list and v is None:
            it[k] = []
        elif f.annotation is str and v is None:
            it[k] = ""
    if "barriers" in model.model_fields and isinstance(it.get("barriers"), dict):
        it["barriers"] = {k: (str(v).lower() in ("true", "yes", "1") if not isinstance(v, bool) else v) for k, v in it["barriers"].items()}
    return it


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
    evidence_span: str = Field(default="", description="VERBATIM excerpt (10-160 chars, copied exactly from the item text) that proves the problem. Empty if noise.")
    persona_in_vertical: bool = Field(default=True, description="False if the person clearly belongs to a different industry than the VERTICAL given (e.g. a clothing reseller in a restaurant set)")


class ExtractionResponse(BaseModel):
    items: list[ExtractedItem]


EXTRACT_PROMPT = """You are a market researcher looking for UNMET NEEDS people express online, to find startup opportunities.
VERTICAL BEING RESEARCHED: {vertical}. Only people who plausibly belong to this vertical count: if the writer is clearly from another
industry (a clothing reseller, a film crew, a generic Excel tutorial viewer), set persona_in_vertical=false and is_noise=true.
NEVER relabel someone's persona to fit the vertical: the persona must be what the text shows.
For each numbered item (a Reddit/HN post or comment, or a 1-2 star app review), extract a structured record.
Be strict on `is_noise`. Reviews of a product ARE valid signals: describe the JOB the reviewer fails to get done, and classify `attack_vector`
honestly — "the app crashes / is slow / bad support / new UI is worse" is quality_complaint, not an opportunity.
Only call it feature_gap when a concrete capability is missing for a concrete segment; no_solution_exists when they resort to spreadsheets, manual work, VAs or scripts.
Write problem_statement in English, third person, concrete. Return one record per item, same idx.
GROUNDING: for every non-noise item copy `evidence_span` EXACTLY from the item text (a substring). It will be checked mechanically:
if the span is not found in the text, the item is discarded as invented. Texts that are mostly page navigation, ads, or off-topic are noise.

ITEMS:
{items}
"""


_NEG_CACHE: dict[str, Any] = {"at": 0.0, "text": ""}


def founder_negative_examples(max_items: int = 12) -> str:
    """The founder's archive reasons become negative examples for extraction/clustering (cached 1h)."""
    if time.time() - _NEG_CACHE["at"] < 3600:
        return _NEG_CACHE["text"]
    reasons = []
    clusters = {c["id"]: c for c in db.list_all(db.PROBLEM_CLUSTERS)}
    for o in db.list_all(db.OPPORTUNITY_SCORING):
        if o.get("is_archived") and o.get("archive_reason") and o["cluster_id"] in clusters:
            reasons.append(f"- \"{clusters[o['cluster_id']].get('name')}\": {o['archive_reason'][:160]}")
    txt = ("\nTHE FOUNDER HAS REJECTED clusters like these (treat similar signals as noise or classify conservatively):\n" + "\n".join(reasons[-max_items:]) + "\n") if reasons else ""
    _NEG_CACHE.update(at=time.time(), text=txt)
    return txt


def _fmt_signal(i: int, s: dict) -> str:
    title = (s.get("title") or "").strip()
    text = (s.get("text") or "").strip().replace("\n", " ")
    ctx = f"[{s.get('source')} · {s.get('channel') or ''}" + (f" · rating {s.get('rating')}★" if s.get("rating") else "") + "]"
    body = (f"{title} — " if title and title != text[: len(title)] else "") + text
    return f"{i}. {ctx} {body[:1200]}"


def extract_batch(signals: list[dict], vertical: str = "general") -> dict[str, dict]:
    items = "\n".join(_fmt_signal(i, s) for i, s in enumerate(signals))
    data = llm_json(EXTRACT_PROMPT.format(items=items, vertical=vertical) + founder_negative_examples(), ExtractionResponse)
    out: dict[str, dict] = {}
    for it in data.get("items", []):
        try:
            sig = signals[int(it["idx"])]
        except (KeyError, IndexError, ValueError, TypeError):
            continue
        if not it.get("is_noise") and it.get("persona_in_vertical") is False:
            it = {**it, "is_noise": True, "noise_reason": "persona outside vertical"}
        if not it.get("is_noise"):
            # REAL, NOT INVENTED: the evidence must literally exist in the text
            span = re.sub(r"\s+", " ", (it.get("evidence_span") or "")).strip().lower()
            hay = re.sub(r"\s+", " ", f"{sig.get('title') or ''} {sig.get('text') or ''}").lower()
            if len(span) < 10 or span[:80] not in hay:
                it = {**it, "is_noise": True, "noise_reason": "evidence_span not found in text"}
        out[sig["id"]] = it
    return out


def process_unprocessed(limit: int | None = None, keyword_set_id: str | None = None) -> dict:
    s = get_settings()
    q = db.get_db().collection(db.RAW_SIGNALS).where("is_processed", "==", False)
    if keyword_set_id:
        q = q.where("keyword_set_id", "==", keyword_set_id)
    pending = [db.doc_to_dict(d) for d in q.limit(limit or 5000).stream()]
    ks_vert = {k["id"]: (k.get("vertical") or k.get("name") or "general") for k in db.list_all(db.KEYWORD_SETS)}
    # group by keyword set so every batch carries its vertical (persona-in-vertical check)
    pending.sort(key=lambda x: (x.get("keyword_set_id") or "", -(x.get("heuristic_score") or 0), -(x.get("score") or 0)))
    processed = noise = 0
    client = db.get_db()
    batches = []
    cur: list[dict] = []
    for sig in pending:
        if cur and (sig.get("keyword_set_id") != cur[0].get("keyword_set_id") or len(cur) >= s.llm_batch_size):
            batches.append(cur); cur = []
        cur.append(sig)
    if cur:
        batches.append(cur)
    for chunk in batches:
        try:
            extracted = extract_batch(chunk, vertical=ks_vert.get(chunk[0].get("keyword_set_id"), "general"))
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
                    "is_noise": is_noise, "noise_reason": it.get("noise_reason"), "evidence_span": it.get("evidence_span"),
                    "persona": it.get("persona"), "attack_vector": it.get("attack_vector"),
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
Rules: reuse an existing cluster whenever relevance >= 0.5. Create at most {new_cap} NEW clusters in this batch; if more would be needed, put the rest in the closest existing one with lower relevance.
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


def cluster_pending(keyword_set_id: str | None = None, limit: int = 2000, max_passes: int = 4) -> dict:
    """Several passes per run: each batch may create at most NEW_CAP clusters, so sets starting from zero need a few rounds."""
    ks_map = {k["id"]: k for k in db.list_all(db.KEYWORD_SETS)}
    sets = [keyword_set_id] if keyword_set_id else list(ks_map)
    created = assigned = 0
    for ksid in sets:
      for _pass in range(max_passes):
        pending = _processed_unclustered(ksid, limit)
        if not pending:
            break
        before = assigned
        vertical = (ks_map.get(ksid) or {}).get("vertical") or "general"
        for chunk in db.chunks(pending, 40):
            existing = db.list_all(db.PROBLEM_CLUSTERS, keyword_set_id=ksid)
            ex_txt = "\n".join(f"{c['id']} :: {c['name']} :: {c.get('problem_statement') or ''}" for c in existing) or "(none yet)"
            sig_txt = "\n".join(
                f"{i} :: {(s.get('llm_metadata') or {}).get('persona') or '?'} :: {s.get('attack_vector') or '?'} :: {s['llm_problem_statement']}"
                for i, s in enumerate(chunk))
            try:
                data = llm_json(CLUSTER_PROMPT.format(vertical=vertical, existing=ex_txt, signals=sig_txt, new_cap=(6 if len(existing) < 10 else 3)), ClusterResponse)
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
                        if len(new_by_name) >= (6 if len(existing) < 10 else 3):
                            continue  # over the NEW cap: leave unassigned, next pass re-tries with more clusters in context
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
        if assigned == before:
            break  # nothing new assigned in this pass: stop
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
        # never merge split children (deliberately narrow) nor parents that have children
        parents = {c.get("parent_cluster_id") for c in clusters if c.get("parent_cluster_id")}
        clusters = [c for c in clusters if not c.get("parent_cluster_id") and c["id"] not in parents]
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
    problem_statement: str = Field(description="ONLY what the quoted signals support. No inferred pains, no invented personas, no extrapolation to other segments.")
    grounded: bool = Field(description="True only if every claim in problem_statement is directly supported by at least one quoted signal")
    unsupported_claims_removed: list[str] = Field(default_factory=list, description="Claims you dropped because no signal supports them")
    persona: str
    urgency_score: float = Field(ge=0, le=10)
    frequency_score: float = Field(ge=0, le=10)
    wtp_score: float = Field(ge=0, le=10, description="Willingness to pay: evidence of budget, existing paid tools, quantified losses")
    mom_test_questions: list[str] = Field(description="6-8 open questions about PAST behaviour, never hypotheticals")
    why_now: str = Field(default="", description="Recent change (regulation, tech, platform, behaviour) that opens this window; '' if none evident")
    why_now_source_url: str = Field(default="")


SCORE_PROMPT = """You are validating a startup opportunity. Below is a cluster of online signals describing the same problem.
RULE ZERO — real, not invented: the problem_statement may contain ONLY claims that the quoted signals literally support. If the signals come
from dentists, do not say "healthcare practices". If nobody mentions cost, do not say "expensive". List every claim you had to drop.
1. Rewrite `name` (max 8 words, job-to-be-done, no product names) and `problem_statement` (persona + job + current pain, grounded).
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

COMPETITOR_PROMPT = """Find existing products that solve (or claim to solve) this problem. Use ONLY the web search results above plus products you are CERTAIN exist
(every URL will be verified; invented products disqualify the analysis). Cover BOTH the US/global landscape (G2, Capterra, Product Hunt)
AND the European one (Capterra.it/.de/.fr, Appvizer, OMR Reviews, GetApp): say explicitly whether a localized EU/Italian player exists.
Problem: {statement}
Persona: {persona}
Vertical: {vertical}

Return ONLY a JSON object:
{{
  "competitors": [
    {{"name": "...", "url": "...", "tagline": "...", "source": "g2|capterra|producthunt|web", "reviews_count": <int|null>, "rating": <float|null>,
      "pricing_monthly_usd": <number|null>, "founded_year": <int|null>, "funding_usd": <number|null>, "is_dead": <bool>, "notes": "..."}}
  ],
  "leader_reviews": <reviews count of the category leader, or null>,
  "eu_localized_player_exists": <bool>,
  "eu_landscape_notes": "which EU/IT/DE/FR players exist (or none) and how well they cover this persona",
  "saturation": "blue|purple|red",
  "saturation_notes": "how many credible players, how entrenched, are they solving it well for THIS persona",
  "prior_failed_attempts": "dead/pivoted products in this space and the likely reason, or 'none found'"
}}
Rules: blue = <=4 credible players or only generic/horizontal tools; purple = 5-12 players but a clear underserved segment; red = >12 players or a dominant leader with 500+ reviews solving it well.
"""


class FounderFitResponse(BaseModel):
    founder_fit: int = Field(ge=1, le=5)
    acquisition_channel: str
    acquisition_channel_type: Literal["outbound", "self_serve_marketplace", "seo_content", "community", "partnerships"] = Field(
        description="outbound = LinkedIn/email/calls by the founder; self_serve_marketplace = app store / marketplace listing; seo_content; community; partnerships")
    acquisition_channel_reachable: bool
    first_20_customers_plan: str = Field(description="Concrete: where exactly to find the first 20 buyers and what to send them")
    barriers: dict[str, bool] = Field(description="keys: regulatory, enterprise_sales, two_sided, capital, technical")
    # --- economics: a blue ocean without margin is not a business ---
    expected_price_eur_month: float = Field(description="Realistic price per customer per month in EUR, anchored to verified competitor pricing and the persona's budget")
    delivery_model: Literal["self_serve_software", "sales_assisted_software", "service_heavy"] = Field(
        description="service_heavy = humans must do work per customer (onboarding, manual processing, support) -> low margin")
    gross_margin_pct: float = Field(ge=0, le=1, description="Expected gross margin after hosting, LLM/API costs, payment fees, per-customer human work. Pure software 0.75-0.9; service-heavy 0.2-0.5")
    buyer_persona: str = Field(description="Who signs the payment (may differ from who has the pain)")
    buyer_is_user: bool
    mvp_weeks_solo: int = Field(description="Weeks for this founder alone to ship a sellable MVP")
    analogues: list[dict] = Field(default_factory=list, description=(
        "1-3 REAL startups that solved a closely analogous problem (same persona type or same job): "
        "{name, url, how_they_found_the_problem, first_customers_channel, bootstrapped: bool, outcome}. Only companies you are certain exist."))
    reasoning: str


FOUNDER_PROMPT = """Assess founder-market fit.
FOUNDER: {profile}
OPPORTUNITY: {statement}
PERSONA / BUYER: {persona}
SATURATION: {saturation} — {saturation_notes}
COMPETITORS: {competitors}

founder_fit 1-5 (5 = this founder can realistically reach the first 20 paying customers alone within 3 months).
Also name 1-3 real analogous startups (vertical SaaS that started from a similar job/persona) and how they got their first customers:
the founder compares every opportunity against real precedents (e.g. Cliniko, Jane App, Jobber, ConvertKit, Fatture in Cloud).
Be sober on economics: if the persona pays < 50 EUR/month and the only channel is founder outbound, the model does not work.
If delivering value requires recurring human work per customer, say so (service_heavy) and lower the margin accordingly.
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
                                        n=c.get("signal_count"), signals=sample), ScoreResponse, strong=True)
    db.upsert(db.PROBLEM_CLUSTERS, cluster_id, {
        "name": data["name"], "problem_statement": data["problem_statement"], "persona": data["persona"],
        "grounded": data.get("grounded"), "unsupported_claims_removed": data.get("unsupported_claims_removed") or [],
        "urgency_score": data["urgency_score"], "frequency_score": data["frequency_score"], "wtp_score": data["wtp_score"],
        "mom_test_questions": data["mom_test_questions"],
        "llm_metadata": {**(c.get("llm_metadata") or {}), "scored_at": db.now(), "model": get_settings().llm_model}})
    if data.get("why_now"):
        db.upsert(db.OPPORTUNITY_SCORING, cluster_id, {"why_now": data["why_now"], "why_now_source_url": data.get("why_now_source_url") or None})
    return data


def estimate_market_components(cluster_id: str) -> dict:
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    data = llm_json(MARKET_PROMPT.format(statement=c.get("problem_statement"), persona=c.get("persona"), vertical=c.get("vertical")),
                    grounded=True, strong=True, search_queries=[f"number of {c.get('persona')} worldwide statistics",
                                                                f"number of {c.get('persona')} in Europe Italy Germany France",
                                                                f"{c.get('vertical')} software pricing per month {c.get('persona')}"])
    out = {}
    for comp in market.COMPONENTS:
        d = data.get(comp)
        if isinstance(d, dict) and isinstance(d.get("value"), (int, float)):
            out = market.set_component(cluster_id, comp, {k: d.get(k) for k in ("value", "unit", "source_url", "method", "confidence", "notes")}, created_by="llm")
    return out


def verify_url(url: str | None) -> bool:
    """Anti-hallucination: a competitor only counts if its website answers. HEAD then GET, 8s, any 2xx/3xx."""
    if not url or not url.startswith("http"):
        return False
    from app.scrapers.base import http_client

    try:
        with http_client(timeout=8) as client:
            r = client.head(url)
            if r.status_code >= 400 or r.status_code == 405:
                r = client.get(url)
            # 401/403/429/5xx = the site exists but blocks bots; only "not found" means hallucinated
            return r.status_code not in (404, 410)
    except Exception:  # noqa: BLE001
        # DNS failure / connection refused -> does not exist; a timeout on a real host is ambiguous -> retry the bare domain
        try:
            from urllib.parse import urlparse

            host = urlparse(url).netloc
            with http_client(timeout=8) as client:
                return client.get(f"https://{host}/").status_code not in (404, 410)
        except Exception:  # noqa: BLE001
            return False


_SAT_RANK = {"blue": 0, "purple": 1, "red": 2}


def find_competitors(cluster_id: str, passes: int = 2) -> dict:
    """
    Two independent grounded passes with different search angles; competitors are unioned (after URL verification)
    and the saturation verdict is the MOST SEVERE of the passes. A single-call verdict flips between runs — a sniper
    needs the conservative one.
    """
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    persona, name, stmt = c.get("persona") or "", c.get("name") or "", c.get("problem_statement") or ""
    angles = [
        [f"best software for {persona} {name}", f"site:capterra.com {name} software",
         f"site:capterra.it OR site:capterra.de OR site:capterra.fr {name}", f"{name} software pricing per month"],
        [f"{stmt[:80]} tool", f"{persona} {name} alternatives comparison 2026",
         f"site:appvizer.com OR site:omr.com/reviews OR site:getapp.com {name}", f"{name} app reviews G2"],
    ]
    data: dict[str, Any] = {"competitors": []}
    for i in range(max(1, passes)):
        d = llm_json(COMPETITOR_PROMPT.format(statement=stmt, persona=persona, vertical=c.get("vertical")),
                     grounded=True, strong=True, search_queries=angles[i % len(angles)])
        data["competitors"] += [x for x in d.get("competitors", []) if isinstance(x, dict) and x.get("name")]
        for k in ("leader_reviews",):
            if isinstance(d.get(k), (int, float)) and (data.get(k) is None or d[k] > data[k]):
                data[k] = d[k]
        if _SAT_RANK.get(d.get("saturation"), -1) > _SAT_RANK.get(data.get("saturation"), -1):
            data["saturation"] = d["saturation"]
            data["saturation_notes"] = d.get("saturation_notes")
        data["eu_localized_player_exists"] = bool(data.get("eu_localized_player_exists")) or bool(d.get("eu_localized_player_exists"))
        for k in ("eu_landscape_notes", "prior_failed_attempts"):
            data[k] = " | ".join(x for x in (data.get(k), d.get(k)) if x)
    # dedupe by normalized name
    seen: dict[str, dict] = {}
    for x in data["competitors"]:
        key = re.sub(r"\W+", "", x["name"].lower())
        if key not in seen or (x.get("pricing_monthly_usd") and not seen[key].get("pricing_monthly_usd")):
            seen[key] = x
    comps = list(seen.values())
    verified, rejected = [], []
    for x in comps:
        (verified if verify_url(x.get("url")) else rejected).append(x)
    if rejected:
        log.warning("competitors rejected (URL not reachable / hallucinated): %s", [r.get("name") for r in rejected])
    comps = verified
    for x in comps:
        ext = re.sub(r"\W+", "-", x["name"].lower()).strip("-")
        db.upsert(db.COMPETITOR_SIGNALS, db.safe_id("llm", ext), {
            "cluster_id": cluster_id, "keyword_set_id": c.get("keyword_set_id"), "source": x.get("source") or "web", "external_id": ext,
            "name": x["name"], "url": x.get("url"), "tagline": x.get("tagline"), "reviews_count": x.get("reviews_count"), "rating": x.get("rating"),
            "pricing_monthly_usd": x.get("pricing_monthly_usd"), "founded_year": x.get("founded_year"), "funding_usd": x.get("funding_usd"),
            "is_dead": x.get("is_dead"), "notes": x.get("notes"), "captured_at": db.now()})
    sat = data.get("saturation") if data.get("saturation") in ("blue", "purple", "red") else None
    # if the model hallucinated most of its list, its saturation verdict is not trustworthy either
    trust = (len(comps) / len(verified + rejected)) if (verified or rejected) else 1.0
    if trust < 0.5:
        sat = None
    db.upsert(db.OPPORTUNITY_SCORING, cluster_id, {
        "competitor_count": len([x for x in comps if not x.get("is_dead")]), "leader_reviews": data.get("leader_reviews"),
        "dead_products_found": len([x for x in comps if x.get("is_dead")]),
        "competitors_rejected": [r.get("name") for r in rejected], "competitor_trust": round(trust, 2),
        "eu_localized_player_exists": data.get("eu_localized_player_exists"), "eu_landscape_notes": data.get("eu_landscape_notes"),
        "saturation": sat, "saturation_notes": data.get("saturation_notes"), "prior_failed_attempts": data.get("prior_failed_attempts")})
    prices = [float(x["pricing_monthly_usd"]) for x in comps if isinstance(x.get("pricing_monthly_usd"), (int, float)) and x["pricing_monthly_usd"] > 0]
    if prices:
        opp = db.get(db.OPPORTUNITY_SCORING, cluster_id) or {}
        cur = (opp.get("market_estimates") or {}).get("annual_spend") or {}
        if cur.get("method") in (None, "assumption") or cur.get("confidence") == "low":
            med = sorted(prices)[len(prices) // 2]
            market.set_component(cluster_id, "annual_spend", {
                "value": round(med * 12 * 0.92), "unit": "EUR/year", "method": "competitor_pricing", "confidence": "medium",
                "source_url": next((x.get("url") for x in comps if x.get("pricing_monthly_usd")), None),
                "notes": f"median of {len(prices)} verified competitor monthly prices x12 (USD->EUR ~0.92)"}, created_by="llm")
    return {"competitors": len(comps), "rejected": len(rejected), "saturation": sat, "pricing_points": len(prices)}


def assess_founder_fit(cluster_id: str) -> dict:
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    o = db.get(db.OPPORTUNITY_SCORING, cluster_id) or {}
    comps = db.list_all(db.COMPETITOR_SIGNALS, cluster_id=cluster_id)
    data = llm_json(FOUNDER_PROMPT.format(profile=FOUNDER_PROFILE, statement=c.get("problem_statement"), persona=c.get("persona"),
                                          saturation=o.get("saturation"), saturation_notes=o.get("saturation_notes"),
                                          competitors=", ".join(x["name"] for x in comps[:12]) or "none found"), FounderFitResponse, strong=True)
    db.upsert(db.OPPORTUNITY_SCORING, cluster_id, {
        "founder_fit": data["founder_fit"], "acquisition_channel": data["acquisition_channel"],
        "acquisition_channel_type": data.get("acquisition_channel_type"),
        "acquisition_channel_reachable": data["acquisition_channel_reachable"], "barriers": data["barriers"],
        "first_20_customers_plan": data["first_20_customers_plan"],
        "expected_price_eur_month": data.get("expected_price_eur_month"), "delivery_model": data.get("delivery_model"),
        "gross_margin_pct": data.get("gross_margin_pct"), "buyer_persona": data.get("buyer_persona"), "buyer_is_user": data.get("buyer_is_user"),
        "mvp_weeks_solo": data.get("mvp_weeks_solo"),
        "analogues": [a for a in (data.get("analogues") or []) if isinstance(a, dict) and a.get("name") and verify_url(a.get("url"))],
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


def enrich_ready_clusters(max_clusters: int = 8) -> dict:
    """Enrich only clusters that already satisfy the stage-2 (problem_clustered) criteria: no calls wasted on noise."""
    stages = {st["key"]: st for st in funnel.get_stages()}
    stage2 = stages.get("problem_clustered") or {"criteria": {}}
    clusters = []
    for c in db.list_all(db.PROBLEM_CLUSTERS):
        if (c.get("llm_metadata") or {}).get("scored_at"):
            continue
        opp = db.get(db.OPPORTUNITY_SCORING, c["id"]) or {}
        if opp.get("path") == "execution_gap":
            continue
        ok, _ = funnel.check_stage(stage2, funnel.collect_metrics(c, opp))
        if ok:
            clusters.append(c)
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
    data = llm_json(INTERVIEW_PROMPT.format(statement=c.get("problem_statement"), persona=c.get("persona"), notes=notes[:12000]), InterviewExtract, strong=True)
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
                                          questions=json.dumps(c.get("mom_test_questions") or [])), RecruitingPack, temperature=0.5, strong=True)
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


THESES = (
    "ACTIVE MARKET THESES (from YC RFS S26, read for Italy/EU): "
    "(1) AI-native SERVICE companies: sell the outcome, not software, in already-outsourced services (accounting/tax, payroll consultants, "
    "condominium administration, sports-club compliance under the Riforma dello Sport, insurance brokerage, healthcare/driving-school paperwork); "
    "(2) SaaS challengers: replace legacy vertical software (desktop, 2000s) at 1/10 the price with an AI-native workflow; "
    "(3) small-business 'company brain': turning the owner's tacit know-how into executable procedures. "
    "Prefer verticals where one of these theses applies, but only ever propose sources; clusters come from real signals."
)

DISCOVERY_PROMPT = """You help a founder find BLUE-OCEAN B2B verticals: professional/trade segments with recurring workflows, budget, and
software that is either absent or generic. Avoid: tools for founders/developers/marketers (red ocean), consumer apps, enterprise.
Given what we already monitor and what we learned, propose 5 NEW verticals or sub-verticals to monitor, with concrete sources.
Prefer European/Italian angles where a recent regulation or platform change creates a why-now.
STRICT RULES: only name subreddits, forums, products and regulations that you are CERTAIN exist (they will be verified; invented names
disqualify the proposal). If unsure, leave the list empty. Use the web search results above to ground regulation names and dates.

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
    # fresh thesis context: a16z feed + YC RFS page (titles only; theses orient search, never create clusters)
    thesis_ctx = ""
    try:
        a16z = _rss_context(["https://a16z.com/feed/"], max_items=15)
        yc = web_search("site:ycombinator.com/rfs requests for startups", 3)
        thesis_ctx = ("\nRECENT INVESTOR THESES (a16z feed, YC RFS) for orientation only:\n" + a16z[:1500] + "\n" + yc[:800]) if (a16z or yc) else ""
    except Exception as e:  # noqa: BLE001
        log.info("thesis context skipped: %s", e)
    data = llm_json(DISCOVERY_PROMPT.format(
        existing=", ".join(f"{k['name']} ({k.get('vertical')})" for k in sets),
        clusters="; ".join(f"{c['name']} :: {c.get('vertical')} :: {c.get('signal_count')} :: {c.get('dominant_attack_vector')}" for c in clusters),
        rising=", ".join(dict.fromkeys(rising))[:1500] or "(none)") + "\n" + THESES + thesis_ctx, DiscoveryResponse, temperature=0.4,
        grounded=True, strong=True, search_queries=["new EU regulation 2026 small business compliance deadline software",
                                       "underserved vertical SaaS niches 2026 small business trades professionals"])
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
        # subreddits are NOT verified until the Reddit API is live: keep them aside, not in `sources`
        unverified = {"subreddits": p.get("subreddits") or [], "apps": p.get("candidate_apps_to_review") or []}
        sources.pop("reddit", None)
        # auto-activate only with sources that cannot be hallucinated into existence (queries, not names): youtube + reddit_search + trends
        if p.get("hn_queries") or p.get("trend_keywords"):
            sources["reddit_search"] = {"queries": (p.get("hn_queries") or [])[:3], "subreddits": [], "days": 365, "max_results": 8}
            sources["youtube"] = {"queries": (p.get("hn_queries") or p.get("trend_keywords") or [])[:3], "videos_per_query": 3}
        auto = bool(sources.get("youtube") or sources.get("reddit_search"))
        db.upsert(db.KEYWORD_SETS, None, {
            "name": p["name"], "vertical": p["vertical"], "country": p.get("country") or "", "description": p["rationale"],
            "is_active": auto, "proposed_by": "llm", "unverified": unverified,
            "review_note": "auto-activated with query-based sources only (subreddits/apps unverified, kept aside)" if auto else "LLM proposal: verify before activating",
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
        res["expand"] = expand_queries()
        res["cross_vertical"] = cross_vertical_merge()
        res["enrich"] = enrich_ready_clusters()
        from app.services import execution_gap as _eg

        res["execution_gap"] = _eg.run_all(min_signals=30, max_clusters=2)  # second path, budgeted
    except BudgetExhausted as e:
        res["stopped"] = str(e)
    res["funnel"] = funnel.evaluate_all(send_notifications)
    res["llm_calls"] = budget.calls
    return res


# ----------------------------------------------------------------------------
# SPLIT: a broad cluster ("run the store") -> narrow jobs-to-be-done, each evaluated on its own
# ----------------------------------------------------------------------------
class SubCluster(BaseModel):
    name: str = Field(description="max 8 words, one specific job-to-be-done")
    problem_statement: str
    persona: str


class SplitResponse(BaseModel):
    subclusters: list[SubCluster]


SPLIT_PROMPT = """This cluster is too broad: it bundles several distinct jobs-to-be-done. Propose 3-7 NARROW sub-clusters,
each one a single job that ONE focused product could solve for ONE persona (e.g. "reconcile B2B net-30 wholesale orders", not "store operations").
Base them on the signals below; prefer specificity. Do NOT assign signals, just define the sub-clusters.

PARENT: {name} :: {statement}
SIGNALS (attack_vector :: statement):
{signals}
"""

ASSIGN_PROMPT = """Assign each signal to exactly one of the sub-clusters below (by id). If none fits well, use "{other}".

SUB-CLUSTERS (id :: name :: statement):
{existing}

SIGNALS (idx :: statement):
{signals}

Return one assignment per signal idx.
"""


def split_cluster(cluster_id: str, min_signals: int = 3) -> dict:
    """
    Broad parent -> narrow children. Step 1 (strong model): define 3-7 sub-clusters. Step 2 (cheap model, batches):
    assign every signal. Children with < min_signals are dissolved; the parent is archived (kept for history).
    """
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    sigs = [s for s in _cluster_signals(cluster_id, limit=300) if s.get("llm_problem_statement")]
    if len(sigs) < 6:
        return {"error": "too few signals to split"}
    sample = "\n".join(f"- {(s.get('attack_vector') or '?')[:12]} :: {s['llm_problem_statement'][:120]}" for s in sigs[:60])
    data = llm_json(SPLIT_PROMPT.format(name=c["name"], statement=c.get("problem_statement"), signals=sample), SplitResponse, strong=True)
    children: dict[str, dict] = {}
    for sc in data.get("subclusters", []):
        cid = db.upsert(db.PROBLEM_CLUSTERS, None, {
            "keyword_set_id": c.get("keyword_set_id"), "vertical": c.get("vertical"), "name": sc["name"],
            "problem_statement": sc["problem_statement"], "persona": sc["persona"], "parent_cluster_id": cluster_id,
            "signal_count": 0, "created_by": "llm_split", "created_at": db.now()})
        children[cid] = {"id": cid, "name": sc["name"], "signals": 0}
    if not children:
        return {"error": "no sub-clusters proposed"}
    other_id = "OTHER"
    ex_txt = "\n".join(f"{cid} :: {ch['name']} :: {db.get(db.PROBLEM_CLUSTERS, cid).get('problem_statement')}" for cid, ch in children.items())
    for chunk in db.chunks(sigs, 30):
        sig_txt = "\n".join(f"{i} :: {s['llm_problem_statement'][:200]}" for i, s in enumerate(chunk))
        try:
            a = llm_json(ASSIGN_PROMPT.format(other=other_id, existing=ex_txt, signals=sig_txt), ClusterResponse)
        except Exception as e:  # noqa: BLE001
            log.error("split assignment failed: %s", e)
            continue
        for it in a.get("assignments", []):
            try:
                sig = chunk[int(it["idx"])]
            except (KeyError, IndexError, ValueError, TypeError):
                continue
            cid = it.get("cluster")
            if cid in children:
                _attach(cid, sig, float(it.get("relevance") or 0.8))
                children[cid]["signals"] += 1
    kept = []
    for cid, ch in children.items():
        if ch["signals"] < min_signals:
            for d in db.get_db().collection(db.PROBLEM_CLUSTERS).document(cid).collection(db.CLUSTER_SIGNALS_SUB).stream():
                db.get_db().collection(db.RAW_SIGNALS).document(d.id).update({"cluster_id": cluster_id}); d.reference.delete()
            db.delete(db.PROBLEM_CLUSTERS, cid); db.delete(db.OPPORTUNITY_SCORING, cid)
            continue
        funnel.refresh_cluster_stats(cid)
        funnel.ensure_opportunity(cid)
        kept.append(ch)
    covered = sum(ch["signals"] for ch in kept)
    if kept and covered >= 0.5 * len(sigs):
        db.upsert(db.OPPORTUNITY_SCORING, cluster_id, {"is_archived": True, "archive_reason": f"split into {len(kept)} narrower sub-clusters"})
    else:
        # children cover a minority: the parent keeps accumulating; children compete on their own
        db.upsert(db.PROBLEM_CLUSTERS, cluster_id, {"split_note": f"{len(kept)} sub-clusters cover {covered}/{len(sigs)} signals; parent kept active"})
    funnel.refresh_cluster_stats(cluster_id)
    return {"parent": c["name"], "children": kept, "covered": covered, "total": len(sigs), "calls": budget.calls}


# ----------------------------------------------------------------------------
# (1) QUERY EXPANSION — follow the scent: real clusters -> new queries in the persona's own words
# ----------------------------------------------------------------------------
class QueryExpansion(BaseModel):
    reddit_search: list[str] = Field(description="3-5 search queries as the persona would phrase the pain (no product names unless they used them)")
    youtube: list[str] = Field(description="2-3 tutorial/vlog-style queries whose comments would contain this pain")
    trends: list[str] = Field(default_factory=list, description="0-2 Google Trends keywords")


EXPAND_PROMPT = """A real problem cluster emerged from these verbatim signals. Write new search queries to find MORE people expressing the SAME pain,
using their vocabulary (copy words from the quotes). Do not broaden to other personas or adjacent problems.

CLUSTER: {name} :: {statement}
PERSONA: {persona} · VERTICAL: {vertical}
VERBATIM QUOTES:
{quotes}
EXISTING QUERIES (do not repeat): {existing}
"""


def expand_queries(min_signals: int = 5, max_clusters: int = 10) -> dict:
    """For each attackable cluster with >= min_signals not yet expanded: add cluster-derived queries to its keyword set."""
    done = []
    clusters = [c for c in db.list_all(db.PROBLEM_CLUSTERS)
                if (c.get("signal_count") or 0) >= min_signals and c.get("dominant_attack_vector") in ATTACKABLE
                and not c.get("queries_expanded_at") and c.get("keyword_set_id") and c.get("vertical") != "founders"]
    clusters.sort(key=lambda c: -(c.get("signal_count") or 0))
    for c in clusters[:max_clusters]:
        ks = db.get(db.KEYWORD_SETS, c["keyword_set_id"])
        if not ks:
            continue
        src = dict(ks.get("sources") or {})
        existing = (src.get("reddit_search", {}).get("queries") or []) + (src.get("youtube", {}).get("queries") or [])
        quotes = "\n".join(f"- \"{q['quote']}\"" for q in (c.get("evidence_quotes") or [])[:6]) or "(none)"
        try:
            data = llm_json(EXPAND_PROMPT.format(name=c["name"], statement=c.get("problem_statement"), persona=c.get("persona"),
                                                 vertical=c.get("vertical"), quotes=quotes, existing=", ".join(existing)[:800]), QueryExpansion, strong=True)
        except BudgetExhausted:
            break
        except Exception as e:  # noqa: BLE001
            log.error("expand_queries failed for %s: %s", c["name"], e)
            continue
        rs = src.setdefault("reddit_search", {"queries": [], "subreddits": (src.get("reddit", {}).get("subreddits") or [])[:3], "days": 365, "max_results": 8})
        rs["queries"] = list(dict.fromkeys((rs.get("queries") or []) + data.get("reddit_search", [])))[:12]
        yt = src.setdefault("youtube", {"queries": [], "videos_per_query": 4})
        yt["queries"] = list(dict.fromkeys((yt.get("queries") or []) + data.get("youtube", [])))[:10]
        if data.get("trends"):
            tr = src.setdefault("trends", {"keywords": ["crm software"], "geo": "", "timeframe": "today 12-m"})
            tr["keywords"] = list(dict.fromkeys((tr.get("keywords") or []) + data["trends"]))[:5]
        db.upsert(db.KEYWORD_SETS, ks["id"], {"sources": src, "expanded_from": list(dict.fromkeys((ks.get("expanded_from") or []) + [c["id"]]))})
        db.upsert(db.PROBLEM_CLUSTERS, c["id"], {"queries_expanded_at": db.now()})
        done.append({"cluster": c["name"], "set": ks["name"], "added": data.get("reddit_search", []) + data.get("youtube", [])})
    return {"expanded": done, "calls": budget.calls}


# ----------------------------------------------------------------------------
# (2) CROSS-VERTICAL — evidence-based only: every vertical must have written it itself
# ----------------------------------------------------------------------------
class CrossMatch(BaseModel):
    groups: list[dict] = Field(description="items {cluster_ids: [...], name, problem_statement}: clusters from DIFFERENT verticals whose signals literally describe the same job")


CROSS_PROMPT = """Below are problem clusters from DIFFERENT verticals, each with verbatim quotes. Group ONLY clusters whose quotes literally describe the same
job-to-be-done (same task, same failure). Do not group by analogy ("dentists and physios probably both..."): if the quotes of a vertical do not say it,
that vertical is not in. Prefer no group over a speculative one.

CLUSTERS (id :: vertical :: name :: quotes):
{clusters}
"""

CROSS_MIN_SIGNALS_PER_VERTICAL = 5
CROSS_MIN_AUTHORS_PER_VERTICAL = 4


def cross_vertical_merge(max_groups: int = 5) -> dict:
    """
    Create horizontal clusters from clusters of different verticals that each, on their own evidence, express the same job.
    Guard rails: each member cluster must have >= 5 signals and >= 4 distinct authors from its own vertical; the merged
    cluster keeps `evidence_by_vertical` so the claim "it exists in N verticals" is always traceable.
    """
    cands = [c for c in db.list_all(db.PROBLEM_CLUSTERS)
             if not c.get("parent_cluster_id") and not c.get("is_cross_vertical") and not c.get("cross_merged_into")
             and (c.get("signal_count") or 0) >= CROSS_MIN_SIGNALS_PER_VERTICAL and (c.get("distinct_authors") or 0) >= CROSS_MIN_AUTHORS_PER_VERTICAL
             and c.get("dominant_attack_vector") in ATTACKABLE and c.get("evidence_quotes")]
    if len({c.get("vertical") for c in cands}) < 2:
        return {"groups": 0, "reason": "fewer than 2 verticals with eligible clusters"}
    txt = "\n".join(f"{c['id']} :: {c.get('vertical')} :: {c['name']} :: " + " | ".join(f"\"{q['quote'][:110]}\"" for q in c['evidence_quotes'][:3]) for c in cands[:60])
    data = llm_json(CROSS_PROMPT.format(clusters=txt), CrossMatch, strong=True)
    by_id = {c["id"]: c for c in cands}
    created = []
    for g in (data.get("groups") or [])[:max_groups]:
        members = [by_id[i] for i in (g.get("cluster_ids") or []) if i in by_id]
        verts = {m.get("vertical") for m in members}
        if len(members) < 2 or len(verts) < 2:
            continue
        new_id = db.upsert(db.PROBLEM_CLUSTERS, None, {
            "name": g.get("name") or members[0]["name"], "problem_statement": g.get("problem_statement") or members[0].get("problem_statement"),
            "persona": " / ".join(sorted({m.get("persona") or "" for m in members if m.get("persona")}))[:200],
            "vertical": "+".join(sorted(verts)), "is_cross_vertical": True, "member_cluster_ids": [m["id"] for m in members],
            "evidence_by_vertical": {m.get("vertical"): {"cluster": m["name"], "signals": m.get("signal_count"), "authors": m.get("distinct_authors"),
                                                          "quotes": (m.get("evidence_quotes") or [])[:3]} for m in members},
            "keyword_set_id": members[0].get("keyword_set_id"), "created_by": "cross_vertical", "signal_count": 0, "created_at": db.now()})
        client = db.get_db()
        for m in members:
            for d in client.collection(db.PROBLEM_CLUSTERS).document(m["id"]).collection(db.CLUSTER_SIGNALS_SUB).stream():
                client.collection(db.PROBLEM_CLUSTERS).document(new_id).collection(db.CLUSTER_SIGNALS_SUB).document(d.id).set(d.to_dict() or {"relevance": 0.8})
            db.upsert(db.PROBLEM_CLUSTERS, m["id"], {"cross_merged_into": new_id})  # members stay (their own funnel), flagged
        funnel.refresh_cluster_stats(new_id)
        funnel.ensure_opportunity(new_id)
        created.append({"id": new_id, "name": g.get("name"), "verticals": sorted(verts), "members": len(members)})
    return {"groups": len(created), "created": created, "calls": budget.calls}
