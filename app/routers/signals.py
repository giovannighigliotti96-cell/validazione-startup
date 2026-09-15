from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response

from app import db
from app.auth import require_api
from app.services import export

router = APIRouter(tags=["signals & export"], dependencies=[Depends(require_api)])


@router.get("/signals")
def list_signals(
    keyword_set_id: str | None = None,
    source: str | None = None,
    min_wtp: int = Query(0, ge=0, le=10),
    since: datetime | None = None,
    limit: int = Query(200, le=5000),
):
    return export.query_signals(keyword_set_id, source, min_wtp, since, limit)


@router.get("/signals/{signal_id}")
def get_signal(signal_id: str):
    s = db.get(db.RAW_SIGNALS, signal_id)
    if not s:
        raise HTTPException(404)
    return s


@router.get("/signals/stats/summary")
def stats():
    """Quick counts per source and per keyword set (Firestore aggregation queries)."""
    ks = db.list_all(db.KEYWORD_SETS)
    return {
        "total": db.count(db.RAW_SIGNALS),
        "unprocessed": db.count(db.RAW_SIGNALS, is_processed=False),
        "by_source": {s: db.count(db.RAW_SIGNALS, source=s) for s in ("reddit", "hackernews", "indiehackers", "trustpilot", "playstore", "appstore", "youtube", "forum")},
        "by_keyword_set": {k["name"]: db.count(db.RAW_SIGNALS, keyword_set_id=k["id"]) for k in ks},
        "competitors": db.count(db.COMPETITOR_SIGNALS),
        "trend_snapshots": db.count(db.TREND_SNAPSHOTS),
    }


def _cluster_signal_ids(cluster_id: str) -> list[str]:
    sub = db.get_db().collection(db.PROBLEM_CLUSTERS).document(cluster_id).collection(db.CLUSTER_SIGNALS_SUB)
    return [d.id for d in sub.stream()]


def _rows(keyword_set_id, source, min_wtp, since, limit, cluster_id):
    if cluster_id:
        ids = set(_cluster_signal_ids(cluster_id))
        ks_names = {k["id"]: k for k in db.list_all(db.KEYWORD_SETS)}
        client = db.get_db()
        sigs = []
        for chunk in db.chunks(list(ids), 300):
            refs = [client.collection(db.RAW_SIGNALS).document(i) for i in chunk]
            sigs.extend(d for d in (db.doc_to_dict(s) for s in client.get_all(refs)) if d)
        return [export._row(s, ks_names) for s in sigs]
    return export.export_rows(keyword_set_id=keyword_set_id, source=source, min_wtp=min_wtp, since=since, limit=limit)


@router.get("/export/signals.csv", response_class=PlainTextResponse)
def export_csv(
    keyword_set_id: str | None = None, source: str | None = None, min_wtp: int = 0,
    since: datetime | None = None, limit: int = 5000, cluster_id: str | None = None,
):
    """Human-readable CSV for User Interviews / Respondent screeners. No usernames."""
    csv_text = export.to_csv(_rows(keyword_set_id, source, min_wtp, since, limit, cluster_id))
    return Response(csv_text, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=signals.csv"})


@router.get("/export/signals.json")
def export_json(
    keyword_set_id: str | None = None, source: str | None = None, min_wtp: int = 0,
    since: datetime | None = None, limit: int = 5000, cluster_id: str | None = None,
):
    return Response(export.to_json(_rows(keyword_set_id, source, min_wtp, since, limit, cluster_id)), media_type="application/json")


@router.get("/trends")
def list_trends(keyword_set_id: str | None = None, limit: int = 200):
    q = db.get_db().collection(db.TREND_SNAPSHOTS)
    if keyword_set_id:
        q = q.where("keyword_set_id", "==", keyword_set_id)
    return [db.doc_to_dict(s) for s in q.order_by("captured_at", direction="DESCENDING").limit(limit).stream()]


@router.post("/signals/manual", status_code=201)
def manual_signal(body: dict = Body(...)):
    """
    Paste something you read yourself (a Facebook group thread, a WhatsApp message, a forum post, notes from a chat):
    {"keyword_set_name": "sport_ski_schools", "text": "...", "url": "optional", "title": "optional", "source_label": "facebook_group",
     "published_at": "2026-09-10" (optional), "author_label": "optional stable pseudonym to count distinct people, e.g. 'direttore scuola A'"}
    Enters the pipeline like any scraped signal (heuristics, LLM extraction with grounding, clustering).
    """
    from app import heuristics
    from app.db import hash_author
    from app.models import RawSignal

    ks = next((k for k in db.list_all(db.KEYWORD_SETS) if k["name"] == body.get("keyword_set_name")), None)
    if not ks:
        raise HTTPException(422, "unknown keyword_set_name (GET /keyword-sets)")
    text = (body.get("text") or "").strip()
    if len(text) < 30:
        raise HTTPException(422, "text too short")
    ext = "manual_" + db.new_id()[:16]
    sig = RawSignal(source="forum", signal_type="post", external_id=ext, url=body.get("url"), title=body.get("title"), text=text[:20000],
                    author_hash=hash_author("manual", body.get("author_label")) if body.get("author_label") else None,
                    published_at=datetime.fromisoformat(body["published_at"]) if body.get("published_at") else datetime.now(timezone.utc),
                    keyword="manual", channel=body.get("source_label") or "manual", raw={"imported_by": "founder"})
    h = heuristics.analyze(sig.text, sig.title)
    d = {**sig.model_dump(), **h.as_dict(), "keyword_set_id": ks["id"], "run_id": None, "scraped_at": db.now(), "is_processed": False,
         "cluster_id": None, "unanswered_ask": False, "attack_vector": None, "llm_problem_statement": None, "llm_urgency": None,
         "llm_frequency": None, "llm_metadata": None}
    doc_id = db.signal_doc_id("forum", ext)
    db.insert_new_only(db.RAW_SIGNALS, {doc_id: d})
    return {"id": doc_id, "keyword_set": ks["name"], "heuristic_score": h.heuristic_score, "note": "will be extracted and clustered at the next analysis run (every 6h) or POST /analyze"}
