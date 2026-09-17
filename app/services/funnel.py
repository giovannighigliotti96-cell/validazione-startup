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
from app.config import get_settings
from app.services import notify

log = logging.getLogger("funnel")
_RANK = {"low": 0, "medium": 1, "high": 2}


# ----------------------------------------------------------------------------
# metrics
# ----------------------------------------------------------------------------
def _experiment_metrics(cluster_id: str) -> dict[str, Any]:
    exps = db.list_all(db.VALIDATION_EXPERIMENTS, cluster_id=cluster_id)
    # interviews count when done; live tests (hosted landing / presale) count while running too
    done = [e for e in exps if e.get("status") == "done" or (e.get("status") == "running" and e.get("type") in ("landing_page", "ads_smoke", "presale"))]
    m: dict[str, Any] = {"n_experiments_done": len(done)}

    def _sum(t: str, key: str) -> float:
        return float(sum((e.get("metrics") or {}).get(key, 0) or 0 for e in done if e.get("type") == t))

    # Interviews: individual records (problem_clusters/{id}/interviews, LLM-extracted) + aggregate experiments
    ivs = [d.to_dict() or {} for d in db.get_db().collection(db.PROBLEM_CLUSTERS).document(cluster_id).collection("interviews").stream()]
    n_int = len(ivs) + _sum("interview", "n_interviews")
    confirmed = sum(1 for i in ivs if i.get("confirmed_problem")) + _sum("interview", "n_confirmed_problem")
    paying = sum(1 for i in ivs if i.get("currently_paying")) + _sum("interview", "n_currently_paying")
    spontaneous = sum(1 for i in ivs if i.get("spontaneous")) + _sum("interview", "n_spontaneous")
    quantified = sum(1 for i in ivs if (i.get("quantified_cost") or "").strip()) + _sum("interview", "n_quantified_cost")
    m["interviews"] = n_int
    m["interview_confirm_rate"] = (confirmed / n_int) if n_int else 0.0
    m["interview_paying_rate"] = (paying / n_int) if n_int else 0.0
    m["interview_spontaneous_rate"] = (spontaneous / n_int) if n_int else 0.0
    m["interview_quantified_cost_count"] = quantified

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
        # language-agnostic willingness-to-pay: best of regex heuristic (EN) and LLM-derived proxy (any language)
        "wtp_avg": max(cluster.get("heuristic_avg") or 0.0, cluster.get("llm_wtp_avg") or 0.0),
        "velocity_30d": cluster.get("velocity_30d"),
        "recent_share": cluster.get("recent_share_90d"),  # 90 days on real dates: a review from June still means the pain is alive
        "dominant_attack_vector": cluster.get("dominant_attack_vector"),
        "attackable_share": cluster.get("attackable_share") or 0.0,
        "unanswered_asks": cluster.get("unanswered_ask_count") or 0,
        "market_components_complete": bool(opp.get("market_components_complete")),
        "market_confidence": opp.get("market_confidence"),
        "leader_reviews": opp.get("leader_reviews"),
        "dead_products_found": opp.get("dead_products_found"),
        "barriers": opp.get("barriers") or {},
        "tam_eur": opp.get("tam_eur"),
        "sam_eur": opp.get("sam_eur"),
        "competitors_checked": opp.get("competitor_count") is not None and opp.get("saturation") is not None,
        "competitor_count": opp.get("competitor_count"),
        "saturation": opp.get("saturation"),
        "founder_fit": opp.get("founder_fit"),
        "channel_reachable": opp.get("acquisition_channel_reachable"),
        "channel_type": opp.get("acquisition_channel_type"),
        "price_eur_year": (float(opp["expected_price_eur_month"]) * 12) if opp.get("expected_price_eur_month") is not None else None,
        "gross_margin_pct": opp.get("gross_margin_pct"),
        "delivery_model": opp.get("delivery_model"),
        "mvp_weeks_solo": opp.get("mvp_weeks_solo"),
        "why_now": bool((opp.get("why_now") or "").strip()),
    }
    eg = opp.get("execution_gap") or {}
    h, lk, sw, ed = eg.get("category_health") or {}, eg.get("lockin") or {}, eg.get("switch_intent") or {}, eg.get("edge") or {}
    m.update({
        "path": opp.get("path") or "new_problem",
        "eg_analyzed": bool(eg.get("analyzed_at")),
        "eg_avg_core_rating": h.get("avg_core_rating"), "eg_avg_store_rating": h.get("avg_store_rating"), "eg_n_rated": h.get("n_rated") or 0,
        "eg_excellent_leader": h.get("excellent_leader_exists"),
        "eg_lockin_level": lk.get("lockin_level"), "eg_do_they_switch": lk.get("do_they_switch"),
        "eg_seeking_share": sw.get("seeking_share"), "eg_alternative_threads": sw.get("alternative_threads_found"),
        "eg_edge_structural": ed.get("edge_is_structural"), "eg_edge": ed.get("execution_edge"),
        "eg_weeks_to_parity": ed.get("weeks_to_parity_on_core_job"),
    })
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
        "min_wtp_avg": lambda: ge("wtp_avg"),
        "min_velocity_30d": lambda: ge("velocity_30d"),
        "min_recent_share": lambda: ge("recent_share"),  # share of the cluster's DATED signals published in the last 90 days
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
        "min_presale_revenue_eur": lambda: ge("presale_revenue_eur"),
        # --- precision filters ---
        "attack_vector_in": lambda: (m.get("dominant_attack_vector") in (threshold or []), f"attack_vector={m.get('dominant_attack_vector')} (in {threshold})"),
        "min_attackable_share": lambda: ge("attackable_share"),
        "min_unanswered_asks": lambda: ge("unanswered_asks"),
        "min_market_confidence": lambda: (_RANK.get(m.get("market_confidence") or "", -1) >= _RANK.get(threshold, 0), f"market_confidence={m.get('market_confidence')} (>= {threshold})"),
        "max_leader_reviews": lambda: (m.get("leader_reviews") is None or float(m.get("leader_reviews")) <= float(threshold), f"leader_reviews={m.get('leader_reviews')} (<= {threshold} or unknown)"),
        "require_dead_product_check": lambda: (m.get("dead_products_found") is not None, f"dead_products_found={m.get('dead_products_found')}"),
        "barriers_must_be_false": lambda: (all(not (m.get("barriers") or {}).get(b) for b in (threshold or [])), "barriers=" + str({b: (m.get("barriers") or {}).get(b) for b in (threshold or [])})),
        # --- economics (a blue ocean without margin is not a business) ---
        "min_gross_margin_pct": lambda: ge("gross_margin_pct"),
        "delivery_model_not_in": lambda: (m.get("delivery_model") is not None and m.get("delivery_model") not in (threshold or []), f"delivery_model={m.get('delivery_model')} (not in {threshold})"),
        "price_channel_consistent": lambda: _price_channel_ok(m, threshold),
        "max_mvp_weeks_solo": lambda: le("mvp_weeks_solo"),
        # --- execution-gap path ---
        "require_eg_analyzed": lambda: req("eg_analyzed"),
        "max_eg_core_rating": lambda: (m.get("eg_avg_core_rating") is not None and float(m["eg_avg_core_rating"]) <= float(threshold), f"avg core rating={m.get('eg_avg_core_rating')} (<= {threshold})"),
        "max_eg_store_rating": lambda: (m.get("eg_avg_store_rating") is None or float(m["eg_avg_store_rating"]) <= float(threshold), f"avg store rating={m.get('eg_avg_store_rating')} (<= {threshold} or n/a)"),
        "min_eg_rated": lambda: ge("eg_n_rated"),
        "require_no_excellent_leader": lambda: (m.get("eg_excellent_leader") is False, f"excellent_leader_exists={m.get('eg_excellent_leader')}"),
        "eg_lockin_not_in": lambda: (m.get("eg_lockin_level") is not None and m.get("eg_lockin_level") not in (threshold or []), f"lockin={m.get('eg_lockin_level')} (not in {threshold})"),
        "eg_switch_in": lambda: (m.get("eg_do_they_switch") in (threshold or []), f"do_they_switch={m.get('eg_do_they_switch')} (in {threshold})"),
        "min_eg_seeking_share": lambda: ge("eg_seeking_share"),
        "require_eg_structural_edge": lambda: (bool(m.get("eg_edge_structural")) and (m.get("eg_edge") or "none").lower() != "none", f"edge_structural={m.get('eg_edge_structural')}: {(m.get('eg_edge') or '')[:60]}"),
        "max_eg_weeks_to_parity": lambda: le("eg_weeks_to_parity"),
        "min_interview_spontaneous_rate": lambda: ge("interview_spontaneous_rate"),
        "min_interview_quantified_cost_count": lambda: ge("interview_quantified_cost_count"),
    }
    fn = table.get(key)
    if fn is None:
        log.warning("unknown criteria key %r — ignored", key)
        return True, f"{key}: unknown key ignored"
    return fn()


