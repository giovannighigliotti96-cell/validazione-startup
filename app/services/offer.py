"""
From validated PROBLEM to testable OFFER.

generate_offer(cluster_id)  -> 2-3 landing-page VARIANTS (angle, headline, price...) + pre-mortem, stored on opportunity_scoring.offer
The landing page (app/routers/landing.py) serves the variants A/B and records views/signups per variant into a
validation_experiment of type landing_page, so stage 7 metrics fill themselves. The market decides, not the model.
"""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from app import db
from app.services import analysis

log = analysis.log


class Variant(BaseModel):
    key: str = Field(description="A, B or C")
    angle: str = Field(description="The one bet this variant makes: e.g. 'time saved', 'errors avoided', 'compliance', 'money recovered'")
    headline: str = Field(description="Max 12 words, in the persona's own words (use vocabulary from the signals), no jargon")
    subheadline: str = Field(description="1-2 sentences: what it does, for whom, outcome")
    benefits: list[str] = Field(description="3 concrete benefits, each anchored to a pain from the signals")
    how_it_works: list[str] = Field(description="3 short steps")
    price_eur_month: float
    plan_name: str
    price_justification: str = Field(description="Why this price: vs verified competitor pricing and vs the cost of the pain")
    cta: str = Field(description="Button text, e.g. 'Pre-ordina a €39/mese' or 'Entra in lista con prezzo bloccato'")
    objections: list[dict] = Field(description="3 items {objection, answer}")
    ad_copies: list[dict] = Field(description="3 items {primary_text, headline} for Meta/Google smoke-test ads, <= 125 chars primary text")
    target_language: Literal["it", "en"] = Field(description="Language of the persona's market")


class PreMortem(BaseModel):
    top_risks: list[dict] = Field(description="3 items {risk, probability: low|medium|high, what_would_disprove_it: observable evidence from the landing/interviews}")
    platform_risk: str = Field(description="Could the platform/incumbent (e.g. Shopify, QuickBooks) absorb this natively? How soon?")
    kill_signal: str = Field(description="The single number from the landing test that, if below X, means stop")


class OfferResponse(BaseModel):
    solution_hypotheses: list[dict] = Field(description="2-3 items {name, what_it_does, differentiation_vs_competitors, why_this_one_or_not}")
    chosen_hypothesis: str
    variants: list[Variant] = Field(description="2-3 landing variants that test DIFFERENT angles or prices, not wording")
    premortem: PreMortem


OFFER_PROMPT = """You turn a validated PROBLEM into TESTABLE OFFERS for a landing-page smoke test run by a solo founder (Italy, marketing/sales background, builds software alone).
Do not write a positioning essay: write hypotheses the market can reject. Each variant must test a genuinely different bet (angle OR price OR persona slice), so results are informative.
Use the persona's own words from the signals. Anchor prices to the VERIFIED competitor prices and to the cost of the pain. Prefer self-serve pricing if the channel is a marketplace/SEO; a higher ticket if the founder must sell by hand.

PROBLEM: {statement}
PERSONA (has the pain): {persona} · BUYER (pays): {buyer}
VERTICAL: {vertical}
ATTACK VECTOR MIX: {attack}
SIGNALS (what people actually say):
{signals}
VERIFIED COMPETITORS (name · price/mo · notes):
{competitors}
ECONOMICS (from founder-fit): channel={channel} · expected price €{price}/mo · delivery={delivery} · margin={margin}
WHY NOW: {why_now}
"""


