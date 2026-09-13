"""
Endpoints for cron-job.org (header X-Cron-Token). Suggested schedule:
  POST /cron/scrape   every 6h   (timeout: set cron-job.org "timeout" to max, we return fast anyway)
  POST /cron/funnel   every 1h
  GET  /cron/health   every 15m  (keeps Cloud Run warm-ish; optional)
"""
from fastapi import APIRouter, BackgroundTasks, Depends

from app import db
from app.auth import require_cron
from app.services import funnel, runner

router = APIRouter(prefix="/cron", tags=["cron"], dependencies=[Depends(require_cron)])


@router.post("/scrape", status_code=202)
def cron_scrape(background: BackgroundTasks, sources: str | None = None):
    """Scrape all active keyword sets in the background, then evaluate the funnel."""
    src = sources.split(",") if sources else None

    def job():
        runner.run_all(None, src, "cron")
        funnel.evaluate_all(send_notifications=True)

    background.add_task(job)
    return {"status": "accepted"}


@router.post("/scrape/sync")
def cron_scrape_sync(sources: str | None = None):
    """Blocking variant (for GitHub Actions or when you want the result in the response)."""
    src = sources.split(",") if sources else None
    res = runner.run_all(None, src, "cron")
    fun = funnel.evaluate_all(send_notifications=True)
    return {"runs": res, "funnel": fun}


@router.post("/funnel")
def cron_funnel():
    return funnel.evaluate_all(send_notifications=True)


@router.get("/health")
def health():
    return {"ok": True, "keyword_sets_active": db.count(db.KEYWORD_SETS, is_active=True), "signals": db.count(db.RAW_SIGNALS)}