def _price_channel_ok(m: dict[str, Any], threshold: Any) -> tuple[bool, str]:
    """Price per customer must cover the acquisition channel: founder outbound needs a high ticket; self-serve can be cheap.
    threshold = {"outbound": 1200, "partnerships": 900, "seo_content": 300, "community": 300, "self_serve_marketplace": 240} (EUR/year)."""
    price = m.get("price_eur_year")
    ch = m.get("channel_type")
    floors = threshold if isinstance(threshold, dict) else {}
    need = floors.get(ch or "", floors.get("outbound", 1200))
    if price is None or ch is None:
        return False, f"price/year={price}, channel={ch} (needs >= {need} for that channel)"
    return float(price) >= float(need), f"price/year={price:.0f} vs channel {ch} (needs >= {need})"


def stage_criteria(stage: dict, m: dict[str, Any]) -> dict:
    """Path-aware: execution-gap opportunities use `criteria_execution_gap` when the stage defines it."""
    if m.get("path") == "execution_gap" and stage.get("criteria_execution_gap") is not None:
        return stage["criteria_execution_gap"]
    return stage.get("criteria") or {}


def check_stage(stage: dict, m: dict[str, Any]) -> tuple[bool, dict[str, str]]:
    evidence: dict[str, str] = {}
    passed = True
    for key, threshold in stage_criteria(stage, m).items():
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
    score += min(m["signals"] / 50, 1) * 10                      # demand volume
    score += min(m.get("wtp_avg", m["heuristic_avg"]) / 5, 1) * 15   # willingness-to-pay proxies
    score += {"blue": 15, "purple": 8, "red": 0}.get(m.get("saturation") or "", 0)
    score += {"no_solution_exists": 10, "feature_gap": 7, "price_complaint": 2}.get(m.get("dominant_attack_vector") or "", 0)
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
    opp.setdefault("funnel_stage", "signal_collected"); opp.setdefault("stage_history", []); opp.setdefault("notified_stages", [])
    opp.setdefault("stage_entered_at", db.now())
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
        if nxt["key"] == "founder_fit_checked":
            # the founder's work starts here: prepare recruiting pack + testable offer automatically (5 strong calls)
            try:
                from app.services import analysis as _an, offer as _offer

                _an.budget.reset()
                if not cluster.get("recruiting_pack"):
                    _an.recruiting_pack(cluster_id)
                if not (db.get(db.OPPORTUNITY_SCORING, cluster_id) or {}).get("offer"):
                    _offer.generate_offer(cluster_id)
                cluster = db.get(db.PROBLEM_CLUSTERS, cluster_id) or cluster
                opp.update({k: v for k, v in (db.get(db.OPPORTUNITY_SCORING, cluster_id) or {}).items() if k in ("offer", "premortem")})
            except Exception as e:  # noqa: BLE001
                log.warning("auto recruiting pack / offer failed: %s", e)
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
    from collections import Counter
    from datetime import timedelta

    client = db.get_db()
    sub = client.collection(db.PROBLEM_CLUSTERS).document(cluster_id).collection(db.CLUSTER_SIGNALS_SUB)
    signal_ids = [d.id for d in sub.stream()]
    sigs = []
    for chunk in db.chunks(signal_ids, 300):
        refs = [client.collection(db.RAW_SIGNALS).document(i) for i in chunk]
        sigs.extend(d for d in (db.doc_to_dict(s) for s in client.get_all(refs)) if d)
    ks_vert = {k["id"]: k.get("vertical") for k in db.list_all(db.KEYWORD_SETS)}
    for s_ in sigs:
        s_["_vertical"] = ks_vert.get(s_.get("keyword_set_id"))
    if not sigs:
        stats = {"signal_count": 0, "distinct_sources": 0, "distinct_authors": 0, "heuristic_avg": 0.0,
                 "attack_vector_dist": {}, "dominant_attack_vector": None, "attackable_share": 0.0, "unanswered_ask_count": 0}
    else:
        # honest dates only: search-engine snippets (reddit_search) carry no date and were stored with the scrape time,
        # which made every one of them "recent" while store reviews / HN with real dates looked old
        def _real_date(s):
            p, sc = s.get("published_at"), s.get("scraped_at")
            return p if p and not (sc and abs((p - sc).total_seconds()) < 600) else None
        dates = [d for d in (_real_date(s) for s in sigs) if d]
        now = db.now()
        last30 = sum(1 for d in dates if d >= now - timedelta(days=30))
        last90 = sum(1 for d in dates if d >= now - timedelta(days=90))
        prev30 = sum(1 for d in dates if now - timedelta(days=60) <= d < now - timedelta(days=30))
        def _llm_wtp(sig: dict) -> float | None:
            md = sig.get("llm_metadata") or {}
            if sig.get("llm_urgency") is None:
                return None
            return min(10.0, float(sig["llm_urgency"]) * 1.2 + (2.5 if (md.get("quantified_pain") or "").strip() else 0) + (1.5 if md.get("mentioned_tools") else 0))
        llm_vals = [v for v in (_llm_wtp(s) for s in sigs) if v is not None]
        # REAL, NOT INVENTED: keep verbatim quotes (with links) so every cluster is traceable to what people actually wrote
        ranked = sorted(sigs, key=lambda s: ((s.get("heuristic_score") or 0) + (s.get("llm_urgency") or 0), s.get("score") or 0), reverse=True)
        evidence = [{"quote": (s.get("text") or "")[:240].replace("\n", " ").strip(), "url": s.get("url"), "source": s.get("source"),
                     "vertical": s.get("_vertical")} for s in ranked[:6] if (s.get("text") or "").strip()]
        av = Counter(s.get("attack_vector") for s in sigs if s.get("attack_vector"))
        n_av = sum(av.values()) or 1
        stats = {
            "attack_vector_dist": dict(av),
            "evidence_quotes": evidence,
            "by_keyword_set": dict(Counter(s.get("keyword_set_id") for s in sigs if s.get("keyword_set_id"))),
            "authors_by_keyword_set": {k: len({s.get("author_hash") or s.get("external_id") for s in sigs if s.get("keyword_set_id") == k}) for k in {s.get("keyword_set_id") for s in sigs if s.get("keyword_set_id")}},
            "dominant_attack_vector": av.most_common(1)[0][0] if av else None,
            "attackable_share": round(sum(v for k, v in av.items() if k in ("feature_gap", "no_solution_exists")) / n_av, 2),
            "unanswered_ask_count": sum(1 for s in sigs if s.get("unanswered_ask")),
            "signal_count": len(sigs),
            "distinct_sources": len({s["source"] for s in sigs}),
            "distinct_authors": len({s.get("author_hash") for s in sigs if s.get("author_hash")}),
            "heuristic_avg": round(sum(s.get("heuristic_score") or 0 for s in sigs) / len(sigs), 2),
            "llm_wtp_avg": round(sum(llm_vals) / len(llm_vals), 2) if llm_vals else None,
            "first_seen": min(dates) if dates else None,
            "last_seen": max(dates) if dates else None,
            "velocity_30d": (last30 / prev30) if prev30 else (float(last30) if last30 else None),
            "recent_share_30d": round(last30 / len(dates), 2) if dates else None,
            "recent_share_90d": round(last90 / len(dates), 2) if dates else None,
            "dated_signals": len(dates),
        }
    db.upsert(db.PROBLEM_CLUSTERS, cluster_id, stats)
    return stats


