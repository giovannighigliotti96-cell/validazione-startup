"""
Funnel engine.

Stages live in `funnel_stages` (ordered by position). Each stage has `criteria`:
thresholds an opportunity must satisfy to ENTER that stage. `evaluate(cluster_id)`
tries to advance one stage at a time (never skips) and, when the new stage has
notify=true and was not notified before, sends the HTML email.

>>> Threshold VALUES are placeholders (see scripts/seed_firestore.py) — to tune together.
>>> Criteria KEYS are interpreted here. Add a key = add a check in `_check`.

Metrics are gathered in `collect_metrics()` from: problem_clusters, opportunity_scoring,
competitor_signals, validation_experiments.
"""
from __future__ import annotations

import logging
from typing import Any

from app import db
from app.services import notify

log = logging.getLogger("funnel")


# ----------------------------------------------------------------------------
# metrics
# ----------------------------------------------------------------------------
def _experiment_metrics(cluster_id: str) -> dict[str, Any]:
    exps = db.list_all(db.VALIDATION_EXPERIMENTS, cluster_id=cluster_id)
    done = [e for e in exps if e.get("status") == "done"]
    m: dict[str, Any] = {"n_experiments_done": len(done)}

    def _sum(t: str, key: str) -> float:
        return float(sum((e.get("metrics") or {}).get(key, 0) or 0 for e in done if e.get("type") == t))

    n_int = _sum("interview", "n_interviews")
    m["interviews"] = n_int
    m["interview_confirm_rate"] = (_sum("interview", "n_confirmed_problem") / n_int) if n_int else 0.0
    m["interview_paying_rate"] = (_sum("interview", "n_currently_paying") / n_int) if n_int else 0.0

    visitors = _sum("landing_page", "visitors") + _sum("ads_smoke", "clicks")
    signups = _sum("landing_page", "signups") + _sum("ads_smoke", "signups")
    m["landing_visitors"] = visitors
    m["landing_signup_rate"] = (signups / visitors) if visitors else 0.0

    pv = _sum("presale", "visitors")
    paid = _sum("presale", "paid")
    m["presale_paid"] = paid
    m["presale_conversion"] = (paid / pv) if pv else 0.0
    m["presale_revenue_eur"] = _sum("presale", "revenue_eur")
    return m


def collect_metrics(cluster: dict, opp: dict) -> dict[str, Any]:
    m: dict[str, Any] = {
        "signals": cluster.get("signal_count") or 0,
        "sources": cluster.get("distinct_sources") or 0,
        "authors": cluster.get("distinct_authors") or 0,
        "heuristic_avg": cluster.get("heuristic_avg") or 0.0,
        "velocity_30d": cluster.get("velocity_30d"),
        "market_components_complete": bool(opp.get("market_components_complete")),
        "tam_eur": opp.get("tam_eur"),
        "sam_eur": opp.get("sam_eur"),
        "competitors_checked": opp.get("competitor_count") is not None and opp.get("saturation") is not None,
        "competitor_count": opp.get("competitor_count"),
        "saturation": opp.get("saturation"),
        "founder_fit": opp.get("founder_fit"),
        "channel_reachable": opp.get("acquisition_channel_reachable"),
        "why_now": bool((opp.get("why_now") or "").strip()),
    }
    m.update(_experiment_metrics(cluster["id"]))
    return m


