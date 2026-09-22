"""Cloud Run Job entry point: every background workload runs here, billed only while it runs, instead of keeping the
web service's CPU allocated 24/7. Cloud Scheduler triggers the job with an args override; the web app triggers
on-demand tasks (matching) the same way (app.services.jobs.trigger).

  python -m scripts.job scrape | funnel | adlib | discover | arbitrage | distressed | procedures | digest
  python -m scripts.job match_lead <lead_id> | match_listing <listing_id>
"""
from __future__ import annotations

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("job")


def scrape() -> None:
    from app.services import analysis, retention, runner

    runner.run_all(None, None, "cron")
    analysis.run_full_analysis()
    retention.apply()


def funnel() -> None:
    from app.services import funnel as _f
    from app.services import guida, poltrona

    _f.evaluate_all(True)
    log.info("poltrona reminders: %s", poltrona.send_reminders())
    log.info("guida workflow emails: %s", guida.run_workflow())


def adlib() -> None:
    from app.services import adlib as _a

    log.info("adlib: %s", _a.run_cycle(max_terms=0, harvest=False))


def discover() -> None:
    from app import db
    from app.services import analysis

    analysis.budget.reset()
    log.info("discover: %s", analysis.discover_verticals())
    strong = {c.get("keyword_set_id") for c in db.list_all(db.PROBLEM_CLUSTERS) if (c.get("distinct_authors") or 0) >= 10}
    for k in db.list_all(db.KEYWORD_SETS, is_active=True):
        if k["id"] in strong:
            try:
                analysis.scan_why_now(k["id"])
            except Exception as e:  # noqa: BLE001
                log.error("whynow %s: %s", k["name"], e)


def arbitrage() -> None:
    from app.services import analysis
    from app.services import arbitrage as _a

    analysis.budget.reset()
    log.info("arbitrage: %s", _a.run())


def distressed() -> None:
    from app.services import distressed as _d

    log.info("distressed: %s", _d.run_weekly())


def procedures() -> None:
    from app.services import procedures as _p

    log.info("procedures: %s", _p.run_weekly())


def digest() -> None:
    from app.services import funnel as _f
    from app.services import notify, social as _s

    log.info("digest: %s", _f.send_weekly_digest())
    try:
        notify.send_email("Pagina Facebook: riepilogo settimanale — Poltrona Libera", _s.week_summary())
    except Exception as e:  # noqa: BLE001
        log.error("social summary: %s", e)


def social() -> None:
    from app.services import instagram, social as _s

    _s.seed_plan()
    instagram.seed()
    log.info("social published: %s", _s.publish_due())


def social_now(post_id: str) -> None:
    from app.services import social as _s

    log.info("social published now: %s", _s.publish_due(force_id=post_id))


def inbox() -> None:
    from app.services import inbox as _i

    log.info("inbox: %s", _i.run())


def report() -> None:
    from app.services import daily

    daily.report(send=True)
    log.info("zone alerts: %s", daily.zone_alerts())


def match_lead(lead_id: str) -> None:
    from app import db
    from app.services import matching
    from app.services import poltrona as P

    lead = db.get_db().collection(db.PROBLEM_CLUSTERS).document(P.PROS).collection("leads").document(lead_id).get().to_dict()
    if lead:
        matching.match_lead(lead_id, lead)


def match_listing(listing_id: str) -> None:
    from app import db
    from app.services import matching

    snap = db.get_db().collection("listings").document(listing_id).get()
    if snap.exists:
        matching.match_listing({"id": listing_id, **snap.to_dict()})


JOBS = {"scrape": scrape, "funnel": funnel, "adlib": adlib, "discover": discover, "arbitrage": arbitrage, "distressed": distressed,
        "procedures": procedures, "digest": digest, "match_lead": match_lead, "match_listing": match_listing, "social": social, "social_now": social_now, "inbox": inbox, "report": report}

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "funnel"
    args = sys.argv[2:]
    log.info("job %s %s", name, args)
    JOBS[name](*args)
    log.info("job %s done", name)