# ----------------------------------------------------------------------------
# weekly digest (human-in-the-loop calibration)
# ----------------------------------------------------------------------------
def build_digest(top_n: int = 5) -> dict:
    from datetime import timedelta

    stages = {st["key"]: st for st in get_stages()}
    keys = [st["key"] for st in get_stages()]
    clusters = {c["id"]: c for c in db.list_all(db.PROBLEM_CLUSTERS)}
    opps = [o for o in db.list_all(db.OPPORTUNITY_SCORING) if not o.get("is_archived") and o["cluster_id"] in clusters]
    rows = []
    for o in opps:
        c = clusters[o["cluster_id"]]
        m = collect_metrics(c, o)
        idx = keys.index(o.get("funnel_stage")) if o.get("funnel_stage") in keys else 0
        blocking = {}
        blocking_detail = []
        if idx + 1 < len(keys):
            nxt = stages[keys[idx + 1]]
            _, ev = check_stage(nxt, m)
            blocking = {k: v for k, v in ev.items() if v.startswith("✘")}
            blocking_detail = [(k, stage_criteria(nxt, m).get(k)) for k in blocking]
        rows.append({"cluster": c, "opp": o, "score": compute_overall_score(m), "stage": o.get("funnel_stage"),
                     "next_stage": keys[idx + 1] if idx + 1 < len(keys) else None, "blocking": blocking,
                     "blocking_detail": blocking_detail, "metrics": m})
    rows.sort(key=lambda r: r["score"], reverse=True)
    # prefer attackable clusters at the top of the digest
    rows.sort(key=lambda r: (r["metrics"].get("dominant_attack_vector") in ("feature_gap", "no_solution_exists"), r["score"]), reverse=True)
    week_ago = db.now() - timedelta(days=7)
    new_signals = sum(1 for _ in db.get_db().collection(db.RAW_SIGNALS).where("scraped_at", ">=", week_ago).select([]).stream())
    stage_counts: dict[str, int] = {}
    for o in opps:
        stage_counts[o.get("funnel_stage")] = stage_counts.get(o.get("funnel_stage"), 0) + 1
    top = rows[:top_n]
    # Italian one-liners for the top clusters (one strong-model call; silently skipped on failure)
    try:
        from app.services import analysis

        analysis.budget.reset()
        items = "\n".join(f"{i}. {r['cluster'].get('name')} :: {r['cluster'].get('problem_statement') or ''} :: persona: {r['cluster'].get('persona') or ''}" for i, r in enumerate(top))
        data = analysis.llm_json(
            "Per ogni cluster scrivi in ITALIANO, per un founder non tecnico: 'titolo' (max 8 parole, chiaro) e 'spiegazione' "
            "(1-2 frasi: chi ha il problema, cosa fa oggi a mano, perché gli costa). Niente gergo, niente inglese salvo nomi di prodotti.\n"
            "Rispondi con JSON {\"items\": [{\"idx\": 0, \"titolo\": \"...\", \"spiegazione\": \"...\"}]}\n\nCLUSTER:\n" + items, strong=True, temperature=0.3)
        for it in data.get("items", []):
            try:
                top[int(it["idx"])]["it"] = {"titolo": it.get("titolo"), "spiegazione": it.get("spiegazione")}
            except (KeyError, ValueError, IndexError, TypeError):
                continue
    except Exception as e:  # noqa: BLE001
        log.warning("digest italian summaries skipped: %s", e)
    attackable = sum(1 for r in rows if r["metrics"].get("dominant_attack_vector") in ("feature_gap", "no_solution_exists"))
    # main reason clusters are stuck, across all attackable clusters
    from collections import Counter
    reasons = Counter(k for r in rows if r["metrics"].get("dominant_attack_vector") in ("feature_gap", "no_solution_exists") for k in r["blocking"])
    arb = sorted(db.list_all("us_launches", limit=200), key=lambda r: str(r.get("checked_at") or ""), reverse=True)
    arb = [r for r in arb if r.get("verdict") in ("candidate", "watchlist_no_it_signals")][:6]
    return {"top": top, "total_clusters": len(opps), "stage_counts": stage_counts, "new_signals_7d": new_signals, "arbitrage": arb,
            "attackable": attackable, "passed_stage2": sum(1 for r in rows if r["stage"] != "signal_collected"),
            "main_reasons": reasons.most_common(3)}