# ----------------------------------------------------------------------------
# criteria evaluation
# ----------------------------------------------------------------------------
def _check(key: str, threshold: Any, m: dict[str, Any]) -> tuple[bool, str]:
    """Return (passed, human-readable evidence)."""
    def ge(metric: str) -> tuple[bool, str]:
        v = m.get(metric)
        ok = v is not None and float(v) >= float(threshold)
        return ok, f"{metric}={v} (>= {threshold})"

    def le(metric: str) -> tuple[bool, str]:
        v = m.get(metric)
        ok = v is not None and float(v) <= float(threshold)
        return ok, f"{metric}={v} (<= {threshold})"

    def req(metric: str) -> tuple[bool, str]:
        v = bool(m.get(metric))
        return (v if threshold else True), f"{metric}={v}"

    table = {
        "min_signals": lambda: ge("signals"),
        "min_sources": lambda: ge("sources"),
        "min_authors": lambda: ge("authors"),
        "min_heuristic_avg": lambda: ge("heuristic_avg"),
        "min_velocity_30d": lambda: ge("velocity_30d"),
        "require_market_components": lambda: req("market_components_complete"),
        "min_sam_eur": lambda: ge("sam_eur"),
        "min_tam_eur": lambda: ge("tam_eur"),
        "require_competitors_checked": lambda: req("competitors_checked"),
        "max_competitor_count": lambda: le("competitor_count"),
        "saturation_not_in": lambda: (m.get("saturation") is not None and m.get("saturation") not in (threshold or []), f"saturation={m.get('saturation')} (not in {threshold})"),
        "min_founder_fit": lambda: ge("founder_fit"),
        "require_channel_reachable": lambda: req("channel_reachable"),
        "require_why_now": lambda: req("why_now"),
        "min_interviews": lambda: ge("interviews"),
        "min_interview_confirm_rate": lambda: ge("interview_confirm_rate"),
        "min_interview_paying_rate": lambda: ge("interview_paying_rate"),
        "min_landing_visitors": lambda: ge("landing_visitors"),
        "min_landing_signup_rate": lambda: ge("landing_signup_rate"),
        "min_presale_paid": lambda: ge("presale_paid"),
        "min_presale_conversion": lambda: ge("presale_conversion"),
    }
    fn = table.get(key)
    if fn is None:
        log.warning("unknown criteria key %r — ignored", key)
        return True, f"{key}: unknown key ignored"
    return fn()


def check_stage(stage: dict, m: dict[str, Any]) -> tuple[bool, dict[str, str]]:
    evidence: dict[str, str] = {}
    passed = True
    for key, threshold in (stage.get("criteria") or {}).items():
        ok, ev = _check(key, threshold, m)
        evidence[key] = ("✔ " if ok else "✘ ") + ev
        passed = passed and ok
    return passed, evidence


# ----------------------------------------------------------------------------
# scoring (placeholder formula — refine together)
# ----------------------------------------------------------------------------
def compute_overall_score(m: dict[str, Any]) -> float:
    """0-100. Weights are placeholders."""
    score = 0.0
    score += min(m["signals"] / 50, 1) * 15                      # demand volume
    score += min(m["heuristic_avg"] / 5, 1) * 15                  # willingness-to-pay proxies
    score += {"blue": 20, "purple": 10, "red": 0}.get(m.get("saturation") or "", 0)
    sam = m.get("sam_eur") or 0
    score += (0 if sam < 5e6 else 10 if sam < 2e7 else 15 if sam < 1e8 else 20)
    score += ((m.get("founder_fit") or 0) / 5) * 15
    score += 5 if m.get("channel_reachable") else 0
    score += 5 if m.get("why_now") else 0
    score += min(m.get("interview_confirm_rate", 0), 1) * 5
    return round(score, 1)


# ----------------------------------------------------------------------------
# evaluation
# ----------------------------------------------------------------------------
def get_stages() -> list[dict]:
    stages = db.list_all(db.FUNNEL_STAGES)
    return sorted(stages, key=lambda s: s.get("position", 0))


def ensure_opportunity(cluster_id: str) -> dict:
    opp = db.get(db.OPPORTUNITY_SCORING, cluster_id)
    if opp:
        return opp
    db.upsert(
        db.OPPORTUNITY_SCORING,
        cluster_id,
        {"cluster_id": cluster_id, "funnel_stage": "signal_collected", "stage_entered_at": db.now(),
         "stage_history": [{"stage": "signal_collected", "at": db.now().isoformat(), "reason": "created"}],
         "notified_stages": [], "is_archived": False, "market_estimates": {}, "created_at": db.now()},
    )
    return db.get(db.OPPORTUNITY_SCORING, cluster_id)


