"""
=============================================================================
 TODO(LLM) — SEMANTIC LAYER. Everything here is a STUB.
 To be implemented with the Claude API (see README "Fase 2").
=============================================================================

Suggested pipeline (each step a separate function so they can be re-run):

 1. extract_problem(signal)            raw text -> {problem_statement, persona, urgency 1-5, frequency 1-5,
                                                   is_noise bool, mentioned_tools [..], quantified_pain str|null}
 2. cluster_signals(keyword_set_id)    embed problem statements (or ask Claude to group in batches)
                                       -> create/merge problem_clusters + problem_clusters/{id}/signals
 3. score_cluster(cluster)             urgency/frequency/wtp 0-10 from its signals + heuristic flags
 4. generate_mom_test_questions(cluster)  5-8 open, past-behaviour questions (never "would you use...")
 5. estimate_market_components(cluster)  Claude + web search -> market_estimates components with source_url
 6. find_competitors(cluster)          Claude + web search over G2/Capterra/PH -> competitor_signals
 7. assess_founder_fit(cluster, profile)  1-5 + reachable channel suggestion, given the founder profile in README

After 2-3 run `funnel.evaluate_all()` so opportunities advance automatically.

Model: use claude-sonnet-5 for bulk extraction (cost), claude-opus-5 for clustering/market
estimates (reasoning). Batch the extraction: 20-40 signals per call, JSON output.
"""
from __future__ import annotations

from typing import Any


class NotImplementedLLM(NotImplementedError):
    pass


def extract_problem(signal: dict) -> dict[str, Any]:
    # TODO(LLM): prompt Claude with signal["title"] + signal["text"]; return structured dict; set is_processed=True
    raise NotImplementedLLM("extract_problem: implement with Claude API")


def cluster_signals(keyword_set_id: str | None = None) -> list[str]:
    # TODO(LLM): group processed signals into problem_clusters; return created/updated cluster ids
    raise NotImplementedLLM("cluster_signals: implement with Claude API")


def score_cluster(cluster_id: str) -> dict[str, float]:
    # TODO(LLM): return {"urgency_score":..,"frequency_score":..,"wtp_score":..}
    raise NotImplementedLLM("score_cluster: implement with Claude API")


def generate_mom_test_questions(cluster_id: str) -> list[str]:
    # TODO(LLM): return 5-8 Mom-Test-compliant interview questions for problem_clusters[cluster_id]
    raise NotImplementedLLM("generate_mom_test_questions: implement with Claude API")


def estimate_market_components(cluster_id: str) -> list[dict]:
    # TODO(LLM+web): return [{"component":"n_entities","value":..,"unit":..,"source_url":..,"confidence":..}, ...]
    raise NotImplementedLLM("estimate_market_components: implement with Claude API + web search")


def find_competitors(cluster_id: str) -> list[dict]:
    # TODO(LLM+web): return competitor rows (G2/Capterra/PH) for competitor_signals
    raise NotImplementedLLM("find_competitors: implement with Claude API + web search")


def assess_founder_fit(cluster_id: str) -> dict[str, Any]:
    # TODO(LLM): return {"founder_fit": 1-5, "acquisition_channel": str, "acquisition_channel_reachable": bool, "barriers": {...}}
    raise NotImplementedLLM("assess_founder_fit: implement with Claude API")
