"""
Google Trends via pytrends (UNOFFICIAL, breaks intermittently, 429 after a few calls).
Mitigations: one snapshot per keyword per day (skip if exists), retries with
backoff, small batches. Values are RELATIVE (0-100 within the request) — always
include a stable reference keyword (e.g. "crm software") in the same keyword set
to compare against.

Config: {"keywords": [...], "geo": "US", "timeframe": "today 12-m"}
Writes to trend_snapshots (not raw_signals) — it's a metric, not a signal.
"""
from __future__ import annotations

from datetime import datetime, timezone

from tenacity import retry, stop_after_attempt, wait_exponential

from app import db
from app.config import get_settings
from app.scrapers.base import log, polite_sleep


def _slope(values: list[float]) -> float | None:
    n = len(values)
    if n < 2:
        return None
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(values) / n
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, values)) / den if den else None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=5, min=5, max=60))
def _interest(pt, kws: list[str], timeframe: str, geo: str):
    pt.build_payload(kws, timeframe=timeframe, geo=geo)
    df = pt.interest_over_time()
    related = {}
    try:
        related = pt.related_queries()
    except Exception:  # noqa: BLE001
        pass
    return df, related


def fetch(keyword_set: dict, config: dict) -> dict:
    """Returns stats dict {"captured": n, "skipped": m}. Persists directly."""
    if not get_settings().enable_trends:
        return {"captured": 0, "skipped": 0, "disabled": True}
    from pytrends.request import TrendReq

    geo = config.get("geo", "")
    timeframe = config.get("timeframe", "today 12-m")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    keywords = config.get("keywords", [])
    captured = skipped = 0
    pt = TrendReq(hl="en-US", tz=0, retries=0)  # retries>0 breaks with urllib3>=2 (method_whitelist); tenacity handles retries

    # pytrends allows max 5 keywords per payload
    for i in range(0, len(keywords), 5):
        batch = keywords[i : i + 5]
        todo = [k for k in batch if not db.get(db.TREND_SNAPSHOTS, db.safe_id(k, geo, timeframe, today))]
        if not todo:
            skipped += len(batch)
            continue
        try:
            df, related = _interest(pt, todo, timeframe, geo)
        except Exception as e:  # noqa: BLE001
            log.error("trends batch %s failed: %s", todo, e)
            continue
        if df is None or df.empty:
            continue
        for k in todo:
            if k not in df.columns:
                continue
            series = [{"date": idx.strftime("%Y-%m-%d"), "value": int(v)} for idx, v in df[k].items()]
            vals = [p["value"] for p in series]
            # weekly points: ~13 per 90 days
            last, prev = vals[-13:], vals[-26:-13]
            rq = related.get(k) or {}
            rel = {}
            for kind in ("rising", "top"):
                d = rq.get(kind)
                if d is not None and not d.empty:
                    rel[kind] = d.head(15).to_dict(orient="records")
            db.upsert(
                db.TREND_SNAPSHOTS,
                db.safe_id(k, geo, timeframe, today),
                {
                    "keyword_set_id": keyword_set.get("id"),
                    "keyword": k,
                    "geo": geo,
                    "timeframe": timeframe,
                    "captured_at": datetime.now(timezone.utc),
                    "series": series,
                    "slope_90d": _slope([float(v) for v in last]),
                    "mean_last_90d": sum(last) / len(last) if last else None,
                    "mean_prev_90d": sum(prev) / len(prev) if prev else None,
                    "related_queries": rel,
                },
            )
            captured += 1
        polite_sleep()
        polite_sleep()
    return {"captured": captured, "skipped": skipped}
