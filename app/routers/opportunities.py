"""Clusters, opportunity scoring, market components, competitors, experiments, funnel stages."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app import db
from app.auth import require_api
from app.models import ClusterIn, CompetitorIn, ExperimentIn, FunnelStagePatch, MarketComponentIn, OpportunityPatch
from app.services import analysis, funnel, market

router = APIRouter(tags=["opportunities"], dependencies=[Depends(require_api)])


# ------------------------------ clusters ------------------------------------
@router.get("/clusters")
def list_clusters():
    return db.list_all(db.PROBLEM_CLUSTERS)


@router.post("/clusters", status_code=201)
def create_cluster(body: ClusterIn):
    """Manual cluster creation (until the LLM clustering exists). Attach signals by id."""
    data = body.model_dump(exclude={"signal_ids"})
    cid = db.upsert(db.PROBLEM_CLUSTERS, None, {**data, "created_at": db.now(), "signal_count": 0})
    if body.signal_ids:
        _attach(cid, body.signal_ids)
    funnel.ensure_opportunity(cid)
    return get_opportunity(cid)


def _attach(cluster_id: str, signal_ids: list[str], relevance: float = 1.0):
    client = db.get_db()
    sub = client.collection(db.PROBLEM_CLUSTERS).document(cluster_id).collection(db.CLUSTER_SIGNALS_SUB)
    for chunk in db.chunks(signal_ids, db.FIRESTORE_BATCH_LIMIT):
        batch = client.batch()
        for sid in chunk:
            batch.set(sub.document(sid), {"relevance": relevance, "attached_at": db.now()})
        batch.commit()
    return funnel.refresh_cluster_stats(cluster_id)


@router.post("/clusters/{cluster_id}/signals")
def attach_signals(cluster_id: str, signal_ids: list[str]):
    if not db.get(db.PROBLEM_CLUSTERS, cluster_id):
        raise HTTPException(404)
    return _attach(cluster_id, signal_ids)


@router.delete("/clusters/{cluster_id}", status_code=204)
def delete_cluster(cluster_id: str):
    db.delete(db.PROBLEM_CLUSTERS, cluster_id)
    db.delete(db.OPPORTUNITY_SCORING, cluster_id)


# ------------------------------ opportunities --------------------------------
@router.get("/opportunities")
def list_opportunities(include_archived: bool = False):
    clusters = {c["id"]: c for c in db.list_all(db.PROBLEM_CLUSTERS)}
    out = []
    for o in db.list_all(db.OPPORTUNITY_SCORING):
        if o.get("is_archived") and not include_archived:
            continue
        out.append({**o, "cluster": clusters.get(o["cluster_id"])})
    out.sort(key=lambda o: (o.get("overall_score") or 0), reverse=True)
    return out


@router.get("/opportunities/{cluster_id}")
def get_opportunity(cluster_id: str):
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    if not c:
        raise HTTPException(404)
    o = funnel.ensure_opportunity(cluster_id)
    return {
        **o,
        "cluster": c,
        "competitors": db.list_all(db.COMPETITOR_SIGNALS, cluster_id=cluster_id),
        "experiments": db.list_all(db.VALIDATION_EXPERIMENTS, cluster_id=cluster_id),
        "metrics": funnel.collect_metrics(c, o),
    }


@router.patch("/opportunities/{cluster_id}")
def patch_opportunity(cluster_id: str, body: OpportunityPatch):
    """Manual fields: saturation, competitor_count, founder_fit, why_now... Then re-evaluates the funnel."""
    if not db.get(db.PROBLEM_CLUSTERS, cluster_id):
        raise HTTPException(404)
    funnel.ensure_opportunity(cluster_id)
    db.upsert(db.OPPORTUNITY_SCORING, cluster_id, body.model_dump(exclude_none=True))
    return funnel.evaluate(cluster_id)


@router.put("/opportunities/{cluster_id}/market/{component}")
def set_market_component(cluster_id: str, component: str, body: MarketComponentIn):
    if component != body.component:
        raise HTTPException(422, "component mismatch")
    if not db.get(db.PROBLEM_CLUSTERS, cluster_id):
        raise HTTPException(404)
    funnel.ensure_opportunity(cluster_id)
    res = market.set_component(cluster_id, component, body.model_dump(exclude={"component"}))
    return {**res, "funnel": funnel.evaluate(cluster_id)}


# ------------------------------ competitors ----------------------------------
@router.get("/competitors")
def list_competitors(cluster_id: str | None = None, keyword_set_id: str | None = None, limit: int = 500):
    where = {k: v for k, v in {"cluster_id": cluster_id, "keyword_set_id": keyword_set_id}.items() if v}
    return db.list_all(db.COMPETITOR_SIGNALS, limit=limit, **where)


@router.post("/competitors", status_code=201)
def add_competitor(body: CompetitorIn):
    ext = body.external_id or db.new_id()
    doc_id = db.safe_id(body.source, ext)
    db.upsert(db.COMPETITOR_SIGNALS, doc_id, {**body.model_dump(), "external_id": ext, "captured_at": db.now()})
    if body.cluster_id:
        n = db.count(db.COMPETITOR_SIGNALS, cluster_id=body.cluster_id)
        db.upsert(db.OPPORTUNITY_SCORING, body.cluster_id, {"competitor_count": n})
    return db.get(db.COMPETITOR_SIGNALS, doc_id)


@router.post("/competitors/{competitor_id}/assign/{cluster_id}")
def assign_competitor(competitor_id: str, cluster_id: str):
    if not db.get(db.COMPETITOR_SIGNALS, competitor_id) or not db.get(db.PROBLEM_CLUSTERS, cluster_id):
        raise HTTPException(404)
    db.upsert(db.COMPETITOR_SIGNALS, competitor_id, {"cluster_id": cluster_id})
    n = db.count(db.COMPETITOR_SIGNALS, cluster_id=cluster_id)
    funnel.ensure_opportunity(cluster_id)
    db.upsert(db.OPPORTUNITY_SCORING, cluster_id, {"competitor_count": n})
    return {"cluster_id": cluster_id, "competitor_count": n}


# ------------------------------ experiments ----------------------------------
@router.get("/experiments")
def list_experiments(cluster_id: str | None = None):
    return db.list_all(db.VALIDATION_EXPERIMENTS, **({"cluster_id": cluster_id} if cluster_id else {}))


@router.post("/experiments", status_code=201)
def add_experiment(body: ExperimentIn):
    if not db.get(db.PROBLEM_CLUSTERS, body.cluster_id):
        raise HTTPException(404, "cluster not found")
    eid = db.upsert(db.VALIDATION_EXPERIMENTS, None, {**body.model_dump(), "created_at": db.now()})
    return {"experiment": db.get(db.VALIDATION_EXPERIMENTS, eid), "funnel": funnel.evaluate(body.cluster_id)}


@router.patch("/experiments/{experiment_id}")
def patch_experiment(experiment_id: str, body: dict):
    e = db.get(db.VALIDATION_EXPERIMENTS, experiment_id)
    if not e:
        raise HTTPException(404)
    db.upsert(db.VALIDATION_EXPERIMENTS, experiment_id, body)
    return {"experiment": db.get(db.VALIDATION_EXPERIMENTS, experiment_id), "funnel": funnel.evaluate(e["cluster_id"])}


# ------------------------------ funnel ---------------------------------------
@router.get("/funnel/stages")
def list_stages():
    return funnel.get_stages()


@router.patch("/funnel/stages/{key}")
def patch_stage(key: str, body: FunnelStagePatch):
    """Tune thresholds without touching code."""
    if not db.get(db.FUNNEL_STAGES, key):
        raise HTTPException(404)
    db.upsert(db.FUNNEL_STAGES, key, body.model_dump(exclude_none=True))
    return db.get(db.FUNNEL_STAGES, key)


@router.post("/funnel/evaluate")
def evaluate_all(send_notifications: bool = True):
    return funnel.evaluate_all(send_notifications)


@router.post("/funnel/evaluate/{cluster_id}")
def evaluate_one(cluster_id: str, send_notifications: bool = True):
    return funnel.evaluate(cluster_id, send_notifications)


@router.get("/notifications")
def list_notifications(limit: int = 50):
    q = db.get_db().collection(db.NOTIFICATIONS).order_by("sent_at", direction="DESCENDING").limit(limit)
    return [db.doc_to_dict(s) for s in q.stream()]


@router.post("/notifications/test")
def test_notification():
    """Send a sample email to verify SMTP/Resend config."""
    from app.services import notify

    cluster = {"id": "test", "name": "TEST — Studi dentistici perdono ore sulle pre-autorizzazioni", "problem_statement": "Esempio di problem statement.",
               "vertical": "dentistry", "persona": "office manager", "signal_count": 42, "distinct_sources": 3, "distinct_authors": 31,
               "mom_test_questions": ["Raccontami l'ultima volta che hai gestito una pre-autorizzazione.", "Quanto tempo ci hai messo?"]}
    opp = {"tam_eur": 450e6, "sam_eur": 60e6, "som_eur": 1.2e6, "market_confidence": "medium", "saturation": "blue", "competitor_count": 4,
           "founder_fit": 4, "acquisition_channel": "LinkedIn outbound + gruppi Facebook di office manager", "why_now": "Nuove regole assicurative 2026", "overall_score": 78,
           "stage_history": [{"stage": "signal_collected", "at": "2026-09-01T10:00", "reason": "created"}]}
    stage = {"key": "presale_validation", "name": "VERIFICA CHE PAGHINO (carta di credito)", "description": "Landing con prezzo + payment link."}
    subject, html = notify.render_stage_email(cluster, opp, stage, {"min_interviews": "✔ interviews=6 (>= 5)"})
    status, err = notify.send_email(subject, html)
    return {"status": status, "error": err, "subject": subject}


# ------------------------------ LLM layer (Gemini) --------------------------
@router.post("/analyze", status_code=202)
def analyze(background: BackgroundTasks, keyword_set_id: str | None = None, extract_limit: int | None = None):
    """Extract -> cluster -> enrich -> funnel, in background (Gemini free-tier budgeted). Watch /clusters and /opportunities."""
    background.add_task(analysis.run_full_analysis, keyword_set_id, extract_limit, True)
    return {"status": "accepted"}


@router.post("/analyze/sync")
def analyze_sync(keyword_set_id: str | None = None, extract_limit: int | None = None):
    return analysis.run_full_analysis(keyword_set_id, extract_limit, True)


@router.post("/clusters/{cluster_id}/enrich")
def enrich(cluster_id: str, force: bool = False):
    analysis.budget.reset()
    res = analysis.enrich_cluster(cluster_id, force=force)
    return {"enrich": res, "funnel": funnel.evaluate(cluster_id)}