def generate_offer(cluster_id: str) -> dict:
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    o = db.get(db.OPPORTUNITY_SCORING, cluster_id) or {}
    if not c:
        raise ValueError("cluster not found")
    sigs = analysis._cluster_signals(cluster_id, limit=80)
    sample = "\n".join(f"- {(s.get('llm_problem_statement') or '')[:140]} || \"{(s.get('text') or '')[:160].replace(chr(10), ' ')}\"" for s in sigs[:20])
    comps = db.list_all(db.COMPETITOR_SIGNALS, cluster_id=cluster_id)
    comp_txt = "\n".join(f"- {x['name']} · {x.get('pricing_monthly_usd') or '?'} · {(x.get('notes') or x.get('tagline') or '')[:100]}" for x in comps[:8]) or "(none verified)"
    data = analysis.llm_json(OFFER_PROMPT.format(
        statement=c.get("problem_statement"), persona=c.get("persona"), buyer=o.get("buyer_persona") or c.get("persona"),
        vertical=c.get("vertical"), attack=json.dumps(c.get("attack_vector_dist") or {}), signals=sample, competitors=comp_txt,
        channel=o.get("acquisition_channel_type") or o.get("acquisition_channel") or "?", price=o.get("expected_price_eur_month") or "?",
        delivery=o.get("delivery_model") or "?", margin=o.get("gross_margin_pct") or "?", why_now=o.get("why_now") or "(none)",
    ), OfferResponse, strong=True, temperature=0.5)
    variants = data.get("variants") or []
    for i, v in enumerate(variants):
        v["key"] = "ABC"[i] if i < 3 else v.get("key", str(i))
    offer = {**data, "variants": variants, "generated_at": db.now(), "payment_link_url": (o.get("offer") or {}).get("payment_link_url"),
             "active_variants": [v["key"] for v in variants]}
    db.upsert(db.OPPORTUNITY_SCORING, cluster_id, {"offer": offer, "premortem": data.get("premortem")})
    try:
        landing_quotes(cluster_id, lang=(variants[0].get("target_language") if variants else "it") or "it")
    except Exception as e:  # noqa: BLE001
        log.warning("landing quotes failed: %s", e)
    return db.get(db.OPPORTUNITY_SCORING, cluster_id)["offer"]


class LandingQuotes(BaseModel):
    quotes: list[dict] = Field(description="3-5 items {quote, role, source}: the quote is a faithful, cleaned, translated rendering of a REAL signal (no page chrome, no URLs, no usernames); role = who said it (e.g. 'titolare di ristorante'); source = forum|reddit|youtube|review")


QUOTES_PROMPT = """Pick 3-5 signals that best express the pain of THIS persona, and render each as a short quote in {lang} for a landing page.
Rules: stay faithful to what the person wrote (translate, remove page chrome / links / usernames, trim), never invent, skip off-topic signals
(other industries), skip anything that mentions a competitor by name. Quotes must read as real people talking, first person.
PERSONA: {persona}
PROBLEM: {statement}
SIGNALS (source :: text):
{signals}
"""


def landing_quotes(cluster_id: str, lang: str = "it") -> list[dict]:
    c = db.get(db.PROBLEM_CLUSTERS, cluster_id)
    # public display never uses Reddit content (Data API Terms: no redistribution beyond the approved research use)
    sigs = [s for s in analysis._cluster_signals(cluster_id, limit=200) if s.get("llm_problem_statement") and not (s.get("llm_metadata") or {}).get("is_noise")
            and s.get("source") != "reddit" and s.get("text")]
    sigs.sort(key=lambda s: -((s.get("llm_urgency") or 0) + (s.get("heuristic_score") or 0)))
    txt = "\n".join(f"- {s.get('source')} :: {(s.get('text') or '')[:400].replace(chr(10), ' ')}" for s in sigs[:25])
    data = analysis.llm_json(QUOTES_PROMPT.format(lang="Italian" if lang == "it" else "English", persona=c.get("persona"), statement=c.get("problem_statement"), signals=txt),
                             LandingQuotes, strong=True, temperature=0.3)
    quotes = [q for q in data.get("quotes", []) if isinstance(q, dict) and len(q.get("quote", "")) > 30][:5]
    o = db.get(db.OPPORTUNITY_SCORING, cluster_id) or {}
    db.upsert(db.OPPORTUNITY_SCORING, cluster_id, {"offer": {**(o.get("offer") or {}), "quotes": quotes, "quotes_lang": lang}})
    return quotes
