"""
DEAL LAYER — what an operator does in the first hour on a target, automated and honest:

  1. diagnose()     cause of the crisis from public numbers only: evento | finanziaria | commerciale | strutturale | ignota
                    (deterministic rules; the LLM only writes the narrative and never adds facts)
  2. feasibility()  "feasible at zero?" calculator for an affitto d'azienda: canone, guarantee, working capital,
                    what public instruments cover (NASpI anticipata, CFI/Marcora), and the GAP a partner must fill
  3. timers()       days since the decree / judgment, next milestone, alert level (the window is the edge)
  4. outputs()      three documents from the SAME facts: PEC (honest, in the founder's real voice), 1-page teaser
                    for financial/industrial partners, feasibility sheet. Unknowns stay "[da verificare]".

Everything is stored on the target doc under `deal` and re-generated on demand. Estimates are labelled as such.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app import db
from app.services import analysis

# Founder facts used in every output — nothing here is invented (see FOUNDER_PROFILE in analysis.py)
FOUNDER = {
    "name": "Giovanni Ghigliotti", "base": "Arenzano (GE)", "age": 30,
    "background": "imprenditore: ha fondato e ceduto una piattaforma digitale nel settore sportivo; commerciale e marketing",
    "capital": "nessun capitale proprio da investire; struttura con partner industriali/finanziari, affitto d'azienda o workers' buyout",
}

AVG_EMPLOYEE_COST = 38_000     # EUR/year, Italian manufacturing/services average incl. contributions
NASPI_ADVANCE_AVG = 20_000     # EUR per worker joining a cooperative (anticipo NASpI, indicative)
NASPI_JOIN_SHARE = 0.4         # share of workers realistically joining a workers' buyout
CFI_MATCH = 1.0                # CFI (Legge Marcora) typically matches members' capital ~1:1 (up to 2:1 in some cases)


def _f(fin: dict, k: str) -> float | None:
    v = (fin or {}).get(k)
    return float(v) if isinstance(v, (int, float)) else None


# ----------------------------------------------------------------------------
# 1. diagnosis
# ----------------------------------------------------------------------------
def diagnose(target: dict) -> dict:
    fin = target.get("financials") or {}
    rev, prev, nr, pc, emp = _f(fin, "revenue"), _f(fin, "revenue_prev"), _f(fin, "net_result"), _f(fin, "personnel_cost"), _f(fin, "employees")
    ev: list[str] = []
    growth = (rev - prev) / prev if (rev and prev) else None
    margin = nr / rev if (rev and nr is not None) else None
    pshare = (pc / rev) if (pc and rev) else ((emp * AVG_EMPLOYEE_COST) / rev if (emp and rev) else None)
    if growth is not None:
        ev.append(f"ricavi {'+' if growth >= 0 else ''}{growth * 100:.0f}% sull'anno precedente")
    if margin is not None:
        ev.append(f"risultato netto {margin * 100:.1f}% dei ricavi")
    if pshare is not None:
        ev.append(f"costo del personale ≈ {pshare * 100:.0f}% dei ricavi" + ("" if pc else " (stimato da n. addetti)"))
    kind = target.get("kind")
    if kind == "cigs":
        ev.append("CIGS per " + ", ".join((target.get("causali") or {}).keys())[:80])
    if target.get("news_stage") and target["news_stage"] != "nessuna notizia pubblica":
        ev.append(f"stampa: {target['news_stage']}")

    if margin is not None and margin < -0.15 or (pshare is not None and pshare > 0.6):
        cause, conf = "strutturale", "alta" if margin is not None else "media"
        note = "perde troppo o il lavoro costa troppo rispetto ai ricavi: il modello non regge, si compra solo il ramo/marchio in procedura"
    elif growth is not None and growth >= 0.05 and (margin is None or margin >= 0):
        cause, conf = "evento", "media"
        note = "cresceva e guadagnava: la crisi è uno shock recente (cliente/commessa persa, credito non incassato, fido ritirato). Il profilo migliore"
    elif growth is not None and growth <= -0.10 and (margin is None or margin >= -0.05):
        cause, conf = "commerciale", "media"
        note = "ricavi in calo con costi sotto controllo: il prodotto c'è, mancano le vendite. È il caso in cui un operatore commerciale è il piano"
    elif margin is not None and -0.15 <= margin < -0.05:
        cause, conf = "finanziaria", "bassa"
        note = "perdita contenuta: probabile problema di debito/circolante; decide la PFN dal bilancio"
    else:
        cause, conf = "ignota", "bassa"
        note = "dati pubblici insufficienti: servono bilancio e una telefonata"
    verify = ["bilancio completo: PFN, patrimonio netto, crediti/magazzino, debiti banche-fornitori-Erario",
              "concentrazione clienti (top 3 = ?% dei ricavi)", "cosa è successo negli ultimi 12 mesi (una domanda alla proprietà/curatore)",
              "contratti in essere: locazione, leasing, clienti pluriennali", "chi altro sta guardando (manifestazioni di interesse, data room)"]
    return {"cause": cause, "confidence": conf, "note": note, "evidence": ev, "verify": verify, "growth": growth, "margin": margin, "personnel_share": pshare}


# ----------------------------------------------------------------------------
# 2. feasibility at zero
# ----------------------------------------------------------------------------
def feasibility(target: dict) -> dict:
    fin = target.get("financials") or {}
    rev, emp, pc = _f(fin, "revenue"), _f(fin, "employees"), _f(fin, "personnel_cost")
    if not rev:
        return {"feasible_at_zero": None, "note": "senza fatturato pubblico non si stima nulla"}
    emp = emp or max(1.0, round(rev / 120_000))
    payroll_m = (pc or emp * AVG_EMPLOYEE_COST) / 12
    canone_m = round(rev * 0.006)                    # ~7% of revenue/year: typical range for an affitto from a procedure
    guarantee = canone_m * 3                         # 3 months, bank or insurance fideiussione
    purchases_m = rev * 0.35 / 12                    # materials/services, paid upfront by suppliers of a distressed company
    working_capital = round(2 * payroll_m + 1.5 * purchases_m)
    need = guarantee + working_capital
    wbo_members = int(emp * NASPI_JOIN_SHARE)
    naspi = wbo_members * NASPI_ADVANCE_AVG
    cfi = naspi * CFI_MATCH
    covered = naspi + cfi
    gap = max(0, need - covered)
    struct = ("workers' buyout (cooperativa dei lavoratori + CFI) con te come direttore" if wbo_members >= 5 and gap <= 0.3 * need
              else "affitto d'azienda con socio garante/capitalizzatore; tu operatore con quota" if need <= 250_000
              else "solo con partner industriale o fondo: la taglia supera un affitto a capitale zero")
    return {"employees_est": emp, "monthly_payroll": round(payroll_m), "canone_month": canone_m, "guarantee": guarantee,
            "working_capital_3m": working_capital, "cash_needed": round(need), "wbo_members": wbo_members, "naspi_advance": naspi, "cfi_match": cfi,
            "public_instruments_cover": round(covered), "gap_for_partner": round(gap), "feasible_at_zero": gap <= 0.3 * need, "structure": struct,
            "assumptions": "stime: canone 7% ricavi/anno, garanzia 3 mesi, circolante = 2 mesi stipendi + 1,5 mesi acquisti (35% ricavi), NASpI anticipata €20k × 40% degli addetti, CFI 1:1",
            "caveat": "il workers' buyout richiede che i lavoratori vengano licenziati (procedura o accordo con la proprietà) e aderiscano alla cooperativa: 6-12 mesi, centrali cooperative a supporto. 'Fattibile a zero' vale sulla carta, non per domani"}


# ----------------------------------------------------------------------------
# 3. timers
# ----------------------------------------------------------------------------
def timers(target: dict) -> dict:
    now = datetime.now(timezone.utc)
    if target.get("kind") == "cigs":
        start = target.get("first_seen")
        days = (now - start).days if start else None
        window = 90
        stage = ("proprietà ancora al comando: trattativa diretta" if days is not None and days <= 90 else
                 "piano CIGS in corso: la proprietà ha già scelto la sua strada, serve un'offerta concreta" if days is not None and days <= 240 else
                 "fine CIGS vicina: o rilancio o procedura")
    else:
        start = target.get("declared_at")
        days = (now - start).days if start else None
        window = 60
        stage = ("curatore sta scrivendo il programma di liquidazione: finestra per l'affitto d'azienda" if days is not None and days <= 60 else
                 "programma depositato: chiedere se è previsto esercizio provvisorio/affitto" if days is not None and days <= 120 else
                 "vendita a lotti probabile: solo marchio/attrezzature")
    alert = "rosso" if days is not None and days >= window else "giallo" if days is not None and days >= window * 0.6 else "verde"
    return {"days_since": days, "window_days": window, "stage": stage, "alert": alert, "next_milestone_in": (window - days) if days is not None else None}


# ----------------------------------------------------------------------------
# 4. outputs
# ----------------------------------------------------------------------------
class PecDoc(BaseModel):
    pec_subject: str
    pec_body: str = Field(description="Italian, formal, 12-18 lines, first person as the founder. ONLY the public facts given. No internal estimates, no jargon, no claims of experience, no 'advisor', no invented numbers.")
    questions_first_call: list[str] = Field(description="6 questions for the 30-minute call, ordered by what decides the deal")


class TeaserDoc(BaseModel):
    teaser: str = Field(description="One-page teaser in Italian for a financial/industrial partner: situazione, numeri pubblici, diagnosi, struttura ipotizzata, fabbisogno (stime, etichettate), prossimi passi. Markdown headings.")


PEC_PROMPT = """Scrivi una PEC per un contatto REALE con un'azienda in difficoltà. Usa SOLO i fatti pubblici sotto; se un dato non c'è, scrivi "[da verificare]".
Chi scrive: {founder}. NON è un advisor, NON ha esperienza da dichiarare, NON ha capitale proprio: non farlo sembrare un professionista o un investitore.
Può dire con verità: imprenditore, ha fondato e ceduto una piattaforma digitale nel settore sportivo, lavora nel commerciale, si muove con partner
industriali/finanziari e con gli strumenti di continuità previsti dalla legge (affitto d'azienda, coinvolgimento dei lavoratori).
Obiettivo della PEC: ottenere un incontro di 30 minuti. Tono diretto, rispettoso, concreto. Mai la parola "fallimento". Nessuna cifra che non sia nei fatti.
NON citare stime di fabbisogno, strumenti finanziari specifici, percentuali di copertura, "alert", "finestra", né proposte dettagliate: quelle vengono dopo.

DESTINATARIO: {recipient}
AZIENDA: {name} — {place} — {sector}
FATTI PUBBLICI (ricavi = ultimo anno; ricavi_anno_precedente = anno prima): {facts}
"""

TEASER_PROMPT = """Scrivi un teaser di una pagina in italiano per un partner finanziario/industriale su questa azienda in difficoltà. Usa SOLO i fatti sotto;
le stime vanno indicate come "stima interna". Chi presenta: {founder} (ruolo proposto: operatore/direttore commerciale con quota, non investitore).
AZIENDA: {name} — {place} — {sector}
FATTI PUBBLICI: {facts}
DIAGNOSI (dai numeri): causa {cause} ({confidence}) — {note}
FABBISOGNO (stime interne): {feas}
TEMPI: {timers}
"""


def outputs(target: dict, diag: dict, feas: dict, tm: dict) -> dict:
    kind = target.get("kind")
    recipient = (f"il curatore della liquidazione giudiziale, {target.get('curatore')}, Tribunale di {target.get('tribunal')} (n. {target.get('number')}/{target.get('year')})"
                 if kind == "procedure" else "l'amministratore/la proprietà dell'azienda (PEC aziendale)")
    fin = target.get("financials") or {}
    labels = {"revenue": "ricavi", "revenue_prev": "ricavi_anno_precedente", "net_result": "risultato_netto", "personnel_cost": "costo_personale", "employees": "dipendenti", "year": "anno_bilancio"}
    facts = {labels[k]: fin.get(k) for k in labels if fin.get(k) is not None}
    if kind == "cigs":
        facts["cigs"] = {e.get("date"): f"{e.get('causale')} {e.get('period_from') or ''}-{e.get('period_to') or ''}" for e in (target.get("events") or [])[-3:]}
    else:
        facts["sentenza"] = str(target.get("declared_at"))[:10]
        facts["attività"] = target.get("activity")
    facts["stampa"] = target.get("news_stage")
    common = dict(founder=FOUNDER, name=target.get("name"), place=target.get("hq") or target.get("tribunal"), sector=target.get("sector") or target.get("activity") or "[da verificare]", facts=facts)
    pec = analysis.llm_json(PEC_PROMPT.format(recipient=recipient, **common), PecDoc, strong=True, temperature=0.3)
    tz = analysis.llm_json(TEASER_PROMPT.format(cause=diag["cause"], confidence=diag["confidence"], note=diag["note"],
                                                feas={k: feas.get(k) for k in ("cash_needed", "public_instruments_cover", "gap_for_partner", "structure", "caveat")}, timers=tm, **common),
                           TeaserDoc, strong=True, temperature=0.3)
    data = {**pec, **tz}
    # hard guard: never let the model claim what the founder is not
    for k in ("pec_body", "teaser"):
        data[k] = re.sub(r"(advisor|consulente|nella mia esperienza|esperienza pluriennale|il nostro fondo|investitore)", "[rimosso: claim non vero]", data.get(k) or "", flags=re.I)
    return data


def build(kind: str, target_id: str, with_docs: bool = True) -> dict:
    coll = "distressed_companies" if kind == "cigs" else "procedures"
    t = db.get(coll, target_id)
    if not t:
        return {"error": "not found"}
    t["kind"] = kind
    diag, feas, tm = diagnose(t), feasibility(t), timers(t)
    deal: dict[str, Any] = {"diagnosis": diag, "feasibility": feas, "timers": tm, "built_at": db.now()}
    if with_docs:
        try:
            deal["docs"] = outputs(t, diag, feas, tm)
        except Exception as e:  # noqa: BLE001
            deal["docs_error"] = str(e)[:200]
    db.upsert(coll, target_id, {"deal": deal})
    return deal
