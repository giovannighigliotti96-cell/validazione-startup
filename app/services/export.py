"""
Human-readable export of raw_signals (CSV / JSON) for manual import into
recruiting platforms (User Interviews, Respondent, Koji...).

Privacy: author usernames are never stored; author_hash is NOT exported either.
The reviewer gets: where it was said, when, what, how much traction, which
willingness-to-pay flags fired. `source_url` lets you open the original.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime

from app import db

EXPORT_COLUMNS = [
    "id", "source", "type", "channel", "vertical", "keyword_set", "date", "title", "excerpt", "full_text",
    "score", "comments", "rating", "wtp_score",
    "uses_existing_tool", "has_diy_workaround", "asks_for_tool", "quantifies_cost_or_time", "frustrated",
    "search_keyword", "source_url", "problem_statement_llm",
]


def _yes(v) -> str:
    return "Yes" if v else ""


def _fmt_date(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    return str(v or "")[:10]


def _row(sig: dict, ks_names: dict[str, dict]) -> dict:
    ks = ks_names.get(sig.get("keyword_set_id") or "", {})
    text = (sig.get("text") or "").replace("\r", " ").strip()
    return {
        "id": sig["id"],
        "source": sig.get("source"),
        "type": sig.get("signal_type"),
        "channel": sig.get("channel"),
        "vertical": ks.get("vertical"),
        "keyword_set": ks.get("name"),
        "date": _fmt_date(sig.get("published_at")),
        "title": sig.get("title") or "",
        "excerpt": (text[:280] + "…") if len(text) > 280 else text,
        "full_text": text,
        "score": sig.get("score"),
        "comments": sig.get("num_comments"),
        "rating": sig.get("rating"),
        "wtp_score": sig.get("heuristic_score"),
        "uses_existing_tool": _yes(sig.get("mentions_existing_tool")),
        "has_diy_workaround": _yes(sig.get("mentions_diy_workaround")),
        "asks_for_tool": _yes(sig.get("asks_for_recommendation")),
        "quantifies_cost_or_time": _yes(sig.get("mentions_cost_or_time")),
        "frustrated": _yes(sig.get("expresses_frustration")),
        "search_keyword": sig.get("keyword"),
        "source_url": sig.get("url"),
        "problem_statement_llm": sig.get("llm_problem_statement") or "",
    }


def query_signals(
    keyword_set_id: str | None = None,
    source: str | None = None,
    min_wtp: int = 0,
    since: datetime | None = None,
    limit: int = 5000,
) -> list[dict]:
    q = db.get_db().collection(db.RAW_SIGNALS)
    if keyword_set_id:
        q = q.where("keyword_set_id", "==", keyword_set_id)
    if source:
        q = q.where("source", "==", source)
    if min_wtp:
        q = q.where("heuristic_score", ">=", min_wtp)
    if since:
        q = q.where("published_at", ">=", since)
    rows = [db.doc_to_dict(s) for s in q.limit(limit).stream()]
    rows.sort(key=lambda r: (r.get("heuristic_score") or 0, r.get("score") or 0), reverse=True)
    return rows


def export_rows(**filters) -> list[dict]:
    ks_names = {k["id"]: k for k in db.list_all(db.KEYWORD_SETS)}
    return [_row(s, ks_names) for s in query_signals(**filters)]


def to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=EXPORT_COLUMNS, extrasaction="ignore", quoting=csv.QUOTE_ALL)
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def to_json(rows: list[dict]) -> str:
    return json.dumps(rows, ensure_ascii=False, indent=2, default=str)
