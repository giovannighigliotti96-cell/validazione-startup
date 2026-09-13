from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app import db
from app.auth import require_api
from app.models import RunRequest
from app.services import runner

router = APIRouter(prefix="/runs", tags=["scrape runs"], dependencies=[Depends(require_api)])


@router.post("", status_code=202)
def start_run(body: RunRequest, background: BackgroundTasks):
    """Launch a scraping run in the background. Poll GET /runs to follow progress."""
    background.add_task(runner.run_all, body.keyword_set_ids, body.sources, body.trigger)
    return {"status": "accepted", "keyword_set_ids": body.keyword_set_ids or "all-active", "sources": body.sources or "all"}


@router.post("/sync")
def start_run_sync(body: RunRequest):
    """Same as POST /runs but waits for completion (use for small tests; Cloud Run timeout is 60 min)."""
    return runner.run_all(body.keyword_set_ids, body.sources, body.trigger)


@router.get("")
def list_runs(limit: int = 50):
    q = db.get_db().collection(db.SCRAPE_RUNS).order_by("started_at", direction="DESCENDING").limit(limit)
    return [db.doc_to_dict(s) for s in q.stream()]


@router.get("/{run_id}")
def get_run(run_id: str):
    r = db.get(db.SCRAPE_RUNS, run_id)
    if not r:
        raise HTTPException(404)
    return r
