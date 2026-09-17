"""
JUDICIAL LIQUIDATIONS (small companies) — the sourcing channel for affitto d'azienda from the curatore.

Source: "Portale dei Fallimenti" per tribunal (Fallco / Zucchetti), a public information portal for creditors and third
parties. For every liquidazione giudiziale (CCII): company, number/year, date of the judgment, CURATORE (the person who
decides on affitto/vendita of the business), giudice delegato, documents, virtual data room.
  Genova: https://fallimentigenova.com/index.php?where=ultime_procedure_dichiarate_mostra_tutte&altre=liquidazioni_ccii

Why it matters: within ~60 days of the judgment the curatore prepares the liquidation programme (art. 213 CCII) and
decides whether the business is kept running (affitto d'azienda, art. 212) or shut. A credible tenant who shows up in
that window, with a canone and a plan, is what a curatore hopes for. After that window, assets are sold piecemeal.

Collection `procedures` (doc id = tribunal_number_year). Weekly, 1-2 requests per tribunal.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from app import db
from app.scrapers.base import http_client, log

COLL = "procedures"
PORTALS = {"Genova": "https://fallimentigenova.com/", "Milano": "https://fallimentimilano.com/", "Savona": "https://fallimentisavona.com/",
           "Alessandria": "https://fallimentialessandria.com/"}
UA = {"User-Agent": "validazione-startup research bot (public insolvency lists; contact giovannighigliotti96@gmail.com)"}

# The founder's rule: only businesses whose MODEL is already validated — a product, a brand, B2B customers with contracts,
# distribution, technology. Not local manual services (bar, gelateria, parrucchiere, officina) and not real-estate shells.
VALIDATED = re.compile(r"fabbric|produz|industri|manifattur|software|tech|digital|informatic|e-?commerce|distribuz|ingross|import|export|logistic|trasport|"
                       r"meccan|elettron|elettr|chimic|plastic|packag|imballag|tessil|moda|brand|abbigliament|calzatur|alimentar|dolciar|farmac|medical|"
                       r"engineering|ingegner|impiant|energ|fotovolt|automaz|robot|stamp|editor|arred|\bmobili|nautic|naval|yacht|cosmet|vino|vinicol|caseific|fibr|fiber|cabl|telecom|"
                       r"lavorazion|serramen|infiss|metall|acciai|fonder|componen|ricambi|macchin|attrezzat|forniture", re.I)
LOCAL_MANUAL = re.compile(r"gelat|\bbar\b|caff[eè]|ristor|pizzer|trattor|osteria|\bpub\b|parrucch|barbier|estetic|\bnail\b|lavander|palestra|tabacch|edicola|"
                          r"ambulant|autofficin|carrozzer|gommist|pulizi|ponteggi|imbianch|idraulic|autolavagg|kebab|sushi|panific|pasticceria artigian", re.I)
SHELL = re.compile(r"immobiliar|holding|real estate|partecipazion|\bs\.\s?s\.|societ[àa] semplice|costruzioni immobiliari", re.I)
INDIVIDUAL = re.compile(r"\bdi [A-Z][a-z]+ [A-Z][a-z]+\b|titolare dell'impresa|ditta individuale", re.I)


def fetch(tribunal: str = "Genova") -> list[dict]:
    base = PORTALS[tribunal]
    with http_client(timeout=30) as c:
        c.headers.update(UA)
        r = c.get(base + "index.php?where=ultime_procedure_dichiarate_mostra_tutte&altre=liquidazioni_ccii")
    s = BeautifulSoup(r.text, "lxml")
    rows = s.find_all("tr")
    head = [th.get_text(" ", strip=True) for th in rows[0].find_all(["th", "td"])] if rows else []
    out = []
    for tr in rows[1:]:
        tds = tr.find_all("td")
        if len(tds) < 8:
            continue
        cells = [td.get_text(" ", strip=True) for td in tds]
        rec = dict(zip(head, cells))
        m = re.search(r"(\d+)/(\d{4})", rec.get("Num./Anno", ""))
        if not m:
            continue
        docs = next((a["href"] for a in tr.find_all("a", href=True) if "documenti" in a["href"]), None)
        vdr = next((a["href"] for a in tr.find_all("a", href=True) if "data_room" in a["href"] or "dataroom" in a["href"].lower()), None)
        try:
            dt = datetime.strptime(rec.get("Data dich.") or rec.get("Data pubb. sentenza") or "", "%d/%m/%Y").replace(tzinfo=timezone.utc)
        except ValueError:
            dt = None
        out.append({"tribunal": tribunal, "name": rec.get("Procedura", ""), "number": int(m.group(1)), "year": int(m.group(2)),
                    "declared_at": dt, "type": rec.get("Tipo"), "curatore": rec.get("Professionista"), "giudice": rec.get("Giudice Delegato"),
                    "n_docs": rec.get("Doc."), "status": rec.get("Stato"), "docs_url": (base + docs) if docs else None, "vdr_url": (base + vdr.lstrip("./")) if vdr else None,
                    "source_url": base + "index.php?altre=liquidazioni_ccii"})
    return out


def score(doc: dict) -> tuple[int, list[str]]:
    s, why = 0, []
    name = doc.get("name") or ""
    age = (datetime.now(timezone.utc) - doc["declared_at"]).days if doc.get("declared_at") else 999
    if age <= 45:
        s += 40; why.append(f"sentenza {age} giorni fa: il curatore sta decidendo se tenere in esercizio")
    elif age <= 90:
        s += 20; why.append(f"sentenza {age} giorni fa: programma di liquidazione in corso")
    else:
        why.append(f"sentenza {age} giorni fa: probabilmente già in vendita a pezzi")
    sec = (doc.get("activity") or "") + " " + name
    if VALIDATED.search(sec):
        s += 30; why.append("modello validato: prodotto/marchio/B2B/distribuzione")
    if LOCAL_MANUAL.search(sec):
        s -= 35; why.append("attività locale/manuale: fuori perimetro")
    if SHELL.search(name):
        s -= 40; why.append("veicolo immobiliare/holding: niente da gestire")
    if INDIVIDUAL.search(name) and not VALIDATED.search(sec):
        s -= 15; why.append("ditta individuale senza attività riconoscibile")
    fin = doc.get("financials") or {}
    rev = fin.get("revenue")
    if rev:
        if 300_000 <= rev <= 5_000_000:
            s += 20; why.append(f"fatturato €{int(rev):,}: taglia da affitto d'azienda")
        elif rev > 5_000_000:
            s += 5; why.append(f"fatturato €{int(rev):,}: serve capitale")
        else:
            s -= 10; why.append(f"fatturato €{int(rev):,}: troppo piccola")
    nr, rev2 = fin.get("net_result"), fin.get("revenue")
    if nr is not None and rev2 and nr < -0.15 * rev2:
        s -= 30; why.append(f"perdita {round(nr / rev2 * 100)}% dei ricavi: crisi strutturale, non finanziaria")
    if doc.get("vdr_url"):
        s += 10; why.append("data room aperta: vendita/affitto in corso")
    return max(0, min(100, s)), why


def refresh(tribunals: list[str] | None = None) -> dict:
    n_new = 0
    for t in tribunals or list(PORTALS):
        try:
            rows = fetch(t)
        except Exception as e:  # noqa: BLE001
            log.warning("procedures %s: %s", t, e); continue
        for r in rows:
            pid = f"{t}_{r['number']}_{r['year']}".lower()
            old = db.get(COLL, pid) or {}
            doc = {**old, **r}
            doc["score"], doc["score_reasons"] = score(doc)
            doc["updated_at"] = db.now()
            if not old:
                doc["first_seen"] = db.now(); n_new += 1
            db.upsert(COLL, pid, doc)
    return {"new": n_new}


def teaser(pid: str) -> dict:
    """Public activity + financial teaser (1 search): what the company did, revenue, employees."""
    from app.services import distressed, search

    doc = db.get(COLL, pid)
    if not doc:
        return {"error": "not found"}
    name = re.sub(r"\b(in liquidazione|unipersonale|s\.?r\.?l\.?s?|s\.?a\.?s\.?|s\.?n\.?c\.?|& c\.?)\b", " ", doc["name"], flags=re.I).strip()
    res = search.search(f"{name} {doc['tribunal']} fatturato dipendenti attività", max_results=8, purpose="enrich")
    blob = " ".join(f"{r.get('title') or ''} {r.get('content') or ''}" for r in res)
    low = blob.lower()
    fin = {k: (distressed._num(m.group(1)) if k != "year" else int(m.group(1))) for k, rx in distressed._FIN.items() if (m := re.search(rx, low, re.I))}
    act = re.search(r"(?:ateco|attivit[àa])[^:]{0,20}:?\s*([^.;|]{10,120})", low)
    upd = {"financials": fin, "activity": act.group(1).strip() if act else None, "news": [{"title": r.get("title"), "url": r.get("url")} for r in res[:5]], "enriched_at": db.now()}
    doc.update(upd)
    upd["score"], upd["score_reasons"] = score(doc)
    db.upsert(COLL, pid, upd)
    return upd


def top(n: int = 20, tribunal: str | None = None, max_age_days: int = 120) -> list[dict]:
    out = []
    for d in db.get_db().collection(COLL).stream():
        x = d.to_dict() | {"id": d.id}
        if tribunal and x.get("tribunal") != tribunal:
            continue
        if x.get("declared_at") and (datetime.now(timezone.utc) - x["declared_at"]).days > max_age_days:
            continue
        out.append(x)
    out.sort(key=lambda x: (-(x.get("score") or 0), -(x["declared_at"].timestamp() if x.get("declared_at") else 0)))
    return [{k: x.get(k) for k in ("id", "name", "tribunal", "number", "year", "declared_at", "curatore", "giudice", "score", "score_reasons", "activity", "financials", "docs_url", "vdr_url")} for x in out[:n]]


def run_weekly(max_teasers: int = 10) -> dict:
    from app.services import search

    r = refresh()
    done = []
    for x in top(30, max_age_days=60):
        if len(done) >= max_teasers or search.remaining("enrich") < 1:
            break
        if (db.get(COLL, x["id"]) or {}).get("enriched_at"):
            continue
        try:
            teaser(x["id"]); done.append(x["name"])
        except Exception as e:  # noqa: BLE001
            log.warning("teaser %s: %s", x["name"], e)
    r["teasers"] = done
    return r