def evaluate(cluster_id: str, send_notifications: bool = True) -> dict:
    cluster = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    if not cluster:
        return {"cluster_id": cluster_id, "error": "cluster not found"}
    opp = ensure_opportunity(cluster_id)
    if opp.get("is_archived"):
        return {"cluster_id": cluster_id, "stage": opp.get("funnel_stage"), "archived": True}

    stages = get_stages()
    keys = [s["key"] for s in stages]
    current = opp.get("funnel_stage") or keys[0]
    idx = keys.index(current) if current in keys else 0
    advanced: list[str] = []
    notified: list[str] = []
    last_evidence: dict[str, str] = {}

    m = collect_metrics(cluster, opp)
    # advance one stage at a time while criteria hold
    while idx + 1 < len(stages):
        nxt = stages[idx + 1]
        ok, evidence = check_stage(nxt, m)
        last_evidence = evidence
        if not ok:
            break
        idx += 1
        history = list(opp.get("stage_history") or [])
        history.append({"stage": nxt["key"], "at": db.now().isoformat(), "reason": "; ".join(evidence.values())[:500]})
        opp.update({"funnel_stage": nxt["key"], "stage_entered_at": db.now(), "stage_history": history})
        advanced.append(nxt["key"])
        if nxt.get("notify") and nxt["key"] not in (opp.get("notified_stages") or []):
            if send_notifications:
                status = notify.notify_stage(cluster, {**opp, "overall_score": compute_overall_score(m)}, nxt, evidence)
                if status == "sent":
                    opp["notified_stages"] = list(opp.get("notified_stages") or []) + [nxt["key"]]
                    notified.append(nxt["key"])
        if nxt.get("is_terminal"):
            break

    opp["overall_score"] = compute_overall_score(m)
    db.upsert(db.OPPORTUNITY_SCORING, cluster_id, {
        k: opp[k] for k in ("funnel_stage", "stage_entered_at", "stage_history", "notified_stages", "overall_score")
    })
    return {
        "cluster_id": cluster_id, "name": cluster.get("name"), "stage": opp["funnel_stage"],
        "advanced": advanced, "notified": notified, "overall_score": opp["overall_score"],
        "blocking_criteria": {k: v for k, v in last_evidence.items() if v.startswith("✘")},
    }


def evaluate_all(send_notifications: bool = True) -> list[dict]:
    return [evaluate(c["id"], send_notifications) for c in db.list_all(db.PROBLEM_CLUSTERS)]


# ----------------------------------------------------------------------------
# cluster stats refresh (called when signals are attached; also by LLM stage later)
# ----------------------------------------------------------------------------
def refresh_cluster_stats(cluster_id: str) -> dict:
    from datetime import timedelta

    client = db.get_db()
    sub = client.collection(db.PROBLEM_CLUSTERS).document(cluster_id).collection(db.CLUSTER_SIGNALS_SUB)
    signal_ids = [d.id for d in sub.stream()]
    sigs = []
    for chunk in db.chunks(signal_ids, 300):
        refs = [client.collection(db.RAW_SIGNALS).document(i) for i in chunk]
        sigs.extend(d for d in (db.doc_to_dict(s) for s in client.get_all(refs)) if d)
    if not sigs:
        stats = {"signal_count": 0, "distinct_sources": 0, "distinct_authors": 0, "heuristic_avg": 0.0}
    else:
        dates = [s["published_at"] for s in sigs if s.get("published_at")]
        now = db.now()
        last30 = sum(1 for d in dates if d >= now - timedelta(days=30))
        prev30 = sum(1 for d in dates if now - timedelta(days=60) <= d < now - timedelta(days=30))
        stats = {
            "signal_count": len(sigs),
            "distinct_sources": len({s["source"] for s in sigs}),
            "distinct_authors": len({s.get("author_hash") for s in sigs if s.get("author_hash")}),
            "heuristic_avg": round(sum(s.get("heuristic_score") or 0 for s in sigs) / len(sigs), 2),
            "first_seen": min(dates) if dates else None,
            "last_seen": max(dates) if dates else None,
            "velocity_30d": (last30 / prev30) if prev30 else (float(last30) if last30 else None),
        }
    db.upsert(db.PROBLEM_CLUSTERS, cluster_id, stats)
    return stats
