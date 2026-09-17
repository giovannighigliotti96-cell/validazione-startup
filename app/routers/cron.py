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


@router.api_route("/funnel", methods=["GET", "POST"], status_code=202)
def cron_funnel(background: BackgroundTasks):
    """Responds immediately (cron-job.org has a 30s limit); evaluation runs in the background (Cloud Run: CPU always allocated)."""
    background.add_task(funnel.evaluate_all, True)
    return {"status": "accepted", "clusters": db.count(db.PROBLEM_CLUSTERS)}


@router.api_route("/funnel/sync", methods=["GET", "POST"])
def cron_funnel_sync():
    return funnel.evaluate_all(send_notifications=True)


@router.get("/health")
def health():
    return {"ok": True, "keyword_sets_active": db.count(db.KEYWORD_SETS, is_active=True), "signals": db.count(db.RAW_SIGNALS)}


@router.api_route("/discover", methods=["GET", "POST"], status_code=202)
def cron_discover(background: BackgroundTasks):
    """Weekly: why-now scan on every active set, then thesis-guided vertical discovery (GitHub cron skipped these; cron-job.org is reliable)."""

    def job():
        analysis.budget.reset()
        for k in db.list_all(db.KEYWORD_SETS, is_active=True):
            try:
                analysis.scan_why_now(k["id"])
            except Exception as e:  # noqa: BLE001
                analysis.log.error("whynow %s: %s", k["name"], e)
        analysis.log.info("discover: %s", analysis.discover_verticals())

    background.add_task(job)
    return {"status": "accepted"}


@router.api_route("/arbitrage", methods=["GET", "POST"], status_code=202)
def cron_arbitrage(background: BackgroundTasks):
    """Weekly: recent US launches -> Italian gap check."""
    from app.services import arbitrage

    def job():
        analysis.budget.reset()
        analysis.log.info("arbitrage: %s", arbitrage.run())

    background.add_task(job)
    return {"status": "accepted"}
