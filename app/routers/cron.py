"""
Endpoints for cron-job.org (header X-Cron-Token). Suggested schedule:
  POST /cron/scrape   every 6h   (timeout: set cron-job.org "timeout" to max, we return fast anyway)
  POST /cron/funnel   every 1h
  GET  /cron/health   every 15m  (keeps Cloud Run warm-ish; optional)
"""
from fastapi import APIRouter, BackgroundTasks, Depends

from app import db
from app.auth import require_api
from app.auth import require_cron
from app.services import analysis, funnel, runner

router = APIRouter(prefix="/cron", tags=["cron"], dependencies=[Depends(require_cron)])


@router.api_route("/scrape", methods=["GET", "POST"], status_code=202)
def cron_scrape(background: BackgroundTasks, sources: str | None = None):
    """Scrape all active keyword sets in the background, then evaluate the funnel."""
    src = sources.split(",") if sources else None

    def job():
        from app.services import retention

        runner.run_all(None, src, "cron")
        analysis.run_full_analysis()  # includes funnel.evaluate_all
        retention.apply()  # privacy policy + Reddit Data API Terms: raw Reddit text purged after 30 days

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
        analysis.log.info("discover: %s", analysis.discover_verticals())  # first: it is the call that matters
        # why-now only for sets that already have a real cluster (>= 10 people): 2 searches each, shared daily budget
        strong = {c.get("keyword_set_id") for c in db.list_all(db.PROBLEM_CLUSTERS) if (c.get("distinct_authors") or 0) >= 10}
        for k in db.list_all(db.KEYWORD_SETS, is_active=True):
            if k["id"] not in strong:
                continue
            try:
                analysis.scan_why_now(k["id"])
            except Exception as e:  # noqa: BLE001
                analysis.log.error("whynow %s: %s", k["name"], e)

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


@router.api_route("/distressed", methods=["GET", "POST"], status_code=202)
def cron_distressed(background: BackgroundTasks):
    """Weekly: CIGS decrees -> distressed companies ranking + news enrichment for the top."""
    from app.services import distressed

    background.add_task(lambda: analysis.log.info("distressed: %s", distressed.run_weekly()))
    return {"status": "accepted"}


@router.api_route("/adlib", methods=["GET", "POST"], status_code=202)
def cron_adlib(background: BackgroundTasks, max_terms: int = 4):
    """Hourly, 24/7: Meta Ad Library broad-first digital-product discovery (proven ads only: active 6m+)."""
    from app.services import adlib

    background.add_task(lambda: adlib.run_cycle(max_terms=max_terms))
    return {"status": "accepted"}


@router.get("/adlib/debug")
def adlib_debug(term: str = "printable", scrolls: int = 10):
    """What the Ad Library page looks like from this server (language, wall, card count)."""
    import time as _t

    from playwright.sync_api import sync_playwright

    from app.services import adlib

    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        pg = b.new_page(viewport={"width": 1300, "height": 900}, locale="it-IT")
        pg.goto(adlib.library_url(term), wait_until="domcontentloaded")
        _t.sleep(6)
        for _ in range(scrolls):
            pg.mouse.wheel(0, 5000)
            _t.sleep(1.3)
        txt = pg.inner_text("body")
        b.close()
    return {"url": adlib.library_url(term), "len": len(txt), "id_libreria": txt.count("ID libreria"), "library_id": txt.count("Library ID"),
            "sponsorizzato": txt.count("Sponsorizzato"), "sponsored": txt.count("Sponsored"), "head": txt[:1500]}


@router.get("/adlib/report", dependencies=[Depends(require_api)])
def adlib_report(limit: int = 80):
    from app.services import adlib

    return adlib.report(limit)


@router.api_route("/procedures", methods=["GET", "POST"], status_code=202)
def cron_procedures(background: BackgroundTasks):
    """Weekly: judicial liquidations per tribunal -> ranking + public teaser for the freshest."""
    from app.services import procedures

    background.add_task(lambda: analysis.log.info("procedures: %s", procedures.run_weekly()))
    return {"status": "accepted"}


@router.api_route("/meta/activate", methods=["GET", "POST"])
def cron_meta_activate(campaign_id: str):
    """One-shot: activate a Meta campaign (all ad sets + ads). Scheduled from cron-job.org because Meta refuses start_time edits."""
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from scripts.meta_campaign import env, call

    tok = env()["META_ACCESS_TOKEN"]
    out = []
    for a in call("GET", f"{campaign_id}/adsets", tok, fields="id,name").get("data", []):
        for ad in call("GET", f"{a['id']}/ads", tok, fields="id").get("data", []):
            call("POST", ad["id"], tok, status="ACTIVE")
        call("POST", a["id"], tok, status="ACTIVE"); out.append(a["name"])
    call("POST", campaign_id, tok, status="ACTIVE")
    analysis.log.info("meta campaign %s activated: %s", campaign_id, out)
    return {"status": "ACTIVE", "campaign_id": campaign_id, "adsets": out}
