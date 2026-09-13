"""
CLI entry point used by GitHub Actions (and for local runs).

  python -m scripts.run_pipeline scrape [--sources reddit,hackernews] [--sets id1,id2]
  python -m scripts.run_pipeline analyze          # Gemini: extract -> cluster -> enrich -> funnel
  python -m scripts.run_pipeline funnel
  python -m scripts.run_pipeline all
  python -m scripts.run_pipeline export --out exports/signals.csv [--min-wtp 3]
"""
from __future__ import annotations

import argparse
import json
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["scrape", "analyze", "funnel", "all", "export", "seed", "digest", "discover", "whynow"])
    p.add_argument("--sources", default=None)
    p.add_argument("--sets", default=None)
    p.add_argument("--out", default="exports/signals.csv")
    p.add_argument("--min-wtp", type=int, default=0)
    p.add_argument("--no-notify", action="store_true")
    a = p.parse_args()

    if a.command == "seed":
        from scripts.seed_firestore import main as seed

        seed()
        return

    from app.services import export, funnel, runner

    sources = a.sources.split(",") if a.sources else None
    sets = a.sets.split(",") if a.sets else None

    if a.command in ("scrape", "all"):
        res = runner.run_all(sets, sources, "github_actions")
        print(json.dumps(res, indent=2, default=str))
    if a.command in ("analyze", "all"):
        from app.services import analysis

        res = analysis.run_full_analysis(send_notifications=not a.no_notify)
        print(json.dumps(res, indent=2, default=str))
    if a.command == "digest":
        print(funnel.send_weekly_digest())
    if a.command in ("discover", "whynow"):
        from app.services import analysis
        from app import db as _db

        analysis.budget.reset()
        if a.command == "discover":
            print(json.dumps(analysis.discover_verticals(), indent=2, default=str))
        else:
            print(json.dumps({k["name"]: analysis.scan_why_now(k["id"]) for k in _db.list_all(_db.KEYWORD_SETS, is_active=True)}, indent=2, default=str))
    if a.command == "funnel":
        res = funnel.evaluate_all(send_notifications=not a.no_notify)
        print(json.dumps(res, indent=2, default=str))
    if a.command == "export":
        rows = export.export_rows(min_wtp=a.min_wtp)
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        with open(a.out, "w", encoding="utf-8", newline="") as f:
            f.write(export.to_csv(rows) if a.out.endswith(".csv") else export.to_json(rows))
        print(f"{len(rows)} rows -> {a.out}")


if __name__ == "__main__":
    main()
