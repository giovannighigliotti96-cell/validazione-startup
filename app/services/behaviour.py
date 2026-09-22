"""Friction report from the behaviour beacon (app.templates.landing.BEHAVIOR_JS): per page, how far people get,
which sections they reach, where they leave, what they click. Read by Claude to spot obvious friction."""
from __future__ import annotations

from collections import Counter
from datetime import timedelta

from app import db

PAGES = {"home": "home (link in bio)", "poltrona_libera_titolari": "landing titolari", "poltrona_libera_professioniste": "landing professioniste",
         "guida_squadra": "sales page A · dipendente andata via", "guida_poltrona": "sales page B · basta dipendenti", "catalogo": "catalogo postazioni"}


def report(days: int = 14) -> dict:
    client = db.get_db()
    since = db.now() - timedelta(days=days)
    out = {"days": days, "pages": {}}
    for pid, label in PAGES.items():
        sessions = [d.to_dict() for d in client.collection(db.PROBLEM_CLUSTERS).document(pid).collection("lp_sessions").stream()]
        sessions = [s for s in sessions if s.get("last_at") and s["last_at"] >= since]
        n = len(sessions)
        if not n:
            out["pages"][pid] = {"label": label, "sessions": 0}
            continue
        ev: Counter = Counter()
        exits: Counter = Counter()
        fields: Counter = Counter()
        by_utm: Counter = Counter()
        widths: Counter = Counter()
        for s in sessions:
            names = [e["e"] for e in s.get("events", [])]
            for e in set(names):
                ev[e] += 1
            secs = [e["e"][4:] for e in s.get("events", []) if e["e"].startswith("see_")]
            exits[secs[-1] if secs else "nessuna_sezione"] += 1
            for e in s.get("events", []):
                if e["e"].startswith("field_"):
                    fields[e["e"][6:]] += 1
            by_utm[s.get("utm") or "diretto"] += 1
            widths["mobile" if (s.get("width") or 0) < 700 else "desktop"] += 1

        def pct(k: str) -> float:
            return round(100 * ev.get(k, 0) / n, 1)

        out["pages"][pid] = {
            "label": label, "sessions": n, "mobile_share": round(100 * widths["mobile"] / n, 1),
            "scroll": {"25": pct("scroll25"), "50": pct("scroll50"), "75": pct("scroll75"), "100": pct("scroll100")},
            "time": {"10s": pct("time10"), "30s": pct("time30"), "60s": pct("time60"), "120s": pct("time120")},
            "sections_reached_pct": {k[4:]: pct(k) for k in ev if k.startswith("see_")},
            "last_section_before_leaving": dict(exits.most_common(8)),
            "cta_click_pct": pct("cta_click"), "form_start_pct": pct("form_start"), "form_submit_pct": pct("form_submit"),
            "fields_touched": dict(fields.most_common(10)), "by_source": dict(by_utm.most_common(10)),
        }
    return out