def send_weekly_digest() -> str:
    d = build_digest()
    subject, html = notify.render_digest_email(d)
    status, err = notify.send_email(subject, html)
    db.upsert(db.NOTIFICATIONS, None, {"cluster_id": None, "stage_key": "digest", "channel": "email", "subject": subject,
                                        "recipient": get_settings().notify_email_to, "status": status, "error": err, "sent_at": db.now()})
    return status


# ----------------------------------------------------------------------------
# calibration report: where do clusters die, per vertical, and why
# ----------------------------------------------------------------------------
def calibration_report() -> dict:
    from collections import Counter, defaultdict

    stages = get_stages()
    keys = [s["key"] for s in stages]
    by_key = {s["key"]: s for s in stages}
    clusters = {c["id"]: c for c in db.list_all(db.PROBLEM_CLUSTERS)}
    per_vertical: dict[str, dict] = defaultdict(lambda: {"clusters": 0, "archived": 0, "by_stage": Counter(), "blocking": Counter(), "attack": Counter()})
    archive_reasons: list[dict] = []
    for o in db.list_all(db.OPPORTUNITY_SCORING):
        c = clusters.get(o["cluster_id"])
        if not c:
            continue
        v = per_vertical[c.get("vertical") or "?"]
        v["clusters"] += 1
        v["attack"][c.get("dominant_attack_vector") or "none"] += 1
        if o.get("is_archived"):
            v["archived"] += 1
            archive_reasons.append({"cluster": c.get("name"), "vertical": c.get("vertical"), "reason": o.get("archive_reason")})
            continue
        stage = o.get("funnel_stage") or keys[0]
        v["by_stage"][stage] += 1
        idx = keys.index(stage) if stage in keys else 0
        if idx + 1 < len(keys):
            _, ev = check_stage(by_key[keys[idx + 1]], collect_metrics(c, o))
            for k, val in ev.items():
                if val.startswith("✘"):
                    v["blocking"][k] += 1
    out = {}
    for name, v in per_vertical.items():
        out[name] = {"clusters": v["clusters"], "archived": v["archived"], "by_stage": dict(v["by_stage"]),
                     "top_blocking_criteria": v["blocking"].most_common(4), "attack_vectors": dict(v["attack"])}
    total_block = Counter()
    for v in per_vertical.values():
        total_block.update(v["blocking"])
    return {"per_vertical": out, "overall_blocking": total_block.most_common(8), "archive_reasons": archive_reasons[-30:],
            "hint": "A criterion blocking >80% of attackable clusters across ALL verticals is a threshold problem; one blocking a single vertical is a data/source problem."}
