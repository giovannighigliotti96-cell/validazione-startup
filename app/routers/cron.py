"""
Endpoints for cron-job.org (header X-Cron-Token). Suggested schedule:
  POST /cron/scrape   every 6h   (timeout: set cron-job.org "timeout" to max, we return fast anyway)
  POST /cron/funnel   every 1h
  GET  /cron/health   every 15m  (keeps Cloud Run warm-ish; optional)
"""
from fastapi import APIRouter, BackgroundTasks, Depends

from app import db
from app.auth import require_cron
from app.services import analysis, funnel, runner

router = APIRouter(prefix="/cron", tags=["cron"], dependencies=[Depends(require_cron)])


@router.api_route("/scrape", methods=["GET", "POST"], status_code=202)
def cron_scrape(background: BackgroundTasks, sources: str | None = None):
    """Scrape all active keyword sets in the background, then evaluate the funnel."""
    src = sources.split(",") if sources else None

    def job():
        runner.run_all(None, src, "cron")
        analysis.run_full_analysis()  # includes funnel.evaluate_all

    background.add_task(job)
    return {"status": "accepted"}


@router.api_route("/scrape/sync", methods=["GET", "POST"])
def cron_scrape_sync(sources: str | None = None):
    """Blocking variant (for GitHub Actions or when you want the result in the response)."""
    src = sources.split(",") if sources else None
    res = runner.run_all(None, src, "cron")
    return {"runs": res, "analysis": analysis.run_full_analysis()}


@router.api_route("/analyze", methods=["GET", "POST"])
def cron_analyze():
    return analysis.run_full_analysis()


@router.api_route("/digest", methods=["GET", "POST"])
def cron_digest():
    return {"status": funnel.send_weekly_digest()}


@router.api_route("/funnel", methods=["GET", "POST"])
def cron_funnel():
    return funnel.evaluate_all(send_notifications=True)


@router.get("/health")
def health():
    return {"ok": True, "keyword_sets_active": db.count(db.KEYWORD_SETS, is_active=True), "signals": db.count(db.RAW_SIGNALS)}
