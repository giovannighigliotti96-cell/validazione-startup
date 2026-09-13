"""
TAM / SAM / SOM from decomposed components stored on opportunity_scoring.market_estimates.

  TAM = n_entities * annual_spend
  SAM = TAM * geo_share * segment_share
  SOM = SAM * capture_share

Each component: {"value", "unit", "source_url", "method", "confidence", "notes", "created_by", "updated_at"}.
Automation later = fill components (Claude + web search), formula stays the same.
"""
from __future__ import annotations

from app import db

COMPONENTS = ("n_entities", "annual_spend", "geo_share", "segment_share", "capture_share")
_DEFAULTS = {"geo_share": 1.0, "segment_share": 1.0, "capture_share": 0.01}
_RANK = {"low": 0, "medium": 1, "high": 2}


def compute(estimates: dict[str, dict]) -> dict:
    ne = (estimates.get("n_entities") or {}).get("value")
    sp = (estimates.get("annual_spend") or {}).get("value")
    if ne is None or sp is None:
        return {"tam_eur": None, "sam_eur": None, "som_eur": None, "market_components_complete": False, "market_confidence": None}
    g = (estimates.get("geo_share") or {}).get("value", _DEFAULTS["geo_share"])
    s = (estimates.get("segment_share") or {}).get("value", _DEFAULTS["segment_share"])
    c = (estimates.get("capture_share") or {}).get("value", _DEFAULTS["capture_share"])
    tam = float(ne) * float(sp)
    sam = tam * float(g) * float(s)
    som = sam * float(c)
    confs = [(estimates.get(k) or {}).get("confidence", "low") for k in ("n_entities", "annual_spend")]
    conf = min(confs, key=lambda x: _RANK.get(x, 0))
    return {"tam_eur": round(tam), "sam_eur": round(sam), "som_eur": round(som), "market_components_complete": True, "market_confidence": conf}


def set_component(cluster_id: str, component: str, payload: dict, created_by: str = "manual") -> dict:
    opp = db.get(db.OPPORTUNITY_SCORING, cluster_id) or {}
    estimates = dict(opp.get("market_estimates") or {})
    estimates[component] = {**payload, "created_by": created_by, "updated_at": db.now()}
    totals = compute(estimates)
    db.upsert(db.OPPORTUNITY_SCORING, cluster_id, {"cluster_id": cluster_id, "market_estimates": estimates, **totals})
    return {"market_estimates": estimates, **totals}
