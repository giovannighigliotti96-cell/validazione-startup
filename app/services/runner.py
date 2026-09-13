"""Orchestrates a scraping run over one or more keyword sets."""
from __future__ import annotations

import logging
import traceback

from app import db, heuristics
from app.scrapers import SIDE_SCRAPERS, SIGNAL_SCRAPERS

log = logging.getLogger("runner")


def _persist_signals(signals, run_id: str, keyword_set_id: str) -> tuple[int, int]:
    docs: dict[str, dict] = {}
    for sig in signals:
        h = heuristics.analyze(sig.text, sig.title)
        d = sig.model_dump()
        d.update(h.as_dict())
        d.update(
            {
                "run_id": run_id,
                "keyword_set_id": keyword_set_id,
                "scraped_at": db.now(),
                "is_processed": False,
                "cluster_id": None,
                # LLM fields — TODO(LLM): filled by app/services/analysis.py
                "llm_problem_statement": None,
                "llm_urgency": None,
                "llm_frequency": None,
                "llm_metadata": None,
            }
        )
        docs[db.signal_doc_id(sig.source, sig.external_id)] = d
    return db.insert_new_only(db.RAW_SIGNALS, docs)


def run_keyword_set(keyword_set: dict, sources: list[str] | None, trigger: str) -> dict:
    run_id = db.upsert(
        db.SCRAPE_RUNS,
        None,
        {"keyword_set_id": keyword_set["id"], "keyword_set_name": keyword_set.get("name"), "trigger": trigger,
         "status": "running", "started_at": db.now(), "finished_at": None, "stats": {}, "error": None},
    )
    configured = keyword_set.get("sources") or {}
    wanted = [s for s in configured if (sources is None or s in sources)]
    stats: dict[str, dict] = {}
    failed = 0

    for source in wanted:
        cfg = configured[source] or {}
        try:
            if source in SIGNAL_SCRAPERS:
                signals = SIGNAL_SCRAPERS[source](keyword_set, cfg)
                inserted, existing = _persist_signals(signals, run_id, keyword_set["id"])
                stats[source] = {"fetched": len(signals), "inserted": inserted, "existing": existing, "error": None}
            elif source in SIDE_SCRAPERS:
                stats[source] = {**SIDE_SCRAPERS[source](keyword_set, cfg), "error": None}
            else:
                stats[source] = {"error": f"unknown source '{source}'"}
        except Exception as e:  # noqa: BLE001
            failed += 1
            log.error("source %s failed for set %s:\n%s", source, keyword_set.get("name"), traceback.format_exc())
            stats[source] = {"error": f"{type(e).__name__}: {e}"}
        # checkpoint after each source so a crash mid-run still leaves partial stats
        db.upsert(db.SCRAPE_RUNS, run_id, {"stats": stats})

    status = "done" if failed == 0 else ("failed" if failed == len(wanted) and wanted else "partial")
    db.upsert(db.SCRAPE_RUNS, run_id, {"status": status, "finished_at": db.now(), "stats": stats})
    return {"run_id": run_id, "status": status, "stats": stats}


def run_all(keyword_set_ids: list[str] | None, sources: list[str] | None, trigger: str) -> list[dict]:
    if keyword_set_ids:
        sets = [ks for i in keyword_set_ids if (ks := db.get(db.KEYWORD_SETS, i))]
    else:
        sets = db.list_all(db.KEYWORD_SETS, is_active=True)
    results = []
    for ks in sets:
        results.append({"keyword_set": ks.get("name"), **run_keyword_set(ks, sources, trigger)})
    return results
