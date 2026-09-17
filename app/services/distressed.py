"""
DISTRESSED COMPANIES — sourcing the way turnaround / special-situations investors do, from OFFICIAL public sources.

Source 1 (live): Ministero del Lavoro, decreti CIGS (Cassa Integrazione Guadagni Straordinaria)
  https://www.lavoro.gov.it/temi-e-priorita/ammortizzatori-sociali/focus-on/cigs/pagine/elencocigs
  One Word-HTML page per fortnight, one row per decree: company, HQ, province, CAUSALE (why), unit, sector, date, period.
  This is the early-warning signal: a company under "Crisi aziendale" CIGS is alive, has workers, and is 12-24 months
  before a procedure — the window in which turnaround buyers act.

Collection `distressed_companies` (doc id = normalised company name):
  name, hq, province, sector, events[] (decrees), first_seen, last_seen, n_decrees, causali{}, cessazione, score, score_reasons[]

Scoring (turnaround lens, all from public facts; financials come later, paid, only for the shortlist):
  +  "Crisi aziendale" (financial/market distress declared)        -> the target profile
  +  repeated decrees over 12+ months                               -> chronic, owner likely exhausted = negotiable
  +  "Riorganizzazione" with solidarietà                            -> restructuring already underway (cheaper to fix)
  +  manufacturing / B2B sectors with assets, brands, certifications
  -  "Cessazione di attività"                                       -> too late (liquidation), asset deal only
  -  very recent single decree with solidarietà only                -> could be a normal dip
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from app import db
from app.scrapers.base import http_client, log, polite_sleep

COLL = "distressed_companies"
INDEX = "https://www.lavoro.gov.it/temi-e-priorita/ammortizzatori-sociali/focus-on/cigs/pagine/elencocigs"
UA = {"User-Agent": "validazione-startup research bot (public CIGS decrees; contact giovannighigliotti96@gmail.com)"}

# field order varies between rows (Unità/Settore may swap): parse each label independently
_FIELDS = {
    "name": r"Denominazione azienda:\s*(.+?)\s*(?=Con sede in:)",
    "hq": r"Con sede in:\s*(.+?)\s*Prov\s*:\s*([A-Z]{2})",
    "causale": r"Causale di Intervento:\s*(.+?)\s*(?=Unità di:|Settore:|Decreto del:)",
    "unit": r"Unità di:\s*(.+?)\s*Prov\s*:\s*([A-Z]{2})",
    "sector": r"Settore:\s*(.+?)\s*(?=Unità di:|Decreto del:)",
    "decree": r"Decreto del:\s*(\d{2}/\d{2}/\d{4})\s*N\.\s*(\d+)\s*(.*)$",
}
_RX = {k: re.compile(v, re.S) for k, v in _FIELDS.items()}
_PERIOD = re.compile(r"dal:?\s*(\d{2}/\d{2}/\d{4})\s*al\s*(\d{2}/\d{2}/\d{4})")


def _norm(name: str) -> str:
    n = re.sub(r"\b(S\.?R\.?L\.?|S\.?P\.?A\.?|S\.?A\.?S\.?|S\.?N\.?C\.?|SOC\.? COOP\.?|SOCIETA'? COOPERATIVA|IN LIQUIDAZIONE|UNIPERSONALE)\b", " ", name.upper())
    return re.sub(r"[^A-Z0-9]+", "_", n).strip("_")[:80]


def list_pages() -> list[tuple[str, str]]:
    with http_client(timeout=30) as c:
        c.headers.update(UA)
        s = BeautifulSoup(c.get(INDEX).text, "lxml")
        out = []
        for a in s.find_all("a", href=True):
            if "/decreti-cigs/" in a["href"]:
                out.append((a.get_text(" ", strip=True), "https://www.lavoro.gov.it" + a["href"] if a["href"].startswith("/") else a["href"]))
        return out


def parse_page(url: str) -> list[dict]:
    with http_client(timeout=40) as c:
        c.headers.update(UA)
        r = c.get(url)
        raw = r.content
        html = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else r.text
    s = BeautifulSoup(html, "lxml")
    t = s.find("table")
    rows = []
    for tr in (t.find_all("tr") if t else []):
        txt = re.sub(r"\s+", " ", tr.get_text(" ", strip=True))
        m = {k: rx.search(txt) for k, rx in _RX.items()}
        if not (m["name"] and m["decree"] and m["causale"]):
            continue
        rest = m["decree"].group(3) or ""
        per = _PERIOD.search(rest)
        causale = m["causale"].group(1).strip()
        rows.append({"name": m["name"].group(1).strip(), "hq": m["hq"].group(1).strip() if m["hq"] else "", "prov": m["hq"].group(2) if m["hq"] else "",
                     "causale": causale, "unit": m["unit"].group(1).strip() if m["unit"] else "", "unit_prov": m["unit"].group(2) if m["unit"] else "",
                     "sector": m["sector"].group(1).strip() if m["sector"] else "", "date": m["decree"].group(1), "num": m["decree"].group(2),
                     "period_from": per.group(1) if per else None, "period_to": per.group(2) if per else None,
                     "cessazione": bool(re.search(r"cessazion", causale + rest, re.I)),
                     "annullamento": bool(re.search(r"annullamento|revoca", rest, re.I)),
                     "note": rest[:200], "page": url})
    return rows


SECTOR_PLUS = re.compile(r"fabbricazione|produzione|metall|meccan|tessil|alimentar|chimic|farmac|plastic|elettr|legno|mobili|carta|vetro|ceramic|calzatur|pelletter|gomma|macchin|lavorazione", re.I)
SECTOR_MINUS = re.compile(r"call center|somministrazione|interinal|pulizia|vigilanza|logistica conto terzi|commercio al dettaglio", re.I)


def score(doc: dict) -> tuple[int, list[str]]:
    s, why = 0, []
    caus = doc.get("causali") or {}
    if any("crisi" in k.lower() for k in caus):
        s += 40; why.append("CIGS per crisi aziendale dichiarata")
    if any("riorganizz" in k.lower() for k in caus):
        s += 20; why.append("riorganizzazione in corso")
    if any("solidariet" in k.lower() for k in caus) and len(caus) == 1 and doc.get("n_decrees", 0) == 1:
        s -= 10; why.append("solo solidarietà, un decreto: può essere un calo temporaneo")
    n = doc.get("n_decrees") or 0
    if n >= 3:
        s += 15; why.append(f"{n} decreti: situazione cronica, proprietà logorata")
    span = doc.get("span_days") or 0
    if span >= 365:
        s += 10; why.append(f"in CIGS da {span // 30} mesi")
    if doc.get("cessazione"):
        s -= 40; why.append("cessazione di attività: solo asset deal in procedura")
    sec = doc.get("sector") or ""
    if SECTOR_PLUS.search(sec):
        s += 15; why.append("manifatturiero: asset, marchio, know-how, base clienti")
    if SECTOR_MINUS.search(sec):
        s -= 15; why.append("settore labour-only: poco da comprare")
    units = len(doc.get("units") or [])
    if units >= 2:
        s += 5; why.append(f"{units} unità produttive")
    return max(0, min(100, s)), why


def refresh(max_pages: int | None = None) -> dict:
    pages = list_pages()
    if max_pages:
        pages = pages[:max_pages]
    client = db.get_db()
    seen_pages = {d.id for d in client.collection("distressed_pages").select([]).stream()}
    companies: dict[str, dict] = {d.id: d.to_dict() for d in client.collection(COLL).stream()}
    new_rows = 0
    for label, url in pages:
        pid = re.sub(r"\W+", "_", url.rsplit("/", 1)[-1])
        if pid in seen_pages and label != pages[0][0]:  # always re-read the newest list (it grows within the fortnight)
            continue
        try:
            rows = parse_page(url)
        except Exception as e:  # noqa: BLE001
            log.warning("cigs page %s: %s", url, e); continue
        for r in rows:
            key = _norm(r["name"])
            if not key:
                continue
            doc = companies.setdefault(key, {"name": r["name"], "hq": r["hq"], "province": r["prov"], "sector": r["sector"],
                                             "events": [], "units": [], "causali": {}, "first_seen": None, "last_seen": None})
            ev_id = r["num"] + "_" + r["date"]
            if any(e.get("id") == ev_id for e in doc["events"]):
                continue
            doc["events"].append({"id": ev_id, "date": r["date"], "num": r["num"], "causale": r["causale"], "unit": f"{r['unit']} ({r['unit_prov']})",
                                  "period_from": r["period_from"], "period_to": r["period_to"], "cessazione": r["cessazione"], "annullamento": r["annullamento"],
                                  "note": r["note"], "source_url": url})
            new_rows += 1
        client.collection("distressed_pages").document(pid).set({"label": label, "url": url, "rows": len(rows), "read_at": db.now()})
        polite_sleep()
    # aggregate + score
    written = 0
    for key, doc in companies.items():
        evs = [e for e in doc["events"] if not e.get("annullamento")]
        if not evs:
            continue
        dates = sorted(datetime.strptime(e["date"], "%d/%m/%Y").replace(tzinfo=timezone.utc) for e in evs)
        doc["units"] = sorted({e["unit"] for e in evs})
        doc["causali"] = {}
        for e in evs:
            doc["causali"][e["causale"][:60]] = doc["causali"].get(e["causale"][:60], 0) + 1
        doc["n_decrees"] = len(evs)
        doc["first_seen"], doc["last_seen"] = dates[0], dates[-1]
        doc["span_days"] = (dates[-1] - dates[0]).days
        doc["cessazione"] = any(e.get("cessazione") for e in evs)
        doc["score"], doc["score_reasons"] = score(doc)
        doc["updated_at"] = db.now()
        client.collection(COLL).document(key).set(doc)
        written += 1
    return {"pages": len(pages), "new_decrees": new_rows, "companies": written}


def top(n: int = 25, province: str | None = None, min_score: int = 40) -> list[dict]:
    docs = [d.to_dict() | {"id": d.id} for d in db.get_db().collection(COLL).stream()]
    docs = [d for d in docs if (d.get("score") or 0) >= min_score and (not province or d.get("province") == province)]
    docs.sort(key=lambda d: (-(d.get("score") or 0), -(d.get("n_decrees") or 0)))
    return [{k: d.get(k) for k in ("id", "name", "hq", "province", "sector", "score", "score_reasons", "n_decrees", "causali", "first_seen", "last_seen", "units", "news_stage", "news")} for d in docs[:n]]


# ----------------------------------------------------------------------------
# Stage 2: what is publicly known beyond the decree (news) — 1 search per company, budgeted
# ----------------------------------------------------------------------------
_SIGNALS = {
    "procedura": r"concordato|liquidazione giudiziale|fallimento|composizione negoziata|amministrazione straordinaria|tribunale",
    "cessione": r"cession|vendita|acquisi|rilev|offerta vincolante|manifestazione di interesse|bando",
    "investitore": r"fondo|private equity|turnaround|investitor|nuovo socio|ricapitalizz",
    "chiusura": r"chiusura|licenziament|cessazione|delocalizz",
    "rilancio": r"rilancio|piano industriale|accordo sindacale|nuovi ordini|commesse",
}


def enrich(company_id: str) -> dict:
    from app.services import search

    doc = db.get(COLL, company_id)
    if not doc:
        return {"error": "not found"}
    q = f"{doc['name']} {doc.get('hq') or ''} crisi OR concordato OR cessione OR cassa integrazione"
    res = search.search(q, max_results=8, days=365, purpose="enrich")
    news = [{"title": r.get("title"), "url": r.get("url"), "snippet": (r.get("content") or "")[:300]} for r in res if r.get("url")]
    blob = " ".join(f"{n['title']} {n['snippet']}" for n in news).lower()
    flags = {k: bool(re.search(v, blob)) for k, v in _SIGNALS.items()}
    stage = ("in procedura" if flags["procedura"] else "in cessione" if flags["cessione"] else "investitore presente" if flags["investitore"]
             else "chiusura annunciata" if flags["chiusura"] else "rilancio in corso" if flags["rilancio"] else "nessuna notizia pubblica")
    db.upsert(COLL, company_id, {"news": news[:6], "news_flags": flags, "news_stage": stage, "enriched_at": db.now()})
    return {"stage": stage, "news": len(news), "flags": flags}


def enrich_top(n: int = 15, min_score: int = 55) -> dict:
    from app.services import search

    done = []
    for d in top(n * 2, min_score=min_score):
        if len(done) >= n or search.remaining("enrich") < 1:
            break
        if (db.get(COLL, d["id"]) or {}).get("enriched_at"):
            continue
        try:
            done.append((d["name"], enrich(d["id"])["stage"]))
        except Exception as e:  # noqa: BLE001
            log.warning("distressed enrich %s: %s", d["name"], e)
    return {"enriched": done}


def run_weekly() -> dict:
    r = refresh()
    r["fresh"] = qualify_fresh()   # first: recent companies are the ones worth a negotiation
    r["enrich"] = enrich_top()
    return r


# ----------------------------------------------------------------------------
# Stage 3: FRESH targets + public financial teaser + buyer gate
# "Fresh" = first decree in the last N days: the owner is still negotiating, the brand is not burnt yet.
# Financial teaser = revenue / net result / personnel cost / employees as shown on public company-data pages
# (search-engine snippets of Registro Imprese-derived data). The full balance sheet is bought (EUR 3-6) only for
# companies that pass the gate.
# ----------------------------------------------------------------------------
_FIN = {
    "revenue": r"fatturato[^0-9€]{0,20}€?\s*([\d.]{5,})",
    "net_result": r"(?:risultato d'esercizio|utile netto|utile/perdita|utile)[^0-9€\-]{0,25}(-?\s?€?\s*-?[\d.]{3,})",
    "personnel_cost": r"costo del personale[^0-9€]{0,20}€?\s*([\d.]{4,})",
    "employees": r"dipendenti[^0-9]{0,25}(?:da\s*)?(\d{1,5})",
    "year": r"\((20\d\d)\)",
}


def _num(x: str | None) -> float | None:
    if not x:
        return None
    neg = "-" in x
    d = re.sub(r"[^\d]", "", x)
    return (-1 if neg else 1) * float(d) if d else None


def financial_teaser(company_id: str) -> dict:
    from app.services import search

    doc = db.get(COLL, company_id)
    if not doc:
        return {"error": "not found"}
    q = f"{doc['name']} {doc.get('hq') or ''} fatturato bilancio dipendenti"
    res = search.search(q, max_results=8, purpose="enrich")
    blob = " ".join(f"{r.get('title') or ''} {r.get('content') or ''}" for r in res)
    low = blob.lower()
    fin: dict = {}
    for k, rx in _FIN.items():
        m = re.search(rx, low, re.I)
        if m:
            fin[k] = _num(m.group(1)) if k != "year" else int(m.group(1))
    fin["sources"] = [r.get("url") for r in res if r.get("url") and re.search(r"fatturato|bilanc|dipendent", (r.get("content") or "").lower())][:4]
    fin["fetched_at"] = db.now()
    db.upsert(COLL, company_id, {"financials": fin})
    return fin


def buyer_gate(doc: dict) -> tuple[bool, list[str]]:
    """The parameters a distressed-M&A operator checks in the first 5 minutes, from public data only."""
    fin = doc.get("financials") or {}
    checks: list[tuple[bool, str]] = []
    rev = fin.get("revenue")
    checks.append((rev is not None and rev >= 2_000_000, f"fatturato {'€' + format(int(rev), ',') if rev else 'n/d'} (>= €2M)"))
    emp = fin.get("employees")
    checks.append((emp is not None and emp >= 10, f"dipendenti {emp if emp is not None else 'n/d'} (>= 10)"))
    nr = fin.get("net_result")
    checks.append((nr is not None and nr > -0.05 * (rev or 1), f"risultato {'€' + format(int(nr), ',') if nr is not None else 'n/d'} (perdita < 5% ricavi = crisi finanziaria, non strutturale)"))
    pc = fin.get("personnel_cost")
    checks.append((not (pc and rev) or pc / rev <= 0.45, f"personale/ricavi {round(pc / rev * 100) if (pc and rev) else 'n/d'}% (<= 45%)"))
    checks.append((not doc.get("cessazione"), "nessuna cessazione di attività"))
    checks.append((any("crisi" in k.lower() or "riorganizz" in k.lower() for k in (doc.get("causali") or {})), "causale: crisi o riorganizzazione"))
    checks.append((bool(SECTOR_PLUS.search(doc.get("sector") or "")) and not SECTOR_MINUS.search(doc.get("sector") or ""), "settore con asset/clienti B2B"))
    checks.append((doc.get("news_stage") not in ("in procedura", "chiusura annunciata"), f"stato pubblico: {doc.get('news_stage') or 'non verificato'} (non in procedura)"))
    return all(ok for ok, _ in checks), [("✔ " if ok else "✘ ") + t for ok, t in checks]


def fresh(days: int = 45, min_score: int = 40) -> list[dict]:
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    out = []
    for d in db.get_db().collection(COLL).stream():
        x = d.to_dict() | {"id": d.id}
        fs = x.get("first_seen")
        if not fs or fs.timestamp() < cutoff or (x.get("score") or 0) < min_score or x.get("cessazione"):
            continue
        ok, checks = buyer_gate(x)
        out.append({k: x.get(k) for k in ("id", "name", "hq", "province", "sector", "score", "n_decrees", "causali", "first_seen", "news_stage", "financials")} | {"passes_gate": ok, "gate": checks})
    out.sort(key=lambda r: (not r["passes_gate"], -(r.get("score") or 0)))
    return out


def qualify_fresh(days: int = 45, max_companies: int = 12) -> dict:
    """Weekly: fresh targets -> news + financial teaser (2 searches each) -> gate. Budgeted."""
    from app.services import search

    done = []
    for r in fresh(days):
        if len(done) >= max_companies or search.remaining("enrich") < 2:
            break
        doc = db.get(COLL, r["id"]) or {}
        if doc.get("financials") and doc.get("enriched_at"):
            continue
        try:
            if not doc.get("enriched_at"):
                enrich(r["id"])
            financial_teaser(r["id"])
            ok, checks = buyer_gate(db.get(COLL, r["id"]) or {})
            done.append((r["name"], ok))
        except Exception as e:  # noqa: BLE001
            log.warning("qualify %s: %s", r["name"], e)
    return {"qualified": done}
